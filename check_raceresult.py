import requests
from bs4 import BeautifulSoup

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "ja,en-US;q=0.9",
    "Referer": "https://www.boatrace.jp/owpc/pc/race/pay?hd=20260507",
}

r = requests.get(
    "https://www.boatrace.jp/owpc/pc/race/raceresult",
    params={"jcd": "21", "hd": "20260507", "rno": "1"},
    headers=headers,
)
print("status:", r.status_code)

soup = BeautifulSoup(r.text, "html.parser")
tables = soup.find_all("table")
print(f"テーブル数: {len(tables)}")
for i, t in enumerate(tables):
    print(f"\n--- table[{i}] class={t.get('class')} ---")
    for row in t.find_all("tr"):
        cells = row.find_all(["th", "td"])
        texts = [c.get_text(strip=True) for c in cells]
        classes = [c.get("class", []) for c in cells]
        print(f"  {texts}  classes={classes}")
