# -*- coding: utf-8 -*-
"""
refine_tenji.py - 展示タイム連携・買い目絞り込みスクリプト（Step4）
=====================================================================
【使い方】
  # 対話モード（推奨）
  python scripts/refine_tenji.py

  # 展示タイムだけ渡す（除外艇は後から対話入力）
  python scripts/refine_tenji.py --venue 大村 --race 5 --tenji 1:6.80 2:6.92 3:6.87 4:7.01 5:6.95 6:7.10

  # 除外艇まで指定してフル自動
  python scripts/refine_tenji.py --venue 大村 --race 5 --tenji 1:6.80 2:6.92 3:6.87 4:7.01 5:6.95 6:7.10 --exclude 4 6

  # 日付指定（当日以外のログを参照）
  python scripts/refine_tenji.py --venue 大村 --race 5 --date 2026-03-05 --tenji 1:6.80 2:6.92 3:6.87 4:7.01 5:6.95 6:7.10

【設計方針】
  展示タイムは「判断材料の提示」に使う。自動除外はしない。
  - 展示タイム・偏差値を並べて表示
  - 「どの艇を外すか」は人間が入力
  - 除外後の候補から最終買い目を確定してログに保存

【前提】
  load_race.py を当日実行済みで logs/YYYY-MM-DD_会場名.json が存在すること。

【出力】
  コンソール: 展示タイム・偏差値一覧 → 人間が除外艇を入力 → 最終買い目
  JSON更新:  tenji_data（偏差値辞書）・tenji_excluded（除外艇）・tenji_buy_list（確定買い目）を追記
"""

import os
import sys
import json
import argparse
import pathlib
import statistics
from datetime import datetime, date

# ============================================================
# パス設定
# ============================================================
BASE_DIR = pathlib.Path(__file__).parent.parent
LOGS_DIR = BASE_DIR / "logs"

# ============================================================
# ユーティリティ
# ============================================================
def sep(char="=", n=55):
    print(char * n)


def safe_float(val, default=None):
    try:
        v = str(val).replace("%", "").strip()
        return float(v) if v not in ("", "None", "nan", "-") else default
    except Exception:
        return default


# ============================================================
# 偏差値計算（タイムあり艇のみで計算）
# ============================================================
def calc_hensa(tenji_times: dict) -> dict:
    """
    展示タイム辞書 {艇番str: タイムfloat} から偏差値辞書を計算する。
    速い（小さい）ほど偏差値が高い。

    タイムが入力された艇のみで平均・標準偏差を計算する。
    タイムなし艇はこの辞書に含まれない（呼び出し側で「計測なし」として扱う）。
    """
    times = list(tenji_times.values())
    if len(times) < 2:
        return {w: 50.0 for w in tenji_times}

    mean = statistics.mean(times)
    try:
        stdev = statistics.stdev(times)
    except statistics.StatisticsError:
        stdev = 0.0

    hensa = {}
    for waku, t in tenji_times.items():
        if stdev == 0:
            hensa[waku] = 50.0
        else:
            # 速い(小さい) → 偏差値高い
            hensa[waku] = round((mean - t) / stdev * 10 + 50, 2)
    return hensa


# ============================================================
# 展示タイム・偏差値の表示
# ============================================================
def print_tenji_table(race_no, all_wakus: list, tenji_times: dict, hensa: dict):
    """
    全艇の展示タイム・偏差値をコンソールに表示する。
    タイムなし艇は「計測なし」として表示。
    偏差値はあくまで参考。自動除外はしない。
    """
    sep()
    print(f"  {race_no}R 展示タイム一覧")
    sep("-")
    print(f"  {'艇番':>4}  {'展示タイム':>10}  {'偏差値':>8}  {'参考':>10}")
    print(f"  {'-'*4}  {'-'*10}  {'-'*8}  {'-'*10}")

    for waku in sorted(all_wakus, key=lambda x: int(x) if x.isdigit() else 99):
        if waku in tenji_times:
            t = tenji_times[waku]
            h = hensa.get(waku, 50.0)
            if h >= 60:
                comment = "速い"
            elif h <= 40:
                comment = "遅め"
            else:
                comment = ""
            print(f"  {waku:>4}号  {t:>10.3f}  {h:>8.2f}  {comment}")
        else:
            print(f"  {waku:>4}号  {'---':>10}  {'---':>8}  計測なし")

    sep("-")
    print()
    print("  ※ 偏差値は参考値です。除外艇は次のステップで人間が判断してください。")
    print()


