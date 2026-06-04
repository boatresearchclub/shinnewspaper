"""
backtest_roi.py  — 競艇投資バックテスト（ROI・的中率・会場別分析）
=======================================================================
【使い方】
    python backtest_roi.py

【前提】
    - scripts/result_data/*.json  : レース結果（着順・払戻）
    - scripts/csv_output/*.csv    : 出走表（選手・会場・日付）
    - scripts/master_data.json    : 選手マスタ

【注意】
    このスクリプトは「シナリオ買い戦略」のバックテストを行います。
    買い目生成ロジックは auto_push.py の Python 移植版を簡略化したものです。
    JavaScriptの完全再現ではないため±5%程度の誤差が生じる可能性があります。

【出力】
    - コンソール: 全体ROI・的中率・会場別・月別集計
    - backtest_result.csv: 全レース詳細（Excelで分析可能）
=======================================================================
"""

import json
import glob
import re
import os
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# ── パス設定（環境に合わせて変更してください）────────────────────────────
SCRIPTS_DIR  = Path(r"C:\Users\user\Desktop\データ収集\scripts")
RESULT_DIR   = SCRIPTS_DIR / "result_data"
CSV_DIR      = SCRIPTS_DIR / "csv_output"
MASTER_JSON  = SCRIPTS_DIR / "master_data.json"

# ── 投資設定 ───────────────────────────────────────────────────────────────
BET_PER_POINT = 100       # 1点あたり賭け金（円）
MAX_POINTS    = 18        # シナリオ買い最大点数

# ── 会場スラッグ → 会場名 逆引きマップ ────────────────────────────────────
SLUG_TO_VENUE = {
    "kiryu":"桐生","toda":"戸田","edogawa":"江戸川","heiwajima":"平和島",
    "tamagawa":"多摩川","hamanako":"浜名湖","gamagori":"蒲郡","tokoname":"常滑",
    "tsu":"津","mikuni":"三国","biwako":"びわこ","suminoe":"住之江",
    "amagasaki":"尼崎","naruto":"鳴門","marugame":"丸亀","kojima":"児島",
    "miyajima":"宮島","tokuyama":"徳山","shimonoseki":"下関","wakamatsu":"若松",
    "ashiya":"芦屋","fukuoka":"福岡","karatsu":"唐津","omura":"大村",
}
VENUE_TO_SLUG = {v: k for k, v in SLUG_TO_VENUE.items()}

# ── ローダー ──────────────────────────────────────────────────────────────

def load_master():
    if not MASTER_JSON.exists():
        print(f"[ERROR] master_data.json が見つかりません: {MASTER_JSON}")
        return {}
    with open(MASTER_JSON, encoding="utf-8") as f:
        return json.load(f)


