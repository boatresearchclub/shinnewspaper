# -*- coding: utf-8 -*-
"""
lr_calc.py  ─  指数計算 / 展開分析 / レース判定
分割元: load_race.py
"""
import re, sys, pathlib, statistics
import pandas as pd
from lr_config import _VENUE_COURSE_ADJ, VENUE_COURSE_ADJ_CSV
from lr_utils import safe_float, _get_cm_val, KIMARI_COL_MAP
from lr_masters import _lookup_name_course, _lookup_player

# ── 循環import回避: lr_suggest / lr_probs は関数内で遅延importする ──
# 下記の関数を使用箇所の直前で import する:
#   lr_suggest: _judge_w1_escape, _judge_main_player, _judge_dark_horse,
#               _suggest_3rentan, _apply_jizen_honmei
#   lr_probs:   _calc_3rentan_probs_v2

# ── scenario_engine / lr_suggest / lr_probs は load_race.py 側で管理 ──────
# calc_race_indices は bet_suggestions を生成しないため、これらのインポートは不要。
# SCENARIO_ENGINE_AVAILABLE フラグは load_race.py に一本化済み。

# ──────────────────────────────────────────────────────────────────────────────
# 【②】グレード補正係数の読み込み
# update_master.py が data/grade_factor.csv に書き出した実測係数を起動時に1回読み込む。
# ファイルがなければデフォルト値（バックテスト暫定値）を使用。
# 係数の意味: G1/SG1着率 × 係数 ≒ 一般戦での推定1着率
# ──────────────────────────────────────────────────────────────────────────────
import os as _os

_GRADE_FACTOR_DEFAULT = {
    "1": 1.15, "2": 1.25, "3": 1.30,
    "4": 1.35, "5": 1.40, "6": 1.45,
}
_GRADE_FACTOR_CSV = _os.path.join(
    _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
    "data", "grade_factor.csv"
)

def _load_grade_factor() -> dict:
    """grade_factor.csv を読み込んでコース→係数のdictを返す。"""
    try:
        if _os.path.exists(_GRADE_FACTOR_CSV):
            import csv as _csv
            result = {}
            with open(_GRADE_FACTOR_CSV, encoding="utf-8-sig") as f:
                for row in _csv.DictReader(f):
                    result[str(row["コース"])] = float(row["補正係数"])
            if result:
                return result
    except Exception:
        pass
    return dict(_GRADE_FACTOR_DEFAULT)

# モジュールロード時に1回だけ読み込む
_GRADE_FACTOR_BY_COURSE: dict = _load_grade_factor()