# ============================================================
# 人間による除外艇の入力
# ============================================================
def ask_exclude_boats(race_no: int, all_wakus: list) -> set:
    """
    除外する艇番を人間に入力させる。
    除外なしの場合はそのままEnter。
    """
    print(f"  除外する艇番を入力（スペース区切り・なければEnter）")
    raw = input(f"  {race_no}R 除外艇番: ").strip()

    if not raw:
        print(f"  → 除外なし")
        return set()

    excluded = set()
    for token in raw.split():
        if token in all_wakus:
            excluded.add(token)
        else:
            print(f"  ⚠️  '{token}' は有効な艇番ではありません（スキップ）")

    if excluded:
        print(f"  → 除外: {', '.join(sorted(excluded, key=int))}号")
    return excluded


# ============================================================
# 買い目絞り込み（人間が指定した除外艇を適用）
# ============================================================
def refine_candidates(candidates: list, excluded: set) -> list:
    """
    除外艇を1着・2着から取り除く。
    3着はヒモとして残す（除外しない）。
    """
    if not excluded:
        return candidates

    return [
        c for c in candidates
        if c["first"] not in excluded and c["second"] not in excluded
    ]


# ============================================================
# 最終買い目の表示
# ============================================================
def print_final_buys(race_no, excluded: set, refined: list, final_buys: list):
    if excluded:
        print(f"  除外艇: {', '.join(sorted(excluded, key=int))}号（1着・2着から除外）")
    else:
        print(f"  除外なし（全候補をそのまま使用）")
    print()

    if refined:
        disp = min(len(refined), 10)
        print(f"  絞り込み後 候補（上位{disp}組）:")
        for i, c in enumerate(refined[:disp]):
            prob_pct = f"{c['prob'] * 100:.2f}%" if c.get("prob") else "-"
            odds_str = f"{c['theoretical_odds']:.0f}倍" if c.get("theoretical_odds") else "-"
            print(f"    {i+1:2}. {c['combo']}  確率:{prob_pct}  理論Odds:{odds_str}")
    else:
        print(f"  ⚠️  絞り込み後の候補がありません（除外艇を減らしてください）")

    print()
    if final_buys:
        print(f"  🎯 最終確定買い目（{len(final_buys)}点）:")
        for i, b in enumerate(final_buys, 1):
            print(f"    {i:2}. {b}")
    else:
        print(f"  ⚠️  確定買い目なし")
    sep()


# ============================================================
# JSONログ操作
# ============================================================
def find_log_file(venue: str, race_date: str = None):
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    if race_date:
        path = LOGS_DIR / f"{race_date}_{venue}.json"
        if path.exists():
            return path
    else:
        today = date.today().strftime("%Y-%m-%d")
        path = LOGS_DIR / f"{today}_{venue}.json"
        if path.exists():
            return path

    # フォールバック: 会場名を含む最新ファイル
    all_logs = sorted(LOGS_DIR.glob(f"*_{venue}.json"))
    if all_logs:
        print(f"  ℹ️  最新ログを使用: {all_logs[-1].name}")
        return all_logs[-1]

    return None


def load_log(log_path) -> dict:
    with open(log_path, encoding="utf-8") as f:
        return json.load(f)


def save_log(log_path, log_data: dict):
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log_data, f, ensure_ascii=False, indent=2)
    print(f"  💾 ログ更新: {log_path.name}")


def get_race_entry(log_data: dict, race_no: int):
    if "races" in log_data:
        for entry in log_data["races"]:
            if str(entry.get("race_no") or entry.get("R")) == str(race_no):
                return entry
    else:
        for key in [f"{race_no}R", str(race_no)]:
            if key in log_data:
                return log_data[key]
    return None


