"""
recommend_bet.py  v7（メンバー間相互作用版）
=============================================
P(A→B→C) = P(1着=A) × P(2着=B|1着=A) × P(3着=C|1着=A,2着=B)

【v7追加: 今日のメンバー間相互作用を全因子に組み込む】

P(1着=A):
  accuracy_data実績着率 × cross補正（1号艇のrate_1st_c1 × 逃げ評価）
  × 攻め力補正（sashi_rate / makuri_rate で今日の攻め能力を反映）
  × motor補正 × ST安定補正 × 個人近況補正

P(2着=B | 1着=A):  ← v7で相互作用を追加
  展開別残存マスタ[kimete][A_course][B_course].r2
  × 攻め力係数（B.sashi_rate or B.makuri_rate → 今日のBの攻め能力）
  × ST優位係数（B.avg_st_self vs A.avg_st_self → 今日のBとAのST差）
  × 個人近況係数

P(3着=C | 1着=A, 2着=B):  ← v7で封鎖係数を個人データ化
  展開別残存マスタ[kimete][A_course][C_course].r3
  × 封鎖係数（B.makuri_rate に依存 → 固定0.88から変更）
  × rate_3ren 地力係数 × jizaisei係数 × 個人近況係数
"""
from __future__ import annotations
import math
from accuracy_data import get_win_rate, get_baseline_rate
from master_data import (
    get_tenkai_zanson, get_innige_bunseki,
    get_kaijo_stats, get_race_are_score,
    get_senshu_index, get_venue_course_rate,
)
# evaluate_jizen の内部関数を流用（ST優位スコア）
try:
    from evaluate_jizen import _st_advantage_score as _st_adv_score
except ImportError:
    def _st_adv_score(avg_st_self, avg_st_1, course_self=3):
        if avg_st_self is None or avg_st_1 is None: return 0.5
        norm = {2:0.025,3:0.035,4:0.045,5:0.055,6:0.055}.get(course_self,0.035)
        return max(0.0, min(1.0, (avg_st_1 - avg_st_self) / norm * 0.5 + 0.5))

# ─── 技別確率の計算 ───────────────────────────────────────────
# 「決まり手を1つに固定」するのをやめる。
# 各艇の技の使用率から決まり手確率分布を求め、展開別に加重平均する。

_KIMETE_DEFAULT = {
    # データなし時のコース別デフォルト（展開別残存マスタ実績比率）
    1: {"逃げ": 1.00},
    2: {"差し": 0.67, "まくり": 0.33, "まくり差し": 0.00},
    3: {"差し": 0.13, "まくり": 0.45, "まくり差し": 0.43},
    4: {"差し": 0.19, "まくり": 0.52, "まくり差し": 0.29},
    5: {"差し": 0.07, "まくり": 0.25, "まくり差し": 0.68},
    6: {"差し": 0.15, "まくり": 0.35, "まくり差し": 0.50},
}

def _kimete_weights(m: dict) -> dict[str, float]:
    """
    その艇が1着になったとき「どの決まり手で勝つか」の確率分布を返す。
    差し率・まくり率・まくり差し率の相対比率で計算。
    """
    c  = int(m.get("course_int", 2))
    sa = _sf(m.get("sashi_rate"))
    mk = _sf(m.get("makuri_rate"))
    mz = _sf(m.get("makuri_zashi_rate"))
    total = sa + mk + mz
    if total <= 0:
        return _KIMETE_DEFAULT.get(c, {"差し":0.20,"まくり":0.50,"まくり差し":0.30})
    return {"差し": sa/total, "まくり": mk/total, "まくり差し": mz/total}

# ─── ユーティリティ ──────────────────────────────────────────
def _b(s: str) -> str: return s.replace("⚠️","").replace("⚠","").strip()
def _warned(s: str) -> bool: return "⚠" in s
def _sf(v, d=0.0):
    try: return float(str(v).replace("%","").strip()) if v not in (None,"","None","nan","-") else d
    except: return d

def _r(axis, sym, course, place, venue="__ALL__") -> float:
    v = get_win_rate(axis, _b(sym), course, place, venue)
    return v if v is not None else (get_win_rate(axis, _b(sym), course, place, "__ALL__") or 0.0)

def _base(course, place, venue="__ALL__") -> float:
    b = get_baseline_rate(course, place, venue)
    return b if b > 0 else (get_baseline_rate(course, place, "__ALL__") or 1/6)

_BIN_EDGES  = [0.19,0.29,0.39,0.49,0.59]
_BIN_LABELS = ["〜19%","20〜29%","30〜39%","40〜49%","50〜59%","60%〜"]
def _bin(r: float) -> str:
    for e,l in zip(_BIN_EDGES,_BIN_LABELS):
        if r <= e: return l
    return _BIN_LABELS[-1]

def _cross_rate(axis, sym, course, r1c1, place):
    from accuracy_data import get_stats
    d  = get_stats()
    bm = (d.get("cross",{}).get(axis,{}).get(_b(sym),{}) if axis=="in_nige"
          else d.get("cross",{}).get(axis,{}).get(str(course),{}).get(_b(sym),{}))
    if not bm: return None
    places = bm.get(_bin(r1c1)) or next(iter(bm.values()),{})
    if not isinstance(places,dict): return None
    total = sum(places.values())
    if not total: return None
    hits = sum(places.get(str(p),0) for p in [1,2,3]) if place==123 else places.get(str(place),0)
    return hits/total

# ─── 個人近況・会場特化係数（0.70〜1.30）────────────────────
def _personal_mult(m: dict, venue: str, course: int) -> float:
    name = m.get("senshu_name","")
    mult = 1.0
    if name:
        si = get_senshu_index(name)
        if si:
            fi = si.get("form_index")
            if fi is not None:
                mult *= 0.85 + min(max(float(fi)+2,0),7)/7*0.30
            w3 = si.get("win3_r5")
            if w3 is not None:
                mult *= 0.92 + float(w3)*0.16
            fi_imp = si.get("fly_impact")
            if fi_imp is not None and float(fi_imp) > 0:
                mult *= max(0.85, 1.0 - float(fi_imp)*0.5)
        vc = get_venue_course_rate(name, venue, course)
        if vc and vc.get("time_win1") is not None:
            b1 = _base(course,1,venue)
            tw1 = float(vc["time_win1"])
            trust = min(1.0, float(vc.get("trust") or 0))
            if b1>0 and trust>0:
                mult *= (1.0*(1-trust) + max(0.75,min(1.25,tw1/b1))*trust)
    th = m.get("tenji_hensa")
    if th is not None:
        mult *= max(0.80, min(1.20, 1.0+(float(th)-50)/50))
    return max(0.70, min(1.30, mult))

