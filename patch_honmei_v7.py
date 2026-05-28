# -*- coding: utf-8 -*-
"""
load_race.py への差分修正案 — v7.0
====================================
変更① _apply_jizen_honmei
  ・1号艇を攻め記号（◎○▲△）の対象外にする
  ・1号艇には逃げ評価専用記号「逃◎/逃○/逃△/逃×」を付与する
  ・2〜6号艇のみ攻撃有効性スコアで◎○▲△を付与する

変更② _needs_orkaeshi_12
  ・折り返し判定に「記号付き艇」の緩和条件を追加する
  ・○以上（◎○）の記号を持つ艇は条件③の閾値を0.5→0.3に緩和する

変更③ 買い目出力フォーマット
  ・折り返しペアを「A＝B－C / B＝A－C」形式で1行にまとめる
  ・数値シートの「本命記号」行ラベルを「攻め記号（2〜6）」に変更する

====================================
適用方法: 各ブロックを load_race.py の該当関数に置き換える
"""

# ============================================================
# 変更① _apply_jizen_honmei の置き換え
# ============================================================
# --- 変更前 (行 7033〜7055) ---
# def _apply_jizen_honmei(results_ref, tobi_prob_val, jizen_ev, first_prob_map=None,
#                         venue_stats=None, race_judgment=None):
#     final_scores = [
#         (i, _calc_honmei_score(r, ...))
#         for i, r in enumerate(results_ref)
#         if r.get("rel_win1") is not None
#     ]
#     final_scores.sort(key=lambda x: x[1], reverse=True)
#     _hmap = {0: "◎", 1: "○", 2: "▲", 3: "△"}
#     for r in results_ref:
#         r["honmei"] = " "
#     for rank, (idx, _) in enumerate(final_scores[:4]):
#         results_ref[idx]["honmei"] = _hmap[rank]

# --- 変更後 ---
NIGE_MARK_MAP = {
    # escape_score（0〜1）→ 逃げ評価記号
    # _calc_w1_escape_score の戻り値をそのまま使う
    # 閾値は jizen の ①イン逃げ ◎○△ と合わせる
    "high":   "逃◎",   # escape_score >= 0.55
    "mid":    "逃○",   # escape_score >= 0.40
    "low":    "逃△",   # escape_score >= 0.25
    "none":   "逃×",   # escape_score <  0.25
}

def _apply_jizen_honmei(results_ref, tobi_prob_val, jizen_ev, first_prob_map=None,
                        venue_stats=None, race_judgment=None):
    """
    【v7.0 攻め評価モデル】

    1号艇: 逃げ評価専用記号（逃◎/逃○/逃△/逃×）を付与。
           攻め記号（◎○▲△）の対象外。
    2〜6号艇: 攻撃有効性スコアで◎○▲△を付与。
              「この1号艇に対して攻め切れる力のランク」が記号の意味。

    設計意図:
      旧版は全6艇を同じ軸（6人相互作用スコア）で順位付けしていたため、
      1号艇の◎（逃げ評価）と2〜6号艇の◎（攻め評価）が混在していた。
      分離することで「1号が逃げられるか」「誰が崩すか」を別軸で読める。
    """
    _venue_stats = venue_stats or {}

    # ── 1号艇: 逃げ評価記号を付与 ──────────────────────────────────────
    res1 = next((r for r in results_ref if r["waku"] == "1"), None)
    if res1 is not None:
        escape_score = _calc_w1_escape_score(
            res1, results_ref, _venue_stats, race_judgment=race_judgment
        )
        if escape_score >= 0.55:
            nige_mark = NIGE_MARK_MAP["high"]
        elif escape_score >= 0.40:
            nige_mark = NIGE_MARK_MAP["mid"]
        elif escape_score >= 0.25:
            nige_mark = NIGE_MARK_MAP["low"]
        else:
            nige_mark = NIGE_MARK_MAP["none"]
        res1["honmei"]       = nige_mark
        res1["nige_mark"]    = nige_mark          # 専用フィールドにも格納
        res1["escape_score"] = round(escape_score, 4)

    # ── 2〜6号艇: 攻め評価スコアで◎○▲△を付与 ──────────────────────
    w1_cm = res1.get("raw_cm", {}) if res1 else {}
    attack_scores = []
    for r in results_ref:
        if r["waku"] == "1":
            continue
        if r.get("rel_win1") is None:
            continue
        atk_score = _calc_honmei_score(
            r, tobi_prob_val,
            jizen_ev=jizen_ev,
            first_prob_map=first_prob_map,
            results_ctx=results_ref,
            venue_stats=_venue_stats,
            race_judgment=race_judgment,
        )
        attack_scores.append((results_ref.index(r), atk_score))

    attack_scores.sort(key=lambda x: x[1], reverse=True)
    _hmap = {0: "◎", 1: "○", 2: "▲", 3: "△"}

    # 2〜6号艇の honmei を初期化
    for r in results_ref:
        if r["waku"] != "1":
            r["honmei"] = " "

    for rank, (idx, _) in enumerate(attack_scores[:4]):
        results_ref[idx]["honmei"] = _hmap[rank]


