"""
fetch_all_venues.py — 指定日の全会場結果を一括取得
====================================================
使い方:
    python fetch_all_venues.py --date 20260507
    python fetch_all_venues.py            ← 省略時は昨日
"""

import argparse
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

# 昨日の開催会場（jcdから逆引き）
# ※ CSVがあれば自動検出、なければここに手動で追加
VENUE_SLUGS = [
    "heiwajima",       # 04
    "tamagawa",   # 05
    "hamanako",   # 06
    "tokoname",   # 08
    "mikuni",     # 10
    "suminoe",    # 12
    "amagasaki",  # 13
    "marugame",   # 15
    "kojima",     # 16
    "tokuyama",   # 18
    "ashiya",     # 21
    "omura",      # 24
]

SCRIPTS_DIR = Path(__file__).parent
FETCH_RESULT_PY = SCRIPTS_DIR / "fetch_result.py"


def main():
    parser = argparse.ArgumentParser(description="全会場結果一括取得")
    parser.add_argument("--date", help="日付 YYYYMMDD（省略時: 昨日）")
    args = parser.parse_args()

    date_str = args.date or (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
    print(f"取得日: {date_str}")
    print(f"対象会場: {len(VENUE_SLUGS)}会場")
    print("=" * 40)

    success, fail = [], []

    for slug in VENUE_SLUGS:
        print(f"\n▶ {slug} ...")
        result = subprocess.run(
            [sys.executable, str(FETCH_RESULT_PY),
             "--venue", slug, "--date", date_str, "--all"],
            cwd=str(SCRIPTS_DIR),
        )
        if result.returncode == 0:
            success.append(slug)
        else:
            fail.append(slug)

    print("\n" + "=" * 40)
    print(f"完了: {len(success)}会場成功 / {len(fail)}会場失敗")
    if fail:
        print(f"失敗: {fail}")


if __name__ == "__main__":
    main()
