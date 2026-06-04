"""
check_wins.py
=============
特定選手の「コース別1着数」を除外条件ごとに段階的に集計し、
公式サイトの数値との乖離がどの条件で発生しているかを特定する。

【使い方】
    python check_wins.py
    → 対話形式で選手名を入力

    python check_wins.py 上原崚
    → コマンドライン引数で選手名を指定

【前提】
    update_master.py と同じフォルダ構成を想定。
    data_csv/ フォルダに *_results.csv / *_results.parquet があること。
"""

import sys
import os
import glob
import re
import pandas as pd

# ── パス設定 ─────────────────────────────────────────────────────────────────
# data_csvの場所を直接指定（スクリプトの置き場所に関係なく動く）
RAW_DIR  = r"C:\Users\user\Desktop\データ収集\data_csv"
BASE_DIR = os.path.dirname(RAW_DIR)  # = C:\Users\user\Desktop\データ収集

# ── 除外設定（update_master.py と完全に合わせる）────────────────────────────
EXCLUDE_GRADES_IPPAN   = {"SG", "G1", "G2", "G3"}
ALWAYS_EXCLUDE         = {"女子戦", "ルーキーS", "マスターズL"}
EXCLUDE_RACE_TYPES_FINAL = {"準優勝戦", "優勝戦", "順位決定戦", "Ｓ戦優勝戦", "賞金女王決定"}

SEP = "=" * 62


def load_raw(player_name: str) -> pd.DataFrame:
    """CSVまたはParquetから指定選手のデータを読み込む。"""

    csv_files     = sorted(glob.glob(os.path.join(RAW_DIR, "*_results.csv")))
    parquet_files = sorted(glob.glob(os.path.join(RAW_DIR, "*_results.parquet")))

    # フォールバック: 旧形式
    if not csv_files and not parquet_files:
        csv_files     = [f for f in sorted(glob.glob(os.path.join(RAW_DIR, "2*.csv")))
                         if "_payouts" not in f and "grade_master" not in f]
        parquet_files = [f for f in sorted(glob.glob(os.path.join(RAW_DIR, "2*.parquet")))
                         if "_payouts" not in f and "grade_master" not in f]

    if not csv_files and not parquet_files:
        print(f"[ERROR] CSV/Parquetが見つかりません: {RAW_DIR}")
        sys.exit(1)

    # parquet優先
    parquet_stems = {os.path.splitext(os.path.basename(f))[0] for f in parquet_files}
    csv_files = [f for f in csv_files
                 if os.path.splitext(os.path.basename(f))[0] not in parquet_stems]

    dfs = []
    for f in csv_files:
        try:
            df = pd.read_csv(f, dtype=str)
            dfs.append(df)
        except Exception as e:
            print(f"  ⚠ スキップ(CSV): {os.path.basename(f)} ({e})")

    for f in parquet_files:
        try:
            df = pd.read_parquet(f).astype(str).replace("nan", pd.NA)
            dfs.append(df)
        except Exception as e:
            print(f"  ⚠ スキップ(Parquet): {os.path.basename(f)} ({e})")

    if not dfs:
        print("[ERROR] 読み込めるファイルがありませんでした。")
        sys.exit(1)

    raw = pd.concat(dfs, ignore_index=True).drop_duplicates()

    # 型変換
    raw["日付"]       = pd.to_datetime(raw["日付"], errors="coerce")
    raw["着順"]       = pd.to_numeric(raw["着順"], errors="coerce")
    raw["進入コース"] = pd.to_numeric(raw["進入コース"], errors="coerce")
    raw["レース番号"] = pd.to_numeric(raw["レース番号"], errors="coerce")
    raw["選手名"]     = raw["選手名"].str.replace(r"\s+", "", regex=True)

    # グレードマスタ適用
    grade_csv = os.path.join(RAW_DIR, "grade_master.csv")
    if os.path.exists(grade_csv):
        gdf = pd.read_csv(grade_csv, dtype=str)
        gdf["開始日"] = pd.to_datetime(gdf["開始日"], errors="coerce")
        gdf["終了日"] = pd.to_datetime(gdf["終了日"], errors="coerce")
        raw["_idx"] = range(len(raw))
        merged = raw[["_idx", "日付", "会場名"]].merge(gdf, on="会場名", how="left")
        merged = merged[
            (merged["開始日"].isna() | (merged["開始日"] <= merged["日付"])) &
            (merged["終了日"].isna() | (merged["日付"]  <= merged["終了日"]))
        ]
        merged = merged.drop_duplicates(subset=["_idx"], keep="first")[["_idx", "グレード"]]
        raw = raw.merge(merged, on="_idx", how="left")
        raw["グレード"] = raw["グレード"].fillna("一般")
        raw.drop(columns=["_idx"], inplace=True)
    else:
        print("  [INFO] grade_master.csv なし → 全レースを一般戦扱い")
        raw["グレード"] = "一般"

    # 対象選手のみ
    df = raw[raw["選手名"] == player_name].copy()
    return raw, df


