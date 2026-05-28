# -*- coding: utf-8 -*-
"""
honmei_scenario.py  v2
======================
「◎の勝ちパターン」起点の買い目構築モジュール

【v2 修正内容】
  Fix1: 印なし艇の買い目除外
        honmei_map が確定している場合、◎○▲△がついていない艇を
        1着軸・ヒモ候補から除外する。

  Fix2: 3択判定の根拠を強化
        ◎の決まり手パターン × 1号艇の被決まり手 × ST差 × tobi_score を
        組み合わせた多因子判定に変更。「◎が1号艇か否か」だけの判定を廃止。

  Fix3: ○▲△を必ずヒモに含める
        ヒモスコアによる累積打ち切り前に、印付き艇（○▲△）を優先レーンで
        確保してから残スロットを埋める方式に変更。

  Fix4: ヒモスコアに◎の決まり手との因果を追加
        「◎がどう勝つか」→「その展開でこの艇は残れるか」を
        _kata_position_mult で決まり手タイプ補正を接続する。

  Fix5: 両建て時の枠配分を意図化
        逃げ強度・飛び強度の比率で逃げ軸：飛び軸の点数を按分する。

  Fix6: 折り返し判定に物理的根拠を追加
        「この決まり手が決まったとき1着が逆転するか」を物理法則で評価し、
        非現実的な折り返しを除外する。

  Fix7: SCシナリオの1着制約
        漁夫候補を3着に補完するとき、1着は飛び役以外の内側艇に限定する。

【使い方】
    from honmei_scenario import integrate_with_suggest_3rentan

    # load_race.py の _suggest_3rentan 末尾で呼ぶ
    return integrate_with_suggest_3rentan(
        original_result = _base_result,
        results         = results,
        honmei_map      = honmei_map,
        combos          = combos,
        race_judgment   = race_judgment,
        jizen_eval      = jizen_eval,
    )
"""

from __future__ import annotations
from typing import Any


# ============================================================
# ユーティリティ
# ============================================================

def _safe(val: Any, default: float = 0.0) -> float:
    if val is None:
        return default
    try:
        v = str(val).replace("%", "").strip()
        if v in ("", "None", "nan", "-", "★"):
            return default
        return float(v)
    except (ValueError, TypeError):
        return default


# ============================================================
# 仕掛け試行確率モデル（v2新規: 3段階分解）
# ============================================================

def calc_attack_probability(
    attacker: dict,
    target_r: dict,
    all_results: list[dict],
) -> dict:
    """
    ある艇が1号艇（先行艇）に「仕掛けを試みる確率」を3段階で計算する。

    【設計思想】
    逃げが◎になる根本原因は「仕掛け発生確率」が計算されていないこと。
    確率計算は「仕掛けが成功した場合の3連単確率」しか見ていないため、
    「仕掛けが起きた前提」の確率が常に1号艇逃げ切りに勝てない。

    3段階モデル:
      P_total = P_attempt × P_success × P_survive

      P_attempt（仕掛け試行確率）:
        「この選手はこの展開でそもそも仕掛けを試みるか」
        = 攻め武器の強さ × STで仕掛けラインに届けるか × コース距離補正

      P_success（仕掛け成功確率）:
        「仕掛けを試みたとき実際に決まるか」
        = 自分の決まり手実績% × (1 - ターゲットの守り力)

      P_survive（仕掛け後の生存確率）:
        「自分が仕掛けたあと後続に潰されずに残るか」
        = 3連対率 × 外側艇の攻め武器の逆数

    Returns
    -------
    dict:
        attempt_prob  : 仕掛け試行確率（0〜1）
        success_prob  : 仕掛け成功確率（0〜1）
        survive_prob  : 生存確率（0〜1）
        total_prob    : P_attempt × P_success（着順確率の起点）
        primary_kata  : 主決まり手（"差し"/"まくり"/"まくり差し"）
        detail        : 各確率の計算根拠
    """
    w      = attacker["waku"]
    course = str(attacker.get("course", w))
    try:
        course_int = int(course)
    except (ValueError, TypeError):
        course_int = 3

    cm   = attacker.get("raw_cm", {})
    cm1  = target_r.get("raw_cm", {})

    # ── P_attempt: 仕掛け試行確率 ────────────────────────────────────────
    # 攻め武器: 差し% or まくり系%（コース別）
    nige_pct = _pct(cm, "逃げ%")
    sash_pct = _pct(cm, "差し%")
    maku_pct = _pct(cm, "まくり%")
    mz_pct   = _pct(cm, "まくり差し%")

    if course_int == 2:
        weapon_pct  = sash_pct
        primary_kata = "差し"
    elif course_int >= 3:
        weapon_pct  = maku_pct + mz_pct
        primary_kata = "まくり差し" if mz_pct > maku_pct else "まくり"
    else:
        weapon_pct  = nige_pct
        primary_kata = "逃げ"

    if weapon_pct <= 0:
        weapon_pct = 0.15   # 実績なしフォールバック

    # STで仕掛けラインに届けるか: STが1号艇より速いほど試行しやすい
    avg_st_self = attacker.get("avg_st")
    avg_st_1    = target_r.get("avg_st")
    COURSE_ADJ = {1: 0.0, 2: 0.03, 3: 0.06, 4: 0.10, 5: 0.15, 6: 0.21}
    eff_self = (avg_st_self or 0.18) + COURSE_ADJ.get(course_int, 0.10)
    eff_1    = (avg_st_1    or 0.18) + COURSE_ADJ.get(1, 0.0)
    # ST到達差が0以下（仕掛け艇が先着）→ 試行確率UP、大幅遅れ → DOWN
    st_gap       = eff_self - eff_1   # 正 = 1号艇が先着（仕掛けが届きにくい）
    st_reach     = max(0.3, min(1.2, 1.0 - st_gap * 5.0))

    # コース距離補正（外コースほど仕掛けが難しい）
    dist_penalty = {2: 1.0, 3: 0.90, 4: 0.80, 5: 0.70, 6: 0.60}.get(course_int, 0.80)

    attempt_prob = min(weapon_pct * st_reach * dist_penalty, 0.95)

    # ── P_success: 仕掛け成功確率 ────────────────────────────────────────
    # 1号艇の守り力: 逃げ%が高いほど守りが強い
    nige1 = _pct(cm1, "逃げ%")
    if nige1 <= 0:
        nige1 = 0.55   # 全国平均フォールバック

    # 被決まり手率（差され% or 捲られ%）- _pctを通してエイリアスを吸収
    if primary_kata == "差し":
        # cm1の「差され%」を読む。_pctはエイリアス対応なし→直接safe+変換
        raw_beaten = cm1.get("差され%") or cm1.get("決まり手_差し%") or 0.0
        beaten_rate = _safe(raw_beaten)
        if beaten_rate > 1.5:
            beaten_rate /= 100.0
    else:
        raw_beaten = cm1.get("捲られ%") or cm1.get("決まり手_まくり%") or 0.0
        beaten_rate = _safe(raw_beaten)
        if beaten_rate > 1.5:
            beaten_rate /= 100.0

    # 被決まり手率がゼロなら逃げ以外率でフォールバック
    if beaten_rate <= 0:
        beaten_rate = 1.0 - nige1

    # 成功確率 = 被決まり手率を基準に攻め武器で補正
    success_prob = min(beaten_rate * (0.5 + weapon_pct * 0.5), 0.90)

    # ── P_survive: 仕掛け後の生存確率 ────────────────────────────────────
    # 3連対率 × 後続艇の攻め武器逆数
    win3 = attacker.get("win3_rate") or 0.5

    # 後続艇の攻め武器（自コース+1の艇）
    outer_w = str(course_int + 1) if course_int < 6 else None
    outer_r = next((r for r in all_results if r["waku"] == outer_w), None) if outer_w else None
    if outer_r:
        outer_cm    = outer_r.get("raw_cm", {})
        outer_wpn   = _pct(outer_cm, "まくり%") + _pct(outer_cm, "まくり差し%")
        outer_wpn   = outer_wpn if outer_wpn > 0 else 0.20
        survive_adj = max(0.60, 1.0 - outer_wpn * 0.5)
    else:
        survive_adj = 0.85

    survive_prob = min(win3 * survive_adj, 0.95)

    return {
        "attempt_prob": round(attempt_prob, 4),
        "success_prob": round(success_prob, 4),
        "survive_prob": round(survive_prob, 4),
        "total_prob":   round(attempt_prob * success_prob, 4),
        "primary_kata": primary_kata,
        "detail": {
            "weapon_pct":    round(weapon_pct, 3),
            "st_reach":      round(st_reach, 3),
            "dist_penalty":  dist_penalty,
            "beaten_rate":   round(beaten_rate, 3),
            "survive_adj":   round(survive_adj, 3),
        },
    }


