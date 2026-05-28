# -*- coding: utf-8 -*-
"""
download_results.py  ─  mbrace K番組LZH 自動取得 + CSV変換
==============================================================
mbraceサーバから前日（または指定日）のK番組LZHをDLし、
解凍 → convert_kyotei.py でCSV変換 → data_csv/ に月別追記まで一括実行。

【旧 kyotei_auto.bat との対応】
  旧（手動）: data_input/ にLZHを手動配置 → kyotei_auto.bat で一括処理
  新（自動）: このスクリプトが毎朝 run_daily.py STEP0 として全自動実行

【run_daily.py との連携】
  python download_results.py --date 20260417   ← run_daily.py から呼ばれる

【単体実行】
  python download_results.py                   # 前日分
  python download_results.py --date 20260409   # 日付指定
  python download_results.py --dry-run         # URLだけ確認
  python download_results.py --keep-lzh        # LZHを data_input/ に残す

【ファイルの流れ】
  mbrace K/YYYYMM/k{YYMMDD}.lzh
    ↓ DL
  scripts/data_input/k{YYMMDD}.lzh       ← 手動配置と共用フォルダ
    ↓ 7-Zip解凍
  scripts/data_extracted/k{YYMMDD}/*.TXT
    ↓ convert_kyotei.parse_kyotei_file（既存ロジック流用）
  scripts/data_csv/{YYYYMM}_results.csv   ← 月別ファイルに追記
  scripts/data_csv/{YYYYMM}_payouts.csv

【依存】
  pip install requests --break-system-packages
  7-Zip: C:\\Program Files\\7-Zip\\7z.exe  (kyotei_auto.bat と同じパス)
  convert_kyotei.py が同じ scripts/ フォルダにあること
"""

import os, sys, csv, re, time, shutil, argparse, subprocess, pathlib
from datetime import datetime, timedelta

# ── パス設定 ──────────────────────────────────────────────────────────────
_SCRIPT_DIR  = pathlib.Path(__file__).parent

INPUT_DIR    = _SCRIPT_DIR / "data_input"      # LZH保存先（kyotei_auto.bat と同じ）
EXTRACT_DIR  = _SCRIPT_DIR / "data_extracted"  # 解凍先   （kyotei_auto.bat と同じ）
CSV_DIR      = _SCRIPT_DIR / "data_csv"        # CSV出力先（kyotei_auto.bat と同じ）

# lr_config.py があれば DATA_CSV_DIR を優先
try:
    sys.path.insert(0, str(_SCRIPT_DIR))
    from lr_config import DATA_CSV_DIR as _cfg_csv
    CSV_DIR = pathlib.Path(_cfg_csv)
except Exception:
    pass

# 7-Zip パス（kyotei_auto.bat と同じ）
SEVENZIP_PATH = pathlib.Path(r"C:\Program Files\7-Zip\7z.exe")

# mbrace URL
MBRACE_BASE      = "https://www1.mbrace.or.jp/od2/K/{ym}/k{yymmdd}.lzh"
REQUEST_INTERVAL = 1.5   # 秒（サーバ負荷抑制）
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}

# ── convert_kyotei.py をインポート ────────────────────────────────────────
# 同じ scripts/ フォルダにある既存スクリプトをそのまま再利用する。
# parse_block / parse_kyotei_file の実績済みロジックを完全流用。
try:
    from convert_kyotei import parse_kyotei_file
    _CONVERTER_AVAILABLE = True
except ImportError:
    _CONVERTER_AVAILABLE = False
    print("[WARN] convert_kyotei.py が見つかりません。同じ scripts/ フォルダに配置してください。")


# ════════════════════════════════════════════════════════════════════════════
# LZH ダウンロード
# ════════════════════════════════════════════════════════════════════════════

