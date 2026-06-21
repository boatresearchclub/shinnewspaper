"""
オッズページの実際のCSSクラス名を確認するデバッグスクリプト
実行: python check_odds_classes.py
"""
import urllib.request
import re

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.boatrace.jp/",
}

URLS = [
    ("3t",  "https://www.boatrace.jp/owpc/pc/race/odds3t?rno=11&jcd=11&hd=20260509"),
    ("3f",  "https://www.boatrace.jp/owpc/pc/race/odds3f?rno=11&jcd=11&hd=20260509"),
    ("2t",  "https://www.boatrace.jp/owpc/pc/race/oddsk?rno=11&jcd=11&hd=20260509"),
    ("2f",  "https://www.boatrace.jp/owpc/pc/race/oddsh?rno=11&jcd=11&hd=20260509"),
    ("tan", "https://www.boatrace.jp/owpc/pc/race/tansho?rno=11&jcd=11&hd=20260509"),
]

for key, url in URLS:
    print(f"\n{'='*50}")
    print(f"  {key}: {url}")
    print('='*50)
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        html = urllib.request.urlopen(req, timeout=15).read().decode("utf-8")

        # tdのクラス名を全部抽出
        td_classes = re.findall(r'<td[^>]+class="([^"]+)"', html)
        odds_classes = sorted(set(c for c in td_classes if "odds" in c.lower() or "Odds" in c))
        print(f"  オッズ関連クラス: {odds_classes}")

        # tdのテキストをクラス付きで先頭20件表示
        td_with_class = re.findall(r'<td[^>]+class="([^"]+)"[^>]*>\s*([^<]{1,20})\s*</td>', html)
        print(f"\n  tdサンプル（先頭20件）:")
        for cls, txt in td_with_class[:20]:
            print(f"    class={cls!r:40s}  text={txt.strip()!r}")

    except Exception as e:
        print(f"  エラー: {e}")
