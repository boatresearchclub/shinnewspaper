"""
mbrace.or.jp B番組表 一括ダウンロードスクリプト
対象: 2025年6月・7月 (TARGET_MONTHS で変更可能)

【ファイル名規則】
  b{YY}{MM}{DD}.lzh  例: b250601.lzh
  URL: https://www1.mbrace.or.jp/od2/B/{YYYYMM}/b{YYMMDD}.lzh

【保存先】
  scriptsフォルダ直下に保存
  → load_race.py が起動時に自動検出して lzh_to_csv.py で変換する
"""

import os
import time
import requests
from datetime import date, timedelta

# ============================================================
# 設定
# ============================================================
TARGET_MONTHS = [
    (2025, 6),
    (2025, 7),
]

# 保存先: scriptsフォルダ直下（load_race.py が自動検出できる場所）
SAVE_DIR = os.path.dirname(os.path.abspath(__file__))

# リクエスト間隔（秒）
INTERVAL_SEC = 1.0

BASE_URL = "https://www1.mbrace.or.jp/od2/B/{ym}/{filename}"
# ============================================================


def date_range(year, month):
    d = date(year, month, 1)
    while d.month == month:
        yield d
        d += timedelta(days=1)


def download_month(year, month, save_dir, session):
    ym = f"{year}{month:02d}"
    success, skip, fail = 0, 0, 0

    for d in date_range(year, month):
        # ファイル名: b{YY}{MM}{DD}.lzh
        yy = str(d.year)[2:]
        filename = f"b{yy}{d.month:02d}{d.day:02d}.lzh"
        save_path = os.path.join(save_dir, filename)

        # すでに存在する場合はスキップ
        if os.path.exists(save_path):
            print(f"  [SKIP] {filename} (既存)")
            skip += 1
            continue

        url = BASE_URL.format(ym=ym, filename=filename)
        try:
            resp = session.get(url, timeout=15)
            if resp.status_code == 200:
                with open(save_path, "wb") as f:
                    f.write(resp.content)
                size_kb = len(resp.content) / 1024
                print(f"  [OK]   {filename}  ({size_kb:.1f} KB)")
                success += 1
            elif resp.status_code == 404:
                print(f"  [404]  {filename} (非開催日)")
                fail += 1
            else:
                print(f"  [ERR]  {filename} (HTTP {resp.status_code})")
                fail += 1
        except Exception as e:
            print(f"  [ERR]  {filename} ({e})")
            fail += 1

        time.sleep(INTERVAL_SEC)

    return success, skip, fail


def main():
    print(f"保存先: {SAVE_DIR}\n")

    total_ok, total_skip, total_fail = 0, 0, 0

    with requests.Session() as session:
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })

        for year, month in TARGET_MONTHS:
            print(f"=== {year}年{month:02d}月 ===")
            ok, skip, fail = download_month(year, month, SAVE_DIR, session)
            total_ok += ok
            total_skip += skip
            total_fail += fail
            print(f"  → 成功:{ok}  スキップ:{skip}  失敗(非開催):{fail}\n")

    print("=" * 40)
    print(f"完了  成功:{total_ok}  スキップ:{total_skip}  失敗:{total_fail}")
    print(f"保存先: {SAVE_DIR}")
    if total_ok > 0:
        print(f"\n次のステップ: python load_race.py を実行するとLZH→CSV変換が自動で走ります")


if __name__ == "__main__":
    main()
