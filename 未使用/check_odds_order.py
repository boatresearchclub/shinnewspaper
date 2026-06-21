"""
3連単ページの全120tdを出力する
実行: python check_odds_order.py
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
cells = soup.find_all("td", class_=lambda c: c and "oddsPoint" in c.split() if c else False)

print(f"総数: {len(cells)}")
for i, td in enumerate(cells):
    print(f"[{i+1:3d}] {td.get_text(strip=True)}")
