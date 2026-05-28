"""
scrape_comments.py — 選手コメント自動取得スクリプト
=====================================================
【tenji_from_csv.py と同じ動作】
  CSVから締め切り時刻を読んで、各レースの締め切り20分前から
  ポーリングしてコメントを取得する。

使い方:
  # 今日のCSVを自動検出して全会場取得（メイン）
  python scrape_comments.py

  # CSVフォルダを指定
  python scrape_comments.py --csv-dir "C:/Users/user/Desktop/データ収集/scripts/csv_output"

  # 会場・日付を指定
  python scrape_comments.py --venue tokoname --date 2026-04-29

  # 特定レースだけ
  python scrape_comments.py --venue 常滑 --date 2026-04-29 --race 1

  # ウィンドウ幅を変更（デフォルト: 締め切り20分前、60秒間隔）
  python scrape_comments.py --window-minutes 20 --poll-interval 60

  # 保存済みをINDEX表示
  python scrape_comments.py --venue tokoname --index

保存先: comment_data/comment_{venue}_{date}_R{nn}.json
形式:
  {
    "__fetched_at": "10:15:32",
    "1": {"comment": "欲張ってペラやって..."},
    "2": {"comment": "足は悪くないけど..."},
    ...
  }
"""

import os, sys, json, time, re, glob, argparse, logging, threading
from pathlib import Path
from datetime import datetime, timedelta, date
import requests
from bs4 import BeautifulSoup
import pandas as pd
from gamagori_fetcher import scrape_gamagori as _gamagori_scrape

# ── 設定 ──────────────────────────────────────────────
BASE_DIR    = Path(__file__).parent
COMMENT_DIR = BASE_DIR / "comment_data"
CSV_DIR     = Path(__file__).parent / "csv_output"

RETRY_COUNT    = 3    # リトライ回数
RETRY_WAIT     = 3    # リトライ間隔（秒）
WINDOW_MINUTES = 20   # 締め切り何分前から取得開始するか
POLL_INTERVAL  = 60   # ポーリング間隔（秒）

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ── 会場名変換 ────────────────────────────────────────
NAME_TO_SLUG = {
    "桐生":   "kiryu",    "戸田":   "toda",     "江戸川": "edogawa",
    "平和島": "heiwajima","多摩川": "tamagawa", "浜名湖": "hamanako",
    "蒲郡":   "gamagori", "常滑":   "tokoname", "津":     "tsu",
    "三国":   "mikuni",   "びわこ": "biwako",   "住之江": "suminoe",
    "尼崎":   "amagasaki","鳴門":   "naruto",   "丸亀":   "marugame",
    "児島":   "kojima",   "宮島":   "miyajima", "徳山":   "tokuyama",
    "下関":   "shimonoseki","若松":  "wakamatsu","芦屋":   "ashiya",
    "福岡":   "fukuoka",  "唐津":   "karatsu",  "大村":   "omura",
}

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


# ── 会場別スクレイパー設定 ───────────────────────────
#
# 新しい会場を追加する場合:
#   1. url_fn  : (race_no, date_str) → URL を返す関数を定義
#   2. parse_fn: requests.Response → {"1": {"comment": "..."}, ...} を返す関数を定義
#   3. VENUE_SCRAPERS に1行追加するだけでOK
#
# ─────────────────────────────────────────────────────

def _fetch_html(url: str) -> "requests.Response | None":
    """URLを取得してResponseを返す。失敗時はNone。"""
    for attempt in range(1, RETRY_COUNT + 1):
        try:
            resp = SESSION.get(url, timeout=15)
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            log.warning(f"  取得失敗 (試行{attempt}/{RETRY_COUNT}): {e}")
            if attempt == RETRY_COUNT:
                return None
            time.sleep(RETRY_WAIT)


def _extract_waku(tds: list) -> int | None:
    """tdリストから枠番(1〜6)を抽出する"""
    for td in tds:
        txt = td.get_text(strip=True)
        if re.match(r"^[1-6]$", txt):
            return int(txt)
        img = td.find("img")
        if img and img.get("alt", "").isdigit():
            n = int(img["alt"])
            if 1 <= n <= 6:
                return n
    return None


# ── 常滑パーサー ──────────────────────────────────────
# URL例: https://www.boatrace-tokoname.jp/modules/yosou/group-syussou.php?day=20260429&race=1&kind=1&if=1
# 構造:
#   各選手は2行構成:
#     行1: 枠番セル + 直前バッジ(オレンジ) + コメントセル
#     行2: 枠番セルなし + 前日バッジ(緑) + コメントセル
#   → 枠番は行1にしか存在しないため、current_waku として次の行へ引き継ぐ必要がある
def _url_tokoname(race_no: int, date_str: str) -> str:
    date_nodash = date_str.replace("-", "")
    return (
        f"https://www.boatrace-tokoname.jp/modules/yosou/group-syussou.php"
        f"?day={date_nodash}&race={race_no}&kind=1&if=1"
    )

