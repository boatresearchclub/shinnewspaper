"""
競艇 買い目点数最適化ロジック  v6.0
的中率改善軸 再設計 ── "長期的に安定して利益を積み上げる"

【v6.0 設計思想】
  最優先目標: 長期安定利益の積み上げ
    - 的中重視モード（HIT）: 的中率 ≥ 44%（現実的上限）、回収率 ≥ 200%
    - 回収重視モード（REC）: 的中率 ≥ 36%、回収率 ≥ 200%
    - 参加数を大幅に絞り「当たりやすい構造」を優先
    - 資金曲線の平滑化・メンタルブレ抑制

  ■ v6.0 コア設計原則（v5.0からの根本変更）

  ◆ 原則1【参加条件の大幅絞り込み】
    HIT モード参加条件（全て満たす場合のみ参加）:
      ① パターン: SSプレミアム他艇 または SS1号艇 のみ
      ② 会場: 優良6会場限定（唐津・住之江・尼崎・桐生・びわこ・浜名湖）
      ③ あれ指数: 40〜50 の安定ゾーン（50超は原則スキップ）
      ④ 高配当1号艇: 全スキップ（HITモード）
      ⑤ 買い目: 5点以上固定
    → シミュレーション期待: 的中率44〜47%、回収率200%超

  ◆ 原則2【SS条件の再定義】
    v5.0: SS = base 0.45〜0.55（固定幅）
    v6.0: SS = base 0.43〜0.57（±0.02拡張）かつ are_index 40〜50 安定ゾーン
    根拠: あれ指数が安定している場合、base幅を少し広げて的中機会を増やす

  ◆ 原則3【HITモード 優良会場限定】
    v5.0: full会場は全て参加
    v6.0 HIT: 優良6会場（唐津・住之江・尼崎・桐生・びわこ・浜名湖）のみ
         REC: 従来のfull会場群（スキップ会場除く）
    根拠: 会場絞り込みで的中率の分母質を向上

  ◆ 原則4【あれ指数 50超スキップ（HITモード）】
    v5.0: あれ>55でSS他艇スキップ（HIT）
    v6.0: あれ>50でSSを含む全パターンスキップ（HIT）
          あれ40〜45を「安定ゾーン」として最優先
    根拠: あれ指数50超は荒れリスクが高く的中率が下落

  ◆ 原則5【高配当1号艇 HITモード全スキップ】
    v5.0: base≥0.60 & あれ46〜48 のみ参加（HIT）
    v6.0: HITモードは全スキップ
          RECモード: base≥0.60 & あれ43〜47（v5.0より少し広げる）
    根拠: シミュレーションで305件・的中率36.1%・回収率203%を確認

  ◆ 原則6【買い目点数の下限保証】
    HITモード参加レース: 最低5点を保証（5点未満になる場合は5点に切り上げ）
    根拠: 的中率向上には適切な買い目幅が必要

  ◆ 原則7【中立他艇の扱い変更】
    HIT: 完全スキップ（的中率向上のため分母削減）
    REC: HITモード優良条件＋中立他艇を追加参加

  ■ v5.0からの継承
    - SSプレミアム他艇（SS × あれ45〜48: 最優先）
    - tenji係数キャップ（減点専用）
    - まくりアラート閾値 are>=48
    - 低配当罠フィルター（期待払戻<1200円）
    - VENUE_RULE スキップ会場（宮島・大村・多摩川・鳴門）
    - プレミアムゾーン追跡ログ

【バックテスト目標（v6.0）】
  HIT: 参加数↓↓（優良会場×安定あれ指数×SS限定）、的中率 44〜47%、回収率 ≥ 200%
  REC: 参加数305件前後、的中率 ≥ 36%、回収率 ≥ 200%
"""

import pandas as pd
from dataclasses import dataclass, field
from typing import Optional
from datetime import date, timedelta


# ============================================================
# 定数
# ============================================================

VENUE_RULE = {
    # ── v6.0: HITモード優良会場（最高パフォーマンス6会場）────────
    "唐津":   "hit_priority",   # HIT優良会場
    "住之江": "hit_priority",
    "尼崎":   "hit_priority",
    "桐生":   "hit_priority",
    "びわこ": "hit_priority",
    "浜名湖": "hit_priority",

    # ── full（RECモードのみ追加参加）─────────────────────────────
    "戸田":   "full", "江戸川": "full",
    "平和島": "full",
    "蒲郡":   "full", "常滑":   "full", "津":     "full",
    "三国":   "full",
    "児島":   "full",
    "徳山":   "full", "下関":   "full", "若松":   "full",
    "芦屋":   "full",

    # ── 特殊ルール会場 ─────────────────────────────────────────
    "福岡":   "fukuoka",
    "丸亀":   "marugame",

    # ── v4.2継承: 期待値低下会場は完全除外 ────────────────────
    "宮島":   "skip",
    "大村":   "skip",
    "多摩川": "skip",
    "鳴門":   "skip",
}

# HITモードで参加する会場セット
HIT_ALLOWED_VENUES = {v for v, rule in VENUE_RULE.items() if rule == "hit_priority"}

# 福岡専用
FUKUOKA_HIGH_POP_BASE    = 0.55
FUKUOKA_HIGH_POP_POINTS  = 4
FUKUOKA_HIGH_POP_STRICT  = 3

# 丸亀専用
MARUGAME_MAKURI_MAX_POINTS = 5

# limitedモードで許可するパターン
LIMITED_ALLOWED_PATTERNS = {
    "スイートスポット1号艇", "スイートスポット他艇",
    "高配当1号艇", "高配当他艇",
    "SSプレミアム他艇",
}

