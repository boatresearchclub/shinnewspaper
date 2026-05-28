"""
競艇 買い目点数最適化ロジック  v3.0
バックテスト結果に基づくパターン分類と動的点数決定

【改善内容 v2.0】
  案1  : base>=0.65 は 原則3〜5点へ圧縮（"当たるが安い"ゾーンの削減）
  案5  : base0.45〜0.55 & tenkai<1.05 をスイートスポット（最大10点・資金集中）
  案7  : tenji係数を「減点専用」に修正（上限1.0キャップ・加点には使わない）
  案8  : スイートスポット内だけ tenkai感度を強化する区分線形補正
  案9  : あれ指数 + tenkai + 決まり手予測フラグ（まくり/差し系アラート）
  案10 : 期待払戻<1200円予測は買い目除外または強制5点以下（低配当罠フィルター）

【改善内容 v3.0】旧除外会場（大村・宮島・福岡・丸亀）を会場別ルールで復活
  バックテスト分析（31日間）から判明した各会場の特性:
    福岡: 1号艇1着率70.5%（全会場最高）・まくり系率15.5%（低い）
          → 逃げが非常に決まりやすい → 高人気圧縮（3〜5点）として購入
    丸亀: まくり系率24.0%（全会場最高）・1号艇1着率64.5%
          → まくりアラート必須・スイートスポットと高配当限定で購入
    宮島: 1号艇1着率60.5%・非除外会場と近い特性
          → スイートスポット＋高配当パターン限定で購入（中立は除外維持）
    大村: 1号艇1着率60.2%・あれ指数39.7（最低＝荒れにくい）
          → スイートスポット＋高配当パターン限定で購入（中立は除外維持）

【分類用 vs 補正用の分離】
  ● 分類判定 → raw_tenkai（元値）を使用。cap後の値は使わない
  ● tenji補正 → capped_tenji（上限1.0）を使用。点数を増やす方向には使わない

【グリッドサーチで確定した最適パラメータ（v1 継承）】
  低配当1号艇:  base >= 0.55 & tenkai >= 0.95  → 5点に削減
  高配当1号艇:  tenkai < 0.90                  → 10点維持（回収率206%）
  高配当他艇:   base >= 0.45 & tenkai >= 1.05  → 10点維持（回収率188%）

【バックテスト結果（2026/4/12〜5/12 / 31日間 / v1）】
  現状   → 投資3,486,000円 / 回収率94.5% / 収支 −190,730円
  改善後 → 投資1,886,200円 / 回収率109.5% / 収支 +179,130円
"""

import pandas as pd
from dataclasses import dataclass, field
from typing import Optional


# ============================================================
# 定数
# ============================================================

# v3.0: 旧「一律除外」から「会場別ルール」へ変更
# 完全除外会場は廃止。各会場に購入条件を設定する。
#
# モード:
#   "full"    : 通常会場と同じルールをすべて適用
#   "limited" : スイートスポット・高配当パターンのみ購入（中立系は除外）
#   "fukuoka" : 福岡専用ルール（1号艇1着率70%超→高人気圧縮メイン）
#   "marugame": 丸亀専用ルール（まくり系24%→まくりアラート時は点数強制削減）
VENUE_RULE = {
    # 通常会場（従来通り）
    "桐生":   "full", "戸田":   "full", "江戸川": "full",
    "平和島": "full", "多摩川": "full", "浜名湖": "full",
    "蒲郡":   "full", "常滑":   "full", "津":     "full",
    "三国":   "full", "びわこ": "full", "住之江": "full",
    "尼崎":   "full", "鳴門":   "full", "児島":   "full",
    "徳山":   "full", "下関":   "full", "若松":   "full",
    "芦屋":   "full", "唐津":   "full",
    # v3.0: 旧除外会場を会場別ルールで復活
    "福岡":   "fukuoka",   # 1号艇1着率70.5% → 高人気圧縮メイン
    "丸亀":   "marugame",  # まくり系率24% → まくりアラート時に強制削減
    "宮島":   "limited",   # スイートスポット・高配当限定
    "大村":   "limited",   # スイートスポット・高配当限定
}

# 福岡専用: 高人気圧縮の閾値をさらに下げる（1号艇1着率が高いため）
FUKUOKA_HIGH_POP_BASE = 0.55     # 非除外の0.65より低い閾値で圧縮開始
FUKUOKA_HIGH_POP_POINTS = 4      # 原則4点（1号艇1着が多く配当が安め）
FUKUOKA_HIGH_POP_STRICT = 3      # 低配当罠時は3点