# ============================================================
# 変更② _needs_orkaeshi_12 の修正（記号を参照する条件を追加）
# ============================================================
# --- 変更前の条件③ ---
#     if rev_first_prob < avg_first_prob * 0.5:
#         return False

# --- 変更後 ---
# （_build_buys のクロージャ内なので、外から honmei_map を参照できるよう
#   _build_buys の引数に honmei_map を追加するか、results から取得する）
#
# _needs_orkaeshi_12 の条件③を以下に置き換える：
#
#     # ③ 折り返し1着艇の1着確率
#     rev_first_waku = combo_lookup[rev_key]["first"]
#     rev_first_prob = first_prob_map.get(rev_first_waku, 0)
#     avg_first_prob = sum(first_prob_map.values()) / max(len(first_prob_map), 1)
#
#     # 記号が○以上の艇は閾値を緩和（0.5 → 0.3）
#     # 「攻め力が評価されている艇なら、確率が低めでも折り返しを追加する価値がある」
#     _honmei_of_rev = next(
#         (r.get("honmei", "") for r in results if r["waku"] == rev_first_waku), ""
#     )
#     _orkaeshi_thresh = 0.3 if _honmei_of_rev in ("◎", "○") else 0.5
#
#     if rev_first_prob < avg_first_prob * _orkaeshi_thresh:
#         return False
#     return True
#
# ※ _needs_orkaeshi_12 は _suggest_3rentan のクロージャなので
#   results（外側スコープ）を参照可能。変更は条件③の部分のみ。

ORKAESHI_12_PATCH = '''
    def _needs_orkaeshi_12(base_combo, rev_key):
        """
        1着折り返し（A-1-B vs 1-A-B）が必要かを判定する。

        不要と判断する条件:
          ① s1_prob >= 0.75: 逃げ確率が圧倒的 → 飛び役1着はほぼない
          ② 折り返しコンボの確率が本体の1/4未満: 展開として非現実的
          ③ 折り返し1着艇の1着確率が全艇平均の0.5倍未満（記号○以上なら0.3倍に緩和）

        いずれか1つでも該当すれば不要と判断。
        """
        if rev_key not in combo_lookup:
            return False
        base = combo_lookup.get(base_combo)
        rev  = combo_lookup[rev_key]
        if not base:
            return True
        # ① 逃げ圧倒的
        if s1_prob >= 0.75:
            return False
        # ② 確率比
        if base["prob"] > 0 and rev["prob"] / base["prob"] < 0.25:
            return False
        # ③ 折り返し1着艇の1着確率（記号○以上は閾値緩和）
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
'''


# ============================================================
# 変更③ 買い目出力フォーマット（行 9062〜9078 周辺）
# ============================================================
# --- 変更前 ---
# line = f"{orr}{c['combo']}  {c['prob_pct']:.1f}%{hs_score_str}"

# --- 変更後 ---
# 折り返しペアを「A＝B－C / B＝A－C (確率A% / 確率B%)」にまとめる。
# ペアリングは _orkaeshi フラグを持つ combo とその base を突き合わせる。

