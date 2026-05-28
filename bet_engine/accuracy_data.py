"""
accuracy_data.py  v2
====================
accuracy_data.json から実績着率を返すユーティリティ。

【v2 強化点】
  - ⚠付きシンボルを独立して参照（◎⚠️は◎と別統計）
  - get_cross_rate(): crossデータ（評価×1着率レンジ）を返す
  - 会場別補正を全API に適用
"""
from __future__ import annotations
import json, os
from functools import lru_cache

def _find_json():
    """scripts/bet_engine/ → scripts/ → プロジェクトルート/ の順に探す"""
    here = os.path.dirname(os.path.abspath(__file__))
    base = here
    for _ in range(3):
        p = os.path.join(base, "accuracy_data.json")
        if os.path.exists(p):
            return p
        base = os.path.dirname(base)
    raise FileNotFoundError(
        f"accuracy_data.json が見つかりません（{here} および上位3フォルダを検索）"
    )
_JSON_PATH = _find_json()

@lru_cache(maxsize=1)
def get_stats() -> dict:
    with open(_JSON_PATH, encoding="utf-8") as f:
        return json.load(f)

def _strip_warn(sym: str) -> str:
    return sym.replace("⚠️","").replace("⚠","").strip()

def _has_warn(sym: str) -> bool:
    return "⚠" in sym

def _sym_lookup(axis: str, symbol: str, course: int, venue: str = "__ALL__") -> dict:
    """
    ⚠付きシンボルを独立参照。
    例: '◎⚠️' → まず '◎⚠️' で検索、なければ '◎' にフォールバック。
    venue指定があれば会場別データを優先、なければ全国。
    """
    d  = get_stats()
    ax = d.get("stats", {}).get(axis, {})

    # venue → fallback __ALL__
    vd_venue = ax.get(venue, {}) if venue != "__ALL__" else {}
    vd_all   = ax.get("__ALL__", {})

    def _lookup_in(vd):
        cd = vd.get(str(course), {})
        # ⚠付きを独立参照（key が完全一致 or ⚠正規化後）
        base = _strip_warn(symbol)
        warn_key = base + "⚠️"
        if _has_warn(symbol):
            # ⚠付きで検索 → なければベースにフォールバック
            return cd.get(warn_key) or cd.get(symbol) or cd.get(base) or {}
        return cd.get(base) or {}

    result = _lookup_in(vd_venue) or _lookup_in(vd_all)
    return result


def get_win_rate(
    axis:   str,
    symbol: str,
    course: int,
    place:  int = 1,
    venue:  str = "__ALL__",
) -> float | None:
    """実績着率 (0〜1)。place=123で複勝率。データなし→None。"""
    sd = _sym_lookup(axis, symbol, course, venue)
    if not sd: return None
    total = sum(sd.values())
    if total == 0: return None
    hits = sum(sd.get(str(p), 0) for p in [1,2,3]) if place == 123 else sd.get(str(place), 0)
    return hits / total


def get_baseline_rate(course: int, place: int = 1, venue: str = "__ALL__") -> float:
    """コース別の全体基準着率。"""
    d  = get_stats()
    cp = d.get("course_place", {})
    vd = cp.get(venue, cp.get("__ALL__", {})) if venue != "__ALL__" else cp.get("__ALL__", {})
    cd = vd.get(str(course), {})
    total = sum(cd.values())
    if total == 0: return 1/6
    hits = sum(cd.get(str(p), 0) for p in [1,2,3]) if place == 123 else cd.get(str(place), 0)
    return hits / total


def get_cross_rate(
    axis:    str,
    symbol:  str,
    win1_bin: str,
    course:  int = 1,
    place:   int = 1,
) -> float | None:
    """
    クロス集計（評価記号 × 1着率レンジ）での実績着率。

    axis    : "in_nige" or "aisho"
    symbol  : "◎" / "○" / "△" / "（なし）"
    win1_bin: "〜19%" / "20〜29%" / "30〜39%" / "40〜49%" / "50〜59%" / "60%〜"
    course  : in_nige=1固定、aisho=2〜6
    place   : 1〜6 or 123
    """
    d    = get_stats()
    base = _strip_warn(symbol)
    crs  = d.get("cross", {}).get(axis, {})

    if axis == "in_nige":
        sym_data = crs.get(base, crs.get(symbol, {}))
        bin_data = sym_data.get(win1_bin, {})
    else:
        # aisho: cross[aisho][course][symbol][bin][place]
        c_data   = crs.get(str(course), {})
        sym_data = c_data.get(base, c_data.get(symbol, {}))
        bin_data = sym_data.get(win1_bin, {})

    if not bin_data: return None
    total = sum(bin_data.values())
    if total == 0: return None
    hits = sum(bin_data.get(str(p), 0) for p in [1,2,3]) if place == 123 else bin_data.get(str(place), 0)
    return hits / total


def rate1_to_bin(rate1: float) -> str:
    """
    1号艇の実績1着率（0〜1）→ win1_bins のレンジ文字列。
    update_master.py や load_race.py のコース別1着率から算出する。
    """
    r = rate1 * 100
    if r >= 60: return "60%〜"
    if r >= 50: return "50〜59%"
    if r >= 40: return "40〜49%"
    if r >= 30: return "30〜39%"
    if r >= 20: return "20〜29%"
    return "〜19%"
