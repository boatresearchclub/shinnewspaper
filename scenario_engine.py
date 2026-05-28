# -*- coding: utf-8 -*-
"""
scenario_engine.py
==================
展開ストーリー＋買い目を「シナリオ分岐型」で一体生成するモジュール。

【設計思想】
  人間の頭の中にある8ステップ思考を、そのままコードの木構造に対応させる。

  ① 1号艇は逃げるか
      → s1_prob + escape_rank でシナリオ確率を確定
  ② 逃げるなら 2・3着は誰か          【シナリオA】
  ③ 逃げないなら 主役は誰か・決まり手は何か  【シナリオB-主役特定】
  ④ その決まり手なら 2・3着は誰か      【シナリオB-残存】
  ⑤ 主役が崩れたとき誰が浮上するか      【シナリオB-崩れ】
  ⑥ 崩れ後に1号が残す確率
  ⑦ 他の艇が展開を突いたとき          【シナリオB-漁夫】
  ⑧ A+Bを s1_prob 加重で統合 → 最終買い目

【既存コードとの対応】
  load_race.py の _suggest_3rentan  →  build_scenarios() が担う
  load_race.py の _generate_tenkai_story → generate_story() が担う

  load_race.py 側の変更は最小限：
    bet_suggestions = _suggest_3rentan(...)
    ↓
    from scenario_engine import build_scenarios, generate_story
    bet_suggestions = build_scenarios(results, race_judgment,
                                      tenkai_venue=..., tenkai_national=...,
                                      venue_stats=...)
    story = generate_story(bet_suggestions)

【出力 bet_suggestions の主要キー】
  s1_prob          : float  1号艇1着確率（確率モデル由来）
  scenario_a       : dict   逃げシナリオ詳細
  scenario_b       : dict   主役シナリオ詳細
  buy_list         : list   最終統合買い目（"1-3-2" 形式文字列）
  candidates       : list   買い目ごとの確率・シナリオ属性（既存互換）
  point_count      : int    買い目点数
  story            : str    展開ストーリー文章
  tenkai_pattern   : str    "A"/"B"/"C"/"D"（既存互換）
  skip             : bool   見送り推奨フラグ
  skip_reason      : str    見送り理由
"""

from __future__ import annotations
from typing import Any
import itertools
import math
from copy import copy
from dataclasses import dataclass, field


# ============================================================
# 会場特性ユーティリティ
# ============================================================

def _get_venue_c1_rate(venue_stats: dict | None, venue: str) -> float | None:
    """
    会場統計から 1コース1着率 を取得する。
    見つからなければ None を返す（呼び出し側でフォールバック）。
    """
    if not venue_stats:
        return None
    for key in ('c1_win_rate', '1c_win_rate', 'in_nige_rate', 'venue_c1_win_rate'):
        v = venue_stats.get(key)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
    return None


def _get_venue_kimete_dist(venue_stats: dict | None, course: int) -> dict[str, float]:
    """
    会場統計から 指定コースの決まり手確率分布 を返す。

    venue_stats に 'kimete_by_course' キーがある場合はそれを使う。
    なければコース別全国平均（実データ集計値）をフォールバックとして返す。

    Returns
    -------
    {決まり手: 確率} の dict（恵まれ・抜きは除外済み）
    """
    if venue_stats:
        kbc = venue_stats.get('kimete_by_course') or {}
        dist = kbc.get(str(course)) or kbc.get(course)
        if dist and isinstance(dist, dict):
            valid = {k: v for k, v in dist.items() if k not in ('恵まれ', '抜き')}
            total = sum(valid.values())
            if total > 0:
                return {k: v / total for k, v in valid.items()}

    # フォールバック: コース別全国平均実測値
    # 出典: ボートリサーチ_マスタ.xlsx 展開別残存_会場別 全24会場集計
    _NATIONAL_KIMETE: dict[int, dict[str, float]] = {
        2: {'差し': 0.62,  'まくり': 0.28,  'まくり差し': 0.10},
        3: {'まくり差し': 0.39, 'まくり': 0.39, '差し': 0.11},
        4: {'まくり': 0.48,  'まくり差し': 0.26, '差し': 0.18},
        5: {'まくり差し': 0.62, 'まくり': 0.20,  '差し': 0.06},
        6: {'まくり差し': 0.42, 'まくり': 0.28,  '差し': 0.13},
    }
    return _NATIONAL_KIMETE.get(course, {'まくり': 0.50, 'まくり差し': 0.30, '差し': 0.20})


def _decide_kimete_from_venue(
    main_course: str,
    venue_stats: dict | None,
) -> str:
    """
    主役の進入コースと会場決まり手分布から最も確率の高い決まり手を返す。

    1コースは常に「逃げ」。2〜6コースは会場実測データの最頻値を採用。
    """
    c = int(main_course) if str(main_course).isdigit() else 1
    if c == 1:
        return '逃げ'
    dist = _get_venue_kimete_dist(venue_stats, c)
    if not dist:
        return 'まくり'
    return max(dist, key=lambda k: dist[k])


def _calc_venue_trust(n_runs: int) -> float:
    """
    会場別出走数 → 信頼度（0〜1）。
    出走数  3走: 0.10  /  8走: 0.40  /  15走: 0.70  /  20走以上: 1.0
    """
    if n_runs is None or n_runs < 3:
        return 0.0
    return min(1.0, n_runs / 20.0)


# ============================================================
# RaceState  展開状態オブジェクト（設計書 §3-1）
# ============================================================

ALL_COURSES: frozenset[str] = frozenset({"1", "2", "3", "4", "5", "6"})

# 設計書 §4-2  コース「塞がれ」の物理モデル
# (決まり手, 攻撃コース) → 塞がれるコースのリスト
# 値は (コース, ペナルティ強度) のタプル
# ペナルティ強度: 1.0=確実, 0.7=高確率, 0.5=確率的, 0.3=弱い
_BLOCK_RULES: dict[tuple[str, str], list[tuple[str, float]]] = {
    ("差し",       "2"): [],                                            # 最内なので塞がれなし
    ("差し",       "3"): [("2", 0.5)],                                  # 3差し→2が内に絞られる
    ("差し",       "4"): [("3", 0.5), ("2", 0.3)],
    ("差し",       "5"): [("4", 0.5), ("3", 0.3)],
    ("差し",       "6"): [("5", 0.5), ("4", 0.3)],
    ("まくり",     "2"): [("1", 0.9)],                                  # 2まくり→1がほぼ確実に沈む
    ("まくり",     "3"): [("1", 0.9), ("2", 0.8)],                      # 3まくり→1・2が強く塞がれる
    ("まくり",     "4"): [("1", 0.7), ("2", 0.7), ("3", 0.5)],          # 4まくり→1・2は強く、3は中程度
    ("まくり",     "5"): [("1", 0.7), ("2", 0.7), ("3", 0.5), ("4", 0.5)],
    ("まくり",     "6"): [("1", 0.7), ("2", 0.7), ("3", 0.5), ("4", 0.5), ("5", 0.5)],
    ("まくり差し", "3"): [("2", 0.7)],                                  # 3まくり差し→2を塞ぐ
    ("まくり差し", "4"): [("3", 0.7), ("2", 0.3)],
    ("まくり差し", "5"): [("4", 0.7), ("3", 0.3)],
    ("まくり差し", "6"): [("5", 0.7), ("4", 0.3)],
}

# デフォルト（キーがない場合）: 攻撃コースより内側を確率的に塞ぐ
_BLOCKED_PENALTY_DEFAULT = 0.3   # 設計書 §7 の初期値


@dataclass
class RaceState:
    """
    ある展開が起きた後のレース状態（設計書 §3-1）。

    Attributes
    ----------
    active_courses   : 現在走路が生きている進入コースのset
    blocked_courses  : 前の展開で走路が塞がれたコースのset
    block_penalties  : コース → ペナルティ係数（0.0〜1.0、1.0=塞がれなし）
    event_log        : 起きた展開の記録リスト (attack_course, kimete, success)
    prob             : この状態に至る確率（0〜1）
    """
    active_courses:  frozenset[str]         = field(default_factory=lambda: frozenset(ALL_COURSES))
    blocked_courses: frozenset[str]         = field(default_factory=frozenset)
    block_penalties: dict[str, float]       = field(default_factory=dict)
    event_log:       list[tuple]            = field(default_factory=list)
    prob:            float                  = 1.0

    def penalty_of(self, course: str) -> float:
        """進入コースのペナルティ係数を返す（塞がれていなければ1.0）"""
        return self.block_penalties.get(course, 1.0)


# ============================================================
# apply_event  展開イベント適用（設計書 §3-2）
# ============================================================

def apply_event(
    state: RaceState,
    attack_course: str,
    kimete: str,
    success: bool,
) -> RaceState:
    """
    展開イベントを適用してRaceStateを更新する純粋関数。

    success=True  → 攻撃成立。attack_courseより内側が物理的に塞がれる
    success=False → 攻撃不発。attack_course自身が失速
    """
    new_blocked   = set(state.blocked_courses)
    new_penalties = dict(state.block_penalties)
    new_log       = list(state.event_log) + [(attack_course, kimete, success)]

    if success:
        # 攻撃成立: ルールに基づいてコースにペナルティを適用
        rules = _BLOCK_RULES.get((kimete, attack_course))
        if rules is not None:
            for c, strength in rules:
                # ペナルティが強い方を採用（複数イベントが重なる場合）
                current = new_penalties.get(c, 1.0)
                # 強度1.0(確実) → penalty=0.0, 強度0.5 → penalty=0.5 などに変換
                penalty_val = max(0.0, 1.0 - strength)
                new_penalties[c] = min(current, penalty_val)
                if penalty_val <= 0.2:
                    new_blocked.add(c)
        else:
            # デフォルト: 攻撃コースの内側を確率的に塞ぐ
            attack_int = int(attack_course) if attack_course.isdigit() else 99
            for c in ALL_COURSES:
                if c.isdigit() and int(c) < attack_int:
                    current = new_penalties.get(c, 1.0)
                    new_penalties[c] = min(current, _BLOCKED_PENALTY_DEFAULT)
    else:
        # 攻撃不発: 攻撃コース自身が失速
        new_blocked.add(attack_course)
        new_penalties[attack_course] = 0.0

    new_active = ALL_COURSES - frozenset(new_blocked)

    return RaceState(
        active_courses  = new_active,
        blocked_courses = frozenset(new_blocked),
        block_penalties = new_penalties,
        event_log       = new_log,
        prob            = state.prob,
    )


# ============================================================
# ユーティリティ
# ============================================================

def _safe(val: Any, default: float = 0.0) -> float:
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _wn(w) -> str:
    """艇番 → ➊〜➏（考察用・買い目表記とは別）"""
    return {"1": "➊", "2": "➋", "3": "➌", "4": "➍", "5": "➎", "6": "➏"}.get(str(w), f"{w}号")


def _pct(v) -> str:
    try:
        return f"{float(v) * 100:.0f}%"
    except (TypeError, ValueError):
        return "-"


# ============================================================
# STEP 1  逃げ確率の確定
# ============================================================