def calc_race_indices(venue, race_no, players, course_master, player_master, ininage_master, venue_stats_master, venue_course_master=None, tenkai_venue_master=None, tenkai_national_master=None, st_kimete_master=None, kaiho_venue_master=None, kaiho_national_master=None, jizen_eval=None, race_grade="一般"):
    """
    1レース分の指数を計算して返す。

    【進入コース前提】
    本システムは「枠なり進入」を前提として分析する。
    CSVに「想定コース」列がある場合はその値を使用するが、
    ない場合・空値の場合は 枠番 = コース として扱う（枠なり進入とみなす）。

    進入変更が確認された場合は race_judgment["nyujo_henkou"] = True を
    セットすることで _should_skip_race が無条件に見送り推奨を返す。

    改善(1)  会場別コースマスタ (venue_course_master) を優先参照。
            選手の当該会場での実績があればそちらを使い、なければ全国マスタにフォールバック。
    改善(3)  ハイブリッド係数を動的計算。
            会場の実績量（会場統計レース数）と選手の当該会場実績量（信頼度）に応じて
            「選手実績 : 会場特性」の比率を動的に調整する。
    """
    results = []
    if venue_course_master is None:
        venue_course_master = {}
    if tenkai_venue_master is None:
        tenkai_venue_master = {}
    if tenkai_national_master is None:
        tenkai_national_master = {}
    if st_kimete_master is None:
        st_kimete_master = {}
    if kaiho_venue_master is None:
        kaiho_venue_master = {}
    if kaiho_national_master is None:
        kaiho_national_master = {}

    # 【問題C修正】_blend_tsをループ外に定義（毎ループの再生成を防ぐ）
    def _blend_ts(ts_val, flat_val, eff_n, full_n=20.0):
        """時系列補正値とフラット平均を有効走数に応じてブレンドして返す。
        eff_n >= full_n → 時系列補正100%採用
        eff_n = 0      → フラット平均100%採用"""
        if ts_val is None and flat_val is None:
            return None
        if ts_val is None:
            return flat_val
        if flat_val is None:
            return ts_val
        t = min(eff_n / full_n, 1.0)
        return ts_val * t + flat_val * (1.0 - t)

    for p in players:
        name_raw = str(p.get("選手名","")).strip()
        # 末尾の年齢数字を除去（例: "熊本英一47" → "熊本英一"、"芦澤　望48" → "芦澤　望"）
        name_raw = re.sub(r'\s*\d+\s*$', '', name_raw).strip()
        name = name_raw.replace("　", "").replace(" ", "")  # スペース除去でマスタキーと統一
        # [修正2] lzh_to_csv.py の出力列名は「艇番」。「枠」にも後方互換対応
        waku = str(p.get("枠", p.get("艇番", ""))).strip()
        # 【枠なり前提】CSVに「想定コース」列があればその値を使用。
        # ない場合・空値（nan/None/空文字）の場合は 枠番 = コース として扱う（枠なり進入を想定）。
        # 進入変更が判明した場合は race_judgment["nyujo_henkou"] = True をセットすること。
        _course_raw = str(p.get("想定コース", "")).strip()
        course = _course_raw if _course_raw not in ("", "nan", "None") else waku

        # ── 改善(1): 会場別コースマスタを優先参照 ────────────────────────────
        # 【軽微(2)改善】ルックアップ関数経由で完全一致→4文字前方一致の順で検索
        # 優先度: 会場別コースマスタ（選手×会場×コース） > 全国コース別マスタ
        vc_key = (name, venue, course)
        vcm = venue_course_master.get(vc_key)
        if vcm is None and len(name) >= 6:
            # 【修正】5文字名（姓4字+名1字、例: 大豆生田蒼）では name[:4] が姓のみになり
            # 誤マッチを引き起こすため、前方一致フォールバックは6文字以上に限定する
            vcm = venue_course_master.get((name[:4], venue, course))

        cm = _lookup_name_course(course_master, name, course)
        cm = cm or {}
        pm = _lookup_player(player_master, name)
        pm = pm or {}

        # ── 【修正(1)(2)(4)】会場別コースマスタと全国マスタの統合 ────────────────────
        # 【修正(1)】vcm存在かつvc_trust=0.0 と vcm=None を明示的に区別する。
        # 【修正(2)】win1_rate は純粋な「選手個人の1着率推定値」のみ。venue_rateは後段で混ぜる。
        # 【修正(4)】時系列有効走数（eff_n）による時系列補正の信頼制御
        #   eff_n >= 20走 → 時系列補正100%採用 / eff_n=0 → フラット平均100%
        #   ※ _blend_ts はループ外で定義済み

        # 全国マスタの有効走数を取得
        cm_eff_n = safe_float(cm.get("時系列有効走数"), 0.0) or 0.0
        _ts  = safe_float(cm.get("時系列補正1着率"))
        _fl  = safe_float(cm.get("1着率"))
        global_win1 = _blend_ts(_ts, _fl, cm_eff_n)
        _ts  = safe_float(cm.get("時系列補正3連対率"))
        _fl  = safe_float(cm.get("3連対率"))
        global_win3 = _blend_ts(_ts, _fl, cm_eff_n)

        if vcm is not None:
            vc_trust_raw = safe_float(vcm.get("信頼度"), 0.0) or 0.0  # 0.0〜1.0
            if vc_trust_raw > 0.0:
                # 会場別実績あり＆信頼度あり → vc_trustに応じて会場別と全国をブレンド
                vc_trust = vc_trust_raw
                # 会場別コースマスタの有効走数で時系列補正を制御
                vc_eff_n = safe_float(vcm.get("時系列有効走数"), 0.0) or 0.0
                _ts  = safe_float(vcm.get("時系列補正1着率"))
                _fl  = safe_float(vcm.get("1着率"))
                vc_win1 = _blend_ts(_ts, _fl, vc_eff_n)
                _ts  = safe_float(vcm.get("時系列補正3連対率"))
                _fl  = safe_float(vcm.get("3連対率"))
                vc_win3 = _blend_ts(_ts, _fl, vc_eff_n)
                if vc_win1 is not None and global_win1 is not None:
                    win1_rate = vc_win1 * vc_trust + global_win1 * (1.0 - vc_trust)
                elif vc_win1 is not None:
                    win1_rate = vc_win1
                else:
                    win1_rate = global_win1
                if vc_win3 is not None and global_win3 is not None:
                    win3_rate = vc_win3 * vc_trust + global_win3 * (1.0 - vc_trust)
                elif vc_win3 is not None:
                    win3_rate = vc_win3
                else:
                    win3_rate = global_win3
            else:
                # vcm存在するが信頼度=0 → 実質データ不足。全国マスタのみ使用
                vc_trust  = 0.0
                win1_rate = global_win1
                win3_rate = global_win3
        else:
            # vcm=None → 会場別実績なし。全国マスタのみ使用
            vc_trust  = 0.0
            win1_rate = global_win1
            win3_rate = global_win3

        gen_win3 = safe_float(pm.get("3連対率\n(一般戦)"))
        avg_st   = safe_float(cm.get("コース別\n平均ST"))
        st_rank  = safe_float(pm.get("ST順位\n(1コース)"))

        # ── 進入コース別ST順位（相性評価のフォールバック用） ──────────────────
        # avg_st（コース別平均ST秒）が取れない選手向けの代替データ。
        # 選手指数マスタには「ST順位\n(Nコース)」が全コース分格納されている。
        # ST順位 = 同レース内での速さ順位（1=最速〜6=最遅）
        # build_jizen_members 側で avg_st が None のとき推定ST秒に変換して使用。
        course_st_rank = safe_float(
            pm.get(f"ST順位\n({course}コース)") or pm.get(f"ST順位({course}コース)")
        )

        # ── コース別マスタ（cm）からST順位を取得（平均ST順位の正値）──────────
        # AB列「コース別ST順位」は avg_st（AA列）と同じ cm から取得する。
        avg_st_rank_val = safe_float(
            cm.get("コース別\nST順位") or cm.get("コース別ST順位")
        )

        # ── 【会場特化決まり手ブレンド】────────────────────────────────────
        # 目的: _calc_attack_effectiveness の raw_cm に渡す決まり手%を
        #       「全国コース別マスタ」だけでなく「会場別コースマスタ」と
        #       vc_trust で加重ブレンドする。
        #
        # 従来は vcm の決まり手%は _build_kimari（表示用文字列）にしか使われず、
        # シナリオ分岐の攻撃有効性計算には全国値しか入っていなかった。
        # これにより「この選手がこの会場のこのコースでどう動くか」が
        # attack_effectiveness に反映されなかった。
        #
        # ブレンド式: blended = vc_val * vc_trust + global_val * (1 - vc_trust)
        #   vc_trust = 0  → 全国値のみ（会場別実績なし or 不足）
        #   vc_trust = 1  → 会場別値のみ（十分な会場実績あり）
        # ──────────────────────────────────────────────────────────────────
        _KIMETE_CATS = ["逃げ%", "差し%", "まくり%", "まくり差し%", "抜き%"]
        if vcm and vc_trust > 0.0:
            blended_cm = dict(cm)  # 全国マスタをベースにコピー
            for _kcat in _KIMETE_CATS:
                _vc_val  = safe_float(_get_cm_val(vcm, _kcat))
                _gl_val  = safe_float(_get_cm_val(cm,  _kcat))
                if _vc_val is not None and _gl_val is not None:
                    blended_cm[_kcat] = round(_vc_val * vc_trust + _gl_val * (1.0 - vc_trust), 4)
                elif _vc_val is not None:
                    blended_cm[_kcat] = _vc_val
                # _vc_val=None の場合は全国値をそのまま維持（上書き不要）
        else:
            blended_cm = cm  # 会場実績なし → 全国マスタそのまま

        # 決まり手（会場別があればそちらを優先・表示用文字列）
        # 1号艇（コース1進入）は被決まり手%（差され/まくられ/まくり差され）
        # 2〜6号艇は攻撃決まり手%（逃げ/差し/まくり等）
        if course == 1:
            kimari = _build_kimari_c1_vuln(cm)
        else:
            kimari = _build_kimari(vcm if vcm else cm)

        # ── データ不足チェック ──────────────────────────────────────────────
        # 【改善】同コース出走数の閾値を5走→15走に引き上げ（update_master.pyと統一）
        # 15走未満の選手は個人実績の信頼性が低いため data_missing=True として
        # win1_rate を薄めて会場平均に引き寄せる。新聞には「※」マークを付与。
        #
        # 【設計大原則】級別(A1/B2等)で選手能力を評価しない。
        #   理由①: A1でもグレード戦非常連の選手は一般戦データが豊富
        #   理由②: B2でもFLY等ペナルティで一時降格した実力者が存在する
        #   理由③: 同じA1でも実力差は大きく、級別は能力の絶対値を示さない
        #   → 「実際の出走実績の質と量」でのみ評価する。
        #
        # 【①G1常連ペナルティ解除】
        #   update_master.py の G1/SG補完（G1補完走数列）が入っている選手は
        #   一般戦データが乏しいのではなく「グレード戦に多く出ているだけ」であり、
        #   実力は十分ある。cm_scarce=False にしてM6ペナルティを解除する。
        #   ・G1補完走数 >= 10走 → グレード常連とみなし cm_scarce を解除
        #   ・新聞表示は「※」ではなく「🏆」マーク（グレード常連識別用）
        CM_SCARCE_THRESH = 15   # 旧: 20
        cm_missing = not cm
        cm_count      = safe_float(cm.get("出走数"), 0)
        g1_補完走数   = safe_float(cm.get("G1補完走数"), 0) or 0.0  # update_master.py が付与
        # 【バグ修正】is_grade_jouren の判定を G1補完走数 だけでなく
        # senshu_master の「選手タイプ」列も参照して補完する。
        # 問題: G1補完走数は「★フラグが立っている かつ G1/SGデータあり」の行のみ付く。
        # 蒲郡3コースなど特定会場でG1/SG出走数が10走未満の場合、G1補完走数 < 10 となり
        # is_grade_jouren=False → cm_scarce=True → data_missing=True になっていた。
        # 修正: pmの選手タイプが「グレードメイン」の場合もグレード常連と判定する。
        _pm_player_type = pm.get("選手タイプ", "")
        is_grade_jouren = (g1_補完走数 >= 10) or (_pm_player_type == "グレードメイン")

        if is_grade_jouren:
            # グレード常連: 一般戦実績が少なくても「データ不足」扱いにしない
            cm_scarce = False
        else:
            cm_scarce  = (not cm_missing) and (cm_count is not None) and (cm_count < CM_SCARCE_THRESH)

        pm_missing = not pm
        pm_count   = safe_float(pm.get("総出走数"), 0)
        pm_scarce  = (not pm_missing) and (pm_count is not None) and (pm_count < 10)
        data_missing = cm_missing or cm_scarce or pm_missing or pm_scarce
        # 新聞表示用マーク: グレード常連→「🏆」、一般戦15走未満→「※」、それ以外→なし
        scarce_mark     = cm_scarce          # Trueのとき新聞側で「※」を付ける
        grade_jouren_mark = is_grade_jouren  # Trueのとき新聞側で「🏆」を付ける
        missing_reasons = []
        if cm_missing:
            missing_reasons.append(f"コース{course}実績なし")
        elif cm_scarce:
            missing_reasons.append(f"コース{course}実績{int(cm_count)}走（15走未満※）")
        elif is_grade_jouren:
            missing_reasons.append(f"コース{course}一般戦{int(cm_count)}走・G1補完{int(g1_補完走数)}走🏆")
        if pm_missing:
            missing_reasons.append("選手マスタ未登録")
        elif pm_scarce:
            missing_reasons.append(f"総実績{int(pm_count)}走")
        missing_reason_str = " / ".join(missing_reasons) if missing_reasons else ""

        # ──────────────────────────────────────────────────────────────────
        # 【②】グレード常連の win1_rate 補正
        # ──────────────────────────────────────────────────────────────────
        # is_grade_jouren 確定後・FLY数取得前のタイミングで実行。
        # 対象: is_grade_jouren=True（G1/SG補完走数10走以上）の選手
        # 処理: 全戦種合算1着率 × グレード補正係数 で win1_rate を上方修正
        #
        # 使う値の優先順位:
        #   ① 全戦種合算1着率（マスタの"全戦種合算1着率"列）があればそれをベース
        #   ② なければ win1_rate（上段で確定済みの一般戦ベース値）をそのまま使用
        #
        # ブレンド（一般戦データが増えるほど補正を薄める）:
        #   一般戦0走  → 補正後100% / 一般戦10走 → 50% / 一般戦20走 → 0%（通常に収束）
        # ──────────────────────────────────────────────────────────────────
        if is_grade_jouren and win1_rate is not None:
            _ippan_count = safe_float(cm.get("出走数"), 0) or 0.0
            if _ippan_count < 15:
                _zenshu_win1 = safe_float(cm.get("全戦種合算1着率"))
                _base_win1   = _zenshu_win1 if _zenshu_win1 is not None else win1_rate
                _gf          = _GRADE_FACTOR_BY_COURSE.get(str(course), 1.20)
                _corrected   = min(_base_win1 * _gf, 0.95)
                _blend_t     = _ippan_count / 15.0
                win1_rate    = _corrected * (1.0 - _blend_t) + win1_rate * _blend_t

        # FLY数・出遅れ数・FLY経過日数（選手指数マスタ pm から取得）
        # 【修正(4)】FLY経過日数を使って影響度を精密判定
        # 旧: FLY数>=2→高、>=1→中 のみ → FLY明け直後(60日)と1年後(365日)が同判定
        # 新: FLY経過日数を加味:
        #   経過日数 < 90  日: 出場停止明け直後 → 判定を1段階引き上げ（中→高等）
        #   経過日数 < 180 日: 影響残存期間    → 素直に使用
        #   経過日数 >= 180 日: 影響ほぼ消滅    → FLY数に依らず「低」
        _fly_count    = int(safe_float(pm.get("FLY数"),    0) or 0)
        _late_count   = int(safe_float(pm.get("出遅れ数"), 0) or 0)
        _fly_days_raw = pm.get("FLY経過日数")
        _fly_days     = safe_float(_fly_days_raw) if _fly_days_raw not in (None, "", "nan") else None

        if _fly_count == 0:
            _fly_label = "低"
        elif _fly_days is not None:
            if _fly_days >= 180:
                # FLY後180日超 → 影響ほぼ消滅
                _fly_label = "低"
            elif _fly_days < 90:
                # 出場停止明け直後 → 1段階引き上げ
                _fly_label = "高"  # (FLY1回でも高)
            else:
                # 90〜180日: 通常判定
                _fly_label = "高" if _fly_count >= 2 else "中"
        else:
            # 経過日数不明（update_master.py 更新前の旧データ）→ 旧来判定にフォールバック
            _fly_label = "高" if _fly_count >= 2 else "中"

        # ── 【追加(5)】FLY後走数によるST慎重係数 ────────────────────────────────
        # FLY直後は選手が慎重になり avg_st が遅れる傾向がある。
        # 「FLY後何走目か」（fly_after_n）を取得し avg_st にオフセットを加算する。
        # オフセット値は競艇の実態（FLY直後は平均+0.02〜0.03秒遅れる）を参考に設定。
        #   fly_after_n=1: 出場停止明け直後   → +0.030秒
        #   fly_after_n=2:                     → +0.020秒
        #   fly_after_n=3:                     → +0.012秒
        #   fly_after_n=4:                     → +0.006秒
        #   fly_after_n=5:                     → +0.002秒
        #   fly_after_n>=6 または FLYなし      → 補正なし
        # ※ FLY経過日数（fly_days）が180日超の場合は影響消滅として補正しない。
        _FLY_ST_OFFSET = {1: 0.030, 2: 0.020, 3: 0.012, 4: 0.006, 5: 0.002}
        _fly_after_n_raw = pm.get("FLY後走数")
        _fly_after_n = int(safe_float(_fly_after_n_raw) or 0) if _fly_after_n_raw not in (None, "", "nan") else 0
        _st_caution_offset = 0.0
        if _fly_count > 0 and _fly_after_n > 0:
            if _fly_days is None or _fly_days < 180:
                _st_caution_offset = _FLY_ST_OFFSET.get(_fly_after_n, 0.0)

        # avg_st にST慎重オフセットを適用（Noneの場合は適用しない）
        _avg_st_adjusted = avg_st
        if avg_st is not None and _st_caution_offset > 0:
            _avg_st_adjusted = round(avg_st + _st_caution_offset, 4)

        # ── モーター2連率キー拡張（番組表自動取得への対応） ────────────────────
        # 現在は p（選手入力データ）の列名ゆれに対応するキー群から取得。
        # download_results.py + scrape_program.py（今後追加）が番組表から
        # モーター2連率を取得するようになった場合も同じキー名で受け取れるよう
        # "モーター2連対率" / "motor_2rate" も候補に追加する。
        _motor2_raw = str(p.get(
            "モーター2連率",
            p.get("M2率",
            p.get("モータ2連",
            p.get("モーター2連対率",   # 番組表スクレイプ時の列名
            p.get("motor_2rate", ""))  # 英字キー（API連携用）
        )))).strip()

        results.append({
            "waku":       waku,
            "name":       name_raw,  # 表示用（スペースあり）
            "name_norm":  name,      # マスタ検索用（スペースなし）
            "kumi":       str(p.get("級別", p.get("組",""))).strip(),
            "motor2":     _motor2_raw,
            "course":     course,
            "win1_rate":      win1_rate,
            "win3_rate":      win3_rate,
            "avg_st":         _avg_st_adjusted,  # ST慎重オフセット適用済み
            "avg_st_raw":     avg_st,            # 補正前の元値（デバッグ用）
            "st_caution_offset": _st_caution_offset,  # 適用したオフセット量
            "fly_after_n":    _fly_after_n,      # FLY後走数（0=不明or補正不要）
            "st_rank":        st_rank,
            "course_st_rank": course_st_rank,   # 進入コース別ST順位（フォールバック用）
            "avg_st_rank":    avg_st_rank_val,  # 平均ST順位 = コース別マスタのST順位（AB列）
            "kimari":     kimari,
            "kosetsu":    str(p.get("今節成績","")).strip(),
            "tenji_time": safe_float(p.get("展示タイム", p.get("展示", p.get("展示ST","")))),
            "raw_cm":        blended_cm,   # 会場別×全国ブレンド済み決まり手%（vc_trust加重）
            "raw_cm_global": cm,          # 全国マスタ原値（デバッグ・フォールバック用）
            "raw_pm":     pm,
            "raw_vcm":    vcm or {},     # 会場別コースマスタ原値（デバッグ用）
            "vc_trust":   vc_trust,      # 会場別実績の信頼度（0〜1）
            "data_missing":       data_missing,
            "missing_reason":     missing_reason_str,
            "scarce_mark":        scarce_mark,        # 同コース15走未満フラグ（新聞表示用「※」）
            "grade_jouren_mark":  grade_jouren_mark,  # G1/SG常連フラグ（新聞表示用「🏆」）
            "g1_補完走数":        int(g1_補完走数),   # G1/SG補完走数（デバッグ用）
            "cm_count":           int(cm_count) if cm_count is not None else 0,  # 一般戦出走数（デバッグ用）
            "fly_count":  _fly_count,   # FLY数（0以上の整数）
            "fly_label":  _fly_label,   # F/ST影響ラベル（高/中/低）
            "late_count": _late_count,  # 出遅れ数
        })

    # ── 【修正(2)(7)】動的ハイブリッド係数: 「選手実績 vs 会場特性」のブレンド ──────────
    # win1_rate は上段で「会場別マスタ×全国マスタ」をブレンド済みの純粋な選手個人実績値。
    # 「その選手実績値をどれだけ信頼するか」を cm_count と vc_trust の両方で決定する。
    #
    # 【修正(7)】vc_trust を後段にも引き継いで w_player 上限を拡張する。
    #   修正(2)で「上段ブレンドに vc_trust を消費」したが、それは
    #   「会場別 vs 全国の個人実績ブレンド」への使用であり、
    #   「個人実績全体 vs 会場特性」のブレンド比率を決める後段とは別の軸。
    #   → 二重混合ではなく「直交した2つの調整」なので後段でも参照してよい。
    #
    # w_player の計算式（修正(7)版）:
    #   cm_trust = min(cm_count / 30, 1.0) × 0.60   全国出走数による基礎信頼度（最大0.60）
    #   vc_bonus = vc_trust × 0.30                   会場別実績が十分なら最大+0.30
    #   w_player = min(cm_trust + vc_bonus, 0.90)    上限0.90（会場特性を最低10%保証）
    #
    # 具体例:
    #   会場別実績なし(vc=0)  全国30走 → 0.60+0.00 = 0.60
    #   会場別実績あり(vc=1)  全国30走 → 0.60+0.30 = 0.90（上限）
    #   会場別実績あり(vc=0.5) 全国10走 → 0.20+0.15 = 0.35
    #   全実績なし(vc=0, cm=0)         → 0.00+0.00 = 0.00 → 会場特性100%
    #
    # ※ キー名正規化は load_masters() 内で実施済み（"1コース1着率"等のエイリアスを追加）

    COURSE_AVG_WIN = {
        "1": 0.555, "2": 0.137, "3": 0.134,
        "4": 0.111, "5": 0.066, "6": 0.021,
    }

    vs = venue_stats_master.get(venue, {})

    # ── 【修正(5)】会場のコース別1着率: R番号別と全体平均を加重平均でブレンド ────────
    # 【旧方式の問題】R番号別1着率が存在すれば無条件に優先していた。
    #   R別はサンプルが少ない（例: 同会場の同R番号は年間50〜200レース程度）ため
    #   たまたまの偏りをシグナルと誤認する「過学習的なノイズ混入」が起きていた。
    #
    # 【修正(6)】R別1着率とコース全体平均のブレンド比率を動的化。
    # 旧方式: W_RC = 0.30 固定 → サンプルが少ない会場でもRC別を30%参照してノイズが混入。
    # 新方式: 会場の総レース数（= 統計の信頼性）に応じてW_RCを動的決定。
    #   計算式: W_RC = clip(レース数 / 3000, 0.05, 0.30)
    #     レース数3000以上（約12年分）→ W_RC = 0.30（上限：RC別を最大30%参照）
    #     レース数1500程度（約6年）  → W_RC = 0.15
    #     レース数300以下（約1年）   → W_RC = 0.05（ほぼ全体平均のみ）
    #   根拠: R別は年間約120〜150レースのデータ。
    #   統計的に安定するには最低5〜8年(600〜1200件)が目安。
    #   上限を0.30に抑えてRC別に過剰依存しないよう設計。
    _venue_race_count = safe_float(vs.get("レース数"), 0) or 0
    W_RC = float(min(max(_venue_race_count / 3000.0, 0.05), 0.30))

    venue_course_rate = {}
    for c in range(1, 7):
        rc_key     = f"{c}C_{race_no}R1着率"   # キー名正規化済み
        course_key = f"{c}コース1着率"          # キー名正規化済み
        nat_avg    = COURSE_AVG_WIN[str(c)]
        rc_val     = safe_float(vs.get(rc_key))
        course_val = safe_float(vs.get(course_key))
        if rc_val is not None and course_val is not None:
            # 両方存在 → 加重平均（R別30%、全体70%）
            blended = rc_val * W_RC + course_val * (1.0 - W_RC)
        elif course_val is not None:
            blended = course_val
        elif rc_val is not None:
            blended = rc_val
        else:
            blended = nat_avg
        venue_course_rate[str(c)] = blended

    for r in results:
        course     = str(r["course"])
        venue_rate = venue_course_rate.get(course, COURSE_AVG_WIN.get(course, 0.10))

        # 【修正(7)】全国出走数 + 会場別実績信頼度の両方でw_playerを決定（上限0.90）
        cm_count_w = safe_float(r.get("raw_cm", {}).get("出走数"), 0) or 0
        vc_trust   = r.get("vc_trust", 0.0)
        cm_trust   = min(cm_count_w / 30.0, 1.0) * 0.60   # 全国出走数による基礎信頼度（最大0.60）
        vc_bonus   = vc_trust * 0.30                        # 会場別実績ボーナス（最大+0.30）
        w_player   = min(cm_trust + vc_bonus, 0.90)        # 上限0.90（会場特性を最低10%保証）
        w_venue    = 1.0 - w_player                         # 0.10〜1.0

        # ── 【新修正: 全国平均比スケール換算（vc_trust対応版）】────────────────────────
        # 問題: win1_rate のスケールが vcm の有無によって変わる。
        #   - vcm=None:  win1_rate は全国コース別実績（全国スケール）
        #   - vcm有り:   win1_rate = vc_win1 * vc_trust + global_win1 * (1-vc_trust)
        #               vc_win1 は「当該会場での絶対的1着率（会場スケール）」
        #               → win1_rate は会場スケールと全国スケールの混合
        #
        # 解決: win1_rate のスケールに合わせた基準値 base でratio計算する。
        #   base = venue_rate * vc_trust + nat_avg_c * (1 - vc_trust)
        #     vc_trust=0.0 → base = nat_avg_c（全国比換算のみ）
        #     vc_trust=1.0 → base = venue_rate → ratio=win1/venue_rate
        #                    win1_scaled = venue_rate * ratio = win1（スケール変換なし）
        #
        # 効果:
        #   vcm無し・荒れ会場: 全国比換算で過大評価を解消（戸田1号艇 54.8%→50.9%）
        #   vcm有り・荒れ会場: 会場スケールの実績をそのまま反映（過小評価なし）
        #   全国平均会場: 変化なし
        #   ratio は [0.25, 4.0] にクリップして外れ値を防ぐ。
        _RATIO_MIN, _RATIO_MAX = 0.25, 4.0
        nat_avg_c = COURSE_AVG_WIN.get(course, 0.10)  # コースの全国平均1着率
        # win1_rate のスケールに合わせた基準値（vc_trust で全国<->会場を補間）
        _ratio_base = venue_rate * vc_trust + nat_avg_c * (1.0 - vc_trust)
        _ratio_base = max(_ratio_base, 1e-6)  # ゼロ除算防止

        if r["win1_rate"] is not None and r["win1_rate"] > 0:
            ratio = max(_RATIO_MIN, min(r["win1_rate"] / _ratio_base, _RATIO_MAX))
            win1_scaled = venue_rate * ratio  # 会場スケールでの個人実績推定値
            r["_raw_win"] = win1_scaled * w_player + venue_rate * w_venue
        elif r["win1_rate"] == 0.0:
            # 【問題B修正】出走したが1着なし → 会場特性をw_venue分だけ使用。
            r["_raw_win"] = venue_rate * w_venue
        else:
            # データなし → 会場特性100%
            r["_raw_win"] = venue_rate

    # ── 【修正(4)】Laplace smoothingフロア: 均等フロアで正規化歪みを防ぐ ────────────
    # 【旧方式の問題】フロア値を「全国平均×10%」にしていたため
    #   6コースのフロア ~= 0.0021（0.2%）と極端に小さく、
    #   この値が正規化の分母に混入することで1〜5コースの確率が不当に圧縮されていた。
    #
    # 【新方式】全コース共通で「全国平均の最小値（6コース=2.1%）の50%」= 0.0105 を下限とする。
    #   これにより「確率0の艇を救済する」目的は維持しつつ、
    #   極小フロアによる正規化への影響を実質ゼロに近づける。
    COURSE_WIN_FLOOR_UNIFORM = 0.021 * 0.50   # ~= 0.0105（全コース共通）
    for r in results:
        r["_raw_win"] = max(r["_raw_win"], COURSE_WIN_FLOOR_UNIFORM)

    # ── 【SG/G1専用補正】────────────────────────────────────────────────────
    # SG・G1はトップ選手が揃うため一般戦マスタで学習したキャリブレーション補正が
    # 1号艇を過剰に割り引く方向に働く。以下の3点を調整する。
    #
    # (1) w_player 上限引き上げ（0.90 → 0.95）
    #   SG/G1選手は実績数が多く個人データの信頼性が高い。
    #   会場特性より個人実績を優先することで精度が上がる。
    #
    # (2) キャリブレーション補正の緩和（_calib_relax に乗算係数を追加）
    #   一般戦のバックテスト誤差 0.0698 はSG/G1には過剰。
    #   SG/G1では1号艇の実際の逃げ率が高いため補正を20%緩和する。
    #
    # (3) 飛びスコア（tobi_prob）の下方補正（×0.80）
    #   SG/G1の1号艇はSTが安定しており外から簡単には飛ばされない。
    #   一般戦と同じ飛びスコア計算では飛び確率が過大評価される。
    _IS_GRADE_RACE = race_grade in ("SG", "G1")

    if _IS_GRADE_RACE:
        # (1) w_player 上限引き上げ（既に計算済みの _raw_win を再補正）
        for r in results:
            course_r   = str(r["course"])
            venue_rate = venue_course_rate.get(course_r, COURSE_AVG_WIN.get(course_r, 0.10))
            cm_count_w = safe_float(r.get("raw_cm", {}).get("出走数"), 0) or 0
            vc_trust   = r.get("vc_trust", 0.0)
            cm_trust   = min(cm_count_w / 30.0, 1.0) * 0.60
            vc_bonus   = vc_trust * 0.35          # SG/G1: vc_bonusを0.30→0.35に拡大
            w_player   = min(cm_trust + vc_bonus, 0.95)   # 上限0.90→0.95
            w_venue    = 1.0 - w_player
            # _raw_win を w_player=0.95 ベースで再計算
            nat_avg_c  = COURSE_AVG_WIN.get(course_r, 0.10)
            vc_trust_r = r.get("vc_trust", 0.0)
            _ratio_base = venue_rate * vc_trust_r + nat_avg_c * (1.0 - vc_trust_r)
            _ratio_base = max(_ratio_base, 1e-6)
            if r["win1_rate"] is not None and r["win1_rate"] > 0:
                ratio = max(0.25, min(4.0, r["win1_rate"] / _ratio_base))
                win1_scaled = venue_rate * ratio
                r["_raw_win"] = win1_scaled * w_player + venue_rate * w_venue
            elif r["win1_rate"] == 0.0:
                r["_raw_win"] = venue_rate * w_venue
            # else: データなし → 会場特性100%のまま
        # Laplace smoothingフロアを再適用
        for r in results:
            r["_raw_win"] = max(r["_raw_win"], COURSE_WIN_FLOOR_UNIFORM)

    # ── 【修正(3)(6)・問題A修正】キャリブレーション補正（_raw_winスケール対応版）──────────
    # 【問題A】修正(3)で「_raw_winに補正を適用」に変えたが、
    #   breakpointsの閾値が旧方式（rel_win1 = 0〜1スケール）のままだった。
    #   _raw_win の実際の範囲は 1号艇:0.02〜0.60、外コース:0.01〜0.10 であり、
    #   旧閾値 p=0.35 未満は補正なし → 2〜6号艇が全て補正なしになっていた。
    #
    # 【修正】breakpointsを _raw_win の実際のスケールに合わせて再設計する。
    #   目標: バックテストCal誤差0.0698を反映しつつ全艇に段階的に補正を掛ける。
    #   設計方針:
    #     ・p < 0.10 → 補正なし（6コース等の極小確率帯は信頼できる）
    #     ・p = 0.15 → scale = 0.990（2%の緩い補正）
    #     ・p = 0.25 → scale = 0.975
    #     ・p = 0.35 → scale = 0.960
    #     ・p = 0.45 → scale = 0.945
    #     ・p = 0.55 → scale = 0.930（1号艇強いケースの核心補正 ≒ Cal誤差0.0698相当）
    #     ・p >= 0.65 → scale = 0.920（上限なし: _raw_winは最大0.60程度のため実質到達しない）
    #
    # 【修正(6)連携】荒れ会場では緩和スケール(relax)を適用:
    #   relax = clip(venue_c1_rate / 0.555, 0.70, 1.0)
    #   戸田(c1~=0.430) → relax=0.775 → 補正を22.5%緩和

    _venue_c1_rate = venue_course_rate.get("1", 0.555)
    _calib_relax   = float(min(max(_venue_c1_rate / 0.555, 0.70), 1.0))
    # (2) SG/G1: キャリブレーション補正を20%緩和（一般戦の誤差補正はSGには過剰）
    if _IS_GRADE_RACE:
        _calib_relax = min(1.0, _calib_relax * 1.20)

    def _calibrate(p_raw, relax=1.0):
        """_raw_winスケール(0〜1)にキャリブレーション補正を適用して返す。
        relax: 1.0=通常補正、<1.0=補正を緩和（荒れ会場向け）"""
        if p_raw is None:
            return None
        p = float(p_raw)
        # _raw_winスケール向けbreakpoints（旧の0.35〜1.01から0.10〜1.01に再設計）
        breakpoints = [
            (0.10, 1.000),
            (0.15, 0.990),
            (0.25, 0.975),
            (0.35, 0.960),
            (0.45, 0.945),
            (0.55, 0.930),
            (0.65, 0.920),
            (1.01, 0.920),
        ]
        if p < breakpoints[0][0]:
            return p  # 極小確率帯は補正なし
        for i in range(len(breakpoints) - 1):
            x0, s0 = breakpoints[i]
            x1, s1 = breakpoints[i + 1]
            if x0 <= p < x1:
                t = (p - x0) / (x1 - x0)
                scale_full = s0 + t * (s1 - s0)
                scale = 1.0 - (1.0 - scale_full) * relax
                return p * scale
        scale_full = breakpoints[-1][1]
        scale = 1.0 - (1.0 - scale_full) * relax
        return p * scale

    # _raw_win は 0〜1 程度のスケール。_calibrate に relax（荒れ会場緩和係数）を渡す。
    for r in results:
        r["_raw_win"] = _calibrate(r["_raw_win"], relax=_calib_relax) or r["_raw_win"]

    # ── 【追加(4)】モーター2連率補正を _raw_win（rel_win1の前段）に反映 ────────────
    # 従来は attack_score（攻撃力スコア）にのみ motor2_boost を掛けていた。
    # rel_win1（1着確率の相対評価）にも反映することで、印・買い目選択にもモーター差が出る。
    #
    # 補正式: motor2_boost = clip(1.0 + (motor2_val - m2_mean) / 10 * 0.12, 0.94, 1.06)
    #   全艇平均+5pt優秀 → ×1.06 / -5pt劣悪 → ×0.94
    #   attack_scoreの ÷10×0.16 より係数を小さく（÷10×0.12）して過補正を防ぐ。
    #   motor2 が取得できていない艇はスキップ（補正なし）。
    #
    # ※ 番組表スクレイプ（scrape_program.py）が未実装の場合、
    #   motor2 は番組表CSV（lzh_to_csv.py 出力）に含まれていれば自動で入る。
    #   含まれていない場合は safe_float が None を返し補正なしとなる（後方互換）。
    _m2_vals = [safe_float(r.get("motor2")) for r in results if safe_float(r.get("motor2")) is not None]
    if _m2_vals:
        _m2_mean = sum(_m2_vals) / len(_m2_vals)
        for r in results:
            _m2v = safe_float(r.get("motor2"))
            if _m2v is not None:
                _m2_boost = max(0.94, min(1.06, 1.0 + (_m2v - _m2_mean) / 10.0 * 0.12))
                r["_raw_win"] = r["_raw_win"] * _m2_boost
                r["_motor2_boost_rel"] = round(_m2_boost, 4)  # デバッグ用
            else:
                r["_motor2_boost_rel"] = 1.0

    total_raw = sum(r["_raw_win"] for r in results)
    for r in results:
        if total_raw > 0:
            r["rel_win1"] = r["_raw_win"] / total_raw * 100
        else:
            r["rel_win1"] = None

    # rel_win1_cal は rel_win1 と同値（補正済み値の別名として下流コードと互換性を保つ）
    for r in results:
        r["rel_win1_cal"] = r["rel_win1"]
    
    # 3連対率：絶対評価（コース別実績をそのまま%表示）
    # 相対化するとメンバーレベルが見えなくなるため絶対値を使用
    for r in results:
        if r["win3_rate"] is not None:
            r["abs_win3"] = round(r["win3_rate"] * 100, 1)  # 例: 0.625 → 62.5%
        else:
            r["abs_win3"] = None
    
    # ==========================================================================
    # 本命記号（多面評価スコアによる総合印）◎→○→▲→△
    # ──────────────────────────────────────────────────────────────────────────
    # 【旧方式の問題】rel_win1（オリジナル1着率）のみで機械的に順位付け
    #   → FLYリスクが高い艇でも◎がつく
    #   → 飛びシナリオ高確率なのに1号艇◎という矛盾が起きる
    #
    # 【新方式: 総合印スコア】
    #   基礎点  = rel_win1 × 0.60
    #   FLY高  : -8pt  / FLY中: -4pt
    #   イン逃げ◎(1号艇): +8pt / ○: +4pt / 空白: -5pt  ← jizen確定後に適用
    #   飛び相性◎(tobi_prob>=55の2〜6号艇): +10pt / ○: +5pt ← jizen確定後に適用
    #
    # 【印の意味】◎>○>▲>△
    #   ◎: 総合スコア1位（本命）  ○: 2位（対抗）
    #   ▲: 3位（単穴）           △: 4位（穴）
    #
    # ※ここではFLYペナルティのみ適用した仮印を付ける。
    #   jizen_eval確定後に main() で _apply_jizen_honmei() を呼んで最終確定する。
    # ==========================================================================

    # _calc_honmei_score / _apply_jizen_honmei はトップレベルで定義（下記参照）

    # 仮印（jizen未確定。相互作用モデルで計算し、jizen確定後に _apply_jizen_honmei で上書き）
    # venue_stats をここで構築して相互作用モデルに渡す
    from lr_suggest import _calc_venue_stats, _calc_honmei_score  # 循環import回避のため遅延import
    _venue_stats_pre = _calc_venue_stats(venue_stats_master, venue)
    # rel_win1=None（マスタ未登録等）もスキップしない。
    # スキップすると4艇未満しか計算されず◎が付かないレースが生じるため。
    _honmei_scores_pre = [
        (i, _calc_honmei_score(r, 0, jizen_ev=None, results_ctx=results,
                               venue_stats=_venue_stats_pre,
                               race_judgment=None,
                               st_kimete_master=st_kimete_master))   # 仮印計算時点ではrace_judgment未確定
        for i, r in enumerate(results)
    ]
    _honmei_scores_pre.sort(key=lambda x: x[1], reverse=True)

    honmei_map = {0: "◎", 1: "○", 2: "▲", 3: "△"}  # ◎>○>▲>△
    for rank, (idx, _) in enumerate(_honmei_scores_pre[:4]):
        results[idx]["honmei"] = honmei_map[rank]
    for r in results:
        if "honmei" not in r:
            r["honmei"] = " "

    # _apply_jizen_honmei はトップレベルで定義（下記参照）

    # ── 新機能(4)：展示タイム偏差値（レース内相対評価） ──────────────────────
    # 【軽微(1)注意】展示タイムは当日展示航走後にしか取得できない。
    # 前日予想CSV（締め切り前スクレイプ）では値が存在しないため tenji_hensa は None になる。
    # 表示側では None の場合「-（前日）」と表示し、当日版で上書きされることを明示する。
    tenji_vals = [r["tenji_time"] for r in results if r.get("tenji_time") is not None]
    _has_tenji_data = len(tenji_vals) >= 2  # 展示タイムデータが揃っているか
    if _has_tenji_data:
        t_mean = statistics.mean(tenji_vals)
        t_stdev = statistics.stdev(tenji_vals) if len(tenji_vals) > 1 else 1
        for r in results:
            t = r.get("tenji_time")
            if t is not None and t_stdev > 0:
                # 競艇の展示タイムは速い（小さい）ほど良いので逆転
                r["tenji_hensa"] = round(50 - (t - t_mean) / t_stdev * 10, 1)
            else:
                r["tenji_hensa"] = None
    else:
        # 前日時点では展示タイム未取得 → 明示的にNoneを設定
        for r in results:
            r["tenji_hensa"] = None
        if not tenji_vals:
            pass  # 前日出力では正常（展示前）

    # 想定スリット（平均STでソート）
    sortable = [(r["waku"], r["avg_st"]) for r in results if r["avg_st"] is not None]
    sortable.sort(key=lambda x: x[1])
    slit = "-".join([s[0] for s in sortable])
    if not slit:
        slit = "-".join([r["waku"] for r in results])
    
    # ==========================================================================
    # circle_pct（2着優位度）・idx3（3着指数）
    # ──────────────────────────────────────────────────────────────────────────
    # 【設計思想】
    #   「この会場でこの出走メンバーが戦ったとき何が起きるか」を計算する。
    #   枠番の固定統計ではなく、各艇の決まり手・ST・1号艇との関係性から
    #   相互作用モデルでスコアを算出する。
    #
    # ──────────────────────────────────────────────────────────────────────────
    # ■ circle_pct（2着優位度）：「イン逃げ時に2着を取れる攻め手の強さ」
    #
    #   コース別に異なる攻め手を評価し、1号艇との具体的な関係性で補正する。
    #
    #   2枠: 差し特化コース
    #     差し% × ST優位(vs 1号艇) × 1号艇の被差し脆弱性
    #
    #   3枠: まくり差し主体
    #     (まくり差し% × 1.2 + まくり%) × ST優位
    #     × 2枠差し力ペナルティ（2枠が強いと進路を塞がれる）
    #
    #   4枠: まくり主体
    #     (まくり% + まくり差し%) × ST優位
    #     × 3枠壁ペナルティ（3枠のまくり力が強いと被る）
    #
    #   5・6枠: 展開待ち・まくり
    #     (まくり% + まくり差し%) × ST優位 × 外枠減衰
    #
    #   ※ 全艇の絶対スコアを算出し、合計100%に正規化して circle_pct とする。
    #   ※ 選手実績データが不足する場合は全国コース別平均でフォールバック。
    #
    # ──────────────────────────────────────────────────────────────────────────
    # ■ idx3（3着指数）：「イン逃げ時に3着に残る固有の力」
    #
    #   純3着率（3着以内率 - 2着率）を主軸に据える。
    #   「2着を取りこぼしても3着に粘り込む能力」を選手個人の実績から評価する。
    #
    #   ベーススコア = 純3着率(選手実績) × trust + 会場枠別純3着率 × (1-trust)
    #   → 選手実績が豊富なほど個人差が出る。データ不足なら会場値に寄せる。
    #   → 最大値=100にスケーリング（ただし枠番固定にならないよう分散を確保）
    # ==========================================================================

    venue_frame   = ininage_master.get(venue, {})            # {枠番str: 会場2着率float}
    venue_3rd_map = ininage_master.get(venue, {}).get("_3rd", {})  # {枠番str: 会場3着以内率float}
    MIN_ININAGE_COUNT = 5

    # ── 全国コース別平均（フォールバック用） ──────────────────────────────────
    # 【修正(2): 2026-04-05】イン逃げ実績1,196件（2025-10〜2026-03）の実測値に更新。
    #   2着実績: 2号=34.4%, 3号=28.5%, 4号=19.8%, 5号=11.5%, 6号=5.7%
    #   3着実績: 2号=24.9%, 3号=25.5%, 4号=21.7%, 5号=15.8%, 6号=12.1%
    #   純3着率(3着実績 - 2着実績):
    #     2号=-9.5% → 3着<2着（2着に集中）→ pure3は2着率の35%で推計
    #     3号=負 → 同上
    #     4号=+1.9% / 5号=+4.3% / 6号=+6.4%（外枠ほど純3着に残りやすい）
    #   ※ 2・3号艇は2着率>3着率。純3着率が負になるため下限0.05で保護する。
    #   ※ この値は「2着を取り損なった時の3着残存力」の会場平均フォールバック。
    NATIONAL_2ND  = {"2": 0.344, "3": 0.285, "4": 0.198, "5": 0.115, "6": 0.057}
    NATIONAL_3RD_PURE = {"2": 0.05, "3": 0.07, "4": 0.10, "5": 0.13, "6": 0.12}
    # 純3着率の解釈:
    #   2・3号艇: 2着に強い分、3着止まりになる頻度は低い（0.05-0.07で最低保護）
    #   4号艇:    2着・3着ともに均等（純3着0.10）
    #   5・6号艇: 2着は取れないが流れ込みで3着には残れる（0.12-0.13）

    # ── 1号艇の情報を事前取得 ────────────────────────────────────────────────
    res1   = next((r for r in results if r["waku"] == "1"), None)
    cm1    = res1.get("raw_cm", {}) if res1 else {}
    st1    = res1.get("avg_st") if res1 else None

    # 1号艇の被差し脆弱性（0〜1、高いほど差されやすい）
    sasar_vuln = safe_float(cm1.get("差され%"), 0) or 0.0    # 被差し%
    makur_vuln = safe_float(cm1.get("捲られ%"), 0) or 0.0   # 被まくり%
    nige_pct1  = safe_float(_get_cm_val(cm1, "逃げ%"), 0.6) or 0.6
    # 被差し脆弱性スコア: 被差し%を主軸にし、逃げ%が低いほど補強
    vuln_sashi  = max(0.0, min(1.0, sasar_vuln * 0.7 + (1.0 - nige_pct1) * 0.3))
    vuln_makuri = max(0.0, min(1.0, makur_vuln * 0.7 + (1.0 - nige_pct1) * 0.3))

    # ── 全艇のST平均（ST優位スコア計算の基準） ───────────────────────────────
    st_vals = [r["avg_st"] for r in results if r.get("avg_st") is not None]
    st_mean = sum(st_vals) / len(st_vals) if st_vals else 0.15

    def _st_advantage(avg_st, reference=None):
        """
        avg_st が reference（デフォルト: メンバー平均ST）より速い（小さい）ほど高い。
        差±0.05秒を基準に [-1, +1] → スコア [0.5〜1.5] に変換。
        """
        ref = reference if reference is not None else st_mean
        if avg_st is None:
            return 1.0   # データなし → 中立
        diff = ref - avg_st   # 正 = 自分が速い
        return max(0.5, min(1.5, 1.0 + diff / 0.05))

    def _st_advantage_vs1(avg_st):
        """1号艇とのST比較。1号艇より速いほど2着争いで有利。"""
        return _st_advantage(avg_st, reference=st1)

    # ==========================================================================
    # circle_pct（イン逃げ時2着優位度）
    # ──────────────────────────────────────────────────────────────────────────
    # 【修正版設計思想】
    #   主軸: コース別マスタの「イン逃げ時2着率」（直接実績）
    #   補正: ST優位（速い艇は差しやすい）× 1号艇脆弱性（差されやすいほど2枠有利）
    #         決まり手%は補正因子として残す（主軸ではなく傾向補正）
    #
    #   ブレンド方式:
    #     player_2nd   : コース別マスタの「2着率」（イン逃げ時2着率）
    #     venue_2nd    : イン逃げ分析シートの「枠番別2着率」（会場ベースライン）
    #     national_2nd : 全国平均（フォールバック）
    #
    #     trust = min(ininage_count / 30, 1.0)
    #     base  = player_2nd * (0.5 + 0.4 * trust) + venue_2nd * (0.5 - 0.4 * trust)
    #           → 実績30走以上: player 90% / venue 10%
    #           → 実績0走(trust=0): player 50% / venue 50%（データ不足でも完全棄却しない）
    #
    #   ST補正（対1号艇）:
    #     速い艇（ST<1号艇）→ 差しやすい → 2着スコアUP（最大×1.3）
    #     遅い艇             → ×0.85程度
    #
    #   脆弱性補正（2・3枠のみ）:
    #     1号艇が差されやすい → 2枠の差しスコアをさらに補強
    #     1号艇が捲られやすい → 3枠のまくり差しスコアを補強
    #
    #   コース変数は「想定コース（waku フォールバック）」を使用。
    #   会場ベースラインは「枠番」ベースのイン逃げ分析シートを参照（シート定義に準拠）。
    # ==========================================================================

    raw_scores = {}
    for r in results:
        w = r["waku"]
        if w == "1":
            raw_scores[w] = None
            continue

        cm    = r.get("raw_cm", {})
        avg_st = r.get("avg_st")
        try:
            wno = int(w)
        except (ValueError, TypeError):
            wno = 3

        # ── イン逃げ時2着率（直接実績）────────────────────────────────────
        ininage_count = safe_float(cm.get("イン逃げ\n出走数"), 0) or 0
        player_2nd    = safe_float(cm.get("2着率"))   # コース別マスタのイン逃げ時2着率
        has_data      = ininage_count >= MIN_ININAGE_COUNT

        # 会場ベースライン（枠番別）
        venue_2nd    = venue_frame.get(w)            # イン逃げ分析シート（枠番ベース）
        national_2nd = NATIONAL_2ND.get(w, 0.10)    # 全国平均フォールバック

        # trust加重ブレンド
        # 【補正(2)】trust=0（データ不足）時のw_playerを0.50→0.25に引き下げ。
        #   旧: w_player = 0.50 + 0.40 * trust → trust=0で選手50%/会場50%
        #   新: w_player = 0.25 + 0.65 * trust → trust=0で選手25%/会場75%
        #   根拠: イン逃げ出走数5件未満の選手実績は統計ノイズになりやすく、
        #         2着外れ256件の主因の一つ。データ不足時は会場ベースラインを優先。
        #         trust=1.0時は0.90（上限変わらず）。
        trust = min(ininage_count / 30.0, 1.0) if has_data else 0.0
        w_player = 0.25 + 0.65 * trust   # 0.25（trust=0）〜 0.90（trust=1）
        w_venue  = 1.0 - w_player         # 0.75 〜 0.10

        baseline = venue_2nd if venue_2nd is not None else national_2nd
        if player_2nd is not None and has_data:
            base_2nd = player_2nd * w_player + baseline * w_venue
        else:
            base_2nd = baseline   # データ不足 → 会場/全国ベースライン

        # ── ST優位補正（対1号艇）──────────────────────────────────────────
        # 速い艇は1号艇より先にスリットを切れる → 2着争いで有利（最大×1.3）
        st_adv = _st_advantage_vs1(avg_st)
        # 【補正(5): 2026-04-05】ST補正範囲を 0.90〜1.15 に縮小。
        #   実績分析(1196R): 2着率は主にコース番号で決まり、ST差は2次的な影響。
        #   ST補正を過大にすると base_2nd（実績ベース）を歪めるため抑制。
        #   内枠(2・3枠): ST速い → 差しやすい。外枠(5・6枠): STより位置決めが優先。
        st_factor = max(0.90, min(1.15, 0.90 + (st_adv - 0.5) * 0.18))  # 旧: 0.88〜1.20

        # ── コース別・脆弱性補正（実績ベース調整）──────────────────────────
        # 【補正(5): 2026-04-05】1,196レース実測データで再調整。
        # 【補正(3)(4)(5)追加: 2026-04-16】構造的3補正を追加
        #   実績2着率: 2号=33.6%, 3号=29.8%, 4号=19.8%, 5号=11.0%, 6号=5.8%
        #   (3) 3号艇STブロック: 3号艇が2号艇よりST速い場合、3号艇inner_bonus ＆ 2号艇wall減衰
        #   (4) 4号艇wall3精密化: 3号艇vs4号艇のST直接比較（旧: vs1号艇比較）
        #   (5) 1号艇モーター劣勢補正: 1号艇モーターが平均より弱い場合、2・3号艇ボーナス
        # ── 【補正(5)】1号艇モーター劣勢時の2着圏残存補正 ────────────────────────
        # 設計思想:
        #   1号艇が逃げても、モーターが弱いと1M以降で後続に詰められる。
        #   特に差し・まくり差しを武器とする2・3号艇はこの恩恵を受けやすい。
        #
        # motor1_2rate: 1号艇のモーター2連率（全艇平均との比較）
        # 補正係数:
        #   1号艇モーターが全艇平均より -5pt以上劣勢 → 2着争い艇に +5%ボーナス
        #   1号艇モーターが全艇平均より -10pt以上劣勢 → +10%ボーナス（上限）
        #   1号艇モーターが優勢（+5pt以上）→ ボーナスなし
        # ※ 2・3号艇のみ対象（差し・まくり差しで恩恵を受ける内枠2艇）
        _m2_vals_all = [safe_float(rx.get("motor2")) for rx in results if safe_float(rx.get("motor2")) is not None]
        _motor1_m2   = safe_float(res1.get("motor2")) if res1 else None
        _m2_mean_all = sum(_m2_vals_all) / len(_m2_vals_all) if _m2_vals_all else None

        motor1_deficit_bonus = 1.0
        if _motor1_m2 is not None and _m2_mean_all is not None and wno in (2, 3):
            _deficit = _m2_mean_all - _motor1_m2   # 正 = 1号艇が平均より弱い
            if _deficit >= 10.0:
                motor1_deficit_bonus = 1.10   # 劣勢大 → 差し・まくり差し有利+10%
            elif _deficit >= 5.0:
                motor1_deficit_bonus = 1.05   # 劣勢中 → +5%
            # 1号艇モーターが平均以上 → ボーナスなし（1.0のまま）

        if wno == 2:
            # 2枠差し: 1号艇が差されやすいほど有利
            # 脆弱性ボーナスを僅かに抑制（過大評価を防ぐ）
            vuln_factor = 1.0 + vuln_sashi * 0.25   # 旧: 0.30

        elif wno == 3:
            # ── 【補正(3)】3号艇STブロック力を精密化 ──────────────────────────
            # 設計思想:
            #   3号艇が2号艇より "スリット通過が速い（ST速い）" 場合、
            #   3号艇が内側に入って2号艇の差しコースを物理的に塞ぐ。
            #   → 3号艇自身のcircle_pctが上がる（まくり差し有利）
            #   → 2号艇のcircle_pctは別途 wall2_by_3 で減衰させる（後述）
            #
            # 補正式:
            #   st3_vs_st2_adv = (st2 - st3) / 0.05  → 正=3号艇が速い
            #   inner_bonus = clip(1.0 + st3_vs_st2_adv * 0.10, 1.00, 1.20)
            #   → 3号艇が2号艇より0.05秒速い → ×1.10（内入りまくり差し有利）
            #   → 3号艇が2号艇と同ST → ×1.00（補正なし）
            r2 = next((x for x in results if x["waku"] == "2"), None)
            st2 = r2.get("avg_st") if r2 else None
            if avg_st is not None and st2 is not None:
                _st3_adv_over_2 = (st2 - avg_st) / 0.05   # 正=3号艇が速い
                _inner_bonus = max(1.00, min(1.20, 1.0 + _st3_adv_over_2 * 0.10))
            else:
                _inner_bonus = 1.0
            # まくり差し基本補正（1号艇捲られ脆弱性）× 3号艇内入りボーナス
            vuln_factor = (1.0 + vuln_makuri * 0.25) * _inner_bonus

        elif wno == 4:
            # ── 【補正(4)】4号艇に対する3号艇ブロック力の精密化 ─────────────────
            # 設計思想:
            #   3号艇が4号艇よりSTが速い場合、3号艇がアウトコースに張り出し
            #   4号艇のまくりコースを潰す「壁」になる。
            #   一方、3号艇のSTが遅い（4号艇より遅い）場合は壁にならず、
            #   4号艇が3号艇の外からまくれる余地が生まれる。
            #
            # 従来: wall3 = mk3_pct × st_advantage_vs1(st3) × 0.25
            #   問題: ST比較の基準が「1号艇」だった → 3号艇vs4号艇の位置関係を反映していない
            #
            # 新方式: 3号艇のSTを4号艇と直接比較
            #   st3_vs_st4 = (st4 - st3) / 0.05  → 正=3号艇が速い=壁になりやすい
            #   wall3_new = mk3_pct × clip(1.0 + st3_vs_st4 * 0.15, 0.5, 1.5) × 0.25
            #   → 3号艇が4号艇より0.05秒速い → wall3が1.15倍強化
            #   → 3号艇が4号艇より0.05秒遅い → wall3が0.85倍に縮小（壁が薄い）
            r3      = next((x for x in results if x["waku"] == "3"), None)
            cm3     = r3.get("raw_cm", {}) if r3 else {}
            mk3_pct = (safe_float(_get_cm_val(cm3, "まくり%"), 0) or 0.0) + \
                      (safe_float(_get_cm_val(cm3, "まくり差し%"), 0) or 0.0)
            st3     = r3.get("avg_st") if r3 else None
            # 3号艇vs4号艇ST比較（新方式）
            if st3 is not None and avg_st is not None:
                _st3_vs_st4 = (avg_st - st3) / 0.05   # 正=3号艇が速い=壁
                _wall3_st_factor = max(0.5, min(1.5, 1.0 + _st3_vs_st4 * 0.15))
            else:
                _wall3_st_factor = _st_advantage_vs1(st3)   # 旧方式フォールバック
            wall3   = mk3_pct * _wall3_st_factor * 0.25
            vuln_factor = max(1.00, 1.0 - wall3)

        elif wno == 5:
            # 5号艇の実績2着率11.5%を正しく反映。
            #   逃げ局面では5号艇も一定頻度で2着争いに参加 → 減衰なし維持。
            vuln_factor = 1.00   # 変更なし
        else:  # 6枠
            # 6号艇の実績2着率5.7% → 小幅減衰を維持（外枠の構造的不利を反映）
            vuln_factor = 0.80   # 旧: 0.78（実績5.7%に対し過大減衰していたため微緩和）

        score = base_2nd * st_factor * vuln_factor * motor1_deficit_bonus
        raw_scores[w] = max(score, 0.001)   # ゼロ除算防止

    # ── 【補正(3)連動】3号艇STブロックによる2号艇スコア減衰 ──────────────────
    # 3号艇が2号艇よりSTが速い場合、3号艇が2号艇の差しコースを内から塞ぐ。
    # → 2号艇のcircle_pctを減衰させる（3号艇のinner_bonusの裏側）
    #
    # 減衰式:
    #   st3_vs_st2 = (st2 - st3) / 0.05  → 正=3号艇が速い
    #   wall2_by_3 = clip(1.0 - st3_vs_st2_adv * 0.08, 0.85, 1.00)
    #   → 3号艇が0.05秒速い → 2号艇スコアを×0.92
    #   → 同ST以下 → 減衰なし
    _r2 = next((x for x in results if x["waku"] == "2"), None)
    _r3 = next((x for x in results if x["waku"] == "3"), None)
    if _r2 is not None and _r3 is not None:
        _st2_val = _r2.get("avg_st")
        _st3_val = _r3.get("avg_st")
        if _st2_val is not None and _st3_val is not None:
            _st3_adv_vs2 = (_st2_val - _st3_val) / 0.05   # 正=3号艇が速い
            _wall2_by_3  = max(0.85, min(1.00, 1.0 - _st3_adv_vs2 * 0.08))
            if _wall2_by_3 < 1.0 and raw_scores.get("2") is not None:
                raw_scores["2"] = raw_scores["2"] * _wall2_by_3

    # ── 【会場別circle_pct補正】────────────────────────────────────────────
    # バックテスト実績（3,215レース）から導出した
    # 「この会場ではこの艇番が全国平均より何倍2着に来やすいか」の係数。
    #
    # 導出方法:
    #   raw_ratio = 会場×艇番の実際2着率 / 全国平均2着率
    #   shrinkage補正: raw_ratio * trust + 1.0 * (1-trust)
    #     trust = min(会場サンプル数 / 50, 1.0)
    #
    # 適用タイミング: raw_scores 確定後・正規化前
    #   → 補正後の raw_scores を正規化するため、合計100%は保たれる
    #
    # 係数の意味:
    #   1.0 = 全国平均通り（補正なし）
    #   1.3 = その会場ではその艇番が全国より30%多く2着に来る傾向
    #   0.7 = その会場ではその艇番が全国より30%少ない傾向
    #
    # クリップ範囲: [0.5, 2.0]
    #   江戸川6号(2.411)等の極端値を抑制して正規化への影響を制限
    #
    # 更新方法:
    #   update_master.py のバックテスト集計が積み上がるたびに
    #   以下の辞書を再計算して上書きする（将来はCSV化を検討）
    # ──────────────────────────────────────────────────────────────────────
    _VENUE_CIRCLE_ADJ = {
        "びわこ":  {"2": 1.042, "3": 0.789, "4": 1.071, "5": 0.905, "6": 1.726},
        "三国":    {"2": 0.890, "3": 1.499, "4": 0.874, "5": 0.711, "6": 0.180},
        "下関":    {"2": 0.997, "3": 0.830, "4": 1.240, "5": 0.770, "6": 1.468},
        "丸亀":    {"2": 1.215, "3": 0.888, "4": 0.884, "5": 0.961, "6": 0.785},
        "住之江":  {"2": 0.950, "3": 0.923, "4": 1.365, "5": 0.731, "6": 0.929},
        "児島":    {"2": 1.020, "3": 0.838, "4": 1.154, "5": 0.839, "6": 1.455},
        "唐津":    {"2": 1.183, "3": 1.041, "4": 0.716, "5": 0.787, "6": 1.125},
        "多摩川":  {"2": 0.877, "3": 1.028, "4": 0.980, "5": 1.093, "6": 1.459},
        "大村":    {"2": 1.126, "3": 0.881, "4": 0.888, "5": 1.321, "6": 0.630},
        "宮島":    {"2": 1.136, "3": 1.146, "4": 0.620, "5": 0.790, "6": 1.206},
        "尼崎":    {"2": 0.839, "3": 1.148, "4": 1.094, "5": 0.906, "6": 1.063},
        "常滑":    {"2": 0.780, "3": 0.978, "4": 1.127, "5": 1.449, "6": 1.074},
        "平和島":  {"2": 0.790, "3": 0.982, "4": 0.874, "5": 1.674, "6": 1.430},
        "徳山":    {"2": 1.214, "3": 1.103, "4": 0.717, "5": 0.614, "6": 0.976},
        "戸田":    {"2": 0.933, "3": 0.678, "4": 1.194, "5": 1.462, "6": 1.413},
        "桐生":    {"2": 0.860, "3": 1.251, "4": 0.750, "5": 1.029, "6": 1.374},
        "江戸川":  {"2": 0.845, "3": 0.744, "4": 1.240, "5": 0.949, "6": 2.000},  # 6号上限クリップ適用(raw:2.411)
        "津":      {"2": 1.084, "3": 1.031, "4": 1.228, "5": 0.701, "6": 0.167},
        "浜名湖":  {"2": 0.954, "3": 0.924, "4": 1.000, "5": 1.356, "6": 0.953},
        "福岡":    {"2": 1.246, "3": 0.913, "4": 0.888, "5": 0.839, "6": 0.711},
        "芦屋":    {"2": 0.692, "3": 1.147, "4": 1.320, "5": 1.142, "6": 0.681},
        "若松":    {"2": 1.002, "3": 0.984, "4": 1.015, "5": 1.046, "6": 0.930},
        "蒲郡":    {"2": 0.915, "3": 1.145, "4": 0.972, "5": 1.278, "6": 0.348},
        "鳴門":    {"2": 1.020, "3": 1.077, "4": 0.941, "5": 1.221, "6": 0.291},
    }
    _venue_circle_adj = _VENUE_CIRCLE_ADJ.get(venue, {})
    if _venue_circle_adj:
        for _w in list(raw_scores.keys()):
            if _w != "1" and raw_scores[_w] is not None:
                _adj = _venue_circle_adj.get(str(_w), 1.0)
                _adj = max(0.5, min(2.0, _adj))   # クリップ [0.5, 2.0]
                raw_scores[_w] = raw_scores[_w] * _adj

    # レース内正規化（合計100%）
    valid_scores = {w: s for w, s in raw_scores.items() if w != "1" and s is not None}
    total_score  = sum(valid_scores.values()) or 1.0

    for r in results:
        w = r["waku"]
        s = raw_scores.get(w)
        if w != "1" and s is not None:
            r["circle_pct"] = round(s / total_score * 100, 1)
            r["_circ_raw"]  = s          # 確率計算用（正規化前絶対スコア）
        else:
            r["circle_pct"] = None
            r["_circ_raw"]  = None

    # ==========================================================================
    # idx3（イン逃げ時3着残存指数）
    # ──────────────────────────────────────────────────────────────────────────
    # 【修正版設計思想】
    #   主軸: 純3着率 = イン逃げ時3着以内率 − イン逃げ時2着率（直接実績）
    #
    #   修正点:
    #     (1) win3_rate（全体3連対率）を除去 → イン逃げ局面と無関係のため
    #     (2) 会場ベースラインも純3着率ベース（3着以内率 − 2着率）で統一
    #     (3) ST補正は「遅い艇ほど流れ込みで3着に残りやすい」傾向を穏やかに反映
    #
    #   trust加重ブレンド（circle_pctと同じ方式）:
    #     base_pure3 = player_pure3 * w_player + venue_pure3 * w_venue
    # ==========================================================================

    raw_idx3_scores = {}
    for r in results:
        w = r["waku"]
        if w == "1":
            raw_idx3_scores[w] = None
            continue

        cm = r.get("raw_cm", {})
        ininage_count = safe_float(cm.get("イン逃げ\n出走数"), 0) or 0
        player_3rd    = safe_float(cm.get("3着以内率"))   # イン逃げ時3着以内率
        player_2nd    = safe_float(cm.get("2着率"))       # イン逃げ時2着率
        has_data      = ininage_count >= MIN_ININAGE_COUNT

        # 選手の純3着率（イン逃げ時3着以内率 − 2着率）
        if player_3rd is not None and player_2nd is not None and has_data:
            player_pure3 = max(player_3rd - player_2nd, 0.0)
        elif player_3rd is not None and has_data:
            # 2着率不明 → 3着以内率の35%を純3着と推定（全国平均比から導出）
            player_pure3 = player_3rd * 0.35
        else:
            player_pure3 = None

        # 会場ベースラインの純3着率（枠番別）
        venue_3rd_rate = venue_3rd_map.get(w)
        venue_2nd_rate = venue_frame.get(w)
        if venue_3rd_rate is not None and venue_2nd_rate is not None:
            venue_pure3 = max(venue_3rd_rate - venue_2nd_rate, 0.0)
        else:
            venue_pure3 = None

        national_pure3 = NATIONAL_3RD_PURE.get(w, 0.10)

        # trust加重ブレンド
        # 【補正(5): 2026-04-05】実測1,196Rの3着分布を反映したNATIONAL_3RD_PUREに更新済み。
        #   trust=0時のw_playerを0.15→0.10に引き下げ（全国平均フォールバックへの依存を強化）。
        #   根拠: 純3着率は2・3号艇でマイナス（2着に集中）→ 個人実績の解釈が困難。
        #         会場ベースライン95% / 個人値5% で安定した推定が得られる。
        trust    = min(ininage_count / 30.0, 1.0) if has_data else 0.0
        w_player = 0.10 + 0.65 * trust   # 0.10（trust=0）〜 0.75（trust=1）旧: 0.15〜0.80
        w_venue  = 1.0 - w_player         # 0.90〜0.25

        venue_val = venue_pure3 if venue_pure3 is not None else national_pure3
        if player_pure3 is not None and has_data:
            score_3rd = player_pure3 * w_player + venue_val * w_venue
        else:
            score_3rd = venue_val

        # ST補正（遅め艇ほど流れ込みで3着に残りやすい）
        # 【補正(5): 2026-04-05】3着残存はSTより「コース位置」で決まる傾向が強い。
        #   ST補正の影響を ±10% → ±8% に縮小（過剰なST依存を防ぐ）。
        avg_st = r.get("avg_st")
        if avg_st is not None:
            # 平均より遅いほど微加算、速いほど微減（影響は小さく±8%以内）
            st_slow_bonus = max(0.92, min(1.08, 1.0 + (avg_st - st_mean) / 0.05 * 0.08))  # 旧: ±15%
        else:
            st_slow_bonus = 1.0
        score_3rd = max(score_3rd * st_slow_bonus, 0.0)

        raw_idx3_scores[w] = score_3rd

    # 最大値=100にスケーリング（分散を保つため下限は設けない）
    valid_idx3 = [s for w, s in raw_idx3_scores.items() if w != "1" and s is not None]
    max_idx3   = max(valid_idx3) if valid_idx3 else 1.0
    for r in results:
        w  = r["waku"]
        s3 = raw_idx3_scores.get(w)
        if w != "1" and s3 is not None and max_idx3 > 0:
            r["idx3"] = min(int(s3 / max_idx3 * 100), 100)
        else:
            r["idx3"] = 0

    # frame_2nd: write_race_flat の2着率テキストブロック描画用に渡す
    frame_2nd = {w: s for w, s in raw_scores.items() if s is not None}
    
    # 会場イン逃げ場平均・決まり手場平均
    venue_stats = _calc_venue_stats(venue_stats_master, venue)

    # ── ★新機能: 6人相性スコア・イン飛び条件定量化 ────────────────────────
    # ── 展開考察エンジン（STxコース連動 → 対立構造 → 展開quality）────────────
    # _judge_tobi_scenario の前段として実行し、結果を race_judgment に連携させる。
    # first_turn: 1M到達順序と展開パターン
    # conflict_map: 誰が誰を潰しに行くかの対立構造
    # scenario_quality: 展開がどれだけ絞れているかのqualityスコア
    first_turn      = _predict_first_turn(results, venue=venue)
    conflict_map    = _build_conflict_map(results, first_turn)
    # scenario_quality は _suggest_3rentan 後に s1_prob が確定してから補完する
    # ここでは先行優位度と対立構造のみで暫定計算
    scenario_quality = _calc_scenario_quality(first_turn, conflict_map, s1_prob_est=None)

    affinity = _calc_affinity_score(results, venue_stats_master, venue)
    tobi     = _judge_tobi_scenario(results, affinity, venue_stats)

    # (3) SG/G1: 飛びスコアを下方補正（一般戦より1号艇ST安定度が高い）
    if _IS_GRADE_RACE:
        _raw_tobi = tobi["tobi_prob"]
        tobi["tobi_prob"]  = round(_raw_tobi * 0.80, 1)
        tobi["tobi_rank"]  = (
            "S" if tobi["tobi_prob"] >= 70 else
            "A" if tobi["tobi_prob"] >= 55 else
            "B" if tobi["tobi_prob"] >= 40 else
            "C" if tobi["tobi_prob"] >= 25 else "D"
        )
        tobi["_sg_tobi_adj"] = True   # デバッグ用フラグ

    # ── 荒れ/堅いレース判定 ＋ 3連単買い目提案（数値シート出力用） ──────────
    race_judgment  = _judge_race_type(results, venue_stats, venue_frame, race_no,
                                      venue_stats_master=venue_stats_master, venue=venue,
                                      tobi_scenario=tobi)
    # ── ★新機能: イン逃げ/イン飛び/両建て 3択判定（暫定：s1_prob未確定）────────
    # この時点では s1_prob がまだ確定していないため、暫定値として計算する。
    # s1_prob 確定後に main() または calc_race_indices の末尾で再計算する。
    ryotate_judgment = _judge_ryotate(race_judgment, tobi, venue_stats, s1_prob=None)
    race_judgment["ryotate"] = ryotate_judgment

    # 会場別1コース1着率を race_judgment に追加（_suggest_3rentan → _calc_3rentan_probs_v2 で使用）
    # 荒れやすい会場（戸田=43%, 平和島=45%等）で過剰なS1重みを抑制するため
    _vs_raw = venue_stats_master.get(venue, {})
    _vc1r = safe_float(_vs_raw.get("1コース1着率") or _vs_raw.get("1C_1着率"))
    race_judgment["venue_c1_win_rate"] = _vc1r  # Noneなら全国平均(0.555)にフォールバック
    race_judgment["affinity"]          = affinity  # (3)相性考察で参照
    race_judgment["venue"]      = venue     # 参加見送り判定用
    race_judgment["race_grade"] = race_grade  # SG/G1補正の有無を下流に伝達

    # ── 【v6.2】会場統計の全データを race_judgment に格納 ─────────────────────
    # RNo別1C1着率: レース番号によるS1重み補正に使用
    # コース別1着率（2C〜6C）: シナリオ重みの会場補正に使用
    # Rレース別荒れスコア: MAX_BETS・買い目点数の調整に使用
    try:
        _rno = int(str(race_no))
    except (ValueError, TypeError):
        _rno = None
    # 当該レース番号の1C1着率（例: 5Rなら "1C_5R1着率"）
    _venue_1c_race_rate = None
    if _rno:
        _venue_1c_race_rate = safe_float(_vs_raw.get(f"1C_{_rno}R1着率"))
    race_judgment["venue_1c_race_rate"] = _venue_1c_race_rate  # R番号補正後の1C1着率

    # コース別1着率（全コース）
    race_judgment["venue_course_win_rates"] = {
        str(c): safe_float(_vs_raw.get(f"{c}C_1着率") or _vs_raw.get(f"{c}コース1着率"))
        for c in range(1, 7)
    }

    # Rレース別荒れスコア
    _venue_are_score = None
    if _rno:
        _venue_are_score = safe_float(_vs_raw.get(f"{_rno}R荒れスコア"))
    race_judgment["venue_race_are_score"] = _venue_are_score  # 当該Rの荒れスコア

    # 【枠なり前提】進入変更フラグ（初期値 False）
    # コース変更が確認された場合は True にセットすること。
    # True の場合 _should_skip_race が最優先で見送り推奨を返す。
    race_judgment.setdefault("nyujo_henkou", False)

    # ── 遅延import（循環import回避） ─────────────────────────────────────────
    from lr_suggest import (
        _judge_w1_escape, _judge_main_player, _judge_dark_horse,
        _judge_escape_fallback, _calc_honmei_score,
        _suggest_3rentan, _apply_jizen_honmei,
    )
    from lr_probs import _calc_3rentan_probs_v2

    # ── (1) 1号艇逃げ力判定（6人構成メンバーを相手に逃げ切れるか）────────────
    # race_judgment や ryotate を参照しない純粋な前向き計算。
    # この結果が後続の ryotate 再計算・印スコアの入力として使われる。
    w1_escape = _judge_w1_escape(results, venue_stats, race_judgment=None, st_kimete_master=st_kimete_master)
    race_judgment["w1_escape"] = w1_escape
    print(f"  ? 1号艇逃げ判定: {w1_escape['escape_pct']}【{w1_escape['escape_rank']}】"
          f" 最大脅威={w1_escape['top_threat_waku']}号艇({w1_escape['top_threat_type']})")

    # ── (2) 主役候補判定（逃げない場合に誰が主役でどの展開か）────────────────
    # w1_escape の threat_list を引き継ぎ、上位2艇・展開タイプ・2/3着候補を確定する。
    # escape_rank が「低」または「中」のとき特に重要。
    main_player = _judge_main_player(results, venue_stats, race_judgment,
                                        tenkai_venue=tenkai_venue_master,
                                        tenkai_national=tenkai_national_master,
                                        st_kimete_master=st_kimete_master)
    race_judgment["main_player"] = main_player
    _mp_sub = (f"  対抗={main_player['sub_waku']}号艇({main_player['sub_type']})"
               if main_player["sub_waku"] else "")
    print(f"  ? 主役候補: {main_player['main_waku']}号艇【{main_player['main_type']}】"
          f" スコア{main_player['main_score']*100:.0f}%{_mp_sub}")

    # ── (3) 主役が来れなかった時の逃げ残存確率 ─────────────────────────────────
    # main_player（主役候補）が自滅した場合に1号艇が2着以内に残れるかを算出。
    # conflict_map はこの時点でローカル変数として確定済み（race_judgmentへの格納は後工程）
    # のでローカル変数を直接渡す。
    escape_fallback = _judge_escape_fallback(results, venue_stats, race_judgment,
                                             conflict_map=conflict_map)
    race_judgment["escape_fallback"] = escape_fallback
    print(f"  ? 逃げ残存({main_player['main_waku']}号艇自滅時):"
          f" {escape_fallback['fallback_pct']}【{escape_fallback['fallback_rank']}】"
          f" 自滅タイプ={escape_fallback['fly_type']}")

    # ── (4) 主役展開の穴をつく艇判定 ──────────────────────────────────────────
    # 主軸対立（main_waku vs 1号艇）の外側で美味しいポジションに入れる艇を特定。
    # collapse_beneficiary は conflict_map から取得するためローカル変数を直接渡す。
    dark_horse = _judge_dark_horse(results, venue_stats, race_judgment,
                                   conflict_map=conflict_map)
    race_judgment["dark_horse"] = dark_horse
    if dark_horse["is_valid"]:
        _dh_str = "  ".join(
            f"{w}号艇({tag}:{s*100:.0f}%)"
            for w, s, tag in dark_horse["dark_horse_candidates"]
        )
        print(f"  ? 穴候補: {_dh_str}")
    else:
        print(f"  ? 穴候補: 有効な穴なし")

    # ── ★ヒモ荒れ判定 ────────────────────────────────────────────────────────
    # 1号艇が強本命（rel_win1 >= 65%）のとき「2・3着ヒモが荒れるか」を判定し
    # 参加可否と買い目点数調整の根拠として race_judgment に格納する。
    race_judgment["himo_are"] = _judge_himo_are(results, race_judgment)

    # ── bet_suggestions は load_race.py 側で生成する（3重計算を排除）────────
    # jizen_eval 確定前の仮 bet_suggestions として空dictを渡し、
    # s1_prob / tenkai_pattern は race_judgment から取得する。
    # 最終的な bet_suggestions は load_race.py の印確定フロー（(1)(2)(3)）で生成される。
    bet_suggestions = {}

    # ── s1_prob 確定後の各種最終補完 ─────────────────────────────────────────
    s1_prob_final = race_judgment.get("s1_prob")

    # (1) scenario_quality を s1_prob・tenkai_pattern ベースで最終補完（v3）
    _tp_final = bet_suggestions.get("tenkai_pattern") or race_judgment.get("tenkai_pattern")
    scenario_quality = _calc_scenario_quality(
        first_turn, conflict_map,
        s1_prob_est=s1_prob_final,
        tenkai_pattern=_tp_final,
    )

    # (2) ryotate（3択判定）を s1_prob 確定後に再計算 ← 【断絶修正】
    #    s1_prob を渡すことで確率モデルと定性スコアの整合性チェックを実行し、
    #    3択の verdict・表示%・consistency_warn をすべて確率ベースに統一する。
    if s1_prob_final is not None:
        ryotate_judgment = _judge_ryotate(
            race_judgment, tobi, venue_stats, s1_prob=s1_prob_final
        )
        race_judgment["ryotate"] = ryotate_judgment

    # (3) ◎艇番とs1_prob最大艇の乖離チェック ← 【内部矛盾検出】
    #    バックテスト除外フラグとして活用可能
    first_prob_map_final = bet_suggestions.get("first_prob_map", {})
    if first_prob_map_final:
        top_prob_waku = max(first_prob_map_final, key=first_prob_map_final.get)
        honmei_waku_check = next(
            (str(r["waku"]) for r in results if r.get("honmei") == "◎"), None
        )
        if honmei_waku_check and honmei_waku_check != top_prob_waku:
            # 印◎ != 確率最大艇 → 矛盾フラグ（展開シナリオが印を覆している）
            race_judgment["honmei_prob_mismatch"] = True
            race_judgment["honmei_prob_mismatch_detail"] = (
                f"◎={honmei_waku_check}号艇 vs 確率最大={top_prob_waku}号艇"
                f"({first_prob_map_final.get(top_prob_waku, 0)*100:.1f}%)"
            )
        else:
            race_judgment["honmei_prob_mismatch"] = False
            race_judgment["honmei_prob_mismatch_detail"] = ""

    # ── 展開考察エンジン結果を race_judgment に格納 ───────────────────────────
    race_judgment["first_turn"]      = first_turn
    race_judgment["conflict_map"]    = conflict_map
    race_judgment["scenario_quality"] = scenario_quality

    # ── 3連対指数（ST補正・展開補正付き相対評価） ───────────────────────
    # 【2段階計算の設計】
    # ここでは第1〜3層（実績比・荒れ係数・ST補正）のみ適用する。
    # 第4層の展開ペナルティ（cascade_scores）は load_race.py 側で
    # build_scenarios 完了後に recalc_sanren_idx_with_tenkai() を呼んで上書きする。
    #
    # nige_prob の取り出し:
    #   escape_score は 0〜100 スケールなので 0〜1 に変換して渡す。
    #   この時点では bet_suggestions 未確定のため暫定値だが、
    #   ST補正（第3層）は nige_prob を使わないので影響なし。
    try:
        from lr_sanren_idx import calc_sanren_idx as _calc_sanren_idx
        _escape_score  = race_judgment.get("escape_score") or race_judgment.get("score") or 55.0
        _nige_prob_est = max(0.0, min(1.0, float(_escape_score) / 100.0))
        results = _calc_sanren_idx(
            results,
            venue,
            venue_course_master,
            venue_stats_master,
            cascade_scores = None,          # 第4層は load_race.py 側で後付け
            nige_prob      = _nige_prob_est,
        )
        # 後付け用フラグ: load_race.py 側で cascade_scores が確定したら再計算する
        race_judgment["sanren_idx_needs_tenkai_update"] = True
    except Exception as _e:
        print(f"  [!]  3連対指数計算エラー（スキップ）: {_e}")
        race_judgment["sanren_idx_needs_tenkai_update"] = False
    # ─────────────────────────────────────────────────────────────────────

    return results, slit, venue_stats, frame_2nd, race_judgment, bet_suggestions