def _get_cm_val(cm: dict, key: str) -> Any:
    aliases = {
        "逃げ%":       ["逃げ%",       "決まり手_逃げ%"],
        "差し%":       ["差し%",       "決まり手_差し%"],
        "まくり%":     ["まくり%",     "決まり手_まくり%"],
        "まくり差し%": ["まくり差し%", "決まり手_まくり差し%"],
        "抜き%":       ["抜き%",       "決まり手_抜き%"],
    }
    for alias in aliases.get(key, [key]):
        v = cm.get(alias)
        if v is not None:
            return v
    return None


def _pct(cm: dict, key: str) -> float:
    """決まり手%を0〜1で返す。%表記(100超)も自動変換。"""
    v = _get_cm_val(cm, key)
    try:
        raw = float(v) if v is not None else 0.0
        return (raw / 100.0) if raw > 1.5 else raw
    except (ValueError, TypeError):
        return 0.0


# ============================================================
# Fix1: 印付き艇ユーティリティ
# ============================================================

def _marked_wakus(honmei_map: dict | None) -> set[str]:
    """◎○▲△がついている艇番のセットを返す"""
    if not honmei_map:
        return set()
    return {w for w, mark in honmei_map.items() if str(mark).strip()}


def _inv_map(honmei_map: dict | None) -> dict[str, str]:
    """{"◎": "1", "○": "3", ...} の逆引き辞書"""
    if not honmei_map:
        return {}
    return {str(v).strip(): k for k, v in honmei_map.items() if str(v).strip()}


# ============================================================
# Step 1: ◎艇の「勝ちパターン」を定義する
# ============================================================

def define_honmei_win_pattern(honmei_r: dict) -> dict:
    """
    ◎艇の決まり手パターンから「この選手がどう勝つか」を定義する。

    Returns
    -------
    dict:
        waku, course, course_int,
        primary_kata ("逃げ"/"差し"/"まくり"/"まくり差し"),
        primary_pct,
        secondary_kata, secondary_pct,
        win_scenario ("S1"/"S2"/"S3"/"SC"),
        win_narrative,
        pattern_confidence (0〜1)
    """
    waku       = honmei_r["waku"]
    course     = str(honmei_r.get("course", waku)).strip()
    course_int = int(course) if str(course).isdigit() else 3
    cm         = honmei_r.get("raw_cm", {})

    nige_pct = _pct(cm, "逃げ%")
    sash_pct = _pct(cm, "差し%")
    maku_pct = _pct(cm, "まくり%")
    mz_pct   = _pct(cm, "まくり差し%")
    nuki_pct = _pct(cm, "抜き%")

    if course_int == 1:
        candidates = [("逃げ", nige_pct)]
    elif course_int == 2:
        # ※ まくり差しは2コースからは物理的にコース取りが成立しないため除外
        candidates = [("差し", sash_pct), ("まくり", maku_pct)]
    else:
        candidates = [
            ("まくり",     maku_pct),
            ("まくり差し", mz_pct),
            ("差し",       sash_pct),
            ("抜き",       nuki_pct),
        ]

    data_missing       = honmei_r.get("data_missing", False)
    total_pct          = sum(p for _, p in candidates)
    pattern_confidence = min(total_pct, 1.0) if total_pct > 0 else 0.3
    if data_missing:
        pattern_confidence *= 0.6

    sorted_c       = sorted(candidates, key=lambda x: x[1], reverse=True)
    primary_kata   = sorted_c[0][0] if sorted_c else "不明"
    primary_pct    = sorted_c[0][1] if sorted_c else 0.0
    secondary_kata = sorted_c[1][0] if len(sorted_c) >= 2 and sorted_c[1][1] > 0.05 else None
    secondary_pct  = sorted_c[1][1] if secondary_kata else 0.0

    kata_to_scenario = {
        "逃げ": "S1", "差し": "S2",
        "まくり差し": "S3", "まくり": "S3", "抜き": "SC",
    }
    win_scenario = kata_to_scenario.get(primary_kata, "S3")

    if course_int == 1:
        narrative = f"{waku}号艇（1コース）が逃げ切る展開"
    elif primary_kata == "差し":
        narrative = f"{waku}号艇（{course}コース）が差し込む展開（差し{primary_pct*100:.0f}%）"
    else:
        narrative = (
            f"{waku}号艇（{course}コース）が{primary_kata}で出る展開"
            f"（{primary_kata}{primary_pct*100:.0f}%"
            + (f"/{secondary_kata}{secondary_pct*100:.0f}%" if secondary_kata else "")
            + "）"
        )

    return {
        "waku":               waku,
        "course":             course,
        "course_int":         course_int,
        "primary_kata":       primary_kata,
        "primary_pct":        round(primary_pct, 3),
        "secondary_kata":     secondary_kata,
        "secondary_pct":      round(secondary_pct, 3),
        "win_scenario":       win_scenario,
        "win_narrative":      narrative,
        "pattern_confidence": round(pattern_confidence, 3),
    }