def _dump_tokoname_html(resp: "requests.Response", race_no: int, date_str: str):
    """
    デバッグ用: 取得したHTMLをファイルに保存し、全trの構造をログ出力する。
    html_dump/ フォルダに保存されるので、実際のクラス名・構造を確認できる。

    使い方:
        python scrape_comments.py --venue tokoname --date 2026-04-29 --race 7 --debug-html
    """
    dump_dir = BASE_DIR / "html_dump"
    dump_dir.mkdir(exist_ok=True)
    date_nodash = date_str.replace("-", "")
    fpath = dump_dir / f"tokoname_{date_nodash}_R{race_no:02d}.html"
    fpath.write_text(resp.text, encoding="utf-8")
    log.info(f"  [DEBUG] HTML保存: {fpath}")

    soup = BeautifulSoup(resp.text, "html.parser")
    log.info(f"  [DEBUG] 全tr数: {len(soup.find_all('tr'))}")
    for i, tr in enumerate(soup.find_all("tr")):
        tds = tr.find_all("td")
        if not tds:
            continue
        classes = [" ".join(td.get("class", [])) for td in tds]
        texts   = [td.get_text(strip=True)[:25] for td in tds]
        log.info(f"  TR[{i:02d}] tds={len(tds)}")
        for j, (cls, txt) in enumerate(zip(classes, texts)):
            log.info(f"           td[{j}] class='{cls}'  text='{txt}'")


def _parse_tokoname(resp: "requests.Response", _debug: bool = False) -> dict:
    """
    常滑HTMLパーサー。
    各選手は2行構成（DOM順）:
      行1: 枠番セルあり + コメントセル  → 前日コメント (comment_prev)
      行2: 枠番セルなし + コメントセル  → 直前コメント (comment)
    row_text でバッジ文字を見ると隣接セルに「前日」が混入するため、
    「1枠につき最初に拾った行=前日、2行目=直前」という順番ベースで判定する。
    """
    soup = BeautifulSoup(resp.text, "html.parser")
    result = {}

    current_waku: int | None = None

    for tr in soup.find_all("tr"):
        tds = tr.find_all("td")
        if not tds:
            continue

        # ── 枠番の更新 ──────────────────────────────────
        # 枠番セルが見つかれば current_waku を更新する（見つからなければ前の値を維持）
        waku = _extract_waku(tds)
        if waku:
            current_waku = waku

        if current_waku is None:
            continue

        # ── コメントセルを取得 ───────────────────────────
        # class属性に "comment" が含まれるtdを探す（複数クラスでも対応）
        comment_td = None
        for td in tds:
            if "comment" in td.get("class", []):
                comment_td = td
                break

        if _debug:
            td_info = [(td.get("class", []), td.get_text(strip=True)[:20]) for td in tds]
            log.debug(f"  waku={current_waku} comment_td={'found' if comment_td else 'None'} tds={td_info}")

        if not comment_td:
            continue
        text = comment_td.get_text(separator="", strip=True)
        if len(text) <= 5:
            continue

        # ── 順番ベースで直前 / 前日を判定 ────────────────
        # row_text でバッジ文字を判定すると混入バグがあるため順番ベースで判定。
        # 実際のDOM順は「前日(comment_prev)→直前(comment)」。
        key = str(current_waku)
        if key not in result:
            result[key] = {}

        if "comment_prev" not in result[key]:
            # この枠の最初のコメント行 → 前日（DOM順: 前日→直前）
            result[key]["comment_prev"] = text
        elif "comment" not in result[key]:
            # この枠の2行目 → 直前
            result[key]["comment"] = text
        # 3行目以降は無視

    return result


# ── 平和島パーサー ────────────────────────────────────
# URL例: https://www.boatrace-livereport.com/heiwajima?race=1
# 構造:
#   p#player-comment-more-{race}-{waku}.means_comment
#   ※ 「続きを読む」で折り畳まれているがHTMLソースには全文が入っている
def _url_heiwajima(race_no: int, date_str: str) -> str:
    return f"https://www.boatrace-livereport.com/heiwajima?race={race_no}"

def _parse_heiwajima(resp: "requests.Response") -> dict:
    soup = BeautifulSoup(resp.text, "html.parser")
    result = {}
    for waku in range(1, 7):
        el = soup.find("p", id=re.compile(rf"player-comment-more-\d+-{waku}$"))
        if not el:
            continue
        text = el.get_text(separator="", strip=True)
        if text:
            result[str(waku)] = {"comment": text}
    # フォールバック: means_comment クラスを順番に取得
    if not result:
        for i, el in enumerate(soup.select("p.means_comment")[:6], start=1):
            text = el.get_text(separator="", strip=True)
            if text:
                result[str(i)] = {"comment": text}
    return result



# ── 蒲郡パーサー ──────────────────────────────────────
# 【確定構造】（b_comment.htm のソース解析で判明）
#
#   b_comment2026052507.htm はナビゲーションボタンだけで、
#   クリック時に下記URLをメインフレームに読み込む:
#
#     /asp/gamagori/kyogi/kyogihtml/comment/comment{YYYYMMDD}{場コード}{レース2桁}.htm
#
#   例: comment/comment202605250701.htm  (1R)
#       comment/comment202605250712.htm  (12R)
#
#   場コード: 07（蒲郡固定）
#   レース番号: 2桁ゼロ埋め
#   各ファイルは1レース分のみ（レースごとに別ファイル）。
#
# ── URL生成 ──────────────────────────────────────────

_GAMAGORI_BASE = "https://www.gamagori-kyotei.com/asp/gamagori/kyogi/kyogihtml"
_GAMAGORI_JYO  = "07"  # 蒲郡の場コード（固定）

