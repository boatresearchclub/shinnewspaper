"""
fetch_tenji.py  —  boaters-boatrace.com テン展示データ 自動取得ツール
======================================================================
使い方:
  python fetch_tenji.py --venue heiwajima --date 2026-04-25 --race 1
  python fetch_tenji.py --venue heiwajima --date 2026-04-25 --all
  python fetch_tenji.py --venue heiwajima --date 2026-04-25 --race 3 --poll 60
  python fetch_tenji.py --venue 平和島 --date 2026-04-25 --races 1,3,5

初回セットアップ:
  pip install playwright beautifulsoup4 pandas
  playwright install chromium

【v2からの変更点】
  - BrowserSession クラスによるブラウザ使い回し（毎回起動→終了を廃止）
  - wait_until="networkidle" → "domcontentloaded" に変更（__NEXT_DATA__はDOMに埋め込み済み）
  - fetch_html() が BrowserSession を受け取れるようになりシングルトン利用可能
  - fetch_one() / fetch_motor_only() がセッションを引き回す構造に変更
"""

import argparse
import json
import re
import threading
import time
from datetime import datetime
from pathlib import Path

# ─────────────────────────────────────────────────────────────
# 場名 → URLスラッグ
# ─────────────────────────────────────────────────────────────
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


def build_url(venue_slug: str, date: str, race: int) -> str:
    return (
        f"https://boaters-boatrace.com/race/{venue_slug}/{date}/{race}R"
        f"/last-minute?last-minute-content=original-tenji"
    )


def build_wind_url(venue_slug: str, date: str, race: int) -> str:
    """風情報ページURL（クエリパラメータなし）"""
    return f"https://boaters-boatrace.com/race/{venue_slug}/{date}/{race}R/last-minute"


def build_motor_url(venue_slug: str, date: str, race: int) -> str:
    """モーター情報ページURL"""
    return f"https://boaters-boatrace.com/race/{venue_slug}/{date}/{race}R/motor"


# ─────────────────────────────────────────────────────────────
# ブラウザセッション管理（1会場1インスタンスで使い回す）
# ─────────────────────────────────────────────────────────────
class BrowserSession:
    """
    Playwright ブラウザを起動したまま保持し、ページだけ都度開閉するクラス。
    with 文で使うか、start()/stop() を明示的に呼ぶ。

    使い方:
        with BrowserSession() as sess:
            html = fetch_html(url, session=sess)

        # または
        sess = BrowserSession()
        sess.start()
        html = fetch_html(url, session=sess)
        sess.stop()
    """

    def __init__(self):
        self._pw      = None
        self._browser = None
        self._contexts: list = []  # ★ 開いたコンテキストを追跡してリーク防止

    def start(self):
        from playwright.sync_api import sync_playwright
        self._pw      = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=True)

    def stop(self):
        # ★ 追跡中のコンテキストをすべて閉じてからブラウザを閉じる
        for ctx in self._contexts:
            try:
                ctx.close()
            except Exception:
                pass
        self._contexts.clear()
        try:
            if self._browser:
                self._browser.close()
        except Exception:
            pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        self._browser = None
        self._pw      = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *_):
        self.stop()

    def new_page(self):
        """新しいページ（タブ）とそのコンテキストを返す。ブラウザは維持したまま。"""
        ctx = self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
            viewport={"width": 1280, "height": 900},
        )
        self._contexts.append(ctx)  # ★ 追跡リストに登録
        return ctx.new_page()


# ─────────────────────────────────────────────────────────────
# Playwright でHTMLフェッチ
# ─────────────────────────────────────────────────────────────
def fetch_html(url: str, timeout: int = 30000,
               wait_for: str = None, poll_count: int = 20,
               session: BrowserSession = None) -> str:
    """
    Playwright でページを取得。

    【変更点】
    - session を渡すとブラウザを使い回す（推奨）。省略時は都度起動（後方互換）。
    - wait_until を networkidle → domcontentloaded に変更。
      __NEXT_DATA__ は DOM に静的埋め込みなので networkidle を待つ必要がなく、
      広告・アナリティクスの通信完了を待たずに済む分、大幅に高速化。

    Args:
        url        : 取得するURL
        timeout    : Playwright側のタイムアウト(ms)
        wait_for   : このキーワードがHTMLに現れるまでポーリング（例: "CrawledRaceBeforeInfo"）
        poll_count : ポーリング最大回数（1回=1秒）
        session    : BrowserSession インスタンス（Noneなら都度起動）
    """
    from playwright.sync_api import TimeoutError as PWTimeout

    def _do_fetch(page) -> str:
        try:
            # ★ networkidle → domcontentloaded に変更（広告通信待ちを回避）
            page.goto(url, wait_until="domcontentloaded", timeout=timeout)

            if wait_for:
                for i in range(poll_count):
                    html = page.content()
                    if wait_for in html:
                        print(f"  [DEBUG] '{wait_for}' 検出 ({i+1}秒後)")
                        return html
                    time.sleep(1)
                html = page.content()
                _debug_typenames(html, wait_for)
                return html
            else:
                for _ in range(poll_count):
                    html = page.content()
                    if ("CrawledRaceOriginalTenji" in html
                            or "CrawledRaceBeforeInfo" in html
                            or "RaceMotor" in html):
                        return html
                    time.sleep(1)
                return page.content()

        except PWTimeout:
            print(f"  [WARN] タイムアウト: {url}")
            return page.content()

    if session is not None:
        # ブラウザ使い回し：ページとコンテキストを開いて閉じる
        page = session.new_page()
        try:
            return _do_fetch(page)
        finally:
            ctx = page.context
            page.close()
            # ★ コンテキストも閉じてリーク防止
            try:
                ctx.close()
                if ctx in session._contexts:
                    session._contexts.remove(ctx)
            except Exception:
                pass
    else:
        # 後方互換：都度ブラウザ起動（session未指定時）
        from playwright.sync_api import sync_playwright
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
                return _do_fetch(page)
            finally:
                browser.close()


def _debug_typenames(html: str, missing_key: str):
    """
    __NEXT_DATA__ に含まれる __typename 一覧を出力。
    wait_for のキーワードが見つからなかった場合のデバッグ用。
    """
    import json as _json
    try:
        from bs4 import BeautifulSoup as _BS
        soup = _BS(html, "html.parser")
        nd = soup.find("script", {"id": "__NEXT_DATA__"})
        if nd and nd.string:
            apollo = (
                _json.loads(nd.string)
                .get("props", {})
                .get("pageProps", {})
                .get("initialApolloState", {})
            )
            typenames = sorted({
                v.get("__typename")
                for v in apollo.values()
                if isinstance(v, dict) and v.get("__typename")
            })
            print(f"  [DEBUG] '{missing_key}' が見つかりません。"
                  f" apollo __typename 一覧: {typenames}")
        else:
            print(f"  [DEBUG] '{missing_key}' が見つかりません。"
                  f" __NEXT_DATA__ タグ自体が存在しないか空です。")
    except Exception as e:
        print(f"  [DEBUG] デバッグ情報取得失敗: {e}")


