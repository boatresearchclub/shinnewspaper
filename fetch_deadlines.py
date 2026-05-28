"""
fetch_deadlines.py  —  boatrace.jp 公式から締め切り時刻を取得
==============================================================
boatrace.jp の出走表ページ (racelist) を Playwright でレンダリングし、
全レースの締め切り時刻を取得して JSON で返す。

場コード対応:
  01=桐生 02=戸田 03=江戸川 04=平和島 05=多摩川 06=浜名湖
  07=蒲郡 08=常滑 09=津 10=三国 11=びわこ 12=住之江
  13=尼崎 14=鳴門 15=丸亀 16=児島 17=宮島 18=徳山
  19=下関 20=若松 21=芦屋 22=福岡 23=唐津 24=大村
"""

import re, time, json
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

VENUE_JCD = {
    "桐生":"01","戸田":"02","江戸川":"03","平和島":"04","多摩川":"05",
    "浜名湖":"06","蒲郡":"07","常滑":"08","津":"09","三国":"10",
    "びわこ":"11","住之江":"12","尼崎":"13","鳴門":"14","丸亀":"15",
    "児島":"16","宮島":"17","徳山":"18","下関":"19","若松":"20",
    "芦屋":"21","福岡":"22","唐津":"23","大村":"24",
    # スラッグ -> jcd
    "kiryu":"01","toda":"02","edogawa":"03","heiwajima":"04","tamagawa":"05",
    "hamanako":"06","gamagori":"07","tokoname":"08","tsu":"09","mikuni":"10",
    "biwako":"11","suminoe":"12","amagasaki":"13","naruto":"14","marugame":"15",
    "kojima":"16","miyajima":"17","tokuyama":"18","shimonoseki":"19","wakamatsu":"20",
    "ashiya":"21","fukuoka":"22","karatsu":"23","omura":"24",
}

# 締切時刻として有効な時間帯（早朝・深夜はノイズ扱い）
_VALID_HOUR_MIN = 9
_VALID_HOUR_MAX = 20


def _parse_deadlines_from_html(html: str) -> dict:
    """
    boatrace.jp racelist ページの HTML から締切時刻を抽出する。

    試みる順序:
      1. is-action1 クラス（公式の締切ステータスセル）付近の時刻
      2. table1 tbody の各行: Rno と時刻の対応
      3. 全テキストから時刻を連番抽出（最終フォールバック）

    Returns: {1: "10:00", 2: "10:30", ...}  ※キーは int
    """
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    time_pat = re.compile(r"\b(\d{1,2}):([0-5]\d)\b")

    def _valid_time(h_str, m_str) -> bool:
        return _VALID_HOUR_MIN <= int(h_str) <= _VALID_HOUR_MAX

    deadlines: dict = {}

    # ── 方法1: .table1 の行からレース番号と時刻を同時に読む ──────────────────
    # 公式HTML構造:
    #   <table class="is-table1"> または class に "table1" を含む
    #     <tbody>
    #       <tr>  ← 1行 = 1レース
    #         <td class="is-lineNo"> 1 </td>   ← レース番号
    #         ...
    #         <td> 10:00 </td>                 ← 締切時刻
    for table in soup.find_all("table", class_=re.compile(r"table1", re.I)):
        for tr in table.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) < 3:
                continue

            # レース番号セルを探す（最初の数字1〜12）
            rno = None
            for td in tds[:3]:
                txt = td.get_text(strip=True)
                if txt.isdigit() and 1 <= int(txt) <= 12:
                    rno = int(txt)
                    break
            if rno is None:
                continue

            # 行内で最初に見つかる有効な時刻を締切時刻とする
            for td in tds:
                m = time_pat.search(td.get_text(strip=True))
                if m and _valid_time(m.group(1), m.group(2)):
                    deadlines[rno] = f"{int(m.group(1)):02d}:{m.group(2)}"
                    break

    if len(deadlines) >= 6:
        return deadlines

    # ── 方法2: レースナビ / タブリスト（.is-tab1 など）から読む ──────────────
    # 一部の場では <ul class="is-tab1"> <li> に "1R 10:00" 形式で入っている
    for nav in soup.find_all(["ul", "ol", "div"],
                              class_=re.compile(r"tab|race.?nav|nav.?race|raceList", re.I)):
        items = nav.find_all("li")
        for item in items:
            text = item.get_text(strip=True)
            m_rno  = re.search(r"(\d{1,2})R", text)
            m_time = time_pat.search(text)
            if m_rno and m_time and _valid_time(m_time.group(1), m_time.group(2)):
                rno = int(m_rno.group(1))
                if rno not in deadlines:
                    deadlines[rno] = f"{int(m_time.group(1)):02d}:{m_time.group(2)}"

    if len(deadlines) >= 6:
        return deadlines

    # ── 方法3: 全テキストから連番12個を抽出（最終フォールバック）─────────────
    # ページ内の「有効時間帯の HH:MM」を出現順に取得し、重複排除後 R1〜R12 に割り当てる
    all_matches = time_pat.findall(html)
    seen: list = []
    for h, mn in all_matches:
        if _valid_time(h, mn):
            t = f"{int(h):02d}:{mn}"
            if t not in seen:
                seen.append(t)

    # 12個以上取れた場合は最初の12個を使用
    for i, t in enumerate(seen[:12], 1):
        if i not in deadlines:
            deadlines[i] = t

    return deadlines


