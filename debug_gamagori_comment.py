"""
蒲郡コメントURL確認スクリプト（確定版）
========================================
【確定構造】b_comment.htm の JS ソース解析で判明:
  コメント本体 URL:
    /asp/gamagori/kyogi/kyogihtml/comment/comment{YYYYMMDD}07{レース2桁}.htm
  例: comment20260525070{1..12}.htm

使い方:
  python debug_gamagori_comment.py              # 今日の1R
  python debug_gamagori_comment.py --race 3     # 3R
  python debug_gamagori_comment.py --dump       # HTMLをdump_gamagori.htmlに保存
"""

import sys, re, argparse, requests
from datetime import date
from bs4 import BeautifulSoup

JYO  = "07"   # 蒲郡の場コード（固定）
BASE = "https://www.gamagori-kyotei.com/asp/gamagori/kyogi/kyogihtml"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en-US;q=0.9",
}
SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def comment_url(date_str: str, race_no: int) -> str:
    d = date_str.replace("-", "")
    return f"{BASE}/comment/comment{d}{JYO}{race_no:02d}.htm"


def parse_race(html: str, race_no: int) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    result = {}

    # パターンA: ul#comID{race_no}
    race_ul = soup.find("ul", id=f"comID{race_no}")
    if race_ul:
        print(f"  [パースA] ul#comID{race_no} を発見")
        for div in race_ul.find_all("div", id=re.compile(rf"comment{race_no}_\d+")):
            m = re.search(rf"comment{race_no}_(\d+)", div.get("id", ""))
            if not m:
                continue
            waku = int(m.group(1))
            if not (1 <= waku <= 6):
                continue
            key = str(waku)
            result[key] = {}
            li_today  = div.find("li", class_="today")
            li_before = div.find("li", class_="before")
            if li_today:
                result[key]["comment"]      = li_today.get_text(separator="", strip=True)
            if li_before:
                result[key]["comment_prev"] = li_before.get_text(separator="", strip=True)
        if result:
            return result

    # パターンB: table.ta_kyogi を行ごとに走査
    print(f"  [パースB] table.ta_kyogi を走査")
    current_waku = None
    for tr in soup.select("table.ta_kyogi tr"):
        tds = tr.find_all("td")
        if not tds:
            continue
        for td in tds:
            txt = td.get_text(strip=True)
            if re.match(r"^[1-6]$", txt):
                current_waku = int(txt)
        if current_waku is None:
            continue
        comment_td = tr.find("td", class_="comment")
        if not comment_td:
            continue
        key = str(current_waku)
        if key not in result:
            result[key] = {}
        li_today  = comment_td.find("li", class_="today")
        li_before = comment_td.find("li", class_="before")
        if li_today:
            text = li_today.get_text(separator="", strip=True)
            if len(text) > 3 and "comment" not in result[key]:
                result[key]["comment"] = text
        if li_before:
            text = li_before.get_text(separator="", strip=True)
            if len(text) > 3 and "comment_prev" not in result[key]:
                result[key]["comment_prev"] = text

    # パターンC: td.comment を直接探す（構造が異なる場合）
    if not result:
        print(f"  [パースC] td.comment を直接探す")
        for i, td in enumerate(soup.select("td.comment")[:6], start=1):
            text = td.get_text(separator="", strip=True)
            if len(text) > 3:
                result[str(i)] = {"comment": text}

    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--race", type=int, default=1)
    parser.add_argument("--dump", action="store_true", help="HTMLをdump_gamagori.htmlに保存")
    args = parser.parse_args()

    url = comment_url(args.date, args.race)
    print(f"\n蒲郡コメントデバッグ  日付={args.date}  {args.race}R")
    print("=" * 60)
    print(f"[1] コメントURL: {url}")

    try:
        resp = SESSION.get(url, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"  ✗ 取得失敗: {e}")
        sys.exit(1)

    print(f"  ステータス: {resp.status_code}  サイズ: {len(resp.text):,} bytes")
    print(f"  ta_kyogi : {'あり' if 'ta_kyogi'  in resp.text else 'なし'}")
    print(f"  li.today : {'あり' if 'today'     in resp.text else 'なし'}")
    print(f"  ul#comID1: {'あり' if 'comID1'    in resp.text else 'なし'}")
    print(f"  td.comment: {'あり' if 'class=\"comment\"' in resp.text else 'なし'}")

    if args.dump:
        with open("dump_gamagori.html", "w", encoding="utf-8") as f:
            f.write(resp.text)
        print("  → dump_gamagori.html に保存しました")

    print(f"\n[2] {args.race}R コメント抽出:")
    result = parse_race(resp.text, args.race)

    if result:
        print(f"  ✓ {len(result)}艇分取得成功")
        for waku in range(1, 7):
            entry = result.get(str(waku))
            if entry:
                c  = entry.get("comment",      "")
                cp = entry.get("comment_prev",  "")
                print(f"    {waku}枠: 本日=「{c[:40]}」  前日=「{cp[:30]}」")
            else:
                print(f"    {waku}枠: （なし）")
    else:
        print("  ✗ コメントを抽出できませんでした")
        print("  → --dump でHTMLを確認: python debug_gamagori_comment.py --dump")
        if not args.dump:
            # 自動でダンプ
            with open("dump_gamagori.html", "w", encoding="utf-8") as f:
                f.write(resp.text)
            print("  → dump_gamagori.html に自動保存しました")


if __name__ == "__main__":
    main()
