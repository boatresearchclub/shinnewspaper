# -*- coding: utf-8 -*-
"""
make_grade_master_auto.py
=========================
ボートレース公式サイトのグレードスケジュールページから
自動スクレイピングして grade_master.csv を生成する。

【使い方】
    pip install requests beautifulsoup4   ← 初回のみ
    python make_grade_master_auto.py

【オプション指定例】
    python make_grade_master_auto.py --year 2025
    python make_grade_master_auto.py --year 2025 2026
    python make_grade_master_auto.py --start 2025-01 --end 2026-02

【生成されるCSV】
    grade_master.csv → 自動で data/raw/ にもコピーされる
"""

import re
import csv
import os
import time
import argparse
import shutil
from datetime import datetime
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from collections import Counter

# ── 設定 ──────────────────────────────────────────────────────────────────
OUTPUT_CSV  = "grade_master.csv"
RAW_DIR_REL = os.path.join("..", "data", "raw")
SLEEP_SEC   = 1.2   # リクエスト間隔（公式サイトへの負荷軽減）
BASE_URL    = "https://www.boatrace.jp/owpc/pc/race/gradesch"

# グレードタブ → グレード名の対応
GRADE_TABS = [
    ("sg",      "SG"),
    ("g1",      "G1"),
    ("g2",      "G2"),
    ("g3",      "G3"),
    ("ladies",  "女子戦"),
    ("rookie",  "ルーキーS"),
    ("masters", "マスターズL"),
]

# 会場名の正規化（表記ゆれ対応）
VENUE_MAP = {
    "桐生": "桐生", "戸田": "戸田", "江戸川": "江戸川", "平和島": "平和島",
    "多摩川": "多摩川", "浜名湖": "浜名湖", "蒲郡": "蒲郡", "常滑": "常滑",
    "津": "津", "三国": "三国", "びわこ": "びわこ", "住之江": "住之江",
    "尼崎": "尼崎", "鳴門": "鳴門", "丸亀": "丸亀", "児島": "児島",
    "宮島": "宮島", "徳山": "徳山", "下関": "下関", "若松": "若松",
    "芦屋": "芦屋", "福岡": "福岡", "唐津": "唐津", "大村": "大村",
    "ボートレース桐生": "桐生",   "ボートレース戸田": "戸田",
    "ボートレース江戸川": "江戸川","ボートレース平和島": "平和島",
    "ボートレース多摩川": "多摩川","ボートレース浜名湖": "浜名湖",
    "ボートレース蒲郡": "蒲郡",   "ボートレース常滑": "常滑",
    "ボートレース津": "津",       "ボートレース三国": "三国",
    "ボートレースびわこ": "びわこ","ボートレース住之江": "住之江",
    "ボートレース尼崎": "尼崎",   "ボートレース鳴門": "鳴門",
    "ボートレース丸亀": "丸亀",   "ボートレース児島": "児島",
    "ボートレース宮島": "宮島",   "ボートレース徳山": "徳山",
    "ボートレース下関": "下関",   "ボートレース若松": "若松",
    "ボートレース芦屋": "芦屋",   "ボートレース福岡": "福岡",
    "ボートレース唐津": "唐津",   "ボートレース大村": "大村",
}
VALID_VENUES = set(VENUE_MAP.values())

def normalize_venue(name: str) -> str:
    name = name.strip()
    for k, v in VENUE_MAP.items():
        if name.startswith(k) or k in name:
            return v
    return ""


# ── HTML取得 ──────────────────────────────────────────────────────────────
def fetch_html(url: str, retry: int = 3) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ja,en;q=0.9",
    }
    for attempt in range(retry):
        try:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=20) as res:
                raw = res.read()
                for enc in ("utf-8", "shift_jis", "euc-jp"):
                    try:
                        return raw.decode(enc)
                    except UnicodeDecodeError:
                        continue
                return raw.decode("utf-8", errors="replace")
        except (URLError, HTTPError) as e:
            print(f"    ⚠ 取得失敗 (試行{attempt+1}/{retry}): {e}")
            time.sleep(SLEEP_SEC * 2)
    return ""


