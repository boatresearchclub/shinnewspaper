# -*- coding: utf-8 -*-
"""
backfill_kimari.py  ─  蓄積CSV「決まり手傾向」補完スクリプト

【概要】
  data/raw/*_results.csv から 選手名×進入コース 別の決まり手%を集計し、
  数値蓄積フォルダ内の全CSVに対して「決まり手傾向」列が空の行を補完する。

【使い方】
  cd データ収集
  python scripts/backfill_kimari.py

【前提条件】
  - data/raw/ に *_results.csv（または 2*.csv）が存在すること
  - 数値蓄積フォルダ（C:\\Users\\user\\Desktop\\データ収集\\scripts\\数値蓄積）
    に会場別の蓄積CSVが存在すること

【決まり手傾向の形式】
  "逃げ65% 差し20% まくり10%"  ← 0%の項目は省略
  update_master.py / lr_calc.py と同じロジック（直近1年・コース別）

【注意】
  - 既に値が入っている行は上書きしない（--force オプションで強制上書き可）
  - 補完後はバックアップを作成してから上書き保存する
"""

import argparse
import glob
import os
import pathlib
import shutil
import sys

import pandas as pd

# ── パス設定 ────────────────────────────────────────────────────────────────
BASE_DIR      = pathlib.Path(__file__).parent.parent  # データ収集/
RAW_DIR       = BASE_DIR / "data" / "raw"
CHIKUSEKI_DIR = pathlib.Path(r"C:\Users\user\Desktop\データ収集\scripts\数値蓄積")

# 決まり手カテゴリ（表示順）
KIMETE_CATS = ["逃げ", "差し", "まくり", "まくり差し", "抜き", "恵まれ"]


# ════════════════════════════════════════════════════════════════════════════
# 1. raw_results.csv から 決まり手% テーブルを作成
# ════════════════════════════════════════════════════════════════════════════
def build_kimari_table(raw_dir: pathlib.Path) -> pd.DataFrame:
    """
    選手名 × 進入コース 別の決まり手% を集計して返す。

    戻り値 DataFrame の列:
        選手名, 進入コース, 逃げ%, 差し%, まくり%, まくり差し%, 抜き%, 恵まれ%
    """
    # CSV読み込み
    csv_files = sorted(glob.glob(str(raw_dir / "*_results.csv")))
    if not csv_files:
        csv_files = sorted(glob.glob(str(raw_dir / "2*.csv")))
        csv_files = [f for f in csv_files if "_payouts" not in f and "grade_master" not in f]
    if not csv_files:
        raise FileNotFoundError(f"raw_results.csv が見つかりません: {raw_dir}")

    dfs = []
    for f in csv_files:
        try:
            dfs.append(pd.read_csv(f, dtype=str))
            print(f"  読込: {os.path.basename(f)}")
        except Exception as e:
            print(f"  ⚠ スキップ: {os.path.basename(f)} ({e})")

    raw = pd.concat(dfs, ignore_index=True).drop_duplicates()
    print(f"  合計: {len(raw):,} 行")

    # 必須列チェック
    required = {"選手名", "進入コース", "着順", "日付"}
    missing = required - set(raw.columns)
    if missing:
        raise ValueError(f"必須列が不足: {missing}")
    if "決まり手" not in raw.columns:
        raise ValueError("「決まり手」列が raw_results.csv にありません。"
                         "boatrace公式の決まり手データを含む形式が必要です。")

    # 型変換
    raw["日付"]       = pd.to_datetime(raw["日付"], errors="coerce")
    raw["着順"]       = pd.to_numeric(raw["着順"],  errors="coerce")
    raw["進入コース"] = pd.to_numeric(raw["進入コース"], errors="coerce")
    raw["選手名"]     = raw["選手名"].str.replace(r"\s+", "", regex=True)

    # 直近1年に絞る（update_master.py と同ロジック）
    cutoff = raw["日付"].max() - pd.Timedelta(days=365)
    df_1y  = raw[raw["日付"] >= cutoff].copy()
    print(f"  📅 集計期間: {cutoff.date()} 〜 {raw['日付'].max().date()} （直近1年）")
    print(f"     対象行数: {len(df_1y):,} 行")

    # ── 分母: 選手名×コース別の出走数（直近1年・全コース） ──────────────────
    base_all = df_1y.groupby(["選手名", "進入コース"]).size().reset_index(name="出走数_1y")

    # ── 逃げ%: 全コース対象（1着時に"逃げ"が決まり手） ─────────────────────
    ichi_all = df_1y[df_1y["着順"] == 1].copy()
    km_all   = (
        ichi_all.groupby(["選手名", "進入コース"])["決まり手"]
        .apply(lambda x: (x == "逃げ").sum())
        .reset_index(name="逃げ_件数")
    )
    km_all = km_all.merge(base_all, on=["選手名", "進入コース"], how="left")
    km_all["逃げ%"] = (km_all["逃げ_件数"] / km_all["出走数_1y"]).fillna(0)

    # ── 攻め決まり手: コース2〜6のみ ─────────────────────────────────────────
    ichi_26 = df_1y[(df_1y["着順"] == 1) & (df_1y["進入コース"] != 1)].copy()
    base_26 = (
        df_1y[df_1y["進入コース"] != 1]
        .groupby(["選手名", "進入コース"]).size()
        .reset_index(name="出走数_1y_26")
    )

    attack_cats = ["差し", "まくり", "まくり差し", "抜き", "恵まれ"]
    km_26_list = []
    for cat in attack_cats:
        tmp = (
            ichi_26.groupby(["選手名", "進入コース"])["決まり手"]
            .apply(lambda x, c=cat: (x == c).sum())
            .reset_index(name=f"{cat}_件数")
        )
        km_26_list.append(tmp)

    # 全カテゴリをマージ
    km_26 = km_26_list[0]
    for tmp in km_26_list[1:]:
        km_26 = km_26.merge(tmp, on=["選手名", "進入コース"], how="outer")
    km_26 = km_26.merge(base_26, on=["選手名", "進入コース"], how="left")
    for cat in attack_cats:
        km_26[f"{cat}%"] = (km_26[f"{cat}_件数"] / km_26["出走数_1y_26"]).fillna(0)

    # ── 結合 ──────────────────────────────────────────────────────────────
    result = km_all[["選手名", "進入コース", "逃げ%"]].merge(
        km_26[["選手名", "進入コース"] + [f"{c}%" for c in attack_cats]],
        on=["選手名", "進入コース"], how="outer"
    )
    for cat in KIMETE_CATS:
        col = f"{cat}%"
        if col not in result.columns:
            result[col] = 0.0
        result[col] = result[col].fillna(0.0)

    print(f"  ✓ 決まり手テーブル: {len(result):,} 行（選手×コース）")
    return result


