r"""
evaluate_model_unified.py  (改良版)
master_data.json の1着率予測精度を results.csv で評価する。

【改良点】
    1. 補正段階別の比較評価
         補正なし（base_rate のみ）
         ST補正+フォーム補正（現行モデル相当）
         ※ calcTenkaiProbs / calcTenjiDelta をPython移植して追加可能
    2. 非均等キャリブレーションバケツ
         高確率帯（0.4以上）を 0.05 刻みに細分化
    3. 会場別・コース別の精度内訳
         会場ごとの Brier / Log Loss / Top1 / 1枠過大評価
         コース別の Top1的中率・平均予測確率

【配置前提】
    C:\Users\user\Desktop\データ収集\
    ├── scripts\
    │   └── evaluate_model_unified.py   ← このファイル
    ├── data_csv\
    │   ├── 202401_results.csv
    │   └── ...
    └── master_data.json

使い方:
    cd C:\Users\user\Desktop\データ収集\scripts
    python evaluate_model_unified.py

    # パスを明示する場合
    python evaluate_model_unified.py <results_csv_dir> <master_json_path> [output_dir]

出力:
    accuracy_report.txt     : 人間が読めるテキストレポート
    accuracy_report.json    : 指標サマリー（全段階）
    calibration.csv         : キャリブレーション詳細（非均等バケツ）
    venue_breakdown.csv     : 会場別精度内訳
    course_breakdown.csv    : コース別精度内訳

【評価指標】
    Brier Score   : 予測確率と結果のズレ（0に近いほど良い、0.25がランダム基準）
    Log Loss      : 自信を持って外した予測に大ペナルティ
    Calibration   : 「0.6と予測したレースで実際何%1着か」のズレ
    Top1 Accuracy : 最も高い確率を付けた選手が1着になった割合
    vs Baseline   : 「常にコース1を予想」との比較

【results.csv の想定列】
    日付, 会場名, レース番号, レース種別, 距離, 天候, 風向, 風速,
    波高, 決まり手, 着順, 艇番, 登録番号, 選手名,
    モーター番号, ボート番号, 展示タイム, 進入コース, スタートタイム, レースタイム
"""

import sys
import json
import math
import csv
import glob
import os
from pathlib import Path
from collections import defaultdict


# ── results.csv の列インデックス（0始まり）──────────────────────────
COL_DATE    = 0
COL_VENUE   = 1
COL_RACE    = 2
COL_RANK    = 10
COL_FRAME   = 11
COL_REG_NO  = 12
COL_NAME    = 13
COL_COURSE  = 17
COL_ST      = 18


# ── 予測パラメータ ──────────────────────────────────────────────────
VENUE_COURSE_MIN_RUNS  = 10
COURSE_MASTER_MIN_RUNS = 20

# ── 非均等キャリブレーションバケツ定義 ──────────────────────────────
# (下限, 上限) のリスト。高確率帯を細かく区切る。
CALIB_BUCKETS = [
    (0.00, 0.10), (0.10, 0.20), (0.20, 0.30), (0.30, 0.40),
    (0.40, 0.45), (0.45, 0.50), (0.50, 0.55), (0.55, 0.60),
    (0.60, 0.65), (0.65, 0.70), (0.70, 0.75), (0.75, 0.80),
    (0.80, 1.01),
]


# ──────────────────────────────────────────────────────────────────
# データ読み込み
# ──────────────────────────────────────────────────────────────────

