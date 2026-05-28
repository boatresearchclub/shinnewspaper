# -*- coding: utf-8 -*-
"""
optimize_grade_factor.py
========================
グレード補正係数（grade_factor.csv）をバックテストデータから自動最適化するスクリプト。

【目的】
  グレード常連選手（G1/SG多出走）が一般戦に出たときの
  「実際の一般戦1着率 ÷ G1/SG1着率」をコース別に集計し、
  lr_calc.py が使うグレード補正係数を実データから更新する。

【設計原則】
  ・級別（A1/B2等）で選手能力を評価しない。
    理由①: A1でもグレード戦非常連の選手は一般戦データが豊富
    理由②: B2でもFLY等ペナルティで一時降格した実力者が存在する
    理由③: 同じA1でも実力差は大きく、級別は能力の絶対値を示さない
    → 「実際の出走実績の質と量」でのみ評価する。
  ・係数はコース別中央値を採用（外れ値の影響を排除）。
  ・サンプルが少ないコースはデフォルト値を保持（過学習防止）。

【使い方】
    python scripts/optimize_grade_factor.py            # 確認してから更新
    python scripts/optimize_grade_factor.py --yes      # 確認なしで即更新
    python scripts/optimize_grade_factor.py --dry-run  # 表示のみ（更新なし）

【run_loop_learning.py からの呼び出し例】
    import subprocess
    subprocess.run(["python", "scripts/optimize_grade_factor.py", "--yes"])

【出力】
    data/grade_factor.csv        ← lr_calc.py が起動時に読み込む係数ファイル
    data/grade_factor_log.csv    ← 更新履歴（日付・係数・サンプル数）
"""

import os
import sys
import glob
import argparse
from datetime import datetime

import numpy as np
import pandas as pd

# ── パス設定 ─────────────────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR    = os.path.join(BASE_DIR, "data_csv")
GRADE_CSV  = os.path.join(BASE_DIR, "data_csv", "grade_master.csv")
OUTPUT_CSV = os.path.join(BASE_DIR, "data", "grade_factor.csv")
LOG_CSV    = os.path.join(BASE_DIR, "data", "grade_factor_log.csv")

# ── デフォルト係数（実測データ不足時のフォールバック）────────────────────────
# 意味: G1/SGの1着率 × この係数 ≒ 一般戦での推定1着率
# 根拠: インコース（1C）は相手強度の影響が小さく係数小。
#       アウトコース（4〜6C）ほど相手弱化の恩恵が大きく係数大。
# ※ update_master.py / lr_calc.py と同じ値で3ファイル統一
GRADE_FACTOR_DEFAULT = {
    "1": 1.15, "2": 1.25, "3": 1.30,
    "4": 1.35, "5": 1.40, "6": 1.45,
}

# ── 集計条件 ─────────────────────────────────────────────────────────────────
MIN_IPPAN_RUNS = 15   # 一般戦の最低出走数（lr_calc.py / update_master.py と統一）
MIN_GRADE_RUNS = 10   # G1/SGの最低出走数（グレード常連とみなす条件）
MIN_SAMPLE_N   = 5    # コース別係数採用の最低選手数（未満はデフォルト値を使用）
FACTOR_MIN     = 0.5  # 係数の下限（外れ値除去）
FACTOR_MAX     = 3.0  # 係数の上限（外れ値除去）

# ── グレード区分 ─────────────────────────────────────────────────────────────
GRADE_G1SG = {"G1", "SG"}
GRADE_EXCL = {"G1", "SG", "G2", "G3", "女子戦", "ルーキーS", "マスターズL"}
EXCL_RACES = {"準優勝戦", "優勝戦", "順位決定戦", "Ｓ戦優勝戦", "賞金女王決定"}


