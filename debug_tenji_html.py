"""
debug_tenji_html.py  —  実際に取得したHTMLを保存して構造を確認
実行: python debug_tenji_html.py
"""
import time, re
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from bs4 import BeautifulSoup
from pathlib import Path

URL = "https://boaters-boatrace.com/race/heiwajima/2026-04-25/1R/last-minute?last-minute-content=original-tenji"

print(f"取得中: {URL}")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    )
    page.goto(URL, wait_until="networkidle", timeout=30000)

    # テーブルが現れるまで最大15秒待機
    for i in range(15):
        html = page.content()
        if "37." in html or "6." in html or "<table" in html.lower():
            print(f"  → {i+1}秒でコンテンツ検出")
            break
        time.sleep(1)
        print(f"  待機中... {i+1}秒", end="\r")
    else:
        print("  → 15秒待ったがコンテンツ未検出")
        html = page.content()

    browser.close()

# HTMLを保存
out = Path("debug_tenji.html")
out.write_text(html, encoding="utf-8")
print(f"\nHTML保存: {out}  ({len(html):,}文字)")
print("  → ブラウザで開いて表示を確認してください")

# 構造を解析
soup = BeautifulSoup(html, "html.parser")
text = soup.get_text("\n")

print("\n--- 数値パターン（3x.xx / 5.xx / 6.xx / 7.xx）---")
nums = re.findall(r"\b(?:3[5-9]\.\d{2}|[567]\.\d{2})\b", text)
print("  見つかった値:", nums[:20] if nums else "なし")

print("\n--- tableタグ ---")
tables = soup.find_all("table")
print(f"  table数: {len(tables)}")
for i, t in enumerate(tables[:3]):
    rows = t.find_all("tr")
    print(f"  table[{i}]: {len(rows)}行")
    for row in rows[:4]:
        cells = [td.get_text(strip=True) for td in row.find_all(["td","th"])]
        if cells:
            print(f"    {cells}")

print("\n--- 1〜6の数字が入った要素 ---")
for tag in soup.find_all(True):
    t = tag.get_text(strip=True)
    if t in ["1","2","3","4","5","6"] and tag.name in ["td","li","span","div"]:
        parent_text = tag.parent.get_text(" ", strip=True)[:80] if tag.parent else ""
        print(f"  <{tag.name} class='{' '.join(tag.get('class',[]))}'>  親: {parent_text}")

print("\n--- __NEXT_DATA__ ---")
nd = soup.find("script", {"id": "__NEXT_DATA__"})
if nd:
    raw = (nd.string or "")[:500]
    print(f"  あり ({len(nd.string or '')}文字)")
    print(f"  先頭: {raw}")
else:
    print("  なし")

print("\n--- 全scriptタグ数 ---")
scripts = soup.find_all("script")
print(f"  {len(scripts)}個")
for sc in scripts:
    src = sc.get("src","")
    snippet = (sc.string or "")[:100]
    if "tenji" in snippet.lower() or "展示" in snippet or "37." in snippet:
        print(f"  [HIT] src={src}  内容: {snippet}")