def load_results(csv_dir: str) -> list[dict]:
    pattern = os.path.join(csv_dir, "*_results.csv")
    files = sorted(glob.glob(pattern))
    if not files:
        pattern = os.path.join(csv_dir, "**", "*_results.csv")
        files = sorted(glob.glob(pattern, recursive=True))

    if not files:
        print(f"警告: {csv_dir} に *_results.csv が見つかりません")
        return []

    print(f"  results CSV: {len(files)} ファイル")

    races = defaultdict(list)

    for fpath in files:
        for enc in ["utf-8", "shift_jis", "cp932", "utf-8-sig"]:
            try:
                with open(fpath, encoding=enc, newline="") as f:
                    reader = csv.reader(f)
                    next(reader, None)
                    for row in reader:
                        if len(row) <= max(COL_COURSE, COL_RANK):
                            continue
                        date    = row[COL_DATE].strip()
                        venue   = row[COL_VENUE].strip()
                        race_no = _safe_int(row[COL_RACE])
                        rank    = _safe_int(row[COL_RANK])
                        course  = _safe_int(row[COL_COURSE])
                        name    = row[COL_NAME].strip()
                        reg_no  = row[COL_REG_NO].strip()
                        st      = _safe_float(row[COL_ST])

                        if not all([date, venue, race_no, rank, course, name]):
                            continue

                        race_key = f"{date}_{venue}_{race_no}"
                        races[race_key].append({
                            "name":   _normalize_name(name),
                            "reg_no": reg_no,
                            "course": course,
                            "rank":   rank,
                            "st":     st,
                            "boat":   course,
                        })
                break
            except (UnicodeDecodeError, LookupError):
                continue

    result_list = []
    for race_key, entrants in races.items():
        parts = race_key.split("_")
        result_list.append({
            "race_key": race_key,
            "date":     parts[0],
            "venue":    parts[1],
            "race_no":  int(parts[2]),
            "entrants": sorted(entrants, key=lambda x: x["course"]),
        })

    print(f"  レース数: {len(result_list)}")
    return result_list


def load_master(json_path: str) -> dict:
    with open(json_path, encoding="utf-8") as f:
        return json.load(f)


# ──────────────────────────────────────────────────────────────────
# 補正関数
# ──────────────────────────────────────────────────────────────────

def _normalize_name(name: str) -> str:
    return str(name).replace("\u3000", "").replace(" ", "").strip()


def _resolve_player_name(raw_name: str, reg_no: str, master: dict) -> str:
    id_map = master.get("player_id_map", {})
    reg_str = str(reg_no).strip() if reg_no else ""
    if reg_str and reg_str in id_map:
        return id_map[reg_str]
    normalized = _normalize_name(raw_name)
    for official in master.get("course_master", {}):
        if official.startswith(normalized):
            return official
    return normalized


def _st_rank_to_correction(st_rank) -> float:
    if st_rank is None:
        return 1.0
    raw = 1.0 + (3.5 - float(st_rank)) * (0.2 / 2.5)
    return max(0.7, min(1.2, raw))


def _form_correction(player_idx: dict | None, overall_win: float | None) -> float:
    if not player_idx:
        return 1.0
    fly_days       = player_idx.get("fly_days")
    fly_after_runs = player_idx.get("fly_after_runs") or 0
    if fly_days is not None and fly_after_runs < 10:
        return 0.85
    recent5 = player_idx.get("recent5_win")
    base    = overall_win or player_idx.get("overall_win")
    if recent5 is None or not base or base <= 0:
        return 1.0
    diff = recent5 - base
    if diff >= 0.15:
        return 1.10
    if diff <= -0.15:
        return 0.90
    return 1.0


def _max_prob_by_arek(arek_score: float) -> float:
    norm = max(0.0, min((arek_score - 39.0) / (60.0 - 39.0), 1.0))
    return round(0.82 - norm * 0.10, 4)


# ──────────────────────────────────────────────────────────────────
# 予測確率の生成（段階別）
# ──────────────────────────────────────────────────────────────────