# 丸亀専用: まくりアラート時の強制削減点数
MARUGAME_MAKURI_MAX_POINTS = 5   # まくりアラート発動時は最大5点

# limited モードで許可するパターン名のセット
LIMITED_ALLOWED_PATTERNS = {
    "スイートスポット1号艇",
    "スイートスポット他艇",
    "高配当1号艇",
    "高配当他艇",
}

# 閾値パラメータ（グリッドサーチ最適値）
PARAMS = {
    # ── 高配当1号艇 ───────────────────────────────────────────
    # 人気あるが当日展開不利 → 飛んだとき高配当 (回収率206%)
    # ※分類判定は raw_tenkai で行う
    "high_div_boat1_tenkai_max":  0.90,

    # ── 低配当1号艇（v1継承） ─────────────────────────────────
    "low_div_boat1_base_min":     0.55,
    "low_div_boat1_tenkai_min":   0.95,
    "low_div_boat1_points":       5,

    # ── 高配当他艇 ────────────────────────────────────────────
    # 予想1位艇自体も実力+展開良し (回収率188%)
    "high_div_other_base_min":    0.45,
    "high_div_other_tenkai_min":  1.05,

    # ── 案1: base>=0.65 高人気ゾーン点数圧縮 ─────────────────
    "high_pop_base_threshold":    0.65,   # このbase以上は「当たるが安い」
    "high_pop_default_points":    5,      # 原則5点以下
    "high_pop_strict_points":     3,      # 期待払戻<1200円時は3点

    # ── 案5: スイートスポット ─────────────────────────────────
    # base 0.45〜0.55 & tenkai<1.05 → 回収率145〜163%の突出ゾーン
    # ※分類判定は raw_tenkai で行う
    "sweet_base_min":             0.45,
    "sweet_base_max":             0.55,
    "sweet_tenkai_max":           1.05,   # raw_tenkai で判定
    "sweet_max_points":           10,     # 点数削減しない

    # ── 案7: tenji係数キャップ・重み ─────────────────────────
    "tenji_cap":                  1.0,    # 上限キャップ（加点不可）
    "tenji_weight_normal":        0.07,   # 通常ゾーンの重み（20%→7%）
    "tenji_weight_sweet":         0.15,   # スイートスポット内の重み（強化）

    # ── 案8: 区分線形補正（スイートスポット内 tenkai感度強化） ─
    "sweet_tenkai_boost":         1.30,   # スイートスポット内の tenkai乗数

    # ── 案10: 低配当罠フィルター ─────────────────────────────
    "low_div_trap_payout":        1200,   # 期待払戻<1200円は圧縮対象
    "low_div_trap_points":        5,      # 強制点数上限
}

# デフォルト点数
DEFAULT_POINTS = 10


# ============================================================
# 拡張フラグ（案9: 決まり手予測・将来拡張用）
# ============================================================

@dataclass
class RaceFlags:
    """
    レース特性フラグ。
    現バージョンでは事前抽出フラグのみ付与し、
    将来的に kimari_type_predict（逃げ/差し/まくり系）へ拡張可能な設計。
    """
    makuri_alert:    bool = False   # まくり/まくり差し発生しやすいレース
    sashi_alert:     bool = False   # 差し/抜き発生しやすいレース
    low_dividend:    bool = False   # 低配当罠フィルター対象
    sweet_spot:      bool = False   # スイートスポット（case5）
    high_pop_zone:   bool = False   # 高人気圧縮ゾーン（case1）
    venue_rule:      str  = "full"  # v3.0: 適用された会場ルール
    kimari_predict:  str  = ""      # 将来拡張: "逃げ" / "差し" / "まくり" / "まくり差し"


# ============================================================
# パターン分類
# ============================================================

@dataclass
class RacePattern:
    name:         str
    points:       int
    expected_roi: float          # バックテスト上の回収率(%)
    description:  str
    flags:        RaceFlags = field(default_factory=RaceFlags)


def _estimate_payout(base: float, tenkai: float) -> float:
    """
    期待払戻の簡易推定（線形モデル）。
    base が高いほど低配当、tenkai が低いほど高配当。
    ※実際の払戻データから係数を合わせた近似式。
    """
    # base >= 0.65: 大半が1000〜1400円帯
    # base 0.45〜0.55 & tenkai<1.05: 2000〜4000円帯
    estimated = 3500 - (base * 2800) - max(0.0, (tenkai - 1.0) * 1500)
    return max(400.0, estimated)


