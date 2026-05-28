#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
debug_analyzer.py  ─ boatrace_analyzer.py が 0件になる原因を診断する
同じフォルダに置いて実行してください。
"""

import os, sys, json, re, subprocess, tempfile, textwrap
from pathlib import Path
from datetime import datetime

DEFAULT_JS_PATH = Path(__file__).parent / "sample.js"

def check_node():
    try:
        r = subprocess.run(
            ["node","--version"],
            capture_output=True, timeout=10,
            encoding="utf-8", errors="replace"
        )
        return r.stdout.strip() if r.returncode == 0 else None
    except: return None

def load_data_folder(base_dir: Path):
    data_dir = base_dir / "data"
    out = {"venue_data":{}, "result_data":{}, "odds_data":{}, "master_ext":None, "tenji_data":{}}
    if not data_dir.exists():
        print(f"[ERROR] data/ フォルダなし: {data_dir}"); return out

    index_path = data_dir / "index.json"
    if not index_path.exists():
        print("[ERROR] data/index.json なし"); return out

    with open(index_path, encoding="utf-8") as f:
        index = json.load(f)

    result_dates  = index.get("result_dates",  [])
    history_dates = index.get("history_dates", [])
    print(f"  index.json  result_dates={len(result_dates)}件  history_dates={len(history_dates)}件")
    if result_dates:
        print(f"  result_dates サンプル: {result_dates[:3]} ... {result_dates[-3:]}")
    if history_dates:
        print(f"  history_dates サンプル: {history_dates[:3]} ... {history_dates[-3:]}")

    # result_*.json
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

    # history_*.json
    for nd in history_dates:
        dash = f"{nd[:4]}-{nd[4:6]}-{nd[6:8]}"
        path = data_dir / f"history_{nd}.json"
        if not path.exists(): continue
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if dash not in out["venue_data"]:
            out["venue_data"][dash] = data
        else:
            for v, vd in data.items():
                if v not in out["venue_data"][dash]:
                    out["venue_data"][dash][v] = vd

    # master_ext.json
    mp = data_dir / "master_ext.json"
    if mp.exists():
        with open(mp, encoding="utf-8") as f:
            out["master_ext"] = json.load(f)

    # odds_data/ フォルダ (1レース1ファイル形式)
    SLUG_TO_VENUE = {
        "kiryu":"桐生","toda":"戸田","edogawa":"江戸川","heiwajima":"平和島",
        "tamagawa":"多摩川","hamanako":"浜名湖","gamagori":"蒲郡","tokoname":"常滑",
        "tsu":"津","mikuni":"三国","biwako":"びわこ","suminoe":"住之江",
        "amagasaki":"尼崎","naruto":"鳴門","marugame":"丸亀","kojima":"児島",
        "miyajima":"宮島","tokuyama":"徳山","shimonoseki":"下関","wakamatsu":"若松",
        "ashiya":"芦屋","fukuoka":"福岡","karatsu":"唐津","omura":"大村",
    }
    odds_dir = base_dir / "odds_data"
    if not odds_dir.exists():
        odds_dir = data_dir / "odds_data"
    if odds_dir.exists():
        sample_files = list(odds_dir.glob("odds_*.json"))
        print(f"  odds_data/ フォルダ: {len(sample_files)}ファイル")
        if sample_files:
            print(f"  サンプルファイル名: {sample_files[0].name}")
            with open(sample_files[0], encoding="utf-8") as f:
                sc = json.load(f)
            print(f"  サンプル内容キー: {list(sc.keys())[:8]}")
        loaded = 0
        for odds_file in odds_dir.glob("odds_*.json"):
            m = re.match(r'^odds_(.+?)_(\d{8})_R(\d+)\.json$', odds_file.name, re.IGNORECASE)
            if not m: continue
            slug, nd, rno_str = m.group(1), m.group(2), m.group(3)
            rno = str(int(rno_str))
            dash = f"{nd[:4]}-{nd[4:6]}-{nd[6:8]}"
            venue = SLUG_TO_VENUE.get(slug, slug)
            try:
                with open(odds_file, encoding="utf-8") as f:
                    race_odds = json.load(f)
            except Exception:
                continue
            out["odds_data"].setdefault(dash, {})
            out["odds_data"][dash].setdefault(venue, {})
            if rno not in out["odds_data"][dash][venue]:
                out["odds_data"][dash][venue][rno] = race_odds
                loaded += 1
        print(f"  odds_data/ 読み込み: {loaded}件")
    else:
        print(f"  [警告] odds_data/ フォルダなし: {odds_dir}")

    return out

def run_node_debug(js_src: str, venue_data_json: str, result_data_json: str,
                   odds_data_json: str, master_ext_json: str, tenji_data_json: str):
    """Node.js 上でデータの中身を診断する。"""
    runner = textwrap.dedent(f"""