# ============================================================
# v6.0 パラメータ
# ============================================================
PARAMS = {

    # ── ★v6.0: SS条件の拡張定義 ─────────────────────────────────
    # v5.0: base 0.45〜0.55（固定）
    # v6.0: base 0.43〜0.57（±0.02拡張）& are 40〜50 安定ゾーン
    "sweet_base_min":             0.43,   # v6.0: 0.45→0.43に拡張
    "sweet_base_max":             0.57,   # v6.0: 0.55→0.57に拡張
    "sweet_tenkai_max":           1.05,
    "sweet_max_points":           10,
    "sweet_are_boost_threshold":  50.0,   # HIT時はここに達したらスキップ
    "sweet_are_boost_points":     2,
    "sweet_hit_are_max":          50.0,   # v6.0: 55→50 に厳格化（HIT）
    "sweet_low_tenkai_threshold": 1.00,
    "sweet_low_tenkai_points":    5,

    # ── ★v6.0: あれ指数 安定ゾーン設計 ─────────────────────────
    # HIT: 40〜50のみ参加（50超スキップ）
    # あれ40〜45: 最安定ゾーン（優先度最高）
    # あれ45〜50: 安定ゾーン（通常参加）
    # あれ50超: HITスキップ / RECは45〜50相当として処理
    "are_hit_max":                50.0,   # HIT参加上限
    "are_stable_min":             40.0,   # 安定ゾーン下限
    "are_stable_top":             45.0,   # 最安定ゾーン上限
    "are_stable_max":             50.0,   # 安定ゾーン上限

    # ── ★v6.0: SSプレミアム他艇（SS × あれ45〜48: v5.0継承・維持）──
    # 的中率72.7% / 回収率869%（11R）という突出した実績
    "premium_are_min":            45.0,
    "premium_are_max":            48.0,
    "premium_points_hit":         15,
    "premium_points_rec":         15,

    # ── ★v6.0: HITモード 買い目点数下限保証 ─────────────────────
    # HITモード参加レースは最低5点を保証
    "hit_min_points":             5,

    # ── ★v6.0改修: 高配当1号艇 ────────────────────────────────
    # HIT: 全スキップ（v6.0最大の変更点）
    # REC: base≥0.60 & あれ43〜47 に参加（v5.0より少し広げる）
    "hd1_buy_base_min":           0.60,
    "hd1_rec_are_min":            43.0,   # v6.0: REC用あれ下限
    "hd1_rec_are_max":            47.0,   # v6.0: REC用あれ上限
    "hd1_rec_points":             8,      # REC: 8点
    # v5.0互換: HITモード buy/quasi 用パラメータ（REC継続使用）
    "hd1_buy_are_min":            46.0,
    "hd1_buy_are_max":            48.0,
    "hd1_buy_points_hit":         5,
    "hd1_buy_points_rec":         8,
    "hd1_quasi_are_min":          40.0,
    "hd1_quasi_are_max":          45.0,
    "hd1_quasi_points_hit":       3,
    "hd1_quasi_points_rec":       3,
    "hd1_skip_points_hit":        0,
    "hd1_skip_points_rec":        1,
    "high_div_boat1_tenkai_max":  0.90,

    # ── ★v6.0: 中立他艇 ─────────────────────────────────────────
    # HIT: 完全スキップ（的中率向上）
    # REC: HITモード優良条件+中立他艇を追加参加
    # 遠隔日前（v5.0継承）
    "neutral_other_distant_points_hit": 0,   # HIT: スキップ
    "neutral_other_distant_points_rec": 15,  # REC: 15点
    "distant_days_threshold":     20,

    # 中立他艇あれゾーン（REC用）
    "neutral_are_main_min":       40.0,
    "neutral_are_main_max":       55.0,
    "neutral_are_main_points":    10,
    "neutral_are_sub_boost":       2,    # あれ45〜48サブゾーン +2点
    "neutral_are_out_points":      5,

    # ── 低配当1号艇 ─────────────────────────────────────────────
    "low_div_boat1_base_min":     0.55,
    "low_div_boat1_tenkai_min":   0.95,
    "low_div_boat1_points":       5,

    # ── 高配当他艇 ──────────────────────────────────────────────
    "high_div_other_base_min":    0.45,
    "high_div_other_tenkai_min":  1.05,

    # ── v4継承: 高人気ゾーン点数圧縮（base≥0.70）────────────────
    "high_pop_base_threshold":    0.70,
    "high_pop_default_points":    5,
    "high_pop_strict_points":     3,

    # ── v4継承: 中人気ロスゾーン（base 0.55〜0.70）───────────────
    "mid_pop_base_min":           0.55,
    "mid_pop_base_max":           0.70,
    "mid_pop_default_points":     7,
    "mid_pop_strict_points":      5,

    # ── v4継承: tenji係数 ─────────────────────────────────────
    "tenji_cap":                  1.0,
    "tenji_weight_normal":        0.07,
    "tenji_weight_sweet":         0.15,
    "sweet_tenkai_boost":         1.30,

    # ── v4継承: まくりアラート閾値 ────────────────────────────
    "makuri_are_threshold":       48.0,
    "makuri_tenkai_threshold":    0.95,

    # ── v4継承: 低配当罠フィルター ──────────────────────────────
    "low_div_trap_payout":        1200,
    "low_div_trap_points":        5,
}

DEFAULT_POINTS = 10

# プレミアムゾーン追跡ログ（サンプル蓄積用）
_premium_log: list[dict] = []

# v6.0 スキップ統計ログ
_skip_stats: dict[str, int] = {
    "hd1_hit_skipped":       0,  # HIT: 高配当1号艇スキップ数
    "neutral_hit_skipped":   0,  # HIT: 中立他艇スキップ数
    "are_over50_skipped":    0,  # HIT: あれ>50スキップ数
    "venue_hit_skipped":     0,  # HIT: 非優良会場スキップ数
}


# ============================================================
# フラグ・パターンクラス
# ============================================================

@dataclass
class RaceFlags:
    makuri_alert:    bool = False
    sashi_alert:     bool = False
    low_dividend:    bool = False
    sweet_spot:      bool = False
    high_pop_zone:   bool = False
    premium_zone:    bool = False   # SSプレミアム
    distant_days:    bool = False   # 遠隔日前
    hd1_filter:      str  = ""      # "buy" / "quasi" / "skip" / "hit_skip"
    venue_rule:      str  = "full"
    kimari_predict:  str  = ""


@dataclass
class RacePattern:
    name:         str
    points:       int
    expected_roi: float
    description:  str
    flags:        RaceFlags = field(default_factory=RaceFlags)
    pass_reason:  str = ""


# ============================================================
# ユーティリティ関数
# ============================================================

def _estimate_payout(base: float, tenkai: float) -> float:
    estimated = 3500 - (base * 2800) - max(0.0, (tenkai - 1.0) * 1500)
    return max(400.0, estimated)


def _cap_tenji(tenji: float) -> float:
    return min(tenji, PARAMS["tenji_cap"])


def _apply_tenji_correction(base_points: int, capped_tenji: float, is_sweet: bool) -> int:
    if capped_tenji >= 1.0:
        return base_points
    deficit = 1.0 - capped_tenji
    weight = PARAMS["tenji_weight_sweet"] if is_sweet else PARAMS["tenji_weight_normal"]
    reduction = deficit * weight * base_points * 10
    adjusted = base_points - int(reduction)
    return max(1, adjusted)


def _detect_makuri_alert(are_index: float, raw_tenkai: float) -> bool:
    return (are_index >= PARAMS["makuri_are_threshold"]) or (raw_tenkai < PARAMS["makuri_tenkai_threshold"])


def _is_distant_days(days_before: Optional[int]) -> bool:
    """遠隔日前（直近X日より古い開催）かどうかを判定"""
    if days_before is None:
        return False
    return days_before >= PARAMS["distant_days_threshold"]


def _hd1_filter_zone_rec(boat1_base: float, are_index: float) -> str:
    """
    v6.0: 高配当1号艇のRECモード用フィルター判定。
    REC: base≥0.60 & あれ43〜47 → 参加
    Returns: "rec_buy" / "skip"
    """
    p = PARAMS
    base_ok = boat1_base >= p["hd1_buy_base_min"]
    if base_ok and p["hd1_rec_are_min"] <= are_index <= p["hd1_rec_are_max"]:
        return "rec_buy"
    return "skip"