# ─── motor係数（全艇中相対位置、0.85〜1.15）─────────────────
def _motor_mult(m: dict, members: list[dict]) -> float:
    motors = [float(x["motor_2rate"]) for x in members if x.get("motor_2rate") is not None]
    v = m.get("motor_2rate")
    if not motors or v is None: return 1.0
    return 0.85 + sum(1 for x in motors if x<=float(v))/len(motors)*0.30

# ─── ⚠係数 ──────────────────────────────────────────────────
def _warn_mult(ev_result: dict, idx: int) -> float:
    for key in ["in_nige","aisho","jizaisei"]:
        syms = ev_result.get(key,[])
        if idx<len(syms) and _warned(syms[idx]): return 0.75
    return 1.0

# ─── 攻め力係数（今日のBの攻め技術、0.70〜1.40）─────────────
def _attack_mult(m: dict, b_course: int) -> float:
    """
    今日のBの攻め技術を係数化。コースで技を固定しない。
    差し + まくり + まくり差し の合算（全部その選手が実際に使う技）
    weapon=0.0 → 0.70倍、weapon=0.5 → 1.05倍、weapon=1.0 → 1.40倍
    """
    sashi = _sf(m.get("sashi_rate"))
    maku  = _sf(m.get("makuri_rate"))
    mz    = _sf(m.get("makuri_zashi_rate"))
    weapon = sashi + maku + mz
    if weapon <= 0.0:
        weapon = _sf(m.get("attack_rate"), 0.10)
    return 0.70 + min(weapon, 1.0) * 0.70

# ─── ST優位係数（BとAのST差、0.80〜1.20）────────────────────
def _st_mult(m_b: dict, m_a: dict, b_course: int) -> float:
    """
    今日のBがAに対してSTで優位かどうかを係数化。
    evaluate_jizen._st_advantage_score() を流用して0〜1に正規化。
    0.0（不利）→0.80倍、0.5（中立）→1.00倍、1.0（有利）→1.20倍
    """
    st_b = m_b.get("avg_st_self")
    st_a = m_a.get("avg_st_self")
    adv = _st_adv_score(st_b, st_a, course_self=b_course)  # 0〜1
    return 0.80 + adv * 0.40

# ─── 封鎖係数（Bの攻め力でCの3着率を減衰、0.80〜1.00）───────
def _block_mult(m_b: dict, b_course: int, c_course: int, kimete: str) -> float:
    """
    BがCより内側かつ攻め系展開のとき、CはBに封鎖されやすい。
    封鎖強度はBのまくり率に依存（固定0.88から変更）。
    """
    if b_course >= c_course or kimete not in ("差し","まくり","まくり差し"):
        return 1.0
    mk = _sf(m_b.get("makuri_rate")) + _sf(m_b.get("makuri_zashi_rate"))
    if b_course == 2:
        mk = _sf(m_b.get("sashi_rate"))
    # mk=0→封鎖なし(1.0), mk=0.5→0.90, mk=1.0→0.80
    return max(0.80, 1.0 - mk * 0.20)

# ─── 汎用脅威スコア（AがBに突破される確率）──────────────────
def _threat_score_generic(m_b: dict, m_a: dict, b_course: int) -> float:
    """
    BがAを突破する脅威スコア（0〜1）。
    evaluate_jizen._threat_score_vs_1 の汎用版（1号艇限定でない）。
    B.weapon × 0.5 + B.ST優位(vs A) × 0.5
    """
    sa  = _sf(m_b.get("sashi_rate"))
    mk  = _sf(m_b.get("makuri_rate"))
    mz  = _sf(m_b.get("makuri_zashi_rate"))
    atk = _sf(m_b.get("attack_rate"))
    weapon = sa + mk + mz
    if weapon <= 0: weapon = atk if atk > 0 else 0.10
    weapon = min(weapon, 1.0)
    st_adv = _st_mult(m_b, m_a, b_course)  # 0.80〜1.20 → 0〜1にスケール
    st_score = (st_adv - 0.80) / 0.40
    return weapon * 0.50 + st_score * 0.50


# ─── 崩れシナリオ生成 ────────────────────────────────────────
def _generate_fail_scenarios(
        a_idx: int, members: list[dict], ev_result: dict,
        p1: list[float], venue: str) -> list[dict]:
    """
    A艇が仕掛けたが崩れた場合のシナリオリストを生成する。

    あなたの思考フロー⑥:
      「主役が攻めたが崩れた時に誰が浮上するか」

    計算式:
      P(仕掛けA崩れ→B1着,C2着,A3着) =
        P(A仕掛け確率)          # p1[a] × Aの攻め力
        × P(Bが突破)            # B の対A脅威スコア
        × P(Aが3着残存)         # 残存マスタ[A決まり手][A_course][A_course].r123-r2
        × P(C が2着|B1着,A3着)  # 残存マスタ[B決まり手][B_course][C_course].r2 正規化

    Returns: [{bet, prob, p1, p2, p3, a_kimete, a_course}, ...]
    """
    m_a     = members[a_idx]
    a_course = int(m_a.get("course_int", a_idx+1))
    n       = len(members)
    others  = [i for i in range(n) if i != a_idx]

    # Aの仕掛け確率 = P(A1着) × Aの攻め力（1号艇は逃げ力）
    sa  = _sf(m_a.get("sashi_rate"))
    mk  = _sf(m_a.get("makuri_rate"))
    mz  = _sf(m_a.get("makuri_zashi_rate"))
    atk = sa + mk + mz
    if a_course == 1:
        # 1号艇は「逃げる」仕掛けなので崩れシナリオは逃げ失敗
        nige_rate = _sf(m_a.get("nigé_rate"), 0.7)
        p_shikake = p1[a_idx] * nige_rate
    else:
        p_shikake = p1[a_idx] * min(atk, 1.0)

    if p_shikake < 0.005:
        return []  # 仕掛け確率が低すぎる → スキップ

    # Aの主力決まり手
    kw_a      = _kimete_weights(m_a) if a_course != 1 else {"逃げ": 1.0}
    main_kimete_a = max(kw_a, key=kw_a.get)

    # Aが崩れた後の3着残存率
    # = 残存マスタ[A決まり手][A_course][?].r123 の平均（A自身の欄がないため近似）
    a_fail_r3 = 0.0
    for kimete_a, w_a in kw_a.items():
        if w_a < 0.01: continue
        # 崩れた = 他のコースが1着になったとき、Aが3着に残る確率
        # 他の艇が1着のときのA残存率を全コース平均で近似
        for b_idx in others:
            b_course_b = int(members[b_idx].get("course_int", b_idx+1))
            tz_b = get_tenkai_zanson(kimete_a, b_course_b, a_course, venue)
            if tz_b:
                a_fail_r3 += (tz_b["r123"] - tz_b["r2"]) * w_a / len(others)
    a_fail_r3 = max(0.05, min(0.40, a_fail_r3))  # 5〜40%にクランプ

    scenarios = []

    for b_idx in others:
        m_b      = members[b_idx]
        b_course = int(m_b.get("course_int", b_idx+1))

        # BがAを突破する確率
        p_b_wins = _threat_score_generic(m_b, m_a, b_course)
        if p_b_wins < 0.05:
            continue

        # Bが主役になったときの決まり手分布
        kw_b          = _kimete_weights(m_b) if b_course != 1 else {"逃げ": 1.0}
        main_kimete_b = max(kw_b, key=kw_b.get)

        # C（残りの艇）の2着確率 | B1着,A3着
        thirds = [i for i in others if i != b_idx]
        c_r2 = {}
        for c_idx in thirds:
            m_c      = members[c_idx]
            c_course = int(m_c.get("course_int", c_idx+1))
            if c_course == a_course:
                continue  # Aはすでに3着想定

            r2_sum = 0.0
            for kimete_b, w_b in kw_b.items():
                if w_b < 0.01: continue
                tz = get_tenkai_zanson(kimete_b, b_course, c_course, venue)
                r2_sum += (tz["r2"] if tz else _base(c_course, 2, venue)) * w_b
            c_r2[c_idx] = r2_sum

        # 正規化（Aが3着を取った分を除く）
        total_r2 = sum(c_r2.values())
        if total_r2 <= 0:
            continue

        for c_idx, r2_c in sorted(c_r2.items(), key=lambda x: -x[1])[:4]:
            m_c      = members[c_idx]
            c_course = int(m_c.get("course_int", c_idx+1))

            # 確率 = 仕掛け × B突破 × A3着残 × C2着
            prob = (p_shikake
                    * p_b_wins
                    * a_fail_r3
                    * (r2_c / total_r2))

            if prob < 0.002:
                continue

            ab = a_course   # A は3着
            bb = b_course   # B は1着
            cb = c_course   # C は2着
            bet = f"{bb}→{cb}→{ab}"

            scenarios.append({
                "bet":      bet,
                "prob":     prob,
                "p1":       p_shikake * p_b_wins,  # 実質的なB1着確率
                "p2":       r2_c / total_r2,
                "p3":       a_fail_r3,
                "a_kimete": f"[崩れ]{main_kimete_b}",
                "a_course": b_course,
                "_fail_scenario": True,
            })

    return scenarios


