# -*- coding: utf-8 -*-
"""
lr_log.py  ─  予想ログ保存 / ROI バックテスト
分割元: load_race.py
"""
import json, glob, pathlib
from lr_utils import sep

def _build_prediction_entry(race_no, bet_suggestions, race_judgment):
    """
    1レース分の予想ログエントリ（dict）を生成して返す。
    ファイルへの書き込みは行わない。_flush_prediction_log() で一括書き込みする。
    """
    _combos_raw = bet_suggestions.get("combos", [])
    combos_full = [
        {
            "combo":            c["combo"],
            "prob":             round(float(c["prob"]), 6),
            "theoretical_odds": c.get("theoretical_odds"),
            "hybrid_score":     round(float(c.get("hybrid_score", 0)), 5),
            "top_scenario":     c.get("top_scenario", "-"),
        }
        for c in _combos_raw
        if float(c.get("prob", 0)) >= 0.0005
    ]
    return {
        "race_no":          int(race_no) if str(race_no).isdigit() else race_no,
        "buy_list":         bet_suggestions.get("buy_list", []),
        "point_count":      bet_suggestions.get("point_count", 0),
        "candidates":       bet_suggestions.get("candidates", []),
        "axis_candidates":  bet_suggestions.get("axis_candidates", []),
        "himo_candidates":  bet_suggestions.get("himo_candidates", []),
        "comment":          bet_suggestions.get("comment", ""),
        "rank":             (race_judgment or {}).get("rank",     bet_suggestions.get("rank",     "-")),
        "score":            (race_judgment or {}).get("score",    bet_suggestions.get("score",    0)),
        "strategy":         (race_judgment or {}).get("strategy", bet_suggestions.get("strategy", "")),
        "ryotate_verdict":  bet_suggestions.get("ryotate_verdict", "-"),
        "ryotate_reason":   bet_suggestions.get("ryotate_detail", {}).get("reason", ""),
        "himo_are_verdict": ((race_judgment or {}).get("himo_are") or {}).get("verdict", "対象外"),
        "himo_are_mcp":     ((race_judgment or {}).get("himo_are") or {}).get("max_combo_prob"),
        "himo_are_est_odds":((race_judgment or {}).get("himo_are") or {}).get("est_top_odds"),
        "himo_are_cc":      ((race_judgment or {}).get("himo_are") or {}).get("circle_concentration"),
        "combos_full":      combos_full,
        # 結果欄（レース後に手動記入）- 初期値はNone
        "result_1st": None,
        "result_2nd": None,
        "result_3rd": None,
        "hit":        None,
        "dividend":   None,
    }


def _save_prediction_log(venue, race_date, race_no, results, bet_suggestions, race_judgment=None):
    """
    予想ログを logs/YYYY-MM-DD_会場名.json に保存する。
    refine_tenji.py が candidates / buy_list を参照するために必須。
    check_ev.py が combos_full を使って当日オッズとEV計算を行う。
    レース後に result_1st / result_2nd / result_3rd / hit / dividend を手動記入すること。

    【高速化】エントリ生成のみ行い、ファイル書き込みは _flush_prediction_log() に委譲。
    ただし単体呼び出し時の後方互換のため、単独でも書き込む。
    """
    logs_dir = pathlib.Path(__file__).parent.parent / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    date_str = str(race_date).replace("/", "-")[:10]
    log_path = logs_dir / f"{date_str}_{venue}.json"

    log_data = {"venue": venue, "date": date_str, "races": []}
    if log_path.exists():
        try:
            with open(log_path, encoding="utf-8") as f:
                log_data = json.load(f)
        except Exception:
            pass

    new_entry = _build_prediction_entry(race_no, bet_suggestions, race_judgment)
    # 既存エントリの結果欄を引き継ぐ
    for ex in log_data.get("races", []):
        if str(ex.get("race_no")) == str(race_no):
            for k in ("result_1st", "result_2nd", "result_3rd", "hit", "dividend"):
                new_entry[k] = ex.get(k)
            log_data["races"].remove(ex)
            break
    log_data.setdefault("races", []).append(new_entry)

    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log_data, f, ensure_ascii=False, indent=2)
    print(f"  ? 予想ログ保存: {log_path.name} ({race_no}R)")


