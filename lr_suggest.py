# -*- coding: utf-8 -*-
"""
lr_suggest.py  ─  買い目提案 / 本命判定 / ヒモ荒れ判定
分割元: load_race.py
"""
import re, sys
import pandas as pd
from lr_utils import safe_float
try:
    from evaluate_jizen import calculate_diversity_rate
except ImportError:
    def calculate_diversity_rate(*args, **kwargs):
        return 0.0

def format_buy_list(buy_list):
    """
    買い目リストを圧縮表示に変換する。

    圧縮ルール（優先度順に適用）:
      (1) 折り返し（1着・2着の入替）       1-2-3 と 2-1-3 → 1=2-3
      (2) 3着まとめ（1着・2着が同じ）       1-2-3 と 1-2-4 → 1-2-3,4
      (3) 2着まとめ（1着・3着が同じ）       1-2-3 と 1-3-3 → 不成立（3連単は重複不可）
      (4) 1着まとめ（2着・3着が同じ）       1-2-3 と 2-2-3 → 不成立（同上）
      → 実質的に (1) と (2) のみ有効

    返り値:
      list[str]  圧縮後の表示文字列リスト
                 例: ["1=2-3,4", "3-1-2", "3-2-1"]

    【表記ルール】
      - 折り返しペア: "A=B-C"  （A-B-C と B-A-C をまとめる）
      - 3着まとめ   : "A-B-C,D,E" （A-B-C / A-B-D / A-B-E をまとめる）
      - 複合       : 折り返し後に3着まとめが可能なら更にまとめる
      - 未圧縮     : "A-B-C"  （そのまま）
    """
    if not buy_list:
        return []

    # ── Step1: パース＋完全重複除去（順序保持） ───────────────────────────
    parsed     = []        # [(f, s, t), ...]
    seen_exact = set()     # "f-s-t" 完全一致の重複除去

    for combo in buy_list:
        parts = combo.split("-")
        if len(parts) != 3:
            continue
        if combo in seen_exact:
            continue
        seen_exact.add(combo)
        parsed.append((parts[0], parts[1], parts[2]))

    # ── Step2: 折り返しペアを検出してグループ化 ───────────────────────────
    # A-B-C と B-A-C（3着が同じ）を orkaeshi グループにまとめる
    used   = set()
    groups = []   # (type, first_a, first_b_or_None, second_or_None, third)

    for i, (f1, s1, t1) in enumerate(parsed):
        if i in used:
            continue
        matched_j = None
        for j, (f2, s2, t2) in enumerate(parsed):
            if j <= i or j in used:
                continue
            if f2 == s1 and s2 == f1 and t2 == t1:
                matched_j = j
                break

        if matched_j is not None:
            a = f1 if int(f1) < int(s1) else s1
            b = s1 if int(f1) < int(s1) else f1
            groups.append(("orkaeshi", a, b, None, t1))
            used.add(i)
            used.add(matched_j)
        else:
            groups.append(("normal", f1, None, s1, t1))
            used.add(i)

    # ── Step3: 重複グループを除去 ─────────────────────────────────────────
    # 「単独で残った normal combo」がすでに orkaeshi に吸収されていないか確認
    orkaeshi_keys = set()
    deduped = []
    for g in groups:
        typ, fa, fb, sec, third = g
        if typ == "orkaeshi":
            key = (fa, fb, third)
            if key not in orkaeshi_keys:
                orkaeshi_keys.add(key)
                deduped.append(g)
        else:
            # この normal combo の折り返し相手が orkaeshi に既にいるなら除外
            a = fa if int(fa) < int(sec) else sec
            b = sec if int(fa) < int(sec) else fa
            if (a, b, third) not in orkaeshi_keys:
                deduped.append(g)

    # ── Step4: 3着まとめ ──────────────────────────────────────────────────
    merged     = []
    merge_used = set()
    for i, g in enumerate(deduped):
        if i in merge_used:
            continue
        typ, fa, fb, sec, third = g
        group_key = (typ, fa, fb, sec)
        thirds = [third]
        for j, g2 in enumerate(deduped):
            if j <= i or j in merge_used:
                continue
            if (g2[0], g2[1], g2[2], g2[3]) == group_key:
                if g2[4] not in thirds:
                    thirds.append(g2[4])
                merge_used.add(j)
        merged.append((typ, fa, fb, sec, sorted(thirds, key=int)))
        merge_used.add(i)

    # ── Step5: 表示文字列を生成 ───────────────────────────────────────────
    result = []
    for typ, fa, fb, sec, thirds in merged:
        thirds_str = ",".join(thirds)
        if typ == "orkaeshi":
            result.append(f"{fa}={fb}-{thirds_str}")
        else:
            result.append(f"{fa}-{sec}-{thirds_str}")
    return result


