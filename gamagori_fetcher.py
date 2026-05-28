"""
蒲郡コメント取得モジュール（確定版・JS直接パース）
====================================================
【解析済み構造】
  ① comment/comment{YYYYMMDD}07{RR}.htm
       → HTMLをregexで解析 → 枠番ごとの登番マッピングを取得
         funcBeforeComment("XXXX") ... getElementById("comment{waku}_1")
         funcToDayComment("XXXX")  ... getElementById("comment{waku}_2")

  ② js/comment{YYYYMMDD}07.js（Shift-JIS）
       → funcToDayComment(登番) → 前検コメント文字列
         （当日コメントは funcToDayNewComment で別管理、レース後に更新）

  ③ 組み合わせで「枠番→コメント」を生成

【使い方（単体テスト）】
  python gamagori_fetcher.py
  python gamagori_fetcher.py --date 2026-05-25 --race 3
  python gamagori_fetcher.py --all          # 全12R一括取得

【scrape_comments.py への組み込み】
  from gamagori_fetcher import scrape_gamagori
  data = scrape_gamagori(race_no=1, date_str="2026-05-25")
  # → {"1": {"comment": "..."}, "2": {...}, ..., "__fetched_at": "07:12:34"}
"""

import re
import sys
import time
import argparse
import logging
from datetime import date, datetime
from typing import Optional

import requests

# ── 定数 ──────────────────────────────────────────────────
_BASE       = "https://www.gamagori-kyotei.com/asp/gamagori/kyogi/kyogihtml"
_JYO        = "07"   # 蒲郡の場コード（固定）
_RETRY      = 3
_RETRY_WAIT = 3

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en-US;q=0.9",
})


# ── URL生成 ───────────────────────────────────────────────
def _comment_htm_url(date_str: str, race_no: int) -> str:
    """枠番→登番マッピングを持つ HTM ファイルの URL"""
    d = date_str.replace("-", "")
    return f"{_BASE}/comment/comment{d}{_JYO}{race_no:02d}.htm"


def _comment_js_url(date_str: str) -> str:
    """全選手コメントが入った JS ファイルの URL（1日1ファイル）"""
    d = date_str.replace("-", "")
    return f"{_BASE}/js/comment{d}{_JYO}.js"


# ── HTTP 取得 ─────────────────────────────────────────────
def _detect_encoding(content: bytes, hint: Optional[str] = None) -> str:
    """
    バイト列の実際のエンコーディングを検出して返す。

    優先順位:
      1. BOM があれば BOM 優先
      2. charset-normalizer / chardet で自動検出（信頼度 0.7 以上）
      3. hint（呼び出し元の期待値）があればそれを採用
      4. デフォルト "utf-8"

    【背景】
      蒲郡の JS ファイルはコメントに "Shift-JIS" と記載されているが、
      実際のサーバー応答は UTF-8 で返る場合がある。
      resp.content.decode("shift_jis") で強制指定すると UTF-8 テキストを
      SJIS として誤読し「襍ｷ縺薙＠縺ｯ...」のような文字化けが発生する。
      この関数で実際のエンコーディングを検出することで問題を回避する。
    """
    # BOM チェック
    if content.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    if content.startswith(b"\xff\xfe"):
        return "utf-16-le"
    if content.startswith(b"\xfe\xff"):
        return "utf-16-be"

    # charset-normalizer（requests が内部で使うライブラリ）
    try:
        from charset_normalizer import from_bytes
        best = from_bytes(content).best()
        if best is not None:
            detected = best.encoding
            log.debug(f"  charset-normalizer 検出: {detected}")
            return detected
    except ImportError:
        pass

    # chardet フォールバック
    try:
        import chardet
        result = chardet.detect(content)
        if result.get("confidence", 0) >= 0.7 and result.get("encoding"):
            detected = result["encoding"]
            log.debug(f"  chardet 検出: {detected} (confidence={result['confidence']:.2f})")
            return detected
    except ImportError:
        pass

    # hint または デフォルト
    if hint:
        log.debug(f"  自動検出失敗 → hint を使用: {hint}")
        return hint

    log.debug("  自動検出失敗 → utf-8 にフォールバック")
    return "utf-8"