def _flush_prediction_log(venue, race_date, entries):
    """
    複数レース分のエントリをまとめて1回でファイルに書き込む（高速化版）。
    entries: list of (race_no, bet_suggestions, race_judgment)
    """
    if not entries:
        return
    logs_dir = pathlib.Path(__file__).parent.parent / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    date_str = str(race_date).replace("/", "-")[:10]
    log_path = logs_dir / f"{date_str}_{venue}.json"

    # 既存ログを1回だけ読み込む
    log_data = {"venue": venue, "date": date_str, "races": []}
    if log_path.exists():
        try:
            with open(log_path, encoding="utf-8") as f:
                log_data = json.load(f)
        except Exception:
            pass

    # 既存エントリをrace_noをキーにした辞書に変換
    existing_map = {str(e.get("race_no")): e for e in log_data.get("races", [])}

    new_races = []
    for race_no, bet_suggestions, race_judgment in entries:
        new_entry = _build_prediction_entry(race_no, bet_suggestions, race_judgment)
        # 既存の結果欄を引き継ぐ
        ex = existing_map.get(str(race_no), {})
        for k in ("result_1st", "result_2nd", "result_3rd", "hit", "dividend"):
            if ex.get(k) is not None:
                new_entry[k] = ex[k]
        new_races.append(new_entry)
        print(f"  ? 予想ログ蓄積: {race_no}R")

    log_data["races"] = new_races
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log_data, f, ensure_ascii=False, indent=2)
    print(f"  [SAVE] 予想ログ一括保存: {log_path.name} ({len(new_races)}R分)")