# ─── P(1着=A) ────────────────────────────────────────────────
def _prob1(idx: int, members: list[dict], ev_result: dict, venue: str) -> float:
    m     = members[idx]
    c     = int(m.get("course_int", idx+1))
    r1c1  = _sf(m.get("rate_1st_c1"), 0.0)
    nige  = ev_result.get("in_nige", [""]*6)
    aisho = ev_result.get("aisho",   [""]*6)
    jiz   = ev_result.get("jizaisei",[""]*6)
    ns    = nige[idx]  if idx<len(nige)  else ""
    as_   = aisho[idx] if idx<len(aisho) else ""
    js    = jiz[idx]   if idx<len(jiz)   else ""

    # 基底: cross補正付き実績1着率
    if c == 1:
        cr = _cross_rate("in_nige", ns, 1, r1c1, 1)
        base = cr if cr is not None else _r("in_nige", ns, 1, 1, venue)
    else:
        cr = _cross_rate("aisho", as_, c, r1c1, 1)
        base = cr if cr is not None else _r("aisho", as_, c, 1, venue)
    if base <= 0: base = _base(c,1,venue) * 0.5

    # 今日の攻め力補正（P(1着)にも反映: 攻め手が強いほど1着も来やすい）
    atk = _attack_mult(m, c) if c >= 2 else 1.0

    # ST安定乗数
    st_m = {"◎":1.10,"○":1.04,"△":0.95,"":0.85}.get(_b(js), 1.0)

    return base * atk * _motor_mult(m,members) * st_m * _warn_mult(ev_result,idx) * _personal_mult(m,venue,c)

# ─── P(2着=B | 1着=A) ────────────────────────────────────────
def _prob2(b_idx: int, a_idx: int, a_course: int,
           members: list[dict], ev_result: dict, venue: str) -> float:
    """
    P(2着=B | 1着=A)
    Aの決まり手を「差し/まくり/まくり差し」の技別に分けて加重平均。
    2号艇がまくるか差すかで2着分布がガラッと変わるためこれが必要。
    """
    m_b   = members[b_idx]
    m_a   = members[a_idx]
    c     = int(m_b.get("course_int", b_idx+1))
    aisho = ev_result.get("aisho",   [""]*6)
    tenk  = ev_result.get("tenkai",  [""]*6)
    as_   = aisho[b_idx] if b_idx<len(aisho) else ""
    ts    = tenk[b_idx]  if b_idx<len(tenk)  else ""

    # Aが1号艇なら逃げ固定（イン逃げ分析を優先使用）
    if a_course == 1:
        ib = get_innige_bunseki(venue, c)
        if ib:
            base = ib["r2"]
        else:
            tz = get_tenkai_zanson("逃げ", 1, c, venue)
            base = tz["r2"] if tz else _base(c, 2, venue)
    else:
        # Aの技別確率で加重平均
        weights = _kimete_weights(m_a)
        base = 0.0
        for kimete, w in weights.items():
            if w <= 0: continue
            tz = get_tenkai_zanson(kimete, a_course, c, venue)
            if tz:
                base += tz["r2"] * w
            else:
                base += _base(c, 2, venue) * w

    # Bの攻め技術 × ST優位 × evaluate_jizen評価
    atk_m = _attack_mult(m_b, c)
    st_m  = _st_mult(m_b, m_a, c)
    SYM   = {"◎":1.15,"○":1.06,"△":0.97,"":0.88}
    sym_m = max(SYM.get(_b(as_),1.0), SYM.get(_b(ts),1.0)) if c>=4 else SYM.get(_b(as_),1.0)

    return base * atk_m * st_m * sym_m * _warn_mult(ev_result,b_idx) * _personal_mult(m_b,venue,c)