# ============================================================
# ★ 新機能(1) 6人相性スコア計算
# ============================================================

# ========================================================================
# 展開考察エンジン（3関数セット）
# _predict_first_turn → _build_conflict_map → _calc_scenario_quality
# ========================================================================

def _predict_first_turn(results, venue=None):
    """
    STとコース位置から第1ターンマーク（1M）到達順序と展開パターンを推定する。

    【競艇の物理法則】
      第1ターンへの到達時間 ~= コース距離 + スタートタイム差
      内側コース（1号艇）ほど距離が短い。
      ただし外側艇がST大幅有利なら距離ハンデを逆転できる。

      到達順序（早い順）= コース距離補正後のST実効値でソート。
      実効ST = avg_st + コース距離補正

    【(5)改善】venue引数を受け取り、venue_course_adj.csv が存在すれば
      固定値の代わりに会場別実測値補正を使用する。
      信頼度 < 0.3 の会場は固定値にフォールバック。

    【ST不明時のフォールバック】
      avg_stがNoneの艇はコース別全国平均STで代替する。

    Returns
    -------
    dict:
        entry_order      : [(waku, eff_st), ...] 1M到達順（早い順・推定）
        lead_waku        : 先行艇（第1ターン最速艇）
        chase_waku       : 追走艇（2番手）
        lead_margin      : 先行差（秒）
        pattern          : "A（逃げ有利）"/"B（差し有利）"/"C（まくり差し）"/"D（大外）"
        pattern_strength : "強"（先行差>0.05）/"中"（>0.02）/"弱"（接戦）
        narrative        : 展開の絵（自然言語）
        st_details       : {waku: {"avg_st", "eff_st", "course_adj"}} デバッグ用
    """
    # コース距離補正（秒）- デフォルト固定値
    COURSE_ADJ = {"1": 0.00, "2": 0.03, "3": 0.06,
                  "4": 0.10, "5": 0.15, "6": 0.21}
    # STデータなし時の全国平均
    ST_NATIONAL = {"1": 0.18, "2": 0.17, "3": 0.17,
                   "4": 0.18, "5": 0.19, "6": 0.20}

    # 【(5)】会場別補正値CSVが存在すれば上書き（信頼度0.3以上の会場のみ）
    if venue and VENUE_COURSE_ADJ_CSV.exists():
        try:
            _adj_df = pd.read_csv(str(VENUE_COURSE_ADJ_CSV), encoding="utf-8-sig")
            _row = _adj_df[_adj_df["会場名"] == venue]
            if not _row.empty and float(_row["信頼度"].iloc[0]) >= 0.3:
                for c in range(2, 7):
                    col = f"{c}C補正"
                    if col in _row.columns:
                        COURSE_ADJ[str(c)] = float(_row[col].iloc[0])
        except Exception:
            pass  # 読み込み失敗時は固定値で継続

    entries = []
    st_details = {}
    for r in results:
        w    = r["waku"]
        st   = r.get("avg_st")
        if st is None or st <= 0:
            st = ST_NATIONAL.get(w, 0.18)
            is_estimated = True
        else:
            is_estimated = False

        # ── 展示タイム補正（当日の実走ST傾向を反映）────────────────────────
        # tenji_hensa: 偏差値50基準。高い=今日速い → STを前倒し補正する。
        # 偏差値55以上 → -0.004秒（早く届く）/ 45以下 → +0.004秒（遅くなる）
        # 補正幅は最大±0.008秒に抑え、過去実績の大枠を崩さない。
        tenji_hensa  = safe_float(r.get("tenji_hensa"))
        tenji_st_adj = 0.0
        if tenji_hensa is not None:
            tenji_st_adj = max(-0.008, min(0.008, -(tenji_hensa - 50) / 50 * 0.008))
        st_today = max(0.05, st + tenji_st_adj)

        adj     = COURSE_ADJ.get(w, 0.10)
        eff_st  = round(st_today + adj, 4)
        entries.append((w, eff_st))
        st_details[w] = {
            "avg_st":       st,
            "st_today":     round(st_today, 4),
            "tenji_hensa":  tenji_hensa,
            "tenji_st_adj": round(tenji_st_adj, 4),
            "course_adj":   adj,
            "eff_st":       eff_st,
            "estimated":    is_estimated,
        }

    entries.sort(key=lambda x: x[1])

    lead_waku  = entries[0][0]
    chase_waku = entries[1][0] if len(entries) >= 2 else None
    lead_margin = round(entries[1][1] - entries[0][1], 4) if len(entries) >= 2 else 0.0

    # 展開パターン
    try:
        lead_course = int(lead_waku)
    except (ValueError, TypeError):
        lead_course = 1

    if lead_course == 1:
        pattern = "A（逃げ有利）"
    elif lead_course == 2:
        pattern = "B（差し有利）"
    elif lead_course <= 4:
        pattern = "C（まくり差し）"
    else:
        pattern = "D（大外まくり）"

    if lead_margin > 0.05:
        pattern_strength = "強"
    elif lead_margin > 0.02:
        pattern_strength = "中"
    else:
        pattern_strength = "弱（接戦）"

    # 展開の絵（自然言語）
    entry_str = " → ".join([f"{w}号({st:.3f})" for w, st in entries])
    if pattern_strength == "強":
        strength_desc = f"{lead_waku}号艇が{lead_margin:.3f}秒差で先行確定的"
    elif pattern_strength == "中":
        strength_desc = f"{lead_waku}号艇が優位だが{chase_waku}号艇が追走できる差"
    else:
        strength_desc = f"{lead_waku}号艇と{chase_waku}号艇が接戦（展開は流動的）"

    narrative = (
        f"【1M到達順（推定）】{entry_str}\n"
        f"【先行】{lead_waku}号艇 → {pattern} / 強度:{pattern_strength}\n"
        f"{strength_desc}"
    )

    return {
        "entry_order":       entries,
        "lead_waku":         lead_waku,
        "chase_waku":        chase_waku,
        "lead_margin":       lead_margin,
        "pattern":           pattern,
        "pattern_strength":  pattern_strength,
        "narrative":         narrative,
        "st_details":        st_details,
    }