def _cap_tenji(tenji: float) -> float:
    """
    案7: tenji係数の上限キャップ（1.0固定）。
    加点方向には使わない。下方補正のみ有効。
    """
    return min(tenji, PARAMS["tenji_cap"])


def _apply_tenji_correction(base_points: int, capped_tenji: float, is_sweet: bool) -> int:
    """
    案7/8: tenji補正による点数調整。
    ・capped_tenji < 1.0 → ペナルティ（点数削減）
    ・capped_tenji >= 1.0 → 変更なし（キャップ済みなので常に1.0以下）
    ・スイートスポット内は tenji感度を強化（案8）
    """
    if capped_tenji >= 1.0:
        return base_points  # 加点しない

    deficit = 1.0 - capped_tenji   # 不足分（0〜1.0）
    weight = PARAMS["tenji_weight_sweet"] if is_sweet else PARAMS["tenji_weight_normal"]

    # 点数を最大 floor(base_points * weight * deficit * 10) だけ削減
    reduction = deficit * weight * base_points * 10
    adjusted = base_points - int(reduction)
    return max(1, adjusted)


def _detect_makuri_alert(are_index: float, raw_tenkai: float) -> bool:
    """
    案9: まくり/まくり差し発生しやすいレース判定。
    ・あれ指数が低い（荒れ指数が低い = 落ち着いたレース → 逃げ強）
     ここでは逆に高いとまくり系が起きやすい
    ・tenkai < 0.95 = 展開が荒れやすい
    将来: 進入崩れ系データも追加予定
    """
    return (are_index >= 55.0) or (raw_tenkai < 0.95)