def get_candidates_from_log(log_data: dict, race_no: int) -> list:
    entry = get_race_entry(log_data, race_no)
    if entry is None:
        return []

    candidates = entry.get("candidates", [])
    if candidates:
        return candidates

    # フォールバック: buy_list から再構築
    buy_list = entry.get("buy_list", [])
    if buy_list:
        print(f"  ℹ️  candidates がログにないため buy_list をフォールバックとして使用")
        result = []
        for b in buy_list:
            parts = b.split("→")
            result.append({
                "combo":            b,
                "first":            parts[0] if len(parts) > 0 else "",
                "second":           parts[1] if len(parts) > 1 else "",
                "third":            parts[2] if len(parts) > 2 else "",
                "prob":             0.0,
                "theoretical_odds": 0.0,
                "hybrid_score":     0.0,
            })
        return result

    return []


def update_log_with_tenji(log_data: dict, race_no: int,
                           hensa: dict, excluded: set, final_buys: list) -> dict:
    entry = get_race_entry(log_data, race_no)

    fields = {
        "tenji_data":       hensa,
        "tenji_excluded":   sorted(list(excluded), key=int) if excluded else [],
        "tenji_buy_list":   final_buys,
        "tenji_updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    if entry is not None:
        entry.update(fields)
    else:
        print(f"  ⚠️  {race_no}R のエントリがログにないため新規追加します")
        new_entry = {"race_no": race_no}
        new_entry.update(fields)
        log_data.setdefault("races", []).append(new_entry)

    return log_data


# ============================================================
# 1レース分の処理
# ============================================================
def process_one_race(race_no: int, tenji_times: dict, excluded_arg: set,
                     log_path, log_data: dict) -> dict:
    """
    展示タイム表示 → 除外艇入力 → 買い目確定 → ログ保存。
    excluded_arg が空でなければ対話入力をスキップ。
    """
    # 全艇番の収集（candidates + tenji_times の両方から）
    candidates = get_candidates_from_log(log_data, race_no)
    all_wakus_set = set(tenji_times.keys())
    for c in candidates:
        for k in ["first", "second", "third"]:
            if c.get(k):
                all_wakus_set.add(c[k])
    all_wakus = sorted(all_wakus_set, key=lambda x: int(x) if x.isdigit() else 99)

    # ① 偏差値計算
    hensa = calc_hensa(tenji_times)

    # ② 表示
    print_tenji_table(race_no, all_wakus, tenji_times, hensa)

    # ③ 除外艇の決定
    if excluded_arg:
        excluded = excluded_arg
        print(f"  除外艇（引数指定）: {', '.join(sorted(excluded, key=int))}号")
        print()
    else:
        excluded = ask_exclude_boats(race_no, all_wakus)
        print()

    # candidates がなければここで終了
    if not candidates:
        print(f"  ⚠️  {race_no}R: ログに candidates がありません。偏差値表示のみ。")
        save_log(log_path, update_log_with_tenji(log_data, race_no, hensa, excluded, []))
        return {"hensa": hensa, "excluded": excluded, "final_buys": []}

    # ④ 絞り込み
    refined = refine_candidates(candidates, excluded)

    # ⑤ 最終買い目（point_count に合わせる）
    entry    = get_race_entry(log_data, race_no)
    target_n = (entry.get("point_count") or 6) if entry else 6
    final_buys = [c["combo"] for c in refined[:target_n]]

    # ⑥ 表示
    print_final_buys(race_no, excluded, refined, final_buys)

    # ⑦ ログ保存
    updated = update_log_with_tenji(log_data, race_no, hensa, excluded, final_buys)
    save_log(log_path, updated)

    return {"hensa": hensa, "excluded": excluded, "final_buys": final_buys}


# ============================================================
# 対話入力
# ============================================================
def interactive_input():
    sep()
    print("  refine_tenji.py - 展示後買い目絞り込み")
    sep("-")

    venue = input("  会場名（例: 大村）: ").strip()
    if not venue:
        print("❌ 会場名が未入力です")
        sys.exit(1)

    race_raw = input("  レース番号（例: 5  または 5 6 7）: ").strip()
    try:
        race_nos = [int(r) for r in race_raw.split()]
    except ValueError:
        print("❌ レース番号は整数で入力してください")
        sys.exit(1)

    tenji_by_race = {}
    for race_no in race_nos:
        print()
        print(f"  ── {race_no}R 展示タイム ──")
        print(f"  入力形式: 1:6.80 2:6.92 3:6.87（タイム不明な艇は省略可）")
        raw = input(f"  {race_no}R: ").strip()
        times = parse_tenji_str(raw.split())
        if times:
            tenji_by_race[race_no] = times
        else:
            print(f"  ⚠️  {race_no}R: タイム未入力 → スキップ")

    return venue, race_nos, tenji_by_race


# ============================================================
# 展示タイム文字列パース
# ============================================================
def parse_tenji_str(tokens: list) -> dict:
    result = {}
    for token in tokens:
        if ":" not in token:
            print(f"  ⚠️  '{token}' は 艇番:タイム 形式ではありません（スキップ）")
            continue
        waku, _, t_str = token.partition(":")
        t = safe_float(t_str)
        if t is None:
            print(f"  ⚠️  '{token}' のタイムが数値ではありません（スキップ）")
            continue
        result[waku.strip()] = t
    return result


# ============================================================
# メイン
# ============================================================
def main():
    parser = argparse.ArgumentParser(
        description="展示タイム連携・買い目絞り込み（Step4）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # 対話モード（推奨）
  python scripts/refine_tenji.py

  # 展示タイムだけ渡す（除外艇は後から対話入力）
  python scripts/refine_tenji.py --venue 大村 --race 5 --tenji 1:6.80 2:6.92 3:6.87 4:7.01 5:6.95 6:7.10

  # 除外艇まで指定してフル自動
  python scripts/refine_tenji.py --venue 大村 --race 5 --tenji 1:6.80 2:6.92 3:6.87 4:7.01 5:6.95 6:7.10 --exclude 4 6

  # 日付指定
  python scripts/refine_tenji.py --venue 大村 --race 5 --date 2026-03-05 --tenji 1:6.80 2:6.92 3:6.87 4:7.01 5:6.95 6:7.10
        """
    )
    parser.add_argument("--venue",   type=str, default=None, help="会場名（例: 大村）")
    parser.add_argument("--race",    type=int, nargs="+", default=None, help="レース番号（複数可）")
    parser.add_argument("--date",    type=str, default=None, help="日付（例: 2026-03-05）")
    parser.add_argument("--tenji",   type=str, nargs="+", default=None,
                        help="展示タイム（例: 1:6.80 2:6.92 ...）")
    parser.add_argument("--exclude", type=str, nargs="+", default=None,
                        help="除外する艇番（例: 4 6）")
    args = parser.parse_args()

    # 引数が不完全なら対話モード
    if args.venue is None or args.race is None:
        venue, race_nos, tenji_by_race = interactive_input()
        excluded_arg = set()
    else:
        sep()
        print("  refine_tenji.py - 展示後買い目絞り込み")
        sep()
        venue    = args.venue
        race_nos = args.race

        if args.tenji is None:
            print("❌ --tenji が未指定です")
            parser.print_help()
            sys.exit(1)

        tenji_times   = parse_tenji_str(args.tenji)
        tenji_by_race = {rno: tenji_times for rno in race_nos}
        excluded_arg  = set(args.exclude) if args.exclude else set()

    # ログ検索
    log_path = find_log_file(venue, args.date if hasattr(args, "date") else None)
    if log_path is None:
        print(f"❌ {venue}のログが見つかりません")
        print(f"   load_race.py を先に実行してください")
        sys.exit(1)

    print(f"  📂 ログ: {log_path.name}")
    log_data = load_log(log_path)

    # レースごとに処理
    results_all = {}
    for race_no in race_nos:
        tenji_times = tenji_by_race.get(race_no)
        if not tenji_times:
            print(f"  ⚠️  {race_no}R: 展示タイムなし → スキップ")
            continue

        result = process_one_race(race_no, tenji_times, excluded_arg,
                                  log_path, log_data)
        results_all[race_no] = result
        log_data = load_log(log_path)

    # サマリ
    sep()
    print(f"  ✅ 完了: {venue}  対象レース {list(results_all.keys())}")
    for rno, res in results_all.items():
        exc_str  = ", ".join(sorted(res["excluded"], key=int)) if res["excluded"] else "なし"
        buys_str = "  ".join(res["final_buys"]) if res["final_buys"] else "なし"
        print(f"    {rno}R: 除外={exc_str}  確定{len(res['final_buys'])}点: {buys_str}")
    sep()


if __name__ == "__main__":
    main()