def wins_by_course(df: pd.DataFrame) -> dict:
    """コース別1着数・出走数・1着率を返す。"""
    result = {}
    for c in range(1, 7):
        sub = df[df["進入コース"] == c]
        runs = len(sub)
        wins = int((sub["着順"] == 1).sum())
        result[c] = {"出走数": runs, "1着数": wins,
                     "1着率": f"{wins/runs*100:.1f}%" if runs > 0 else "—"}
    return result


def print_table(label: str, stats: dict, total_runs: int, total_wins: int):
    """コース別集計テーブルを整形して出力。"""
    print(f"\n【{label}】  総出走:{total_runs}  総1着:{total_wins}")
    print(f"  {'コース':>4} | {'出走数':>6} | {'1着数':>5} | {'1着率':>6}")
    print(f"  {'-'*4}-+-{'-'*6}-+-{'-'*5}-+-{'-'*6}")
    for c in range(1, 7):
        s = stats[c]
        print(f"  {c:>4} | {s['出走数']:>6} | {s['1着数']:>5} | {s['1着率']:>6}")


def apply_nyujo_filter(df: pd.DataFrame) -> pd.DataFrame:
    """進入変更レースを除外（update_master.py と同ロジック）。"""
    if "艇番" not in df.columns and "枠" not in df.columns:
        return df
    waku_col = "艇番" if "艇番" in df.columns else "枠"
    _nyujo = pd.to_numeric(df["進入コース"], errors="coerce")
    _waku  = pd.to_numeric(df[waku_col], errors="coerce")
    changed_mask = _nyujo != _waku
    changed_keys = (
        df.loc[changed_mask, "日付"].astype(str) + "_" +
        df.loc[changed_mask, "会場名"].astype(str) + "_" +
        df.loc[changed_mask, "レース番号"].astype(str)
    ).unique()
    if len(changed_keys) == 0:
        return df
    all_keys = (
        df["日付"].astype(str) + "_" +
        df["会場名"].astype(str) + "_" +
        df["レース番号"].astype(str)
    )
    return df[~all_keys.isin(changed_keys)].copy()


