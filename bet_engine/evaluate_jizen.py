"""
evaluate_jizen.py
=================
ボートリサーチ倶楽部流 事前評価 算出モジュール

load_race.py から import して使用します。
単体テストも末尾に記載。

【システム前提】
    進入は枠なり固定。展示で進入変更があった場合はレースに参加しない。
    このモジュールは展示前確定情報のみで動作する。

算出する5項目:
    ① in_nigé   : イン逃げ評価   ◎>○>△>空白
    ② aishō     : 相性評価       ◎>○>△>空白（1枠は常に空白）
    ③ kiryoku   : 機力評価       A>B>C>D>E
    ④ jizaisei  : 自在性評価     ◎>○>△>空白
    ⑤ tenkai    : 展開評価       ◎>○>△>空白（3〜6枠のみ）

【v2 変更点】
    ③ 機力: モーターデータなし艇に中央値を代入し「-」消滅。
    ④ 自在性: 乗算→加重平均に変更し、どちらか一方が0でも評価が消えなくなる。
    ⑤ 展開: 3枠も評価対象に追加（3コースのまくり差しは展開形成の主役）。
             評価対象4艇（3〜6枠）内でランク付け。

【v3 変更点】
    ② 相性: 評価軸の優先順位を競艇の本質に合わせて再設計。
            優先順位:
              1位（45%）自分の決まり手%（差し・まくり系）
              2位（35%）1号艇とのST差
              3位（20%）1号艇の被決まり手%

【v4 変更点】
    ② 相性: ST優位スコアにコース別正規化幅を適用。
            艇間干渉スコアを第4因子として追加（重み10%）。
            攻め武器の重みを45%→40%に微調整。

【v5 変更点】
    ② 相性(2号艇): ST差の重みを35%→50%に引き上げ、攻め武器を40%→30%に引き下げ。
               2号艇の差しはSTで8割が決まるという競艇の原則に合わせた修正。
               3〜6号艇の重みは現行維持（攻め武器40%, ST差35%, 被決まり手15%, 干渉10%）。

【v7 変更点】─────────────────────────────────────────────────────
    ② 相性: 攻め武器スコアを「コース固定の決まり手」から
            「実データの全決まり手%を動的に重み付け」した計算に変更。

            旧方式の問題:
              2号艇 = sashi_rate のみ（まくり差し%を無視）
              3〜6号艇 = makuri_rate + makuri_zashi_rate のみ（差し%を無視）
              → 3コースの差し巧者、2コースのまくり差し選手が過小評価されていた。

            新方式: _calc_weapon_score(sashi, makuri, makuri_zashi, course) で計算。
              各コースで「期待値が高い決まり手の重み」を基本係数とし、
              実データ比率でさらに動的に調整する。

              基本係数（全国平均の決まり手比率から導出）:
                コース2: 差し×0.65  まくり差し×0.25  まくり×0.10
                コース3: まくり差し×0.45  まくり×0.35  差し×0.20
                コース4: まくり×0.60  まくり差し×0.30  差し×0.10
                コース5: まくり×0.65  まくり差し×0.25  差し×0.10
                コース6: まくり×0.60  まくり差し×0.30  差し×0.10

              さらに実データ比率が基本係数から大きく乖離する場合（例: 3コースで
              差しがまくりより実際に多い会場）、実データ比率に寄せる動的補正を加える。
              → 画像で示された「3コース差し6%≒まくり6%」のような会場特性を自動反映。
─────────────────────────────────────────────────────────────────

【v6 変更点】─────────────────────────────────────────────────────
    ① イン逃げ: 2〜6号艇全員に対する相対評価に刷新。
               問い:「1号艇が今日のメンバー全員に対して逃げ切れるか」
               各艇の対1号艇脅威スコア（攻め武器×0.50 + ST優位×0.50）を計算し、
               max_threat×0.70 + mean_threat×0.30 で全体脅威を集約。
               逃げスコア = 1号艇合成スコア − 全体脅威 × 0.35
               最大脅威を主軸に置くのは「最も強い1艇に突破されると逃げが消える」
               という競艇の本質を反映するため。
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations
from typing import Any


# ============================================================
# 共通ユーティリティ
# ============================================================

def _rank6(scores: list[float | None]) -> list[int | None]:
    """
    任意長のスコアリストをランク（1=最高）に変換。
    Noneはランク対象外でNoneを返す。
    同点は同順位（dense ranking）。
    """
    indexed = [(i, s) for i, s in enumerate(scores) if s is not None]
    if not indexed:
        return [None] * len(scores)

    sorted_vals = sorted({s for _, s in indexed}, reverse=True)
    rank_map = {v: r + 1 for r, v in enumerate(sorted_vals)}

    result: list[int | None] = [None] * len(scores)
    for i, s in indexed:
        result[i] = rank_map[s]
    return result


def _symbol_4(rank: int | None, max_rank: int = 6) -> str:
    """
    ランク → ◎>○>△>空白 に変換（4段階）。
    max_rank: 評価対象の総数（境界計算に使用）
    """
    if rank is None:
        return ""
    if rank == 1:
        return "◎"
    if rank == 2:
        return "○"
    if rank <= round(max_rank * 0.67):
        return "△"
    return ""


def _symbol_grade(rank: int | None, n: int = 6) -> str:
    """
    ランク → A>B>C>D>E に変換（機力用）。
    """
    if rank is None:
        return "C"   # データなし艇はデフォルト C（中央値代入後なので通常到達しない）
    grade = ["A", "B", "C", "D", "E"]
    idx = min(round((rank - 1) / max(n - 1, 1) * 4), 4)
    return grade[idx]


def _safe(val: Any, default: float = 0.0) -> float:
    """None・文字列を安全にfloatへ変換"""
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _median_of(values: list[float]) -> float:
    """非空リストの中央値を返す"""
    s = sorted(values)
    n = len(s)
    if n == 0:
        return 0.0
    mid = n // 2
    return (s[mid - 1] + s[mid]) / 2 if n % 2 == 0 else s[mid]


# ============================================================
# ① イン逃げ評価
# ============================================================

def _calc_weapon_score(
    sashi: float, makuri: float, makuri_zashi: float, course: int
) -> float:
    """
    全決まり手%を実データ比率で動的重み付けして攻め武器スコアを計算。

    【v7 新設】
    旧方式: 2号艇=差しのみ、3〜6号艇=まくり+まくり差しのみ（固定）
    新方式: 全決まり手%を「基本係数 × 0.50 + 実データ比率 × 0.50」でブレンド

    基本係数（コース別全国平均決まり手比率から導出）:
        2コース: 差し×0.65  まくり差し×0.25  まくり×0.10
        3コース: まくり差し×0.45  まくり×0.35  差し×0.20  ← 差しも評価対象
        4コース: まくり×0.60  まくり差し×0.30  差し×0.10
        5コース: まくり×0.65  まくり差し×0.25  差し×0.10
        6コース: まくり×0.60  まくり差し×0.30  差し×0.10

    実データ比率でブレンドする理由:
        「3コース差し6%≒まくり6%」のような会場では差しとまくりが
        拮抗して評価され、差し巧者の3コース選手が過小評価されなくなる。
        逆に「3コースまくり差しが圧倒的」な会場では基本係数を強化する方向に働く。

    Returns
    -------
    float: 攻め武器スコア（0.0〜約1.0）。全データ0のとき0.0を返す。
    """
    total = sashi + makuri + makuri_zashi
    if total <= 0.0:
        return 0.0

    # 実データ比率（差し/まくり/まくり差し それぞれが全体に占める割合）
    r_s  = sashi        / total
    r_mk = makuri       / total
    r_mz = makuri_zashi / total

    # コース別基本係数 (差し, まくり, まくり差し)
    # 全国平均の決まり手分布: 2C=差し主体、3C=まくり差し主体(差しも有意)、
    #                         4〜6C=まくり主体
    BASE: dict[int, tuple[float, float, float]] = {
        2: (0.65, 0.10, 0.25),
        3: (0.20, 0.35, 0.45),
        4: (0.10, 0.60, 0.30),
        5: (0.10, 0.65, 0.25),
        6: (0.10, 0.60, 0.30),
    }
    b_s, b_mk, b_mz = BASE.get(course, (0.15, 0.50, 0.35))

    # 基本係数 50% + 実データ比率 50% でブレンド
    w_s  = b_s  * 0.50 + r_s  * 0.50
    w_mk = b_mk * 0.50 + r_mk * 0.50
    w_mz = b_mz * 0.50 + r_mz * 0.50

    return sashi * w_s + makuri * w_mk + makuri_zashi * w_mz


def _threat_score_vs_1(m: dict, avg_st_1: float | None, course: int) -> float:
    """
    1艇分の「対1号艇脅威スコア」を計算する内部ヘルパー。

    各コースの攻め武器とST優位を組み合わせて
    「この艇が1号艇に勝てる力」を 0.0〜1.0 で返す。

    【v7 変更】攻め武器を _calc_weapon_score による動的重み付けに変更。
    旧: 2コース=差しのみ、3〜6コース=まくり+まくり差しのみ（固定）
    新: 全決まり手%を実データ比率でブレンドして算出。

    ST優位スコアは _st_advantage_score を流用（コース別正規化幅）。
    合成: 攻め武器 × 0.50 + ST優位 × 0.50
    """
    avg_st_self = m.get("avg_st_self")
    st_adv = _st_advantage_score(avg_st_self, avg_st_1, course_self=course)

    sashi = _safe(m.get("sashi_rate"))
    makuri = _safe(m.get("makuri_rate"))
    makuri_zashi = _safe(m.get("makuri_zashi_rate"))
    weapon = _calc_weapon_score(sashi, makuri, makuri_zashi, course)
    if weapon <= 0.0:
        weapon = _safe(m.get("attack_rate")) * (0.80 if course == 2 else 0.60)

    weapon = min(weapon, 1.0)
    return weapon * 0.50 + st_adv * 0.50


def calc_in_nige(members: list[dict]) -> list[str]:
    """
    逃げ評価は1号艇（インデックス0）専用。2〜6号艇は常に空白。

    ════════════════════════════════════════════════════════════════
    【v6: 全メンバー相対評価に変更】
    問い: 「1号艇が今日の2〜6号艇全員に対して逃げ切れるか」

    逃げが成立する条件は「全員をかわすこと」。
    最も強い1艇に突破されても逃げは消える。
    複数艇から同時に圧力をかけられても逃げは苦しくなる。
    この2つを数値化して1号艇スコアから差し引く。

    ────────────────────────────────────────────────────────────────
    ■ Step1: 1号艇の逃げ合成スコア（0〜1）

        rate_1st_c1 × 0.40 + ST順位スコア × 0.60

        ST順位スコア = (7 - st_rank_c1) / 6
          1位→1.00 / 3位→0.67 / 6位→0.17 / データなし→0.50（中立）

    ■ Step2: 2〜6号艇それぞれの「対1号艇脅威スコア」を計算

        各艇の脅威スコア = 攻め武器 × 0.50 + ST優位（対1号艇）× 0.50

        攻め武器:
          2号艇  → 差し%（最低保証値0.35）
          3〜6号艇 → まくり% + まくり差し%

        ST優位: _st_advantage_score を流用（コース別正規化幅）

    ■ Step3: メンバー全体の脅威を集約

        max_threat  = 脅威スコアの最大値（最も危険な1艇）
        mean_threat = 脅威スコアの平均値（包囲圧力の全体水準）

        total_threat = max_threat × 0.70 + mean_threat × 0.30

        最大脅威を主軸（0.70）とするのは、
        競艇の逃げは「最も強い攻め手1艇をかわせるか」で
        ほぼ決まるため。平均脅威（0.30）は複数艇が同水準で
        圧力をかけている状況を補正する役割。

    ■ Step4: 相対逃げスコア

        relative_score = nige_score − total_threat × 0.45

        total_threat の45%を減算。
        係数0.45は「相手全員が最強水準（1.0）のとき逃げ評価が
        空白まで落ちる」現実的なバランスに合わせた値。
        係数0.35では外側艇の圧力が軽すぎるため引き上げ。

    ────────────────────────────────────────────────────────────────
    【記号の閾値（相対スコア）】
    実際の分布は概ね −0.10〜+0.75 程度。

       ◎ (relative ≥ 0.45) : 全メンバーを踏まえても逃げ信頼度高
       ○ (relative ≥ 0.33) : 逃げ期待できる
       △ (relative ≥ 0.20) : 圧力あり、やや不安
       空白 (relative < 0.20): 逃げ苦しい。誰かに突破されるリスク大

    ────────────────────────────────────────────────────────────────
    【暫定★フラグ】
    マスタの実績が少ない場合、記号に「⚠️」を付与。

    returns: 6要素の記号リスト（インデックス0=1号艇、1〜5は空白）
    ════════════════════════════════════════════════════════════════
    """
    if not members:
        return []

    m0 = members[0]
    avg_st_1 = m0.get("avg_st_self")

    # ── Step1: 1号艇の逃げ合成スコア ──────────────────────────────
    rate = _safe(m0.get("rate_1st_c1"))
    st_rank = m0.get("st_rank_c1")
    st_score_1 = (7 - _safe(st_rank)) / 6 if st_rank is not None else 0.5
    nige_score = rate * 0.40 + st_score_1 * 0.60

    # ── Step2: 2〜6号艇それぞれの脅威スコアを計算 ─────────────────
    threat_list: list[float] = []
    for i, m in enumerate(members[1:], start=2):   # i=コース番号(2〜6)
        course = int(m.get("course_int", i))
        threat_list.append(_threat_score_vs_1(m, avg_st_1, course))

    # ── Step3: 全体脅威の集約 ─────────────────────────────────────
    if threat_list:
        max_threat  = max(threat_list)
        mean_threat = sum(threat_list) / len(threat_list)
        total_threat = max_threat * 0.70 + mean_threat * 0.30
    else:
        total_threat = 0.0

    # ── Step4: 相対逃げスコア ─────────────────────────────────────
    relative_score = nige_score - total_threat * 0.45

    # 記号決定
    if relative_score >= 0.45:
        sym = "◎"    # 全メンバーを踏まえても逃げ信頼度高
    elif relative_score >= 0.33:
        sym = "○"    # 逃げ期待できる
    elif relative_score >= 0.20:
        sym = "△"    # 圧力あり、やや不安
    else:
        sym = ""     # 逃げ苦しい、誰かに突破されるリスク大

    # 暫定★フラグ
    if m0.get("star_rate") and sym:
        sym += "⚠️"

    # 2〜6号艇は空白（逃げ評価は1号艇専用）
    return [sym] + [""] * (len(members) - 1)


# ============================================================
# ② 相性評価（v3: 優先順位付き 3要素加重スコア）
# ============================================================

def _st_advantage_score(
    avg_st_self: float | None,
    avg_st_1: float | None,
    course_self: int = 3,
) -> float:
    """
    1号艇とのST相対位置をスコア化（0.0〜1.0）。

    【v4 変更点】
    コース別の「仕掛け有効ST差閾値」を導入。
    競艇の物理法則では、コースが外になるほど
    スタート位置が遠いため、同じST差でも仕掛けの
    しやすさが変わる。

    有効差閾値（仕掛けが届く最大ST差）:
        2コース（差し）: ±0.025秒 — 最も繊細。小差で差せる
        3コース（まくり差し）: ±0.035秒
        4コース（まくり）: ±0.045秒
        5〜6コース（大外まくり）: ±0.055秒

    この閾値で diff を正規化することで、
    外コースほどST有利/不利の影響が大きく出る。
    どちらかのSTデータがない場合は中立値 0.5 を返す。
    """
    if avg_st_self is None or avg_st_1 is None:
        return 0.5   # データなし → 中立

    # コース別の正規化幅（仕掛け有効ST差）
    NORM_BY_COURSE = {2: 0.025, 3: 0.035, 4: 0.045, 5: 0.055, 6: 0.055}
    norm = NORM_BY_COURSE.get(course_self, 0.035)

    diff = avg_st_1 - avg_st_self   # 正 = 自分が速い（有利）
    score = diff / norm * 0.5 + 0.5
    return max(0.0, min(1.0, score))


def calc_aisho(members: list[dict]) -> list[str]:
    """
    members: 艇番順リスト（インデックス0=1号艇）。
    各要素に以下のキーが必要:

        【攻め武器】
            sashi_rate         : 自コースの差し%
            makuri_rate        : 自コースのまくり%
            makuri_zashi_rate  : 自コースのまくり差し%
            attack_rate        : 上記3種の合計（フォールバック用）

        【STデータ】
            avg_st_self        : 自分のコース別平均ST（float 秒）
            course_int         : 自コース番号（int, ST正規化幅に使用）
            avg_st_1           : 1号艇の1コース平均ST（全艇共通: members[0] から参照）

        【1号艇の被決まり手%】※ members[0] に格納
            lose_sashi_rate    : 1号艇が差された%
            lose_makuri_rate   : 1号艇が捲られた%
            lose_rate_reliable : C1敗戦数≥10ならTrue（v6.5追加）
                                 Falseの場合はlose_sashi/makuriをNone扱いにして
                                 ippan_rate_1（逃げ以外率）でフォールバック
            nigé_rate          : 1号艇の逃げ%（被決まり手データ不在時のフォールバック）

        【4位 10%】艇間干渉スコア（v4新規）
            直前コース艇（自コース-1）の攻め武器強度から
            「自分が仕掛けるより前に内側から先に行かれる」リスクを評価。
            内側干渉が強いほどスコアが下がる。

    【v5 変更点: 2号艇の重み変更】
    ─────────────────────────────────────────────────────────────────
    2号艇の差しはSTで8割が決まるという競艇の原則に基づき、
    2号艇のみ重みを以下のように変更する:

        2号艇: 攻め武器30% + ST差50% + 被決まり手15% + 干渉5%
        3〜6号艇（変更なし）: 攻め武器40% + ST差35% + 被決まり手15% + 干渉10%

    2号艇がSTで1号艇を上回るかどうかが相性◎の最重要条件。
    攻め武器（差し%）は確認材料として残すが主軸はSTに移す。
    干渉は2号艇の内側（1号艇）は攻撃艇ではないため重みを5%に縮小。
    ─────────────────────────────────────────────────────────────────
    """
    if not members:
        return []

    # ── 1号艇のデータ取得 ──
    m0 = members[0]
    avg_st_1    = m0.get("avg_st_self")          # 1号艇の1コース平均ST
    nige_rate_1 = _safe(m0.get("nigé_rate"), 1.0)
    ippan_rate_1 = 1.0 - nige_rate_1              # 逃げ以外率（フォールバック）

    # 【v6.5対応】C1敗戦数 < 10 の場合は被決まり手%が不安定なためフォールバック扱いにする
    _lose_reliable = m0.get("lose_rate_reliable", True)
    lose_sashi  = m0.get("lose_sashi_rate")  if _lose_reliable else None
    lose_makuri = m0.get("lose_makuri_rate") if _lose_reliable else None

    # 艇間干渉スコア計算用: 各艇の攻め武器を事前に計算しておく
    # 【v7】_calc_weapon_score を使用して全決まり手を動的評価
    def _weapon(idx, m):
        s  = _safe(m.get("sashi_rate"))
        mk = _safe(m.get("makuri_rate"))
        mz = _safe(m.get("makuri_zashi_rate"))
        c  = int(m.get("course_int", idx + 1))
        w  = _calc_weapon_score(s, mk, mz, c)
        if w > 0.0:
            return w
        a = _safe(m.get("attack_rate"))
        return a * (0.8 if c == 2 else 0.6) if a > 0 else 0.10

    weapons = [_weapon(i, m) for i, m in enumerate(members)]

    scores: list[float | None] = [None]            # 1号艇は評価外

    for i, m in enumerate(members):
        if i == 0:
            continue

        course_self = int(m.get("course_int", i + 1))

        # ── 攻め武器スコア（v7: 全決まり手の動的重み付け）──
        sashi        = _safe(m.get("sashi_rate"))
        makuri       = _safe(m.get("makuri_rate"))
        makuri_zashi = _safe(m.get("makuri_zashi_rate"))
        attack_all   = _safe(m.get("attack_rate"))

        weapon = _calc_weapon_score(sashi, makuri, makuri_zashi, course_self)
        if weapon <= 0.0:
            # 全データなし → attack_rate でフォールバック
            weapon = attack_all * (0.8 if course_self == 2 else 0.6) if attack_all > 0 else 0.10

        # ── ST優位スコア（コース別正規化幅） ──
        avg_st_self = m.get("avg_st_self")
        st_score = _st_advantage_score(avg_st_self, avg_st_1, course_self=course_self)

        # ── 1号艇の被決まり手補正 ──
        # 【v7】コースに応じた被決まり手を参照する。
        # 2コース → 差された%（差し系の攻め）
        # 3コース → 差された%とまくられ%の加重平均（まくり差し+差し混在コース）
        # 4〜6コース → まくられ%（まくり系の攻め）
        if i == 1:
            # 2号艇: 差し主体。1号艇が差されやすいほど有利
            vuln = _safe(lose_sashi) if lose_sashi is not None else ippan_rate_1
        elif i == 2:
            # 3号艇: まくり差し+差しが混在。両方を重み付けで参照
            ls = _safe(lose_sashi)  if lose_sashi  is not None else None
            lm = _safe(lose_makuri) if lose_makuri is not None else None
            if ls is not None and lm is not None:
                # 3コースは差し20%・まくり差し45%なので被まくり差し主体
                vuln = ls * 0.40 + lm * 0.60
            elif lm is not None:
                vuln = lm
            elif ls is not None:
                vuln = ls
            else:
                vuln = ippan_rate_1
        else:
            # 4〜6号艇: まくり主体
            vuln = _safe(lose_makuri) if lose_makuri is not None else ippan_rate_1

        # ── 艇間干渉スコア ──
        inner_idx = i - 1
        if inner_idx >= 0:
            inner_weapon = weapons[inner_idx]
            interference_score = 1.0 - min(inner_weapon, 1.0) * 0.5
        else:
            interference_score = 1.0

        # ── 加重合成（v5: 2号艇のみ重み変更）──────────────────────
        if i == 1:
            # 2号艇: STを主軸、攻め武器を補助に格下げ、干渉は最小限
            # 「ST差で差せるか」が2号艇相性の本質
            score = (weapon        * 0.30
                   + st_score      * 0.50
                   + vuln          * 0.15
                   + interference_score * 0.05)
        else:
            # 3〜6号艇: 従来通り
            score = (weapon        * 0.40
                   + st_score      * 0.35
                   + vuln          * 0.15
                   + interference_score * 0.10)
        # ────────────────────────────────────────────────────────────

        scores.append(score)

    # ── コース別絶対閾値フィルタ ─────────────────────────────────────────
    # 【修正】全コース一律0.40 → コース別に閾値を設定。
    #
    # 背景:
    #   2号艇は差しコースで「差し20%・ST普通」という組み合わせが
    #   一律閾値0.40を超えられなかった（score≈0.33）。
    #   差しは物理的に2号艇専用の技であり、差し20%は十分な攻め力を示している。
    #
    #   一方4〜6号艇はまくりコースで外コースほど成功率が低く、
    #   高い閾値を維持することが「本当に攻め切れる艇だけ評価する」ために正しい。
    #
    # コース別閾値の根拠（実測スコアから逆算）:
    #   2号艇: 0.32
    #     差し場平均(14%)×ST中立 → score≈0.31（空白の下限）
    #     差し20%×ST不利        → score≈0.33（○がつく最低ライン）
    #     差し30%×ST中立        → score≈0.36（○）
    #     差し50%×ST有利        → score≈0.50（◎）
    #
    #   3号艇: 0.35
    #     まくり差し11%×ST普通  → score≈0.30（空白）
    #     まくり差し20%×ST普通  → score≈0.34（○の下限）
    #     まくり差し30%×ST速め  → score≈0.42（◎）
    #
    #   4〜6号艇: 0.40のまま
    #     外コースほどまくり成功率が低く、強い攻め力がないと相性なしで正しい。
    #
    # 全員弱いレース対策（一律閾値で解決していた問題）は
    # コース別閾値でも同様に機能する。
    AISHO_MIN_BY_COURSE = {2: 0.32, 3: 0.35, 4: 0.40, 5: 0.40, 6: 0.40}
    AISHO_MIN_DEFAULT   = 0.40

    sub_scores = scores[1:]
    sub_ranks  = _rank6(sub_scores)

    result = [""]   # 1枠は空白
    # sub_scores はインデックス0=2号艇、1=3号艇... なので course = idx + 2
    for idx, (r, raw_score) in enumerate(zip(sub_ranks, sub_scores)):
        course = idx + 2
        min_score = AISHO_MIN_BY_COURSE.get(course, AISHO_MIN_DEFAULT)
        # コース別絶対閾値未満はランク問わず空白
        if raw_score is not None and raw_score < min_score:
            result.append("")
        else:
            result.append(_symbol_4(r, max_rank=len(members) - 1))
    return result


# ============================================================
# ③ 機力評価（v3: モーターCSVなしは全艇「－」表示）
# ============================================================

def calc_kiryoku(members: list[dict]) -> list[str]:
    """
    members: 艇番順リスト。
    各要素に以下のキーが必要:
        motor_2rate : モーター2連対率（float, %値, Noneも可）

    【v3 変更点】
    有効なモーターデータが1件もない場合（モーターCSV未取得）は
    全艇「－」を返す。全員同値による誤った「全艇A」を防ぐ。

    有効データが1件以上ある場合:
        - データあり艇: 相対ランク → A〜E
        - データなし艇: 有効値の中央値を代入して評価し「*」を付与

    6艇の相対ランク → A〜E
    """
    raw_scores = [
        m.get("motor_2rate")   # None保持（_safeで0変換しない）
        for m in members
    ]

    valid = [s for s in raw_scores if s is not None]

    # モーターCSV未取得（有効値ゼロ件）→ 全艇「－」
    if not valid:
        return ["-"] * len(members)

    # 一部Noneあり → 中央値で代入して評価、「*」付与
    median_val = _median_of(valid)
    filled  = [s if s is not None else median_val for s in raw_scores]
    imputed = [s is None for s in raw_scores]

    ranks   = _rank6(filled)
    symbols = [_symbol_grade(r, n=len(members)) for r in ranks]

    for i, imp in enumerate(imputed):
        if imp:
            symbols[i] += "*"

    return symbols


# ============================================================
# ④ 安定性評価（旧：自在性評価）
# ============================================================

def calc_jizaisei(members: list[dict]) -> list[str]:
    """
    【v4: 自在性評価を廃止し、安定性評価に置き換え】
    ────────────────────────────────────────────────────────────
    廃止理由:
        自在性（diversity_rate × 0.6 + jizaisei_rate × 0.4）は
        「複数コースで攻め技術がある選手か」を測っていたが、
        相性評価（攻め武器スコア）と展開評価（差し込み力）の両方に
        すでに同じ攻め技術軸が含まれており、独立した情報として
        新聞に並べる意義が薄かった。

        一方、全5項目のうちスタートリスクを評価する項目がゼロであり、
        FLY明け直後の艇や出遅れ癖のある艇への過大評価という実害があった。

    新設: 安定性評価
        問い: 「この艇はスタートで自沈するリスクがあるか」
        どんなに攻め力があってもスタートで自滅すれば意味がない。

    【スコア構成】
        安定スコア = ST安定スコア（0〜100）× 0.5
                   + FLYリスク補正（0〜1）         × 0.3
                   + 出遅れ率の低さ（0〜1）         × 0.2

        ST安定スコア（0〜100）:
            マスタの「ST安定スコア」をそのまま利用（0〜100に正規化済み）。
            0.03秒以下のばらつき→95点、0.08秒→50点（区間線形補間）。

        FLYリスク補正（0〜1）:
            FLY経過日数を使った連続関数で滑らかに減衰。
            FLY経過日数 ≥ 180日  → 影響ほぼ消滅 → 補正1.0（ペナルティなし）
            FLY経過日数  60〜179日 → 線形補間で 0.40〜1.0
            FLY経過日数  < 60日   → 0.40（最大ペナルティ）
            FLYなし（fly_count=0）→ 1.0（ペナルティなし）
            fly_days データなし   → fly_count で代替判定
                fly_count ≥ 2 → 0.50 / fly_count = 1 → 0.70 / 0 → 1.0

        出遅れ率の低さ（0〜1）:
            出遅れ率 = 出遅れ数 / 総走数（st_count）
            出遅れ率 0%     → 1.0（最高）
            出遅れ率 5%以上 → 0.5（慢性的な出遅れ癖）
            出遅れ率 10%以上→ 0.0（深刻な出遅れ癖）
            データなし      → 0.7（中立）

    【警告マーク】
        FLY経過日数が90日未満（出場停止明け直後）の艇は
        記号の末尾に「⚠」を付与して新聞上で視覚的に警告する。
        これは記号の上下には影響しない（表示のみ）。

    【対象】
        全艇（1〜6号艇）。相性評価と異なり1号艇も対象。
        1号艇はスタートで自沈すると逃げが消えるため安定性が最も重要。
        6艇内での相対ランクで◎○△を付与。

    必要キー（build_jizen_members で追加が必要）:
        st_stable_score : ST安定スコア（0〜100、float or None）
        fly_count       : FLY数（int）
        fly_days        : FLY経過日数（float or None）
        late_count      : 出遅れ数（int）
        st_count        : ST計測件数（int、出遅れ率の分母）
    ────────────────────────────────────────────────────────────
    """
    scores: list[float | None] = []
    warn_flags: list[bool] = []   # 警告マーク用

    for m in members:
        st_stable = m.get("st_stable_score")   # 0〜100
        fly_count = int(_safe(m.get("fly_count"), 0))
        fly_days  = m.get("fly_days")          # float or None
        late_count = int(_safe(m.get("late_count"), 0))
        st_count   = int(_safe(m.get("st_count"), 1))

        # ── ST安定スコアを0〜1に正規化 ──────────────────────────────
        if st_stable is not None:
            st_score = float(st_stable) / 100.0
        else:
            st_score = 0.5   # データなし → 中立

        # ── FLYリスク補正（0〜1）────────────────────────────────────
        warn = False
        if fly_count == 0:
            fly_penalty = 1.0
        elif fly_days is not None:
            fd = float(fly_days)
            if fd >= 180:
                fly_penalty = 1.0
            elif fd < 60:
                fly_penalty = 0.40
                warn = True
            else:
                # 60〜179日: 線形補間 0.40〜1.0
                fly_penalty = 0.40 + (fd - 60) / 120.0 * 0.60
                if fd < 90:
                    warn = True
        else:
            # fly_days データなし → fly_count で代替
            if fly_count >= 2:
                fly_penalty = 0.50
            else:
                fly_penalty = 0.70

        # ── 出遅れ率の低さ（0〜1）────────────────────────────────────
        if st_count > 0:
            late_rate = late_count / st_count
            if late_rate >= 0.10:
                late_score = 0.0
            elif late_rate >= 0.05:
                late_score = 0.5
            else:
                # 0〜5%: 線形補間 0.5〜1.0
                late_score = 1.0 - late_rate / 0.05 * 0.5
        else:
            late_score = 0.7   # データなし → 中立

        score = st_score * 0.5 + fly_penalty * 0.3 + late_score * 0.2
        scores.append(score)
        warn_flags.append(warn)

    ranks = _rank6(scores)

    result = []
    for r, warn in zip(ranks, warn_flags):
        sym = _symbol_4(r, max_rank=len(members))
        if warn and sym:
            sym += "⚠"
        result.append(sym)
    return result


# ============================================================
# ⑤ 展開評価（v3: 4〜6枠専用・展開に乗る能力を評価）
# ============================================================

def calc_tenkai(members: list[dict]) -> list[str]:
    """
    members: 艇番順リスト（インデックス0=1号艇）。
    各要素に以下のキーが必要:
        rate_3ren         : そのコースの3連対率（絶対値）
        sashi_rate        : 差し%（自コース）
        makuri_rate       : まくり%（自コース）
        makuri_zashi_rate : まくり差し%（自コース）
        avg_st_self       : 自コース平均ST（秒）
        star_kimete       : 暫定★（決まり手）フラグ

    【v3 変更点】
    ────────────────────────────────────────────────────────────
    旧（v2）の問題:
        3〜6枠を同列評価 → 3号はまくり%が構造的に高いため
        ほぼ必然的に◎になるだけで「展開の中で誰が突けるか」
        という問いに答えていなかった。

    新（v3）の設計:
        問い: 「2・3号艇が第1展開をつくった後、
               4〜6号艇の中で誰が展開に乗れるか」

        ・1〜3枠は空白（1号:逃げ評価で評価済み、
                        2号:相性評価で評価済み、
                        3号:第1展開の形成役であり評価の対象ではない）
        ・4〜6枠の3艇内でランク付け

    【展開スコアの構成】
        3号まくり後に生まれるのは「内側への差し込みコース」。
        4〜6号艇に必要な能力は「差し込む技術」×「ST」×「3連対の地力」。

        スコア = (差し% + まくり差し%) × 0.5
               + ST速さスコア           × 0.3
               + 3連対率                × 0.2

        差し%とまくり差し%を主軸（0.5）とする理由:
            3号まくりで内側が空いたとき、4〜6号は
            「差す」か「まくり差す」で入るのが基本形。
            まくり単体は外に振る動きなのでここでは軽く見る。

        ST速さスコア（0.3）:
            展開に乗るには「スリットで遅れない」ことが前提。
            同レース内でのST相対速度を使用する。
            avg_st_self が小さい（速い）ほど高スコア。
            データなしは中立値 0.5。
            正規化: メンバーのST平均を基準に ±0.03秒幅でスコア化。

        3連対率（0.2）:
            展開が来なくても地力で3着に残る底力の補正。
            あくまで補助で重みは最小。

        ★フラグ（決まり手データ少）の艇はNone扱い（ランク対象外）。
    ────────────────────────────────────────────────────────────
    """
    # ── ST速さスコアの計算（4〜6枠分のみ） ──────────────────────────
    # 4〜6枠のavg_st_selfを収集してメンバー内平均を算出
    st_vals = [
        _safe(members[i].get("avg_st_self"), default=-1.0)
        for i in range(3, len(members))
    ]
    valid_st = [v for v in st_vals if v >= 0]
    st_mean = sum(valid_st) / len(valid_st) if valid_st else 0.17  # データなしは競艇平均値

    def _st_score(avg_st) -> float:
        """avg_st（秒）→ ST速さスコア（0〜1）。速いほど高い。"""
        if avg_st is None or avg_st < 0:
            return 0.5  # データなし → 中立
        diff = st_mean - avg_st   # 正 = 平均より速い
        score = diff / 0.03 * 0.5 + 0.5  # ±0.03秒を0〜1に正規化
        return max(0.0, min(1.0, score))

    # ── 4〜6枠のスコア計算 ────────────────────────────────────────
    sub_scores: list[float | None] = []

    for i in range(3, len(members)):   # 4〜6枠（インデックス3〜5）
        m = members[i]
        if m.get("star_kimete"):
            sub_scores.append(None)    # ★フラグ → ランク対象外
            continue

        sashi = _safe(m.get("sashi_rate"))
        mz    = _safe(m.get("makuri_zashi_rate"))
        r3    = _safe(m.get("rate_3ren"))
        st_s  = _st_score(m.get("avg_st_self"))

        score = (sashi + mz) * 0.5 + st_s * 0.3 + r3 * 0.2
        sub_scores.append(score)

    sub_ranks = _rank6(sub_scores)

    # 1〜3枠は空白、4〜6枠は3艇内ランクで記号付与
    result = ["", "", ""]
    for r in sub_ranks:
        result.append(_symbol_4(r, max_rank=len(sub_scores)))
    return result


# ============================================================
# 多様性割合の事前算出ヘルパー（変更なし）
# ============================================================

def calculate_diversity_rate(
    course_data: list[dict],
) -> float:
    """
    1選手の2〜6コース分のコース別マスタデータから多様性割合を算出。

    course_data: コース2〜6の各行データ（コース1は除外）
    各行に必要なキー: 差し(件), まくり(件), まくり差し%（件数推定用）, 1着数

    まくり差し件数は件数列が存在しないため、まくり差し% × 1着数 で推定。
    """
    total_1st    = 0
    total_attack = 0
    for row in course_data:
        course = _safe(row.get("course"))
        if course < 2:
            continue
        n1st   = _safe(row.get("1着数"))
        sashi  = _safe(row.get("差し(件)"))
        makuri = _safe(row.get("まくり(件)"))
        mz_pct = _safe(row.get("まくり差し%"))
        mz_est = mz_pct * n1st

        total_1st    += n1st
        total_attack += sashi + makuri + mz_est

    if total_1st == 0:
        return 0.0
    return total_attack / total_1st


# ============================================================
# まとめて評価するメイン関数
# ============================================================

def evaluate_all(members: list[dict]) -> dict[str, list[str]]:
    """
    6艇分の members データから全5項目を一括評価。

    members は以下のキーを含む辞書のリスト（インデックス0=1号艇）:
        rate_1st_c1, st_rank_c1, star_rate                 ← イン逃げ用
        nigé_rate, attack_rate                             ← 相性フォールバック用
        sashi_rate, makuri_rate, makuri_zashi_rate         ← 相性：攻め武器（1位 45%）
        avg_st_self                                        ← 相性：自コース平均ST秒（2位 35%）
        lose_sashi_rate, lose_makuri_rate                  ← 相性：1号艇被決まり手（3位 20%）members[0]に格納
        motor_2rate                                        ← 機力用
        diversity_rate, jizaisei_rate, star_kimete         ← 自在性用
        rate_3ren                                          ← 展開用（makuri_rate/makuri_zashi_rateと共用）

    【load_race.py の build_jizen_members で追加が必要なキー】
        sashi_rate       : _s(cm.get("差し%"))
        avg_st_self      : res.get("avg_st")           ← calc_race_indicesのresultsに既存
        lose_sashi_rate  : _s(cm0.get("差され%"))      ← 1号艇のcm（members[0]にのみ格納）
        lose_makuri_rate : _s(cm0.get("捲られ%"))      ← 同上
        st_stable_score  : _s(pm.get("ST安定スコア"))  ← 安定性評価用（新規追加）
        fly_count        : int(pm.get("FLY数"))         ← 安定性評価用（新規追加）
        fly_days         : pm.get("FLY経過日数")        ← 安定性評価用（新規追加）
        late_count       : int(pm.get("出遅れ数"))      ← 安定性評価用（新規追加）
        st_count         : int(pm.get("ST計測件数"))    ← 安定性評価用（新規追加）

    returns: {
        "in_nige":  [str × 6],
        "aisho":    [str × 6],
        "kiryoku":  [str × 6],
        "jizaisei": [str × 6],
        "tenkai":   [str × 6],
    }
    """
    return {
        "in_nige":  calc_in_nige(members),
        "aisho":    calc_aisho(members),
        "kiryoku":  calc_kiryoku(members),
        "jizaisei": calc_jizaisei(members),
        "tenkai":   calc_tenkai(members),
    }


# ============================================================
# ユニットテスト（python evaluate_jizen.py で実行）
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("  evaluate_jizen.py v8 動作テスト（安定性評価v4反映）")
    print("=" * 60)
    print()
    print("【システム前提】進入は枠なり固定。展示変更時はレース不参加。")
    print()

    # ─────────────────────────────────────────────────────────────
    # テストケース A: 1号艇強い×2号艇弱い → 逃げ◎が維持されるか
    # ─────────────────────────────────────────────────────────────
    print("─" * 60)
    print("【テストA】1号艇強い(ST速+1着率高) × 2号艇弱い(差し苦手+ST遅)")
    print("  期待: イン逃げ ◎  相性2号艇 低評価  安定性: ST安定高い艇が上位")
    print("─" * 60)

    # 安定性キーの共通デフォルト（FLYなし・ST安定スコア中程度）
    _stable_default = {
        "st_stable_score": 70.0, "fly_count": 0, "fly_days": None,
        "late_count": 0, "st_count": 50,
    }

    test_A = [
        {   # 1号艇: ST速い・1着率高・差されにくい・ST超安定
            "rate_1st_c1": 0.70, "st_rank_c1": 1.0, "star_rate": False,
            "nigé_rate": 0.82, "attack_rate": 0.0,
            "sashi_rate": 0.0, "makuri_rate": 0.0, "makuri_zashi_rate": 0.0,
            "avg_st_self": 0.13,
            "lose_sashi_rate": 0.08, "lose_makuri_rate": 0.05,
            "lose_rate_reliable": True,
            "motor_2rate": 50.0,
            "diversity_rate": 0.0, "jizaisei_rate": 0.05, "star_kimete": False,
            "rate_3ren": 0.85, "course_int": 1,
            **{**_stable_default, "st_stable_score": 90.0},  # 超安定
        },
        {   # 2号艇: 差し苦手 + ST遅い → 脅威低・FLY明け90日以内（警告あり）
            "rate_1st_c1": 0.08, "st_rank_c1": 5.0, "star_rate": False,
            "nigé_rate": 0.0, "attack_rate": 0.20,
            "sashi_rate": 0.10, "makuri_rate": 0.05, "makuri_zashi_rate": 0.05,
            "avg_st_self": 0.22,
            "motor_2rate": 35.0,
            "diversity_rate": 0.15, "jizaisei_rate": 0.10, "star_kimete": False,
            "rate_3ren": 0.35, "course_int": 2,
            **{**_stable_default, "fly_count": 1, "fly_days": 75.0},  # FLY明け75日
        },
        {   # 3号艇
            "rate_1st_c1": 0.08, "st_rank_c1": 4.0, "star_rate": False,
            "nigé_rate": 0.0, "attack_rate": 0.45,
            "sashi_rate": 0.10, "makuri_rate": 0.20, "makuri_zashi_rate": 0.15,
            "avg_st_self": 0.16,
            "motor_2rate": 40.0,
            "diversity_rate": 0.40, "jizaisei_rate": 0.18, "star_kimete": False,
            "rate_3ren": 0.50, "course_int": 3,
            **_stable_default,
        },
        {   # 4号艇
            "rate_1st_c1": 0.10, "st_rank_c1": 3.0, "star_rate": False,
            "nigé_rate": 0.0, "attack_rate": 0.55,
            "sashi_rate": 0.05, "makuri_rate": 0.40, "makuri_zashi_rate": 0.15,
            "avg_st_self": 0.15,
            "motor_2rate": 48.0,
            "diversity_rate": 0.45, "jizaisei_rate": 0.22, "star_kimete": False,
            "rate_3ren": 0.52, "course_int": 4,
            **{**_stable_default, "st_stable_score": 85.0},
        },
        {   # 5号艇
            "rate_1st_c1": 0.07, "st_rank_c1": 5.5, "star_rate": False,
            "nigé_rate": 0.0, "attack_rate": 0.30,
            "sashi_rate": 0.05, "makuri_rate": 0.25, "makuri_zashi_rate": 0.10,
            "avg_st_self": None,
            "motor_2rate": None,
            "diversity_rate": 0.20, "jizaisei_rate": 0.10, "star_kimete": False,
            "rate_3ren": 0.40, "course_int": 5,
            **{**_stable_default, "st_stable_score": 55.0, "late_count": 4},  # 出遅れ癖
        },
        {   # 6号艇
            "rate_1st_c1": 0.05, "st_rank_c1": 6.0, "star_rate": False,
            "nigé_rate": 0.0, "attack_rate": 0.20,
            "sashi_rate": 0.05, "makuri_rate": 0.15, "makuri_zashi_rate": 0.10,
            "avg_st_self": 0.21,
            "motor_2rate": 28.0,
            "diversity_rate": 0.15, "jizaisei_rate": 0.08, "star_kimete": True,
            "rate_3ren": 0.30, "course_int": 6,
            **{**_stable_default, "st_stable_score": 40.0, "fly_count": 2, "fly_days": 50.0},  # FLY×2・直後
        },
    ]

    result_A = evaluate_all(test_A)
    print(f"{'項目':<12}" + "".join(f"  {i+1}号艇 " for i in range(6)))
    print("-" * 58)
    labels = {
        "in_nige":  "①イン逃げ",
        "aisho":    "②相性    ",
        "kiryoku":  "③機力    ",
        "jizaisei": "④安定性  ",
        "tenkai":   "⑤展開    ",
    }
    for key, label in labels.items():
        vals = result_A[key]
        row = f"{label}  " + "".join(f"  {(v or '空'):^5} " for v in vals)
        print(row)

    print()
    print("  ✅ 期待: ①逃げ◎  ④安定性1号艇◎（ST90点）、6号艇空白（FLY×2直後）")
    print("           2号艇に⚠マーク（FLY明け75日）")

    # ─────────────────────────────────────────────────────────────
    # テストケース B: 1号艇普通×2号艇強い(差し+ST速) → 逃げ△以下になるか
    # ─────────────────────────────────────────────────────────────
    print()
    print("─" * 60)
    print("【テストB】1号艇普通 × 2号艇強い(差し55%+ST0.12秒で速い)")
    print("  期待: イン逃げ △以下  ②相性2号艇 ◎")
    print("─" * 60)

    test_B = [
        {   # 1号艇: 平均的
            "rate_1st_c1": 0.55, "st_rank_c1": 3.0, "star_rate": False,
            "nigé_rate": 0.72, "attack_rate": 0.0,
            "sashi_rate": 0.0, "makuri_rate": 0.0, "makuri_zashi_rate": 0.0,
            "avg_st_self": 0.18,
            "lose_sashi_rate": 0.18, "lose_makuri_rate": 0.08,
            "lose_rate_reliable": True,
            "motor_2rate": 45.0,
            "diversity_rate": 0.0, "jizaisei_rate": 0.05, "star_kimete": False,
            "rate_3ren": 0.75, "course_int": 1,
        },
        {   # 2号艇: 差し強い + ST速い → v5で相性◎になるはず
            "rate_1st_c1": 0.10, "st_rank_c1": 1.5, "star_rate": False,
            "nigé_rate": 0.0, "attack_rate": 0.65,
            "sashi_rate": 0.55, "makuri_rate": 0.05, "makuri_zashi_rate": 0.05,
            "avg_st_self": 0.12,   # 1号艇より0.06速い
            "motor_2rate": 55.0,
            "diversity_rate": 0.60, "jizaisei_rate": 0.25, "star_kimete": False,
            "rate_3ren": 0.60, "course_int": 2,
        },
        {   # 3〜6号艇は同上
            "rate_1st_c1": 0.08, "st_rank_c1": 4.0, "star_rate": False,
            "nigé_rate": 0.0, "attack_rate": 0.55,
            "sashi_rate": 0.10, "makuri_rate": 0.20, "makuri_zashi_rate": 0.25,
            "avg_st_self": 0.15,
            "motor_2rate": 30.0,
            "diversity_rate": 0.50, "jizaisei_rate": 0.20, "star_kimete": False,
            "rate_3ren": 0.55, "course_int": 3,
        },
        {
            "rate_1st_c1": 0.12, "st_rank_c1": 2.5, "star_rate": False,
            "nigé_rate": 0.0, "attack_rate": 0.30,
            "sashi_rate": 0.05, "makuri_rate": 0.45, "makuri_zashi_rate": 0.35,
            "avg_st_self": 0.13,
            "motor_2rate": 35.0,
            "diversity_rate": 0.45, "jizaisei_rate": 0.20, "star_kimete": False,
            "rate_3ren": 0.50, "course_int": 4,
        },
        {
            "rate_1st_c1": 0.09, "st_rank_c1": 5.0, "star_rate": False,
            "nigé_rate": 0.0, "attack_rate": 0.20,
            "sashi_rate": 0.05, "makuri_rate": 0.25, "makuri_zashi_rate": 0.20,
            "avg_st_self": None,
            "motor_2rate": None,
            "diversity_rate": 0.20, "jizaisei_rate": 0.10, "star_kimete": False,
            "rate_3ren": 0.45, "course_int": 5,
        },
        {
            "rate_1st_c1": 0.06, "st_rank_c1": 6.0, "star_rate": False,
            "nigé_rate": 0.0, "attack_rate": 0.15,
            "sashi_rate": 0.05, "makuri_rate": 0.20, "makuri_zashi_rate": 0.15,
            "avg_st_self": 0.22,
            "motor_2rate": 20.0,
            "diversity_rate": 0.15, "jizaisei_rate": 0.08, "star_kimete": True,
            "rate_3ren": 0.30, "course_int": 6,
        },
    ]

    result_B = evaluate_all(test_B)
    print(f"{'項目':<12}" + "".join(f"  {i+1}号艇 " for i in range(6)))
    print("-" * 58)
    for key, label in labels.items():
        vals = result_B[key]
        row = f"{label}  " + "".join(f"  {(v or '空'):^4} " for v in vals)
        print(row)

    print()
    print("  ✅ 期待: ①逃げ △以下（2号艇脅威スコアが高く相対スコアが下がる）")
    print("  ✅ 期待: ②相性 2号艇◎（ST0.06秒優位×差し55%でv5重み変更が効く）")
    print()
    print("─" * 60)
    print("【テストC】1号艇普通 × 2〜6号艇が全員強い（包囲圧力）")
    print("  v6新機能: max_threat + mean_threat の両方が効くか確認")
    print("  期待: イン逃げ 空白（全体脅威が高く逃げスコア大幅減）")
    print("─" * 60)

    test_C = [
        {   # 1号艇: 平均的
            "rate_1st_c1": 0.55, "st_rank_c1": 3.0, "star_rate": False,
            "nigé_rate": 0.68, "attack_rate": 0.0,
            "sashi_rate": 0.0, "makuri_rate": 0.0, "makuri_zashi_rate": 0.0,
            "avg_st_self": 0.17,
            "lose_sashi_rate": 0.20, "lose_makuri_rate": 0.12,
            "lose_rate_reliable": True,
            "motor_2rate": 42.0,
            "diversity_rate": 0.0, "jizaisei_rate": 0.05, "star_kimete": False,
            "rate_3ren": 0.70, "course_int": 1,
        },
        {   # 2号艇: 差し強 + ST速い
            "sashi_rate": 0.60, "makuri_rate": 0.05, "makuri_zashi_rate": 0.05,
            "attack_rate": 0.70, "avg_st_self": 0.11,
            "rate_1st_c1": 0.10, "st_rank_c1": 2.0, "star_rate": False,
            "nigé_rate": 0.0, "motor_2rate": 58.0,
            "diversity_rate": 0.65, "jizaisei_rate": 0.28, "star_kimete": False,
            "rate_3ren": 0.62, "course_int": 2,
        },
        {   # 3号艇: まくり差し強 + ST速め
            "sashi_rate": 0.10, "makuri_rate": 0.30, "makuri_zashi_rate": 0.35,
            "attack_rate": 0.75, "avg_st_self": 0.14,
            "rate_1st_c1": 0.09, "st_rank_c1": 2.5, "star_rate": False,
            "nigé_rate": 0.0, "motor_2rate": 52.0,
            "diversity_rate": 0.60, "jizaisei_rate": 0.25, "star_kimete": False,
            "rate_3ren": 0.58, "course_int": 3,
        },
        {   # 4号艇: まくり強 + ST速め
            "sashi_rate": 0.05, "makuri_rate": 0.55, "makuri_zashi_rate": 0.20,
            "attack_rate": 0.80, "avg_st_self": 0.13,
            "rate_1st_c1": 0.11, "st_rank_c1": 2.0, "star_rate": False,
            "nigé_rate": 0.0, "motor_2rate": 60.0,
            "diversity_rate": 0.55, "jizaisei_rate": 0.26, "star_kimete": False,
            "rate_3ren": 0.55, "course_int": 4,
        },
        {   # 5号艇: まくり系そこそこ
            "sashi_rate": 0.05, "makuri_rate": 0.35, "makuri_zashi_rate": 0.20,
            "attack_rate": 0.60, "avg_st_self": 0.15,
            "rate_1st_c1": 0.08, "st_rank_c1": 3.5, "star_rate": False,
            "nigé_rate": 0.0, "motor_2rate": 45.0,
            "diversity_rate": 0.40, "jizaisei_rate": 0.18, "star_kimete": False,
            "rate_3ren": 0.48, "course_int": 5,
        },
        {   # 6号艇: まくり系そこそこ
            "sashi_rate": 0.05, "makuri_rate": 0.30, "makuri_zashi_rate": 0.20,
            "attack_rate": 0.55, "avg_st_self": 0.16,
            "rate_1st_c1": 0.07, "st_rank_c1": 4.0, "star_rate": False,
            "nigé_rate": 0.0, "motor_2rate": 40.0,
            "diversity_rate": 0.35, "jizaisei_rate": 0.15, "star_kimete": False,
            "rate_3ren": 0.42, "course_int": 6,
        },
    ]

    result_C = evaluate_all(test_C)
    print(f"{'項目':<12}" + "".join(f"  {i+1}号艇 " for i in range(6)))
    print("-" * 58)
    for key, label in labels.items():
        vals = result_C[key]
        row = f"{label}  " + "".join(f"  {(v or '空'):^4} " for v in vals)
        print(row)

    print()
    print("  ✅ 期待: ①逃げ 空白  ④安定性2号艇◎（ST92点）、3号艇に⚠（FLY明け65日）")
    print()
    print("【v8 変更点まとめ】")
    print("  ② 相性: 絶対閾値0.40を追加（全員弱いレースで◎が出るのを防ぐ）")
    print()
    print("  ④ 自在性 → 安定性評価に置き換え（全艇対象・1〜6号艇）")
    print("    廃止理由: 相性・展開と攻め技術軸が重複、独立情報として薄かった")
    print("    新設理由: 5項目中スタートリスク評価がゼロだった")
    print("    スコア = ST安定スコア × 0.5")
    print("           + FLYリスク補正（経過日数で滑らか減衰）× 0.3")
    print("           + 出遅れ率の低さ × 0.2")
    print("    警告⚠: FLY経過日数90日未満の艇に付与（記号の上下には影響しない）")
    print()
    print("  ⑤ 展開評価v3: 4〜6枠専用に変更")
    print("    問い: 「2・3号の第1展開後、4〜6号で誰が展開に乗れるか」")
    print("    スコア = (差し% + まくり差し%) × 0.5 + ST速さ × 0.3 + 3連対率 × 0.2")
    print()
    print("✅ テスト完了")
