# -*- coding: utf-8 -*-
"""
apply_correction.py  ★v3修正版★
====================
【v3 修正内容】
  修正①: _find_band の戻り値型を統一（バグ修正）
          ・旧版では _find_band が2種類存在し、一方はfloat、他方は文字列キーを返していた。
          ・backtest_engine.py v4 の _find_band_weight / _find_band_key と同様に分離。
          ・apply_correction()  内では _find_band_weight（float戻り）を使用。
          ・calc_corrected_score() 内でも _find_band_weight に統一。

  修正②: 蓄積CSVへの上書きを「補助列（_補正スコア / _新見送り推奨）のみ」に限定
          ・旧版は「買い目」列を直接書き換えていた。
          ・これが backtest_engine.py のフィードバックループを汚染する根本原因。
          ・v3 では apply_correction.py は「買い目」列を一切書き換えない。
          ・代わりに「補正済み見送り推奨」列 (_corrected_skip) のみを更新する。
          ・点数削減の効果はリアルタイム予想（load_race.py 経由の apply_correction()）
            でのみ反映される。

  修正③: _calc_max_bets / _calc_max_bets_rt の重複を解消
          ・1つの _calc_max_bets に統一。

【既存機能】
  apply_correction()    ← load_race.py から呼ばれるリアルタイム補正（維持）
  process_venue_csv()   ← 蓄積CSV更新（買い目列の書き換えを廃止）
  trim_bets()           ← 内部ロジック（維持）
  main()                ← CLI（維持）
"""

import argparse
import glob
import json
import sys
import pathlib
from datetime import datetime
from pathlib import Path

import pandas as pd

try:
    _SCRIPTS_DIR = pathlib.Path(__file__).parent
    sys.path.insert(0, str(_SCRIPTS_DIR))
    from lr_config import CHIKUSEKI_DIR as _CHIKUSEKI_DIR_CFG
    from lr_config import CHIKUSEKI_DIR
except Exception:
    _CHIKUSEKI_DIR_CFG = None

BASE_DIR        = Path(r"C:\Users\user\Desktop\データ収集")
CHIKUSEKI_DIR   = _CHIKUSEKI_DIR_CFG if _CHIKUSEKI_DIR_CFG else BASE_DIR / "scripts" / "数値蓄積"
CORRECTION_JSON = BASE_DIR / "scripts" / "correction_table.json"
LOG_FILE        = BASE_DIR / "scripts" / "apply_correction_log.jsonl"

_CORR_CACHE: dict | None = None


def _load_corr_cached() -> dict:
    global _CORR_CACHE
    if _CORR_CACHE is not None:
        return _CORR_CACHE
    if CORRECTION_JSON.exists():
        try:
            with open(str(CORRECTION_JSON), encoding="utf-8") as f:
                _CORR_CACHE = json.load(f)
            return _CORR_CACHE
        except Exception:
            pass
    return {}


# ══════════════════════════════════════════════════════════
# ★修正①: _find_band をモジュールレベルで1種類に統一
#
# 旧版では apply_correction() 内と calc_corrected_score() 内に
# それぞれ異なる戻り値型（float / str）の同名インナー関数があり、
# backtest と load_race.py で異なる重み計算が実行されていた。
# ══════════════════════════════════════════════════════════

def _find_band_weight(value: float, band_dict: dict) -> float:
    """バンドに対応する重み（float）を返す。スコア計算用。"""
    for band_key, w in band_dict.items():
        try:
            lo_str, hi_str = band_key.split("〜")
            if float(lo_str) <= value < float(hi_str):
                return float(w)
        except Exception:
            continue
    return 1.0


def _find_band_key(value: float, band_dict: dict) -> str:
    """バンドキー（文字列）を返す。必要に応じて参照用に使用。"""
    for band_key in band_dict:
        try:
            lo_str, hi_str = band_key.split("〜")
            if float(lo_str) <= value < float(hi_str):
                return band_key
        except Exception:
            continue
    return ""