def _fetch(url: str, encoding: Optional[str] = None) -> Optional[str]:
    """
    URLを取得してテキストを返す。

    encoding 引数は「期待するエンコーディングのヒント」として扱う。
    実際には _detect_encoding() でバイト列から自動検出し、
    ヒントと一致しない場合は検出結果を優先する。

    【修正履歴】
      旧実装: resp.content.decode(encoding, errors='replace') で強制デコード
        → サーバーが UTF-8 を返しているのに SJIS で強制デコードして文字化け
      新実装: _detect_encoding() で実際のエンコーディングを検出してからデコード
    """
    for attempt in range(1, _RETRY + 1):
        try:
            resp = _SESSION.get(url, timeout=15)
            resp.raise_for_status()

            if encoding:
                # ヒントあり → 自動検出して実際のエンコーディングを使う
                actual_enc = _detect_encoding(resp.content, hint=encoding)
                if actual_enc.lower().replace("-", "") != encoding.lower().replace("-", ""):
                    log.info(
                        f"  エンコーディング自動補正: hint={encoding} → 実際={actual_enc}  url={url}"
                    )
                return resp.content.decode(actual_enc, errors="replace")

            # ヒントなし → requests の自動検出（apparent_encoding）を使う
            resp.encoding = resp.apparent_encoding
            return resp.text

        except requests.RequestException as e:
            log.warning(f"  取得失敗 (試行{attempt}/{_RETRY}): {e}")
            if attempt == _RETRY:
                return None
            time.sleep(_RETRY_WAIT)
    return None


# ── STEP1: HTM から枠番→登番マッピングを抽出 ──────────────
def _parse_waku_touban_map(htm_text: str) -> dict[str, str]:
    """
    comment{YYYYMMDD}{JYO}{RR}.htm のHTMLテキストから
    {waku: touban} 辞書を返す。

    パターン:
      funcBeforeComment( "XXXX" ) ... getElementById("comment{waku}_1")
      funcToDayComment(  "XXXX" ) ... getElementById("comment{waku}_2")
    前検・当日で同じ登番のはずなので前検側（_1）を優先して取得。
    """
    # 改行を正規化してから潰す（\r\n → \n → スペース の順が正しい）
    flat = htm_text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", " ")

    mapping: dict[str, str] = {}

    # ── パターンA: 前検側 funcBeforeComment → getElementById("comment{waku}_1") ──
    # .{0,600}? に拡大（日によってHTMLの間隔が変わるため）
    for m in re.finditer(
        r'funcBeforeComment\(\s*["\'](\d{4})["\']\s*\)'
        r'.{0,600}?getElementById\s*\(\s*["\']comment(\d)_1["\']\s*\)',
        flat,
    ):
        touban, waku = m.group(1), m.group(2)
        mapping[waku] = touban

    # ── パターンB: 当日側 funcToDayComment → getElementById("comment{waku}_2") ──
    # 前検で取れなかった枠のフォールバック
    for m in re.finditer(
        r'funcToDayComment\(\s*["\'](\d{4})["\']\s*\)'
        r'.{0,600}?getElementById\s*\(\s*["\']comment(\d)_2["\']\s*\)',
        flat,
    ):
        touban, waku = m.group(1), m.group(2)
        if waku not in mapping:
            mapping[waku] = touban

    if mapping:
        return mapping

    # ── パターンC: 逆順パターン getElementById → funcBeforeComment ──
    # HTMLの記述順が逆になっているケース（日付変更後に発生することがある）
    for m in re.finditer(
        r'getElementById\s*\(\s*["\']comment(\d)_1["\']\s*\)'
        r'.{0,600}?funcBeforeComment\(\s*["\'](\d{4})["\']\s*\)',
        flat,
    ):
        waku, touban = m.group(1), m.group(2)
        mapping[waku] = touban

    for m in re.finditer(
        r'getElementById\s*\(\s*["\']comment(\d)_2["\']\s*\)'
        r'.{0,600}?funcToDayComment\(\s*["\'](\d{4})["\']\s*\)',
        flat,
    ):
        waku, touban = m.group(1), m.group(2)
        if waku not in mapping:
            mapping[waku] = touban

    if mapping:
        log.info("  [gamagori] パターンC（逆順）でマッピング取得")
        return mapping

    # ── パターンD: 登番とcommentXのIDが同一script内に存在するケース ──
    # スクリプトブロックを1つずつ見て登番とwakuを同時に拾う
    for script_m in re.finditer(r'<script[^>]*>(.*?)</script>', flat, re.IGNORECASE):
        block = script_m.group(1)
        # このscriptブロック内に comment{waku}_1 or _2 と 4桁登番が共存するか確認
        waku_m   = re.search(r'getElementById\s*\(\s*["\']comment(\d)_[12]["\']\s*\)', block)
        touban_m = re.search(r'func(?:Before|ToDay)(?:New)?Comment\(\s*["\'](\d{4})["\']\s*\)', block)
        if waku_m and touban_m:
            waku, touban = waku_m.group(1), touban_m.group(1)
            if waku not in mapping:
                mapping[waku] = touban

    if mapping:
        log.info("  [gamagori] パターンD（scriptブロック単位）でマッピング取得")

    return mapping  # {"1": "3867", "2": "3081", ...}


