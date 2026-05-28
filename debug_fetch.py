# -*- coding: utf-8 -*-
"""デバッグ用: 1ページのtd構造＋img alt/srcを詳細出力"""
import re, argparse
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.boatrace.jp/",
}
DATE_RE  = re.compile(r'(\d{1,2})/(\d{1,2})\s*[-~]\s*(\d{1,2})/(\d{1,2})')
MONTH_RE = re.compile(r'^\d{1,2}月$')

parser = argparse.ArgumentParser()
parser.add_argument("--year", type=int, default=2020)
parser.add_argument("--hcd",  type=str, default="03")
args = parser.parse_args()

url = f"https://www.boatrace.jp/owpc/pc/race/gradesch?year={args.year}&hcd={args.hcd}"
print(f"取得: {url}\n")

resp = requests.get(url, headers=HEADERS, timeout=20)
resp.encoding = "utf-8"
soup = BeautifulSoup(resp.text, "html.parser")

for table in soup.find_all("table"):
    rows = table.find_all("tr")
    print(f"=== テーブル ({len(rows)}行) ===")
    for tr in rows[:5]:  # 最初の5行だけ
        tds = tr.find_all("td")
        if len(tds) < 3:
            continue
        t0 = tds[0].get_text(strip=True)
        if not (MONTH_RE.match(t0) or DATE_RE.search(t0)):
            continue
        print(f"\n  td数={len(tds)}")
        for i, td in enumerate(tds):
            txt  = repr(td.get_text(strip=True))
            imgs = td.find_all("img")
            img_info = ""
            if imgs:
                for img in imgs:
                    alt = repr(img.get("alt", ""))
                    src = img.get("src", "")[-40:]  # srcの末尾40文字
                    img_info += f" [img alt={alt} src=...{src}]"
            print(f"    [{i}] {txt}{img_info}")