# =============================================================================
# データ読み込み
# =============================================================================
def load_raw(raw_dir: str, grade_csv: str) -> pd.DataFrame:
    """data_csv/ の全 *_results.csv を読み込み、グレード列を付与して返す。"""
    csv_files = sorted(glob.glob(os.path.join(raw_dir, "*_results.csv")))
    if not csv_files:
        csv_files = sorted(glob.glob(os.path.join(raw_dir, "2*.csv")))
        csv_files = [f for f in csv_files
                     if "_payouts" not in f and "grade_master" not in f]
    if not csv_files:
        raise FileNotFoundError(f"CSVが見つかりません: {raw_dir}")

    dfs = []
    for f in csv_files:
        try:
            dfs.append(pd.read_csv(f, dtype=str))
            print(f"  読込: {os.path.basename(f)}")
        except Exception as e:
            print(f"  スキップ: {os.path.basename(f)} ({e})")
    raw = pd.concat(dfs, ignore_index=True).drop_duplicates()

    # 型変換
    raw["日付"]       = pd.to_datetime(raw["日付"], errors="coerce")
    raw["着順"]       = pd.to_numeric(raw["着順"],       errors="coerce")
    raw["進入コース"] = pd.to_numeric(raw["進入コース"], errors="coerce")
    raw["選手名"]     = raw["選手名"].str.replace(r"\s+", "", regex=True)

    # グレード付与
    if os.path.exists(grade_csv):
        gdf = pd.read_csv(grade_csv, dtype=str)
        gdf["開始日"] = pd.to_datetime(gdf["開始日"], errors="coerce")
        gdf["終了日"] = pd.to_datetime(gdf["終了日"], errors="coerce")
        raw["_idx"] = range(len(raw))
        merged_g = raw[["_idx", "日付", "会場名"]].merge(gdf, on="会場名", how="left")
        merged_g = merged_g[
            (merged_g["開始日"].isna() | (merged_g["開始日"] <= merged_g["日付"])) &
            (merged_g["終了日"].isna() | (merged_g["日付"] <= merged_g["終了日"]))
        ].drop_duplicates(subset=["_idx"], keep="first")[["_idx", "グレード"]]
        raw = raw.merge(merged_g, on="_idx", how="left")
        raw["グレード"] = raw["グレード"].fillna("一般")
        raw.drop(columns=["_idx"], inplace=True)
        print(f"  グレード分布: {dict(raw['グレード'].value_counts())}")
    else:
        print("  [WARN] grade_master.csv なし → 全レースを一般戦扱い（係数が不正確になります）")
        raw["グレード"] = "一般"

    # 進入変更レース除外
    _waku_col = "艇番" if "艇番" in raw.columns else "枠"
    if "進入コース" in raw.columns and _waku_col in raw.columns:
        _nyujo = pd.to_numeric(raw["進入コース"], errors="coerce")
        _waku  = pd.to_numeric(raw[_waku_col],   errors="coerce")
        _keys  = (raw["日付"].astype(str) + "_" +
                  raw["会場名"].astype(str) + "_" +
                  raw["レース番号"].astype(str))
        _changed = _keys[_nyujo != _waku].unique()
        before = len(raw)
        raw = raw[~_keys.isin(_changed)].copy()
        print(f"  進入変更除外: {before - len(raw):,}行削除")

    # 準優勝戦等を除外
    if "レース種別" in raw.columns:
        raw = raw[~raw["レース種別"].isin(EXCL_RACES)].copy()

    print(f"  最終: {len(raw):,}行")
    return raw


# =============================================================================
# グレード補正係数の算出
# =============================================================================
def calc_grade_factor(raw: pd.DataFrame) -> pd.DataFrame:
    """
    コース別グレード補正係数を算出して返す。

    Returns
    -------
    DataFrame: コース / 補正係数 / サンプル数 / 一般戦1着率中央値 / G1SG1着率中央値 / 採用区分
    """
    ippan = raw[~raw["グレード"].isin(GRADE_EXCL)].copy()
    g1sg  = raw[raw["グレード"].isin(GRADE_G1SG)].copy()

    if len(g1sg) == 0:
        print("\n  [WARN] G1/SGデータが0件です。grade_master.csv が正しく適用されているか確認してください。")
        return pd.DataFrame()

    # ── 選手×コース別1着率を集計 ──────────────────────────────────────────────
    def _agg(df: pd.DataFrame, label: str) -> pd.DataFrame:
        g = df.groupby(["選手名", "進入コース"])
        r = g.agg(
            出走数=("着順", "count"),
            一着数=("着順", lambda x: (x == 1).sum()),
        ).reset_index()
        r[f"{label}_出走数"] = r["出走数"]
        r[f"{label}_1着率"] = r["一着数"] / r["出走数"].replace(0, np.nan)
        return r[["選手名", "進入コース", f"{label}_出走数", f"{label}_1着率"]]

    ippan_s = _agg(ippan, "ippan")
    g1sg_s  = _agg(g1sg,  "g1sg")

    # ── 両条件を満たす選手のみ ────────────────────────────────────────────────
    merged = ippan_s.merge(g1sg_s, on=["選手名", "進入コース"], how="inner")
    merged = merged[
        (merged["ippan_出走数"] >= MIN_IPPAN_RUNS) &
        (merged["g1sg_出走数"]  >= MIN_GRADE_RUNS) &
        merged["ippan_1着率"].notna() &
        merged["g1sg_1着率"].notna() &
        (merged["g1sg_1着率"] > 0)
    ].copy()
    merged["補正係数"] = merged["ippan_1着率"] / merged["g1sg_1着率"]

    print(f"\n  対象選手×コース: {len(merged)}件")
    print(f"  （一般戦{MIN_IPPAN_RUNS}走以上 & G1/SG{MIN_GRADE_RUNS}走以上）")

    # ── コース別に中央値を算出 ────────────────────────────────────────────────
    rows = []
    for c in range(1, 7):
        c_data = merged[merged["進入コース"] == c]
        vals   = c_data["補正係数"].dropna()
        vals   = vals[(vals >= FACTOR_MIN) & (vals <= FACTOR_MAX)]  # 外れ値除去
        n      = len(vals)

        if n >= MIN_SAMPLE_N:
            factor    = round(float(vals.median()), 3)
            source    = "実測"
            ippan_med = round(float(c_data["ippan_1着率"].median()), 4)
            g1sg_med  = round(float(c_data["g1sg_1着率"].median()),  4)
        else:
            factor    = GRADE_FACTOR_DEFAULT[str(c)]
            source    = f"デフォルト(n={n})"
            ippan_med = None
            g1sg_med  = None

        rows.append({
            "コース":            str(c),
            "補正係数":          factor,
            "サンプル数":        n,
            "一般戦1着率中央値": ippan_med,
            "G1SG1着率中央値":   g1sg_med,
            "採用区分":          source,
        })

    return pd.DataFrame(rows)