def _get_base_rates(race: dict, master: dict) -> dict[str, dict]:
    """
    各選手のベース1着率と補正係数を返す。

    戻り値: {raw_name: {"base": float, "st_corr": float, "form_corr": float, "name": str}}
    """
    venue   = race["venue"]
    race_no = str(race["race_no"])

    course_master       = master.get("course_master", {})
    venue_course_master = master.get("venue_course_master", {})
    venue_stats         = master.get("venue_stats", {}).get(venue, {})
    player_index        = master.get("player_index", {})

    race_course_rates  = venue_stats.get("race_course_rates", {}).get(race_no, {})
    venue_course_rates = venue_stats.get("course_rates", {})

    result = {}

    for ent in race["entrants"]:
        raw_name = ent["name"]
        reg_no   = ent.get("reg_no", "")
        course   = str(ent["course"])

        name = _resolve_player_name(raw_name, reg_no, master)

        # ── ベース1着率 ──
        base_rate = None

        vc = venue_course_master.get(name, {}).get(venue, {}).get(course)
        if vc and vc.get("reliable"):
            base_rate = vc.get("ts_win_rate") or vc.get("win_rate")

        if base_rate is None:
            cm = course_master.get(name, {}).get(course)
            if cm and cm.get("reliable"):
                base_rate = cm.get("ts_win_rate") or cm.get("win_rate")

        if base_rate is None:
            rv = race_course_rates.get(course) or venue_course_rates.get(course)
            if rv is not None:
                base_rate = rv

        if base_rate is None:
            fallback = None
            if vc:
                fallback = vc.get("ts_win_rate") or vc.get("win_rate")
            if fallback is None:
                cm = course_master.get(name, {}).get(course)
                if cm:
                    fallback = cm.get("ts_win_rate") or cm.get("win_rate")
            base_rate = fallback if fallback is not None else 0.001

        base_rate = max(base_rate, 0.001)

        # ── ST補正 ──
        st_rank = None
        cm_data = course_master.get(name, {}).get(course)
        if cm_data:
            st_rank = cm_data.get("st_rank")
        if st_rank is None:
            pi = player_index.get(name, {})
            st_rank = pi.get("st_rank", {}).get(course)
        st_corr = _st_rank_to_correction(st_rank)

        # ── フォーム補正 ──
        pi          = player_index.get(name)
        overall_win = pi.get("overall_win") if pi else None
        form_corr   = _form_correction(pi, overall_win)

        result[raw_name] = {
            "name":      name,
            "base":      base_rate,
            "st_corr":   st_corr,
            "form_corr": form_corr,
        }

    return result


def _normalize_with_clip(scores: dict[str, float], max_prob: float) -> dict[str, float]:
    total = sum(scores.values())
    if total <= 0:
        return {n: 1 / len(scores) for n in scores}
    clipped = {n: min(v / total, max_prob) for n, v in scores.items()}
    prob_sum = sum(clipped.values())
    if prob_sum <= 0:
        return {n: 1 / len(scores) for n in scores}
    return {n: round(v / prob_sum, 4) for n, v in clipped.items()}


def predict_base_only(race: dict, master: dict) -> dict[str, float]:
    """補正なし: base_rate のみで正規化"""
    rates = _get_base_rates(race, master)
    venue = race["venue"]
    arek_score = master.get("venue_stats", {}).get(venue, {}).get("arek_score", 50.0)
    max_prob   = _max_prob_by_arek(arek_score)
    scores = {n: d["base"] for n, d in rates.items()}
    return _normalize_with_clip(scores, max_prob)


def predict_with_corrections(race: dict, master: dict) -> dict[str, float]:
    """ST補正＋フォーム補正あり（現行モデル相当）"""
    rates = _get_base_rates(race, master)
    venue = race["venue"]
    arek_score = master.get("venue_stats", {}).get(venue, {}).get("arek_score", 50.0)
    max_prob   = _max_prob_by_arek(arek_score)
    scores = {n: d["base"] * d["st_corr"] * d["form_corr"] for n, d in rates.items()}
    return _normalize_with_clip(scores, max_prob)


# ──────────────────────────────────────────────────────────────────
# キャリブレーションバケツ
# ──────────────────────────────────────────────────────────────────

def _find_bucket(prob: float) -> tuple[float, float] | None:
    for lo, hi in CALIB_BUCKETS:
        if lo <= prob < hi:
            return (lo, hi)
    return None


def _empty_calib_buckets() -> dict:
    return {b: {"pred_sum": 0.0, "actual": 0, "count": 0} for b in CALIB_BUCKETS}


# ──────────────────────────────────────────────────────────────────
# 精度評価コア
# ──────────────────────────────────────────────────────────────────

