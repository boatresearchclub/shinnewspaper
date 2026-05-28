#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
boatrace_analyzer.py
====================
起動時に sample.js を読み込み、Node.js 経由で買い目ロジックを実行して
直近 30 日の AI 予想成績を集計・表示するスクリプト。

使い方:
    python boatrace_analyzer.py [sample.jsのパス]

引数省略時は、スクリプトと同じフォルダにある sample.js を使用。
data/ フォルダも同じフォルダに置いてください。
"""

import os
import sys
import json
import re
import subprocess
import tempfile
import textwrap
from pathlib import Path
from datetime import datetime, timedelta

# ════════════════════════════════════════════════════════
#  設定
# ════════════════════════════════════════════════════════

# sample.js のパス（引数で上書き可）
DEFAULT_JS_PATH = Path(__file__).parent / "sample.js"

# 集計対象日数
DAYS_TO_COLLECT = 30

# 除外会場
EXCLUDED_VENUES = {"江戸川"}

# 合成オッズ基準
SYNTH_MIN = {"hit": 2.5, "rec": 4.0}

# 買い目上限点数
BUY_MAX_POINTS = 10

# ════════════════════════════════════════════════════════
#  ターミナル出力ユーティリティ
# ════════════════════════════════════════════════════════

RESET  = "\033[0m"
BOLD   = "\033[1m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
DIM    = "\033[2m"
WHITE  = "\033[97m"
BLUE   = "\033[94m"

def color(text, *codes):
    return "".join(codes) + str(text) + RESET

def rate_color(rate):
    if rate >= 0.70: return GREEN
    if rate >= 0.50: return YELLOW
    return RED

def recovery_color(rate):
    if rate >= 1.00: return GREEN
    if rate >= 0.75: return YELLOW
    return RED

def bar(rate, width=20, char="█"):
    filled = int(rate * width)
    empty  = width - filled
    return char * filled + DIM + "░" * empty + RESET

# ════════════════════════════════════════════════════════
#  sample.js 読み込み・Node.js 経由でロジック抽出
# ════════════════════════════════════════════════════════

def load_js_logic(js_path: Path) -> str:
    """sample.js を読み込んで文字列で返す。"""
    if not js_path.exists():
        raise FileNotFoundError(f"sample.js が見つかりません: {js_path}")
    return js_path.read_text(encoding="utf-8")

def check_node():
    """Node.js が使えるか確認。"""
    try:
        result = subprocess.run(
            ["node", "--version"],
            capture_output=True, timeout=10,
            encoding="utf-8", errors="replace"
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None

def extract_buy_logic_via_node(js_src: str, venue_data_json: str,
                                result_data_json: str, odds_data_json: str,
                                master_ext_json: str, tenji_data_json: str,
                                mode: str = "hit") -> list:
    """
    Node.js で sample.js の買い目生成ロジック（computeBuy3）を実行し、
    集計結果リストを返す。
    返り値: [{venue, rno, buy3cnt, isHit, hitOdds, buy3combos, ...}, ...]
    """

    # Node.js に渡すランナースクリプト
    # sample.js が参照するグローバル変数をスタブで定義してから
    # collectResultsForDate を全日付に対して実行する
    runner = textwrap.dedent(f"""
'use strict';
// ── グローバルスタブ ─────────────────────────────────────
const location = {{ href: 'http://localhost/', hostname: 'localhost' }};
const document = {{
  getElementById: () => ({{ innerHTML: '', style: {{}} }}),
  querySelectorAll: () => ([]),
  querySelector: () => null,
  createElement: () => ({{ href:'', download:'', click:()=>{{}}, style:{{}} }}),
  body: {{ appendChild: ()=>{{}}, removeChild: ()=>{{}} }},
  readyState: 'complete',
  addEventListener: ()=>{{}},
}};
const window = {{ scrollTo:()=>{{}}, location }};
const URL = {{ createObjectURL:()=>'', revokeObjectURL:()=>{{}} }};
const requestAnimationFrame = cb => cb();
const setInterval = ()=>{{}};
const Blob = class {{ constructor(a,b){{ this._data=a; }} }};
const fetch = async ()=>({{}});

// ── データ変数（外部JSONをここに注入）─────────────────
const _venueDataAll = {venue_data_json};
const _resultData   = {result_data_json};
const _oddsData     = {odds_data_json};
const _masterExt    = {master_ext_json};
const _tenjiData    = {tenji_data_json};

