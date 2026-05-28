# -*- coding: utf-8 -*-
"""
download_b.py
=============
mbrace.or.jp から当日（または指定日）の番組表 LZH を
C:\\Users\\user\\Desktop\\データ収集\\scripts\\ に直接ダウンロードする。

【使い方】
  python scripts/download_b.py               # 当日分
  python scripts/download_b.py --date 2026-04-03   # 日付指定

【URL構造】
  http://www1.mbrace.or.jp/od2/B/{YYYYMM}/b{YYMMDD}.lzh
  例: http://www1.mbrace.or.jp/od2/B/202604/b260403.lzh

【出力先】
  C:\\Users\\user\\Desktop\\データ収集\\scripts\\b{YYMMDD}.lzh
  ※ lzh_to_csv.py が同フォルダの LZH を自動検出する設定に合わせる
"""

import sys
import pathlib
import argparse
import time
from datetime import datetime

try:
    import requests
except ImportError:
    print("❌ requests がインストールされていません。")
    print("   pip install requests を実行してください。")
    sys.exit(1)

# ============================================================
# 設定
# ============================================================
BASE_URL    = "http://www1.mbrace.or.jp/od2/B/"
SAVE_DIR    = pathlib.Path(r"C:\Users\user\Desktop\データ収集\scripts")
INTERVAL    = 3   # サーバ負荷軽減のための待機秒数
TIMEOUT     = 30  # ダウンロードタイムアウト（秒）
MAX_RETRY   = 3   # リトライ回数


def build_url(dt: datetime) -> str:
    """datetime から LZH の URL を生成する"""
    yyyymm = dt.strftime("%Y%m")
    yymmdd = dt.strftime("%y%m%d")
    return f"{BASE_URL}{yyyymm}/b{yymmdd}.lzh"


def build_filename(dt: datetime) -> str:
    """保存ファイル名を生成する  例: b260403.lzh"""
    return f"b{dt.strftime('%y%m%d')}.lzh"


def download_lzh(dt: datetime, save_dir: pathlib.Path) -> pathlib.Path | None:
    """
    指定日の番組表 LZH をダウンロードして save_dir に保存する。
    成功時は保存パスを、失敗時は None を返す。
    """
    url      = build_url(dt)
    filename = build_filename(dt)
    out_path = save_dir / filename

    if out_path.exists():
        print(f"  [SKIP] 既にダウンロード済み: {filename}")
        return out_path

    print(f"  [DL]   {url}")

    for attempt in range(1, MAX_RETRY + 1):
        try:
            resp = requests.get(url, timeout=TIMEOUT)

            if resp.status_code == 404:
                print(f"  [404]  番組表が公開されていません: {filename}")
                print(f"         （開催なし、または配信前の可能性があります）")
                return None

            resp.raise_for_status()

            # LZH ファイルとして保存
            out_path.write_bytes(resp.content)
            size_kb = len(resp.content) / 1024
            print(f"  [OK]   保存完了: {filename}  ({size_kb:.1f} KB)")
            return out_path

        except requests.exceptions.Timeout:
            print(f"  [!]   タイムアウト (試行 {attempt}/{MAX_RETRY})")
        except requests.exceptions.ConnectionError:
            print(f"  [!]   接続エラー (試行 {attempt}/{MAX_RETRY})")
        except requests.exceptions.HTTPError as e:
            print(f"  [!]   HTTPエラー: {e} (試行 {attempt}/{MAX_RETRY})")
        except Exception as e:
            print(f"  [!]   予期せぬエラー: {e} (試行 {attempt}/{MAX_RETRY})")

        if attempt < MAX_RETRY:
            wait = INTERVAL * attempt
            print(f"         {wait}秒後にリトライ...")
            time.sleep(wait)

    print(f"  [NG]  ダウンロード失敗: {filename}")
    return None


def main():
    parser = argparse.ArgumentParser(description="番組表 LZH ダウンロード")
    parser.add_argument(
        "--date", type=str, default=None,
        help="対象日付 (例: 2026-04-03)。省略時は当日"
    )
    args = parser.parse_args()

    print("=" * 55)
    print("  番組表 LZH ダウンロード (mbrace.or.jp)")
    print("=" * 55)

    # 対象日付を決定
    if args.date:
        try:
            target = datetime.strptime(args.date, "%Y-%m-%d")
        except ValueError:
            print(f"❌ 日付形式が正しくありません: {args.date}  (例: 2026-04-03)")
            sys.exit(1)
    else:
        target = datetime.now()

    print(f"  対象日付: {target.strftime('%Y-%m-%d')}")
    print(f"  保存先  : {SAVE_DIR}")
    print()

    # 保存先フォルダの確認
    if not SAVE_DIR.exists():
        print(f"❌ 保存先フォルダが見つかりません: {SAVE_DIR}")
        print("   フォルダを作成するか、スクリプト上部の SAVE_DIR を修正してください。")
        sys.exit(1)

    result = download_lzh(target, SAVE_DIR)

    print()
    if result:
        print(f"✅ ダウンロード完了: {result.name}")
        print(f"   → lzh_to_csv.py が自動的にCSVに変換します")
    else:
        print("⚠️  ダウンロードできませんでした。")
        print("   番組表の配信時刻（前日夜〜当日朝）を確認してください。")
        sys.exit(1)

    print("=" * 55)


if __name__ == "__main__":
    main()