# ── STEP2: comment JS から登番→コメントを抽出 ─────────────
def _parse_comment_js(js_text: str) -> dict[str, str]:
    """
    comment{YYYYMMDD}{JYO}.js のテキストから
    funcToDayComment の {touban: comment} 辞書を返す。

    JSは Shift-JIS だが decode 済みのテキストを受け取る前提。

    funcToDayComment のシンプルなブロック（行1〜103相当）だけを対象にする。
    funcToDayNewComment はレース後に更新されるため別途対応。
    """
    # funcToDayComment の定義ブロックだけを切り出す
    # パターン1: 行頭の } で終わるブロック（MULTILINE）
    simple_block_match = re.search(
        r"function funcToDayComment\b.*?^}",
        js_text,
        re.DOTALL | re.MULTILINE,
    )
    # パターン2: 次の function 定義の直前まで
    if not simple_block_match:
        func_match = re.search(
            r"(function funcToDayComment\b.*?)(?=\nfunction |\Z)",
            js_text,
            re.DOTALL,
        )
        simple_block_match = func_match

    if not simple_block_match:
        # 最終フォールバック: funcToDayNewComment の前まで
        new_comment_pos = js_text.find("function funcToDayNewComment")
        target = js_text[:new_comment_pos] if new_comment_pos != -1 else js_text
    else:
        target = simple_block_match.group(0)

    result: dict[str, str] = {}
    for m in re.finditer(
        r"strTouban\s*===\s*['\"](\d{4})['\"]"
        r".*?strComment\s*=\s*'([^']*)'",
        target,
        re.DOTALL,
    ):
        touban, comment = m.group(1), m.group(2)
        if comment and touban not in result:  # 最初のマッチを採用
            result[touban] = comment

    return result  # {"3867": "起こしはちょっと...", "3081": "数字のない..."}


# ── STEP3: 組み合わせて 枠番→コメント を生成 ─────────────
def _build_result(
    waku_map: dict[str, str],
    comment_map: dict[str, str],
) -> dict:
    """
    waku_map:    {waku: touban}
    comment_map: {touban: comment}
    → {"1": {"comment": "...", "touban": "3867"}, ...}
    """
    result: dict = {}
    for waku in ("1", "2", "3", "4", "5", "6"):
        touban = waku_map.get(waku)
        if not touban:
            continue
        comment = comment_map.get(touban, "")
        entry: dict = {"touban": touban}
        if comment:
            entry["comment"] = comment
        result[waku] = entry
    return result