def _suggest_3rentan(results, race_judgment, jizen_eval=None, honmei_map=None, tenkai_venue=None, tenkai_national=None, venue=None, venue_stats=None, st_kimete_master=None):
    """
    3連単買い目提案 v5 ── 印ベース軸決定＋内側残存補正ヒモ選択

    【設計思想】
      実オッズ・参加可否は人間が最終判断する前提。
      このロジックは「どの展開が来そうか」「その展開で何を買うべきか」を
      展示前の素材として提供することに専念する。

    【シナリオ判定と買い目形式】
      S1確率 >= 60%           → 逃げ軸流し（1着=1号艇固定）
      S1確率 40〜60%（拮抗）  → 両建てフォーメーション（逃げ軸＋飛び軸）
      S1確率 < 40%（飛び有力）→ 飛び軸フォーメーション

    【買い目の構成原則】
      ・全120通りの推定確率をシナリオ別に分類
      ・各シナリオの確率上位から累積80%を目安に買い目を選出
      ・折り返し買い（1-A-B と A-1-B）を自動的に対で追加
      ・カットオフなし・点数上限なし（確率で自動決定）

    【出力】
      scenario_type    : "逃げ軸流し" / "両建て" / "飛び軸"
      buy_list         : 推奨買い目（combo文字列リスト）
      point_count      : 点数
      theory_syn_odds  : 理論合成オッズ（= 0.75 / Σprob）
      required_syn_odds: 必要合成オッズ（= 点数 × 1.10）
      margin_ratio     : theory_syn_odds / required_syn_odds
      margin_verdict   : "余裕あり" / "要確認" / "見送り有力"
      candidates       : 買い目ごとの確率・シナリオ種別リスト
    """
    ryotate         = race_judgment.get("ryotate", {})
    ryotate_verdict = ryotate.get("verdict", "逃げ狙い")

    if not results:
        return {
            "axis1": "-", "axis2": "-", "buy_list": [], "point_count": 0,
            "comment": "データ不足", "combos": [], "candidates": [],
            "scenario_type": "-", "scenario_verdict": "-",
            "theory_syn_odds": None, "required_syn_odds": None,
            "margin_ratio": None, "margin_verdict": "-",
            "escape_score": 50, "tobi_score": 30, "fly_axes": [],
            "candidates_s1": [], "candidates_s2": [],
            "axis_candidates": [], "himo_candidates": [],
            "jizen_formation": {}, "ryotate_verdict": ryotate_verdict,
            "ryotate_detail": ryotate,
        }

    from lr_probs import _calc_3rentan_probs_v2  # 循環import回避のため遅延import
    combos = _calc_3rentan_probs_v2(
        results,
        venue_course_1c_rate=race_judgment.get("venue_c1_win_rate"),
        jizen_eval=jizen_eval,
        race_judgment=race_judgment,
        tenkai_national=tenkai_national,
        tenkai_venue=tenkai_venue,
        venue_stats=venue_stats,
    )
    if not combos:
        return {
            "axis1": "-", "axis2": "-", "buy_list": [], "point_count": 0,
            "comment": "確率計算不能", "combos": [], "candidates": [],
            "scenario_type": "-", "scenario_verdict": "-",
            "theory_syn_odds": None, "required_syn_odds": None,
            "margin_ratio": None, "margin_verdict": "-",
            "escape_score": 50, "tobi_score": 30, "fly_axes": [],
            "candidates_s1": [], "candidates_s2": [],
            "axis_candidates": [], "himo_candidates": [],
            "jizen_formation": {}, "ryotate_verdict": ryotate_verdict,
            "ryotate_detail": ryotate, "first_prob_map": {},
        }

    # ======================================================================
    # Step A: 1着別確率集計
    # ======================================================================
    first_prob_map = {}
    for c in combos:
        w = c["first"]
        first_prob_map[w] = first_prob_map.get(w, 0) + c["prob"]

    s1_prob  = first_prob_map.get("1", 0.0)
    fly_prob = sum(p for w, p in first_prob_map.items() if w != "1")

    # ======================================================================
    # Step A-2: 個人攻撃有効性による first_prob_map 補正
    # ======================================================================
    # 【設計思想】
    # 現状の first_prob_map は「統計的な1着確率（コース別マスタ×会場特性）」で
    # 計算されており、「このメンバー6人の個人間の勝負」が反映されていない。
    #
    # _calc_attack_effectiveness は既に
    #   攻撃力 × 1号艇脆弱性 × STアドバンテージ × 会場適性
    # を個人レベルで計算しているため、これを first_prob_map に直接フィードバックする。
    #
    # 補正方式:
    #   2〜6号艇: first_prob × (1 + atk_eff × ATKCORR_WEIGHT)
    #   1号艇:    first_prob × (1 - max_threat × NIGE_SUPPRESS_WEIGHT)
    #   → 全艇を再正規化して確率の総和を1.0に保つ
    #
    # 係数設計:
    #   ATKCORR_WEIGHT = 0.40: 攻撃有効性スコアが1.0のとき最大+40%の確率ブースト
    #   NIGE_SUPPRESS_WEIGHT = 0.30: 最大脅威スコア1.0のとき1号艇を最大-30%抑制
    #   → 統計確率を完全に置き換えるのではなく「メンバー補正」として重ねる設計
    # ======================================================================
    ATKCORR_WEIGHT      = 0.22   # 修正: 0.40→0.22（統計確率を守る）
    NIGE_SUPPRESS_WEIGHT = 0.20  # 修正: 0.30→0.20（1号艇確率の過剰抑制を防ぐ）

    _r1_for_atk = next((r for r in results if r["waku"] == "1"), None)
    _w1_cm_atk  = _r1_for_atk.get("raw_cm", {}) if _r1_for_atk else {}

    # 各攻撃艇の有効性スコアを計算
    _atk_eff_map = {}   # {waku: total_score}
    _atk_type_map = {}  # {waku: attack_type}
    _atk_breakdown = {} # {waku: breakdown dict} ← 狙い目コメント生成用
    for _r in results:
        if _r["waku"] == "1":
            continue
        _eff = _calc_attack_effectiveness(_r, _w1_cm_atk, venue_stats or {}, results, st_kimete_master=st_kimete_master)
        _atk_eff_map[_r["waku"]]   = _eff["total_score"]
        _atk_type_map[_r["waku"]]  = _eff["attack_type"]
        _atk_breakdown[_r["waku"]] = _eff

    # 最大脅威スコア（1号艇の逃げ抑制用）
    _max_threat_score = max(_atk_eff_map.values()) if _atk_eff_map else 0.0

    # first_prob_map を個人攻撃有効性で補正
    _corrected_prob = {}
    for _w, _p in first_prob_map.items():
        if _w == "1":
            # 1号艇: 最大脅威が高いほど逃げ確率を抑制
            _suppress = 1.0 - _max_threat_score * NIGE_SUPPRESS_WEIGHT
            _corrected_prob[_w] = max(_p * _suppress, 0.001)
        else:
            # 2〜6号艇: 個人攻撃有効性でブースト
            _boost = 1.0 + _atk_eff_map.get(_w, 0.0) * ATKCORR_WEIGHT
            _corrected_prob[_w] = _p * _boost

    # 再正規化（総和を1.0に保つ）
    _total_corrected = sum(_corrected_prob.values()) or 1.0
    first_prob_map = {
        _w: round(_p / _total_corrected, 5)
        for _w, _p in _corrected_prob.items()
    }

    # ── 狙い目（neraime）生成 ────────────────────────────────────────────
    # 攻め型: 攻撃有効性が閾値を超えた艇（1着狙い）
    # 残存型: 逃げ本命時に展開別残存マスタから2着残存確率が高い艇（2着狙い）
    #
    # 閾値: 0.15（旧0.25から引き下げ。各因子の積で0.25超えは稀すぎた）
    # 信頼度: 高(>=0.35) / 中(>=0.22) / 低(>=0.15) の3段階で表示
    NERAIME_THRESHOLD = 0.15
    _neraime_cands = sorted(
        [(w, s) for w, s in _atk_eff_map.items() if s >= NERAIME_THRESHOLD],
        key=lambda x: x[1], reverse=True
    )

    def _build_neraime_reason(waku, breakdown):
        """攻撃有効性の内訳から狙い目の根拠文を生成"""
        atk_type  = _atk_type_map.get(waku, "攻撃")
        atk_score = _atk_eff_map.get(waku, 0.0)
        bd        = breakdown or {}
        parts     = [f"{waku}号艇【{atk_type}】 攻撃有効性{atk_score*100:.0f}%"]
        if atk_type == "差し":
            v = bd.get("breakdown", {}).get("差し%", 0)
            if v:
                parts.append(f"差し実績{v*100:.0f}%")
        elif atk_type in ("まくり", "まくり差し"):
            mk  = bd.get("breakdown", {}).get("まくり%", 0)
            mks = bd.get("breakdown", {}).get("まくり差し%", 0)
            if mk or mks:
                parts.append(f"まくり系{(mk+mks)*100:.0f}%")
        vuln = bd.get("w1_vulnerability", 0)
        if vuln >= 0.3:
            parts.append(f"1号艇脆弱性高({vuln*100:.0f}%)")
        st_adv = bd.get("st_advantage", 1.0)
        if st_adv >= 1.3:
            parts.append(f"ST優位({st_adv:.2f}倍)")
        elif st_adv <= 0.7:
            parts.append(f"ST不利({st_adv:.2f}倍)")
        return " / ".join(parts)

    _neraime_list = []
    for _nw, _ns in _neraime_cands:
        _nbd = _atk_breakdown.get(_nw, {})
        _level = "高" if _ns >= 0.35 else "中" if _ns >= 0.22 else "低"
        _neraime_list.append({
            "waku":        _nw,
            "score":       round(_ns, 4),
            "level":       _level,
            "attack_type": _atk_type_map.get(_nw, "-"),
            "reason":      _build_neraime_reason(_nw, _nbd),
            "prob_after":  first_prob_map.get(_nw, 0.0),
            "type":        "攻め",   # 攻め型狙い目
        })

    # ── 残存型狙い目（逃げ本命時：展開別残存マスタの2着率直接参照）──────────
    # 逃げ本命（s1_prob >= 0.60）のとき「1号艇逃げ確定なら誰が2着に残るか」を
    # 展開別残存マスタの S1（逃げ/1着コース=1）から直接取得する。
    # circle_pct（イン逃げ時2着優位度）と 0.7:0.3 でブレンド。
    _neraime_2nd = []
    if s1_prob >= 0.60:
        _tenkai_s1_2nd = {}
        for _c in range(2, 7):
            _c_str = str(_c)
            _row_s1 = None
            _venue_rj = race_judgment.get("venue") if race_judgment else None
            if tenkai_venue and _venue_rj:
                _key_v = (str(_venue_rj), "逃げ", "1", _c_str)
                _rv = tenkai_venue.get(_key_v)
                if _rv:
                    try:
                        if float(_rv.get("信頼度") or 0) >= 0.15:
                            _row_s1 = _rv
                    except (ValueError, TypeError):
                        pass
            if _row_s1 is None and tenkai_national:
                _row_s1 = tenkai_national.get(("逃げ", "1", _c_str))
            if _row_s1:
                try:
                    _r2_v  = float(_row_s1.get("2着率")     or 0)
                    _r3i_v = float(_row_s1.get("3着以内率") or 0)
                    _tenkai_s1_2nd[_c_str] = {"2着率": _r2_v, "3着以内率": _r3i_v}
                except (ValueError, TypeError):
                    pass

        if _tenkai_s1_2nd:
            _circ_total = max(sum(circ_map.values()), 1)
            for _c_str, _rates in sorted(
                _tenkai_s1_2nd.items(), key=lambda x: x[1]["2着率"], reverse=True
            ):
                _r2_v   = _rates["2着率"]
                _r3i_v  = _rates["3着以内率"]
                _circ_v = circ_map.get(_c_str, 0)
                _circ_n = _circ_v / _circ_total   # 正規化
                # マスタ2着率(0.70) + 正規化circle_pct(0.30) でブレンド
                _blend2 = _r2_v * 0.70 + _circ_n * 0.30
                if _r2_v >= 0.15:
                    _neraime_2nd.append({
                        "waku":     _c_str,
                        "r2_rate":  round(_r2_v, 4),
                        "r3i_rate": round(_r3i_v, 4),
                        "blend":    round(_blend2, 4),
                        "reason":   (
                            f"{_c_str}号艇 逃げ時2着残存{_r2_v*100:.0f}%"
                            f"（展開別残存マスタ）/ 2着優位度{_circ_v:.0f}%"
                        ),
                        "type":     "残存",   # 残存型狙い目
                    })

    # 最有力狙い目（攻め型のスコア最大の1艇）
    neraime_top = _neraime_list[0] if _neraime_list else None

    # ── s1_prob / fly_prob を補正後の first_prob_map で再計算 ───────────
    s1_prob  = first_prob_map.get("1", 0.0)
    fly_prob = sum(p for w, p in first_prob_map.items() if w != "1")

    # 飛び候補艇を確率降順でリストアップ
    fly_candidates_sorted = sorted(
        [(w, p) for w, p in first_prob_map.items() if w != "1"],
        key=lambda x: x[1], reverse=True
    )
    main_fly_waku = fly_candidates_sorted[0][0] if fly_candidates_sorted else None
    sub_fly_waku  = fly_candidates_sorted[1][0] if len(fly_candidates_sorted) >= 2 else None

    # ======================================================================
    # Step 0: 見送り判定（最優先 ── 買い目生成の前に実行）
    # ======================================================================
    # 【設計思想】
    # 引き継ぎ書の方針に従い、見送り判定を買い目生成より前に実行する。
    # 見送りが確定した時点で買い目生成をスキップし、理由のみを返す。
    #
    # ここで必要な情報:
    #   - first_prob_map     : 追加条件A（1着団子判定）に使用
    #   - kimete_mismatch    : 追加条件B（根拠指標矛盾判定）を計算して渡す
    #   - nyujo_henkou / himo_are / s1_prob / honmei_prob_mismatch
    #                        : 既存条件(0)〜(3) は race_judgment から取得
    # ──────────────────────────────────────────────────────────────────────
    # 【追加B】根拠指標矛盾の計算
    # 1着確率最高艇の「個人逃げ%」が「会場逃げ平均」と±20%以上乖離していれば矛盾
    # venue_stats から会場逃げ平均を取得（なければ全国平均 55.5% で代替）
    _venue_nige_avg = 0.555  # 全国1コース逃げ率デフォルト
    if venue_stats:
        _vna_raw = venue_stats.get("nige_avg") or venue_stats.get("venue_nige_rate")
        if _vna_raw is not None:
            try:
                _vna_v = float(_vna_raw)
                _venue_nige_avg = _vna_v / 100.0 if _vna_v > 1.5 else _vna_v
            except (ValueError, TypeError):
                pass

    _kimete_mismatch = {}
    if first_prob_map:
        _top_waku_b = max(first_prob_map, key=first_prob_map.get)
        _top_prob_b = first_prob_map[_top_waku_b]
        _top_r_b    = next((r for r in results if r["waku"] == _top_waku_b), None)
        if _top_r_b is not None:
            _cm_b        = _top_r_b.get("raw_cm", {}) or {}
            _indiv_nige  = safe_float(_cm_b.get("逃げ%")) or 0.0
            # %表記（100超）を0〜1に変換
            if _indiv_nige > 1.5:
                _indiv_nige /= 100.0
            _diff_b = _indiv_nige - _venue_nige_avg
            # 差が±20%超（絶対値0.20超）かつ1着率がある程度高い（40%以上）場合のみ矛盾
            _is_mismatch_b = (abs(_diff_b) >= 0.20 and _top_prob_b >= 0.40)
            _kimete_mismatch = {
                "is_mismatch":   _is_mismatch_b,
                "waku":          _top_waku_b,
                "first_prob":    _top_prob_b,
                "indiv_nige_pct": _indiv_nige,
                "venue_nige_avg": _venue_nige_avg,
                "diff_pct":      _diff_b,
            }

    # 早期見送り用の仮 bet_suggestions を組み立てて判定を実行
    _early_skip_dict = {
        "nyujo_henkou":              (race_judgment or {}).get("nyujo_henkou", False),
        "s1_prob":                   s1_prob,
        "himo_are":                  (race_judgment or {}).get("himo_are", {}),
        "honmei_prob_mismatch":      (race_judgment or {}).get("honmei_prob_mismatch", False),
        "honmei_prob_mismatch_detail": (race_judgment or {}).get("honmei_prob_mismatch_detail", ""),
        "first_prob_map":            first_prob_map,
        "kimete_mismatch":           _kimete_mismatch,
    }
    _early_skip, _early_skip_reason = _should_skip_race(
        _early_skip_dict,
        venue=(race_judgment or {}).get("venue", ""),
    )
    if _early_skip:
        # 見送り確定 → 買い目生成をスキップして即時返却
        _skip_result = {
            "axis1": "-", "axis2": "-", "buy_list": [], "point_count": 0,
            "comment":        _early_skip_reason,
            "combos":         combos,
            "candidates":     [],
            "scenario_type":  "見送り",
            "scenario_verdict": "見送り",
            "theory_syn_odds": None, "required_syn_odds": None,
            "margin_ratio": None, "margin_verdict": "-",
            "escape_score": 50, "tobi_score": 30, "fly_axes": [],
            "candidates_s1": [], "candidates_s2": [],
            "axis_candidates": [], "himo_candidates": [],
            "jizen_formation": {}, "ryotate_verdict": ryotate_verdict,
            "ryotate_detail": ryotate,
            "first_prob_map": {w: round(p, 4) for w, p in first_prob_map.items()},
            "s1_prob":        s1_prob,
            "neraime":        [], "neraime_2nd": [], "neraime_top": None,
            "atk_eff_map":    {},
            "skip":           True,
            "skip_reason":    _early_skip_reason,
            "kimete_mismatch": _kimete_mismatch,
            # 後続処理で参照されるキーをデフォルト値で埋める
            "consistency_warn": False,
            "honmei_prob_mismatch": False,
            "honmei_prob_mismatch_detail": "",
            "ev_warning": False, "ev_warning_msg": "",
            "tenkai_pattern": "-", "tenkai_pattern_policy": "",
            "entry_grade": {},
            "kelly": {},
            "nyujo_henkou": (race_judgment or {}).get("nyujo_henkou", False),
            "himo_are": (race_judgment or {}).get("himo_are", {}),
        }
        return _skip_result

    # ======================================================================
    # Step B: シナリオ判定（確率優先型 v3 ── 印は確率を補強する証拠として使用）
    # ======================================================================
    # 【設計思想】
    # 旧版は「印◎の艇番でシナリオを決定」していたため、
    # 確率と印が逆向きになるとシナリオも買い目も確率と矛盾していた。
    # v3 では確率を起点にシナリオを決定し、印はその補強証拠として扱う。
    #
    # 判定フロー:
    #   Step B-1: s1_prob（確率）でシナリオの「下地」を決める
    #   Step B-2: 印◎の位置で補強・修正する（確率と同方向なら強化、逆方向なら両建て）
    #   Step B-3: ryotate（定性スコア）で最終調整
    # ======================================================================
    first_turn      = race_judgment.get("first_turn", {}) or {}
    conflict_map    = race_judgment.get("conflict_map", {}) or {}
    sq              = race_judgment.get("scenario_quality", {}) or {}
    quality_rank    = sq.get("quality_rank", "B")
    lead_waku       = first_turn.get("lead_waku", "1")
    main_conflict   = conflict_map.get("main_conflict") or {}
    sub_conflict    = conflict_map.get("sub_conflict") or {}
    collapse_bene   = conflict_map.get("collapse_beneficiary", [])
    lead_is_1       = (lead_waku == "1")
    p_strength      = first_turn.get("pattern_strength", "中")
    mc_strength     = main_conflict.get("strength", 0) or 0

    # ── 印から軸・ヒモ情報を取得 ─────────────────────────────────────────
    # 【v7.0修正】1号艇の honmei は「逃◎→◎」に変換済みだが、
    # 2〜6号艇にも攻め◎が存在するため inv 辞書で後勝ちになり
    # 1号艇の◎が攻め◎で上書きされる問題を修正。
    #
    # 1号艇の軸判断: s1_prob の水準で直接決める（honmei_map を介さない）
    # 2〜6号艇の軸判断: 1号艇を除外した honmei_map の◎○▲△を参照
    if honmei_map:
        # 2〜6号艇のみで inv を構築（1号艇の"◎"を除外して上書き衝突を防ぐ）
        inv = {v: k for k, v in honmei_map.items() if v.strip() and k != "1"}
        atk_honmei_waku  = inv.get("◎")   # 攻め◎（2〜6号艇）
        taiko_waku       = inv.get("○")
        tanhana_waku     = inv.get("▲")
        ana_waku         = inv.get("△")
    else:
        sorted_fp = sorted(
            [(w, p) for w, p in first_prob_map.items() if w != "1"],
            key=lambda x: x[1], reverse=True
        )
        atk_honmei_waku  = sorted_fp[0][0] if len(sorted_fp) > 0 else None
        taiko_waku       = sorted_fp[1][0] if len(sorted_fp) > 1 else None
        tanhana_waku     = sorted_fp[2][0] if len(sorted_fp) > 2 else None
        ana_waku         = sorted_fp[3][0] if len(sorted_fp) > 3 else None

    # ── 1号艇の軸判断（v8.0: s1_prob バイパスで逃げ軸転落を防止）──────────
    # 【v7.0の副作用と修正】
    #   v7.0で1号艇の honmei は「逃◎」専用となり攻め◎は付かなくなった。
    #   そのため honmei_map 逆引きの atk_honmei_waku は常に2〜6号艇を指す。
    #   旧ロジックでは s1_prob>=0.60 で honmei_waku="1" としていたが、
    #   直後の Step B-2 で「honmei_waku!=1 → 両建て転落」に上書きされていた。
    #   （_prob_gap_pct の大小に関わらず全分岐が両建てを返す構造だった）
    #
    #   v8.0修正: s1_prob >= 0.60 の場合は honmei_waku="1" かつ
    #   scenario_type="逃げ軸流し" を直接確定し Step B-2 をバイパスする。
    #   飛び軸・両建て域（s1_prob < 0.60）は旧ロジックと同一。
    _s1_bypass = (s1_prob >= 0.60)  # True のとき Step B-2 をスキップ

    if s1_prob >= 0.60:
        honmei_waku   = "1"
        scenario_type = "逃げ軸流し"   # Step B-2 をバイパスして直接確定
    elif s1_prob >= 0.42:
        # 拮抗域: 攻め◎がいれば飛び軸候補、いなければ1号艇
        honmei_waku   = atk_honmei_waku if atk_honmei_waku else "1"
        scenario_type = None            # Step B-2 で確定
    else:
        # 飛び有力: 攻め◎を主軸に
        honmei_waku   = atk_honmei_waku if atk_honmei_waku else "1"
        scenario_type = None            # Step B-2 で確定

    # ── Step B-1: 確率でシナリオ下地を決定 ──────────────────────────────
    # s1_prob が高い → 1号艇が1着になる確率が高い → 逃げ軸が基本
    # s1_prob が低い → 他艇が1着になる確率が高い → 飛び軸が基本
    if s1_prob >= 0.60:
        scenario_base = "逃げ軸流し"
    elif s1_prob >= 0.42:
        scenario_base = "両建て"
    else:
        scenario_base = "飛び軸"

    # ── Step B-2: 印◎で補強・修正（s1_prob>=0.60 はバイパス済み）──────────
    # 確率と印が同方向 → シナリオ確定
    # 確率と印が逆方向 → 矛盾の「強度」で判断
    #
    # 【v2 改善: 矛盾解消ロジック】
    # 旧方式: 逆方向なら無条件に両建て
    # 新方式: 乖離幅に応じて判断
    #   ・乖離が大きい（確率差 >= 20pt）→ 確率優先でシナリオ決定、印は◎位置を修正
    #   ・乖離が中程度（10〜20pt）      → 両建て（どちらが正しいか不確実）
    #   ・乖離が小さい（< 10pt）         → 印優先（印の方が人間の定性判断が入っている）
    #
    # 「確率vs印の乖離幅」: honmei_waku の first_prob を確率上位艇と比較
    _honmei_first_prob = first_prob_map.get(honmei_waku, 0) if honmei_waku else 0
    _top_prob_waku     = max(first_prob_map, key=first_prob_map.get) if first_prob_map else "1"
    _top_first_prob    = first_prob_map.get(_top_prob_waku, 0)
    _prob_gap_pct      = (_top_first_prob - _honmei_first_prob) * 100  # 正 = 確率最大艇 > ◎

    if not _s1_bypass:
        # s1_prob < 0.60 のみ Step B-2 を実行（逃げ軸は既に確定済みのためスキップ）
        if scenario_base == "逃げ軸流し":
            if honmei_waku == "1":
                # 確率高×印◎=1号艇 → 最強の逃げシナリオ
                scenario_type = "逃げ軸流し"
            elif honmei_waku is not None:
                # 確率高なのに印◎≠1号艇
                if _prob_gap_pct >= 20:
                    # 確率と印の乖離が大きい → 確率優先（印が誤っている可能性）
                    scenario_type = "逃げ軸流し"
                    # ただし飛び軸候補として印◎艇も両建てに含める
                    main_fly_waku = honmei_waku
                    scenario_type = "両建て"
                elif _prob_gap_pct >= 10:
                    scenario_type = "両建て"
                    main_fly_waku = honmei_waku
                else:
                    # 乖離小 → 印優先（定性が確率を微修正している）
                    scenario_type = "両建て"
                    main_fly_waku = honmei_waku
            else:
                scenario_type = "逃げ軸流し"

        elif scenario_base == "飛び軸":
            if honmei_waku != "1":
                # 確率低×印◎≠1号艇 → 飛び軸確定
                scenario_type = "飛び軸"
                main_fly_waku = honmei_waku
            elif honmei_waku == "1":
                # 確率低なのに印◎=1号艇
                if _prob_gap_pct >= 20:
                    # 確率と印の乖離大 → 確率優先して飛び軸
                    scenario_type = "飛び軸"
                else:
                    # 乖離小 → 印を尊重して両建て
                    scenario_type = "両建て"
            else:
                scenario_type = "飛び軸"

        else:  # 両建て
            scenario_type = "両建て"
            if honmei_waku and honmei_waku != "1":
                main_fly_waku = honmei_waku

    # ── Step B-3: ryotate（定性スコア）で最終調整 ───────────────────────
    _ryotate_verdict   = ryotate.get("verdict", "逃げ狙い")
    _consistency_warn  = ryotate.get("consistency_warn", False)

    # ryotate が明確に飛び狙いと言っているのにシナリオが逃げ軸なら両建てに
    if _ryotate_verdict == "飛び狙い" and scenario_type == "逃げ軸流し":
        scenario_type = "両建て"
    # quality D は混戦 → 逃げ軸流しは危険
    if quality_rank == "D" and scenario_type == "逃げ軸流し":
        scenario_type = "両建て"

    # ── 飛び軸主軸の確定 ─────────────────────────────────────────────────
    if scenario_type in ("飛び軸", "両建て"):
        if main_fly_waku is None or main_fly_waku == "1":
            # 飛び軸主軸が未確定 or 1号艇になっている → 確率2位の艇に
            main_fly_waku = fly_candidates_sorted[0][0] if fly_candidates_sorted else "2"
        if sub_fly_waku is None or sub_fly_waku == main_fly_waku:
            sub_fly_waku = fly_candidates_sorted[1][0] if len(fly_candidates_sorted) >= 2 else taiko_waku

    # ======================================================================
    # Step C: 買い目構成 ── 考察フル連動モデル v8.0
    # ======================================================================
    #
    # 考察行 → 買い目への因果
    # (1)逃げ力(escape_rank)   → tenkai_pattern の基盤
    # (2)主役(main_score/type) → 飛び頭の軸・スロット比率
    # (3)残存(fallback_rank)   → 逃げ残存フォロー点数
    # (4)穴(dark_horse)        → 穴ヒモ挿入
    # (7)展開quality(rank)     → 累積閾値・総点数
    # tenkai_pattern          → 1号頭/飛び頭 スロット比率
    #
    # ─── tenkai_pattern 別スロット比率 ──────────────────────────────────
    # A（鉄板逃げ）: 1号頭100%（逃げのみ）
    # B（主役展開）: 1号頭30% / 飛び頭70%  ← 飛び主体・逃げ残存フォロー付き
    # C（拮抗）    : 1号頭50% / 飛び頭50%  ← 均等両建て
    # D（荒れ）    : 1号頭30% / 飛び頭70%  ← 広め・穴ヒモ付き

    # ── quality 別 累積閾値 ──────────────────────────────────────────────
    THRESHOLD_BY_QUALITY = {"S": 0.70, "A": 0.75, "B": 0.80, "C": 0.85, "D": 0.85}
    CUMULATIVE_THRESHOLD = THRESHOLD_BY_QUALITY.get(quality_rank, 0.78)
    MIN_BETS = 3

    _race_are = safe_float((race_judgment or {}).get("venue_race_are_score")) if race_judgment else None
    if _race_are is not None:
        if _race_are >= 65:
            CUMULATIVE_THRESHOLD = min(0.92, CUMULATIVE_THRESHOLD + 0.05)
        elif _race_are >= 55:
            CUMULATIVE_THRESHOLD = min(0.90, CUMULATIVE_THRESHOLD + 0.02)
        elif _race_are <= 30:
            CUMULATIVE_THRESHOLD = max(0.65, CUMULATIVE_THRESHOLD - 0.05)
        elif _race_are <= 40:
            CUMULATIVE_THRESHOLD = max(0.68, CUMULATIVE_THRESHOLD - 0.02)

    # ── tenkai_pattern 確定 ───────────────────────────────────────────────
    _mp      = race_judgment.get("main_player", {}) or {}
    _dh      = race_judgment.get("dark_horse", {}) or {}
    _ef      = race_judgment.get("escape_fallback", {}) or {}
    _er      = (race_judgment.get("w1_escape", {}) or {}).get("escape_rank", "中")
    _ms      = float(_mp.get("main_score", 0) or 0)
    _fb_rank = _ef.get("fallback_rank", "中")
    _dh_ok   = _dh.get("is_valid", False)

    # v8.0: s1_prob を第1軸として tenkai_pattern を決定する
    # 【旧版の問題】escape_rank×main_score の2変数マトリクスのみで判定していたため、
    #   _er="高" でも _ms>=0.40 であれば常にBとなり、Aがほぼ発動しなかった。
    #   競艇では「逃げ力が高くても攻め手がいる」のは普通の状況なので
    #   _ms>=0.40 はほぼ全レースで成立し、結果1号頭スロット30%に固定されていた。
    # 【新版の設計】
    #   確率モデルが逃げ鉄板（s1_prob>=0.65）と判断しているなら、
    #   主役スコアに関わらず tenkai_pattern A を発動させる。
    #   s1_prob と escape_rank の両方が逃げを示す場合のみA確定とすることで
    #   確率と展開パターンの一貫性を保つ。
    if s1_prob >= 0.65 and _er == "高":
        # 確率モデル・定性スコア双方が逃げ鉄板 → A確定
        tenkai_pattern = "A"
    elif s1_prob >= 0.60 and _er == "高":
        # 逃げ有力だが主役候補が強い場合はB、そうでなければA
        tenkai_pattern = "A" if _ms < 0.55 else "B"
    elif s1_prob >= 0.60 and _er == "中":
        # 確率高・逃げ力中程度 → 拮抗C（逃げ軸寄り）
        tenkai_pattern = "C"
    elif s1_prob >= 0.50 and _er == "高" and _ms >= 0.50:
        # 逃げ力高・主役明確 → 主役展開B
        tenkai_pattern = "B"
    elif s1_prob >= 0.50 and _er == "高":
        # 逃げ力高・主役弱 → 拮抗C（逃げ軸寄り）
        tenkai_pattern = "C"
    elif s1_prob >= 0.42 and _ms >= 0.45:
        # 拮抗域・主役候補明確 → 主役展開B
        tenkai_pattern = "B"
    elif s1_prob >= 0.42:
        # 拮抗域・主役弱 → 拮抗C
        tenkai_pattern = "C"
    elif _er == "低" and _dh_ok:
        # 逃げ弱・穴候補あり → 荒れD
        tenkai_pattern = "D"
    elif _er == "低" and _ms >= 0.45:
        # 逃げ弱・主役強 → 主役展開B
        tenkai_pattern = "B"
    elif _er == "低":
        # 逃げ弱・主役弱 → 荒れD
        tenkai_pattern = "D"
    else:
        tenkai_pattern = "C"

    _TENKAI_POLICY = {
        "A": "1着1号艇固定・ヒモ絞り（逃げ圧倒・主役展開リスク低）",
        "B": "主役1着軸・逃げ残存フォロー（escape_fallback補強）",
        "C": "1号艇＋主役の2頭軸・ヒモ広め",
        "D": "穴候補込みの広め買い（dark_horse補強）",
    }
    _tenkai_policy_text = (
        "広め買い・参加慎重（逃げ弱・主役弱・穴候補なし＝全面荒れリスク）"
        if tenkai_pattern == "D" and not _dh_ok
        else _TENKAI_POLICY[tenkai_pattern]
    )
    race_judgment["tenkai_pattern"]        = tenkai_pattern
    race_judgment["tenkai_pattern_policy"] = _tenkai_policy_text

    # ── スロット配分 ─────────────────────────────────────────────────────
    MAX_BETS = 20 if tenkai_pattern == "D" else 18
    if _race_are is not None:
        if _race_are >= 65:
            MAX_BETS = min(MAX_BETS + 2, 22)
        elif _race_are >= 55:
            MAX_BETS = min(MAX_BETS + 1, 21)
        elif _race_are <= 30:
            MAX_BETS = max(MAX_BETS - 2, 10)
        elif _race_are <= 40:
            MAX_BETS = max(MAX_BETS - 1, 12)

    add_sc_bets   = (mc_strength >= 40 and len(collapse_bene) >= 1)
    _dh_cands_all = _dh.get("dark_horse_candidates", []) or []
    _dh_slots = (4 if len(_dh_cands_all) >= 2 else 2) if (tenkai_pattern in ("B", "D") and _dh_ok) else 0
    SC_SLOTS  = 2 if add_sc_bets and collapse_bene else 0
    base_max  = MAX_BETS - SC_SLOTS - _dh_slots

    # tenkai_pattern 別の 1号頭スロット比率
    _slot_ratio = {"A": 1.0, "B": 0.30, "C": 0.50, "D": 0.30}
    _w1_ratio   = _slot_ratio.get(tenkai_pattern, 0.50)
    # v8.0: s1_prob 連動の1号頭最低保証点数
    # 旧版 MIN_BETS=3 固定では打ち切り時に1号頭買い目が削られていた
    # s1_prob が高いほど1号頭スロットを積み増すことで逃げ軸を確保する
    _s1_min_bets = (
        5 if s1_prob >= 0.60 else
        4 if s1_prob >= 0.50 else
        MIN_BETS
    )
    _w1_slots   = base_max if tenkai_pattern == "A" else max(_s1_min_bets, round(base_max * _w1_ratio))
    _fly_slots  = 0 if tenkai_pattern == "A" else base_max - _w1_slots

    # ── 飛び軸スロットを◎頭（main）と○頭（taiko）に分割 ────────────────
    # 飛び軸（B/C/D）で taiko_waku（印○）が存在する場合、
    # ◎の確率に応じて◎頭と○頭にスロットを配分する。
    # ◎単独（taiko_waku なし）の場合は全スロットを◎頭に集中。
    #
    # 配分ロジック:
    #   確率比率 = ◎確率 / (◎確率 + ○確率) を基本に
    #   min 6:4（◎有利）〜 max 8:2 でクランプ
    _main_fly_prob  = first_prob_map.get(main_fly_waku, 0) if main_fly_waku else 0
    _taiko_prob     = first_prob_map.get(taiko_waku, 0)    if taiko_waku    else 0
    _has_taiko      = (
        taiko_waku is not None
        and taiko_waku != main_fly_waku
        and taiko_waku != "1"
        and _taiko_prob > 0
        and tenkai_pattern in ("B", "C", "D")
        and _fly_slots >= 4          # 最低4スロットないと○頭に割く余裕がない
    )
    if _has_taiko and (_main_fly_prob + _taiko_prob) > 0:
        _raw_ratio   = _main_fly_prob / (_main_fly_prob + _taiko_prob)
        _main_ratio  = max(0.60, min(0.80, _raw_ratio))   # 6:4〜8:2 でクランプ
    else:
        _main_ratio  = 1.0

    _main_fly_slots  = _fly_slots if not _has_taiko else max(MIN_BETS, round(_fly_slots * _main_ratio))
    _taiko_fly_slots = 0          if not _has_taiko else max(2, _fly_slots - _main_fly_slots)

    combo_lookup = {c["combo"]: c for c in combos}

    # 買い目根拠を生成する補助関数
    def _build_reason(e, scenario_ctx):
        """
        各買い目コンボの「買う理由」を自然言語で生成する。
        考察（展開エンジン）→ 買い目への因果を明示する。
        """
        first  = e["first"]
        second = e["second"]
        third  = e["third"]
        is_rev = e.get("_orkaeshi", False)

        # 1着根拠
        if first == "1":
            if lead_is_1 and p_strength == "強":
                r1 = f"1号先行確定的({p_strength})"
            elif lead_is_1:
                r1 = f"1号先行優位"
            else:
                r1 = f"1号逃げ残り(先行は{lead_waku}号)"
        elif first == main_fly_waku:
            mc_method = main_conflict.get("method", "攻撃")
            r1 = f"{first}号{mc_method}（主軸攻撃・強度{mc_strength:.0f}）"
        elif first == sub_fly_waku:
            sc_method = sub_conflict.get("method", "攻撃") if sub_conflict else "攻撃"
            r1 = f"{first}号{sc_method}（副軸）"
        else:
            r1 = f"{first}号（その他）"

        # 2着根拠
        top_bene = [w for w, _ in collapse_bene[:2]]
        if is_rev:
            r2 = f"{second}号折返（{first}号自滅時の逃げ取り戻し想定）"
        elif second in top_bene:
            r2 = f"{second}号漁夫（{main_conflict.get('attacker','?')}号自滅時の受益）"
        else:
            r2 = f"{second}号残存"

        return f"{r1} / {r2}"

    # ── 折り返し要否の判定関数 ──────────────────────────────────────────────────

    def _needs_orkaeshi_12(base_combo, rev_key):
        """
        1着折り返し（A-1-B vs 1-A-B）が必要かを判定する。

        不要と判断する条件:
          (1) s1_prob >= 0.75: 逃げ確率が圧倒的 → 飛び役1着はほぼない
          (2) 折り返しコンボの確率が本体の1/4未満: 展開として非現実的
          (3) 折り返し1着艇の1着確率が全艇平均の0.5倍未満: その艇が1着になる素地がない

        いずれか1つでも該当すれば不要と判断。
        """
        if rev_key not in combo_lookup:
            return False
        base = combo_lookup.get(base_combo)
        rev  = combo_lookup[rev_key]
        if not base:
            return True
        # (1) 逃げ圧倒的
        if s1_prob >= 0.75:
            return False
        # (2) 確率比
        if base["prob"] > 0 and rev["prob"] / base["prob"] < 0.25:
            return False
        # (3) 折り返し1着艇の1着確率（記号○以上は閾値を0.5→0.3に緩和）
        # 「攻め力を認められた艇なら確率が低めでも折り返しを追加する価値がある」
        rev_first_waku = rev["first"]
        rev_first_prob = first_prob_map.get(rev_first_waku, 0)
        avg_first_prob = sum(first_prob_map.values()) / max(len(first_prob_map), 1)
        _honmei_of_rev = next(
            (r.get("honmei", "") for r in results if r["waku"] == rev_first_waku), ""
        )
        _thresh = 0.3 if _honmei_of_rev in ("◎", "○") else 0.5
        if rev_first_prob < avg_first_prob * _thresh:
            return False
        return True

    def _needs_orkaeshi_23(base_combo, rev_key):
        """
        2着3着折り返し（1-A-B vs 1-B-A）が必要かを判定する。

        不要と判断する条件:
          (1) 本体と折り返しの確率比が3倍以上: 順序がほぼ固定的
          (2) 2着と3着の circle_pct（イン逃げ時2着優位度）差が2倍以上:
             2着候補がほぼ固定されている
          (3) 折り返しコンボの確率が全買い目平均の0.4倍未満: 薄すぎる

        いずれか1つでも該当すれば不要と判断。
        """
        if rev_key not in combo_lookup:
            return False
        base = combo_lookup.get(base_combo)
        rev  = combo_lookup[rev_key]
        if not base:
            return True
        # (1) 確率比（3倍以上なら逆順はほぼ来ない）
        if base["prob"] > 0 and base["prob"] / max(rev["prob"], 1e-9) >= 3.0:
            return False
        # (2) circle_pct差（2着固定度）
        circ_a = next((r.get("circle_pct") or 0 for r in results if r["waku"] == base["second"]), 0)
        circ_b = next((r.get("circle_pct") or 0 for r in results if r["waku"] == base["third"]),  0)
        if circ_a > 0 and circ_b > 0 and circ_a / circ_b >= 2.0:
            return False
        if circ_b > 0 and circ_a > 0 and circ_b / circ_a >= 2.0:
            return False
        # (3) 折り返し確率が薄すぎる
        avg_prob = sum(c["prob"] for c in combos) / max(len(combos), 1)
        if rev["prob"] < avg_prob * 0.4:
            return False
        return True

    # ======================================================================
    # 共通データマップ（_build_buys内で参照）
    # ======================================================================
    _r_map     = {r["waku"]: r for r in results}
    _cm_map    = {r["waku"]: r.get("raw_cm", {}) for r in results}
    _circ_map  = {r["waku"]: (r.get("circle_pct") or 0) for r in results}
    _win3_map  = {r["waku"]: (r.get("win3_rate") or 0.0) for r in results}
    _st_map    = {r["waku"]: r.get("avg_st") for r in results}
    _motor_map = {}
    for r in results:
        try:
            v = float(r.get("motor2") or 0)
            _motor_map[r["waku"]] = v if v > 0 else None
        except (ValueError, TypeError):
            _motor_map[r["waku"]] = None

    # ── 【v6.2】_suggest_3rentan用 選手指数マップ（raw_pmから全指数を取得）──
    # _calc_3rentan_probs_v2内の同名変数と独立して構築（スコープが異なるため）
    _sg_form_map    = {}  # フォーム指数
    _sg_recent3_map = {}  # 直近3走1着率
    _sg_recent5_map = {}  # 直近5走1着率
    _sg_st_std_map  = {}  # ST標準偏差
    _sg_st_stab_map = {}  # ST安定スコア
    _sg_jizai_map   = {}  # 自在性加重1着率
    _sg_ippan_map   = {}  # 一般戦1着率
    _sg_recent10_map= {}  # 直近10走平均着順
    for r in results:
        w   = r["waku"]
        pm_r = r.get("raw_pm") or {}
        _sg_form_map[w]     = safe_float(pm_r.get("フォーム\n指数")    or pm_r.get("フォーム指数"))
        _sg_recent3_map[w]  = safe_float(pm_r.get("直近3走\n1着率")    or pm_r.get("直近3走1着率"))
        _sg_recent5_map[w]  = safe_float(pm_r.get("直近5走\n1着率")    or pm_r.get("直近5走1着率"))
        _sg_st_std_map[w]   = safe_float(pm_r.get("ST\n標準偏差")      or pm_r.get("ST標準偏差"))
        _sg_st_stab_map[w]  = safe_float(pm_r.get("ST安定\nスコア")    or pm_r.get("ST安定スコア"))
        _sg_jizai_map[w]    = safe_float(pm_r.get("自在性\n加重1着率") or pm_r.get("自在性加重1着率"))
        _sg_ippan_map[w]    = safe_float(pm_r.get("1着率\n(一般戦)")   or pm_r.get("1着率(一般戦)"))
        _sg_recent10_map[w] = safe_float(pm_r.get("直近10走\n平均着順")or pm_r.get("直近10走平均着順"))

    # ── 【v6.3】STレンジマップ（_member_scenario_scaleのr["_st_range"]を再利用）──
    # コース別マスタの最速ST・最遅STから算出済みの値をそのまま使う
    _sg_st_range_map  = {r["waku"]: r.get("_st_range") for r in results}
    _sg_valid_ranges  = [v for v in _sg_st_range_map.values() if v is not None]
    _sg_st_range_mean = sum(_sg_valid_ranges) / len(_sg_valid_ranges) if _sg_valid_ranges else 0.30

    # ── 【v6.4新設】★STフラグマップ（_suggest_3rentan スコープ）────────────
    # _member_scenario_scale側の_star_st_mapと同じ判定ロジック（スコープが独立しているため再構築）
    _sg_star_st_map = {}
    for r in results:
        cm_r = r.get("raw_cm") or {}
        val  = cm_r.get("★ST")
        _sg_star_st_map[r["waku"]] = bool(val and str(val).strip() in ("★", "True", "1"))

    # jizen評価マップ（jizen_eval から艇別に取り出す）
    _jizen_aisho   = {}
    _jizen_tenkai  = {}
    _jizen_jizai   = {}
    _jizen_kiryoku = {}
    if jizen_eval is not None:
        for idx in range(6):
            w = str(idx + 1)
            _jizen_aisho[w]   = (jizen_eval.get("aisho")    or [""] * 6)[idx]
            _jizen_tenkai[w]  = (jizen_eval.get("tenkai")   or [""] * 6)[idx]
            _jizen_jizai[w]   = (jizen_eval.get("jizaisei") or [""] * 6)[idx]
            _jizen_kiryoku[w] = (jizen_eval.get("kiryoku")  or [""] * 6)[idx]

    # 1着軸ごとの2着残存補正テーブル（動的版 v2）
    # 【設計根拠 v2】
    # 旧版は静的テーブル（物理的な内側残存のみ）。
    # 実際には「2着に来る艇は、残存するだけでなく自分も仕掛けて生き残った艇」。
    # → POSITION_REMAIN[first][second] = 内側残存補正 × max(active_score, 0.5)
    #   active_score: その艇が仕掛け試行して生き残れる確率（calc_attack_probabilityで計算）
    #
    # 1号艇1着のときは circle_pct（イン逃げ時2着優位度）を使うためニュートラル維持。
    # ── 展開別残存マスタから動的にPOSITION_REMAIN_BASEを構築 ──────────────────
    # Phase 1: 純粋に「場の論理」（コース位置）だけで補正係数を実データから算出
    # 【構築方法】
    #   1. 各軸艇の「主な決まり手」を決まり手%から推定（最頻決まり手）
    #   2. (会場, 決まり手, 1着コース) でtenkai_venue_masterを検索
    #   3. 会場データが薄い(信頼度<0.3)場合はtenkai_national_masterでフォールバック
    #   4. 各残存コースの2着率を全体平均で割って相対補正係数に変換（1.0=平均）
    #   5. データなし → フォールバック静的テーブルを使用
    _POSITION_REMAIN_FALLBACK = {
        "1": {"2": 1.0, "3": 1.0, "4": 1.0, "5": 1.0, "6": 1.0},
        "2": {"1": 1.35, "3": 0.75, "4": 0.90, "5": 0.95, "6": 0.95},
        "3": {"1": 1.25, "2": 1.20, "4": 0.85, "5": 0.90, "6": 0.90},
        "4": {"1": 1.20, "2": 1.15, "3": 1.10, "5": 0.80, "6": 0.85},
        "5": {"1": 1.15, "2": 1.10, "3": 1.05, "4": 1.00, "6": 0.75},
        "6": {"1": 1.15, "2": 1.10, "3": 1.05, "4": 1.00, "5": 0.95},
    }

    # 各軸艇の主な決まり手を推定（コース別マスタの決まり手%から）
    KIMETE_PRIORITY = {
        "1": ["逃げ"],
        "2": ["差し", "まくり差し"],
        "3": ["まくり", "まくり差し", "差し"],
        "4": ["まくり", "まくり差し", "差し"],
        "5": ["まくり", "まくり差し"],
        "6": ["まくり", "まくり差し"],
    }

    def _get_main_kimete(waku):
        """軸艇の主な決まり手をコース別マスタから推定する"""
        r = _r_map.get(waku, {})
        candidates = KIMETE_PRIORITY.get(waku, ["まくり"])
        best_k, best_pct = candidates[0], 0.0
        for k in candidates:
            pct_key = f"決まり手_{k}%"
            try:
                v = float(r.get(pct_key) or r.get("raw_cm", {}).get(pct_key, 0) or 0)
                if v > best_pct:
                    best_pct, best_k = v, k
            except (ValueError, TypeError):
                pass
        return best_k

    def _build_pos_remain_from_master(first_w):
        """
        展開別残存マスタから first_w 軸の残存補正係数を構築する。
        戻り値: {second_w: 補正係数} （1.0=全国平均、>1.0=残りやすい、<1.0=残りにくい）

        【修正】決まり手を1つに固定せず、全決まり手の2着率を実データ比率でブレンド。
        例: 3号艇が差し6%・まくり6%の会場では「差し/3」と「まくり/3」のマスタを
            それぞれ参照し、比率に応じてブレンドした係数を返す。
        これにより決まり手が拮抗する場合のマスタ精度が向上する。
        """
        if first_w == "1":
            return _POSITION_REMAIN_FALLBACK["1"]  # 逃げはcircle_pctで判断

        # 実際の進入コースを results から取得
        r_data = _r_map.get(first_w, {})
        actual_course = str(int(float(r_data.get("course") or r_data.get("進入コース") or first_w)))

        # 各決まり手の実データ比率を取得（cm_map から）
        cm_fw = _cm_map.get(first_w, {})
        def _safe_pct_local(key):
            v = cm_fw.get(key)
            try:
                return max(float(v), 0.0) if v is not None else 0.0
            except (ValueError, TypeError):
                return 0.0

        kimete_weights = {}
        if actual_course == "1":
            kimete_weights["逃げ"] = 1.0
        else:
            sashi   = _safe_pct_local("差し%")
            makuri  = _safe_pct_local("まくり%")
            maksa   = _safe_pct_local("まくり差し%")
            total_k = sashi + makuri + maksa
            if total_k > 0:
                kimete_weights["差し"]      = sashi  / total_k
                kimete_weights["まくり"]    = makuri / total_k
                kimete_weights["まくり差し"] = maksa  / total_k
            else:
                # データなし → コース別デフォルト
                _DEFAULT_KIMETE = {
                    "2": {"差し": 0.70, "まくり": 0.10, "まくり差し": 0.20},
                    "3": {"差し": 0.20, "まくり": 0.35, "まくり差し": 0.45},
                    "4": {"差し": 0.10, "まくり": 0.60, "まくり差し": 0.30},
                    "5": {"差し": 0.10, "まくり": 0.65, "まくり差し": 0.25},
                    "6": {"差し": 0.10, "まくり": 0.60, "まくり差し": 0.30},
                }
                kimete_weights = _DEFAULT_KIMETE.get(actual_course, {"まくり": 1.0})

        def _fetch_row(kimete_k, c_str):
            """(決まり手, 進入コース) の行を会場別→全国の優先順で取得"""
            if c_str == actual_course:
                return None
            if tenkai_venue and venue:
                key_v = (str(venue), kimete_k, actual_course, c_str)
                row_v = tenkai_venue.get(key_v)
                if row_v:
                    try:
                        if float(row_v.get("信頼度") or 0) >= 0.3:
                            return row_v
                    except (ValueError, TypeError):
                        pass
            if tenkai_national:
                key_n = (kimete_k, actual_course, c_str)
                return tenkai_national.get(key_n)
            return None

        # 全決まり手をブレンドして2着率を集計
        blended_rates = {}
        for c in range(1, 7):
            c_str = str(c)
            if c_str == actual_course:
                continue
            blended_r2 = 0.0
            total_weight = 0.0
            for kimete_k, w_k in kimete_weights.items():
                if w_k <= 0:
                    continue
                row = _fetch_row(kimete_k, c_str)
                if row is None:
                    continue
                try:
                    r2 = float(row.get("2着率") or 0)
                    blended_r2    += r2 * w_k
                    total_weight  += w_k
                except (ValueError, TypeError):
                    pass
            if total_weight > 0:
                blended_rates[c_str] = blended_r2 / total_weight

        if not blended_rates:
            return _POSITION_REMAIN_FALLBACK.get(first_w, {})

        avg_rate = sum(blended_rates.values()) / max(len(blended_rates), 1)
        if avg_rate < 0.001:
            return _POSITION_REMAIN_FALLBACK.get(first_w, {})

        result = {}
        for wk, rate in blended_rates.items():
            coef = rate / avg_rate
            result[wk] = max(0.5, min(2.0, coef))
        return result

    # 全軸艇の残存補正テーブルを事前構築
    POSITION_REMAIN_BASE = {}
    for _fw in [str(i) for i in range(1, 7)]:
        POSITION_REMAIN_BASE[_fw] = _build_pos_remain_from_master(_fw)

    # 各艇の仕掛け積極性スコアを事前計算（動的補正用）
    # active_score = P_attempt × P_survive（仕掛けて生き残れる確率）
    _r1_for_ap = next((r for r in results if r["waku"] == "1"), None)
    _active_scores = {}
    if HONMEI_SCENARIO_AVAILABLE and _r1_for_ap:
        try:
            from honmei_scenario import calc_attack_probability as _cap
            for _r in results:
                if _r["waku"] == "1":
                    _active_scores["1"] = 0.5   # 1号艇自身は逃げなので中立
                else:
                    _ap = _cap(_r, _r1_for_ap, results)
                    _active_scores[_r["waku"]] = _ap["attempt_prob"] * _ap["survive_prob"]
        except Exception:
            pass

    def _get_pos_remain(first_w, second_w):
        """POSITION_REMAIN_BASE × active_score補正で動的残存補正係数を返す"""
        base = POSITION_REMAIN_BASE.get(first_w, {}).get(second_w, 1.0)
        if first_w == "1":
            return base   # 逃げ時は circle_pct で別途判断
        # active_score: 0.5未満でも0.5を下限（完全に来ない艇は除外されるが補正は緩く）
        active = _active_scores.get(second_w, 0.5)
        active_adj = max(0.5, min(1.2, active * 1.5 + 0.25))
        return base * active_adj

    POSITION_REMAIN = POSITION_REMAIN_BASE   # 後方互換 (circle_pct処理で直接参照する箇所用)

    def _calc_himo_score(first_w, second_w, third_w, combo_prob):
        """
        1着軸が決まったときの 2着・3着組み合わせの総合スコアを算出。

        【スコア構成】
          (1) combo確率ベース     (35%): シナリオ計算済みの3連単確率
          (2) 位置残存補正        (25%): 内側残存の物理補正（対話ログ合意版）
              差し1着   → 1号艇内残存×1.35、3号艇競合×0.75
              まくり1着 → 内側艇↑（×1.05〜1.25）、外側艇↓（×0.75〜0.95）
              1号艇1着  → circle_pct（イン逃げ時2着優位度）で補正
          (3) 個人能力            (25%): コース別3連対率 × ST能力 × 機力 × 自在性
          (4) jizen展開・相性     (15%): 2着艇の相性評価 × 3着艇の展開評価
        """
        # ── (1) combo確率（S1シナリオとは別物。3連単の確率値） ─────────────
        combo_prob_val = combo_prob

        # ── (2) 位置残存補正 ───────────────────────────────────────────────
        # 1号艇1着のときは circle_pct（イン逃げ時2着優位度）を使う
        # 【補正: 2026-04-05】イン逃げ局面では pos_score（circle_pct）が
        #   最も的中率に直結する指標であることをバックテストで確認。
        #   circle_pct の正規化スケールを 0.5〜1.0 → 0.4〜1.0 に拡張して
        #   内外枠の差別化を強化する（2・3枠を正しく上位評価）。
        if first_w == "1":
            circ2 = _circ_map.get(second_w, 50) / 100.0
            circ3 = _circ_map.get(third_w, 50) / 100.0
            # 【変更】スケール範囲を 0.5〜1.0 → 0.40〜1.0 に拡大（差別化強化）
            pos2  = 0.40 + circ2 * 0.60   # 旧: 0.5 + circ2 * 0.5
            pos3  = 0.40 + circ3 * 0.60   # 旧: 0.5 + circ3 * 0.5
        else:
            # 動的残存補正: 物理的内側残存 × 仕掛け積極性
            pos2 = _get_pos_remain(first_w, second_w)
            pos3 = _get_pos_remain(first_w, third_w)
        pos_score = (pos2 + pos3) / 2.0

        # ── (3) 個人能力スコア ─────────────────────────────────────────────
        def _personal(w):
            """
            【v6.3強化版】2着・3着候補の個人能力を多面的に評価。

            構成要素（重み合計 = 1.0）:
              コース別3連対率  (0.30): 場の論理に即した実績
              STスコア         (0.18): このレースでの発艇優位
              機力スコア       (0.12): モーター2連率の相対評価
              フォーム指数     (0.10): 直近調子の総合指標
              直近3走1着率     (0.08): 超短期フォーム
              直近5走1着率     (0.05): 短期フォーム
              自在性加重1着率  (0.07): 外枠攻め実力（S2〜S4で重要）
              ST標準偏差(逆)   (0.025): STばらつき小=安定 【v6.3: 0.04→0.025に調整】
              STレンジ(逆)     (0.015): 最速〜最遅レンジ小=コース内安定 【v6.3新追加】
              一般戦1着率      (0.03): 格付け補正
              直近10走平均着順 (0.03): 中期トレンド
            """
            # コース別3連対率（0〜1）
            w3 = _win3_map.get(w, 0.0)

            # STスコア: 速い艇ほど高い（艇間相対、0〜1）
            st_self = _st_map.get(w)
            all_sts = [v for v in _st_map.values() if v is not None]
            if st_self is not None and len(all_sts) >= 2:
                st_min, st_max = min(all_sts), max(all_sts)
                st_score = 1.0 - (st_self - st_min) / max(st_max - st_min, 0.001)
            else:
                st_score = 0.5

            # 機力スコア（艇間相対、0〜1）
            valid_motors = [v for v in _motor_map.values() if v is not None]
            mv = _motor_map.get(w)
            if mv is not None and len(valid_motors) >= 2:
                m_min, m_max = min(valid_motors), max(valid_motors)
                motor_score = (mv - m_min) / max(m_max - m_min, 0.001)
            else:
                motor_score = 0.5

            # フォーム指数（中央値3.0基準、0〜1にスケール）
            form = _sg_form_map.get(w)
            form_score = 0.5
            if form is not None:
                form_score = max(0.0, min(1.0, form / 6.0))  # 0〜6+で0〜1+

            # 直近3走1着率（全国平均0.17基準、0〜1）
            r3 = _sg_recent3_map.get(w)
            r3_score = 0.5
            if r3 is not None:
                r3_score = max(0.0, min(1.0, r3 / 0.34))   # 0.34(2倍平均)で1.0

            # 直近5走1着率
            r5 = _sg_recent5_map.get(w)
            r5_score = 0.5
            if r5 is not None:
                r5_score = max(0.0, min(1.0, r5 / 0.34))

            # 自在性加重1着率（外枠攻め実力、全国平均0.06基準）
            jizai = _sg_jizai_map.get(w)
            jizai_score = 0.5
            if jizai is not None:
                jizai_score = max(0.0, min(1.0, jizai / 0.12))  # 0.12(2倍平均)で1.0

            # ST標準偏差逆スコア（小さいほど高スコア）
            # ★STフラグ = サンプル10未満 → ST値が不安定なためスキップ（0.5=中立を維持）
            _sg_st_unreliable = _sg_star_st_map.get(w, False)
            st_std = _sg_st_std_map.get(w)
            st_std_score = 0.5
            if st_std is not None and not _sg_st_unreliable:
                # 0.044〜0.143の範囲: 0.044→1.0、0.143→0.0
                st_std_score = max(0.0, min(1.0, 1.0 - (st_std - 0.044) / 0.099))

            # ── 【v6.3新追加 / v6.4★STガード追加】STレンジ逆スコア ─────────
            # _sg_st_range_map は _suggest_3rentan スコープで構築済み
            st_range = _sg_st_range_map.get(w)
            st_range_score = 0.5
            if st_range is not None and _sg_st_range_mean > 0 and not _sg_st_unreliable:
                # レンジが平均より小さいほど1.0に近づく（最大1.0、最小0.0）
                st_range_score = max(0.0, min(1.0,
                    0.5 + (_sg_st_range_mean - st_range) / (2.0 * _sg_st_range_mean)
                ))

            # 一般戦1着率（全国平均0.17基準）
            ippan = _sg_ippan_map.get(w)
            ippan_score = 0.5
            if ippan is not None:
                ippan_score = max(0.0, min(1.0, ippan / 0.34))

            # 直近10走平均着順（3.5基準、2.0→1.0、5.0→0.0）
            r10 = _sg_recent10_map.get(w)
            r10_score = 0.5
            if r10 is not None:
                r10_score = max(0.0, min(1.0, (5.0 - r10) / 3.0))

            return (w3              * 0.30
                  + st_score        * 0.18
                  + motor_score     * 0.12
                  + form_score      * 0.10
                  + r3_score        * 0.08
                  + jizai_score     * 0.07
                  + r5_score        * 0.05
                  + st_std_score    * 0.025   # v6.3: 0.04→0.025（STレンジと合計0.04を分担）
                  + st_range_score  * 0.015   # v6.3新追加
                  + ippan_score     * 0.03
                  + r10_score       * 0.03)

        personal2 = _personal(second_w)
        personal3 = _personal(third_w)
        personal_score = (personal2 + personal3) / 2.0

        # ── (4) jizen展開・相性スコア ──────────────────────────────────────
        sym4 = {"◎": 1.0, "○": 0.75, "△": 0.40, "": 0.25}

        # 2着艇の相性（1号艇に対する攻め適性）
        aisho2  = sym4.get(_jizen_aisho.get(second_w, ""), 0.25)
        # 3着艇の展開（外枠での展開形成力）
        tenkai3 = sym4.get(_jizen_tenkai.get(third_w, ""), 0.25)
        jizen_score = (aisho2 + tenkai3) / 2.0

        # ── (5) 課題1修正: (2)主役候補のplace2/3_candidatesボーナス ────────────
        # _judge_main_playerが「このメンバー構成でこの展開なら2・3着に来やすい」
        # と判断した艇番リストに一致するコンボを加点する。
        # 加点幅: 2着一致=+0.08 / 3着一致=+0.05（合成比率の範囲内に収まるよう設計）
        _mp_data      = race_judgment.get("main_player", {}) or {}
        _p2_wakus     = {w for w, _ in (_mp_data.get("place2_candidates") or [])}
        _p3_wakus     = {w for w, _ in (_mp_data.get("place3_candidates") or [])}
        _p2_bonus     = 0.08 if second_w in _p2_wakus else 0.0
        _p3_bonus     = 0.05 if third_w  in _p3_wakus else 0.0
        main_cand_bonus = _p2_bonus + _p3_bonus   # 最大 0.13

        # ── 合成（イン逃げ局面: pos_score重みを0.25→0.32に増加）────────────
        # 【補正: 2026-04-05】バックテスト(1196R)で circle_pct（pos_score）が
        #   2着的中率に最も相関する指標と確認。
        #   イン逃げ局面（first_w=="1"）では pos_score の重みを増やし、
        #   combo確率・personal_score の重みを減らして整合させる。
        #   非逃げ局面（first_w!="1"）は旧重みを維持する。
        if first_w == "1":
            # イン逃げ時: circle_pctベースのpos_scoreを重視
            score = min(1.0,
                   combo_prob_val * 0.28   # 旧: 0.35（削減）
                   + pos_score        * 0.32   # 旧: 0.25（増加: circle_pctを重視）
                   + personal_score   * 0.25   # 変更なし
                   + jizen_score      * 0.15   # 変更なし
                   + main_cand_bonus)
        else:
            # 非逃げ時: 旧重み維持
            score = min(1.0,
                   combo_prob_val * 0.35
                   + pos_score        * 0.25
                   + personal_score   * 0.25
                   + jizen_score      * 0.15
                   + main_cand_bonus)

        return score

    def _build_buys(base_first_waku, orkaeshi_first=None, max_bets=None):
        source = [c for c in combos if c["first"] == base_first_waku]
        if not source:
            return [], set()

        scored = []
        for c in source:
            hs = _calc_himo_score(c["first"], c["second"], c["third"], c["prob"])
            scored.append((c, hs))
        scored.sort(key=lambda x: x[1], reverse=True)
        total_hs = sum(hs for _, hs in scored) or 1.0
        scored_with_share = [(c, hs, hs / total_hs) for c, hs in scored]

        _limit = max_bets if max_bets is not None else base_max
        selected  = []
        combo_set = set()
        cum_share = 0.0

        for c, hs, share in scored_with_share:
            key = c["combo"]
            if key not in combo_set:
                selected.append(c)
                combo_set.add(key)
                cum_share += share
            if orkaeshi_first is not None:
                rev_key = f"{c['second']}-{orkaeshi_first}-{c['third']}"
                if rev_key not in combo_set and _needs_orkaeshi_12(c["combo"], rev_key):
                    rev = dict(combo_lookup[rev_key])
                    rev["_orkaeshi"] = True
                    combo_set.add(rev_key)
                    selected.append(rev)
                    rev_hs = _calc_himo_score(rev["first"], rev["second"], rev["third"], rev["prob"])
                    cum_share += rev_hs / total_hs
            if len(selected) >= MIN_BETS and cum_share >= CUMULATIVE_THRESHOLD:
                break
            if len(selected) >= _limit:
                break
        return selected, combo_set

    def _trim_to_max(entries, max_n):
        return sorted(entries, key=lambda x: x["prob"], reverse=True)[:max_n]

    buy_entries = []
    seen_combos = set()

    # ====================================================================
    # パターン別 買い目生成（考察→買い目 フル連動）
    # ====================================================================
    if tenkai_pattern == "A":
        # A: 鉄板逃げ ── 1号頭のみ
        entries, _ = _build_buys("1", orkaeshi_first="1", max_bets=base_max)
        buy_entries = entries
        # 2着3着折り返し（逃げ軸専用）
        orkaeshi_23_set = set()
        for e in list(buy_entries):
            if e["first"] != "1":
                continue
            rev_key  = f"1-{e['third']}-{e['second']}"
            pair_key = tuple(sorted([e["combo"], rev_key]))
            if pair_key in orkaeshi_23_set:
                continue
            orkaeshi_23_set.add(pair_key)
            if not any(x["combo"] == rev_key for x in buy_entries) and _needs_orkaeshi_23(e["combo"], rev_key):
                rev = dict(combo_lookup[rev_key])
                rev["_orkaeshi_23"] = True
                buy_entries.append(rev)

    elif tenkai_pattern == "C":
        # C: 拮抗 ── 1号頭50% + 飛び頭50%（◎＋○に分割）
        s1_entries,  s1_seen  = _build_buys("1", orkaeshi_first="1", max_bets=_w1_slots)
        fly_entries, fly_seen = (
            _build_buys(main_fly_waku, orkaeshi_first=main_fly_waku, max_bets=_main_fly_slots)
            if main_fly_waku else ([], set())
        )
        taiko_entries, taiko_seen = (
            _build_buys(taiko_waku, orkaeshi_first=None, max_bets=_taiko_fly_slots)
            if _has_taiko else ([], set())
        )
        all_raw = (
            s1_entries
            + [e for e in fly_entries    if e["combo"] not in s1_seen]
            + [e for e in taiko_entries  if e["combo"] not in s1_seen and e["combo"] not in fly_seen]
        )
        all_raw.sort(key=lambda x: x["prob"], reverse=True)
        for e in all_raw:
            if e["combo"] not in seen_combos:
                buy_entries.append(e)
                seen_combos.add(e["combo"])

    else:
        # B/D: 主役/荒れ ── 飛び頭主体（◎＋○） + 1号頭最低保証
        fly_entries, fly_seen = (
            _build_buys(main_fly_waku, orkaeshi_first=main_fly_waku, max_bets=_main_fly_slots)
            if main_fly_waku else ([], set())
        )
        taiko_entries, taiko_seen = (
            _build_buys(taiko_waku, orkaeshi_first=None, max_bets=_taiko_fly_slots)
            if _has_taiko else ([], set())
        )
        s1_entries, s1_seen = _build_buys("1", orkaeshi_first="1", max_bets=_w1_slots)
        all_raw = (
            fly_entries
            + [e for e in taiko_entries if e["combo"] not in fly_seen]
            + [e for e in s1_entries    if e["combo"] not in fly_seen
                                          and e["combo"] not in taiko_seen]
        )
        all_raw.sort(key=lambda x: x["prob"], reverse=True)
        for e in all_raw:
            if e["combo"] not in seen_combos:
                buy_entries.append(e)
                seen_combos.add(e["combo"])

    # ── base_max 打ち切り（1号頭 _w1_slots 点を保証してから打ち切る）────────
    if len(buy_entries) > base_max:
        w1_in  = [e for e in buy_entries if e["first"] == "1"]
        non_w1 = [e for e in buy_entries if e["first"] != "1"]
        _keep_w1 = min(len(w1_in), _w1_slots if tenkai_pattern != "A" else base_max)
        kept_w1  = sorted(w1_in,  key=lambda x: x["prob"], reverse=True)[:_keep_w1]
        kept_fly = sorted(non_w1, key=lambda x: x["prob"], reverse=True)[:base_max - _keep_w1]
        buy_entries = kept_w1 + kept_fly
        seen_combos = {e["combo"] for e in buy_entries}

    # ── (5) SC1着按分を escape_fallback で補正 ────────────────────────────────────
    _fb_prob = float(_ef.get("fallback_prob", 0.5) or 0.5)
    _fb_type = _ef.get("fly_type", "不明")
    _rel_map_for_sc = {w: p for w, p in first_prob_map.items()}
    _sc_info2 = _calc_sc_weight(
        results, _cm_map, _win3_map, _rel_map_for_sc, jizen_eval=jizen_eval
    )
    _sc_1st_weights = dict(_sc_info2["sc_1st_weights"])
    if _fb_type == "まくり系":
        _corrected_w1 = max(0.35, min(0.95, 0.35 + _fb_prob * 0.60))
    elif _fb_type == "差し系":
        _corrected_w1 = max(0.10, min(0.50, 0.10 + _fb_prob * 0.40))
    else:
        _corrected_w1 = _sc_1st_weights.get("1", 0.50)
    _old_w1 = _sc_1st_weights.get("1", 0.50)
    _delta  = _corrected_w1 - _old_w1
    _sc_1st_weights["1"] = _corrected_w1
    if sub_fly_waku and sub_fly_waku in _sc_1st_weights:
        _sc_1st_weights[sub_fly_waku] = max(0.05, _sc_1st_weights[sub_fly_waku] - _delta)

    # ── SCシナリオ（潰れ展開）漁夫候補を補完 ─────────────────────────────
    if add_sc_bets and collapse_bene:
        top_bene_w = collapse_bene[0][0]
        sc_additions = sorted(
            [c for c in combos
             if c["third"] == top_bene_w and c["combo"] not in seen_combos],
            key=lambda x: x["prob"], reverse=True
        )[:SC_SLOTS]
        for c in sc_additions:
            c = dict(c); c["_sc_bet"] = True
            buy_entries.append(c); seen_combos.add(c["combo"])

    # ── (3) 逃げ残存フォロー ────────────────────────────────────────────────
    _fallback_limit = 0
    if tenkai_pattern == "B" and _fb_rank == "高":
        _fallback_limit = 2
    elif tenkai_pattern == "C" and _fb_rank == "高":
        _fallback_limit = 1
    if _fallback_limit > 0:
        _main_w = _mp.get("main_waku")
        if _main_w and _main_w != "1":
            for c in sorted(
                [c for c in combos
                 if c["first"] == _main_w and c["second"] == "1"
                 and c["combo"] not in seen_combos],
                key=lambda x: x["prob"], reverse=True
            )[:_fallback_limit]:
                c = dict(c); c["_fallback_bet"] = True
                buy_entries.append(c); seen_combos.add(c["combo"])

    # ── (4) ダークホース3着挿入 ─────────────────────────────────────────────
    _venue_c1    = float(race_judgment.get("venue_c1_win_rate") or 0.555)
    _venue_ratio = max(0.70, min(1.30, _venue_c1 / 0.555))
    _dh_thresh   = round({"D": 0.15, "B": 0.20}.get(tenkai_pattern, 0.20) * _venue_ratio, 3)
    if _dh_ok and tenkai_pattern in ("B", "D"):
        _dh_top_w = _dh.get("top_waku")
        _dh_score = float(_dh.get("top_score", 0) or 0)
        if _dh_top_w and _dh_score >= _dh_thresh:
            for c in sorted(
                [c for c in combos
                 if c["third"] == _dh_top_w and c["combo"] not in seen_combos],
                key=lambda x: x["prob"], reverse=True
            )[:2]:
                c = dict(c); c["_dh_bet"] = True
                buy_entries.append(c); seen_combos.add(c["combo"])
            for _rank_i, (_dh_w, _dh_s, _dh_tag) in enumerate(_dh_cands_all[1:3], start=2):
                if _dh_s < _dh_thresh * (1.0 + _rank_i * 0.25):
                    continue
                for c in sorted(
                    [c for c in combos
                     if c["third"] == _dh_w and c["combo"] not in seen_combos],
                    key=lambda x: x["prob"], reverse=True
                )[:1]:
                    c = dict(c); c["_dh_bet"] = True
                    buy_entries.append(c); seen_combos.add(c["combo"])

    # ── 最終上限チェック ──────────────────────────────────────────────────
    if len(buy_entries) > MAX_BETS:
        buy_entries = _trim_to_max(buy_entries, MAX_BETS)

    # ── 飛び狙い判定時の1号頭フィルタ ────────────────────────────────────
    # v8.0修正: s1_prob >= 0.55 の場合は確率モデルが逃げを支持しているため
    # 定性スコア由来の「飛び狙い」判定で1号頭を消してはいけない
    # （escape_score は race_judgment["score"] 由来でs1_probと別軸のため矛盾が生じやすい）
    if _ryotate_verdict == "飛び狙い" and tenkai_pattern in ("B", "D") and s1_prob < 0.55:
        non_w1 = [e for e in buy_entries if e["first"] != "1"]
        if len(non_w1) >= MIN_BETS:
            buy_entries = non_w1

    # 艇番若い順ソート
    buy_entries.sort(key=lambda e: (int(e["first"]), int(e["second"]), int(e["third"])))
    buy_list    = [e["combo"] for e in buy_entries]
    point_count = len(buy_list)

    # ======================================================================
    # Step D: 理論合成オッズ・余裕度・期待値警告
    # ======================================================================
    # 【設計思想】
    # 点数で削らない。合成オッズが基準を下回った場合は「警告」として表示し、
    # 判断はユーザーに委ねる。
    #   → 回収重視ユーザー: 警告を見て見送り
    #   → 的中重視ユーザー: 警告を無視して参考買い目を使う
    #
    # 期待値基準:
    #   quality S/A → 3.0倍未満で警告
    #   quality B/C/D → 2.5倍未満で警告
    # ======================================================================
    total_prob        = sum(e["prob"] for e in buy_entries)
    theory_syn_odds   = round(0.75 / total_prob, 1) if total_prob > 0 else None
    required_syn_odds = round(point_count * 1.10, 1) if point_count > 0 else None

    # 期待値警告フラグ
    # 胴元控除25%を考慮したブレークイーブンは1.33倍。
    # 実用的な下限を2.0倍とし、それを下回る場合のみ警告する。
    # （旧設定のS/A=3.0倍、B以下=2.5倍は厳しすぎて正常なレースにも警告が出ていた）
    EV_THRESHOLD = 2.0
    ev_warning = (theory_syn_odds is not None and theory_syn_odds < EV_THRESHOLD)
    ev_warning_msg = (
        f"[!] 理想合成オッズ{theory_syn_odds}倍（期待値基準{EV_THRESHOLD}倍を下回っています）\n"
        f"  → 回収重視なら見送り推奨 / 的中重視なら参考買い目を使用可"
    ) if ev_warning else ""

    if theory_syn_odds and required_syn_odds and required_syn_odds > 0:
        margin_ratio = round(theory_syn_odds / required_syn_odds, 2)
        if margin_ratio >= 2.0:
            margin_verdict = "余裕あり（実オッズが理論値の半分でも成立）"
        elif margin_ratio >= 1.2:
            margin_verdict = "要確認（実オッズで判断）"
        else:
            margin_verdict = "見送り有力（理論値に余裕なし）"
    else:
        margin_ratio   = None
        margin_verdict = "-"

    # ======================================================================
    # ======================================================================
    # Step E: コメント・候補リスト生成
    # 引き継ぎ書 第10章フォーマットに準拠した考察テキストを生成する
    # ======================================================================

    # ── Step1: 逃げ判定テキスト ────────────────────────────────────────────
    _w1_escape_d   = (race_judgment or {}).get("w1_escape", {}) or {}
    _escape_rank   = _w1_escape_d.get("escape_rank", "中")
    _venue_c1_pct  = float((race_judgment or {}).get("venue_c1_win_rate") or 0.555) * 100
    _r1            = next((r for r in results if r["waku"] == "1"), None)
    _r1_cm         = (_r1 or {}).get("raw_cm", {}) or {}
    _indiv_nige_r  = safe_float(_r1_cm.get("逃げ%")) or 0.0
    if _indiv_nige_r > 1.5:
        _indiv_nige_r /= 100.0
    _indiv_nige_pct = _indiv_nige_r * 100
    _r1_1st_pct     = s1_prob * 100
    _nige_mark      = (_r1 or {}).get("nige_mark", "") or ""
    # 記号なし（空白）のとき引き継ぎ書定義の「空白」として扱う
    _nige_mark_disp = _nige_mark if _nige_mark else "（記号なし）"

    # 逃げ判定ロジック（引き継ぎ書 Step1 4-3に準拠）
    if _nige_mark in ("逃◎", "逃○") and s1_prob >= (_venue_c1_pct / 100) and s1_prob >= 0.50:
        _nige_verdict = "逃げ確定"
    elif _nige_mark == "逃△":
        _nige_verdict = "逃げ否定"
    elif not _nige_mark and _indiv_nige_r < (_venue_c1_pct / 100) - 0.20:
        _nige_verdict = "逃げ否定（記号なし・個人が場平均を大幅下回る）"
    else:
        _nige_verdict = "要総合判断"

    _step1_line = (
        f"逃げ判定: {_nige_mark_disp} /"
        f" 場平均{_venue_c1_pct:.0f}% /"
        f" 個人{_indiv_nige_pct:.0f}% /"
        f" 1着率{_r1_1st_pct:.0f}%"
        f" → {_nige_verdict}"
    )

    # ── Step2: 本命選定テキスト ───────────────────────────────────────────
    _honmei_waku_disp = honmei_waku if honmei_waku else "-"
    if honmei_waku == "1":
        _honmei_reason = "逃げ確定のため1号艇を本命"
    else:
        # 攻め評価・相性・機力・ST安定から根拠を収集
        _hm_r    = next((r for r in results if r["waku"] == honmei_waku), None)
        _hm_mark = (_hm_r or {}).get("honmei", "") if _hm_r else ""
        _hm_eff  = _atk_eff_map.get(honmei_waku, 0.0)
        _hm_reasons = []
        if _hm_mark in ("◎", "○"):
            _hm_reasons.append(f"攻め{_hm_mark}")
        if _hm_eff >= 0.22:
            _hm_reasons.append(f"攻撃有効性{_hm_eff*100:.0f}%")
        _hm_atk_type = _atk_type_map.get(honmei_waku, "-")
        if _hm_atk_type != "-":
            _hm_reasons.append(_hm_atk_type)
        _honmei_reason = " / ".join(_hm_reasons) if _hm_reasons else "確率最上位艇"

    _step2_line = f"本命: {_honmei_waku_disp}号艇（{_honmei_reason}）"

    # ── Step3: 決まり手分岐テキスト ──────────────────────────────────────
    _mc_method  = main_conflict.get("method", "-") if main_conflict else "-"
    _mc_pct     = main_conflict.get("pct", 0) if main_conflict else 0
    _sc_method  = sub_conflict.get("method", "-") if sub_conflict else None
    _sc_pct     = sub_conflict.get("pct", 0) if sub_conflict else 0
    if _sc_method and _sc_pct:
        _step3_line = (
            f"決まり手: {_mc_method}({_mc_pct:.0f}%) /"
            f" {_sc_method}({_sc_pct:.0f}%)"
        )
    elif _mc_method != "-":
        _step3_line = f"決まり手: {_mc_method}({_mc_pct:.0f}%)"
    else:
        _step3_line = "決まり手: データなし"

    # ── Step4: 2・3着候補テキスト ─────────────────────────────────────────
    # 本命の決まり手に基づく残存候補（引き継ぎ書Step4）
    _himo_top_wakus = []
    _himo_top_reason = ""
    if honmei_waku == "1":
        # 逃げ本命 → 逃げ決着時2着率（neraime_2nd）から上位を採用
        if _neraime_2nd:
            _himo_top_wakus = [h["waku"] for h in sorted(
                _neraime_2nd, key=lambda x: x["blend"], reverse=True
            )[:3]]
            _himo_top_reason = "逃げ決着時2着残存マスタ"
        elif _neraime_list:
            _himo_top_wakus = [h["waku"] for h in _neraime_list[:3]]
            _himo_top_reason = "攻撃有効性スコア"
    else:
        # 飛び本命 → 決まり手分岐ごとの残存艇
        _cand_wakus = [w for w, _ in fly_candidates_sorted if w != honmei_waku]
        _himo_top_wakus = _cand_wakus[:3]
        _himo_top_reason = f"{_mc_method}展開残存候補"

    _step4_line = (
        f"2・3着候補: {'・'.join([f'{w}号' for w in _himo_top_wakus]) or '-'}"
        f"（{_himo_top_reason}）"
    )

    # ── Step5: 3着絞り込みテキスト ───────────────────────────────────────
    # 3着指数（circle_pct or 確率）が最低値から20以上離れた艇を切る
    _san_scores = {}
    for _r in results:
        _w = _r["waku"]
        _cp = _r.get("circle_pct") or first_prob_map.get(_w, 0) * 100
        _san_scores[_w] = float(_cp or 0)
    if _san_scores:
        _san_min_waku = min(_san_scores, key=_san_scores.get)
        _san_min_val  = _san_scores[_san_min_waku]
        _san_second   = sorted(_san_scores.values())[1] if len(_san_scores) >= 2 else _san_min_val
        _san_cut = (
            f"{_san_min_waku}号艇切り（指数{_san_min_val:.0f}）"
            if (_san_second - _san_min_val) >= 20
            else "全艇競合（絞り込みなし）"
        )
    else:
        _san_cut = "データなし"

    _step5_line = f"3着絞り込み: {_san_cut}"

    # ── Step6: 押さえ選定テキスト ─────────────────────────────────────────
    # 攻め◎ かつ 機力B以上 → 本命崩れ時の頭候補
    _osaie_wakus = []
    for _r in results:
        _w = _r["waku"]
        if _w == honmei_waku or _w == "1":
            continue
        _mark = _r.get("honmei", "")
        _motor = safe_float(_r.get("motor2") or _r.get("motor_2rate"))
        # 攻め◎ かつ モーター2連対率が場平均以上（B以上の目安として相対判定）
        _all_motors = [
            safe_float(r.get("motor2") or r.get("motor_2rate")) or 0
            for r in results
        ]
        _motor_avg = sum(_all_motors) / max(len(_all_motors), 1)
        if _mark == "◎" and _motor is not None and _motor >= _motor_avg:
            _osaie_wakus.append((_w, _motor))

    if _osaie_wakus:
        _osaie_str = " / ".join(
            f"{w}号艇（攻め◎・機力{m:.0f}%）" for w, m in _osaie_wakus
        )
        _step6_line = f"押さえ: {_osaie_str}"
    else:
        _step6_line = "押さえ: なし（攻め◎×機力B以上の艇なし）"

    # ── 最終コメント組み立て（新フォーマット）────────────────────────────────
    # 【考察】
    #   本命: ●号艇
    #   対抗: ●号艇（本命が1艇1本でいけないときのみ）
    #   選定理由: 本命が1号艇→逃げ率総合 / 2〜6号艇→決まり手説明
    # 【参考買い目】
    #   本線: ...
    #   押さえ: ...
    # ─────────────────────────────────────────────────────────────────────────

    # ── 本命・対抗 ──────────────────────────────────────────────────────────
    _honmei_line = f"本命：{_honmei_waku_disp}号艇"

    # 対抗: taiko_waku が存在し本命と異なる場合のみ出力
    _taiko_waku_disp = taiko_waku if (taiko_waku and taiko_waku != honmei_waku) else None
    _taiko_line = f"対抗：{_taiko_waku_disp}号艇" if _taiko_waku_disp else ""

    # ── 選定理由 ────────────────────────────────────────────────────────────
    # 本命が1号艇 → 「なぜ逃げが決まるか」を数値で総合説明＋ヒモ選定根拠
    # 本命が2〜6号艇 → 「なぜ1号を切ったか」＋「なぜこの艇か」を数値で説明

    # ── 共通: モーター・ST情報を各艇から取得するヘルパー ────────────────────
    def _motor_str(waku):
        """機力評価記号（jizen_eval）と2連対率を返す"""
        kiry = _jizen_kiryoku.get(waku, "")
        m    = _motor_map.get(waku)
        if kiry and m is not None:
            return f"機力{kiry}（{m:.0f}%）"
        elif kiry:
            return f"機力{kiry}"
        elif m is not None:
            return f"機力{m:.0f}%"
        return None

    def _st_str(waku):
        """avg_stをST順位付きで返す（速いほど良い）"""
        st = _st_map.get(waku)
        if st is None:
            return None
        all_st = [(w, v) for w, v in _st_map.items() if v is not None]
        rank   = sorted(all_st, key=lambda x: x[1]).index((waku, st)) + 1
        return f"ST平均{st:.2f}秒（{len(all_st)}艇中{rank}位）"

    def _jizen_str(waku):
        """jizen評価記号を返す（相性・展開・自在性）"""
        parts = []
        a = _jizen_aisho.get(waku, "")
        t = _jizen_tenkai.get(waku, "")
        j = _jizen_jizai.get(waku, "")
        if a: parts.append(f"相性{a}")
        if t: parts.append(f"展開{t}")
        if j: parts.append(f"自在{j}")
        return "・".join(parts) if parts else None

    def _first_prob_str(waku):
        """1着率を返す"""
        p = first_prob_map.get(waku, 0.0)
        return f"1着率{p*100:.0f}%" if p > 0 else None

    if honmei_waku == "1":
        # ── 1号艇本命：逃げの根拠を多角的に説明 ────────────────────────────
        # 逃げ評価・場平均/個人逃げ率・1着率・モーター・STを使って
        # 「なぜ逃げが決まるか」を購読者が納得できる形で記述する

        # 逃げ根拠の要素を収集
        _r1_motor = _motor_str("1")
        _r1_st    = _st_str("1")
        _r1_jizen = _jizen_str("1")

        # 逃げ強度の判断文
        _nige_diff = _indiv_nige_pct - _venue_c1_pct
        if _nige_diff >= 10:
            _nige_diff_comment = f"個人逃げ率が場平均を{_nige_diff:.0f}pt上回り逃げ実績で上位"
        elif _nige_diff >= 0:
            _nige_diff_comment = f"個人逃げ率は場平均並み（差{_nige_diff:+.0f}pt）"
        else:
            _nige_diff_comment = f"個人逃げ率は場平均を{abs(_nige_diff):.0f}pt下回るが評価{_nige_mark_disp}で補完"

        _reason_parts = [
            f"逃げ評価{_nige_mark_disp}",
            f"場平均{_venue_c1_pct:.0f}%・個人{_indiv_nige_pct:.0f}%（{_nige_diff_comment}）",
            f"総合1着率{_r1_1st_pct:.0f}%→{_nige_verdict}",
        ]
        if _r1_motor: _reason_parts.append(_r1_motor)
        if _r1_st:    _reason_parts.append(_r1_st)
        if _r1_jizen: _reason_parts.append(_r1_jizen)

        _reason_body = "1号艇本命（逃げ軸）。" + "、".join(_reason_parts) + "。"

        # ヒモ選定根拠：_neraime_2nd 上位艇を説明
        if _neraime_2nd:
            _himo_sorted = sorted(_neraime_2nd, key=lambda x: x["blend"], reverse=True)[:3]
            _himo_lines  = []
            for _h in _himo_sorted:
                _hw   = _h["waku"]
                _hblend = _h["blend"]
                _h_atk  = _atk_type_map.get(_hw, "-")
                _h_eff  = _atk_eff_map.get(_hw, 0.0)
                _h_circ = _circ_map.get(_hw, 0)
                _h_motor= _motor_str(_hw)
                _h_detail_parts = [f"逃げ時2着残存スコア{_hblend:.2f}"]
                if _h_eff > 0:    _h_detail_parts.append(f"攻撃有効性{_h_eff*100:.0f}%[{_h_atk}]")
                if _h_circ > 0:   _h_detail_parts.append(f"イン逃げ時2着優位度{_h_circ:.0f}")
                if _h_motor:      _h_detail_parts.append(_h_motor)
                _himo_lines.append(f"{_hw}号艇（{'・'.join(_h_detail_parts)}）")
            _reason_body += "\nヒモ候補：" + "、".join(_himo_lines) + "。"

        # 対抗の説明
        if _taiko_waku_disp:
            _taiko_mc  = _atk_type_map.get(_taiko_waku_disp, "-")
            _taiko_eff = _atk_eff_map.get(_taiko_waku_disp, 0.0)
            _taiko_blend = next(
                (h["blend"] for h in _neraime_2nd if h["waku"] == _taiko_waku_disp), None
            ) if _neraime_2nd else None
            _taiko_blend_str = f"残存スコア{_taiko_blend:.2f}・" if _taiko_blend else ""
            _taiko_motor = _motor_str(_taiko_waku_disp)
            _taiko_extra = f"・{_taiko_motor}" if _taiko_motor else ""
            _reason_body += (
                "\n対抗" + str(_taiko_waku_disp) + "号艇："
                + _taiko_blend_str
                + f"決まり手[{_taiko_mc}]・攻撃有効性{_taiko_eff*100:.0f}%"
                + _taiko_extra + "。"
            )

    else:
        # ── 2〜6号艇本命：なぜ1号を切ったか＋なぜこの艇かを説明 ─────────────
        _honmei_r   = next((r for r in results if r["waku"] == honmei_waku), None)
        _honmei_mc  = _atk_type_map.get(honmei_waku, "-")
        _honmei_eff = _atk_eff_map.get(honmei_waku, 0.0)
        _honmei_mark = (_honmei_r or {}).get("honmei", "") if _honmei_r else ""
        _honmei_motor= _motor_str(honmei_waku)
        _honmei_st   = _st_str(honmei_waku)
        _honmei_jizen= _jizen_str(honmei_waku)
        _honmei_1st  = _first_prob_str(honmei_waku)

        # 1号艇を切る根拠
        _w1_1st_pct = first_prob_map.get("1", 0.0) * 100
        _cut_reason = (
            f"1号艇：逃げ評価{_nige_mark_disp}・個人逃げ率{_indiv_nige_pct:.0f}%"
            f"（場平均{_venue_c1_pct:.0f}%）・1着率{_w1_1st_pct:.0f}%→{_nige_verdict}のため本命外。"
        )

        # 本命艇の根拠を収集
        _hm_parts = [f"決まり手[{_honmei_mc}]・攻撃有効性{_honmei_eff*100:.0f}%"]
        if _honmei_mark in ("◎", "○"): _hm_parts.append(f"攻め{_honmei_mark}")
        if _honmei_1st:  _hm_parts.append(_honmei_1st)
        if _honmei_motor: _hm_parts.append(_honmei_motor)
        if _honmei_st:   _hm_parts.append(_honmei_st)
        if _honmei_jizen: _hm_parts.append(_honmei_jizen)

        _reason_body = (
            f"{honmei_waku}号艇本命（飛び軸）。"
            + _cut_reason
            + "\n" + str(honmei_waku) + "号艇選定根拠："
            + "・".join(_hm_parts) + "。"
        )

        # 対抗の説明
        if _taiko_waku_disp:
            _taiko_mc  = _atk_type_map.get(_taiko_waku_disp, "-")
            _taiko_eff = _atk_eff_map.get(_taiko_waku_disp, 0.0)
            _taiko_motor = _motor_str(_taiko_waku_disp)
            _taiko_1st   = _first_prob_str(_taiko_waku_disp)
            _taiko_extra_parts = [f"決まり手[{_taiko_mc}]・攻撃有効性{_taiko_eff*100:.0f}%"]
            if _taiko_1st:   _taiko_extra_parts.append(_taiko_1st)
            if _taiko_motor: _taiko_extra_parts.append(_taiko_motor)
            _reason_body += (
                "\n対抗" + str(_taiko_waku_disp) + "号艇："
                + "・".join(_taiko_extra_parts) + "。"
            )

    _reason_line = f"選定理由：{_reason_body}"

    # ── 買い目リスト（本線/押さえ） ─────────────────────────────────────────
    # osaie（押さえ）: _osaie_wakus が存在する艇が1着に含まれる買い目
    _osaie_waku_set = {w for w, _ in _osaie_wakus}

    _honsen_combos = [
        e["combo"] for e in buy_entries
        if e["first"] not in _osaie_waku_set
    ]
    _osaie_combos = [
        e["combo"] for e in buy_entries
        if e["first"] in _osaie_waku_set
    ]

    # buy_entriesにtierを付与（lr_excel.py の _honsen / _osaae フィルタ用）
    for e in buy_entries:
        e["tier"] = "押さえ" if e["first"] in _osaie_waku_set else "本線"

    _honsen_str = "　".join(_honsen_combos) if _honsen_combos else "（なし）"
    _osaie_str2 = "　".join(_osaie_combos) if _osaie_combos else "なし"

    # ── 警告サフィックス ─────────────────────────────────────────────────────
    _warn_parts = []
    if ryotate.get("consistency_warn"):
        _warn_parts.append("[!]スコア<->確率乖離補正済")
    if race_judgment.get("honmei_prob_mismatch", False):
        _mismatch_detail = race_judgment.get("honmei_prob_mismatch_detail", "")
        _warn_parts.append(f"[!]印<->確率不一致({_mismatch_detail})")
    warn_suffix = "\n" + " / ".join(_warn_parts) if _warn_parts else ""

    # ── comment 本文 ─────────────────────────────────────────────────────────
    _taiko_block = f"\n{_taiko_line}" if _taiko_line else ""
    comment = (
        f"【考察】\n"
        f"{_honmei_line}"
        f"{_taiko_block}\n"
        f"{_reason_line}\n"
        f"\n【参考買い目】\n"
        f"本線：{_honsen_str}\n"
        f"押さえ：{_osaie_str2}"
        f"{warn_suffix}"
    )

    def _scenario_label(e):
        f = e["first"]
        if e.get("_sc_bet"):
            return f"潰れ受益({f}号頭)"
        elif e.get("_fallback_bet"):
            return f"(3)逃げ残存({f}号頭-1号2着)"
        elif e.get("_dh_bet"):
            return f"(4)穴ヒモ({f}号頭)"
        elif e.get("_orkaeshi_23"):
            return f"2着3着折返({f}号頭)"
        elif f == "1":
            return "逃げ（1号艇頭）"
        elif f == main_fly_waku:
            return f"◎飛び（{f}号艇頭）"
        elif f == taiko_waku and _has_taiko:
            return f"○飛び（{f}号艇頭）"
        elif e.get("_orkaeshi"):
            return f"1着折返({f}号頭)"
        else:
            return f"その他（{f}号艇頭）"

    # ヒモスコアを買い目エントリに付与（candidatesで表示用）
    _himo_score_cache = {}
    for e in buy_entries:
        k = e["combo"]
        if k not in _himo_score_cache:
            _himo_score_cache[k] = _calc_himo_score(
                e["first"], e["second"], e["third"], e["prob"]
            )

    candidates = [
        {
            "combo":          e["combo"],
            "prob":           round(e["prob"], 5),
            "prob_pct":       round(e["prob"] * 100, 2),
            "himo_score":     round(_himo_score_cache.get(e["combo"], 0), 4),
            "scenario":       _scenario_label(e),
            "is_orkaeshi":    e.get("_orkaeshi", False),
            "is_orkaeshi_23": e.get("_orkaeshi_23", False),
            "is_sc_bet":      e.get("_sc_bet", False),
            "is_fallback_bet": e.get("_fallback_bet", False),
            "is_dh_bet":      e.get("_dh_bet", False),
            "reason":         _build_reason(e, scenario_type),
        }
        for e in buy_entries
    ]

    # ── 下流コードとの互換性維持 ──────────────────────────────────────────
    fly_axes = [w for w, _ in fly_candidates_sorted[:2]]

    from collections import Counter
    himo_counter = Counter()
    for c in combos[:30]:
        himo_counter[c["second"]] += 2
        himo_counter[c["third"]]  += 1
    axis_candidates = list(first_prob_map.keys())[:3]
    himo_candidates = [w for w, _ in himo_counter.most_common()
                       if w not in axis_candidates][:4]

    # race_judgmentへ分析結果を追記
    race_judgment["scenario_type"]   = scenario_type
    race_judgment["s1_prob"]         = round(s1_prob, 4)
    race_judgment["fly_prob"]        = round(fly_prob, 4)
    race_judgment["main_fly_waku"]   = main_fly_waku
    race_judgment["theory_syn_odds"] = theory_syn_odds
    race_judgment["margin_ratio"]    = margin_ratio
    race_judgment["margin_verdict"]  = margin_verdict
    race_judgment["ev_axes"]         = (
        ["1"] if scenario_type == "逃げ軸流し"
        else [main_fly_waku] if scenario_type == "飛び軸" and main_fly_waku
        else (["1", main_fly_waku] if main_fly_waku else ["1"])
    )
    race_judgment["w1_vs_venue"]     = round(
        (first_prob_map.get("1", 0) - (race_judgment.get("venue_c1_win_rate") or 0.555)) * 100, 1
    )
    race_judgment["w1_ev_pos_count"] = 0   # 互換維持（EV概念廃止）
    race_judgment["ev_axis_summary"] = [
        f"{w}号艇(1着確率{p*100:.1f}%)" for w, p in fly_candidates_sorted[:3]
    ]
    # SCシナリオ情報（数値シート表示用）
    _sc_combos_info = combos[0].get("sc_fly_type", None) if combos else None
    race_judgment["sc_fly_type"]    = _sc_combos_info or "-"
    race_judgment["sc_fly_waku"]    = main_fly_waku  # 飛び役兼潰れ役
    # 漁夫候補: 漁夫スコアが高い上位3艇（buy_listに含まれるもの優先）
    _sc_b = combos[0].get("sc_beneficiary") if combos else None
    if _sc_b is None:
        race_judgment["sc_gyofu_top3"] = []
    else:
        # combos全体からsc_beneficiaryを一度だけ取り出す（全艇共通値）
        # _calc_sc_weightの結果はcombo単位ではなく全艇共通なので最初のcomboから取得
        _all_b = {c["second"]: c.get("sc_beneficiary", 0) for c in combos[:30]}
        race_judgment["sc_gyofu_top3"] = sorted(
            _all_b.keys(), key=lambda w: _all_b.get(w, 0), reverse=True
        )[:3]

    h1 = "1" if scenario_type != "飛び軸" else (main_fly_waku or "1")
    h2 = main_fly_waku or "-"

    # ── honmei_scenario v2 統合 ──────────────────────────────────────────
    _base_result = {
        "axis1":             h1,
        "axis2":             h2,
        "buy_list":          buy_list,
        "point_count":       point_count,
        "comment":           comment,
        "combos":            combos,
        "candidates":        candidates,
        "scenario_type":     scenario_type,
        "scenario_verdict":  scenario_type,
        "s1_prob":           round(s1_prob, 4),
        "fly_prob":          round(fly_prob, 4),
        "theory_syn_odds":   theory_syn_odds,
        "required_syn_odds": required_syn_odds,
        "margin_ratio":      margin_ratio,
        "margin_verdict":    margin_verdict,
        "escape_score":      ryotate.get("escape_score", 50),
        "tobi_score":        ryotate.get("tobi_score", 30),
        "fly_axes":          fly_axes,
        "candidates_s1":     [],
        "candidates_s2":     [],
        "axis_candidates":   axis_candidates,
        "himo_candidates":   himo_candidates,
        "jizen_formation":   {},
        "ryotate_verdict":   ryotate_verdict,
        "ryotate_detail":    ryotate,
        "first_prob_map":    {w: round(p, 4) for w, p in first_prob_map.items()},
        # ── 狙い目（個人攻撃有効性ベース）──────────────────────────────
        "neraime":           _neraime_list,       # 攻め型狙い目候補リスト
        "neraime_2nd":       _neraime_2nd,        # 残存型2着狙い目（逃げ本命時）
        "neraime_top":       neraime_top,         # 最有力攻め型狙い目（1艇）
        "atk_eff_map":       {w: round(s, 4) for w, s in _atk_eff_map.items()},
        # 整合性フラグ（バックテスト除外・警告表示用）
        "consistency_warn":          ryotate.get("consistency_warn", False),
        "honmei_prob_mismatch":      race_judgment.get("honmei_prob_mismatch", False),
        "honmei_prob_mismatch_detail": race_judgment.get("honmei_prob_mismatch_detail", ""),
        # 期待値警告（合成オッズが基準を下回っている場合）
        "ev_warning":     ev_warning,
        "ev_warning_msg": ev_warning_msg,
        # (6) 展開4分類（A:鉄板逃げ / B:主役展開 / C:拮抗 / D:荒れ）
        "tenkai_pattern":        tenkai_pattern,
        "tenkai_pattern_policy": _tenkai_policy_text,  # D判定の_dh_ok別出し分けを反映
    }

    if HONMEI_SCENARIO_AVAILABLE and honmei_map:
        # 【v8.0】逃げ鉄板判定: s1_prob高 かつ tenkai_pattern=A の場合は
        # integrate_with_suggest_3rentan を呼ばず _base_result をそのまま使う。
        # honmei_scenario は印◎艇（2〜6号）を軸にするため、
        # 逃げ鉄板レースで呼ぶと1号頭の買い目が4号頭等に差し替えられる。
        _hs_s1p = _base_result.get("s1_prob", 0) or 0
        _hs_tp  = _base_result.get("tenkai_pattern", "")
        _skip_integrate = (_hs_s1p >= 0.60 and _hs_tp == "A")

        if _skip_integrate:
            # 逃げ鉄板: honmei_scenario を呼ばず確率モデルの結果を使用
            _result = _base_result
        else:
            # honmei_scenario.py は results[waku]["honmei"] を直接参照する。
            # v7.0で1号艇の honmei が「逃◎」になったため、
            # resultsのコピーで1号艇 honmei を変換してから渡す。
            _nige_conv = {"逃◎": "◎", "逃○": "○", "逃△": "△", "逃×": " "}
            _results_for_hs = []
            for _r in results:
                if str(_r.get("waku", "")) == "1":
                    _rc = dict(_r)
                    _rc["honmei"] = _nige_conv.get(_rc.get("honmei", " "), " ")
                    _results_for_hs.append(_rc)
                else:
                    _results_for_hs.append(_r)

            _result = integrate_with_suggest_3rentan(
                original_result = _base_result,
                results         = _results_for_hs,
                honmei_map      = honmei_map,
                combos          = combos,
                race_judgment   = race_judgment,
                jizen_eval      = jizen_eval,
                )
        # integrate_with_suggest_3rentan が theory_syn_odds を上書きするため
        # ev_warning を最終的な theory_syn_odds で再計算する
        _tso = _result.get("theory_syn_odds")
        _result["ev_warning"] = (_tso is not None and _tso < EV_THRESHOLD)
        _result["ev_warning_msg"] = (
            f"[!] 理想合成オッズ{_tso}倍（期待値基準{EV_THRESHOLD}倍を下回っています）\n"
            f"  → 回収重視なら見送り推奨 / 的中重視なら参考買い目を使用可"
        ) if _result["ev_warning"] else ""
    else:
        _result = _base_result

    # ── 参加グレードを付与 ──
    _venue   = (race_judgment or {}).get("venue", "")
    _result["entry_grade"] = _get_entry_grade(
        venue           = _venue,
        scenario_type   = _result.get("scenario_type", ""),
        honmei_scenario = _result.get("honmei_scenario"),
    )

    # ── 【(9)追加】ケリー基準による最適賭け比率を付与 ──
    # buy_listの要素はdictが前提だが、文字列等が混入するケースに備えて型チェック
    _buy_list_safe = [c for c in (_result.get("buy_list") or []) if isinstance(c, dict)]
    _kelly = _calc_kelly_fraction(
        theory_syn_odds = _result.get("theory_syn_odds"),
        total_prob      = sum(c.get("prob", 0) for c in _buy_list_safe),
    )
    _result["kelly"] = _kelly

    # ── 参加見送り判定をフラグとして付与 ──
    # venue は race_judgment 経由で受け取る（_suggest_3rentan は venue を直接知らない）
    # himo_are を race_judgment から _result に渡す（_should_skip_race が参照するため）
    if "himo_are" not in _result:
        _result["himo_are"] = (race_judgment or {}).get("himo_are", {}) or {}
    # nyujo_henkou（進入変更フラグ）を race_judgment から転記
    _result["nyujo_henkou"] = (race_judgment or {}).get("nyujo_henkou", False)
    # main_player（主役候補判定）を race_judgment から転記
    _result["main_player"] = (race_judgment or {}).get("main_player", {})
    # escape_fallback（(3) 主役自滅時の逃げ残存確率）を転記
    _result["escape_fallback"] = (race_judgment or {}).get("escape_fallback", {})
    # dark_horse（(4) 穴候補）を転記
    _result["dark_horse"] = (race_judgment or {}).get("dark_horse", {})
    # kimete_mismatch（追加B判定結果）を転記
    if "kimete_mismatch" not in _result:
        _result["kimete_mismatch"] = _kimete_mismatch

    # ── scenario_type の実態補正（v8.0）──────────────────────────────────
    # integrate_with_suggest_3rentan は buy_list/candidates を印◎ベースで差し替えるが
    # scenario_type を更新しない。その結果「逃げ軸流し」と書かれているのに
    # 買い目が全て非1号頭という矛盾が生じる。
    # ここで candidates の実際の1着分布から scenario_type を補正する。
    # ── is_orkaeshi フラグを base_result から復元 ──────────────────────────
    # integrate が candidates を差し替えるとき is_orkaeshi / is_orkaeshi_23 フラグが
    # 失われる。base_result の candidates から combo をキーにしてフラグを引き継ぐ。
    _base_cands_map = {
        c["combo"]: c
        for c in (_base_result.get("candidates") or [])
    }
    _cands_final = _result.get("candidates", [])
    for _c in _cands_final:
        _ck = _c.get("combo", "")
        if _ck in _base_cands_map:
            _bc = _base_cands_map[_ck]
            if "is_orkaeshi"    not in _c: _c["is_orkaeshi"]    = _bc.get("is_orkaeshi", False)
            if "is_orkaeshi_23" not in _c: _c["is_orkaeshi_23"] = _bc.get("is_orkaeshi_23", False)
    # ───────────────────────────────────────────────────────────────────────
    if _cands_final:
        from collections import Counter as _SC
        _first_dist = _SC(
            c["combo"].split("-")[0]
            for c in _cands_final
            if c.get("combo") and not c.get("is_fallback_bet") and not c.get("is_dh_bet")
        )
        _w1_cnt  = _first_dist.get("1", 0)
        _fly_cnt = sum(v for k, v in _first_dist.items() if k != "1")
        _top_fly = _first_dist.most_common(1)[0][0] if _fly_cnt > 0 else None

        _declared = _result.get("scenario_type", "")

        # 「逃げ軸流し」なのに1号頭が1点もない → 実態は飛び軸か両建て
        if _declared == "逃げ軸流し" and _w1_cnt == 0 and _fly_cnt > 0:
            _result["scenario_type"]    = "飛び軸"
            _result["scenario_verdict"] = "飛び軸"
            _result["scenario_type_note"] = (
                f"[!] 確率モデル逃げ{s1_prob*100:.0f}%→逃げ軸流しだが"
                f"印◎{_top_fly}号により買い目は{_top_fly}号頭軸に変更"
            )

        # 「逃げ軸流し」だが1号頭と非1号頭が混在 → 両建て
        elif _declared == "逃げ軸流し" and _w1_cnt > 0 and _fly_cnt > 0:
            _result["scenario_type"]    = "両建て"
            _result["scenario_verdict"] = "両建て"
            _result["scenario_type_note"] = (
                f"1号頭{_w1_cnt}点 / {_top_fly}号頭{_fly_cnt}点の両建て"
                f"（確率逃げ{s1_prob*100:.0f}%・印◎{_top_fly}号）"
            )

        # 「飛び軸」なのに1号頭が過半数 → 逃げ軸流しに補正
        elif _declared == "飛び軸" and _w1_cnt > _fly_cnt:
            _result["scenario_type"]    = "逃げ軸流し"
            _result["scenario_verdict"] = "逃げ軸流し"
            _result["scenario_type_note"] = (
                f"1号頭{_w1_cnt}点が多数 → 逃げ軸流しに補正"
            )

        else:
            _result["scenario_type_note"] = ""
    # ─────────────────────────────────────────────────────────────────────
    # 後処理の最終見送り判定
    # （早期見送りを通過した場合の最終チェック: scenario補正後の状態で再確認）
    # first_prob_map と kimete_mismatch を _result に注入してから判定
    if "first_prob_map" not in _result:
        _result["first_prob_map"] = {w: round(p, 4) for w, p in first_prob_map.items()}
    if "kimete_mismatch" not in _result:
        _result["kimete_mismatch"] = _kimete_mismatch
    _skip, _skip_reason = _should_skip_race(_result, _venue)
    _result["skip"]        = _skip
    _result["skip_reason"] = _skip_reason

    return _result


