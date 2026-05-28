"""
fetch_race_index.py  —  ボートレース公式サイトから本日の開催情報を取得
========================================================================
【出力】
  このスクリプトと同じフォルダに race_index.json を保存する。
  （--out 引数は日本語パスの文字化けを避けるため廃止）

【使い方】
  python fetch_race_index.py
  python fetch_race_index.py --date 20260510

【依存】
  pip install requests beautifulsoup4

【変更履歴】
  - race_kinds取得を並列化（ThreadPoolExecutor）→ タイムアウト対策
  - グレード検出をテーブル全体スキャン方式に変更（rowspan対応）
  - GRADE_CLASS_RE を [a-z] サフィックス対応に修正（is-G3b 等を正しく検出）
"""

import argparse, json, re, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("pip install requests beautifulsoup4 を実行してください")
    sys.exit(1)

BASE_URL      = "https://www.boatrace.jp/owpc/pc/race/index"
RACEINDEX_URL = "https://www.boatrace.jp/owpc/pc/race/raceindex"
HEADERS  = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}
TIMEOUT = 20  # 1会場あたりのタイムアウト

SCRIPTS_DIR = Path(__file__).parent

GRADE_CLASS_RE = re.compile(r"\bis-(SG|PG1|G1|G2|G3)[a-z]\b", re.IGNORECASE)

# 女子戦判定キーワード（タイトルに含まれていれば is_joshi: true）
JOSHI_KEYWORDS = {
    "ヴィーナス", "レディース", "女子", "クイーン", "プリンセス",
    "VENUS", "LADIES", "LADY", "PRINCESS",
    "Lady", "Venus", "Princess",
}

def normalize_venue(raw):
    return raw.replace("\u3000","").replace(" ","").replace("\u00a0","").strip()

def build_grade_map(soup):
    """
    テーブル全体を走査し、tr インデックス → グレード のマップを返す。
    rowspan をまたいでいるケース（SG等）に対応。
    """
    grade_map = {}
    for i, row in enumerate(soup.select("table tbody tr")):
        for td in row.find_all("td"):
            for cls in td.get("class", []):
                m = GRADE_CLASS_RE.search(cls)
                if m:
                    g = m.group(1).upper()
                    grade = "SG" if g in ("SG", "PG1") else g
                    span = int(td.get("rowspan", 1))
                    for j in range(span):
                        grade_map[i + j] = grade
    return grade_map