# ══════════════════════════════════════════════════════════
# apply_correction() ― load_race.py が import して呼ぶ関数
# ★修正①: インナー _find_band を廃止し _find_band_weight に統一
# ══════════════════════════════════════════════════════════

def apply_correction(
    bet_suggestions: dict,
    race_judgment:   dict,
    row_data:        dict,
    corr:            dict | None = None,
) -> dict:
    """
    load_race.py から呼ばれるリアルタイム補正。

    Parameters
    ----------
    bet_suggestions : scenario_engine が生成した買い目辞書
    race_judgment   : レース判定辞書（レースランク・脅威合計等を含む）
    row_data        : 蓄積CSVの先頭行（会場・グレード等を含む）
    corr            : correction_table.json の内容（省略時は自動読込）

    Returns
    -------
    bet_suggestions に以下のキーを追加して返す:
      buy_level       : "STRONG_BUY" / "BUY" / "WEAK_BUY" / "SKIP"
      composite_score : float  補正後スコア
    """
    if corr is None:
        corr = _load_corr_cached()
    if not corr:
        return bet_suggestions

    venue    = str(row_data.get("会場",  bet_suggestions.get("venue", "")))
    grade    = str(row_data.get("グレード", "一般"))
    rank     = str(race_judgment.get("race_rank",  bet_suggestions.get("race_rank", "B")))
    strategy = str(race_judgment.get("strategy",   bet_suggestions.get("strategy", "")))
    threat   = float(race_judgment.get("threat_total", 0) or
                     bet_suggestions.get("threat_total", 0) or 0)
    vuln     = float(race_judgment.get("s1_vuln",  0) or
                     bet_suggestions.get("s1_vuln", 0) or 0)
    score    = float(race_judgment.get("race_score", 0) or
                     bet_suggestions.get("race_score", 0) or 0)

    venue_key     = f"{venue}_{grade}"
    venue_weights = corr.get("venue_weight", {})
    venue_stats   = corr.get("venue_stats", {})
    _vs           = venue_stats.get(venue, {})

    if _vs.get("insufficient_data", False):
        venue_weight = 1.0
    else:
        venue_weight = venue_weights.get(venue_key) or venue_weights.get(venue, 1.0)

    w_rank     = corr.get("rank_weight",     {}).get(rank,     1.0)
    w_strategy = corr.get("strategy_weight", {}).get(strategy, 1.0)
    # ★修正①: _find_band_weight に統一（float を直接返す）
    w_threat   = _find_band_weight(threat, corr.get("threat_penalty", {}))
    w_vuln     = _find_band_weight(vuln,   corr.get("vuln_penalty",   {}))

    composite = round(score * w_rank * venue_weight * w_strategy * w_threat * w_vuln, 3)

    threshold = float(corr.get("score_threshold", 0))
    base_hit  = float(corr.get("base_hit_rate",   0))

    if composite <= 0 or (threshold > 0 and composite < threshold * 0.7):
        buy_level = "SKIP"
    elif composite < threshold * 0.9:
        buy_level = "WEAK_BUY"
    elif composite >= threshold * 1.2 and base_hit >= 10:
        buy_level = "STRONG_BUY"
    else:
        buy_level = "BUY"

    buy_list   = list(bet_suggestions.get("buy_list", []))
    candidates = list(bet_suggestions.get("candidates", []))

    if buy_level == "SKIP":
        buy_list   = []
        candidates = []
    else:
        max_bets = _calc_max_bets(venue_weight, rank, None)

        if candidates and len(candidates) > max_bets:
            try:
                sorted_cands = sorted(
                    candidates,
                    key=lambda c: float(c.get("prob", 0)),
                    reverse=True,
                )
                candidates = sorted_cands[:max_bets]
                kept_combos = {c.get("combo", "") for c in candidates}
                buy_list = [b for b in buy_list if b in kept_combos]
            except Exception:
                buy_list   = buy_list[:max_bets]
                candidates = candidates[:max_bets]
        elif len(buy_list) > max_bets:
            buy_list   = buy_list[:max_bets]
            candidates = candidates[:max_bets]

    out = dict(bet_suggestions)
    out["buy_list"]        = buy_list
    out["candidates"]      = candidates
    out["buy_level"]       = buy_level
    out["composite_score"] = composite
    out["point_count"]     = len(buy_list)
    return out


