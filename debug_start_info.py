"""
debug_start_info.py — last-minute ページの __NEXT_DATA__ 構造を調査するスクリプト
==============================================================================
使い方:
  python debug_start_info.py --venue tokoname --date 2026-05-06 --race 1

出力:
  - CrawledRaceBeforeRacer の全フィールドと値（枠ごと）
  - CrawledRaceBeforeInfo の全フィールドと値
  - sinnyuMethod などコース関連フィールドの候補
"""

import argparse
import json
import time

VENUE_SLUG = {
    "桐生":   "kiryu",    "戸田":   "toda",     "江戸川": "edogawa",
    "平和島": "heiwajima","多摩川": "tamagawa", "浜名湖": "hamanako",
    "蒲郡":   "gamagori", "常滑":   "tokoname", "津":     "tsu",
    "三国":   "mikuni",   "びわこ": "biwako",   "住之江": "suminoe",
    "尼崎":   "amagasaki","鳴門":   "naruto",   "丸亀":   "marugame",
    "児島":   "kojima",   "宮島":   "miyajima", "徳山":   "tokuyama",
    "下関":   "shimonoseki","若松":  "wakamatsu","芦屋":   "ashiya",
    "福岡":   "fukuoka",  "唐津":   "karatsu",  "大村":   "omura",
}


def fetch_html(url: str, wait_for: str = "CrawledRaceBeforeInfo", poll: int = 20) -> str:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
            viewport={"width": 1280, "height": 900},
        )
        page = ctx.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            for i in range(poll):
                html = page.content()
                if wait_for in html:
                    print(f"  '{wait_for}' 検出 ({i+1}秒後)")
                    return html
                time.sleep(1)
            return page.content()
        except PWTimeout:
            print(f"  タイムアウト: {url}")
            return page.content()
        finally:
            browser.close()


def dump(url: str):
    print(f"\nURL: {url}")
    html = fetch_html(url)

    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    nd = soup.find("script", {"id": "__NEXT_DATA__"})
    if not nd or not nd.string:
        print("  __NEXT_DATA__ が見つかりません")
        return

    data = json.loads(nd.string)
    apollo = (
        data.get("props", {})
            .get("pageProps", {})
            .get("initialApolloState", {})
    )

    print("\n" + "="*60)
    print("■ CrawledRaceBeforeRacer（枠ごとの全フィールド）")
    print("="*60)
    found = False
    for v in apollo.values():
        if not isinstance(v, dict):
            continue
        if v.get("__typename") != "CrawledRaceBeforeRacer":
            continue
        found = True
        bn = v.get("boatNumber", "?")
        print(f"\n  [枠{bn}]")
        for k, val in sorted(v.items()):
            print(f"    {k}: {val!r}")
    if not found:
        print("  ※ CrawledRaceBeforeRacer が存在しません")

    print("\n" + "="*60)
    print("■ CrawledRaceBeforeInfo（全フィールド）")
    print("="*60)
    found = False
    for v in apollo.values():
        if not isinstance(v, dict):
            continue
        if v.get("__typename") != "CrawledRaceBeforeInfo":
            continue
        found = True
        for k, val in sorted(v.items()):
            # リスト系は先頭2件だけ表示
            if isinstance(val, list):
                print(f"  {k}: (list, {len(val)}件) 先頭={val[:2]}")
            else:
                print(f"  {k}: {val!r}")
    if not found:
        print("  ※ CrawledRaceBeforeInfo が存在しません")

    print("\n" + "="*60)
    print("■ CrawledRace（sinnyuMethod / course 系フィールド）")
    print("="*60)
    for v in apollo.values():
        if not isinstance(v, dict):
            continue
        if v.get("__typename") != "CrawledRace":
            continue
        for k, val in sorted(v.items()):
            if any(kw in k.lower() for kw in ("sinnyu", "course", "start", "order")):
                if isinstance(val, list):
                    print(f"  {k}: (list, {len(val)}件) 先頭={val[:3]}")
                else:
                    print(f"  {k}: {val!r}")

    print("\n" + "="*60)
    print("■ 全 __typename 一覧")
    print("="*60)
    seen: dict[str, set] = {}
    for v in apollo.values():
        if isinstance(v, dict) and v.get("__typename"):
            tn = v["__typename"]
            seen.setdefault(tn, set()).update(v.keys())
    for tn, keys in sorted(seen.items()):
        print(f"  {tn}: {sorted(keys)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--venue", required=True)
    ap.add_argument("--date",  required=True)
    ap.add_argument("--race",  type=int, required=True)
    args = ap.parse_args()

    slug = VENUE_SLUG.get(args.venue, args.venue)
    url  = f"https://boaters-boatrace.com/race/{slug}/{args.date}/{args.race}R/last-minute"
    dump(url)


if __name__ == "__main__":
    main()