# ─── P(3着=C | 1着=A, 2着=B) ────────────────────────────────
def _prob3(c_idx: int, a_course: int,
           b_idx: int, b_course: int,
           members: list[dict], ev_result: dict, venue: str) -> float:
    """
    P(3着=C | 1着=A, 2着=B)

    【改善】2着=Bが確定した後のCの3着確率を正確に計算する。
    展開別残存マスタの r123（3着以内率）と r2（2着率）を使い:

      r3_adj[C] = r123[C] - r2[C]  ← 2着に来る余地を除いた純粋な3着確率
      → B確定後の残り艇で正規化

    これにより「2号艇が差しで2着 vs まくりで2着」で
    3着分布が変わる展開を正しく反映できる。
    """
    m_c = members[c_idx]
    m_b = members[b_idx]
    # a_idxをa_courseから特定
    a_idx = next((i for i, m in enumerate(members)
                  if int(m.get("course_int", i+1)) == a_course), 0)
    m_a = members[a_idx] if a_idx < len(members) else {}
    c   = int(m_c.get("course_int", c_idx+1))
    jiz = ev_result.get("jizaisei", [""]*6)
    js  = jiz[c_idx] if c_idx < len(jiz) else ""

    # A艇の決まり手重みを取得
    kw = _kimete_weights(m_a) if a_course != 1 else {"逃げ": 1.0}

    if a_course == 1:
        # ── 逃げ固定：イン逃げ分析優先 ──────────────────────────
        ib = get_innige_bunseki(venue, c)
        if ib:
            # r3w（3着以内率）からCが2着に来た分を除く
            r3_adj = max(0.0, ib["r3w"] - ib["r2"])
        else:
            tz = get_tenkai_zanson("逃げ", 1, c, venue)
            if tz:
                r3_adj = max(0.0, tz["r123"] - tz["r2"])
            else:
                r3_adj = _base(c, 3, venue)

        # B確定後の正規化: 残り艇のr3_adjの合計で割る
        others_r3 = {}
        for other_idx, other_m in enumerate(members):
            other_c = int(other_m.get("course_int", other_idx+1))
            if other_c in (1, b_course): continue  # 1着・2着確定艇を除く
            ib_o = get_innige_bunseki(venue, other_c)
            if ib_o:
                others_r3[other_c] = max(0.0, ib_o["r3w"] - ib_o["r2"])
            else:
                tz_o = get_tenkai_zanson("逃げ", 1, other_c, venue)
                others_r3[other_c] = max(0.0, tz_o["r123"] - tz_o["r2"]) if tz_o else _base(other_c, 3, venue)
        total_r3 = sum(others_r3.values())
        if total_r3 > 0 and c in others_r3:
            base = others_r3[c] / total_r3
        else:
            base = r3_adj

    else:
        # ── 技別加重平均 ─────────────────────────────────────────
        # 各決まり手について r3_adj を計算して加重平均
        base_weighted = 0.0
        for kimete, w in kw.items():
            if w < 0.01: continue
            tz = get_tenkai_zanson(kimete, a_course, c, venue)
            if tz:
                r3_adj_k = max(0.0, tz["r123"] - tz["r2"])
            else:
                r3_adj_k = _base(c, 3, venue)
            base_weighted += r3_adj_k * w

        # B確定後の正規化
        others_total = 0.0
        for other_idx, other_m in enumerate(members):
            other_c = int(other_m.get("course_int", other_idx+1))
            if other_c in (a_course, b_course): continue
            w_total = 0.0
            for kimete, w in kw.items():
                if w < 0.01: continue
                tz_o = get_tenkai_zanson(kimete, a_course, other_c, venue)
                if tz_o:
                    w_total += max(0.0, tz_o["r123"] - tz_o["r2"]) * w
                else:
                    w_total += _base(other_c, 3, venue) * w
            others_total += w_total

        base = base_weighted / others_total * (1 - 1/max(len(members)-2, 1)) if others_total > 0 else base_weighted

    # Bの進路封鎖（Bのまくり率依存）
    main_kimete = max(kw, key=kw.get)
    block_m = _block_mult(m_b, b_course, c, main_kimete)

    # rate_3ren（地力）
    r3 = _sf(m_c.get("rate_3ren"))
    if r3 > 0:
        b3 = sum(_base(c, p, venue) for p in [1, 2, 3])
        r3_m = max(0.85, min(1.15, r3 / b3)) if b3 > 0 else 1.0
    else:
        r3_m = 1.0

    jiz_m = {"◎":1.10,"○":1.04,"△":0.96,"":0.88}.get(_b(js), 1.0)

    return base * block_m * r3_m * jiz_m * _warn_mult(ev_result, c_idx) * _personal_mult(m_c, venue, c)

# ─── パターン判定 ─────────────────────────────────────────────
def classify_pattern(ev_result: dict, venue: str="__ALL__", race_no: int=0,
                     weather_speed=None, wave_height=None) -> str:
    nige0  = _b(ev_result.get("in_nige",[""])[0])
    aisho  = ev_result.get("aisho",[])
    aisho1 = _b(aisho[1]) if len(aisho)>1 else ""
    tenk   = ev_result.get("tenkai",[])
    tenk_strong = any(_b(tenk[i])=="◎" for i in range(3,min(6,len(tenk))))

    are = get_race_are_score(venue, race_no) if race_no else 50.0
    if weather_speed is not None and float(weather_speed)>=6:
        are += (float(weather_speed)-5)*2.0
    if wave_height is not None and float(wave_height)>=5:
        are += (float(wave_height)-4)*1.5

    effective = "○" if (nige0=="◎" and are>=65) else nige0
    sashi_threat = aisho1 in {"◎","○"}
    if effective in {"◎","○"} and not sashi_threat: return "nige"
    if sashi_threat:                                  return "sashi"
    if effective=="" and tenk_strong:                 return "tenkai"
    return "mixed"

# ─── 1着候補 ──────────────────────────────────────────────────
def _first_candidates(pattern: str, members: list[dict], ev_result: dict,
                      p1_raw: list[float]) -> list[int]:
    """
    1着候補をP1スコアに基づいて動的に選出する。
    パターン固定で1・2号艇に縛るのをやめ、
    実際に高確率の艇を候補に含める。
    """
    tenk  = ev_result.get("tenkai", [])
    aisho = ev_result.get("aisho",  [])
    n     = len(members)
    top3  = sorted(range(n), key=lambda i: -p1_raw[i])[:3]

    if pattern == "nige":
        # 逃げ本命: 1号艇固定。ただし2位との差が小さければ2位も追加
        if len(top3) >= 2 and p1_raw[top3[1]] > p1_raw[top3[0]] * 0.50:
            return [top3[0], top3[1]]
        return [top3[0]]

    elif pattern == "sashi":
        # 差しパターン: P1上位2艇（1・2号艇固定ではない）
        # 3号艇などが高確率の場合も候補に含める
        cands = top3[:2]
        # aisho◎の艇も追加（まだ含まれていなければ）
        for i, sym in enumerate(aisho):
            if _b(sym) == "◎" and i not in cands:
                cands.append(i)
                break
        return cands[:3]

    elif pattern == "tenkai":
        # 展開パターン: tenkai◎の外コース艇 + P1上位
        cands = [i for i in range(3, 6) if i < len(tenk) and _b(tenk[i]) == "◎"]
        if not cands:
            cands = top3[:2]
        elif top3[0] not in cands:
            cands = [top3[0]] + cands
        return cands[:3]

    else:
        # 混戦: P1上位3艇
        return top3[:3]