def _hd1_filter_zone_v5(boat1_base: float, are_index: float) -> str:
    """v5.0互換: 高配当1号艇フィルター（REC内部処理で使用）"""
    p = PARAMS
    base_ok = boat1_base >= p["hd1_buy_base_min"]
    if base_ok and p["hd1_buy_are_min"] <= are_index <= p["hd1_buy_are_max"]:
        return "buy"
    if base_ok and p["hd1_quasi_are_min"] <= are_index < p["hd1_quasi_are_max"]:
        return "quasi"
    return "skip"


def _neutral_other_are_points(are_index: float) -> int:
    """
    中立他艇のあれ指数別点数（REC用）
    """
    p = PARAMS
    if p["neutral_are_main_min"] <= are_index <= p["neutral_are_main_max"]:
        if p["premium_are_min"] <= are_index <= p["premium_are_max"]:
            return p["neutral_are_main_points"] + p["neutral_are_sub_boost"]
        return p["neutral_are_main_points"]
    return p["neutral_are_out_points"]


def _apply_hit_min_points(pts: int) -> int:
    """HITモード: 買い目点数下限保証（最低5点）"""
    return max(pts, PARAMS["hit_min_points"])


def _is_hit_venue(venue: str) -> bool:
    """HITモード優良会場かどうかを判定"""
    return venue in HIT_ALLOWED_VENUES


def _is_are_stable_for_hit(are_index: float) -> bool:
    """HITモード: あれ指数が安定ゾーン(40〜50)かを判定"""
    return PARAMS["are_stable_min"] <= are_index <= PARAMS["are_hit_max"]


# ============================================================
# メイン分類関数
# ============================================================

