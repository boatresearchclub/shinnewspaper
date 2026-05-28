"""
3連単ページのtr構造を確認する
実行: python check_odds_tr.py
"""
import urllib.request
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.boatrace.jp/",
}

url = "https://www.boatrace.jp/owpc/pc/race/odds3t?rno=11&jcd=11&hd=20260509"
req = urllib.request.Request(url, headers=HEADERS)
html = urllib.request.urlopen(req, timeout=15).read().decode("utf-8")
soup = BeautifulSoup(html, "html.parser")

# オッズテーブルのtrを全部見る
tables = soup.find_all("table")
print(f"テーブル数: {len(tables)}")

for ti, table in enumerate(tables):
    rows = table.find_all("tr")
    odds_rows = [r for r in rows if r.find("td", class_=lambda c: c and "oddsPoint" in c.split() if c else False)]
    if not odds_rows:
        continue
    print(f"\n=== テーブル{ti} (行数:{len(rows)}, オッズ行:{len(odds_rows)}) ===")
    for ri, row in enumerate(rows[:25]):
        tds = row.find_all("td")
        if not tds:
            continue
        td_info = [((" ".join(td.get("class") or [])), td.get_text(strip=True)[:10]) for td in tds]
        print(f"  行{ri}: {td_info}")
