"""
tdの順番とサイト表示の対応を総当たりで特定する
実行: python check_odds_mapping.py
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
values = [td.get_text(strip=True) for td in cells]

# 画像2から読み取った実際のオッズ（1着=1の部分）
# 1着固定、2着=2,3,4,5,6、3着=残り の順で画像2から読み取り
known = {
    "1-2-3": 7.4,  "1-2-4": 11.6, "1-2-5": 19.3, "1-2-6": 21.8,
    "1-3-2": 9.7,  "1-3-4": 10.9, "1-3-5": 18.1, "1-3-6": 20.7,
    "1-4-2": 20.0, "1-4-3": 23.3, "1-4-5": 25.6, "1-4-6": 27.8,
    "1-5-2": 35.4, "1-5-3": 41.7, "1-5-4": 42.9, "1-5-6": 40.2,
    "1-6-2": 63.2, "1-6-3": 77.6, "1-6-4": 76.9, "1-6-5": 66.8,
}

# tdの値と既知オッズを照合
print("td順番 → 推定コンボ（値が近いものを表示）")
print()
for i, v in enumerate(values[:30]):
    try:
        fv = float(v)
    except:
        continue
    matches = [(k, ov) for k, ov in known.items() if abs(fv - ov) < 2.0]
    print(f"  [{i+1:3d}] {v:8s} → {matches}")