def _evaluate_probs(races: list[dict], prob_fn) -> dict:
    """
    prob_fn(race, master) → {name: prob} の関数を受け取って全指標を計算する。
    """
    brier_total      = 0.0
    log_loss_total   = 0.0
    top1_correct     = 0
    baseline_correct = 0
    n_entrants       = 0
    n_races          = 0

    calib_buckets = _empty_calib_buckets()

    # 会場別集計
    venue_stats = defaultdict(lambda: {
        "brier": 0.0, "log_loss": 0.0, "top1": 0, "n": 0, "n_ent": 0,
        "c1_over_sum": 0.0, "c1_count": 0,
    })

    # コース別集計
    course_stats = defaultdict(lambda: {
        "top1": 0, "n": 0, "pred_sum": 0.0, "actual": 0,
    })

    # masterはクロージャ外から渡せないのでグローバル的に持つ
    # → evaluate()でラップして呼ぶ
    return {
        "_brier_total":      brier_total,
        "_log_loss_total":   log_loss_total,
        "_top1_correct":     top1_correct,
        "_baseline_correct": baseline_correct,
        "_n_entrants":       n_entrants,
        "_n_races":          n_races,
        "_calib_buckets":    calib_buckets,
        "_venue_stats":      venue_stats,
        "_course_stats":     course_stats,
    }


def evaluate_stage(races: list[dict], master: dict, prob_fn) -> dict:
    brier_total      = 0.0
    log_loss_total   = 0.0
    top1_correct     = 0
    baseline_correct = 0
    n_entrants       = 0
    n_races          = 0

    calib_buckets = _empty_calib_buckets()
    venue_stats   = defaultdict(lambda: {
        "brier": 0.0, "log_loss": 0.0, "top1": 0, "n": 0, "n_ent": 0,
        "c1_pred_sum": 0.0, "c1_actual_sum": 0.0, "c1_count": 0,
    })
    course_stats = defaultdict(lambda: {
        "top1": 0, "n_winner": 0, "pred_sum": 0.0, "actual": 0, "n_ent": 0,
    })

    for race in races:
        entrants = race["entrants"]
        if len(entrants) < 2:
            continue

        winners = [e for e in entrants if e["rank"] == 1]
        if not winners:
            continue

        winner_name   = winners[0]["name"]
        winner_course = winners[0]["course"]

        probs = prob_fn(race, master)
        if not probs:
            continue

        n_races += 1
        venue = race["venue"]
        vs    = venue_stats[venue]
        vs["n"] += 1

        for ent in entrants:
            name   = ent["name"]
            actual = 1.0 if name == winner_name else 0.0
            prob   = probs.get(name, 1e-6)
            course = ent["course"]

            brier_total      += (prob - actual) ** 2
            vs["brier"]      += (prob - actual) ** 2
            n_entrants       += 1
            vs["n_ent"]      += 1

            bucket = _find_bucket(prob)
            if bucket:
                calib_buckets[bucket]["pred_sum"] += prob
                calib_buckets[bucket]["actual"]   += int(actual)
                calib_buckets[bucket]["count"]    += 1

            # コース別集計
            cs = course_stats[course]
            cs["n_ent"]    += 1
            cs["pred_sum"] += prob
            cs["actual"]   += int(actual)
            if actual == 1.0:
                cs["n_winner"] += 1

            # 1枠の過大/過小評価
            if course == 1:
                vs["c1_pred_sum"]   += prob
                vs["c1_actual_sum"] += actual
                vs["c1_count"]      += 1

        winner_prob = max(probs.get(winner_name, 1e-6), 1e-7)
        ll = -math.log(winner_prob)
        log_loss_total += ll
        vs["log_loss"] += ll

        predicted_winner = max(probs, key=probs.get)
        if predicted_winner == winner_name:
            top1_correct += 1
            vs["top1"]   += 1

        # コース別: 1着コースの集計
        cs_w = course_stats[winner_course]
        cs_w["n_winner"] = cs_w.get("n_winner", 0)  # already counted above

        course1_players = [e for e in entrants if e["course"] == 1]
        if course1_players and course1_players[0]["rank"] == 1:
            baseline_correct += 1

    brier_score = brier_total / n_entrants if n_entrants > 0 else None
    log_loss    = log_loss_total / n_races  if n_races > 0    else None
    top1_acc    = top1_correct / n_races    if n_races > 0    else None
    baseline    = baseline_correct / n_races if n_races > 0   else None

    # キャリブレーション整形
    calibration = []
    for (lo, hi), b in sorted(calib_buckets.items()):
        if b["count"] == 0:
            continue
        pred_avg    = b["pred_sum"] / b["count"]
        actual_rate = b["actual"]  / b["count"]
        calibration.append({
            "pred_range":  f"{lo:.2f}〜{hi:.2f}",
            "pred_avg":    round(pred_avg, 4),
            "actual_rate": round(actual_rate, 4),
            "count":       b["count"],
            "gap":         round(pred_avg - actual_rate, 4),
        })

    # 会場別整形
    venue_breakdown = []
    for v, s in sorted(venue_stats.items()):
        if s["n"] == 0:
            continue
        c1_gap = None
        if s["c1_count"] > 0:
            c1_pred   = s["c1_pred_sum"] / s["c1_count"]
            c1_actual = s["c1_actual_sum"] / s["c1_count"]
            c1_gap    = round(c1_pred - c1_actual, 4)
        venue_breakdown.append({
            "venue":      v,
            "n_races":    s["n"],
            "brier":      round(s["brier"] / s["n_ent"], 4) if s["n_ent"] > 0 else None,
            "log_loss":   round(s["log_loss"] / s["n"], 4)  if s["n"] > 0    else None,
            "top1_acc":   round(s["top1"] / s["n"], 4)      if s["n"] > 0    else None,
            "c1_gap":     c1_gap,  # 正=1枠を過大評価、負=過小評価
        })

    # コース別整形
    course_breakdown = []
    for c in sorted(course_stats.keys()):
        s = course_stats[c]
        if s["n_ent"] == 0:
            continue
        course_breakdown.append({
            "course":     c,
            "n_entries":  s["n_ent"],
            "pred_avg":   round(s["pred_sum"] / s["n_ent"], 4),
            "actual_rate": round(s["actual"] / s["n_ent"], 4),
            "gap":        round(s["pred_sum"] / s["n_ent"] - s["actual"] / s["n_ent"], 4),
        })

    return {
        "n_races":          n_races,
        "n_entrants":       n_entrants,
        "brier_score":      round(brier_score, 4) if brier_score is not None else None,
        "log_loss":         round(log_loss, 4)    if log_loss    is not None else None,
        "top1_accuracy":    round(top1_acc, 4)    if top1_acc    is not None else None,
        "baseline_top1":    round(baseline, 4)    if baseline    is not None else None,
        "calibration":      calibration,
        "venue_breakdown":  venue_breakdown,
        "course_breakdown": course_breakdown,
    }