# ── メイン公開関数 ────────────────────────────────────────
def scrape_gamagori(
    race_no: int,
    date_str: Optional[str] = None,
    verbose: bool = True,
) -> Optional[dict]:
    """
    蒲郡の指定レースのコメントを取得して返す。

    戻り値:
      {
        "1": {"touban": "3867", "comment": "起こしはちょっと良くなかった。"},
        "2": {"touban": "3081", "comment": "数字のないエンジンだけど..."},
        ...
        "__fetched_at": "07:12:34",
        "__date": "2026-05-25",
        "__race": 1,
      }
      取得失敗 → None

    Notes:
      - comment JS は1日1ファイル（全レース共通）なのでキャッシュ推奨
      - 前検当日の朝に公開されるため、前日は 404 になる
    """
    if date_str is None:
        date_str = date.today().isoformat()

    htm_url = _comment_htm_url(date_str, race_no)
    js_url  = _comment_js_url(date_str)

    if verbose:
        log.info(f"[gamagori] {date_str} {race_no}R コメント取得開始")
        log.info(f"  HTM: {htm_url}")
        log.info(f"  JS : {js_url}")

    # ── STEP1: HTM 取得（UTF-8 or SJIS、サイトによる）──────
    htm_text = _fetch(htm_url)
    if htm_text is None:
        log.warning(f"  [gamagori] HTM 取得失敗 → コメント未公開の可能性: {htm_url}")
        return None

    waku_map = _parse_waku_touban_map(htm_text)
    if not waku_map:
        # HTM のエンコーディングが Shift-JIS だった場合を試みる
        htm_text_sjis = _fetch(htm_url, encoding="shift_jis")
        if htm_text_sjis:
            waku_map = _parse_waku_touban_map(htm_text_sjis)

    if not waku_map:
        log.warning(f"  [gamagori] {race_no}R: HTM から枠番→登番マッピング取得失敗")
        return None

    if verbose:
        log.info(f"  枠番マッピング: { {w: t for w, t in sorted(waku_map.items())} }")

    # ── STEP2: JS 取得（Shift-JIS）────────────────────────
    # JS はファイルサイズが大きい（〜150KB）が1日1回で全選手分
    js_text = _fetch(js_url, encoding="shift_jis")
    if js_text is None:
        log.warning(f"  [gamagori] JS 取得失敗: {js_url}")
        return None

    comment_map = _parse_comment_js(js_text)
    if verbose:
        log.info(f"  JS から {len(comment_map)} 選手分のコメントを読み込み")

    # ── STEP3: 組み合わせ ──────────────────────────────────
    result = _build_result(waku_map, comment_map)

    if not result:
        log.warning(f"  [gamagori] {race_no}R: コメントを組み立てられませんでした")
        return None

    result["__fetched_at"] = datetime.now().strftime("%H:%M:%S")
    result["__date"]       = date_str
    result["__race"]       = race_no

    if verbose:
        log.info(f"  [gamagori] {race_no}R: {len([k for k in result if not k.startswith('__')])}艇分取得成功")

    return result


