# fetch_odds.py の _fetch_html を流用してHTMLを保存するデバッグスクリプト
import urllib.request, pathlib, sys

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.boatrace.jp/",
}

url = "https://www.boatrace.jp/owpc/pc/race/odds3t?rno=12&jcd=15&hd=20260509"
req = urllib.request.Request(url, headers=HEADERS)
with urllib.request.urlopen(req, timeout=15) as res:
    html = res.read().decode("utf-8")

pathlib.Path("odds3t_debug.html").write_text(html, encoding="utf-8")
print(f"保存完了: {len(html)} bytes")