# ============================================================
# 本命記号スコア計算（トップレベル関数）
# ※ 元は calc_race_indices 内のローカル関数だったが
#   main() から直接呼ぶためトップレベルに移動。
# ============================================================

# ============================================================
# 6人相互作用モデル：攻撃有効性スコア計算
# ============================================================

def _calc_attack_effectiveness(attacker, w1_cm, venue_stats, results, st_kimete_master=None):
    """
    「この攻撃艇が、今日の1号艇を実際に崩せるか」を定量化する。

    【設計思想】
    単独の決まり手%や平均STではなく、
    「攻撃艇の攻撃力 × 1号艇の当該攻撃への脆弱性 × STアドバンテージ × 会場適性」
    の積として攻撃有効性を算出する。

    これにより「1号艇の逃げ率が高くても、2号艇のSTが圧倒的で差し実績が高ければ
    2号艇◎」という競艇の実態に即した印付けが可能になる。

    Parameters
    ----------
    attacker    : dict  攻撃艇のresultsエントリ
    w1_cm       : dict  1号艇のraw_cm（被決まり手データ含む）
    venue_stats : dict  会場統計（決まり手別比率）
    results     : list  全艇のresultsリスト（ST平均計算用）

    Returns
    -------
    dict:
        total_score     : 総合攻撃有効性スコア（0〜1）
        attack_type     : 主要攻撃手段（"差し"/"まくり"/"まくり差し"/"逃げ"）
        attack_power    : 攻撃力（0〜1）
        w1_vulnerability: 1号艇の当該攻撃への脆弱性（0〜1）
        st_advantage    : STアドバンテージ（0.5〜1.5）
        venue_affinity  : 会場の当該決まり手適性（0〜1）
        breakdown       : 各因子の詳細
    """
    waku      = str(attacker.get("waku", ""))
    cm        = attacker.get("raw_cm", {})
    avg_st    = attacker.get("avg_st")

    # 1号艇の情報
    st1       = next((r.get("avg_st") for r in results if r["waku"] == "1"), None)
    nige_pct1 = safe_float(w1_cm.get("逃げ%"), 0.6) or 0.6
    sasar_v   = safe_float(w1_cm.get("差され%"),     0.0) or 0.0
    makur_v   = safe_float(w1_cm.get("捲られ%"),     0.0) or 0.0
    maksa_v   = safe_float(w1_cm.get("捲り差され%"), 0.0) or 0.0

    # 全艇ST平均（基準）
    st_vals = [r["avg_st"] for r in results if r.get("avg_st") is not None]
    st_mean = sum(st_vals) / len(st_vals) if st_vals else 0.15

    # 会場の決まり手別成功率（攻撃が会場に合うか）
    kimari_avg = venue_stats.get("kimari_avg", {}) or {}
    v_sashi   = safe_float(kimari_avg.get("差し"),      0.15) or 0.15
    v_makuri  = safe_float(kimari_avg.get("まくり"),    0.20) or 0.20
    v_maksa   = safe_float(kimari_avg.get("まくり差し"),0.10) or 0.10
    # 会場実績はそのまま確率として保持（選手実績との加重平均ブレンド用）
    # ※旧: 全国平均で割った倍率（最大2.0）→ 確率スケールを逸脱していたため廃止

    # ── STアドバンテージ（1号艇比較）─────────────────────────────────────
    # 0.5〜1.0 に圧縮して確率スケールを維持
    # STが同じ→0.75、大幅優位(+0.04s)→1.0、大幅劣位(-0.04s)→0.5
    if avg_st is not None and st1 is not None:
        st_diff   = st1 - avg_st          # 正 = 自分が速い
        st_adv_v1 = max(0.5, min(1.0, 0.75 + st_diff / 0.04 * 0.25))
    else:
        st_diff   = None
        st_adv_v1 = 0.75

    # ── (2) ST差×決まり手 閾値マスタによる決まり手別ST感度補正 ──────────
    # 従来: 全決まり手に同一の st_adv_v1 を乗算（感度が一律）
    # 改善: 決まり手ごとに「この ST差帯での実際の成功率」を参照し補正係数を算出
    #
    # 補正係数の計算:
    #   ST差帯 = "優位"(>=+0.02s) / "同等"(-0.02〜+0.02s) / "劣位"(<-0.02s)
    #   基準   = "同等"ST差帯の成功率（分母）
    #   ratio  = 当該ST差帯の成功率 / 基準成功率
    #   補正係数 = (1 - trust) × 1.0 + trust × ratio  ← 信頼度で線形補間
    #            trust=0 → 従来通り（固定スケールのみ） / trust=1 → マスタ成功率100%反映
    def _st_kimete_adj(kimete: str) -> float:
        """決まり手ごとのST差補正係数を返す（(2)マスタ）。マスタ未生成時は1.0。"""
        if not st_kimete_master or st_diff is None:
            return 1.0
        _band = "優位" if st_diff >= 0.02 else ("劣位" if st_diff < -0.02 else "同等")
        _row  = st_kimete_master.get((waku, kimete, _band))
        if not _row:
            return 1.0
        _rate   = safe_float(_row.get("成功率"),  0.0) or 0.0
        _trust  = safe_float(_row.get("信頼度"),  0.0) or 0.0
        # 基準（同等ST差帯）成功率を取得
        _base_row = st_kimete_master.get((waku, kimete, "同等"))
        _base     = safe_float(_base_row.get("成功率"), 0.0) if _base_row else 0.0
        if _base <= 0.0:
            return 1.0
        _ratio = _rate / _base
        # 補正係数: 信頼度ゼロ→無補正(1.0)、信頼度1→マスタ比率をフル適用
        # 上下限を設けてスコアが極端にならないよう制御
        return max(0.4, min(2.0, 1.0 * (1.0 - _trust) + _ratio * _trust))

    # ── 全艇共通: 差し・まくり・まくり差しの3決まり手を全て評価し最大を採用 ──
    # 枠番で決まり手を固定せず、選手実績に基づいて最も有効な仕掛けを選ぶ。

    if waku == "1":
        # 1号艇：逃げ力のみ（別関数で詳細計算）
        nige_pct = safe_float(cm.get("逃げ%"), 0.6) or 0.6
        return {
            "total_score":      nige_pct,
            "attack_type":      "逃げ",
            "attack_power":     nige_pct,
            "w1_vulnerability": 0.0,
            "st_advantage":     1.0,
            "venue_affinity":   1.0,
            "breakdown":        {"逃げ%": nige_pct},
        }

    waku_i = int(waku)

    # ── 選手の各決まり手% ────────────────────────────────────────────────
    sashi_pct = safe_float(cm.get("差し%"),      0.0) or 0.0
    maku_pct  = safe_float(cm.get("まくり%"),    0.0) or 0.0
    maksa_pct = safe_float(cm.get("まくり差し%"),0.0) or 0.0

    # ── 枠番補正（物理的な届きやすさ）──────────────────────────────────
    # 差し:  内枠ほど届きやすい（2枠=1.0、外枠ほど低下）
    # まくり: 外枠ほど届きにくい（4枠=1.0、5枠=0.85、6枠=0.70、内枠は割増）
    # まくり差し: 中間枠が最適（3枠=1.0、内外に向かって低下）
    _sashi_waku  = {2: 1.00, 3: 0.80, 4: 0.60, 5: 0.40, 6: 0.25}.get(waku_i, 0.25)
    _maku_waku   = {2: 0.70, 3: 0.90, 4: 1.00, 5: 0.85, 6: 0.70}.get(waku_i, 0.70)
    _maksa_waku  = {2: 0.70, 3: 1.00, 4: 0.90, 5: 0.75, 6: 0.55}.get(waku_i, 0.55)

    # ── 2枠ブロックペナルティ（3枠以降の差し・まくり差しに影響）────────
    r2 = next((r for r in results if r["waku"] == "2"), None)
    if r2 and waku_i >= 3:
        w2_sashi = safe_float(r2.get("raw_cm", {}).get("差し%"), 0.0) or 0.0
        w2_st    = r2.get("avg_st")
        if w2_st is not None and st1 is not None:
            w2_adv = max(0.0, (st1 - w2_st) / 0.04)
        else:
            w2_adv = 0.0
        block_2 = max(0.5, 1.0 - w2_sashi * w2_adv * 0.5)
    else:
        block_2 = 1.0

    # ── 内側艇まくり壁ペナルティ（4枠以降のまくりに影響）───────────────
    inner_block = 1.0
    if waku_i >= 4:
        for r in results:
            rw = int(r["waku"])
            if 2 <= rw < waku_i:
                r_maku = safe_float(r.get("raw_cm", {}).get("まくり%"), 0.0) or 0.0
                r_st   = r.get("avg_st")
                if r_st is not None and avg_st is not None:
                    r_adv = max(0.0, (avg_st - r_st) / 0.04)
                else:
                    r_adv = 0.0
                inner_block = max(0.4, inner_block - r_maku * r_adv * 0.15)

    # ── 各決まり手の有効性スコア ─────────────────────────────────────────
    # 発生確率 = 選手実績×0.7 + 会場実績×0.3（加重平均）
    # 有効性   = 発生確率 × 1号艇脆弱性 × ST優位 × 枠番補正 × ブロックペナルティ
    #            × ST差×決まり手補正（(2)マスタ: 決まり手ごとのST感度）

    vuln_s  = min(1.0, sasar_v * 0.65 + (1.0 - nige_pct1) * 0.35)  # 差し脆弱性
    vuln_m  = min(1.0, makur_v * 0.70 + (1.0 - nige_pct1) * 0.30)  # まくり脆弱性
    vuln_ms = min(1.0, maksa_v * 0.60 + makur_v * 0.40)             # まくり差し脆弱性

    # 会場特性の寄与を高める（30% → 50%）
    # 理由: 戸田のようにまくりが多い会場で2号艇差しが常に主役になる問題を解消
    blend_s  = sashi_pct * 0.5 + v_sashi  * 0.5
    blend_m  = maku_pct  * 0.5 + v_makuri * 0.5
    blend_ms = maksa_pct * 0.5 + v_maksa  * 0.5

    # (2) 決まり手別ST感度補正係数（マスタ未生成時は1.0で無補正）
    _st_adj_s  = _st_kimete_adj("差し")
    _st_adj_m  = _st_kimete_adj("まくり")
    _st_adj_ms = _st_kimete_adj("まくり差し")

    score_sashi = blend_s  * vuln_s  * st_adv_v1 * _sashi_waku         * _st_adj_s
    score_maku  = blend_m  * vuln_m  * st_adv_v1 * _maku_waku  * inner_block * _st_adj_m
    score_maksa = blend_ms * vuln_ms * st_adv_v1 * _maksa_waku * block_2     * _st_adj_ms

    # 最大スコアの決まり手を採用
    scores = {
        "差し":      score_sashi,
        "まくり":    score_maku,
        "まくり差し": score_maksa,
    }
    best_type  = max(scores, key=lambda k: scores[k])
    best_score = scores[best_type]

    # ── (3) 当日調子補正（展示タイム・今節成績・モーター2連率）────────────────
    # 設計思想: 過去実績（raw_cm）だけでは「今日この選手が動けるか」がわからない。
    # 展示タイムの偏差・今節の調子・モーターの良し悪しを乗算係数として加える。
    # 各係数は0.80〜1.20の範囲に収め、スコアの大枠（決まり手適性・ST）を崩さない。
    today_mult = 1.0

    # A) 展示タイム偏差（tenji_hensa: 50基準、高い=速い=プラス）
    # 偏差+5（速い） → ×1.10 / 偏差-5（遅い） → ×0.90
    tenji_hensa = safe_float(attacker.get("tenji_hensa"))
    tenji_mult = None
    if tenji_hensa is not None:
        tenji_mult = max(0.80, min(1.20, 1.0 + (tenji_hensa - 50) / 50 * 1.0))
        today_mult *= tenji_mult

    # B) 今節成績スコア（kosetsu: "1-2-3" 形式、1着=高得点）
    # 今節スコア0.8以上（好調）→ ×1.10 / 0.2以下（不調）→ ×0.90
    kosetsu_str = str(attacker.get("kosetsu", "") or "")
    kosetsu_score = None
    kosetsu_mult = None
    if kosetsu_str and kosetsu_str not in ("", "None", "nan", "-"):
        _ks = []
        for tok in re.split(r"[-・/]", kosetsu_str):
            tok = tok.strip()
            if tok == "1":       _ks.append(1.0)
            elif tok == "2":     _ks.append(0.5)
            elif tok == "3":     _ks.append(0.25)
            elif tok.isdigit(): _ks.append(0.0)
        if _ks:
            kosetsu_score = sum(_ks) / len(_ks)
            kosetsu_mult  = max(0.85, min(1.15, 1.0 + (kosetsu_score - 0.5) * 0.30))
            today_mult   *= kosetsu_mult

    # C) モーター2連率補正（全艇平均比）
    # 全艇平均より+5pt以上優秀 → ×1.10 / -5pt以下 → ×0.90
    motor2_val  = safe_float(attacker.get("motor2"))
    motor2_mult = None
    if motor2_val is not None:
        m2_vals = [safe_float(r.get("motor2")) for r in results if safe_float(r.get("motor2")) is not None]
        if m2_vals:
            m2_mean     = sum(m2_vals) / len(m2_vals)
            motor2_mult = max(0.85, min(1.15, 1.0 + (motor2_val - m2_mean) / 10 * 0.20))
            today_mult *= motor2_mult

    # 当日調子補正を最終スコアに乗算（上限1.0）
    best_score = best_score * today_mult

    _vuln_map  = {"差し": vuln_s,  "まくり": vuln_m,  "まくり差し": vuln_ms}
    _blend_map = {"差し": blend_s, "まくり": blend_m, "まくり差し": blend_ms}
    _venue_map = {"差し": v_sashi, "まくり": v_makuri, "まくり差し": v_maksa}

    return {
        "total_score":      min(best_score, 1.0),
        "attack_type":      best_type,
        "attack_power":     _blend_map[best_type],
        "w1_vulnerability": _vuln_map[best_type],
        "st_advantage":     st_adv_v1,
        "venue_affinity":   _venue_map[best_type],
        "today_mult":       round(today_mult, 4),
        "breakdown":        {
            "差し%":           round(sashi_pct,   3),
            "まくり%":         round(maku_pct,    3),
            "まくり差し%":     round(maksa_pct,   3),
            "差しスコア":      round(score_sashi,  4),
            "まくりスコア":    round(score_maku,   4),
            "まくり差しスコア": round(score_maksa, 4),
            "採用":            best_type,
            "ST優位":          round(st_adv_v1,   3),
            "展示補正":        round(tenji_mult,  3) if tenji_mult  is not None else None,
            "今節補正":        round(kosetsu_mult,3) if kosetsu_mult is not None else None,
            "モーター補正":    round(motor2_mult, 3) if motor2_mult  is not None else None,
            "当日調子計":      round(today_mult,  3),
        },
    }