# ★修正③: _calc_max_bets / _calc_max_bets_rt を1つに統一
def _calc_max_bets(venue_weight: float, rank: str, manual_max: int | None) -> int:
    """点数上限計算（リアルタイム・バッチ共通）"""
    if manual_max is not None:
        return manual_max
    rank_base = {"S": 12, "A": 9, "B": 6, "C": 5, "D": 4}
    base = rank_base.get(rank, 8)
    if venue_weight >= 1.15:
        adj = +2
    elif venue_weight >= 1.00:
        adj = 0
    elif venue_weight >= 0.85:
        adj = -2
    else:
        adj = -3
    return max(3, base + adj)


# 後方互換エイリアス（load_race.py が _calc_max_bets_rt を import している場合の対策）
_calc_max_bets_rt = _calc_max_bets


def sep(c="=", w=55):
    print(c * w)


def _load_correction(path) -> dict:
    if not Path(path).exists():
        raise FileNotFoundError(
            f"correction_table.json が見つかりません: {path}\n"
            "先に python backtest_engine.py を実行してください。"
        )
    with open(str(path), encoding="utf-8") as f:
        return json.load(f)


def _parse_bets(bets_str: str) -> list[str]:
    if not bets_str or str(bets_str) in ("nan", "None", ""):
        return []
    return [b for b in str(bets_str).split("|") if b.strip()]


def _bets_to_str(bets: list[str]) -> str:
    return "|".join(bets)


def _trim_bets_by_threat(bets: list[str], threat_score: float) -> list[str]:
    if threat_score < 12:
        return bets
    cut_firsts: set[str] = set()
    if threat_score >= 20:
        cut_firsts = {"3", "4", "5", "6"}
    elif threat_score >= 16:
        cut_firsts = {"4", "5", "6"}
    elif threat_score >= 12:
        cut_firsts = {"5", "6"}
    return [b for b in bets if not (len(b.split("-")) >= 1 and b.split("-")[0] in cut_firsts)]


