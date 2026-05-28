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

def _resolve_nige_prob(race_judgment: dict, combos: list[dict]) -> tuple[float, str]:
    """
    s1_prob（確率モデル）と escape_rank（定性スコア）を統合して
    最終的な「逃げシナリオ発生確率」を返す。

    Returns
    -------
    nige_prob : float   逃げシナリオ発生確率（0〜1）
    escape_rank: str    "高"/"中"/"低"
    """
    # 確率モデルから s1_prob を取得
    first_prob_map: dict[str, float] = {}
    for c in combos:
        w = str(c.get("first", ""))
        first_prob_map[w] = first_prob_map.get(w, 0.0) + _safe(c.get("prob", 0))

    s1_prob_raw = first_prob_map.get("1", 0.0)

    # 定性スコアから escape_rank を取得
    w1_escape   = (race_judgment.get("w1_escape") or {})
    escape_rank = w1_escape.get("escape_rank", "中")

    # escape_rank は _judge_w1_escape（被決まり手ベース）の判定を絶対優先する
    # 確率モデル（s1_prob_raw）による上書きは行わない
    # 理由: 統計確率モデルはまだ被決まり手を反映していないため
    #       被まくり差し48%のような艇でも高い確率を出してしまう
    #
    # nige_prob は escape_rank に応じた上限・下限でキャップする
    if escape_rank == "低":
        nige_prob = min(s1_prob_raw, 0.35)   # 低は35%上限
    elif escape_rank == "高":
        nige_prob = max(s1_prob_raw, 0.55)   # 高は55%下限
    else:
        nige_prob = s1_prob_raw              # 中はそのまま

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
    main_waku: str = "",  # 主役の艇番（逃げ展開の2着候補から除外）
) -> dict:
    """
    シナリオA：1号艇が逃げた場合の 2・3着候補と買い目を構築。

    使用データ:
      ① イン逃げ残存マスタ（venue別の2着・3着以内率）
      ② combo確率（1号艇1着のcomboから2・3着を集計）
    """
    # ── イン逃げ残存マスタから会場の2着率を取得 ────────────────────────
    venue_2nd_map = {}
    venue_3rd_map = {}
    if venue and ininage_master:
        vd = ininage_master.get(venue, {})
        if isinstance(vd, dict):
            venue_2nd_map = vd.get("_2nd", vd) or {}  # 旧形式互換
            venue_3rd_map = vd.get("_3rd", {}) or {}

    # ── combo確率から1号艇1着の2・3着分布を集計 ────────────────────────
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

    # 2着候補：combo確率 60% + 残存マスタ 40% でブレンド
    second_scores: dict[str, float] = {}
    for w in [str(r["waku"]) for r in results
              if str(r.get("waku", "")) != "1" and str(r.get("waku", "")) != main_waku]:
        combo_w = second_prob_sum.get(w, 0.0)
        mast_w  = _safe(venue_2nd_map.get(w, 0))
        total_combo = sum(second_prob_sum.values()) or 1.0
        total_mast  = sum(_safe(v) for v in venue_2nd_map.values() if v) or 1.0
        score = (combo_w / total_combo) * 0.60 + (mast_w / total_mast) * 0.40 if total_mast > 0 else combo_w / total_combo
        second_scores[w] = round(score, 5)

    second_sorted = sorted(second_scores.items(), key=lambda x: x[1], reverse=True)

    # 3着候補：combo確率から集計
    third_scores: dict[str, float] = {}
    total_third = sum(third_prob_sum.values()) or 1.0
    for w, p in third_prob_sum.items():
        if w != "1":
            third_scores[w] = round(p / total_third, 5)
    third_sorted = sorted(third_scores.items(), key=lambda x: x[1], reverse=True)

    # ── 買い目生成（1着=1固定）────────────────────────────────────────
    # 上位2着候補 × 上位3着候補の組み合わせ
    top2nd = [w for w, _ in second_sorted[:3]]
    top3rd = [w for w, _ in third_sorted[:4]]

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
) -> dict:
    """
    逃げない場合の「主役」を特定する。

    判定軸:
      1着確率（combo集計）× 攻撃有効性スコア（race_judgmentから取得）
    """
    first_prob_map: dict[str, float] = {}
    for c in combos:
        w = str(c.get("first", ""))
        if w != "1":
            first_prob_map[w] = first_prob_map.get(w, 0.0) + _safe(c.get("prob", 0))

    # race_judgment の main_player を優先（既に計算済みならそれを使う）
    mp = race_judgment.get("main_player") or {}
    main_waku = str(mp.get("main_waku", ""))
    main_type = mp.get("main_type", "-")
    main_score = _safe(mp.get("main_score", 0))

    if not main_waku or main_waku == "-":
        # フォールバック: 1着確率が最大の艇を主役とする
        if first_prob_map:
            main_waku = max(first_prob_map, key=lambda w: first_prob_map[w])
            main_type = "攻め系"
            main_score = first_prob_map.get(main_waku, 0.0)

    # 主役の1着確率（確率モデル由来）
    main_1st_prob = first_prob_map.get(main_waku, 0.0)

    # 対抗主役（主役の次点）
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
            cb = _COURSE_BIAS.get(c_str, 0.6)
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
) -> dict:
    """
    シナリオB：主役が1着に来た場合の 2・3着と崩れシナリオを構築。

    【設計方針】
    combo確率（120通りの平均的基準値）への依存を廃止し、
    「このレースで何が起きるか」を直接計算する。

    2着スコア = 展開別残存マスタ「2着率」 × 個人能力補正
    3着スコア = 展開別残存マスタ「3着率」 × 個人能力補正
                （3着以内率 - 2着率 = 純粋な3着率）

    マスタがない場合のみcombo確率にフォールバック。
    """
    fly_prob = 1.0 - nige_prob
    mp       = _identify_main_player(combos, results, race_judgment)
    main_w   = mp["main_waku"]
    main_t   = mp.get("main_type", "")

    # ── 個人能力マップ構築 ────────────────────────────────────────────
    # rel_win1（相対1着率）× idx3（3着指数）を能力スコアとして使用
    rel_map  = {r["waku"]: max(_safe(r.get("rel_win1"), 0.02), 0.02) for r in results}
    idx3_map = {r["waku"]: max(_safe(r.get("idx3"),     0.02), 0.02) for r in results}

    def _ability(w: str) -> float:
        """個人能力スコア（rel_win1 × idx3 の幾何平均）"""
        import math
        r = rel_map.get(w, 0.02)
        i = idx3_map.get(w, 0.02)
        return math.sqrt(r * i)

    # ── 主役の進入コースを取得 ──────────────────────────────────────
    main_result = next((r for r in results if r["waku"] == main_w), {})
    main_course = str(int(float(
        main_result.get("course") or main_result.get("進入コース") or main_w
    )))

    # ── 決まり手キー変換 ────────────────────────────────────────────
    _TYPE_TO_KIMETE = {
        "差し":       "差し",
        "差し系":     "差し",
        "まくり":     "まくり",
        "まくり系":   "まくり",
        "まくり差し": "まくり差し",
        "まくり差し系": "まくり差し",
        "攻め系":     "まくり",   # フォールバック
    }
    kimete = _TYPE_TO_KIMETE.get(main_t, "まくり")

    # ── 展開別残存マスタから2着率・3着率を取得 ──────────────────────
    venue = (race_judgment or {}).get("venue", "")

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

    # ── ⑤ 崩れシナリオ（apply_eventで連鎖化）─────────────────────────
    dh       = (race_judgment.get("dark_horse") or {})
    cb       = (race_judgment.get("conflict_map") or {}).get("collapse_beneficiary", []) or []
    dh_cands = dh.get("dark_horse_candidates", []) or []

    if dh_cands:
        collapse_top = [(str(w), _safe(s)) for w, s, *_ in dh_cands[:2]]
    elif cb:
        collapse_top = [(str(w), _safe(s)) for w, s in cb[:2]]
    else:
        other_fp = sorted(
            [(w, p) for w, p in mp["first_prob_map"].items()
             if w not in (main_w, "1")],
            key=lambda x: x[1], reverse=True
        )
        collapse_top = other_fp[:2]

    fb_prob = _safe((race_judgment.get("escape_fallback") or {}).get("fallback_prob", 0))

    # 崩れ時買い目：崩れ艇が主役に浮上した展開連鎖で2・3着を算出
    buys_b_collapse: list[dict] = []
    for cw, cs in collapse_top:
        cr = next((r for r in results if r["waku"] == cw), {})
        c_course = str(int(float(cr.get("course") or cr.get("進入コース") or cw)))
        c_kimete = kimete  # 同じ展開系で崩れを想定

        # 崩れ艇が動いた後のRaceStateを生成（主役失敗→崩れ艇が浮上）
        collapse_state = apply_event(initial_state, c_course, c_kimete, success=True)

        # 崩れ展開での残存スコアを連鎖計算
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
            c_top2 = sorted(c_sec_n.items(), key=lambda x: x[1], reverse=True)[:3]
            c_top3 = sorted(c_thi_n.items(), key=lambda x: x[1], reverse=True)[:4]
            for sec2, s2v in c_top2:
                for thi2, t2v in c_top3:
                    if thi2 == sec2:
                        continue
                    prob = s2v * t2v * fly_prob * (1.0 - mp["main_1st_prob"])
                    buys_b_collapse.append({
                        "combo":    f"{cw}-{sec2}-{thi2}",
                        "first":    cw,
                        "second":   sec2,
                        "third":    thi2,
                        "prob":     round(prob, 6),
                        "scenario": "B_collapse",
                    })
        else:
            # フォールバック: combo確率から集計
            for c in combos:
                if str(c.get("first", "")) == cw:
                    sec = str(c.get("second", ""))
                    thi = str(c.get("third",  ""))
                    if sec and thi and sec != cw and thi != cw and sec != thi:
                        prob = _safe(c.get("prob", 0)) * fly_prob * (1.0 - mp["main_1st_prob"])
                        buys_b_collapse.append({
                            "combo":    f"{cw}-{sec}-{thi}",
                            "first":    cw,
                            "second":   sec,
                            "third":    thi,
                            "prob":     round(prob, 6),
                            "scenario": "B_collapse",
                        })

    buys_b_collapse.sort(key=lambda x: x["prob"], reverse=True)
    buys_b_collapse = buys_b_collapse[:6]

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
      A : 本線=逃げ  8点 / 押さえ=崩れ・漁夫   2点  → 合計10点
      B : 本線=主役  6点 / 押さえ=逃げ残+崩れ   4点  → 合計10点
      C : 本線=逃+主 6点 / 押さえ=崩れ・漁夫    3点  → 合計 9点
      D : 本線=主+崩 6点 / 押さえ=逃げ残        2点  → 合計 8点
    """
    # ── パターン別の本線・押さえ点数定義 ────────────────────────────
    # (本線点数, 押さえ点数)  合計が max_bets を超えないよう設定
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
        # 崩れ・漁夫を押さえ（存在しなければ主役の上位を追加）
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
    results:          list[dict],
    race_judgment:    dict,
    combos:           list[dict] | None = None,
    ininage_master:   dict | None = None,
    tenkai_venue:     dict | None = None,
    tenkai_national:  dict | None = None,
    venue:            str  = "",
    venue_stats:      dict | None = None,
    max_bets:         int  = 12,
    kaiho_venue:      dict | None = None,
    kaiho_national:   dict | None = None,
    course_weight:    float = 0.3,  # コースバイアス重み（0.0〜1.0）
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

    Returns
    -------
    dict  load_race.py の bet_suggestions 互換
    """
    if not results:
        return _empty_result()

    combos = combos or []

    # ── STEP 1: 逃げ確率確定 ─────────────────────────────────────────
    nige_prob, escape_rank = _resolve_nige_prob(race_judgment, combos)
    fly_prob = round(1.0 - nige_prob, 4)

    # ── STEP 2: シナリオA ────────────────────────────────────────────
    scenario_a = _build_scenario_a(
        nige_prob     = nige_prob,
        combos        = combos,
        ininage_master= ininage_master or {},
        venue         = venue,
        results       = results,
        main_waku     = (race_judgment.get("main_player") or {}).get("main_waku", ""),
    )

    # ── STEP 3-5: シナリオB ──────────────────────────────────────────
    scenario_b = _build_scenario_b(
        nige_prob       = nige_prob,
        combos          = combos,
        results         = results,
        race_judgment   = race_judgment,
        tenkai_venue    = tenkai_venue,
        tenkai_national = tenkai_national,
        kaiho_venue     = kaiho_venue,
        kaiho_national  = kaiho_national,
        course_weight   = course_weight,
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
    #   buy_list の prob 合計が高いほど合成オッズは下がる（＝的中しやすいが安い）
    # required_syn_odds = 点数 × 単位オッズ ではなく、
    #   「この点数で買うなら最低このオッズが必要」＝ 1 / total_prob
    #   実際には 1/total_prob ~ syn_odds × (1/0.75) なので
    #   margin_ratio ~ 0.75 が基準値となる。
    # 判定: margin_ratio = syn_odds × total_prob
    #   = (0.75 / total_prob) × total_prob = 0.75（固定）→ 意味がない。
    # 正しい判定: 合成オッズが「点数 × 平均オッズ」に対して余裕があるか
    #   平均的な3連単オッズを仮定せず、回収率ラインだけで判定する。
    # 【修正①】合成オッズ見送り閾値を3倍→4倍に引き上げ
    # 根拠: BT結果で合成オッズ4倍未満レースが52%あり回収不可。
    #       4倍未満は期待値マイナスのため自動見送りとする。
    total_prob   = sum(b["prob"] for b in merged) or 0.001
    syn_odds     = round(0.75 / total_prob, 2) if total_prob > 0 else None
    SYN_ODDS_SKIP = 4.0   # 見送り閾値（BTデータから設定）
    SYN_ODDS_GOOD = 8.0   # 余裕あり閾値
    if syn_odds is None:
        margin_verdict = "-"
        margin_ratio   = None
    elif syn_odds >= SYN_ODDS_GOOD:
        margin_verdict = "余裕あり"
        margin_ratio   = round(syn_odds / SYN_ODDS_GOOD, 3)
    elif syn_odds >= SYN_ODDS_SKIP:
        margin_verdict = "要確認"
        margin_ratio   = round(syn_odds / SYN_ODDS_GOOD, 3)
    else:
        margin_verdict = "見送り有力"
        margin_ratio   = round(syn_odds / SYN_ODDS_GOOD, 3)
    req_syn_odds = SYN_ODDS_GOOD

    # ── 見送り判定 ───────────────────────────────────────────────────
    skip, skip_reason = _judge_skip(nige_prob, escape_rank, margin_verdict, race_judgment)

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
    margin_verdict: str,
    race_judgment:  dict,
) -> tuple[bool, str]:
    """見送り判定（シンプル化）"""
    # 逃げ鉄板 + ヒモ固まり → 低オッズ確実
    if nige_prob >= 0.72:
        return True, f"[!]見送り推奨（逃げ確率{nige_prob*100:.0f}%超・低オッズ濃厚）"
    # 合成オッズが買えない水準
    if margin_verdict == "見送り有力":
        return True, "[!]見送り推奨（合成オッズが回収率の目安を下回る）"
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

    w1_escape = rj.get("w1_escape", {}) or {}
    thr_w     = w1_escape.get("top_threat_waku", "-")
    thr_t     = w1_escape.get("top_threat_type", "-")

    # 逃げ判定の言葉
    nige_pct = f"{nige_prob * 100:.0f}%"
    if escape_rank == "高":
        nige_judge = f"①の逃げは堅い（逃げ力：高／{nige_pct}）。"
    elif escape_rank == "低":
        nige_judge = f"①の逃げは危うい（逃げ力：低／{nige_pct}）。"
    else:
        # escape_rank=中 でも確率で言葉を細分化（五分五分≒45〜55%のみ）
        if nige_prob >= 0.65:
            nige_judge = f"①の逃げは有力（逃げ力：中高／{nige_pct}）。"
        elif nige_prob >= 0.55:
            nige_judge = f"①の逃げはやや有利（逃げ力：中／{nige_pct}）。"
        elif nige_prob >= 0.45:
            nige_judge = f"①の逃げは五分五分（逃げ力：中／{nige_pct}）。"
        else:
            nige_judge = f"①の逃げはやや危うい（逃げ力：中低／{nige_pct}）。"

    # 最大脅威の補足
    if thr_w and thr_w != "-" and thr_t and thr_t != "-":
        threat_note = f"最大の脅威は{_wn(thr_w)}の{thr_t}。"
    else:
        threat_note = ""

    # 主役の決まり手を短く整形
    main_type_short = main_t.replace("系", "").replace("攻め", "").strip() or "攻め"

    # 対抗主役
    sub_note = f"対抗は{_wn(sub_w)}。" if sub_w and sub_w not in ("-", main_w, "") else ""

    # ── 逃げた場合の2・3着候補 ──────────────────────────────────────
    # 主役（main_w）は逃げ展開の2着候補から除外（まくり主役が逃げ展開に混入しない）
    a_top2    = [w for w, _ in scenario_a.get("top_2nd", [])[:4] if w != main_w][:3]
    a_top3    = [w for w, _ in scenario_a.get("top_3rd", [])[:4] if w != main_w][:3]
    a_2nd_str = "・".join(_wn(w) for w in a_top2) if a_top2 else "-"
    a_3rd_str = "・".join(_wn(w) for w in a_top3) if a_top3 else "-"

    # ── 主役が来た場合の2・3着候補 ──────────────────────────────────
    b_top2    = [w for w, _ in scenario_b.get("second_sorted", [])[:3]]
    b_top3    = [w for w, _ in scenario_b.get("third_sorted",  [])[:3]]
    b_2nd_str = "・".join(_wn(w) for w in b_top2) if b_top2 else "-"
    b_3rd_str = "・".join(_wn(w) for w in b_top3) if b_top3 else "-"

    # ── 崩れた場合の浮上候補 ────────────────────────────────────────
    ct     = scenario_b.get("collapse_top", [])
    ct_str = "・".join(_wn(w) for w, _ in ct[:2]) if ct else "-"

    # ── 展開連鎖ストーリー（event_logから自動生成）──────────────────
    event_log    = scenario_b.get("event_log", [])
    cascade_story = build_story_from_log(event_log, results) if event_log else ""

    # ── 見送り判定 ──────────────────────────────────────────────────
    skip        = rj.get("skip", False)
    skip_reason = rj.get("skip_reason", "")

    # ── 展開考察の組み立て ──────────────────────────────────────────
    lines: list[str] = []
    lines.append("【展開考察】")

    # 1行目：逃げ判定 ＋ 主役紹介
    if escape_rank == "低":
        line1 = f"{nige_judge}{threat_note}{_wn(main_w)}の{main_type_short}が主役。{sub_note}"
    elif escape_rank == "高":
        line1 = f"{nige_judge}{_wn(thr_w)}の警戒は必要だが、①中心の展開が濃厚。"
    else:
        line1 = f"{nige_judge}{threat_note}{_wn(main_w)}が対抗主役。{sub_note}"
    lines.append(line1.strip())

    # 箇条書き補足（3行固定）
    lines.append(f"・逃げるなら　　→ 2着：{a_2nd_str}　3着：{a_3rd_str}")
    lines.append(f"・{_wn(main_w)}{main_type_short}なら → 2着：{b_2nd_str}　3着：{b_3rd_str}")
    lines.append(f"・崩れれば　　　→ {ct_str}が浮上")

    # 展開連鎖ストーリー（event_logから自動生成された場合のみ表示）
    if cascade_story:
        lines.append(f"【展開連鎖】{cascade_story}")

    # 見送り推奨の場合（展開考察の末尾に1回だけ追記）
    if skip and skip_reason:
        lines.append(f"※ {skip_reason}")

    # ── 参考買い目：本線・押さえに分割 ─────────────────────────────
    def _fmt_buys(buy_list: list[dict]) -> str:
        if not buy_list:
            return "─"
        parts = []
        for c in buy_list:
            combo = c.get("combo", "")
            pct   = c.get("prob_pct", None)
            parts.append(f"{combo}（{pct:.1f}%）" if pct is not None else combo)
        per_line = 6
        rows = []
        for i in range(0, len(parts), per_line):
            rows.append("　".join(parts[i:i + per_line]))
        return "\n".join(rows)

    lines.append("")

    # 見送り推奨の場合は買い目を出力しない
    if skip:
        lines.append("【参考買い目】")
        lines.append("─（見送り推奨のため省略）")
    elif not candidates:
        lines.append("【参考買い目】")
        lines.append("─")
    else:
        sc_a       = [c for c in candidates if c.get("scenario") == "A"]
        sc_b_main  = [c for c in candidates if c.get("scenario") == "B_main"]
        sc_b_other = [c for c in candidates if c.get("scenario") in ("B_collapse", "B_sc")]

        if tenkai_pattern == "A":
            # 逃げ鉄板：逃げが本線、穴・荒れが押さえ
            honsen = sc_a
            osaae  = sc_b_other if sc_b_other else sc_b_main[:2]
            honsen_label = "本線（逃げ展開）"
            osaae_label  = "押さえ（穴・荒れ展開）"

        elif tenkai_pattern == "B":
            # 主役展開：主役が本線、逃げ残存・崩れが押さえ
            if sc_b_main:
                honsen = sc_b_main
            else:
                honsen = [c for c in candidates if c.get("tier") == "本線"]
            osaae  = sc_a + sc_b_other
            honsen_label = "本線（主役展開）"
            osaae_label  = "押さえ（逃げ残存・崩れ）"

        elif tenkai_pattern == "C":
            # 拮抗：逃げ・主役の上位が本線、崩れ・漁夫が押さえ
            honsen = sorted(sc_a[:3] + sc_b_main[:3],
                            key=lambda c: _safe(c.get("prob_pct", 0)), reverse=True)
            osaae  = sc_b_other
            honsen_label = "本線（逃げ・主役両建て）"
            osaae_label  = "押さえ（崩れ・漁夫展開）"

        else:  # D（荒れ）
            # 荒れ：主役＋浮上が本線、逃げ残存が押さえ
            honsen = sorted(sc_b_main + sc_b_other,
                            key=lambda c: _safe(c.get("prob_pct", 0)), reverse=True)
            osaae  = sc_a[:3]
            honsen_label = "本線（主役・浮上展開）"
            osaae_label  = "押さえ（逃げ残存）"

        lines.append(f"【本線】{honsen_label}")
        lines.append(_fmt_buys(honsen))
        if osaae:
            lines.append(f"【押さえ】{osaae_label}")
            lines.append(_fmt_buys(osaae))

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