def evaluate(races: list[dict], master: dict) -> dict:
    """全段階を評価して比較結果を返す"""
    print("  [1/2] 補正なし（base_rate のみ）を評価中...")
    result_base = evaluate_stage(races, master, predict_base_only)

    print("  [2/2] ST補正＋フォーム補正ありを評価中...")
    result_full = evaluate_stage(races, master, predict_with_corrections)

    return {
        "base_only":    result_base,
        "with_corrections": result_full,
    }


# ──────────────────────────────────────────────────────────────────
# レポート生成
# ──────────────────────────────────────────────────────────────────

def _bs_judge(v):
    if v is None: return "測定不能"
    if v < 0.15:  return "◎ 実用レベル"
    if v < 0.20:  return "○ 有意な予測力あり"
    if v < 0.25:  return "△ コース1常時予想と同程度"
    return              "✕ ランダム以下"


def make_report(results: dict) -> str:
    rb = results["base_only"]
    rf = results["with_corrections"]

    def fmt(v, pct=False):
        if v is None: return "    N/A"
        return f"{v*100:6.2f}%" if pct else f"{v:.4f}"

    def diff(a, b, pct=False, invert=False):
        """b - a の差分（改善方向を+で表示）"""
        if a is None or b is None: return ""
        d = b - a
        if invert:
            d = -d
        sign = "+" if d >= 0 else ""
        if pct:
            return f"  ({sign}{d*100:.2f}pt)"
        return f"  ({sign}{d:.4f})"

    lines = [
        "=" * 60,
        "  1着率予測 精度評価レポート（改良版）",
        "  段階別比較 / 非均等キャリブレーション / 会場・コース内訳",
        "=" * 60,
        f"  評価レース数  : {rf['n_races']:,} レース",
        f"  評価エントリ数: {rf['n_entrants']:,} 件",
        "",
        "【主要指標の比較】",
        f"  {'指標':<20}  {'補正なし':>10}  {'ST+フォーム補正':>14}  差分",
        "  " + "-" * 56,
        f"  {'Brier Score':<20}  {fmt(rb['brier_score']):>10}  {fmt(rf['brier_score']):>14}"
        f"{diff(rb['brier_score'], rf['brier_score'], invert=True)}",
        f"  {'Log Loss':<20}  {fmt(rb['log_loss']):>10}  {fmt(rf['log_loss']):>14}"
        f"{diff(rb['log_loss'], rf['log_loss'], invert=True)}",
        f"  {'Top1 的中率':<20}  {fmt(rb['top1_accuracy'], pct=True):>10}  {fmt(rf['top1_accuracy'], pct=True):>14}"
        f"{diff(rb['top1_accuracy'], rf['top1_accuracy'], pct=True)}",
        f"  {'コース1常時予想':<20}  {fmt(rb['baseline_top1'], pct=True):>10}  {'':>14}",
        "",
        f"  Brier Score 判定: {_bs_judge(rf['brier_score'])}",
        f"  モデル上乗せ: {(rf['top1_accuracy'] or 0) - (rf['baseline_top1'] or 0):+.2%}",
        "",
        "【キャリブレーション（ST+フォーム補正版）】",
        "  ※ 高確率帯（0.40以上）を 0.05 刻みで細分化",
        f"  {'予測確率帯':^14}  {'予測平均':^10}  {'実際1着率':^10}  {'ズレ':^8}  {'件数':>6}",
        "  " + "-" * 54,
    ]

    for c in rf["calibration"]:
        gap_mark = "←過大" if c["gap"] > 0.03 else ("←過小" if c["gap"] < -0.03 else "  良好")
        lines.append(
            f"  {c['pred_range']:^14}  {c['pred_avg']:^10.4f}  {c['actual_rate']:^10.4f}"
            f"  {c['gap']:^+8.4f}  {c['count']:>6}  {gap_mark}"
        )

    lines += [
        "",
        "【会場別内訳（ST+フォーム補正版）】",
        "  ※ c1_gap: 1枠予測確率 − 1枠実際1着率（正=過大評価）",
        f"  {'会場':<8}  {'レース数':>8}  {'Brier':>8}  {'LogLoss':>8}  {'Top1%':>7}  {'1枠gap':>8}",
        "  " + "-" * 54,
    ]

    for v in rf["venue_breakdown"]:
        c1g = f"{v['c1_gap']:+.4f}" if v["c1_gap"] is not None else "    N/A"
        lines.append(
            f"  {v['venue']:<8}  {v['n_races']:>8}  {v['brier']:>8.4f}"
            f"  {v['log_loss']:>8.4f}  {(v['top1_acc'] or 0)*100:>6.1f}%  {c1g:>8}"
        )

    lines += [
        "",
        "【コース別内訳（ST+フォーム補正版）】",
        f"  {'コース':>6}  {'出走数':>8}  {'予測平均':>10}  {'実際1着率':>10}  {'ズレ':>8}",
        "  " + "-" * 48,
    ]

    for c in rf["course_breakdown"]:
        gap_mark = "←過大" if c["gap"] > 0.03 else ("←過小" if c["gap"] < -0.03 else "  良好")
        lines.append(
            f"  {c['course']:>6}枠  {c['n_entries']:>8}  {c['pred_avg']:>10.4f}"
            f"  {c['actual_rate']:>10.4f}  {c['gap']:>+8.4f}  {gap_mark}"
        )

    lines += [
        "",
        "【解説】",
        "  Brier Score が 0.25 を下回れば「ランダムよりマシ」です。",
        "  0.20 を下回ると「コース1常時予想」も上回り始めます。",
        "  キャリブレーションのズレが ±0.03 以内なら確率が正直です。",
        "  会場別 c1_gap がプラスに偏っている会場は 1枠を過大評価しています。",
        "  コース別 gap がプラスの枠は全体的に過大評価されています。",
        "  これらのズレが相対補正・展示補正の係数チューニングの根拠になります。",
        "=" * 60,
    ]

    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────