def _calc_w1_escape_score(r1, results, venue_stats, race_judgment=None, st_kimete_master=None):
    """
    1号艇が「今日このメンバーを相手に逃げ切れる確率」を定量化する。

    【v2: 展開エンジン連動】
    race_judgment の escape_score（逃げ定性スコア）と tobi_score（飛び定性スコア）を
    直接参照する。展開エンジンが「飛び優勢」と判定しているのに
    1号艇◎になるという矛盾を根本から解消する。

    計算式:
      逃げ有効スコア
        = 選手固有の逃げ力（nige_pct × ST安定性）   … 過去実績
        × 今日の展開的な逃げ支持度（ryotate補正）    … 展開エンジン判定
        × 攻撃艇脅威ペナルティ                       … メンバー相互作用

    ryotate補正の設計:
      escape_score > tobi_score + 15 → 逃げ明確優勢 → 補正なし（×1.0）
      escape_score ≒ tobi_score（差±15以内）→ 拮抗  → 軽い抑制（×0.75）
      tobi_score > escape_score + 15  → 飛び優勢    → 強い抑制（×0.45）
      tobi_score > escape_score + 30  → 飛び圧倒    → 最大抑制（×0.25）

    Returns
    -------
    float: 逃げ有効スコア（0〜1）
    """
    cm1      = r1.get("raw_cm", {})
    nige_pct = safe_float(cm1.get("逃げ%"), 0.6) or 0.6
    st1      = r1.get("avg_st")

    # ── 展開エンジン（ryotate）の逃げ/飛びスコアを参照 ──────────────────
    rj = race_judgment or {}
    ryotate = rj.get("ryotate", {}) or {}
    esc_s = float(ryotate.get("escape_score", 50) or 50)   # 逃げ定性スコア（0〜100）
    tob_s = float(ryotate.get("tobi_score",   30) or 30)   # 飛び定性スコア（0〜100）
    diff  = esc_s - tob_s   # 正=逃げ優勢、負=飛び優勢

    if diff >= 15:
        ryotate_mult = 1.00   # 逃げ明確優勢
    elif diff >= -15:
        ryotate_mult = 0.75   # 拮抗（両建て領域）
    elif diff >= -30:
        ryotate_mult = 0.45   # 飛び優勢（画像のケース: esc=23, tob=35 → diff=-12 → 0.75）
    else:
        ryotate_mult = 0.25   # 飛び圧倒

    # ── 攻撃艇脅威ペナルティ（メンバー相互作用）───────────────────────
    threats = []
    for r in results:
        if r["waku"] == "1":
            continue
        eff = _calc_attack_effectiveness(r, cm1, venue_stats, results, st_kimete_master=st_kimete_master)
        threats.append(eff["total_score"])

    if threats:
        max_threat = max(threats)
        avg_threat = sum(threats) / len(threats)
        threat_penalty = max(0.4, 1.0 - max_threat * 0.5 - avg_threat * 0.15)
    else:
        threat_penalty = 1.0

    # ── ST安定性 ────────────────────────────────────────────────────────
    fly_label  = r1.get("fly_label", "低")
    fly_mult   = {"低": 1.0, "中": 0.88, "高": 0.72}.get(fly_label, 1.0)
    st_vals    = [r["avg_st"] for r in results if r.get("avg_st") is not None]
    if st1 is not None and st_vals:
        st_mean    = sum(st_vals) / len(st_vals)
        st_penalty = max(0.7, min(1.15, 1.0 - (st1 - st_mean) / 0.05 * 0.15))
    else:
        st_penalty = 1.0

    escape_score = nige_pct * ryotate_mult * threat_penalty * fly_mult * st_penalty
    return min(escape_score, 1.0)