def _url_gamagori_comment(race_no: int, date_str: str) -> str:
    """コメント本体ページのURLを返す（確定構造）"""
    date_nodash = date_str.replace("-", "")
    return (
        f"https://www.gamagori-kyotei.com/asp/gamagori/kyogi/kyogihtml/comment/"
        f"comment{date_nodash}{_GAMAGORI_JYO}{race_no:02d}.htm"
    )

def _url_gamagori(race_no: int, date_str: str) -> str:
    # scrape_one_race では gamagori 専用ルートに分岐するため実際には呼ばれない。
    # VENUE_SCRAPERS の url_fn として登録するためのダミー。
    return _url_gamagori_comment(race_no, date_str)


def _parse_gamagori_soup(soup: "BeautifulSoup", race_no: int) -> dict:
    """
    BeautifulSoup オブジェクトから指定レースのコメントを抽出する。

    【確定構造】（DevTools + frame URL調査済み）
      table.ta_kyogi > tbody > tr > td.comment > ul#comIDx > div#commentX_Y > li.today

    b_comment ページには全レース分が入っているため、
    レース番号は ul の id 属性 "comID{race}" で判別する。
      ul#comID1  → 1レース目
      ul#comID2  → 2レース目
      ...
    各 ul の中に 枠1〜6 の div が並ぶ構造。
    """
    result: dict = {}

    # ── パターンA: ul#comID{race_no} でレースを絞り込む ──────────
    race_ul = soup.find("ul", id=f"comID{race_no}")
    if race_ul:
        # ul 直下の div が各艇。div の id は "comment{race}_{waku}" 形式
        for div in race_ul.find_all("div", id=re.compile(rf"comment{race_no}_\d+")):
            m = re.search(rf"comment{race_no}_(\d+)", div.get("id", ""))
            if not m:
                continue
            waku = int(m.group(1))
            if not (1 <= waku <= 6):
                continue
            key = str(waku)
            if key not in result:
                result[key] = {}
            li_today = div.find("li", class_="today")
            if li_today:
                text = li_today.get_text(separator="", strip=True)
                if len(text) > 3:
                    result[key]["comment"] = text
            li_before = div.find("li", class_="before")
            if li_before:
                text = li_before.get_text(separator="", strip=True)
                if len(text) > 3:
                    result[key]["comment_prev"] = text
        if result:
            return result

    # ── パターンB: table.ta_kyogi を行ごとに走査（全レース共通テーブルの場合）──
    # レースブロックの区切りを検出しながら race_no 番目のブロックを取得する
    current_race: int | None = None
    current_waku: int | None = None

    for tr in soup.select("table.ta_kyogi tr"):
        tds = tr.find_all("td")
        if not tds:
            continue

        # レース番号セル検出（例: "1R", "2R" などのテキスト）
        row_text = tr.get_text(strip=True)
        m_race = re.match(r"^(\d{1,2})R", row_text)
        if m_race:
            current_race = int(m_race.group(1))
            current_waku = None
            continue

        if current_race != race_no:
            continue

        waku = _extract_waku(tds)
        if waku:
            current_waku = waku
        if current_waku is None:
            continue

        comment_td = tr.find("td", class_="comment")
        if not comment_td:
            continue

        key = str(current_waku)
        if key not in result:
            result[key] = {}

        li_today = comment_td.find("li", class_="today")
        if li_today:
            text = li_today.get_text(separator="", strip=True)
            if len(text) > 3 and "comment" not in result[key]:
                result[key]["comment"] = text
        li_before = comment_td.find("li", class_="before")
        if li_before:
            text = li_before.get_text(separator="", strip=True)
            if len(text) > 3 and "comment_prev" not in result[key]:
                result[key]["comment_prev"] = text

    return result


def _fetch_gamagori_playwright(race_no: int, date_str: str) -> "dict | None":
    """
    蒲郡コメント取得（JS直接パース版・Playwright完全不要）。

    【確定構造（2026-05-25 JSソース解析済み）】
      1) comment/comment{YYYYMMDD}07{RR}.htm
           → 正規表現で「枠番→登番」マッピングを取得
             funcBeforeComment("XXXX") ... getElementById("comment{waku}_1")
      2) js/comment{YYYYMMDD}07.js（Shift-JIS）
           → funcToDayComment(登番) → 前検コメント文字列
      gamagori_fetcher.py に処理を委譲。
    """
    return _gamagori_scrape(race_no=race_no, date_str=date_str, verbose=True)


