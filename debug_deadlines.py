"""
debug_deadlines.py  —  boatrace.jp の締め切り時刻HTML構造を調査
================================================================
まずこれを実行して、HTMLの構造を確認してください。

  python debug_deadlines.py --venue heiwajima --date 2026-04-25

出力される内容:
  - ページ取得の成否
  - 時刻らしきテキストの一覧
  - 締め切り関連キーワード周辺のHTML断片
  - 生HTMLをファイルに保存（ブラウザで開いて確認可能）
"""

import re, time, argparse
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from bs4 import BeautifulSoup

VENUE_JCD = {
    "桐生":"01","戸田":"02","江戸川":"03","平和島":"04","多摩川":"05",
    "浜名湖":"06","蒲郡":"07","常滑":"08","津":"09","三国":"10",
    "びわこ":"11","住之江":"12","尼崎":"13","鳴門":"14","丸亀":"15",
    "児島":"16","宮島":"17","徳山":"18","下関":"19","若松":"20",
    "芦屋":"21","福岡":"22","唐津":"23","大村":"24",
    "kiryu":"01","toda":"02","edogawa":"03","heiwajima":"04","tamagawa":"05",
    "hamanako":"06","gamagori":"07","tokoname":"08","tsu":"09","mikuni":"10",
    "biwako":"11","suminoe":"12","amagasaki":"13","naruto":"14","marugame":"15",
    "kojima":"16","miyajima":"17","tokuyama":"18","shimonoseki":"19","wakamatsu":"20",
    "ashiya":"21","fukuoka":"22","karatsu":"23","omura":"24",
}


def fetch_and_inspect(venue: str, date_str: str, save_html: bool = True):
    jcd = VENUE_JCD.get(venue)
    if not jcd:
        print(f"[ERROR] 未対応の場: {venue}")
        return

    hd = date_str.replace("-", "")
    url = f"https://www.boatrace.jp/owpc/pc/race/racelist?rno=1&jcd={jcd}&hd={hd}"
    print(f"\nURL: {url}")

    html = ""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        )
        try:
            page.goto(url, wait_until="networkidle", timeout=25000)
            time.sleep(3)
            html = page.content()
            print(f"[OK] HTML取得成功: {len(html):,} 文字")
        except PWTimeout:
            html = page.content()
            print(f"[WARN] タイムアウト、途中のHTMLを使用: {len(html):,} 文字")
        except Exception as e:
            print(f"[ERROR] {e}")
        finally:
            browser.close()

    if not html or len(html) < 500:
        print("[ERROR] HTMLが取得できていません")
        return

    # HTMLを保存（ブラウザで開いて確認）
    if save_html:
        out_path = Path(f"debug_{venue}_{hd}.html")
        out_path.write_text(html, encoding="utf-8")
        print(f"[保存] {out_path}  ← ブラウザで開いて内容を確認してください")

    soup = BeautifulSoup(html, "html.parser")
    full_text = soup.get_text("\n")

    # ── 1. 時刻パターンを全部抽出 ──
    print("\n" + "="*55)
    print("■ ページ内の時刻パターン (HH:MM)")
    print("="*55)
    times = re.findall(r"\d{1,2}:\d{2}", full_text)
    time_counts = {}
    for t in times:
        h = int(t.split(":")[0])
        if 8 <= h <= 21:
            time_counts[t] = time_counts.get(t, 0) + 1
    for t, cnt in sorted(time_counts.items()):
        print(f"  {t}  ({cnt}回)")

    # ── 2. 締め切りキーワード周辺のHTML ──
    print("\n" + "="*55)
    print("■ 締め切りキーワード周辺のHTML")
    print("="*55)
    keywords = ["〆切", "締切", "締め切り", "deadline", "〆"]
    for kw in keywords:
        idx = html.find(kw)
        if idx >= 0:
            snippet = html[max(0, idx-100):idx+200]
            print(f"\n--- '{kw}' が見つかりました (位置:{idx}) ---")
            print(snippet)

    # ── 3. レースナビゲーション周辺のHTML ──
    print("\n" + "="*55)
    print("■ レース番号タブ/ナビ周辺のHTML")
    print("="*55)
    for tag in soup.find_all(string=re.compile(r"1R|2R|3R")):
        parent = tag.parent
        if parent:
            snippet = str(parent)[:300]
            print(f"\n--- '{tag.strip()}' の親要素 ---")
            print(snippet)
            break  # 最初の1件だけ

    # ── 4. table要素の構造 ──
    print("\n" + "="*55)
    print("■ tableの最初の数行")
    print("="*55)
    for table in soup.find_all("table")[:3]:
        rows = table.find_all("tr")[:5]
        for row in rows:
            cells = [td.get_text(strip=True)[:20] for td in row.find_all(["td","th"])]
            if cells:
                print("  |", " | ".join(cells))
        print()

    # ── 5. クラス名一覧（時刻が含まれそうなもの） ──
    print("\n" + "="*55)
    print("■ 時刻を含む要素のクラス名")
    print("="*55)
    time_pat = re.compile(r"\d{1,2}:\d{2}")
    for tag in soup.find_all(True):
        text = tag.get_text(strip=True)
        if time_pat.match(text) and len(text) <= 10:
            cls = tag.get("class", [])
            print(f"  <{tag.name} class='{' '.join(cls)}'> {text}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="boatrace.jp HTML構造調査ツール")
    ap.add_argument("--venue", required=True, help="場スラッグ or 日本語名")
    ap.add_argument("--date", required=True, help="日付 YYYY-MM-DD")
    ap.add_argument("--no-save", action="store_true", help="HTMLファイルを保存しない")
    args = ap.parse_args()
    fetch_and_inspect(args.venue, args.date, save_html=not args.no_save)