def download_lzh(target_date: str, dry_run: bool = False) -> pathlib.Path | None:
    """
    mbraceから K番組LZHをダウンロードして data_input/ に保存。
    既存ファイルは再ダウンロードせずスキップ。
    """
    dt      = datetime.strptime(target_date, "%Y%m%d")
    ym      = dt.strftime("%Y%m")    # 202604
    yymmdd  = dt.strftime("%y%m%d")  # 260417
    fname   = f"k{yymmdd}.lzh"
    url     = MBRACE_BASE.format(ym=ym, yymmdd=yymmdd)
    dest    = INPUT_DIR / fname

    if dry_run:
        print(f"  [DRY]  {url}")
        return None

    # 既存ファイルがあればスキップ（手動配置 or 前回DL済み）
    if dest.exists():
        print(f"  [SKIP] {fname} は既に data_input/ にあります")
        return dest

    INPUT_DIR.mkdir(parents=True, exist_ok=True)

    try:
        import requests
    except ImportError:
        print("[ERROR] requests が必要: pip install requests --break-system-packages")
        return None

    print(f"  [DL]   {url}")
    try:
        with requests.Session() as sess:
            resp = sess.get(url, headers=HEADERS, timeout=30)
            if resp.status_code == 200:
                dest.write_bytes(resp.content)
                print(f"  [OK]   {fname}  ({len(resp.content)/1024:.1f} KB)")
                time.sleep(REQUEST_INTERVAL)
                return dest
            elif resp.status_code == 404:
                print(f"  [404]  {fname}（未配信 or 非開催日）")
                return None
            else:
                print(f"  [ERR]  HTTP {resp.status_code}: {url}")
                return None
    except Exception as e:
        print(f"  [ERR]  ダウンロード失敗: {e}")
        return None


# ════════════════════════════════════════════════════════════════════════════
# LZH 解凍（kyotei_auto.bat の [1/3] と同じ処理）
# ════════════════════════════════════════════════════════════════════════════