# ============================================================
# Fix2: 3択判定の再設計（多因子）
# ============================================================

def judge_scenario_type(
    honmei_pattern: dict,
    results:        list[dict],
    race_judgment:  dict,
    honmei_map:     dict | None,
    s1_prob:        float,
) -> dict:
    """
    「逃げ軸流し」「飛び軸」「両建て」を対戦型モデルで判定する。

    【v2→v3 変更点】
    旧方式: 6因子を独立に加点 → 「逃げも強い＋飛びも強い」で必ず両建てに収束
            「仕掛け発生確率」が計算されていないため逃げがデフォルト優位

    新方式: 対戦型（◎ vs 1号艇の直接対決）
      Step1: ◎艇の「仕掛け試行確率」を3段階で計算（calc_attack_probability）
             → P_attempt × P_success = ◎が1号艇を実際に倒せる確率
      Step2: 1号艇の「逃げ切り確率」= s1_prob（既に計算済み）
      Step3: 対戦スコア = 飛び総合確率 vs 逃げ確率 を比較
             差が大きい方にシナリオを寄せる
             差が20pt未満なら両建て

    ◎が1号艇の場合のみ旧来の逃げ強度計算にフォールバック。

    Returns
    -------
    dict:
        scenario_type   : "逃げ軸流し" / "飛び軸" / "両建て"
        escape_strength : 逃げ強度スコア（0〜100）
        fly_strength    : 飛び強度スコア（0〜100）
        attack_prob     : ◎艇の仕掛け試行確率（0〜1）
        reasons         : 判定根拠リスト
    """
    honmei_waku  = honmei_pattern["waku"]
    primary_kata = honmei_pattern["primary_kata"]
    course_int   = honmei_pattern["course_int"]
    marked       = _marked_wakus(honmei_map)
    reasons      = []

    ryotate      = race_judgment.get("ryotate", {}) or {}
    tobi_score   = float(ryotate.get("tobi_score", 30))
    sq           = race_judgment.get("scenario_quality", {}) or {}
    quality_rank = sq.get("quality_rank", "B")

    res1 = next((r for r in results if r["waku"] == "1"), None)
    honmei_r = next((r for r in results if r["waku"] == honmei_waku), None)

    # ◎が1号艇の場合: 逃げモデルで計算
    if honmei_waku == "1" or course_int == 1:
        cm1 = honmei_r.get("raw_cm", {}) if honmei_r else {}
        nige1 = _pct(cm1, "逃げ%") if honmei_r else 0.55
        nige1 = nige1 if nige1 > 0 else 0.55

        # 逃げ強度 = s1_prob × 逃げ% × 会場補正
        escape_strength = min(100.0, s1_prob * 80.0 + nige1 * 30.0)
        fly_strength    = max(0.0, tobi_score * 0.5)
        reasons.append(f"◎=1号艇逃げ主体({nige1*100:.0f}%) s1={s1_prob*100:.0f}% → 逃げ強度{escape_strength:.0f}")

        boat1_marked = "1" in marked
        if escape_strength >= fly_strength + 20 and boat1_marked:
            scenario_type = "逃げ軸流し"
        elif fly_strength >= escape_strength + 20:
            scenario_type = "飛び軸"
        else:
            scenario_type = "両建て"

        reasons.insert(0, f"逃げ強度{escape_strength:.0f} / 飛び強度{fly_strength:.0f} → {scenario_type}")
        return {
            "scenario_type":   scenario_type,
            "escape_strength": round(escape_strength, 1),
            "fly_strength":    round(fly_strength, 1),
            "attack_prob":     0.0,
            "reasons":         reasons,
        }

    # ── ◎が外コースの場合: 対戦型モデル ──────────────────────────────────
    if honmei_r is None or res1 is None:
        # データ不足フォールバック
        return {
            "scenario_type": "両建て",
            "escape_strength": 50.0, "fly_strength": 50.0,
            "attack_prob": 0.0,
            "reasons": ["データ不足→両建て"],
        }

    # Step1: ◎艇の仕掛け試行確率（3段階）
    ap = calc_attack_probability(honmei_r, res1, results)
    attack_total = ap["total_prob"]   # P_attempt × P_success
    survive      = ap["survive_prob"]

    reasons.append(
        f"◎{honmei_waku}号{ap['primary_kata']}: "
        f"試行{ap['attempt_prob']*100:.0f}%×成功{ap['success_prob']*100:.0f}%"
        f"=仕掛け確率{attack_total*100:.0f}%"
    )
    reasons.append(
        f"生存確率{survive*100:.0f}% / "
        f"武器{ap['detail']['weapon_pct']*100:.0f}% "
        f"ST到達{ap['detail']['st_reach']:.2f}"
    )

    # Step2: 逃げ確率 vs 飛び仕掛け確率を0〜100スコアに変換
    # 逃げ強度: s1_prob を直接使用（すでにキャリブレーション済み）
    escape_strength = min(100.0, s1_prob * 100.0)

    # 飛び強度: 仕掛け確率 × 生存確率 を0〜100に変換
    # + tobi_score（定性）による補強（最大+15pt）
    fly_raw         = attack_total * survive
    fly_qual_bonus  = min(15.0, tobi_score * 0.25)
    # quality補正: D/Cは混戦なので飛び強度を抑制
    q_fly_adj = {"S": 5.0, "A": 2.0, "B": 0.0, "C": -5.0, "D": -10.0}.get(quality_rank, 0.0)
    fly_strength    = min(100.0, max(0.0, fly_raw * 100.0 + fly_qual_bonus + q_fly_adj))

    reasons.append(f"飛び強度={fly_raw*100:.0f}+定性{fly_qual_bonus:.0f}+quality{q_fly_adj:+.0f}={fly_strength:.0f}")

    # Step3: 対戦判定
    boat1_marked = "1" in marked
    diff = fly_strength - escape_strength

    if not boat1_marked and honmei_waku != "1":
        # 1号艇に印がなければ飛び軸固定（Fix1継承）
        scenario_type = "飛び軸"
        reasons.append("1号艇に印なし → 飛び軸固定")
    elif diff >= 20:
        scenario_type = "飛び軸"
    elif -diff >= 20:
        scenario_type = "逃げ軸流し"
        if not boat1_marked:
            scenario_type = "両建て"
            reasons.append("逃げ優位だが1号艇に印なし → 両建て")
    else:
        scenario_type = "両建て"

    reasons.insert(0, f"逃げ強度{escape_strength:.0f} / 飛び強度{fly_strength:.0f} → {scenario_type}")

    return {
        "scenario_type":   scenario_type,
        "escape_strength": round(escape_strength, 1),
        "fly_strength":    round(fly_strength, 1),
        "attack_prob":     round(attack_total, 4),
        "reasons":         reasons,
    }