def _resolve_nige_prob(
    race_judgment: dict,
    combos: list[dict],
    jizen_eval: dict | None = None,
    venue_stats: dict | None = None,
    venue: str = "",
) -> tuple[float, str]:
    """
    逃げシナリオ発生確率と escape_rank を返す。

    【v3 会場特性対応】
    jizen_eval（メンバー評価）に加えて venue_stats（会場1C1着率）を組み込む。

    計算式:
        nige_prob = member_prob × (1 - venue_weight)
                  + venue_c1_rate × venue_weight

        venue_weight = 0.30
        （会場特性30% + メンバー評価70% のブレンド）

    根拠:
        会場によって1コース1着率は 42%（戸田）〜 63%（大村）と20pt以上の差がある。
        同じメンバー評価でも会場が変われば逃げ確率は変わるべき。
        ただしメンバー構成（1号艇の逃げ力・2〜6号艇の攻め力）の方が支配的なので
        重みはメンバー70% : 会場30% とする。

    in_nige 記号 → member_prob マッピング:
        ◎ → 0.70 / ○ → 0.57 / △ → 0.42 / 空白 → 0.27

    Returns
    -------
    nige_prob  : float  逃げシナリオ発生確率（0〜1）
    escape_rank: str    "高"/"中"/"低"
    """
    # ── escape_rank を race_judgment から取得（常に必要） ──────────────
    w1_escape   = (race_judgment.get("w1_escape") or {})
    escape_rank = w1_escape.get("escape_rank", "中")

    # ── 会場1C1着率を取得（ブレンド用） ──────────────────────────────
    venue_c1_rate = _get_venue_c1_rate(venue_stats, venue)
    # venue_stats になければ race_judgment から試みる
    if venue_c1_rate is None:
        venue_c1_rate = _safe(race_judgment.get("venue_c1_win_rate"), None)
    venue_weight = 0.30 if venue_c1_rate is not None else 0.0

    # ── jizen_eval 優先パス ───────────────────────────────────────────
    if jizen_eval:
        in_nige_list = jizen_eval.get("in_nige") or []
        symbol_1     = in_nige_list[0] if in_nige_list else ""

        _SYMBOL_TO_PROB = {"◎": 0.70, "○": 0.57, "△": 0.42, "": 0.27}
        member_prob = _SYMBOL_TO_PROB.get(symbol_1, 0.42)

        # ── 会場特性スケーリング（v3）──────────────────────────────────
        # 単純なブレンドではなく「全国平均比の倍率」でメンバー評価をスケールする。
        # 全国平均1C1着率 ≒ 0.535（24会場実測値の平均）
        # 会場補正係数 = venue_c1_rate / 0.535
        #   戸田: 0.423 / 0.535 = 0.790 → 逃げ21%ダウン
        #   大村: 0.634 / 0.535 = 1.185 → 逃げ19%アップ
        # 補正上限: ×1.20（上振れ抑制） 下限: ×0.70（下振れ抑制）
        # 結果は [0.10, 0.90] にクリップして現実的な確率域に収める
        if venue_c1_rate is not None:
            _NATIONAL_AVG_C1 = 0.535
            multiplier = venue_c1_rate / _NATIONAL_AVG_C1
            multiplier = max(0.70, min(1.20, multiplier))
            nige_prob  = max(0.10, min(0.90, member_prob * multiplier))
        else:
            nige_prob = member_prob

        # escape_rank は記号ベース（スケール後の数値ではなく記号で管理）
        if symbol_1 == "◎":
            escape_rank = "高"
        elif symbol_1 in ("○", "△"):
            escape_rank = "中"
        else:
            escape_rank = "低"

        return round(nige_prob, 4), escape_rank

    # ── フォールバック: combo集計（jizen_eval なし時の旧挙動） ──────────
    first_prob_map: dict[str, float] = {}
    for c in combos:
        w = str(c.get("first", ""))
        first_prob_map[w] = first_prob_map.get(w, 0.0) + _safe(c.get("prob", 0))

    s1_prob_raw = first_prob_map.get("1", 0.0)

    if escape_rank == "低":
        nige_prob = min(s1_prob_raw, 0.35)
    elif escape_rank == "高":
        nige_prob = max(s1_prob_raw, 0.55)
    else:
        nige_prob = s1_prob_raw

    return round(nige_prob, 4), escape_rank


# ============================================================
# STEP 2  シナリオA（逃げ展開）の 2・3着候補
# ============================================================

def _build_scenario_a(
    nige_prob: float,
    combos: list[dict],
    ininage_master: dict,
    venue: str,
    results: list[dict],
    main_waku: str = "",  # 参考情報として受け取るが除外には使わない
    jizen_eval: dict | None = None,
    venue_stats: dict | None = None,  # 会場統計（会場別コースバイアス補正に使用）
) -> dict:
    """
    シナリオA：1号艇が逃げた場合の 2・3着候補と買い目を構築。

    【重要な設計変更】
    旧版では「主役（main_waku）を2着候補から除外」していたが、これは誤り。
    「①が逃げた＋主役が2着に残る」はレースで頻繁に起きる展開であり、
    この買い目が買い目リストから消えることは精度上の大きな欠陥だった。
    → main_waku を2着・3着候補から除外しない（1号艇のみ除外）。

    【確率ツリーとの整合】
    シナリオA の買い目確率 = P(①逃げ) × P(2着=X | ①逃げ) × P(3着=Y | ①逃げ,2着=X)
    main_waku が X になることも Y になることも物理的に正しい。

    【2着スコア計算】
    主軸: circle_pct（イン逃げ時2着実績）
    補助: aisho_raw（相性）/ venue_2nd_map（会場ベースライン）
    スコア = circle_pct × 0.50 + aisho_raw × 0.30 + venue_2nd × 0.20

    【3着スコア計算】
    主軸: idx3（イン逃げ時純3着残存指数）
    補助: tenkai_raw（展開評価）/ aisho_raw（相性）
    スコア = idx3_norm × 0.50 + tenkai_raw × 0.30 + aisho_raw × 0.20
    """
    # ── イン逃げ残存マスタから会場の2着率を取得 ────────────────────────
    venue_2nd_map = {}
    venue_3rd_map = {}
    if venue and ininage_master:
        vd = ininage_master.get(venue, {})
        if isinstance(vd, dict):
            venue_2nd_map = vd.get("_2nd", vd) or {}
            venue_3rd_map = vd.get("_3rd", {}) or {}

    # ── jizen_eval 優先パス ─────────────────────────────────────────────
    if jizen_eval:
        aisho_raw   = jizen_eval.get("aisho_raw_scores")   or []
        tenkai_raw  = jizen_eval.get("tenkai_raw_scores")  or []

        second_scores: dict[str, float] = {}
        total_mast = sum(_safe(v) for v in venue_2nd_map.values() if v) or 1.0

        # circle_pct 正規化（1号艇のみ除外）
        circ_vals = [
            _safe(r.get("circle_pct"), 0.0)
            for r in results
            if str(r.get("waku", "")) != "1"
        ]
        total_circ = sum(circ_vals) or 1.0

        for r in results:
            w = str(r.get("waku", ""))
            if w == "1":
                continue  # 1号艇は1着固定なので除外
            idx = int(w) - 1
            circ_w    = _safe(r.get("circle_pct"), 0.0)
            aisho_w   = _safe(aisho_raw[idx] if idx < len(aisho_raw) else None)
            mast_w    = _safe(venue_2nd_map.get(w, 0))
            mast_norm = (mast_w / total_mast) if total_mast > 0 else 0.0
            circ_norm = (circ_w / total_circ) if total_circ > 0 else 0.0

            if circ_w > 0:
                second_scores[w] = round(circ_norm * 0.50 + aisho_w * 0.30 + mast_norm * 0.20, 5)
            else:
                second_scores[w] = round(aisho_w * 0.70 + mast_norm * 0.30, 5)

        # 3着スコア（1号艇のみ除外）
        third_scores: dict[str, float] = {}
        idx3_vals = [
            _safe(r.get("idx3"), 0.0)
            for r in results
            if str(r.get("waku", "")) != "1"
        ]
        total_idx3 = sum(idx3_vals) or 1.0

        # ── 改良①: jizaisei_raw / sanren_idx を取得 ──────────────────────
        jizaisei_raw = jizen_eval.get("jizaisei_raw_scores") or []

        for r in results:
            w = str(r.get("waku", ""))
            if w == "1":
                continue
            idx = int(w) - 1
            idx3_w    = _safe(r.get("idx3"), 0.0)
            tenkai_w  = _safe(tenkai_raw[idx] if idx < len(tenkai_raw) else None)
            aisho_w   = _safe(aisho_raw[idx]  if idx < len(aisho_raw)  else None)
            # 追加: sanren_idx（0〜100 → 0〜1 に正規化）
            sanren_w  = _safe(r.get("sanren_idx"), 50.0) / 100.0
            # 追加: jizaisei_raw（results注入値を優先、なければjizen_evalから）
            stable_w  = _safe(
                r.get("jizaisei_raw",
                      jizaisei_raw[idx] if idx < len(jizaisei_raw) else None)
            )
            idx3_norm = (idx3_w / total_idx3) if total_idx3 > 0 else 0.0

            # 改良後重み: idx3×0.25 + tenkai×0.20 + aisho×0.20 + sanren×0.10 + stable×0.25
            if idx3_w > 0:
                third_scores[w] = round(
                    idx3_norm * 0.25 +
                    tenkai_w  * 0.20 +
                    aisho_w   * 0.20 +
                    sanren_w  * 0.10 +
                    stable_w  * 0.25,
                    5
                )
            elif tenkai_w > 0:
                third_scores[w] = round(
                    tenkai_w  * 0.50 +
                    aisho_w   * 0.25 +
                    sanren_w  * 0.15 +
                    stable_w  * 0.10,
                    5
                )
            else:
                third_scores[w] = round(
                    aisho_w  * 0.40 +
                    sanren_w * 0.30 +
                    stable_w * 0.30,
                    5
                )

        second_sorted = sorted(second_scores.items(), key=lambda x: x[1], reverse=True)
        third_sorted  = sorted(third_scores.items(),  key=lambda x: x[1], reverse=True)

    else:        # ── フォールバック: combo集計（旧挙動） ─────────────────────────────
        second_prob_sum: dict[str, float] = {}
        third_prob_sum:  dict[str, float] = {}

        for c in combos:
            if str(c.get("first", "")) != "1":
                continue
            prob = _safe(c.get("prob", 0))
            sec  = str(c.get("second", ""))
            thi  = str(c.get("third",  ""))
            if sec:
                second_prob_sum[sec] = second_prob_sum.get(sec, 0.0) + prob
            if thi:
                third_prob_sum[thi]  = third_prob_sum.get(thi,  0.0) + prob

        second_scores = {}
        for w in [str(r["waku"]) for r in results
                  if str(r.get("waku", "")) != "1"]:  # 1号艇のみ除外
            combo_w = second_prob_sum.get(w, 0.0)
            mast_w  = _safe(venue_2nd_map.get(w, 0))
            total_combo = sum(second_prob_sum.values()) or 1.0
            total_mast  = sum(_safe(v) for v in venue_2nd_map.values() if v) or 1.0
            score = (combo_w / total_combo) * 0.60 + (mast_w / total_mast) * 0.40 if total_mast > 0 else combo_w / total_combo
            second_scores[w] = round(score, 5)

        second_sorted = sorted(second_scores.items(), key=lambda x: x[1], reverse=True)

        third_scores = {}
        total_third = sum(third_prob_sum.values()) or 1.0
        for w, p in third_prob_sum.items():
            if w != "1":
                third_scores[w] = round(p / total_third, 5)
        third_sorted = sorted(third_scores.items(), key=lambda x: x[1], reverse=True)

    # ── 改良②: _dynamic_top（スコア僅差時に候補を動的拡張） ──────────────
    def _dynamic_top(sorted_list, base=3, extend_to=5, gap=0.025):
        """
        上位 base 位と (base+1) 位以降のスコア差が gap 以内なら
        extend_to まで拡張する。常滑データのスコアstd≒0.06から導出。
        """
        candidates = [w for w, _ in sorted_list[:base]]
        scores = [s for _, s in sorted_list]
        for i in range(base, min(extend_to, len(sorted_list))):
            if len(scores) > 1 and (scores[0] - scores[i]) <= gap:
                candidates.append(sorted_list[i][0])
            else:
                break
        return candidates

    # ── 買い目生成（1着=1固定）────────────────────────────────────────
    # 改良後: base=3 から動的拡張（僅差のとき最大4/5枚まで広げる）
    top2nd = _dynamic_top(second_sorted, base=3, extend_to=4, gap=0.025)
    top3rd = _dynamic_top(third_sorted,  base=3, extend_to=5, gap=0.025)

    buys_a: list[dict] = []
    for sec in top2nd:
        for thi in top3rd:
            if thi == sec:
                continue
            prob = (
                _safe(second_scores.get(sec, 0)) *
                _safe(third_scores.get(thi,  0)) *
                nige_prob
            )
            buys_a.append({
                "combo":    f"1-{sec}-{thi}",
                "first":    "1",
                "second":   sec,
                "third":    thi,
                "prob":     round(prob, 6),
                "scenario": "A",
            })

    buys_a.sort(key=lambda x: x["prob"], reverse=True)

    return {
        "nige_prob":      nige_prob,
        "second_scores":  second_sorted,
        "third_scores":   third_sorted,
        "buys":           buys_a,
        "top_2nd":        second_sorted[:3],
        "top_3rd":        third_sorted[:3],
    }


# ============================================================
# STEP 3-5  シナリオB（主役展開・崩れ）の構築
# ============================================================