def _build_conflict_map(results, first_turn, cm_map_ext=None):
    """
    1M到達順序を受けて「誰が誰を潰しに行くか」の対立構造を計算する。

    【競艇の対立構造の本質】
      1M到達順序が決まれば、各艇の「攻撃対象」が物理的に決まる。

      攻撃対象の決まり方:
        先行艇（1番手）: 攻撃対象なし（前に誰もいない）
        2番手艇: 先行艇を差す or まくる
        3番手艇: 2番手艇を外から包む（まくり）or 1番手を差す（まくり差し）
        4番手以降: 外からまくる or 内側の争いを待って2着圏に滑り込む

      攻撃強度 = 決まり手適性 × ST差（接戦ほど攻撃が届きやすい）× 位置補正

    【対立の主軸と副軸】
      主軸対立: 1M到達2番手が先行艇を攻撃する構図
      副軸対立: 1M到達3〜4番手が2番手を潰す構図（漁夫の利の発生源）

    【出力する「展開の絵」】
      例:
        主軸: 3号艇(まくり差し系)が1号艇を包む構図
        副軸: 4号艇(まくり系)が3号艇を外から被せる可能性
        潰れ受益: 3号艇が自滅した場合、5号艇（攻撃性低・win3_rate高）が漁夫

    Returns
    -------
    dict:
        main_conflict    : {"attacker", "target", "method", "strength", "desc"}
        sub_conflict     : {"attacker", "target", "method", "strength", "desc"} or None
        collapse_beneficiary : [(waku, score), ...]  潰れ受益候補（スコア降順）
        narrative        : 対立構造の展開の絵（自然言語）
        conflict_entries : 全艇の対立エントリ（詳細デバッグ用）
    """
    entry_order = first_turn["entry_order"]  # [(waku, eff_st), ...]
    wakus_in_order = [w for w, _ in entry_order]

    # cm_mapを構築（resultsから）
    cm_map = {r["waku"]: r.get("raw_cm", {}) for r in results}
    win3_map = {r["waku"]: r.get("win3_rate") or 0.5 for r in results}

    def safe_pct(cm, key):
        v = cm.get(key)
        try:
            return max(float(v), 0.0) if v is not None else 0.0
        except (ValueError, TypeError):
            return 0.0

    def _kime_type(waku):
        """決まり手タイプを返す（まくり系/差し系/逃げ系）"""
        cm = cm_map.get(waku, {})
        mak  = safe_pct(cm, "まくり%") + safe_pct(cm, "まくり差し%")
        sash = safe_pct(cm, "差し%")
        nige = safe_pct(cm, "逃げ%")
        best = max(mak, sash, nige)
        if best == 0:
            return "不明"
        if mak == best:
            return "まくり系"
        if sash == best:
            return "差し系"
        return "逃げ系"

    def _attack_strength(attacker_w, target_w, entry_idx_diff):
        """
        攻撃強度 = 決まり手適性スコア × ST接近度補正 × 位置距離補正
        entry_idx_diff: 1M到達順序上の距離（1=直後、2=2つ後ろ etc.）
        """
        cm = cm_map.get(attacker_w, {})
        mak  = safe_pct(cm, "まくり%") + safe_pct(cm, "まくり差し%")
        sash = safe_pct(cm, "差し%")
        base = max(mak, sash)  # 攻撃決まり手の主力
        if base == 0:
            base = 10.0  # データなしフォールバック

        # 位置距離減衰（直後が最も攻撃しやすい）
        dist_factor = {1: 1.0, 2: 0.7, 3: 0.5, 4: 0.3, 5: 0.2}
        dist_dec = dist_factor.get(entry_idx_diff, 0.15)

        # ST接近度（eff_st差が小さいほど追いつきやすい）
        lead_eff = dict(entry_order).get(target_w, 0.5)
        att_eff  = dict(entry_order).get(attacker_w, 0.5)
        st_gap   = abs(lead_eff - att_eff)
        st_factor = max(0.3, 1.0 - st_gap * 8.0)  # 0.1秒差で0.2低下

        return round(base * dist_dec * st_factor, 1)

    # ── 各艇の攻撃対象・手法・強度を計算 ──────────────────────────────────────
    conflict_entries = []
    for idx, (w, eff_st) in enumerate(entry_order):
        if idx == 0:
            # 先行艇は攻撃対象なし（前方クリア）
            conflict_entries.append({
                "waku": w, "role": "先行",
                "target": None, "method": "-", "strength": 0
            })
            continue

        # 攻撃対象 = 1M到達順で1つ前の艇（最も自然な攻撃対象）
        target_w = entry_order[idx - 1][0]
        kime     = _kime_type(w)
        strength = _attack_strength(w, target_w, 1)

        # 攻撃手法の決定
        try:
            w_course      = int(w)
            target_course = int(target_w)
        except (ValueError, TypeError):
            w_course = target_course = 3

        if kime == "差し系" and w_course < target_course + 2:
            method = "差し"
        elif kime == "まくり系":
            method = "まくり"
        elif kime in ("まくり系", "不明"):
            method = "まくり"
        else:
            method = "まくり差し"

        conflict_entries.append({
            "waku":     w,
            "role":     f"{idx+1}番手",
            "target":   target_w,
            "method":   method,
            "kime":     kime,
            "strength": strength,
        })

    # ── 主軸対立（進入2番手 vs 先行艇）──────────────────────────────────────────
    main_entry = conflict_entries[1] if len(conflict_entries) >= 2 else None
    if main_entry and main_entry["target"]:
        main_conflict = {
            "attacker": main_entry["waku"],
            "target":   main_entry["target"],
            "method":   main_entry["method"],
            "strength": main_entry["strength"],
            "desc": (
                f"{main_entry['waku']}号艇が{main_entry['target']}号艇に"
                f"「{main_entry['method']}」で挑む"
                f"（強度{main_entry['strength']:.0f}）"
            ),
        }
    else:
        main_conflict = None

    # ── 副軸対立（進入3番手 vs 2番手）──────────────────────────────────────────
    sub_entry = conflict_entries[2] if len(conflict_entries) >= 3 else None
    if sub_entry and sub_entry["target"]:
        sub_conflict = {
            "attacker": sub_entry["waku"],
            "target":   sub_entry["target"],
            "method":   sub_entry["method"],
            "strength": sub_entry["strength"],
            "desc": (
                f"{sub_entry['waku']}号艇が{sub_entry['target']}号艇を"
                f"「{sub_entry['method']}」で外から被せる"
                f"（強度{sub_entry['strength']:.0f}）"
            ),
        }
    else:
        sub_conflict = None

    # ── 潰れ受益者（主軸攻撃艇が自滅した場合の漁夫候補）────────────────────────
    # 主軸攻撃艇が自滅 → 受益者の条件:
    #   (1) 攻撃性が低い（自分は仕掛けに行かない）
    #   (2) win3_rateが高い（荒れても残る力がある）
    #   (3) 主軸対立の外側にいる（巻き込まれない位置）
    main_attacker = main_conflict["attacker"] if main_conflict else None
    beneficiary_scores = {}
    for r in results:
        w = r["waku"]
        if w == main_attacker or w == (main_conflict["target"] if main_conflict else None):
            continue  # 主軸の当事者は除外
        cm   = cm_map.get(w, {})
        mak  = safe_pct(cm, "まくり%") + safe_pct(cm, "まくり差し%")
        sash = safe_pct(cm, "差し%")
        attack_rate  = min((mak + sash) / 100.0, 1.0)
        passivity    = 1.0 - attack_rate * 0.6  # 低攻撃性 = 高漁夫スコア
        ground       = win3_map.get(w, 0.5)
        beneficiary_scores[w] = round(passivity * ground, 4)

    collapse_beneficiary = sorted(
        beneficiary_scores.items(), key=lambda x: x[1], reverse=True
    )

    # ── 展開の絵（自然言語ナラティブ）──────────────────────────────────────────
    parts = []
    if main_conflict:
        parts.append(f"主軸: {main_conflict['desc']}")
    if sub_conflict:
        parts.append(f"副軸: {sub_conflict['desc']}")
    if collapse_beneficiary:
        top_b = collapse_beneficiary[0]
        parts.append(
            f"潰れ受益候補: {top_b[0]}号艇"
            f"（攻撃性低・win3高・主軸争いの外側）"
        )
    narrative = "\n".join(parts) if parts else "展開の絵を生成できませんでした"

    return {
        "main_conflict":         main_conflict,
        "sub_conflict":          sub_conflict,
        "collapse_beneficiary":  collapse_beneficiary,
        "narrative":             narrative,
        "conflict_entries":      conflict_entries,
        "lead_waku":             wakus_in_order[0] if wakus_in_order else None,
    }