# ─── 全120通り計算・累積70%カット ─────────────────────────────
def generate_sanrentan(members: list[dict], ev_result: dict,
                       venue: str="__ALL__", race_no: int=0,
                       weather_speed=None, wave_height=None) -> dict:
    n = len(members)
    p1_raw = [_prob1(i, members, ev_result, venue) for i in range(n)]
    p1_sum = sum(p1_raw) or 1.0
    p1     = [p/p1_sum for p in p1_raw]

    pattern   = classify_pattern(ev_result, venue, race_no, weather_speed, wave_height)
    first_idx = _first_candidates(pattern, members, ev_result, p1_raw)

    combos = []
    for a_idx in first_idx:
        a_course = int(members[a_idx].get("course_int", a_idx+1))
        p_a      = p1[a_idx]
        others   = [i for i in range(n) if i!=a_idx]

        # A艇の主要決まり手（考察テキスト用）
        a_kw = _kimete_weights(members[a_idx])
        a_main_kimete = max(a_kw, key=a_kw.get) if a_course != 1 else "逃げ"

        p2_raw = {i: _prob2(i, a_idx, a_course, members, ev_result, venue)
                  for i in others}

        for b_idx in sorted(others, key=lambda i:-p2_raw[i]):
            b_course = int(members[b_idx].get("course_int", b_idx+1))
            p_b      = p2_raw[b_idx]
            thirds   = [i for i in others if i!=b_idx]

            p3_raw = {i: _prob3(i, a_course, b_idx, b_course,
                                members, ev_result, venue)
                      for i in thirds}

            for c_idx in sorted(thirds, key=lambda i:-p3_raw[i]):
                prob = p_a * p_b * p3_raw[c_idx]
                ab = int(members[a_idx].get("course_int",a_idx+1))
                bb = int(members[b_idx].get("course_int",b_idx+1))
                cb = int(members[c_idx].get("course_int",c_idx+1))
                combos.append({
                    "bet": f"{ab}→{bb}→{cb}", "prob": prob,
                    "p1": p_a, "p2": p_b, "p3": p3_raw[c_idx],
                    "a_kimete": a_main_kimete, "a_course": a_course,
                })

    # ── 崩れシナリオを追加（⑥主役が攻めたが崩れた時）─────────────
    fail_combos = []
    all_candidates = sorted(range(n), key=lambda i: -p1[i])[:4]
    for a_idx in all_candidates:
        fail_scenarios = _generate_fail_scenarios(
            a_idx, members, ev_result, p1, venue)
        fail_combos.extend(fail_scenarios)

    # 通常combosと崩れcomboを確率加算で合算
    prob_map = {}
    for c in combos + fail_combos:
        prob_map[c["bet"]] = prob_map.get(c["bet"], 0.0) + c["prob"]

    # metaは最初の出現を使い、確率を合算値に更新
    meta_map = {}
    for c in combos + fail_combos:
        if c["bet"] not in meta_map:
            meta_map[c["bet"]] = c.copy()
        meta_map[c["bet"]]["prob"] = prob_map[c["bet"]]

    seen, unique = set(), []
    for c in sorted(meta_map.values(), key=lambda x: -x["prob"]):
        if c["bet"] not in seen:
            seen.add(c["bet"]); unique.append(c)

    # ── 点数制御 ──────────────────────────────────────────────
    # 1着候補が何艇いるか
    n_first = len(set(c["a_course"] for c in unique[:20]))

    # 最大点数: 1着1軸→10点 / 1着2軸→14点 / 1着3軸以上→18点
    max_bets = {1: 10, 2: 14}.get(n_first, 18)

    # 累積カット率: 1軸=65% / 2軸=70% / 3軸=75%
    cum_cut  = {1: 0.65, 2: 0.70}.get(n_first, 0.75)

    # 確率下限: 上位1点の確率の30%未満は除外
    top_prob = unique[0]["prob"] if unique else 0
    prob_floor = top_prob * 0.30

    total_prob = sum(c["prob"] for c in unique)
    cum, bets = 0.0, []
    for c in unique:
        if c["prob"] < prob_floor: break  # 確率下限カット
        bets.append(c)
        cum += c["prob"]
        if cum/(total_prob or 1) >= cum_cut and len(bets) >= 6:
            break
    bets = bets[:max_bets]
    if len(bets) < 6: bets = unique[:6]

    top3    = sum(c["prob"] for c in bets[:3]) / (total_prob or 1)
    n_bets  = len(bets)
    # 点数も加味した信頼度（点数が多いほど1点あたりの確度が下がる）
    if   top3 >= 0.30 and n_bets <= 8:  conf = "高"
    elif top3 >= 0.20 and n_bets <= 12: conf = "高"
    elif top3 >= 0.15:                  conf = "中"
    elif top3 >= 0.10:                  conf = "中"
    else:                               conf = "低"

    PATTERN_JP = {
        "nige":   "インパターン（逃げ本命）",
        "sashi":  "差しパターン（1-2号艇攻防）",
        "tenkai": "展開パターン（外コース台頭）",
        "mixed":  "混戦パターン",
    }
    return {
        "pattern": pattern, "pattern_jp": PATTERN_JP[pattern],
        "combos": bets, "bets": [c["bet"] for c in bets],
        "count": len(bets), "confidence": conf,
        "p1": p1, "first_idx": first_idx, "total_prob": total_prob,
    }

# ─── 考察テキスト ─────────────────────────────────────────────
def _pct(v) -> str: return f"{float(v)*100:.1f}%" if v is not None else "-"