def _dump_gamagori_html(resp: "requests.Response", race_no: int, date_str: str):
    """デバッグ用: 取得したHTMLをファイルに保存し、要素構造をログ出力する。"""
    dump_dir = BASE_DIR / "html_dump"
    dump_dir.mkdir(exist_ok=True)
    date_nodash = date_str.replace("-", "")
    fpath = dump_dir / f"gamagori_{date_nodash}_R{race_no:02d}.html"
    fpath.write_text(resp.text, encoding="utf-8", errors="replace")
    log.info(f"  [DEBUG] HTML保存: {fpath}")

    soup = BeautifulSoup(resp.text, "html.parser")
    trs = soup.find_all("tr")
    log.info(f"  [DEBUG] <tr> 総数: {len(trs)}")
    for i, tr in enumerate(trs[:30]):
        tds = tr.find_all("td")
        if not tds:
            continue
        log.info(f"  TR[{i:02d}] tds={len(tds)}")
        for j, td in enumerate(tds):
            cls = " ".join(td.get("class", []))
            txt = td.get_text(strip=True)[:30]
            log.info(f"           td[{j}] class='{cls}'  text='{txt}'")
    for tag_name in ["div", "p", "span", "li"]:
        elems = [el for el in soup.find_all(tag_name) if el.get("class")]
        if elems:
            log.info(f"  [DEBUG] <{tag_name}> with class ({len(elems)}個, 先頭20件):")
            for el in elems[:20]:
                cls = " ".join(el.get("class", []))
                txt = el.get_text(strip=True)[:40]
                log.info(f"    class='{cls}'  text='{txt}'")
    log.info("  [DEBUG] 'comment' / 'コメント' 含む要素:")
    for el in soup.find_all(True):
        cls_str = " ".join(el.get("class", []))
        id_str  = el.get("id", "")
        txt     = el.get_text(strip=True)
        if ("comment" in cls_str.lower() or "comment" in id_str.lower()
                or "コメント" in txt[:10]):
            log.info(f"    <{el.name}> class='{cls_str}' id='{id_str}' "
                     f"text='{txt[:60]}'")


def _parse_gamagori(resp: "requests.Response") -> dict:
    """
    蒲郡コメントページパーサー（requests経由用・フォールバック）。
    race_no が不明な場合は全レース分を返す（キーは "1"〜"6" で上書きされる可能性あり）。
    通常は scrape_one_race → _fetch_gamagori_playwright 経由で呼ばれない。
    """
    soup = BeautifulSoup(resp.text, "html.parser")
    # race_no 不明なので全 li.today を順番に拾う簡易パース
    result: dict = {}
    current_waku: int | None = None
    for tr in soup.select("table.ta_kyogi tr"):
        tds = tr.find_all("td")
        if not tds:
            continue
        waku = _extract_waku(tds)
        if waku:
            current_waku = waku
        if current_waku is None:
            continue
        comment_td = tr.find("td", class_="comment")
        if not comment_td:
            continue
        key = str(current_waku)
        if key not in result:
            result[key] = {}
        li_today = comment_td.find("li", class_="today")
        if li_today:
            text = li_today.get_text(separator="", strip=True)
            if len(text) > 3 and "comment" not in result[key]:
                result[key]["comment"] = text
        li_before = comment_td.find("li", class_="before")
        if li_before:
            text = li_before.get_text(separator="", strip=True)
            if len(text) > 3 and "comment_prev" not in result[key]:
                result[key]["comment_prev"] = text
    if result:
        log.info(f"  [gamagori] {len(result)}艇分のコメント取得")
    return result



# ── 会場別設定テーブル ────────────────────────────────
VENUE_SCRAPERS: dict[str, dict] = {
    "tokoname":  {"url_fn": _url_tokoname,  "parse_fn": _parse_tokoname},
    "heiwajima": {"url_fn": _url_heiwajima, "parse_fn": _parse_heiwajima},
    "gamagori":  {"url_fn": _url_gamagori,  "parse_fn": _parse_gamagori},
    # 今後追加:
    # "toda":    {"url_fn": _url_toda,      "parse_fn": _parse_toda},
}


# ── 1レース取得 ───────────────────────────────────────
def scrape_one_race(venue_slug: str, date_str: str, race_no: int,
                    debug_html: bool = False) -> dict | None:
    scraper = VENUE_SCRAPERS.get(venue_slug)
    if not scraper:
        log.warning(f"  {venue_slug} はスクレイパー未対応のためスキップ")
        return None
    # ── 蒲郡は JS直接パース（gamagori_fetcher.py に委譲）──
    if venue_slug == "gamagori":
        result = _fetch_gamagori_playwright(race_no, date_str)
        if not result:
            return None
        # __fetched_at は gamagori_fetcher 内で付与済みのため二重付与を防ぐ
        if "__fetched_at" not in result:
            result["__fetched_at"] = datetime.now().strftime("%H:%M:%S")
        return result

    url  = scraper["url_fn"](race_no, date_str)
    log.info(f"  URL: {url}")
    resp = _fetch_html(url)
    if not resp:
        return None

    # デバッグモード: HTMLをファイルに保存して構造をログ出力
    if debug_html:
        if venue_slug == "tokoname":
            _dump_tokoname_html(resp, race_no, date_str)
            result = _parse_tokoname(resp, _debug=True)
        else:
            result = scraper["parse_fn"](resp)
    else:
        result = scraper["parse_fn"](resp)

    if not result:
        return None
    result["__fetched_at"] = datetime.now().strftime("%H:%M:%S")
    return result