def _identify_main_player(
    combos: list[dict],
    results: list[dict],
    race_judgment: dict,
    jizen_eval: dict | None = None,
) -> dict:
    """
    逃げない場合の「主役」を特定する。

    【v2 jizen_eval 対応】
    jizen_eval がある場合は ② aisho（相性）記号で主役を決める。
    優先順: 相性◎艇 → 相性○艇 → race_judgment.main_player → combo集計最大艇

    相性◎○は「1号艇に実際に攻撃できる選手」を示しているため、
    combo集計の1着確率より信頼性が高い。

    main_1st_prob は jizen_eval.aisho_raw_scores[主役index] を使う。
    （combo集計の確率は参考値として first_prob_map に保持する）

    判定軸（旧）:
      1着確率（combo集計）× 攻撃有効性スコア（race_judgmentから取得）
    """
    # combo集計（first_prob_map は既存コード互換のため常に作る）
    first_prob_map: dict[str, float] = {}
    for c in combos:
        w = str(c.get("first", ""))
        if w != "1":
            first_prob_map[w] = first_prob_map.get(w, 0.0) + _safe(c.get("prob", 0))

    # ── jizen_eval 優先パス ───────────────────────────────────────────
    if jizen_eval:
        aisho_list     = jizen_eval.get("aisho")           or []  # list[str] 記号
        aisho_raw      = jizen_eval.get("aisho_raw_scores") or []  # list[float|None]

        # 相性◎艇を主役候補に（1号艇は除外）
        maru_candidates = [
            str(i + 1) for i, sym in enumerate(aisho_list)
            if sym == "◎" and str(i + 1) != "1"
        ]
        maru2_candidates = [
            str(i + 1) for i, sym in enumerate(aisho_list)
            if sym == "○" and str(i + 1) != "1"
        ]

        if maru_candidates:
            # 相性◎が複数いる場合は aisho_raw スコアが高い方を主役
            main_waku  = max(maru_candidates, key=lambda w: _safe(aisho_raw[int(w)-1] if int(w)-1 < len(aisho_raw) else None))
            main_type  = "相性◎"
            main_score = _safe(aisho_raw[int(main_waku)-1] if int(main_waku)-1 < len(aisho_raw) else None)
        elif maru2_candidates:
            main_waku  = max(maru2_candidates, key=lambda w: _safe(aisho_raw[int(w)-1] if int(w)-1 < len(aisho_raw) else None))
            main_type  = "相性○"
            main_score = _safe(aisho_raw[int(main_waku)-1] if int(main_waku)-1 < len(aisho_raw) else None)
        else:
            # aisho ◎○なし → race_judgment.main_player にフォールバック
            mp         = race_judgment.get("main_player") or {}
            main_waku  = str(mp.get("main_waku", ""))
            main_type  = mp.get("main_type", "-")
            main_score = _safe(mp.get("main_score", 0))

            if not main_waku or main_waku == "-":
                # 最終フォールバック: aisho_raw スコア最大艇（1号艇除く）
                aisho_scored = {
                    str(i+1): _safe(v)
                    for i, v in enumerate(aisho_raw)
                    if str(i+1) != "1"
                }
                if aisho_scored:
                    main_waku  = max(aisho_scored, key=lambda w: aisho_scored[w])
                    main_type  = "aishoスコア最大"
                    main_score = aisho_scored.get(main_waku, 0.0)

        # main_1st_prob: aisho_raw を正規化した値を使う（combo集計を捨てる）
        idx = int(main_waku) - 1 if main_waku.isdigit() else -1
        main_1st_prob_raw = _safe(aisho_raw[idx] if 0 <= idx < len(aisho_raw) else None)
        total_aisho = sum(_safe(v) for i, v in enumerate(aisho_raw) if str(i+1) != "1")
        main_1st_prob = (main_1st_prob_raw / total_aisho) if total_aisho > 0 else 0.15

        # sub_waku: 主役の次点（aisho_raw スコア順）
        sub_pool = [
            (str(i+1), _safe(v)) for i, v in enumerate(aisho_raw)
            if str(i+1) != "1" and str(i+1) != main_waku
        ]
        sub_pool.sort(key=lambda x: x[1], reverse=True)
        sub_waku = sub_pool[0][0] if sub_pool else None
        sub_prob = sub_pool[0][1] if sub_pool else 0.0

        return {
            "main_waku":      main_waku,
            "main_type":      main_type,
            "main_score":     main_score,
            "main_1st_prob":  round(main_1st_prob, 4),
            "sub_waku":       sub_waku,
            "sub_prob":       round(sub_prob, 4),
            "first_prob_map": first_prob_map,  # 既存互換のため保持
        }

    # ── フォールバック: 旧挙動（jizen_eval なし） ──────────────────────
    mp = race_judgment.get("main_player") or {}
    main_waku = str(mp.get("main_waku", ""))
    main_type = mp.get("main_type", "-")
    main_score = _safe(mp.get("main_score", 0))

    if not main_waku or main_waku == "-":
        if first_prob_map:
            main_waku = max(first_prob_map, key=lambda w: first_prob_map[w])
            main_type = "攻め系"
            main_score = first_prob_map.get(main_waku, 0.0)

    main_1st_prob = first_prob_map.get(main_waku, 0.0)

    fp_sorted = sorted(
        [(w, p) for w, p in first_prob_map.items() if w != main_waku],
        key=lambda x: x[1], reverse=True
    )
    sub_waku  = fp_sorted[0][0] if fp_sorted else None
    sub_prob  = fp_sorted[0][1] if fp_sorted else 0.0

    return {
        "main_waku":      main_waku,
        "main_type":      main_type,
        "main_score":     main_score,
        "main_1st_prob":  round(main_1st_prob, 4),
        "sub_waku":       sub_waku,
        "sub_prob":       round(sub_prob, 4),
        "first_prob_map": first_prob_map,
    }


# ============================================================
# _calc_cascade_scores  連鎖スコア計算（設計書 §3-3, §4-1）
# ============================================================

def _calc_cascade_scores(
    main_course: str,
    kimete: str,
    results: list[dict],
    state: RaceState,
    kaiho_venue: dict | None,
    kaiho_national: dict | None,
    tenkai_venue: dict | None,
    tenkai_national: dict | None,
    venue: str,
    ability_fn,          # waku → float の能力スコア関数
    course_weight: float = 0.3,  # コースバイアスの重み（0=ability優先, 1=コース優先）
) -> dict[str, dict]:
    """
    展開連鎖後のコース別2・3着スコアを返す（設計書 §3-3）。

    course_weight:
        マスタなしフォールバック時に「コース番号ベースの有利不利」をどれだけ重視するか。
        0.3（デフォルト）= ability70% + コースバイアス30%
        0.0 = abilityのみ（旧挙動）
        1.0 = コースバイアスのみ

    Returns
    -------
    {waku: {'2着': score, '3着': score}}
    """
    # コースバイアス: 内コース有利（1=1.0, 6=0.45の線形）
    # まくりで内側がpenaltyを受けた後でも、まくった艇の外側が開いた展開を考慮
    _COURSE_BIAS = {"1": 1.0, "2": 0.85, "3": 0.75, "4": 0.65, "5": 0.55, "6": 0.45}

    def _get_row(master: dict, key: tuple) -> dict | None:
        return master.get(key) if master else None

    def _extract(row: dict) -> dict:
        r2  = _safe(row.get("2着率"),     0.0)
        r3i = _safe(row.get("3着以内率"), 0.0)
        r3  = _safe(row.get("3着率"),     0.0)
        if r3 == 0.0 and r3i > r2:
            r3 = r3i - r2
        return {"2着率": r2, "3着率": r3}

    def _fetch_kaiho(c_str: str) -> dict | None:
        """kaiho_chainマスタから残存率を取得（設計書 Step3）"""
        if kaiho_venue and venue:
            key_kv = (str(venue), main_course, kimete, c_str)
            rkv = _get_row(kaiho_venue, key_kv)
            if rkv:
                trust = _safe(rkv.get("信頼度"), 0.0)
                if trust >= 0.15:
                    return _extract(rkv)
        if kaiho_national:
            key_kn = (main_course, kimete, c_str)
            rkn = _get_row(kaiho_national, key_kn)
            if rkn:
                trust = _safe(rkn.get("信頼度"), 0.0) * 0.7
                if trust >= 0.15:
                    return _extract(rkn)
        return None

    def _fetch_tenkai(c_str: str) -> dict | None:
        """tenkai_survivalマスタから残存率を取得（フォールバック）"""
        row_v, trust_v = None, 0.0
        if tenkai_venue and venue:
            key_v = (str(venue), kimete, main_course, c_str)
            rv = _get_row(tenkai_venue, key_v)
            if rv:
                try:
                    trust_v = float(rv.get("信頼度") or 0)
                    if trust_v >= 0.15:
                        row_v = rv
                except (ValueError, TypeError):
                    pass
        row_n = None
        if tenkai_national:
            key_n = (kimete, main_course, c_str)
            row_n = _get_row(tenkai_national, key_n)
        if row_v is None:
            return _extract(row_n) if row_n else None
        elif trust_v >= 0.50:
            return _extract(row_v)
        elif row_n is None:
            return _extract(row_v)
        else:
            w_v = trust_v / 0.50
            w_n = 1.0 - w_v
            rv_e = _extract(row_v)
            rn_e = _extract(row_n)
            return {
                "2着率": rv_e["2着率"] * w_v + rn_e["2着率"] * w_n,
                "3着率": rv_e["3着率"] * w_v + rn_e["3着率"] * w_n,
            }

    # ── Step 1: 初期状態（全コースアクティブ）───────────────────────────
    # stateは呼び出し元から渡される（主役イベント適用済みであること）

    # ── Step 3: 各艇の2着スコア算出（連鎖後状態で）─────────────────────
    second_scores: dict[str, float] = {}
    third_scores:  dict[str, float] = {}

    for r in results:
        w     = r["waku"]
        c_str = str(int(float(r.get("course") or r.get("進入コース") or w)))
        if c_str == main_course:
            continue  # 主役自身は除外

        ab    = ability_fn(w)
        penalty = state.penalty_of(c_str)

        if penalty <= 0.0:
            # 完全に走路が塞がれた艇はスコアをゼロにする
            second_scores[w] = 0.0
            third_scores[w]  = 0.0
            continue

        # kaiho_chainマスタを優先（設計書 Step3 の優先ロジック）
        kaiho_r  = _fetch_kaiho(c_str)
        tenkai_r = _fetch_tenkai(c_str)

        if kaiho_r:
            # 連鎖マスタあり: ability補正 × ペナルティ
            second_scores[w] = kaiho_r["2着率"] * ab * penalty
            third_scores[w]  = kaiho_r["3着率"] * ab * penalty
        elif tenkai_r:
            # フォールバック: tenkai_survival × penalty
            second_scores[w] = tenkai_r["2着率"] * ab * penalty
            third_scores[w]  = tenkai_r["3着率"] * ab * penalty
        else:
            # どちらもなし: ability × コースバイアス加重 × penalty
            # course_weight で ability と コースバイアスの比率を調整
            #
            # ── シナリオA専用バイアス（会場別動的補正） ──────────────────
            # _COURSE_BIAS（内枠優遇）はシナリオBでは概ね正しいが、
            # シナリオA（イン逃げ）時は1号艇が先頭に抜けた後に外枠が
            # 差す・まくり差すパターンが頻出する（実データで4〜6号艇が
            # 2着外れの84%を占める）。
            # さらに venue_c1_rate が全国平均を下回る会場（常滑・下関等）は
            # 逃げが決まりにくく外枠台頭の傾向が強いため、4〜6号艇バイアスを
            # venue_c1_rate に応じて動的に引き上げる。
            _COURSE_BIAS_NIGE = {
                "1": 0.0,   # 1着固定のためスコア対象外
                "2": 0.80,
                "3": 0.78,
                "4": 0.75,  # 通常バイアスより +0.10〜+0.15
                "5": 0.68,
                "6": 0.60,
            }
            _NATIONAL_AVG_C1 = 0.535  # 全24会場実測平均

            cb_base = _COURSE_BIAS_NIGE.get(c_str, 0.6)

            # venue_c1_rate が取得できた場合のみ動的スケーリング適用
            # （venue_stats は _build_scenario_a の引数として受け取る）
            _venue_c1 = _get_venue_c1_rate(venue_stats, venue) if venue_stats else None
            if _venue_c1 and int(c_str) >= 4:
                # 逃げにくい会場（_venue_c1 < 全国平均）ほど外枠を持ち上げる
                # 例: 常滑 _venue_c1≒0.48 → scale=0.90 → cb×1.10
                _scale = _venue_c1 / _NATIONAL_AVG_C1
                cb = min(cb_base * (2.0 - _scale), 0.90)  # 上限0.90
            else:
                cb = cb_base

            base = ab * (1.0 - course_weight) + cb * course_weight
            second_scores[w] = base * penalty
            third_scores[w]  = base * penalty * 0.5

    # ── Step 4: 3着スコア（2着決定後の条件付き更新）─────────────────────
    # 2着候補上位で状態を更新し、残存艇の3着スコアを再計算
    sorted_2nd = sorted(second_scores.items(), key=lambda x: x[1], reverse=True)
    top2_candidates = sorted_2nd[:3]  # 計算コスト削減のため上位3艇のみ（設計書 §7）

    # 3着の条件付きスコア: {(2着waku, 3着waku): score}
    third_conditional: dict[tuple[str, str], float] = {}

    for w2, s2v in top2_candidates:
        if s2v <= 0.0:
            continue
        r2 = next((r for r in results if r["waku"] == w2), {})
        c2 = str(int(float(r2.get("course") or r2.get("進入コース") or w2)))
        # 2着が決まった後の状態を更新（2着艇の内側が開く）
        state_after_2nd = apply_event(state, c2, "通過", True)

        for r in results:
            w3    = r["waku"]
            c3    = str(int(float(r.get("course") or r.get("進入コース") or w3)))
            if c3 == main_course or w3 == w2:
                continue
            ab3     = ability_fn(w3)
            pen3    = state_after_2nd.penalty_of(c3)
            tenkai3 = _fetch_tenkai(c3)
            kaiho3  = _fetch_kaiho(c3)
            if kaiho3:
                base = kaiho3["3着率"]
            elif tenkai3:
                base = tenkai3["3着率"]
            else:
                base = ab3 * 0.5
            third_conditional[(w2, w3)] = base * ab3 * pen3

    # 3着スコアを条件付き期待値で更新（2着確率で加重平均）
    total_2nd = sum(s for _, s in top2_candidates) or 1.0
    third_scores_updated: dict[str, float] = {}
    for w3 in third_scores:
        weighted = sum(
            (s2v / total_2nd) * third_conditional.get((w2, w3), third_scores.get(w3, 0.0))
            for w2, s2v in top2_candidates
        )
        third_scores_updated[w3] = weighted if weighted > 0.0 else third_scores[w3]

    # 最終的な3着スコアは条件付き計算結果で上書き
    third_scores.update(third_scores_updated)

    return {
        w: {"2着": second_scores.get(w, 0.0), "3着": third_scores.get(w, 0.0)}
        for w in second_scores
    }