def build_kousatsu(members, ev_result, result, venue, race_no=0) -> str:
    """
    「なぜこの買い目になったか」を一貫したロジックで説明する考察テキスト。

    構成:
      [0] レース概況（パターン・荒れ度）
      [1] 1着軸の根拠（逃げ力・脅威・機力）
      [2] 1着候補ごとの「どの技で勝つか」と「そのときの2着分布」
      [3] 2・3着候補の根拠
      [4] 結論（買い目点数・信頼度）
    """
    nige  = ev_result.get("in_nige",  [""]*6)
    aisho = ev_result.get("aisho",    [""]*6)
    kiry  = ev_result.get("kiryoku",  [""]*6)
    jiz   = ev_result.get("jizaisei", [""]*6)
    tenk  = ev_result.get("tenkai",   [""]*6)
    p1    = result["p1"]
    are   = get_race_are_score(venue, race_no) if race_no else None
    are_s = f" 荒れ{are:.0f}pt" if are else ""

    lines = []

    # ── [0] レース概況 ──────────────────────────────────────────
    lines.append(f"■ {result['pattern_jp']}  [{venue}{are_s}]")
    lines.append("")

    # ── [1] 1着軸の根拠 ─────────────────────────────────────────
    lines.append("【1着軸の根拠】")
    first_idx = result.get("first_idx", [])
    for a_idx in first_idx:
        m_a   = members[a_idx]
        c_a   = int(m_a.get("course_int", a_idx+1))
        ns    = nige[a_idx]  if a_idx < len(nige)  else ""
        ks    = kiry[a_idx]  if a_idx < len(kiry)  else ""
        js    = jiz[a_idx]   if a_idx < len(jiz)   else ""
        as_   = aisho[a_idx] if a_idx < len(aisho) else ""
        ts    = tenk[a_idx]  if a_idx < len(tenk)  else ""
        p1_a  = p1[a_idx] if a_idx < len(p1) else 0

        # 技の主力
        sa  = _sf(m_a.get("sashi_rate"))
        mk  = _sf(m_a.get("makuri_rate"))
        mz  = _sf(m_a.get("makuri_zashi_rate"))
        kw  = _kimete_weights(m_a)
        main_kimete = max(kw, key=kw.get) if c_a != 1 else "逃げ"
        st  = m_a.get("avg_st_self")

        if c_a == 1:
            ev1 = _r("in_nige", ns, 1, 1, venue)
            sym = _b(ns) or "（評価なし）"
            lines.append(f"  1号艇  P1={_pct(p1_a)}  逃げ{sym} 実績{_pct(ev1)}"
                         f"  機力{_b(ks)}  安定{_b(js) or '－'}  ST{st or '?'}")
            # 脅威艇の表示
            threats = []
            for j, m_b in enumerate(members[1:], 1):
                c_b  = int(m_b.get("course_int", j+1))
                sa_b = _sf(m_b.get("sashi_rate"))
                mk_b = _sf(m_b.get("makuri_rate"))
                mz_b = _sf(m_b.get("makuri_zashi_rate"))
                atk  = sa_b + mk_b + mz_b
                if atk > 0.30:
                    threats.append((c_b, atk, sa_b, mk_b, mz_b))
            if threats:
                lines.append("  脅威艇:")
                for c_b, atk, sa_b, mk_b, mz_b in sorted(threats, key=lambda x:-x[1])[:3]:
                    techs = []
                    if sa_b > 0.05: techs.append(f"差し{sa_b:.0%}")
                    if mk_b > 0.05: techs.append(f"まくり{mk_b:.0%}")
                    if mz_b > 0.05: techs.append(f"まくり差し{mz_b:.0%}")
                    lines.append(f"    {c_b}号艇  攻め合計{atk:.0%}  ({' / '.join(techs)})")
        else:
            sym = _b(as_) or _b(ts) or "（評価なし）"
            techs = []
            if sa  > 0.05: techs.append(f"差し{sa:.0%}")
            if mk  > 0.05: techs.append(f"まくり{mk:.0%}")
            if mz  > 0.05: techs.append(f"まくり差し{mz:.0%}")
            lines.append(f"  {c_a}号艇  P1={_pct(p1_a)}  相性{sym}"
                         f"  機力{_b(ks)}  主力:{main_kimete}"
                         f"  ({' / '.join(techs) if techs else 'データなし'})")

    lines.append("")

    # ── [2] 1着候補ごとの「技×展開」分析 ─────────────────────────
    lines.append("【展開分析：1着の技によって2着が変わる】")
    for a_idx in first_idx:
        m_a   = members[a_idx]
        c_a   = int(m_a.get("course_int", a_idx+1))
        p1_a  = p1[a_idx] if a_idx < len(p1) else 0
        kw    = _kimete_weights(m_a) if c_a != 1 else {"逃げ": 1.0}
        others = [i for i in range(len(members)) if i != a_idx]

        lines.append(f"  ▶ {c_a}号艇 1着（P1={_pct(p1_a)}）のとき:")

        if c_a == 1:
            # 逃げ固定
            lines.append(f"    決まり手: 逃げ（固定）")
            b_rates = []
            for b_idx in others:
                m_b  = members[b_idx]
                c_b  = int(m_b.get("course_int", b_idx+1))
                ib   = get_innige_bunseki(venue, c_b)
                tz   = get_tenkai_zanson("逃げ", 1, c_b, venue)
                r2   = ib["r2"] if ib else (tz["r2"] if tz else _base(c_b, 2, venue))
                b_rates.append((c_b, r2))
            b_rates.sort(key=lambda x: -x[1])
            lines.append(f"    2着実績: " +
                         "  ".join(f"{c}号艇{r:.1%}" for c,r in b_rates[:4]))
        else:
            # 技別に2着分布を表示
            for kimete, w in sorted(kw.items(), key=lambda x:-x[1]):
                if w < 0.05: continue
                b_rates = []
                for b_idx in others:
                    m_b = members[b_idx]
                    c_b = int(m_b.get("course_int", b_idx+1))
                    tz  = get_tenkai_zanson(kimete, c_a, c_b, venue)
                    r2  = tz["r2"] if tz else _base(c_b, 2, venue)
                    b_rates.append((c_b, r2))
                b_rates.sort(key=lambda x: -x[1])
                lines.append(f"    {kimete}({w:.0%}): 2着→ " +
                             "  ".join(f"{c}号艇{r:.1%}" for c,r in b_rates[:4]))
            # 加重平均
            lines.append(f"    ─加重平均2着確率─")
            merged = {}
            for b_idx in others:
                m_b  = members[b_idx]
                c_b  = int(m_b.get("course_int", b_idx+1))
                r2w  = 0.0
                for kimete, w in kw.items():
                    if w < 0.01: continue
                    tz = get_tenkai_zanson(kimete, c_a, c_b, venue)
                    r2w += (tz["r2"] if tz else _base(c_b, 2, venue)) * w
                merged[c_b] = r2w
            top_b = sorted(merged.items(), key=lambda x:-x[1])
            lines.append("    " + "  ".join(f"{c}号艇{r:.1%}" for c,r in top_b[:4]))

    lines.append("")

    # ── [3] 2・3着候補の根拠 ─────────────────────────────────────
    lines.append("【2・3着候補の根拠】")
    # combosから2着・3着の出現頻度を集計
    from collections import Counter
    cnt2 = Counter()
    cnt3 = Counter()
    for combo in result["combos"]:
        parts = combo["bet"].split("→")
        if len(parts) == 3:
            cnt2[parts[1]] += combo["prob"]
            cnt3[parts[2]] += combo["prob"]

    top2 = cnt2.most_common(4)
    top3 = cnt3.most_common(4)
    total = sum(c["prob"] for c in result["combos"])
    if total > 0:
        lines.append(f"  2着: " + "  ".join(
            f"{c}号艇({v/total:.0%})" for c,v in top2))
        lines.append(f"  3着: " + "  ".join(
            f"{c}号艇({v/total:.0%})" for c,v in top3))

        # 2着候補の根拠
        lines.append("  2着候補の攻め力:")
        shown = set()
        for c_str, _ in top2[:3]:
            if c_str in shown: continue
            shown.add(c_str)
            c_int = int(c_str)
            idx = next((i for i,m in enumerate(members)
                        if int(m.get("course_int",i+1))==c_int), None)
            if idx is None: continue
            m_b  = members[idx]
            sa   = _sf(m_b.get("sashi_rate"))
            mk   = _sf(m_b.get("makuri_rate"))
            mz   = _sf(m_b.get("makuri_zashi_rate"))
            st   = m_b.get("avg_st_self")
            as_  = aisho[idx] if idx < len(aisho) else ""
            ts   = tenk[idx]  if idx < len(tenk)  else ""
            sym  = _b(as_) or _b(ts)
            techs = []
            if sa  > 0.05: techs.append(f"差し{sa:.0%}")
            if mk  > 0.05: techs.append(f"まくり{mk:.0%}")
            if mz  > 0.05: techs.append(f"まくり差し{mz:.0%}")
            lines.append(f"    {c_int}号艇 相性{sym or '－'}"
                         f"  ST{st or '?'}"
                         f"  ({' / '.join(techs) if techs else 'データなし'})")

    lines.append("")

    # ── [4] 結論 ────────────────────────────────────────────────
    lines.append(f"【結論】{result['count']}点  信頼度:{result['confidence']}")
    lines.append(f"  買い目: " + "  ".join(result["bets"][:5]) +
                 (f"  他{result['count']-5}点" if result["count"] > 5 else ""))

    return "\n".join(lines)