# ── ファイル保存（差分検知付き）─────────────────────
def save_comment(venue_slug: str, date_str: str, race_no: int, data: dict) -> bool:
    """
    コメントを保存する。既存ファイルがある場合は差分チェックを行い、
    変更があった場合のみ上書きして True を返す。変更なしは False を返す。

    差分の対象: 各枠の comment / comment_prev テキスト
    （__fetched_at などのメタキーは比較しない）
    """
    COMMENT_DIR.mkdir(exist_ok=True)
    date_nodash = date_str.replace("-", "")
    fname = f"comment_{venue_slug}_{date_nodash}_R{race_no:02d}.json"
    fpath = COMMENT_DIR / fname

    def _extract_comments(d: dict) -> dict:
        """比較用に枠番キーのコメントだけ抜き出す"""
        return {
            k: {ck: cv for ck, cv in v.items() if ck in ("comment", "comment_prev")}
            for k, v in d.items()
            if not k.startswith("__") and isinstance(v, dict)
        }

    # 既存ファイルがある場合は差分チェック
    if fpath.exists():
        try:
            with open(fpath, encoding="utf-8") as f:
                existing = json.load(f)
            if _extract_comments(existing) == _extract_comments(data):
                log.info(f"  差分なし: {fname}（上書きスキップ）")
                return False
            else:
                # 変更された枠だけログ出力
                old_c = _extract_comments(existing)
                new_c = _extract_comments(data)
                changed = [
                    w for w in set(old_c) | set(new_c)
                    if old_c.get(w) != new_c.get(w)
                ]
                log.info(f"  差分あり: {fname}  変更枠={sorted(changed)}")
        except Exception:
            pass  # 読み込み失敗時は無条件で上書き

    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    log.info(f"  保存: {fname}")
    return True


def already_fetched(venue_slug: str, date_str: str, race_no: int) -> bool:
    """
    JSONファイルが存在し、かつ少なくとも1艇分のコメント（comment または comment_prev）
    が入っている場合のみ True を返す。
    コメントなしで保存されたファイルは「未取得」として再取得対象にする。
    """
    date_nodash = date_str.replace("-", "")
    fname = f"comment_{venue_slug}_{date_nodash}_R{race_no:02d}.json"
    fpath = COMMENT_DIR / fname
    if not fpath.exists():
        return False
    try:
        with open(fpath, encoding="utf-8") as f:
            data = json.load(f)
        # __fetched_at 以外のキーで comment or comment_prev が1つでもあればOK
        for key, val in data.items():
            if key == "__fetched_at":
                continue
            if isinstance(val, dict) and (val.get("comment") or val.get("comment_prev")):
                return True
        return False  # ファイルはあるがコメントが空 → 再取得する
    except Exception:
        return False  # 読み込み失敗も再取得対象


# ── 時刻ユーティリティ ────────────────────────────────
def parse_hhmm(s: str, date_str: str = None) -> datetime:
    """
    'HH:MM' → datetime。
    date_str（YYYY-MM-DD）が指定された場合はその日付を使う。
    省略時は今日（後方互換）。
    """
    h, m = map(int, s.strip().split(":"))
    if date_str:
        base = datetime.strptime(date_str, "%Y-%m-%d")
    else:
        base = datetime.now()
    return base.replace(hour=h, minute=m, second=0, microsecond=0)

def seconds_until(target: datetime) -> float:
    return (target - datetime.now()).total_seconds()


# ── 1レース分のポーリング（tenji_scheduler_v2.poll_raceと同じ構造）──
def poll_race(venue_slug: str, date_str: str, race_no: int,
              deadline: datetime, window_minutes: int, poll_interval: int) -> bool:
    """
    締め切り window_minutes 分前から deadline まで
    poll_interval 秒ごとにコメント取得を試みる。成功したら True を返す。
    """
    start_time = deadline - timedelta(minutes=window_minutes)

    if datetime.now() < start_time:
        wait_sec = (start_time - datetime.now()).total_seconds()
        log.info(f"  [{race_no}R] 取得ウィンドウ開始まで {wait_sec:.0f}秒待機 "
                 f"({start_time.strftime('%H:%M')}〜{deadline.strftime('%H:%M')})")
        time.sleep(wait_sec)

    attempt = 0
    while datetime.now() <= deadline:
        attempt += 1
        log.info(f"  [{race_no}R] 取得試行 #{attempt} "
                 f"(締切 {deadline.strftime('%H:%M')} まで {seconds_until(deadline):.0f}秒)")

        data = scrape_one_race(venue_slug, date_str, race_no)
        if data:
            count = len([k for k in data if not k.startswith("__")])
            log.info(f"  [{race_no}R] ✓ {count}艇分のコメント取得成功")
            save_comment(venue_slug, date_str, race_no, data)
            return True

        remain = seconds_until(deadline)
        if remain <= 0:
            log.warning(f"  [{race_no}R] 締め切り時刻を過ぎました（取得失敗）")
            break
        sleep_sec = min(poll_interval, max(10, remain - 5))
        log.info(f"  [{race_no}R] データ未公開。{sleep_sec:.0f}秒後に再試行...")
        time.sleep(sleep_sec)

    return False