def _calc_scenario_quality(first_turn, conflict_map, s1_prob_est=None, tenkai_pattern=None):
    """
    展開の「絞れ度」= 展開が特定シナリオに集中しているか（quality）を計算する。

    【質スコアの概念】
      競艇のレースには「読みやすいレース」と「読みにくいレース」がある。

      読みやすいレース（quality高）:
        → 先行艇が圧倒的有利、攻撃艇が1艇に絞れる
        → 買い目を少点数に絞れる根拠になる
        → 合成オッズが低くても期待値が確保できる

      読みにくいレース（quality低）:
        → 先行艇と追走艇が接戦、攻撃艇が複数
        → 何でも起きる → 買い目を絞ることに根拠がない
        → 高いqualityのレースを待つ方が合理的

    【quality構成要素】（v3: 100点満点再設計）
      (1) 先行優位度  (0〜35点): lead_margin が大きいほど高い
      (2) 主軸集中度  (0〜25点): 主軸攻撃が強く副軸が弱いほど高い
      (3) 展開2択度   (0〜20点): 逃げか1つの飛びかに絞れているほど高い
      (4) 展開確定度  (0〜30点): tenkai_pattern を A=30/B=20/C=10/D=0 に変換
      (5) 接戦ペナルティ (-10〜0点): 3艇以上が接戦のとき減点
      合計最大 110点 → 100点にクリップ

    Returns
    -------
    dict:
        quality_score  : 0〜100
        quality_rank   : "S"(>=75)/"A"(>=55)/"B"(>=40)/"C"(>=25)/"D"(<25)
        quality_verdict: "展開が絞れている" / "要注意（展開流動的）" / "見送り推奨（混戦）"
        bet_size_guide : "点数を絞れる" / "標準点数" / "増やすか見送り"
        components     : 各要素のスコア（デバッグ用）
        narrative      : qualityの説明（自然言語）
    """
    score = 0.0
    components = {}

    # (1) 先行優位度（0〜35点）
    # v3: 上限を40→35に変更（展開確定度30点追加に伴う配点調整）
    lead_margin = first_turn.get("lead_margin", 0)
    if lead_margin > 0.08:
        lead_score = 35.0
    elif lead_margin > 0.05:
        lead_score = 26.0
    elif lead_margin > 0.02:
        lead_score = 17.0
    elif lead_margin > 0.00:
        lead_score = 8.0
    else:
        lead_score = 0.0
    score += lead_score
    components["先行優位度"] = round(lead_score, 1)

    # (2) 主軸集中度（0〜25点）
    # v3: 上限を30→25に変更（展開確定度30点追加に伴う配点調整）
    # 主軸強・副軸弱 = 集中度高
    main = conflict_map.get("main_conflict") or {}
    sub  = conflict_map.get("sub_conflict") or {}
    main_str = main.get("strength", 0) or 0
    sub_str  = sub.get("strength", 0) or 0
    if main_str > 0:
        concentration = main_str / max(main_str + sub_str, 1)
        axis_score = min(25.0, concentration * 25.0 * (main_str / 50.0))
    else:
        axis_score = 0.0
    score += axis_score
    components["主軸集中度"] = round(axis_score, 1)

    # (3) 展開2択度（0〜20点）
    # s1_prob_est が渡されている場合は逃げ確率を使用
    # 渡されていない場合はパターンで推定
    if s1_prob_est is not None:
        # 逃げ一択 or 飛び一択に近いほど高い
        two_choice = abs(s1_prob_est - 0.5) * 2  # 0〜1
        two_score  = two_choice * 20.0
    else:
        pattern = first_turn.get("pattern", "")
        if first_turn.get("pattern_strength") == "強":
            two_score = 20.0
        elif first_turn.get("pattern_strength") == "中":
            two_score = 12.0
        else:
            two_score = 5.0
    score += two_score
    components["展開2択度"] = round(two_score, 1)

    # (4) 展開確定度（0〜30点）
    # v3新設: tenkai_pattern を要素として組み込む（後付け補正を廃止）
    # A（鉄板逃げ）=30点: 展開が最も読みやすい
    # B（主役展開）=20点: 主役が読めている
    # C（拮抗）   =10点: 展開が割れており不安定
    # D（荒れ）   = 0点: 混戦で予測困難
    _TP_SCORE = {"A": 30.0, "B": 20.0, "C": 10.0, "D": 0.0}
    tp_score = _TP_SCORE.get(str(tenkai_pattern), 10.0)  # 未確定時はC相当
    score += tp_score
    components["展開確定度"] = round(tp_score, 1)

    # (5) 接戦ペナルティ（-10〜0点）
    entry_order = first_turn.get("entry_order", [])
    if len(entry_order) >= 3:
        eff_sts = [st for _, st in entry_order[:4]]
        if len(eff_sts) >= 3:
            spread = eff_sts[2] - eff_sts[0]
            if spread < 0.03:  # 上位3艇が0.03秒以内 = 接戦
                penalty = -10.0
                score += penalty
                components["接戦ペナルティ"] = round(penalty, 1)

    # 合計最大110点（35+25+20+30）→ 100点にクリップ
    score = max(0.0, min(100.0, score))

    # ── ランク判定（v3: 100点満点基準に閾値を再設計）────────────────────────
    # 設計思想:
    #   S(>=80): 先行差大+主役明確+展開A → 買い目を絞れる鉄板レース
    #   A(>=60): 先行差中+主役読める+展開B → 標準点数で十分
    #   B(>=40): 先行差小 or 展開C → やや流動的、点数増か厳選
    #   C(>=20): 複数要素が低い → 読みにくい、参加基準UP
    #   D(<20) : 全要素低+展開D → 混戦、見送り推奨
    if score >= 80:
        quality_rank    = "S"
        quality_verdict = "展開が絞れている（買い目を絞る根拠あり）"
        bet_size_guide  = "点数を絞れる（少点数で合成オッズを高く保てる）"
    elif score >= 60:
        quality_rank    = "A"
        quality_verdict = "ある程度の展開集中（標準的な点数で対応可）"
        bet_size_guide  = "標準点数"
    elif score >= 40:
        quality_rank    = "B"
        quality_verdict = "展開やや流動的（点数増か厳選が必要）"
        bet_size_guide  = "点数増か主軸に絞る"
    elif score >= 20:
        quality_rank    = "C"
        quality_verdict = "展開が読みにくい（参加基準を上げる）"
        bet_size_guide  = "参加するなら大幅厳選"
    else:
        quality_rank    = "D"
        quality_verdict = "混戦（展開予測が困難。見送り推奨）"
        bet_size_guide  = "見送り推奨"

    # 自然言語
    narrative = (
        f"展開quality: {quality_rank}（{score:.0f}点）\n"
        f"→ {quality_verdict}\n"
        f"→ {bet_size_guide}"
    )

    return {
        "quality_score":   round(score, 1),
        "quality_rank":    quality_rank,
        "quality_verdict": quality_verdict,
        "bet_size_guide":  bet_size_guide,
        "components":      components,
        "narrative":       narrative,
    }