def _format_kaime_lines(cands):
    """
    買い目リストを人間が読みやすい形式にフォーマットする。

    通常買い目:   1-2-3  5.9%
    1着折り返し:  1＝2-3 / 2＝1-3  (5.9% / 2.5%)
    2着3着折返:   1-2＝3 / 1-3＝2  (5.9% / 3.0%)
    """
    combo_map = {c["combo"]: c for c in cands}
    used = set()
    lines_nige     = []
    lines_tobi     = []
    lines_sc       = []
    lines_fallback = []
    lines_dh       = []
    lines_other    = []

    for c in cands:
        key = c["combo"]
        if key in used:
            continue

        sc = c.get("scenario", "")
        is_orkaeshi    = c.get("is_orkaeshi",    False) or c.get("_orkaeshi",    False)
        is_orkaeshi_23 = c.get("is_orkaeshi_23", False) or c.get("_orkaeshi_23", False)
        is_sc_bet      = c.get("is_sc_bet",      False)
        is_fallback    = c.get("is_fallback_bet", False)
        is_dh          = c.get("is_dh_bet",       False)

        parts = key.split("-")
        if len(parts) != 3:
            line = f"  {key}  {c.get('prob_pct', 0):.1f}%"
            _append_line(line, sc, is_sc_bet, is_fallback, is_dh,
                         lines_nige, lines_tobi, lines_sc, lines_fallback, lines_dh, lines_other)
            used.add(key)
            continue

        first, second, third = parts

        # 1着折り返しペア: 1-A-B と A-1-B
        if not is_orkaeshi_23:
            rev12_key = f"{second}-{first}-{third}"
            if rev12_key in combo_map and rev12_key not in used:
                rev12 = combo_map[rev12_key]
                # 「A＝B－C / B＝A－C」形式
                line = (
                    f"  {first}＝{second}-{third}  {c.get('prob_pct',0):.1f}%"
                    f"  /  {second}＝{first}-{third}  {rev12.get('prob_pct',0):.1f}%"
                )
                used.add(key)
                used.add(rev12_key)
                _append_line(line, sc, is_sc_bet, is_fallback, is_dh,
                             lines_nige, lines_tobi, lines_sc, lines_fallback, lines_dh, lines_other)
                continue

        # 2着3着折り返しペア: 1-A-B と 1-B-A
        if not is_orkaeshi:
            rev23_key = f"{first}-{third}-{second}"
            if rev23_key in combo_map and rev23_key not in used:
                rev23 = combo_map[rev23_key]
                # 「1-A＝B / 1-B＝A」形式
                line = (
                    f"  {first}-{second}＝{third}  {c.get('prob_pct',0):.1f}%"
                    f"  /  {first}-{third}＝{second}  {rev23.get('prob_pct',0):.1f}%"
                )
                used.add(key)
                used.add(rev23_key)
                _append_line(line, sc, is_sc_bet, is_fallback, is_dh,
                             lines_nige, lines_tobi, lines_sc, lines_fallback, lines_dh, lines_other)
                continue

        # ペアが見つからない単独買い目
        used.add(key)
        line = f"  {key}  {c.get('prob_pct', 0):.1f}%"
        _append_line(line, sc, is_sc_bet, is_fallback, is_dh,
                     lines_nige, lines_tobi, lines_sc, lines_fallback, lines_dh, lines_other)

    sections = []
    if lines_nige:
        sections.append(f"── 🟢逃げ軸 {len(lines_nige)}点 ──")
        sections.extend(lines_nige)
    if lines_tobi:
        sections.append(f"── 🔴飛び軸 {len(lines_tobi)}点 ──")
        sections.extend(lines_tobi)
    if lines_sc:
        sections.append(f"── 🎣潰れ受益 {len(lines_sc)}点 ──")
        sections.extend(lines_sc)
    if lines_fallback:
        sections.append(f"── ❸逃げ残存 {len(lines_fallback)}点 ──")
        sections.extend(lines_fallback)
    if lines_dh:
        sections.append(f"── ❹穴ヒモ {len(lines_dh)}点 ──")
        sections.extend(lines_dh)
    if lines_other:
        sections.append(f"── その他 {len(lines_other)}点 ──")
        sections.extend(lines_other)

    total = len(cands)
    header = f"【計{total}点】＝=折返ペア 🎣=潰れ ❸=逃げ残存 ❹=穴"
    return header + "\n" + "\n".join(sections)