def classify_race(
    venue:            str,
    pred_rank1_boat:  int,
    boat1_base:       float,
    boat1_tenkai:     float,
    pred1_base:       float,
    pred1_tenkai:     float,
    boat1_tenji:      float = 1.0,
    pred1_tenji:      float = 1.0,
    are_index:        float = 50.0,
    expected_payout:  Optional[float] = None,
    buy_mode:         str   = "hit",
    days_before:      Optional[int] = None,
    race_id:          str   = "",
) -> Optional[RacePattern]:
    """
    1レース分の情報を受け取り、パターン分類と推奨点数を返す。

    Parameters
    ----------
    venue            : 会場名
    pred_rank1_boat  : 予想1位艇番号（1〜6）
    boat1_base       : 1号艇のbase係数
    boat1_tenkai     : 1号艇のtenkai係数（raw値）
    pred1_base       : 予想1位艇のbase係数
    pred1_tenkai     : 予想1位艇のtenkai係数（raw値）
    boat1_tenji      : 1号艇の展示係数
    pred1_tenji      : 予想1位艇の展示係数
    are_index        : あれ指数
    expected_payout  : 期待払戻（省略時は簡易推定）
    buy_mode         : "hit"（的中重視）or "rec"（回収重視）
    days_before      : この開催が本日から何日前か（遠隔日前判定用）
    race_id          : ログ用レースID

    Returns
    -------
    RacePattern | None  (Noneは除外レース)
    """

    # ── 0. 会場ルール ──────────────────────────────────────────
    venue_rule = VENUE_RULE.get(venue, "full")
    if venue_rule == "skip":
        return None

    # ── ★v6.0: HITモード 会場絞り込み ───────────────────────────
    # HIT: 優良6会場のみ（それ以外はRECとして参加 or スキップ）
    if buy_mode == "hit" and not _is_hit_venue(venue):
        # 非優良会場はHITではスキップ
        _skip_stats["venue_hit_skipped"] += 1
        return RacePattern(
            name="非対象会場(HIT)",
            points=0,
            expected_roi=0.0,
            description=f"HITモード: {venue}は優良6会場外のためスキップ",
            flags=RaceFlags(venue_rule=venue_rule),
            pass_reason=(
                f"v6.0 HITモード: 優良会場（唐津/住之江/尼崎/桐生/びわこ/浜名湖）"
                f"のみ参加。{venue}は対象外。RECモードで参加可能。"
            ),
        )

    p        = PARAMS
    is_boat1 = (pred_rank1_boat == 1)

    # ── 1. tenji係数キャップ ──────────────────────────────────
    capped_boat1_tenji = _cap_tenji(boat1_tenji)
    capped_pred1_tenji = _cap_tenji(pred1_tenji)
    main_capped_tenji  = capped_boat1_tenji if is_boat1 else capped_pred1_tenji

    # ── 2. 期待払戻・フラグ ───────────────────────────────────
    main_base   = boat1_base   if is_boat1 else pred1_base
    main_tenkai = boat1_tenkai if is_boat1 else pred1_tenkai

    if expected_payout is None:
        expected_payout = _estimate_payout(main_base, main_tenkai)

    low_div_trap  = expected_payout < p["low_div_trap_payout"]
    makuri_alert  = _detect_makuri_alert(are_index, main_tenkai)
    sashi_alert   = (main_tenkai < 1.0) and (main_base < 0.55)
    is_distant    = _is_distant_days(days_before)

    # ── 3. ★v6.0: SS条件（拡張定義）───────────────────────────
    # v6.0: base 0.43〜0.57 & あれ40〜50安定ゾーン
    tenkai_available = (main_tenkai != 1.0)
    is_sweet_base = (p["sweet_base_min"] <= main_base < p["sweet_base_max"])
    is_sweet = (
        is_sweet_base
        and (not tenkai_available or main_tenkai < p["sweet_tenkai_max"])
    )
    # SS条件でのあれ安定ゾーン補正
    is_sweet_are_stable = is_sweet and _is_are_stable_for_hit(are_index)
    is_sweet_boosted = is_sweet and (are_index >= p["sweet_are_boost_threshold"])

    # ── 4. 高人気ゾーン・中人気ロスゾーン ─────────────────────
    is_high_pop = (main_base >= p["high_pop_base_threshold"])
    is_mid_pop  = (
        p["mid_pop_base_min"] <= main_base < p["mid_pop_base_max"]
        and not is_sweet
    )

    # ── 5. ★v6.0: プレミアムゾーン判定（SS他艇 × あれ45〜48）───
    is_premium = (
        not is_boat1
        and is_sweet
        and p["premium_are_min"] <= are_index <= p["premium_are_max"]
    )

    # ── ★v6.0: HITモード あれ指数50超スキップ ────────────────
    # プレミアムゾーン（45〜48）はあれ50以下なので除外対象外
    if buy_mode == "hit" and not _is_are_stable_for_hit(are_index):
        # プレミアムゾーンは例外的に通過させる（45〜48は50以下なので通常通過）
        if not is_premium:
            _skip_stats["are_over50_skipped"] += 1
            return RacePattern(
                name="あれ超過スキップ(HIT)",
                points=0,
                expected_roi=0.0,
                description=f"HITモード: あれ{are_index:.0f}>50の荒れリスク → スキップ",
                flags=RaceFlags(makuri_alert=makuri_alert, venue_rule=venue_rule),
                pass_reason=(
                    f"v6.0 HITモード: あれ指数{are_index:.1f}が安定ゾーン"
                    f"({p['are_stable_min']}〜{p['are_hit_max']})を超過。"
                    f"荒れリスク高→スキップ。RECモードで情報収集可。"
                ),
            )

    # ============================================================
    # 福岡専用ルール
    # ============================================================
    if venue_rule == "fukuoka":
        # HITモードでは福岡は優良会場外なのでここには到達しない
        fuk_high_pop = (main_base >= FUKUOKA_HIGH_POP_BASE)

        if fuk_high_pop:
            base_pts = FUKUOKA_HIGH_POP_STRICT if low_div_trap else FUKUOKA_HIGH_POP_POINTS
            pts  = _apply_tenji_correction(base_pts, main_capped_tenji, is_sweet=False)
            flags = RaceFlags(makuri_alert=makuri_alert, low_dividend=low_div_trap,
                              high_pop_zone=True, venue_rule="fukuoka")
            return RacePattern(name="高人気圧縮(福岡)", points=pts, expected_roi=95.0,
                               description=f"福岡: base>={FUKUOKA_HIGH_POP_BASE} → {base_pts}点圧縮", flags=flags)

        if is_sweet:
            base_pts = p["sweet_max_points"]
            pts  = _apply_tenji_correction(base_pts, main_capped_tenji, is_sweet=True)
            pat_name = "スイートスポット1号艇" if is_boat1 else "スイートスポット他艇"
            flags = RaceFlags(makuri_alert=makuri_alert, sashi_alert=sashi_alert,
                              low_dividend=low_div_trap, sweet_spot=True, venue_rule="fukuoka")
            return RacePattern(name=pat_name, points=pts, expected_roi=155.0,
                               description="福岡スイートスポット → 資金集中", flags=flags)

        base_pts = p["low_div_trap_points"] if low_div_trap else 7
        pts  = _apply_tenji_correction(base_pts, main_capped_tenji, is_sweet=False)
        flags = RaceFlags(makuri_alert=makuri_alert, low_dividend=low_div_trap, venue_rule="fukuoka")
        return RacePattern(name="中立(福岡)", points=pts, expected_roi=100.0,
                           description="福岡: 低base → 荒れ狙い7点", flags=flags)

    # ============================================================
    # 分岐A: 1号艇が予想1位
    # ============================================================
    if is_boat1:

        # ◎ 高配当1号艇: v6.0 HITモード全スキップ
        if boat1_tenkai < p["high_div_boat1_tenkai_max"]:

            # ★v6.0 最大変更: HITモードは問答無用でスキップ
            if buy_mode == "hit":
                _skip_stats["hd1_hit_skipped"] += 1
                return RacePattern(
                    name="高配当1号艇",
                    points=0,
                    expected_roi=88.3,
                    description="【HITスキップ】高配当1号艇: v6.0でHIT全スキップ",
                    flags=RaceFlags(makuri_alert=makuri_alert, low_dividend=low_div_trap,
                                    hd1_filter="hit_skip"),
                    pass_reason=(
                        f"v6.0 HITモード: 高配当1号艇は全スキップ。"
                        f"的中率向上のため分母から除外（全体的中率26%→排除後改善）。"
                        f"RECモード(base≥0.60 & あれ43〜47)で参加可能。"
                    ),
                )

            # RECモード: base≥0.60 & あれ43〜47
            zone_rec = _hd1_filter_zone_rec(boat1_base, are_index)
            if zone_rec == "rec_buy":
                base_pts = p["hd1_rec_points"]
                if low_div_trap:
                    base_pts = min(base_pts, p["low_div_trap_points"])
                pts = _apply_tenji_correction(base_pts, capped_boat1_tenji, is_sweet=False)
                flags = RaceFlags(makuri_alert=makuri_alert, low_dividend=low_div_trap,
                                  hd1_filter="rec_buy")
                return RacePattern(
                    name="高配当1号艇",
                    points=pts,
                    expected_roi=203.0,
                    description=(
                        f"【REC参加】高配当1号艇: base={boat1_base:.2f}(≥0.60) "
                        f"× あれ{are_index:.0f}(43〜47) → 305件/的中36.1%/回収203%"
                    ),
                    flags=flags,
                )
            else:
                # RECでも条件外はスキップ
                pts = p["hd1_skip_points_rec"]  # 1点情報収集
                flags = RaceFlags(makuri_alert=makuri_alert, low_dividend=low_div_trap,
                                  hd1_filter="skip")
                return RacePattern(
                    name="高配当1号艇",
                    points=pts,
                    expected_roi=88.3,
                    description=f"【REC条件外】高配当1号艇: base={boat1_base:.2f} あれ{are_index:.0f}",
                    flags=flags,
                    pass_reason=(
                        f"REC条件外（base<0.60 or あれ範囲外43〜47）: 情報収集1点のみ。"
                    ),
                )

        # ★ 高人気圧縮（base≥0.70）
        elif is_high_pop:
            base_pts = p["high_pop_strict_points"] if low_div_trap else p["high_pop_default_points"]
            pts  = _apply_tenji_correction(base_pts, capped_boat1_tenji, is_sweet=False)
            if buy_mode == "hit":
                pts = _apply_hit_min_points(pts)
            flags = RaceFlags(makuri_alert=makuri_alert, low_dividend=low_div_trap, high_pop_zone=True)
            return RacePattern(
                name="高人気圧縮", points=pts, expected_roi=80.0,
                description=(
                    f"base≥{p['high_pop_base_threshold']} → "
                    f"{'強制3点' if low_div_trap else '5点圧縮'}"
                ),
                flags=flags,
                pass_reason=(
                    f"高人気圧縮ゾーン（base≥{p['high_pop_base_threshold']}）："
                    f"回収率79%損失ゾーン。{pts}点圧縮。見送りも合理的。"
                ),
            )

        # ★ 中人気ロスゾーン（base 0.55〜0.70）
        elif is_mid_pop:
            base_pts = p["mid_pop_strict_points"] if low_div_trap else p["mid_pop_default_points"]
            pts  = _apply_tenji_correction(base_pts, capped_boat1_tenji, is_sweet=False)
            flags = RaceFlags(makuri_alert=makuri_alert, low_dividend=low_div_trap)
            return RacePattern(
                name="中人気ロス", points=pts, expected_roi=87.0,
                description=f"base 0.55〜0.70（回収率87%ゾーン）→ {pts}点削減",
                flags=flags,
                pass_reason=(
                    f"中人気ロスゾーン（base {p['mid_pop_base_min']}〜{p['mid_pop_base_max']}）："
                    f"回収率86〜88%損失ゾーン。不参加推奨。"
                ),
            )

        # ★ スイートスポット1号艇（v6.0: base 0.43〜0.57）
        elif is_sweet:
            base_pts = p["sweet_max_points"]
            if is_sweet_boosted:
                base_pts = min(DEFAULT_POINTS, base_pts + p["sweet_are_boost_points"])
            pts  = _apply_tenji_correction(base_pts, capped_boat1_tenji, is_sweet=True)
            if buy_mode == "hit":
                pts = _apply_hit_min_points(pts)
            flags = RaceFlags(makuri_alert=makuri_alert, sashi_alert=sashi_alert,
                              low_dividend=low_div_trap, sweet_spot=True)
            desc = f"base{p['sweet_base_min']}〜{p['sweet_base_max']}・回収率突出ゾーン・資金集中"
            if is_sweet_are_stable:
                desc += f"（あれ{are_index:.0f}: 安定ゾーン✅）"
            if is_sweet_boosted:
                desc += f"（あれ≥{p['sweet_are_boost_threshold']}ブースト）"
            return RacePattern(
                name="スイートスポット1号艇", points=pts,
                expected_roi=160.0 if is_sweet_boosted else 155.0,
                description=desc, flags=flags,
            )

        # × 低配当1号艇
        elif (not is_mid_pop
              and boat1_base >= p["low_div_boat1_base_min"]
              and boat1_tenkai >= p["low_div_boat1_tenkai_min"]):
            base_pts = p["low_div_boat1_points"]
            if low_div_trap:
                base_pts = min(base_pts, p["low_div_trap_points"])
            pts = _apply_tenji_correction(base_pts, capped_boat1_tenji, is_sweet=False)
            if buy_mode == "hit":
                pts = _apply_hit_min_points(pts)
            flags = RaceFlags(low_dividend=low_div_trap)
            return RacePattern(name="低配当1号艇", points=pts, expected_roi=102.2,
                               description="1号艇人気+展開良 → 点数削減", flags=flags)

        # ○ 中立1号艇
        else:
            base_pts = p["low_div_trap_points"] if low_div_trap else 4
            pts  = _apply_tenji_correction(base_pts, capped_boat1_tenji, is_sweet=False)
            if buy_mode == "hit":
                pts = _apply_hit_min_points(pts)
            flags = RaceFlags(makuri_alert=makuri_alert, low_dividend=low_div_trap)
            return RacePattern(name="中立1号艇", points=pts, expected_roi=100.7,
                               description="1号艇予想・条件中立", flags=flags)

    # ============================================================
    # 分岐B: 他艇が予想1位
    # ============================================================
    else:

        # ★★ 最優先: SSプレミアム他艇（SS × あれ45〜48）
        if is_premium:
            pts = p["premium_points_hit"] if buy_mode == "hit" else p["premium_points_rec"]
            if buy_mode == "hit":
                pts = _apply_hit_min_points(pts)
            flags = RaceFlags(
                makuri_alert=makuri_alert, sashi_alert=sashi_alert,
                sweet_spot=True, premium_zone=True,
            )
            _premium_log.append({
                "race_id": race_id, "venue": venue, "buy_mode": buy_mode,
                "are_index": are_index, "pred1_base": pred1_base,
                "points": pts,
            })
            return RacePattern(
                name="SSプレミアム他艇",
                points=pts,
                expected_roi=869.0,
                description=(
                    f"【最優先】SS他艇 × あれ{are_index:.0f}(45〜48): "
                    f"的中率72.7%/回収率869%（11R）→ {pts}点フル投資"
                ),
                flags=flags,
            )

        # ★ スイートスポット他艇（プレミアム以外のSS）
        if is_sweet:
            # v6.0 HIT: あれ≥50 は不買い（v5.0の55→50に厳格化）
            if buy_mode == "hit" and are_index >= p["sweet_hit_are_max"]:
                flags = RaceFlags(makuri_alert=makuri_alert, sashi_alert=sashi_alert, sweet_spot=True)
                return RacePattern(
                    name="スイートスポット他艇", points=0, expected_roi=155.0,
                    description=f"HIT: あれ{are_index:.0f}≥{p['sweet_hit_are_max']}のため不買い",
                    flags=flags,
                    pass_reason=(
                        f"v6.0 HITモード：あれ{are_index:.0f}(≥{p['sweet_hit_are_max']})。"
                        f"SS他艇×高あれ指数は的中率低下ゾーン → 見送り推奨。"
                    ),
                )
            base_pts = p["sweet_max_points"]
            if is_sweet_boosted:
                base_pts = min(DEFAULT_POINTS, base_pts + p["sweet_are_boost_points"])
            pts  = _apply_tenji_correction(base_pts, capped_pred1_tenji, is_sweet=True)
            if pred1_tenkai < p["sweet_low_tenkai_threshold"]:
                pts = min(pts, p["sweet_low_tenkai_points"])
            if buy_mode == "hit":
                pts = _apply_hit_min_points(pts)
            flags = RaceFlags(makuri_alert=makuri_alert, sashi_alert=sashi_alert, sweet_spot=True)
            desc = f"base{p['sweet_base_min']}〜{p['sweet_base_max']} 他艇予想 → 資金集中ゾーン"
            if is_sweet_are_stable:
                desc += f"（あれ{are_index:.0f}: 安定ゾーン✅）"
            if pred1_tenkai < p["sweet_low_tenkai_threshold"]:
                desc += f"（tenkai<{p['sweet_low_tenkai_threshold']} → 点数{p['sweet_low_tenkai_points']}点圧縮）"
            if is_sweet_boosted:
                desc += f"（あれ≥{p['sweet_are_boost_threshold']}ブースト）"
            return RacePattern(
                name="スイートスポット他艇", points=pts,
                expected_roi=160.0 if is_sweet_boosted else 155.0,
                description=desc, flags=flags,
            )

        # ◎ 高配当他艇
        if pred1_base >= p["high_div_other_base_min"] and pred1_tenkai >= p["high_div_other_tenkai_min"]:
            base_pts = p["low_div_trap_points"] if low_div_trap else DEFAULT_POINTS
            pts  = _apply_tenji_correction(base_pts, capped_pred1_tenji, is_sweet=False)
            if buy_mode == "hit":
                pts = _apply_hit_min_points(pts)
            flags = RaceFlags(makuri_alert=makuri_alert, low_dividend=low_div_trap)
            return RacePattern(name="高配当他艇", points=pts, expected_roi=187.9,
                               description="他艇1位・実力+展開好調 → 高配当狙い", flags=flags)

        # △ 中立他艇
        # ★v6.0: HITモードは完全スキップ
        if buy_mode == "hit":
            _skip_stats["neutral_hit_skipped"] += 1
            return RacePattern(
                name="中立他艇",
                points=0,
                expected_roi=0.0,
                description="【HITスキップ】中立他艇: v6.0でHIT全スキップ",
                flags=RaceFlags(makuri_alert=makuri_alert, low_dividend=low_div_trap,
                                distant_days=is_distant),
                pass_reason=(
                    f"v6.0 HITモード: 中立他艇はスキップ。"
                    f"SS他艇・SS1号艇のみに絞ることで的中率向上。"
                    f"RECモードでは参加可能。"
                ),
            )

        # RECモード: 遠隔日前フラグで点数増量
        if is_distant:
            base_pts = p["neutral_other_distant_points_rec"]
            if low_div_trap:
                base_pts = p["low_div_trap_points"]
            pts  = _apply_tenji_correction(base_pts, capped_pred1_tenji, is_sweet=False)
            flags = RaceFlags(makuri_alert=makuri_alert, low_dividend=low_div_trap, distant_days=True)
            return RacePattern(
                name="中立他艇",
                points=pts,
                expected_roi=180.0,
                description=(
                    f"【REC遠隔日前】中立他艇: 的中率58.1%ゾーン "
                    f"→ {base_pts}点増量（RECモード）"
                ),
                flags=flags,
            )

        # 通常の中立他艇（REC）: あれ指数別点数
        base_pts = _neutral_other_are_points(are_index)
        if low_div_trap:
            base_pts = p["low_div_trap_points"]
        pts  = _apply_tenji_correction(base_pts, capped_pred1_tenji, is_sweet=False)

        are_zone_label = (
            "45〜48プレミアム(非SS)+2点" if p["premium_are_min"] <= are_index <= p["premium_are_max"]
            else ("40〜55主戦場" if p["neutral_are_main_min"] <= are_index <= p["neutral_are_main_max"]
                  else "範囲外→抑制")
        )
        roi_neutral = 248.0 if p["neutral_are_main_min"] <= are_index <= p["neutral_are_main_max"] else 107.2

        flags = RaceFlags(makuri_alert=makuri_alert, low_dividend=low_div_trap)
        return RacePattern(
            name="中立他艇",
            points=pts,
            expected_roi=roi_neutral,
            description=f"REC中立他艇（あれ{are_index:.0f}: {are_zone_label}）→ {pts}点",
            flags=flags,
        )