# ── HTMLパース（BeautifulSoup版） ─────────────────────────────────────────
def parse_bs4(html: str, grade: str, year: int) -> list:
    from bs4 import BeautifulSoup
    records = []
    soup = BeautifulSoup(html, "html.parser")
    range_re = re.compile(r'(\d{1,2})/(\d{1,2})\s*[〜～~\-–]\s*(\d{1,2})/(\d{1,2})')

    for tr in soup.find_all("tr"):
        cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
        row_text = " ".join(cells)
        m = range_re.search(row_text)
        if not m:
            continue

        sm, sd, em, ed = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
        end_year = year + 1 if (sm == 12 and em <= 2) else year
        start_date = f"{year}-{sm:02d}-{sd:02d}"
        end_date   = f"{end_year}-{em:02d}-{ed:02d}"

        venue = ""
        title_parts = []
        for cell in cells:
            v = normalize_venue(cell)
            if v and not venue:
                venue = v
            elif cell and not range_re.search(cell):
                title_parts.append(cell)

        if not venue:
            continue

        title = " ".join(
            c for c in title_parts
            if len(c) > 2
            and not range_re.search(c)
            and not normalize_venue(c)
        )
        title = re.sub(r'レース結果.*$', '', title).strip()

        records.append({"会場名": venue, "開始日": start_date,
                        "終了日": end_date, "グレード": grade, "タイトル": title})
    return records


# ── HTMLパース（正規表現フォールバック版） ────────────────────────────────
def parse_regex(html: str, grade: str, year: int) -> list:
    records = []
    tag_re  = re.compile(r'<[^>]+>')
    tr_re   = re.compile(r'<tr[^>]*>(.*?)</tr>', re.DOTALL | re.IGNORECASE)
    td_re   = re.compile(r'<t[dh][^>]*>(.*?)</t[dh]>', re.DOTALL | re.IGNORECASE)
    range_re = re.compile(r'(\d{1,2})/(\d{1,2})\s*[〜～~\-–]\s*(\d{1,2})/(\d{1,2})')

    def clean(s):
        s = tag_re.sub('', s)
        s = s.replace('&nbsp;', ' ').replace('&amp;', '&')
        return re.sub(r'\s+', ' ', s).strip()

    for tr_m in tr_re.finditer(html):
        cells = [clean(m.group(1)) for m in td_re.finditer(tr_m.group(1))]
        if not cells:
            continue
        row_text = " ".join(cells)
        m = range_re.search(row_text)
        if not m:
            continue

        sm, sd, em, ed = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
        end_year = year + 1 if (sm == 12 and em <= 2) else year
        start_date = f"{year}-{sm:02d}-{sd:02d}"
        end_date   = f"{end_year}-{em:02d}-{ed:02d}"

        venue = ""
        title_parts = []
        for cell in cells:
            v = normalize_venue(cell)
            if v and not venue:
                venue = v
            elif cell and not range_re.search(cell):
                title_parts.append(cell)

        if not venue:
            continue

        title = " ".join(
            c for c in title_parts
            if len(c) > 2 and not range_re.search(c) and not normalize_venue(c)
        )
        title = re.sub(r'レース結果.*$', '', title).strip()

        records.append({"会場名": venue, "開始日": start_date,
                        "終了日": end_date, "グレード": grade, "タイトル": title})
    return records


def parse_page(html: str, grade: str, year: int) -> list:
    try:
        import bs4  # noqa
        return parse_bs4(html, grade, year)
    except ImportError:
        return parse_regex(html, grade, year)