def _calc_affinity_score(results, venue_stats_master, venue):
    """
    出走6選手の相互作用を定量化し、各艇が「インを脅かす力」を数値化する。

    【設計思想】
    イン飛びは「インが弱い」だけでなく「誰かが積極的に攻める」ときに起きる。
    この関数は各艇の攻撃力と、1号艇の被攻撃脆弱性を組み合わせて評価する。

    出力 (dict):
      attack_score[waku]  : 各艇のイン攻撃ポテンシャル (0〜100)
      threat_total        : 全艇合計攻撃力 (イン脅威度)
      boat1_vulnerability : 1号艇の被攻撃脆弱性スコア (0〜100、高いほど飛びやすい)
      dominant_attacker   : 最も脅威の高い艇番 (str)
      affinity_summary    : 各艇の攻撃根拠テキスト dict

    【スコア計算要素】
    A. 差し力 (2コース艇)  : 差し% × ST速さ（1号艇との相対ST差）
    B. まくり力 (3〜5C)    : (まくり% + まくり差し%) × コース別1着率 × ST出足補正
    C. 1号艇の脆弱性       : 差され% + 捲られ% + ST遅さペナルティ + STばらつき
    D. A1選手補正          : 外枠にA1級選手がいる場合に攻撃力を+20%
    E. 今節成績補正        : 直近好成績の艇は攻撃スコアを最大+15%加算
    """
    NATIONAL_ATTACK_BASE = {
        "2": 0.137, "3": 0.134, "4": 0.111, "5": 0.066, "6": 0.021
    }

    res1 = next((r for r in results if r["waku"] == "1"), None)
    st1  = res1.get("avg_st") if res1 else None
    cm1  = res1.get("raw_cm", {}) if res1 else {}

    # 1号艇の脆弱性スコア（0〜100）
    # ※ "差し%"（_get_cm_val経由）は「自分が差して勝った割合」であり脆弱性評価には使わない
    nige_pct    = safe_float(_get_cm_val(cm1, "逃げ%"), 0) or 0    # 逃げ率（高いほど脆弱性低）

    # 被攻撃実績（update_masterが生成する被決まり手%）
    sasar_vuln = safe_float(cm1.get("差され%"), 0) or 0
    makur_vuln = safe_float(cm1.get("捲られ%"), 0) or 0
    maksa_vuln = safe_float(cm1.get("捲り差され%"), 0) or 0  # update_master出力キーに統一

    # ST脆弱性（1号艇が遅いほど脆弱）
    st_vuln = 0.0
    if st1 is not None:
        if st1 > 0.18:
            st_vuln = 30.0
        elif st1 > 0.15:
            st_vuln = 15.0
        elif st1 > 0.12:
            st_vuln = 5.0

    # STばらつき（不安定なほど脆弱）
    pm1 = res1.get("raw_pm", {}) if res1 else {}
    st_stable = safe_float(pm1.get("ST安定\nスコア") or pm1.get("ST安定スコア"))
    st_unstable_vuln = 0.0
    if st_stable is not None:
        if st_stable < 40:
            st_unstable_vuln = 20.0
        elif st_stable < 60:
            st_unstable_vuln = 10.0

    # ── FLY数・出遅れ数によるST脆弱性補正 ────────────────────────────────
    # 選手指数マスタに FLY数・出遅れ数 が集計されているが、従来は未使用だった。
    # FLY（フライング） → ペナルティ後の緊張・心理的影響で次走STが不安定になりやすい
    # 出遅れ（出遅れ数が多い）→ スロースタートの癖がある → イン逃げ失敗リスクUP
    #
    # FLY補正:
    #   FLY数が1走内に存在 → 直近にフライングあり → ST脆弱性+15
    #   FLY数が2走以上    → 繰り返しフライング → ST脆弱性+25（最大値）
    # 出遅れ補正:
    #   出遅れ数/総出走数 が 5%超 → 出遅れ癖あり → ST脆弱性+10
    #   出遅れ数/総出走数 が 10%超 → 出遅れ癖強い → ST脆弱性+20
    fly_count    = safe_float(pm1.get("FLY数"),    0) or 0
    late_count   = safe_float(pm1.get("出遅れ数"), 0) or 0
    total_runs_pm = safe_float(pm1.get("ST計測件数") or pm1.get("総出走数"), 0) or 1

    fly_vuln = 0.0
    if fly_count >= 2:
        fly_vuln = 25.0
    elif fly_count >= 1:
        fly_vuln = 15.0

    late_rate = late_count / max(total_runs_pm, 1)
    late_vuln = 0.0
    if late_rate >= 0.10:
        late_vuln = 20.0
    elif late_rate >= 0.05:
        late_vuln = 10.0

    boat1_vulnerability = min(100.0,
        (sasar_vuln * 100) * 0.30 +          # 差された実績（旧0.35から微調整）
        (makur_vuln * 100) * 0.22 +          # 捲られた実績
        (maksa_vuln * 100) * 0.12 +          # 捲り差された実績
        st_vuln * 0.12 +                     # ST遅さペナルティ
        st_unstable_vuln * 0.08 +            # STばらつきペナルティ
        fly_vuln * 0.10 +                    # 【新追加】FLY履歴ペナルティ
        late_vuln * 0.06 +                   # 【新追加】出遅れ癖ペナルティ
        max(0.0, (40.0 - nige_pct) * 0.5)   # 逃げ%が低いほど加算
    )

    # 各艇の攻撃スコアを計算
    attack_score  = {}
    affinity_summary = {}

    for r in results:
        w = r["waku"]
        if w == "1":
            attack_score[w] = 0.0
            affinity_summary[w] = "1号艇（逃げ側）"
            continue

        cm  = r.get("raw_cm", {})
        pm  = r.get("raw_pm", {})
        st  = r.get("avg_st")

        # 基礎攻撃力（決まり手%）
        sashi_pct = safe_float(_get_cm_val(cm, "差し%"), 0) or 0
        makuri_pct = (safe_float(_get_cm_val(cm, "まくり%"), 0) or 0) + \
                     (safe_float(_get_cm_val(cm, "まくり差し%"), 0) or 0)
        nat_base   = NATIONAL_ATTACK_BASE.get(w, 0.05) * 100

        if w == "2":
            # 2号艇：差し特化
            base_attack = sashi_pct if sashi_pct > 0 else nat_base * 0.3
            attack_type = f"差し{sashi_pct:.0f}%"
        else:
            # 3〜6号艇：まくり系
            base_attack = makuri_pct if makuri_pct > 0 else nat_base * 0.4
            attack_type = f"まくり系{makuri_pct:.0f}%"

        # ST相対補正（1号艇より速い艇は攻撃力UP）
        st_boost = 1.0
        if st is not None and st1 is not None:
            diff = st1 - st  # 正 = この艇が速い
            if diff > 0.03:
                st_boost = 1.20
            elif diff > 0.01:
                st_boost = 1.10
            elif diff < -0.03:
                st_boost = 0.85

        # 今節成績補正（直近の実走成績から個人の調子を反映）
        kosetsu = str(r.get("kosetsu", ""))
        kosetsu_boost = 1.0
        if kosetsu and kosetsu not in ("", "None", "nan", "-"):
            try:
                tokens = [t.strip() for t in re.split(r"[-・/]", kosetsu)]
                win_count = tokens.count("1")
                if win_count >= 2:
                    kosetsu_boost = 1.15
                elif win_count == 1:
                    kosetsu_boost = 1.07
            except Exception:
                pass

        # コース別実績補正（会場別コースマスタ優先）
        # ※ 級別（A1/A2等）は使用しない。
        #   個々の選手が「実際にそのコースで何をしてきたか」
        #   （決まり手%・ST・今節成績）のみで評価する。
        venue_win = safe_float(r.get("win1_rate")) or 0

        # ── 展示タイム補正（当日の調子を攻撃力に反映）────────────────────
        # tenji_hensa: 50基準（高=速=攻撃力UP）
        # 偏差値55以上 → ×1.12 / 45以下 → ×0.88
        tenji_hensa = safe_float(r.get("tenji_hensa"))
        tenji_boost = 1.0
        if tenji_hensa is not None:
            tenji_boost = max(0.88, min(1.12, 1.0 + (tenji_hensa - 50) / 50 * 1.2))

        # ── モーター2連率補正（全艇平均比）────────────────────────────────
        # 平均+5pt以上優秀 → ×1.08 / -5pt以下 → ×0.92
        motor2_val   = safe_float(r.get("motor2"))
        motor2_boost = 1.0
        if motor2_val is not None:
            m2_all = [safe_float(rx.get("motor2")) for rx in results if safe_float(rx.get("motor2")) is not None]
            if m2_all:
                m2_mean      = sum(m2_all) / len(m2_all)
                motor2_boost = max(0.92, min(1.08, 1.0 + (motor2_val - m2_mean) / 10 * 0.16))

        score = base_attack * st_boost * kosetsu_boost * tenji_boost * motor2_boost
        # 実績との整合（選手の実際のコース別1着率で加重）
        score = score * 0.7 + venue_win * 100 * 0.3

        attack_score[w] = round(score, 2)
        summary_parts = [attack_type]
        if st_boost > 1.05:
            summary_parts.append(f"ST優位(×{st_boost:.2f})")
        elif st_boost < 0.90:
            summary_parts.append(f"ST劣位(×{st_boost:.2f})")
        if kosetsu_boost > 1.0:
            summary_parts.append(f"今節好調(×{kosetsu_boost:.2f})")
        if tenji_boost > 1.05:
            summary_parts.append(f"展示速い(×{tenji_boost:.2f})")
        elif tenji_boost < 0.95:
            summary_parts.append(f"展示遅い(×{tenji_boost:.2f})")
        if motor2_boost > 1.03:
            summary_parts.append(f"モーター優(×{motor2_boost:.2f})")
        elif motor2_boost < 0.97:
            summary_parts.append(f"モーター劣(×{motor2_boost:.2f})")
        affinity_summary[w] = " / ".join(summary_parts)

    # 合計攻撃力（1号艇除く）
    threat_total = sum(v for k, v in attack_score.items() if k != "1")

    # 最大攻撃艇
    outer_scores = {k: v for k, v in attack_score.items() if k != "1"}
    dominant_attacker = max(outer_scores, key=lambda k: outer_scores[k]) if outer_scores else "-"

    return {
        "attack_score":       attack_score,
        "threat_total":       round(threat_total, 2),
        "boat1_vulnerability": round(boat1_vulnerability, 1),
        "dominant_attacker":  dominant_attacker,
        "affinity_summary":   affinity_summary,
    }


# ============================================================
# ★ 新機能(2) イン飛び条件総合判定
# ============================================================
def _judge_tobi_scenario(results, affinity, venue_stats):
    """
    イン飛び（1号艇が1着にならない）の総合確率と根拠を返す。

    【判定ロジック】
    以下5つの条件を重みづけして飛び確率(0〜100)を算出する。

    条件(1)  1号艇の脆弱性スコア（被差され・捲られ実績）
    条件(2)  攻撃艇の合計脅威スコア（全艇の攻撃力合算）
    条件(3)  会場のイン逃げ率（低い会場ほど飛びやすい）
    条件(4)  支配的攻撃艇の存在感（最強攻撃艇のスコアが突出しているか）
    条件(5)  スリット不利（1号艇STが相対的に遅い場合）

    出力:
      tobi_prob   : イン飛び推定確率 (0〜100)
      tobi_rank   : 飛び確率ランク  S(>70)/A(>55)/B(>40)/C(>25)/D(<=25)
      main_threat : 最も危険な飛ばし役の艇番
      reasons     : 判定根拠リスト
      tobi_type   : 予想される飛び方 ("差し" / "まくり" / "まくり差し" / "不明")
    """
    reasons = []
    score = 0.0  # 0〜100: 高いほどイン飛び確率大

    vuln  = affinity["boat1_vulnerability"]
    total = affinity["threat_total"]
    dom   = affinity["dominant_attacker"]
    atk   = affinity["attack_score"]

    # 条件(1): 1号艇の脆弱性（最大35点）
    vul_contrib = min(35.0, vuln * 0.35)
    score += vul_contrib
    if vuln >= 40:
        reasons.append(f"1号艇脆弱性スコア{vuln:.0f}（被差し・捲られ実績大）")
    elif vuln >= 20:
        reasons.append(f"1号艇脆弱性スコア{vuln:.0f}（やや脆弱）")

    # 条件(2): 攻撃艇の合計脅威（最大30点）
    # threat_total の自然な範囲は0〜150程度 → 100以上で満点
    threat_contrib = min(30.0, total / 100.0 * 30.0)
    score += threat_contrib
    if total >= 80:
        reasons.append(f"攻撃艇合計スコア{total:.0f}（攻撃力が強い）")
    elif total >= 50:
        reasons.append(f"攻撃艇合計スコア{total:.0f}（中程度の攻撃）")

    # 条件(3): 会場イン逃げ率（最大20点）
    in_rate = venue_stats.get("in_rate")
    if in_rate is not None:
        # イン逃げ率が低い会場ほどスコアUP（逃げ率50%以下で最大）
        venue_contrib = max(0.0, (0.65 - float(in_rate)) / 0.65 * 20.0)
        score += venue_contrib
        if float(in_rate) < 0.45:
            reasons.append(f"会場イン逃げ率{float(in_rate)*100:.0f}%（飛びやすい会場）")

    # 条件(4): 支配的攻撃艇の突出度（最大10点）
    if dom != "-":
        dom_score = atk.get(dom, 0)
        other_scores = [v for k, v in atk.items() if k != "1" and k != dom]
        if other_scores:
            avg_other = sum(other_scores) / len(other_scores)
            if avg_other > 0 and dom_score > avg_other * 1.5:
                score += 10.0
                reasons.append(f"{dom}号艇が突出した攻撃力({dom_score:.0f}pt)：明確な飛ばし役")
            elif dom_score > 0:
                score += 5.0
                reasons.append(f"{dom}号艇が攻撃力最大({dom_score:.0f}pt)")

    # 条件(5): スリット不利（1号艇のSTが遅い）（最大5点）
    res1 = next((r for r in results if r["waku"] == "1"), None)
    if res1:
        st1 = res1.get("avg_st")
        all_sts = [r.get("avg_st") for r in results if r.get("avg_st") is not None and r["waku"] != "1"]
        if st1 is not None and all_sts:
            faster_count = sum(1 for s in all_sts if s < st1 - 0.02)
            if faster_count >= 3:
                score += 5.0
                reasons.append(f"1号艇STが相対的に遅い（{faster_count}艇が有意に速い）")

    score = min(100.0, max(0.0, score))

    # ランク判定
    if score >= 70:
        tobi_rank = "S"
    elif score >= 55:
        tobi_rank = "A"
    elif score >= 40:
        tobi_rank = "B"
    elif score >= 25:
        tobi_rank = "C"
    else:
        tobi_rank = "D"

    # 飛び方の予測（最強攻撃艇のコースと決まり手から推定）
    tobi_type = "不明"
    if dom != "-":
        dom_r = next((r for r in results if r["waku"] == dom), None)
        if dom_r:
            cm_dom = dom_r.get("raw_cm", {})
            sashi  = safe_float(_get_cm_val(cm_dom, "差し%"), 0) or 0
            makuri = safe_float(_get_cm_val(cm_dom, "まくり%"), 0) or 0
            maksa  = safe_float(_get_cm_val(cm_dom, "まくり差し%"), 0) or 0
            if dom == "2":
                tobi_type = "差し"
            elif makuri >= maksa and makuri >= sashi:
                tobi_type = "まくり"
            elif maksa >= makuri and maksa >= sashi:
                tobi_type = "まくり差し"
            elif sashi > 0:
                tobi_type = "差し"

    return {
        "tobi_prob":   round(score, 1),
        "tobi_rank":   tobi_rank,
        "main_threat": dom,
        "reasons":     reasons,
        "tobi_type":   tobi_type,
        "affinity":    affinity,
    }