def _trim_bets_by_vuln(bets: list[str], vuln_score: float) -> list[str]:
    if vuln_score < 25:
        return bets
    w1_bets = [b for b in bets if b.startswith("1-")]
    non_w1  = [b for b in bets if not b.startswith("1-")]
    if vuln_score >= 35:
        return non_w1
    elif vuln_score >= 30:
        return non_w1 if non_w1 else bets[:3]
    else:
        keep_w1 = w1_bets[:max(1, len(w1_bets) // 2)]
        return keep_w1 + non_w1


def _trim_to_max(bets: list[str], max_bets: int) -> list[str]:
    return bets[:max_bets]


def trim_bets(
    bets_str: str,
    venue_weight: float,
    rank: str,
    threat_score: float,
    vuln_score: float,
    manual_max: int | None,
) -> tuple[list[str], list[str], dict]:
    original = _parse_bets(bets_str)
    log = {"original": len(original)}
    if not original:
        return original, original, log
    bets = original.copy()
    bets = _trim_bets_by_threat(bets, threat_score)
    log["after_threat_trim"] = len(bets)
    bets = _trim_bets_by_vuln(bets, vuln_score)
    log["after_vuln_trim"] = len(bets)
    max_bets = _calc_max_bets(venue_weight, rank, manual_max)
    bets = _trim_to_max(bets, max_bets)
    log["after_max_trim"] = len(bets)
    log["max_bets_applied"] = max_bets
    return original, bets, log


def calc_corrected_score(row: pd.Series, corr: dict) -> float:
    """補正後スコアを計算する（蓄積CSV 行ごとに呼ばれる）"""
    base_score = float(row.get("レーススコア", 0) or 0)
    rank       = str(row.get("レースランク", ""))
    venue      = str(row.get("会場", row.get("_venue_file", "")))
    grade      = str(row.get("グレード", "一般"))
    strategy   = str(row.get("戦略", ""))
    threat     = float(row.get("脅威合計", 0) or 0)
    vuln       = float(row.get("1号艇脆弱性", 0) or 0)

    w_rank     = corr.get("rank_weight", {}).get(rank, 1.0)
    venue_weights = corr.get("venue_weight", {})
    venue_key  = f"{venue}_{grade}"
    w_venue    = venue_weights.get(venue_key) or venue_weights.get(venue, 1.0)
    w_strategy = corr.get("strategy_weight", {}).get(strategy, 1.0)
    # ★修正①: _find_band_weight に統一
    w_threat   = _find_band_weight(threat, corr.get("threat_penalty", {}))
    w_vuln     = _find_band_weight(vuln,   corr.get("vuln_penalty",   {}))
    return round(base_score * w_rank * w_venue * w_strategy * w_threat * w_vuln, 3)


def process_venue_csv(
    csv_path: Path,
    corr: dict,
    dry_run: bool,
    manual_max: int | None,
) -> dict:
    """
    蓄積CSV に補正スコアと補正済み見送り推奨を反映する。

    ★修正②: 「買い目」列は一切書き換えない。
    ・旧版は buy_list をトリミングして「買い目」列を上書きしていた。
    ・これが backtest_engine の自己参照ループ汚染の根本原因だった。
    ・v3 では補正済み見送り推奨（_corrected_skip）列の追加のみを行う。
    ・点数削減はリアルタイム予想（apply_correction() 経由）でのみ機能する。
    """
    venue_name = csv_path.stem
    df = pd.read_csv(str(csv_path), encoding="utf-8")
    required = ["レーススコア"]
    missing  = [c for c in required if c not in df.columns]
    if missing:
        return {"venue": venue_name, "status": "スキップ", "reason": f"必須列なし: {missing}"}
    if "会場" not in df.columns:
        df["会場"] = venue_name
    if "グレード" not in df.columns:
        df["グレード"] = "一般"

    venue_stats  = corr.get("venue_stats", {})
    _vs          = venue_stats.get(venue_name, {})

    if _vs.get("insufficient_data", False):
        venue_weight = 1.0
        print(f"    [{venue_name}] データ不足（n<30）→ venue_weight=1.0 で補正スキップ")
    else:
        venue_key    = f"{venue_name}_{df['グレード'].iloc[0]}"
        venue_weights = corr.get("venue_weight", {})
        venue_weight = venue_weights.get(venue_key) or venue_weights.get(venue_name, 1.0)

    race_keys = ["日付", "レース番号"]
    if not all(c in df.columns for c in race_keys):
        return {"venue": venue_name, "status": "スキップ", "reason": "日付/レース番号列なし"}

    threshold = corr.get("score_threshold", 0)
    if "枠番" in df.columns:
        rep_df = (
            df.sort_values("枠番")
            .groupby(race_keys, sort=False)
            .first()
            .reset_index()
        )
    else:
        rep_df = df.drop_duplicates(subset=race_keys).copy()

    rep_df["_補正スコア"] = rep_df.apply(
        lambda row: calc_corrected_score(row, corr), axis=1
    )
    rep_df["_新見送り推奨"] = (rep_df["_補正スコア"] < threshold).astype(int)

    skip_map = dict(
        zip(
            zip(rep_df["日付"].astype(str), rep_df["レース番号"].astype(int)),
            rep_df["_新見送り推奨"],
        )
    )

    before_skip = int(df["見送り推奨"].fillna(0).astype(int).sum()) if "見送り推奨" in df.columns else 0
    # ★修正②: 「見送り推奨」列は上書きせず、「_補正済み見送り推奨」として別列で保持
    df["_補正済み見送り推奨"] = df.apply(
        lambda r: skip_map.get((str(r["日付"]), int(r["レース番号"])), 0), axis=1
    ).astype(int)
    # 「_補正スコア」も参照用に追加（任意）
    score_map = dict(
        zip(
            zip(rep_df["日付"].astype(str), rep_df["レース番号"].astype(int)),
            rep_df["_補正スコア"],
        )
    )
    df["_補正スコア"] = df.apply(
        lambda r: score_map.get((str(r["日付"]), int(r["レース番号"])), 0.0), axis=1
    )

    after_skip = int(df["_補正済み見送り推奨"].sum())
    skip_delta = after_skip - before_skip

    # ★修正②: 買い目列の変更は一切行わない
    status = "更新"
    changed_flag = skip_delta != 0

    summary = {
        "venue":              venue_name,
        "status":             status if changed_flag else "変更なし",
        "total_races":        len(rep_df),
        "before_skip":        before_skip,
        "after_corrected_skip": after_skip,
        "skip_delta":         skip_delta,
        "venue_weight":       venue_weight,
        "dry_run":            dry_run,
        "note":               "買い目列は変更しない（v3修正②）",
    }
    if not dry_run and changed_flag:
        df.to_csv(str(csv_path), index=False, encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser(description="補正係数を蓄積CSVに反映（v3修正版）")
    parser.add_argument("--venue",      type=str,  default=None)
    parser.add_argument("--dry-run",    action="store_true")
    parser.add_argument("--max-bets",   type=int,  default=None,
                        help="リアルタイム補正の点数上限（蓄積CSV書き換えには不使用）")
    parser.add_argument("--chikuseki",  type=str,  default=None)
    parser.add_argument("--correction", type=str,  default=None)
    args = parser.parse_args()

    chikuseki_dir   = Path(args.chikuseki)  if args.chikuseki  else CHIKUSEKI_DIR
    correction_path = Path(args.correction) if args.correction else CORRECTION_JSON

    print(); sep()
    print("  補正係数反映スクリプト (apply_correction.py) v3修正版")
    print("  ※ 買い目列は書き換えません。補正スコア列のみ更新します。")
    if args.dry_run:
        print("  ※ DRY-RUN モード（蓄積CSVは変更されません）")
    sep()

    print("\n[Step 1]  correction_table.json 読み込み中...")
    try:
        corr = _load_correction(correction_path)
    except FileNotFoundError as e:
        print(f"  [NG] {e}"); return

    print(f"  生成日時   : {corr.get('generated_at', '不明')}")
    print(f"  基準的中率 : {corr.get('base_hit_rate', 0)}%  ← 補正前の素の値")
    print(f"  スコア閾値 : {corr.get('score_threshold', 0)}")
    if corr.get("corrected_hit_rate") is not None:
        print(f"  補正後的中率: {corr.get('corrected_hit_rate')}%（参考値）")

    print("\n[Step 2]  蓄積CSV 処理中...")
    pattern   = f"{args.venue}.csv" if args.venue else "*.csv"
    csv_files = sorted(glob.glob(str(chikuseki_dir / pattern)))
    if not csv_files:
        print(f"  [NG] 蓄積CSVが見つかりません: {chikuseki_dir / pattern}"); return

    results = []
    for csv_path in csv_files:
        result = process_venue_csv(Path(csv_path), corr, args.dry_run, args.max_bets)
        results.append(result)
        venue  = result["venue"]
        status = result["status"]
        if result.get("reason"):
            print(f"  [{venue}]  {status} ← {result['reason']}")
        else:
            vw = result.get("venue_weight", 1.0)
            sd = result.get("skip_delta", 0)
            print(f"  [{venue}]  {status}  見送り変化:{sd:+d}  venue_w={vw:.3f}"
                  f"  / {result.get('total_races',0)}R")

    sep()
    updated = sum(1 for r in results if r["status"] == "更新")
    print(f"  更新: {updated} / {len(results)} 会場")
    if args.dry_run:
        print("  ※ DRY-RUN のため変更なし。--dry-run を外して再実行してください。")
    print()
    print("  【補足】買い目列は書き換えていません。")
    print("  　補正の効果はリアルタイム予想（load_race.py → apply_correction()）で発揮されます。")

    log_entry = {
        "executed_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "dry_run": args.dry_run,
        "results": results,
    }
    try:
        with open(str(LOG_FILE), "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    except Exception:
        pass
    sep(); print()


if __name__ == "__main__":
    main()