# ============================================================
# 会場別後処理
# ============================================================

def _post_process(pat: RacePattern, venue_rule: str) -> RacePattern:
    """会場別後処理"""
    pat.flags.venue_rule = venue_rule

    if venue_rule == "limited" and pat.name not in LIMITED_ALLOWED_PATTERNS:
        pat.points = 0
        pat.pass_reason = (
            f"限定会場モード：{pat.name}はスイートスポット・高配当パターン外のため見送り推奨。"
        )

    if venue_rule == "marugame" and pat.flags.makuri_alert:
        pat.points = min(pat.points, MARUGAME_MAKURI_MAX_POINTS)
        pat.description += f" ※丸亀まくり補正→最大{MARUGAME_MAKURI_MAX_POINTS}点"

    return pat


# ============================================================
# CSV一括処理
# ============================================================

def process_backtest_csv(input_path: str, output_path: Optional[str] = None) -> pd.DataFrame:
    """
    バックテストCSVを読み込み、v6.0ロジックで点数・分類・収支を計算。
    """
    df = pd.read_csv(input_path)

    # 的中順位
    def get_hit_position(row):
        if row["的中"] != "的中":
            return None
        bets = [b.strip().replace("−", "-") for b in row["買い目組合せ"].split("/")]
        target = str(row["的中組合せ"]).strip()
        try:
            return bets.index(target) + 1
        except ValueError:
            return None

    df["的中順位"] = df.apply(get_hit_position, axis=1)

    def apply_classify(row):
        b1_tenji  = float(row["1号艇_tenji"])   if pd.notna(row.get("1号艇_tenji"))   else 1.0
        p1_tenji  = float(row["予想1位_tenji"]) if pd.notna(row.get("予想1位_tenji")) else 1.0
        are_idx   = float(row["あれ指数"])       if pd.notna(row.get("あれ指数"))       else 50.0
        days_bef  = int(row["days_before"])      if pd.notna(row.get("days_before"))    else None
        race_id   = str(row.get("race_id", ""))

        pat = classify_race(
            venue            = row["会場"],
            pred_rank1_boat  = int(row["予想1位艇"]),
            boat1_base       = float(row["1号艇_base"]),
            boat1_tenkai     = float(row["1号艇_tenkai"]),
            pred1_base       = float(row["予想1位_base"]),
            pred1_tenkai     = float(row["予想1位_tenkai"]),
            boat1_tenji      = b1_tenji,
            pred1_tenji      = p1_tenji,
            are_index        = are_idx,
            days_before      = days_bef,
            race_id          = race_id,
        )
        if pat is None:
            return pd.Series({
                "パターン": "除外会場", "推奨点数": 0, "期待回収率": 0.0,
                "まくりアラート": False, "差しアラート": False,
                "低配当フラグ": False,  "スイートスポット": False,
                "プレミアムゾーン": False, "遠隔日前": False,
                "HD1フィルター": "", "見送り理由": "",
            })
        return pd.Series({
            "パターン":         pat.name,
            "推奨点数":         pat.points,
            "期待回収率":       pat.expected_roi,
            "まくりアラート":   pat.flags.makuri_alert,
            "差しアラート":     pat.flags.sashi_alert,
            "低配当フラグ":     pat.flags.low_dividend,
            "スイートスポット": pat.flags.sweet_spot,
            "プレミアムゾーン": pat.flags.premium_zone,
            "遠隔日前":         pat.flags.distant_days,
            "HD1フィルター":    pat.flags.hd1_filter,
            "見送り理由":       pat.pass_reason,
        })

    cols = ["パターン", "推奨点数", "期待回収率",
            "まくりアラート", "差しアラート", "低配当フラグ",
            "スイートスポット", "プレミアムゾーン", "遠隔日前",
            "HD1フィルター", "見送り理由"]
    df[cols] = df.apply(apply_classify, axis=1)

    def calc_actual(row):
        if row["推奨点数"] == 0:
            return pd.Series({"実的中": False, "実払戻": 0.0, "実投資": 0})
        inv = int(row["推奨点数"]) * 100
        if (row["的中"] == "的中"
                and pd.notna(row["的中順位"])
                and row["的中順位"] <= row["推奨点数"]):
            return pd.Series({"実的中": True, "実払戻": row["払戻金"], "実投資": inv})
        return pd.Series({"実的中": False, "実払戻": 0.0, "実投資": inv})

    df[["実的中", "実払戻", "実投資"]] = df.apply(calc_actual, axis=1)

    if output_path:
        df.to_csv(output_path, index=False, encoding="utf-8-sig")
        print(f"保存完了: {output_path}")

    return df