# ============================================================
# ★ 買い方ヒント生成（一気通貫：根拠→展開→買い目）
# ============================================================
def _generate_tenkai_story(results, venue, venue_stats, race_judgment, bet_suggestions):
    """
    あなたの7ステップ思考フローをそのまま1つのストーリーとして出力する。

    (1) 1号艇は逃げるか
    (2) 逃げる → 2・3着は誰か
    (3) 逃げない → 誰が主役か・決まり手は何か
    (4) その決まり手なら2・3着は誰か
    (5) 主役が崩れたとき誰が浮上するか
    (6) 崩れ後に1号が逃げを拾う確率
    (7) 他の艇が展開を突いたとき2・3着は誰か
    → 最終買い目サマリー
    """
    rj  = race_judgment  or {}
    bet = bet_suggestions or {}

    # ── データ取り出し ──────────────────────────────────────────────────
    # scenario_engine の計算結果を最優先で使用
    # nige_prob / escape_rank は scenario_engine が被決まり手ベースで計算した値
    s1_prob      = bet.get("nige_prob") or bet.get("s1_prob") or rj.get("s1_prob") or 0.0
    fp_map       = bet.get("first_prob_map", {}) or {}
    w1_escape    = rj.get("w1_escape",    {}) or {}
    main_player  = rj.get("main_player",  {}) or {}
    escape_fb    = rj.get("escape_fallback", {}) or {}
    dark_horse   = rj.get("dark_horse",   {}) or {}
    conflict_map = rj.get("conflict_map", {}) or {}
    neraime_2nd  = bet.get("neraime_2nd", []) or []
    candidates   = bet.get("candidates",  []) or []
    tenkai_pat   = bet.get("tenkai_pattern", rj.get("tenkai_pattern", "?"))
    # scenario_engine 計算済みのシナリオデータ
    scenario_a   = bet.get("scenario_a", {}) or {}
    scenario_b   = bet.get("scenario_b", {}) or {}

    rd = [r for r in (results or []) if isinstance(r, dict)]
    name_map = {str(r.get("waku","")): r.get("name","") for r in rd}

    _WAKU_CIRCLE = {"1":"[1]","2":"[2]","3":"[3]","4":"[4]","5":"[5]","6":"[6]"}
    def wn(w):
        """艇番を[1]〜[6]で返す"""
        return _WAKU_CIRCLE.get(str(w), f"{w}号")

    def pct(v):
        """0〜1のfloatを%文字列に変換"""
        try:
            return f"{float(v)*100:.0f}%"
        except (TypeError, ValueError):
            return "-"

    lines = []

    # ==================================================================
    # (1) 1号艇は逃げるか
    # scenario_engine の nige_prob / escape_rank を最優先で使用
    # ==================================================================
    esc_rank  = bet.get("escape_rank") or w1_escape.get("escape_rank", "中")
    esc_prob  = s1_prob  # nige_prob（被決まり手ベース）
    esc_pct   = f"{s1_prob*100:.0f}%"
    thr_w     = w1_escape.get("top_threat_waku",  "-")
    thr_t     = w1_escape.get("top_threat_type",  "-")
    thr_s     = w1_escape.get("top_threat_score", 0)

    rank_mark = {"高": "[高]", "中": "[中]", "低": "[低]"}.get(esc_rank, "[-]")
    lines.append(
        f"(1) 1号艇 逃げ力：{esc_pct}【{esc_rank}】{rank_mark}\n"
        f"   最大脅威：{wn(thr_w)}（{thr_t}）"
    )

    # ==================================================================
    # (2) 逃げた場合の2・3着（展開別残存マスタ活用）
    # ==================================================================
    if neraime_2nd:
        # 残存型狙い目から2着候補を取得（展開別残存マスタ参照済み）
        top3_2nd = neraime_2nd[:3]
        s2_str = "  ".join(
            f"{n['waku']}号{n['r2_rate']*100:.0f}%"
            for n in top3_2nd
        )
        # 3着以内率から2着率を引いて純3着率を計算
        s3_str = "  ".join(
            f"{n['waku']}号{max(n['r3i_rate']-n['r2_rate'],0)*100:.0f}%"
            for n in top3_2nd
        )
    else:
        # circle_pctから2着候補を生成
        circ_sorted = sorted(
            [(r["waku"], r.get("circle_pct") or 0)
             for r in rd if r["waku"] != "1"],
            key=lambda x: x[1], reverse=True
        )
        s2_str = "  ".join(f"{w}号{v:.0f}%" for w, v in circ_sorted[:3])
        s3_str = "（展示後確認）"

    # 逃げ時買い目上位3点
    nige_buys = sorted(
        [c["combo"] for c in candidates if c.get("combo","").split("-")[0] == "1"],
        key=lambda x: next((c["prob"] for c in candidates if c["combo"]==x), 0),
        reverse=True
    )[:3]
    nige_buy_str = " / ".join(nige_buys) if nige_buys else "─"

    lines.append(
        f"\n(2) 逃げた場合\n"
        f"   2着候補：{s2_str}\n"
        f"   純3着候補：{s3_str}\n"
        f"   └ 買い目：{nige_buy_str}"
    )

    # ==================================================================
    # (3) 主役は誰か・決まり手は何か
    # ==================================================================
    main_w     = main_player.get("main_waku",  "-")
    main_type  = main_player.get("main_type",  "-")
    main_score = main_player.get("main_score", 0)
    sub_w      = main_player.get("sub_waku")
    sub_type   = main_player.get("sub_type",   "-")
    sub_score  = main_player.get("sub_score",  0)

    main_prob  = fp_map.get(str(main_w), 0)

    sub_line = ""
    if sub_w:
        sub_line = f"\n   対抗主役：{wn(sub_w)}【{sub_type}】{pct(sub_score)}"

    lines.append(
        f"\n(3) 主役（逃げない場合）\n"
        f"   {wn(main_w)}【{main_type}】攻撃力{pct(main_score)} → 1着確率{pct(main_prob)}"
        f"{sub_line}"
    )

    # ==================================================================
    # (4) 主役が来た場合の2・3着（展開別残存マスタ活用）
    # ==================================================================
    p2_cands = main_player.get("place2_candidates", []) or []
    p3_cands = main_player.get("place3_candidates", []) or []

    p2_str = "  ".join(f"{w}号({s:.0f}pt)" for w, s in p2_cands[:3]) if p2_cands else "─"
    p3_str = "  ".join(f"{w}号({s:.0f}pt)" for w, s in p3_cands[:3]) if p3_cands else "─"

    # 主役頭の買い目上位3点
    main_buys = sorted(
        [c["combo"] for c in candidates
         if c.get("combo","").split("-")[0] == str(main_w)
         and not c.get("is_fallback_bet") and not c.get("is_dh_bet")],
        key=lambda x: next((c["prob"] for c in candidates if c["combo"]==x), 0),
        reverse=True
    )[:3]
    main_buy_str = " / ".join(main_buys) if main_buys else "─"

    lines.append(
        f"\n(4) {wn(main_w)}が来た場合\n"
        f"   2着残存：{p2_str}\n"
        f"   3着残存：{p3_str}\n"
        f"   └ 買い目：{main_buy_str}"
    )

    # ==================================================================
    # (5) 主役が崩れたとき誰が浮上するか
    # ==================================================================
    dh_ok    = dark_horse.get("is_valid", False)
    dh_top   = dark_horse.get("top_waku",  "-")
    dh_score = dark_horse.get("top_score", 0)
    dh_cands = dark_horse.get("dark_horse_candidates", []) or []
    cb       = conflict_map.get("collapse_beneficiary", []) or []

    if dh_ok and dh_cands:
        dh_str = "  ".join(
            f"{w}号【{tag}】{s*100:.0f}%"
            for w, s, tag in dh_cands[:2]
        )
    elif cb:
        dh_str = "  ".join(f"{w}号({s*100:.0f}%)" for w, s in cb[:2])
    else:
        dh_str = "─"

    fly_type = escape_fb.get("fly_type", "-")
    lines.append(
        f"\n(5) {wn(main_w)}が崩れた場合\n"
        f"   浮上候補：{dh_str}\n"
        f"   崩れ方：{fly_type}"
    )

    # ==================================================================
    # (6) 崩れ後に1号が逃げを拾う確率
    # ==================================================================
    fb_prob = escape_fb.get("fallback_prob", 0)
    fb_rank = escape_fb.get("fallback_rank", "-")
    fb_pct  = escape_fb.get("fallback_pct",  pct(fb_prob))

    fb_emoji = {"高": "[緑]", "中": "[黄]", "低": "[赤]"}.get(fb_rank, "[白]")
    lines.append(
        f"\n(6) 崩れ後に1号が残す確率：{fb_pct}【{fb_rank}】{fb_emoji}"
    )

    # ==================================================================
    # (7) 他の艇が展開を突いたとき（SC漁夫・2着3着）
    # ==================================================================
    sc_buys = sorted(
        [c["combo"] for c in candidates if c.get("is_sc_bet")],
        key=lambda x: next((c["prob"] for c in candidates if c["combo"]==x), 0),
        reverse=True
    )[:2]
    fb_buys = sorted(
        [c["combo"] for c in candidates if c.get("is_fallback_bet")],
        key=lambda x: next((c["prob"] for c in candidates if c["combo"]==x), 0),
        reverse=True
    )[:2]

    other_buys = sc_buys + fb_buys
    other_buy_str = " / ".join(other_buys) if other_buys else "─"

    if dh_ok:
        tobi_line = f"   展開突き候補：{wn(dh_top)}（浮上スコア{dh_score*100:.0f}%）"
    elif cb:
        top_cb = cb[0]
        tobi_line = f"   展開突き候補：{wn(top_cb[0])}（漁夫{top_cb[1]*100:.0f}%）"
    else:
        tobi_line = "   展開突き候補：─"

    lines.append(
        f"\n(7) 展開を他の艇が突く場合\n"
        f"{tobi_line}\n"
        f"   └ 潰れ・残存買い目：{other_buy_str}"
    )

    # ==================================================================
    # → 最終買い目サマリー
    # ==================================================================
    total_pts  = len(candidates)
    syn_odds   = bet.get("theory_syn_odds")
    skip       = bet.get("skip", False)
    skip_rsn   = bet.get("skip_reason", "")
    entry_grade = bet.get("entry_grade", "-")

    # 展開パターン絵文字
    tp_emoji = {"A": "[緑]鉄板", "B": "[赤]主役", "C": "[黄]拮抗", "D": "[紫]荒れ"}.get(tenkai_pat, "[白]")

    # 全買い目をセクション別に集計
    n_nige  = sum(1 for c in candidates if c.get("combo","").split("-")[0] == "1"
                  and not c.get("is_fallback_bet") and not c.get("is_dh_bet"))
    n_main  = sum(1 for c in candidates if c.get("combo","").split("-")[0] == str(main_w)
                  and not c.get("is_fallback_bet") and not c.get("is_dh_bet"))
    n_other = total_pts - n_nige - n_main

    skip_line = f"\n   [NG] {skip_rsn}" if skip else ""
    syn_line  = f"理論合成{syn_odds}倍" if syn_odds else ""

    lines.append(
        f"\n{'━'*30}\n"
        f"展開：{tp_emoji}  参加：{entry_grade}  {syn_line}\n"
        f"逃げ軸{n_nige}点 / 主役軸{n_main}点 / その他{n_other}点 = 計{total_pts}点"
        f"{skip_line}"
    )

    return "\n".join(lines)


def _generate_buy_hint(results, venue, venue_stats, race_judgment, bet_suggestions):
    """
    (8)考察の結論：(1)展開ストーリーと同じ書き方で出力する。
    ・丸数字（(1)〜(6)）を使用、選手名なし
    ・【】見出し＋・箇条書き形式
    """
    rj  = race_judgment  or {}
    bet = bet_suggestions or {}

    # ── データ取り出し ─────────────────────────────────────────────────
    nige_prob     = bet.get("nige_prob") or bet.get("s1_prob") or rj.get("s1_prob") or 0.0
    escape_rank   = bet.get("escape_rank") or (rj.get("w1_escape") or {}).get("escape_rank", "中")
    tenkai_pat    = bet.get("tenkai_pattern", rj.get("tenkai_pattern", "C"))
    scenario_a    = bet.get("scenario_a", {}) or {}
    scenario_b    = bet.get("scenario_b", {}) or {}
    mp            = scenario_b.get("main_player", {}) or rj.get("main_player", {}) or {}
    w1_escape     = rj.get("w1_escape",       {}) or {}
    escape_fb     = rj.get("escape_fallback", {}) or {}
    dark_horse    = rj.get("dark_horse",      {}) or {}
    himo_are      = rj.get("himo_are",        {}) or {}
    conflict_map  = rj.get("conflict_map",    {}) or {}

    ha_verdict    = himo_are.get("verdict", "対象外")
    dh_ok         = dark_horse.get("is_valid", False)
    dh_cands      = dark_horse.get("dark_horse_candidates", []) or []
    fb_prob       = escape_fb.get("fallback_prob", 0.0)
    collapse_bene = conflict_map.get("collapse_beneficiary", []) or []

    rd = [r for r in (results or []) if isinstance(r, dict)]

    # (1) と同じ丸数字変換
    def wn(w):
        return {"1": "(1)", "2": "(2)", "3": "(3)", "4": "(4)", "5": "(5)", "6": "(6)"}.get(str(w), f"{w}号")

    main_w    = str(mp.get("main_waku", "") or "")
    main_type = mp.get("main_type", "攻め")
    main_type_short = main_type.replace("系", "").replace("攻め", "").strip() or "攻め"
    sub_w     = str(mp.get("sub_waku", "") or "")
    thr_w     = str(w1_escape.get("top_threat_waku", "") or "")
    thr_t     = w1_escape.get("top_threat_type", "攻め")

    # シナリオA（逃げ展開）の2・3着候補（主役を除外）
    a_top2 = [str(w) for w, _ in (scenario_a.get("top_2nd") or [])[:4]
               if str(w) != main_w][:3]
    a_top3 = [str(w) for w, _ in (scenario_a.get("top_3rd") or [])[:4]
               if str(w) != main_w][:3]

    # シナリオB（主役展開）の2・3着候補
    b_top2 = [str(w) for w, _ in (scenario_b.get("second_sorted") or [])[:3]]
    b_top3 = [str(w) for w, _ in (scenario_b.get("third_sorted")  or [])[:3]]

    # 崩れ浮上候補
    ct = scenario_b.get("collapse_top") or [(str(w), s) for w, s in collapse_bene[:2]]

    # 買い目（本線/押さえ分割）
    cands     = bet.get("candidates") or []
    honsen    = [c for c in cands if c.get("tier") == "本線"]
    osaae     = [c for c in cands if c.get("tier") == "押さえ"]

    lines = []

    # ── 【展開考察】 ──────────────────────────────────────────────────
    lines.append("【展開考察】")

    # 1行目: 逃げ判定
    nige_pct = f"{nige_prob*100:.0f}%"
    if escape_rank == "高":
        nige_judge = f"(1)の逃げは堅い（逃げ力：高／{nige_pct}）。"
        line1 = f"{nige_judge}(1)中心の展開が濃厚。"
    elif escape_rank == "低":
        nige_judge = f"(1)の逃げは危うい（逃げ力：低／{nige_pct}）。"
        thr_note = f"最大の脅威は{wn(thr_w)}の{thr_t}。" if thr_w and thr_w not in ("", "-") else ""
        sub_note = f"対抗は{wn(sub_w)}。" if sub_w and sub_w not in ("", "-", main_w) else ""
        line1 = f"{nige_judge}{thr_note}{wn(main_w)}の{main_type_short}が主役。{sub_note}" if main_w and main_w != "-" else f"{nige_judge}{thr_note}"
    else:
        nige_judge = f"(1)の逃げは五分五分（逃げ力：中／{nige_pct}）。"
        thr_note = f"最大の脅威は{wn(thr_w)}の{thr_t}。" if thr_w and thr_w not in ("", "-") else ""
        sub_note = f"対抗は{wn(sub_w)}。" if sub_w and sub_w not in ("", "-", main_w) else ""
        line1 = f"{nige_judge}{thr_note}{wn(main_w)}が対抗主役。{sub_note}" if main_w and main_w != "-" else f"{nige_judge}{thr_note}"
    lines.append(line1.strip())

    # 箇条書き3行（(1)と完全同形式）
    a_2nd_str = "・".join(wn(w) for w in a_top2) if a_top2 else "-"
    a_3rd_str = "・".join(wn(w) for w in a_top3) if a_top3 else "-"
    lines.append(f"・逃げるなら　　→ 2着：{a_2nd_str}　3着：{a_3rd_str}")

    if main_w and main_w != "-":
        b_2nd_str = "・".join(wn(w) for w in b_top2) if b_top2 else "-"
        b_3rd_str = "・".join(wn(w) for w in b_top3) if b_top3 else "-"
        lines.append(f"・{wn(main_w)}{main_type_short}なら → 2着：{b_2nd_str}　3着：{b_3rd_str}")

        ct_str = "・".join(wn(str(w)) for w, _ in ct[:2]) if ct else "-"
        lines.append(f"・崩れれば　　　→ {ct_str}が浮上")

        # 崩れ後(1)残存
        if fb_prob > 0.05:
            lines.append(f"・崩れ後(1)残存　→ {fb_prob*100:.0f}%")

    # 漁夫
    sc_gyofu = rj.get("sc_gyofu_top3", []) or []
    if sc_gyofu:
        gy_str = "・".join(wn(str(w)) for w, *_ in sc_gyofu[:2])
        lines.append(f"・展開突き　　　→ {gy_str}（漁夫）")

    # ── 【買い目】 ────────────────────────────────────────────────────
    def _fmt(buy_list):
        if not buy_list:
            return "─"
        from lr_suggest import format_buy_list  # 循環import回避のため遅延import
        raw_combos = [c["combo"] for c in buy_list]
        parts = format_buy_list(raw_combos)
        # 6点ごとに改行
        rows = []
        for i in range(0, len(parts), 6):
            rows.append("　".join(parts[i:i+6]))
        return "\n".join(rows)

    # 本線・押さえラベル（パターン別）
    _HONSEN_LABEL = {
        "A": "本線（逃げ展開）",
        "B": "本線（主役展開）",
        "C": "本線（逃げ・主役両建て）",
        "D": "本線（主役・浮上展開）",
    }
    _OSAAE_LABEL = {
        "A": "押さえ（穴・荒れ展開）",
        "B": "押さえ（逃げ残存・崩れ）",
        "C": "押さえ（崩れ・漁夫展開）",
        "D": "押さえ（逃げ残存）",
    }

    lines.append("")
    if honsen:
        lines.append(f"【{_HONSEN_LABEL.get(tenkai_pat, '本線')}】")
        lines.append(_fmt(honsen))
    if osaae:
        lines.append(f"【{_OSAAE_LABEL.get(tenkai_pat, '押さえ')}】")
        lines.append(_fmt(osaae))
    if not honsen and not osaae:
        # tierキーがない旧データへの互換フォールバック
        buy_list = bet.get("buy_list") or []
        if buy_list:
            from lr_suggest import format_buy_list  # 循環import回避のため遅延import
            lines.append("【参考買い目】")
            parts = format_buy_list(buy_list)
            rows = []
            for i in range(0, len(parts), 6):
                rows.append("　".join(parts[i:i+6]))
            lines.append("\n".join(rows))

    # ヒモ広め/絞り
    if ha_verdict == "参加推奨":
        lines.append("※ヒモは広めに")
    elif ha_verdict == "点数絞り":
        lines.append("※ヒモは絞り推奨")
    elif ha_verdict == "不参加推奨":
        lines.append("※[!]見送り検討")

    # 見送り
    skip_reason = bet.get("skip_reason", "")
    if bet.get("skip") and skip_reason:
        lines.append(f"※ {skip_reason}")

    return "\n".join(lines)


def _judge_ryotate(race_judgment, tobi_scenario, venue_stats, s1_prob=None):
    """
    「イン逃げ狙い」「イン飛び狙い」「両建て」の3択を判定する。

    【判定ロジック v2 - 確率モデルとの一貫性確保】
    s1_prob（確率モデル由来）が渡された場合はそれを主軸にし、
    escape_score（定性スコア）との乖離を検出・調整する。

    - s1_prob が渡される場合（bet_suggestions確定後の再呼び出し）:
        確率値を直接 verdict の判定基準として使用し、
        定性スコアとの整合チェックを行う。
    - s1_prob が渡されない場合（初回暫定計算）:
        従来通り escape_score / tobi_score の差分で判定。

    整合性チェック:
      s1_prob が高い（>=0.65）のに escape_score が低い（<50）場合 →
        確率モデル優先で逃げスコアを上方補正し警告フラグを立てる。
      tobi_score が高い（>=55）のに s1_prob も高い（>=0.60）場合 →
        両建て推奨とし矛盾フラグを立てる。

    出力:
      verdict          : "逃げ狙い" / "飛び狙い" / "両建て推奨"
      confidence       : 判断の確信度 (0〜100)
      escape_score     : 逃げスコア（補正後）
      tobi_score       : 飛びスコア
      escape_pct       : 逃げ確率%（s1_prob * 100、確率モデル由来）
      tobi_pct         : 飛び確率%（(1 - s1_prob) * 100）
      reason           : 判定根拠
      buy_style        : 買い方の具体的指示
      consistency_warn : 定性スコアと確率モデルの乖離警告（True/False）
      realtime_hook    : リアルタイム情報で確認すべき事項
    """
    escape_score = float(race_judgment.get("score", 50))
    tobi_score   = float(tobi_scenario.get("tobi_prob", 30))

    # ── s1_prob による整合性チェックと補正 ──────────────────────────────
    consistency_warn = False
    consistency_note = ""

    if s1_prob is not None:
        fly_prob = 1.0 - s1_prob
        # s1_probを0〜100スケールのスコアに変換して escape_score と比較
        s1_score_equiv = s1_prob * 100.0

        # ケース(1): 確率モデルは逃げ優勢なのに定性スコアが低い
        if s1_prob >= 0.65 and escape_score < 50:
            consistency_warn = True
            consistency_note = (
                f"[!] 確率モデル逃げ{s1_prob*100:.0f}%だが定性スコア{escape_score:.0f}。"
                f"確率モデル優先で補正。"
            )
            # 確率モデルに寄せて escape_score を上方補正（加重平均）
            escape_score = round(escape_score * 0.35 + s1_score_equiv * 0.65, 1)

        # ケース(2): 確率モデルは飛び優勢なのに定性スコアが高い
        elif s1_prob < 0.45 and escape_score >= 65:
            consistency_warn = True
            consistency_note = (
                f"[!] 確率モデル逃げ{s1_prob*100:.0f}%（飛び優勢）だが定性スコア{escape_score:.0f}（高）。"
                f"両建てに引き寄せ。"
            )
            # 確率モデルに寄せて escape_score を下方補正
            escape_score = round(escape_score * 0.35 + s1_score_equiv * 0.65, 1)

        # ケース(3): 飛びスコアが高いのに s1_prob も高い（真の矛盾）
        elif tobi_score >= 55 and s1_prob >= 0.60:
            consistency_warn = True
            consistency_note = (
                f"[!] 飛びスコア{tobi_score:.0f}と逃げ確率{s1_prob*100:.0f}%が矛盾。"
                f"両建て推奨に強制。"
            )
            # この場合は両建てに強制するため escape_score を中間値に
            escape_score = round((escape_score + s1_score_equiv) / 2, 1)
            tobi_score   = round(tobi_score * 0.8, 1)   # 飛びスコアも緩める
    else:
        fly_prob = None

    diff = escape_score - tobi_score

    # ── 表示用確率（s1_prob 確定後のみ意味を持つ） ───────────────────────
    escape_pct = round(s1_prob * 100, 1) if s1_prob is not None else None
    tobi_pct   = round((1.0 - s1_prob) * 100, 1) if s1_prob is not None else None

    # リアルタイム情報差し込み口
    realtime_hook = {
        "展示タイム_確認事項":  "1号艇の展示タイムがレース内偏差値50未満なら飛びスコア+10",
        "直前オッズ_確認事項":  "1号艇単勝オッズが1.2倍未満なら過剰人気→飛び狙いの妙味UP",
        "進入_確認事項":        "枠なり進入確認後にコース変更があれば再判定を推奨",
        "hook_fn":              None,
    }

    if escape_score >= 65 and tobi_score < 40:
        verdict     = "逃げ狙い"
        confidence  = min(100, int(escape_score * 0.7 + (65 - tobi_score) * 0.3))
        buy_style   = (
            f"1号艇1着固定。2着は「circle_pct（イン逃げ時2着率）上位2〜3艇」に絞る。"
            f"3連単で5〜8点。"
        )
        reason = (
            f"逃げスコア{escape_score:.0f}（高）・飛びスコア{tobi_score:.0f}（低）。"
            f"イン逃げが成立しやすい局面。"
        )
        if escape_pct is not None:
            reason += f" 確率モデル逃げ{escape_pct:.0f}%。"

    elif tobi_score >= 55 and escape_score < 55:
        threat = tobi_scenario.get("main_threat", "-")
        ttype  = tobi_scenario.get("tobi_type", "不明")
        verdict     = "飛び狙い"
        confidence  = min(100, int(tobi_score * 0.7 + (65 - escape_score) * 0.3))
        buy_style   = (
            f"{threat}号艇1着候補（{ttype}）。2・3着は残りの内寄り艇を広めに。"
            f"3連単で6〜10点。1号艇2・3着付けは除外か最小限に。"
        )
        reason = (
            f"飛びスコア{tobi_score:.0f}（高）・逃げスコア{escape_score:.0f}（低）。"
            f"{threat}号艇が主な脅威（{ttype}）。"
        )
        if tobi_pct is not None:
            reason += f" 確率モデル飛び{tobi_pct:.0f}%。"

    else:
        verdict     = "両建て推奨"
        confidence  = max(10, 80 - int(abs(diff) * 1.5))
        threat = tobi_scenario.get("main_threat", "-")
        ttype  = tobi_scenario.get("tobi_type", "不明")
        buy_style   = (
            f"【逃げ軸】1号艇1着の買い目を確保（4〜5点）。"
            f"【飛び軸】{threat}号艇1着の買い目（3〜4点）。"
            f"合計7〜9点。両軸を保持し軸の比重を傾ける。"
        )
        reason = (
            f"逃げスコア{escape_score:.0f}・飛びスコア{tobi_score:.0f}（差{abs(diff):.0f}pt）。"
            f"拮抗しており単軸は危険。{threat}号艇({ttype})が飛ばし役候補。"
        )
        if escape_pct is not None:
            reason += f" 確率モデル逃げ{escape_pct:.0f}%/飛び{tobi_pct:.0f}%。"

    if consistency_warn and consistency_note:
        reason = consistency_note + " " + reason

    return {
        "verdict":          verdict,
        "confidence":       confidence,
        "escape_score":     round(escape_score, 1),
        "tobi_score":       round(tobi_score, 1),
        "escape_pct":       escape_pct,    # 確率モデル由来の逃げ%（None=初回暫定）
        "tobi_pct":         tobi_pct,      # 確率モデル由来の飛び%
        "reason":           reason,
        "buy_style":        buy_style,
        "consistency_warn": consistency_warn,
        "realtime_hook":    realtime_hook,
    }