# ── 全年・全グレード取得 ──────────────────────────────────────────────────
def fetch_all(years: list) -> list:
    all_records = []
    seen = set()

    for year in sorted(set(years)):
        print(f"\n{'='*55}")
        print(f"  {year}年 グレードスケジュール取得中...")
        print(f"{'='*55}")

        for tab_key, grade_name in GRADE_TABS:
            url = f"{BASE_URL}?year={year}&type={tab_key}"
            print(f"\n  [{grade_name:<8}] {url}")

            html = fetch_html(url)
            if not html:
                print(f"    → HTMLの取得に失敗しました（スキップ）")
                time.sleep(SLEEP_SEC)
                continue

            records = parse_page(html, grade_name, year)

            new_cnt = 0
            for r in records:
                key = (r["会場名"], r["開始日"], r["終了日"], r["グレード"])
                if key not in seen:
                    seen.add(key)
                    all_records.append(r)
                    new_cnt += 1
                    print(f"    + {r['開始日']}〜{r['終了日']}  {r['会場名']}  {r['タイトル']}")

            if new_cnt == 0:
                print(f"    → 0件（ページにデータなし or パース失敗）")
            else:
                print(f"    → {new_cnt}件取得")

            time.sleep(SLEEP_SEC)

    return all_records


# ── メイン ────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="ボートレース グレードマスタ自動生成")
    parser.add_argument("--year",  type=int, nargs="+",
                        help="対象年（複数可）例: --year 2025 2026")
    parser.add_argument("--start", type=str,
                        help="開始年月 例: --start 2025-01")
    parser.add_argument("--end",   type=str,
                        help="終了年月 例: --end 2026-02")
    args = parser.parse_args()

    # 対象年の決定
    if args.year:
        years = args.year
    elif args.start and args.end:
        sy = int(args.start.split('-')[0])
        ey = int(args.end.split('-')[0])
        years = list(range(sy, ey + 1))
    else:
        cy = datetime.now().year
        years = [cy - 1, cy]
        print(f"[INFO] 年指定なし → {years} を対象にします")
        print(f"       25年1月〜26年2月の場合:")
        print(f"       python make_grade_master_auto.py --start 2025-01 --end 2026-02\n")

    print(f"対象年: {years}")

    # bs4の有無を確認
    try:
        import bs4
        print("  [INFO] beautifulsoup4 が使用可能です（高精度パース）")
    except ImportError:
        print("  [INFO] beautifulsoup4 未インストール → 正規表現フォールバック使用")
        print("         精度向上のため: pip install beautifulsoup4")

    records = fetch_all(years)

    if not records:
        print("\n[ERROR] データが取得できませんでした。")
        print("  ネットワーク接続を確認してください。")
        print("  または手動でpaste_*.txtを作成し元のmake_grade_master.pyを実行してください。")
        return

    records.sort(key=lambda x: x["開始日"])

    # CSV書き出し
    script_dir = os.path.dirname(os.path.abspath(__file__))
    out_path = os.path.join(script_dir, OUTPUT_CSV)
    with open(out_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=["会場名","開始日","終了日","グレード","タイトル"])
        writer.writeheader()
        writer.writerows(records)
    print(f"\n✅ CSV出力: {out_path}  ({len(records)}件)")

    # data/raw/ にも自動コピー
    raw_dir = os.path.join(script_dir, RAW_DIR_REL)
    if os.path.isdir(raw_dir):
        dest = os.path.join(raw_dir, OUTPUT_CSV)
        shutil.copy2(out_path, dest)
        print(f"✅ data/raw/ にコピー完了: {dest}")
    else:
        print(f"ℹ️  data/raw/ が見つかりません。手動でコピーしてください。")

    # サマリー
    print(f"\n{'='*55}")
    print(f"  グレード別件数")
    print(f"{'='*55}")
    for g, cnt in sorted(Counter(r["グレード"] for r in records).items()):
        print(f"  {g:<12}: {cnt:3d}件")
    print(f"  {'合計':<12}: {len(records):3d}件")
    if records:
        print(f"\n  データ期間: {min(r['開始日'] for r in records)}"
              f" 〜 {max(r['終了日'] for r in records)}")
    print(f"\n  次のステップ:")
    print(f"  python scripts/update_master.py  ← マスタ更新を再実行")


if __name__ == "__main__":
    main()