# ============================================================
# Fix4: 決まり手×位置補正テーブル
# ============================================================

def _kata_position_mult(
    first_course_int: int,
    primary_kata:     str,
    target_waku_int:  int,
) -> tuple[float, str]:
    """
    ◎の決まり手 × ターゲット艇のコース位置から残存補正係数を返す。

    競艇物理法則:
      差し（◎2コース）:
        1号艇は内側に残りやすい（×1.35）
        ◎直外（3号艇）は競合で来にくい（×0.75）
        それ以外の内側は残存（×1.10）
        外側は来にくい（×0.90）

      まくり・まくり差し（◎3〜6コース）:
        内側艇は圧縮されて流れ込む（×1.05〜1.25）
        外側艇は被まくりで来にくい（×0.80〜0.90）

      逃げ（1コース）:
        circle_pct で判断するためここではニュートラル
    """
    if first_course_int == 1:
        return 1.0, "逃げ展開（circle_pctで判断）"

    diff  = first_course_int - target_waku_int  # 正 = 内側

    if primary_kata == "差し":
        if target_waku_int == 1:
            return 1.35, "差し展開: 1号艇内残存最大"
        elif diff == -1:
            return 0.75, "差し展開: 直外艇は競合で来にくい"
        elif diff > 0:
            return 1.10, "差し展開: 内側残存"
        else:
            return 0.90, "差し展開: 外側は来にくい"

    elif primary_kata in ("まくり", "まくり差し"):
        if diff > 0:  # 内側
            bonus = min(1.25, 1.05 + diff * 0.05)
            return round(bonus, 2), f"まくり展開: 内×{bonus:.2f}"
        elif diff < 0:  # 外側
            penalty = max(0.80, 0.95 - abs(diff) * 0.05)
            return round(penalty, 2), f"まくり展開: 外×{penalty:.2f}"
        else:
            return 1.0, "中立"

    return 1.0, "展開補正なし"


# ============================================================
# Step 2: ◎の展開が成立したときのヒモ候補スコアリング
# ============================================================