def scrape_gamagori_all(
    date_str: Optional[str] = None,
    races: Optional[list[int]] = None,
    interval: float = 1.0,
) -> dict[int, Optional[dict]]:
    """
    蒲郡の複数レースを一括取得して返す。

    戻り値: {race_no: scrape_gamagori() の戻り値}

    Notes:
      - JS は全レース共通なので1回だけ取得してキャッシュする
      - HTM はレースごとに別ファイルなので都度取得
    """
    if date_str is None:
        date_str = date.today().isoformat()
    if races is None:
        races = list(range(1, 13))

    log.info(f"[gamagori] {date_str} 全{len(races)}R 一括取得開始")

    # JS を最初に1回だけ取得
    js_url  = _comment_js_url(date_str)
    js_text = _fetch(js_url, encoding="shift_jis")
    if js_text is None:
        log.error(f"  [gamagori] JS 取得失敗（中断）: {js_url}")
        return {r: None for r in races}

    comment_map = _parse_comment_js(js_text)
    log.info(f"  JS から {len(comment_map)} 選手分のコメントを読み込み")

    results: dict[int, Optional[dict]] = {}
    for race_no in races:
        htm_url  = _comment_htm_url(date_str, race_no)
        htm_text = _fetch(htm_url)
        if htm_text is None:
            htm_text = _fetch(htm_url, encoding="shift_jis")  # SJIS フォールバック

        if htm_text is None:
            log.warning(f"  [{race_no}R] HTM 取得失敗（未公開の可能性）")
            results[race_no] = None
            time.sleep(interval)
            continue

        waku_map = _parse_waku_touban_map(htm_text)
        if not waku_map:
            log.warning(f"  [{race_no}R] 枠番マッピング取得失敗")
            results[race_no] = None
            time.sleep(interval)
            continue

        data = _build_result(waku_map, comment_map)
        if data:
            data["__fetched_at"] = datetime.now().strftime("%H:%M:%S")
            data["__date"]       = date_str
            data["__race"]       = race_no
            log.info(f"  [{race_no}R] ✓ {len([k for k in data if not k.startswith('__')])}艇分取得成功"
                     f"  枠1登番={waku_map.get('1','?')}")
        else:
            log.warning(f"  [{race_no}R] コメント組み立て失敗")
            data = None

        results[race_no] = data
        time.sleep(interval)

    ok  = [r for r, d in results.items() if d]
    ng  = [r for r, d in results.items() if not d]
    log.info(f"[gamagori] 完了  成功: {ok}  失敗: {ng}")
    return results


# ── scrape_comments.py 用ラッパー ─────────────────────────
def gamagori_scrape_one_race(
    race_no: int,
    date_str: str,
    _debug_html: bool = False,
) -> Optional[dict]:
    """
    scrape_comments.py の scrape_one_race から呼ぶための互換関数。
    戻り値は scrape_gamagori() と同じ形式。
    """
    return scrape_gamagori(race_no=race_no, date_str=date_str)


# ── CLI（単体テスト用）────────────────────────────────────
def _main():
    parser = argparse.ArgumentParser(
        description="蒲郡コメント取得（JS直接パース版）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--date", default=date.today().isoformat(),
                        help="日付 YYYY-MM-DD（デフォルト: 今日）")
    parser.add_argument("--race", type=int, default=1,
                        help="レース番号 1〜12（デフォルト: 1）")
    parser.add_argument("--all", action="store_true",
                        help="全12R一括取得")
    args = parser.parse_args()

    if args.all:
        results = scrape_gamagori_all(date_str=args.date)
        print(f"\n{'='*60}")
        print(f"  蒲郡コメント 全レース取得結果  {args.date}")
        print(f"{'='*60}")
        for race_no in range(1, 13):
            data = results.get(race_no)
            if not data:
                print(f"  {race_no:2d}R: 取得失敗")
                continue
            print(f"\n  {race_no:2d}R ({data.get('__fetched_at', '')})")
            for waku in range(1, 7):
                entry = data.get(str(waku))
                if entry:
                    touban  = entry.get("touban", "????")
                    comment = entry.get("comment", "（なし）")
                    print(f"    {waku}枠 [{touban}]: {comment[:50]}")
    else:
        data = scrape_gamagori(race_no=args.race, date_str=args.date)
        print(f"\n{'='*60}")
        print(f"  蒲郡コメント  {args.date} {args.race}R")
        print(f"{'='*60}")
        if not data:
            print("  取得失敗（未公開またはURL構造変更の可能性）")
            sys.exit(1)
        for waku in range(1, 7):
            entry = data.get(str(waku))
            if entry:
                touban  = entry.get("touban", "????")
                comment = entry.get("comment", "（コメントなし）")
                print(f"  {waku}枠 [{touban}]: {comment}")
            else:
                print(f"  {waku}枠: （データなし）")


if __name__ == "__main__":
    _main()