# ─────────────────────────────────────────────────────────────
# __NEXT_DATA__ 抽出共通ヘルパー（メモリ最適化）
# ─────────────────────────────────────────────────────────────
# parse_tenji / parse_wind / parse_start_info / parse_motor は
# いずれも同じ手順（HTML → BeautifulSoup → __NEXT_DATA__タグ → json.loads）
# で apollo state を取り出している。
#
# fetch_one() は風情報ページの同一HTML文字列(wind_html)を
# parse_wind() と parse_start_info() の両方に渡すため、何も対策しないと
# 同じ（数百KB〜MB級になりうる）HTMLを2回 BeautifulSoup + json.loads する
# ことになる。
#
# 対策: 直前に処理した1件分の (html文字列のid, apollo辞書) だけを
# キャッシュする。
#
# 重要（スレッド安全性）: main_loop.py は会場ごとに別スレッドで
# fetch_one() 等を並行実行する設計のため、単純なモジュールグローバル変数で
# id(html) をキーにキャッシュすると、CPythonのid()がメモリアドレス由来で
# 再利用されうる点と相まって、別スレッドが書き込んだ結果を誤って受け取る
# 可能性が理論上ゼロではない。
# これを完全に避けるため、threading.local() を使い「スレッドごとに
# 独立したキャッシュ領域」を持たせる。各スレッドは自分が書いた値しか
# 読めないため、競合状態は構造的に発生しない。
_apollo_cache_local = threading.local()


def _extract_apollo(html: str) -> dict:
    """
    HTML文字列から __NEXT_DATA__ の initialApolloState を取り出す。
    解析できなければ空dictを返す（既存の各parse_*関数と同じ失敗時挙動）。

    スレッドごとに直前1件分だけキャッシュするため、同一スレッド内で
    同じHTML文字列オブジェクトが連続して渡された場合のみ再パースを
    スキップする（fetch_one内でwind_htmlをparse_wind→parse_start_infoの
    順に渡すケースが該当）。他スレッドの結果が混ざることはない。
    """
    cached_id     = getattr(_apollo_cache_local, "html_id", None)
    cached_apollo = getattr(_apollo_cache_local, "apollo", None)

    if html is not None and id(html) == cached_id:
        return cached_apollo

    from bs4 import BeautifulSoup

    apollo: dict = {}
    soup = BeautifulSoup(html, "html.parser")
    nd = soup.find("script", {"id": "__NEXT_DATA__"})
    if nd and nd.string:
        try:
            data = json.loads(nd.string)
            apollo = data.get("props", {}).get("pageProps", {}).get("initialApolloState", {}) or {}
        except Exception:
            apollo = {}

    # このスレッド用の直前1件分だけ更新（古いものは自動的に上書き）
    _apollo_cache_local.html_id = id(html)
    _apollo_cache_local.apollo  = apollo
    return apollo