# ユーティリティ
# ──────────────────────────────────────────────────────────────────

def _safe_int(v, default=None):
    try:
        return int(str(v).strip())
    except (ValueError, TypeError):
        return default


def _safe_float(v, default=None):
    try:
        f = float(str(v).strip())
        return f if f == f else default
    except (ValueError, TypeError):
        return default


# ──────────────────────────────────────────────────────────────────
# メイン
# ──────────────────────────────────────────────────────────────────

def main():
    _here = Path(__file__).resolve().parent
    _root = _here.parent

    DEFAULT_CSV_DIR     = _root / "data_csv"
    DEFAULT_MASTER_PATH = _here / "master_data.json"
    DEFAULT_OUT_DIR     = _root / "accuracy_report"

    if len(sys.argv) == 1:
        csv_dir     = str(DEFAULT_CSV_DIR)
        master_path = str(DEFAULT_MASTER_PATH)
        out_dir     = DEFAULT_OUT_DIR
        print("[デフォルトパスで実行]")
        print(f"  CSV フォルダ  : {csv_dir}")
        print(f"  マスタ JSON   : {master_path}")
        print(f"  出力先        : {out_dir}")
        print()
    elif len(sys.argv) >= 3:
        csv_dir     = sys.argv[1]
        master_path = sys.argv[2]
        out_dir     = Path(sys.argv[3]) if len(sys.argv) >= 4 else DEFAULT_OUT_DIR
    else:
        print("使い方:")
        print("  引数なし  : python evaluate_model_unified.py")
        print("  パス指定  : python evaluate_model_unified.py <csv_dir> <master_json> [out_dir]")
        sys.exit(1)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not Path(master_path).exists():
        print(f"エラー: master_data.json が見つかりません → {master_path}")
        sys.exit(1)

    print("データ読み込み中...")
    races  = load_results(csv_dir)
    master = load_master(master_path)

    if not races:
        print("エラー: レースデータが読み込めませんでした")
        print("  ※ 列インデックスがCSVと合わない場合はスクリプト冒頭の COL_* を修正してください")
        sys.exit(1)

    print("評価中...")
    results = evaluate(races, master)

    report_txt = make_report(results)
    print("\n" + report_txt)

    # accuracy_report.txt
    txt_path = out_dir / "accuracy_report.txt"
    txt_path.write_text(report_txt, encoding="utf-8")

    # accuracy_report.json（全段階）
    json_path = out_dir / "accuracy_report.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # calibration.csv（ST+フォーム補正版）
    calib_path = out_dir / "calibration.csv"
    with open(calib_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["pred_range", "pred_avg", "actual_rate", "gap", "count"])
        writer.writeheader()
        writer.writerows(results["with_corrections"]["calibration"])

    # venue_breakdown.csv
    venue_path = out_dir / "venue_breakdown.csv"
    with open(venue_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["venue", "n_races", "brier", "log_loss", "top1_acc", "c1_gap"])
        writer.writeheader()
        writer.writerows(results["with_corrections"]["venue_breakdown"])

    # course_breakdown.csv
    course_path = out_dir / "course_breakdown.csv"
    with open(course_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["course", "n_entries", "pred_avg", "actual_rate", "gap"])
        writer.writeheader()
        writer.writerows(results["with_corrections"]["course_breakdown"])

    print(f"\n出力完了:")
    print(f"  {txt_path}")
    print(f"  {json_path}")
    print(f"  {calib_path}")
    print(f"  {venue_path}")
    print(f"  {course_path}")


if __name__ == "__main__":
    main()
