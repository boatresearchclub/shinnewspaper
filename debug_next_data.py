"""
debug_next_data.py  —  __NEXT_DATA__ の全構造を確認
実行: python debug_next_data.py
"""
import json, time
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from pathlib import Path

URL = "https://boaters-boatrace.com/race/heiwajima/2026-04-25/1R/last-minute?last-minute-content=original-tenji"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    )
    page.goto(URL, wait_until="networkidle", timeout=30000)
    time.sleep(2)
    html = page.content()
    browser.close()

soup = BeautifulSoup(html, "html.parser")
nd = soup.find("script", {"id": "__NEXT_DATA__"})
data = json.loads(nd.string)

# 全文保存
Path("next_data.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
print("next_data.json に保存しました")

# Apollo State の中身を確認
apollo = data.get("props", {}).get("pageProps", {}).get("initialApolloState", {})
print(f"\nApolloStateのキー数: {len(apollo)}")

# CrawledRaceBeforeRacer系のキーを全部表示
racer_keys = [k for k in apollo if "Racer" in k or "racer" in k]
print(f"\nRacerキー: {racer_keys[:10]}")

# 最初のRacerの中身を全部表示
if racer_keys:
    print(f"\n最初のRacer ({racer_keys[0]}) の全フィールド:")
    print(json.dumps(apollo[racer_keys[0]], ensure_ascii=False, indent=2))

# BeforeInfoキーを確認
before_keys = [k for k in apollo if "BeforeInfo" in k or "Tenji" in k or "tenji" in k or "exhibition" in k.lower()]
print(f"\nBeforeInfo系キー: {before_keys}")
if before_keys:
    print(json.dumps(apollo[before_keys[0]], ensure_ascii=False, indent=2))