def build_logic_text(members, ev_result, result) -> str:
    """数値ベースのスコア詳細（Excel出力用）"""
    p1    = result["p1"]
    lines = [
        f"パターン: {result['pattern_jp']}",
        "P(1着) 正規化後 / 主力決まり手 / 攻め合計:",
    ]
    for i, m in enumerate(members):
        c    = int(m.get("course_int", i+1))
        kw   = _kimete_weights(m) if c != 1 else {"逃げ": 1.0}
        main = max(kw, key=kw.get)
        sa   = _sf(m.get("sashi_rate"))
        mk   = _sf(m.get("makuri_rate"))
        mz   = _sf(m.get("makuri_zashi_rate"))
        atk  = sa + mk + mz
        lines.append(
            f"  {c}号艇 P1={_pct(p1[i] if i<len(p1) else 0)}"
            f"  主力:{main}  攻め合計:{atk:.2f}"
            f"  (差し:{sa:.2f} まくり:{mk:.2f} まくり差し:{mz:.2f})"
        )
    lines.append(f"確率上位{result['count']}点:")
    for c in result["combos"]:
        lines.append(f"  {c['bet']}  {c['prob']*100:.3f}%"
                     f"  [決={c['a_kimete']} P1={_pct(c['p1'])} P2={_pct(c['p2'])} P3={_pct(c['p3'])}]")
    return "\n".join(lines)


# ─── メイン ──────────────────────────────────────────────────
def recommend(members, ev_result, venue="__ALL__", race_no=0,
              weather_speed=None, wave_height=None) -> dict:
    result   = generate_sanrentan(members, ev_result, venue, race_no, weather_speed, wave_height)
    kousatsu = build_kousatsu(members, ev_result, result, venue, race_no)
    logic    = build_logic_text(members, ev_result, result)
    bet_list = "\n".join(result["bets"])
    p1       = result["p1"]
    top3     = "・".join(f"{int(members[i].get('course_int',i+1))}号"
                         for i in sorted(range(len(members)),key=lambda i:-p1[i])[:3])
    summary  = f"【{result['pattern_jp']}】上位:{top3} 信頼度:{result['confidence']} {result['count']}点"
    return {
        "scores":     [{"boat":int(m.get("course_int",i+1)),"score_1":p1[i],"ev1":p1[i]}
                       for i,m in enumerate(members)],
        "pattern":    result["pattern"],    "pattern_jp":  result["pattern_jp"],
        "bets":       result["bets"],       "count":       result["count"],
        "confidence": result["confidence"], "kousatsu":    kousatsu,
        "logic":      logic,               "bet_list":    bet_list,
        "summary":    summary,
        "p1":         p1,                  "combos":      result["combos"],
        "excel_cells":{"レース考察":kousatsu,"買い目ロジック":logic,
                       "買い目リスト":bet_list,"買い目点数":result["count"],"信頼度":result["confidence"]},
    }