def derive_himo_candidates(
    honmei_pattern: dict,
    results:        list[dict],
    jizen_eval:     dict | None,
    marked:         set[str] | None = None,
) -> list[dict]:
    """
    ◎の展開が成立したとき2・3着に残りやすい艇をスコアリングして返す。

    スコア構成 v3（仕掛け試行確率連動版）:
      (1) 位置残存スコア    (35%) : Fix4の決まり手×位置補正
      (2) 仕掛け干渉スコア  (25%) : 「その艇が独自に仕掛けて生き残れるか」
                                   ※◎の仕掛けが成功した後も自分の試行で残れるか
      (3) 個人能力スコア    (25%) : 3連対率 × ST相対 × 機力相対
      (4) jizen評価スコア   (15%) : 相性×0.5 + 展開×0.3 + 自在性×0.2

    【v3 変更点】
      ・(2)に仕掛け干渉スコアを追加（旧は(1)のみで「あとは確率まかせ」だった）
      ・仕掛け干渉 = P_attempt(自艇) × P_survive(自艇) → 自艇が2着で残れる積極性
      ・Fix3継承: is_marked フラグ付与
    """
    honmei_waku  = honmei_pattern["waku"]
    primary_kata = honmei_pattern["primary_kata"]
    course_int   = honmei_pattern["course_int"]

    res1 = next((r for r in results if r["waku"] == "1"), None)

    sym_score = {"◎": 1.0, "○": 0.75, "△": 0.40, "": 0.25}

    _ja, _jt, _jz = {}, {}, {}
    if jizen_eval is not None:
        for idx in range(6):
            w = str(idx + 1)
            _ja[w] = (jizen_eval.get("aisho")    or [""] * 6)[idx]
            _jt[w] = (jizen_eval.get("tenkai")   or [""] * 6)[idx]
            _jz[w] = (jizen_eval.get("jizaisei") or [""] * 6)[idx]

    # ST・機力の相対スコア用ベースライン
    all_sts = [r.get("avg_st") for r in results if r.get("avg_st") is not None]
    st_min  = min(all_sts) if all_sts else 0.15
    st_max  = max(all_sts) if all_sts else 0.20
    valid_m = []
    for r in results:
        try:
            v = float(r.get("motor2") or 0)
            if v > 0:
                valid_m.append(v)
        except (ValueError, TypeError):
            pass
    m_min = min(valid_m) if valid_m else 30.0
    m_max = max(valid_m) if valid_m else 60.0

    himo_list = []
    for r in results:
        w = r["waku"]
        if w == honmei_waku:
            continue

        w_int   = int(w) if str(w).isdigit() else 3
        reasons = []

        # ── (1) 位置残存スコア（Fix4）────────────────────────────────────────
        if primary_kata == "逃げ" or course_int == 1:
            circ      = r.get("circle_pct") or 0.0
            pos_score = circ / 100.0
            reasons.append(f"イン逃げ2着優位度{circ:.1f}%")
        else:
            win3_base = r.get("win3_rate") or 0.5
            mult, rtxt = _kata_position_mult(course_int, primary_kata, w_int)
            pos_score  = win3_base * mult
            reasons.append(rtxt)

        # ── (2) 仕掛け干渉スコア（v3新規）─────────────────────────────────
        # この艇自身が「仕掛けを試みて生き残れるか」を計算する。
        # 高い → 2着で積極的に絡んでくる可能性が高い（買い目に入れる価値大）
        # 低い → 受け身で後ろに残るか、つぶされて消える可能性が高い
        target_for_ap = res1 if res1 else (next((x for x in results if x["waku"] != w), None))
        if target_for_ap:
            ap = calc_attack_probability(r, target_for_ap, results)
            # 試行確率 × 生存確率 = 「この艇が2着で踏ん張れる積極性スコア」
            active_score = ap["attempt_prob"] * ap["survive_prob"]
        else:
            active_score = 0.3   # データなしフォールバック

        reasons.append(f"積極性{active_score*100:.0f}%")

        # ── (3) 個人能力スコア ─────────────────────────────────────────────
        win3     = r.get("win3_rate") or 0.5
        st       = r.get("avg_st")
        st_score = (
            (1.0 - (st - st_min) / max(st_max - st_min, 0.001))
            if st is not None else 0.5
        )
        try:
            mv = float(r.get("motor2") or 0)
        except (ValueError, TypeError):
            mv = None
        motor_score = (
            (mv - m_min) / max(m_max - m_min, 0.001)
            if mv and valid_m else 0.5
        )
        personal_score = win3 * 0.50 + st_score * 0.30 + motor_score * 0.20

        # ── (4) jizen評価スコア ─────────────────────────────────────────────
        aisho_s  = sym_score.get(_ja.get(w, ""), 0.25)
        tenkai_s = sym_score.get(_jt.get(w, ""), 0.25)
        jizai_s  = sym_score.get(_jz.get(w, ""), 0.25)
        jizen_score = aisho_s * 0.5 + tenkai_s * 0.3 + jizai_s * 0.2
        if _ja.get(w):
            reasons.append(f"相性{_ja[w]}")

        # ── 合成 ─────────────────────────────────────────────────────────
        total = (pos_score    * 0.35
               + active_score * 0.25
               + personal_score * 0.25
               + jizen_score  * 0.15)

        himo_list.append({
            "waku":           w,
            "name":           r.get("name", w),
            "residual_score": round(total, 4),
            "pos_score":      round(pos_score, 4),
            "active_score":   round(active_score, 4),
            "personal_score": round(personal_score, 4),
            "jizen_score":    round(jizen_score, 4),
            "reasons":        reasons,
            "honmei_mark":    r.get("honmei", " ").strip(),
            "is_marked":      (marked is not None and w in marked),
        })

    himo_list.sort(key=lambda x: x["residual_score"], reverse=True)
    return himo_list
    honmei_waku  = honmei_pattern["waku"]
    primary_kata = honmei_pattern["primary_kata"]
    course_int   = honmei_pattern["course_int"]

    sym_score = {"◎": 1.0, "○": 0.75, "△": 0.40, "": 0.25}

    _ja, _jt, _jz = {}, {}, {}
    if jizen_eval is not None:
        for idx in range(6):
            w = str(idx + 1)
            _ja[w] = (jizen_eval.get("aisho")    or [""] * 6)[idx]
            _jt[w] = (jizen_eval.get("tenkai")   or [""] * 6)[idx]
            _jz[w] = (jizen_eval.get("jizaisei") or [""] * 6)[idx]

    # ST・機力の相対スコア用ベースライン
    all_sts = [r.get("avg_st") for r in results if r.get("avg_st") is not None]
    st_min  = min(all_sts) if all_sts else 0.15
    st_max  = max(all_sts) if all_sts else 0.20
    valid_m = []
    for r in results:
        try:
            v = float(r.get("motor2") or 0)
            if v > 0:
                valid_m.append(v)
        except (ValueError, TypeError):
            pass
    m_min = min(valid_m) if valid_m else 30.0
    m_max = max(valid_m) if valid_m else 60.0

    himo_list = []
    for r in results:
        w = r["waku"]
        if w == honmei_waku:
            continue

        w_int   = int(w) if str(w).isdigit() else 3
        reasons = []

        # ── (1) 位置残存スコア（Fix4）────────────────────────────────────────
        if primary_kata == "逃げ" or course_int == 1:
            circ      = r.get("circle_pct") or 0.0
            pos_score = circ / 100.0
            reasons.append(f"イン逃げ2着優位度{circ:.1f}%")
        else:
            win3_base = r.get("win3_rate") or 0.5
            mult, rtxt = _kata_position_mult(course_int, primary_kata, w_int)
            pos_score  = win3_base * mult
            reasons.append(rtxt)

        # ── (2) 個人能力スコア ─────────────────────────────────────────────
        win3     = r.get("win3_rate") or 0.5
        st       = r.get("avg_st")
        st_score = (
            (1.0 - (st - st_min) / max(st_max - st_min, 0.001))
            if st is not None else 0.5
        )
        try:
            mv = float(r.get("motor2") or 0)
        except (ValueError, TypeError):
            mv = None
        motor_score = (
            (mv - m_min) / max(m_max - m_min, 0.001)
            if mv and valid_m else 0.5
        )
        personal_score = win3 * 0.50 + st_score * 0.30 + motor_score * 0.20

        # ── (3) jizen評価スコア ─────────────────────────────────────────────
        aisho_s  = sym_score.get(_ja.get(w, ""), 0.25)
        tenkai_s = sym_score.get(_jt.get(w, ""), 0.25)
        jizai_s  = sym_score.get(_jz.get(w, ""), 0.25)
        jizen_score = aisho_s * 0.5 + tenkai_s * 0.3 + jizai_s * 0.2
        if _ja.get(w):
            reasons.append(f"相性{_ja[w]}")

        # ── 合成 ─────────────────────────────────────────────────────────
        total = pos_score * 0.40 + personal_score * 0.35 + jizen_score * 0.25

        himo_list.append({
            "waku":           w,
            "name":           r.get("name", w),
            "residual_score": round(total, 4),
            "pos_score":      round(pos_score, 4),
            "personal_score": round(personal_score, 4),
            "jizen_score":    round(jizen_score, 4),
            "reasons":        reasons,
            "honmei_mark":    r.get("honmei", " ").strip(),
            "is_marked":      (marked is not None and w in marked),
        })

    himo_list.sort(key=lambda x: x["residual_score"], reverse=True)
    return himo_list