# ════════════════════════════════════════════════════════════════════════════
# 2. 決まり手% → "逃げ65% 差し20%..." 形式の文字列に変換
# ════════════════════════════════════════════════════════════════════════════
def pct_to_str(row: dict) -> str:
    """
    {'逃げ%': 0.65, '差し%': 0.20, ...} → "逃げ65% 差し20%"
    0%の項目は省略。小数は四捨五入して整数%表示。
    """
    parts = []
    for cat in KIMETE_CATS:
        pct = row.get(f"{cat}%", 0) or 0
        pct_int = round(float(pct) * 100)
        if pct_int > 0:
            parts.append(f"{cat}{pct_int}%")
    return " ".join(parts)


# ════════════════════════════════════════════════════════════════════════════
# 3. 蓄積CSVを補完
# ════════════════════════════════════════════════════════════════════════════
def backfill_csv(csv_path: pathlib.Path, kimari_table: pd.DataFrame, force: bool = False) -> int:
    """
    指定CSVの「決まり手傾向」が空の行を補完する。
    戻り値: 補完した行数
    """
    try:
        df = pd.read_csv(csv_path, encoding="utf-8-sig", dtype=str)
    except Exception as e:
        print(f"  ⚠ 読み込み失敗: {csv_path.name} ({e})")
        return 0

    if "決まり手傾向" not in df.columns:
        print(f"  ⚠ 「決まり手傾向」列なし: {csv_path.name}")
        return 0
    if "選手名" not in df.columns or "進入コース" not in df.columns:
        print(f"  ⚠ 必須列（選手名/進入コース）なし: {csv_path.name}")
        return 0

    # 補完対象の行を特定
    if force:
        target_mask = pd.Series([True] * len(df))
    else:
        target_mask = (
            df["決まり手傾向"].isna() |
            (df["決まり手傾向"].str.strip() == "") |
            (df["決まり手傾向"].str.strip() == "-")
        )

    if target_mask.sum() == 0:
        print(f"  → 補完対象なし: {csv_path.name}")
        return 0

    # lookup用インデックスを作成（選手名×進入コース → 決まり手文字列）
    # 進入コースは整数に正規化して照合
    lookup = {}
    for _, row in kimari_table.iterrows():
        name  = str(row["選手名"]).strip()
        course = int(row["進入コース"]) if pd.notna(row["進入コース"]) else 0
        lookup[(name, course)] = pct_to_str(row)

    filled = 0
    for idx in df[target_mask].index:
        name   = str(df.at[idx, "選手名"]).strip()
        try:
            course = int(float(df.at[idx, "進入コース"]))
        except (ValueError, TypeError):
            continue

        val = lookup.get((name, course), "")
        if val:
            df.at[idx, "決まり手傾向"] = val
            filled += 1

    if filled == 0:
        print(f"  → マッチなし: {csv_path.name}")
        return 0

    # バックアップ作成
    bak = csv_path.with_suffix(".bak.csv")
    shutil.copy2(csv_path, bak)

    # 上書き保存
    df.to_csv(csv_path, encoding="utf-8-sig", index=False)
    print(f"  ✓ {csv_path.name}: {filled}行 補完  (bak: {bak.name})")
    return filled