def _judge_w1_escape(results, venue_stats, race_judgment=None, st_kimete_master=None):
    """
    (1) 1号艇逃げ力判定 ── 6人構成メンバーを相手に逃げ切れるか

    【設計思想】
    「1号艇単体の逃げ実績」ではなく、
    「このメンバー6人の構成の中で、1号艇が逃げ切れる確率」を評価する。

    循環依存を排除するため race_judgment（ryotate/escape_score）は参照しない。
    本関数の出力が後続の ryotate 判定・印スコアの入力になる一方向の流れ。

    計算ステップ:
      Step1: 1号艇の固有逃げ力
             = nige_pct（コース別逃げ決まり手%）× ST安定性 × FLYリスク
      Step2: 2〜6号艇それぞれの対1号艇攻撃力（_calc_attack_effectiveness）
             → 最大脅威艇と攻撃タイプを特定
      Step3: 会場イン逃げ率による補正
             = 逃げやすい会場ならボーナス、荒れ会場ならペナルティ
      Step4: 総合逃げ確率（0〜1）と根拠テキストを出力

    Returns
    -------
    dict:
        escape_prob      : 逃げ確率（0〜1）
        escape_pct       : 逃げ確率%表示（例: "62.3%"）
        escape_rank      : "高"(>=0.60) / "中"(>=0.40) / "低"(<0.40)
        nige_power       : 1号艇固有逃げ力（0〜1）
        top_threat_waku  : 最大脅威艇の艇番
        top_threat_type  : 最大脅威の攻撃タイプ（"差し"/"まくり"等）
        top_threat_score : 最大脅威スコア（0〜1）
        threat_list      : 全攻撃艇の脅威スコア一覧 [(waku, type, score), ...]
        venue_modifier   : 会場補正係数
        reason           : 根拠テキスト（コンソール・新聞出力用）
    """
    r1 = next((r for r in results if r["waku"] == "1"), None)
    if r1 is None:
        return {
            "escape_prob": 0.5, "escape_pct": "50.0%", "escape_rank": "中",
            "nige_power": 0.5, "top_threat_waku": None, "top_threat_type": "-",
            "top_threat_score": 0.0, "threat_list": [], "venue_modifier": 1.0,
            "reason": "1号艇データなし",
        }

    cm1      = r1.get("raw_cm", {})
    st1      = r1.get("avg_st")
    fly_label = r1.get("fly_label", "低")
    fly_days  = safe_float((r1.get("raw_pm") or {}).get("FLY経過日数"))

    # ── nige_pct: 実質逃げ確率（修正版）────────────────────────────────
    # 旧: 「1着時の逃げ決まり手%」のみ → 常に80%台で高すぎる
    # 新: 「1コース1着率」×「逃げ決まり手%」= 実際に逃げ切れる確率
    #   例: 1コース1着率65% × 逃げ決まり手82% = 実質53%
    # ── 逃げ力の正しい設計 ──────────────────────────────────────────────
    # 【設計思想の転換】
    # 旧: 1コース1着率 × 逃げ決まり手% → 「1着になれる確率」×「逃げで決まる率」
    #     問題: 被まくり差され48%のような弱点を全く反映しない
    #
    # 新: 会場の1コース1着率（ベース）× 被決まり手補正 × ST補正
    #     「被決まり手」= 差された% + まくられた% + まくり差された%（1号艇の弱点）
    #     これが高いほど外枠の攻めに弱く、逃げ切れない
    #
    # 根拠: 新聞の「決まり手」欄の1枠数値は全て「被決まり手%」
    #       差された22% + まくり差された48% のような艇は逃げ力が低い

    _pm1 = r1.get("raw_pm", {}) or {}

    # ベース: 会場の1コース1着率（選手個人値 → 会場平均 → 全国平均の順でフォールバック）
    _rate_1st_c1 = safe_float(
        _pm1.get("イン\n1着率") or _pm1.get("イン1着率") or
        r1.get("rate_1st_c1")
    )
    if _rate_1st_c1 is None or _rate_1st_c1 <= 0:
        _rate_1st_c1 = safe_float(
            (venue_stats or {}).get("c1_win_rate") or
            (venue_stats or {}).get("in_rate")
        ) or 0.555

    # 被決まり手（1号艇の弱点）: raw_cm から取得
    # ── デバッグ: 被決まり手データ確認 ────────────────────────────────
    _cm1_keys = [k for k in cm1.keys() if "差" in str(k) or "捲" in str(k) or "逃" in str(k)]
    print(f"  [DEBUG逃げ力] cm1キー中の関連項目: {_cm1_keys}")
    print(f"  [DEBUG逃げ力] rate_1st_c1={_rate_1st_c1:.3f} nige_kimete={cm1.get('逃げ%')}")
    print(f"  [DEBUG逃げ力] 差され%={cm1.get('差され%')} 捲られ%={cm1.get('捲られ%')} 捲り差され%={cm1.get('捲り差され%')}")
    _lose_sashi = safe_float(cm1.get("差され%"),     0.0) or 0.0   # 差された%
    _lose_makur = safe_float(cm1.get("捲られ%"),     0.0) or 0.0   # まくられた%
    _lose_maksa = safe_float(cm1.get("捲り差され%"), 0.0) or 0.0   # まくり差された%

    # 被決まり手脆弱性（0〜1）: まくり差しへの弱さを最重視
    _lose_vuln = min(1.0,
        _lose_sashi * 0.40 +    # 差し系への弱さ
        _lose_maksa * 0.45 +    # まくり差し系への弱さ（競艇で最も崩れやすいパターン）
        _lose_makur * 0.15      # まくり系への弱さ
    )
    _lose_suppress = max(0.30, 1.0 - _lose_vuln)

    # 逃げ決まり手比率補正: 逃げ率が低い = 1着でも差し/まくり差しで決まることが多い
    _nige_kimete = safe_float(cm1.get("逃げ%"), 0.55) or 0.55
    _nige_ratio_penalty = max(0.40, _nige_kimete / 0.555)  # 全国平均55%を基準

    # 実質逃げ確率
    nige_pct = min(_rate_1st_c1 * _lose_suppress * _nige_ratio_penalty, 1.0)

    # ── Step1: 1号艇固有逃げ力 ─────────────────────────────────────────
    # FLYリスク補正（平均STへの影響）
    fly_mult = {"低": 1.0, "中": 0.88, "高": 0.72}.get(fly_label, 1.0)

    # 【(7)改善】FLY明けST分散拡大補正
    # FLY明け選手はSTが遅くなるだけでなく、ばらつきが大きくなる（読めない）。
    # これを「逃げ確率の信頼区間幅拡大」として表現:
    #   fly_uncertainty = ST分散拡大率（0.0〜0.20）
    #   fly_uncert_penalty = uncertainty × 0.5 として逃げ確率から減算
    # 根拠: ばらつきが大きいほど「たまに速いが信頼できない」状態を確率に反映
    # fly_daysが短いほど分散が大きい（出場停止明け直後が最大）
    if fly_label == "高":
        if fly_days is not None and fly_days < 90:
            fly_uncertainty = 0.20   # 出場停止明け直後: 最大分散
        else:
            fly_uncertainty = 0.14   # FLY複数回・日数不明
    elif fly_label == "中":
        if fly_days is not None and fly_days < 90:
            fly_uncertainty = 0.10
        else:
            fly_uncertainty = 0.06
    else:
        fly_uncertainty = 0.0        # FLYなし: 分散拡大なし

    # ST安定性補正（全艇平均より遅いほど逃げ力低下）
    st_vals = [r["avg_st"] for r in results if r.get("avg_st") is not None]
    if st1 is not None and st_vals:
        st_mean    = sum(st_vals) / len(st_vals)
        st_penalty = max(0.70, min(1.15, 1.0 - (st1 - st_mean) / 0.05 * 0.15))
    else:
        st_penalty = 1.0

    nige_power = min(nige_pct * fly_mult * st_penalty, 1.0)

    # ── Step2: 2〜6号艇の対1号艇攻撃力 ────────────────────────────────
    threat_list = []
    for r in results:
        if r["waku"] == "1":
            continue
        eff = _calc_attack_effectiveness(r, cm1, venue_stats, results, st_kimete_master=st_kimete_master)
        threat_list.append((
            r["waku"],
            eff["attack_type"],
            round(eff["total_score"], 4),
        ))
    threat_list.sort(key=lambda x: x[2], reverse=True)

    if threat_list:
        top_threat_waku  = threat_list[0][0]
        top_threat_type  = threat_list[0][1]
        top_threat_score = threat_list[0][2]
        avg_threat       = sum(s for _, _, s in threat_list) / len(threat_list)
        # 脅威ペナルティ: 最大脅威×0.50 + 平均脅威×0.15（下限0.40）
        threat_penalty = max(0.40, 1.0 - top_threat_score * 0.50 - avg_threat * 0.15)
    else:
        top_threat_waku  = None
        top_threat_type  = "-"
        top_threat_score = 0.0
        threat_penalty   = 1.0

    # ── Step3: 会場イン逃げ率補正 ───────────────────────────────────────
    in_rate = safe_float(venue_stats.get("in_rate"))
    if in_rate is not None:
        # 全国平均0.555を基準に補正（上限1.15、下限0.75）
        venue_modifier = max(0.75, min(1.15, in_rate / 0.555))
    else:
        venue_modifier = 1.0

    # ── Step4: 総合逃げ確率 ────────────────────────────────────────────
    escape_prob_raw = min(nige_power * threat_penalty * venue_modifier, 1.0)

    # 【(7)】FLY明け分散拡大ペナルティを逃げ確率に適用
    # ばらつきが大きい = 「高い時もあるが低い時もある」 → 期待値を下方修正
    fly_uncert_penalty = fly_uncertainty * 0.5
    escape_prob = max(0.0, min(1.0, escape_prob_raw - fly_uncert_penalty))

    # ── 逃げランク ──────────────────────────────────────────────────────
    if escape_prob >= 0.60:
        escape_rank = "高"
    elif escape_prob >= 0.40:
        escape_rank = "中"
    else:
        escape_rank = "低"

    # ── 根拠テキスト生成 ────────────────────────────────────────────────
    reason_parts = []
    reason_parts.append(
        f"1号艇逃げ力: 1着率={_rate_1st_c1*100:.0f}%"
        f" × 被決まり手抑制={_lose_suppress:.2f}(差され{_lose_sashi*100:.0f}%/まくり差され{_lose_maksa*100:.0f}%)"
        f" × 逃げ率補正={_nige_ratio_penalty:.2f}"
        f" → 実質{nige_pct*100:.0f}%"
        f" / FLY={fly_mult:.2f} ST={st_penalty:.2f} → 固有{nige_power*100:.0f}%"
    )
    if fly_uncertainty > 0:
        reason_parts.append(
            f"FLY明けST分散拡大: 不確実度±{fly_uncertainty*100:.0f}% "
            f"→ 逃げ確率を{fly_uncert_penalty*100:.1f}%下方修正"
        )
    if threat_list:
        top_w, top_t, top_s = threat_list[0]
        reason_parts.append(
            f"最大脅威: {top_w}号艇（{top_t}） 脅威スコア{top_s*100:.0f}% "
            f"→ 脅威ペナルティ×{threat_penalty:.2f}"
        )
        if len(threat_list) >= 2:
            w2, t2, s2 = threat_list[1]
            reason_parts.append(f"次点脅威: {w2}号艇（{t2}） {s2*100:.0f}%")
    if in_rate is not None:
        reason_parts.append(
            f"会場イン逃げ率{in_rate*100:.1f}% → 会場補正×{venue_modifier:.2f}"
        )
    reason_parts.append(
        f"→ 総合逃げ確率 {escape_prob*100:.1f}%【{escape_rank}】"
        + (f"（FLY分散補正前:{escape_prob_raw*100:.1f}%）" if fly_uncertainty > 0 else "")
    )

    return {
        "escape_prob":      round(escape_prob, 4),
        "escape_pct":       f"{escape_prob*100:.1f}%",
        "escape_rank":      escape_rank,
        "nige_power":       round(nige_power, 4),
        "top_threat_waku":  top_threat_waku,
        "top_threat_type":  top_threat_type,
        "top_threat_score": top_threat_score,
        "threat_list":      threat_list,
        "venue_modifier":   round(venue_modifier, 4),
        "reason":           " / ".join(reason_parts),
    }