# ============================================================
# Fix3: ○▲△を必ずヒモに含める買い目構築
# ============================================================

def _build_axis_buys(
    axis_waku:      str,
    himo_ranking:   list[dict],
    combo_lookup:   dict,
    n_slots:        int,
    honmei_pattern: dict,
    results:        list[dict],
    marked:         set[str],
    inv:            dict[str, str],
) -> list[dict]:
    """
    1着軸を固定し、Pass1(印付き優先確保)→Pass2(スコア順補充)で買い目を生成する。

    Pass1: ○▲△が2着か3着に入る組み合わせを先に確保
    Pass2: 残スロットを total_score 順で補充
    """
    wakus  = [r["waku"] for r in results]
    if len([w for w in wakus if w != axis_waku]) < 2:
        return []

    hs_map = {h["waku"]: h["residual_score"] for h in himo_ranking}
    # 印ボーナス（2着に入ったとき）
    mb_map = {
        inv.get("○"): 0.15,
        inv.get("▲"): 0.10,
        inv.get("△"): 0.06,
    }
    mb_map = {k: v for k, v in mb_map.items() if k}

    def _make(second, third):
        key  = f"{axis_waku}-{second}-{third}"
        data = combo_lookup.get(key)
        if data is None or data.get("prob", 0) < 1e-6:
            return None
        prob  = data["prob"]
        s2    = hs_map.get(second, 0.05)
        s3    = hs_map.get(third,  0.05)
        hs    = s2 * 0.6 + s3 * 0.4
        mb    = mb_map.get(second, 0.0) + mb_map.get(third, 0.0) * 0.5
        score = hs * 0.65 + prob * 0.25 + mb * 0.10
        h2    = next((h for h in himo_ranking if h["waku"] == second), {})
        h3    = next((h for h in himo_ranking if h["waku"] == third),  {})
        return {
            "combo":       key,
            "first":       axis_waku,
            "second":      second,
            "third":       third,
            "prob":        round(prob, 5),
            "himo_score":  round(hs, 4),
            "total_score": round(score, 4),
            "reason":      (
                f"◎{axis_waku}号{honmei_pattern['primary_kata']}/"
                f"2着{second}号{h2.get('honmei_mark','')}(残存{s2:.3f})/"
                f"3着{third}号{h3.get('honmei_mark','')}(残存{s3:.3f})"
            ),
            "is_priority": (second in mb_map or third in mb_map),
        }

    seen    = set()
    entries = []

    # Pass1: 印付き艇が含まれる組み合わせを先確保
    priority_w = [w for w in (inv.get("○"), inv.get("▲"), inv.get("△"))
                  if w and w != axis_waku]
    himo_ord   = priority_w[:]
    for h in himo_ranking:
        if h["waku"] not in himo_ord:
            himo_ord.append(h["waku"])

    for pw in priority_w:
        for ow in himo_ord:
            if ow == pw:
                continue
            for s, t in ((pw, ow), (ow, pw)):
                e = _make(s, t)
                if e and e["combo"] not in seen:
                    seen.add(e["combo"])
                    entries.append(e)

    # Pass2: 残スロットをスコア順で補充
    all_cands = []
    for s in himo_ord:
        for t in himo_ord:
            if s == t:
                continue
            e = _make(s, t)
            if e and e["combo"] not in seen:
                all_cands.append(e)
    all_cands.sort(key=lambda x: x["total_score"], reverse=True)
    for e in all_cands:
        if e["combo"] not in seen:
            seen.add(e["combo"])
            entries.append(e)

    entries.sort(key=lambda x: x["total_score"], reverse=True)
    return entries[:n_slots]


# ============================================================
# Fix6: 折り返し判定（物理的根拠追加）
# ============================================================

def needs_orkaeshi(
    base_key:       str,
    rev_key:        str,
    combo_lookup:   dict,
    honmei_pattern: dict,
    s1_prob:        float,
) -> bool:
    """
    1着折り返しが必要かを物理的根拠で判定する。

    追加制約:
      差し1着が決まったとき「差した艇より内側の艇」が折り返し1着になるのは
      物理的にほぼ起きない。
      まくり1着でも同様（まくり艇が前に出た後、内側艇が再逆転する展開は稀）。
    """
    if rev_key not in combo_lookup:
        return False
    base = combo_lookup.get(base_key)
    rev  = combo_lookup.get(rev_key)
    if not base or not rev:
        return False

    primary_kata = honmei_pattern["primary_kata"]
    first_ci     = honmei_pattern["course_int"]
    try:
        rev_fi = int(rev["first"])
    except (ValueError, TypeError):
        rev_fi = 3

    # Fix6: 物理制約
    if primary_kata in ("差し", "まくり", "まくり差し"):
        if rev_fi < first_ci:
            return False  # 内側艇が折り返し1着 → 非現実的

    # 逃げ確率が圧倒的 → 折り返し不要
    if s1_prob >= 0.75:
        return False

    # 確率比（3倍以上なら不要）
    if base["prob"] > 0 and base["prob"] / max(rev["prob"], 1e-9) >= 3.0:
        return False

    return True


# ============================================================
# Fix7: SCシナリオ補完（1着制約）
# ============================================================