# ============================================================
# build_story_from_log  展開ストーリー生成（設計書 §4-3）
# ============================================================

def build_story_from_log(event_log: list[tuple], results: list[dict]) -> str:
    """
    RaceState.event_logから日本語ストーリーを組み立てる（設計書 §4-3）。

    event_log の各要素: (attack_course, kimete, success)
    """
    # コース → 艇名マップ
    course_to_name: dict[str, str] = {}
    for r in results:
        c = str(int(float(r.get("course") or r.get("進入コース") or r["waku"])))
        w = str(r["waku"])
        # 選手名があれば使う
        name = r.get("name") or r.get("選手名") or f"{w}号艇"
        course_to_name[c] = f"{w}号({name})" if name != f"{w}号艇" else f"{w}号艇"

    lines = []
    for (attack_course, kimete, success) in event_log:
        attacker = course_to_name.get(str(attack_course), f"{attack_course}コース")
        if success:
            # 塞がれるコースを特定
            rules    = _BLOCK_RULES.get((kimete, str(attack_course)), [])
            blocked  = [c for c, strength in rules if strength >= 0.5]
            lines.append(f"{attacker}が{kimete}で主役に浮上")
            if blocked:
                blocked_names = "・".join(
                    course_to_name.get(c, f"{c}コース") for c in blocked
                )
                lines.append(f"  → {blocked_names}は走路を失う")
            else:
                lines.append(f"  → {attack_course}コースより外は開放")
        else:
            lines.append(f"{attacker}は不発、1号艇が逃げ残り")

    return " / ".join(lines) if lines else ""