# =============================================================================
# 既存CSVの読み込み
# =============================================================================
def load_current(output_csv: str) -> dict:
    """現在の grade_factor.csv を {コース: 係数} として返す。"""
    if not os.path.exists(output_csv):
        return {}
    try:
        df = pd.read_csv(output_csv, dtype=str)
        return {str(r["コース"]): float(r["補正係数"]) for _, r in df.iterrows()}
    except Exception:
        return {}


# =============================================================================
# 差分表示
# =============================================================================
def print_diff(current: dict, new_df: pd.DataFrame):
    """現在の係数と新しい係数の差分を表示する。"""
    print("\n" + "=" * 60)
    print("  コース別グレード補正係数  （現在値 → 新規値）")
    print("=" * 60)
    print(f"  {'C':>3}  {'現在':>7}  {'新規':>7}  {'変化':>7}  {'n':>4}  採用区分")
    print("-" * 60)
    any_change = False
    for _, row in new_df.iterrows():
        c      = str(row["コース"])
        new_v  = float(row["補正係数"])
        cur_v  = current.get(c)
        n      = int(row["サンプル数"])
        source = row["採用区分"]
        if cur_v is not None:
            diff = new_v - cur_v
            diff_s = f"{diff:+.3f}" if abs(diff) >= 0.001 else "  ±0  "
            cur_s  = f"{cur_v:.3f}"
            changed = abs(diff) >= 0.005
        else:
            diff_s = " (新規)"
            cur_s  = "  ---  "
            changed = True
        if changed:
            any_change = True
        mark = "🔄" if changed else "  "
        print(f"  {mark}{c}C  {cur_s:>7}  {new_v:>7.3f}  {diff_s:>7}  {n:>4}  {source}")
    print("=" * 60)
    if not any_change:
        print("  変化なし（現在の係数と同一）")


# =============================================================================
# CSV保存
# =============================================================================
def save_csv(new_df: pd.DataFrame, output_csv: str, log_csv: str):
    """grade_factor.csv と更新ログを保存する。"""
    os.makedirs(os.path.dirname(output_csv), exist_ok=True)

    # grade_factor.csv（lr_calc.py が読み込む本体）
    out = new_df[["コース", "補正係数"]].copy()
    out.to_csv(output_csv, index=False, encoding="utf-8-sig")
    print(f"\n  保存: {output_csv}")

    # grade_factor_log.csv（更新履歴）
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_rows = []
    for _, row in new_df.iterrows():
        log_rows.append({
            "更新日時":      now_str,
            "コース":        row["コース"],
            "補正係数":      row["補正係数"],
            "サンプル数":    row["サンプル数"],
            "採用区分":      row["採用区分"],
        })
    log_df = pd.DataFrame(log_rows)
    if os.path.exists(log_csv):
        existing = pd.read_csv(log_csv, dtype=str)
        log_df = pd.concat([existing, log_df], ignore_index=True)
    log_df.to_csv(log_csv, index=False, encoding="utf-8-sig")
    print(f"  ログ: {log_csv}")


# =============================================================================
# メイン
# =============================================================================
def main():
    parser = argparse.ArgumentParser(description="グレード補正係数の自動最適化")
    parser.add_argument("--yes",     action="store_true", help="確認なしで即更新")
    parser.add_argument("--dry-run", action="store_true", help="表示のみ（ファイル更新なし）")
    args = parser.parse_args()

    print("=" * 60)
    print("  optimize_grade_factor.py  グレード補正係数最適化")
    print("=" * 60)
    print(f"\n[1] データ読み込み中... ({RAW_DIR})")

    try:
        raw = load_raw(RAW_DIR, GRADE_CSV)
    except FileNotFoundError as e:
        print(f"\n  [ERROR] {e}")
        sys.exit(1)

    print(f"\n[2] グレード補正係数を算出中...")
    new_df = calc_grade_factor(raw)

    if new_df.empty:
        print("\n  [ERROR] 係数を算出できませんでした。処理を中断します。")
        sys.exit(1)

    # 差分表示
    current = load_current(OUTPUT_CSV)
    print_diff(current, new_df)

    if args.dry_run:
        print("\n  [DRY-RUN] ファイルは更新しませんでした。")
        return

    # 確認プロンプト
    if not args.yes:
        ans = input("\n  上記の係数で grade_factor.csv を更新しますか？ [y/N]: ").strip().lower()
        if ans != "y":
            print("  キャンセルしました。")
            return

    save_csv(new_df, OUTPUT_CSV, LOG_CSV)
    print("\n  完了！次回の load_race.py 実行から新しい係数が反映されます。")
    print("=" * 60)


if __name__ == "__main__":
    main()