def fetch_race_kinds(jcd, hd):
    """
    会場の raceindex ページから各レース番号→種別名を取得する。
    例: {12: "優勝戦", 11: "準優勝戦", 10: "準優勝戦", ...}
    取得できなかった場合は空dict を返す。
    """
    try:
        resp = requests.get(
            RACEINDEX_URL,
            headers=HEADERS,
            params={"jcd": jcd, "hd": hd},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  [raceindex] 取得エラー jcd={jcd}: {e}", flush=True)
        return {}

    soup = BeautifulSoup(resp.text, "html.parser")
    kinds = {}

    for row in soup.select("table tbody tr, .is-raceList li, [class*='race'] tr"):
        text = row.get_text(separator=" ", strip=True)
        m_rno = re.search(r"(\d{1,2})[Rレ]", text)
        if not m_rno:
            continue
        rno = int(m_rno.group(1))
        kind = ""
        for kw in ["優勝戦", "準優勝戦", "準優進出戦", "敗者復活戦", "一般戦", "予選"]:
            if kw in text:
                kind = kw
                break
        if kind:
            kinds[rno] = kind

    return kinds

def fetch(date_str=None):
    # date_str が未指定の場合は今日の日付を明示的に使う（キャッシュ防止）
    today = datetime.now().strftime("%Y%m%d")
    hd = date_str if date_str else today
    params = {"hd": hd}

    try:
        resp = requests.get(BASE_URL, headers=HEADERS, params=params, timeout=TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  取得エラー: {e}", flush=True)
        return {}

    soup = BeautifulSoup(resp.text, "html.parser")

    # 日付：リクエストした hd を正とする（HTMLパースに頼らない）
    date_label = f"{hd[:4]}-{hd[4:6]}-{hd[6:]}"

    # テーブル全体からグレードマップを先に構築（rowspan対応）
    grade_map = build_grade_map(soup)

    venues = {}
    for i, row in enumerate(soup.select("table tbody tr")):
        cells = row.find_all("td")
        if not cells:
            continue

        venue = ""
        for img in cells[0].find_all("img"):
            alt = img.get("alt","").strip()
            if alt:
                venue = normalize_venue(alt)
                break
        if not venue:
            continue

        grade = grade_map.get(i, "一般")

        title = ""
        jcd   = ""
        for td in cells:
            for a in td.find_all("a", href=True):
                href = a.get("href","")
                m_jcd = re.search(r"jcd=(\d{2})", href)
                if m_jcd and "raceindex" in href:
                    jcd   = m_jcd.group(1)
                    title = a.get_text(separator="", strip=True)
                    break
            if title:
                break

        period = ""
        day    = ""
        for td in cells:
            text = td.get_text(separator="\n", strip=True)
            if not period:
                m_p = re.search(r"(\d{1,2}/\d{1,2}[-–]\d{1,2}/\d{1,2})", text)
                if m_p:
                    period = m_p.group(1)
            if not day:
                m_d = re.search(r"(\d+日目|最終日|初日)", text)
                if m_d:
                    day = m_d.group(1)
            if period and day:
                break

        # 総日数: period "M/D-M/D" から計算
        total_days = None
        if period:
            m_pd = re.match(r"(\d{1,2})/(\d{1,2})[-–](\d{1,2})/(\d{1,2})", period)
            if m_pd:
                from datetime import date as _date
                year = int(hd[:4])
                sm, sd = int(m_pd.group(1)), int(m_pd.group(2))
                em, ed = int(m_pd.group(3)), int(m_pd.group(4))
                try:
                    start = _date(year, sm, sd)
                    end   = _date(year if em >= sm else year + 1, em, ed)
                    total_days = (end - start).days + 1
                except ValueError:
                    pass

        venues[venue] = {
            "grade":      grade,
            "title":      title,
            "period":     period,
            "day":        day,
            "total_days": total_days,
            "jcd":        jcd,
            "is_joshi":   any(kw in title for kw in JOSHI_KEYWORDS),
            "race_kinds": {},
        }

    # ── 各会場の raceindex を並列取得（直列→並列化でタイムアウト対策）──
    def _fetch_kinds_task(venue_info):
        venue, info = venue_info
        if not info["jcd"]:
            return venue, {}
        kinds = fetch_race_kinds(info["jcd"], hd)
        if kinds:
            print(f"  {venue}: race_kinds={kinds}", flush=True)
        return venue, kinds

    targets = [(v, info) for v, info in venues.items() if info["jcd"]]
    if targets:
        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = {executor.submit(_fetch_kinds_task, t): t[0] for t in targets}
            for future in as_completed(futures):
                try:
                    venue, kinds = future.result()
                    venues[venue]["race_kinds"] = kinds
                except Exception as e:
                    print(f"  [race_kinds] 例外: {e}", flush=True)

    return {
        "date":       date_label,
        "fetched_at": datetime.now().strftime("%H:%M"),
        "venues":     venues,
    }

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="", help="YYYYMMDD (省略=当日)")
    args = ap.parse_args()

    data = fetch(args.date or None)
    if not data or not data.get("venues"):
        print("取得失敗（会場数0）", flush=True)
        sys.exit(1)

    # 日付別ファイルに保存（race_index_YYYYMMDD.json）
    hd = args.date if args.date else datetime.now().strftime("%Y%m%d")
    out_path = SCRIPTS_DIR / f"race_index_{hd}.json"
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK {len(data['venues'])}会場 -> {out_path}", flush=True)
