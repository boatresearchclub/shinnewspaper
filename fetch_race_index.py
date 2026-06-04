"""
fetch_race_index.py  —  ボートレース公式サイトから本日の開催情報を取得
========================================================================
【出力】
  このスクリプトと同じフォルダに race_index_YYYYMMDD.json を保存する。

【使い方】
  python fetch_race_index.py
  python fetch_race_index.py --date 20260510

【依存】
  pip install requests beautifulsoup4

【変更履歴】
  - race_kinds取得を並列化（ThreadPoolExecutor）→ タイムアウト対策
  - グレード検出をテーブル全体スキャン方式に変更（rowspan対応）
  - GRADE_CLASS_RE を [a-z] サフィックス対応に修正（is-G3b 等を正しく検出）
  - 中止・中止順延・取消 ステータスを取得する cancel_status フィールドを追加
    "cancel_status": null         → 通常開催（中止情報なし）
    "cancel_status": "中止"       → 当日全レース中止
    "cancel_status": "中止順延"   → 中止順延（翌日以降に順延）
    "cancel_status": "取消"       → 開催自体が取消
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

# ── 中止ステータス検出 ────────────────────────────────────────────────────
# 公式サイトの進行状況セルに含まれるテキスト/クラスで中止を判定する。
# クラスベース検出（is-cancel / is-stop 等）とテキストベース検出を併用し
# どちらか一方でもヒットすれば cancel_status を設定する。

# テキストマッチ: 優先度順に並べる（より具体的なものを先に）
CANCEL_TEXT_MAP = [
    ("中止順延", "中止順延"),
    ("中止",     "中止"),
    ("取消",     "取消"),
    ("CANCEL",   "中止"),   # 英語表記も一応カバー
]

# CSSクラスマッチ（公式は is-cancel / is-cancelDelay 等が多い）
CANCEL_CLASS_RE = re.compile(
    r"\bis-(cancel|stop|closed|delay)[a-zA-Z]*\b",
    re.IGNORECASE,
)

def _detect_cancel_status(cell_text: str, cell_classes: list[str]) -> str | None:
    """
    進行状況セルのテキストとCSSクラスから中止ステータスを返す。
    中止なし → None
    """
    # 1) テキストベース（最優先・確実）
    for keyword, status in CANCEL_TEXT_MAP:
        if keyword in cell_text:
            return status

    # 2) CSSクラスベース（クラス名だけで判断できる場合）
    for cls in cell_classes:
        if CANCEL_CLASS_RE.search(cls):
            # クラス名から種別を推定
            lc = cls.lower()
            if "delay" in lc or "jun" in lc:
                return "中止順延"
            return "中止"

    return None


# ── 女子戦判定 ───────────────────────────────────────────────────────────
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
    中止会場はスキップ（呼び出し側で cancel_status をチェック）。
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

    date_label = f"{hd[:4]}-{hd[4:6]}-{hd[6:]}"
    grade_map = build_grade_map(soup)

    venues = {}
    for i, row in enumerate(soup.select("table tbody tr")):
        cells = row.find_all("td")
        if not cells:
            continue

        # ── 会場名 ──────────────────────────────────────────────────────
        venue = ""
        for img in cells[0].find_all("img"):
            alt = img.get("alt","").strip()
            if alt:
                venue = normalize_venue(alt)
                break
        if not venue:
            continue

        grade = grade_map.get(i, "一般")

        # ── 中止ステータス検出 ──────────────────────────────────────────
        # 進行状況セル（通常は cells[1]）を主要チェック対象とするが、
        # 念のため全セルを走査してヒットしたものを採用する。
        cancel_status = None
        for td in cells:
            td_text   = td.get_text(separator=" ", strip=True)
            td_classes = td.get("class", [])
            cs = _detect_cancel_status(td_text, td_classes)
            if cs:
                cancel_status = cs
                break

        # ── タイトル・jcd ────────────────────────────────────────────────
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

        # ── 開催期間・日目 ───────────────────────────────────────────────
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

        # ── 総日数 ───────────────────────────────────────────────────────
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
            "grade":         grade,
            "title":         title,
            "period":        period,
            "day":           day,
            "total_days":    total_days,
            "jcd":           jcd,
            "is_joshi":      any(kw in title for kw in JOSHI_KEYWORDS),
            "cancel_status": cancel_status,   # ★ 新フィールド
            "race_kinds":    {},
        }

        if cancel_status:
            print(f"  {venue}: 【{cancel_status}】検出", flush=True)

    # ── 各会場の raceindex を並列取得 ────────────────────────────────────
    # 中止会場は race_kinds 取得をスキップする
    def _fetch_kinds_task(venue_info):
        venue, info = venue_info
        if not info["jcd"]:
            return venue, {}
        # 中止・取消の場合はスキップ（どうせデータがない）
        if info["cancel_status"] in ("中止", "取消"):
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

    hd = args.date if args.date else datetime.now().strftime("%Y%m%d")
    out_path = SCRIPTS_DIR / f"race_index_{hd}.json"
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # サマリー表示
    cancel_venues = [v for v, info in data["venues"].items() if info["cancel_status"]]
    normal_venues = [v for v, info in data["venues"].items() if not info["cancel_status"]]
    print(f"OK {len(data['venues'])}会場 -> {out_path}", flush=True)
    if cancel_venues:
        details = ", ".join(f"{v}({data['venues'][v]['cancel_status']})" for v in cancel_venues)
        print(f"  ※中止/順延: {details}", flush=True)
    print(f"  通常開催: {len(normal_venues)}会場 / 中止等: {len(cancel_venues)}会場", flush=True)