def load_result(fpath):
    """result_data/*.json を読み込む"""
    try:
        with open(fpath, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def parse_csv_simple(fpath):
    """
    csv_output/*.csv から {rno: [boats]} を返す最小限パーサ。
    pandas を使わず標準ライブラリのみ（依存を減らすため）。
    """
    import csv
    try:
        for enc in ["utf-8", "shift_jis", "cp932"]:
            try:
                with open(fpath, encoding=enc, newline="") as f:
                    reader = csv.DictReader(f)
                    rows = list(reader)
                break
            except UnicodeDecodeError:
                continue
        else:
            return None, None

        if not rows:
            return None, None

        venue = str(rows[0].get("会場", "")).strip()
        date  = str(rows[0].get("日付", "")).strip().replace("/", "-")

        races = {}
        for row in rows:
            rno_raw = row.get("レース", "")
            if not str(rno_raw).isdigit():
                continue
            rno = int(rno_raw)
            if rno not in races:
                races[rno] = []

            name = re.sub(r'\d+$', '', str(row.get("選手名", "")).strip())
            try:
                boat = int(row.get("艇番", 0))
            except ValueError:
                continue

            races[rno].append({
                "boat": boat,
                "name": name,
                "win_rate": float(row.get("全国勝率", 0) or 0),
            })

        return venue, date, races
    except Exception as e:
        return None, None, None


# ── 超シンプルな買い目生成（シナリオ買いの近似）──────────────────────────
# 完全なロジック再現はJSエンジンが必要なため、ここではマスタの1着率ベースで
# 「このシステムが出すであろう買い目」を近似する。
# 具体的には：
#   1着: 最終確率1位艇（マスタ1着率×ST補正）
#   2着: 加重2着率上位2艇
#   3着: 残り艇の上位3艇
# 各組み合わせ(正方向+折り返し) = 最大12〜18点

def safe_float(v, default=0.0):
    try:
        return float(v) if v else default
    except (ValueError, TypeError):
        return default


def calc_probs_simple(boats, venue, master):
    """
    マスタの ts_win_rate を使って各艇の相対確率を計算。
    auto_push.py の calc_prob_from_master の簡略版。
    """
    course_master = master.get("course_master", {})
    venue_stats   = master.get("venue_stats", {}).get(venue, {})
    venue_course_rates = venue_stats.get("course_rates", {})

    scores = []
    for bt in boats:
        name = bt["name"]
        c    = str(bt["boat"])
        cm   = course_master.get(name, {}).get(c, {})

        if cm and cm.get("reliable"):
            rate = cm.get("ts_win_rate") or cm.get("win_rate") or 0
        else:
            # データ不足 → 会場平均にフォールバック
            rate = safe_float(venue_course_rates.get(c), 1/6)

        # ST順位補正（簡略化: course_master の st_rank を使用）
        st_rank = cm.get("st_rank") if cm else None
        if st_rank:
            raw = 1.0 + (3.0 - st_rank) * (0.2 / 2.5)
            st_corr = max(0.7, min(1.2, raw))
        else:
            st_corr = 1.0

        scores.append(max(rate * st_corr, 0.001))

    total = sum(scores) or 1.0
    ranked = sorted(
        [{"boat": bt["boat"], "name": bt["name"], "prob": scores[i]/total}
         for i, bt in enumerate(boats)],
        key=lambda x: -x["prob"]
    )
    return ranked


def get_inn2place(venue, master):
    """イン逃げ時の2着率テーブル（会場別）"""
    inn2 = master.get("venue_stats", {}).get(venue, {}).get("inn_2place", {})
    return inn2


def generate_scenario_combos(boats, venue, master):
    """
    シナリオ買い目を生成（超簡略版）。
    完全なJS再現は不可能なため、以下の近似を使用：
      - 1着軸: 最終確率1位（fp1st）
      - 2着A: 1着軸での加重2着確率1位
      - 2着B: 同2位
      - 3着: merged3rdMap相当（残り艇の確率順）
      - block1(fp1st-2着A-3着), block2(fp1st-2着B-3着)
      - fp差≤15%pt の場合: fp2ndも2着軸として追加block3
    """
    if not boats:
        return []

    ranked = calc_probs_simple(boats, venue, master)
    if len(ranked) < 3:
        return []

    fp1st = ranked[0]["boat"]
    fp2nd = ranked[1]["boat"]
    fp1st_prob = ranked[0]["prob"]
    fp2nd_prob = ranked[1]["prob"]
    fp_diff_pct = (fp1st_prob - fp2nd_prob) * 100

    # 2着率: イン逃げ時は inn_2place、それ以外は確率順
    inn2 = get_inn2place(venue, master)
    if fp1st == 1 and inn2:
        # イン1着時: inn_2place で2着を決定
        others = sorted(
            [(int(c), v) for c, v in inn2.items() if int(c) != fp1st],
            key=lambda x: -x[1]
        )
        second_list = [b for b, _ in others]
    else:
        second_list = [b["boat"] for b in ranked if b["boat"] != fp1st]

    second_A = second_list[0] if len(second_list) > 0 else None
    second_B = second_list[1] if len(second_list) > 1 else None

    # 3着候補: 1着・2着以外を確率順
    def get_thirds(winner, second):
        return [b["boat"] for b in ranked
                if b["boat"] != winner and b["boat"] != second][:3]

    def make_block(winner, second, thirds):
        """正方向 + 折り返し（重複なし）"""
        combos = []
        used = set()
        for t in thirds:
            if t == winner or t == second:
                continue
            fwd = f"{winner}-{second}-{t}"
            bwd = f"{winner}-{t}-{second}"
            if fwd not in used:
                used.add(fwd); combos.append(fwd)
            if bwd not in used:
                used.add(bwd); combos.append(bwd)
        return combos

    all_set  = set()
    all_list = []

    def add_combos(combos):
        for c in combos:
            if c not in all_set:
                all_set.add(c)
                all_list.append(c)

    if second_A:
        add_combos(make_block(fp1st, second_A, get_thirds(fp1st, second_A)))
    if second_B:
        add_combos(make_block(fp1st, second_B, get_thirds(fp1st, second_B)))

    # fp差 ≤ 15%pt の場合: fp2nd 軸も追加
    if fp_diff_pct <= 15.0 and fp2nd != fp1st:
        second_list2 = [b["boat"] for b in ranked
                        if b["boat"] != fp2nd]
        second_C = second_list2[0] if second_list2 else None
        if second_C:
            add_combos(make_block(fp2nd, second_C, get_thirds(fp2nd, second_C)))

    return all_list[:MAX_POINTS]


# ── 着順コンボの正規化 ─────────────────────────────────────────────────────

def normalize_combo(s):
    return re.sub(r'[－−\-]', '-', str(s or ''))


# ── メインバックテスト ────────────────────────────────────────────────────

def run_backtest():
    print("=" * 60)
    print("  競艇投資バックテスト 開始")
    print("=" * 60)

    # マスタ読み込み
    print("\n[1/4] マスタデータ読み込み中...")
    master = load_master()
    if not master:
        print("[ERROR] マスタが読み込めません。終了します。")
        return
    print(f"  選手数: {len(master.get('course_master', {}))} 名")

    # result_data を全件収集
    print("\n[2/4] レース結果ファイルをスキャン中...")
    result_files = list(RESULT_DIR.glob("result_*.json"))
    print(f"  {len(result_files)} 件")

    # ファイル名から (slug, date_nd, rno) を取得してインデックス化
    result_index = {}  # (slug, date_nd, rno) -> fpath
    for fpath in result_files:
        m = re.match(r"result_(.+)_(\d{8})_R0*(\d+)\.json", fpath.name)
        if m:
            result_index[(m.group(1), m.group(2), int(m.group(3)))] = fpath

    # CSV を全件収集して出走表を構築
    print("\n[3/4] 出走表CSVをスキャン中...")
    csv_files = list(CSV_DIR.glob("*.csv"))
    print(f"  {len(csv_files)} 件")

    # 集計用変数
    records = []          # 全レース詳細
    total_bet   = 0       # 総投資額
    total_ret   = 0       # 総払戻額
    hit_count   = 0       # 的中レース数
    total_races = 0       # 集計対象レース数

    # 会場別・月別集計
    venue_stats = defaultdict(lambda: {"bet":0,"ret":0,"hit":0,"races":0})
    month_stats = defaultdict(lambda: {"bet":0,"ret":0,"hit":0,"races":0})

    print("\n[4/4] バックテスト実行中...")

    for csv_path in sorted(csv_files):
        result = parse_csv_simple(csv_path)
        if result[0] is None:
            continue
        venue, date, races = result
        if not venue or not date or not races:
            continue

        slug = VENUE_TO_SLUG.get(venue)
        if not slug:
            continue

        # YYYY-MM-DD → YYYYMMDD
        try:
            date_nd = date.replace("-", "")
            dt = datetime.strptime(date_nd, "%Y%m%d")
        except ValueError:
            continue

        month_key = dt.strftime("%Y-%m")

        for rno, boats in sorted(races.items()):
            if len(boats) < 4:
                continue

            # 結果ファイルを探す
            key = (slug, date_nd, rno)
            result_fpath = result_index.get(key)
            if not result_fpath:
                continue

            result_data = load_result(result_fpath)
            if not result_data:
                continue

            sanrentan = result_data.get("sanrentan", [])
            if not sanrentan:
                continue  # 未確定・中止

            # 実際の1着-2着-3着
            actual_combo = normalize_combo(sanrentan[0].get("combo", ""))
            actual_odds  = sanrentan[0].get("odds", 0)  # 3連単払戻（100円あたり）

            # 買い目生成
            combos = generate_scenario_combos(boats, venue, master)
            if not combos:
                continue

            n_points = len(combos)
            bet      = n_points * BET_PER_POINT
            is_hit   = any(normalize_combo(c) == actual_combo for c in combos)
            ret      = actual_odds if is_hit else 0  # 的中時: 払戻額（100円→actual_odds円）

            # 注: actual_oddsは「100円あたりの払戻」ではなく「払戻総額（円）」
            # result_data の odds 形式を確認して調整が必要な場合あり
            # ここでは「1点100円での払戻額」として扱う

            total_bet   += bet
            total_ret   += ret
            total_races += 1
            if is_hit:
                hit_count += 1

            venue_stats[venue]["bet"]   += bet
            venue_stats[venue]["ret"]   += ret
            venue_stats[venue]["hit"]   += int(is_hit)
            venue_stats[venue]["races"] += 1

            month_stats[month_key]["bet"]   += bet
            month_stats[month_key]["ret"]   += ret
            month_stats[month_key]["hit"]   += int(is_hit)
            month_stats[month_key]["races"] += 1

            records.append({
                "date":      date,
                "month":     month_key,
                "venue":     venue,
                "rno":       rno,
                "n_points":  n_points,
                "bet":       bet,
                "actual":    actual_combo,
                "hit":       int(is_hit),
                "ret":       ret,
                "profit":    ret - bet,
                "odds":      actual_odds,
                "combos":    ",".join(combos[:5]) + ("..." if len(combos) > 5 else ""),
            })

    # ── 結果表示 ─────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  ■ 全体集計")
    print("=" * 60)

    if total_races == 0:
        print("[ERROR] 集計対象レースが0件です。")
        print("  → result_data/ または csv_output/ のパスを確認してください。")
        print(f"     RESULT_DIR: {RESULT_DIR}")
        print(f"     CSV_DIR:    {CSV_DIR}")
        return

    overall_roi    = total_ret / total_bet if total_bet > 0 else 0
    overall_hitpct = hit_count / total_races * 100 if total_races > 0 else 0
    avg_points     = sum(r["n_points"] for r in records) / len(records) if records else 0
    profit         = total_ret - total_bet

    print(f"  集計レース数  : {total_races:,} レース")
    print(f"  平均買い目点数: {avg_points:.1f} 点")
    print(f"  総投資額      : {total_bet:,} 円")
    print(f"  総払戻額      : {total_ret:,} 円")
    print(f"  損益          : {profit:+,} 円")
    print(f"  ROI           : {overall_roi:.4f}  ({overall_roi*100:.2f}%)")
    print(f"  的中率        : {overall_hitpct:.1f}%  ({hit_count}/{total_races}レース)")

    # ROI判定
    print()
    if overall_roi >= 1.15:
        verdict = "✅ 優秀: 実戦投資を検討できるレベル"
    elif overall_roi >= 1.05:
        verdict = "🟡 有望: もう少しデータを積んで判断"
    elif overall_roi >= 0.95:
        verdict = "🟠 要改善: 控除率には勝てていない"
    elif overall_roi >= 0.80:
        verdict = "🔴 危険: このまま投資すると損失大"
    else:
        verdict = "🚫 ロジック根本見直し必要"
    print(f"  判定: {verdict}")

    # ── 月別集計 ────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  ■ 月別集計")
    print("=" * 60)
    print(f"  {'月':8}  {'レース':>6}  {'投資':>10}  {'払戻':>10}  {'ROI':>7}  {'的中率':>7}")
    print("  " + "-" * 55)
    for month in sorted(month_stats.keys()):
        s = month_stats[month]
        roi = s["ret"] / s["bet"] if s["bet"] > 0 else 0
        hit = s["hit"] / s["races"] * 100 if s["races"] > 0 else 0
        print(f"  {month:8}  {s['races']:>6}R  {s['bet']:>9,}円  {s['ret']:>9,}円"
              f"  {roi:>6.3f}  {hit:>5.1f}%")

    # ── 会場別集計（ROI降順）────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  ■ 会場別集計（ROI降順）")
    print("=" * 60)
    print(f"  {'会場':6}  {'レース':>6}  {'投資':>9}  {'払戻':>9}  {'ROI':>7}  {'的中率':>7}")
    print("  " + "-" * 55)

    venue_rows = []
    for v, s in venue_stats.items():
        roi = s["ret"] / s["bet"] if s["bet"] > 0 else 0
        hit = s["hit"] / s["races"] * 100 if s["races"] > 0 else 0
        venue_rows.append((v, s["races"], s["bet"], s["ret"], roi, hit, s["hit"]))
    venue_rows.sort(key=lambda x: -x[4])

    profitable_venues = []
    unprofitable_venues = []
    for v, races, bet, ret, roi, hit, h in venue_rows:
        marker = "✅" if roi >= 1.0 else ("🟡" if roi >= 0.9 else "🔴")
        print(f"  {marker}{v:5}  {races:>6}R  {bet:>8,}円  {ret:>8,}円"
              f"  {roi:>6.3f}  {hit:>5.1f}%")
        if roi >= 1.0 and races >= 20:
            profitable_venues.append(v)
        elif roi < 0.85 and races >= 20:
            unprofitable_venues.append(v)

    # ── 投資推奨サマリ ───────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  ■ 投資判断サマリ")
    print("=" * 60)

    if profitable_venues:
        print(f"\n  ✅ ROI1.0以上（20R以上）の会場 → 投資候補:")
        print(f"     {', '.join(profitable_venues)}")
    else:
        print(f"\n  ✅ ROI1.0以上の会場: なし（全会場でシステムが負けている）")

    if unprofitable_venues:
        print(f"\n  🔴 ROI0.85未満（20R以上）の会場 → 投資停止推奨:")
        print(f"     {', '.join(unprofitable_venues)}")

    # ── 1万円スタートシミュレーション ────────────────────────────────────
    print("\n" + "=" * 60)
    print("  ■ 1万円スタートシミュレーション（ケリー基準 資金5%/レース）")
    print("=" * 60)

    bankroll = 10000
    bankroll_history = [bankroll]
    bust_count = 0

    for r in sorted(records, key=lambda x: (x["date"], x["venue"], x["rno"])):
        if bankroll <= 0:
            bust_count += 1
            break
        # 1レース最大5%
        max_bet  = bankroll * 0.05
        n_points = r["n_points"]
        bet_per  = min(BET_PER_POINT, max_bet / n_points)
        bet_per  = max(bet_per, 10)  # 最低10円
        actual_bet = bet_per * n_points

        if r["hit"]:
            # 払戻: actual_bet / 100 * odds
            actual_ret = (actual_bet / 100) * r["odds"]
        else:
            actual_ret = 0

        bankroll = bankroll - actual_bet + actual_ret
        bankroll_history.append(bankroll)

    min_bankroll = min(bankroll_history)
    max_bankroll = max(bankroll_history)
    final_bankroll = bankroll_history[-1]

    print(f"  初期資金      : 10,000 円")
    print(f"  最終資金      : {final_bankroll:,.0f} 円  ({final_bankroll/100:.1f}倍)")
    print(f"  最小資金      : {min_bankroll:,.0f} 円  (最大ドローダウン: {(1-min_bankroll/10000)*100:.1f}%)")
    print(f"  最大資金      : {max_bankroll:,.0f} 円")
    if bust_count > 0:
        print(f"  ⚠ 破産: {bust_count} 回")
    else:
        print(f"  破産: なし")

    # ── CSV出力 ────────────────────────────────────────────────────────
    out_path = Path("backtest_result.csv")
    import csv
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "date","month","venue","rno","n_points","bet",
            "actual","hit","ret","profit","odds","combos"
        ])
        writer.writeheader()
        writer.writerows(records)

    print(f"\n  詳細CSV出力: {out_path.resolve()}")
    print("  → Excelで開いてピボットテーブル分析が可能です")

    # ── 重要な注意事項 ─────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  ⚠ 注意事項")
    print("=" * 60)
    print("""
  1. このバックテストはシナリオ買いのPython簡略版です。
     実際のJSロジックと±5〜10%の誤差があります。

  2. 「展示情報なし」レースが多数含まれている可能性があります。
     実際の運用では展示情報ありのレースのみ使うため
     本当のROIはここで出た数値より高い可能性があります。

  3. バックテスト期間（5ヶ月）は統計的には不十分です。
     少なくとも1年分のデータで再検証することを推奨します。

  4. この数字は「過去に使えた」ことの証明であり、
     「将来も使える」保証ではありません。
     実戦は月に1,000円規模で試すことから始めてください。
""")
    print("=" * 60)
    print("  バックテスト完了")
    print("=" * 60)


if __name__ == "__main__":
    run_backtest()