def _build_scenario_b(
    nige_prob: float,
    combos: list[dict],
    results: list[dict],
    race_judgment: dict,
    tenkai_venue: dict | None,
    tenkai_national: dict | None,
    kaiho_venue: dict | None = None,
    kaiho_national: dict | None = None,
    course_weight: float = 0.3,
    jizen_eval: dict | None = None,
    venue_stats: dict | None = None,
    venue_course_master: dict | None = None,
) -> dict:
    """
    シナリオB：主役が1着に来た場合の 2・3着と崩れシナリオを構築。

    【v3 会場特性対応】
    ② 決まり手推定: 選手の実決まり手%（コース別マスタ）× 会場決まり手比率 でブレンド
       → 「戸田はまくりが多いが、この選手は差し巧者」を正しく反映
       → 旧方式（文字列マッチングで常に"まくり"）を完全廃止

    ability_fn（③2・3着スコア補正）:
       venue_course_master がある場合:
           会場別実績（1着率×信頼度）と全国実績（aisho_raw）を
           出走数ベースの信頼度で動的ブレンド
           → 「この選手はこの会場でどれだけ走れるか」を反映
       ない場合: aisho_raw × 0.7 + jizaisei_raw × 0.3（旧挙動）

    2着スコア = 展開別残存マスタ「2着率」 × 個人能力補正
    3着スコア = 展開別残存マスタ「3着率」 × 個人能力補正
    """
    fly_prob = 1.0 - nige_prob
    mp       = _identify_main_player(combos, results, race_judgment, jizen_eval=jizen_eval)
    main_w   = mp["main_waku"]
    main_t   = mp.get("main_type", "")

    # ── 主役の進入コースを取得 ──────────────────────────────────────
    main_result = next((r for r in results if r["waku"] == main_w), {})
    main_course = str(int(float(
        main_result.get("course") or main_result.get("進入コース") or main_w
    )))

    # ── 会場名を取得 ─────────────────────────────────────────────────
    venue = (race_judgment or {}).get("venue", "")

    # ================================================================
    # ② 決まり手推定: 選手実績 × 会場特性 のブレンド（v3新設）
    # ================================================================
    # 選手の実決まり手%（コース別マスタから取得）
    main_name   = main_result.get("name_norm") or main_result.get("name", "")
    main_c_str  = main_course

    # 選手の実決まり手%を全国コース別マスタから取得
    # results の raw_cm に格納されている
    main_cm = main_result.get("raw_cm") or {}
    player_sashi    = _safe(main_cm.get("差し%"),       0.0)
    player_makuri   = _safe(main_cm.get("まくり%"),     0.0)
    player_mz       = _safe(main_cm.get("まくり差し%"), 0.0)
    player_total    = player_sashi + player_makuri + player_mz

    # 会場決まり手分布を取得（venue_stats の kimete_by_course を使う）
    venue_dist = _get_venue_kimete_dist(venue_stats, int(main_c_str))

    # ブレンド: 選手60% × 会場40%
    # 選手データがない場合は会場100%、会場データがない場合は選手100%
    if player_total > 0 and venue_dist:
        p_s  = player_sashi  / player_total
        p_mk = player_makuri / player_total
        p_mz = player_mz     / player_total
        v_s  = venue_dist.get("差し",       0.0)
        v_mk = venue_dist.get("まくり",     0.0)
        v_mz = venue_dist.get("まくり差し", 0.0)
        b_s  = p_s  * 0.60 + v_s  * 0.40
        b_mk = p_mk * 0.60 + v_mk * 0.40
        b_mz = p_mz * 0.60 + v_mz * 0.40
        blended = {"差し": b_s, "まくり": b_mk, "まくり差し": b_mz}
    elif player_total > 0:
        blended = {
            "差し": player_sashi / player_total,
            "まくり": player_makuri / player_total,
            "まくり差し": player_mz / player_total,
        }
    else:
        blended = venue_dist or {"まくり": 0.5, "まくり差し": 0.3, "差し": 0.2}

    # 最頻の決まり手を採用（恵まれ・抜きは除外）
    kimete = max(blended, key=lambda k: blended[k]) if blended else "まくり"

    # ================================================================
    # ③ 個人能力マップ構築: 会場適性 × 全国実績 のブレンド（v3新設）
    # ================================================================
    # venue_course_master: キー = (選手名, 会場名, コース文字列)
    # 出走数ベース信頼度で「会場別実績」と「全国実績（aisho_raw）」を動的ブレンド
    # 信頼度 = min(1.0, 出走数 / 20)  ← 20走で完全信頼
    aisho_raw = (jizen_eval.get("aisho_raw_scores") or []) if jizen_eval else []
    jizai_raw = (jizen_eval.get("jizaisei_raw_scores") or []) if jizen_eval else []

    ability_map: dict[str, float] = {}
    for r in results:
        w    = r["waku"]
        idx  = int(w) - 1
        name = r.get("name_norm") or r.get("name", "")
        c    = str(int(float(r.get("course") or r.get("進入コース") or w)))

        # 全国実績スコア（改良③: sanren_idx と jizaisei_raw を追加）
        a_s = _safe(aisho_raw[idx] if idx < len(aisho_raw) else None, 0.02)
        j_s = _safe(jizai_raw[idx] if idx < len(jizai_raw) else None, 0.02)
        # 改良③: results に注入された jizaisei_raw を優先参照
        j_s_injected = _safe(r.get("jizaisei_raw"), None)
        if j_s_injected is not None:
            j_s = j_s_injected
        # sanren_idx（0〜100 → 0〜1 に正規化）
        sanren_s = _safe(r.get("sanren_idx"), 50.0) / 100.0
        # 改良後: win3_rate×0.60 + sanren×0.25 + stable×0.15
        win3_s = _safe(r.get("win3_rate"), 0.5)
        national_score = max(win3_s * 0.60 + sanren_s * 0.25 + j_s * 0.15, 0.02)

        if not jizen_eval:
            # jizen_eval なし → rel_win1 × idx3 の幾何平均（旧挙動）
            rv = max(_safe(r.get("rel_win1"), 0.02), 0.02)
            i3 = max(_safe(r.get("idx3"),     0.02), 0.02)
            national_score = math.sqrt(rv * i3)

        # 会場別実績（venue_course_master から取得）
        vcm_row = None
        if venue_course_master and name and venue:
            vcm_row = (venue_course_master.get((name, venue, c))
                       or venue_course_master.get((name[:4], venue, c) if len(name) >= 4 else ("", "", "")))

        if vcm_row:
            n_runs = _safe(vcm_row.get("出走数") or vcm_row.get("n_runs"), 0)
            trust  = _calc_venue_trust(n_runs)   # 出走数 → 信頼度 0〜1
            if trust > 0:
                # 会場別1着率を正規化して能力スコア化
                v_win1 = _safe(vcm_row.get("1着率") or vcm_row.get("win1_rate"), 0.0)
                # 全国平均1着率 ~16.7% を基準に相対化 (1.0が平均)
                v_score = max(v_win1 / 0.167, 0.1) if v_win1 > 0 else 0.5
                # 会場別信頼度に応じてブレンド: 信頼度×50%が会場、残りが全国
                venue_w  = trust * 0.50
                ability_map[w] = max(
                    national_score * (1 - venue_w) + v_score * venue_w,
                    0.02
                )
            else:
                ability_map[w] = national_score
        else:
            ability_map[w] = national_score

    def _ability(w: str) -> float:
        return ability_map.get(w, 0.02)

    def _fetch_rates(c_str: str) -> dict | None:
        """
        進入コース c_str の 2着率・3着率を返す。

        【ブレンド設計】
        tenkai_survival  : (決まり手, 1着コース, 進入コース) → 結果からの残存率
        kaiho_chain（③） : (攻撃コース, 決まり手, 進入コース) → 攻撃の連鎖残存率

        両マスタを信頼度加重でブレンドして返す。
        kaiho_chain は「誰が仕掛けた結果として誰が残るか」の視点を加え、
        展開ストーリーの連鎖性を強化する。
        """
        if c_str == main_course:
            return None  # 主役自身は除外

        def _get_row(master: dict, key: tuple) -> dict | None:
            return master.get(key) if master else None

        def _extract(row: dict) -> dict:
            r2  = _safe(row.get("2着率"),     0.0)
            r3i = _safe(row.get("3着以内率"), 0.0)
            r3  = _safe(row.get("3着率"),     0.0)
            if r3 == 0.0 and r3i > r2:
                r3 = r3i - r2
            return {"2着率": r2, "3着率": r3}

        # ── A) tenkai_survival（既存・結果ベース）──────────────────
        row_v, trust_v = None, 0.0
        if tenkai_venue and venue:
            key_v = (str(venue), kimete, main_course, c_str)
            rv = _get_row(tenkai_venue, key_v)
            if rv:
                try:
                    trust_v = float(rv.get("信頼度") or 0)
                    if trust_v >= 0.15:
                        row_v = rv
                except (ValueError, TypeError):
                    pass

        row_n = None
        if tenkai_national:
            key_n = (kimete, main_course, c_str)
            row_n = _get_row(tenkai_national, key_n)

        if row_v is None:
            tenkai_rates = _extract(row_n) if row_n else None
        elif trust_v >= 0.50:
            tenkai_rates = _extract(row_v)
        elif row_n is None:
            tenkai_rates = _extract(row_v)
        else:
            w_v = trust_v / 0.50
            w_n = 1.0 - w_v
            rv_e = _extract(row_v)
            rn_e = _extract(row_n)
            tenkai_rates = {
                "2着率": rv_e["2着率"] * w_v + rn_e["2着率"] * w_n,
                "3着率": rv_e["3着率"] * w_v + rn_e["3着率"] * w_n,
            }

        # ── B) kaiho_chain（③・攻撃コース軸）──────────────────────
        # キー: (会場名, 攻撃コース=main_course, 決まり手, 進入コース=c_str)
        # 「main_courseが kimete で仕掛けた → c_str が残る確率」
        kaiho_rates = None
        kaiho_trust = 0.0
        if kaiho_venue and venue:
            key_kv = (str(venue), main_course, kimete, c_str)
            rkv = _get_row(kaiho_venue, key_kv)
            if rkv:
                try:
                    kaiho_trust = float(rkv.get("信頼度") or 0)
                    if kaiho_trust >= 0.15:
                        kaiho_rates = _extract(rkv)
                except (ValueError, TypeError):
                    pass
        if kaiho_rates is None and kaiho_national:
            key_kn = (main_course, kimete, c_str)
            rkn = _get_row(kaiho_national, key_kn)
            if rkn:
                kaiho_trust = float(rkn.get("信頼度") or 0) * 0.7  # 全国版は信頼度を減衰
                kaiho_rates = _extract(rkn)

        # ── C) 両マスタのブレンド ──────────────────────────────────
        # tenkai_survival（結果ベース）70% + kaiho_chain（連鎖ベース）30%
        # kaiho_chain がない場合は tenkai_survival のみ使用
        if tenkai_rates is None and kaiho_rates is None:
            return None
        if tenkai_rates is None:
            return kaiho_rates
        if kaiho_rates is None or kaiho_trust < 0.15:
            return tenkai_rates

        # 両方あり: 信頼度を考慮してブレンド（kaiho最大30%）
        kaiho_w  = min(0.30, kaiho_trust * 0.30)
        tenkai_w = 1.0 - kaiho_w
        return {
            "2着率": tenkai_rates["2着率"] * tenkai_w + kaiho_rates["2着率"] * kaiho_w,
            "3着率": tenkai_rates["3着率"] * tenkai_w + kaiho_rates["3着率"] * kaiho_w,
        }
    # ── ④ 2着・3着スコア算出（展開連鎖）─────────────────────────────
    # Step2: 主役が動いた後のRaceStateを生成（設計書 §4-1 Step2）
    initial_state = RaceState()
    state_after_main = apply_event(initial_state, main_course, kimete, success=True)

    # Step3: _calc_cascade_scoresで連鎖後スコアを一括計算（設計書 §5-2）
    cascade = _calc_cascade_scores(
        main_course     = main_course,
        kimete          = kimete,
        results         = results,
        state           = state_after_main,
        kaiho_venue     = kaiho_venue,
        kaiho_national  = kaiho_national,
        tenkai_venue    = tenkai_venue,
        tenkai_national = tenkai_national,
        venue           = venue,
        ability_fn      = _ability,
        course_weight   = course_weight,
    )

    second_scores_b: dict[str, float] = {}
    third_scores_b:  dict[str, float] = {}
    _used_master = bool(cascade)

    for w, scores in cascade.items():
        second_scores_b[w] = round(scores["2着"], 6)
        third_scores_b[w]  = round(scores["3着"], 6)

    # マスタが取れなかった場合のフォールバック（combo確率集計）
    if not _used_master:
        _sec_raw: dict[str, float] = {}
        _thi_raw: dict[str, float] = {}
        for c in combos:
            if str(c.get("first", "")) != main_w:
                continue
            prob = _safe(c.get("prob", 0))
            sec  = str(c.get("second", ""))
            thi  = str(c.get("third",  ""))
            if sec:
                _sec_raw[sec] = _sec_raw.get(sec, 0.0) + prob
            if thi:
                _thi_raw[thi] = _thi_raw.get(thi, 0.0) + prob
        total_s = sum(_sec_raw.values()) or 1.0
        total_t = sum(_thi_raw.values()) or 1.0
        second_scores_b = {w: p / total_s for w, p in _sec_raw.items() if w != main_w}
        third_scores_b  = {w: p / total_t for w, p in _thi_raw.items() if w != main_w}

    # 正規化（合計を1に揃える）
    total_sec = sum(second_scores_b.values()) or 1.0
    total_thi = sum(third_scores_b.values())  or 1.0
    second_scores_b = {w: round(v / total_sec, 5) for w, v in second_scores_b.items()}
    third_scores_b  = {w: round(v / total_thi, 5) for w, v in third_scores_b.items()}

    # event_logをシナリオBに保存（ストーリー生成用）
    _cascade_event_log = state_after_main.event_log

    second_sorted_b = sorted(second_scores_b.items(), key=lambda x: x[1], reverse=True)
    third_sorted_b  = sorted(third_scores_b.items(),  key=lambda x: x[1], reverse=True)

    # ── 主役1着買い目生成 ─────────────────────────────────────────────
    top2nd_b = [w for w, _ in second_sorted_b[:3]]
    top3rd_b = [w for w, _ in third_sorted_b[:4]]

    buys_b_main: list[dict] = []
    for sec in top2nd_b:
        for thi in top3rd_b:
            if thi == sec or thi == main_w:
                continue
            prob = (
                _safe(second_scores_b.get(sec, 0)) *
                _safe(third_scores_b.get(thi,  0)) *
                mp["main_1st_prob"] *
                fly_prob
            )
            buys_b_main.append({
                "combo":    f"{main_w}-{sec}-{thi}",
                "first":    main_w,
                "second":   sec,
                "third":    thi,
                "prob":     round(prob, 6),
                "scenario": "B_main",
            })

    # ── ⑤ 崩れシナリオ v3（タイプ別分岐・多段展開）─────────────────────
    #
    # 【設計方針】
    # 「主役が崩れた」は一種類ではない。崩れの"タイプ"によって
    # ・コースの開放パターン（誰に走路が生まれるか）
    # ・浮上候補の決まり手（どんな展開で台頭するか）
    # ・逃げ残存への影響
    # が全て異なる。この3タイプを明示的に処理する。
    #
    # タイプX（まくり系自滅）:
    #   主役コースから内側が開放される → 内側の艇が差しで台頭
    #   1号艇には有利（コースが戻る）
    #
    # タイプY（差し系自滅）:
    #   主役が蓋になって内側を圧迫したまま止まる → 外の艇がまくりで台頭
    #   1号艇には不利（蓋が残る）
    #
    # タイプZ（まくり差し系自滅）:
    #   中間コースが開く → 外の艇か抜いてきた内側の艇が台頭
    #   1号艇への影響は中程度
    #
    # 各タイプの「崩れ確率」は主役の決まり手から推定する。
    # ─────────────────────────────────────────────────────────────────────

    # 主役の決まり手からタイプ別発生確率を算出
    # kimete は _build_scenario_b 冒頭で確定済み
    _KIMETE_TYPE_DIST: dict[str, dict[str, float]] = {
        "まくり":     {"X": 0.70, "Y": 0.10, "Z": 0.20},
        "差し":       {"X": 0.10, "Y": 0.70, "Z": 0.20},
        "まくり差し": {"X": 0.20, "Y": 0.25, "Z": 0.55},
        "逃げ":       {"X": 0.00, "Y": 0.00, "Z": 0.00},  # 逃げ主役は崩れシナリオなし
    }
    _type_dist = _KIMETE_TYPE_DIST.get(kimete, {"X": 0.33, "Y": 0.33, "Z": 0.34})

    # 崩れ後の浮上艇が使う「新しい決まり手」のマッピング
    # タイプX: まくり系が崩れた → 内側が差しで台頭
    # タイプY: 差し系が崩れた  → 外側がまくりで台頭
    # タイプZ: まくり差し崩れ  → 外が差し or まくり差し
    _COLLAPSE_NEW_KIMETE: dict[str, dict[str, str]] = {
        "X": {"内": "差し",   "外": "まくり差し"},
        "Y": {"内": "差し",   "外": "まくり"},
        "Z": {"内": "差し",   "外": "まくり差し"},
    }

    # 主役コースの内外どちらの艇が台頭するかのタイプ別判断
    # X: 内側が開く → 内側艇優先
    # Y: 蓋が残る  → 外側艇優先（主役より外）
    # Z: 中間が開く → 外側艇優先（ただしコース5,6が対象）
    _COLLAPSE_DIRECTION: dict[str, str] = {
        "X": "内",
        "Y": "外",
        "Z": "外",
    }

    fb_prob = _safe((race_judgment.get("escape_fallback") or {}).get("fallback_prob", 0))
    _main_course_int = int(main_course) if str(main_course).isdigit() else 3

    # ── 崩れ候補艇の選定（タイプ共通の入力）──────────────────────────────
    # 候補スコアを3軸で評価:
    #   axis_pos:    崩れタイプに対して物理的に有利なコース位置
    #   axis_aisho:  jizen_eval の相性スコア（実力指標）
    #   axis_jizai:  安定性（じざいせい）が低い = 攻撃型 = 崩れで浮上しやすい
    _JIZAI_SCORE = {"◎": 0.0, "○": 0.3, "△": 0.6, "": 1.0}  # 低いほど不安定→崩れ候補

    if jizen_eval:
        jizai_list = jizen_eval.get("jizaisei") or []
        aisho_raw  = jizen_eval.get("aisho_raw_scores") or []
    else:
        jizai_list = []
        aisho_raw  = []

    # 全候補艇（主役・1号艇を除く）のスコアを計算
    _cand_pool: list[dict] = []
    for r in results:
        w = r["waku"]
        if w in (main_w, "1"):
            continue
        idx       = int(w) - 1
        c_str_r   = str(int(float(r.get("course") or r.get("進入コース") or w)))
        c_int_r   = int(c_str_r) if c_str_r.isdigit() else int(w)
        j_sym     = jizai_list[idx] if idx < len(jizai_list) else ""
        a_raw     = _safe(aisho_raw[idx] if idx < len(aisho_raw) else None, 0.0)
        j_sc      = _JIZAI_SCORE.get(j_sym, 0.5)
        _cand_pool.append({
            "waku":     w,
            "course":   c_str_r,
            "c_int":    c_int_r,
            "aisho":    a_raw,
            "jizai_sc": j_sc,   # 高いほど不安定
        })

    # タイプ別に浮上候補艇を選ぶ内部関数
    def _pick_collapse_cands(
        collapse_type: str,
        n: int = 2,
    ) -> list[tuple[str, float, str]]:
        """
        崩れタイプに応じた「浮上候補艇リスト」を返す。
        Returns: [(waku, score, new_kimete), ...]
        """
        direction  = _COLLAPSE_DIRECTION[collapse_type]
        kimete_map = _COLLAPSE_NEW_KIMETE[collapse_type]

        scored: list[tuple[str, float, str]] = []
        for cand in _cand_pool:
            c_int_r = cand["c_int"]

            # コース方向スコア: タイプに応じた「有利コース」かどうか
            if direction == "内":
                # 内側が有利: 主役コースより内側の艇を優先
                if c_int_r < _main_course_int:
                    pos_score = 1.0 - (c_int_r - 1) / 5.0  # コース1近いほど高い
                    new_k     = kimete_map["内"]
                else:
                    pos_score = 0.2  # 外側も一応候補だが低スコア
                    new_k     = kimete_map["外"]
            else:  # direction == "外"
                # 外側が有利: 主役コースより外側の艇を優先
                if c_int_r > _main_course_int:
                    pos_score = (c_int_r - 1) / 5.0  # コース6近いほど高い
                    new_k     = kimete_map["外"]
                else:
                    pos_score = 0.2
                    new_k     = kimete_map["内"]

            # 総合スコア: コース位置 × 0.40 + 相性スコア × 0.35 + 不安定性 × 0.25
            total = pos_score * 0.40 + cand["aisho"] * 0.35 + cand["jizai_sc"] * 0.25
            scored.append((cand["waku"], total, new_k))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:n]

    # ── タイプ別崩れ買い目を生成 ──────────────────────────────────────────
    buys_b_collapse: list[dict] = []
    _main_fail_prob = fly_prob * (1.0 - mp["main_1st_prob"])  # 逃げず+主役不発の確率

    for collapse_type, type_weight in _type_dist.items():
        if type_weight <= 0.0:
            continue

        cands = _pick_collapse_cands(collapse_type, n=2)
        if not cands:
            continue

        for cw, c_score, c_kimete in cands:
            cr       = next((r for r in results if r["waku"] == cw), {})
            c_course = str(int(float(cr.get("course") or cr.get("進入コース") or cw)))

            # 崩れ状態の生成:
            # Step1: 主役が失速（main_course 失速 = success=False）
            state_after_fail   = apply_event(initial_state, main_course, kimete, success=False)
            # Step2: 崩れ艇が新しい決まり手で台頭（success=True）
            collapse_state     = apply_event(state_after_fail, c_course, c_kimete, success=True)

            c_cascade = _calc_cascade_scores(
                main_course     = c_course,
                kimete          = c_kimete,
                results         = results,
                state           = collapse_state,
                kaiho_venue     = kaiho_venue,
                kaiho_national  = kaiho_national,
                tenkai_venue    = tenkai_venue,
                tenkai_national = tenkai_national,
                venue           = venue,
                ability_fn      = _ability,
                course_weight   = course_weight,
            )

            c_sec_scores = {w: v["2着"] for w, v in c_cascade.items() if w != cw}
            c_thi_scores = {w: v["3着"] for w, v in c_cascade.items() if w != cw}

            if c_sec_scores and c_thi_scores:
                ts2 = sum(c_sec_scores.values()) or 1.0
                ts3 = sum(c_thi_scores.values()) or 1.0
                c_sec_n = {w: v / ts2 for w, v in c_sec_scores.items()}
                c_thi_n = {w: v / ts3 for w, v in c_thi_scores.items()}
                c_top2  = sorted(c_sec_n.items(), key=lambda x: x[1], reverse=True)[:3]
                c_top3  = sorted(c_thi_n.items(), key=lambda x: x[1], reverse=True)[:4]
                for sec2, s2v in c_top2:
                    for thi2, t2v in c_top3:
                        if thi2 == sec2:
                            continue
                        # 確率: 逃げず×主役不発×タイプ発生×候補スコア正規化
                        prob = (s2v * t2v
                                * _main_fail_prob
                                * type_weight
                                * min(c_score, 1.0))
                        buys_b_collapse.append({
                            "combo":         f"{cw}-{sec2}-{thi2}",
                            "first":         cw,
                            "second":        sec2,
                            "third":         thi2,
                            "prob":          round(prob, 6),
                            "scenario":      "B_collapse",
                            "collapse_type": collapse_type,   # X/Y/Z（デバッグ・新聞表示用）
                            "new_kimete":    c_kimete,        # 崩れ後の決まり手（表示用）
                        })
            else:
                # フォールバック: combo確率から集計
                for c in combos:
                    if str(c.get("first", "")) == cw:
                        sec = str(c.get("second", ""))
                        thi = str(c.get("third",  ""))
                        if sec and thi and sec != cw and thi != cw and sec != thi:
                            prob = (_safe(c.get("prob", 0))
                                    * _main_fail_prob
                                    * type_weight
                                    * min(c_score, 1.0))
                            buys_b_collapse.append({
                                "combo":         f"{cw}-{sec}-{thi}",
                                "first":         cw,
                                "second":        sec,
                                "third":         thi,
                                "prob":          round(prob, 6),
                                "scenario":      "B_collapse",
                                "collapse_type": collapse_type,
                                "new_kimete":    c_kimete,
                            })

    # 重複コンボを統合（タイプXとタイプZで同じコンボが出た場合に合算）
    _combo_map: dict[str, dict] = {}
    for entry in buys_b_collapse:
        key = entry["combo"]
        if key in _combo_map:
            _combo_map[key]["prob"] = round(_combo_map[key]["prob"] + entry["prob"], 6)
        else:
            _combo_map[key] = dict(entry)
    buys_b_collapse = sorted(_combo_map.values(), key=lambda x: x["prob"], reverse=True)[:8]

    # collapse_top は旧互換キー（_merge_scenarios 等で参照される）
    # タイプ別で複数候補が出るため、上位2艇を代表として設定
    _all_cands_flat = [(cw, cs) for collapse_type in _type_dist
                       for cw, cs, _ in _pick_collapse_cands(collapse_type, n=1)]
    seen_cw: set[str] = set()
    collapse_top: list[tuple[str, float]] = []
    for cw, cs in sorted(_all_cands_flat, key=lambda x: x[1], reverse=True):
        if cw not in seen_cw:
            collapse_top.append((cw, cs))
            seen_cw.add(cw)
        if len(collapse_top) >= 2:
            break

    # ── ⑦ 漁夫（SC）候補 ────────────────────────────────────────────
    buys_b_sc: list[dict] = []
    if fb_prob >= 0.08:
        # 主役攻撃不発 → 主役コースがブロックされた状態で3着を計算（連鎖化）
        sc_state = apply_event(initial_state, main_course, kimete, success=False)
        sc_cascade = _calc_cascade_scores(
            main_course     = "1",
            kimete          = "逃げ",
            results         = results,
            state           = sc_state,
            kaiho_venue     = kaiho_venue,
            kaiho_national  = kaiho_national,
            tenkai_venue    = tenkai_venue,
            tenkai_national = tenkai_national,
            venue           = venue,
            ability_fn      = _ability,
            course_weight   = course_weight,
        )
        sc_thi_scores: dict[str, float] = {
            w: sc_cascade[w]["3着"] for w in sc_cascade
            if w not in (main_w, "1") and sc_cascade[w]["3着"] > 0
        }
        # フォールバック: _calc_cascade_scoresが空の場合は旧方式
        if not sc_thi_scores:
            for r3 in results:
                w3 = r3["waku"]
                if w3 in (main_w, "1"):
                    continue
                w3_course = str(int(float(r3.get("course") or r3.get("進入コース") or w3)))
                rates3 = _fetch_rates(w3_course)
                if rates3:
                    sc_thi_scores[w3] = rates3["3着率"] * _ability(w3)
        if sc_thi_scores:
            ts_sc = sum(sc_thi_scores.values()) or 1.0
            sc_top3 = sorted(sc_thi_scores.items(), key=lambda x: x[1], reverse=True)[:3]
            for w3, sv in sc_top3:
                prob = (sv / ts_sc) * fly_prob * fb_prob
                buys_b_sc.append({
                    "combo":    f"{main_w}-1-{w3}",
                    "first":    main_w,
                    "second":   "1",
                    "third":    w3,
                    "prob":     round(prob, 6),
                    "scenario": "B_sc",
                })
        else:
            # フォールバック
            for c in combos:
                if str(c.get("first", "")) == main_w and str(c.get("second", "")) == "1":
                    thi = str(c.get("third", ""))
                    if thi and thi not in (main_w, "1"):
                        prob = _safe(c.get("prob", 0)) * fly_prob * fb_prob
                        buys_b_sc.append({
                            "combo":    f"{main_w}-1-{thi}",
                            "first":    main_w,
                            "second":   "1",
                            "third":    thi,
                            "prob":     round(prob, 6),
                            "scenario": "B_sc",
                        })

    buys_b_sc.sort(key=lambda x: x["prob"], reverse=True)
    buys_b_sc = buys_b_sc[:3]

    return {
        "main_player":     mp,
        "second_sorted":   second_sorted_b,
        "third_sorted":    third_sorted_b,
        "collapse_top":    collapse_top,
        "fb_prob":         fb_prob,
        "buys_main":       sorted(buys_b_main, key=lambda x: x["prob"], reverse=True),
        "buys_collapse":   buys_b_collapse,
        "buys_sc":         buys_b_sc,
        "_used_master":    _used_master,   # デバッグ用
        "event_log":       _cascade_event_log,  # ストーリー文章生成用
        "predicted_kimete": kimete,        # 決まり手フィルタ用（_judge_skipが参照）
    }