# ── 即時一括取得（--now モード）────────────────────────
def run_now(venue_slug: str, date_str: str, deadlines: dict,
            window_minutes: int = WINDOW_MINUTES,
            poll_interval: int = POLL_INTERVAL,
            force: bool = False):
    """
    締め切り時刻を待たず、今すぐ全レースのコメントを一括取得する（朝イチ用）。

    動作:
      1. 全レースを即時取得（取得できなかったレースは results に記録）
      2. 取得できなかったレース → 通常の締め切りスケジュールで再取得
         （= run_scheduler に引き継ぐ）

    こうすることで:
      ・朝イチ公開済みのコメントをすぐ取得してpushできる
      ・締め切り前に追加公開されたコメントも漏れなく取得できる
    """
    if not deadlines:
        log.error(f"[{venue_slug}] 締め切り時刻が空です")
        return

    race_nums = sorted(deadlines.keys())

    log.info(f"\n{'='*60}")
    log.info(f"  [--now] 即時一括取得  場: {venue_slug}  日付: {date_str}")
    log.info(f"  対象: {race_nums}")
    log.info(f"{'='*60}")

    now_results: dict[int, str] = {}  # race_no → "成功" / "失敗"

    # ── フェーズ1: 全レース即時取得 ──────────────────────
    for race in race_nums:
        if not force and already_fetched(venue_slug, date_str, race):
            log.info(f"  [{race}R] スキップ（取得済み）")
            now_results[race] = "スキップ"
            continue

        log.info(f"  [{race}R] 即時取得中... (締切: {deadlines[race]})")
        data = scrape_one_race(venue_slug, date_str, race)
        if data:
            count = len([k for k in data if not k.startswith("__")])
            log.info(f"  [{race}R] ✓ {count}艇分取得成功")
            save_comment(venue_slug, date_str, race, data)
            now_results[race] = "✓ 成功"
        else:
            log.warning(f"  [{race}R] ✗ 取得失敗（コメント未公開 or 締切前）")
            now_results[race] = "✗ 失敗"
        time.sleep(1)  # サーバー負荷軽減

    # 即時取得サマリー
    ok  = [r for r, s in now_results.items() if "成功" in s]
    ng  = [r for r, s in now_results.items() if "失敗" in s]
    skp = [r for r, s in now_results.items() if "スキップ" in s]
    log.info(f"\n  [--now] 即時取得サマリー")
    log.info(f"    成功: {ok}  失敗（未公開）: {ng}  スキップ: {skp}")

    # ── フェーズ2: 全レース（成功・失敗問わず）を締め切り20分前に再チェック ───
    # 目的: 朝一取得後にコメントが更新された場合に差分を上書き保存する
    # 締め切り済みのレースは除外（もう変わらない）
    now_dt = datetime.now()
    recheck_deadlines = {
        r: deadlines[r]
        for r in race_nums
        if parse_hhmm(deadlines[r], date_str) > now_dt
    }
    already_past = [r for r in race_nums if r not in recheck_deadlines]
    if already_past:
        log.info(f"  [{venue_slug}] 締切済みのため再チェックスキップ: {already_past}R")

    if recheck_deadlines:
        log.info(f"\n  [--now] 全レース {sorted(recheck_deadlines.keys())} を"
                 f"締め切り{window_minutes}分前に再チェックします（差分更新）")
        run_scheduler(venue_slug, date_str, recheck_deadlines,
                      window_minutes, poll_interval, force=True)  # force=True で差分上書き
    else:
        log.info(f"  [--now] 再チェック対象なし（全レース締切済み）。完了")


# ── 1会場分のスケジューラ（tenji_scheduler_v2.run_schedulerと同じ構造）──
def run_scheduler(venue_slug: str, date_str: str,
                  deadlines: dict,
                  window_minutes: int = WINDOW_MINUTES,
                  poll_interval: int = POLL_INTERVAL,
                  force: bool = False):
    """deadlines に従って各レースのコメントを自動取得する。"""
    if not deadlines:
        log.error(f"[{venue_slug}] 締め切り時刻が空です")
        return

    race_nums = sorted(deadlines.keys())
    now = datetime.now()

    log.info(f"\n{'='*60}")
    log.info(f"  コメント自動取得  場: {venue_slug}  日付: {date_str}")
    log.info(f"  ウィンドウ: 締め切り{window_minutes}分前〜  ポーリング: {poll_interval}秒")
    log.info(f"{'='*60}")
    for r in race_nums:
        dl_dt = parse_hhmm(deadlines[r], date_str)
        start = dl_dt - timedelta(minutes=window_minutes)
        log.info(f"    {r:>2}R  締切={deadlines[r]}  取得開始={start.strftime('%H:%M')}")

    results = {}

    # ── 起動時点で締め切り済み・未取得のレースを先にまとめて即時取得 ──────
    missed_races = [
        r for r in race_nums
        if not already_fetched(venue_slug, date_str, r)
        and parse_hhmm(deadlines[r], date_str) < now - timedelta(minutes=1)
    ]
    if missed_races:
        log.info(f"\n  ── 締切済み未取得レースを即時取得: {missed_races} ──")
        for race in missed_races:
            log.info(f"\n  [{race}R] 締切済み未取得 → 即時取得試みます ({deadlines[race]} 締切)")
            data = scrape_one_race(venue_slug, date_str, race)
            if data:
                count = len([k for k in data if not k.startswith("__")])
                log.info(f"  [{race}R] ✓ {count}艇分のコメント取得成功")
                save_comment(venue_slug, date_str, race, data)
                results[race] = "✓ 成功（遡及）"
            else:
                log.warning(f"  [{race}R] ✗ 取得失敗（コメント未公開の可能性）")
                results[race] = "✗ 失敗（遡及）"
        log.info(f"\n  ── 遡及取得完了。以降は通常スケジュールで実行 ──\n")

    for race in race_nums:
        # 取得済みならスキップ（遡及取得済みも含む）
        if not force and already_fetched(venue_slug, date_str, race):
            log.info(f"\n  [{race}R] スキップ（取得済み）")
            results[race] = results.get(race, "スキップ")
            continue

        deadline = parse_hhmm(deadlines[race], date_str)

        # 締め切り済みは遡及取得済み or 失敗済みなのでスキップ
        if deadline < now - timedelta(minutes=1):
            if race not in results:
                results[race] = "締切済みスキップ"
            continue

        # 取得ウィンドウ開始前なら待機
        start_time = deadline - timedelta(minutes=window_minutes)
        wait_sec   = (start_time - datetime.now()).total_seconds()
        if wait_sec > 0:
            log.info(f"\n  [{race}R] {wait_sec/60:.1f}分後に取得開始 "
                     f"({start_time.strftime('%H:%M')} — 締切 {deadlines[race]})")
            while (s := seconds_until(start_time)) > 30:
                log.info(f"    待機中... 開始まで {s/60:.1f}分")
                time.sleep(30)
            remaining = seconds_until(start_time)
            if remaining > 0:
                time.sleep(remaining)

        ok = poll_race(venue_slug, date_str, race, deadline,
                       window_minutes, poll_interval)
        results[race] = "✓ 成功" if ok else "✗ 失敗"

    # サマリー
    log.info(f"\n{'='*60}")
    log.info(f"  [{venue_slug}] 取得結果サマリー")
    for r, status in results.items():
        log.info(f"    {r:>2}R  {status}  (締切: {deadlines[r]})")
    ok_count = sum(1 for s in results.values() if "成功" in s)
    log.info(f"  合計: {ok_count}/{len(results)} レース取得成功")