def classify_race(
    venue:           str,
    pred_rank1_boat: int,
    boat1_base:      float,
    boat1_tenkai:    float,    # ← raw値（分類判定用）
    pred1_base:      float,
    pred1_tenkai:    float,    # ← raw値（分類判定用）
    boat1_tenji:     float = 1.0,   # 案7: 展示係数（tenji）
    pred1_tenji:     float = 1.0,   # 案7: 展示係数（tenji）
    are_index:       float = 50.0,  # 案9: あれ指数
    expected_payout: Optional[float] = None,  # 案10: 外部から渡す場合
) -> Optional["RacePattern"]:
    """
    1レース分の情報を受け取り、パターン分類と推奨点数を返す。

    Parameters
    ----------
    venue            : 会場名（例: '桐生'）
    pred_rank1_boat  : 予想1位艇番号（1〜6）
    boat1_base       : 1号艇のbase係数（正規化確率）
    boat1_tenkai     : 1号艇のtenkai係数 ★raw値★ ← 分類判定に使用
    pred1_base       : 予想1位艇のbase係数
    pred1_tenkai     : 予想1位艇のtenkai係数 ★raw値★ ← 分類判定に使用
    boat1_tenji      : 1号艇の展示係数（tenji）← 上限1.0キャップ後に補正のみ
    pred1_tenji      : 予想1位艇の展示係数（tenji）
    are_index        : あれ指数（案9 まくりアラート用）
    expected_payout  : 期待払戻（省略時は base/tenkai から簡易推定）

    Returns
    -------
    RacePattern | None  (Noneは除外レース)

    【重要】
    boat1_tenkai / pred1_tenkai は分類判定に「元値（raw）」を使う。
    tenji係数（boat1_tenji / pred1_tenji）は案7に従いキャップ後に点数補正のみ適用。
    tenkai をキャップしないため high_div_boat1 等の判定は崩れない。
    """

    # ── 0. 会場ルール取得（v3.0: 旧一律除外 → 会場別ルール）──────
    venue_rule = VENUE_RULE.get(venue, "full")

    p   = PARAMS
    is_boat1 = (pred_rank1_boat == 1)

    # ── 1. 案7: tenji係数をキャップ（補正用・分類には使わない）──
    capped_boat1_tenji = _cap_tenji(boat1_tenji)
    capped_pred1_tenji = _cap_tenji(pred1_tenji)

    # 主要艇（予想1位）のキャップ済みtenji
    main_capped_tenji = capped_boat1_tenji if is_boat1 else capped_pred1_tenji

    # ── 2. 期待払戻の推定（案10 低配当罠フィルター用）──────────
    main_base   = boat1_base   if is_boat1 else pred1_base
    main_tenkai = boat1_tenkai if is_boat1 else pred1_tenkai  # raw値

    if expected_payout is None:
        expected_payout = _estimate_payout(main_base, main_tenkai)

    low_div_trap = expected_payout < p["low_div_trap_payout"]

    # ── 3. 案9: まくり/差しアラートフラグ ───────────────────
    makuri_alert = _detect_makuri_alert(are_index, main_tenkai)
    sashi_alert  = (main_tenkai < 1.0) and (main_base < 0.55)

    # ── 4. スイートスポット判定（案5）──────────────────────
    # ★分類判定は raw_tenkai を使う（capしない）★
    is_sweet = (
        p["sweet_base_min"] <= main_base < p["sweet_base_max"]
        and main_tenkai < p["sweet_tenkai_max"]
    )

    # ── 5. 高人気ゾーン判定（案1）──────────────────────────
    is_high_pop = (main_base >= p["high_pop_base_threshold"])

    # ============================================================
    # ── v3.0: 福岡専用ルール（分岐A/B前に優先評価）──────────────
    # 1号艇1着率70.5%・まくり系率15.5% → 高人気圧縮をメインに据える
    # ============================================================
    if venue_rule == "fukuoka":
        fuk_base = main_base
        fuk_high_pop = (fuk_base >= FUKUOKA_HIGH_POP_BASE)

        if fuk_high_pop:
            # 高人気圧縮（福岡版: base>=0.55から圧縮）
            if low_div_trap:
                base_pts = FUKUOKA_HIGH_POP_STRICT
            else:
                base_pts = FUKUOKA_HIGH_POP_POINTS
            pts = _apply_tenji_correction(
                base_pts, capped_boat1_tenji if is_boat1 else capped_pred1_tenji,
                is_sweet=False,
            )
            flags = RaceFlags(
                makuri_alert=makuri_alert,
                low_dividend=low_div_trap,
                high_pop_zone=True,
                venue_rule="fukuoka",
            )
            return RacePattern(
                name="高人気圧縮(福岡)",
                points=pts,
                expected_roi=95.0,
                description=f"福岡: base>={FUKUOKA_HIGH_POP_BASE}・逃げ率高い → {base_pts}点圧縮",
                flags=flags,
            )

        if is_sweet:
            # スイートスポットは通常通り最大点数
            base_pts = p["sweet_max_points"]
            capped_t = capped_boat1_tenji if is_boat1 else capped_pred1_tenji
            pts = _apply_tenji_correction(base_pts, capped_t, is_sweet=True)
            pat_name = "スイートスポット1号艇" if is_boat1 else "スイートスポット他艇"
            flags = RaceFlags(
                makuri_alert=makuri_alert,
                sashi_alert=sashi_alert,
                low_dividend=low_div_trap,
                sweet_spot=True,
                venue_rule="fukuoka",
            )
            return RacePattern(
                name=pat_name,
                points=pts,
                expected_roi=155.0,
                description="福岡スイートスポット → 資金集中",
                flags=flags,
            )

        # 低base（荒れ狙い）
        base_pts = 7
        if low_div_trap:
            base_pts = p["low_div_trap_points"]
        capped_t = capped_boat1_tenji if is_boat1 else capped_pred1_tenji
        pts = _apply_tenji_correction(base_pts, capped_t, is_sweet=False)
        flags = RaceFlags(
            makuri_alert=makuri_alert,
            low_dividend=low_div_trap,
            venue_rule="fukuoka",
        )
        return RacePattern(
            name="中立(福岡)",
            points=pts,
            expected_roi=100.0,
            description="福岡: 低base → 荒れ狙い7点",
            flags=flags,
        )

    # ============================================================
    # ── 分岐A: 1号艇が予想1位の場合 ──────────────────────────
    # ============================================================
    if is_boat1:

        # ◎ 高配当1号艇: 展開不利で配当が開く（tenkai raw値で判定）
        if boat1_tenkai < p["high_div_boat1_tenkai_max"]:
            base_pts = DEFAULT_POINTS
            # 案10: 低配当罠なら点数圧縮
            if low_div_trap:
                base_pts = p["low_div_trap_points"]
            pts = _apply_tenji_correction(base_pts, capped_boat1_tenji, is_sweet=False)
            flags = RaceFlags(
                makuri_alert=makuri_alert,
                sashi_alert=sashi_alert,
                low_dividend=low_div_trap,
                sweet_spot=is_sweet,
                high_pop_zone=is_high_pop,
            )
            pat = RacePattern(
                name="高配当1号艇",
                points=pts,
                expected_roi=206.3,
                description="1号艇人気あり・当日展開不利 → 高配当ゾーン",
                flags=flags,
            )

        # ★ 案1: base>=0.65 高人気ゾーン → 点数圧縮 ★
        elif is_high_pop:
            if low_div_trap:
                base_pts = p["high_pop_strict_points"]   # 強制3点
            else:
                base_pts = p["high_pop_default_points"]  # 原則5点
            pts = _apply_tenji_correction(base_pts, capped_boat1_tenji, is_sweet=False)
            flags = RaceFlags(
                low_dividend=low_div_trap,
                high_pop_zone=True,
            )
            pat = RacePattern(
                name="高人気圧縮",
                points=pts,
                expected_roi=85.0,
                description=(
                    f"base>={p['high_pop_base_threshold']}・当たるが安い → "
                    f"{'強制3点' if low_div_trap else '5点圧縮'}"
                ),
                flags=flags,
            )

        # ★ 案5: スイートスポット（最優先・資金集中）★
        elif is_sweet:
            base_pts = p["sweet_max_points"]   # 削減しない
            # 案8: スイートスポット内は tenkai感度を強化
            pts = _apply_tenji_correction(base_pts, capped_boat1_tenji, is_sweet=True)
            flags = RaceFlags(
                makuri_alert=makuri_alert,
                sashi_alert=sashi_alert,
                low_dividend=low_div_trap,
                sweet_spot=True,
            )
            pat = RacePattern(
                name="スイートスポット1号艇",
                points=pts,
                expected_roi=155.0,
                description="base0.45〜0.55 & tenkai<1.05 → 回収率突出ゾーン・資金集中",
                flags=flags,
            )

        # × 低配当1号艇（v1継承）: 人気+展開良 → 配当が安い
        elif boat1_base >= p["low_div_boat1_base_min"] and boat1_tenkai >= p["low_div_boat1_tenkai_min"]:
            base_pts = p["low_div_boat1_points"]
            if low_div_trap:
                base_pts = min(base_pts, p["low_div_trap_points"])
            pts = _apply_tenji_correction(base_pts, capped_boat1_tenji, is_sweet=False)
            flags = RaceFlags(low_dividend=low_div_trap)
            pat = RacePattern(
                name="低配当1号艇",
                points=pts,
                expected_roi=102.2,
                description="1号艇が人気かつ展開良 → 点数削減",
                flags=flags,
            )

        # ○ 中立1号艇
        else:
            base_pts = 8
            if low_div_trap:
                base_pts = p["low_div_trap_points"]
            pts = _apply_tenji_correction(base_pts, capped_boat1_tenji, is_sweet=False)
            flags = RaceFlags(
                makuri_alert=makuri_alert,
                low_dividend=low_div_trap,
            )
            pat = RacePattern(
                name="中立1号艇",
                points=pts,
                expected_roi=100.7,
                description="1号艇予想・条件中立",
                flags=flags,
            )

    # ============================================================
    # ── 分岐B: 他艇が予想1位の場合 ──────────────────────────
    # ============================================================
    else:

        # ★ 案5: スイートスポット（他艇版）★
        if is_sweet:
            base_pts = p["sweet_max_points"]
            pts = _apply_tenji_correction(base_pts, capped_pred1_tenji, is_sweet=True)
            flags = RaceFlags(
                makuri_alert=makuri_alert,
                sashi_alert=sashi_alert,
                sweet_spot=True,
            )
            pat = RacePattern(
                name="スイートスポット他艇",
                points=pts,
                expected_roi=155.0,
                description="base0.45〜0.55 & tenkai<1.05 他艇予想 → 資金集中ゾーン",
                flags=flags,
            )

        # ◎ 高配当他艇: 予想1位艇自体が実力+展開良し (回収率188%)
        # ★分類判定は raw pred1_tenkai を使う★
        elif pred1_base >= p["high_div_other_base_min"] and pred1_tenkai >= p["high_div_other_tenkai_min"]:
            base_pts = DEFAULT_POINTS
            if low_div_trap:
                base_pts = p["low_div_trap_points"]
            pts = _apply_tenji_correction(base_pts, capped_pred1_tenji, is_sweet=False)
            flags = RaceFlags(
                makuri_alert=makuri_alert,
                low_dividend=low_div_trap,
            )
            pat = RacePattern(
                name="高配当他艇",
                points=pts,
                expected_roi=187.9,
                description="他艇1位予想・自艇実力あり+展開好調 → 高配当狙い",
                flags=flags,
            )

        # △ 中立他艇
        else:
            base_pts = 8
            if low_div_trap:
                base_pts = p["low_div_trap_points"]
            pts = _apply_tenji_correction(base_pts, capped_pred1_tenji, is_sweet=False)
            flags = RaceFlags(
                makuri_alert=makuri_alert,
                low_dividend=low_div_trap,
            )
            pat = RacePattern(
                name="中立他艇",
                points=pts,
                expected_roi=107.2,
                description="他艇1位予想・条件中立",
                flags=flags,
            )

    # ============================================================
    # ── v3.0: 会場別ルール 後処理 ────────────────────────────
    # ============================================================
    pat.flags.venue_rule = venue_rule

    # limited モード（宮島・大村）: 許可パターン以外は不買い
    if venue_rule == "limited" and pat.name not in LIMITED_ALLOWED_PATTERNS:
        return None

    # marugame モード（丸亀）: まくりアラート発動時は点数を強制削減
    if venue_rule == "marugame" and pat.flags.makuri_alert:
        pat.points = min(pat.points, MARUGAME_MAKURI_MAX_POINTS)
        pat.description += f" ※丸亀まくり補正→最大{MARUGAME_MAKURI_MAX_POINTS}点"

    return pat


