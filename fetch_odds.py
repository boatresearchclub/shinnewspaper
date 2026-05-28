"""
fetch_odds.py
=============
boatrace.jp から全種別オッズを取得し、JSON保存 + auto_push.py への
inject_odds_to_html() 連携まで一貫して行う。

【対応種別】
  3t  : 3連単（odds3t）   120通り
  3f  : 3連複（odds3f）    20通り
  2t  : 2連単（oddsk）     30通り
  2f  : 2連複（oddsh）     15通り
  tan : 単勝（tansho）      6通り

【キー形式】
  全種別とも "1-2-3" / "1-2" / "1" 形式（ハイフン区切り）
  ← index.html の normalizeCombo() と統一

【使い方】
  (A) auto_push.py から呼び出す
      from fetch_odds import fetch_all_races, inject_odds_to_html

  (B) 単体テスト
      python fetch_odds.py --jcd 05 --hd 20260509
      python fetch_odds.py --url "https://www.boatrace.jp/owpc/pc/race/odds3t?rno=6&jcd=05&hd=20260509"

【場コード】
  01=桐生  02=戸田  03=江戸川  04=平和島  05=多摩川  06=浜名湖
  07=蒲郡  08=常滑  09=津     10=三国    11=びわこ  12=住之江
  13=尼崎  14=鳴門  15=丸亀   16=児島    17=宮島    18=徳山
  19=下関  20=若松  21=芦屋   22=福岡    23=唐津    24=大村
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from itertools import permutations, combinations
from pathlib import Path
from typing import Optional

# ─────────────────────────────────────────────────────────────────────────────
# 定数・マスタ
# ─────────────────────────────────────────────────────────────────────────────

SCRIPTS_DIR  = Path(__file__).parent
ODDS_DIR     = SCRIPTS_DIR / "odds_data"
RESULT_DIR   = SCRIPTS_DIR / "result_data"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.boatrace.jp/",
}

FETCH_TIMEOUT  = 15   # 秒
RETRY_COUNT    = 3
RETRY_WAIT     = 2    # 秒
INTER_REQ_WAIT = 1.5  # リクエスト間のウェイト（基本値・サーバー負荷対策）

# 優先度別のリクエスト間隔（秒）
# 締め切り5分以内 （超優先）: 1.5秒 × 3tのみ ≒ 1.5秒/レース  ★追加
# 締め切り20分以内（最優先）: 1.5秒 × 5種別 ≒ 7.5秒/レース
# 締め切り20〜60分（通常）  : 3.0秒 × 5種別 ≒ 15秒/レース
# 締め切り60分以上（低優先）: 3.0秒 × 3tのみ ≒ 3秒/レース
INTER_REQ_WAIT_PRIORITY = 1.5   # 20分以内
INTER_REQ_WAIT_NORMAL   = 3.0   # 20〜60分
ULTRA_PRIORITY_MINUTES  = 5     # この分以内は3tのみ取得（巡回速度最優先）
PRIORITY_MINUTES        = 20    # この分以内を「最優先」とみなす
LOW_PRIORITY_MINUTES    = 60    # この分以上先は3tのみ取得
FINAL_ODDS_WINDOW_MINUTES = 60  # 締め切り後、何分以内なら「確定オッズ取得待ち」とみなすか

# 取得する種別の定義
# key: HTML/JS側の識別子, endpoint: URLのパス部分, css_class: オッズtdのクラス名
ODDS_TYPES = [
    {"key": "3t",  "endpoint": "odds3t",  "css": "oddsPoint",  "count": 120},
    {"key": "3f",  "endpoint": "odds3f",  "css": "oddsPoint",  "count": 20},
    {"key": "2t",  "endpoint": "oddsk",   "css": "oddsPoint",  "count": 30},
    {"key": "2f",  "endpoint": "oddsh",   "css": "oddsPoint",  "count": 15},
    {"key": "tan", "endpoint": "tansho",  "css": "oddsPoint",  "count": 6},
]

# 会場名 → 場コード（2桁）
VENUE_JCD = {
    "桐生":   "01", "戸田":   "02", "江戸川": "03", "平和島": "04",
    "多摩川": "05", "浜名湖": "06", "蒲郡":   "07", "常滑":   "08",
    "津":     "09", "三国":   "10", "びわこ": "11", "住之江": "12",
    "尼崎":   "13", "鳴門":   "14", "丸亀":   "15", "児島":   "16",
    "宮島":   "17", "徳山":   "18", "下関":   "19", "若松":   "20",
    "芦屋":   "21", "福岡":   "22", "唐津":   "23", "大村":   "24",
}

# 会場名 → スラッグ（ファイル名用）
VENUE_SLUG = {
    "桐生":   "kiryu",       "戸田":   "toda",       "江戸川": "edogawa",
    "平和島": "heiwajima",   "多摩川": "tamagawa",   "浜名湖": "hamanako",
    "蒲郡":   "gamagori",    "常滑":   "tokoname",   "津":     "tsu",
    "三国":   "mikuni",      "びわこ": "biwako",     "住之江": "suminoe",
    "尼崎":   "amagasaki",   "鳴門":   "naruto",     "丸亀":   "marugame",
    "児島":   "kojima",      "宮島":   "miyajima",   "徳山":   "tokuyama",
    "下関":   "shimonoseki", "若松":   "wakamatsu",  "芦屋":   "ashiya",
    "福岡":   "fukuoka",     "唐津":   "karatsu",    "大村":   "omura",
}

# スラッグ → 会場名（逆引き）
SLUG_VENUE = {v: k for k, v in VENUE_SLUG.items()}


# ─────────────────────────────────────────────────────────────────────────────
# 組み合わせマスタ（公式サイトの表示順）
# ─────────────────────────────────────────────────────────────────────────────

def _make_combos_3t() -> list[tuple]:
    """
    3連単: 120通り（boatrace.jp HTML出現順と完全一致）

    HTMLの oddsPoint の並び順:
      1着を1→6で固定し、
      2着を「1着を除く昇順」、
      3着を「1着・2着を除く昇順」で変化。

      例: 1-2-3, 1-2-4, 1-2-5, 1-2-6,
          1-3-2, 1-3-4, 1-3-5, 1-3-6, ...
          2-1-3, 2-1-4, ..., 2-3-1, 2-3-4, ...
    """
    return [
        (f, s, t)
        for f in range(1, 7)
        for s in range(1, 7) if s != f
        for t in range(1, 7) if t != f and t != s
    ]

def _make_combos_3f() -> list[tuple]:
    """3連複: 20通り（数字昇順）"""
    return list(combinations(range(1, 7), 3))

def _make_combos_2t() -> list[tuple]:
    """2連単: 30通り（1着→2着の昇順）"""
    return [(f, s) for f in range(1, 7) for s in range(1, 7) if f != s]

def _make_combos_2f() -> list[tuple]:
    """2連複: 15通り（数字昇順）"""
    return list(combinations(range(1, 7), 2))

def _make_combos_tan() -> list[tuple]:
    """単勝: 6通り"""
    return [(i,) for i in range(1, 7)]

COMBOS = {
    "3t":  _make_combos_3t(),
    "3f":  _make_combos_3f(),
    "2t":  _make_combos_2t(),
    "2f":  _make_combos_2f(),
    "tan": _make_combos_tan(),
}


def _combo_key(combo: tuple) -> str:
    """組み合わせタプルをキー文字列に変換: (1,2,3) → "1-2-3" """
    return "-".join(str(n) for n in combo)


# ─────────────────────────────────────────────────────────────────────────────
# HTMLフェッチ
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_html(url: str) -> str:
    """URLからHTMLを取得（リトライ付き）"""
    last_err = None
    for attempt in range(1, RETRY_COUNT + 1):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as res:
                raw = res.read()
                # ページは UTF-8 だが念のため charset 検出
                try:
                    return raw.decode("utf-8")
                except UnicodeDecodeError:
                    return raw.decode("shift_jis", errors="replace")
        except Exception as e:
            last_err = e
            if attempt < RETRY_COUNT:
                print(f"    ⚠ 取得失敗({attempt}/{RETRY_COUNT}): {e} → {RETRY_WAIT}秒後リトライ",
                      flush=True)
                time.sleep(RETRY_WAIT)
    raise ConnectionError(f"取得失敗: {last_err}  URL: {url}")


# ─────────────────────────────────────────────────────────────────────────────
# オッズHTML解析
# ─────────────────────────────────────────────────────────────────────────────

def _parse_odds_page(html: str, odds_key: str) -> dict[str, float]:
    """
    boatrace.jp のオッズページHTMLを解析して辞書を返す。

    解析戦略（優先順）:
      1. BeautifulSoup + CSS class → 最も確実
      2. 正規表現で class属性のオッズtdを抽出
      3. 正規表現で全数値を抽出して順序マッピング
    各方法が失敗するか件数不足なら次にフォールバック。
    """
    combos    = COMBOS[odds_key]
    expected  = len(combos)
    css_class = next(t["css"] for t in ODDS_TYPES if t["key"] == odds_key)

    # ── 方法1: BeautifulSoup ──────────────────────────────
    try:
        from bs4 import BeautifulSoup
        result = _bs4_parse(html, combos, css_class, odds_key)
        if len(result) >= expected * 0.9:
            return result
        # 件数不足なら方法2へ
        print(f"    ⚠ BS4解析: {len(result)}/{expected}件 → 正規表現にフォールバック",
              flush=True)
    except ImportError:
        pass  # bs4未インストール → 方法2へ

    # ── 方法2: 正規表現 class属性マッチ ──────────────────
    result = _regex_class_parse(html, combos, css_class)
    if len(result) >= expected * 0.9:
        return result

    print(f"    ⚠ 正規表現解析: {len(result)}/{expected}件 → 数値順序マッピングにフォールバック",
          flush=True)

    # ── 方法3: 数値トークン順序マッピング ──────────────
    return _regex_token_parse(html, combos)


def _bs4_parse(html: str, combos: list, css_class: str,
               odds_key: str = "") -> dict[str, float]:
    """
    BeautifulSoupでオッズを取得。odds_key で直接専用パーサーへ委譲する。

    odds_key を渡すことでHTMLの構造判定に依存せず確実にパーサーを選択する。
    odds_key 不明時のみ HTML の tbody クラスから推定する（後方互換）。
    """
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")

    # odds_key が明示されていれば直接対応パーサーへ（HTML構造判定不要）
    _dispatch = {
        "3t":  _bs4_parse_3t,
        "3f":  _bs4_parse_3f,
        "2t":  _bs4_parse_2t,
        "2f":  _bs4_parse_2f,
        "tan": _bs4_parse_tan,
    }
    if odds_key in _dispatch:
        return _dispatch[odds_key](soup)

    # ── 後方互換: odds_key 不明時は tbody クラスから推定 ──────────────────
    if soup.find("tbody", class_=re.compile(r"is-p3-\d+")):
        return _bs4_parse_3t(soup)
    if soup.find("tbody", class_=re.compile(r"is-p3f-\d+")):
        return _bs4_parse_3f(soup)
    if soup.find("tbody", class_=re.compile(r"is-p2-\d+")):
        return _bs4_parse_2t(soup)
    if soup.find("tbody", class_=re.compile(r"is-p2f-\d+")):
        return _bs4_parse_2f(soup)
    if soup.find("tbody", class_=re.compile(r"is-p1-\d+")):
        return _bs4_parse_tan(soup)

    # ── フォールバック（構造不明時）──────────────────────────────────────────
    return _bs4_parse_generic(soup, combos, css_class)


def _bs4_parse_generic(soup, combos: list, css_class: str) -> dict[str, float]:
    """構造不明時のフォールバック: oddsPointセルを順番にcomboへマッピング"""
    cells = soup.find_all("td", class_=lambda c: c and (css_class in c.split() if c else False))
    if len(cells) < len(combos) * 0.9:
        cells = [td for td in soup.find_all("td")
                 if _is_odds_text(td.get_text(strip=True))]
    odds = {}
    for idx, combo in enumerate(combos):
        if idx >= len(cells):
            break
        txt = cells[idx].get_text(strip=True).replace(",", "")
        val = _to_float(txt)
        if val is not None:
            odds[_combo_key(combo)] = val
    return odds


def _expand_grid(tbody) -> list:
    """
    tbody の rowspan を展開して仮想グリッド grid[row][col] を返す。
    各セルは (classes_list, text_str) のタプル。
    """
    rows = tbody.find_all("tr")
    MAX_COLS = 18
    grid = [[None] * MAX_COLS for _ in range(len(rows))]
    for r, tr in enumerate(rows):
        tds = tr.find_all("td")
        col = 0
        td_i = 0
        while col < MAX_COLS and td_i < len(tds):
            # rowspan 展開済みのセルをスキップ
            while col < MAX_COLS and grid[r][col] is not None:
                col += 1
            if col >= MAX_COLS:
                break
            td = tds[td_i]; td_i += 1
            rs = int(td.get("rowspan", 1))
            cs = int(td.get("colspan", 1))
            val = (td.get("class") or [], td.get_text(strip=True))
            for dr in range(rs):
                for dc in range(cs):
                    if r + dr < len(rows) and col + dc < MAX_COLS:
                        grid[r + dr][col + dc] = val
            col += cs
    return grid


def _bs4_parse_3t(soup) -> dict[str, float]:
    """
    3連単専用パーサー。

    【実際のHTML構造 (boatrace.jp)】
      - tbody class="is-p3-0" が1つのみで全120通りを格納
      - thead class="is-p15-N" の th(艇番セル, is-boatColorN) が
        左→右の「1着列グループ順」を示す（例: 1,2,3,4,5,6）
      - tbody は 20行（2着5グループ×4行）× 18列（6列グループ×3セット）
      - 各列グループ(3列) = [2着固定(rowspan=4), 3着変動, odds]
        - 左端列グループの2着固定セルは is-borderLeftNone クラス付き
        - 1着番号はthead列グループ順で左から first_order[0..5]
      - キー: "1着-2着-3着"
    """
    odds = {}

    tbody = soup.find("tbody", class_=re.compile(r"is-p3-\d+"))
    if not tbody:
        return odds

    # thead の is-p15-N から1着の列順を取得
    # th のうち is-boatColorN かつ is-borderLeftNone でないセルが艇番
    thead = soup.find("thead", class_=re.compile(r"is-p15"))
    first_order = []
    if thead:
        for th in thead.find_all("th"):
            cls = th.get("class") or []
            txt = th.get_text(strip=True)
            if (txt.isdigit() and 1 <= int(txt) <= 6
                    and "is-borderLeftNone" not in cls):
                first_order.append(int(txt))

    # fallback: 順番通り [1,2,3,4,5,6]
    if len(first_order) != 6:
        first_order = list(range(1, 7))

    # rowspan を展開してグリッドを構築
    grid = _expand_grid(tbody)

    # 各行について: 列グループ i (base=i*3) ごとに読み取る
    #   grid[r][base+0] = 2着番号 (rowspan=4 固定セル)
    #   grid[r][base+1] = 3着番号 (変動セル)
    #   grid[r][base+2] = oddsPoint (変動セル)
    for r, row in enumerate(grid):
        for i, first in enumerate(first_order):
            base = i * 3
            second_cell = row[base]
            third_cell  = row[base + 1]
            odds_cell   = row[base + 2]
            if not (second_cell and third_cell and odds_cell):
                continue
            second_txt = second_cell[1]
            third_txt  = third_cell[1]
            odds_txt   = odds_cell[1]
            if not (second_txt.isdigit() and third_txt.isdigit()):
                continue
            second = int(second_txt)
            third  = int(third_txt)
            val = _to_float(odds_txt)
            if val and len({first, second, third}) == 3:
                key = f"{first}-{second}-{third}"
                odds[key] = val

    return odds


def _read_boat_odds_pairs(tbody) -> list:
    """
    tbody のグリッドを展開して ((艇番A, 艇番B), オッズ値) のリストを返す汎用ヘルパー。
    rowspan付きの固定セルと変動セルをペアにして返す。
    """
    grid = _expand_grid(tbody)
    pairs = []
    for row in grid:
        boat_nums = []
        odds_val  = None
        for cell in row:
            if cell is None:
                continue
            classes, text = cell
            text = text.strip()
            if text.isdigit() and 1 <= int(text) <= 6:
                n = int(text)
                if n not in boat_nums:
                    boat_nums.append(n)
            elif classes and "oddsPoint" in classes:
                odds_val = _to_float(text.replace(",", ""))
        if len(boat_nums) >= 2 and odds_val is not None:
            pairs.append(((boat_nums[0], boat_nums[1]), odds_val))
    return pairs


def _bs4_parse_3f(soup) -> dict[str, float]:
    """
    3連複専用パーサー。
    構造: tbody is-p3f-N → N+1 = 大きい艇番グループ
    各行: rowspan付き「中」艇番 + 「小」艇番 + oddsPoint
    キー: 小-中-大（昇順）
    """
    odds = {}
    for tbody in soup.find_all("tbody", class_=re.compile(r"is-p3f-\d+")):
        cls_match = re.search(r"is-p3f-(\d+)", " ".join(tbody.get("class", [])))
        if not cls_match:
            continue
        large = int(cls_match.group(1)) + 1

        pairs = _read_boat_odds_pairs(tbody)
        for (mid, small), val in pairs:
            if val is not None and len({large, mid, small}) == 3:
                combo = tuple(sorted([large, mid, small]))
                key = _combo_key(combo)
                odds[key] = val
    return odds


def _bs4_parse_2t(soup) -> dict[str, float]:
    """
    2連単専用パーサー。
    構造: tbody is-p2-N → N+1 = 1着艇番
    各行: rowspan付き「1着」 + 「2着」 + oddsPoint
    キー: 1着-2着
    """
    odds = {}
    for tbody in soup.find_all("tbody", class_=re.compile(r"is-p2-\d+")):
        cls_match = re.search(r"is-p2-(\d+)", " ".join(tbody.get("class", [])))
        if not cls_match:
            continue
        first = int(cls_match.group(1)) + 1

        pairs = _read_boat_odds_pairs(tbody)
        for (_, second), val in pairs:
            if val is not None and first != second:
                key = f"{first}-{second}"
                odds[key] = val
    return odds


def _bs4_parse_2f(soup) -> dict[str, float]:
    """
    2連複専用パーサー。
    構造: tbody is-p2f-N → N+1 = 大きい方の艇番
    各行: rowspan付き「大」艇番 + 「小」艇番 + oddsPoint
    キー: 小-大（昇順）
    """
    odds = {}
    for tbody in soup.find_all("tbody", class_=re.compile(r"is-p2f-\d+")):
        cls_match = re.search(r"is-p2f-(\d+)", " ".join(tbody.get("class", [])))
        if not cls_match:
            continue
        large = int(cls_match.group(1)) + 1

        pairs = _read_boat_odds_pairs(tbody)
        for (_, small), val in pairs:
            if val is not None and large != small:
                combo = (min(large, small), max(large, small))
                key = _combo_key(combo)
                odds[key] = val
    return odds


def _bs4_parse_tan(soup) -> dict[str, float]:
    """
    単勝専用パーサー。
    構造: tbody is-p1-N → N+1 = 艇番
    各行: 艇番セル + oddsPoint（rowspanなしのシンプル構造）
    """
    odds = {}
    for tbody in soup.find_all("tbody", class_=re.compile(r"is-p1-\d+")):
        cls_match = re.search(r"is-p1-(\d+)", " ".join(tbody.get("class", [])))
        if not cls_match:
            continue
        boat = int(cls_match.group(1)) + 1

        # oddsPointセルを探す
        for td in tbody.find_all("td", class_=lambda c: c and "oddsPoint" in c.split() if c else False):
            val = _to_float(td.get_text(strip=True).replace(",", ""))
            if val is not None:
                odds[str(boat)] = val
                break  # 1tbodyに1オッズ
    return odds



def _regex_class_parse(html: str, combos: list, css_class: str) -> dict[str, float]:
    """正規表現でclass属性を持つtdのテキストを抽出しcomboにマッピング"""
    # <td class="oddsPoint3t ...">12.3</td> のパターン
    pattern = rf'class="[^"]*{re.escape(css_class)}[^"]*"[^>]*>\s*([0-9,]+(?:\.[0-9]+)?)\s*<'
    values = re.findall(pattern, html)

    # 単純なクラスマッチで取れない場合：tdのテキストだけ順番に抽出
    if len(values) < len(combos) * 0.5:
        # odds_Xで始まるセクションを切り出し
        section = _extract_odds_section(html, css_class)
        values = re.findall(r'>([0-9,]+\.[0-9]+)<', section)

    odds = {}
    for idx, combo in enumerate(combos):
        if idx >= len(values):
            break
        val = _to_float(values[idx].replace(",", ""))
        if val is not None:
            odds[_combo_key(combo)] = val
    return odds


def _regex_token_parse(html: str, combos: list) -> dict[str, float]:
    """
    HTMLから全数値を抽出し、combo数分のオッズを順序でマッピング。
    最後の手段だが、ページに他の数値が混在するため精度は低い。
    """
    # オッズっぽい数値（小数点あり or 10以上）を抽出
    tokens = re.findall(r'\b(\d{1,4}(?:\.\d{1,2})?)\b', html)
    # 艇番(1-6)を除いた数値をオッズ候補とみなす
    odds_candidates = []
    for t in tokens:
        v = _to_float(t)
        if v is not None and (v > 6.0 or (v > 1.0 and "." in t)):
            odds_candidates.append(v)

    odds = {}
    for idx, combo in enumerate(combos):
        if idx >= len(odds_candidates):
            break
        odds[_combo_key(combo)] = odds_candidates[idx]
    return odds


def _extract_odds_section(html: str, css_class: str) -> str:
    """オッズテーブル部分のHTMLを切り出す"""
    # css_classが最初に登場してから、次の大きなセクション区切りまでを返す
    start = html.find(css_class)
    if start == -1:
        return html
    end = html.find("</table>", start)
    return html[start: end + 10] if end != -1 else html[start: start + 50000]


def _is_odds_text(txt: str) -> bool:
    """テキストがオッズ値らしいか判定（整数の艇番1〜6は除外）"""
    try:
        v = float(txt.replace(",", ""))
        # 小数点ありのみ許可（艇番「1」〜「6」などの整数を除外）
        return v >= 1.0 and "." in txt
    except ValueError:
        return False


def _to_float(txt: str) -> Optional[float]:
    """文字列をfloatに変換。失敗時はNone。
    締切前の範囲表示（例: "1.4-1.7"）は上限値を採用。
    """
    try:
        s = txt.replace(",", "").strip()
        # 範囲表示 "min-max" → 上限値（より安全な方）を採用
        m = re.match(r"(\d+\.\d+)-(\d+\.\d+)$", s)
        if m:
            s = m.group(2)
        v = float(s)
        return v if v > 0 else None
    except (ValueError, AttributeError):
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 1レース・1種別のオッズ取得
# ─────────────────────────────────────────────────────────────────────────────

def fetch_odds_one(jcd: str, rno: int, hd: str, odds_key: str,
                   verbose: bool = True) -> dict[str, float]:
    """
    1レース・1種別のオッズを取得して返す。

    Parameters
    ----------
    jcd      : 場コード（例: "05"）
    rno      : レース番号（1〜12）
    hd       : 日付 YYYYMMDD
    odds_key : "3t" / "3f" / "2t" / "2f" / "tan"

    Returns
    -------
    dict  {"1-2-3": 12.5, ...}  ※取得失敗時は空dict
    """
    ot = next((t for t in ODDS_TYPES if t["key"] == odds_key), None)
    if ot is None:
        raise ValueError(f"未対応の種別: {odds_key}")

    url = (f"https://www.boatrace.jp/owpc/pc/race/{ot['endpoint']}"
           f"?rno={rno}&jcd={jcd}&hd={hd}")
    try:
        html   = _fetch_html(url)
        result = _parse_odds_page(html, odds_key)
        if verbose:
            print(f"    ✓ {odds_key} {len(result)}/{ot['count']}件", flush=True)
        return result
    except Exception as e:
        if verbose:
            print(f"    ✕ {odds_key} 取得失敗: {e}", flush=True)
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# 1レース・全種別まとめて取得
# ─────────────────────────────────────────────────────────────────────────────

def fetch_race_all_odds(jcd: str, rno: int, hd: str,
                        verbose: bool = True,
                        mins_to_deadline: Optional[float] = None) -> dict[str, dict]:
    """
    1レース分の全種別オッズを取得。

    Parameters
    ----------
    mins_to_deadline : 締め切りまでの残り分数（Noneなら優先度判定なし）
                       優先度に応じてリクエスト間隔・取得種別を自動調整する。

    取得種別とリクエスト間隔の選択ルール:
      締め切り20分以内（最優先）: 全5種別 / 間隔 1.5秒
      締め切り20〜60分（通常）  : 全5種別 / 間隔 3.0秒
      締め切り60分以上（低優先）: 3t のみ / 間隔 3.0秒
    """
    from datetime import datetime

    # 優先度に応じた設定を決定
    if mins_to_deadline is not None and mins_to_deadline <= ULTRA_PRIORITY_MINUTES:
        # 締め切り5分以内: 3tのみ・最速間隔（巡回速度を最優先）
        target_types = [ot for ot in ODDS_TYPES if ot["key"] == "3t"]
        wait = INTER_REQ_WAIT_PRIORITY
        tier = "超優先(3tのみ)"
    elif mins_to_deadline is None or mins_to_deadline <= PRIORITY_MINUTES:
        target_types = ODDS_TYPES
        wait = INTER_REQ_WAIT_PRIORITY
        tier = "最優先" if mins_to_deadline is not None else "時刻不明"
    elif mins_to_deadline <= LOW_PRIORITY_MINUTES:
        target_types = ODDS_TYPES
        wait = INTER_REQ_WAIT_NORMAL
        tier = "通常"
    else:
        target_types = [ot for ot in ODDS_TYPES if ot["key"] == "3t"]
        wait = INTER_REQ_WAIT_NORMAL
        tier = "低優先(3tのみ)"

    if verbose:
        mins_str = f"{mins_to_deadline:.0f}分前" if mins_to_deadline is not None else "時刻不明"
        print(f"  取得: jcd={jcd} R{rno}  [{tier} / 締切{mins_str} / 間隔{wait}秒]", flush=True)

    # 既存JSONがあれば読み込んで土台にする（低優先時に他種別を保持するため）
    result: dict = {}
    slug = next((s for v, s in VENUE_SLUG.items() if VENUE_JCD.get(v) == jcd), None)
    if slug:
        existing_path = ODDS_DIR / f"odds_{slug}_{hd}_R{int(rno):02d}.json"
        if existing_path.exists():
            try:
                with open(existing_path, encoding="utf-8") as f:
                    result = json.load(f)
            except Exception:
                result = {}

    # 取得・上書き
    for ot in target_types:
        result[ot["key"]] = fetch_odds_one(jcd, rno, hd, ot["key"], verbose)
        time.sleep(wait)

    result["fetched_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return result


# ─────────────────────────────────────────────────────────────────────────────
# 全会場・全レース取得（auto_push.py から呼ぶ）
# ─────────────────────────────────────────────────────────────────────────────

def fetch_all_races(venues_dict: dict[str, str],
                    deadline_map: Optional[dict] = None,
                    verbose: bool = True) -> tuple[list, int, bool]:
    """
    複数会場の全レースオッズを「1巡」取得してJSONに保存する。

    【設計方針】
      この関数は while True を持たない。繰り返しループは呼び出し元
      （auto_push.py の _odds_loop_worker）が管理する。
      これにより、スレッド死亡時の検知・再起動が呼び出し元で可能になる。

    【取得順の優先ルール】
      締め切り20分前以内のレースを最優先し、それ以外は締め切りが
      近い順（残り時間昇順）で取得する。
      締め切り済み or 結果JSON確定済みのレースは除外。

    Parameters
    ----------
    venues_dict  : {"常滑": "2026-05-09", "鳴門": "2026-05-09", ...}
    deadline_map : {venue: {rno: "HH:MM"}} 形式の締切時刻マップ（省略可）
                   渡された場合、締切前のレースのみ取得対象とする。
                   渡されない場合は全レースを一巡して終了。

    Returns
    -------
    (saved, next_wait_sec, has_active)
      saved          : 保存したファイルパスのリスト
      next_wait_sec  : 次巡まで待機すべき秒数（呼び出し元がsleepする）
      has_active     : アクティブなレースが残っているか（False なら終了）
    """
    from datetime import datetime

    ODDS_DIR.mkdir(exist_ok=True)
    saved = []

    def _minutes_to_deadline(dl_dt) -> Optional[float]:
        if dl_dt is None:
            return None
        return (dl_dt - datetime.now()).total_seconds() / 60

    def _sort_key(race_tuple):
        """
        ソートキー: (優先グループ, 締め切りまでの残り時間)
          グループ0 = 締め切り20分前以内（残り時間昇順）
          グループ1 = それ以外の締め切り前（残り時間昇順）
          グループ2 = deadline不明（最後）
        """
        _, _, _, _, _, dl_dt = race_tuple
        mins = _minutes_to_deadline(dl_dt)
        if mins is None:
            return (2, 0)
        if mins < 0:
            return (3, mins)          # 締め切り済み（絞り込み後は通常出現しない）
        if mins <= PRIORITY_MINUTES:
            return (0, mins)          # 最優先: 残り時間が短い順
        return (1, mins)              # 通常: 締め切りが近い順

    # ── 全対象レースをフラットリストに展開 ──────────────────────────────────
    # 各要素: (venue, jcd, slug, hd, rno, deadline_dt or None)
    all_races = []
    for venue, date_str in venues_dict.items():
        jcd  = VENUE_JCD.get(venue)
        slug = VENUE_SLUG.get(venue)
        if not jcd or not slug:
            print(f"  ⚠ 未対応の会場: {venue}", flush=True)
            continue

        hd = date_str.replace("-", "")
        venue_deadlines = (deadline_map or {}).get(venue, {})

        for rno in range(1, 13):
            dl_str = venue_deadlines.get(rno) or venue_deadlines.get(str(rno))
            dl_dt  = None
            if dl_str:
                try:
                    dl_dt = datetime.strptime(f"{date_str} {dl_str}", "%Y-%m-%d %H:%M")
                except ValueError:
                    pass
            all_races.append((venue, jcd, slug, hd, rno, dl_dt))

    # ── deadline_map なし → 全レースを一巡して終了（従来互換モード）──────────
    if not deadline_map:
        for venue, jcd, slug, hd, rno, _ in all_races:
            result_json = RESULT_DIR / f"result_{slug}_{hd}_R{rno:02d}.json"
            if result_json.exists():
                if verbose:
                    print(f"  スキップ: {venue} R{rno}（確定済み）", flush=True)
                continue
            data  = fetch_race_all_odds(jcd, rno, hd, verbose)
            fpath = _save_odds(slug, hd, rno, data)
            saved.append(fpath)
        return saved, 0, False   # 互換モードは繰り返し不要

    # ── deadline_map あり → アクティブレースを1巡取得して返す ────────────────
    now = datetime.now()

    # ── レースを 3 種類に分類 ────────────────────────────────────────────────
    # active      : 締め切り前（通常取得対象）
    # post_dl     : 締め切り後 FINAL_ODDS_WINDOW_MINUTES 以内（確定オッズ取得対象）
    # completed   : 確定済み or 締め切りから時間が経ちすぎ（スキップ）
    #
    # 【取得開始タイミングのルール】
    #   R1 のみ : 締め切り30分前になるまで取得しない（開幕前から叩くのを防止）
    #   R2以降  : 前レース（rno-1）の締め切りを過ぎていれば取得開始
    #             （前レースの締切時刻が不明な場合は rno==1 と同様に30分前ルールを適用）
    R1_FETCH_START_MINUTES = 30   # 1レース目：締め切り何分前から取得開始するか

    # 会場ごとの全締切時刻を rno → dl_dt で引けるよう整理（前レース判定に使う）
    # all_races はこの時点で全会場・全レース含むため venue+rno でインデックス化
    dl_by_venue_rno: dict[tuple, Optional[object]] = {
        (r[0], r[4]): r[5] for r in all_races  # (venue, rno) -> dl_dt
    }

    active  = []
    post_dl = []
    for race in all_races:
        venue, jcd, slug, hd, rno, dl_dt = race

        # result_*.json が存在する → 払い戻し確定済みなので完全スキップ
        result_json = RESULT_DIR / f"result_{slug}_{hd}_R{rno:02d}.json"
        if result_json.exists():
            continue

        if dl_dt is None:
            # deadline_map に会場が載っているのに時刻が取れなかった → スキップ
            # （deadline_map 自体にない会場は互換モードで処理済みのためここには来ない）
            if verbose:
                print(f"  スキップ: {venue} R{rno}（締切時刻取得不可）", flush=True)
            continue

        mins = _minutes_to_deadline(dl_dt)  # 正 = 締め切り前, 負 = 締め切り後

        if mins > 0:
            # ── 取得開始タイミングチェック ──────────────────────────────────
            # R1: 締め切り30分前になるまでスキップ
            if rno == 1:
                if mins > R1_FETCH_START_MINUTES:
                    if verbose:
                        print(f"  スキップ: {venue} R{rno}（締切{mins:.0f}分前・開始待ち[30分前から]）",
                              flush=True)
                    continue
            else:
                # R2以降: 前レース(rno-1)の締め切りを過ぎているか確認
                prev_dl_dt = dl_by_venue_rno.get((venue, rno - 1))
                if prev_dl_dt is not None:
                    prev_mins = _minutes_to_deadline(prev_dl_dt)
                    if prev_mins > 0:
                        # 前レースがまだ締め切られていない → このレースもスキップ
                        if verbose:
                            print(f"  スキップ: {venue} R{rno}"
                                  f"（前レース R{rno-1} 締切まで{prev_mins:.0f}分）",
                                  flush=True)
                        continue
                else:
                    # 前レースの締切時刻が不明 → 30分前ルールにフォールバック
                    if mins > R1_FETCH_START_MINUTES:
                        if verbose:
                            print(f"  スキップ: {venue} R{rno}"
                                  f"（前レースR{rno-1}締切不明・締切{mins:.0f}分前・30分前ルール適用）",
                                  flush=True)
                        continue
            # ────────────────────────────────────────────────────────────────
            # 締め切り前かつ開始条件を満たした → 通常取得
            active.append(race)
        elif abs(mins) <= FINAL_ODDS_WINDOW_MINUTES:
            # 締め切り後 FINAL_ODDS_WINDOW_MINUTES 以内 → 確定オッズ取得待ち
            post_dl.append(race)
        # それ以上経過している場合は無視（時間切れ）

    # アクティブ・確定待ちが両方なければ終了を通知
    if not active and not post_dl:
        if verbose:
            print("✅ 全レース締め切り or 確定済み。", flush=True)
        return saved, 0, False

    # ── 確定オッズ取得（締め切り後レース）──────────────────────────────────
    if post_dl:
        if verbose:
            print(f"\n🏁 確定オッズ取得対象: {len(post_dl)}レース", flush=True)
        for venue, jcd, slug, hd, rno, dl_dt in post_dl:
            fpath = fetch_final_odds(jcd, rno, hd, slug, verbose)
            if fpath:
                saved.append(fpath)

    # 通常取得対象がなければここで終了
    if not active:
        if verbose:
            print("✅ 締め切り前レースなし（確定オッズ処理のみ）。", flush=True)
        return saved, 60, bool(post_dl)

    # 優先順でソート（締め切りが近い順・最優先グループ優先）
    active.sort(key=_sort_key)

    if verbose:
        print(f"\n📋 今巡の取得対象: {len(active)}レース（優先順）", flush=True)

    # ── 1巡: アクティブレースを優先順に取得 ─────────────────────────────────
    for venue, jcd, slug, hd, rno, dl_dt in active:
        now = datetime.now()

        # 巡回中に締め切りを過ぎた場合: 確定オッズ取得に委ねるためスキップ
        if dl_dt is not None and dl_dt <= now:
            if verbose:
                print(f"  スキップ: {venue} R{rno}（巡回中に締め切り過ぎ → 次巡で確定取得）",
                      flush=True)
            continue

        mins = _minutes_to_deadline(dl_dt)
        priority_tag = "🔴優先" if (mins is not None and mins <= PRIORITY_MINUTES) else "  "

        if verbose:
            mins_str = f"{mins:.0f}分後" if mins is not None else "時刻不明"
            print(f"  {priority_tag} {venue} R{rno}（締切{mins_str}）", flush=True)

        data  = fetch_race_all_odds(jcd, rno, hd, verbose, mins_to_deadline=mins)
        fpath = _save_odds(slug, hd, rno, data)
        saved.append(fpath)

    # ── 次巡までの待機時間を計算して返す ────────────────────────────────────
    # 直近の締め切りまでの残り時間で決定する（サーバー負荷を抑えつつ鮮度を確保）
    #   5分以内レースあり  → 15秒（超優先・3tのみ巡回で高速化）
    #   20分以内レースあり → 30秒（オッズ変動が大きいため短めに）
    #   20〜60分レースのみ → 90秒（通常ペース）
    #   60分超のみ        → 180秒（低優先・サーバー負荷軽減）
    now = datetime.now()
    remaining_mins_list = [
        (dl - now).total_seconds() / 60
        for _, _, _, _, _, dl in active
        if dl is not None and dl > now
    ]
    if remaining_mins_list:
        next_dl_mins = min(remaining_mins_list)
        if next_dl_mins <= ULTRA_PRIORITY_MINUTES:
            next_wait_sec = 15
        elif next_dl_mins <= PRIORITY_MINUTES:
            next_wait_sec = 30
        elif next_dl_mins <= LOW_PRIORITY_MINUTES:
            next_wait_sec = 90
        else:
            next_wait_sec = 180
    else:
        next_wait_sec = 180   # deadline不明のみ残っている場合

    if verbose:
        print(f"  ⏳ 次巡まで {next_wait_sec}秒待機\n", flush=True)

    return saved, next_wait_sec, True   # has_active=True → 呼び出し元が継続判断


def fetch_final_odds(jcd: str, rno: int, hd: str, slug: str,
                     verbose: bool = True) -> Optional[Path]:
    """
    締め切り後の「確定オッズ」を取得して JSON に上書き保存する。

    boatrace.jp は締め切り後もオッズページを公開し続け、
    レース確定後は払い戻し確定値に更新される。
    この関数は通常取得と同じエンドポイントから全5種別を取得し、
    既存の odds_*.json に "final": true フラグを付けて上書きする。

    Returns
    -------
    Path : 保存したファイルパス（スキップ or 失敗時は None）
    """
    existing_path = ODDS_DIR / f"odds_{slug}_{hd}_R{int(rno):02d}.json"

    # 既に確定取得済みならスキップ
    if existing_path.exists():
        try:
            with open(existing_path, encoding="utf-8") as f:
                existing = json.load(f)
            if existing.get("final"):
                if verbose:
                    print(f"    スキップ: {slug} R{rno}（確定オッズ取得済み）", flush=True)
                return None
        except Exception:
            pass

    if verbose:
        print(f"  🏁 確定オッズ取得: jcd={jcd} R{rno}", flush=True)

    # 全5種別を取得（締め切り後は変動なしのため通常間隔で十分）
    from datetime import datetime
    result: dict = {}
    for ot in ODDS_TYPES:
        result[ot["key"]] = fetch_odds_one(jcd, rno, hd, ot["key"], verbose)
        time.sleep(INTER_REQ_WAIT_NORMAL)

    result["fetched_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    result["final"] = True   # 確定済みフラグ

    fpath = _save_odds(slug, hd, rno, result)
    if verbose:
        print(f"  ✅ 確定オッズ保存: {fpath.name}", flush=True)
    return fpath


def _save_odds(slug: str, date_nd: str, rno: int, data: dict) -> Path:
    """odds_data/{slug}_{YYYYMMDD}_R{XX}.json に保存"""
    ODDS_DIR.mkdir(exist_ok=True)
    fname = f"odds_{slug}_{date_nd}_R{int(rno):02d}.json"
    fpath = ODDS_DIR / fname
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    return fpath


# ─────────────────────────────────────────────────────────────────────────────
# index.html への ODDS_DATA 埋め込み（auto_push.py から呼ぶ）
# ─────────────────────────────────────────────────────────────────────────────

def inject_odds_to_html(index_html_path: Optional[Path] = None,
                        verbose: bool = True) -> bool:
    """
    odds_data/*.json を読み込んで ODDS_DATA を index.html に埋め込む。

    index.html 内に以下のプレースホルダーが必要:
        /* __ODDS_DATA__ */
        const ODDS_DATA = {};

    埋め込み後の形式:
        const ODDS_DATA = {
          "常滑": {
            "6": {
              "3t":  {"1-2-3": 12.5, ...},
              "3f":  {...},
              "2t":  {...},
              "2f":  {...},
              "tan": {...}
            }
          }
        };
    """
    html_path = index_html_path or (SCRIPTS_DIR / "index.html")
    if not html_path.exists():
        print(f"  ✕ index.html が見つかりません: {html_path}", flush=True)
        return False

    # ── odds_data/ から全JSONを読み込んで集約 ──
    ODDS_DIR.mkdir(exist_ok=True)
    all_odds: dict = {}

    for fpath in sorted(ODDS_DIR.glob("odds_*.json")):
        # ファイル名: odds_{slug}_{YYYYMMDD}_R{XX}.json
        m = re.match(r"odds_([a-z]+)_(\d{8})_R(\d{2})\.json$", fpath.name)
        if not m:
            continue
        slug, _date_nd, rno_str = m.group(1), m.group(2), str(int(m.group(3)))
        venue = SLUG_VENUE.get(slug, slug)

        try:
            if fpath.stat().st_size == 0:
                print(f"  ⚠ 空ファイルを削除: {fpath.name}", flush=True)
                fpath.unlink(missing_ok=True)
                continue
            with open(fpath, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"  ⚠ 読み込み失敗 {fpath.name}: {e}", flush=True)
            continue

        # fetched_at はHTMLに埋め込まない（サイズ削減）、final フラグは保持
        race_data = {k: v for k, v in data.items() if k != "fetched_at"}
        all_odds.setdefault(venue, {})[rno_str] = race_data

    # ── index.html に埋め込み ──
    html = html_path.read_text(encoding="utf-8")
    new_block = (
        "const ODDS_DATA = "
        + json.dumps(all_odds, ensure_ascii=False, separators=(",", ":"))
        + ";"
    )

    if "const ODDS_DATA" in html:
        # 既存の宣言を置換（複数行にわたる可能性あり）
        html = re.sub(
            r"const ODDS_DATA\s*=\s*\{.*?\};",
            new_block,
            html,
            flags=re.DOTALL,
        )
    elif "/* __ODDS_DATA__ */" in html:
        # プレースホルダーの直後に挿入
        html = html.replace("/* __ODDS_DATA__ */",
                            f"/* __ODDS_DATA__ */\n{new_block}")
    else:
        print("  ⚠ ODDS_DATA のプレースホルダーが index.html に見つかりません。",
              flush=True)
        print("    index.html の適切な位置に以下を追加してください:", flush=True)
        print("      /* __ODDS_DATA__ */", flush=True)
        print("      const ODDS_DATA = {};", flush=True)
        return False

    html_path.write_text(html, encoding="utf-8")

    total = sum(len(v) for v in all_odds.values())
    if verbose:
        print(f"  ✓ ODDS_DATA埋め込み完了: {len(all_odds)}会場 / {total}レース分",
              flush=True)
    return True


# ─────────────────────────────────────────────────────────────────────────────
# コマンドライン実行
# ─────────────────────────────────────────────────────────────────────────────

def _cli_usage():
    print(__doc__)
    print("使用例:")
    print('  # 場コード+日付で全種別取得（R1〜R12）')
    print('  python fetch_odds.py --jcd 05 --hd 20260509')
    print()
    print('  # 特定レースのみ')
    print('  python fetch_odds.py --jcd 05 --hd 20260509 --rno 6')
    print()
    print('  # URLから直接（3連単のみ）')
    print('  python fetch_odds.py --url "https://www.boatrace.jp/owpc/pc/race/odds3t?rno=6&jcd=05&hd=20260509"')
    print()
    print('  # 会場名で指定')
    print('  python fetch_odds.py --venue 多摩川 --hd 20260509')


def _cli_print_result(result: dict, odds_key: str = "3t"):
    """取得結果を整形して表示"""
    data = result.get(odds_key, {})
    combos = COMBOS[odds_key]
    print(f"\n{'='*55}")
    print(f"  {odds_key} オッズ  ({len(data)}/{len(combos)}件)")
    print(f"{'='*55}")
    for combo in combos[:15]:
        key = _combo_key(combo)
        val = data.get(key)
        print(f"  {key}  : {val:.1f}倍" if val else f"  {key}  : —")
    if len(combos) > 15:
        print(f"  ... 他{len(combos)-15}件")
    print(f"\nfetched_at: {result.get('fetched_at', '—')}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="boatrace.jp オッズ取得ツール",
                                     add_help=True)
    parser.add_argument("--url",   help="オッズページURL（odds3tのみ対応）")
    parser.add_argument("--jcd",   help="場コード 2桁（例: 05）")
    parser.add_argument("--hd",    help="日付 YYYYMMDD（例: 20260509）")
    parser.add_argument("--rno",   type=int, help="レース番号（省略時: 全レース）")
    parser.add_argument("--venue", help="会場名（例: 多摩川）")
    parser.add_argument("--save",  action="store_true",
                        help="odds_data/ に JSON保存する")
    parser.add_argument("--inject",action="store_true",
                        help="index.html に ODDS_DATA を埋め込む（--saveと併用）")
    args = parser.parse_args()

    # ── URL指定モード ──
    if args.url:
        m = re.search(r"rno=(\d+).*?jcd=(\d+).*?hd=(\d{8})", args.url)
        if not m:
            m = re.search(r"jcd=(\d+).*?rno=(\d+).*?hd=(\d{8})", args.url)
            if m:
                jcd_, rno_, hd_ = m.group(1).zfill(2), int(m.group(2)), m.group(3)
            else:
                print("❌ URLからパラメータを取得できませんでした")
                sys.exit(1)
        else:
            rno_, jcd_, hd_ = int(m.group(1)), m.group(2).zfill(2), m.group(3)

        result = fetch_race_all_odds(jcd_, rno_, hd_)
        _cli_print_result(result)
        if args.save:
            slug_ = next((s for jcd, s in zip(VENUE_JCD.values(), VENUE_SLUG.values())
                         if jcd == jcd_), jcd_)
            fpath = _save_odds(slug_, hd_, rno_, result)
            print(f"\n💾 保存: {fpath}")
        sys.exit(0)

    # ── jcd / venue + hd モード ──
    jcd = args.jcd
    if not jcd and args.venue:
        jcd = VENUE_JCD.get(args.venue)
        if not jcd:
            print(f"❌ 未対応の会場名: {args.venue}")
            sys.exit(1)

    if not jcd or not args.hd:
        _cli_usage()
        sys.exit(1)

    jcd  = jcd.zfill(2)
    hd   = args.hd
    slug = next((VENUE_SLUG[v] for v, c in VENUE_JCD.items() if c == jcd), jcd)

    if args.rno:
        # 単一レース
        result = fetch_race_all_odds(jcd, args.rno, hd)
        _cli_print_result(result)
        if args.save:
            fpath = _save_odds(slug, hd, args.rno, result)
            print(f"\n💾 保存: {fpath}")
    else:
        # 全レース（R1〜R12）
        print(f"\n場コード={jcd} / {hd} / 全12レース取得開始\n")
        for rno in range(1, 13):
            result = fetch_race_all_odds(jcd, rno, hd)
            if args.save:
                fpath = _save_odds(slug, hd, rno, result)
                print(f"  💾 R{rno}: {fpath.name}")

    if args.inject:
        inject_odds_to_html()