# ─────────────────────────────────────────────────────────────
# HTMLパース — テン展示テーブル抽出（3段階フォールバック）
# ─────────────────────────────────────────────────────────────
def parse_tenji(html: str, venue: str, date: str, race: int) -> list:
    """
    __NEXT_DATA__ の Apollo State から直接テン展示データを抽出。
    データ構造:
      CrawledRaceOriginalTenji → isshuTime(1周) / mawariashiTime(回り足) / chokusenTime(直線)
      CrawledRaceBeforeRacer  → tenjiTime(展示) / tenjiRank(展示順位) / tilt(チルト)
      CrawledRaceRacer        → name(選手名) / rank(級別)
    """
    apollo = _extract_apollo(html)
    if not apollo:
        return []

    tenji_by_boat  = {}
    before_by_boat = {}
    racer_by_boat  = {}

    for v in apollo.values():
        if not isinstance(v, dict):
            continue
        typename = v.get("__typename", "")
        bn_raw = v.get("boatNumber")
        if bn_raw is None:
            continue
        # ★ 型を int に統一（APIが str/int どちらで返しても同一キーに）
        try:
            bn = int(bn_raw)
        except (ValueError, TypeError):
            continue
        if typename == "CrawledRaceOriginalTenji":
            tenji_by_boat[bn] = v
        elif typename == "CrawledRaceBeforeRacer":
            before_by_boat[bn] = v
        elif typename == "CrawledRaceRacer":
            racer_by_boat[bn] = v

    if not tenji_by_boat:
        return []

    # ★ デバッグ: before_by_boat が空なら原因を出力
    if not before_by_boat:
        typenames = sorted({
            v.get("__typename") for v in apollo.values()
            if isinstance(v, dict) and v.get("__typename")
        })
        print(f"  [DEBUG] CrawledRaceBeforeRacer が0件。apollo __typename 一覧: {typenames}")
        # tenjiTime の代替フィールドを CrawledRaceOriginalTenji から探す
        for k, v in apollo.items():
            if isinstance(v, dict) and v.get("__typename") == "CrawledRaceOriginalTenji":
                print(f"  [DEBUG] CrawledRaceOriginalTenji の全キー: {list(v.keys())}")
                break

    rows = []
    for bn in sorted(tenji_by_boat.keys()):
        t  = tenji_by_boat.get(bn, {})
        br = before_by_boat.get(bn, {})
        rr = racer_by_boat.get(bn, {})

        # 進入コース: CrawledRaceBeforeRacer の course / startCourse を取得
        course_raw = (
            br.get("course")
            or br.get("startCourse")
            or br.get("courseNumber")
            or br.get("startCourseNumber")
        )
        course = int(course_raw) if course_raw is not None else None

        # 枠なり判定: コース番が枠番と一致すれば枠なり(True)、異なれば進入変更(False)
        is_normal_course = (course == bn) if course is not None else None

        rows.append({
            "venue":            venue,
            "date":             date,
            "race":             race,
            "frame":            bn,  # 常に int
            "racer":            rr.get("name", ""),
            "grade":            rr.get("rank", ""),
            "lap1":             t.get("isshuTime"),
            "mawari":           t.get("mawariashiTime"),
            "chokusen":         t.get("chokusenTime"),
            "tenji":            br.get("tenjiTime"),
            "tenji_rank":       br.get("tenjiRank"),
            "tilt":             br.get("tilt"),
            "course":           course,           # HTMLが参照するキー
            "is_normal_course": is_normal_course, # HTMLが参照するキー
            "parts_exchange":   br.get("partsExchange"),
            "weight":           br.get("weight"),
            "weight_adjust":    br.get("weightAdjust"),
            "fetched_at":       datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
    return rows


# ─────────────────────────────────────────────────────────────
# HTMLパース — 風・天候情報抽出
# ─────────────────────────────────────────────────────────────

_WIND_DIR = {
    1:  "北",    2:  "北北東", 3:  "北東",  4:  "東北東",
    5:  "東",    6:  "東南東", 7:  "南東",  8:  "南南東",
    9:  "南",    10: "南南西", 11: "南西",  12: "西南西",
    13: "西",    14: "西北西", 15: "北西",  16: "北北西",
}


def parse_wind(html: str) -> dict:
    """
    __NEXT_DATA__ の CrawledRaceBeforeInfo から風・天候情報を抽出。
    """
    apollo = _extract_apollo(html)
    if not apollo:
        return {}

    for v in apollo.values():
        if not isinstance(v, dict):
            continue
        if v.get("__typename") != "CrawledRaceBeforeInfo":
            continue

        wind_dir_num = v.get("windDirection")
        return {
            "weather":             v.get("weather"),
            "weather_degree":      v.get("weatherDegree"),
            "water_degree":        v.get("waterDegree"),
            "wind_speed":          v.get("windSpeed"),
            "wind_direction":      wind_dir_num,
            "wind_direction_text": _WIND_DIR.get(wind_dir_num, "不明") if wind_dir_num else None,
            "wave_height":         v.get("waveHeight"),
            "shukai_length":       v.get("shukaiLength"),
        }

    return {}


# ─────────────────────────────────────────────────────────────
# HTMLパース — 進入（スタート隊形）情報抽出
# ─────────────────────────────────────────────────────────────
def parse_start_info(html: str) -> dict:
    """
    __NEXT_DATA__ の Apollo State から進入・STタイム情報を抽出。

    対象キー（boaters-boatrace.com の __NEXT_DATA__ 構造）:
      CrawledRaceBeforeInfo  → startCourseOrders / startTimings
      CrawledRaceBeforeRacer → startTiming (ST) / course (進入コース)

    戻り値:
      {
        "has_change": bool,          # 進入変更ありかどうか (枠番≠コース番で判定)
        "courses": {                 # 枠番 → 進入コース番
            1: 1, 2: 3, 3: 2, ...
        },
        "start_timings": {          # 枠番 → STタイム (float or None)
            1: 0.12, 2: 0.12, ...
        },
        "start_order": [            # コース順に並べた枠番リスト [コース1の枠, コース2の枠, ...]
            1, 3, 2, 4, 5, 6
        ],
      }
    """
    apollo = _extract_apollo(html)
    if not apollo:
        return {}

    # ── 方法1: CrawledRaceBeforeRacer から course / startTiming を収集 ──
    courses: dict[int, int]       = {}  # 枠番 → 進入コース
    start_timings: dict[int, float | None] = {}  # 枠番 → ST

    for v in apollo.values():
        if not isinstance(v, dict):
            continue
        if v.get("__typename") != "CrawledRaceBeforeRacer":
            continue
        bn = v.get("boatNumber")
        if bn is None:
            continue
        bn = int(bn)

        # 進入コース: "startSinnyu" が正式フィールド名。フォールバックも残す
        course = (
            v.get("startSinnyu")
            or v.get("course")
            or v.get("startCourse")
            or v.get("courseNumber")
            or v.get("startCourseNumber")
        )
        if course is not None:
            courses[bn] = int(course)

        # STタイム: "startTenjiTime" が正式フィールド名。フォールバックも残す
        st = (
            v.get("startTenjiTime")
            or v.get("startTiming")
            or v.get("st")
            or v.get("startTime")
        )
        try:
            start_timings[bn] = float(st) if st is not None else None
        except (ValueError, TypeError):
            start_timings[bn] = None

    # ── 方法2: CrawledRaceBeforeInfo の startCourseOrders / startTimings を試みる ──
    if not courses:
        for v in apollo.values():
            if not isinstance(v, dict):
                continue
            if v.get("__typename") != "CrawledRaceBeforeInfo":
                continue

            # startCourseOrders: [{"boatNumber": 1, "course": 3}, ...]
            orders = v.get("startCourseOrders") or v.get("courseOrders") or []
            if isinstance(orders, list):
                for item in orders:
                    if isinstance(item, dict):
                        bn = item.get("boatNumber")
                        c  = item.get("course") or item.get("courseNumber")
                        if bn is not None and c is not None:
                            courses[int(bn)] = int(c)

            # startTimings: [{"boatNumber": 1, "startTiming": 0.12}, ...]
            timings = v.get("startTimings") or v.get("startInfos") or []
            if isinstance(timings, list):
                for item in timings:
                    if isinstance(item, dict):
                        bn = item.get("boatNumber")
                        st = item.get("startTiming") or item.get("st") or item.get("startTime")
                        if bn is not None:
                            try:
                                start_timings[int(bn)] = float(st) if st is not None else None
                            except (ValueError, TypeError):
                                start_timings[int(bn)] = None
            if courses:
                break

    # ── 方法3: CrawledRaceBeforeInfo の courses / startTimings がネスト参照の場合 ──
    # Apollo Client は {__ref: "SomeKey:123"} でネストを表現することがある
    def _resolve(item):
        if isinstance(item, dict) and "__ref" in item:
            return apollo.get(item["__ref"], item)
        return item

    if not courses:
        for v in apollo.values():
            if not isinstance(v, dict):
                continue
            if v.get("__typename") != "CrawledRaceBeforeInfo":
                continue
            for list_key in ("startCourseOrders", "courseOrders", "startInfos", "startInfo"):
                raw = v.get(list_key, [])
                if not isinstance(raw, list):
                    continue
                resolved = [_resolve(x) for x in raw]
                for item in resolved:
                    if not isinstance(item, dict):
                        continue
                    bn = item.get("boatNumber") or item.get("waku")
                    c  = item.get("course") or item.get("courseNumber") or item.get("startCourse")
                    st = item.get("startTiming") or item.get("st") or item.get("startTime")
                    if bn is not None and c is not None:
                        courses[int(bn)] = int(c)
                    if bn is not None and st is not None:
                        try:
                            start_timings[int(bn)] = float(st)
                        except (ValueError, TypeError):
                            pass
                if courses:
                    break
            if courses:
                break

    if not courses:
        # デバッグ: どんな __typename が存在するか出力（キー調査用）
        typenames = sorted({
            v.get("__typename")
            for v in apollo.values()
            if isinstance(v, dict) and v.get("__typename")
        })
        print(f"  [DEBUG] 進入情報取得失敗。apollo __typename 一覧: {typenames}")
        return {}

    # 進入変更判定: 枠番とコース番が1つでも異なれば変更あり
    has_change = any(courses.get(bn) != bn for bn in courses)

    # コース順に枠番を並べる
    start_order = [
        bn for _, bn in sorted((c, bn) for bn, c in courses.items())
    ]

    return {
        "has_change":    has_change,
        "courses":       courses,
        "start_timings": start_timings,
        "start_order":   start_order,
    }


def _fmt_start_info(start_info: dict) -> str:
    """進入情報を1行テキストで返す"""
    if not start_info:
        return "  進入情報: 取得できず"

    courses       = start_info.get("courses", {})
    start_timings = start_info.get("start_timings", {})
    has_change    = start_info.get("has_change", False)

    label = "【進入変更あり】" if has_change else "【進入変更なし】"
    lines = [f"  {label}"]

    # コース順に表示
    sorted_courses = sorted(courses.items(), key=lambda x: x[1])  # コース番でソート
    header = f"  {'コース':>4}  {'枠':>2}  {'ST':>6}"
    lines.append(header)
    lines.append("  " + "─" * 18)
    for bn, course in sorted_courses:
        st = start_timings.get(bn)
        st_str = f".{int(round(st * 100)):02d}" if st is not None else "  ---"
        lines.append(f"  {course:>4}  {bn:>2}  {st_str:>6}")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# HTMLパース — モーター情報抽出
# ─────────────────────────────────────────────────────────────
def parse_motor(html: str, debug: bool = False) -> list:
    """
    __NEXT_DATA__ の Apollo State からモーター情報を抽出。
    """
    apollo = _extract_apollo(html)
    if not apollo:
        return []

    if debug:
        seen_types: dict[str, set] = {}
        for v in apollo.values():
            if not isinstance(v, dict):
                continue
            tn = v.get("__typename", "")
            if tn:
                seen_types.setdefault(tn, set()).update(v.keys())
        print("  [DEBUG] ===== apollo __typename 一覧 =====")
        for tn, keys in sorted(seen_types.items()):
            print(f"  [DEBUG] __typename={tn!r}  keys={sorted(keys)}")

        for v in apollo.values():
            if isinstance(v, dict) and v.get("__typename") == "CrawledRace":
                agg = v.get("motorAggregations", [])
                rec = v.get("motorRecentResults", [])
                print(f"  [DEBUG] motorAggregations({len(agg)}件) 先頭={agg[:2]}")
                print(f"  [DEBUG] motorRecentResults({len(rec)}件) 先頭={rec[:4]}")
                break

    agg_list: list[dict] = []
    recent_list: list[dict] = []

    for v in apollo.values():
        if not isinstance(v, dict):
            continue
        if v.get("__typename") != "CrawledRace":
            continue
        agg = v.get("motorAggregations")
        rec = v.get("motorRecentResults")
        if isinstance(agg, list) and agg:
            agg_list = agg
        if isinstance(rec, list) and rec:
            recent_list = rec
        if agg_list and recent_list:
            break

    if not agg_list:
        if debug:
            print("  [DEBUG] motorAggregations が空です")
        return []

    racer_by_boat: dict[int, dict] = {}
    for v in apollo.values():
        if not isinstance(v, dict):
            continue
        if v.get("__typename") != "CrawledRaceRacer":
            continue
        bn = v.get("boatNumber")
        if bn is not None:
            racer_by_boat[bn] = {
                "racer":    v.get("name", ""),
                "grade":    v.get("rank", ""),
                "motor_no": v.get("motorRegN"),
            }

    def resolve_ref(item: dict) -> dict:
        ref = item.get("__ref")
        if ref:
            return apollo.get(ref, item)
        return item

    agg_list    = [resolve_ref(x) for x in agg_list    if isinstance(x, dict)]
    recent_list = [resolve_ref(x) for x in recent_list if isinstance(x, dict)]

    stats_by_waku: dict[int, dict] = {}
    for agg in agg_list:
        if not isinstance(agg, dict):
            continue
        waku = agg.get("waku")
        if waku is None:
            continue
        waku = int(waku)
        mno_raw = agg.get("motorN")
        mno = int(mno_raw) if mno_raw is not None else None
        r2 = agg.get("result2renAvg")
        r3 = agg.get("result3renAvg")
        def _to_pct(v):
            if v is None:
                return None
            fv = float(v)
            return round(fv, 1) if fv > 1.0 else round(fv * 100, 1)
        motor_rank_raw = agg.get("motorRank") or agg.get("rank") or agg.get("motorOrder")
        stats_by_waku[waku] = {
            "motor_no":    mno,
            "motor_rate2": _to_pct(r2),
            "motor_rate3": _to_pct(r3),
            "motor_rank":  int(motor_rank_raw) if motor_rank_raw is not None else None,
        }

    def _norm(s: str) -> str:
        return s.replace(" ", "").replace("\u3000", "").replace("　", "")

    recent_by_motor: dict[int, list] = {}
    for rec in recent_list:
        if not isinstance(rec, dict):
            continue
        mno_raw = rec.get("motorN")
        if mno_raw is None:
            continue
        mno = int(mno_raw)
        order = rec.get("nRaceFromHere", 999)
        name  = rec.get("racerName", "")
        if name:
            recent_by_motor.setdefault(mno, []).append((int(order), name.strip()))

    current_racer_by_motor: dict[int, str] = {}
    for waku, st in stats_by_waku.items():
        mno = st.get("motor_no")
        rr  = racer_by_boat.get(waku, {})
        name = rr.get("racer", "")
        if mno is not None and name:
            current_racer_by_motor[mno] = name
    for mno, racers in recent_by_motor.items():
        if mno not in current_racer_by_motor:
            sorted_r = sorted(racers, key=lambda x: x[0])
            if sorted_r:
                current_racer_by_motor[mno] = sorted_r[0][1]

    rows = []
    for waku in sorted(stats_by_waku.keys()):
        st = stats_by_waku[waku]
        rr = racer_by_boat.get(waku, {})
        mno = st["motor_no"]
        current_name = current_racer_by_motor.get(mno, rr.get("racer", ""))

        prev_user = None
        if mno is not None and mno in recent_by_motor:
            norm_current = _norm(current_name)
            sorted_racers = sorted(recent_by_motor[mno], key=lambda x: x[0])
            passed_current = False
            for _, name in sorted_racers:
                norm_name = _norm(name)
                if norm_name == norm_current:
                    passed_current = True
                elif passed_current:
                    prev_user = name
                    break
            if not passed_current and prev_user is None and norm_current:
                for _, name in sorted_racers:
                    if _norm(name) != norm_current:
                        prev_user = name
                        break

        racer_name = rr.get("racer", "")
        if not racer_name and mno is not None and mno in recent_by_motor:
            sorted_recent = sorted(recent_by_motor[mno], key=lambda x: x[0])
            if sorted_recent:
                racer_name = sorted_recent[0][1]

        rows.append({
            "frame":       waku,
            "racer":       racer_name,
            "grade":       rr.get("grade", ""),
            "motor_no":    mno,
            "motor_rate2": st["motor_rate2"],
            "motor_rate3": st["motor_rate3"],
            "motor_rank":  st["motor_rank"],
            "prev_user":   prev_user,
        })

    return rows


def _parse_table(soup, venue, date, race) -> list:
    rows = []
    for table in soup.find_all("table"):
        for tr in table.find_all("tr"):
            tds = tr.find_all(["td", "th"])
            texts = [td.get_text(strip=True) for td in tds]
            if not texts:
                continue
            if not (texts[0].isdigit() and 1 <= int(texts[0]) <= 6):
                continue
            hl = {}
            for i, td in enumerate(tds):
                bg = td.get("style", "") + " ".join(td.get("class", []))
                if re.search(r"red|#[Ee][Ff]|#[Ff][Aa]|salmon|orange", bg, re.I):
                    hl[i] = "red"
                elif re.search(r"yellow|#[Ff]{2}[C-Fc-f]|#[Ff][Ee]", bg, re.I):
                    hl[i] = "yellow"
            nums = []
            name = ""
            grade = ""
            frame = int(texts[0])
            for t in texts[1:]:
                t = t.replace("\xa0", "")
                if re.match(r"^(B1|B2|A1|A2|SG|G1|G2|G3)$", t):
                    grade = t
                elif re.match(r"^\d{4,5}$", t):
                    pass
                elif re.match(r"^[3-9]\d\.\d{2}$", t):
                    nums.append(("lap1", float(t)))
                elif re.match(r"^5\.\d{2}$", t):
                    nums.append(("mawari", float(t)))
                elif re.match(r"^7\.\d{2}$", t):
                    nums.append(("chokusen", float(t)))
                elif re.match(r"^6\.\d{2}$", t):
                    nums.append(("six", float(t)))
                elif t and not t.isdigit() and len(t) >= 2:
                    if not name:
                        name = t
            field_map = {}
            six_vals = [v for k, v in nums if k == "six"]
            for k, v in nums:
                if k in ("lap1", "mawari", "chokusen"):
                    field_map.setdefault(k, v)
            if six_vals:
                if "mawari" not in field_map:
                    field_map["mawari"] = six_vals[0]
                    if len(six_vals) >= 2:
                        field_map["tenji"] = six_vals[1]
                else:
                    field_map["tenji"] = six_vals[0]
            rows.append({
                "venue":    venue, "date": date, "race": race,
                "frame":    frame,
                "racer":    name,
                "grade":    grade,
                "lap1":     field_map.get("lap1"),
                "mawari":   field_map.get("mawari"),
                "chokusen": field_map.get("chokusen"),
                "tenji":    field_map.get("tenji"),
                "highlight": list(hl.values()),
                "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })
    return rows


def _parse_next_data(soup, venue, date, race) -> list:
    tag = soup.find("script", {"id": "__NEXT_DATA__"})
    if not tag:
        return []
    try:
        data = json.loads(tag.string or "{}")
    except Exception:
        return []
    return _dig_json(data, venue, date, race)


def _dig_json(obj, venue, date, race) -> list:
    rows = []
    if isinstance(obj, dict):
        for key, val in obj.items():
            if isinstance(val, list) and len(val) == 6:
                candidate = _try_parse_boat_list(val, venue, date, race)
                if candidate:
                    return candidate
            rows = _dig_json(val, venue, date, race)
            if rows:
                return rows
    elif isinstance(obj, list):
        for item in obj:
            rows = _dig_json(item, venue, date, race)
            if rows:
                return rows
    return rows


def _try_parse_boat_list(lst, venue, date, race) -> list:
    rows = []
    for item in lst:
        if not isinstance(item, dict):
            return []
        tenji_val = (
            item.get("exhibitionTime") or item.get("tenji") or
            item.get("tenjiTime") or item.get("originalTenji")
        )
        frame_val = (
            item.get("frame") or item.get("waku") or
            item.get("course") or item.get("no")
        )
        if frame_val is None or tenji_val is None:
            return []
        rows.append({
            "venue":    venue, "date": date, "race": race,
            "frame":    _toint(frame_val),
            "racer":    item.get("name") or item.get("playerName") or "",
            "grade":    item.get("class") or item.get("grade") or "",
            "lap1":     _tofloat(item.get("lap1") or item.get("ichisuTime")),
            "mawari":   _tofloat(item.get("mawari") or item.get("turnTime")),
            "chokusen": _tofloat(item.get("chokusen") or item.get("straightTime")),
            "tenji":    _tofloat(tenji_val),
            "highlight": [],
            "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
    return rows if len(rows) == 6 else []


def _parse_regex(text: str, venue, date, race) -> list:
    rows = []
    for line in text.splitlines():
        line = line.strip()
        m = re.match(
            r"([1-6])\s+(.+?)\s+(B[12]|A[12]|SG|G[123])"
            r"\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)",
            line,
        )
        if m:
            rows.append({
                "venue": venue, "date": date, "race": race,
                "frame": int(m.group(1)),
                "racer": m.group(2).strip(),
                "grade": m.group(3),
                "lap1":  _tofloat(m.group(4)),
                "mawari":   _tofloat(m.group(5)),
                "chokusen": _tofloat(m.group(6)),
                "tenji":    _tofloat(m.group(7)),
                "highlight": [],
                "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })
    return rows


def _tofloat(v):
    try:
        return float(v) if v is not None else None
    except (ValueError, TypeError):
        return None


def _toint(v):
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


# ─────────────────────────────────────────────────────────────
# 保存
# ─────────────────────────────────────────────────────────────
def save_csv(rows: list, out_dir: Path, venue: str, date: str, race: int):
    import pandas as pd
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = out_dir / f"tenji_{venue}_{date.replace('-', '')}.csv"
    df_new = pd.DataFrame(rows)
    if fname.exists():
        df_old = pd.read_csv(fname)
        df_old = df_old[~(
            (df_old["date"] == date) &
            (df_old["race"] == race) &
            (df_old["frame"].isin(df_new["frame"].tolist()))
        )]
        # ★ FutureWarning修正: 両DataFrameの列を揃えてからconcat
        all_cols = df_old.columns.union(df_new.columns)
        df_old = df_old.reindex(columns=all_cols)
        df_new = df_new.reindex(columns=all_cols)
        df_out = pd.concat([df_old, df_new], ignore_index=True)
        # 1レース分の保存ごとに呼ばれる関数のため、24会場×12レース規模だと
        # 1日に数百回呼ばれうる。df_old/df_newは結合後は不要になるので、
        # 関数を抜けるまで保持せず明示的に解放してピークメモリを抑える
        # （出力結果には影響しない）。
        del df_old, df_new
    else:
        df_out = df_new
    df_out.sort_values(["date", "race", "frame"], inplace=True)
    df_out.to_csv(fname, index=False, encoding="utf-8-sig")
    print(f"  [CSV保存] {fname}")
    return fname


def save_json(rows: list, out_dir: Path, venue: str, date: str, race: int):
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = out_dir / f"tenji_{venue}_{date.replace('-','')}_R{race:02d}.json"
    with open(fname, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    print(f"  [JSON保存] {fname}")
    return fname


# ─────────────────────────────────────────────────────────────
# モーター情報のみ取得
# ─────────────────────────────────────────────────────────────
def fetch_motor_only(venue_slug: str, date: str, race: int, out_dir,
                     motor_debug: bool = False,
                     session: BrowserSession = None) -> list:
    """
    モーター情報だけを取得してJSONに保存する。
    session を渡すとブラウザを使い回す（推奨）。
    """
    print(f"\n▶ [motor-only] {race}R  venue={venue_slug}  date={date}")

    motor_url = build_motor_url(venue_slug, date, race)
    print(f"  モーター情報取得: {motor_url}")
    motor_html = fetch_html(motor_url, wait_for="MotorAggregation",
                            poll_count=20, session=session)
    motor_rows = parse_motor(motor_html, debug=motor_debug)

    if not motor_rows:
        print(f"  ⚠ {race}R モーター情報取得できず → スキップ")
        return []

    existing_path = (
        Path(out_dir) / f"tenji_{venue_slug}_{date.replace('-','')}_R{race:02d}.json"
        if out_dir else None
    )
    if existing_path and existing_path.exists():
        with open(existing_path, encoding="utf-8") as f:
            existing_rows = json.load(f)
        print(f"  既存JSON読み込み: {existing_path.name} ({len(existing_rows)}艇)")
    else:
        existing_rows = [
            {
                "venue": venue_slug, "date": date, "race": race,
                "frame": m["frame"],
                "racer": m.get("racer", ""),
                "grade": m.get("grade", ""),
                "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            for m in motor_rows
        ]
        print(f"  既存JSONなし → モーター情報のみで新規作成")

    motor_by_frame = {m["frame"]: m for m in motor_rows if m.get("frame") is not None}
    motor_by_racer = _build_motor_by_racer(motor_rows)
    for r in existing_rows:
        m = motor_by_frame.get(r.get("frame")) or _lookup_motor(r.get("racer", ""), motor_by_racer)
        if m is None:
            m = {}
        r.update({
            "motor_no":    m.get("motor_no"),
            "motor_rate2": m.get("motor_rate2"),
            "motor_rate3": m.get("motor_rate3"),
            "motor_rank":  m.get("motor_rank"),
            "prev_user":   m.get("prev_user"),
        })

    print(f"  {'枠':>2}  {'レーサー':<10}  {'M番':>3}  {'M2連':>5}  {'M3連':>5}  {'順位':>4}  前節使用者")
    print("  " + "─" * 58)
    for r in existing_rows:
        m2   = f"{r['motor_rate2']:.1f}" if r.get("motor_rate2") is not None else " --- "
        m3   = f"{r['motor_rate3']:.1f}" if r.get("motor_rate3") is not None else " --- "
        mno  = str(r["motor_no"]) if r.get("motor_no") is not None else "---"
        mrnk = f"{r['motor_rank']}位" if r.get("motor_rank") is not None else " ---"
        prev = r.get("prev_user") or "---"
        print(f"  {r['frame']:>2}  {r['racer']:<10}  {mno:>3}  {m2:>5}  {m3:>5}  {mrnk:>4}  {prev}")

    if out_dir:
        save_json(existing_rows, Path(out_dir), venue_slug, date, race)
    print(f"  ✓ {race}R モーター情報保存完了")
    return existing_rows


# ─────────────────────────────────────────────────────────────
# メイン処理
# ─────────────────────────────────────────────────────────────
def fetch_one(venue_slug: str, date: str, race: int, out_dir,
              motor_debug: bool = False,
              session: BrowserSession = None):
    """
    1レース分の展示タイム・モーター・風情報を取得して保存。
    session を渡すとブラウザを使い回す（推奨）。
    """
    print(f"\n▶ {race}R  venue={venue_slug}  date={date}")

    # ── モーター情報取得 ──
    motor_url = build_motor_url(venue_slug, date, race)
    print(f"  モーター情報取得: {motor_url}")
    motor_html = fetch_html(motor_url, wait_for="MotorAggregation",
                            poll_count=20, session=session)
    motor_rows = parse_motor(motor_html, debug=motor_debug)

    if not motor_rows and out_dir:
        existing_json = Path(out_dir) / f"tenji_{venue_slug}_{date.replace('-','')}_R{race:02d}.json"
        if existing_json.exists():
            import json as _json
            with open(existing_json, encoding="utf-8") as _f:
                _existing = _json.load(_f)
            motor_rows = [r for r in _existing if r.get("motor_no") is not None]
            if motor_rows:
                print("  モーター情報: 既存JSONから引き継ぎ")

    # ── 展示タイム取得 ──
    url = build_url(venue_slug, date, race)
    print(f"  展示タイム取得: {url}")
    rows = []
    # ★ 最大3回リトライ（展示ページのJS初期化遅延対策）
    for _attempt in range(1, 4):
        html = fetch_html(url, poll_count=30, session=session)
        rows = parse_tenji(html, venue_slug, date, race)
        if rows:
            break
        if _attempt < 3:
            print(f"  [WARN] 展示データ取得失敗（{_attempt}回目）。5秒後に再試行...")
            time.sleep(5)

    if not rows:
        print("  ⚠ 展示データなし（展示前または締め切り後）→ モーター情報のみ保存します")
        if not motor_rows:
            print("  モーター情報: 取得できず → スキップ")
            return []

        existing_rows = []
        if out_dir:
            existing_json = Path(out_dir) / f"tenji_{venue_slug}_{date.replace('-','')}_R{race:02d}.json"
            if existing_json.exists():
                import json as _json
                with open(existing_json, encoding="utf-8") as _f:
                    existing_rows = _json.load(_f)
                print(f"  既存JSON読み込み: {existing_json.name} ({len(existing_rows)}艇)")
        if not existing_rows:
            existing_rows = [
                {
                    "venue": venue_slug, "date": date, "race": race,
                    "frame": m["frame"], "racer": m.get("racer", ""),
                    "grade": m.get("grade", ""),
                    "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
                for m in motor_rows
            ]
            print("  既存JSONなし → モーター情報のみで新規作成します")

        motor_by_frame = {m["frame"]: m for m in motor_rows if m.get("frame") is not None}
        motor_by_racer = _build_motor_by_racer(motor_rows)
        for r in existing_rows:
            m = motor_by_frame.get(r.get("frame")) or _lookup_motor(r.get("racer", ""), motor_by_racer)
            if m is None:
                m = {}
            r.update({
                "motor_no":    m.get("motor_no"),
                "motor_rate2": m.get("motor_rate2"),
                "motor_rate3": m.get("motor_rate3"),
                "motor_rank":  m.get("motor_rank"),
                "prev_user":   m.get("prev_user"),
            })
        if out_dir:
            save_json(existing_rows, Path(out_dir), venue_slug, date, race)
            save_csv(existing_rows, Path(out_dir), venue_slug, date, race)
        print("  モーター情報保存完了")
        return existing_rows

    # ── モーター情報をrowsにマージ ──
    if not motor_rows:
        print("  モーター情報: 取得できず（null で埋めて保存）")
    motor_by_frame = {m["frame"]: m for m in motor_rows if m.get("frame") is not None}
    motor_by_racer = _build_motor_by_racer(motor_rows) if motor_rows else {}
    for r in rows:
        m = motor_by_frame.get(r.get("frame")) or _lookup_motor(r.get("racer", ""), motor_by_racer)
        if m is None:
            m = {}
        r.update({
            "motor_no":    m.get("motor_no"),
            "motor_rate2": m.get("motor_rate2"),
            "motor_rate3": m.get("motor_rate3"),
            "motor_rank":  m.get("motor_rank"),
            "prev_user":   m.get("prev_user"),
        })

    # ── 風情報取得 ──
    wind_url = build_wind_url(venue_slug, date, race)
    print(f"  風情報取得: {wind_url}")
    wind = {}
    wind_html = ""   # ← 進入情報パースでも再利用するため初期化
    _wind_poll = 20
    for attempt in range(1, 3):
        wind_html = fetch_html(
            wind_url,
            wait_for="CrawledRaceBeforeInfo",
            poll_count=_wind_poll,
            session=session,
        )
        wind = parse_wind(wind_html)
        if wind:
            break
        _wind_poll = 3
        if attempt < 2:
            print(f"  [WARN] 風情報取得失敗（{attempt}回目）。3秒後に最終確認...")
            time.sleep(3)

    if wind:
        wd = wind.get("wind_direction_text") or "不明"
        print(
            f"  天気:{wind.get('weather','---')}  気温:{wind.get('weather_degree','---')}℃"
            f"  水温:{wind.get('water_degree','---')}℃"
            f"  風速:{wind.get('wind_speed','---')}m/s({wd})"
            f"  波高:{wind.get('wave_height','---')}cm"
        )
    else:
        print("  風情報: 取得できず")

    # ── 進入（スタート隊形）情報取得 ──
    # 風情報と同じページ(last-minute)から取得済みのwind_htmlを再利用
    start_info = parse_start_info(wind_html)
    print(_fmt_start_info(start_info))

    # rowsに進入情報をマージ
    if start_info:
        for r in rows:
            bn = r["frame"]
            r["course"]        = start_info["courses"].get(bn)
            r["start_timing"]  = start_info["start_timings"].get(bn)
            r["has_start_change"] = start_info["has_change"]

    print(f"  {'枠':>2}  {'レーサー':<10} {'級':>3}  {'1周':>6}  {'回り足':>5}  {'直線':>5}  {'展示':>5}  {'M番':>3}  {'M2連':>5}  {'M3連':>5}  {'順位':>4}  前節使用者")
    print("  " + "─" * 88)
    for r in rows:
        m2 = f"{r['motor_rate2']:.1f}" if r.get("motor_rate2") is not None else " --- "
        m3 = f"{r['motor_rate3']:.1f}" if r.get("motor_rate3") is not None else " --- "
        mno = str(r["motor_no"]) if r.get("motor_no") is not None else "---"
        mrank = f"{r['motor_rank']}位" if r.get("motor_rank") is not None else " ---"
        prev = r.get("prev_user") or "---"
        print(
            f"  {r['frame']:>2}  {r['racer']:<10} {r['grade']:>3}"
            f"  {_fmt(r['lap1']):>6}  {_fmt(r['mawari']):>5}"
            f"  {_fmt(r['chokusen']):>5}  {_fmt(r['tenji']):>5}"
            f"  {mno:>3}  {m2:>5}  {m3:>5}  {mrank:>4}  {prev}"
        )

    if wind:
        for r in rows:
            r.update({
                "weather":             wind.get("weather"),
                "weather_degree":      wind.get("weather_degree"),
                "water_degree":        wind.get("water_degree"),
                "wind_speed":          wind.get("wind_speed"),
                "wind_direction":      wind.get("wind_direction"),
                "wind_direction_text": wind.get("wind_direction_text"),
                "wave_height":         wind.get("wave_height"),
            })

    if out_dir:
        save_csv(rows, out_dir, venue_slug, date, race)
        save_json(rows, out_dir, venue_slug, date, race)

    return rows


def _norm_racer(name: str) -> str:
    return str(name).replace(" ", "").replace("\u3000", "").replace("　", "").strip()


def _build_motor_by_racer(motor_rows: list) -> dict:
    return {_norm_racer(m["racer"]): m for m in motor_rows if m.get("racer")}


def _lookup_motor(racer_name: str, motor_by_racer: dict) -> dict:
    key = _norm_racer(racer_name)
    if key in motor_by_racer:
        return motor_by_racer[key]
    for k, v in motor_by_racer.items():
        if k.startswith(key) or key.startswith(k):
            return v
    return {}


def _fmt(v):
    return f"{v:.2f}" if v is not None else " --- "


# ─────────────────────────────────────────────────────────────
# 並列取得（モーター・展示・風を同時フェッチ）
# ─────────────────────────────────────────────────────────────
def fetch_one_parallel(venue_slug: str, date: str, race: int, out_dir,
                       motor_debug: bool = False) -> list:
    """
    モーター・展示タイム・風情報を ThreadPoolExecutor で並列取得し、
    fetch_one() と同じ形式のrowsを返す。

    【設計原則】
    - BrowserSession は各スレッドで独立して生成（Playwright非スレッドセーフのため）
    - fetch_one() の内部ロジックをそのまま呼ばず、フェッチ+パースだけ並列化
    - マージ・保存・表示は直列で実行（副作用の順序を保証）
    - fetch_one() / fetch_motor_only() との外部インターフェース互換を維持
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    print(f"\n▶ [parallel] {race}R  venue={venue_slug}  date={date}")

    motor_url = build_motor_url(venue_slug, date, race)
    tenji_url  = build_url(venue_slug, date, race)
    wind_url   = build_wind_url(venue_slug, date, race)

    results: dict = {}

    def _fetch_motor():
        with BrowserSession() as s:
            html = fetch_html(motor_url, wait_for="MotorAggregation",
                              poll_count=20, session=s)
        return parse_motor(html, debug=motor_debug)

    def _fetch_tenji():
        rows, html = [], ""
        # ★ 最大3回リトライ（展示ページのJS初期化遅延対策）
        for _attempt in range(1, 4):
            with BrowserSession() as s:
                html = fetch_html(tenji_url, poll_count=30, session=s)
            rows = parse_tenji(html, venue_slug, date, race)
            if rows:
                break
            if _attempt < 3:
                print(f"  [WARN] [parallel] 展示データ取得失敗（{_attempt}回目）。5秒後に再試行...")
                time.sleep(5)
        return rows, html

    def _fetch_wind():
        with BrowserSession() as s:
            html = fetch_html(wind_url, wait_for="CrawledRaceBeforeInfo",
                              poll_count=20, session=s)
        wind = parse_wind(html)
        # 1回目で取れなければ3秒待って最終確認
        if not wind:
            time.sleep(3)
            with BrowserSession() as s2:
                html = fetch_html(wind_url, wait_for="CrawledRaceBeforeInfo",
                                  poll_count=3, session=s2)
            wind = parse_wind(html)
        start_info = parse_start_info(html)
        return wind, start_info

    # ── 3タスクを並列実行 ──
    task_map = {
        "motor": _fetch_motor,
        "tenji": _fetch_tenji,
        "wind":  _fetch_wind,
    }
    with ThreadPoolExecutor(max_workers=3) as ex:
        futures = {ex.submit(fn): name for name, fn in task_map.items()}
        for fut in as_completed(futures):
            name = futures[fut]
            try:
                results[name] = fut.result()
            except Exception as e:
                print(f"  [WARN] {name} 取得失敗: {e}")
                results[name] = None

    motor_rows = results.get("motor") or []
    tenji_result = results.get("tenji")
    rows, _ = tenji_result if tenji_result else ([], "")
    wind_result = results.get("wind")
    wind, start_info = wind_result if wind_result else ({}, {})

    # ── 以降は fetch_one() と同一のマージ・表示・保存ロジック ──

    if not rows:
        print(f"  ⚠ {race}R 展示データなし（展示前または締め切り後）→ モーター情報のみ保存します")
        if not motor_rows:
            print("  モーター情報: 取得できず → スキップ")
            return []

        existing_rows = []
        if out_dir:
            existing_json = Path(out_dir) / f"tenji_{venue_slug}_{date.replace('-','')}_R{race:02d}.json"
            if existing_json.exists():
                with open(existing_json, encoding="utf-8") as f:
                    existing_rows = json.load(f)
                print(f"  既存JSON読み込み: {existing_json.name} ({len(existing_rows)}艇)")
        if not existing_rows:
            existing_rows = [
                {
                    "venue": venue_slug, "date": date, "race": race,
                    "frame": m["frame"], "racer": m.get("racer", ""),
                    "grade": m.get("grade", ""),
                    "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
                for m in motor_rows
            ]

        motor_by_frame = {m["frame"]: m for m in motor_rows if m.get("frame") is not None}
        motor_by_racer = _build_motor_by_racer(motor_rows)
        for r in existing_rows:
            m = motor_by_frame.get(r.get("frame")) or _lookup_motor(r.get("racer", ""), motor_by_racer)
            if m is None:
                m = {}
            r.update({
                "motor_no":    m.get("motor_no"),
                "motor_rate2": m.get("motor_rate2"),
                "motor_rate3": m.get("motor_rate3"),
                "motor_rank":  m.get("motor_rank"),
                "prev_user":   m.get("prev_user"),
            })
        if out_dir:
            save_json(existing_rows, Path(out_dir), venue_slug, date, race)
            save_csv(existing_rows, Path(out_dir), venue_slug, date, race)
        print("  モーター情報保存完了")
        return existing_rows

    # モーター情報マージ
    if not motor_rows:
        print("  モーター情報: 取得できず（null で埋めて保存）")
    motor_by_frame = {m["frame"]: m for m in motor_rows if m.get("frame") is not None}
    motor_by_racer = _build_motor_by_racer(motor_rows) if motor_rows else {}
    for r in rows:
        m = motor_by_frame.get(r.get("frame")) or _lookup_motor(r.get("racer", ""), motor_by_racer)
        if m is None:
            m = {}
        r.update({
            "motor_no":    m.get("motor_no"),
            "motor_rate2": m.get("motor_rate2"),
            "motor_rate3": m.get("motor_rate3"),
            "motor_rank":  m.get("motor_rank"),
            "prev_user":   m.get("prev_user"),
        })

    # 風情報ログ
    if wind:
        wd = wind.get("wind_direction_text") or "不明"
        print(
            f"  天気:{wind.get('weather','---')}  気温:{wind.get('weather_degree','---')}℃"
            f"  水温:{wind.get('water_degree','---')}℃"
            f"  風速:{wind.get('wind_speed','---')}m/s({wd})"
            f"  波高:{wind.get('wave_height','---')}cm"
        )
    else:
        print("  風情報: 取得できず")

    # 進入情報マージ
    print(_fmt_start_info(start_info))
    if start_info:
        for r in rows:
            bn = r["frame"]
            r["course"]           = start_info["courses"].get(bn)
            r["start_timing"]     = start_info["start_timings"].get(bn)
            r["has_start_change"] = start_info["has_change"]

    # 表示
    lap1_label = "半周" if venue_slug == "kiryu" else "1周"
    print(f"  {'枠':>2}  {'レーサー':<10} {'級':>3}  {lap1_label:>6}  {'回り足':>5}  {'直線':>5}  {'展示':>5}  {'M番':>3}  {'M2連':>5}  {'M3連':>5}  {'順位':>4}  前節使用者")
    print("  " + "─" * 88)
    for r in rows:
        m2    = f"{r['motor_rate2']:.1f}" if r.get("motor_rate2") is not None else " --- "
        m3    = f"{r['motor_rate3']:.1f}" if r.get("motor_rate3") is not None else " --- "
        mno   = str(r["motor_no"]) if r.get("motor_no") is not None else "---"
        mrank = f"{r['motor_rank']}位" if r.get("motor_rank") is not None else " ---"
        prev  = r.get("prev_user") or "---"
        print(
            f"  {r['frame']:>2}  {r['racer']:<10} {r['grade']:>3}"
            f"  {_fmt(r['lap1']):>6}  {_fmt(r['mawari']):>5}"
            f"  {_fmt(r['chokusen']):>5}  {_fmt(r['tenji']):>5}"
            f"  {mno:>3}  {m2:>5}  {m3:>5}  {mrank:>4}  {prev}"
        )

    # 風情報をrowsに付与
    if wind:
        for r in rows:
            r.update({
                "weather":             wind.get("weather"),
                "weather_degree":      wind.get("weather_degree"),
                "water_degree":        wind.get("water_degree"),
                "wind_speed":          wind.get("wind_speed"),
                "wind_direction":      wind.get("wind_direction"),
                "wind_direction_text": wind.get("wind_direction_text"),
                "wave_height":         wind.get("wave_height"),
            })

    if out_dir:
        save_csv(rows, Path(out_dir), venue_slug, date, race)
        save_json(rows, Path(out_dir), venue_slug, date, race)

    return rows


def main():
    ap = argparse.ArgumentParser(
        description="boaters-boatrace.com テン展示データ 自動取得",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--venue", required=True,
        help="場スラッグ(heiwajima等) または日本語名(平和島等)")
    ap.add_argument("--date", required=True, help="日付 YYYY-MM-DD")
    ap.add_argument("--race", type=int, help="レース番号 1〜12")
    ap.add_argument("--races", help="複数指定 例: 1,3,5")
    ap.add_argument("--all", action="store_true", help="全レース 1〜12R")
    ap.add_argument("--poll", type=int, default=0,
        help="ポーリング間隔(秒)。0=1回のみ")
    ap.add_argument("--out", default=r"C:\Users\user\Desktop\データ収集\scripts\tenji_data", help="保存先ディレクトリ")
    ap.add_argument("--no-save", action="store_true", help="保存しない")
    ap.add_argument("--motor-debug", action="store_true",
        help="モーター取得時に Apollo の型/フィールド名をデバッグ出力する")
    ap.add_argument("--motor-only", action="store_true",
        help="モーター情報のみ取得（展示タイム・風情報はスキップ）")
    ap.add_argument("--parallel", action="store_true",
        help="モーター・展示・風を並列取得（複数レース時に高速化）")
    args = ap.parse_args()

    venue = VENUE_SLUG.get(args.venue, args.venue)
    out_dir = None if args.no_save else Path(args.out)

    if args.all:
        race_list = list(range(1, 13))
    elif args.races:
        race_list = [int(r) for r in args.races.split(",")]
    elif args.race:
        race_list = [args.race]
    else:
        ap.error("--race / --races / --all のいずれかが必要です")

    # ★ --parallel: 各レースをスレッド並列。BrowserSession不要（各スレッドが独立生成）
    # ★ 通常: ブラウザを1回起動して全レース分使い回す
    if args.parallel and not args.motor_only:
        try:
            while True:
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                print(f"\n{'='*60}")
                print(f"  {ts}  場={venue}  日付={args.date}  [parallel]")
                print("=" * 60)
                from concurrent.futures import ThreadPoolExecutor, as_completed as _ac
                def _run_race(race):
                    try:
                        return fetch_one_parallel(venue, args.date, race, out_dir,
                                                  motor_debug=args.motor_debug)
                    except Exception as e:
                        print(f"  [ERROR] {race}R: {e}")
                        return []
                with ThreadPoolExecutor(max_workers=len(race_list)) as ex:
                    futs = {ex.submit(_run_race, r): r for r in race_list}
                    for fut in _ac(futs):
                        pass  # 結果はfetch_one_parallel内で保存済み

                if args.poll <= 0:
                    break
                print(f"\n⏱ {args.poll}秒後に再取得 ... (Ctrl+C で終了)")
                time.sleep(args.poll)

        except KeyboardInterrupt:
            print("\n[終了]")

    else:
        with BrowserSession() as session:
            try:
                while True:
                    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    print(f"\n{'='*60}")
                    print(f"  {ts}  場={venue}  日付={args.date}"
                          f"{'  [motor-only]' if args.motor_only else ''}")
                    print("=" * 60)
                    for race in race_list:
                        try:
                            if args.motor_only:
                                fetch_motor_only(venue, args.date, race, out_dir,
                                                 motor_debug=args.motor_debug,
                                                 session=session)
                            else:
                                fetch_one(venue, args.date, race, out_dir,
                                          motor_debug=args.motor_debug,
                                          session=session)
                            if len(race_list) > 1:
                                time.sleep(2)
                        except Exception as e:
                            print(f"  [ERROR] {race}R: {e}")

                    if args.poll <= 0:
                        break
                    print(f"\n⏱ {args.poll}秒後に再取得 ... (Ctrl+C で終了)")
                    time.sleep(args.poll)

            except KeyboardInterrupt:
                print("\n[終了]")


if __name__ == "__main__":
    main()