def _judge_main_player(results, venue_stats, race_judgment,
                       tenkai_venue=None, tenkai_national=None, st_kimete_master=None):
    """
    (2) 主役候補判定 ── 逃げない場合に誰が主役で、どの展開になるか

    【設計思想】
    俊太さんの思考フローを忠実に再現:
      1. 誰が主役か（attack_effectiveness の最大艇）
      2. その主役はどの決まり手か（attack_type）
      3. その決まり手なら2・3着は誰か（展開別残存マスタを直接参照）
      4. 主役が崩れたら誰が浮上するか（collapse_beneficiary）
      5. そのまま1号艇が逃げを決めるか / 第三者が展開を突くか

    Step3で展開別残存マスタを「主役の決まり手 × 主役の進入コース」で
    引くことで、逃げ時の残存マスタ（circle_pct流用）から脱却する。
    """
    # ── w1_escape の threat_list を取得 ────────────────────────────────
    w1_escape   = race_judgment.get("w1_escape", {})
    threat_list = w1_escape.get("threat_list", [])  # [(waku, type, score), ...]

    # threat_list が空なら直接計算
    if not threat_list:
        r1 = next((r for r in results if r["waku"] == "1"), None)
        w1_cm = r1.get("raw_cm", {}) if r1 else {}
        for r in results:
            if r["waku"] == "1":
                continue
            eff = _calc_attack_effectiveness(r, w1_cm, venue_stats, results, st_kimete_master=st_kimete_master)
            threat_list.append((r["waku"], eff["attack_type"], round(eff["total_score"], 4)))
        threat_list.sort(key=lambda x: x[2], reverse=True)

    if not threat_list:
        return {
            "main_waku": None, "main_type": "-", "main_score": 0.0,
            "sub_waku": None,  "sub_type":  "-", "sub_score":  0.0,
            "place2_candidates": [], "place3_candidates": [],
            "place2_by_kimete": {}, "place3_by_kimete": {},
            "reason": "攻撃艇データなし",
        }

    # ── Step1: 主役候補1・2位を確定 ────────────────────────────────────
    main_waku  = threat_list[0][0]
    main_type  = threat_list[0][1]
    main_score = threat_list[0][2]
    sub_waku   = threat_list[1][0] if len(threat_list) >= 2 else None
    sub_type   = threat_list[1][1] if len(threat_list) >= 2 else "-"
    sub_score  = threat_list[1][2] if len(threat_list) >= 2 else 0.0

    # ── Step2: 決まり手→展開別残存マスタのキーを決定 ────────────────────
    _KIMETE_MAP = {"差し": "差し", "まくり": "まくり", "まくり差し": "まくり差し"}
    venue = (race_judgment or {}).get("venue")

    def _fetch_tenkai_2nd3rd(kimete, main_w):
        """
        展開別残存マスタから「決まり手=kimete, 1着コース=主役コース」の
        各艇の2着率・3着以内率を取得する。
        会場別→全国の優先順で参照。
        """
        r_main = next((r for r in results if r["waku"] == main_w), {})
        course = str(int(float(r_main.get("course") or r_main.get("進入コース") or main_w)))
        rates  = {}
        for c in range(1, 7):
            c_str = str(c)
            if c_str == course:
                continue  # 1着艇自身は除外
            row = None
            # 会場別マスタ優先
            if tenkai_venue and venue:
                key_v = (str(venue), kimete, course, c_str)
                rv = tenkai_venue.get(key_v)
                if rv:
                    try:
                        trust = float(rv.get("信頼度") or 0)
                        if trust >= 0.15:
                            # 全国マスタとブレンド
                            rn = tenkai_national.get((kimete, course, c_str)) if tenkai_national else None
                            if rn and trust < 0.50:
                                w_v = trust / 0.50
                                w_n = 1.0 - w_v
                                row = {
                                    "2着率":     float(rv.get("2着率") or 0) * w_v + float(rn.get("2着率") or 0) * w_n,
                                    "3着以内率": float(rv.get("3着以内率") or 0) * w_v + float(rn.get("3着以内率") or 0) * w_n,
                                }
                            else:
                                row = rv
                    except (ValueError, TypeError):
                        pass
            # 全国マスタフォールバック
            if row is None and tenkai_national:
                row = tenkai_national.get((kimete, course, c_str))
            if row:
                try:
                    rates[c_str] = {
                        "2着率":     float(row.get("2着率")     or 0),
                        "3着以内率": float(row.get("3着以内率") or 0),
                    }
                except (ValueError, TypeError):
                    pass
        return rates

    # ── Step3: 主役の決まり手で2・3着候補を決定 ──────────────────────────
    # 「その決まり手なら2・3着は誰か」を展開別残存マスタから直接引く
    kimete = _KIMETE_MAP.get(main_type, "まくり")
    tenkai_rates = _fetch_tenkai_2nd3rd(kimete, main_waku)

    place2_raw = []
    place3_raw = []

    if tenkai_rates:
        # 展開別残存マスタあり → マスタの2着率・3着以内率で評価
        for c_str, rates in tenkai_rates.items():
            if c_str == main_waku:
                continue
            r2  = rates.get("2着率", 0)
            r3i = rates.get("3着以内率", 0)
            # 2着候補: 2着率が高い艇
            place2_raw.append((c_str, round(r2, 4)))
            # 3着候補: 3着以内率 - 2着率 = 純3着率
            place3_raw.append((c_str, round(max(r3i - r2, 0), 4)))
    else:
        # マスタなし → フォールバック（決まり手に応じた内側/外側残存ルール）
        # 差し: 内側（1号艇含む）が残りやすい
        # まくり: まくった外側後続が残りやすい
        # まくり差し: 内外混在
        _INNER_BONUS = {"差し": ["1","2","3"], "まくり差し": ["1","2","3","4"], "まくり": ["3","4","5"]}
        inner_wakus = _INNER_BONUS.get(main_type, [])
        for r in results:
            w = r["waku"]
            if w == main_waku:
                continue
            win3 = r.get("win3_rate") or 0.5
            idx3 = r.get("idx3") or 0
            bonus = 1.3 if w in inner_wakus else 0.8
            place2_raw.append((w, round(win3 * bonus, 4)))
            place3_raw.append((w, round(idx3 * bonus * 0.5, 4)))

    place2_candidates = sorted(
        [(w, s) for w, s in place2_raw if w != main_waku],
        key=lambda x: x[1], reverse=True
    )[:3]

    # 3着候補: 主役+2着最有力を除いた艇
    top2_wakus = {main_waku}
    if place2_candidates:
        top2_wakus.add(place2_candidates[0][0])
    place3_candidates = sorted(
        [(w, s) for w, s in place3_raw if w not in top2_wakus],
        key=lambda x: x[1], reverse=True
    )[:3]

    # ── Step4: 対抗主役（sub_waku）の決まり手でも同様に取得 ──────────────
    # 「対抗主役が来たときの2・3着」も保持しておく（考察・買い目で活用）
    sub_place2 = []
    sub_place3 = []
    if sub_waku:
        sub_kimete = _KIMETE_MAP.get(sub_type, "まくり")
        sub_rates  = _fetch_tenkai_2nd3rd(sub_kimete, sub_waku)
        if sub_rates:
            sub_p2r = sorted(
                [(c, v["2着率"]) for c, v in sub_rates.items() if c != sub_waku],
                key=lambda x: x[1], reverse=True
            )
            sub_p3r = sorted(
                [(c, max(v["3着以内率"] - v["2着率"], 0)) for c, v in sub_rates.items() if c != sub_waku],
                key=lambda x: x[1], reverse=True
            )
            sub_place2 = sub_p2r[:3]
            sub_place3 = sub_p3r[:3]

    # ── Step5: 根拠テキスト生成 ─────────────────────────────────────────
    p2_str = "  ".join(f"{w}号{s*100:.0f}%" for w, s in place2_candidates)
    p3_str = "  ".join(f"{w}号{s*100:.0f}%" for w, s in place3_candidates)
    src    = "展開別残存マスタ" if tenkai_rates else "フォールバック"

    reason_parts = [
        f"主役候補(1): {main_waku}号艇【{main_type}】 攻撃スコア{main_score*100:.0f}%",
    ]
    if sub_waku:
        reason_parts.append(
            f"主役候補(2): {sub_waku}号艇【{sub_type}】 攻撃スコア{sub_score*100:.0f}%"
        )
    reason_parts.append(f"→ {main_type}時2着候補({src}): {p2_str}")
    reason_parts.append(f"→ {main_type}時3着候補({src}): {p3_str}")

    return {
        "main_waku":         main_waku,
        "main_type":         main_type,
        "main_score":        round(main_score, 4),
        "sub_waku":          sub_waku,
        "sub_type":          sub_type,
        "sub_score":         round(sub_score, 4),
        "place2_candidates": place2_candidates,
        "place3_candidates": place3_candidates,
        "sub_place2":        sub_place2,
        "sub_place3":        sub_place3,
        "tenkai_rates_used": bool(tenkai_rates),
        "reason":            " / ".join(reason_parts),
    }