def _append_line(line, sc, is_sc_bet, is_fallback, is_dh,
                 lines_nige, lines_tobi, lines_sc, lines_fallback, lines_dh, lines_other):
    if is_fallback:
        lines_fallback.append(line)
    elif is_dh:
        lines_dh.append(line)
    elif "逃げ" in sc:
        lines_nige.append(line)
    elif "飛び" in sc:
        lines_tobi.append(line)
    elif "潰れ" in sc or is_sc_bet:
        lines_sc.append(line)
    else:
        lines_other.append(line)


# ============================================================
# 変更④ write_item_block の「本命記号」行ラベルを変更
# ============================================================
# 行 8366 付近:
# --- 変更前 ---
# write_item_block(row, "選手情報", "本命記号", FILL_SEC_B, FILL_ITEM_P, ...)

# --- 変更後 ---
# write_item_block(row, "選手情報", "攻め記号\n（2〜6号）", FILL_SEC_B, FILL_ITEM_P, ...)
#
# ※ 1号艇の honmei フィールドには「逃◎」等が入るため、
#   そのまま表示すると「逃◎」が評価列に出る。
#   新聞上で 1号艇の評価列を「逃げ評価」に切り替えるには
#   write_race_flat の 1号艇行の評価セルだけラベルを変えるか、
#   nige_mark フィールドを別列に出力する。
#
# 最小コスト案: 既存の「評価」列はそのまま使い、
#   1号艇セルの値が「逃◎/逃○/逃△/逃×」であることを凡例行に追記する。
LEGEND_TEXT = (
    "◎○▲△ = 攻め力評価（2〜6号艇）\n"
    "逃◎○△× = 逃げ力評価（1号艇専用）"
)

# ============================================================
# honmei_prob_mismatch チェックの更新（行 9919〜9934 付近）
# ============================================================
# 変更後は1号艇が◎を持たなくなるため、◎の検索対象を2〜6号艇に限定する。
# --- 変更前 ---
# _honmei_w = next(
#     (str(r["waku"]) for r in results if r.get("honmei") == "◎"), None
# )
# --- 変更後 ---
# _honmei_w = next(
#     (str(r["waku"]) for r in results
#      if r.get("honmei") == "◎" and r["waku"] != "1"), None
# )
MISMATCH_CHECK_PATCH = '''
                    _honmei_w = next(
                        (str(r["waku"]) for r in results
                         if r.get("honmei") == "◎" and r["waku"] != "1"), None
                    )
'''


# ============================================================
# 変更サマリー
# ============================================================
print("""
=== load_race.py v7.0 修正サマリー ===

【変更①】_apply_jizen_honmei（行 7033〜7055）
  ・1号艇 → _calc_w1_escape_score の結果で「逃◎/逃○/逃△/逃×」を付与
  ・2〜6号艇 → _calc_honmei_score（攻撃有効性スコア）で「◎○▲△」を付与
  ・触るコード: 関数本体の置き換えのみ

【変更②】_needs_orkaeshi_12 の条件③（行 5068〜5072）
  ・条件③の閾値を記号○以上の艇は 0.5 → 0.3 に緩和
  ・「攻め力を認められた艇なら first_prob が低めでも折り返し追加」
  ・触るコード: 条件③の if 文 5行の置き換えのみ

【変更③】買い目フォーマット（行 9062〜9078 周辺）
  ・折り返しペアを「1＝2-3 / 2＝1-3  (5.9% / 2.5%)」形式に
  ・_format_kaime_lines() を新関数として追加し、既存のループを呼び出しに変更
  ・触るコード: lines_nige/lines_tobi 等の生成ループをまるごと置き換え

【変更④】行ラベル（行 8366）
  ・「本命記号」→「攻め記号（2〜6号）」に変更
  ・凡例テキストを追記（LEGEND_TEXT）

【変更⑤】honmei_prob_mismatch チェック（行 9923〜9924）
  ・◎検索の対象から1号艇を除外

副作用チェック:
  ・_should_skip_race の「印↔確率不一致」チェック: ◎が2〜6号のみになるため
    1号艇が確率最大でも mismatch にならない → 意図通り（逃げシナリオで1号確率最大は正常）
  ・_suggest_3rentan の honmei_map 参照: honmei_waku が「逃◎」にはならない
    （逃◎は1号艇専用フィールドで、honmei_map["◎"] には2〜6号艇しか来ない）
  ・既存テストケース: evaluate_jizen のテストには影響なし
""")
