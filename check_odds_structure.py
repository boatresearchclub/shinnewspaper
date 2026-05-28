"""
3連単ページのtd周辺構造（艇番+オッズのペア）を確認する
実行: python check_odds_structure.py
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

# 全tdをリストアップしてoddsPointの前後を確認
all_tds = soup.find_all("td")
print(f"全td数: {len(all_tds)}")
print()

# oddsPointのtdを見つけて、その前後5つのtdを表示
odds_indices = [i for i, td in enumerate(all_tds)
                if td.get("class") and "oddsPoint" in td.get("class", [])]

print(f"oddsPoint tdの個数: {len(odds_indices)}")
print()
print("先頭5件のoddsPoint前後のtd:")
for oi in odds_indices[:5]:
    print(f"\n  --- oddsPoint[{oi}] = {all_tds[oi].get_text(strip=True)} ---")
    for j in range(max(0, oi-5), min(len(all_tds), oi+3)):
        marker = " <<<" if j == oi else ""
        cls = " ".join(all_tds[j].get("class") or [])
        txt = all_tds[j].get_text(strip=True)[:20]
        print(f"    [{j}] class={cls!r:40s} text={txt!r}{marker}")