// sample.js が参照する変数名に合わせて定義
let   ALL_DATA         = {{}};
let   ALL_DATA_HISTORY = {{}};
let   RESULT_DATA      = _resultData;
let   ODDS_DATA        = _oddsData;
let   MASTER_EXT       = _masterExt;
const TENJI_DATA       = _tenjiData;
const COMMENT_DATA     = {{}};
const FLYING_DATA      = {{}};

// ALL_DATA / ALL_DATA_HISTORY にデータを振り分け
(function() {{
  const dates = Object.keys(_venueDataAll).sort();
  if (dates.length === 0) return;
  const todayDate = dates[dates.length - 1];
  ALL_DATA = _venueDataAll[todayDate] || {{}};
  for (const d of dates.slice(0, -1)) {{
    ALL_DATA_HISTORY[d] = _venueDataAll[d] || {{}};
  }}
}})();

// ── sample.js 本体をここに展開 ─────────────────────────
""")

    # sample.js 本体を埋め込む（DOM操作のある即時実行関数はスキップ）
    # IIFE の末尾でエラーが出ないよう、console.error を安全にする
    runner += "\n" + js_src + "\n"

    # 集計実行コード
    runner += textwrap.dedent(f"""
// ── 集計実行 ─────────────────────────────────────────
// ブラウザの calcTopAIStats と同一ロジック:
//   getAvailableDates() の末尾 = 当日、それ以外 = 過去日
//   過去日を新しい順に最大 {DAYS_TO_COLLECT} 日分だけ集計（当日は含まない）
try {{
  const mode      = "{mode}";
  const allDates  = getAvailableDates().sort();          // 古い順
  const todayDate = allDates[allDates.length - 1];       // 当日
  const histDates = allDates.slice(0, -1).reverse();     // 過去日（新しい順）
  const past30    = histDates.slice(0, {DAYS_TO_COLLECT}); // 直近30日

  const output     = [];
  const dateSample = past30.slice(0, 3);  // デバッグ用

  for (const dateStr of past30) {{
    const {{ results }} = collectResultsForDate(dateStr, mode);
    for (const r of results) {{
      output.push({{ date: dateStr, ...r }});
    }}
  }}

  process.stdout.write(JSON.stringify({{ ok: true, results: output, dateSample, totalDays: past30.length }}));
}} catch(e) {{
  process.stdout.write(JSON.stringify({{ ok: false, error: e.message, stack: e.stack }}));
}}
""")

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".js", encoding="utf-8", delete=False
    ) as f:
        f.write(runner)
        tmp_path = f.name

    try:
        result = subprocess.run(
            ["node", tmp_path],
            capture_output=True, timeout=120,
            encoding="utf-8", errors="replace"
        )
        if result.returncode != 0:
            raise RuntimeError(f"Node.js エラー:\n{result.stderr[:2000]}")
        raw = result.stdout.strip()
        if not raw:
            raise RuntimeError("Node.js から出力がありません。\nstderr:\n" + result.stderr[:1000])
        data = json.loads(raw)
        if not data.get("ok"):
            raise RuntimeError(f"ロジックエラー: {data.get('error')}\n{data.get('stack','')[:1000]}")
        date_sample  = data.get("dateSample", [])
        total_days   = data.get("totalDays", "?")
        if date_sample:
            import sys as _sys
            print(f"  [info] 集計期間: {total_days}日  日付サンプル: {date_sample}", file=_sys.stderr)
        return data["results"]
    finally:
        os.unlink(tmp_path)

# ════════════════════════════════════════════════════════
#  data/ フォルダ読み込み
# ════════════════════════════════════════════════════════

def load_data_folder(base_dir: Path) -> dict:
    """
    data/ フォルダの index.json を読んで、
    history_*.json / result_*.json / master_ext.json を読み込む。
    返り値: {
      "venue_data": { "YYYY-MM-DD": { venue: {...} } },
      "result_data": { key: {...} },
      "odds_data": { date: { venue: { rno: {...} } } },
      "master_ext": {...} | None,
      "tenji_data": { key: {...} },
    }
    """
    data_dir = base_dir / "data"
    out = {
        "venue_data":  {},
        "result_data": {},
        "odds_data":   {},
        "master_ext":  None,
        "tenji_data":  {},
    }

    if not data_dir.exists():
        print(color(f"  [警告] data/ フォルダが見つかりません: {data_dir}", YELLOW))
        return out

    # index.json
    index_path = data_dir / "index.json"
    if not index_path.exists():
        print(color("  [警告] data/index.json が見つかりません。", YELLOW))
        return out

    with open(index_path, encoding="utf-8") as f:
        index = json.load(f)

    result_dates  = index.get("result_dates",  [])
    history_dates = index.get("history_dates", [])

    # result_*.json → RESULT_DATA
    for nd in result_dates:
        path = data_dir / f"result_{nd}.json"
        if not path.exists(): continue
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        for key, val in data.items():
            m = re.match(r'^(.+)_(\d+)$', key)
            full_key = f"{m.group(1)}_{nd}_{m.group(2)}" if m else f"{key}_{nd}"
            if full_key not in out["result_data"]:
                out["result_data"][full_key] = val

    # history_*.json → venue_data
    for nd in history_dates:
        dash = f"{nd[:4]}-{nd[4:6]}-{nd[6:8]}"
        path = data_dir / f"history_{nd}.json"
        if not path.exists(): continue
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if dash not in out["venue_data"]:
            out["venue_data"][dash] = data
        else:
            for venue, vdata in data.items():
                if venue not in out["venue_data"][dash]:
                    out["venue_data"][dash][venue] = vdata

    # odds_*.json → odds_data
    # 形式①: data/odds_YYYYMMDD.json (日付まとめ型)
    for nd in result_dates:
        path = data_dir / f"odds_{nd}.json"
        if not path.exists(): continue
        dash = f"{nd[:4]}-{nd[4:6]}-{nd[6:8]}"
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        if dash not in out["odds_data"]:
            out["odds_data"][dash] = d

    # 形式②: odds_data/odds_{slug}_{YYYYMMDD}_R{rno}.json (1レース1ファイル型)
    # ファイル名例: odds_amagasaki_20260417_R01.json
    odds_dir = base_dir / "odds_data"
    if not odds_dir.exists():
        # data/odds_data/ も探す
        odds_dir = data_dir / "odds_data"

    SLUG_TO_VENUE = {
        "kiryu":"桐生","toda":"戸田","edogawa":"江戸川","heiwajima":"平和島",
        "tamagawa":"多摩川","hamanako":"浜名湖","gamagori":"蒲郡","tokoname":"常滑",
        "tsu":"津","mikuni":"三国","biwako":"びわこ","suminoe":"住之江",
        "amagasaki":"尼崎","naruto":"鳴門","marugame":"丸亀","kojima":"児島",
        "miyajima":"宮島","tokuyama":"徳山","shimonoseki":"下関","wakamatsu":"若松",
        "ashiya":"芦屋","fukuoka":"福岡","karatsu":"唐津","omura":"大村",
    }
    VENUE_TO_SLUG = {v: k for k, v in SLUG_TO_VENUE.items()}

    if odds_dir.exists():
        for odds_file in odds_dir.glob("odds_*.json"):
            # ファイル名: odds_{slug}_{YYYYMMDD}_R{rno}.json
            m = re.match(r'^odds_(.+?)_(\d{8})_R(\d+)\.json$', odds_file.name, re.IGNORECASE)
            if not m:
                continue
            slug, nd, rno_str = m.group(1), m.group(2), m.group(3)
            rno = str(int(rno_str))  # "01" → "1"
            dash = f"{nd[:4]}-{nd[4:6]}-{nd[6:8]}"
            venue = SLUG_TO_VENUE.get(slug, slug)

            try:
                with open(odds_file, encoding="utf-8") as f:
                    race_odds = json.load(f)
            except Exception:
                continue

            # ODDS_DATA[date][venue][rno] = race_odds の形に格納
            out["odds_data"].setdefault(dash, {})
            out["odds_data"][dash].setdefault(venue, {})
            if rno not in out["odds_data"][dash][venue]:
                out["odds_data"][dash][venue][rno] = race_odds

    # tenji_*.json → tenji_data
    # ② history_dates と result_dates に重複日付がある場合の二重読み込みを防ぐ
    seen_tenji_dates: set = set()
    for nd in history_dates + result_dates:
        if nd in seen_tenji_dates:
            continue
        seen_tenji_dates.add(nd)
        path = data_dir / f"tenji_{nd}.json"
        if not path.exists(): continue
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        # キーを YYYY-MM-DD 形式に正規化
        # ① JS側の String.replace() は最初の1箇所のみ置換するため
        #    Python側も re.sub の count=1 で揃える（スラッグに数字が含まれる場合の誤置換防止）
        dash = f"{nd[:4]}-{nd[4:6]}-{nd[6:8]}"
        for key, val in data.items():
            normalized = re.sub(r'_(\d{4})(\d{2})(\d{2})_', f'_{dash}_', key, count=1)
            if normalized not in out["tenji_data"]:
                out["tenji_data"][normalized] = val

    # master_ext.json
    master_path = data_dir / "master_ext.json"
    if master_path.exists():
        with open(master_path, encoding="utf-8") as f:
            out["master_ext"] = json.load(f)

    return out

# ════════════════════════════════════════════════════════
#  表示
# ════════════════════════════════════════════════════════

def fmt_rate(rate, decimals=1):
    return f"{rate*100:.{decimals}f}%"

def print_header(js_path: Path, node_ver: str):
    width = 72
    print()
    print(color("═" * width, CYAN, BOLD))
    print(color(f"  🚤  ボートレース AI 予想 成績アナライザー", CYAN, BOLD))
    print(color("═" * width, CYAN, BOLD))
    print(f"  sample.js : {color(str(js_path), WHITE)}")
    mtime = datetime.fromtimestamp(js_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    print(f"  更新日時  : {color(mtime, DIM)}")
    print(f"  Node.js   : {color(node_ver, DIM)}")
    print(color("─" * width, DIM))
    print()

def print_buy_logic_summary(js_src: str):
    """sample.js から買い目ロジックの主要パラメータを表示。"""
    print(color("  ▶ AI 予想タブ 買い目ロジック概要", BOLD, CYAN))
    print()

    # FINAL_PROB_WEIGHTS
    m_base   = re.search(r'base\s*:\s*([\d.]+)',   js_src)
    m_tenkai = re.search(r'tenkai\s*:\s*([\d.]+)', js_src)
    m_tenji  = re.search(r'tenji\s*:\s*([\d.]+)',  js_src)
    print(f"  {'重み設定 (FINAL_PROB_WEIGHTS)':30s}")
    if m_base:   print(f"    {'base   (基準1着率)':28s} = {color(m_base.group(1),   YELLOW)}")
    if m_tenkai: print(f"    {'tenkai (展開補正)':28s} = {color(m_tenkai.group(1), YELLOW)}")
    if m_tenji:  print(f"    {'tenji  (展示補正)':28s} = {color(m_tenji.group(1),  YELLOW)}")

    # BUY_PROB_THRESHOLD
    m_thr = re.search(r'BUY_PROB_THRESHOLD\s*=\s*([\d.]+)', js_src)
    if m_thr:
        print(f"    {'確率フィルター閾値':28s} = {color(m_thr.group(1)+'%', YELLOW)}")

    # 合成オッズ基準（コメントから抽出）
    m_hit_synth = re.search(r'HIT_SYNTH_MIN\s*=\s*([\d.]+)', js_src)
    m_rec_synth = re.search(r'REC_SYNTH_MIN\s*=\s*([\d.]+)', js_src)
    if m_hit_synth:
        print(f"    {'合成オッズ基準(的中重視)':28s} = {color(m_hit_synth.group(1)+'x', YELLOW)}")
    if m_rec_synth:
        print(f"    {'合成オッズ基準(回収重視)':28s} = {color(m_rec_synth.group(1)+'x', YELLOW)}")

    # 参加除外条件
    print()
    print(f"  {'参加条件 / 除外条件':30s}")
    print(f"    {'RESULT_DATA あり':28s}: ○ 集計対象")
    print(f"    {'データ不足(dq=insufficient)':28s}: × 除外")
    print(f"    {'進入変更あり':28s}: × 除外")
    print(f"    {'合成オッズ未達':28s}: × 見送り（集計対象外）")
    print(f"    {'江戸川':28s}: × 除外（固定）")
    print()
    print(color("─" * 72, DIM))
    print()

def print_mode_summary(results: list, mode_label: str, synth_min: float):
    """モード別サマリーを表示。"""
    total = len(results)
    if total == 0:
        print(f"    {mode_label}: {color('集計対象なし', DIM)}")
        return

    hit_count  = sum(1 for r in results if r["isHit"])
    hit_rate   = hit_count / total
    total_bet  = sum(r["buy3cnt"] * 100 for r in results)
    total_ret  = sum(r["hitOdds"] for r in results if r["isHit"])
    rec_rate   = total_ret / total_bet if total_bet > 0 else 0
    avg_pts    = sum(r["buy3cnt"] for r in results) / total

    hc = rate_color(hit_rate)
    rc = recovery_color(rec_rate)

    print(f"  {color(mode_label, BOLD)}  {color(f'合成{synth_min}倍以上', DIM)}")
    print(f"  {'':4s}{'的中率':8s} {color(bar(hit_rate), hc)} "
          f"{color(fmt_rate(hit_rate), hc, BOLD):>8s}  ({hit_count}/{total}R)")
    print(f"  {'':4s}{'回収率':8s} {color(bar(rec_rate), rc)} "
          f"{color(fmt_rate(rec_rate), rc, BOLD):>8s}  ({total_ret:,.0f}円 / {total_bet:,.0f}円)")
    print(f"  {'':4s}{'集計R数':8s} {color(str(total)+'R', WHITE, BOLD)}  "
          f"平均買い目 {avg_pts:.1f}点")
    print()

def print_venue_table(results: list, title: str):
    """会場別内訳テーブルを表示。"""
    from collections import defaultdict
    venue_map = defaultdict(list)
    for r in results:
        venue_map[r["venue"]].append(r)

    VENUE_LIST = [
        "桐生","戸田","江戸川","平和島","多摩川","浜名湖","蒲郡","常滑",
        "津","三国","びわこ","住之江","尼崎","鳴門","丸亀","児島",
        "宮島","徳山","下関","若松","芦屋","福岡","唐津","大村"
    ]

    header = f"  {'会場':6s} {'的中率':>8s} {'R数':>6s} {'回収率':>8s} {'払戻合計':>10s}"
    print(color(f"  ── {title} 会場別内訳 ──", DIM))
    print(color(header, DIM))
    print(color("  " + "─" * 46, DIM))

    for v in VENUE_LIST:
        if v not in venue_map:
            continue
        vrs = venue_map[v]
        v_hit   = sum(1 for r in vrs if r["isHit"])
        v_total = len(vrs)
        v_bet   = sum(r["buy3cnt"] * 100 for r in vrs)
        v_ret   = sum(r["hitOdds"] for r in vrs if r["isHit"])
        v_rec   = v_ret / v_bet if v_bet > 0 else 0
        v_rate  = v_hit / v_total

        hc = rate_color(v_rate)
        rc = recovery_color(v_rec)
        print(
            f"  {v:6s}"
            f" {color(fmt_rate(v_rate), hc):>14s}"
            f" {color(str(v_hit)+'/'+str(v_total)+'R', DIM):>12s}"
            f" {color(fmt_rate(v_rec), rc):>14s}"
            f" {color(f'{v_ret:,.0f}円', DIM):>16s}"
        )
    print()

def print_daily_table(results_by_date: dict, mode_label: str):
    """日付×会場の一覧表示。"""
    print(color(f"  ── {mode_label} 日別詳細 ──", DIM))
    header = f"  {'日付':12s} {'会場':6s} {'R':>3s} {'点':>3s} {'結果':>6s} {'払戻':>8s} {'組合せ'}"
    print(color(header, DIM))
    print(color("  " + "─" * 64, DIM))

    for date_str in sorted(results_by_date.keys(), reverse=True):
        rows = results_by_date[date_str]
        for r in sorted(rows, key=lambda x: (x["venue"], x["rno"])):
            hit_str  = color("🎯的中", GREEN) if r["isHit"] else color("  外れ", DIM)
            odds_str = color(f"¥{r['hitOdds']:>6,.0f}", YELLOW) if r["isHit"] else color("      —", DIM)
            print(
                f"  {date_str:12s}"
                f" {r['venue']:6s}"
                f" {r['rno']:>3d}R"
                f" {r['buy3cnt']:>3d}点"
                f"  {hit_str}"
                f"  {odds_str}"
                f"  {color(r.get('buy3combos','')[:50], DIM)}"
            )
    print()

# ════════════════════════════════════════════════════════
#  メイン
# ════════════════════════════════════════════════════════

def main():
    # ── パス解決 ──
    if len(sys.argv) >= 2:
        js_path = Path(sys.argv[1]).resolve()
    else:
        js_path = DEFAULT_JS_PATH.resolve()

    base_dir = js_path.parent

    # ── Node.js 確認 ──
    print(color("\n  Node.js を確認中...", DIM), end="", flush=True)
    node_ver = check_node()
    if not node_ver:
        print(color("\n\n  [エラー] Node.js が見つかりません。", RED, BOLD))
        print("  インストール後に再実行してください: https://nodejs.org/")
        sys.exit(1)
    print(color(f" {node_ver} ✓", GREEN))

    # ── sample.js 読み込み ──
    print(color("  sample.js を読み込み中...", DIM), end="", flush=True)
    js_src = load_js_logic(js_path)
    print(color(f" {len(js_src):,} 文字 ✓", GREEN))

    # ── data/ フォルダ読み込み ──
    print(color("  data/ フォルダを読み込み中...", DIM), end="", flush=True)
    data = load_data_folder(base_dir)
    n_dates  = len(data["venue_data"])
    n_result = len(data["result_data"])
    n_tenji  = len(data["tenji_data"])
    n_odds   = sum(
        len(races)
        for venues in data["odds_data"].values()
        for races in venues.values()
    )
    print(color(f" 日付={n_dates}日 結果={n_result}件 展示={n_tenji}件 オッズ={n_odds}件 ✓", GREEN))

    # ── ヘッダー出力 ──
    print_header(js_path, node_ver)
    print_buy_logic_summary(js_src)

    # ── Node.js で買い目生成・集計 ──
    all_results = {}  # mode -> list[dict]

    for mode in ("hit", "rec"):
        mode_label = "🎯 的中重視" if mode == "hit" else "💰 回収重視"
        print(color(f"  [{mode_label}] 集計中...", DIM), end="", flush=True)

        try:
            results = extract_buy_logic_via_node(
                js_src,
                json.dumps(data["venue_data"], ensure_ascii=False),
                json.dumps(data["result_data"], ensure_ascii=False),
                json.dumps(data["odds_data"],   ensure_ascii=False),
                json.dumps(data["master_ext"],  ensure_ascii=False),
                json.dumps(data["tenji_data"],  ensure_ascii=False),
                mode=mode,
            )
            all_results[mode] = results
            # Node.js側で既に直近30日に絞っているのでそのまま使う
            results_30 = results
            all_results[mode + "_30"] = results_30

            print(color(f" {len(results_30)}件 ✓", GREEN))

        except Exception as e:
            print(color(f"\n  [エラー] {e}", RED))
            all_results[mode] = []
            all_results[mode + "_30"] = []

    print()
    print(color("═" * 72, CYAN, BOLD))
    print(color("  直近 30 日 AI 予想成績サマリー", BOLD, WHITE))
    print(color("═" * 72, CYAN, BOLD))
    print()

    for mode in ("hit", "rec"):
        mode_label = "🎯 的中重視" if mode == "hit" else "💰 回収重視"
        synth_min  = SYNTH_MIN[mode]
        results_30 = all_results.get(mode + "_30", [])
        print_mode_summary(results_30, mode_label, synth_min)

    print(color("─" * 72, DIM))
    print()

    # ── 会場別内訳 ──
    for mode in ("hit", "rec"):
        mode_label = "🎯 的中重視" if mode == "hit" else "💰 回収重視"
        results_30 = all_results.get(mode + "_30", [])
        if results_30:
            print_venue_table(results_30, mode_label)

    # ── 日別詳細 ──
    print(color("─" * 72, DIM))
    print()
    for mode in ("hit", "rec"):
        mode_label = "🎯 的中重視" if mode == "hit" else "💰 回収重視"
        results_30 = all_results.get(mode + "_30", [])
        if not results_30:
            continue
        # 日付ごとにまとめる
        from collections import defaultdict
        by_date = defaultdict(list)
        for r in results_30:
            by_date[r.get("date","")].append(r)
        print_daily_table(dict(by_date), mode_label)

    print(color("═" * 72, CYAN))
    print(color("  集計完了", GREEN, BOLD))
    print(color("═" * 72, CYAN))
    print()


if __name__ == "__main__":
    main()
