"""
debug_grade_html.py  —  グレードセルのHTML構造を確認するデバッグスクリプト
使い方: python debug_grade_html.py
"""
import requests, re
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}

resp = requests.get(
    "https://www.boatrace.jp/owpc/pc/race/index?hd=20260510",
    headers=HEADERS, timeout=20
)
soup = BeautifulSoup(resp.text, "html.parser")

print("=== 津(jcd=09)・丸亀(jcd=15) 行の全セルHTML ===\n")

for row in soup.select("table tbody tr"):
    cells = row.find_all("td")
    if not cells:
        continue

    # 会場名取得
    venue = ""
    for img in cells[0].find_all("img"):
        alt = img.get("alt","").strip()
        if alt:
            venue = alt
            break

    if venue in ("津", "丸亀"):
        print(f"\n{'='*60}")
        print(f"会場: {venue}  (セル数: {len(cells)})")
        for i, td in enumerate(cells):
            inner = str(td)
            if len(inner) > 20:  # 空セルは除外
                print(f"  [td{i}] {inner[:300]}")
