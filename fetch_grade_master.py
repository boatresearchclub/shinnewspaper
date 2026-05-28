# -*- coding: utf-8 -*-
"""
fetch_grade_master.py  ─ 2020〜2027年 全グレード自動取得
python scripts/fetch_grade_master.py
python scripts/fetch_grade_master.py --year 2024 2025 2026
"""
import re, csv, time, argparse
from pathlib import Path

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("[ERROR] pip install requests beautifulsoup4 を実行してください")
    raise

BASE_DIR   = Path(__file__).parent.parent
OUTPUT_DIR = BASE_DIR / "data_csv"
OUTPUT_CSV = OUTPUT_DIR / "grade_master.csv"

PAGES = [
    ("01", "SG"),
    ("02", "G1"),
    ("03", "G3"),
    ("04", "女子戦"),
    ("05", "ルーキーS"),
    ("06", "マスターズL"),
]

VENUE_MAP = {
    "ボートレース桐生": "桐生", "ボートレース戸田": "戸田",
    "ボートレース江戸川": "江戸川", "ボートレース平和島": "平和島",
    "ボートレース多摩川": "多摩川", "ボートレース浜名湖": "浜名湖",
    "ボートレース蒲郡": "蒲郡", "ボートレース常滑": "常滑",
    "ボートレース津": "津", "ボートレース三国": "三国",
    "ボートレースびわこ": "びわこ", "ボートレース住之江": "住之江",
    "ボートレース尼崎": "尼崎", "ボートレース鳴門": "鳴門",
    "ボートレース丸亀": "丸亀", "ボートレース児島": "児島",
    "ボートレース宮島": "宮島", "ボートレース徳山": "徳山",
    "ボートレース下関": "下関", "ボートレース若松": "若松",
    "ボートレース芦屋": "芦屋", "ボートレース福岡": "福岡",
    "ボートレース唐津": "唐津", "ボートレース大村": "大村",
    "桐生": "桐生", "戸田": "戸田", "江戸川": "江戸川", "平和島": "平和島",
    "多摩川": "多摩川", "浜名湖": "浜名湖", "蒲郡": "蒲郡", "常滑": "常滑",
    "津": "津", "三国": "三国", "びわこ": "びわこ", "住之江": "住之江",
    "尼崎": "尼崎", "鳴門": "鳴門", "丸亀": "丸亀", "児島": "児島",
    "宮島": "宮島", "徳山": "徳山", "下関": "下関", "若松": "若松",
    "芦屋": "芦屋", "福岡": "福岡", "唐津": "唐津", "大村": "大村",
}
VENUE_LIST = sorted(VENUE_MAP.items(), key=lambda x: -len(x[0]))
VENUE_SET  = {re.sub(r'[\s\u3000]+', '', k): v for k, v in VENUE_MAP.items()}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    "Referer": "https://www.boatrace.jp/",
}

DATE_RE  = re.compile(r'(\d{1,2})/(\d{1,2})\s*[-~]\s*(\d{1,2})/(\d{1,2})')
MONTH_RE = re.compile(r'^\d{1,2}月$')


def normalize_venue(text):
    t = re.sub(r'[\s\u3000]+', '', text.strip())
    if t in VENUE_SET:
        return VENUE_SET[t]
    for k, v in VENUE_LIST:
        k2 = re.sub(r'[\s\u3000]+', '', k)
        if k2 and t.startswith(k2):
            return v
    return text.strip()


def get_venue_from_td(td):
    """
    会場tdから会場名を取得。
    新しい年: tdのテキスト（例: '常\u3000滑'）
    古い年:   td内imgのalt属性（例: alt='常滑'）
    """
    # まずテキストを試みる
    text = td.get_text(strip=True)
    if text:
        normalized = normalize_venue(text)
        if normalized in VENUE_SET.values():
            return normalized

    # テキストが空 or 会場名に変換できない → imgのaltを試みる
    img = td.find("img")
    if img:
        alt = img.get("alt", "").strip()
        if alt:
            return normalize_venue(alt)

    return ""


def parse_date_range(s, year):
    m = DATE_RE.search(s)
    if not m:
        return None, None
    sm, sd, em, ed = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
    ey = year + 1 if sm == 12 and em == 1 else year
    return f"{year}-{sm:02d}-{sd:02d}", f"{ey}-{em:02d}-{ed:02d}"


