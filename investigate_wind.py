# investigate_wind.py
import time, json
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# 風情報ページ（クエリなし）
url = "https://boaters-boatrace.com/race/gamagori/2026-05-03/1R/last-minute"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        locale="ja-JP", viewport={"width": 1280, "height": 900},
    )
    page = ctx.new_page()
    page.goto(url, wait_until="networkidle", timeout=30000)
    for _ in range(15):
        html = page.content()
        if "__NEXT_DATA__" in html:
            break
        time.sleep(1)
    browser.close()

soup = BeautifulSoup(html, "html.parser")
nd = soup.find("script", {"id": "__NEXT_DATA__"})
data = json.loads(nd.string)
apollo = data["props"]["pageProps"]["initialApolloState"]

# ① typename一覧
print("=== __typename 一覧 ===")
for t in sorted({v.get("__typename") for v in apollo.values() if isinstance(v, dict) and v.get("__typename")}):
    print(" ", t)

# ② 風・天候っぽいキーを持つオブジェクトを全表示
print("\n=== 風・天候関連オブジェクト ===")
weather_keys = {"wind","windSpeed","windDirection","windDir","wave","waveHeight","weather","temperature"}
for k, v in apollo.items():
    if isinstance(v, dict) and set(v.keys()) & weather_keys:
        print(f"\n[{k}]")
        print(json.dumps(v, ensure_ascii=False, indent=2))