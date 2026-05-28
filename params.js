// params.js — 定数・パラメータ定義（sample.js から分離）
// ============================================================
// ── betting_optimizer.py 連動パラメータ ──────────────────────
// betting_optimizer.py (v6.0) が変わったらここだけ書き換える。
// ピックアップレースの「AI条件該当」バッジ判定がここを参照する。
// ============================================================
const BETTING_PARAMS = {
  // ★ HIT: 参加優良会場（hit_priority 会場のみ）
  hit_allowed_venues: new Set(['唐津','住之江','尼崎','桐生','びわこ','浜名湖']),

  // ★ 全モード: 完全除外会場（skip 会場）
  skip_venues: new Set(['宮島','大村','多摩川','鳴門']),

  // ★ HIT: あれ指数上限（これ超えたら HIT スキップ）
  are_hit_max: 50.0,

  // ★ SS条件 base幅（v6.0: 0.43〜0.57）
  sweet_base_min: 0.43,
  sweet_base_max: 0.57,
  sweet_tenkai_max: 1.05,

  // ★ 高配当1号艇判定閾値（boat1_tenkai がこれ未満 = 高配当1号艇）
  hd1_tenkai_max: 0.90,

  // ★ REC: 高配当1号艇参加条件
  hd1_rec_base_min: 0.60,
  hd1_rec_are_min:  43.0,
  hd1_rec_are_max:  47.0,

  // ★ SSプレミアム他艇あれ範囲（あれ45〜48）
  premium_are_min: 45.0,
  premium_are_max: 48.0,

  // ★ HIT: 買い目点数下限
  hit_min_points: 5,
};

/**
 * betting_optimizer.py の classify_race に相当する JS 版簡易判定。
 * ピックアップカードの「AI条件該当」バッジ専用。
 * 戻り値: { hit: bool, rec: bool }
 *
 * 引数:
 *   venue       : 会場名
 *   boat1Base   : 1号艇 base 確率（0〜1）
 *   boat1Tenkai : 1号艇 tenkai 係数
 *   pred1Boat   : AI予想1位の艇番（1〜6）
 *   pred1Base   : AI予想1位の base 確率
 *   pred1Tenkai : AI予想1位の tenkai 係数
 *   areIndex    : あれ指数
 */
function classifyRaceJS(venue, boat1Base, boat1Tenkai, pred1Boat, pred1Base, pred1Tenkai, areIndex) {
  const bp = BETTING_PARAMS;

  // 除外会場は両モードとも不参加
  if (bp.skip_venues.has(venue)) return { hit: false, rec: false };

  const isBoat1   = (pred1Boat === 1);
  const mainBase  = isBoat1 ? boat1Base   : pred1Base;
  const mainTenkai = isBoat1 ? boat1Tenkai : pred1Tenkai;

  // SS条件
  const isSweet = (mainBase >= bp.sweet_base_min && mainBase < bp.sweet_base_max)
               && (mainTenkai < bp.sweet_tenkai_max);

  // SSプレミアム他艇（!isBoat1 & SS & あれ45〜48）
  const isPremium = !isBoat1 && isSweet
                 && areIndex >= bp.premium_are_min && areIndex <= bp.premium_are_max;

  // 高配当1号艇（boat1_tenkai < 0.90）
  const isHD1 = isBoat1 && boat1Tenkai < bp.hd1_tenkai_max;

  // ── HIT 判定 ──────────────────────────────────────────────
  let hit = false;
  if (bp.hit_allowed_venues.has(venue)) {
    // あれ上限チェック（プレミアムは例外通過）
    const areOk = isPremium || areIndex <= bp.are_hit_max;
    if (areOk) {
      if (isPremium)       hit = true;   // SSプレミアム他艇: 最優先
      else if (isHD1)      hit = false;  // 高配当1号艇: HIT全スキップ
      else if (isSweet)    hit = true;   // SS1号艇 or SS他艇
      else if (!isBoat1)   hit = false;  // 中立他艇: HIT全スキップ
      else                 hit = true;   // その他1号艇系（低配当・高人気・中立）
    }
  }

  // ── REC 判定 ──────────────────────────────────────────────
  // REC は skip_venues 以外は基本参加（高配当1号艇は条件付き）
  let rec = true;
  if (isHD1) {
    // base≥0.60 & あれ43〜47 のみ参加
    rec = (boat1Base >= bp.hd1_rec_base_min)
       && (areIndex  >= bp.hd1_rec_are_min)
       && (areIndex  <= bp.hd1_rec_are_max);
  }

  return { hit, rec };
}