def fetch_deadlines_official(venue, date_str):
    """
    公式 boatrace.jp の出走表から締め切り時刻を取得。

    Parameters
    ----------
    venue    : 会場名（例: "常滑"）またはスラッグ（例: "tokoname"）
    date_str : "YYYY-MM-DD" または "YYYYMMDD"

    Returns
    -------
    {1: "10:00", 2: "10:30", ...}  ※キーは int, 時刻は "HH:MM"
    取得失敗時は {} を返す（例外は送出しない）
    """
    jcd = VENUE_JCD.get(venue)
    if not jcd:
        raise ValueError(f"未対応の場コード/スラッグ: {venue}")

    hd = date_str.replace("-", "")

    # racelist は rno=1 で全レース分の情報が得られる（公式仕様）
    url = (
        f"https://www.boatrace.jp/owpc/pc/race/racelist"
        f"?rno=1&jcd={jcd}&hd={hd}"
    )

    deadlines: dict = {}

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                locale="ja-JP",
            )
            page = ctx.new_page()
            try:
                page.goto(url, wait_until="networkidle", timeout=30000)
                # JS レンダリング待ち
                time.sleep(2)
            except PWTimeout:
                # タイムアウトしてもHTMLは取得できている場合がある
                pass

            html = page.content()
            browser.close()

        deadlines = _parse_deadlines_from_html(html)

    except Exception as e:
        print(f"  [fetch_deadlines] ⚠ 取得エラー ({venue}): {e}", flush=True)
        return {}

    # 6レース未満しか取れなかった場合は信頼性なしとして空を返す
    if len(deadlines) < 6:
        print(
            f"  [fetch_deadlines] ⚠ 締切時刻が{len(deadlines)}件しか取れませんでした"
            f"（{venue} / {date_str}） → スキップ",
            flush=True,
        )
        return {}

    # キーを int に統一して返す
    return {int(k): v for k, v in deadlines.items()}


def fetch_deadlines_manual(schedule_dict):
    """
    手動で締め切り時刻を渡す場合のラッパー。
    schedule_dict: {1: "10:15", 2: "10:45", ...}
    """
    return schedule_dict


def fetch_deadlines_from_boaters(venue_slug, date_str):
    """
    boaters-boatrace.com のレース一覧ページから締め切り時刻を取得。
    """
    url = f"https://boaters-boatrace.com/race/{venue_slug}/{date_str}"
    html = ""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                locale="ja-JP",
            )
            page = ctx.new_page()
            try:
                page.goto(url, wait_until="networkidle", timeout=30000)
                time.sleep(3)
            except PWTimeout:
                pass
            html = page.content()
            browser.close()
    except Exception as e:
        print(f"  [fetch_deadlines] ⚠ boaters取得エラー: {e}", flush=True)
        return {}

    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    deadlines = {}
    pat = re.compile(r"(\d{1,2}):([0-5]\d)")

    for tag in soup.find_all(string=re.compile(r"[1-9]R|1[012]R")):
        m_race = re.search(r"(\d{1,2})R", tag)
        if not m_race:
            continue
        race_no = int(m_race.group(1))
        parent = tag.parent
        for _ in range(5):
            if parent is None:
                break
            text = parent.get_text()
            m_time = pat.search(text)
            if m_time:
                h = int(m_time.group(1))
                if _VALID_HOUR_MIN <= h <= _VALID_HOUR_MAX:
                    deadlines[race_no] = f"{h:02d}:{m_time.group(2)}"
                    break
            parent = parent.parent

    return deadlines


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--venue", required=True)
    ap.add_argument("--date", required=True)
    ap.add_argument("--source", default="official",
                    choices=["official", "boaters"],
                    help="取得元: official=boatrace.jp, boaters=boaters-boatrace.com")
    args = ap.parse_args()

    if args.source == "boaters":
        dl = fetch_deadlines_from_boaters(args.venue, args.date)
    else:
        dl = fetch_deadlines_official(args.venue, args.date)

    print(json.dumps(dl, ensure_ascii=False, indent=2))