# ── CSVから会場・締め切り時刻を読み込む（tenji_from_csv.pyと同じ）──
def load_venues_from_csv(csv_dir: Path, date_str: str) -> list:
    results = []
    seen    = set()

    for csv_path in sorted(csv_dir.glob("*.csv")):
        try:
            try:
                df = pd.read_csv(csv_path, encoding="utf-8-sig", dtype=str)
            except UnicodeDecodeError:
                df = pd.read_csv(csv_path, encoding="shift_jis", dtype=str)
        except Exception as e:
            log.warning(f"  CSV読込失敗 {csv_path.name}: {e}")
            continue

        if not {"会場", "日付", "レース", "締切時刻"}.issubset(set(df.columns)):
            continue

        df["日付_norm"] = df["日付"].astype(str).str.replace("/", "-").str.strip()
        df_day = df[df["日付_norm"] == date_str]
        if df_day.empty:
            continue

        venue_name = df_day["会場"].iloc[0].strip()
        slug = NAME_TO_SLUG.get(venue_name)
        if not slug:
            log.warning(f"  未対応の会場名: {venue_name}")
            continue

        # スクレイパー未対応会場はスキップ
        if slug not in VENUE_SCRAPERS:
            log.info(f"  {venue_name}（{slug}）: スクレイパー未対応のためスキップ")
            continue

        key = (venue_name, date_str)
        if key in seen:
            continue
        seen.add(key)

        deadlines = {}
        for _, row in df_day.drop_duplicates("レース").sort_values("レース").iterrows():
            try:
                race_no = int(str(row["レース"]).strip())
                dl_time = str(row["締切時刻"]).strip()
                if re.match(r"\d{1,2}:\d{2}", dl_time):
                    deadlines[race_no] = dl_time
            except Exception:
                continue

        if deadlines:
            results.append({"name": venue_name, "slug": slug, "deadlines": deadlines})
            log.info(f"  ✓ {venue_name}: {len(deadlines)}R分"
                     f" ({deadlines[min(deadlines)]}〜{deadlines[max(deadlines)]})")

    return results


# ── 会場ごとのスレッド（tenji_from_csv.pyのvenue_workerと同じ）──
def venue_worker(venue_info: dict, date_str: str,
                 window_minutes: int, poll_interval: int,
                 results: dict, lock: threading.Lock, force: bool,
                 use_now: bool = False):
    name = venue_info["name"]
    slug = venue_info["slug"]
    try:
        runner = run_now if use_now else run_scheduler
        runner(slug, date_str, venue_info["deadlines"],
               window_minutes, poll_interval, force)
        results[name] = "✓ 完了"
    except Exception as e:
        with lock:
            log.error(f"[{name}] エラー: {e}")
        results[name] = f"✗ エラー: {e}"


# ── INDEX表示 ─────────────────────────────────────────
def print_index(venue_slug: str, date_str: str, race_nos: list[int]):
    date_nodash = date_str.replace("-", "")
    print(f"\n{'═'*40}")
    print(f"  {venue_slug}  {date_str}")
    print(f"{'═'*40}")
    found_any = False
    for rno in race_nos:
        fpath = COMMENT_DIR / f"comment_{venue_slug}_{date_nodash}_R{rno:02d}.json"
        if not fpath.exists():
            continue
        found_any = True
        with open(fpath, encoding="utf-8") as f:
            data = json.load(f)
        print(f"\n  [R{rno:02d}]  {data.get('__fetched_at', '')}")
        for waku in range(1, 7):
            entry = data.get(str(waku))
            if entry:
                comment = entry.get("comment", "")
                print(f"    {waku}: {comment[:40]}{'…' if len(comment) > 40 else ''}")
            else:
                print(f"    {waku}: （コメントなし）")
    if not found_any:
        print("  ※ 保存済みコメントが見つかりません")
    print()