# ============================================================
# サマリーレポート
# ============================================================

def print_summary(df: pd.DataFrame) -> None:
    active = df[df["推奨点数"] > 0]
    total_inv  = active["実投資"].sum()
    total_pay  = active["実払戻"].sum()
    total_hits = active["実的中"].sum()
    roi        = total_pay / total_inv * 100 if total_inv > 0 else 0
    profit     = total_pay - total_inv

    print("=" * 70)
    print("  最適化後 バックテストサマリー  v6.0")
    print("  ─ 的中率改善軸 再設計 / 参加条件大幅絞り込み ─")
    print("=" * 70)
    print(f"  対象レース数  : {len(active):,}R  (除外: {len(df)-len(active):,}R)")
    print(f"  総投資額      : {total_inv:,.0f}円")
    print(f"  総払戻金      : {total_pay:,.0f}円")
    print(f"  的中レース    : {total_hits:,}件  ({total_hits/max(len(active),1)*100:.1f}%)")
    print(f"  回収率        : {roi:.1f}%")
    print(f"  収支          : {profit:+,.0f}円")
    print()

    # ── v6.0: スキップ統計 ──
    print("  ── v6.0 スキップ統計（HIT品質向上のため除外）─────────────")
    print(f"  高配当1号艇スキップ(HIT)  : {_skip_stats['hd1_hit_skipped']:>5}R")
    print(f"  中立他艇スキップ(HIT)      : {_skip_stats['neutral_hit_skipped']:>5}R")
    print(f"  あれ>50スキップ(HIT)       : {_skip_stats['are_over50_skipped']:>5}R")
    print(f"  非優良会場スキップ(HIT)    : {_skip_stats['venue_hit_skipped']:>5}R")
    print()

    # ── パターン別内訳 ──
    print("  ── パターン別内訳 ───────────────────────────────────────")
    order = [
        "SSプレミアム他艇",
        "スイートスポット1号艇", "スイートスポット他艇",
        "高配当1号艇", "高配当他艇",
        "中立他艇", "中立1号艇",
        "低配当1号艇",
        "中人気ロス", "高人気圧縮",
        "高人気圧縮(福岡)", "中立(福岡)",
    ]
    for pat in order:
        sub = active[active["パターン"] == pat]
        if len(sub) == 0:
            continue
        inv  = sub["実投資"].sum()
        pay  = sub["実払戻"].sum()
        hits = sub["実的中"].sum()
        r    = pay / inv * 100 if inv > 0 else 0
        avg_pts = sub["推奨点数"].mean()
        print(f"  {pat:<22}: {len(sub):>4}R  "
              f"的中率{hits/len(sub)*100:5.1f}%  "
              f"回収率{r:6.1f}%  "
              f"平均点数{avg_pts:4.1f}  "
              f"収支{pay-inv:+10,.0f}円")

    print()

    # ── v6.0: HD1フィルター別内訳 ──
    hd1_all = df[df["パターン"] == "高配当1号艇"]
    if len(hd1_all) > 0:
        print("  ── 高配当1号艇 フィルター別内訳 ───────────────────────")
        for zone, label in [
            ("hit_skip",  "HITスキップ(v6.0全除外)"),
            ("rec_buy",   "REC参加(base≥0.60 & あれ43〜47)"),
            ("skip",      "REC条件外スキップ"),
        ]:
            sub = hd1_all[hd1_all["HD1フィルター"] == zone]
            if len(sub) == 0:
                continue
            act_sub = sub[sub["推奨点数"] > 0]
            if len(act_sub) == 0:
                print(f"  {label}: {len(sub):>4}R → 全スキップ")
                continue
            inv  = act_sub["実投資"].sum()
            pay  = act_sub["実払戻"].sum()
            hits = act_sub["実的中"].sum()
            r    = pay / inv * 100 if inv > 0 else 0
            print(f"  {label}: {len(sub):>4}R "
                  f"（参加{len(act_sub)}R）  "
                  f"的中率{hits/max(len(act_sub),1)*100:5.1f}%  "
                  f"回収率{r:6.1f}%  "
                  f"収支{pay-inv:+10,.0f}円")
        print()

    # ── プレミアムゾーン追跡 ──
    premium = active[active.get("プレミアムゾーン", pd.Series(False, index=active.index)) == True]
    if len(premium) > 0:
        p_inv  = premium["実投資"].sum()
        p_pay  = premium["実払戻"].sum()
        p_hits = premium["実的中"].sum()
        p_roi  = p_pay / p_inv * 100 if p_inv > 0 else 0
        print(f"  💎 SSプレミアム他艇合算: {len(premium)}R  "
              f"的中率{p_hits/len(premium)*100:.1f}%  "
              f"回収率{p_roi:.1f}%  "
              f"収支{p_pay-p_inv:+,.0f}円")

    # ── 遠隔日前中立他艇 ──
    distant = active[active.get("遠隔日前", pd.Series(False, index=active.index)) == True]
    if len(distant) > 0:
        d_inv  = distant["実投資"].sum()
        d_pay  = distant["実払戻"].sum()
        d_hits = distant["実的中"].sum()
        d_roi  = d_pay / d_inv * 100 if d_inv > 0 else 0
        print(f"  📅 遠隔日前 中立他艇    : {len(distant)}R  "
              f"的中率{d_hits/len(distant)*100:.1f}%  "
              f"回収率{d_roi:.1f}%  "
              f"収支{d_pay-d_inv:+,.0f}円")

    # ── skip会場 ──
    skip_venues = [v for v, rule in VENUE_RULE.items() if rule == "skip"]
    skip_rows   = df[df["会場"].isin(skip_venues)] if "会場" in df.columns else pd.DataFrame()
    if len(skip_rows) > 0:
        print()
        print(f"  ── skip除外会場（{'/'.join(skip_venues)}）")
        print(f"  skip除外計: {len(skip_rows):>4}R  ({len(skip_rows)/max(len(df),1)*100:.1f}%)")

    # ── v6.0: HITモード優良会場内訳 ──
    if "会場" in df.columns:
        hit_active = active[active["会場"].isin(HIT_ALLOWED_VENUES)]
        if len(hit_active) > 0:
            print()
            print(f"  ── v6.0 HIT優良会場内訳 {'─'*30}")
            h_inv  = hit_active["実投資"].sum()
            h_pay  = hit_active["実払戻"].sum()
            h_hits = hit_active["実的中"].sum()
            h_roi  = h_pay / h_inv * 100 if h_inv > 0 else 0
            print(f"  優良6会場合算: {len(hit_active)}R  "
                  f"的中率{h_hits/len(hit_active)*100:.1f}%  "
                  f"回収率{h_roi:.1f}%  "
                  f"収支{h_pay-h_inv:+,.0f}円")

    print("=" * 70)