// ============================================================
const FINAL_PROB_WEIGHTS = {
  base:   1.0,  // 基準1着率  （長期統計）  ← 変更可: 0.5〜2.0 推奨
  tenkai: 1.0,  // 展開補正   （決まり手適性）← 変更可: 0.5〜2.0 推奨
  tenji:  0.5,  // 展示補正   （当日展示タイム）← 変更可: 0.0〜2.0 推奨（0=無効化）
  // [2026-05-13 修正] 1.0→0.3: wTenji=1.0 では展示ありで払戻が約20%低下していた
  // 原因: 1号艇baseProb高いレースで展示スコアがさらに上乗せされ低配当組合せを優先
  // バックテスト: 高配当1号艇 展示あり回収率 88.1%→推定103%台へ改善
  // [2026-05-14 修正] 0.3→0.5: 枠別指数テーブル導入に合わせて底上げ
  slit:   0.5,  // スリット補正基本強度 ← 変更可: 0.0〜1.0（arek連動で動的調整される）
  // [2026-05-20 追加] slit を arek 連動の動的重みに統合。荒れ会場ほど強く効く。
};

// ── スリット補正パラメータ ──
// [2026-05-18 修正] 評価軸を「今日の展示1周タイム差」に統一
//
// 【設計思想】
//   スリット戦の本質は「自艇が後艇より前に出られるか」。
//   旧設計の問題点:
//     ① _slitCoef（前艇比較）をペナルティにも流用 → 評価方向が曖昧
//     ② ST差にマスタ長期データを使用 → 今日の実態と乖離することがある
//   新設計:
//     ① 自艇ボーナス: 「自艇 vs 前艇」の1周タイム差で判定
//     ② ペナルティ:   「後艇 vs 自艇」の1周タイム差で独立して判定
//     ③ 後艇が自艇より遅い/同等 → ペナルティゼロ（不当なマイナスを防止）
//     ④ ST差（マスタ）は「まくりアラートボーナス」の強調にのみ補助的に使用
//
// スリット優劣スコア閾値（展示タイム差 + ST順差×0.02 の合算値）: 正値=自艇が優位=捲り有効
const SLIT_LAP_THRESHOLDS = [
  { min:  0.40, coef: 1.30 },  // 差0.4秒以上: 捲り強
  { min:  0.20, coef: 1.15 },  // 差0.2〜0.4秒: 捲り中
  { min: -0.20, coef: 1.00 },  // 差±0.2秒未満: 互角
  { min: -Infinity, coef: 0.90 },  // 差-0.2秒以下: 前艇有利
];
// スリット補正全体の適用強度（0=無効 / 1=フル）
const SLIT_WEIGHT = 0.5;  // ← 後方互換用（renderBuy では使用しない）
// [2026-05-20] renderBuy 内では calcDynamicWeights が返す wSlit を使用。
//              wSlit = FINAL_PROB_WEIGHTS.slit(0.5) ± arek連動調整（±0.3）
//              この定数はバックテスト用スクリプト等から参照される可能性があるため残す。

// ── 枠番別 展示感度テーブル ──
// [2026-05-18 修正] TENJI_WEIGHT_BY_COURSE → TENJI_SENSITIVITY_BY_COURSE に変更
// 旧: calcTenjiScore が返す係数に後付けで乗算するだけ（コース差が弱かった）
// 新: 合成スコアの平均乖離率に掛ける感度係数として calcTenjiScore 内部で使用
//     → 同じ乖離率でも枠番によって係数の伸びが変わる
//     → 1号艇と6号艇が同タイムなら6号艇を高評価（外枠ほど展示の価値が高い）
//
// 設計方針:
//   1枠: イン優位はコース補正が支配的。展示が突き抜けても評価を抑制。
//   2枠: 差しに展示が絡むが1枠に次いで抑制。
//   3枠: 差し・まくり差しの主力。展示差が着順に直結。
//   4枠: まくり最多コース。展示最重要。
//   5枠: まくり一発。外枠で同タイムなら内枠より高評価。
//   6枠: 距離ロス大きいが展示突き抜けなら評価。1枠より明確に高く。
const TENJI_SENSITIVITY_BY_COURSE = {
  1: 3.0,   // 抑制: イン優位はコース補正で十分
  2: 5.0,   // やや抑制
  3: 9.0,   // 標準〜強め
  4: 11.0,  // 最重要コース
  5: 10.0,  // 外枠まくり評価
  6: 7.0,   // 1枠より明確に高く、ただし距離ロス分を控えめに
};