'use strict';
const location = {{ href: 'http://localhost/', hostname: 'localhost' }};
const document = {{
  getElementById: () => ({{ innerHTML: '', style: {{}} }}),
  querySelectorAll: () => ([]),
  querySelector: () => null,
  createElement: () => ({{ href:'', download:'', click:()=>{{}}, style:{{}} }}),
  body: {{ appendChild:()=>{{}}, removeChild:()=>{{}} }},
  readyState: 'complete',
  addEventListener: ()=>{{}},
}};
const window = {{ scrollTo:()=>{{}}, location }};
const URL = {{ createObjectURL:()=>'', revokeObjectURL:()=>{{}} }};
const requestAnimationFrame = cb => cb();
const setInterval = ()=>{{}};
const Blob = class {{ constructor(a,b){{ this._data=a; }} }};
const fetch = async ()=>({{}});

const _venueDataAll = {venue_data_json};
const _resultData   = {result_data_json};
const _oddsData     = {odds_data_json};
const _masterExt    = {master_ext_json};
const _tenjiData    = {tenji_data_json};

let ALL_DATA = {{}};
let ALL_DATA_HISTORY = {{}};
let RESULT_DATA   = _resultData;
let ODDS_DATA     = _oddsData;
let MASTER_EXT    = _masterExt;
const TENJI_DATA  = _tenjiData;
const COMMENT_DATA = {{}};
const FLYING_DATA  = {{}};

(function() {{
  const dates = Object.keys(_venueDataAll).sort();
  if (!dates.length) return;
  const todayDate = dates[dates.length - 1];
  ALL_DATA = _venueDataAll[todayDate] || {{}};
  for (const d of dates.slice(0,-1)) {{
    ALL_DATA_HISTORY[d] = _venueDataAll[d] || {{}};
  }}
}})();

""") + "\n" + js_src + textwrap.dedent("""

// ── 診断開始 ──────────────────────────────────
const diag = {};

// 1. getAvailableDates
let allDates = [];
try {
  allDates = getAvailableDates();
  diag.availableDates = allDates;
} catch(e) {
  diag.availableDates_error = e.message;
}

// 2. RESULT_DATA のキーサンプル
const rKeys = Object.keys(RESULT_DATA);
diag.resultDataCount = rKeys.length;
diag.resultDataKeySample = rKeys.slice(0,5);

// 3. 最新日のvenue一覧
try {
  const latest = allDates[allDates.length - 1];
  const d = getDataForDate(latest);
  diag.latestDate = latest;
  diag.latestVenues = Object.keys(d || {});
} catch(e) {
  diag.latestDate_error = e.message;
}

// 4. 1件だけ collectResultsForDate を試す
try {
  const testDate = allDates[allDates.length - 2] || allDates[0];
  diag.testDate = testDate;
  const { results, excludedList } = collectResultsForDate(testDate, 'hit');
  diag.testResults    = results.length;
  diag.testExcluded   = excludedList.length;
  diag.testExcSample  = excludedList.slice(0,5);
  diag.testResSample  = results.slice(0,3);
} catch(e) {
  diag.testDate_error = e.message + "\\n" + (e.stack||'').slice(0,500);
}

// 5. RESULT_DATA のキーと実際のresultKey形式を比較
try {
  const testDate2 = allDates[allDates.length - 2] || allDates[0];
  const d2 = getDataForDate(testDate2);
  const venues = Object.keys(d2 || {});
  const sampleVenue = venues[0];
  if (sampleVenue) {
    const vdata = d2[sampleVenue];
    const slugMap = {
      "桐生":"kiryu","戸田":"toda","江戸川":"edogawa","平和島":"heiwajima",
      "多摩川":"tamagawa","浜名湖":"hamanako","蒲郡":"gamagori","常滑":"tokoname",
      "津":"tsu","三国":"mikuni","びわこ":"biwako","住之江":"suminoe",
      "尼崎":"amagasaki","鳴門":"naruto","丸亀":"marugame","児島":"kojima",
      "宮島":"miyajima","徳山":"tokuyama","下関":"shimonoseki","若松":"wakamatsu",
      "芦屋":"ashiya","福岡":"fukuoka","唐津":"karatsu","大村":"omura"
    };
    const slug = slugMap[sampleVenue] || sampleVenue;
    const dateNd = (vdata.date||'').replace(/-/g,'');
    const rno = Object.keys(vdata.races||{})[0];
    const generatedKey = `${slug}_${dateNd}_${rno}`;
    diag.keyCheck = {
      venue: sampleVenue, slug, date: vdata.date, dateNd, rno,
      generatedKey,
      existsInResultData: !!RESULT_DATA[generatedKey],
      sampleResultKeys: Object.keys(RESULT_DATA).slice(0,5),
    };
  }
} catch(e) {
  diag.keyCheck_error = e.message;
}