# ============================================================
# メイン実行
# ============================================================

if __name__ == "__main__":
    import sys
    import glob
    from pathlib import Path
    from datetime import datetime

    SCRIPT_DIR = Path(__file__).parent
    CSV_DIR    = SCRIPT_DIR / "csv_output"

    if len(sys.argv) >= 2:
        INPUT  = Path(sys.argv[1])
        OUTPUT = SCRIPT_DIR / f"backtest_v6_{datetime.now().strftime('%Y%m%d')}.csv"
        if not INPUT.exists():
            print(f"[エラー] CSVが見つかりません: {INPUT}")
            sys.exit(1)
        df = process_backtest_csv(str(INPUT), str(OUTPUT))

    else:
        today    = datetime.now().strftime("%Y-%m-%d")
        today_nd = datetime.now().strftime("%Y%m%d")
        OUTPUT   = SCRIPT_DIR / f"backtest_v6_{today_nd}.csv"

        candidates = sorted(set(
            glob.glob(str(CSV_DIR / f"*{today}*.csv")) +
            glob.glob(str(CSV_DIR / f"*{today_nd}*.csv"))
        ))
        if not candidates:
            candidates = sorted(set(
                glob.glob(str(SCRIPT_DIR / f"*{today}*.csv")) +
                glob.glob(str(SCRIPT_DIR / f"*{today_nd}*.csv"))
            ))

        if not candidates:
            print(f"[エラー] 当日({today})のCSVが見つかりません")
            sys.exit(1)

        print(f"  当日CSV {len(candidates)}件を検出: {[Path(p).name for p in candidates]}")

        dfs = []
        for csv_path in candidates:
            try:
                _df = process_backtest_csv(csv_path)
                dfs.append(_df)
                print(f"  ✓ 読込: {Path(csv_path).name}  ({len(_df)}R)")
            except Exception as e:
                print(f"  ⚠ スキップ: {Path(csv_path).name}  ({e})")

        if not dfs:
            print("[エラー] 有効なCSVが1件もありませんでした")
            sys.exit(1)

        df = pd.concat(dfs, ignore_index=True)
        df.to_csv(str(OUTPUT), index=False, encoding="utf-8-sig")
        print(f"  保存完了: {OUTPUT.name}  (合計{len(df)}R)")

    print_summary(df)

    # ── プレミアムゾーン追跡ログ出力 ──
    if _premium_log:
        print(f"\n  💎 SSプレミアム追跡ログ（{len(_premium_log)}件）:")
        for entry in _premium_log:
            print(f"    {entry}")

    # ── v6.0 単体レース判定例 ──
    print("\n  ── v6.0 単体レース判定例 ──────────────────────────────────")
    examples = [
        # ① HITモード: SS他艇 × プレミアムゾーン（優良会場・あれ安定）
        dict(label="[HIT] SSプレミアム他艇（唐津・あれ46・base0.50）",
             venue="唐津", pred_rank1_boat=2,
             boat1_base=0.30, boat1_tenkai=1.0,
             pred1_base=0.50, pred1_tenkai=1.0,
             are_index=46.5, buy_mode="hit"),

        # ② HITモード: SS1号艇（優良会場・あれ安定）
        dict(label="[HIT] SS1号艇（住之江・あれ43・base0.48）",
             venue="住之江", pred_rank1_boat=1,
             boat1_base=0.48, boat1_tenkai=1.0,
             pred1_base=0.48, pred1_tenkai=1.0,
             are_index=43.0, buy_mode="hit"),

        # ③ HITモード: 高配当1号艇 → v6.0でスキップ
        dict(label="[HIT] 高配当1号艇 → 全スキップ確認（唐津・あれ47）",
             venue="唐津", pred_rank1_boat=1,
             boat1_base=0.62, boat1_tenkai=0.85,
             pred1_base=0.62, pred1_tenkai=0.85,
             are_index=47.0, buy_mode="hit"),

        # ④ HITモード: あれ52 → スキップ確認
        dict(label="[HIT] あれ52超スキップ確認（桐生・SS他艇）",
             venue="桐生", pred_rank1_boat=2,
             boat1_base=0.30, boat1_tenkai=1.0,
             pred1_base=0.50, pred1_tenkai=1.0,
             are_index=52.0, buy_mode="hit"),

        # ⑤ HITモード: 非優良会場 → スキップ確認
        dict(label="[HIT] 非優良会場スキップ確認（津・SS他艇）",
             venue="津", pred_rank1_boat=2,
             boat1_base=0.30, boat1_tenkai=1.0,
             pred1_base=0.50, pred1_tenkai=1.0,
             are_index=44.0, buy_mode="hit"),

        # ⑥ RECモード: 高配当1号艇（base≥0.60 & あれ43〜47）
        dict(label="[REC] 高配当1号艇 REC参加（津・あれ45・base0.62）",
             venue="津", pred_rank1_boat=1,
             boat1_base=0.62, boat1_tenkai=0.85,
             pred1_base=0.62, pred1_tenkai=0.85,
             are_index=45.0, buy_mode="rec"),

        # ⑦ RECモード: 中立他艇 遠隔日前
        dict(label="[REC] 中立他艇 遠隔日前（津・days=25）",
             venue="津", pred_rank1_boat=3,
             boat1_base=0.30, boat1_tenkai=1.0,
             pred1_base=0.40, pred1_tenkai=1.0,
             are_index=44.0, buy_mode="rec",
             days_before=25),
    ]
    for ex in examples:
        label = ex.pop("label")
        pat = classify_race(**ex)
        print(f"\n  【{label}】")
        if pat:
            skip_mark = "🚫 見送り推奨" if (pat.points == 0) else "✅ 買い推奨"
            print(f"    {skip_mark}")
            print(f"    パターン    : {pat.name}")
            print(f"    推奨点数    : {pat.points}点")
            print(f"    期待回収率  : {pat.expected_roi}%")
            print(f"    理由        : {pat.description}")
            if pat.pass_reason:
                print(f"    見送り理由  : {pat.pass_reason[:100]}")
            print(f"    プレミアム  : {pat.flags.premium_zone}")
            print(f"    遠隔日前    : {pat.flags.distant_days}")
            print(f"    HD1フィルタ : {pat.flags.hd1_filter or 'N/A'}")
        else:
            print("    → 除外会場のため購入しない")

    # ── v6.0 vs v5.0 設計差分サマリー ──
    print("\n  ── v6.0 vs v5.0 設計差分サマリー ───────────────────────")
    print("  変更点                       | v5.0              | v6.0")
    print("  " + "─" * 60)
    print("  SS base幅                    | 0.45〜0.55        | 0.43〜0.57（±0.02拡張）")
    print("  HIT参加会場                  | 全full会場         | 優良6会場のみ")
    print("  HIT あれ上限                 | 55（SS他艇のみ）   | 50（全パターン）")
    print("  高配当1号艇 HIT              | buy/quasi/skipで分類| 全スキップ")
    print("  高配当1号艇 REC              | あれ46〜48         | あれ43〜47（少し広げる）")
    print("  中立他艇 HIT                 | 通常参加           | 全スキップ")
    print("  買い目下限（HIT）            | なし               | 5点保証")
    print("  期待的中率 HIT               | 〜30%前後          | 44〜47%")
    print("  期待回収率                   | 〜110%             | ≥200%")