def build_sc_bets(
    combos:          list[dict],
    collapse_bene:   list,
    fly_role_waku:   str | None,
    existing_combos: set[str],
    sc_slots:        int,
) -> list[dict]:
    """
    SCシナリオ（潰れ展開）の漁夫受益買い目を生成する。

    Fix7: 1着は「飛び役より内側の艇」に限定。
    飛び役が自滅 → 飛び役より内側の艇が先頭になるのが物理的に自然。
    """
    if not collapse_bene or sc_slots <= 0:
        return []

    try:
        fly_int = int(fly_role_waku) if fly_role_waku else 6
    except (ValueError, TypeError):
        fly_int = 6

    # 飛び役より内側（1〜fly_int-1）が1着候補
    inner_first = {str(i) for i in range(1, fly_int)}
    if not inner_first:
        inner_first = {"1", "2", "3"}  # フォールバック

    top_bene_w = collapse_bene[0][0]

    sc_cands = sorted(
        [c for c in combos
         if c.get("third") == top_bene_w
         and c.get("first") in inner_first
         and c["combo"] not in existing_combos],
        key=lambda x: x["prob"],
        reverse=True,
    )[:sc_slots]

    result = []
    for c in sc_cands:
        c2 = dict(c)
        c2["_sc_bet"] = True
        result.append(c2)
    return result


# ============================================================
# メイン: build_honmei_driven_buys（全Fix統合）
# ============================================================

def build_honmei_driven_buys(
    results:       list[dict],
    honmei_map:    dict,
    combos:        list[dict],
    race_judgment: dict,
    jizen_eval:    dict | None = None,
    max_bets:      int = 12,
) -> dict:
    """
    ◎の勝ちパターン起点で3連単買い目を構築する（全Fix統合版）。
    """
    if not results or not honmei_map:
        return _empty_result("印データなし")

    inv    = _inv_map(honmei_map)
    marked = _marked_wakus(honmei_map)

    honmei_waku  = inv.get("◎")
    taiko_waku   = inv.get("○")

    if not honmei_waku:
        return _empty_result("◎なし")

    honmei_r = next((r for r in results if r["waku"] == honmei_waku), None)
    if not honmei_r:
        return _empty_result(f"◎艇（{honmei_waku}号艇）データなし")

    combo_lookup = {c["combo"]: c for c in combos}

    sq           = race_judgment.get("scenario_quality", {}) or {}
    quality_rank = sq.get("quality_rank", "B")

    # s1_prob を first_prob_map から算出
    first_prob_map = {}
    for c in combos:
        w = c["first"]
        first_prob_map[w] = first_prob_map.get(w, 0) + c["prob"]
    s1_prob = first_prob_map.get("1", 0.0)

    # Step1: ◎の勝ちパターン
    honmei_pattern = define_honmei_win_pattern(honmei_r)

    # Fix2: 3択判定（多因子）
    sj = judge_scenario_type(
        honmei_pattern = honmei_pattern,
        results        = results,
        race_judgment  = race_judgment,
        honmei_map     = honmei_map,
        s1_prob        = s1_prob,
    )
    scenario_type = sj["scenario_type"]
    is_ryotate    = (scenario_type == "両建て")

    # ◎軸ヒモスコアリング（Fix3/Fix4）
    himo_ranking = derive_himo_candidates(honmei_pattern, results, jizen_eval, marked)

    # 両建て時の○軸
    taiko_pattern = None
    taiko_himo    = []
    if is_ryotate and taiko_waku and taiko_waku in marked:
        taiko_r = next((r for r in results if r["waku"] == taiko_waku), None)
        if taiko_r:
            taiko_pattern = define_honmei_win_pattern(taiko_r)
            taiko_himo    = derive_himo_candidates(taiko_pattern, results, jizen_eval, marked)

    # Fix5: 両建て枠配分（逃げ/飛び強度比で按分）
    QUALITY_SLOTS = {"S": 6, "A": 8, "B": 10, "C": 10, "D": 8}
    base_slots    = min(QUALITY_SLOTS.get(quality_rank, 8), max_bets - 2)

    if is_ryotate:
        es = sj["escape_strength"]
        fs = sj["fly_strength"]
        total_s      = max(es + fs, 1.0)
        honmei_slots = max(2, round(base_slots * es / total_s))
        taiko_slots  = max(2, base_slots - honmei_slots)
    else:
        honmei_slots = base_slots
        taiko_slots  = 0

    # 買い目生成（Fix3）
    honmei_buys = _build_axis_buys(
        axis_waku=honmei_waku, himo_ranking=himo_ranking,
        combo_lookup=combo_lookup, n_slots=honmei_slots,
        honmei_pattern=honmei_pattern, results=results,
        marked=marked, inv=inv,
    )
    taiko_buys = []
    if is_ryotate and taiko_pattern and taiko_himo and taiko_waku:
        taiko_buys = _build_axis_buys(
            axis_waku=taiko_waku, himo_ranking=taiko_himo,
            combo_lookup=combo_lookup, n_slots=taiko_slots,
            honmei_pattern=taiko_pattern, results=results,
            marked=marked, inv=inv,
        )

    seen     = set()
    all_buys = []
    for b in honmei_buys + taiko_buys:
        if b["combo"] not in seen:
            seen.add(b["combo"])
            all_buys.append(b)

    # Fix6: 折り返し付与（物理制約あり）
    for b in list(all_buys):
        rev_key = f"{b['second']}-{b['first']}-{b['third']}"
        if rev_key not in seen and needs_orkaeshi(
            b["combo"], rev_key, combo_lookup, honmei_pattern, s1_prob
        ):
            rev = dict(combo_lookup[rev_key])
            rev["_orkaeshi"] = True
            all_buys.append(rev)
            seen.add(rev_key)

    # Fix7: SC補完（1着制約あり）
    conflict_map  = race_judgment.get("conflict_map", {}) or {}
    collapse_bene = conflict_map.get("collapse_beneficiary", [])
    mc_strength   = (conflict_map.get("main_conflict") or {}).get("strength", 0) or 0
    if mc_strength >= 40 and collapse_bene:
        fly_sorted = sorted(
            [(w, p) for w, p in first_prob_map.items() if w != "1"],
            key=lambda x: x[1], reverse=True,
        )
        fly_role  = fly_sorted[0][0] if fly_sorted else None
        sc_adds   = build_sc_bets(combos, collapse_bene, fly_role, seen, sc_slots=2)
        all_buys.extend(sc_adds)
        for b in sc_adds:
            seen.add(b["combo"])

    # 最終打ち切り
    all_buys.sort(key=lambda x: x["prob"], reverse=True)
    all_buys = all_buys[:max_bets]

    buy_list    = [b["combo"] for b in all_buys]
    point_count = len(buy_list)
    total_prob  = sum(b["prob"] for b in all_buys)
    theory_syn_odds = round(0.75 / total_prob, 2) if total_prob > 0 else None

    # 信頼度
    missing_count = sum(1 for r in results if r.get("data_missing"))
    confidence    = round(
        honmei_pattern["pattern_confidence"] * max(0.5, 1.0 - missing_count * 0.1),
        3,
    )

    # ── 考察テキスト生成（引き継ぎ書 第10章フォーマット）──────────────────
    himo_top3 = [h["waku"] for h in himo_ranking[:3]]

    # Step2: 本命
    _honmei_kata = honmei_pattern["primary_kata"]
    _honmei_pct  = honmei_pattern["primary_pct"] * 100
    _honmei_conf = confidence * 100

    # Step3: 決まり手
    _sec_kata = honmei_pattern.get("secondary_kata")
    _sec_pct  = honmei_pattern.get("secondary_pct", 0) * 100
    if _sec_kata and _sec_pct >= 5:
        _kata_line = (
            f"決まり手: {_honmei_kata}({_honmei_pct:.0f}%) /"
            f" {_sec_kata}({_sec_pct:.0f}%)"
        )
    else:
        _kata_line = f"決まり手: {_honmei_kata}({_honmei_pct:.0f}%)"

    # Step4: ヒモ（上位3艇）と根拠
    _himo_reasons = []
    for _h in himo_ranking[:3]:
        _hw = _h["waku"]
        _hs = _h.get("score", 0) * 100
        _himo_reasons.append(f"{_hw}号({_hs:.0f}pt)")
    _himo_line = "2・3着候補: " + " / ".join(_himo_reasons) if _himo_reasons else "2・3着候補: -"

    # 両建て補足
    _ryotate_note = ""
    if is_ryotate and taiko_pattern:
        _ryotate_note = (
            f"\n対抗軸: {taiko_waku}号艇"
            f"（{taiko_pattern['primary_kata']}{taiko_pattern['primary_pct']*100:.0f}%）"
        )

    narrative = honmei_pattern["win_narrative"]
    if is_ryotate and taiko_pattern:
        narrative += f" ／ {taiko_pattern['win_narrative']}（両建て）"

    comment = (
        f"【考察】\n"
        f"本命: {honmei_waku}号艇（{_honmei_kata}主体 / 信頼度{_honmei_conf:.0f}%）\n"
        f"{_kata_line}\n"
        f"{_himo_line}\n"
        f"展開: {narrative}{_ryotate_note}\n"
        f"\n【買い目】\n"
        f"シナリオ: {scenario_type}\n"
        f"{point_count}点 / 理論合成{theory_syn_odds}倍"
    )

    return {
        "buy_list":           buy_list,
        "point_count":        point_count,
        "honmei_patterns":    {"honmei": honmei_pattern, "taiko": taiko_pattern},
        "himo_ranking":       himo_ranking,
        "buy_details":        all_buys,
        "scenario_type":      scenario_type,
        "scenario_narrative": narrative,
        "scenario_judgment":  sj,
        "theory_syn_odds":    theory_syn_odds,
        "confidence":         confidence,
        "comment":            comment,
        "is_ryotate":         is_ryotate,
        "honmei_waku":        honmei_waku,
        "taiko_waku":         taiko_waku,
    }