process.stdout.write(JSON.stringify(diag, null, 2));
""")

    with tempfile.NamedTemporaryFile(mode="w", suffix=".js", encoding="utf-8", delete=False) as f:
        f.write(runner)
        tmp = f.name
    try:
        r = subprocess.run(
            ["node", tmp],
            capture_output=True, timeout=120,
            encoding="utf-8", errors="replace"
        )
        if r.returncode != 0:
            return None, r.stderr[:3000]
        stdout = r.stdout.strip()
        if not stdout:
            return None, "stdout が空です。\nstderr:\n" + r.stderr[:1000]
        return json.loads(stdout), r.stderr[:500]
    except Exception as e:
        return None, str(e)
    finally:
        os.unlink(tmp)

def main():
    js_path  = (Path(sys.argv[1]) if len(sys.argv) >= 2 else DEFAULT_JS_PATH).resolve()
    base_dir = js_path.parent

    print(f"\n=== 診断開始 ===")
    print(f"sample.js : {js_path}")

    node_ver = check_node()
    print(f"Node.js   : {node_ver or 'NOT FOUND'}\n")

    js_src = js_path.read_text(encoding="utf-8")
    print(f"sample.js 読み込み: {len(js_src):,} 文字\n")

    print("--- data/ フォルダ診断 ---")
    data = load_data_folder(base_dir)
    print(f"  venue_data  : {len(data['venue_data'])} 日付")
    print(f"  result_data : {len(data['result_data'])} 件")
    print()

    if data["venue_data"]:
        dates = sorted(data["venue_data"].keys())
        print(f"  venue_data 日付一覧 ({len(dates)}件):")
        for d in dates[-10:]:
            venues = list(data["venue_data"][d].keys())
            print(f"    {d}: {venues}")
        print()

    if data["result_data"]:
        keys = list(data["result_data"].keys())[:5]
        print(f"  result_data キーサンプル:")
        for k in keys: print(f"    {k}")
        print()

    print("--- Node.js 上での診断 ---")
    diag, stderr = run_node_debug(
        js_src,
        json.dumps(data["venue_data"], ensure_ascii=False),
        json.dumps(data["result_data"], ensure_ascii=False),
        json.dumps(data["odds_data"], ensure_ascii=False),
        json.dumps(data["master_ext"], ensure_ascii=False),
        json.dumps(data["tenji_data"], ensure_ascii=False),
    )

    if diag is None:
        print(f"[ERROR] Node.js 実行失敗:\n{stderr}")
        return

    if stderr:
        print(f"[stderr] {stderr}\n")

    print(json.dumps(diag, ensure_ascii=False, indent=2))

    # わかりやすいまとめ
    print("\n=== 診断まとめ ===")
    if "testDate_error" in diag:
        print(f"[問題] collectResultsForDate でエラー:\n  {diag['testDate_error']}")
    elif diag.get("testResults", 0) == 0 and diag.get("testExcluded", 0) == 0:
        print("[問題] 集計対象レースが0件かつ除外も0件 → RESULT_DATA とのキー不一致の可能性が高い")
        if "keyCheck" in diag:
            kc = diag["keyCheck"]
            print(f"  生成キー  : {kc['generatedKey']}")
            print(f"  RESULTに存在: {kc['existsInResultData']}")
            print(f"  RESULTサンプルキー: {kc['sampleResultKeys']}")
    elif diag.get("testExcluded", 0) > 0 and diag.get("testResults", 0) == 0:
        print(f"[問題] 全レースが除外されている ({diag['testExcluded']}件除外)")
        for ex in diag.get("testExcSample", []):
            print(f"  除外: {ex}")
    else:
        print(f"[OK?] testDate={diag.get('testDate')} → {diag.get('testResults')}件 / 除外{diag.get('testExcluded')}件")
        print("集計は動いている。日付フィルター（cutoff）の問題かもしれません。")

if __name__ == "__main__":
    main()
