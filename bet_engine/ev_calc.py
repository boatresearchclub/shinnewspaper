#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ev_calc.py — 期待値（EV）計算モジュール
=========================================
boatrace.jp から3連単オッズをスクレイピングし、
recommend_bet の確率と掛け合わせて期待値を計算する。

EV = オッズ × 的中確率 - 1.0
  EV > 0 → 期待値プラス（長期的に儲かる）
  EV < 0 → 期待値マイナス（長期的に損する）

【使い方】
  from ev_calc import fetch_odds, calc_ev, suggest_by_ev
  odds = fetch_odds("鳴門", "5", "2026-03-21")
  ev_list = calc_ev(res["combos"], odds)
  suggestion = suggest_by_ev(ev_list)
"""
import re
import pathlib
import sys

_HERE    = pathlib.Path(__file__).parent
_SCRIPTS = _HERE.parent

# 会場コードマッピング
VENUE_JCD_MAP = {
    "桐生":"01","戸田":"02","江戸川":"03","平和島":"04",
    "多摩川":"05","浜名湖":"06","蒲郡":"07","常滑":"08",
    "津":"09","三国":"10","びわこ":"11","住之江":"12",
    "尼崎":"13","鳴門":"14","丸亀":"15","児島":"16",
    "宮島":"17","徳山":"18","下関":"19","若松":"20",
    "芦屋":"21","福岡":"22","唐津":"23","大村":"24",
}

def build_odds_url(venue: str, race_no, race_date: str) -> str | None:
    """boatrace.jpの3連単オッズURLを生成する"""
    jcd = VENUE_JCD_MAP.get(str(venue).strip())
    if not jcd:
        return None
    rno = int(race_no) if str(race_no).isdigit() else race_no
    hd  = str(race_date).replace("-","").replace("/","")
    if len(hd) != 8 or not hd.isdigit():
        return None
    return f"https://www.boatrace.jp/owpc/pc/race/odds3t?rno={rno}&jcd={jcd}&hd={hd}"


def fetch_odds(venue: str, race_no, race_date: str) -> dict | None:
    """
    boatrace.jp から3連単オッズを取得する。
    returns: {"1→2→3": float, ...} または None
    """
    url = build_odds_url(venue, race_no, race_date)
    if not url:
        print(f"  ⚠ 会場コード不明: {venue}")
        return None

    print(f"  🌐 オッズ取得中: {url}")

    # fetch_odds.py が scripts/ にあれば使う
    sys.path.insert(0, str(_SCRIPTS))
    try:
        from fetch_odds import fetch_odds_from_url_bs4, fetch_odds_from_url
        odds = fetch_odds_from_url_bs4(url) or fetch_odds_from_url(url)
        if odds:
            print(f"  ✅ オッズ取得完了 ({len(odds)}件)")
            return odds
    except ImportError:
        pass

    # fetch_odds.pyがなければ自前でスクレイピング
    try:
        import urllib.request
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=10) as res:
            html = res.read().decode("utf-8", errors="ignore")
        return _parse_odds_html(html)
    except Exception as e:
        print(f"  ❌ オッズ取得失敗: {e}")
        return None


def _parse_odds_html(html: str) -> dict | None:
    """
    boatrace.jp の3連単オッズページをパースする。
    返す形式: {"1→2→3": float, ...}
    """
    # 3連単オッズの抽出
    # HTMLパターン: <td class="oddsPoint">12.3</td> など
    odds = {}
    
    # boatrace.jpのオッズページ構造に合わせてパース
    # 1→2→3 の順にTDが並んでいる
    patterns = [
        r'(\d+\.\d+)',  # 数値
    ]
    
    # 全120通りの組み合わせを順番に抽出
    boats = [1,2,3,4,5,6]
    combos = []
    for a in boats:
        for b in boats:
            if b == a: continue
            for c in boats:
                if c == a or c == b: continue
                combos.append(f"{a}→{b}→{c}")
    
    # oRankの数値を抽出（boatrace.jpの形式）
    nums = re.findall(r'class="oddsPoint"[^>]*>([0-9.]+)<', html)
    if not nums:
        # 別パターン
        nums = re.findall(r'>([0-9]{1,5}\.[0-9])<', html)
    
    if len(nums) >= 120:
        for i, combo in enumerate(combos):
            try:
                odds[combo] = float(nums[i])
            except (ValueError, IndexError):
                pass
    
    if not odds:
        print("  ⚠ HTMLのパースに失敗しました")
        return None
    
    return odds


def calc_ev(combos: list[dict], odds_dict: dict) -> list[dict]:
    """
    各買い目の期待値を計算する。

    Parameters
    ----------
    combos    : recommend_bet.recommend() の "combos" リスト
    odds_dict : {"1→2→3": float, ...} 形式のオッズdict

    Returns
    -------
    list[dict] — 各combosに以下を追加してEV降順でソート:
        actual_odds : 実オッズ（取得できなければNone）
        ev          : 期待値 = オッズ × 確率 - 1.0
        ev_pct      : "+12.3%" 形式の文字列
        ev_positive : EVがプラスかどうか
    """
    result = []
    for c in combos:
        bet    = c["bet"]         # "1→2→3" 形式
        prob   = c.get("prob", 0)
        actual = odds_dict.get(bet) if odds_dict else None
        c2     = dict(c)

        if actual is not None and prob > 0:
            ev = actual * prob - 1.0
            c2["actual_odds"] = round(actual, 1)
            c2["ev"]          = round(ev, 4)
            c2["ev_pct"]      = f"{'+' if ev >= 0 else ''}{ev*100:.1f}%"
            c2["ev_positive"] = ev > 0
        else:
            c2["actual_odds"] = None
            c2["ev"]          = None
            c2["ev_pct"]      = "N/A"
            c2["ev_positive"] = False

        result.append(c2)

    result.sort(key=lambda x: (x["ev"] if x["ev"] is not None else -999), reverse=True)
    return result


def suggest_by_ev(combos_with_ev: list[dict],
                  min_ev: float = 0.0,
                  max_bets: int = 10) -> dict:
    """
    期待値プラスの組み合わせを返す。

    Parameters
    ----------
    combos_with_ev : calc_ev() の戻り値
    min_ev         : 最低期待値閾値（0.0 = EV+以上のみ）
    max_bets       : 最大買い目数

    Returns
    -------
    dict:
        bets       : 買い目リスト（EV降順）
        ev_detail  : 各買い目の詳細
        count      : 点数
        best_ev    : 最高EV
        skip       : True = 見送り推奨
        reason     : 判定理由
        odds_available : オッズが取得できたか
    """
    # オッズ取得できているか確認
    has_odds = any(c.get("actual_odds") is not None for c in combos_with_ev)

    if not has_odds:
        return {
            "bets": [], "ev_detail": [], "count": 0,
            "best_ev": None, "skip": True,
            "reason": "オッズ未取得 → EV計算不可",
            "odds_available": False,
        }

    positives = [c for c in combos_with_ev
                 if c.get("ev") is not None and c["ev"] > min_ev][:max_bets]

    best_any = next((c for c in combos_with_ev if c.get("ev") is not None), None)

    if not positives:
        best_str = (f"（最高EV: {best_any['ev_pct']} {best_any['bet']} "
                    f"オッズ{best_any['actual_odds']}倍）") if best_any else ""
        return {
            "bets": [], "ev_detail": [], "count": 0,
            "best_ev": best_any, "skip": True,
            "reason": f"EV+の組み合わせなし → 見送り推奨 {best_str}",
            "odds_available": True,
        }

    ev_detail = [
        {
            "bet":         c["bet"],
            "prob":        f"{c['prob']*100:.2f}%",
            "odds":        f"{c['actual_odds']}倍",
            "ev":          c["ev_pct"],
            "ev_value":    c["ev"],
        }
        for c in positives
    ]

    return {
        "bets":      [c["bet"] for c in positives],
        "ev_detail": ev_detail,
        "count":     len(positives),
        "best_ev":   positives[0],
        "skip":      False,
        "reason":    f"EV+が{len(positives)}点（最高: {positives[0]['ev_pct']} "
                     f"{positives[0]['bet']} オッズ{positives[0]['actual_odds']}倍）",
        "odds_available": True,
    }


# ── テスト用ダミーオッズ生成 ─────────────────────────────────
def make_dummy_odds(seed_combos: list[dict] = None) -> dict:
    """
    オッズが取得できないときのテスト用。
    理論オッズ（1/prob × 0.75）で近似したダミーを返す。
    """
    if not seed_combos:
        return {}
    odds = {}
    for c in seed_combos:
        prob = c.get("prob", 0)
        if prob > 0:
            # 理論オッズ = 1/prob × 控除率0.75
            theoretical = round(0.75 / prob, 1)
            odds[c["bet"]] = theoretical
    return odds


if __name__ == "__main__":
    # 動作テスト
    print("=== ev_calc.py 動作テスト ===\n")
    url = build_odds_url("鳴門", 5, "2026-03-21")
    print(f"URLテスト: {url}")
    
    # ダミーcomboでEV計算テスト
    dummy_combos = [
        {"bet": "1→2→3", "prob": 0.05},
        {"bet": "1→2→4", "prob": 0.04},
        {"bet": "3→2→1", "prob": 0.02},
        {"bet": "4→2→1", "prob": 0.01},
    ]
    dummy_odds = {
        "1→2→3": 20.0,   # 理論値15倍 → 過小評価
        "1→2→4": 25.0,   # 理論値18.75倍 → やや割安
        "3→2→1": 120.0,  # 理論値37.5倍 → 大幅割安
        "4→2→1": 50.0,   # 理論値75倍 → 割高
    }
    ev_list = calc_ev(dummy_combos, dummy_odds)
    print("\n期待値計算結果（EV降順）:")
    for c in ev_list:
        print(f"  {c['bet']}  確率{c['prob']*100:.1f}%  "
              f"オッズ{c['actual_odds']}倍  EV{c['ev_pct']}")
    
    suggestion = suggest_by_ev(ev_list)
    print(f"\n推奨: {suggestion['reason']}")
    for d in suggestion["ev_detail"]:
        print(f"  {d['bet']}  {d['prob']}  {d['odds']}  {d['ev']}")