# ============================================================
# STEP 6  tenkai_pattern の決定（矛盾なし版）
# ============================================================

def _decide_tenkai_pattern(nige_prob: float, escape_rank: str, race_judgment: dict) -> str:
    """
    s1_prob（=nige_prob）と escape_rank を「同一軸」で判定する。

    【改善③】BT結果でCパターンが55%を占め的中率の天井になっていた原因を修正。
    旧バグ①: escape_rank=中 かつ nige_prob>=0.60 なのに無条件でC → Aに近いのに拮抗扱い
    旧バグ②: escape_rank=中 かつ nige_prob<0.48 かつ dh_ok=False → D相当なのにC扱い
    旧バグ③: escape_rank=高 かつ nige_prob<0.55 かつ main_scoreなし → Cにしていたが
              逃げ「高」判定なのに拮抗は矛盾、Aに引き上げ

    修正後のロジック:
      escape_rank=高  → A/B が基本。Cは使わない（逃げ力高いのに拮抗は矛盾）
      escape_rank=中  → nige_prob 60%超はB/A判定（旧Cバグ修正）
                         nige_prob 48%未満 かつ 主役もなければD
      escape_rank=低  → B/D のみ（変更なし）

    Returns
    -------
    "A" 鉄板逃げ / "B" 主役展開 / "C" 拮抗 / "D" 荒れ
    """
    mp       = (race_judgment.get("main_player")  or {})
    dh       = (race_judgment.get("dark_horse")   or {})
    ms_raw   = _safe(mp.get("main_score", 0))
    dh_ok    = dh.get("is_valid", False)

    ms_has_main = ms_raw > 0.005   # 主役候補が存在する
    ms_strong   = ms_raw >= 0.03   # 主役候補が強い

    if escape_rank == "高":
        # 【修正③】逃げ力「高」の判定を受けているのにCにしない
        if nige_prob >= 0.65:
            return "A"
        elif nige_prob >= 0.55:
            return "A" if not ms_strong else "B"
        else:
            # nige_prob<0.55 でも escape_rank=高 → 主役がいればB、いなければA
            # （旧コード: ms_has_mainがFalseならC → 修正: Aに変更）
            return "B" if ms_strong else "A"

    elif escape_rank == "中":
        if nige_prob >= 0.60:
            # 【修正①】逃げ60%超は「拮抗」ではなくAかB
            # 主役が強ければBも混在（両建て）、弱ければA寄り
            return "B" if ms_strong else "A"
        elif nige_prob >= 0.48:
            return "B" if ms_has_main else "C"
        else:
            # 【修正②】主役なし・穴なし → D（展開全く読めない＝見送り方向）
            if dh_ok:
                return "D"
            elif ms_has_main:
                return "B"
            else:
                return "D"   # 旧コード: C → 修正: D（主役も穴も読めないならD）

    else:  # escape_rank == "低"
        if ms_has_main:
            return "B"
        elif dh_ok:
            return "D"
        else:
            return "D"


# ============================================================
# STEP 7  シナリオA+B を統合して最終買い目を生成
# ============================================================