def _judge_himo_are(results, race_judgment):
    """
    ヒモ荒れ判定：1号艇が有力本命のときに「2・3着ヒモが荒れるか」を評価する。

    【v2 変更点】
    旧版は rel_win1 >= 60% という高すぎる閾値で「対象外」が大半を占めていた。
    番組表確定時点では 45% 以上あれば参加/見送り判断の材料として十分有効。

    【判定フロー v2】
    Step1: rel_win1 >= 45% → 判定対象（旧60%→45%に緩和）
    Step2: 最有力3連単の推定確率と2着集中度でヒモ固まり度を評価
    Step3: 展示前推奨アクションを明示（展示確認トリガーを含む）

    【閾値基準 v2】
    max_combo_prob:
      >= 0.25 → 不参加推奨（推定最高人気オッズ ~= 5倍以下）
      0.12〜0.25 → 点数絞り
      < 0.12   → 参加推奨（ヒモ分散・広め流し）
    """
    res1     = next((r for r in results if r["waku"] == "1"), None)
    rel_win1 = res1.get("rel_win1") if res1 else None

    NOT_TARGET = {
        "is_target": False, "verdict": "対象外", "max_combo_prob": None,
        "est_top_odds": None, "circle_concentration": None,
        "eligible_count": 0, "bet_adj": 0,
        "reason": "1号艇rel_win1 < 45%: 通常判定に委ねる",
        "tenji_trigger": "",
    }
    if rel_win1 is None or rel_win1 < 45.0:
        return NOT_TARGET

    # ── Step2: 組み合わせ確率を計算 ──────────────────────────────────────
    wakus_rest = [r["waku"] for r in results if r["waku"] != "1"]
    sum_rel    = sum(r.get("rel_win1") or 0 for r in results) or 100.0
    p1_win     = rel_win1 / sum_rel

    circ_raw  = {r["waku"]: max(r.get("circle_pct") or 0, 0.001)
                 for r in results if r["waku"] != "1"}
    total_circ = sum(circ_raw.values()) or 1.0
    idx3_raw  = {r["waku"]: max(float(r.get("idx3") or 0), 0.001)
                 for r in results if r["waku"] != "1"}

    combo_probs = []
    for second in wakus_rest:
        p2 = circ_raw[second] / total_circ
        remaining = [w for w in wakus_rest if w != second]
        total_i3  = sum(idx3_raw[w] for w in remaining) or 1.0
        for third in remaining:
            p3   = idx3_raw[third] / total_i3
            prob = p1_win * p2 * p3
            combo_probs.append((f"1-{second}-{third}", prob))

    combo_probs.sort(key=lambda x: x[1], reverse=True)
    max_combo_prob = combo_probs[0][1] if combo_probs else 0.0
    est_top_odds   = round(1.0 / (max_combo_prob * 0.75), 1) if max_combo_prob > 0 else 999.9

    # ── Step3: 2着集中度 ──────────────────────────────────────────────────
    circ_sorted   = sorted(circ_raw.items(), key=lambda x: x[1], reverse=True)
    top2_circ_sum = (
        (circ_sorted[0][1] + circ_sorted[1][1]) / total_circ * 100
        if len(circ_sorted) >= 2 else 100.0
    )

    # ── Step4: 有効組み合わせ数 ────────────────────────────────────────────
    rank     = (race_judgment or {}).get("rank", "B")
    TARGET_BETS = {"S": 6, "A": 8, "B": 9, "C": 6, "D": 6}
    target_n = TARGET_BETS.get(rank, 8)
    _vc1 = (race_judgment or {}).get("venue_c1_win_rate")
    if _vc1 is not None:
        target_n += 2 if _vc1 < 0.45 else (1 if _vc1 < 0.50 else 0)
    eligible_count = min(target_n, len(combo_probs))

    # ── Step5: 総合判定（v2: 閾値を緩和・展示確認トリガー追加）─────────────
    circ_adj = 0.04 if top2_circ_sum >= 70 else (-0.04 if top2_circ_sum < 55 else 0.0)
    prob_adj = max_combo_prob + circ_adj

    # 展示確認トリガー（展示前システムとして必須）
    # 1号艇のST実績をチェックしてトリガー文言を組み立てる
    st1 = res1.get("avg_st") if res1 else None
    st_trigger = ""
    if st1 is not None:
        if st1 > 0.18:
            st_trigger = f"展示で1号艇スタート遅め({st1:.3f}秒)確認→ヒモが荒れやすい"
        elif st1 < 0.14:
            st_trigger = f"展示で1号艇スタート超安定({st1:.3f}秒)→ヒモ固まり方向に注意"

    reasons = [
        f"rel_win1={rel_win1:.1f}%（本命度）",
        f"最有力組み合わせ確率: {max_combo_prob:.3f}（推定実オッズ?{est_top_odds:.0f}倍）",
        f"2着集中度: 上位2艇 {top2_circ_sum:.1f}%（補正{circ_adj:+.2f}）",
        f"総合判定確率: {prob_adj:.3f}",
    ]

    if prob_adj >= 0.25:
        verdict = "不参加推奨"
        bet_adj = -99
        tenji_trigger = (
            f"展示確認: 1号艇の伸びが平凡以下なら見送り確定。"
            f"好伸びでも推定オッズ{est_top_odds:.0f}倍台のため回収期待値低。"
            + (f"\n{st_trigger}" if st_trigger else "")
        )
        reasons.append(f"→ ヒモ固まり（推定1番人気{est_top_odds:.0f}倍台）。回収率が構造的に低い")
    elif prob_adj >= 0.12:
        verdict = "点数絞り"
        bet_adj = 0
        tenji_trigger = (
            f"展示確認: 1号艇伸び良→そのまま採用。悪→飛び組に差し替え。"
            f"circle_pct上位2艇に絞り込むこと。"
            + (f"\n{st_trigger}" if st_trigger else "")
        )
        reasons.append("→ ヒモはやや固め。上位2艇以外を切ること")
    else:
        verdict = "参加推奨"
        bet_adj = +2
        tenji_trigger = (
            f"展示確認: ヒモ分散レース。1号艇伸び確認後、広めのヒモ流しを採用。"
            f"穴ヒモ（5・6号艇）を積極的に含める。"
            + (f"\n{st_trigger}" if st_trigger else "")
        )
        reasons.append("→ ヒモ分散。1号艇1着固定で広めのヒモ流し推奨（買い目+2点）")

    return {
        "is_target":            True,
        "verdict":              verdict,
        "max_combo_prob":       round(max_combo_prob, 4),
        "est_top_odds":         est_top_odds,
        "circle_concentration": round(top2_circ_sum, 1),
        "eligible_count":       eligible_count,
        "bet_adj":              bet_adj,
        "reason":               " / ".join(reasons),
        "tenji_trigger":        tenji_trigger,
    }


def _build_kimari(cm):
    parts = []
    mapping = [
        ("逃げ%", "逃"),
        ("差し%", "差"),
        ("まくり%", "ま"),
        ("まくり差し%", "差ま"),
        ("抜き%", "抜"),
    ]
    for col, label in mapping:
        v = safe_float(_get_cm_val(cm, col))
        if v and v > 0:
            parts.append(f"{label}{int(round(v))}%")
    return " ".join(parts) if parts else "-"

def _build_kimari_c1_vuln(cm):
    """1号艇用：被決まり手%（差され/まくられ/まくり差され）を文字列化"""
    parts = []
    mapping = [
        ("差され%",     "差され"),
        ("捲られ%",     "まくられ"),
        ("捲り差され%", "まくり差され"),
    ]
    for col, label in mapping:
        v = safe_float(_get_cm_val(cm, col))
        if v and v > 0:
            parts.append(f"{label}{int(round(v * 100))}%")
    return " ".join(parts) if parts else "-"


def _judge_race_type(results, venue_stats, venue_frame, race_no=None,
                     venue_stats_master=None, venue=None, tobi_scenario=None):
    """
    荒れ/堅いレース自動判定。乗法モデルで複合確率スコアを計算して S/A/B/C/D を返す。
    score 高（1.0に近い）→ 堅い、低（0.0に近い）→ 荒れ

    【旧方式の問題点と修正理由】
    旧方式: 各指標を単純に加算/減算 → score が 50±αで計算
      問題(1): 加算モデルは独立事象の積を無視する
        例）「1号艇3連対率92%」かつ「会場イン逃げ率60%」の複合は
             P(堅い) = 0.92 × 0.60 ≒ 0.55 だが、加算では過大評価される
      問題(2): score が 0〜100 に張り付きやすく、ランク境界が不安定
      問題(3): 各指標の重みが明示されず、調整根拠が不明

    【新方式: 乗法モデル】
      base_prob = 各確率因子の積（0〜1）
      修正因子（乗算）= 連続値で補正（0.5〜1.5程度）
      最終スコア = base_prob × 修正因子群 を 0〜100 にスケール

      確率因子（直接確率として解釈できるもの）:
        P1: 1号艇の相対1着率 / 理論値(40%)   正規化乗数
        P2: 1号艇の3連対率                  直接使用
        P3: 会場イン逃げ率                  直接使用
        P4: 1号艇がTop-1の確率（1位集中度）  Top1比率

      修正因子（確率ではなく補正係数）:
        M1: フォーム指数補正     0.85〜1.15
        M2: ST安定スコア補正     0.90〜1.10
        M3: FLY/出遅れペナルティ 0.75〜1.00
        M4: 飛びシナリオ補正     0.60〜1.00
        M5: R番号補正            0.90〜1.05
        M6: データ不足補正       0.70〜1.00
    """
    reasons = []
    honmei_concentrated = False
    two_top_race = False

    res1 = next((r for r in results if r["waku"] == "1"), None)

    # ─── 確率因子 ───────────────────────────────────────────────────────────

    # P1: 1号艇の相対1着率（理論値40%との比で正規化、上限1.5・下限0.3）
    p1 = 1.0
    if res1 and res1.get("rel_win1") is not None:
        r1 = res1["rel_win1"]
        p1 = max(0.30, min(1.50, r1 / 40.0))
        if r1 >= 45:
            reasons.append(f"1号艇相対1着率{r1:.1f}%（突出 ×{p1:.2f}）")
        elif r1 >= 35:
            reasons.append(f"1号艇相対1着率{r1:.1f}%（高い ×{p1:.2f}）")
        elif r1 <= 20:
            reasons.append(f"1号艇相対1着率{r1:.1f}%（低い→荒れ要素 ×{p1:.2f}）")
        elif r1 <= 28:
            reasons.append(f"1号艇相対1着率{r1:.1f}%（やや低い ×{p1:.2f}）")

    # P2: 1号艇の3連対率（直接確率として使用、基準値0.75）
    # ※ 95%超は少数データ疑いのため0.90に上限クリップ
    p2 = 0.75  # データなし時のデフォルト
    if res1 and res1.get("win3_rate") is not None:
        w3 = float(res1["win3_rate"])
        if w3 >= 0.95:
            p2 = 0.90   # 高すぎ → 少数データ疑い → 上限クリップ
            reasons.append(f"1号艇3連対率{w3*100:.0f}%（高すぎ→少数データ疑い→0.90にクリップ）")
        elif 0.92 <= w3 < 0.95:
            p2 = w3
            reasons.append(f"1号艇3連対率{w3*100:.0f}%（最安定帯 92-95%）")
        elif w3 >= 0.90:
            p2 = w3
            reasons.append(f"1号艇3連対率{w3*100:.0f}%（安定型）")
        elif w3 <= 0.55:
            p2 = w3
            reasons.append(f"1号艇3連対率{w3*100:.0f}%（不安定）")
        else:
            p2 = w3

    # P3: 会場イン逃げ率（直接確率として使用、デフォルト0.55）
    p3 = 0.55
    in_rate = venue_stats.get("in_rate")
    if in_rate is not None:
        p3 = float(in_rate)
        if in_rate >= 0.60:
            reasons.append(f"会場イン逃げ率{in_rate*100:.1f}%（逃げ率高）")
        elif in_rate <= 0.42:
            reasons.append(f"会場イン逃げ率{in_rate*100:.1f}%（荒れやすい会場）")

    # P4: 1号艇のトップ集中度（sorted_rel[0] / sorted_rel[1] の比率）
    p4 = 1.0
    sorted_rel = sorted(
        [r["rel_win1"] for r in results if r.get("rel_win1") is not None],
        reverse=True
    )
    if len(sorted_rel) >= 2:
        gap = sorted_rel[0] - sorted_rel[1]
        h2_threat = sorted_rel[1]
        if h2_threat >= 22 and gap < 15:
            # 実質2強 → 集中度低下
            p4 = 0.80
            two_top_race = True
            reasons.append(f"2番手脅威{h2_threat:.1f}%・差{gap:.1f}pt（実質2強→2軸推奨 ×{p4:.2f}）")
        elif gap >= 20:
            # 本命突出
            p4 = 1.20
            honmei_concentrated = True
            reasons.append(f"1・2位差{gap:.1f}pt（本命突出 ×{p4:.2f}）")
        elif gap <= 8:
            # 実力拮抗
            p4 = 0.85
            reasons.append(f"1・2位差{gap:.1f}pt（実力拮抗 ×{p4:.2f}）")

    # base_prob: P1〜P4の積（0〜1.5程度、後でスケール化）
    base_prob = p1 * p2 * p3 * p4

    # ─── 修正因子 ───────────────────────────────────────────────────────────

    # M1: フォーム指数補正
    m1 = 1.0
    if res1:
        pm1 = res1.get("raw_pm", {})
        form_idx = safe_float(pm1.get("フォーム\n指数") or pm1.get("フォーム指数"))
        if form_idx is not None:
            if form_idx >= 8.0:
                m1 = 1.12; reasons.append(f"1号艇フォーム指数{form_idx:.1f}（[高]ホット ×{m1:.2f}）")
            elif form_idx < 4.0:
                m1 = 0.88; reasons.append(f"1号艇フォーム指数{form_idx:.1f}（[低]コールド ×{m1:.2f}）")
            elif form_idx < 6.0:
                m1 = 0.94; reasons.append(f"1号艇フォーム指数{form_idx:.1f}（やや不調 ×{m1:.2f}）")

    # M2: ST安定スコア補正
    m2 = 1.0
    if res1:
        pm1 = res1.get("raw_pm", {})
        st_stable = safe_float(pm1.get("ST安定\nスコア") or pm1.get("ST安定スコア"))
        if st_stable is not None:
            if st_stable >= 80:
                m2 = 1.08; reasons.append(f"1号艇ST安定スコア{st_stable:.0f}（◎超安定 ×{m2:.2f}）")
            elif st_stable >= 60:
                m2 = 1.04; reasons.append(f"1号艇ST安定スコア{st_stable:.0f}（○安定 ×{m2:.2f}）")
            elif st_stable < 40:
                m2 = 0.92; reasons.append(f"1号艇ST安定スコア{st_stable:.0f}（×不安定→ST信頼性低 ×{m2:.2f}）")

    # M3: FLY数・出遅れ数によるペナルティ
    m3 = 1.0
    if res1:
        pm1 = res1.get("raw_pm", {})
        fly_count_j  = safe_float(pm1.get("FLY数"),    0) or 0
        late_count_j = safe_float(pm1.get("出遅れ数"), 0) or 0
        st_meas_j    = safe_float(pm1.get("ST計測件数") or pm1.get("総出走数"), 1) or 1
        late_rate_j  = late_count_j / max(st_meas_j, 1)

        if fly_count_j >= 2:
            m3 *= 0.82; reasons.append(f"1号艇FLY{int(fly_count_j)}回（直近複数FLY ×0.82）")
        elif fly_count_j >= 1:
            m3 *= 0.91; reasons.append(f"1号艇FLY{int(fly_count_j)}回（直近FLYあり ×0.91）")

        if late_rate_j >= 0.10:
            m3 *= 0.88; reasons.append(f"1号艇出遅れ率{late_rate_j*100:.0f}%（出遅れ癖あり ×0.88）")
        elif late_rate_j >= 0.05:
            m3 *= 0.94; reasons.append(f"1号艇出遅れ率{late_rate_j*100:.0f}%（出遅れやや多い ×0.94）")

    # M4: イン飛びシナリオ補正（飛び確率が高いほど逃げ確率を下げる）
    m4 = 1.0
    if tobi_scenario is not None:
        tobi_prob = tobi_scenario.get("tobi_prob", 0)
        if tobi_prob >= 70:
            m4 = 0.62; reasons.append(f"飛び確率{tobi_prob:.0f}%（S：強い飛び示唆 ×{m4:.2f}）")
        elif tobi_prob >= 55:
            m4 = 0.75; reasons.append(f"飛び確率{tobi_prob:.0f}%（A：飛び傾向あり ×{m4:.2f}）")
        elif tobi_prob >= 40:
            m4 = 0.88; reasons.append(f"飛び確率{tobi_prob:.0f}%（B：やや飛びの余地 ×{m4:.2f}）")

    # M5: R番号補正（後半Rほど荒れやすい）
    m5 = 1.0
    NATIONAL_R_AREYASUSA = {
        1: 55, 2: 52, 3: 50, 4: 48, 5: 46, 6: 44,
        7: 43, 8: 42, 9: 41, 10: 40, 11: 39, 12: 38,
    }
    try:
        rno = int(race_no) if hasattr(race_no, '__int__') else int(str(race_no))
        r_are_score = None
        if venue_stats_master and venue:
            vs_m = venue_stats_master.get(venue, {})
            r_are_score = safe_float(vs_m.get(f"{rno}R荒れスコア"))
        if r_are_score is None:
            r_are_score = NATIONAL_R_AREYASUSA.get(rno, 45)
        # 荒れスコア50を基準に乗算係数へ変換（50→1.0、55→1.03、38→0.94）
        m5 = max(0.90, min(1.06, 1.0 + (float(r_are_score) - 50) * 0.006))
        if abs(m5 - 1.0) >= 0.02:
            direction = "堅め" if m5 > 1.0 else "荒れやすい"
            reasons.append(f"{rno}R荒れスコア{r_are_score:.0f}（{direction} ×{m5:.3f}）")
    except (ValueError, TypeError) as e:
        print(f"  [!]  R番号補正の計算をスキップしました: {e}")

    # M6: データ不足補正
    missing_list = [r for r in results if r.get("data_missing")]
    missing = len(missing_list)
    m6 = max(0.70, 1.0 - missing * 0.08)  # 1人欠け→×0.92、3人→×0.76
    data_trust_score = round((6 - missing) / 6 * 100)
    if missing >= 3:
        reasons.append(f"データ不足{missing}人（信頼性低 ×{m6:.2f}）")
    elif missing >= 1:
        reasons.append(f"データ不足{missing}人（×{m6:.2f}）")
        missing_names = "・".join(
            f"{r['waku']}号艇{r['name']}({r.get('missing_reason','')})"
            for r in missing_list
        )
        reasons.append(f"データ信頼度{data_trust_score}%（不足:{missing_names}）")

    # ─── 最終スコア計算 ────────────────────────────────────────────────────
    # base_prob（0〜約1.5）× 修正因子群 を 0〜100 にスケール
    # 基準値（全てデフォルトの場合）: 1.0 × 0.75 × 0.55 × 1.0 ≒ 0.41 → score ≒ 50
    raw_score  = base_prob * m1 * m2 * m3 * m4 * m5 * m6
    # 正規化: raw_score=0.41 → 50点 となるよう線形スケール（slope = 50/0.41 ≒ 122）
    NORMALIZATION_CENTER = 0.41   # 全デフォルト値での期待出力
    score = int(round(min(100, max(0, raw_score / NORMALIZATION_CENTER * 50))))

    reasons.insert(0, f"複合確率スコア: {raw_score:.4f} → {score}点")

    if score >= 80:
        rank, strategy, skip = "S", "◎1着固定 2-3着流し（5〜8点）", False
    elif score >= 60:
        rank, strategy, skip = "A", "◎-○軸 3着3〜4艇流し（10〜15点）", False
    elif score >= 45:
        rank, strategy, skip = "B", "◎○△フォーメーション（15〜20点）", False
    elif score >= 35:
        # 【改善】旧閾値30→35に厳格化。過去バックテストでC帯の回収率が損益分岐を下回った。
        rank, strategy, skip = "C", "荒れ傾向。高配当狙いか見送り", False
    else:
        # score < 35 → 大荒れ確実。見送り推奨。
        rank, strategy, skip = "D", "大荒れ。見送り推奨", True

    return {
        "rank":                rank,
        "score":               score,
        "reason":              reasons,
        "skip":                skip,
        "strategy":            strategy,
        "honmei_concentrated": honmei_concentrated,
        "two_top_race":        two_top_race,
        "data_trust_score":    data_trust_score,
    }