# ============================================================
# 回収率バックテスト（ログファイルから集計）
# ============================================================
def calc_roi_from_logs(logs_dir=None, strategy_filter=None):
    """
    logs/ フォルダの予想ログ（JSON）から回収率バックテストを実行する。

    レース後に手動記入した result_1st/result_2nd/result_3rd/hit/dividend を読み込み、
    戦略タイプ・ランク別の回収率（ROI）を集計して返す。

    【使い方】
        from load_race import calc_roi_from_logs
        summary = calc_roi_from_logs()
        print(summary)

    【出力形式】
        {
          "total_bets":    全ベット点数合計,
          "total_hits":    3連単的中数,
          "total_cost":    総購入金額（100円/点換算）,
          "total_payout":  総払戻金額,
          "roi":           回収率 (払戻/購入, 例: 1.23 = 123%),
          "hit_rate":      3連単的中率 (0〜1),
          "by_rank":       ランク別集計 {"S": {...}, "A": {...}, ...},
          "by_venue":      会場別集計,
          "skip_races":    見送り推奨（ランクD）だったレース数,
          "missing_logs":  結果未記入のレース数（dividend=None）,
          "details":       全レース詳細リスト,
        }

    Parameters
    ----------
    logs_dir       : Path or str  ログフォルダ（省略時: ../logs/）
    strategy_filter: str or None  "全速型"等で絞り込み（Noneは全戦略）
    """
    if logs_dir is None:
        logs_dir = pathlib.Path(__file__).parent.parent / "logs"
    logs_dir = pathlib.Path(logs_dir)

    if not logs_dir.exists():
        print(f"  [!]  logsフォルダが存在しません: {logs_dir}")
        return None

    log_files = sorted(logs_dir.glob("*.json"))
    if not log_files:
        print(f"  [!]  ログファイルが見つかりません: {logs_dir}")
        return None

    # 集計用変数
    total_bets    = 0
    total_hits    = 0
    total_cost    = 0      # 100円/点換算
    total_payout  = 0
    missing_logs  = 0
    skip_races    = 0
    details       = []

    by_rank   = {r: {"bets": 0, "hits": 0, "cost": 0, "payout": 0, "races": 0}
                 for r in ("S", "A", "B", "C", "D", "-")}
    by_venue  = {}

    for log_file in log_files:
        try:
            with open(log_file, encoding="utf-8") as f:
                log_data = json.load(f)
        except Exception as e:
            print(f"  [!]  ログ読み込みエラー: {log_file.name} ({e})")
            continue

        venue    = log_data.get("venue", "不明")
        date_str = log_data.get("date", "")

        for entry in log_data.get("races", []):
            race_no    = entry.get("race_no", "?")
            buy_list   = entry.get("buy_list", [])
            point_count = entry.get("point_count", len(buy_list))
            hit        = entry.get("hit")         # True/False/None
            dividend   = entry.get("dividend")    # 払戻金額（100円単位）/ None
            rank       = entry.get("rank", "-")   # ランク（S/A/B/C/D）

            # 結果未記入のレースはカウントのみ
            if dividend is None:
                missing_logs += 1
                continue

            cost   = point_count * 100  # 100円/点
            payout = int(dividend) if hit else 0

            total_bets   += point_count
            total_cost   += cost
            total_payout += payout
            if hit:
                total_hits += 1

            # 見送りレース（ランクD or 買い目0点）をカウント
            if rank == "D" or point_count == 0:
                skip_races += 1

            # ランク別
            r_key = rank if rank in by_rank else "-"
            by_rank[r_key]["bets"]   += point_count
            by_rank[r_key]["hits"]   += (1 if hit else 0)
            by_rank[r_key]["cost"]   += cost
            by_rank[r_key]["payout"] += payout
            by_rank[r_key]["races"]  += 1

            # 会場別
            if venue not in by_venue:
                by_venue[venue] = {"bets": 0, "hits": 0, "cost": 0, "payout": 0, "races": 0}
            by_venue[venue]["bets"]   += point_count
            by_venue[venue]["hits"]   += (1 if hit else 0)
            by_venue[venue]["cost"]   += cost
            by_venue[venue]["payout"] += payout
            by_venue[venue]["races"]  += 1

            details.append({
                "date":       date_str,
                "venue":      venue,
                "race_no":    race_no,
                "rank":       rank,
                "buy_list":   buy_list,
                "point_count": point_count,
                "hit":        hit,
                "dividend":   dividend,
                "cost":       cost,
                "payout":     payout,
                "roi":        round(payout / cost, 3) if cost > 0 else 0,
            })

    if total_cost == 0:
        print("  [!]  結果が記入されたレースが見つかりません。")
        print("  　  logs/*.json の result_1st/result_2nd/result_3rd/hit/dividend を記入してください。")
        return None

    roi = round(total_payout / total_cost, 4) if total_cost > 0 else 0.0
    hit_rate = round(total_hits / max(len(details), 1), 4)

    # ランク別ROI計算
    for rk_data in by_rank.values():
        rk_data["roi"] = round(rk_data["payout"] / max(rk_data["cost"], 1), 4)
        rk_data["hit_rate"] = round(rk_data["hits"] / max(rk_data["races"], 1), 4)

    # 会場別ROI計算
    for vk_data in by_venue.values():
        vk_data["roi"] = round(vk_data["payout"] / max(vk_data["cost"], 1), 4)
        vk_data["hit_rate"] = round(vk_data["hits"] / max(vk_data["races"], 1), 4)

    summary = {
        "total_bets":   total_bets,
        "total_hits":   total_hits,
        "total_cost":   total_cost,
        "total_payout": total_payout,
        "roi":          roi,
        "roi_pct":      f"{roi*100:.1f}%",
        "hit_rate":     hit_rate,
        "hit_rate_pct": f"{hit_rate*100:.1f}%",
        "total_races":  len(details),
        "missing_logs": missing_logs,
        "skip_races":   skip_races,
        "by_rank":      by_rank,
        "by_venue":     by_venue,
        "details":      details,
    }

    # ── コンソール出力 ──
    sep()
    print("  ? 回収率バックテスト結果")
    sep()
    print(f"  対象レース数   : {len(details)}")
    print(f"  総ベット点数   : {total_bets}")
    print(f"  総購入金額     : {total_cost:,}円")
    print(f"  総払戻金額     : {total_payout:,}円")
    print(f"  3連単的中数    : {total_hits}（的中率 {hit_rate*100:.1f}%）")
    print(f"  回収率         : {roi*100:.1f}%  ({'[OK]プラス' if roi >= 1.0 else '[NG]マイナス'})")
    print()
    print("  ランク別:")
    for rk, rk_data in by_rank.items():
        if rk_data["races"] == 0:
            continue
        print(f"    [{rk}] {rk_data['races']:3}レース | "
              f"的中{rk_data['hit_rate']*100:.0f}% | "
              f"ROI {rk_data['roi']*100:.1f}% | "
              f"{rk_data['cost']:,}→{rk_data['payout']:,}円")
    print()
    print("  会場別（ROI上位）:")
    venue_sorted = sorted(by_venue.items(), key=lambda x: x[1]["roi"], reverse=True)
    for vn, vk_data in venue_sorted[:5]:
        print(f"    {vn:6} | {vk_data['races']:3}レース | "
              f"ROI {vk_data['roi']*100:.1f}% | "
              f"的中{vk_data['hit_rate']*100:.0f}%")
    sep()

    return summary