def _merge_scenarios(
    scenario_a: dict,
    scenario_b: dict,
    nige_prob:  float,
    tenkai_pattern: str,
    max_bets: int = 12,
) -> list[dict]:
    """
    シナリオA買い目 + シナリオB買い目を統合し、本線→押さえの順で max_bets 点に絞る。

    【設計方針】
    「本線N点→押さえM点」をパターン別に直接指定し、
    本線が押さえより少なくなる逆転現象を構造的に防ぐ。

    本線＝最も起きやすい展開の主軸買い目（必ず押さえより多い）
    押さえ＝サブシナリオの保険（余裕があれば追加する）

    パターン別の本線・押さえ点数（12点基準）:
      A       : 本線=逃げ  9点 / 押さえ=崩れのみ   3点  → 合計12点
      A_strong: 本線=逃げ 10点 / 押さえ=崩れのみ   2点  → 合計12点
                ※ nige_prob >= 0.85 の場合。B_main（主役1着）を押さえから除外し
                   「逃げ堅い」という考察と押さえ買い目の矛盾を解消する。
      B : 本線=主役  7点 / 押さえ=逃げ残+崩れ   5点  → 合計12点
      C : 本線=逃+主 6点 / 押さえ=崩れ・漁夫    3点  → 合計 9点
      D : 本線=主+崩 7点 / 押さえ=逃げ残        5点  → 合計12点

    【矛盾解消】nige_prob >= 0.85（逃げ堅い）のとき:
      押さえを B_collapse（崩れ）のみに限定する。
      B_main（主役1着）を押さえに混入させない。
      → 考察「①の逃げは堅い」と押さえ「②が1着」が矛盾する状況を防ぐ。
    """
    # ── 逃げ鉄板フラグ（nige_prob >= 0.85）────────────────────────────
    # このフラグが立つと押さえから B_main を除外し、崩れのみに絞る
    nige_strong = (nige_prob >= 0.85)

    # ── パターン別の本線・押さえ点数定義 ────────────────────────────
    if tenkai_pattern == "A" and nige_strong:
        honsen_n, osaae_n = 10, 2   # 逃げ鉄板強: 本線10 / 崩れ押さえ2
    else:
        _SLOTS: dict[str, tuple[int, int]] = {
            "A": (9, 3),   # 本線9 / 押さえ3  = 12点
            "B": (7, 5),   # 本線7 / 押さえ5  = 12点
            "C": (6, 6),   # 本線6 / 押さえ6  = 12点（両建て均等）
            "D": (7, 5),   # 本線7 / 押さえ5  = 12点
        }
        honsen_n, osaae_n = _SLOTS.get(tenkai_pattern, (6, 4))

    # プール取得
    buys_a          = scenario_a.get("buys",          [])
    buys_b_main     = scenario_b.get("buys_main",     [])
    buys_b_collapse = scenario_b.get("buys_collapse", [])
    buys_b_sc       = scenario_b.get("buys_sc",       [])

    # 重複除去しながら上位を選ぶ（seen は関数全体で共有）
    seen: set[str] = set()

    def _take(pool: list[dict], n: int) -> list[dict]:
        taken = []
        for b in pool:
            if len(taken) >= n:
                break
            if b["combo"] not in seen:
                seen.add(b["combo"])
                taken.append(b)
        return taken

    # ── 本線プール構築 ───────────────────────────────────────────────
    if tenkai_pattern == "A":
        # 逃げ鉄板: 逃げ買い目のみ本線
        honsen_pool = buys_a

    elif tenkai_pattern == "B":
        # 主役展開: 主役買い目のみ本線
        honsen_pool = buys_b_main

    elif tenkai_pattern == "C":
        # 拮抗: 逃げ・主役を確率降順でブレンド（均等に混ぜる）
        honsen_pool = sorted(
            buys_a + buys_b_main,
            key=lambda x: x["prob"], reverse=True,
        )

    else:  # D
        # 荒れ: 主役＋崩れを本線（逃げは薄い）
        honsen_pool = sorted(
            buys_b_main + buys_b_collapse,
            key=lambda x: x["prob"], reverse=True,
        )

    honsen = _take(honsen_pool, honsen_n)

    # ── 押さえプール構築（本線で使った買い目は seen で自動除外）────
    if tenkai_pattern == "A":
        if nige_strong:
            # 逃げ鉄板強（≥85%）: 崩れのみ押さえ。B_main（主役1着）は一切混入しない。
            # 「①の逃げは堅い」という考察と「②が1着」という押さえの矛盾を解消する。
            osaae_pool = sorted(
                buys_b_collapse + buys_b_sc,
                key=lambda x: x["prob"], reverse=True,
            )
        else:
            # 通常のAパターン: 崩れ・漁夫を押さえ（存在しなければ主役の上位を追加）
            osaae_pool = sorted(
                buys_b_collapse + buys_b_sc + buys_b_main,
                key=lambda x: x["prob"], reverse=True,
            )

    elif tenkai_pattern == "B":
        # 逃げ残存を最優先、次いで崩れ・漁夫
        osaae_pool = sorted(
            buys_a + buys_b_collapse + buys_b_sc,
            key=lambda x: x["prob"], reverse=True,
        )

    elif tenkai_pattern == "C":
        # 崩れ・漁夫を押さえ
        osaae_pool = sorted(
            buys_b_collapse + buys_b_sc,
            key=lambda x: x["prob"], reverse=True,
        )

    else:  # D
        # 逃げ残存を押さえ、足りなければ漁夫
        osaae_pool = sorted(
            buys_a + buys_b_sc,
            key=lambda x: x["prob"], reverse=True,
        )

    osaae = _take(osaae_pool, osaae_n)

    # ── 本線→押さえの順で結合（本線が先頭に来る）────────────────────
    merged = honsen + osaae

    # tier付与（本線/押さえ）
    for b in honsen:
        b["tier"] = "本線"
    for b in osaae:
        b["tier"] = "押さえ"

    return merged[:max_bets]


# ============================================================
# メインエントリ
# ============================================================

def build_scenarios(
    results:              list[dict],
    race_judgment:        dict,
    combos:               list[dict] | None = None,
    ininage_master:       dict | None = None,
    tenkai_venue:         dict | None = None,
    tenkai_national:      dict | None = None,
    venue:                str  = "",
    venue_stats:          dict | None = None,
    max_bets:             int  = 12,
    kaiho_venue:          dict | None = None,
    kaiho_national:       dict | None = None,
    course_weight:        float = 0.3,
    jizen_eval:           dict | None = None,
    venue_course_master:  dict | None = None,   # (選手名, 会場名, コース) → row_dict
) -> dict:
    """
    シナリオ分岐型で買い目を生成し、bet_suggestions dict を返す。

    Parameters
    ----------
    results       : calc_race_indices の出力（6艇分のデータ）
    race_judgment : calc_race_indices の出力（レース全体の判定）
    combos        : _calc_3rentan_probs_v2 の出力（120通りの確率）
                    None の場合は race_judgment から first_prob_map を使う簡易計算
    ininage_master: イン逃げ残存マスタ（venue別の2・3着率）
    tenkai_venue  : 展開別残存マスタ（会場別）
    tenkai_national: 展開別残存マスタ（全国）
    venue         : 会場名
    venue_stats   : 会場統計
    max_bets      : 最大買い目点数
    kaiho_venue   : コース開放連鎖マスタ（会場別）③
    kaiho_national: コース開放連鎖マスタ（全国）③
    jizen_eval    : evaluate_jizen.evaluate_all() の出力 dict。
                    渡すと ①in_nige / ②aisho / ⑤tenkai を主軸に切り替わる。
                    None の場合は旧挙動（combo集計）を維持。

                    期待するキー:
                      "in_nige"           : list[str]         記号（◎○△空白）
                      "aisho"             : list[str]         記号
                      "aisho_raw_scores"  : list[float|None]  生スコア
                      "tenkai"            : list[str]         記号
                      "tenkai_raw_scores" : list[float|None]  生スコア
                      "jizaisei"          : list[str]         記号（崩れ判定に使用）

    Returns
    -------
    dict  load_race.py の bet_suggestions 互換
    """
    if not results:
        return _empty_result()

    combos = combos or []

    # ── STEP 1: 逃げ確率確定 ─────────────────────────────────────────
    nige_prob, escape_rank = _resolve_nige_prob(
        race_judgment, combos,
        jizen_eval=jizen_eval,
        venue_stats=venue_stats,
        venue=venue,
    )
    fly_prob = round(1.0 - nige_prob, 4)

    # ── STEP 2: シナリオA ────────────────────────────────────────────
    # main_waku は渡さない（1号艇のみ除外、主役も2着候補に含める）
    scenario_a = _build_scenario_a(
        nige_prob      = nige_prob,
        combos         = combos,
        ininage_master = ininage_master or {},
        venue          = venue,
        results        = results,
        jizen_eval     = jizen_eval,
        venue_stats    = venue_stats,   # 会場別コースバイアス補正のために追加
    )

    # ── STEP 3-5: シナリオB ──────────────────────────────────────────
    scenario_b = _build_scenario_b(
        nige_prob           = nige_prob,
        combos              = combos,
        results             = results,
        race_judgment       = race_judgment,
        tenkai_venue        = tenkai_venue,
        tenkai_national     = tenkai_national,
        kaiho_venue         = kaiho_venue,
        kaiho_national      = kaiho_national,
        course_weight       = course_weight,
        jizen_eval          = jizen_eval,
        venue_stats         = venue_stats,
        venue_course_master = venue_course_master,
    )

    # ── STEP 6: tenkai_pattern 決定 ──────────────────────────────────
    tenkai_pattern = _decide_tenkai_pattern(nige_prob, escape_rank, race_judgment)

    # ── STEP 7: 統合・最終買い目生成 ────────────────────────────────
    merged = _merge_scenarios(scenario_a, scenario_b, nige_prob, tenkai_pattern, max_bets)

    # candidates（既存コード完全互換フォーマット）
    # write_numeric_sheet / _generate_tenkai_story 等が参照する全キーを含める
    _scenario_reason = {
        "A":          "逃げシナリオ",
        "B_main":     "主役シナリオ",
        "B_collapse": "崩れシナリオ",
        "B_sc":       "漁夫シナリオ",
    }
    candidates = [
        {
            "combo":             b["combo"],
            "prob":              round(b["prob"], 5),
            "prob_pct":          round(b["prob"] * 100, 2),   # ← write_numeric_sheet が参照
            "himo_score":        round(b["prob"] * 100, 4),   # 暫定: prob を代替値として使用
            "scenario":          b["scenario"],
            "is_orkaeshi":       False,
            "is_orkaeshi_23":    False,
            "is_sc_bet":         b["scenario"] == "B_sc",
            "is_fallback_bet":   b["scenario"] == "B_collapse",
            "is_dh_bet":         False,
            "first":             b["first"],
            "second":            b["second"],
            "third":             b["third"],
            "reason":            _scenario_reason.get(b["scenario"], b["scenario"]),
            "tier":              b.get("tier", "本線"),   # 本線/押さえ（load_race.py側でセパレーター挿入に使用）
        }
        for b in merged
    ]

    buy_list = [b["combo"] for b in merged]

    # ── 合成オッズ計算 ───────────────────────────────────────────────
    # 合成オッズ = 回収率75%ライン / 買い目合計確率
    # 【設計方針】
    # 合成オッズは参考表示のみ。見送り判定には使用しない。
    # 見送り判定は lr_probs._should_skip_race に統一する（事前情報のみで完結）。
    total_prob   = sum(b["prob"] for b in merged) or 0.001
    syn_odds     = round(0.75 / total_prob, 2) if total_prob > 0 else None
    SYN_ODDS_GOOD = 8.0   # 余裕あり閾値（参考表示用）
    if syn_odds is None:
        margin_verdict = "-"
        margin_ratio   = None
    elif syn_odds >= SYN_ODDS_GOOD:
        margin_verdict = "余裕あり"
        margin_ratio   = round(syn_odds / SYN_ODDS_GOOD, 3)
    elif syn_odds >= 4.0:
        margin_verdict = "要確認"
        margin_ratio   = round(syn_odds / SYN_ODDS_GOOD, 3)
    else:
        margin_verdict = "低め（参考）"
        margin_ratio   = round(syn_odds / SYN_ODDS_GOOD, 3)
    req_syn_odds = SYN_ODDS_GOOD

    # ── 見送り判定 ───────────────────────────────────────────────────
    skip, skip_reason = _judge_skip(nige_prob, escape_rank, race_judgment,
                                    scenario_b=scenario_b)

    # ── ストーリー生成 ───────────────────────────────────────────────
    story = generate_story(
        nige_prob     = nige_prob,
        escape_rank   = escape_rank,
        scenario_a    = scenario_a,
        scenario_b    = scenario_b,
        tenkai_pattern= tenkai_pattern,
        candidates    = candidates,
        race_judgment = race_judgment,
        results       = results,
    )

    # ── first_prob_map（既存互換） ───────────────────────────────────
    first_prob_map: dict[str, float] = {}
    for c in combos:
        w = str(c.get("first", ""))
        first_prob_map[w] = first_prob_map.get(w, 0.0) + _safe(c.get("prob", 0))

    return {
        # ── 既存コード互換キー ──────────────────────────────────────
        "s1_prob":               nige_prob,
        "first_prob_map":        first_prob_map,
        "tenkai_pattern":        tenkai_pattern,
        "tenkai_pattern_policy": _tenkai_policy_text(tenkai_pattern),
        "buy_list":              buy_list,
        "candidates":            candidates,
        "point_count":           len(buy_list),
        "theory_syn_odds":       syn_odds,
        "required_syn_odds":     req_syn_odds,
        "margin_ratio":          margin_ratio,
        "margin_verdict":        margin_verdict,
        "skip":                  skip,
        "skip_reason":           skip_reason,
        "escape_score":          round(nige_prob * 100, 1),
        "tobi_score":            round(fly_prob  * 100, 1),
        "fly_axes":              [scenario_b["main_player"]["main_waku"]],
        "axis1":                 "1",
        "axis2":                 scenario_b["main_player"]["main_waku"],
        "scenario_type":         _scenario_type_str(tenkai_pattern),
        "jizen_formation":       {},
        # ── 新規キー ────────────────────────────────────────────────
        "scenario_a":            scenario_a,
        "scenario_b":            scenario_b,
        "story":                 story,
        "nige_prob":             nige_prob,
        "fly_prob":              fly_prob,
        "escape_rank":           escape_rank,
    }