def run(player_name: str):
    print(f"\n{SEP}")
    print(f"  対象選手: 【{player_name}】")
    print(f"  データ場所: {RAW_DIR}")
    print(SEP)

    print("\nデータ読み込み中...")
    raw, df = load_raw(player_name)

    if len(df) == 0:
        print(f"\n[ERROR] 選手「{player_name}」のデータが見つかりません。")
        print("  ※ スペースの有無・漢字の表記を確認してください。")
        # 似た選手名を候補表示
        candidates = raw["選手名"].dropna().unique()
        similar = [n for n in candidates if any(c in n for c in player_name)]
        if similar:
            print(f"\n  似た選手名: {similar[:10]}")
        return

    print(f"  {player_name} の行数: {len(df):,}行")
    print(f"  期間: {df['日付'].min().date()} 〜 {df['日付'].max().date()}")
    print(f"  グレード分布: {dict(df['グレード'].value_counts())}")

    print(f"\n{SEP}")
    print("  ▼ 段階別 コース別1着数（どの除外で数が減るか確認）")
    print(SEP)

    # ── STEP 1: 全データ（公式サイトに最も近い）──────────────────────────────
    s1 = wins_by_course(df)
    print_table("STEP1: 全データ（除外なし）",
                s1, len(df), int((df["着順"] == 1).sum()))

    # ── STEP 2: グレードレース除外（SG/G1〜G3）───────────────────────────────
    df2 = df[~df["グレード"].isin(EXCLUDE_GRADES_IPPAN | ALWAYS_EXCLUDE)].copy()
    s2 = wins_by_course(df2)
    print_table("STEP2: + グレード除外（SG/G1/G2/G3/女子戦等）",
                s2, len(df2), int((df2["着順"] == 1).sum()))

    # ── STEP 3: 優勝戦・準優勝戦等も除外 ─────────────────────────────────────
    df3 = df2.copy()
    if "レース種別" in df3.columns:
        df3 = df3[~df3["レース種別"].isin(EXCLUDE_RACE_TYPES_FINAL)].copy()
    s3 = wins_by_course(df3)
    print_table("STEP3: + 優勝戦・準優勝戦等除外",
                s3, len(df3), int((df3["着順"] == 1).sum()))

    # ── STEP 4: 進入変更レース除外 ────────────────────────────────────────────
    df4 = apply_nyujo_filter(df3)
    s4 = wins_by_course(df4)
    print_table("STEP4: + 進入変更レース除外（= update_master.pyと同じ）",
                s4, len(df4), int((df4["着順"] == 1).sum()))

    # ── 差分サマリー ──────────────────────────────────────────────────────────
    print(f"\n{SEP}")
    print("  ▼ 差分サマリー（各STEPで何着分減ったか）")
    print(SEP)
    steps = [
        ("全データ",         s1),
        ("グレード除外後",    s2),
        ("優勝戦等除外後",    s3),
        ("進入変更除外後",    s4),
    ]
    print(f"\n  {'':20} " + " ".join(f"  C{c}" for c in range(1, 7)))
    for i, (label, s) in enumerate(steps):
        vals = " ".join(f"{s[c]['1着数']:>4}" for c in range(1, 7))
        print(f"  {label:20} {vals}")
        if i > 0:
            prev_s = steps[i-1][1]
            diffs  = " ".join(
                f"{s[c]['1着数'] - prev_s[c]['1着数']:>+4}" for c in range(1, 7)
            )
            print(f"  {'  └差分':20} {diffs}")

    # ── 公式との比較入力 ──────────────────────────────────────────────────────
    print(f"\n{SEP}")
    print("  ▼ 公式サイトの数値と比較（任意）")
    print("    公式の1着数をコース順に入力（例: 29 0 12 7 6 1）")
    print("    スキップする場合はそのままEnter")
    print(SEP)

    try:
        official_input = input("  公式1着数 > ").strip()
        if official_input:
            official = list(map(int, official_input.split()))
            if len(official) == 6:
                print(f"\n  {'':20} " + " ".join(f"  C{c}" for c in range(1, 7)))
                my_vals  = " ".join(f"{s4[c]['1着数']:>4}" for c in range(1, 7))
                off_vals = " ".join(f"{v:>4}" for v in official)
                diff_vals= " ".join(f"{s4[c]['1着数'] - official[c-1]:>+4}" for c in range(1, 7))
                print(f"  {'マスタ(STEP4)':20} {my_vals}")
                print(f"  {'公式サイト':20} {off_vals}")
                print(f"  {'差(マスタ-公式)':20} {diff_vals}")

                # 乖離が大きいコースを詳細表示
                for c in range(1, 7):
                    diff = s4[c]["1着数"] - official[c-1]
                    if abs(diff) >= 2:
                        print(f"\n  ⚠ コース{c}で乖離{diff:+d}着 → 詳細確認:")
                        # そのコースの1着レース一覧（STEP4基準）
                        wins_detail = df4[
                            (df4["進入コース"] == c) & (df4["着順"] == 1)
                        ][["日付", "会場名", "レース番号", "グレード",
                           "レース種別" if "レース種別" in df4.columns else "会場名"]
                        ].copy()
                        wins_detail = wins_detail.sort_values("日付")
                        print(wins_detail.to_string(index=False))
            else:
                print("  ※ 6コース分の数値を入力してください")
    except (EOFError, KeyboardInterrupt):
        pass

    print(f"\n{SEP}")
    print("  完了")
    print(SEP)


if __name__ == "__main__":
    if len(sys.argv) >= 2:
        name = " ".join(sys.argv[1:])
    else:
        print("選手名を入力してください（例: 上原崚）")
        name = input("> ").strip()

    if name:
        run(name)