def _judge_escape_fallback(results, venue_stats, race_judgment, conflict_map=None, st_kimete_master=None):
    """
    (3) 主役が来れなかった時の逃げ残存確率

    【設計思想】
    主役候補（main_player.main_waku）が自滅・失速した場合に、
    1号艇が2着以内に「生き残れるか」を数値化する。

    現状の SC シナリオには「1号艇が2着に残れる確率」が明示的に出ないため、
    本関数でそれを算出し買い目の「逃げ残存フォロー」判断に使う。

    計算ステップ:
      Step1: 1号艇の逃げ力ベース（w1_escape.escape_prob）を取得
      Step2: 主役の自滅タイプ（sc_fly_type）に応じた1号艇残存補正
             まくり系自滅 → コースが開く → 1号艇残存ボーナス（×1.30）
             差し系自滅   → 蓋の影響あり → 1号艇残存ペナルティ（×0.75）
      Step3: 漁夫（collapse_beneficiary）の上位艇が外から来ると1号艇の
             2着スペースが圧迫される → 上位受益艇数に応じた追加ペナルティ
      Step4: 最終的な逃げ残存確率（0〜1）と根拠テキストを出力

    Returns
    -------
    dict:
        fallback_prob   : 主役自滅時の1号艇2着以内残存確率（0〜1）
        fallback_pct    : fallback_prob の%表示
        fallback_rank   : "高"(>=0.55) / "中"(>=0.35) / "低"(<0.35)
        fly_type        : 主役の自滅タイプ（"まくり系"/"差し系"/"不明"）
        pressure_wakus  : 1号艇を圧迫する上位受益艇リスト [(waku, score), ...]
        reason          : 根拠テキスト
    """
    w1_escape   = race_judgment.get("w1_escape", {}) or {}
    main_player = race_judgment.get("main_player", {}) or {}
    # conflict_map はキーワード引数優先、なければ race_judgment から取得
    conflict_map = conflict_map or race_judgment.get("conflict_map", {}) or {}

    escape_prob = float(w1_escape.get("escape_prob", 0.5) or 0.5)
    main_waku   = main_player.get("main_waku")
    main_type   = main_player.get("main_type", "-")

    # ── Step2: 主役の自滅タイプを展開タイプから推定 ──────────────────────────
    # main_type（差し/まくり/まくり差し）を _calc_sc_weight の sc_fly_type に対応させる
    if main_type in ("まくり", "まくり差し"):
        fly_type       = "まくり系"
        type_modifier  = 1.30   # コースが開く → 1号艇が取り戻しやすい
    elif main_type == "差し":
        fly_type       = "差し系"
        type_modifier  = 0.75   # 差し自滅では蓋の影響が1号艇に及ぶ
    else:
        fly_type       = "不明"
        type_modifier  = 1.00

    base_prob = min(escape_prob * type_modifier, 1.0)

    # ── Step3: 漁夫受益艇による圧迫ペナルティ ────────────────────────────────
    # collapse_beneficiary は主軸当事者を除いた外側の艇 → これらが来ると
    # 1号艇の2着スペースがさらに圧迫される
    collapse_bene = conflict_map.get("collapse_beneficiary", []) or []

    # 主役艇自身は受益者リストから除外（主役が自滅した場合の話なので）
    pressure_wakus = [
        (w, s) for w, s in collapse_bene
        if w != main_waku and w != "1"
    ][:3]

    # 上位受益艇のスコア合計に応じてペナルティ加算（最大 -0.15）
    top_pressure_sum = sum(s for _, s in pressure_wakus[:2])
    pressure_penalty = min(top_pressure_sum * 0.20, 0.15)

    fallback_prob = max(0.0, min(base_prob - pressure_penalty, 1.0))

    # ── ランク付け ────────────────────────────────────────────────────────────
    if fallback_prob >= 0.55:
        fallback_rank = "高"
    elif fallback_prob >= 0.35:
        fallback_rank = "中"
    else:
        fallback_rank = "低"

    # ── 根拠テキスト生成 ──────────────────────────────────────────────────────
    reason_parts = [
        f"逃げ力ベース={escape_prob*100:.0f}%"
        f" × {fly_type}補正×{type_modifier:.2f} → {base_prob*100:.0f}%",
    ]
    if pressure_wakus:
        pw_str = "  ".join(f"{w}号({s:.2f})" for w, s in pressure_wakus)
        reason_parts.append(
            f"圧迫受益艇: {pw_str} → 圧迫ペナルティ-{pressure_penalty*100:.0f}%"
        )
    reason_parts.append(
        f"→ 逃げ残存確率 {fallback_prob*100:.1f}%【{fallback_rank}】"
    )

    return {
        "fallback_prob":  round(fallback_prob, 4),
        "fallback_pct":   f"{fallback_prob*100:.1f}%",
        "fallback_rank":  fallback_rank,
        "fly_type":       fly_type,
        "pressure_wakus": pressure_wakus,
        "reason":         " / ".join(reason_parts),
    }


def _judge_dark_horse(results, venue_stats, race_judgment, conflict_map=None, st_kimete_master=None):
    """
    (4) 主役展開の穴をつく艇（ダークホース）判定

    【設計思想】
    主役展開（main_player.main_waku が1着に来る）が成立するとき、
    主軸の対立構造（main_waku vs 1号艇）の「外側」で美味しいポジションに
    入れる艇を特定する。

    既に計算済みの collapse_beneficiary（_build_conflict_map の出力）を活用し、
    さらに以下3条件でフィルタリングして「本物の穴」を絞り込む：
      条件(1): 主軸対立の外側にいる（main_waku でも "1" でもない）
      条件(2): win3_rate が高い（地力がある = 荒れても残れる）
      条件(3): 決まり手が抜き・逃げ系（受動型 = 自滅しない）

    計算ステップ:
      Step1: collapse_beneficiary から主軸当事者を除いた外側艇リストを取得
      Step2: 各艇に対して「抜き系受動スコア」を計算
             = win3_rate × 受動性 × 漁夫スコア（collapse_beneficiaryスコア）
      Step3: スコア上位3艇を dark_horse_candidates として返す
      Step4: 根拠テキスト生成

    Returns
    -------
    dict:
        dark_horse_candidates : [(waku, score, reason_tag), ...] 上位3艇
        top_waku              : 最有力ダークホース艇番（Noneの場合あり）
        top_score             : 最有力艇のスコア（0〜1）
        is_valid              : True = 有効なダークホース候補あり
        reason                : 根拠テキスト
    """
    main_player  = race_judgment.get("main_player", {}) or {}
    # conflict_map はキーワード引数優先、なければ race_judgment から取得
    conflict_map = conflict_map or race_judgment.get("conflict_map", {}) or {}

    main_waku     = main_player.get("main_waku")
    collapse_bene = conflict_map.get("collapse_beneficiary", []) or []

    if not collapse_bene:
        return {
            "dark_horse_candidates": [],
            "top_waku":   None,
            "top_score":  0.0,
            "is_valid":   False,
            "reason":     "潰れ受益候補データなし",
        }

    # results を waku をキーにした辞書に変換
    results_map = {r["waku"]: r for r in results}

    # ── Step1: 外側艇リスト（主軸当事者を除外） ───────────────────────────────
    outer_bene = [
        (w, s) for w, s in collapse_bene
        if w != main_waku and w != "1"
    ]

    if not outer_bene:
        return {
            "dark_horse_candidates": [],
            "top_waku":   None,
            "top_score":  0.0,
            "is_valid":   False,
            "reason":     "主軸外側の受益候補なし",
        }

    # ── Step2: 各艇の「穴スコア」計算 ─────────────────────────────────────────
    def _safe_pct(cm, key):
        v = cm.get(key) if cm else None
        try:
            return max(float(v), 0.0) if v is not None else 0.0
        except (ValueError, TypeError):
            return 0.0

    dark_horse_raw = []
    for w, bene_score in outer_bene:
        r = results_map.get(w, {})
        cm = r.get("raw_cm", {}) or {}

        win3  = r.get("win3_rate") or 0.5
        # 受動性スコア: 抜き・逃げ系の決まり手比率が高いほど受動型
        nuki_pct  = _safe_pct(cm, "抜き%")
        nige_pct  = _safe_pct(cm, "逃げ%")
        mak_pct   = _safe_pct(cm, "まくり%") + _safe_pct(cm, "まくり差し%")
        sash_pct  = _safe_pct(cm, "差し%")

        passive_score = (nuki_pct + nige_pct * 0.5) / 100.0
        attack_score  = (mak_pct + sash_pct) / 100.0
        # 受動性 = 攻撃性の低さ（仕掛けに行かない → 自滅しない）
        passivity = max(0.0, 1.0 - attack_score * 0.7) + passive_score * 0.3

        # 穴スコア = win3 × 受動性 × 漁夫スコア（collapse_beneficiaryスコア）
        dark_score = round(win3 * passivity * (bene_score + 0.1), 4)

        # 根拠タグ（印コメント用）
        if nuki_pct >= 15.0:
            tag = "抜き系"
        elif win3 >= 0.65:
            tag = "高win3"
        elif passivity >= 0.7:
            tag = "受動型"
        else:
            tag = "漁夫"

        dark_horse_raw.append((w, dark_score, tag))

    dark_horse_raw.sort(key=lambda x: x[1], reverse=True)
    dark_horse_candidates = dark_horse_raw[:3]

    # ── Step3: 有効判定 ───────────────────────────────────────────────────────
    # is_valid 閾値を venue_c1_win_rate 連動に変更（(4)(5)対応）
    # race_judgment に格納済みの venue_c1_win_rate を参照する。
    # 荒れやすい会場（戸田=0.43等） → 閾値↓（穴が出やすい）
    # 堅い会場（住之江=0.65等）     → 閾値↑（本当に強い候補のみ）
    _vc1_dh          = float(race_judgment.get('venue_c1_win_rate') or 0.555)
    _vr_dh           = max(0.70, min(1.30, _vc1_dh / 0.555))
    _is_valid_thresh = round(0.15 * _vr_dh, 3)  # 基準閾値0.15を会場補正
    top_waku  = dark_horse_candidates[0][0] if dark_horse_candidates else None
    top_score = dark_horse_candidates[0][1] if dark_horse_candidates else 0.0
    is_valid  = top_score >= _is_valid_thresh

    # ── Step4: 根拠テキスト生成 ──────────────────────────────────────────────
    reason_parts = []
    if main_waku:
        reason_parts.append(f"主軸: {main_waku}号艇展開の外側を探索")
    for w, s, tag in dark_horse_candidates:
        reason_parts.append(f"{w}号艇【{tag}】 穴スコア{s*100:.0f}%")

    if not is_valid:
        reason_parts.append("→ 有効な穴候補なし（スコア不十分）")
    else:
        reason_parts.append(f"→ 最有力穴: {top_waku}号艇 スコア{top_score*100:.0f}%")

    return {
        "dark_horse_candidates": dark_horse_candidates,
        "top_waku":   top_waku,
        "top_score":  round(top_score, 4),
        "is_valid":   is_valid,
        "reason":     " / ".join(reason_parts),
    }