def _empty_result() -> dict:
    return {
        "s1_prob": 0.0, "first_prob_map": {}, "tenkai_pattern": "C",
        "buy_list": [], "candidates": [], "point_count": 0,
        "theory_syn_odds": None, "required_syn_odds": None,
        "margin_ratio": None, "margin_verdict": "-",
        "skip": False, "skip_reason": "", "escape_score": 50, "tobi_score": 50,
        "fly_axes": [], "axis1": "-", "axis2": "-",
        "scenario_type": "-", "jizen_formation": {},
        "scenario_a": {}, "scenario_b": {}, "story": "データ不足",
        "nige_prob": 0.0, "fly_prob": 1.0, "escape_rank": "中",
        "tenkai_pattern_policy": "-",
    }


def _tenkai_policy_text(tp: str) -> str:
    return {
        "A": "1着1号艇固定・ヒモ絞り（逃げ圧倒）",
        "B": "主役1着軸・逃げ残存フォロー",
        "C": "1号艇＋主役の2頭軸・ヒモ広め",
        "D": "穴候補込みの広め買い",
    }.get(tp, "-")


def _scenario_type_str(tp: str) -> str:
    return {
        "A": "逃げ軸流し",
        "B": "主役軸流し",
        "C": "両建てフォーメーション",
        "D": "荒れ広め",
    }.get(tp, "-")


def _judge_skip(
    nige_prob:      float,
    escape_rank:    str,
    race_judgment:  dict,
    scenario_b:     dict | None = None,
) -> tuple[bool, str]:
    """見送り判定

    【決まり手フィルタ】
    バックテスト結果（2025-10-01〜2026-03-27 / 1,779レース）より:
      まくり・まくり差し・差し の3決まり手は合計455件・的中率0%。
      1号艇逃げ固定のシナリオAは逃げ以外の展開で成立しない。
      シナリオBの主役決まり手が非逃げ系の場合、
      現行の2着スコア・3着スコアが機能しないため自動見送りとする。

    nige_prob >= 0.50（逃げが優勢）のときは逃げシナリオAが主体となるため
    決まり手フィルタを適用しない。逃げが劣勢（< 0.50）の場面のみ
    シナリオBの predicted_kimete を確認する。
    """
    # ── 決まり手フィルタ（BT的中率0%の展開を除外） ──────────────────
    # 【設計方針】
    # 合成オッズ・逃げ確率による見送りは lr_probs._should_skip_race に統一。
    # scenario_engine 側では「展開的に成立しない」ケースのみ見送りとする。
    _SKIP_KIMETE = {"まくり", "まくり差し", "差し"}
    if scenario_b is not None and nige_prob < 0.50:
        predicted_kimete = scenario_b.get("predicted_kimete", "")
        if predicted_kimete in _SKIP_KIMETE:
            return True, f"[!]見送り推奨（主役決まり手「{predicted_kimete}」― 逃げ劣勢レースで的中実績なし）"

    return False, ""


# ============================================================
# generate_story  展開ストーリー生成
# ============================================================

def generate_story(
    nige_prob:      float,
    escape_rank:    str,
    scenario_a:     dict,
    scenario_b:     dict,
    tenkai_pattern: str,
    candidates:     list[dict],
    race_judgment:  dict,
    results:        list[dict],
    skip:           bool = False,
    skip_reason:    str  = "",
) -> str:
    """
    新聞右下欄と同じ感覚の展開考察＋参考買い目を生成する。

    【構成】
      【展開考察】
        1行目: ①の逃げ判定と根拠（1文）＋主役紹介
        ・逃げるなら    → 2・3着候補
        ・主役が来るなら → 2・3着候補
        ・崩れれば      → 浮上候補
        ※見送り推奨の場合はその旨を末尾に追記

      【参考買い目】
        ◎○△で優先度を付けて横並び表示
        candidates の prob 降順（1位◎、2〜3位○、4位以下△）
    """
    rj  = race_judgment or {}
    mp  = scenario_b.get("main_player", {}) or {}

    # ── 基本情報の取り出し ──────────────────────────────────────────
    main_w  = str(mp.get("main_waku",  "-"))
    main_t  = mp.get("main_type",  "攻め系")
    sub_w   = str(mp.get("sub_waku",  "") or "")

    # ── 主役の根拠記号を取得（aisho 記号を考察に添える）────────────
    # 買い目の1着軸（main_w）と考察の「主役」を同じ艇にするため、
    # aisho 記号（相性評価）を括弧内に明示して根拠を透明化する
    _aisho_sym = ""
    je = rj.get("jizen_eval") or {}
    aisho_list = je.get("aisho", [])
    if main_w.isdigit():
        idx_main = int(main_w) - 1
        if idx_main < len(aisho_list):
            _aisho_sym = aisho_list[idx_main] or ""
    # results に _jizen_aisho キーがあればそちらを優先
    for r in results:
        if str(r.get("waku", "")) == main_w:
            v = r.get("_jizen_aisho", "")
            if v:
                _aisho_sym = v
            break
    basis_note = f"（相性{_aisho_sym}）" if _aisho_sym else ""

    # 逃げ判定の言葉
    nige_pct = f"{nige_prob * 100:.0f}%"
    if escape_rank == "高":
        nige_judge = f"①の逃げは堅い（逃げ力：高／{nige_pct}）。"
    elif escape_rank == "低":
        nige_judge = f"①の逃げは危うい（逃げ力：低／{nige_pct}）。"
    else:
        if nige_prob >= 0.65:
            nige_judge = f"①の逃げは有力（逃げ力：中高／{nige_pct}）。"
        elif nige_prob >= 0.55:
            nige_judge = f"①の逃げはやや有利（逃げ力：中／{nige_pct}）。"
        elif nige_prob >= 0.45:
            nige_judge = f"①の逃げは五分五分（逃げ力：中／{nige_pct}）。"
        else:
            nige_judge = f"①の逃げはやや危うい（逃げ力：中低／{nige_pct}）。"

    # 主役の決まり手を短く整形
    main_type_short = main_t.replace("系", "").replace("攻め", "").strip() or "攻め"

    # 対抗主役
    sub_note = f"対抗は{_wn(sub_w)}。" if sub_w and sub_w not in ("-", main_w, "") else ""

    # ── 逃げた場合の2・3着候補 ──────────────────────────────────────
    # シナリオAは主役を除外しない設計に変更済みのため、top_2ndをそのまま使用
    a_top2    = [w for w, _ in scenario_a.get("top_2nd", [])[:4]][:3]
    a_top3    = [w for w, _ in scenario_a.get("top_3rd", [])[:4]][:3]
    a_2nd_str = "・".join(_wn(w) for w in a_top2) if a_top2 else "-"
    a_3rd_str = "・".join(_wn(w) for w in a_top3) if a_top3 else "-"

    # ── 主役が来た場合の2・3着候補 ──────────────────────────────────
    b_top2    = [w for w, _ in scenario_b.get("second_sorted", [])[:3]]
    b_top3    = [w for w, _ in scenario_b.get("third_sorted",  [])[:3]]
    b_2nd_str = "・".join(_wn(w) for w in b_top2) if b_top2 else "-"
    b_3rd_str = "・".join(_wn(w) for w in b_top3) if b_top3 else "-"

    # ── 崩れた場合の浮上候補（タイプ別） ──────────────────────────────
    ct          = scenario_b.get("collapse_top", [])
    ct_str      = "・".join(_wn(w) for w, _ in ct[:2]) if ct else "-"

    # buys_b_collapse から上位コンボを取り出してタイプ別説明を生成
    _buys_col   = scenario_b.get("buys_collapse", [])
    _col_by_type: dict[str, list[str]] = {}
    for _bc in _buys_col[:6]:
        _ctype  = _bc.get("collapse_type", "?")
        _cw     = _bc.get("first", "")
        _newk   = _bc.get("new_kimete", "")
        _label  = f"{_wn(_cw)}({_newk})" if _newk else _wn(_cw)
        if _ctype not in _col_by_type:
            _col_by_type[_ctype] = []
        if _label not in _col_by_type[_ctype]:
            _col_by_type[_ctype].append(_label)

    _TYPE_LABEL = {
        "X": "まくり崩れ→内台頭",
        "Y": "差し崩れ→外台頭",
        "Z": "まくり差し崩れ",
    }
    _collapse_lines: list[str] = []
    for _ct, _wlist in _col_by_type.items():
        _tlabel = _TYPE_LABEL.get(_ct, f"タイプ{_ct}")
        _wstr   = "・".join(_wlist[:2])
        _collapse_lines.append(f"　　[{_tlabel}] {_wstr}")

    if _collapse_lines:
        _col_detail_str = "\n".join(_collapse_lines)
    else:
        _col_detail_str = f"　　{ct_str}が浮上"

    # ── 展開考察の組み立て ──────────────────────────────────────────
    lines: list[str] = []
    lines.append("【展開考察】")
    main_intro = f"{_wn(main_w)}の{main_type_short}が主役{basis_note}。{sub_note}"
    lines.append((f"{nige_judge}。{main_intro}").replace("。。", "。").strip())
    lines.append(f"・逃げるなら　　　→ 2着：{a_2nd_str}　3着：{a_3rd_str}")
    lines.append(f"・{_wn(main_w)}{main_type_short}なら → 2着：{b_2nd_str}　3着：{b_3rd_str}")
    lines.append(f"・崩れれば（展開別）→")
    lines.append(_col_detail_str)
    lines.append("")

    # 逃げ確率≥85%のとき押さえの意味を明示（「逃げ堅い」と押さえの論理矛盾を解消）
    if nige_prob >= 0.85:
        lines.append(f"※押さえは①逃げ失敗時の崩れ保険（崩れ確率{(1 - nige_prob) * 100:.0f}%）")
        lines.append("")

    # 見送りの場合は注記を1行追加（買い目は参考として必ず出力する）
    if skip and skip_reason:
        lines.append(f"※ {skip_reason}（以下参考）")
        lines.append("")

    # ── 買い目（本線 / 押さえ）──────────────────────────────────────
    def _fmt_combos(clist):
        if not clist:
            return "─"
        combos = [c.get("combo", "") for c in clist if c.get("combo")]
        rows = []
        for i in range(0, len(combos), 6):
            rows.append("　".join(combos[i:i + 6]))
        return "\n".join(rows)

    if not candidates:
        lines.append("【本線】─")
    else:
        honsen = [c for c in candidates if c.get("tier", "本線") == "本線"]
        osaae  = [c for c in candidates if c.get("tier") == "押さえ"]
        lines.append("【本線】")
        lines.append(_fmt_combos(honsen))
        if osaae:
            lines.append("【押さえ】")
            lines.append(_fmt_combos(osaae))

    return "\n".join(lines)


# ============================================================
# load_race.py への組み込み方（コメント）
# ============================================================
#
# 【変更箇所 1】 import 追加
#   from scenario_engine import build_scenarios
#
# 【変更箇所 2】 calc_race_indices の末尾付近
#   旧: bet_suggestions = _suggest_3rentan(results, race_judgment, ...)
#   新: from scenario_engine import build_scenarios
#       bet_suggestions = build_scenarios(
#           results         = results,
#           race_judgment   = race_judgment,
#           combos          = _calc_3rentan_probs_v2(results, ...),  # 既存の呼び出し結果を渡す
#           ininage_master  = ininage_master,
#           tenkai_venue    = tenkai_venue_master,
#           tenkai_national = tenkai_national_master,
#           venue           = venue,
#           venue_stats     = venue_stats,
#       )
#
# 【変更箇所 3】 展開ストーリー出力
#   旧: story = _generate_tenkai_story(results, venue, venue_stats, race_judgment, bet_suggestions)
#   新: story = bet_suggestions.get("story", "")  # build_scenarios 内で生成済み
#
# 【変更箇所 4】 _suggest_3rentan と _generate_tenkai_story は
#   削除しても良いし、フォールバックとして残しても良い。
#
# 【変更箇所 5】 買い目リスト行（Excel）への本線/押さえセパレーター挿入
#   candidates の各要素に tier キー（"本線"/"押さえ"）が付いている。
#   Excel書き込みループ内で tier が切り替わるタイミングに行挿入する:
#
#   prev_tier = None
#   for c in bet_suggestions["candidates"]:
#       t = c.get("tier", "本線")
#       if t != prev_tier:
#           ws.write(row, col, f"◆{t}", separator_fmt)  # セパレーター行
#           row += 1
#       ws.write(row, col, c["combo"])
#       ... (prob等の書き込み)
#       row += 1
#       prev_tier = t
#
# 【変更箇所 6】 course_weight パラメータ（顔ぶれズレ調整）
#   build_scenarios(..., course_weight=0.3) で渡せる。
#   値が大きいほどコース有利（内コース）が強く出る（0.0〜1.0）。
#   デフォルト0.3 = ability70% + コースバイアス30%
#   マスタ(tenkai_survival/kaiho_chain)がヒットした場合は course_weight は無効。