# ── CLI ──────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="選手コメント自動取得（締め切り時刻ベース）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--csv-dir", default=str(CSV_DIR), help="CSVフォルダのパス")
    parser.add_argument("--venue",   help="会場名またはスラッグ。省略時はCSVから全会場")
    parser.add_argument("--date",    help="日付 YYYY-MM-DD (省略時: 今日)")
    parser.add_argument("--race",    type=int, help="レース番号 (--venue 指定時のみ有効)")
    parser.add_argument("--window-minutes", type=int, default=WINDOW_MINUTES,
                        help=f"締め切り何分前から取得開始するか（デフォルト: {WINDOW_MINUTES}）")
    parser.add_argument("--poll-interval",  type=int, default=POLL_INTERVAL,
                        help=f"ポーリング間隔(秒)（デフォルト: {POLL_INTERVAL}）")
    parser.add_argument("--force",      action="store_true", help="取得済みでも上書き")
    parser.add_argument("--now",        action="store_true",
                        help="締め切り時刻を待たず今すぐ全レース一括取得（朝イチ用）。"
                             "取得できなかったレースは通常スケジュールで再取得される")
    parser.add_argument("--index",      action="store_true", help="保存済みコメントをINDEX表示（取得はしない）")
    parser.add_argument("--debug-html", action="store_true",
                        help="HTMLをhtml_dump/に保存して要素構造をログ出力（tokoname・gamagori対応、--venue --race と併用）")
    args = parser.parse_args()

    date_str = args.date or date.today().isoformat()
    csv_dir  = Path(args.csv_dir)

    # デバッグモード: 即時1レース取得してHTML構造を出力
    if args.debug_html:
        if not args.venue or not args.race:
            print("--debug-html には --venue と --race も指定してください")
            print("例: python scrape_comments.py --venue tokoname --race 7 --debug-html")
            return
        slug = NAME_TO_SLUG.get(args.venue) or args.venue
        log.setLevel(logging.DEBUG)
        print(f"\n[DEBUG] {slug} {args.race}R のHTML構造を確認します...")
        data = scrape_one_race(slug, date_str, args.race, debug_html=True)
        if data:
            print(f"\n取得結果:")
            for k, v in data.items():
                if not k.startswith("__"):
                    print(f"  {k}枠: {v}")
        else:
            print("  コメント取得できませんでした（HTMLはhtml_dump/を確認してください）")
        return

    # INDEX表示モード
    if args.index:
        slug = NAME_TO_SLUG.get(args.venue, args.venue) if args.venue else None
        if not slug:
            print("--index には --venue も指定してください")
            return
        print_index(slug, date_str, [args.race] if args.race else list(range(1, 13)))
        return

    print("=" * 65)
    print(f"  コメント自動取得（CSV連携版）")
    print(f"  日付      : {date_str}")
    print(f"  CSVフォルダ: {csv_dir}")
    if args.now:
        print(f"  モード    : 即時一括取得（--now）→ 未取得分は締切{args.window_minutes}分前に再取得")
    else:
        print(f"  ウィンドウ: 締め切り{args.window_minutes}分前〜締め切り時刻")
    print(f"  ポーリング: {args.poll_interval}秒ごと")
    print("=" * 65)

    if args.venue:
        # 特定会場を指定
        slug = NAME_TO_SLUG.get(args.venue) or args.venue
        if slug not in VENUE_SCRAPERS:
            log.error(f"{slug} はスクレイパー未対応です")
            return
        venues = load_venues_from_csv(csv_dir, date_str)
        venue_info = next((v for v in venues if v["slug"] == slug), None)
        if not venue_info:
            log.error(f"{args.venue} の締め切り時刻がCSVから取得できませんでした")
            return
        deadlines = {args.race: venue_info["deadlines"][args.race]} \
                    if args.race else venue_info["deadlines"]
        runner = run_now if args.now else run_scheduler
        runner(slug, date_str, deadlines,
               args.window_minutes, args.poll_interval, args.force)

    else:
        # CSVから全会場を並列実行（tenji_from_csv.pyと同じ）
        print(f"\n【Step1】{date_str} のCSVを読み込み中...")
        venues = []
        attempt = 0
        while not venues:
            attempt += 1
            venues = load_venues_from_csv(csv_dir, date_str)
            if venues:
                break
            log.warning(f"  対応会場が見つかりません（試行{attempt}回目）"
                        f" — 60秒後に再試行... (Ctrl+C で終了)")
            try:
                time.sleep(60)
            except KeyboardInterrupt:
                print("\n\n[終了] 中断されました")
                return

        print(f"\n対象: {len(venues)}会場")
        print(f"\n【Step2】{len(venues)}会場を並列実行開始\n")

        results = {}
        lock    = threading.Lock()
        threads = [
            threading.Thread(
                target=venue_worker,
                args=(v, date_str, args.window_minutes, args.poll_interval,
                      results, lock, args.force),
                kwargs={"use_now": args.now},
                name=v["name"], daemon=True,
            )
            for v in venues
        ]
        for t in threads:
            t.start()
            time.sleep(0.3)
        try:
            for t in threads:
                t.join()
        except KeyboardInterrupt:
            print("\n\n[終了] 中断されました")
            return

        print(f"\n{'='*65}")
        print("  完了サマリー")
        print("=" * 65)
        for name, status in results.items():
            print(f"  {name}: {status}")


if __name__ == "__main__":
    main()