def _calc_honmei_score(r, tobi_prob_val, jizen_ev=None, first_prob_map=None, results_ctx=None,
                       venue_stats=None, race_judgment=None, st_kimete_master=None):
    """
    【6人相互作用モデル 印スコア v4】

    設計思想:
      「確率が高い艇を◎にする」でも「補正点が高い艇を◎にする」でもなく、
      「このレースのこのメンバー構成で最も主導権を握れる艇を◎にする」。

      Stage1: 相互作用スコア（0〜50pt）← 土台
        攻撃艇: _calc_attack_effectiveness による「この1号艇を崩せる力」
        1号艇:  _calc_w1_escape_score による「このメンバーに逃げられる力」
        → 確率モデル（first_prob_map）との加重平均でブレンド
          相互作用 × 0.55 + 確率シェア × 0.45

      Stage2: 状態補正（0〜30pt）← このレースの「今の状態」
        (2) 機力（0〜10pt）: モーター2連率ランク
        (3) jizen（0〜14pt）: 事前評価（展示での状態確認）
        (4) ST安定（0〜6pt）: FLYリスク・出遅れ癖

      確率ガード:
        first_prob_map の確率最大艇と自艇の確率差が大きいとき、
        相互作用スコアが高くても◎になれる上限を設ける。
        ただし旧版より緩め（25pt差で発動）: 相互作用モデルが
        確率を覆す場合もあり得るため。

      合計最大: 80pt
    """
    results   = results_ctx or []
    waku_str  = str(r["waku"])
    waku_idx  = int(r["waku"]) - 1
    _venue_stats = venue_stats or {}

    EQUAL_SHARE = 1.0 / 6.0

    # ======================================================
    # Stage1: 相互作用スコア (0〜50pt)
    # ======================================================

    # 1号艇の raw_cm を取得（全艇の攻撃有効性計算に必要）
    res1 = next((x for x in results if x["waku"] == "1"), None)
    w1_cm = res1.get("raw_cm", {}) if res1 else {}

    # 相互作用スコア（0〜1）
    if waku_str == "1":
        if res1:
            interaction_raw = _calc_w1_escape_score(res1, results, _venue_stats,
                                                    race_judgment=race_judgment,
                                                    st_kimete_master=st_kimete_master)
        else:
            interaction_raw = 0.5
    else:
        eff = _calc_attack_effectiveness(r, w1_cm, _venue_stats, results, st_kimete_master=st_kimete_master)
        interaction_raw = eff["total_score"]
        # 攻撃タイプを記録（展開考察のコメント用）
        r["_attack_type"] = eff["attack_type"]
        r["_attack_eff"]  = round(eff["total_score"], 4)

    # first_prob_map との加重ブレンド
    if first_prob_map:
        total_p = sum(first_prob_map.values()) or 1.0
        p_share = first_prob_map.get(waku_str, 0.0) / total_p
    else:
        total_r = sum((x.get("rel_win1") or 0) for x in results) or 1.0
        p_share = (r.get("rel_win1") or 0) / total_r

    # ── ryotate（展開エンジン）の逃げ/飛びスコアを取得 ──────────────────
    rj       = race_judgment or {}
    ryotate  = rj.get("ryotate", {}) or {}
    esc_s    = float(ryotate.get("escape_score", 50) or 50)
    tob_s    = float(ryotate.get("tobi_score",   30) or 30)
    ryo_diff = esc_s - tob_s   # 正=逃げ優勢、負=飛び優勢

    # ── Stage1スコアを ryotate で補正 ───────────────────────────────────
    # 【核心設計】
    # first_prob_map は「1号艇55%の統計的優位」を内包している。
    # 飛び優勢レースでも1号艇の確率シェアが高くなるバイアスがある。
    # このバイアスを ryotate_diff で直接打ち消す。
    #
    # 1号艇: 飛び優勢のとき → 逃げ力スコアを削る（interaction_rawが既に削られているが不十分）
    # 飛び艇（2〜6号艇）: 飛び優勢のとき → 攻撃有効性スコアにボーナスを加算
    if waku_str == "1":
        # 飛び優勢度に応じて1号艇の相互作用スコアをさらに抑制
        if ryo_diff >= 10:
            w1_adj = 1.0    # 逃げ優勢 → 抑制なし
        elif ryo_diff >= -10:
            w1_adj = 0.80   # 拮抗
        elif ryo_diff >= -25:
            w1_adj = 0.60   # 飛び優勢（画像のケース diff=-12 → 0.80）
        else:
            w1_adj = 0.40   # 飛び圧倒
        interaction_raw = interaction_raw * w1_adj

        # 確率ボーナスも飛び優勢時は削る（統計バイアスを打ち消す）
        p_share_adj = p_share * max(0.5, (ryo_diff + 50) / 100.0)
    else:
        # 飛び艇: 飛び優勢のとき攻撃有効性ボーナス
        if ryo_diff <= -10:
            # 飛び優勢レースで攻撃力がある艇を後押し
            tobi_bonus = min(abs(ryo_diff) / 100.0, 0.30)  # 最大+0.30
            interaction_raw = min(interaction_raw * (1.0 + tobi_bonus), 1.0)
        p_share_adj = p_share

    blended = interaction_raw * 0.55 + p_share_adj * 0.45
    excess  = p_share_adj - EQUAL_SHARE
    prob_bonus = max(0.0, excess) * 20.0
    pt_stage1  = min(blended * 50 + prob_bonus, 50.0)

    # ======================================================
    # Stage2: 状態補正 (0〜30pt)
    # ======================================================

    # ── (2) 機力点 (0〜10pt) ──────────────────────────────────────────────
    motor_vals = []
    for x in results:
        try:
            mv = float(x.get("motor2") or 0)
            if mv > 0:
                motor_vals.append((x["waku"], mv))
        except (ValueError, TypeError):
            pass
    if motor_vals:
        sorted_motors = sorted(motor_vals, key=lambda x: x[1], reverse=True)
        rank_map = {w: i for i, (w, _) in enumerate(sorted_motors)}
        my_rank  = rank_map.get(waku_str, len(sorted_motors) - 1)
        pt_motor = (1.0 - my_rank / max(len(sorted_motors) - 1, 1)) * 10.0
    else:
        pt_motor = 5.0

    # ── (3) jizen総合点 (0〜14pt) ─────────────────────────────────────────
    pt_jizen = 0.0
    if jizen_ev is not None:
        sym4 = {"◎": 3, "◎?": 2, "○": 2, "△": 1, "": 0, "-": 0}
        sym3 = {"A": 3, "B": 2, "C": 1, "D": 0, "E": 0, "-": 1}
        if waku_str == "1":
            in_sym  = (jizen_ev.get("in_nige")   or [""]   )[0]
            pt_jizen += sym4.get(in_sym,  0) / 3.0 * 4.0
        if waku_str != "1":
            ai_sym  = (jizen_ev.get("aisho")      or [""] * 6)[waku_idx]
            pt_jizen += sym4.get(ai_sym,  0) / 3.0 * 4.0
        ki_sym      = (jizen_ev.get("kiryoku")    or ["C"] * 6)[waku_idx]
        pt_jizen += sym3.get(ki_sym,  1) / 3.0 * 2.0
        jz_sym      = (jizen_ev.get("jizaisei")   or [""] * 6)[waku_idx]
        pt_jizen += sym4.get(jz_sym,  0) / 3.0 * 4.0
        if waku_str not in ("1", "2"):
            tk_sym  = (jizen_ev.get("tenkai")     or [""] * 6)[waku_idx]
            pt_jizen += sym4.get(tk_sym, 0) / 3.0 * 4.0
    pt_jizen = min(pt_jizen, 14.0)

    # ── (4) ST安定点 (0〜6pt) ─────────────────────────────────────────────
    all_sts = [(x["waku"], x.get("avg_st")) for x in results if x.get("avg_st") is not None]
    if len(all_sts) >= 2:
        sorted_sts  = sorted(all_sts, key=lambda x: x[1])
        st_rank_map = {w: i for i, (w, _) in enumerate(sorted_sts)}
        my_st_rank  = st_rank_map.get(waku_str, len(all_sts) - 1)
        pt_st       = (1.0 - my_st_rank / max(len(all_sts) - 1, 1)) * 6.0
    else:
        pt_st = 3.0

    # FLYリスク控除（状態補正からペナルティ）
    fly_pen = {"高": -15, "中": -7, "低": 0}.get(r.get("fly_label", "低"), 0)

    raw_score = pt_stage1 + pt_motor + pt_jizen + pt_st + fly_pen

    # ======================================================
    # 確率ガード（旧版より緩和: 差25pt以上で発動）
    # 相互作用モデルが確率を覆す正当な根拠がある場合を許容する
    # ======================================================
    if first_prob_map:
        max_p      = max(first_prob_map.values()) / (sum(first_prob_map.values()) or 1.0)
        max_excess = max_p - EQUAL_SHARE
        if max_excess >= 0:
            max_pt_stage1 = min(EQUAL_SHARE * 50 + max_excess * 2 * 50 + max_excess * 20, 50.0)
        else:
            max_pt_stage1 = max(0.0, max_p * 50)

        # 自艇の確率スコア相当値
        own_excess     = p_share - EQUAL_SHARE
        own_pt_stage1  = min(p_share * 50 + max(0.0, own_excess) * 20, 50.0)
        prob_gap       = max_pt_stage1 - own_pt_stage1

        if prob_gap >= 25:
            # 確率差が大きい → 相互作用が高くても上限キャップ
            cap = max_pt_stage1 + 30.0   # Stage2上限30ptまでは届ける
            raw_score = min(raw_score, cap)

    return raw_score


def _apply_jizen_honmei(results_ref, tobi_prob_val, jizen_ev, first_prob_map=None,
                        venue_stats=None, race_judgment=None, st_kimete_master=None):
    """
    【v7.0 攻め評価モデル】

    1号艇: _calc_w1_escape_score の結果で逃げ評価専用記号を付与。
           逃◎(>=0.55) / 逃○(>=0.40) / 逃△(>=0.25) / 逃×(<0.25)
           攻め記号（◎○▲△）の対象外とする。

    2〜6号艇: _calc_honmei_score（攻撃有効性スコア）で◎○▲△を付与。
              「この1号艇に対して攻め切れる力のランク」が記号の意味。

    設計意図:
      旧版は全6艇を同じ軸（6人相互作用スコア）で順位付けしていたため、
      1号艇の◎（逃げ評価）と2〜6号艇の◎（攻め評価）が混在していた。
      分離することで「1号が逃げられるか」「誰が崩すか」を別軸で読める。
    """
    _venue_stats = venue_stats or {}

    # ── 1号艇: 逃げ評価専用記号を付与 ──────────────────────────────────
    res1 = next((r for r in results_ref if r["waku"] == "1"), None)
    if res1 is not None:
        escape_score = _calc_w1_escape_score(
            res1, results_ref, _venue_stats, race_judgment=race_judgment,
            st_kimete_master=st_kimete_master
        )
        if escape_score >= 0.55:
            nige_mark = "逃◎"
        elif escape_score >= 0.40:
            nige_mark = "逃○"
        elif escape_score >= 0.25:
            nige_mark = "逃△"
        else:
            nige_mark = "逃×"
        res1["honmei"]       = nige_mark
        res1["nige_mark"]    = nige_mark
        res1["escape_score"] = round(escape_score, 4)

    # ── 2〜6号艇: 攻め評価スコアで◎○▲△を付与 ──────────────────────
    # rel_win1=None（マスタ未登録等）の艇もスキップせずスコア計算に参加させる。
    # スキップすると attack_scores が4艇未満になり◎が付かないレースが生じるため。
    attack_scores = []
    for i, r in enumerate(results_ref):
        if r["waku"] == "1":
            continue
        atk_score = _calc_honmei_score(
            r, tobi_prob_val,
            jizen_ev=jizen_ev,
            first_prob_map=first_prob_map,
            results_ctx=results_ref,
            venue_stats=_venue_stats,
            race_judgment=race_judgment,
            st_kimete_master=st_kimete_master,
        )
        attack_scores.append((i, atk_score))

    attack_scores.sort(key=lambda x: x[1], reverse=True)
    _hmap = {0: "◎", 1: "○", 2: "▲", 3: "△"}

    for r in results_ref:
        if r["waku"] != "1":
            r["honmei"] = " "

    for rank, (idx, _) in enumerate(attack_scores[:4]):
        results_ref[idx]["honmei"] = _hmap[rank]


def _calc_venue_stats(venue_stats_master, venue):
    """会場イン逃げ率・決まり手場平均・コース別1着率を返す（会場統計シートから取得）"""
    vs = venue_stats_master.get(venue, {})
    in_rate  = safe_float(vs.get("イン逃げ率"))
    kimari_avg = {
        "差し":      safe_float(vs.get("差し率")),
        "まくり":    safe_float(vs.get("まくり率")),
        "まくり差し": safe_float(vs.get("まくり差し率")),
    }
    areyasusa = round((1.0 - float(in_rate)) * 100, 1) if in_rate is not None else None
    # コース別1着率（1C〜6C）
    course_win_rates = {
        str(c): safe_float(vs.get(f"{c}C_1着率") or vs.get(f"{c}コース1着率"))
        for c in range(1, 7)
    }
    # ── コース別決まり手分布（scenario_engine の決まり手推定に使用） ────
    # 展開別残存マスタが venue_stats_master に格納されていない場合は
    # 会場統計の全体決まり手率をコース別に分解して近似する。
    # ※ 本来は展開別残存_会場別シートから集計するが、
    #   _calc_venue_stats 呼び出し時点では tenkai_venue_master が別変数のため
    #   ここでは全体決まり手率を全コース共通のフォールバックとして提供する。
    #   コース固有の分布は scenario_engine._get_venue_kimete_dist の
    #   全国平均フォールバックで補完される。
    v_sashi = safe_float(vs.get("差し率"),       0.0) or 0.0
    v_makuri = safe_float(vs.get("まくり率"),    0.0) or 0.0
    v_mz     = safe_float(vs.get("まくり差し率"), 0.0) or 0.0
    kimete_by_course = {}
    for c in range(2, 7):
        kimete_by_course[str(c)] = {
            "差し":       v_sashi,
            "まくり":     v_makuri,
            "まくり差し": v_mz,
        }

    return {
        "in_rate":          in_rate,
        "kimari_avg":       kimari_avg,
        "areyasusa_score":  areyasusa,
        "course_win_rates": course_win_rates,
        "c1_win_rate":      course_win_rates.get("1"),   # scenario_engine が参照
        "kimete_by_course": kimete_by_course,            # scenario_engine が参照
    }


# ============================================================
# 倶楽部流 事前評価 - メンバーデータ組み立て
# ============================================================
def build_jizen_members(results, course_master, player_master, motor_df, race_no):
    """
    calc_race_indicesの戻り値(results)から evaluate_all 用データを組み立てる。

    Parameters
    ----------
    results       : list[dict]  calc_race_indices の戻り値（艇番順）
    course_master : dict        {(選手名, コース文字列): {指数dict}}
    player_master : dict        {選手名: {指数dict}}
    motor_df      : pd.DataFrame or None  scrape_motor.py の出力
    race_no       : int or str

    Returns
    -------
    list[dict]  evaluate_all() に渡せる6要素リスト（インデックス0=1号艇）
    """
    def _s(val, default=0.0):
        """文字列/数値を float に変換。変換不能な場合は default を返す。
        【修正(8)】default=None の場合は 0.0 も "データなし" と同一視せず None として扱う。
        つまり:
          _s("0.0", 0.0)  → 0.0  （正常変換）
          _s(None, 0.0)   → 0.0  （デフォルト）
          _s(None, None)  → None （「データなし」を明示したい場合）
          _s("0.0", None) → 0.0  （正常変換: 0.0 は有効なデータ）
        """
        try:
            v = str(val).replace("%", "").strip()
            if v in ("", "None", "nan", "-", "★"):
                return default
            return float(v)
        except Exception:
            return default

    def _s_nullable(val):
        """float変換を試み、変換不能(欠損)は None を返す。0.0は有効値として区別する。"""
        try:
            v = str(val).replace("%", "").strip()
            if v in ("", "None", "nan", "-", "★"):
                return None
            return float(v)
        except Exception:
            return None

    # モーターデータをインデックス化 {艇番int: 2連対率float or None}
    motor_index = {}
    if motor_df is not None:
        race_motor = motor_df[motor_df["race_no"] == int(race_no)]
        for _, row in race_motor.iterrows():
            bn = int(row["boat_no"]) if pd.notna(row["boat_no"]) else 0
            rate = row["motor_2rate"] if pd.notna(row["motor_2rate"]) else None
            motor_index[bn] = rate

    # 1枠の逃げ率（相性計算用）
    res0 = results[0] if results else {}
    cm0 = res0.get("raw_cm", {})
    nige_rate_1 = _s(cm0.get("逃げ%"), 1.0)

    members = []
    for i, res in enumerate(results[:6]):
        waku = res.get("waku", str(i + 1))
        boat_no = int(waku) if str(waku).isdigit() else (i + 1)
        name = res.get("name_norm", res.get("name", "").replace("　","").replace(" ",""))
        course = str(res.get("course", str(i + 1))).strip()
        cm = res.get("raw_cm", {})
        pm = res.get("raw_pm", {})

        # ── イン逃げ ──
        # 1コースのイン1着率（選手指数マスタ）
        rate_1st_c1 = _s(pm.get("イン\n1着率") or pm.get("イン1着率"))
        # 1コースのST順位（選手指数マスタ）
        st_rank_raw = pm.get("ST順位\n(1コース)") or pm.get("ST順位(1コース)")
        st_rank_c1 = _s(st_rank_raw) if st_rank_raw not in (None, "", "None") else None
        # 自コース出走数が20件未満の場合に[!]を表示するフラグ
        # 旧: ★1着率フラグ（update_master.pyのコース別閾値）を流用
        # 新: 出走数を直接参照して一律20件未満を信頼不足とみなす
        _course_races = safe_float(cm.get("出走数"))
        STAR_RATE_MIN_SAMPLES = 20
        star_rate = (_course_races is not None and _course_races < STAR_RATE_MIN_SAMPLES)

        # ── 相性（自コースの攻め決まり手割合） ──
        sashi_pct  = _s(cm.get("差し%"))
        makuri_pct = _s(cm.get("まくり%"))
        mz_pct     = _s(cm.get("まくり差し%"))
        attack_rate = sashi_pct + makuri_pct + mz_pct  # 合計割合（0〜1）

        # ── 相性用: 自コースの平均ST（秒）── evaluate_jizen.calc_aisho に必要
        avg_st_self = res.get("avg_st")  # calc_race_indices で算出済み

        # ── 【修正】avg_st が None のとき ST順位から推定値でフォールバック ──────
        # 問題: コース別マスタにデータが少ない選手は avg_st = None になり
        #       _st_advantage_score が中立値0.5を返す → ST比較が完全に無効化される。
        #       2〜6号艇で全員Noneだと相性評価が全員空白になる（鳴門2R等で確認）。
        #
        # 解決: 選手指数マスタの「ST順位(Nコース)」を使って推定ST秒を計算する。
        #   ST順位 = 同レース内での速さ順位（1=最速〜6=最遅）
        #   推定式: avg_st_est = 0.12 + (rank - 1) / 5 × 0.08
        #     ST順位1.0 → 0.120秒（最速クラス）
        #     ST順位3.5 → 0.160秒（平均的）
        #     ST順位6.0 → 0.200秒（最遅クラス）
        #   これはコース別マスタ実測値より精度は落ちるが、
        #   「中立0.5固定」よりは大幅に正確なST比較が可能になる。
        if avg_st_self is None:
            _csr = res.get("course_st_rank")   # 進入コース別ST順位
            if _csr is not None:
                avg_st_self = round(0.12 + (_csr - 1) / 5 * 0.08, 4)

        # ── 相性用: 1号艇の被決まり手%（members[0] = 1号艇にのみ格納）──
        # 2号艇以降の相性評価で「この1号艇は差されやすいか/捲られやすいか」を参照する
        # 【修正(8)】_s_nullable を使って「差された回数ゼロ(0.0)」と「データなし(None)」を区別
        lose_sashi_rate  = None
        lose_makuri_rate = None
        lose_rate_reliable = False   # 【v6.4新設】C1敗戦数が十分あるか
        if i == 0:
            # cm0（1号艇のコース別マスタ）から被決まり手%を取得
            lose_sashi_rate  = _s_nullable(cm.get("差され%"))
            lose_makuri_rate = _s_nullable(cm.get("捲られ%"))
            # キー名ゆれ対応（0.0 は有効値なので None の場合のみ代替キーを試みる）
            if lose_sashi_rate is None:
                lose_sashi_rate  = _s_nullable(cm.get("差し被%") or cm.get("被差し%"))
            if lose_makuri_rate is None:
                lose_makuri_rate = _s_nullable(cm.get("まくり被%") or cm.get("被まくり%"))

            # ── 【v6.4新設】C1敗戦数による信頼度判定 ────────────────────────
            # update_master.py はC1敗戦数=「1コース出走で負けた回数」を集計している。
            # 件数が少ない（目安: 10件未満）場合、差され%・捲られ%はノイズが大きいため
            # evaluate_jizen 側で信頼度フラグを参照して重みを下げることができる。
            # C1敗戦数はコース別マスタの「C1敗戦数」列に格納されている（コース1行のみ有効）。
            c1_lose_cnt = safe_float(cm.get("C1敗戦数"))
            LOSE_RATE_MIN_SAMPLES = 10  # 信頼度ありとみなす最低件数
            lose_rate_reliable = (
                c1_lose_cnt is not None and c1_lose_cnt >= LOSE_RATE_MIN_SAMPLES
            )

        # ── 機力 ──
        motor_2rate = motor_index.get(boat_no)

        # ── 自在性（2〜6コースの多様性割合） ──
        course_rows = []
        for c in range(2, 7):
            ck = (name, str(c))  # name is already normalized
            crow = course_master.get(ck) or {}
            crow_copy = dict(crow)
            crow_copy["course"] = c
            crow_copy["1着数"]    = _s(crow.get("1着数"))
            crow_copy["差し(件)"]  = _s(crow.get("差し(件)"))
            crow_copy["まくり(件)"] = _s(crow.get("まくり(件)"))
            crow_copy["まくり差し%"] = _s(crow.get("まくり差し%"))
            course_rows.append(crow_copy)
        diversity_rate = calculate_diversity_rate(course_rows)
        jizaisei_rate  = _s(pm.get("自在性\n1着率") or pm.get("自在性1着率"))
        star_kimete    = bool(cm.get("★決手"))

        # ── 安定性評価用キー（evaluate_jizen.calc_jizaisei に渡す） ──
        # ST安定スコア（0〜100）
        st_stable_score = _s(
            pm.get("ST安定\nスコア") or pm.get("ST安定スコア"), default=None
        )
        # FLY数・FLY経過日数・出遅れ数・ST計測件数
        _fly_count_raw  = pm.get("FLY数")
        _fly_days_raw   = pm.get("FLY経過\n日数") or pm.get("FLY経過日数")
        _late_count_raw = pm.get("出遅れ数")
        _st_count_raw   = pm.get("ST\n計測件数") or pm.get("ST計測件数")
        fly_count_stab  = int(safe_float(_fly_count_raw,  0) or 0)
        fly_days_stab   = safe_float(_fly_days_raw) if _fly_days_raw not in (None, "", "nan") else None
        late_count_stab = int(safe_float(_late_count_raw, 0) or 0)
        st_count_stab   = int(safe_float(_st_count_raw,   1) or 1)

        # ── 展開（自コースの3連対率・まくり系） ──
        rate_3ren          = _s(cm.get("3連対率"))
        makuri_rate_t      = _s(cm.get("まくり%"))
        mz_rate_t          = _s(cm.get("まくり差し%"))

        members.append({
            # イン逃げ
            "rate_1st_c1":  rate_1st_c1,
            "st_rank_c1":   st_rank_c1,
            "star_rate":    star_rate,
            # 相性（v3対応: 攻め武器・ST・被決まり手）
            "nige_rate":         nige_rate_1,
            "attack_rate":       attack_rate,
            "sashi_rate":        sashi_pct,         # 差し%（相性用・展開用共通）
            "makuri_rate":       makuri_pct,         # まくり%（相性用・展開用共通）
            "makuri_zashi_rate": mz_pct,             # まくり差し%（相性用・展開用共通）
            "avg_st_self":       avg_st_self,         # 【修正(2)】自コース平均ST秒（相性用）
            "lose_sashi_rate":   lose_sashi_rate,     # 【修正(2)】1号艇のみ: 差され%（相性用）
            "lose_makuri_rate":  lose_makuri_rate,    # 【修正(2)】1号艇のみ: 捲られ%（相性用）
            "lose_rate_reliable": lose_rate_reliable, # 【v6.4新設】C1敗戦数>=10ならTrue
            # 機力
            "motor_2rate":  motor_2rate,
            # 自在性（後方互換のため残存・evaluate_jizen側では未使用）
            "diversity_rate": diversity_rate,
            "jizaisei_rate":  jizaisei_rate,
            "star_kimete":    star_kimete,
            # 安定性評価用（evaluate_jizen.calc_jizaisei v4）
            "st_stable_score": st_stable_score,
            "fly_count":       fly_count_stab,
            "fly_days":        fly_days_stab,
            "late_count":      late_count_stab,
            "st_count":        st_count_stab,
            # 展開（makuri_rate / makuri_zashi_rate は相性用と同値のため共用）
            "rate_3ren":  rate_3ren,
            # 【v7追加】コース番号（evaluate_jizen._calc_weapon_score で使用）
            "course_int": int(course) if str(course).isdigit() else (i + 1),
        })

    return members

# ============================================================
# サンプルシートからレイアウトをコピーして新シートを作成
# ============================================================