# ============================================================
# load_race.py への統合パッチ
# ============================================================

def integrate_with_suggest_3rentan(
    original_result: dict,
    results:         list[dict],
    honmei_map:      dict | None,
    combos:          list[dict],
    race_judgment:   dict,
    jizen_eval:      dict | None = None,
) -> dict:
    """
    既存 _suggest_3rentan の戻り値に honmei_scenario v2 の結果を統合する。

    - honmei_map が確定（2回目呼び出し）のときのみ新ロジックを適用
    - 既存の戻り値キーとの完全互換を維持
    - 新キー "honmei_scenario" に詳細を格納
    """
    if not honmei_map:
        original_result["honmei_scenario"] = None
        return original_result

    hs = build_honmei_driven_buys(
        results=results, honmei_map=honmei_map,
        combos=combos, race_judgment=race_judgment,
        jizen_eval=jizen_eval, max_bets=12,
    )

    merged = dict(original_result)
    merged["buy_list"]         = hs["buy_list"]
    merged["point_count"]      = hs["point_count"]
    merged["scenario_type"]    = hs["scenario_type"]
    merged["scenario_verdict"] = hs["scenario_type"]
    merged["theory_syn_odds"]  = hs["theory_syn_odds"]
    merged["comment"]          = hs["comment"]
    merged["honmei_scenario"]  = hs

    merged["candidates"] = [
        {
            "combo":          b["combo"],
            "prob":           b["prob"],
            "prob_pct":       round(b["prob"] * 100, 2),
            "himo_score":     b.get("himo_score", 0),
            "scenario":       hs["scenario_type"],
            "reason":         b.get("reason", ""),
            "is_orkaeshi":    b.get("_orkaeshi", False),
            "is_orkaeshi_23": False,
            "is_sc_bet":      b.get("_sc_bet", False),
        }
        for b in hs["buy_details"]
    ]
    return merged


# ============================================================
# 空結果ヘルパー
# ============================================================

def _empty_result(reason: str = "") -> dict:
    return {
        "buy_list": [], "point_count": 0,
        "honmei_patterns": {}, "himo_ranking": [], "buy_details": [],
        "scenario_type": "-", "scenario_narrative": reason,
        "scenario_judgment": {}, "theory_syn_odds": None,
        "confidence": 0.0, "comment": f"買い目構築不能: {reason}",
        "is_ryotate": False, "honmei_waku": None, "taiko_waku": None,
    }