# ─── 単体テスト ──────────────────────────────────────────────
if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from evaluate_jizen import evaluate_all

    _sd = {"st_stable_score":70.0,"fly_count":0,"fly_days":None,"late_count":0,"st_count":50}
    cases = {
        "A: インパターン": ([
            {"rate_1st_c1":0.70,"st_rank_c1":1.0,"star_rate":False,"nigé_rate":0.82,
             "attack_rate":0.0,"sashi_rate":0.0,"makuri_rate":0.0,"makuri_zashi_rate":0.0,
             "avg_st_self":0.13,"lose_sashi_rate":0.08,"lose_makuri_rate":0.05,
             "lose_rate_reliable":True,"motor_2rate":52.0,"diversity_rate":0.0,
             "jizaisei_rate":0.05,"star_kimete":False,"rate_3ren":0.85,"course_int":1,
             **{**_sd,"st_stable_score":90.0}},
            {"rate_1st_c1":0.08,"avg_st_self":0.22,"sashi_rate":0.10,"makuri_rate":0.05,
             "makuri_zashi_rate":0.05,"attack_rate":0.20,"motor_2rate":35.0,"rate_3ren":0.35,
             "course_int":2,"nigé_rate":0.0,"star_rate":False,"star_kimete":False,
             "diversity_rate":0.15,"jizaisei_rate":0.10,"st_rank_c1":5.0,
             "lose_sashi_rate":None,"lose_makuri_rate":None,"lose_rate_reliable":False,
             **{**_sd,"fly_count":1,"fly_days":75.0}},
            {"rate_1st_c1":0.08,"avg_st_self":0.16,"sashi_rate":0.10,"makuri_rate":0.20,
             "makuri_zashi_rate":0.15,"attack_rate":0.45,"motor_2rate":40.0,"rate_3ren":0.50,
             "course_int":3,"nigé_rate":0.0,"star_rate":False,"star_kimete":False,
             "diversity_rate":0.40,"jizaisei_rate":0.18,"st_rank_c1":4.0,
             "lose_sashi_rate":None,"lose_makuri_rate":None,"lose_rate_reliable":False,**_sd},
            {"rate_1st_c1":0.10,"avg_st_self":0.15,"sashi_rate":0.05,"makuri_rate":0.40,
             "makuri_zashi_rate":0.15,"attack_rate":0.55,"motor_2rate":48.0,"rate_3ren":0.52,
             "course_int":4,"nigé_rate":0.0,"star_rate":False,"star_kimete":False,
             "diversity_rate":0.45,"jizaisei_rate":0.22,"st_rank_c1":3.0,
             "lose_sashi_rate":None,"lose_makuri_rate":None,"lose_rate_reliable":False,
             **{**_sd,"st_stable_score":85.0}},
            {"rate_1st_c1":0.07,"avg_st_self":None,"sashi_rate":0.05,"makuri_rate":0.25,
             "makuri_zashi_rate":0.10,"attack_rate":0.30,"motor_2rate":None,"rate_3ren":0.40,
             "course_int":5,"nigé_rate":0.0,"star_rate":False,"star_kimete":False,
             "diversity_rate":0.20,"jizaisei_rate":0.10,"st_rank_c1":5.5,
             "lose_sashi_rate":None,"lose_makuri_rate":None,"lose_rate_reliable":False,
             **{**_sd,"st_stable_score":55.0,"late_count":4}},
            {"rate_1st_c1":0.05,"avg_st_self":0.21,"sashi_rate":0.05,"makuri_rate":0.15,
             "makuri_zashi_rate":0.10,"attack_rate":0.20,"motor_2rate":28.0,"rate_3ren":0.30,
             "course_int":6,"nigé_rate":0.0,"star_rate":False,"star_kimete":True,
             "diversity_rate":0.15,"jizaisei_rate":0.08,"st_rank_c1":6.0,
             "lose_sashi_rate":None,"lose_makuri_rate":None,"lose_rate_reliable":False,
             **{**_sd,"st_stable_score":40.0,"fly_count":2,"fly_days":50.0}},
        ], "nige"),
        "B: 差しパターン": ([
            {"rate_1st_c1":0.55,"avg_st_self":0.18,"sashi_rate":0.0,"makuri_rate":0.0,
             "makuri_zashi_rate":0.0,"attack_rate":0.0,"motor_2rate":45.0,"rate_3ren":0.75,
             "course_int":1,"nigé_rate":0.72,"star_rate":False,"star_kimete":False,
             "diversity_rate":0.0,"jizaisei_rate":0.05,"st_rank_c1":3.0,
             "lose_sashi_rate":0.18,"lose_makuri_rate":0.08,"lose_rate_reliable":True,**_sd},
            {"rate_1st_c1":0.10,"avg_st_self":0.12,"sashi_rate":0.55,"makuri_rate":0.05,
             "makuri_zashi_rate":0.05,"attack_rate":0.65,"motor_2rate":55.0,"rate_3ren":0.60,
             "course_int":2,"nigé_rate":0.0,"star_rate":False,"star_kimete":False,
             "diversity_rate":0.60,"jizaisei_rate":0.25,"st_rank_c1":1.5,
             "lose_sashi_rate":None,"lose_makuri_rate":None,"lose_rate_reliable":False,**_sd},
            {"rate_1st_c1":0.08,"avg_st_self":0.15,"sashi_rate":0.10,"makuri_rate":0.20,
             "makuri_zashi_rate":0.25,"attack_rate":0.55,"motor_2rate":30.0,"rate_3ren":0.55,
             "course_int":3,"nigé_rate":0.0,"star_rate":False,"star_kimete":False,
             "diversity_rate":0.50,"jizaisei_rate":0.20,"st_rank_c1":4.0,
             "lose_sashi_rate":None,"lose_makuri_rate":None,"lose_rate_reliable":False,**_sd},
            {"rate_1st_c1":0.12,"avg_st_self":0.13,"sashi_rate":0.05,"makuri_rate":0.45,
             "makuri_zashi_rate":0.35,"attack_rate":0.30,"motor_2rate":35.0,"rate_3ren":0.50,
             "course_int":4,"nigé_rate":0.0,"star_rate":False,"star_kimete":False,
             "diversity_rate":0.45,"jizaisei_rate":0.20,"st_rank_c1":2.5,
             "lose_sashi_rate":None,"lose_makuri_rate":None,"lose_rate_reliable":False,**_sd},
            {"rate_1st_c1":0.09,"avg_st_self":None,"sashi_rate":0.05,"makuri_rate":0.25,
             "makuri_zashi_rate":0.20,"attack_rate":0.20,"motor_2rate":None,"rate_3ren":0.45,
             "course_int":5,"nigé_rate":0.0,"star_rate":False,"star_kimete":False,
             "diversity_rate":0.20,"jizaisei_rate":0.10,"st_rank_c1":5.0,
             "lose_sashi_rate":None,"lose_makuri_rate":None,"lose_rate_reliable":False,**_sd},
            {"rate_1st_c1":0.06,"avg_st_self":0.22,"sashi_rate":0.05,"makuri_rate":0.20,
             "makuri_zashi_rate":0.15,"attack_rate":0.15,"motor_2rate":20.0,"rate_3ren":0.30,
             "course_int":6,"nigé_rate":0.0,"star_rate":False,"star_kimete":True,
             "diversity_rate":0.15,"jizaisei_rate":0.08,"st_rank_c1":6.0,
             "lose_sashi_rate":None,"lose_makuri_rate":None,"lose_rate_reliable":False,**_sd},
        ], "sashi"),
    }

    for label,(mems,expected) in cases.items():
        print("="*64)
        print(f"  テスト{label}")
        print("="*64)
        ev  = evaluate_all(mems)
        for k in ["in_nige","aisho","kiryoku","jizaisei","tenkai"]:
            print(f"  {k:12s}: {ev[k]}")
        res = recommend(mems, ev, venue="大村", race_no=3)
        ok  = "✅" if res["pattern"]==expected else "⚠"
        print(f"\nパターン: {res['pattern_jp']}  期待:{expected} {ok}")
        print(f"\n{res['kousatsu']}")
        print(f"\n【3連単 {res['count']}点】")
        for b in res["bets"]: print(f"  {b}")
        print(f"\n{res['summary']}\n")
    print("✅ テスト完了")