def find_title(tds, start_idx):
    """start_idx以降のaタグからタイトルを取得（優勝者名・レース結果を除外）"""
    NAME_RE = re.compile(
        r'^[\u4e00-\u9fff\u30a0-\u30ff\u3040-\u309f]{1,5}'
        r'[\s\u3000]+'
        r'[\u4e00-\u9fff\u30a0-\u30ff\u3040-\u309f]{1,5}$'
    )
    for j in range(start_idx, len(tds)):
        a = tds[j].find("a")
        if not a:
            continue
        t = a.get_text(strip=True)
        if not t or "レース結果" in t:
            break
        if NAME_RE.match(t):
            continue
        return t
    return ""


def fetch_schedule(year, hcd, grade):
    """
    HTML構造（debug確認済み）:
      新しい年: td内テキストに会場名（全角スペース入り）
      古い年:   td内imgのaltに会場名

      月初行(8列): [月] [日付] [会場td] [img] [空] [タイトルa] [優勝者] [リンク]
      続き行(7列): [日付] [会場td] [img] [空] [タイトルa] [優勝者] [リンク]
    """
    url = f"https://www.boatrace.jp/owpc/pc/race/gradesch?year={year}&hcd={hcd}"
    print(f"  [{grade}] {year}年 取得中... ", end="", flush=True)

    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.encoding = "utf-8"
        if resp.status_code != 200:
            print(f"[NG] HTTP {resp.status_code}")
            return []
    except Exception as e:
        print(f"[NG] {e}")
        return []

    soup    = BeautifulSoup(resp.text, "html.parser")
    records = []

    for table in soup.find_all("table"):
        for tr in table.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) < 3:
                continue

            t0 = tds[0].get_text(strip=True)

            # 列オフセット決定
            if MONTH_RE.match(t0) and len(tds) > 1 and DATE_RE.search(tds[1].get_text(strip=True)):
                # 月初行: td[0]=月, td[1]=日付, td[2]=会場, td[3~]=タイトル
                date_str  = tds[1].get_text(strip=True)
                venue_td  = tds[2]
                title_start = 3
            elif DATE_RE.search(t0):
                # 続き行: td[0]=日付, td[1]=会場, td[2~]=タイトル
                date_str  = t0
                venue_td  = tds[1]
                title_start = 2
            else:
                continue

            start_date, end_date = parse_date_range(date_str, year)
            if not start_date:
                continue

            venue = get_venue_from_td(venue_td)  # テキスト → imgのalt の順で取得
            title = find_title(tds, title_start)
            title = re.sub(r'\s+', ' ', title).strip()

            records.append({
                "会場名":   venue,
                "開始日":   start_date,
                "終了日":   end_date,
                "グレード": grade,
                "タイトル": title,
            })

    print(f"{len(records)}件")
    return records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, nargs="+", default=list(range(2020, 2028)))
    args = parser.parse_args()

    years = sorted(args.year)
    total = len(years) * len(PAGES)
    print(f"取得対象: {years[0]}〜{years[-1]}年 / {len(PAGES)}グレード / 計{total}ページ")
    print()

    all_records = []
    done = 0
    for year in years:
        for hcd, grade in PAGES:
            done += 1
            print(f"[{done}/{total}]", end=" ")
            all_records.extend(fetch_schedule(year, hcd, grade))
            time.sleep(0.8)

    if not all_records:
        print("\n[ERROR] データが取得できませんでした。")
        return

    all_records.sort(key=lambda x: (x["開始日"], x["会場名"]))
    seen, unique = set(), []
    for r in all_records:
        key = (r["開始日"], r["会場名"], r["グレード"])
        if key not in seen:
            seen.add(key)
            unique.append(r)

    no_venue = [r for r in unique if not r["会場名"]]
    if no_venue:
        print(f"\n⚠ 会場名未取得: {len(no_venue)}件（先頭5件）")
        for r in no_venue[:5]:
            print(f"  {r['開始日']} {r['グレード']} {r['タイトル']}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["会場名","開始日","終了日","グレード","タイトル"])
        writer.writeheader()
        writer.writerows(unique)

    print(f"\n✅ 完了: {OUTPUT_CSV}")
    print(f"   件数: {len(unique)}件  ({years[0]}〜{years[-1]}年)")
    if no_venue:
        print(f"   ⚠ 会場名未取得 {len(no_venue)}件")


if __name__ == "__main__":
    main()