# ════════════════════════════════════════════════════════════════════════════
# 4. メイン
# ════════════════════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(description="蓄積CSV「決まり手傾向」補完スクリプト")
    parser.add_argument("--raw-dir",    type=str, default=str(RAW_DIR),
                        help=f"raw_results.csv フォルダ（デフォルト: {RAW_DIR}）")
    parser.add_argument("--chikuseki-dir", type=str, default=str(CHIKUSEKI_DIR),
                        help=f"数値蓄積フォルダ（デフォルト: {CHIKUSEKI_DIR}）")
    parser.add_argument("--force", action="store_true",
                        help="既に値がある行も上書きする")
    parser.add_argument("--dry-run", action="store_true",
                        help="補完せずに対象行数だけ確認する")
    args = parser.parse_args()

    raw_dir       = pathlib.Path(args.raw_dir)
    chikuseki_dir = pathlib.Path(args.chikuseki_dir)

    print("=" * 60)
    print("  決まり手傾向 補完スクリプト")
    print("=" * 60)

    # ── 1. 決まり手テーブル構築 ──────────────────────────────────────────
    print(f"\n[1/2] raw_results.csv から決まり手テーブルを集計...")
    print(f"      読込先: {raw_dir}")
    try:
        kimari_table = build_kimari_table(raw_dir)
    except FileNotFoundError as e:
        print(f"\n[NG] {e}")
        print("     data/raw/ に *_results.csv を置いてください。")
        sys.exit(1)
    except ValueError as e:
        print(f"\n[NG] {e}")
        sys.exit(1)

    # ── 2. 蓄積CSVを補完 ────────────────────────────────────────────────
    print(f"\n[2/2] 蓄積CSVを補完...")
    print(f"      対象フォルダ: {chikuseki_dir}")

    if not chikuseki_dir.exists():
        print(f"\n[NG] フォルダが見つかりません: {chikuseki_dir}")
        sys.exit(1)

    csv_files = sorted(chikuseki_dir.glob("*.csv"))
    # バックアップファイルは除外
    csv_files = [f for f in csv_files if not f.name.endswith(".bak.csv")]

    if not csv_files:
        print("  [!] 補完対象のCSVが見つかりません。")
        sys.exit(0)

    print(f"  対象ファイル: {len(csv_files)} 件")

    total_filled = 0
    for csv_path in csv_files:
        if args.dry_run:
            # dry-run: 対象行数だけカウント
            try:
                df = pd.read_csv(csv_path, encoding="utf-8-sig", dtype=str)
                if "決まり手傾向" in df.columns:
                    n = (df["決まり手傾向"].isna() | (df["決まり手傾向"].str.strip() == "")).sum()
                    print(f"  {csv_path.name}: 補完対象 {n}行")
                    total_filled += n
            except Exception as e:
                print(f"  ⚠ {csv_path.name}: {e}")
        else:
            total_filled += backfill_csv(csv_path, kimari_table, force=args.force)

    print()
    print("=" * 60)
    if args.dry_run:
        print(f"  [DRY-RUN] 補完予定: {total_filled}行")
    else:
        print(f"  [完了] 補完: {total_filled}行")
        if total_filled > 0:
            print("  ※ 元ファイルは .bak.csv としてバックアップ済み")
    print("=" * 60)


if __name__ == "__main__":
    main()