// ── arek_score連動 動的wBase/wTenkai 算出 ──
// 荒れやすい会場（arek高）ほど展開の読みが重要 → wTenkai を増やし wBase を下げる。
// 鉄板会場（arek低）ほど長期統計が支配的    → wBase を増やし wTenkai を抑える。
// 実データ範囲: 39（大村）〜 60（戸田）を 0〜1 に正規化し最大±0.3 調整。
// wTenji は arek と無関係（当日展示はどの会場でも同等の情報量）のため固定。
//
// 例: 戸田(arek=60) → arekNorm=1.0 → wBase=0.7, wTenkai=1.3
//     大村(arek=39) → arekNorm=0.0 → wBase=1.3, wTenkai=0.7
//     平均(arek=50) → arekNorm=0.52 → wBase≈1.0, wTenkai≈1.0
const AREK_WEIGHT_RANGE   = 0.3;  // 調整幅上限（上げる側・下げる側ともに）
const AREK_SCORE_MIN      = 39;   // 最小実測値（大村）
const AREK_SCORE_MAX      = 60;   // 最大実測値（戸田）

function calcDynamicWeights(arek) {
  const base   = FINAL_PROB_WEIGHTS.base   ?? 1.0;
  const tenkai = FINAL_PROB_WEIGHTS.tenkai ?? 1.0;
  const tenji  = FINAL_PROB_WEIGHTS.tenji  ?? 1.0;
  // [2026-05-20 追加] slit を arek 連動化
  // 荒れ会場（arek高）ほどスリット戦になりやすくスリット補正が重要になる。
  // 鉄板会場（arek低）ではスリット差よりコース利益が支配的なため補正を弱める。
  // 調整幅は wBase/wTenkai と同じ AREK_WEIGHT_RANGE（±0.3）を使用。
  const slitBase = FINAL_PROB_WEIGHTS.slit ?? 0.5;
  // [2026-05-20 追加] arek 範囲外チェック
  // AREK_SCORE_MIN/MAX は実測会場データ（大村39〜戸田60）に基づく定数。
  // この範囲を外れた arek 値が来ても Math.max/min でクリップするため計算は正常に動作するが、
  // 想定外の会場・特殊開催の場合は補正が歪むため警告をコンソールに出す。
  if(typeof arek === 'number' && isFinite(arek)){
    if(arek < AREK_SCORE_MIN){
      console.warn(
        `[calcDynamicWeights] arek(${arek}) が最小値 AREK_SCORE_MIN(${AREK_SCORE_MIN}) を下回っています。` +
        `会場名を確認し、必要であれば AREK_SCORE_MIN を更新してください。`
      );
    } else if(arek > AREK_SCORE_MAX){
      console.warn(
        `[calcDynamicWeights] arek(${arek}) が最大値 AREK_SCORE_MAX(${AREK_SCORE_MAX}) を上回っています。` +
        `会場名を確認し、必要であれば AREK_SCORE_MAX を更新してください。`
      );
    }
  } else {
    console.warn(`[calcDynamicWeights] arek が数値ではありません（値: ${arek}）。デフォルト重みを使用します。`);
  }
  const arekNorm = Math.max(0, Math.min(
    (arek - AREK_SCORE_MIN) / (AREK_SCORE_MAX - AREK_SCORE_MIN), 1
  ));
  // 荒れるほど: wBase 下がる / wTenkai 上がる / wSlit 上がる
  const adj = (arekNorm - 0.5) * 2 * AREK_WEIGHT_RANGE;  // -0.3 〜 +0.3
  return {
    wBase:   Math.max(0.1, base     - adj),
    wTenkai: Math.max(0.1, tenkai   + adj),
    wTenji:  tenji,  // arek非連動（当日展示はどの会場でも同等の情報量）
    wSlit:   Math.max(0.0, Math.min(1.0, slitBase + adj)),  // 0.0〜1.0 にクリップ
  };
}