def extract_lzh(lzh_path: pathlib.Path, out_dir: pathlib.Path) -> list:
    """
    7-ZipでLZHを解凍してTXTファイルのパスリストを返す。
    kyotei_auto.bat の 7z.exe 呼び出しと同一。
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    # 7-Zip 実行ファイルを確認
    if SEVENZIP_PATH.exists():
        sevenzip = str(SEVENZIP_PATH)
    else:
        sevenzip = shutil.which("7z") or shutil.which("lhasa") or shutil.which("lha")
        if not sevenzip:
            print(f"  [ERROR] 7-Zip が見つかりません: {SEVENZIP_PATH}")
            print(f"  インストール: https://www.7-zip.org/")
            return []

    try:
        result = subprocess.run(
            [sevenzip, "x", str(lzh_path), f"-o{out_dir}", "-y"],
            capture_output=True, timeout=60,
        )
        if result.returncode != 0:
            print(f"  [WARN] 7-Zip 解凍失敗 (code={result.returncode})")
            return []
    except subprocess.TimeoutExpired:
        print(f"  [WARN] 7-Zip タイムアウト")
        return []
    except Exception as e:
        print(f"  [WARN] 7-Zip エラー: {e}")
        return []

    # 解凍されたTXTファイルを収集（K番組は .TXT または拡張子なし）
    txt_files = list(out_dir.rglob("*.TXT")) + list(out_dir.rglob("*.txt"))
    if not txt_files:
        txt_files = [f for f in out_dir.rglob("*") if f.is_file() and f.suffix == ""]
    return txt_files


# ════════════════════════════════════════════════════════════════════════════
# CSV 月別追記（重複除去付き）
# ════════════════════════════════════════════════════════════════════════════

def _append_csv_dedup(rows: list, filepath: pathlib.Path, key_fields: list) -> int:
    """
    既存CSVに重複なく追記。key_fields の組み合わせで重複判定。
    追記件数を返す。
    """
    if not rows:
        return 0

    filepath.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())

    # 既存行のキーを読み込む
    existing_keys: set = set()
    if filepath.exists():
        try:
            with open(str(filepath), "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    k = tuple(str(row.get(c, "")) for c in key_fields if c in row)
                    existing_keys.add(k)
        except Exception:
            pass

    # 新規行のみ抽出
    new_rows = []
    for row in rows:
        k = tuple(str(row.get(c, "")) for c in key_fields)
        if k not in existing_keys:
            new_rows.append(row)
            existing_keys.add(k)

    if not new_rows:
        return 0

    file_exists = filepath.exists()
    with open(str(filepath), "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        if not file_exists:
            writer.writeheader()
        writer.writerows(new_rows)

    return len(new_rows)


# ════════════════════════════════════════════════════════════════════════════
# メイン処理
# ════════════════════════════════════════════════════════════════════════════

def process_date(target_date: str, keep_lzh: bool = False, dry_run: bool = False) -> bool:
    """
    1日分を全自動処理:
      1. mbrace から K番組LZH をDL（data_input/ に既存ならスキップ）
      2. 7-Zip で解凍 → data_extracted/k{YYMMDD}/
      3. convert_kyotei.parse_kyotei_file でパース
      4. data_csv/{YYYYMM}_results.csv / payouts.csv に月別追記（重複除去）
      5. LZHをアーカイブへ退避（--keep-lzh 指定時はそのまま）
    """
    if not _CONVERTER_AVAILABLE:
        print("[ERROR] convert_kyotei.py が見つかりません。処理を中断します。")
        return False

    dt       = datetime.strptime(target_date, "%Y%m%d")
    yyyymm   = dt.strftime("%Y%m")
    yymmdd   = dt.strftime("%y%m%d")
    lzh_name = f"k{yymmdd}.lzh"

    # CSV出力先（月別ファイル）
    result_csv = CSV_DIR / f"{yyyymm}_results.csv"
    payout_csv = CSV_DIR / f"{yyyymm}_payouts.csv"

    print(f"\n[download_results] {target_date} の処理を開始")

    # ─── STEP1: LZH取得 ─────────────────────────────────────────────────────
    lzh_path = INPUT_DIR / lzh_name
    if lzh_path.exists():
        print(f"  [FOUND] 既存LZH使用: {lzh_name}")
    else:
        lzh_path = download_lzh(target_date, dry_run=dry_run)
        if lzh_path is None:
            return False

    if dry_run:
        return True

    # ─── STEP2: 解凍 ────────────────────────────────────────────────────────
    extract_subdir = EXTRACT_DIR / f"k{yymmdd}"
    if extract_subdir.exists():
        shutil.rmtree(str(extract_subdir), ignore_errors=True)  # 前回残骸を削除

    print(f"  [UNZIP] {lzh_name} → {extract_subdir.name}/")
    txt_files = extract_lzh(lzh_path, extract_subdir)

    if not txt_files:
        print(f"  [WARN]  解凍ファイルが見つかりません。スキップ。")
        return False

    # ─── STEP3: パース（convert_kyotei.parse_kyotei_file を流用）────────────
    all_results, all_payouts = [], []
    for fpath in txt_files:
        print(f"  [PARSE] {fpath.name}")
        try:
            results, payouts, _ = parse_kyotei_file(str(fpath))
            all_results.extend(results)
            all_payouts.extend(payouts)
            print(f"    → 着順: {len(results)}行  払戻: {len(payouts)}行")
        except Exception as e:
            print(f"  [WARN] パース失敗: {fpath.name}  ({e})")

    # ─── STEP4: CSV月別追記 ─────────────────────────────────────────────────
    added_r = _append_csv_dedup(
        all_results, result_csv,
        key_fields=["日付", "会場名", "レース番号", "艇番"]
    )
    added_p = _append_csv_dedup(
        all_payouts, payout_csv,
        key_fields=["日付", "会場名", "レース番号", "券種", "組み合わせ"]
    )

    print(f"  [CSV]  着順 +{added_r}行  払戻 +{added_p}行")
    if added_r > 0 or added_p > 0:
        print(f"  [CSV]  → {result_csv.name}")
        print(f"  [CSV]  → {payout_csv.name}")
    else:
        print(f"  [CSV]  ※ 追記なし（既に取得済みか、データなし）")

    # ─── STEP5: 後処理 ──────────────────────────────────────────────────────
    shutil.rmtree(str(extract_subdir), ignore_errors=True)  # 解凍テンポラリ削除

    if keep_lzh:
        print(f"  [KEEP] LZHを data_input/ に保持: {lzh_name}")
    else:
        _archive_dir = INPUT_DIR / "archive"
        _archive_dir.mkdir(exist_ok=True)
        _dest = _archive_dir / lzh_name
        if not _dest.exists() and lzh_path.exists():
            try:
                shutil.move(str(lzh_path), str(_dest))
                print(f"  [BAK]  LZH退避: data_input/archive/{lzh_name}")
            except Exception as e:
                print(f"  [WARN] LZH退避失敗（続行）: {e}")

    return True


# ════════════════════════════════════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="mbrace K番組LZH → 月別CSV 自動取得（run_daily.py STEP0）"
    )
    parser.add_argument(
        "--date", default=None,
        help="取得日 YYYYMMDD（省略時: 前日）"
    )
    parser.add_argument(
        "--keep-lzh", action="store_true",
        help="処理後もLZHを data_input/ に残す（デフォルト: archive/ へ退避）"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="URLの確認のみ（ダウンロード・変換しない）"
    )
    args = parser.parse_args()

    target_date = args.date or (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
    ok = process_date(target_date, keep_lzh=args.keep_lzh, dry_run=args.dry_run)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