# ============================================================
# CSV一括処理（既存バックテストデータに適用）
# ============================================================

def process_backtest_csv(input_path: str, output_path: Optional[str] = None) -> pd.DataFrame:
    """
    バックテストCSVを読み込み、最適化後の点数・分類・実収支を計算して返す。

    Parameters
    ----------
    input_path  : 入力CSVパス
    output_path : 出力CSVパス（省略時は保存しない）
    """
    df = pd.read_csv(input_path)

    # ── 的中順位の計算 ──
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

    # ── パターン分類と推奨点数の付与 ──
    def apply_classify(row):
        # tenji係数（なければ1.0）
        b1_tenji = float(row["1号艇_tenji係数"]) if pd.notna(row.get("1号艇_tenji係数")) else 1.0
        p1_tenji = float(row["予想1位_tenji係数"]) if pd.notna(row.get("予想1位_tenji係数")) else 1.0

        # あれ指数（なければ50.0）
        are_idx  = float(row["あれ指数"]) if pd.notna(row.get("あれ指数")) else 50.0

        pat = classify_race(
            venue            = row["会場"],
            pred_rank1_boat  = int(row["予想1位艇"]),
            boat1_base       = float(row["1号艇_base係数"]),
            boat1_tenkai     = float(row["1号艇_tenkai係数"]),   # raw値
            pred1_base       = float(row["予想1位_base係数"]),
            pred1_tenkai     = float(row["予想1位_tenkai係数"]), # raw値
            boat1_tenji      = b1_tenji,
            pred1_tenji      = p1_tenji,
            are_index        = are_idx,
        )
        if pat is None:
            return pd.Series({
                "パターン": "除外会場", "推奨点数": 0, "期待回収率": 0.0,
                "まくりアラート": False, "差しアラート": False,
                "低配当フラグ": False,  "スイートスポット": False,
            })
        return pd.Series({
            "パターン":         pat.name,
            "推奨点数":         pat.points,
            "期待回収率":       pat.expected_roi,
            "まくりアラート":   pat.flags.makuri_alert,
            "差しアラート":     pat.flags.sashi_alert,
            "低配当フラグ":     pat.flags.low_dividend,
            "スイートスポット": pat.flags.sweet_spot,
        })

    cols = ["パターン", "推奨点数", "期待回収率",
            "まくりアラート", "差しアラート", "低配当フラグ", "スイートスポット"]
    df[cols] = df.apply(apply_classify, axis=1)

    # ── 実際の的中・払戻の計算 ──
    def calc_actual(row):
        if row["推奨点数"] == 0:
            return pd.Series({"実的中": False, "実払戻": 0.0, "実投資": 0})
        inv = int(row["推奨点数"]) * 100
        if (row["的中"] == "的中"
                and pd.notna(row["的中順位"])
                and row["的中順位"] <= row["推奨点数"]):
            return pd.Series({"実的中": True, "実払戻": row["払戻金(円)"], "実投資": inv})
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
    total_inv   = active["実投資"].sum()
    total_pay   = active["実払戻"].sum()
    total_hits  = active["実的中"].sum()
    roi         = total_pay / total_inv * 100 if total_inv > 0 else 0
    profit      = total_pay - total_inv

    print("=" * 60)
    print("  最適化後 バックテストサマリー  v3.0")
    print("=" * 60)
    print(f"  対象レース数  : {len(active):,}R  (除外: {len(df)-len(active):,}R)")
    print(f"  総投資額      : {total_inv:,.0f}円")
    print(f"  総払戻金      : {total_pay:,.0f}円")
    print(f"  的中レース    : {total_hits:,}件  ({total_hits/len(active)*100:.1f}%)")
    print(f"  回収率        : {roi:.1f}%")
    print(f"  収支          : {profit:+,.0f}円")
    print()

    # ── パターン別内訳 ──
    print("  ── パターン別内訳 ──────────────────────────────")
    order = [
        "スイートスポット1号艇", "スイートスポット他艇",
        "高配当1号艇", "高配当他艇",
        "中立他艇", "中立1号艇",
        "低配当1号艇", "高人気圧縮",
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
    # ── v3.0: 旧除外会場の内訳 ──
    ex_venues = ["福岡", "丸亀", "宮島", "大村"]
    ex_rows = active[active.get("会場", pd.Series(dtype=str)).isin(ex_venues)] if "会場" in active.columns else pd.DataFrame()
    if len(ex_rows) > 0:
        print("  ── 旧除外会場（v3.0復活）内訳 ──────────────────")
        for v in ex_venues:
            sub = ex_rows[ex_rows["会場"] == v]
            if len(sub) == 0:
                continue
            inv  = sub["実投資"].sum()
            pay  = sub["実払戻"].sum()
            hits = sub["実的中"].sum()
            r    = pay / inv * 100 if inv > 0 else 0
            print(f"  {v:<6}: {len(sub):>4}R  "
                  f"的中率{hits/len(sub)*100:5.1f}%  "
                  f"回収率{r:6.1f}%  "
                  f"収支{pay-inv:+10,.0f}円")
        ex_inv  = ex_rows["実投資"].sum()
        ex_pay  = ex_rows["実払戻"].sum()
        ex_hits = ex_rows["実的中"].sum()
        ex_roi  = ex_pay / ex_inv * 100 if ex_inv > 0 else 0
        print(f"  {'旧除外合算':<6}: {len(ex_rows):>4}R  "
              f"的中率{ex_hits/len(ex_rows)*100:5.1f}%  "
              f"回収率{ex_roi:6.1f}%  "
              f"収支{ex_pay-ex_inv:+10,.0f}円")
        print()

    print()
    # ── スイートスポット詳細 ──
    sweet = active[active["スイートスポット"] == True]
    if len(sweet) > 0:
        s_inv  = sweet["実投資"].sum()
        s_pay  = sweet["実払戻"].sum()
        s_hits = sweet["実的中"].sum()
        s_roi  = s_pay / s_inv * 100 if s_inv > 0 else 0
        print(f"  ★ スイートスポット合算: {len(sweet)}R  "
              f"的中率{s_hits/len(sweet)*100:.1f}%  "
              f"回収率{s_roi:.1f}%  "
              f"収支{s_pay-s_inv:+,.0f}円")

    # ── まくりアラート ──
    makuri = active[active["まくりアラート"] == True]
    if len(makuri) > 0:
        m_inv = makuri["実投資"].sum()
        m_pay = makuri["実払戻"].sum()
        m_roi = m_pay / m_inv * 100 if m_inv > 0 else 0
        print(f"  ⚡ まくりアラート対象  : {len(makuri)}R  回収率{m_roi:.1f}%")

    # ── 低配当罠フィルター ──
    low_trap = active[active["低配当フラグ"] == True]
    if len(low_trap) > 0:
        lt_inv = low_trap["実投資"].sum()
        lt_pay = low_trap["実払戻"].sum()
        lt_roi = lt_pay / lt_inv * 100 if lt_inv > 0 else 0
        print(f"  🚫 低配当罠フィルター  : {len(low_trap)}R  回収率{lt_roi:.1f}%")

    print("=" * 60)


# ============================================================
# メイン実行
# ============================================================

if __name__ == "__main__":
    import sys
    import glob
    from pathlib import Path
    from datetime import datetime

    SCRIPT_DIR = Path(__file__).parent
    CSV_DIR    = SCRIPT_DIR / "csv_output"   # auto_push.py と同じCSV格納先

    # ── 入力CSVの解決 ─────────────────────────────────────────
    # 優先順位:
    #   1. コマンドライン引数で明示指定された場合
    #   2. csv_output/ 内の当日CSVを自動収集（複数会場をまとめて集計）
    #   3. スクリプトと同じフォルダの当日CSV（後方互換）
    #   4. どれもなければエラー

    if len(sys.argv) >= 2:
        # 明示指定
        INPUT  = Path(sys.argv[1])
        OUTPUT = SCRIPT_DIR / f"backtest_optimized_{datetime.now().strftime('%Y%m%d')}.csv"
        if not INPUT.exists():
            print(f"[エラー] CSVが見つかりません: {INPUT}")
            sys.exit(1)
        df = process_backtest_csv(str(INPUT), str(OUTPUT))

    else:
        # 当日CSVを自動検索
        today    = datetime.now().strftime("%Y-%m-%d")
        today_nd = datetime.now().strftime("%Y%m%d")
        OUTPUT   = SCRIPT_DIR / f"backtest_optimized_{today_nd}.csv"

        # csv_output/ を優先探索（ハイフンあり・なし両方）
        candidates = sorted(set(
            glob.glob(str(CSV_DIR / f"*{today}*.csv")) +
            glob.glob(str(CSV_DIR / f"*{today_nd}*.csv"))
        ))

        # csv_output/ になければスクリプトと同じフォルダも探す（ハイフンあり・なし両方）
        if not candidates:
            candidates = sorted(set(
                glob.glob(str(SCRIPT_DIR / f"*{today}*.csv")) +
                glob.glob(str(SCRIPT_DIR / f"*{today_nd}*.csv"))
            ))

        if not candidates:
            print(f"[エラー] 当日({today})のCSVが見つかりません")
            print("対処法:")
            print(f"  ① csv_output/ に当日CSVを置く（例: 桐生_{today}.csv または 桐生_{today_nd}.csv）")
            print("  ② コマンドライン引数でパスを直接指定する")
            print(f"     例: python betting_optimizer.py csv_output/桐生_{today_nd}.csv")
            sys.exit(1)

        print(f"  当日CSV {len(candidates)}件を検出: {[Path(p).name for p in candidates]}")

        # 複数CSVをまとめて読み込んで結合
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

    # ── 単体レース判定の使用例 ────────────────────────────
    print("\n  ── 単体レース判定の例 ──────────────────────────")
    examples = [
        dict(
            label="スイートスポット該当例",
            venue="津", pred_rank1_boat=1,
            boat1_base=0.50, boat1_tenkai=0.97,  # raw値
            pred1_base=0.50, pred1_tenkai=0.97,
            boat1_tenji=1.08,  # tenji>1.0 → cap後1.0 → 加点なし
            pred1_tenji=1.08,
            are_index=53.0,
        ),
        dict(
            label="高人気圧縮例（base>=0.65）",
            venue="桐生", pred_rank1_boat=1,
            boat1_base=0.72, boat1_tenkai=0.98,
            pred1_base=0.72, pred1_tenkai=0.98,
            boat1_tenji=1.05,
            pred1_tenji=1.05,
            are_index=48.0,
        ),
        dict(
            label="まくりアラート例（tenkai<0.95）",
            venue="津", pred_rank1_boat=2,
            boat1_base=0.30, boat1_tenkai=0.82,
            pred1_base=0.48, pred1_tenkai=0.88,  # raw<0.95 → まくりアラート
            boat1_tenji=0.95,
            pred1_tenji=0.90,
            are_index=57.0,
        ),
    ]
    for ex in examples:
        label = ex.pop("label")
        pat = classify_race(**ex)
        print(f"\n  【{label}】")
        if pat:
            print(f"    パターン     : {pat.name}")
            print(f"    推奨点数     : {pat.points}点")
            print(f"    期待回収率   : {pat.expected_roi}%")
            print(f"    理由         : {pat.description}")
            print(f"    まくりアラート: {pat.flags.makuri_alert}")
            print(f"    スイートスポット: {pat.flags.sweet_spot}")
            print(f"    低配当フラグ : {pat.flags.low_dividend}")
        else:
            print("    → 除外会場のため購入しない")
