// ============================================================
const FINAL_PROB_WEIGHTS = {
  base:   1.0,  // 基準1着率  （長期統計）  ← 変更可: 0.5〜2.0 推奨
  tenkai: 1.0,  // 展開補正   （決まり手適性）← 変更可: 0.5〜2.0 推奨
  tenji:  0.5,  // 展示補正   （当日展示タイム）← 変更可: 0.0〜2.0 推奨（0=無効化）
  // [2026-05-13 修正] 1.0→0.3: wTenji=1.0 では展示ありで払戻が約20%低下していた
  // 原因: 1号艇baseProb高いレースで展示スコアがさらに上乗せされ低配当組合せを優先
  // バックテスト: 高配当1号艇 展示あり回収率 88.1%→推定103%台へ改善
  // [2026-05-14 修正] 0.3→0.5: 枠別指数テーブル導入に合わせて底上げ
};

// ── スリット補正パラメータ ──
// 前艇（枠番-1）との ST差・展示タイム差から捲り/前艇有利を判定する。
// 「後艇が前艇より有利」な場合に後艇を加点、前艇を減点する。
//
// ST差閾値（前艇ST - 後艇ST）: 正値=後艇が速い=捲り有効
const SLIT_ST_THRESHOLDS = [
  { min: 0.5,  coef: 1.30 },  // 差0.5以上: 捲り強
  { min: 0.3,  coef: 1.15 },  // 差0.3〜0.5: 捲り中
  { min: -0.3, coef: 1.00 },  // 差±0.3未満: 互角
  { min: -Infinity, coef: 0.90 },  // 差-0.3以下: 前艇有利
];
// 展示タイム差閾値（前艇展示 - 後艇展示）: 正値=後艇が速い
const SLIT_TENJI_THRESHOLDS = [
  { min: 0.10,  coef: 1.20 },
  { min: 0.05,  coef: 1.10 },
  { min: -0.05, coef: 1.00 },
  { min: -Infinity, coef: 0.90 },
];
// スリット補正全体の適用強度（0=無効 / 1=フル）
const SLIT_WEIGHT = 0.5;  // ← 変更可: 0.0〜1.0

// ── 枠番別 展示補正指数テーブル ──
// FINAL_PROB_WEIGHTS.tenji をベースに枠番ごとに調整する乗数。
// 1〜2枠: コース優位が支配的なため展示の影響を抑制。
// 3〜5枠: 差し・まくりの爆発力に直結するため強めに効かせる。
// 6枠:    まくり一発狙いで展示差が出やすいが6枠自体の勝率が低いため中程度。
// 最終的な指数 = FINAL_PROB_WEIGHTS.tenji × TENJI_WEIGHT_BY_COURSE[枠番]
const TENJI_WEIGHT_BY_COURSE = {
  1: 0.6,  // イン有利はコース補正で十分、展示は補助的
  2: 0.8,  // 差しに展示が絡むが1枠に次いで抑制
  3: 1.3,  // 差し・まくり差しの主力、展示差が着順に直結
  4: 1.4,  // まくり・まくり差し最多コース、展示最重要
  5: 1.3,  // まくり一発、外枠でも展示良ければ上位に
  6: 1.0,  // まくり狙いだが距離ロスが大きく控えめ
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
  const arekNorm = Math.max(0, Math.min(
    (arek - AREK_SCORE_MIN) / (AREK_SCORE_MAX - AREK_SCORE_MIN), 1
  ));
  // 荒れるほど: wBase 下がる / wTenkai 上がる
  const adj = (arekNorm - 0.5) * 2 * AREK_WEIGHT_RANGE;  // -0.3 〜 +0.3
  return {
    wBase:   Math.max(0.1, base   - adj),
    wTenkai: Math.max(0.1, tenkai + adj),
    wTenji:  tenji,  // arek非連動
  };
}

// ── 買い目確率フィルター閾値 ──
// この確率（3連単推定）を下回る買い目を除外する。
// スライダーUIから変更可能。単位: % (例: 2.0 → 2%)
let BUY_PROB_THRESHOLD = 2.0;

// ── 的中重視: 1着軸を1艇固定にするための乖離率閾値 ──
// final_prob 1位と2位の差がこの値（%）以上のとき、1位艇を1艇固定軸として組み立てる。
// 下回る場合は僅差2頭軸（isDualAxis）として2軸展開する。
// 根拠: 全国平均1コース確率≒50%, 2コース≒15% → 典型的な「明確な軸」レースで差は15%前後。
//       10%では拮抗レースでも固定軸になりすぎ回収悪化、15%では条件過剰で殆ど非該当。
//       12% = 1位の確率が2位の約1.25倍以上を「明確な1艇軸」と定義する仮置き値。
//       バックテスト後に調整すること（推奨範囲: 8〜15%）。
let DIVERGENCE_THRESHOLD_HIT = 12.0; // 単位: % ← スライダーUIから変更可




// ══════════════════════════════════════════════════════════════════
// フェーズ2: data/*.json を fetch して埋め込み変数にマージするローダー
//
// 設計方針:
//   - 埋め込み変数（RESULT_DATA / ALL_DATA_HISTORY）はそのまま残す
//     → 埋め込み済みデータが既にあれば即座に表示できる
//   - fetch完了後に変数へマージ → 過去日数が増えても HTML は軽量
//   - fetch失敗しても埋め込みデータで動作継続（フォールバック保証）
//   - IS_SERVER 環境では fetch を行わない（ローカルサーバーのAPIを使うため）
// ══════════════════════════════════════════════════════════════════

// フェーズ2: data/ ディレクトリのベースURL（index.htmlと同階層）
const DATA_BASE_URL = (function() {
  const base = location.href.replace(/\/[^\/]*$/, '');
  return base + '/data';
})();

// フェーズ2ローダー: data/index.json を先にfetchして存在する日付だけ並列fetch
async function fetchAndMergeJsonData() {
  // ローカル環境ではfetch不要（埋め込みデータで動作）
  if (location.hostname === 'localhost' || location.hostname === '127.0.0.1') {
    return;
  }

  // ── fetchヘルパー: 失敗しても null を返す ──
  async function safeFetch(url) {
    try {
      const res = await fetch(url, { cache: 'no-store' });
      if (!res.ok) return null;
      return await res.json();
    } catch (e) {
      return null;
    }
  }

  // ① data/index.json を先にfetchして存在する日付リストを取得
  const idx = await safeFetch(`${DATA_BASE_URL}/index.json`);
  if (!idx) {
    // index.json がなければ何もしない（フェーズ1未完了 or 初回push前）
    console.log('[fetchAndMergeJsonData] data/index.json なし → スキップ');
    return;
  }

  const resultDates  = idx.result_dates  || [];   // ["20260512", "20260511", ...]
  const historyDates = idx.history_dates || [];

  // ② RESULT_DATA: index.json に記録された日付だけfetch（404が出ない）
  const resultFetches = resultDates.map(nd =>
    safeFetch(`${DATA_BASE_URL}/result_${nd}.json`).then(data => {
      if (!data) return;
      for (const [key, val] of Object.entries(data)) {
        // key = "{slug}_{rno}" → RESULT_DATA キー = "{slug}_{YYYYMMDD}_{rno}"
        const m = key.match(/^(.+)_(\d+)$/);
        const fullKey = m ? `${m[1]}_${nd}_${m[2]}` : `${key}_${nd}`;
        if (!RESULT_DATA[fullKey]) RESULT_DATA[fullKey] = val;
      }
    })
  );

  // ③ ALL_DATA_HISTORY: index.json に記録された日付だけfetch
  const historyFetches = historyDates.map(nd => {
    const dash = `${nd.slice(0,4)}-${nd.slice(4,6)}-${nd.slice(6,8)}`;
    return safeFetch(`${DATA_BASE_URL}/history_${nd}.json`).then(data => {
      if (!data) return;
      if (!ALL_DATA_HISTORY[dash]) {
        ALL_DATA_HISTORY[dash] = data;
      } else {
        // 会場単位で補完（埋め込みが空の会場のみ）
        for (const [venue, vdata] of Object.entries(data)) {
          if (!ALL_DATA_HISTORY[dash][venue]) {
            ALL_DATA_HISTORY[dash][venue] = vdata;
          }
        }
      }
    });
  });

  // ④ master_ext.json（MASTER_EXT が null の場合のみ上書き）
  const masterFetch = safeFetch(`${DATA_BASE_URL}/master_ext.json`).then(data => {
    if (data && !MASTER_EXT) MASTER_EXT = data;
  });

  // 全fetch並列実行（失敗しても続行）
  await Promise.allSettled([...resultFetches, ...historyFetches, masterFetch]);
  console.log('[fetchAndMergeJsonData] 完了');
}


// IS_SERVER: localhost以外（Netlify/GitHub Pages）では動的APIは使えないため
// ホスト名でランタイム判定する（auto_pushによるハードコード true を廃止）
const IS_SERVER = (location.hostname === 'localhost' || location.hostname === '127.0.0.1');
// APIサーバー疎通フラグ（初回チェック後に確定）
let _serverAvailable = IS_SERVER;
const PLAYER_ID_MAP = {};

// ============================================================
// アプリロジック（本番index.htmlと同じ）
// ============================================================
let DATA = null;
let selectedRace = 0;
let currentVenue = '';

function arekClass(v){ return v < 45 ? 'arek-lo' : v < 65 ? 'arek-md' : 'arek-hi'; }
function arekLabel(v){ return v < 45 ? '安定' : v < 65 ? '中荒れ' : '大荒れ'; }

function weightDots(w, max=3){
  let s='';
  for(let i=0;i<max;i++) s+=`<span class="wdot${i<w?'':' empty'}"></span>`;
  return `<div class="buy-weight">${s}</div>`;
}

const _tenjiCache = {};
(function(){
  for(const [key, val] of Object.entries(TENJI_DATA)){
    const normalized = key.replace(/_(\d{4})(\d{2})(\d{2})_/, '_$1-$2-$3_');
    _tenjiCache[normalized] = val;
  }
})();
function tenjiKey(venue, date, race){ return `${venue}_${date}_${race}`; }

function buildWeatherBar(rno){
  const SLUG = {
    "桐生":"kiryu","戸田":"toda","江戸川":"edogawa","平和島":"heiwajima",
    "多摩川":"tamagawa","浜名湖":"hamanako","蒲郡":"gamagori","常滑":"tokoname",
    "津":"tsu","三国":"mikuni","びわこ":"biwako","住之江":"suminoe",
    "尼崎":"amagasaki","鳴門":"naruto","丸亀":"marugame","児島":"kojima",
    "宮島":"miyajima","徳山":"tokuyama","下関":"shimonoseki","若松":"wakamatsu",
    "芦屋":"ashiya","福岡":"fukuoka","唐津":"karatsu","大村":"omura"
  };
  const slug   = SLUG[DATA.venue] || DATA.venue;
  const key    = tenjiKey(slug, DATA.date, rno);
  const cached = _tenjiCache[key];

  // ── 会場別スタートライン方向（ボートの進行方位角 °）──────────
  // 追い風 = 風がボートを後ろから押す（風向とボート進行が逆方向）
  // 風向き数値: 1=北(0°), 2=北北東(22.5°)... 時計回り16方位
  // 会場別スタートライン方向（ボートの進行方位角°）
  // ソース: 公式サイト実データの追い風/向かい風分析（2014-2022）から逆算
  // 追い風方向の逆がボート進行方向 = SL_DIR
  const SL_DIR = {
    "kiryu":       180,  // 桐生    南  （追い風=北）
    "toda":        135,  // 戸田    南東 （追い風=北西）
    "edogawa":      45,  // 江戸川  北東 （追い風=南西）
    "heiwajima":     0,  // 平和島  北  （追い風=南）
    "tamagawa":    270,  // 多摩川  西  （追い風=東）※変更なし
    "hamanako":      0,  // 浜名湖  北  （追い風=南）
    "gamagori":    225,  // 蒲郡    南西 （追い風=北東）
    "tokoname":    315,  // 常滑    北西 （追い風=南東）※変更なし
    "tsu":         315,  // 津      北西 （追い風=南東）
    "mikuni":      180,  // 三国    南  （追い風=北）
    "biwako":      180,  // びわこ  南  （追い風=北）
    "suminoe":     180,  // 住之江  南  （追い風=北）
    "amagasaki":   225,  // 尼崎    南西 （追い風=北東）
    "naruto":      135,  // 鳴門    南東 （追い風=北西）
    "marugame":      0,  // 丸亀    北  （追い風=南）
    "kojima":      180,  // 児島    南  （追い風=北）
    "miyajima":    225,  // 宮島    南西 （追い風=北東）
    "tokuyama":    315,  // 徳山    北西 （追い風=南東）
    "shimonoseki": 270,  // 下関    西  （追い風=東）※変更なし
    "wakamatsu":   180,  // 若松    南  （追い風=北）※変更なし
    "ashiya":      180,  // 芦屋    南  （若松隣接・地形推定）
    "fukuoka":     225,  // 福岡    南西 （博多湾・地形推定）
    "karatsu":     180,  // 唐津    南  （追い風=北、年間追い風多し）
    "omura":       270,  // 大村    西  （大村湾・地形推定）※変更なし
  };
  function windNumToDeg(n){ return ((n - 1) * 22.5) % 360; }
  function getWindType(windNum, slDeg){
    if(windNum == null || slDeg == null) return null;
    const windDeg = windNumToDeg(windNum);
    let diff = Math.abs(windDeg - slDeg) % 360;
    if(diff > 180) diff = 360 - diff;
    // diff≈0° → 風向=ボート進行方向 → 向かい風
    // diff≈180° → 風向=ボート逆方向 → 追い風
    if(diff <= 30)  return 'head';    // ±30°以内 = 向かい風
    if(diff >= 150) return 'tail';    // ±30°以内(逆) = 追い風
    // 横風: 符号付き差分で右/左を判定
    // signed 0〜180° → 風がボートの右側から来る（右横風）
    // signed 180〜360° → 風がボートの左側から来る（左横風）
    const signed = (windDeg - slDeg + 360) % 360;
    return signed < 180 ? 'cross_right' : 'cross_left';
  }
  const WIND_LABEL = { tail:'追い風', head:'向かい風', cross_right:'右横風', cross_left:'左横風' };
  // 矢印はスタートライン(右)に向かうボートを基準にした画面座標
  // ボート進行=→, 追い風=後ろから→, 向かい風=正面から←, 右横風=下から↑, 左横風=上から↓
  const WIND_ARROW = { tail:'→', head:'←', cross_right:'↑', cross_left:'↓' };

  // データ未取得 → 過去日なら「記録なし」、当日なら「取得待ち」
  if(!cached){
    const today = new Date().toISOString().slice(0,10);
    const isPastDay = DATA.date && DATA.date < today;
    const msg = isPastDay ? '記録なし' : '取得待ち';
    return `<div class="weather-bar"><span class="weather-bar-title">水面気象情報</span><div class="weather-bar-body"><span class="tenji-waiting" style="margin:0;padding:0;display:inline;font-size:11px">${msg}</span></div></div>`;
  }

  const w = {
    weather:       cached.__weather,
    weather_degree:cached.__weather_degree,
    water_degree:  cached.__water_degree,
    wind_speed:    cached.__wind_speed,
    wind_dir_num:  cached.__wind_direction,
    wind_dir_text: cached.__wind_direction_text,
    wave_height:   cached.__wave_height,
  };

  // キャッシュはあるが気象フィールドがすべて null
  if(Object.values(w).every(v => v == null)){
    return `<div class="weather-bar"><span class="weather-bar-title">水面気象情報</span><div class="weather-bar-body"><span class="tenji-waiting" style="margin:0;padding:0;display:inline;font-size:11px">取得待ち</span></div></div>`;
  }

  // 追い風/向かい風バッジ
  const windType  = getWindType(w.wind_dir_num, SL_DIR[slug] ?? null);
  const windBadge = windType
    ? `<span class="wind-badge ${windType}">${WIND_ARROW[windType]} ${WIND_LABEL[windType]}</span>`
    : '';

  const weatherIcon = {'晴':'☀️','曇':'☁️','雨':'🌧️','雪':'❄️'};
  const icon = weatherIcon[w.weather] || '🌤️';
  const row1 = [
    w.weather        != null ? `<div class="weather-item"><span class="wi-label">天候</span><span class="wi-val">${icon} ${w.weather}</span></div>` : '',
    w.weather_degree != null ? `<div class="weather-item"><span class="wi-label">気温</span><span class="wi-val">${w.weather_degree}℃</span></div>` : '',
    w.water_degree   != null ? `<div class="weather-item"><span class="wi-label">水温</span><span class="wi-val">${w.water_degree}℃</span></div>` : '',
  ].filter(Boolean).join('');
  const row2 = [
    w.wind_speed  != null ? `<div class="weather-item"><span class="wi-label">風速</span><span class="wi-val">${w.wind_speed}m/s${w.wind_dir_text ? ' ' + w.wind_dir_text : ''}${windBadge}</span></div>` : '',
    w.wave_height != null ? `<div class="weather-item"><span class="wi-label">波高</span><span class="wi-val">${w.wave_height}cm</span></div>` : '',
  ].filter(Boolean).join('');
  const weatherRows = [
    row1 ? `<div style="display:flex;align-items:center;justify-content:center;gap:16px;flex-wrap:wrap">${row1}</div>` : '',
    row2 ? `<div style="display:flex;align-items:center;justify-content:center;gap:16px;flex-wrap:wrap">${row2}</div>` : ''
  ].filter(Boolean).join('');
  return `<div class="weather-bar"><span class="weather-bar-title">水面気象情報</span><div class="weather-bar-body" style="flex-direction:column;gap:4px;align-items:center">${weatherRows}</div></div>`;
}

function buildCourseOrderBanner(rno, boats){
  // _tenjiCache から course/is_normal_course を読んで「進入変更」バナーを生成
  const SLUG2 = {
    "桐生":"kiryu","戸田":"toda","江戸川":"edogawa","平和島":"heiwajima",
    "多摩川":"tamagawa","浜名湖":"hamanako","蒲郡":"gamagori","常滑":"tokoname",
    "津":"tsu","三国":"mikuni","びわこ":"biwako","住之江":"suminoe",
    "尼崎":"amagasaki","鳴門":"naruto","丸亀":"marugame","児島":"kojima",
    "宮島":"miyajima","徳山":"tokuyama","下関":"shimonoseki","若松":"wakamatsu",
    "芦屋":"ashiya","福岡":"fukuoka","唐津":"karatsu","大村":"omura"
  };
  const slug2  = SLUG2[DATA.venue] || DATA.venue;
  const key2   = tenjiKey(slug2, DATA.date, rno);
  const cached2 = _tenjiCache[key2];
  if(!cached2) return '';  // 展示未取得 → バナーなし

  const cf2 = bn => cached2[String(bn)] ?? cached2[bn];

  // course が null の艇が1つでもあればコースデータなし → バナーなし
  const entries = boats.map(b => {
    const d = cf2(b.boat);
    const course = d?.course ?? null;
    // is_normal_course が明示されていればそちらを優先、
    // なければ「展示コース ≠ 枠番」で進入変更を判定
    const is_normal = d?.is_normal_course != null
      ? d.is_normal_course
      : (course != null ? course === b.boat : null);
    return { frame: b.boat, name: b.name, course, is_normal };
  });
  if(entries.some(e => e.course == null)) return '';

  const allNormal = entries.every(e => e.is_normal !== false);
  if(allNormal) return '';  // 全艇枠なり → バナー不要

  // コース順でソート（1コース→2→…）
  const sorted = [...entries].sort((a,b) => a.course - b.course);

  // ボートサークル
  const circle = (n) =>
    `<span class="boat-circle b${n}" style="width:20px;height:20px;font-size:10px;line-height:20px;display:inline-flex;align-items:center;justify-content:center;flex-shrink:0">${n}</span>`;

  // コース順に全艇の枠番サークルを並べる
  const orderHtml = sorted.map((e, i) =>
    `${i > 0 ? '<span class="cb-sep">›</span>' : ''}${circle(e.frame)}`
  ).join('');

  return `<div class="course-order-banner">
    <span class="cb-icon">⚠</span>
    <span class="cb-text">進入変更</span>
    <span class="cb-order">${orderHtml}</span>
  </div>`;
}

function buildTenjiSection(rno, boats){
  const SLUG = {
    "桐生":"kiryu","戸田":"toda","江戸川":"edogawa","平和島":"heiwajima",
    "多摩川":"tamagawa","浜名湖":"hamanako","蒲郡":"gamagori","常滑":"tokoname",
    "津":"tsu","三国":"mikuni","びわこ":"biwako","住之江":"suminoe",
    "尼崎":"amagasaki","鳴門":"naruto","丸亀":"marugame","児島":"kojima",
    "宮島":"miyajima","徳山":"tokuyama","下関":"shimonoseki","若松":"wakamatsu","芦屋":"ashiya",
    "福岡":"fukuoka","唐津":"karatsu","大村":"omura"
  };
  const slug   = SLUG[DATA.venue] || DATA.venue;
  const key    = tenjiKey(slug, DATA.date, rno);
  const cached = _tenjiCache[key];

  // 未取得の場合
  if(cached === undefined || cached === null){
    const rd = DATA.races[String(rno)];
    const timeStr = rd && rd.time;
    // 過去日かどうか判定（DATA.date が今日より前）
    const today = new Date().toISOString().slice(0,10);
    const isPastDay = DATA.date && DATA.date < today;
    let pastDeadline = isPastDay; // 過去日は無条件で「記録なし」
    if(!isPastDay && timeStr && /^\d{1,2}:\d{2}$/.test(timeStr.trim())){
      const now = new Date();
      const [h, m] = timeStr.trim().split(':').map(Number);
      const deadlineMin = h * 60 + m - 5;  // 締め切り5分前
      const nowMin = now.getHours() * 60 + now.getMinutes();
      pastDeadline = nowMin >= deadlineMin;
    }
    // 過去日または締め切り後は「展示情報がありません」
    const msg = pastDeadline ? '展示情報がありません' : '取得待ち';
    return `${buildWeatherBar(rno)}<div class="tenji-section">
      <div class="tenji-title">展示情報</div>
      <div style="background:var(--bg2)"><div class="tenji-waiting">${msg}</div></div>
    </div>`;
  }

  // 枠番キーは文字列で統一（Python側JSON → 文字列キー、数値/文字列どちらでも取得できるよう正規化）
  const cf = bn => cached[String(bn)] ?? cached[bn];
  const lap1vals   = boats.map(b=>cf(b.boat)?.lap1).filter(v=>v!=null);
  const mawarivals = boats.map(b=>cf(b.boat)?.mawari).filter(v=>v!=null);
  const chokuvals  = boats.map(b=>cf(b.boat)?.chokusen).filter(v=>v!=null);
  const tenjivals  = boats.map(b=>cf(b.boat)?.tenji).filter(v=>v!=null);
  const bestLap1   = lap1vals.length   ? Math.min(...lap1vals)   : null;
  const bestMawari = mawarivals.length ? Math.min(...mawarivals) : null;
  const bestChoku  = chokuvals.length  ? Math.min(...chokuvals)  : null;
  const bestTenji  = tenjivals.length  ? Math.min(...tenjivals)  : null;
  const rows = boats.map(bt => {
    const bn = bt.boat;
    const t  = cf(bn);
    if(!t) return `<tr><td>${bn}</td><td>${bt.name}</td><td colspan="5">—</td></tr>`;
    const f = (v, best) => v==null ? '—' : `<span class="${v===best?'tenji-best':''}">${v.toFixed(2)}</span>`;
    const rankCls = t.tenji_rank===1 ? 'tenji-rank1' : '';
    const tilt = t.tilt != null ? `<span class="tenji-tilt">${t.tilt>0?'+':''}${t.tilt}</span>` : '';
    return `<tr>
      <td><span class="boat-circle b${bn}" style="width:22px;height:22px;font-size:11px;line-height:22px;display:inline-flex;align-items:center;justify-content:center">${bn}</span></td>
      <td>${bt.name}</td>
      <td>${f(t.lap1, bestLap1)}</td>
      <td>${f(t.mawari, bestMawari)}</td>
      <td>${f(t.chokusen, bestChoku)}</td>
      <td><span class="${rankCls}">${f(t.tenji, bestTenji)}</span></td>
      <td>${tilt}</td>
    </tr>`;
  }).join('');
  return `${buildWeatherBar(rno)}<div class="tenji-section">
    <div class="tenji-title">展示情報</div>
    <div style="background:var(--bg2)">
      <table class="tenji-table">
        <thead><tr>
          <th>枠</th><th style="text-align:center">選手名</th>
          <th>1周</th><th>回り足</th><th>直線</th><th>展示</th><th>チルト</th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  </div>`;
}

// ── 会場別展示情報タイム計測制約 ＋ 重みテーブル ──
//
// 重み設計方針:
//   lap1  = 4.5（固定）: 1周タイム → 総合的なモーター力
//   tenji = 4.5（固定）: 展示タイム → スリット後の直線加速力
//   回り足 or 直線 = 1.0（どちらか一方のみ使用、もう一方は0）:
//     差し強会場  → mawari=1.0, chokusen=0  （ターン巧さが差し展開に直結）
//     まくり強会場 → mawari=0,  chokusen=1.0 （立ち上がり加速がまくり展開に直結）
//   合計 = 10.0 → 再正規化後: lap1≒0.45, tenji≒0.45, mawari or chokusen≒0.10
//
// available: 計測が存在するか（falseはデータ自体がない）
//   lap1:"half" → 桐生は半周計測のため重みを半減して扱う
//
const VENUE_TENJI_CONFIG = {

  // ── 計測制約あり（tenji のみ）──
  "江戸川": {
    available: { lap1:false,  mawari:false, chokusen:false, tenji:true },
    weight:    { lap1:0,      mawari:0,     chokusen:0,     tenji:1.0  },
  },

  // ── lap1が半周計測（桐生）→ まくり強なので直線を採用、lap1重みを半減 ──
  "桐生": {
    available: { lap1:"half", mawari:true,  chokusen:true,  tenji:true },
    weight:    { lap1:2.25,   mawari:0,     chokusen:1.0,   tenji:2.0  },
  },

  // ── mawari のみ計測あり（直線なし会場）→ 差し寄りのため回り足採用 ──
  "尼崎": {
    available: { lap1:true,   mawari:true,  chokusen:false, tenji:true },
    weight:    { lap1:4.5,    mawari:1.0,   chokusen:0,     tenji:2.0  },
  },
  "住之江": {
    available: { lap1:true,   mawari:true,  chokusen:false, tenji:true },
    weight:    { lap1:4.5,    mawari:1.0,   chokusen:0,     tenji:2.0  },
  },
  "徳山": {
    available: { lap1:true,   mawari:true,  chokusen:false, tenji:true },
    weight:    { lap1:4.5,    mawari:1.0,   chokusen:0,     tenji:2.0  },
  },

  // ── まくり強会場 → 直線を採用 ──
  "蒲郡": {
    available: { lap1:true,   mawari:true,  chokusen:true,  tenji:true },
    weight:    { lap1:4.5,    mawari:0,     chokusen:1.0,   tenji:2.0  },
  },
  "戸田": {
    available: { lap1:true,   mawari:true,  chokusen:true,  tenji:true },
    weight:    { lap1:4.5,    mawari:0,     chokusen:1.0,   tenji:2.0  },
  },
  "三国": {
    available: { lap1:true,   mawari:true,  chokusen:true,  tenji:true },
    weight:    { lap1:4.5,    mawari:0,     chokusen:1.0,   tenji:2.0  },
  },
  "平和島": {
    available: { lap1:true,   mawari:true,  chokusen:true,  tenji:true },
    weight:    { lap1:4.5,    mawari:0,     chokusen:1.0,   tenji:2.0  },
  },
  "浜名湖": {
    available: { lap1:true,   mawari:true,  chokusen:true,  tenji:true },
    weight:    { lap1:4.5,    mawari:0,     chokusen:1.0,   tenji:2.0  },
  },

  // ── 差し強会場 → 回り足を採用 ──
  "宮島": {
    available: { lap1:true,   mawari:true,  chokusen:true,  tenji:true },
    weight:    { lap1:4.5,    mawari:1.0,   chokusen:0,     tenji:2.0  },
  },
  "下関": {
    available: { lap1:true,   mawari:true,  chokusen:true,  tenji:true },
    weight:    { lap1:4.5,    mawari:1.0,   chokusen:0,     tenji:2.0  },
  },
  "若松": {
    available: { lap1:true,   mawari:true,  chokusen:true,  tenji:true },
    weight:    { lap1:4.5,    mawari:1.0,   chokusen:0,     tenji:2.0  },
  },

  // ── 逃げ強会場（差しもそこそこ）→ 回り足を採用 ──
  "大村": {
    available: { lap1:true,   mawari:true,  chokusen:true,  tenji:true },
    weight:    { lap1:4.5,    mawari:1.0,   chokusen:0,     tenji:2.0  },
  },
  "常滑": {
    available: { lap1:true,   mawari:true,  chokusen:true,  tenji:true },
    weight:    { lap1:4.5,    mawari:1.0,   chokusen:0,     tenji:2.0  },
  },
  "丸亀": {
    available: { lap1:true,   mawari:true,  chokusen:true,  tenji:true },
    weight:    { lap1:4.5,    mawari:1.0,   chokusen:0,     tenji:2.0  },
  },

  // ── デフォルト（多摩川・津・びわこ・鳴門・児島・芦屋・福岡・唐津）→ 回り足を採用 ──
  // [2026-05-13 修正] tenji重みを 4.5→2.0 に削減
  // 旧: lap1=45% tenji=45% → 展示タイムが周回タイムと同等の影響力（過剰）
  // 新: lap1=56% tenji=25% → 展示タイムを補助的な判断材料に位置付け
  "_default": {
    available: { lap1:true,   mawari:true,  chokusen:true,  tenji:true },
    weight:    { lap1:4.5,    mawari:1.0,   chokusen:0,     tenji:2.0  },
  },
};

// ── 会場別 hiKimariStrength テーブル ──────────────────────────────────
//
// 1コース選手の被kimari率がvKimariを動的補正する際の強度係数。
// 値が大きいほど個人の被kimari率が展開確率に強く反映される。
//
// 設計基準:
//   逃げ強会場（大村・常滑・丸亀・尼崎・住之江）
//     → 1.5: イン有利な水面特性で1号艇が崩れにくい。外コース補正を抑える。
//   荒れ強会場（戸田・三国・平和島・浜名湖・蒲郡）
//     → 2.5: 外コースが決まりやすく、被kimari個人差が展開に直結しやすい。
//   特殊水面（江戸川）
//     → 2.0: 潮流・水路の特異性が強く個人被kimari率の汎化精度が低いため中程度に抑制。
//   デフォルト（上記以外: 多摩川・津・びわこ・鳴門・児島・芦屋・福岡・唐津など）
//     → 2.0: 現行より若干抑制し過補正リスクを低減。
//
const VENUE_HI_KIMARI_STRENGTH = {
  // 逃げ強会場 → 弱め
  "大村":    1.5,
  "常滑":    1.5,
  "丸亀":    1.5,
  "尼崎":    1.5,
  "住之江":  1.5,
  "桐生":    1.5,
  "下関":    1.5,
  // 荒れ強会場 → 強め
  "戸田":    2.5,
  "三国":    2.5,
  "平和島":  2.5,
  "浜名湖":  2.5,
  "蒲郡":    2.5,
  // 特殊水面 → 中程度
  "江戸川":  2.0,
  // デフォルト (未登録会場はここを使用)
  "_default": 2.0,
};

// 会場名から hiKimariStrength を取得するヘルパー
function getHiKimariStrength(venue){
  return VENUE_HI_KIMARI_STRENGTH[venue] ?? VENUE_HI_KIMARI_STRENGTH["_default"];
}

// 会場設定から最終重みを返す（arek動的調整なし・会場固定重みのみ）
function resolveWeights(venue, arek){
  const cfg = VENUE_TENJI_CONFIG[venue] || VENUE_TENJI_CONFIG["_default"];
  const base = { ...cfg.weight };

  // 計測がない項目をゼロにして再正規化
  const FIELDS = ["lap1", "mawari", "chokusen", "tenji"];
  FIELDS.forEach(f => { if(!cfg.available[f]) base[f] = 0; });
  const total = FIELDS.reduce((s, f) => s + base[f], 0) || 1;
  FIELDS.forEach(f => { base[f] = base[f] / total; });
  return base;
}

// タイム値 → 偏差値ベースの補正係数（小さい=速い=偏差値高）
function timeToCoef(h){
  if(h >= 60) return 1.15;
  if(h >= 55) return 1.08;
  if(h >= 45) return 1.00;
  if(h >= 40) return 0.93;
  return 0.85;
}

// 1項目分の補正係数配列を返す（値がnullの艇が1艇でもあればnullを返す）
// 全項目「小さいほど速い（タイム値）」
function fieldCoefs(boats, tenjiData, field){
  const vals = boats.map(b => tenjiData[b.boat]?.[field] ?? null);
  // [2026-05-13 修正] 全艇欠損のみnullを返す（旧: 1艇でもnull→全体null）
  // 欠損艇は計測値の平均で補完 → 展示データが一部欠けても他艇のスコアを活かす
  const validVals = vals.filter(v => v !== null);
  if(validVals.length === 0) return null;
  const fillAvg = validVals.reduce((a, v) => a + v, 0) / validVals.length;
  const filled  = vals.map(v => v !== null ? v : fillAvg);
  const avg = filled.reduce((a, v) => a + v, 0) / filled.length;
  const std = Math.sqrt(filled.reduce((a, v) => a + (v - avg) ** 2, 0) / filled.length);
  if(std === 0) return filled.map(() => 1.0);  // 全艇同タイム → 補正なし
  return filled.map(v => timeToCoef(50 + ((avg - v) / std) * 10));
}

// ── calcTenjiScore（独立展示スコア生成）──
//
// 【変更点】
//   旧 calcTenjiDelta: base_score（prob/tenkai_prob）に展示係数を乗算
//     → 基準probやtenkai_probに依存した連鎖計算になっていた
//   新 calcTenjiScore: 展示タイムだけから独立した正規化スコアを生成
//     → 基準prob・tenkai_probを一切参照しない
//
// 返り値: { [boat番号]: 展示独立スコア（正規化済み 0-1） } または null
//
function calcTenjiScore(boats, tenjiData, venue, arek){
  if(!tenjiData) return null;

  const w = resolveWeights(venue || "_default", arek || 50);
  const FIELDS = ["lap1", "mawari", "chokusen", "tenji"];

  const coefsMap = {};
  for(const f of FIELDS){
    if(w[f] <= 0) continue;
    const c = fieldCoefs(boats, tenjiData, f);
    if(c) coefsMap[f] = c;
  }

  if(Object.keys(coefsMap).length === 0) return null;

  // 加重平均で合成係数を算出（各艇の展示パフォーマンス指標）
  const compositeCoefs = boats.map((_, i) => {
    let score = 0, wTotal = 0;
    for(const f of FIELDS){
      if(!coefsMap[f]) continue;
      score  += w[f] * coefsMap[f][i];
      wTotal += w[f];
    }
    return wTotal > 0 ? score / wTotal : 1.0;
  });

  // ★ 係数をそのまま正規化して独立スコアにする（probを一切掛けない）
  const coefTotal = compositeCoefs.reduce((a, v) => a + v, 0) || 1;
  const coefAvg   = coefTotal / boats.length;  // 平均係数（6艇均等なら全艇1.0）
  const tenjiScoreMap = {};
  boats.forEach((b, i) => {
    tenjiScoreMap[b.boat] = compositeCoefs[i] / coefTotal;
    // 表示用: 平均を1.0基準とした係数（0.5〜2.0にクリップ）
    tenjiScoreMap[`__coef_${b.boat}`] = coefAvg > 0
      ? Math.min(2.0, Math.max(0.5, compositeCoefs[i] / coefAvg))
      : 1.0;
  });
  return tenjiScoreMap;
}

// 後方互換ラッパー（updateTenjiDelta等の既存呼び出し箇所向け）
function calcTenjiDelta(boats, tenjiData, venue, arek){
  return calcTenjiScore(boats, tenjiData, venue, arek);
}

function updateTenjiDelta(venue, date, rno){
  if(!DATA||!DATA.races[String(rno)]) return;
  const SLUG = {
    "桐生":"kiryu","戸田":"toda","江戸川":"edogawa","平和島":"heiwajima",
    "多摩川":"tamagawa","浜名湖":"hamanako","蒲郡":"gamagori","常滑":"tokoname",
    "津":"tsu","三国":"mikuni","びわこ":"biwako","住之江":"suminoe",
    "尼崎":"amagasaki","鳴門":"naruto","丸亀":"marugame","児島":"kojima",
    "宮島":"miyajima","徳山":"tokuyama","下関":"shimonoseki","若松":"wakamatsu",
    "芦屋":"ashiya","福岡":"fukuoka","唐津":"karatsu","大村":"omura"
  };
  const slug = SLUG[DATA.venue]||DATA.venue||'';
  const key = tenjiKey(slug, date||DATA.date, rno);
  const tenjiData = _tenjiCache[key];
  if(!tenjiData) return;
  const boats = DATA.races[String(rno)].boats;
  const arekForTenji = (DATA.races[String(rno)]?.arek) ?? 54.7;
  const deltaMap = calcTenjiDelta(boats, tenjiData, DATA.venue, arekForTenji);
  if(!deltaMap) return;
  boats.forEach(b=>{
    b.tenji_delta = deltaMap[b.boat];
    if(b.final_prob == null) b.final_prob = b.tenkai_prob ?? b.prob;
  });
}

// ── コメント（サンプルでは固定テキスト） ──
const _commentCache = {};
(function(){
  for(const [key, val] of Object.entries(COMMENT_DATA)){
    const normalized = key.replace(/_(\d{4})(\d{2})(\d{2})_/, '_$1-$2-$3_');
    _commentCache[normalized] = val;
  }
})();
function commentKey(venue, date, race){ return `${venue}_${date}_${race}`; }

const COMMENT_KEYWORDS_GOOD = ['調子いい','足がいい','足は良','仕上がって','自信','乗れてる','感触いい','良さそう','行ける','自信あり'];
const COMMENT_KEYWORDS_BAD  = ['エンジンに力','力がない','届かない','失敗','苦しい','厳しい','遅い','差ない','出し切れ','整備'];

function highlightComment(text){
  if(!text) return '<span class="comment-empty">コメントなし</span>';
  let t = text.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  COMMENT_KEYWORDS_GOOD.forEach(kw=>{ t = t.replaceAll(kw, `<span class="comment-keyword good">${kw}</span>`); });
  COMMENT_KEYWORDS_BAD.forEach(kw=>{  t = t.replaceAll(kw, `<span class="comment-keyword bad">${kw}</span>`); });
  return t;
}

// ── モーター情報セクション（コメントタブ用）──
//
// データソース優先順位:
//   1. _tenjiCache[key][frameNo].motor_rate2 / motor_no / prev_user  ← 展示取得済み
//   2. boats[].motor2 / motor_no / prev_user                         ← CSV埋め込み値
//
// M2率順位は当該レースの6艇間で算出（同率は同順位）。
//
function buildMotorInfoSection(rno, boats){
  const SLUG2 = {
    "桐生":"kiryu","戸田":"toda","江戸川":"edogawa","平和島":"heiwajima",
    "多摩川":"tamagawa","浜名湖":"hamanako","蒲郡":"gamagori","常滑":"tokoname",
    "津":"tsu","三国":"mikuni","びわこ":"biwako","住之江":"suminoe",
    "尼崎":"amagasaki","鳴門":"naruto","丸亀":"marugame","児島":"kojima",
    "宮島":"miyajima","徳山":"tokuyama","下関":"shimonoseki","若松":"wakamatsu",
    "芦屋":"ashiya","福岡":"fukuoka","唐津":"karatsu","大村":"omura"
  };
  const slug2  = SLUG2[DATA.venue] || DATA.venue;
  const key2   = tenjiKey(slug2, DATA.date, rno);
  const cached2 = _tenjiCache[key2];

  // 各艇のモーター情報をマージ（展示キャッシュ優先、なければboatsのフィールドを使用）
  const motorRows = boats.map(bt => {
    const td = cached2 ? cached2[String(bt.boat)] : null;
    return {
      boat:       bt.boat,
      name:       bt.name,
      motor_no:   td?.__motor_no   ?? td?.motor_no   ?? bt.motor_no   ?? null,
      motor2:     (td?.__motor_rate2 != null) ? td.__motor_rate2
                  : (td?.motor_rate2 != null) ? td.motor_rate2
                  : (bt.motor2 != null)       ? bt.motor2
                  : null,
      motor_rank: td?.__motor_rank ?? td?.motor_rank ?? bt.motor_rank ?? null,
      prev_user:  td?.__prev_user  ?? td?.prev_user  ?? bt.prev_user  ?? null,
    };
  });

  // M2率順位:
  //   サイト取得値(motor_rank)があればそちらをそのまま使用。
  //   なければ当該レースの6艇のM2率で降順ランクを計算（同率同順位）。
  const hasSiteRank = motorRows.some(r => r.motor_rank != null);
  const rankMap = {};
  if(hasSiteRank){
    motorRows.forEach(r => { rankMap[r.boat] = r.motor_rank; });
  } else {
    const sorted2 = [...motorRows]
      .filter(r => r.motor2 != null)
      .sort((a, b) => b.motor2 - a.motor2);
    sorted2.forEach((r, i) => {
      rankMap[r.boat] = (i > 0 && r.motor2 === sorted2[i-1].motor2)
        ? rankMap[sorted2[i-1].boat]
        : i + 1;
    });
  }

  const hasAny = motorRows.some(r => r.motor2 != null || r.motor_no != null || r.prev_user != null);
  if(!hasAny) return '';

  // 順位バッジ色（1位→金, 2位→銀, 3位→銅）
  function rankBadge(rank){
    if(rank == null) return '<span style="color:var(--text3);font-size:11px">—</span>';
    const colors = {1:'#e6a800',2:'#7a8a99',3:'#a0672a'};
    const c = colors[rank] || 'var(--text3)';
    return `<span style="font-size:11px;font-weight:700;color:${c}">${rank}位</span>`;
  }

  function m2Color(v){
    if(v == null) return 'var(--text3)';
    return v >= 40 ? 'var(--green)' : v >= 25 ? 'var(--orange)' : 'var(--red)';
  }

  const rows = motorRows.map(r => {
    const rank   = rankMap[r.boat] ?? null;
    const m2disp = r.motor2 != null
      ? `<span style="font-family:var(--mono);font-weight:700;color:${m2Color(r.motor2)}">${r.motor2.toFixed(1)}%</span>`
      : '<span style="color:var(--text3)">—</span>';
    const monoDisp = r.motor_no != null
      ? `<span style="font-size:10px;color:var(--text3);font-family:var(--mono)">#${r.motor_no}</span>`
      : '';
    const prevDisp = r.prev_user
      ? `<span style="font-size:11px;color:var(--text2)">${r.prev_user}</span>`
      : `<span style="font-size:11px;color:var(--text3)">—</span>`;

    return `<div style="display:grid;grid-template-columns:28px 1fr 52px 36px 1fr;gap:4px 8px;align-items:center;padding:0.4rem 1rem;border-bottom:1px solid var(--border)">
      <span class="boat-circle b${r.boat}" style="width:22px;height:22px;font-size:11px;line-height:22px;display:inline-flex;align-items:center;justify-content:center">${r.boat}</span>
      <div style="min-width:0">
        <div style="font-size:12px;font-weight:600;color:var(--text2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${r.name}</div>
        ${monoDisp ? `<div style="margin-top:1px">${monoDisp}</div>` : ''}
      </div>
      <div style="text-align:center">${m2disp}</div>
      <div style="text-align:center">${rankBadge(rank)}</div>
      <div>${prevDisp}</div>
    </div>`;
  }).join('');

  return `<div style="border-bottom:1px solid var(--border)">
    <div style="display:grid;grid-template-columns:28px 1fr 52px 36px 1fr;gap:4px 8px;align-items:center;padding:0.35rem 1rem;background:var(--bg3);border-bottom:1px solid var(--border)">
      <span></span>
      <span style="font-size:10px;font-weight:700;letter-spacing:.06em;color:var(--text3)">🔧 モーター</span>
      <span style="font-size:10px;color:var(--text3);text-align:center">M2率</span>
      <span style="font-size:10px;color:var(--text3);text-align:center">順位</span>
      <span style="font-size:10px;color:var(--text3)">前節使用者</span>
    </div>
    ${rows}
  </div>`;
}

function buildCommentSection(rno, boats){
  const SLUG = {
    "桐生":"kiryu","戸田":"toda","江戸川":"edogawa","平和島":"heiwajima",
    "多摩川":"tamagawa","浜名湖":"hamanako","蒲郡":"gamagori","常滑":"tokoname",
    "津":"tsu","三国":"mikuni","びわこ":"biwako","住之江":"suminoe",
    "尼崎":"amagasaki","鳴門":"naruto","丸亀":"marugame","児島":"kojima",
    "宮島":"miyajima","徳山":"tokuyama","下関":"shimonoseki","若松":"wakamatsu",
    "芦屋":"ashiya","福岡":"fukuoka","唐津":"karatsu","大村":"omura"
  };
  const slug = SLUG[DATA.venue] || DATA.venue;
  const key  = `${slug}_${DATA.date}_${rno}`;

  // COMMENT_DATAに実データがあればそちらを使用
  const cached = _commentCache[key];
  if(cached){
    const rows = boats.map(bt => {
      const entry = cached[bt.boat] || cached[String(bt.boat)] || {};
      return `<div class="comment-row">
        <span class="boat-circle b${bt.boat}" style="width:22px;height:22px;font-size:11px;line-height:22px;display:inline-flex;align-items:center;justify-content:center">${bt.boat}</span>
        <span class="comment-name">${bt.name}</span>
        <span class="comment-text">${highlightComment(entry.comment||'')}</span>
      </div>`;
    }).join('');
    const fetched = cached['__fetched_at'] || '';
    return `<div class="comment-section">
      <div class="comment-title">選手コメント <span class="comment-badge">取得済み${fetched?' '+fetched:''}</span></div>
      ${rows}
    </div>`;
  }

  // データなし → コメントなし表示
  const rows = boats.map(bt => `
    <div class="comment-row">
      <span class="boat-circle b${bt.boat}" style="width:22px;height:22px;font-size:11px;line-height:22px;display:inline-flex;align-items:center;justify-content:center">${bt.boat}</span>
      <span class="comment-name">${bt.name}</span>
      <span class="comment-empty">コメントなし</span>
    </div>`).join('');
  return `<div class="comment-section">
    <div class="comment-title">選手コメント <span class="comment-badge waiting">未取得</span></div>
    ${rows}
  </div>`;
}

// ── F回数取得（列表示用）──
// FLYING_DATA[会場][レースno文字列] = [{waku, name, flying, f_total}, ...]
function getFTotal(boatNo, rno){
  if(!DATA || !currentVenue) return 0;
  const raceMap = (FLYING_DATA[currentVenue] || {})[String(rno)] || [];
  const rec = raceMap.find(r => String(r.waku) === String(boatNo));
  return rec ? (rec.f_total || 1) : 0;
}

// ── renderDetail ──
function renderDetail(rno){
  const rd = DATA.races[String(rno)];
  if(!rd) return;
  const boats = [...rd.boats].sort((a,b)=>a.boat-b.boat);
  const tenjiHtml = buildTenjiSection(rno, boats);


  // グリッド列: 枠32px 選手名82px 級40px F列28px 基準1着率60px 3連対率52px ST順52px
  const colStyle = 'grid-template-columns: 32px 82px 40px 28px 60px 52px 52px';

  // バナーをタブ外の常時表示エリアに更新
  updatePersistentBanners(rno);

  const html = `
    <div class="detail-panel">
      <div class="bt-head-simple" style="${colStyle}">
        <span>枠</span><span style="text-align:center">選手名</span><span>級</span><span style="text-align:center">F</span><span style="text-align:center">1着率</span><span style="text-align:center">3連対率</span><span style="text-align:center">平均ST順</span>
      </div>
      ${boats.map((bt,i)=>{
        const fTotal = getFTotal(bt.boat, rno);
        const fCell = fTotal > 0
          ? `<span style="color:#e60012;font-weight:700;font-size:13px;display:block;text-align:center">${fTotal}</span>`
          : `<span style="color:var(--text3);font-size:11px;display:block;text-align:center">—</span>`;
        const course = String(bt.boat);
        const stRank = MASTER_EXT?.course_master?.[bt.name]?.[course]?.st_rank;
        const stCell = stRank != null
          ? `<span style="display:block;text-align:center;font-size:12px">${stRank.toFixed(1)}</span>`
          : `<span style="color:var(--text3);font-size:11px;display:block;text-align:center">—</span>`;
        const ap3 = MASTER_EXT?.player_index?.[bt.name]?.annual_place3;
        const place3Cell = ap3 != null
          ? `<span style="display:block;text-align:center;font-size:12px;color:var(--text)">${(ap3*100).toFixed(1)}%</span>`
          : `<span style="color:var(--text3);font-size:11px;display:block;text-align:center">—</span>`;
        return `
        <div class="bt-row${i===0?' top1':''}" style="${colStyle}">
          <span class="boat-circle b${bt.boat}" style="width:22px;height:22px;font-size:11px;line-height:22px;display:inline-flex;align-items:center;justify-content:center">${bt.boat}</span>
          <div style="text-align:center">${bt.name}</div>
          <div class="bt-grade">${bt.grade ?? '-'}</div>
          <div>${fCell}</div>
          <div style="display:flex;flex-direction:column;align-items:center;gap:1px">
            <span>${bt.base_rate != null ? (bt.base_rate*100).toFixed(1)+'%' : '<span style="color:var(--text3);font-size:11px">—</span>'}</span>
          </div>
          <div>${place3Cell}</div>
          <div>${stCell}</div>
        </div>`;
      }).join('')}
      ${tenjiHtml}
    </div>
  `;
  // ── 展開シミュボタンをパネル下部に追加 ──
  const simBtnHtml = `<button
    onclick="openSimModal(${rno})"
    style="display:block;width:100%;padding:11px 16px;
      background:rgba(0,102,255,0.06);border:none;
      border-top:1px solid var(--border);
      color:var(--accent2);font-size:13px;font-weight:700;
      cursor:pointer;letter-spacing:0.05em;transition:background 0.15s;"
    onmouseover="this.style.background='rgba(0,102,255,0.12)'"
    onmouseout="this.style.background='rgba(0,102,255,0.06)'"
  >⚡ 展開シミュ</button>`;
  document.getElementById('inline-detail').innerHTML = html + simBtnHtml;
}

// ── 展開推定（1着率のみ）──
//
// 【役割】venue_kimari × prob × 個人kimari適性 × 相対評価 で各艇の1着率(tenkai_prob)を算出する。
// 2着率の優先順位: ①逃げ→inn_2place ②非逃げ→tenkai_remaining(会場別のみ)+winner_course_order(個人補正・重み1.5倍) ③フォールバック→tenkai_prob相対値
//
// MASTER_EXT なし → prob をそのまま tenkai_prob にコピーして返す
// MASTER_EXT あり → 決まり手別有効コース制約（ハード除外＋個人適性）＋
//                   1コースの被kimari × 攻め手の kimari による相対評価補正を適用
//
// 【修正A】個人kimari係数にruns信頼度重みを付与（runs<50は中立値1.0に引き寄せ）
// 【修正C】1コースの被kimari率でvKimariを動的補正（差され率→差し展開UP等）
//
// 恵まれ（転覆等による繰り上がり）は予測不可のため除外。
//
function calcTenkaiProbs(boats, arek){
  // ── MASTER_EXT なし ──
  if(!MASTER_EXT || !MASTER_EXT.venue_kimari){
    return [...boats].map(b=>({
      ...b,
      tenkai_prob:  b.prob,
      tenkai_score: b.prob,  // ★ MASTER_EXTなし: probをそのまま独立スコアとして使用
    })).sort((a,b)=>b.tenkai_prob-a.tenkai_prob);
  }

  const venue   = DATA.venue;
  const vKimari = MASTER_EXT.venue_kimari[venue];

  if(!vKimari){
    return [...boats].map(b=>({
      ...b,
      tenkai_prob:  b.prob,
      tenkai_score: b.prob,  // ★ 会場データなし: 同上
    })).sort((a,b)=>b.tenkai_prob-a.tenkai_prob);
  }

  // ── 決まり手ごとのハード除外コース（物理的に絶対ありえない）──
  // 恵まれは除外（転覆等による繰り上がりのため予測不可）
  const KIMARI_HARD_EXCLUDE = {
    '逃げ':       new Set(['2','3','4','5','6']),
    '差し':       new Set(['1']),
    'まくり':     new Set(['1']),
    'まくり差し': new Set(['1','2']),
    '抜き':       new Set(),
  };

  // ── グレーゾーン：個人kimari%が閾値以上なら有効とみなす ──
  const KIMARI_SOFT_THRESHOLD = {
    'まくり': {'2': 0.05},   // 2コースのまくりは個人実績5%以上で有効
    '抜き':   {'1': 0.03},   // 1コースの抜きは個人実績3%以上で有効
  };

  // 相対評価補正の上下限（個人差をより大きく反映するため拡大 ※会場3:個人7）
  const RELATIVE_MIN = 0.3;
  const RELATIVE_MAX = 3.0;

  // 選手のコース別kimari%をマスタから取得するヘルパー
  function getPersonalKimari(boatName, courseStr, kimariType){
    return MASTER_EXT?.course_master?.[boatName]?.[courseStr]?.kimari?.[kimariType] ?? 0;
  }

  // 1コース選手の被kimari%を取得するヘルパー
  function getPersonal被Kimari(boatName, hiKimariType){
    return MASTER_EXT?.course_master?.[boatName]?.['1']?.['被kimari']?.[hiKimariType] ?? null;
  }

  // 選手×決まり手の有効判定
  function isValidFirst(boat, kimari){
    const wc  = String(boat.boat);
    const exc = KIMARI_HARD_EXCLUDE[kimari];
    if(!exc) return false;
    if(exc.has(wc)) return false;
    const soft = KIMARI_SOFT_THRESHOLD[kimari];
    if(soft && wc in soft){
      const threshold = soft[wc];
      const personal  = getPersonalKimari(boat.name, wc, kimari);
      return personal >= threshold;
    }
    return true;
  }

  // ── 相対評価補正係数の計算 ──
  //
  // 1コース選手の被kimari率 × 攻め手選手のkimari率 を掛け合わせ、
  // 全体平均との比率で補正係数を算出する。
  //
  // 例: 差し展開
  //   1コースの差され率=0.20、2コースの差し率=0.45
  //   → 積 = 0.09
  //   全6艇の同積の平均が0.05なら係数 = 0.09/0.05 = 1.8（差しが決まりやすい）
  //
  // 逃げ展開は1コースの逃げ率（攻め手）と差され率（被）の両方で評価:
  //   逃げ率が高く差され率が低いほど係数UP
  //
  // 対応表:
  //   決まり手       攻め手kimari    1コース被kimari
  //   逃げ           逃げ率          差され率(逆数)・捲られ率(逆数)・捲り差され率(逆数)
  //   差し           差し率          差され率
  //   まくり         まくり率        捲られ率
  //   まくり差し     まくり差し率    捲り差され率
  //   抜き           抜き率          (被kimariなし → 補正なし)
  //
  function calcRelativeCoef(winner, kimari, boat1){
    if(!boat1) return 1.0;  // 1コース艇がいない → 補正なし

    const wc = String(winner.boat);

    if(kimari === '逃げ'){
      // 逃げ展開は1コース選手の逃げ率のみで評価する。
      // ※被kimari（差され率等）は winner === boat1 の同一人物参照になるため使用しない。
      //   kuzureRate = 差され率+捲られ率+捲り差され率 は合計が1.0を超えやすく、
      //   1.0 - kuzureRate が負になって係数が極小→スコアがほぼ0になるバグの原因。
      const nigeRate = getPersonalKimari(winner.name, '1', '逃げ');
      return nigeRate > 0 ? nigeRate : 1.0;
    }

    if(kimari === '差し'){
      const attackRate = getPersonalKimari(winner.name, wc, '差し');
      const defRate    = getPersonal被Kimari(boat1.name, '差され');
      if(defRate === null) return attackRate || 1.0;
      return attackRate * defRate;
    }

    if(kimari === 'まくり'){
      const attackRate = getPersonalKimari(winner.name, wc, 'まくり');
      const defRate    = getPersonal被Kimari(boat1.name, '捲られ');
      if(defRate === null) return attackRate || 1.0;
      return attackRate * defRate;
    }

    if(kimari === 'まくり差し'){
      const attackRate = getPersonalKimari(winner.name, wc, 'まくり差し');
      const defRate    = getPersonal被Kimari(boat1.name, '捲り差され');
      if(defRate === null) return attackRate || 1.0;
      return attackRate * defRate;
    }

    // 抜き・その他 → 補正なし
    return 1.0;
  }

  // 1コース艇を特定
  const boat1 = boats.find(b => b.boat === 1) || null;

  // ── 修正C: 1コース選手の被kimari率でvKimariを動的補正 ──
  //
  // 1コース選手の「差され率・捲られ率・捲り差され率」が高いほど
  // 対応する展開の事前確率を底上げする。
  //
  // 例: 差され率0.30（高い）→ 差し展開の確率を最大+50%補正
  //     捲られ率0.05（低い）→ まくり展開はほぼそのまま
  //
  // 補正強度は VENUE_HI_KIMARI_STRENGTH で会場別に制御。
  // 被kimariデータがない場合は vKimari をそのまま使用。
  //
  const hiKimariStrength = getHiKimariStrength(venue); // 会場別: 逃げ強→1.5 / 荒れ強→2.5 / 既定→2.0
  let adjustedVKimari = { ...vKimari };

  if(boat1){
    const hiKimari = MASTER_EXT?.course_master?.[boat1.name]?.['1']?.['被kimari'];
    const boat1Runs = MASTER_EXT?.course_master?.[boat1.name]?.['1']?.runs ?? 0;
    // 被kimari（1コース専用）: 差され/捲られ率の閾値は30走（決まり手ブレンドとは独立した設定）
    if(hiKimari && boat1Runs >= 30){
      // 被kimari率をどれだけ信頼するか（100走で信頼度1.0） ※50→100に変更
      const hiTrust = Math.min(boat1Runs / 100, 1.0);

      const sasareRate     = (hiKimari['差され']     ?? null);
      const makurareRate   = (hiKimari['捲られ']     ?? null);
      const makurisasareRate = (hiKimari['捲り差され'] ?? null);

      if(sasareRate !== null){
        // 差し: 被差され率が高いほど差し展開確率を上げる
        adjustedVKimari['差し'] = (vKimari['差し'] || 0)
          * (1 + hiTrust * sasareRate * hiKimariStrength);
      }
      if(makurareRate !== null){
        // まくり: 被捲られ率が高いほどまくり展開確率を上げる
        adjustedVKimari['まくり'] = (vKimari['まくり'] || 0)
          * (1 + hiTrust * makurareRate * hiKimariStrength);
      }
      if(makurisasareRate !== null){
        // まくり差し: 被捲り差され率が高いほどまくり差し展開確率を上げる
        adjustedVKimari['まくり差し'] = (vKimari['まくり差し'] || 0)
          * (1 + hiTrust * makurisasareRate * hiKimariStrength);
      }
      // 逃げ: 被kimariの合計が高いほど逃げ展開確率を下げる
      const totalHiRate = (sasareRate ?? 0) + (makurareRate ?? 0) + (makurisasareRate ?? 0);
      const nigeRate = getPersonalKimari(boat1.name, '1', '逃げ');
      if(nigeRate > 0){
        // 逃げ率が高く被kimari合計が低いほど逃げ展開を維持
        const nigeBoost = nigeRate / Math.max(nigeRate + totalHiRate, 0.01);
        adjustedVKimari['逃げ'] = (vKimari['逃げ'] || 0) * (0.5 + 0.5 * nigeBoost * 2);
      }

      // 再正規化（合計を1.0に揃える）
      const adjTotal = Object.values(adjustedVKimari).reduce((s, v) => s + v, 0);
      if(adjTotal > 0){
        for(const k of Object.keys(adjustedVKimari)){
          adjustedVKimari[k] = adjustedVKimari[k] / adjTotal;
        }
      }
    }
  }

  const kimariTypes = Object.keys(adjustedVKimari).filter(k => adjustedVKimari[k] > 0 && k in KIMARI_HARD_EXCLUDE);

  // ── 修正D: 全選手の個人kimari率をadjustedVKimariにブレンドする ──
  //
  // 各艇の「そのコースでの決まり手使用率」を個人傾向として取り出し、
  // 会場傾向(adjustedVKimari)と trust 比率でブレンドする。
  //
  // strength = 個人傾向の最大ウェイト（50走時）
  //   0.4 → 「会場60%:個人40%」が上限。データが少ないほど会場寄り。
  //
  // 逃げ（1コース専用展開）は1コース艇の個人率のみで補正済み（修正C）のため
  // ここでは差し・まくり・まくり差し・抜きのみ対象。
  //
  const PERSONAL_BLEND_STRENGTH = 0.7; // チューニング用: 0.3(控えめ)〜0.6(強め) ※会場3:個人7に変更

  function blendPersonalKimari(boatObj, baseVKimari){
    const name   = boatObj.name;
    const course = String(boatObj.boat);
    const cm     = MASTER_EXT?.course_master?.[name]?.[course];
    if(!cm) return baseVKimari;

    const runs = cm.runs ?? 0;
    if(runs < 20) return baseVKimari; // データ不足はスキップ（kimariCoefSumのreliable閾値と統一: 20走）

    // runs数に応じた信頼度（20走→0.14、50走→0.35、100走→0.7） ※閾値を30→20に統一
    const trust = Math.min(runs / 100, 1.0) * PERSONAL_BLEND_STRENGTH;

    const personalKimari = cm.kimari ?? {};
    // 個人kimari率を差し・まくり・まくり差し・抜きのみ対象に正規化
    const BLEND_TARGETS = ['差し', 'まくり', 'まくり差し', '抜き'];
    const personalTotal = BLEND_TARGETS.reduce((s, k) => s + (personalKimari[k] ?? 0), 0);
    if(personalTotal <= 0) return baseVKimari;

    const blended = { ...baseVKimari };
    for(const k of BLEND_TARGETS){
      if(!(k in blended)) continue;
      const personalRate = (personalKimari[k] ?? 0) / personalTotal
        // 個人率を「ブレンド対象キーの会場合計」スケールに合わせる
        * BLEND_TARGETS.reduce((s, kk) => s + (baseVKimari[kk] ?? 0), 0);
      blended[k] = baseVKimari[k] * (1 - trust) + personalRate * trust;
    }

    // 再正規化（合計を元の合計に揃える）
    const origTotal   = Object.values(baseVKimari).reduce((s, v) => s + v, 0);
    const blendTotal  = Object.values(blended).reduce((s, v) => s + v, 0);
    if(blendTotal > 0){
      for(const k of Object.keys(blended)) blended[k] = blended[k] / blendTotal * origTotal;
    }
    return blended;
  }

  // ── 各艇の決まり手適性スコアを prob に乗算する係数を算出 ──
  //
  // 設計方針（修正D適用後）:
  //   tenkai_prob ∝ prob × Σ(personalKimariProb × normalizedCoef)
  //
  //   各艇ごとに個人ブレンドvKimariを使用するため、
  //   「差し得意な選手がいれば差し展開確率が上がる」が自然に表現される。
  //
  // normalizedCoef は有効艇の平均を1.0基準に正規化しているため、
  // 全艇の補正係数の平均は常に1.0付近に揃い、prob の合計スケールを保持する。

  // まず各艇の「決まり手加重適性係数」を計算
  const kimariCoefSum = {};
  boats.forEach(b => { kimariCoefSum[b.boat] = 0; });

  // 修正D: 艇ごとに個人ブレンドvKimariを先に算出しておく
  const boatVKimari = {};
  boats.forEach(b => { boatVKimari[b.boat] = blendPersonalKimari(b, adjustedVKimari); });

  for(const kimari of kimariTypes){
    // 有効艇の relCoef を取得（修正D: kimariProbは艇ごとの個人ブレンド値を使用）
    const relCoefs = {};
    for(const b of boats){
      if(!isValidFirst(b, kimari)){ relCoefs[b.boat] = 0; continue; }
      const rawCoef = calcRelativeCoef(b, kimari, boat1);
      // ── 修正A: runs数に応じて個人適性の信頼度を調整 ──
      // runs不足の選手は係数を中立値(1.0)に引き寄せる。
      // 100走で信頼度1.0（個人適性をフル反映）
      // 20走で信頼度0.2（会場平均寄り）
      // 20走未満は reliable=false のためここには来ない（blendPersonalKimariと同じ閾値）
      const kimariRuns = MASTER_EXT?.course_master?.[b.name]?.[String(b.boat)]?.runs ?? 0;
      const personalTrust = Math.min(kimariRuns / 100, 1.0); // ※基準を50→100に変更
      // 信頼度が低いほど中立値(1.0)に引き戻す
      relCoefs[b.boat] = rawCoef * personalTrust + 1.0 * (1 - personalTrust);
    }

    // 有効艇の平均 relCoef（1.0基準に正規化するため）
    const validBoats = boats.filter(b => isValidFirst(b, kimari));
    if(validBoats.length === 0) continue;
    const avgCoef = validBoats.reduce((s, b) => s + relCoefs[b.boat], 0) / validBoats.length;
    if(avgCoef <= 0) continue;

    for(const b of boats){
      if(!isValidFirst(b, kimari)) continue;
      // 修正D: この艇の個人ブレンドvKimariから当該決まり手の確率を取得
      const kimariProb = boatVKimari[b.boat][kimari] || 0;
      if(kimariProb <= 0) continue;
      // 平均を1.0基準に正規化してクリップ
      const normalizedCoef = Math.min(RELATIVE_MAX, Math.max(RELATIVE_MIN, relCoefs[b.boat] / avgCoef));
      // 決まり手比率で重み付けして加算（合計 ≈ 1.0 になる）
      kimariCoefSum[b.boat] += kimariProb * normalizedCoef;
    }
    // 有効外の艇（ハード除外）は会場平均値として kimariProb を加算
    // → 「その展開では勝てないが存在は無視しない」扱い
    for(const b of boats){
      if(isValidFirst(b, kimari)) continue;
      const kimariProb = adjustedVKimari[kimari] || 0; // 有効外は会場平均を維持
      kimariCoefSum[b.boat] += kimariProb * RELATIVE_MIN;
    }
  }

  // prob × 決まり手適性係数 → 正規化
  const scores = {};
  boats.forEach(b => { scores[b.boat] = b.prob * (kimariCoefSum[b.boat] || RELATIVE_MIN); });

  // ★ tenkai_score: 「probを加味した上で、相対補正の寄与分だけを独立スコアとして返す」
  //
  // 【設計思想】
  //   kimariCoefSumをそのまま正規化すると、1号艇は「逃げ以外ハード除外→係数が集まりにくい」
  //   という構造的な問題で、どのレースでも1号艇の相対補正が下がってしまう。
  //
  //   これは kimariCoefSum が「決まり手の有効範囲の広さ」を内包しているためで、
  //   「強さの独立評価」として使うには不適切。
  //
  //   解決策: scores（prob × kimariCoefSum）を正規化したものを tenkai_score とする。
  //   これは旧来の tenkai_prob と同じ値だが、「相対補正後の強さスコア」として
  //   加重合成に使う目的では正しい。
  //   ※ 加重合成で base(prob) と tenkai_score(≒tenkai_prob) を別々に足すことで
  //     「probの情報を2回使いすぎる」問題は生じない。
  //     なぜなら tenkai_score = prob × 適性係数 / total であり、
  //     prob単体（base）と「probに適性を掛けた後の順位」は別の情報だから。
  const tenkaiOnlyTotal = Object.values(scores).reduce((a,v) => a+v, 0) || 1;

  const total = Object.values(scores).reduce((a,b)=>a+b, 0) || 1;
  return [...boats]
    .map(b => ({
      ...b,
      tenkai_prob:  scores[b.boat] / total,
      tenkai_score: scores[b.boat] / tenkaiOnlyTotal,  // ★ = tenkai_prob（prob×適性の正規化値）
      kimari_coef:  kimariCoefSum[b.boat] || RELATIVE_MIN,  // ★ 表示用: 生の決まり手適性係数
      // final_prob: renderBuy の加重合成で上書きされる
      final_prob:   scores[b.boat] / total,
    }))
    .sort((a,b) => b.tenkai_prob - a.tenkai_prob);
}

// ── 条件付き2着率推定 ──
//
// 【役割】inn_2place（イン逃げ時の会場別枠別2着率）を使い、
//         各艇の「2着に来る期待スコア」を算出する。
//
// アルゴリズム:
//   1. 1コースが逃げで1着になる確率 = vKimari["逃げ"] × 1コースのtenkai_prob比率
//   2. その場合の各コースの2着率 = inn_2place[コース] + winner_course_order 個人補正
//   3. それ以外の展開（差し・まくり等）は tenkai_remaining（会場別実績、なければ全国実績）+
//      winner_course_order（個人補正）でブレンド。データなし → tenkai_prob 相対値
//
// 返り値: { [boat番号]: place2スコア（正規化済み 0-1） }
//
function calcPlace2Probs(boats, ranked){
  const place2Score = {};
  ranked.forEach(b => { place2Score[b.boat] = 0; });

  const tpMap = {};
  ranked.forEach(b => { tpMap[b.boat] = b.tenkai_prob; });

  // inn_2place: inn_data に直接入っていれば使用、なければ venue_stats から取得
  const inn2Place = (() => {
    const v = (DATA.inn_data || {}).inn_2place;
    if(v && typeof v === 'object' && !Array.isArray(v) && Object.keys(v).length > 0) return v;
    return MASTER_EXT?.venue_stats?.[DATA.venue]?.inn_2place || {};
  })();
  const hasInn2 = Object.keys(inn2Place).length > 0;

  // venue_kimari があれば逃げ展開確率を取得
  const vKimari = MASTER_EXT?.venue_kimari?.[DATA.venue] || null;
  const nigeProb = vKimari?.['逃げ'] ?? 0.45;  // なければ0.45をデフォルト

  // winner_course_order: 個人の「勝者コース別・自コース別2着率」
  const winnerCO = MASTER_EXT?.winner_course_order || {};

  // 1コース艇の final_prob 比率（展示補正後の最終確率ベースで按分）
  const boat1 = ranked.find(b => b.boat === 1);
  const fp1   = boat1?.final_prob ?? boat1?.tenkai_prob ?? 0;
  const totalFP = ranked.reduce((s, b) => s + (b.final_prob ?? b.tenkai_prob ?? 0), 0) || 1;
  // 後続処理（非逃げ按分）でも参照するため totalTP は残す
  const tp1   = boat1 ? boat1.tenkai_prob : 0;
  const totalTP = ranked.reduce((s, b) => s + b.tenkai_prob, 0) || 1;

  // 逃げ展開（1コース1着）の確率: final_prob ベースで按分
  const nigeWinProb = nigeProb * (fp1 / totalFP);

  // ── 逃げ展開での2着: inn_2place ベース + winner_course_order 個人補正 ──
  if(hasInn2 && nigeWinProb > 0){
    const othersTP = ranked.filter(r => r.boat !== 1).reduce((s, r) => s + r.tenkai_prob, 0) || 1;
    for(const b of ranked){
      if(b.boat === 1) continue;
      const sc     = String(b.boat);
      const baseP2 = inn2Place[sc] ?? null;

      // winner_course_order: 「1号艇(wc='1')が1着のとき、自艇(sc)が2着に来た率」
      const personEntry = winnerCO[b.name]?.[sc]?.['1'];
      const personRate2 = (personEntry && personEntry.rate2 != null) ? personEntry.rate2 : null;
      const personTrust = (personEntry && personEntry.trust != null) ? personEntry.trust : 0;

      let p2;
      if(baseP2 != null && personRate2 != null && personTrust > 0.3){
        // 個人実績と inn_2place をブレンド（personTrust で重み付け）※閾値: 0.3（count>=10相当）
        p2 = personRate2 * personTrust + baseP2 * (1 - personTrust);
      } else if(baseP2 != null){
        p2 = baseP2;
      } else {
        // inn_2place にもデータなし → tenkai_prob 相対値
        p2 = tpMap[b.boat] / othersTP;
      }
      place2Score[b.boat] += nigeWinProb * p2;
    }
  }

  // ── 非逃げ展開（差し・まくり等）の2着: tenkai_remaining + winner_course_order ──
  const nonNigeProb = 1.0 - nigeWinProb;
  // tenkai_remaining: {決まり手: {1着コース: {進入コース: {rate2, trust}}}}
  // 会場別データ優先、なければ全国実績にフォールバック（calcScenarioData と統一）
  const tenkaiRemaining = (() => {
    const vLocal = MASTER_EXT?.venue_stats?.[DATA.venue]?.tenkai_remaining;
    if(vLocal && Object.keys(vLocal).length > 0) return vLocal;
    return MASTER_EXT?.tenkai_remaining || {};
  })();
  if(nonNigeProb > 0){
    for(const winner of ranked){
      const winnerProb = nonNigeProb * (tpMap[winner.boat] / totalTP);
      if(winnerProb <= 0) continue;
      const wc = String(winner.boat);
      const othersTotal = ranked.filter(b => b.boat !== winner.boat)
                                .reduce((s, b) => s + b.tenkai_prob, 0) || 1;

      // vKimari × tenkai_remaining が使える場合は決まり手別に残存率を集計
      let usedRemaining = false;
      if(vKimari && Object.keys(tenkaiRemaining).length > 0){
        const validKimariTot = Object.entries(vKimari)
          .filter(([k]) => k in tenkaiRemaining && tenkaiRemaining[k][wc])
          .reduce((s, [, v]) => s + v, 0);
        if(validKimariTot > 0){
          for(const self of ranked){
            if(self.boat === winner.boat) continue;
            const sc = String(self.boat);
            // ── tenkai_remaining の全国実績を決まり手加重平均で集計 ──
            let p2sum = 0, wsum = 0;
            for(const [kimari, kRate] of Object.entries(vKimari)){
              const entry = tenkaiRemaining[kimari]?.[wc]?.[sc];
              if(entry && entry.rate2 != null){
                const w = kRate * (entry.trust ?? 0.5);
                p2sum += entry.rate2 * w;
                wsum  += w;
              }
            }
            if(wsum > 0){
              const baseTR = p2sum / wsum;
              // ── winner_course_order で個人補正 ──
              // キー: winnerCO[自艇名][自コース(sc)][勝者コース(wc)]
              const personEntry = winnerCO[self.name]?.[sc]?.[wc];
              const personRate2 = (personEntry && personEntry.rate2 != null) ? personEntry.rate2 : null;
              const personTrust = (personEntry && personEntry.trust != null) ? personEntry.trust : 0;
              let p2;
              if(personRate2 != null && personTrust > 0.3){
                // 会場別実績と個人実績をブレンド ※閾値: 0.3（count>=10相当）
                const wNat = (1 - personTrust);
                p2 = (personRate2 * personTrust + baseTR * wNat);
              } else {
                p2 = baseTR;
              }
              place2Score[self.boat] += winnerProb * p2;
              usedRemaining = true;
            } else {
              place2Score[self.boat] += winnerProb * (tpMap[self.boat] / othersTotal);
            }
          }
        }
      }
      if(!usedRemaining){
        for(const self of ranked){
          if(self.boat === winner.boat) continue;
          place2Score[self.boat] += winnerProb * (tpMap[self.boat] / othersTotal);
        }
      }
    }
  }

  // 正規化
  const p2Total = Object.values(place2Score).reduce((a, b) => a + b, 0) || 1;
  const res = {};
  ranked.forEach(b => { res[b.boat] = place2Score[b.boat] / p2Total; });
  return res;
}

// venue_kimari が有効かどうか判定（1着率補正に使う）
function hasMasterExt(){
  return !!(MASTER_EXT &&
    MASTER_EXT.venue_kimari &&
    Object.keys(MASTER_EXT.venue_kimari).length > 0);
}
function tenkaiLabel(arek){
  if(arek < 40) return { label:'逃げ展開', cls:'safe', icon:'🏃' };
  if(arek > 60) return { label:'まくり展開', cls:'warn', icon:'💥' };
  return { label:'混戦展開', cls:'mix', icon:'🔀' };
}
function combo2(a,b){ return `${Math.min(a,b)}＝${Math.max(a,b)}`; }

// ── 展開シナリオ計算（純粋関数）──
//
// 買い目生成・HTML表示の両方から参照する共通計算。
// 戻り値:
//   {
//     scenarioProb  : {boat: {kimari: 発生確率}},
//     scenarioPlace2: {boat: {kimari: [{boat, p2}]}},  // 正規化済み2着リスト（展示係数補正済み）
//     kimariTypes   : string[],
//     inn2Place     : object,
//     top3          : ranked2の上位3艇,
//     valid         : boolean  // MASTERなし等で計算不可の場合 false
//   }
//
// tenjiScoreMap: calcTenjiScore の戻り値（展示データなし時は null）
//   __coef_N（平均=1.0基準）を 2着確率の補正に使用。
//   null の場合は補正なし（係数=1.0 として扱う）。
//   補正強度は TENJI_P2_COEF_CLIP でクリップ（過補正防止）。
//
function calcScenarioData(ranked2, rawBoats, tenjiScoreMap){
  if(!MASTER_EXT || !MASTER_EXT.venue_kimari){
    return { valid: false };
  }
  const venue   = DATA.venue;
  const vKimari = MASTER_EXT.venue_kimari[venue];
  if(!vKimari) return { valid: false };

  // inn_2place: inn_data に直接入っていれば使用、なければ venue_stats から取得
  const inn2Place = (() => {
    const v = (DATA.inn_data || {}).inn_2place;
    if(v && typeof v === 'object' && !Array.isArray(v) && Object.keys(v).length > 0) return v;
    return MASTER_EXT?.venue_stats?.[DATA.venue]?.inn_2place || {};
  })();

  const KIMARI_HARD_EXCLUDE = {
    '逃げ':       new Set(['2','3','4','5','6']),
    '差し':       new Set(['1']),
    'まくり':     new Set(['1']),
    'まくり差し': new Set(['1','2']),
    '抜き':       new Set(),
  };
  function isValidFirst(boat, kimari){
    const wc = String(boat.boat);
    const exc = KIMARI_HARD_EXCLUDE[kimari];
    if(!exc) return false;
    return !exc.has(wc);
  }

  // ── 1コース被kimariでvKimariを補正 ──
  const boat1Scenario = rawBoats.find(b => b.boat === 1) || null;
  let scenarioVKimari = { ...vKimari };
  if(boat1Scenario){
    const hiKimari = MASTER_EXT?.course_master?.[boat1Scenario.name]?.['1']?.['被kimari'];
    const boat1Runs = MASTER_EXT?.course_master?.[boat1Scenario.name]?.['1']?.runs ?? 0;
    if(hiKimari && boat1Runs >= 30){
      const hiTrust = Math.min(boat1Runs / 100, 1.0);
      const hiStr   = getHiKimariStrength(venue); // 会場別強度 (calcTenkaiProbs と同一テーブル参照)
      const sasareRate       = hiKimari['差され']     ?? null;
      const makurareRate     = hiKimari['捲られ']     ?? null;
      const makurisasareRate = hiKimari['捲り差され'] ?? null;
      if(sasareRate !== null)
        scenarioVKimari['差し'] = (vKimari['差し'] || 0) * (1 + hiTrust * sasareRate * hiStr);
      if(makurareRate !== null)
        scenarioVKimari['まくり'] = (vKimari['まくり'] || 0) * (1 + hiTrust * makurareRate * hiStr);
      if(makurisasareRate !== null)
        scenarioVKimari['まくり差し'] = (vKimari['まくり差し'] || 0) * (1 + hiTrust * makurisasareRate * hiStr);
      const totalHiRate = (sasareRate ?? 0) + (makurareRate ?? 0) + (makurisasareRate ?? 0);
      const nigeRate = MASTER_EXT?.course_master?.[boat1Scenario.name]?.['1']?.kimari?.['逃げ'] ?? 0;
      if(nigeRate > 0){
        const nigeBoost = nigeRate / Math.max(nigeRate + totalHiRate, 0.01);
        scenarioVKimari['逃げ'] = (vKimari['逃げ'] || 0) * (0.5 + 0.5 * nigeBoost * 2);
      }
      const adjTotal = Object.values(scenarioVKimari).reduce((s, v) => s + v, 0);
      if(adjTotal > 0){
        for(const k of Object.keys(scenarioVKimari))
          scenarioVKimari[k] = scenarioVKimari[k] / adjTotal;
      }
    }
  }

  const kimariTypes = Object.keys(scenarioVKimari).filter(k => scenarioVKimari[k] > 0 && k in KIMARI_HARD_EXCLUDE && k !== '抜き');

  // ── winner艇の個人kimari率をscenarioVKimariにブレンド ──
  const SCENARIO_BLEND_STRENGTH = 0.7;
  function blendPersonalKimariScenario(boatObj, baseVKimari){
    const name   = boatObj.name;
    const course = String(boatObj.boat);
    const cm     = MASTER_EXT?.course_master?.[name]?.[course];
    if(!cm) return baseVKimari;
    const runs = cm.runs ?? 0;
    if(runs < 20) return baseVKimari; // データ不足はスキップ（blendPersonalKimariと閾値統一: 20走）
    const trust = Math.min(runs / 100, 1.0) * SCENARIO_BLEND_STRENGTH;
    const personalKimari = cm.kimari ?? {};
    const BLEND_TARGETS = ['差し', 'まくり', 'まくり差し', '抜き'];
    const personalTotal = BLEND_TARGETS.reduce((s, k) => s + (personalKimari[k] ?? 0), 0);
    if(personalTotal <= 0) return baseVKimari;
    const blended = { ...baseVKimari };
    const venueBlendSum = BLEND_TARGETS.reduce((s, kk) => s + (baseVKimari[kk] ?? 0), 0);
    for(const k of BLEND_TARGETS){
      if(!(k in blended)) continue;
      const personalRate = (personalKimari[k] ?? 0) / personalTotal * venueBlendSum;
      blended[k] = baseVKimari[k] * (1 - trust) + personalRate * trust;
    }
    const origTotal  = Object.values(baseVKimari).reduce((s, v) => s + v, 0);
    const blendTotal = Object.values(blended).reduce((s, v) => s + v, 0);
    if(blendTotal > 0){
      for(const k of Object.keys(blended)) blended[k] = blended[k] / blendTotal * origTotal;
    }
    return blended;
  }

  // 1着率上位3艇（後方互換・表示タイトル用に保持）
  const top3 = ranked2.slice(0, 3);

  // 各1着候補について決まり手別の発生確率を計算（全艇対象）
  const scenarioProb = {};
  for(const winner of ranked2){
    scenarioProb[winner.boat] = {};
    const winnerVKimari = blendPersonalKimariScenario(winner, scenarioVKimari);
    const validKimariTotal = kimariTypes
      .filter(k => isValidFirst(winner, k))
      .reduce((s, k) => s + (winnerVKimari[k] || 0), 0);
    if(validKimariTotal <= 0) continue;
    for(const kimari of kimariTypes){
      if(!isValidFirst(winner, kimari)) continue;
      // final_prob: 基準確率×展開係数×展示係数を正規化した最終1着率（展示加味済み）
      // ここで final_prob を使うことで展示評価がシナリオ発生確率に直接反映される。
      // final_prob が未設定（MASTERなし等）の場合は tenkai_prob にフォールバック。
      const baseWeight = winner.final_prob ?? winner.tenkai_prob;
      scenarioProb[winner.boat][kimari] = baseWeight * (winnerVKimari[kimari] / validKimariTotal);
    }
  }

  // ── 各シナリオの2着リストを計算して scenarioPlace2 に格納 ──
  const tenkaiRem = (() => {
    const vLocal = MASTER_EXT?.venue_stats?.[DATA.venue]?.tenkai_remaining;
    if(vLocal && typeof vLocal === 'object' && Object.keys(vLocal).length > 0) return vLocal;
    return MASTER_EXT?.tenkai_remaining || {};
  })();
  const winnerCO = MASTER_EXT?.winner_course_order || {};

  const scenarioPlace2 = {};
  for(const winner of ranked2){
    scenarioPlace2[winner.boat] = {};
    const wc = String(winner.boat);
    // final_prob（展示加味済み最終確率）ベースで他艇の合計を算出
    const othersTotal = ranked2
      .filter(r => r.boat !== winner.boat)
      .reduce((s, r) => s + (r.final_prob ?? r.tenkai_prob), 0) || 1;

    for(const kimari of kimariTypes){
      if(!(scenarioProb[winner.boat]?.[kimari] > 0)) continue;

      const useInn2 = (kimari === '逃げ' && winner.boat === 1 && Object.keys(inn2Place).length > 0);
      const remForThis = tenkaiRem[kimari]?.[wc] || null;

      const place2List = rawBoats
        .filter(b => b.boat !== winner.boat)
        .map(b => {
          const sc = String(b.boat);
          let p2;
          if(useInn2){
            const baseP2 = inn2Place[sc] ?? null;
            const personEntry2 = winnerCO[b.name]?.[sc]?.['1'];
            const personRate2  = personEntry2?.rate2 ?? null;
            const personTrust2 = personEntry2?.trust ?? 0;
            if(baseP2 != null && personRate2 != null && personTrust2 > 0.3){ // 他箇所と統一(count>=10相当)
              p2 = personRate2 * personTrust2 + baseP2 * (1 - personTrust2);
            } else {
              p2 = baseP2;
            }
            if(p2 == null){
              const bt = ranked2.find(r => r.boat === b.boat);
              p2 = bt ? (bt.final_prob ?? bt.tenkai_prob) / othersTotal : 0;
            }
          } else if(remForThis){
            const remEntry  = remForThis[sc];
            const baseTR    = remEntry?.rate2 ?? null;
            const trTrust   = remEntry?.trust ?? 0;
            const personEntry = winnerCO[b.name]?.[sc]?.[wc];
            const personRate2 = personEntry?.rate2 ?? null;
            const personTrust = personEntry?.trust ?? 0;
            if(baseTR != null && personRate2 != null && personTrust > 0.3){
              const wPerson = personTrust;
              const wNat    = trTrust * (1 - personTrust);
              const wTot    = wPerson + wNat;
              p2 = wTot > 0 ? (personRate2 * wPerson + baseTR * wNat) / wTot : baseTR;
            } else if(baseTR != null){
              p2 = baseTR;
            } else {
              const bt = ranked2.find(r => r.boat === b.boat);
              p2 = bt ? (bt.final_prob ?? bt.tenkai_prob) / othersTotal : 0;
            }
          } else {
            const bt = ranked2.find(r => r.boat === b.boat);
            p2 = bt ? (bt.final_prob ?? bt.tenkai_prob) / othersTotal : 0;
          }
          return { boat: b.boat, name: b.name, p2 };
        });

      // 展示係数補正（問題3対応）
      //
      // 正規化前に各艇の展示係数（平均=1.0基準）を p2 に乗算する。
      // 展示が速い艇は p2 が上昇、遅い艇は p2 が低下。
      // 正規化後も相対順位のみ変わるため、合計は常に 1.0 を維持する。
      //
      // 過補正防止: 係数は枠番別クリップ範囲を適用。
      //   3〜5枠（差し・まくり主体）は展示の影響を強く効かせるため範囲を広げる。
      //   1〜2枠はイン優位が支配的なため狭く抑える。
      //
      const TENJI_P2_CLIP_BY_COURSE = {
        1: [0.85, 1.20],  // イン有利、展示で大きく変動しない
        2: [0.80, 1.25],
        3: [0.70, 1.40],  // 差し・まくり差し主体、展示が効く
        4: [0.65, 1.45],  // まくり最多、展示差が2着にも直結
        5: [0.70, 1.40],
        6: [0.75, 1.35],
      };
      if(tenjiScoreMap){
        place2List.forEach(x => {
          const [lo, hi] = TENJI_P2_CLIP_BY_COURSE[x.boat] ?? [0.75, 1.35];
          const rawCoef = tenjiScoreMap[`__coef_${x.boat}`] ?? 1.0;
          const coef    = Math.min(hi, Math.max(lo, rawCoef));
          x.p2 *= coef;
        });
      }

      const p2Sum = place2List.reduce((s, x) => s + x.p2, 0) || 1;
      place2List.forEach(x => { x.p2 = x.p2 / p2Sum; });
      place2List.sort((a, b) => b.p2 - a.p2);
      scenarioPlace2[winner.boat][kimari] = place2List;
    }
  }

  return { valid: true, scenarioProb, scenarioPlace2, kimariTypes, inn2Place, top3, scenarioVKimari, isValidFirst };
}

// ── 展開シナリオセクション生成（強化版: 2着+3着確率表示・1着率信頼度バー付き）──
//
// 全艇 × 全決まり手の発生確率から上位3シナリオを抽出して表示。
// 「決まり手」を主軸にし、同じ決まり手の重複は最上位1件のみ残す。
// 2着率: 逃げ(1コース1着)→inn_2place, それ以外→tenkai_remaining+winner_course_order
// 3着率: tenkai_remaining.rate3 × winner_course_order.rate3 個人補正ブレンド
// ── トップレベル関数（buildScenarioSection・renderBuy 両方から参照）──
function calc3rdScores(ranked2, tenjiScoreMap, winnerBoat, kimari, secondBoat){
  const tenkaiRem = (() => {
    const vLocal = MASTER_EXT?.venue_stats?.[DATA.venue]?.tenkai_remaining;
    if(vLocal && typeof vLocal === 'object' && Object.keys(vLocal).length > 0) return vLocal;
    return MASTER_EXT?.tenkai_remaining || null;
  })();
  const winnerCO = MASTER_EXT?.winner_course_order || {};
  const wc = String(winnerBoat);
  return ranked2
    .filter(b => b.boat !== winnerBoat && b.boat !== secondBoat)
    .map(b => {
      const sc = String(b.boat);
      const entry   = tenkaiRem?.[kimari]?.[wc]?.[sc];
      const baseR3  = entry?.rate3 ?? null;
      const personEntry = winnerCO[b.name]?.[sc]?.[wc];
      const personR3    = personEntry?.rate3 ?? null;
      const personTrust = personEntry?.trust  ?? 0;
      let r3;
      if(baseR3 != null && personR3 != null && personTrust > 0.3){
        r3 = personR3 * personTrust + baseR3 * (1 - personTrust);
      } else if(personR3 != null && personTrust > 0.3){
        r3 = personR3;
      } else {
        r3 = baseR3;
      }
      const tenjiCoef = tenjiScoreMap ? (tenjiScoreMap[`__coef_${b.boat}`] ?? 1.0) : 1.0;
      const CLIP3_BY_COURSE = {
        1: [0.85, 1.20],
        2: [0.80, 1.25],
        3: [0.70, 1.40],
        4: [0.65, 1.45],
        5: [0.70, 1.40],
        6: [0.75, 1.35],
      };
      const [c3lo, c3hi] = CLIP3_BY_COURSE[b.boat] ?? [0.75, 1.35];
      const clipped = Math.min(c3hi, Math.max(c3lo, tenjiCoef));
      let score = r3 != null ? r3 * clipped : (b.final_prob ?? b.tenkai_prob ?? 0);

      // ── 2着艇の強さ補正: 2着が強いほど残り枠が埋まり3着争いが狭まる ──
      if(secondBoat != null){
        const secondFP = ranked2.find(r => r.boat === secondBoat)?.final_prob ?? (1/6);
        const secondFPNorm = secondFP / (ranked2.reduce((s, r) => s + (r.final_prob ?? r.tenkai_prob ?? 0), 0) || 1);
        const secondOccupyAdj = Math.max(0.7, 1.0 - secondFPNorm * 0.5);
        score *= secondOccupyAdj;
      }

      return { boat: b.boat, name: b.name, r3, score };
    })
    .sort((a, b) => b.score - a.score);
}

//
function buildScenarioSection(ranked2, place2Map, rawBoats, tenjiScoreMap, hasTenji){
  const sd = calcScenarioData(ranked2, rawBoats, tenjiScoreMap);
  if(!sd.valid) return '';

  const { scenarioProb, scenarioPlace2, kimariTypes } = sd;

  // tenkaiRem & winnerCO（3着率取得用）
  const tenkaiRem_scen = (() => {
    const vLocal = MASTER_EXT?.venue_stats?.[DATA.venue]?.tenkai_remaining;
    if(vLocal && typeof vLocal === 'object' && Object.keys(vLocal).length > 0) return vLocal;
    return MASTER_EXT?.tenkai_remaining || null;
  })();
  const winnerCO_scen = MASTER_EXT?.winner_course_order || {};

  // 3着スコアを計算する関数 → トップレベルの calc3rdScores に委譲
  function calc3rdScoresLocal(winnerBoat, kimari, secondBoat){
    return calc3rdScores(ranked2, tenjiScoreMap, winnerBoat, kimari, secondBoat);
  }

  const boatCircle = (n) =>
    `<span class="boat-circle b${n}" style="width:20px;height:20px;font-size:10px;line-height:20px;display:inline-flex;align-items:center;justify-content:center;flex-shrink:0">${n}</span>`;

  // ── 艇ごとに全決まり手の確率を合算し、final_prob上位3艇を選出 ──
  // 各艇の「代表決まり手」= その艇のscenarioProbが最大のkimari
  // 右端合計 = final_prob と一致する
  const top3Scenarios = ranked2
    .filter(winner => {
      const total = kimariTypes.reduce((s, k) => s + (scenarioProb[winner.boat]?.[k] ?? 0), 0);
      return total > 0.001;
    })
    .slice(0, 3)
    .map(winner => {
      // 代表決まり手: このwinner艇でscenarioProbが最大のkimari
      let bestKimari = kimariTypes[0];
      let bestProb = 0;
      for(const k of kimariTypes){
        const p = scenarioProb[winner.boat]?.[k] ?? 0;
        if(p > bestProb){ bestProb = p; bestKimari = k; }
      }
      return { boat: winner.boat, name: winner.name, final_prob: winner.final_prob, kimari: bestKimari, prob: bestProb };
    });

  if(top3Scenarios.length === 0) return '';

  // ── 艇ごとに全決まり手をscenariosに格納（2着・3着の加重平均に全kimariを使う）──
  // totalProb = final_prob と一致する
  const boatGroups = new Map();
  for(const sc of top3Scenarios){
    // 全kimariをscenariosに追加
    const allScens = kimariTypes
      .map(k => ({ kimari: k, prob: scenarioProb[sc.boat]?.[k] ?? 0, place2List: scenarioPlace2[sc.boat]?.[k] || [] }))
      .filter(x => x.prob > 0.001);
    boatGroups.set(sc.boat, {
      boat: sc.boat,
      name: sc.name,
      bestKimari: sc.kimari,  // 代表決まり手（バッジ表示用）
      scenarios: allScens,
    });
  }

  // グループを合計確率の降順でソート
  const groupList = [...boatGroups.values()]
    .sort((a, b) =>
      b.scenarios.reduce((s, x) => s + x.prob, 0) -
      a.scenarios.reduce((s, x) => s + x.prob, 0)
    );

  // 決まり手→カラー
  const KIMARI_COLOR = {
    '逃げ': 'var(--accent2)', '差し': 'var(--green)',
    'まくり': 'var(--red)', 'まくり差し': 'var(--orange)', '抜き': 'var(--text3)'
  };
  const KIMARI_BG = {
    '逃げ': 'rgba(0,102,255,.1)', '差し': 'rgba(0,184,107,.1)',
    'まくり': 'rgba(255,59,59,.1)', 'まくり差し': 'rgba(255,122,0,.1)', '抜き': 'rgba(108,122,148,.1)'
  };

  const scenarioBlocks = groupList.map((grp) => {
    const totalProb = grp.scenarios.reduce((s, x) => s + x.prob, 0);
    const isMulti = true; // 全kimariを加重平均するため常にtrue

    // ── 2着確率を加重平均で合算 ──
    // 各シナリオの place2List を prob で重み付けして同一艇番ごとに合算し正規化する
    const mergedP2Map = {}; // boat番号 → { boat, name, p2sum }
    for(const scen of grp.scenarios){
      const w = scen.prob / (totalProb || 1); // シナリオ重み（合計1.0）
      for(const item of scen.place2List){
        if(!mergedP2Map[item.boat]){
          mergedP2Map[item.boat] = { boat: item.boat, name: item.name, p2sum: 0 };
        }
        mergedP2Map[item.boat].p2sum += item.p2 * w;
      }
    }
    // p2sum を正規化（合計が1.0になるよう）
    const p2Total = Object.values(mergedP2Map).reduce((s, x) => s + x.p2sum, 0) || 1;
    const mergedPlace2 = Object.values(mergedP2Map)
      .map(x => ({ boat: x.boat, name: x.name, p2: x.p2sum / p2Total }))
      .sort((a, b) => b.p2 - a.p2);

    const top4Place = mergedPlace2.slice(0, 4);

    // ── 3着確率も加重平均で合算 ──
    // 各2着候補に対して、複数シナリオ分の3着スコアをシナリオ確率で加重平均する
    function calcMerged3rd(secondBoat){
      const r3Map = {}; // boat番号 → { boat, r3sum, scoreSum, weight }
      for(const scen of grp.scenarios){
        const w = scen.prob / (totalProb || 1);
        const thirds = calc3rdScoresLocal(grp.boat, scen.kimari, secondBoat);
        for(const t3 of thirds){
          if(!r3Map[t3.boat]){
            r3Map[t3.boat] = { boat: t3.boat, r3sum: 0, scoreSum: 0, r3Count: 0, scoreCount: 0 };
          }
          if(t3.r3 != null){
            r3Map[t3.boat].r3sum   += t3.r3 * w;
            r3Map[t3.boat].r3Count += w;
          }
          r3Map[t3.boat].scoreSum   += t3.score * w;
          r3Map[t3.boat].scoreCount += w;
        }
      }
      return Object.values(r3Map)
        .map(x => ({
          boat:  x.boat,
          r3:    x.r3Count > 0 ? x.r3sum / x.r3Count : null,
          score: x.scoreCount > 0 ? x.scoreSum / x.scoreCount : 0,
        }))
        .sort((a, b) => b.score - a.score);
    }

    // 各2着候補の行を生成
    const p2Lines = top4Place.map(item => {
      const third3     = (isMulti ? calcMerged3rd(item.boat) : calc3rdScoresLocal(grp.boat, grp.scenarios[0].kimari, item.boat)).slice(0, 3);
      const third3html = third3.map(t3 =>
        `<span style="display:inline-flex;align-items:center;gap:2px;white-space:nowrap">
          ${boatCircle(t3.boat)}
          <span style="font-size:11px;font-family:var(--mono);color:var(--text)">${t3.r3 != null ? (t3.r3*100).toFixed(0)+'%' : '—'}</span>
        </span>`
      ).join('<span style="color:var(--text3);margin:0 3px;font-size:11px">/</span>');

      return `<div style="display:flex;align-items:center;gap:6px;padding:4px 0;border-bottom:1px solid var(--border);flex-wrap:wrap">
        <span style="font-size:11px;color:var(--text3);flex-shrink:0">2着</span>
        ${boatCircle(item.boat)}
        <span style="font-size:11px;font-family:var(--mono);font-weight:600;color:var(--text);min-width:2.8em">${(item.p2*100).toFixed(0)}%</span>
        <span style="font-size:11px;color:var(--text3);flex-shrink:0;margin-left:2px">ー 3着</span>
        ${third3html}
      </div>`;
    }).join('');

    // ── ヘッダー部分: 代表決まり手バッジ（bestKimari）のみ表示 ──
    const bestK     = grp.bestKimari;
    const bestKProb = grp.scenarios.find(s => s.kimari === bestK)?.prob ?? 0;
    const kColor    = KIMARI_COLOR[bestK] || 'var(--accent2)';
    const kBg       = KIMARI_BG[bestK]    || 'rgba(108,122,148,.1)';
    const kimariBadges = `<span style="font-size:11px;font-weight:700;padding:2px 7px;border-radius:4px;background:${kBg};color:${kColor};flex-shrink:0">${bestK}<span style="font-weight:400;font-size:10px;margin-left:3px">${(bestKProb*100).toFixed(1)}%</span></span>`;

    return `<div style="padding:10px 0;border-bottom:1px solid var(--border)">
      <div style="display:flex;align-items:center;gap:6px;margin-bottom:8px;flex-wrap:wrap">
        ${boatCircle(grp.boat)}
        <span style="font-size:13px;font-weight:700;flex-shrink:0">${grp.name}</span>
        ${kimariBadges}
        <span style="font-size:13px;font-family:var(--mono);font-weight:700;color:var(--text);margin-left:auto;flex-shrink:0">${(totalProb*100).toFixed(1)}%</span>
      </div>
      <div style="padding-left:4px">${p2Lines}</div>
    </div>`;
  }).join('');

  const tenjiBadge = hasTenji
    ? `<span style="font-size:10px;font-weight:700;padding:1px 7px;border-radius:4px;background:rgba(0,102,255,.12);color:var(--accent2);margin-left:8px;vertical-align:middle">展示情報込み</span>`
    : '';

  return `<div style="padding:0.75rem 1.25rem;border-bottom:1px solid var(--border)">
    <div style="font-size:11px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--text3);margin-bottom:10px">展開シナリオ${tenjiBadge}</div>
    ${scenarioBlocks}
  </div>`;
}
// ── renderBuy ──
function renderBuy(rno){
  const rd = DATA.races[String(rno)];
  if(!rd) return;
  const arek     = rd.arek ?? 54.7;
  const rawBoats = rd.boats;

  // ── 買い目点数上限（betting_optimizer による推奨点数）──
  // opt_points が埋め込まれていればそれを使用、なければ 10点（デフォルト）
  // ※ 要注意会場（大村・宮島・福岡・丸亀）は最大7点で返ってくるため 0 は存在しない
  // 見送り推奨（pass_reason あり）でも買い目は参考表示するため上限は10点固定
  // 通常パターンは buyMode 別に opt_points_hit/rec を参照
  const _optHit  = rd.opt_points_hit != null ? rd.opt_points_hit : (rd.opt_points != null ? rd.opt_points : 10);
  const _optRec  = rd.opt_points_rec != null ? rd.opt_points_rec : (rd.opt_points != null ? rd.opt_points : 10);
  const _passHit = rd.opt_pass_reason_hit || '';
  const _passRec = rd.opt_pass_reason_rec || '';
  const BUY_MAX_POINTS_HIT = _passHit ? 10 : (_optHit > 0 ? _optHit : 10);
  const BUY_MAX_POINTS_REC = _passRec ? 10 : (_optRec > 0 ? _optRec : 10);
  const BUY_MAX_POINTS = BUY_MAX_POINTS_HIT; // 後方互換（buildBuy3ForMode のクロージャ参照用）

  // ─ STEP1: 1着率計算（venue_kimari × prob × 個人kimari適性）
  const ranked   = calcTenkaiProbs(rawBoats, arek);

  // ─ STEP2: 3スコア独立計算 → 加重合成（base:50% / tenkai:30% / tenji:20%）──
  //
  // 【変更点】
  //   旧: tenkai_prob に展示係数を連鎖乗算 → 二重加点/二重減点が発生していた
  //   新: 基準prob・相対補正スコア・展示スコアをそれぞれ独立計算し加算合成
  //       各スコアは互いを参照しない
  //
  const SLUG = {
    "桐生":"kiryu","戸田":"toda","江戸川":"edogawa","平和島":"heiwajima",
    "多摩川":"tamagawa","浜名湖":"hamanako","蒲郡":"gamagori","常滑":"tokoname",
    "津":"tsu","三国":"mikuni","びわこ":"biwako","住之江":"suminoe",
    "尼崎":"amagasaki","鳴門":"naruto","丸亀":"marugame","児島":"kojima",
    "宮島":"miyajima","徳山":"tokuyama","下関":"shimonoseki","若松":"wakamatsu",
    "芦屋":"ashiya","福岡":"fukuoka","唐津":"karatsu","大村":"omura"
  };
  const slug      = SLUG[DATA.venue] || DATA.venue;
  const tKey      = tenjiKey(slug, DATA.date, rno);
  const tenjiData = _tenjiCache[tKey] || null;
  const hasTenji  = !!tenjiData;

  // 展示独立スコアを取得（展示データがある場合のみ）
  let tenjiScoreMap = null;
  if(hasTenji){
    tenjiScoreMap = calcTenjiScore(ranked, tenjiData, DATA.venue, arek);
  }

  // ── STEP2: 指数重み方式で最終確率を計算 ──
  //
  //   final_prob ∝ baseNorm^wBase × tenkaiCoef^wTenkai × tenjiCoef^wTenji
  //
  //   FINAL_PROB_WEIGHTS の各値がべき乗の指数として機能する。
  //   weight=1.0 → 素の乗算と同じ挙動
  //   weight=2.0 → その指標の影響を2倍強く効かせる
  //   weight=0.0 → その指標を完全に無効化（係数が何であっても1.0扱い）
  //
  //   展示データなし時: tenjiCoef=1.0 のため wTenji の値に関わらず影響ゼロ
  //
  const probTotal = ranked.reduce((s, b) => s + b.prob, 0) || 1;
  const useMaster = hasMasterExt() && !!MASTER_EXT.venue_kimari[DATA.venue];

  // arek連動動的重みを取得（荒れ会場ほどwTenkai増・wBase減）
  const { wBase, wTenkai, wTenji } = calcDynamicWeights(arek);

  // 各艇の展開係数・展示係数を算出
  const tenkaiOnlyTotal = ranked.reduce((s, x) => s + (x.tenkai_score ?? x.tenkai_prob), 0) || 1;

  // ── 枠番順に並んだrawBoatsから「1つ前コース（枠番-1）の艇」参照マップを生成 ──
  // 例: 4号艇なら3号艇を前コースとして参照
  const boatByNo = {};
  rawBoats.forEach(b => { boatByNo[b.boat] = b; });

  // 展示データ（枠番→テンジタイム）を取得
  const tenjiRawMap = {};  // { [boat番号]: tenji秒数 }
  if(hasTenji && tenjiData){
    const boatKeysTenji = Object.keys(tenjiData).filter(k => /^\d+$/.test(k));
    boatKeysTenji.forEach(k => {
      const entry = tenjiData[k];
      // テンジタイム: entry.tenji（数値）
      if(entry && typeof entry.tenji === 'number'){
        tenjiRawMap[parseInt(k)] = entry.tenji;
      }
    });
  }

  ranked.forEach(b => {
    const baseNorm    = b.prob / probTotal;  // 基準確率（正規化済み）

    // ── 1つ前コースの艇を取得（枠番 b.boat - 1）──
    const prevBoat = boatByNo[b.boat - 1] || null;

    // ── 展開補正: 展開スコアベース + ST順位相対差補正 ──
    let tenkaiCoef = 1.0;
    if(useMaster && baseNorm > 0){
      const tenkaiNorm = (b.tenkai_score ?? b.tenkai_prob) / tenkaiOnlyTotal;
      tenkaiCoef = Math.min(3.0, Math.max(0.3, tenkaiNorm / baseNorm));
    }
    // ST順位相対差補正: 1つ前コースの艇より0.5位早いごとに+0.05（半艇身前）
    // st_rank は小さいほど早い（1位=最速）
    if(prevBoat){
      const myStRank   = MASTER_EXT?.course_master?.[b.name]?.[String(b.boat)]?.st_rank;
      const prevStRank = MASTER_EXT?.course_master?.[prevBoat.name]?.[String(prevBoat.boat)]?.st_rank;
      if(myStRank != null && prevStRank != null){
        // 正: 前コースより早い（st_rankが小さい）→ 係数加算
        const stDiff = prevStRank - myStRank;  // 正値なら自艇が早い
        // 0.5位差ごとに半艇身（+0.05）→ 0.1/位
        const stAdj = stDiff * 0.10;
        tenkaiCoef = Math.min(3.0, Math.max(0.3, tenkaiCoef + stAdj));
      }
    }

    // ── 展示補正: 展示タイムスコアベース + 展示タイム相対差補正 ──
    let tenjiCoef = 1.0;
    if(tenjiScoreMap){
      tenjiCoef = tenjiScoreMap[`__coef_${b.boat}`] ?? 1.0;
    }
    // 展示タイム相対差補正: 1つ前コースの艇より0.1秒速いごとに+0.05（半艇身前）
    // tenji は小さいほど速い
    if(prevBoat && hasTenji){
      const myTenji   = tenjiRawMap[b.boat]    ?? null;
      const prevTenji = tenjiRawMap[prevBoat.boat] ?? null;
      if(myTenji != null && prevTenji != null){
        // 正: 前コースより速い（tenjiが小さい）→ 係数加算
        const tenjiDiff = prevTenji - myTenji;  // 正値なら自艇が速い
        // 0.1秒差ごとに半艇身（+0.05）→ 0.5/秒
        const tenjiAdj = tenjiDiff * 0.50;
        tenjiCoef = Math.min(2.0, Math.max(0.5, tenjiCoef + tenjiAdj));
      }
    }

    // ── スリット補正: 前艇(枠番-1)との ST差・展示タイム差から捲り優位を評価 ──
    //
    // 1枠は前艇なし → slitCoef=1.0（補正なし）
    // ST差・展示タイム差それぞれから係数を取得し乗算する。
    // SLIT_WEIGHT で全体の強度を調整（0=無効 / 1=フル適用）。
    //
    let slitCoef = 1.0;
    if(prevBoat && hasTenji && SLIT_WEIGHT > 0){
      // ST差係数（平均ST: MASTER_EXT から取得）
      const myStRank   = MASTER_EXT?.course_master?.[b.name]?.[String(b.boat)]?.st_rank;
      const prevStRank = MASTER_EXT?.course_master?.[prevBoat.name]?.[String(prevBoat.boat)]?.st_rank;
      let stSlitCoef = 1.0;
      if(myStRank != null && prevStRank != null){
        const stDiff = prevStRank - myStRank;  // 正値: 後艇が速い
        const found  = SLIT_ST_THRESHOLDS.find(t => stDiff >= t.min);
        stSlitCoef   = found ? found.coef : 1.0;
      }

      // 展示タイム差係数
      const myTenji2   = tenjiRawMap[b.boat]        ?? null;
      const prevTenji2 = tenjiRawMap[prevBoat.boat] ?? null;
      let tenjiSlitCoef = 1.0;
      if(myTenji2 != null && prevTenji2 != null){
        const tenjiDiff2 = prevTenji2 - myTenji2;  // 正値: 後艇が速い
        const found2     = SLIT_TENJI_THRESHOLDS.find(t => tenjiDiff2 >= t.min);
        tenjiSlitCoef    = found2 ? found2.coef : 1.0;
      }

      // ST差・展示差の乗算でスリット係数を確定
      const rawSlitCoef = stSlitCoef * tenjiSlitCoef;
      // SLIT_WEIGHT で中立値(1.0)に引き寄せる（0なら常に1.0、1なら rawSlitCoef そのまま）
      slitCoef = 1.0 + (rawSlitCoef - 1.0) * SLIT_WEIGHT;

      // ── まくりアラートボーナス ──
      // アラート発動条件: ST差≥0.5 かつ 展示差≥0.1（両条件の最強ランク同時成立）
      // 通常スリット補正に加えて追加ボーナスを付与する。
      const MAKURI_ALERT_BONUS = 0.30;  // ← 変更可: 0.1〜0.5推奨
      const myStRankA   = MASTER_EXT?.course_master?.[b.name]?.[String(b.boat)]?.st_rank ?? null;
      const prevStRankA = MASTER_EXT?.course_master?.[prevBoat.name]?.[String(prevBoat.boat)]?.st_rank ?? null;
      const myTenji2A   = tenjiRawMap[b.boat]        ?? null;
      const prevTenji2A = tenjiRawMap[prevBoat.boat] ?? null;
      const stAlertOk    = (myStRankA != null && prevStRankA != null) && (prevStRankA - myStRankA >= 0.5);
      const tenjiAlertOk = (myTenji2A != null && prevTenji2A != null) && (prevTenji2A - myTenji2A >= 0.1);
      if(stAlertOk && tenjiAlertOk){
        slitCoef += MAKURI_ALERT_BONUS;
      }

      slitCoef = Math.min(2.0, Math.max(0.5, slitCoef));
    }

    // 枠番別展示指数
    const wTenjiCourse = wTenji * (TENJI_WEIGHT_BY_COURSE[b.boat] ?? 1.0);

    // 1パス目: 各係数と baseNorm を保存（2パス目で後艇参照するため）
    b._baseNorm   = baseNorm;
    b._tenkaiCoef = tenkaiCoef;
    b._tenjiCoef  = tenjiCoef;
    b._wTenjiCourse = wTenjiCourse;
    b._slitCoef   = slitCoef;
    b.display_base   = baseNorm;
    b.display_tenkai = useMaster ? tenkaiCoef : null;
    b.display_tenji  = hasTenji  ? tenjiCoef  : null;
    b.display_slit   = hasTenji  ? slitCoef   : null;
  });

  // ══════════════════════════════════════════════════════════════════
  // 2パス目: 展開補正・展示補正・スリット補正を「加算ボーナス方式」で統一適用
  //
  // 【設計思想】
  //   従来の乗算方式では tenkaiCoef・tenjiCoef が baseNorm に依存して生成されるため、
  //   どれだけ係数が大きくても prob が低い艇の最終確率はほとんど変わらなかった。
  //   → 各補正を「全艇共通の基準値 × (係数-1.0) × 重み」として加算することで、
  //     prob に関わらず補正の絶対量が一定になり、外枠まくり艇が適切に評価される。
  //
  //   さらに後艇が有利（まくり・差し）な場合、前艇も対称的にペナルティを受ける。
  //
  // BONUS_BASE: 加算量の基準値（≒6艇均等時のbaseNorm=1/6に相当、調整可）
  // ══════════════════════════════════════════════════════════════════
  const BONUS_BASE_TENKAI = 0.15;  // 展開補正の加算強度（推奨: 0.10〜0.20）
  const BONUS_BASE_TENJI  = 0.15;  // 展示補正の加算強度（推奨: 0.10〜0.20）
  const SLIT_BONUS_BASE   = 0.15;  // スリット補正の加算強度（推奨: 0.10〜0.20）

  ranked.forEach(b => {
    const nextBoat = boatByNo[b.boat + 1] || null;

    // ── 展開補正: 自艇ボーナスのみ ──
    // 後艇の展開適性は自艇の展開評価とは独立（物理的な因果なし）
    const tenkaiBonus = BONUS_BASE_TENKAI * (b._tenkaiCoef - 1.0) * wTenkai;

    // ── 展示補正: 自艇ボーナスのみ ──
    const tenjiBonus  = BONUS_BASE_TENJI * (b._tenjiCoef - 1.0) * b._wTenjiCourse;

    // ── スリット補正: 自艇ボーナス − 後艇まくり優位ペナルティ ──
    // まくられる（後艇がスリット有利）という物理的因果があるためペナルティ適用
    const slitBonus   = SLIT_BONUS_BASE * (b._slitCoef - 1.0) * SLIT_WEIGHT;
    const nextSlitCoef = nextBoat?._slitCoef ?? 1.0;
    const slitPenalty = SLIT_BONUS_BASE * (nextSlitCoef - 1.0) * SLIT_WEIGHT;

    // baseNorm をそのまま基準スコアとして使用（指数乗算廃止）
    b._multi_score = Math.max(0.001,  // 確率がゼロ以下にならないよう下限保証
      b._baseNorm
      + tenkaiBonus
      + tenjiBonus
      + slitBonus - slitPenalty
    );

    // display_slit を net係数に更新（表示用）
    if(hasTenji){
      const netSlit = 1.0 + (slitBonus - slitPenalty) / (SLIT_BONUS_BASE * Math.max(SLIT_WEIGHT, 0.001));
      b.display_slit = Math.min(2.0, Math.max(0.5, netSlit));
    }
  });

  // 正規化して final_prob を確定
  const multiTotal = ranked.reduce((s, b) => s + b._multi_score, 0) || 1;
  ranked.forEach(b => {
    b.final_prob = b._multi_score / multiTotal;
    b.tenkai_prob_base  = b.tenkai_prob;
    b.tenji_score_indep = tenjiScoreMap ? (tenjiScoreMap[b.boat] ?? null) : null;
  });
  ranked.sort((a, b) => b.final_prob - a.final_prob);

  // ─ STEP3: 2着率計算（inn_2place ベース）
  const place2Map = calcPlace2Probs(rawBoats, ranked);
  // place2Map を各ボートに付与して2着ランクを作成
  const ranked2 = [...ranked].map(b=>({...b, place2_prob: place2Map[b.boat]||0}));

  const [A, B, C, D] = ranked;
  const mode    = tenkaiLabel(arek);
  const modeDesc = arek < 40
    ? `インの${A.name}（${A.boat}号）が主導権。逃げ・先マイが濃厚。`
    : arek > 60
      ? `${A.name}（${A.boat}号）軸だが、まくり・差しが入りやすい展開。`
      : `${A.name}（${A.boat}号）中心だが${B.name}（${B.boat}号）との競り合いも。`;

  const probDiff   = A.final_prob - B.final_prob;
  // 乖離率（%）: DIVERGENCE_THRESHOLD_HIT と同一単位で比較する
  // 旧: probDiff <= 0.05（固定5%）→ 新: DIVERGENCE_THRESHOLD_HIT（デフォルト12%）未満を僅差とみなす
  const probDiffPct = probDiff * 100;
  const isDualAxis  = probDiffPct < DIVERGENCE_THRESHOLD_HIT;

  // ─ STEP4 & STEP5: 展開シナリオベースの買い目生成
  //
  // 【1着軸の決定】
  //   1号艇 final_prob が会場平均（inn_data.course_rates[1]）を下回る場合、
  //   1号艇を除いた中でシナリオ確率合計が最大の艇を本命軸とする。
  //   それ以外は final_prob 1位（= A）を本命軸とする。
  //
  // 【2着候補の選定】
  //   各シナリオの place2List から確率を累積し、合計50%以上になるまで採用。
  //   逃げシナリオ(1号艇逃げ)では inn_2place の会場平均を上回る艇を優先。
  //
  // 【3着の選定】
  //   全艇のうち final_prob 最下位の艇を除外した残りを流す。
  //
  // 【MASTERなし時】place2_prob ベースの旧ロジックにフォールバック。

  const innData_buy  = DATA.inn_data || {};
  const cRates_buy   = innData_buy.course_rates || [];
  const inn2Place_buy = (() => {
    const v = innData_buy.inn_2place;
    if(v && typeof v === 'object' && !Array.isArray(v) && Object.keys(v).length > 0) return v;
    return MASTER_EXT?.venue_stats?.[DATA.venue]?.inn_2place || {};
  })();

  // 会場平均1コース1着率
  const venueAvgCourse1 = cRates_buy[1] ?? null;

  // 1号艇が会場平均を下回るか
  const boat1 = ranked2.find(b => b.boat === 1);
  const boat1BelowAvg = (venueAvgCourse1 !== null && boat1)
    ? boat1.final_prob < venueAvgCourse1
    : false;

  // ── 3着: rate3 最下位1艇を除外して残り全流し ──
  //
  // pick3rd(winnerBoat, kimari, secondBoat) で呼び出す。
  // シナリオの rate3（個人補正ブレンド済み）が最も低い艇を1艇除外し、
  // 残り全艇を3着候補として返す。
  // rate3 データが全くない場合は final_prob 最下位を除外してフォールバック。
  //
  const tenkaiRem_buy = (() => {
    const vLocal = MASTER_EXT?.venue_stats?.[DATA.venue]?.tenkai_remaining;
    if(vLocal && typeof vLocal === 'object' && Object.keys(vLocal).length > 0) return vLocal;
    return MASTER_EXT?.tenkai_remaining || null;
  })();

  // winner_course_order（個人実績）: renderBuy スコープで参照できるよう定義
  const winnerCO_buy = MASTER_EXT?.winner_course_order || {};

  // calcScenarioData を先読み（軸決定より前に呼ぶため）
  // tenjiScoreMap を渡して 2着確率に展示係数を反映させる（問題3対応）
  const sd = calcScenarioData(ranked2, rawBoats, tenjiScoreMap);

  // ── 軸信頼度判定（if(sd.valid)の外で定義しないと参照エラーになる）──
  const venueAvg1_buy = cRates_buy[1] ?? 0.45;
  const top1FinalProb = ranked2[0]?.final_prob ?? 0;

  // ── 【改修】的中重視モード: 1着固定軸の採用条件 ──
  // 仕様（変更）:
  //   ① final_prob 1位と2位の乖離率 ≥ DIVERGENCE_THRESHOLD_HIT（デフォルト12%）
  //   ② その1位艇の最終確率順位が1位（= 実質同義だが明示）
  // → 乖離が十分に大きい場合のみ1位艇を1艇固定軸とする。
  //    乖離が閾値未満（isDualAxis=true）の場合は2頭軸展開に自動移行。
  // ※ 旧条件「1号艇が場平均以上 AND top2以内」は廃止。
  //    1号艇かどうかは axisReliable の判定に含めない（rec側で制御）。
  const boat1ForAxis   = ranked2.find(b => b.boat === 1);
  const boat1FinalProb = boat1ForAxis?.final_prob ?? 0;
  const boat1RankAmongFinal = [...ranked2]
    .sort((a, b) => (b.final_prob ?? 0) - (a.final_prob ?? 0))
    .findIndex(b => b.boat === 1);
  // axisReliable: 乖離率が閾値以上（= isDualAxis が偽）のとき真
  const axisReliable = !isDualAxis; // isDualAxis=true（僅差）のとき false になる
  // 後方互換: boat1AboveAvg は rec 側の判定で引き続き使用
  const boat1AboveAvg = boat1FinalProb >= venueAvg1_buy;

  // ── 【改修】3着候補絞り込み関数（画面表示と同一データベース）──
  //
  // 旧: tenkaiRem_buy の rate3 を使用 → 画面の3着表示と乖離が発生
  // 新: 画面の展開シナリオ表示と同じ scenarioPlace2[winnerBoat][kimari] の p2 を使用
  //     （1着→2着→3着の流れで、2着候補リストから2着指定艇を除いた残りを
  //       p2 降順で累積まで採用する）
  //
  // buyMode: 'hit'（的中重視）または 'rec'（回収重視）
  //
  // 【2026-05-16 改修】モード別に3着累積目標を分離
  //   hit: 0.80 → 3着ヒモを広げて的中率向上（0.85はMAX10点上限と衝突し2軸目が押し出された）
  //   rec: 0.70 → 従来通り（配当重視のため絞りを維持）
  const PICK3_PROB_TARGET_HIT = 0.80; // 的中重視: 3着累積確率目標 80%
  const PICK3_PROB_TARGET_REC = 0.70; // 回収重視: 3着累積確率目標 70%（従来通り）

  function pick3rd(winnerBoat, kimari, secondBoat, buyMode){
    const pick3Target = (buyMode === 'hit') ? PICK3_PROB_TARGET_HIT : PICK3_PROB_TARGET_REC;

    if(!sd.valid) {
      // MASTERなしフォールバック: final_prob 降順でモード別累積%
      const allBoats = ranked2.map(b => b.boat).filter(b => b !== winnerBoat && b !== secondBoat);
      if(allBoats.length <= 2) return allBoats;
      const sorted = [...allBoats].sort((a, b) => {
        const fa = ranked2.find(r => r.boat === a)?.final_prob ?? 0;
        const fb = ranked2.find(r => r.boat === b)?.final_prob ?? 0;
        return fb - fa;
      });
      const totalFP = sorted.reduce((s, b) => s + (ranked2.find(r => r.boat === b)?.final_prob ?? 0), 0) || 1;
      const picked = []; let cum = 0;
      for(const b of sorted){
        picked.push(b);
        cum += (ranked2.find(r => r.boat === b)?.final_prob ?? 0) / totalFP;
        if(cum >= pick3Target) break;
      }
      return picked;
    }

    // scenarioPlace2 から対象シナリオの p2 リストを取得
    // 2着指定艇・1着軸を除いた残りを p2 降順でモード別累積%まで採用
    const place2List = sd.scenarioPlace2[winnerBoat]?.[kimari] || [];
    const candidates = place2List.filter(x => x.boat !== winnerBoat && x.boat !== secondBoat);

    if(candidates.length === 0) return [];
    if(candidates.length <= 2) return candidates.map(x => x.boat);

    // p2 の合計で正規化してモード別累積%まで
    const totalP2 = candidates.reduce((s, x) => s + x.p2, 0) || 1;
    const picked = []; let cum = 0;
    for(const item of candidates){ // candidates は既に p2 降順ソート済み
      picked.push(item.boat);
      cum += item.p2 / totalP2;
      if(cum >= pick3Target) break;
    }
    return picked;
  }

  // ── モード別買い目生成関数 ──
  // buyMode: 'hit' | 'rec'
  // 1着軸選定ロジックもモードで変える:
  //   hit: final_prob 1位固定（ブレ排除）
  //   rec: top3Scen の1〜2位も候補（穴も許容）
  function buildBuy3ForMode(buyMode, maxPts){
    const b3    = [];
    const b3seen = new Set();
    const b2    = [];
    const b2seen = new Set();
    const MAX_PTS = (maxPts != null) ? maxPts : BUY_MAX_POINTS; // 10点上限

    function tryAdd3m(first, second, third, label, lc, prob, sg){
      const key = `${first}-${second}-${third}`;
      if(first===second||second===third||first===third) return;
      if(b3seen.has(key)) return;
      if(b3.length >= MAX_PTS) return;
      b3seen.add(key);
      b3.push({c:`${first}−${second}−${third}`, l:label, lc, prob: prob ?? null, scenarioGroup: sg ?? 0});
    }
    function tryAdd2m(first, second, label, lc, prob, sg){
      const key = `${first}-${second}`;
      if(first===second) return;
      if(b2seen.has(key)) return;
      b2seen.add(key);
      b2.push({c:`${first}−${second}`, l:label, lc, prob: prob ?? null, scenarioGroup: sg ?? 0});
    }

    if(sd.valid){
      const { scenarioProb, scenarioPlace2, kimariTypes } = sd;
      function kimariToLc(kimari){
        return { '逃げ':'bl-nige', '差し':'bl-sashi', 'まくり':'bl-makuri',
                 'まくり差し':'bl-makusas', '抜き':'bl-nuki' }[kimari] || 'bl-nuki';
      }

      // ── 【改修】2着閾値: hitモード 75% / recモード 70% ──
      // hit: 的中重視のため2着も拡張して取りこぼし削減
      // rec: 配当重視のため従来通り絞りを維持（10点上限圧迫を回避）
      const PICK2_PROB_TARGET_HIT2 = 0.75;
      const PICK2_PROB_TARGET_REC2 = 0.70;

      function pick2nd(winnerBoat, kimari, bMode){
        const pick2Target = (bMode === 'hit') ? PICK2_PROB_TARGET_HIT2 : PICK2_PROB_TARGET_REC2;
        const list = scenarioPlace2[winnerBoat]?.[kimari] || [];
        if(list.length === 0) return [];
        const isNige = (kimari === '逃げ' && winnerBoat === 1);
        let sorted;
        if(isNige && Object.keys(inn2Place_buy).length > 0){
          const avgRate = Object.values(inn2Place_buy).reduce((s,v)=>s+v,0) / Object.keys(inn2Place_buy).length;
          sorted = [...list].sort((a,b) => {
            const aAbove = (inn2Place_buy[String(a.boat)] ?? 0) >= avgRate ? 1 : 0;
            const bAbove = (inn2Place_buy[String(b.boat)] ?? 0) >= avgRate ? 1 : 0;
            if(bAbove !== aAbove) return bAbove - aAbove;
            return b.p2 - a.p2;
          });
        } else {
          sorted = [...list].sort((a,b) => b.p2 - a.p2);
        }
        // 累積 p2 がモード別目標以上になるまで追加
        const picked = [];
        let cum = 0;
        for(const item of sorted){
          if(item.boat === winnerBoat) continue;
          picked.push(item.boat);
          cum += item.p2;
          if(cum >= pick2Target) break;
        }
        return picked;
      }

      const allScenPairs = [];
      for(const winner of ranked2){
        for(const k of kimariTypes){
          const p = scenarioProb[winner.boat]?.[k];
          if(p > 0.001) allScenPairs.push({ boat: winner.boat, name: winner.name, kimari: k, prob: p });
        }
      }
      allScenPairs.sort((a, b) => b.prob - a.prob);
      const seenK = new Set();
      const top3Scen = [];
      for(const pair of allScenPairs){
        if(seenK.has(pair.kimari)) continue;
        seenK.add(pair.kimari);
        top3Scen.push(pair);
        if(top3Scen.length >= 3) break;
      }

      // ── 【改修】1着軸の決定（モード別）──
      //
      // ① 的中重視(hit):
      //   axisReliable（乖離率 ≥ DIVERGENCE_THRESHOLD_HIT）が真:
      //     1位艇を1艇固定軸（全シナリオ展開 + 他艇補完）
      //   axisReliable が偽（isDualAxis=true: 乖離率 < 閾値）:
      //     final_prob 1位艇 + 2位艇の2軸展開（各軸の最有力シナリオ）
      //     ※ 旧: axisReliable 偽のときも1位を強制先頭にしていたが、
      //        isDualAxis 経路で吸収するため廃止。
      //
      // ② 回収重視(rec):
      //   【改修】final_prob 1位が1号艇でないとき → 1・2位艇の両シナリオを展開（穴狙い）
      //   1号艇が1位のとき → top3Scen 順（通常フロー）
      let scenariosToProcess;
      if(buyMode === 'hit'){
        if(axisReliable){
          // ── 乖離率 ≥ 閾値: final_prob 1位艇を1艇固定軸 ──
          const fp1stBoat = ranked2[0]; // final_prob 降順ソート済みの先頭
          const boat1Scens = top3Scen.filter(s => s.boat === fp1stBoat.boat);
          if(boat1Scens.length === 0){
            const fp1stBest = allScenPairs.find(p => p.boat === fp1stBoat.boat);
            scenariosToProcess = fp1stBest ? [fp1stBest, ...top3Scen.filter(s => s.boat !== fp1stBoat.boat)] : top3Scen;
          } else {
            scenariosToProcess = [...boat1Scens, ...top3Scen.filter(s => s.boat !== fp1stBoat.boat)];
          }
        } else {
          // ── 乖離率 < 閾値（isDualAxis）: final_prob 1位 + 2位の2軸展開 ──
          const fp1stBoat = ranked2[0];
          const fp2ndBoat = ranked2[1];
          const dualAxes  = [fp1stBoat?.boat, fp2ndBoat?.boat].filter(Boolean);
          const dualScens = dualAxes.map(ax => allScenPairs.find(p => p.boat === ax)).filter(Boolean);
          const dualRest  = top3Scen.filter(s => !dualAxes.includes(s.boat)).slice(0, 1);
          scenariosToProcess = [...dualScens, ...dualRest];
        }
      } else {
        // ── 回収重視: final_prob 1位が1号艇でないとき穴軸展開 ──
        // 【改修】旧: 1号艇 final_prob が場平均以下 → 新: 1位が1号艇でないとき
        // 理由: 場平均との比較は閾値が緩く誤発動が多い。
        //       「1号艇が最終確率1位でない」= モデルが明示的に他艇を上位評価しているケースのみ穴狙い。
        const fp1stIsBoat1 = (ranked2[0]?.boat === 1);
        if(!fp1stIsBoat1){
          // final_prob 上位2艇を軸に展開シナリオを組み立てる
          const top2FPBoats = [ranked2[0]?.boat, ranked2[1]?.boat].filter(Boolean);
          const recScens = allScenPairs
            .filter(p => top2FPBoats.includes(p.boat))
            .slice(0, 4); // 2艇 × 最大2シナリオ（点数上限は後段で制御）
          scenariosToProcess = recScens.length > 0 ? recScens : top3Scen;
        } else {
          // 1号艇が1位 → 通常フロー（top3Scen 順）
          scenariosToProcess = top3Scen;
        }
      }

      scenariosToProcess.forEach((topScen, scenIdx) => {
        const axisBoat = topScen.boat;
        const kimari   = topScen.kimari;
        const lc       = kimariToLc(kimari);
        const baseLabel = kimari;
        const scenProb  = scenarioProb[axisBoat]?.[kimari] ?? 0;
        const seconds   = pick2nd(axisBoat, kimari, buyMode);

        seconds.forEach(s2 => {
          const place2List = scenarioPlace2[axisBoat]?.[kimari] || [];
          const p2Item     = place2List.find(x => x.boat === s2);
          const p2         = p2Item?.p2 ?? 0;
          const prob2      = scenProb * p2;

          const thirdAll   = calc3rdScores(ranked2, tenjiScoreMap, axisBoat, kimari, s2);
          const R3_MIN_THRESHOLD = 0.03; // 3着率3%未満の艇は買い目から除外
          const scoreTotal = thirdAll.reduce((s, x) => s + x.score, 0) || 1;
          const thirdList  = [];
          let cumScore = 0;
          // 【2026-05-16 改修】モード別3着累積目標: hit=0.85, rec=0.70
          const pick3TargetInner = (buyMode === 'hit') ? PICK3_PROB_TARGET_HIT : PICK3_PROB_TARGET_REC;
          for(const x of thirdAll){
            if(x.r3 != null && x.r3 < R3_MIN_THRESHOLD) continue; // 絶対値ガード
            thirdList.push(x);
            cumScore += x.score / scoreTotal;
            if(cumScore >= pick3TargetInner) break;
          }
          thirdList.forEach(t => {
            const prob3 = t.r3 != null ? prob2 * t.r3 : null;
            tryAdd3m(axisBoat, s2, t.boat, baseLabel, lc, prob3, scenIdx);

            // 折り返し
            if(seconds.length === 1){
              const p2RevItem  = (scenarioPlace2[axisBoat]?.[kimari] || []).find(x => x.boat === t.boat);
              const p2Rev      = p2RevItem?.p2 ?? 0;
              const prob2Rev   = scenProb * p2Rev;
              const probRev    = t.r3 != null ? prob2Rev * t.r3 : null;
              tryAdd3m(axisBoat, t.boat, s2, baseLabel+'（折返）', lc, probRev, scenIdx);
            }
          });
          tryAdd2m(axisBoat, s2, baseLabel, lc, prob2, scenIdx);
        });
      });

    } else {
      // MASTERなし: 旧ロジックにフォールバック
      function place2For(axisBoat){
        return ranked2.filter(bt => bt.boat !== axisBoat).sort((x,y) => y.place2_prob - x.place2_prob);
      }
      const p2A  = place2For(A.boat);
      const P2a_ = p2A[0]||B;
      const P2b_ = p2A[1]||C;
      const lbNige = arek < 40 ? '逃げ' : arek > 60 ? 'まくり' : '差し';
      const lcNige = arek < 40 ? 'bl-nige' : arek > 60 ? 'bl-makuri' : 'bl-sashi';
      pick3rd(A.boat, null, P2a_.boat, buyMode).forEach(b=>tryAdd3m(A.boat,P2a_.boat,b,lbNige,lcNige,null,0));
      pick3rd(A.boat, null, P2b_.boat, buyMode).forEach(b=>tryAdd3m(A.boat,P2b_.boat,b,lbNige,lcNige,null,1));
      tryAdd2m(A.boat, P2a_.boat, lbNige, lcNige, null, 0);
      tryAdd2m(A.boat, P2b_.boat, lbNige, lcNige, null, 1);
      if(arek>=45){
        pick3rd(P2a_.boat, null, A.boat, buyMode).forEach(b=>tryAdd3m(P2a_.boat,A.boat,b,'差し','bl-sashi',null,2));
        tryAdd2m(P2a_.boat, A.boat, '差し', 'bl-sashi', null, 2);
      }
    }

    return { b3, b2 };
  }

  // ── 2モードの買い目をそれぞれ生成 ──
  // HIT/REC 別の点数上限で買い目を生成（見送り推奨時は10点で参考表示）
  const { b3: buy3Hit_raw, b2: buy2Hit_raw } = buildBuy3ForMode('hit', BUY_MAX_POINTS_HIT);
  const { b3: buy3Rec_raw, b2: buy2Rec_raw } = buildBuy3ForMode('rec', BUY_MAX_POINTS_REC);

  // 旧コードとの互換性のため buy3 / buy2 は的中重視ベースで定義
  // ※ 合成オッズ判定（buy3Hit_checked）は後段で行うため、ここでは raw を参照
  const buy3 = buy3Hit_raw;
  const buy2 = buy2Hit_raw;


  // ─ STEP6: 確率テーブル生成
  const probRows = ranked2.map((bt,i)=>{
    // 基準列: probを6艇で正規化した相対確率（合計100%）
    const basePct = (bt.display_base * 100).toFixed(1);

    // 展開補正列: 係数表示（▲1.08 / ▼0.82 形式）
    let relCorrCell;
    if(useMaster && bt.display_tenkai != null){
      const coef  = bt.display_tenkai;
      if(Math.abs(coef - 1.0) < 0.02){
        relCorrCell = `<span style="font-size:10px;color:var(--text3)">±1.00</span>`;
      } else {
        const color = coef >= 1.0 ? 'var(--green)' : 'var(--red)';
        const mark  = coef >= 1.0 ? '▲' : '▼';
        relCorrCell = `<span style="font-size:10px;font-weight:600;color:${color}">${mark}${coef.toFixed(2)}</span>`;
      }
    } else {
      relCorrCell = `<span style="font-size:10px;color:var(--text3)">—</span>`;
    }

    // 展示補正列: 係数表示（▲1.08 / ▼0.82 形式）
    let tenjiCorrCell;
    if(hasTenji && bt.display_tenji != null){
      const coef  = bt.display_tenji;
      if(Math.abs(coef - 1.0) < 0.02){
        tenjiCorrCell = `<span style="font-size:10px;color:var(--text3)">±1.00</span>`;
      } else {
        const color = coef >= 1.0 ? 'var(--green)' : 'var(--red)';
        const mark  = coef >= 1.0 ? '▲' : '▼';
        tenjiCorrCell = `<span style="font-size:10px;font-weight:600;color:${color}">${mark}${coef.toFixed(2)}</span>`;
      }
    } else {
      tenjiCorrCell = `<span style="font-size:10px;color:var(--text3)">—</span>`;
    }

    // スリット補正列: 係数表示（▲1.08 / ▼0.82 形式）展示データありの場合のみ表示
    let slitCorrCell;
    if(hasTenji && bt.display_slit != null){
      const coef = bt.display_slit;
      if(Math.abs(coef - 1.0) < 0.02){
        slitCorrCell = `<span style="font-size:10px;color:var(--text3)">±1.00</span>`;
      } else {
        const color = coef >= 1.0 ? 'var(--green)' : 'var(--red)';
        const mark  = coef >= 1.0 ? '▲' : '▼';
        slitCorrCell = `<span style="font-size:10px;font-weight:600;color:${color}">${mark}${coef.toFixed(2)}</span>`;
      }
    } else {
      slitCorrCell = `<span style="font-size:10px;color:var(--text3)">—</span>`;
    }

    // 最終確率: 3スコアの加重合成結果（合計は常に100%）
    const finalProb = bt.final_prob ?? bt.tenkai_prob;
    const finalPct  = (finalProb * 100).toFixed(1);

    // 期待値セル
    const evCell = `<span class="ev-cell" data-boat="${bt.boat}" data-fp="${finalProb.toFixed(4)}" style="font-size:11px;color:var(--text3)">—</span>`;

    return `<tr>
      <td style="text-align:center;padding:4px 3px"><span class="boat-circle b${bt.boat}" style="width:22px;height:22px;font-size:11px;line-height:22px;display:inline-flex;align-items:center;justify-content:center">${bt.boat}</span></td>
      <td class="col-name" style="padding:4px 4px;font-size:0.82rem;text-align:center">${bt.name}</td>
      <td style="padding:4px 4px;text-align:center;font-family:var(--mono);font-size:0.82rem;color:var(--text3)">${basePct}%</td>
      <td style="padding:4px 3px;text-align:center;font-size:0.82rem">${relCorrCell}</td>
      <td style="padding:4px 3px;text-align:center;font-size:0.82rem">${tenjiCorrCell}</td>
      <td style="padding:4px 3px;text-align:center;font-size:0.82rem">${slitCorrCell}</td>
      <td style="padding:4px 4px;text-align:center;font-family:var(--mono);font-size:0.82rem;font-weight:700;color:var(--accent2)">${finalPct}%</td>
    </tr>`;
  }).join('');

  const dualNote = isDualAxis
    ? `<span style="color:var(--orange);font-size:11px;font-weight:700">⚡ 僅差2頭軸（${A.boat}号・${B.boat}号 差${probDiffPct.toFixed(1)}% / 閾値${DIVERGENCE_THRESHOLD_HIT}%）</span>`
    : '';

  // ── 会場平均率テーブル ──
  // コース1着率: inn_data.course_rates（会場平均）
  // 1－◯ 2着率: inn_data.inn_2place → なければ MASTER_EXT.venue_stats[venue].inn_2place にフォールバック
  const innData   = DATA.inn_data || {};
  const cRates    = innData.course_rates || [];

  // inn_2place: inn_data に直接入っていれば使用、なければ venue_stats から取得
  const inn2Place = (() => {
    const fromInnData = innData.inn_2place;
    if(fromInnData && typeof fromInnData === 'object' && !Array.isArray(fromInnData) && Object.keys(fromInnData).length > 0)
      return fromInnData;
    return MASTER_EXT?.venue_stats?.[DATA.venue]?.inn_2place || {};
  })();

  // コース番号ラベル（進入コース）
  const courseLabels = ['1','2','3','4','5','6'];

  // 各コースのセル
  const courseRateCells = courseLabels.map(c => {
    const ci   = parseInt(c);
    const rate = cRates[ci];
    const pct  = rate != null ? (rate * 100).toFixed(1) + '%' : '—';
    // 1コースは強調
    const style = ci === 1
      ? 'font-weight:700;color:var(--text)'
      : 'color:var(--text)';
    return `<td style="text-align:center;padding:4px 6px;font-size:12px;font-family:var(--mono);${style}">${pct}</td>`;
  }).join('');

  // イン逃げ時2着率のセル（オブジェクト形式から取得）
  const inn2Cells = courseLabels.map(c => {
    const ci   = parseInt(c);
    if(ci === 1){
      return `<td style="text-align:center;padding:4px 6px;font-size:11px;color:var(--text3)">—</td>`;
    }
    const rate = inn2Place[c] ?? null;
    const pct  = rate != null ? (rate * 100).toFixed(1) + '%' : 'データなし';
    const style = rate == null
      ? 'color:var(--text3);font-size:11px'
      : 'color:var(--text)';
    return `<td style="text-align:center;padding:4px 6px;font-size:12px;font-family:var(--mono);${style}">${pct}</td>`;
  }).join('');

  const venueStatsTable = `
    <div style="padding:0.6rem 1.25rem;border-bottom:1px solid var(--border)">
      <div style="font-size:10px;font-weight:700;letter-spacing:.08em;color:var(--text3);margin-bottom:6px;text-transform:uppercase">
        ${DATA.venue} — 会場平均
      </div>
      <div class="prob-table-wrap">
      <table style="width:100%;border-collapse:collapse;font-size:11px">
        <thead>
          <tr style="border-bottom:1px solid var(--border)">
            <td style="padding:2px 6px;font-size:10px;color:var(--text3);min-width:7em"></td>
            ${courseLabels.map(c=>`<th style="text-align:center;padding:2px 6px;font-size:10px;color:var(--text3);font-weight:500">
              <span class="boat-circle b${c}" style="width:18px;height:18px;font-size:10px;display:inline-flex;align-items:center;justify-content:center">${c}</span>
            </th>`).join('')}
          </tr>
        </thead>
        <tbody>
          <tr style="border-bottom:1px solid var(--border)">
            <td style="padding:4px 6px;font-size:10px;color:var(--text3);white-space:nowrap">コース1着率</td>
            ${courseRateCells}
          </tr>
          <tr>
            <td style="padding:4px 6px;font-size:10px;color:var(--text3);white-space:nowrap">1－◯ 2着率</td>
            ${inn2Cells}
          </tr>
        </tbody>
      </table>
      </div>
    </div>`;

  // ── 展開分析タブ: 会場平均・着順確率・展開シナリオ ──
  document.getElementById('buy-panel').innerHTML = `
    ${venueStatsTable}
    <div style="padding:0.75rem 1.25rem 0.5rem;border-bottom:1px solid var(--border)">
      <div style="display:flex;align-items:center;gap:12px;margin-bottom:8px;flex-wrap:wrap">
        <div style="font-size:11px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--text3)">独自補正 最終確率</div>
      </div>
      <div class="prob-table-wrap">
      <table class="prob-table" style="width:100%;border-collapse:collapse">
        <thead><tr>
          <th style="font-size:10px;color:var(--text3);font-weight:500;padding:3px 4px;text-align:center">枠</th>
          <th style="font-size:10px;color:var(--text3);font-weight:500;padding:3px 4px;text-align:center">選手名</th>
          <th style="font-size:10px;color:var(--text3);font-weight:500;padding:3px 6px;text-align:center" title="6艇のprobを正規化した相対1着率（合計100%）">基準</th>
          <th style="font-size:10px;color:var(--text3);font-weight:500;padding:3px 4px;text-align:center" title="展開適性の係数（1.0基準: ▲=有利 ▼=不利）">展開補正</th>
          <th style="font-size:10px;color:var(--text3);font-weight:500;padding:3px 4px;text-align:center" title="展示タイムの係数（1.0基準: ▲=有利 ▼=不利）">展示補正</th>
          <th style="font-size:10px;color:var(--text3);font-weight:500;padding:3px 4px;text-align:center" title="前艇とのST差・展示タイム差から捲り優位を判定（展示データありの場合のみ）">スリット補正</th>
          <th style="font-size:10px;color:var(--text3);font-weight:500;padding:3px 6px;text-align:center" title="基準・展開・展示を均等（1:1:1）で合成・正規化した最終1着率（合計は常に100%）">最終確率</th>
        </tr></thead>
        <tbody>${probRows}</tbody>
      </table>
      </div>
    </div>
    ${buildScenarioSection(ranked2, place2Map, rawBoats, tenjiScoreMap, hasTenji)}
  `;

  // ── AI予想タブ: 買い目のみ ──
  // 結果データとの的中チェック
  const rKey      = resultKey(slug, DATA.date, rno);
  const resultRd  = RESULT_DATA[rKey];
  const hasResult = !!(resultRd && resultRd.sanrentan && resultRd.sanrentan.length > 0);

  // 結果comboを正規化（区切り文字を統一）して比較用セットを作成
  function normalizeCombo(s){ return (s||'').replace(/[－−\-]/g,'-'); }
  // sanrentan[0] が確定着順（1着-2着-3着）。全件Setにすると払戻データの他組み合わせと誤マッチする
  const resultSan3  = hasResult && resultRd.sanrentan[0] ? new Set([normalizeCombo(resultRd.sanrentan[0].combo)]) : null;
  // nirentan は sanrentan と独立してチェック（sanrentan がなくても 2連単的中を正しく判定する）
  const resultNiren = resultRd?.nirentan?.[0] ? new Set([normalizeCombo(resultRd.nirentan[0].combo)]) : null;

  function hitBadge(){ return `<span class="hit-badge">🎯 的中</span>`; }

  // 艇番文字列（例: "1−2−3"）を color-circle バッジ列に変換
  function comboToBadges(combo){
    return (combo || '').split(/([－−\-])/).map(part => {
      if (/^[－−\-]$/.test(part)) {
        return `<span style="color:var(--text3);font-size:13px;margin:0 1px;font-weight:400">−</span>`;
      }
      const n = part.trim();
      if (/^[1-6]$/.test(n)) {
        return `<span class="boat-circle b${n}" style="width:22px;height:22px;font-size:11px;display:inline-flex;align-items:center;justify-content:center;flex-shrink:0">${n}</span>`;
      }
      return part;
    }).join('');
  }

  function buy3Row(r){
    const nc = normalizeCombo(r.c);
    const isHit = resultSan3 && resultSan3.has(nc);
    const probCell = r.prob != null
      ? `<span style="font-size:10px;font-family:var(--mono);color:var(--text3);margin-left:auto;flex-shrink:0">${(r.prob*100).toFixed(1)}%</span>`
      : '';
    return `<div class="buy-row${isHit?' hit':''}">
      <span class="buy-label ${r.lc}">${r.l}</span>
      <span class="buy-combo" style="display:inline-flex;align-items:center;gap:0;letter-spacing:0">${comboToBadges(r.c)}</span>
      ${probCell}
      ${isHit?hitBadge():''}
    </div>`;
  }

  function buy2Row(r){
    const nc = normalizeCombo(r.c);
    const isHit = resultNiren && resultNiren.has(nc);
    const probCell = r.prob != null
      ? `<span style="font-size:10px;font-family:var(--mono);color:var(--text3);margin-left:auto;flex-shrink:0">${(r.prob*100).toFixed(1)}%</span>`
      : '';
    return `<div class="buy-row${isHit?' hit':''}">
      <span class="buy-label ${r.lc}">${r.l}</span>
      <span class="buy-combo" style="display:inline-flex;align-items:center;gap:0;letter-spacing:0">${comboToBadges(r.c)}</span>
      ${probCell}
      ${isHit?hitBadge():''}
    </div>`;
  }

  // ── 買い目を艇番の若い順でソート ──
  buy3.sort((a, b) => {
    const [a1,a2,a3] = a.c.split(/\D+/).map(Number);
    const [b1,b2,b3] = b.c.split(/\D+/).map(Number);
    if(a1 !== b1) return a1 - b1;
    if(a2 !== b2) return a2 - b2;
    return a3 - b3;
  });
  buy2.sort((a, b) => {
    const [a1,a2] = a.c.split(/\D+/).map(Number);
    const [b1,b2] = b.c.split(/\D+/).map(Number);
    if(a1 !== b1) return a1 - b1;
    return a2 - b2;
  });

  // ── シナリオグループ別に買い目をグループ化して表示 ──
  function buildGroupedBuyRows(buyList, resultSet, isTriple) {
  const oddsType = isTriple ? "3t" : "2t";
  // 現在レースのオッズを取得
  const _oddsDate = viewDate || (DATA?.date) || todayDate;
  const raceOdds = ODDS_DATA?.[_oddsDate]?.[DATA?.venue]?.[String(rno)]?.[oddsType] || {};

  let html = '';
  buyList.forEach((r, idx) => {
    const nc    = normalizeCombo(r.c);
    const isHit = resultSet && resultSet.has(nc);

    // AI予想確率
    const probPct = r.prob != null ? (r.prob * 100).toFixed(2) + '%' : '—';

    // ── オッズ取得 ──
    // normalizeCombo で "1-2-3" 形式になっているのでそのまま参照
    const oddsVal = raceOdds[nc] ?? null;
    const oddsStr = oddsVal != null ? oddsVal.toFixed(1) : '—';
    const oddsColor = oddsVal == null ? 'var(--text3)' : 'var(--text)';

    // ── 期待値計算 (AI確率 × オッズ) ──
    let evHtml = '';
    if (r.prob != null && oddsVal != null) {
      const ev = r.prob * oddsVal;
      // EV ≥ 1.0: 緑（プラス期待値） / 0.7〜1.0: オレンジ / < 0.7: 赤
      const evColor = ev >= 1.0
        ? 'var(--green)'
        : ev >= 0.7 ? 'var(--orange)' : 'var(--red)';
      const evWeight = ev >= 1.0 ? '700' : '500';
      evHtml = `<span style="font-size:10px;font-family:var(--mono);font-weight:${evWeight};color:${evColor};flex-shrink:0;min-width:4em;text-align:right">EV${ev.toFixed(2)}</span>`;
    } else if (r.prob != null) {
      // オッズ未取得時はプレースホルダー
      evHtml = `<span style="font-size:10px;color:var(--text3);flex-shrink:0;min-width:4em;text-align:right">EV—</span>`;
    }

    // 順位ラベル
    const rankColor = idx === 0 ? 'var(--gold)' : idx === 1 ? '#aaa' : 'var(--text3)';
    const rankNum   = `<span style="font-size:9px;color:${rankColor};font-weight:700;min-width:14px;flex-shrink:0">${idx+1}</span>`;

    html += `<div class="buy-row${isHit?' hit':''}" style="padding:6px 0">
      <div style="display:flex;align-items:center;gap:5px;flex-wrap:nowrap">
        ${rankNum}
        <span class="buy-combo" style="display:inline-flex;align-items:center;gap:0;letter-spacing:0;flex:1;min-width:0">${comboToBadges(r.c)}</span>
        <span style="font-size:10px;font-family:var(--mono);color:var(--text3);flex-shrink:0;min-width:3.5em;text-align:right">${probPct}</span>
        <span style="font-size:12px;font-family:var(--mono);font-weight:600;color:${oddsColor};flex-shrink:0;min-width:3.8em;text-align:right">${oddsStr}倍</span>
        ${evHtml}
        ${isHit ? hitBadge() : ''}
      </div>
    </div>`;
  });
  return html;
  } // buildGroupedBuyRows 終了

  // ── AI予想タブ: 的中重視 / 回収重視 の2モード生成 ──

  // オッズ取得
  const _oddsDateEv = viewDate || (DATA?.date) || todayDate;
  const raceOdds3tEv = ODDS_DATA?.[_oddsDateEv]?.[DATA?.venue]?.[String(rno)]?.['3t'] || {};
  const _raceOdds2tRaw = ODDS_DATA?.[_oddsDateEv]?.[DATA?.venue]?.[String(rno)]?.['2t'] || {};
  // ODDS_DATAに '2t' がない場合は RESULT_DATA.nirentan の払戻オッズをフォールバックとして使用
  const raceOdds2tEv = (Object.keys(_raceOdds2tRaw).length > 0)
    ? _raceOdds2tRaw
    : (() => {
        const fb = {};
        (resultRd?.nirentan || []).forEach(r => {
          if (r.combo != null && r.odds != null) fb[normalizeCombo(r.combo)] = r.odds;
        });
        return fb;
      })();

  // ── 合成オッズ計算ヘルパー ──
  function calcSynthOdds(list, oddsMap){
    let denom = 0, cnt = 0;
    list.forEach(r => {
      const ov = oddsMap[normalizeCombo(r.c)] ?? null;
      if(ov != null && ov > 0){ denom += 1/ov; cnt++; }
    });
    if(cnt === 0 || denom === 0) return null;
    return 1 / denom;
  }
  function synthOddsHtml(list, oddsMap){
    const so = calcSynthOdds(list, oddsMap);
    if(so == null) return '';
    const soColor = so >= 3.0 ? 'var(--green)' : so >= 1.5 ? 'var(--text2)' : 'var(--red)';
    return `<span style="margin-left:auto;font-size:11px;font-family:var(--mono);font-weight:700;color:${soColor}">合成${so.toFixed(2)}倍</span>`;
  }

  // ── 合成オッズ判定関数 ──
  // 生成した買い目セットの合成オッズを計算し、目標未達なら空配列（見送り）を返す。
  // 買い目の中身は一切削らない。確率順に生成した買い目をそのまま判定する。
  // targetSynth: 目標合成オッズ（hit=2.5, rec=4.0）
  // maxPts: 点数上限
  function checkSynthOdds(list, oddsMap, targetSynth, maxPts){
    const candidates = list.slice(0, maxPts);
    const so = calcSynthOdds(candidates, oddsMap);
    // オッズが1点も取得できていない場合は見送り（参加しない）
    if(so == null){
      console.warn('[checkSynthOdds] オッズ未取得のため見送り', { targetSynth, candidates: candidates.map(r=>r.c) });
      return [];
    }
    // 合成オッズ未達 → 空配列（見送り扱い）
    if(so < targetSynth){
      console.log('[checkSynthOdds] 合成オッズ未達', { so: so.toFixed(2), targetSynth });
      return [];
    }
    return candidates;
  }

  // ── 各買い目にオッズを付与するヘルパー（EV表示用に残す）──
  function attachEV(list, oddsMap){
    return list.map(r => {
      const nc  = normalizeCombo(r.c);
      const ov  = oddsMap[nc] ?? null;
      const ev  = (r.prob != null && ov != null) ? r.prob * ov : null;
      return { ...r, _odds: ov, _ev: ev };
    });
  }

  // ── 【改修】的中重視モード ──
  // 生成済み buy3Hit_raw を最大10点、合成2.5倍以上にトリム
  // 合成オッズ未達の場合は空配列（見送り）
  const HIT_MAX_PTS     = 10;
  const HIT_SYNTH_MIN   = 2.5;
  const buy3Hit_checked  = checkSynthOdds(buy3Hit_raw, raceOdds3tEv, HIT_SYNTH_MIN, HIT_MAX_PTS);
  // 合成オッズ未達フラグ
  const hitUnderSynth    = buy3Hit_checked.length === 0;
  // 表示用: 未達でも参考として raw を表示するが、EV付与は checked ベース
  // ※ 集計（collectResultsForDate）は computeBuy3 内部で同じ閾値チェック済みなので二重カウントなし
  const buy3Hit          = attachEV(buy3Hit_checked.length > 0 ? buy3Hit_checked : buy3Hit_raw.slice(0, HIT_MAX_PTS), raceOdds3tEv);
  const buy2Hit          = attachEV(buy2Hit_raw.slice(0, 8), raceOdds2tEv);

  // ── 【改修】回収重視モード ──
  // 生成済み buy3Rec_raw を最大10点、合成4.0倍以上にトリム
  // 合成オッズ未達の場合は空配列（見送り）
  const REC_MAX_PTS     = 10;
  // rec合成オッズ基準: 4.0倍固定
  const REC_SYNTH_MIN   = 4.0;
  const buy3Rec_checked  = checkSynthOdds(buy3Rec_raw, raceOdds3tEv, REC_SYNTH_MIN, REC_MAX_PTS);
  const recUnderSynth    = buy3Rec_checked.length === 0;
  const buy3Rec          = attachEV(buy3Rec_checked.length > 0 ? buy3Rec_checked : buy3Rec_raw.slice(0, REC_MAX_PTS), raceOdds3tEv);
  const buy2Rec          = attachEV(buy2Rec_raw.slice(0, 8), raceOdds2tEv);

  // ── パターンバッジ・見送り推奨 ──
  const optPattern    = rd.opt_pattern || null;
  const optPoints     = rd.opt_points  != null ? rd.opt_points : 10;
  // 見送り推奨理由（モード別）
  const passReasonHit = rd.opt_pass_reason_hit || '';
  const passReasonRec = rd.opt_pass_reason_rec || '';
  const patternColors = {
    '高配当1号艇': '#0066ff', '高配当他艇': '#00b86b',
    '中立1号艇':   '#6c7a94', '中立他艇':   '#6c7a94',
    '低配当1号艇': '#ff7a00', '要注意会場': '#ff7a00',
  };
  const patColor   = optPattern ? (patternColors[optPattern] || '#6c7a94') : '#6c7a94';
  const isCaution  = optPattern === '要注意会場';
  const patLabel   = isCaution ? '⚠ ' + optPattern : optPattern;
  const patBadge   = optPattern
    ? `<span style="display:inline-flex;align-items:center;gap:4px;margin-left:6px;">
        <span style="background:${patColor};color:#fff;font-size:9px;font-weight:700;padding:1px 6px;border-radius:10px;letter-spacing:.02em;">${patLabel}</span>
        <span style="color:var(--text3);font-size:10px;">推奨${optPoints}点</span>
       </span>`
    : '';

  // ── buildGroupedBuyRows: EVを付与済みリストにも対応 ──
  function buildBuyRows(buyList, resultSet, isTriple){
    const oddsMap = isTriple ? raceOdds3tEv : raceOdds2tEv;
    let html = '';
    buyList.forEach((r, idx) => {
      const nc    = normalizeCombo(r.c);
      const isHit = resultSet && resultSet.has(nc);
      const probPct = r.prob != null ? (r.prob * 100).toFixed(2) + '%' : '—';
      const oddsVal = r._odds ?? (oddsMap[nc] ?? null);
      const oddsStr = oddsVal != null ? oddsVal.toFixed(1) : '—';
      const oddsColor = oddsVal == null ? 'var(--text3)' : 'var(--text)';
      const ev  = r._ev ?? null;
      let evHtml = '';
      if(ev != null){
        const evColor  = ev >= 1.0 ? 'var(--green)' : ev >= 0.7 ? 'var(--orange)' : 'var(--red)';
        const evWeight = ev >= 1.0 ? '700' : '500';
        evHtml = `<span style="font-size:10px;font-family:var(--mono);font-weight:${evWeight};color:${evColor};flex-shrink:0;min-width:4em;text-align:right">EV${ev.toFixed(2)}</span>`;
      } else if(r.prob != null){
        evHtml = `<span style="font-size:10px;color:var(--text3);flex-shrink:0;min-width:4em;text-align:right">EV—</span>`;
      }
      const rankColor = idx === 0 ? 'var(--gold)' : idx === 1 ? '#aaa' : 'var(--text3)';
      const rankNum   = `<span style="font-size:9px;color:${rankColor};font-weight:700;min-width:14px;flex-shrink:0">${idx+1}</span>`;
      html += `<div class="buy-row${isHit?' hit':''}" style="padding:6px 0">
        <div style="display:flex;align-items:center;gap:5px;flex-wrap:nowrap">
          ${rankNum}
          <span class="buy-combo" style="display:inline-flex;align-items:center;gap:0;letter-spacing:0;flex:1;min-width:0">${comboToBadges(r.c)}</span>
          <span style="font-size:10px;font-family:var(--mono);color:var(--text3);flex-shrink:0;min-width:3.5em;text-align:right">${probPct}</span>
          <span style="font-size:12px;font-family:var(--mono);font-weight:600;color:${oddsColor};flex-shrink:0;min-width:3.8em;text-align:right">${oddsStr}倍</span>
          ${evHtml}
          ${isHit ? hitBadge() : ''}
        </div>
      </div>`;
    });
    return html || '<div style="padding:8px;color:var(--text3);font-size:12px">買い目なし</div>';
  }

  // ── 各モードのHTML生成 ──
  // underSynth=true のとき: 買い目はそのまま表示し、合成オッズ未達の注意書きを添える
  // passReason が空でないとき: 見送り推奨バナーをタブ直下・buy-grid上に表示
  function buildModePanel(buy3list, buy2list, modeId, underSynth, synthMin, passReason){
    // 見送り・合成オッズ未達に関係なく、買い目が結果と一致すれば的中バッジを常に表示する
    const b3html = buildBuyRows(buy3list, resultSan3, true);
    const b2html = buildBuyRows(buy2list, resultNiren, false);
    const so3    = synthOddsHtml(buy3list, raceOdds3tEv);
    const _soVal = calcSynthOdds(buy3list, raceOdds3tEv);
    const _soStr = _soVal != null ? _soVal.toFixed(2) + '倍' : '取得中';
    const synthWarning = underSynth
      ? `<div style="display:flex;align-items:center;gap:6px;padding:6px 8px;margin-bottom:4px;
                     background:rgba(255,180,0,0.10);border:1px solid rgba(255,180,0,0.35);
                     border-radius:6px;font-size:11px;color:var(--orange)">
           <span style="font-size:14px;flex-shrink:0">⚠️</span>
           <span>合成オッズ <strong>${_soStr}</strong>（基準${synthMin}倍未満）。参考買い目として表示していますが、購入は自己判断でお願いします。</span>
         </div>`
      : '';
    // ── 見送り推奨バナー（➊高人気圧縮 ➋中人気ロス ➌limited会場 ➍SS他艇高あれ指数）──
    const passWarning = passReason
      ? `<div style="display:flex;align-items:flex-start;gap:8px;padding:8px 10px;margin:4px 0 6px;
                     background:rgba(220,53,69,0.08);border:1px solid rgba(220,53,69,0.30);
                     border-radius:6px;font-size:11px;color:#c0392b">
           <span style="font-size:15px;flex-shrink:0;line-height:1.4">🚫</span>
           <div style="line-height:1.6">
             <div style="font-weight:700;margin-bottom:2px">見送り推奨</div>
             <div style="color:var(--text2)">${passReason}</div>
           </div>
         </div>`
      : '';
    return `
      <div id="${modeId}" style="display:none">
        ${passWarning}
        <div class="buy-grid">
          <div class="buy-card">
            <div class="buy-card-title" style="display:flex;align-items:center;gap:4px;flex-wrap:wrap">
              <span>3連単</span>
              <span style="font-weight:400;color:var(--text3);font-size:10px;">${buy3list.length}点</span>
              ${patBadge}
              ${so3}
            </div>
            ${synthWarning}
            ${b3html}
          </div>
          <div class="buy-card">
            <div class="buy-card-title">2連単 <span style="font-weight:400;color:var(--text3);font-size:10px;margin-left:6px">${buy2list.length}点</span></div>
            ${b2html}
          </div>
        </div>
      </div>`;
  }

  const hitPanelHtml = buildModePanel(buy3Hit, buy2Hit, 'buy-mode-hit', hitUnderSynth, HIT_SYNTH_MIN, passReasonHit);
  const recPanelHtml = buildModePanel(buy3Rec, buy2Rec, 'buy-mode-rec', recUnderSynth, REC_SYNTH_MIN, passReasonRec);

  // ── タブUI ──
  const modeTabs = `
    <div style="display:flex;gap:0;border-bottom:1px solid var(--border);margin-bottom:0;background:var(--bg2);">
      <button id="buy-tab-hit" onclick="switchBuyMode('hit')"
        style="flex:1;padding:8px 4px;font-size:12px;font-weight:700;border:none;background:none;cursor:pointer;
               border-bottom:2px solid var(--accent);color:var(--accent);font-family:'Noto Sans JP',sans-serif;">
        🎯 的中重視<span style="font-size:9px;font-weight:400;color:var(--text3);margin-left:4px;">合成2.5x以上</span>
      </button>
      <button id="buy-tab-rec" onclick="switchBuyMode('rec')"
        style="flex:1;padding:8px 4px;font-size:12px;font-weight:500;border:none;background:none;cursor:pointer;
               border-bottom:2px solid transparent;color:var(--text3);font-family:'Noto Sans JP',sans-serif;">
        💰 回収重視<span style="font-size:9px;font-weight:400;color:var(--text3);margin-left:4px;">合成4.0x以上</span>
      </button>
    </div>`;

  document.getElementById('detail2-panel').innerHTML = modeTabs + hitPanelHtml + recPanelHtml;

  // 初期表示
  document.getElementById('buy-mode-hit').style.display = 'block';

} // renderBuy 終了

// ── 買い目モード切り替え ──
function switchBuyMode(mode){
  const hitPanel = document.getElementById('buy-mode-hit');
  const recPanel = document.getElementById('buy-mode-rec');
  const hitTab   = document.getElementById('buy-tab-hit');
  const recTab   = document.getElementById('buy-tab-rec');
  if(!hitPanel || !recPanel) return;
  const isHit = (mode === 'hit');
  hitPanel.style.display = isHit ? 'block' : 'none';
  recPanel.style.display = isHit ? 'none'  : 'block';
  hitTab.style.borderBottomColor = isHit ? 'var(--accent)' : 'transparent';
  hitTab.style.color             = isHit ? 'var(--accent)' : 'var(--text3)';
  hitTab.style.fontWeight        = isHit ? '700' : '500';
  recTab.style.borderBottomColor = isHit ? 'transparent' : 'var(--accent)';
  recTab.style.color             = isHit ? 'var(--text3)' : 'var(--accent)';
  recTab.style.fontWeight        = isHit ? '500' : '700';
}


// ── renderComment ──
function renderComment(rno){
  const rd = DATA.races[String(rno)];
  if(!rd){ console.warn('[renderComment] no race data for rno=', rno); return; }
  const boats = [...rd.boats].sort((a,b)=>a.boat-b.boat);
  const motorHtml   = buildMotorInfoSection(rno, boats);
  const commentHtml = buildCommentSection(rno, boats);
  const html = `<div class="detail-panel">${motorHtml}${commentHtml}</div>`;
  document.getElementById('comment-panel').innerHTML = html;
}

// ── タブ切り替え ──
// ── 結果タブ描画 ──────────────────────────────────────────────────────────
function resultKey(venueSlug, date, rno){
  // RESULT_DATA のキー形式: "{slug}_{YYYYMMDD}_{rno}"
  const dateNd = (date || '').replace(/-/g, '');
  return `${venueSlug}_${dateNd}_${rno}`;
}

const VENUE_SLUG_MAP = {
  "桐生":"kiryu","戸田":"toda","江戸川":"edogawa","平和島":"heiwajima",
  "多摩川":"tamagawa","浜名湖":"hamanako","蒲郡":"gamagori","常滑":"tokoname",
  "津":"tsu","三国":"mikuni","びわこ":"biwako","住之江":"suminoe",
  "尼崎":"amagasaki","鳴門":"naruto","丸亀":"marugame","児島":"kojima",
  "宮島":"miyajima","徳山":"tokuyama","下関":"shimonoseki","若松":"wakamatsu",
  "芦屋":"ashiya","福岡":"fukuoka","唐津":"karatsu","大村":"omura"
};

function renderResult(rno){
  const panel = document.getElementById('result-panel');
  if(!panel) return;
  if(!DATA || !rno){
    panel.innerHTML = '<div style="padding:2rem;text-align:center;color:var(--text3)">レースを選択してください</div>';
    return;
  }

  const slug    = VENUE_SLUG_MAP[DATA.venue] || DATA.venue;
  const key     = resultKey(slug, DATA.date, rno);
  const rd      = RESULT_DATA[key];

  if(!rd || !rd.sanrentan || rd.sanrentan.length === 0){
    panel.innerHTML = `
      <div style="padding:2rem;text-align:center;color:var(--text3)">
        <div style="font-size:24px;margin-bottom:8px">⏳</div>
        <div style="font-size:13px">${rno}R の結果はまだありません</div>
        <div style="font-size:11px;margin-top:6px;color:var(--text3)">レース確定後に自動取得されます</div>
      </div>`;
    return;
  }

  // 枠番カラー丸バッジ（boat-circle スタイル流用）
  const boatBadge = n => `<span class="boat-circle b${n}" style="width:22px;height:22px;font-size:12px;display:inline-flex;align-items:center;justify-content:center;flex-shrink:0;vertical-align:middle">${n}</span>`;

  // comboを枠番バッジの並びに変換（例: "3-1-5" → ➌➊➎バッジ列）
  function formatCombo(combo){
    return (combo||'').replace(/(\d)/g, m => boatBadge(parseInt(m)));
  }

  // 数字単体を枠番バッジに（返還用）
  const circledNum = n => boatBadge(n);

  // 3連単トップ3
  const san = rd.sanrentan.slice(0, 3);

  const sanHtml = san.map((r, i) => {
    const isHigh = r.odds >= 10000;
    const oddsClass = isHigh ? ' high' : '';
    const ninki = r.ninki ? `<span class="result-ninki">${r.ninki}番人気</span>` : '';
    return `
    <div class="result-row">
      <span class="result-combo">${formatCombo(r.combo)}</span>
      <span class="result-odds${oddsClass}">￥${r.odds.toLocaleString()}</span>
      ${ninki}
    </div>`;
  }).join('');

  // 決まり手（JSONキー: kimari）
  const kimariHtml = rd.kimari
    ? `<div class="result-meta-row"><span class="result-meta-label">決まり手</span><span>${rd.kimari}</span></div>`
    : '';

  // 返還（あれば表示、空配列・nullなら非表示）
  const henkanList = Array.isArray(rd.henkan) ? rd.henkan : (rd.henkan ? [rd.henkan] : []);
  const henkanHtml = henkanList.length > 0
    ? `<div class="result-henkan-row"><span class="result-meta-label">返還</span><span>${henkanList.map(n => circledNum(n)).join('　')}</span></div>`
    : '';

  panel.innerHTML = `
    <div class="result-panel-inner">
      <div class="result-section-title">3連単 払戻</div>
      ${sanHtml}
      ${kimariHtml}
      ${henkanHtml}
    </div>
  `;
}

function renderOdds(rno) {
  const panel = document.getElementById('odds-panel');
  if (!panel) return;
  if (!DATA || !rno) {
    panel.innerHTML = '<div style="padding:2rem;text-align:center;color:var(--text3)">レースを選択してください</div>';
    return;
  }

  const _oddsDateR = viewDate || (DATA?.date) || todayDate;
  const raceOdds = ODDS_DATA?.[_oddsDateR]?.[DATA.venue]?.[String(rno)];

  if (!raceOdds) {
    panel.innerHTML = `
      <div style="padding:2rem;text-align:center;color:var(--text3)">
        <div style="font-size:1.5rem;margin-bottom:8px">—</div>
        <div style="font-size:13px">オッズ未取得</div>
        <div style="font-size:11px;margin-top:6px;color:var(--text3)">次回 auto_push 時に反映されます</div>
      </div>`;
    return;
  }

  // ── 各種別のテーブルを生成 ──
  const TYPES = [
    { key: "3t",  label: "3連単", cols: 3 },
    { key: "3f",  label: "3連複", cols: 3 },
    { key: "2t",  label: "2連単", cols: 2 },
    { key: "2f",  label: "2連複", cols: 2 },
    { key: "tan", label: "単勝",  cols: 1 },
  ];

  // 人気順（オッズ昇順）でソート
  function sortedEntries(dict) {
    if (!dict) return [];
    return Object.entries(dict)
      .map(([combo, odds]) => ({ combo, odds }))
      .sort((a, b) => a.odds - b.odds);
  }

  // 各種別のHTMLを生成
  const sectionsHtml = TYPES.map(({ key, label }) => {
    const entries = sortedEntries(raceOdds[key]);
    if (entries.length === 0) return '';

    const rows = entries.map((e, idx) => {
      const ninki   = idx + 1;
      const ninkiColor = ninki <= 3 ? 'var(--accent2)' : 'var(--text3)';
      const oddsHigh   = e.odds >= 100;
      const oddsColor  = oddsHigh ? 'var(--red)' : 'var(--text)';

      // comboToBadges は "-" 区切りで動くので combo を正規化
      const badgesHtml = comboToBadges(e.combo.replace(/-/g, '−'));

      return `<div style="display:flex;align-items:center;gap:6px;padding:5px 0;border-bottom:1px solid var(--border)">
        <span style="font-size:10px;color:${ninkiColor};font-weight:700;min-width:18px;text-align:right;flex-shrink:0">${ninki}</span>
        <span style="display:inline-flex;align-items:center;gap:0;flex:1">${badgesHtml}</span>
        <span style="font-family:var(--mono);font-size:14px;font-weight:600;color:${oddsColor};min-width:5em;text-align:right;flex-shrink:0">${e.odds.toFixed(1)}</span>
      </div>`;
    }).join('');

    return `<div class="buy-card">
      <div class="buy-card-title">${label}
        <span style="font-weight:400;color:var(--text3);font-size:10px;margin-left:6px">${entries.length}通り</span>
      </div>
      ${rows}
    </div>`;
  }).join('');

  // fetched_at / final フラグの表示
  // inject_odds_to_html() は fetched_at を除外して埋め込むため、
  // __fetched_at ではなく fetched_at キーは存在しない。
  // final フラグ（確定オッズ）があれば確定済みバッジを表示する。
  const isFinal    = raceOdds['final'] === true;
  const finalBadge = isFinal
    ? `<span style="display:inline-block;background:var(--accent2);color:#fff;font-size:10px;font-weight:700;padding:1px 6px;border-radius:3px;margin-left:6px">確定</span>`
    : '';

  const updatedHtml = isFinal
    ? `<div style="padding:0.5rem 1.25rem;font-size:11px;color:var(--accent2);border-bottom:1px solid var(--border);font-weight:700">🏁 確定オッズ${finalBadge}</div>`
    : '';

  panel.innerHTML = `
    <div class="detail-panel">
      ${updatedHtml}
      <div class="buy-grid" style="border-top:none">
        ${sectionsHtml}
      </div>
    </div>`;
}


function switchTab(name){
  ['detail','detail2','buy','comment','result','odds'].forEach(t=>{
    const el = document.getElementById('tab-' + t);
    if(el) el.style.display = t===name?'':'none';
  });
  document.querySelectorAll('.tab-btn').forEach(b=>{
    b.classList.toggle('active', b.dataset.tab===name);
  });
  if(name==='detail'){
    renderDetail(selectedRace);
  } else if(name==='buy'){
    renderBuy(selectedRace);
  } else if(name==='detail2'){
    renderBuy(selectedRace); // AI予想タブ（buy-panel+detail2-panelに同時出力）
  } else if(name==='comment'){
    if(IS_SERVER && DATA && DATA.date){
      fetchTenjiAll(currentVenue, DATA.date)
        .then(() => renderComment(selectedRace))
        .catch(e => console.warn('[switchTab] fetchTenjiAll error:', e));
    } else {
      renderComment(selectedRace);
    }
  } else if(name==='result'){
    renderResult(selectedRace);
  } else if(name==='odds'){
    renderOdds(selectedRace);
  }
}

function currentTabName(){
  const b = document.querySelector('.tab-btn.active');
  return b ? (b.dataset.tab||'detail') : 'detail';
}

// ── 日付ナビゲーター ──
// viewDate: 現在表示中の日付文字列 "YYYY-MM-DD"（null = 当日 ALL_DATA）
let viewDate = null;

function getAvailableDates(){
  // ALL_DATA_HISTORY のキー（過去日）+ 当日（ALL_DATAから推定）
  const histDates = Object.keys(ALL_DATA_HISTORY).sort();
  // 当日の日付を ALL_DATA から取得
  const todayDate = (function(){
    for(const v of Object.values(ALL_DATA)){
      if(v && v.date) return v.date;
    }
    return null;
  })();
  const all = [...histDates];
  if(todayDate && !all.includes(todayDate)) all.push(todayDate);
  return all.sort();
}

function getDataForDate(dateStr){
  // dateStr が null or 当日 → ALL_DATA、それ以外 → ALL_DATA_HISTORY[dateStr]
  const dates = getAvailableDates();
  const todayDate = dates[dates.length - 1];
  if(!dateStr || dateStr === todayDate) return ALL_DATA;
  return ALL_DATA_HISTORY[dateStr] || {};
}

function updateDateNav(){
  const nav = document.getElementById('date-nav');
  const dates = getAvailableDates();
  if(dates.length <= 1){ nav.style.display = 'none'; return; }
  nav.style.display = 'flex';

  const todayDate = dates[dates.length - 1];
  const current = viewDate || todayDate;
  const idx = dates.indexOf(current);

  document.getElementById('date-nav-label').textContent = current;
  document.getElementById('date-prev').disabled = idx <= 0;
  document.getElementById('date-next').disabled = idx >= dates.length - 1;
}

function shiftDate(delta){
  const dates = getAvailableDates();
  const todayDate = dates[dates.length - 1];
  const current = viewDate || todayDate;
  const idx = dates.indexOf(current);
  const newIdx = idx + delta;
  if(newIdx < 0 || newIdx >= dates.length) return;
  viewDate = dates[newIdx];

  // 表示日のデータで会場タブを再構築
  const dataForDate = getDataForDate(viewDate);

  // 現在選択中の会場が新しい日付でも存在するか確認
  const hasCurrentVenue = currentVenue && dataForDate[currentVenue];
  if(hasCurrentVenue){
    DATA = dataForDate[currentVenue];
    selectedRace = findCurrentRace(DATA.races);
  } else {
    // 新しい日付でデータがある最初の会場を自動選択
    const firstVenue = VENUE_LIST.find(v => dataForDate[v]);
    if(firstVenue){
      currentVenue = firstVenue;
      DATA = dataForDate[firstVenue];
      selectedRace = findCurrentRace(DATA.races);
    } else {
      currentVenue = ''; DATA = null; selectedRace = 0;
    }
  }

  buildVenueTabs();
  updateDateNav();

  if(currentVenue && DATA){
    document.getElementById('header-meta').innerHTML = `<strong>${currentVenue}</strong> — ${DATA.date||''}`;
    buildRaceBar();
    selectRace(selectedRace || findCurrentRace(DATA.races));
  } else {
    document.getElementById('race-bar').innerHTML = '';
    document.getElementById('inline-detail').innerHTML =
      '<div style="padding:2rem;text-align:center;color:var(--text3)">会場を選択してください</div>';
  }
}

// ── 締め切りアラートバナー ──
function updateAlertStrip(){
  const strip   = document.getElementById('alert-strip');
  const cardsEl = document.getElementById('alert-cards');
  if(!strip || !cardsEl) return;

  const now    = new Date();
  const nowMin = now.getHours() * 60 + now.getMinutes();
  const LIMIT  = 15;

  const hits = [];
  const dataForDate = getDataForDate(viewDate);

  VENUE_LIST.forEach(venue => {
    const vdata = dataForDate[venue];
    if(!vdata || !vdata.races) return;
    Object.entries(vdata.races).forEach(([rno, rd]) => {
      if(!rd || !rd.time) return;
      const t = String(rd.time).trim();
      const match = t.match(/^(\d{1,2}):(\d{2})$/);
      if(!match) return;
      const raceMin = parseInt(match[1]) * 60 + parseInt(match[2]);
      const diff = raceMin - nowMin;
      if(diff >= 0 && diff <= LIMIT){
        hits.push({ venue, rno: parseInt(rno), time: t, diff });
      }
    });
  });

  hits.sort((a, b) => a.diff - b.diff);

  if(hits.length === 0){
    strip.style.display = 'none';
    return;
  }

  strip.style.display = 'block';
  cardsEl.innerHTML = hits.map(h => {
    const urgent = h.diff <= 5;
    const dotCls = urgent ? 'alert-dot urgent' : 'alert-dot';
    const label  = h.diff <= 0 ? '発走直前' : `残り ${h.diff}分`;
    return `<div class="alert-card${urgent?' urgent':''}" onclick="jumpToAlert('${h.venue}',${h.rno})">
      <div class="alert-card-badge"><span class="${dotCls}"></span>${label}</div>
      <div class="alert-card-venue">${h.venue}</div>
      <div class="alert-card-race">${h.rno}R</div>
      <div class="alert-card-time">${h.time} 発走</div>
    </div>`;
  }).join('');
}

function jumpToAlert(venue, rno){
  const dataForDate = getDataForDate(viewDate);
  if(!dataForDate[venue]) return;
  hideTopPage();
  currentVenue = venue;
  DATA = dataForDate[venue];
  selectedRace = rno;
  document.getElementById('header-meta').innerHTML =
    `<strong>${venue}</strong> — ${DATA.date||''}`;
  document.querySelectorAll('.vtab').forEach(b =>
    b.classList.toggle('active', b.dataset.venue === venue));
  buildRaceBar();
  selectRace(rno);
}

// ── 会場タブ構築 ──
const VENUE_LIST = [
  '桐生','戸田','江戸川','平和島','多摩川','浜名湖','蒲郡','常滑',
  '津','三国','びわこ','住之江','尼崎','鳴門','丸亀','児島',
  '宮島','徳山','下関','若松','芦屋','福岡','唐津','大村'
];

// ── サーバーモード: tenji_all API → _tenjiCache に格納 ──
const SLUG_MAP = {
  "桐生":"kiryu","戸田":"toda","江戸川":"edogawa","平和島":"heiwajima",
  "多摩川":"tamagawa","浜名湖":"hamanako","蒲郡":"gamagori","常滑":"tokoname",
  "津":"tsu","三国":"mikuni","びわこ":"biwako","住之江":"suminoe",
  "尼崎":"amagasaki","鳴門":"naruto","丸亀":"marugame","児島":"kojima",
  "宮島":"miyajima","徳山":"tokuyama","下関":"shimonoseki","若松":"wakamatsu",
  "芦屋":"ashiya","福岡":"fukuoka","唐津":"karatsu","大村":"omura"
};
async function fetchTenjiAll(venue, date){
  const slug = SLUG_MAP[venue] || venue;

  // ① 埋め込みキャッシュ（inject_tenji_to_html済み）があれば APIコール不要
  const cachedKeys = Object.keys(_tenjiCache).filter(k => k.startsWith(`${slug}_${date}_`));
  if(cachedKeys.length > 0){
    return;
  }

  // ② API が使えない環境（Netlify / GitHub Pages）はスキップ
  if(!_serverAvailable){
    return;
  }

  // ③ ローカルサーバーから取得
  try {
    const res = await fetch(`/api/tenji_all?venue=${slug}&date=${date}`);
    if(!res.ok){
      // 404等 → 以降のAPIコールも抑制
      _serverAvailable = false;
      console.warn('[fetchTenjiAll] API returned', res.status, '→ server unavailable');
      return;
    }
    const json = await res.json();
    if(!json.ok || !json.races) return;
    for(const [rno, frameMap] of Object.entries(json.races)){
      _tenjiCache[`${slug}_${date}_${rno}`] = frameMap;
    }
  } catch(e) {
    _serverAvailable = false;
    console.warn('[fetchTenjiAll] error (server unavailable):', e);
  }
}

function buildVenueTabs(){
  const tabs = document.getElementById('venue-tabs');
  tabs.innerHTML = '';
  const dataForDate = getDataForDate(viewDate);
  VENUE_LIST.forEach(v => {
    const btn = document.createElement('button');
    btn.className = 'vtab';
    const _datesVt = getAvailableDates();
    const _todayVt = _datesVt[_datesVt.length - 1];
    const _isTodayVt = (viewDate || _todayVt) === _todayVt;
    const infoVt = _isTodayVt
      ? ((RACE_INDEX_DATA && RACE_INDEX_DATA.venues) ? (RACE_INDEX_DATA.venues[v] || null) : null)
      : (dataForDate[v] ? (dataForDate[v].race_info || null) : null);
    const day = infoVt ? (infoVt.day || '') : '';
    btn.innerHTML = day ? `${v}<span class="vtab-day">${day}</span>` : v;
    btn.dataset.venue = v;
    const isLoaded = !!dataForDate[v];
    if(isLoaded) btn.classList.add('loaded');
    else { btn.style.opacity = '0.35'; btn.style.cursor = 'default'; }
    if(v === currentVenue) btn.classList.add('active');
    btn.onclick = () => {
      if(!dataForDate[v]) return;
      hideTopPage();
      currentVenue = v;
      DATA = dataForDate[v];
      selectedRace = findCurrentRace(DATA.races);
      document.getElementById('header-meta').innerHTML = `<strong>${v}</strong> — ${DATA.date||''}`;
      document.querySelectorAll('.vtab').forEach(b => b.classList.toggle('active', b.dataset.venue===v));
      buildRaceBar();
      selectRace(selectedRace);
    };
    tabs.appendChild(btn);
  });
}

// ── レース選択バー ──

// 現在時刻に最も近い「これから／直近」のレースを返す
function findCurrentRace(races){
  const now = new Date();
  const nowMin = now.getHours() * 60 + now.getMinutes();
  const entries = Object.entries(races).sort((a,b)=>+a[0]-+b[0]);

  // 未来のレースがあれば最初のものを返す
  for(const [rno, rd] of entries){
    if(!rd.time || !/^\d{1,2}:\d{2}$/.test(rd.time.trim())) continue;
    const [h, m] = rd.time.trim().split(':').map(Number);
    if(h * 60 + m >= nowMin) return parseInt(rno);
  }
  // 全部過去なら最後のレースを返す
  return parseInt(entries[entries.length - 1][0]) || 1;
}
function isRacePast(timeStr){
  if(!timeStr || !/^\d{1,2}:\d{2}$/.test(timeStr.trim())) return false;
  const now = new Date();
  const [h, m] = timeStr.trim().split(':').map(Number);
  const raceMin = h * 60 + m;
  const nowMin  = now.getHours() * 60 + now.getMinutes();
  return nowMin > raceMin;
}

// ── レース種別ラベル取得 ──
// RACE_INDEX_DATA.venues[venue].race_kinds から直接引く。
// race_kinds は fetch_race_index.py が raceindex ページから取得した
// {レース番号: "優勝戦" | "準優勝戦" | ...} の辞書。
function getRaceKindLabel(rno, rd){
  // rd に直接 race_kind が入っている場合は最優先
  if(rd && rd.race_kind) return rd.race_kind;

  const info = (RACE_INDEX_DATA && RACE_INDEX_DATA.venues)
    ? (RACE_INDEX_DATA.venues[currentVenue] || null)
    : null;
  if(!info || !info.race_kinds) return '';

  // race_kinds のキーは数値または文字列どちらの場合もあるため両方試す
  return info.race_kinds[parseInt(rno)] || info.race_kinds[String(rno)] || '';
}

function buildRaceBar(){
  const bar = document.getElementById('race-bar');
  if(!bar) return;
  if(!DATA || !DATA.races){ bar.innerHTML = ''; return; }
  bar.innerHTML = '';  Object.entries(DATA.races).sort((a,b)=>+a[0]-+b[0]).forEach(([rno,rd])=>{
    const btn = document.createElement('button');
    const past = isRacePast(rd.time);
    const hasInsuf = rd.boats && rd.boats.some(b=>b.dq==='insufficient');
    const kindLabel = getRaceKindLabel(rno, rd);
    btn.className = 'race-btn' + (parseInt(rno)===selectedRace?' active':'') + (past?' past':'');
    btn.id = `rc-${rno}`;
    btn.innerHTML = `<span class="race-btn-no">${rno}R</span><span class="race-btn-time">${rd.time||''}</span>${kindLabel?`<span style="display:block;font-size:8px;line-height:1.2;color:var(--accent,#00aaff);letter-spacing:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%">${kindLabel}</span>`:''}${hasInsuf?'<span style="font-size:9px;color:var(--orange)">⚠</span>':''}`;
    btn.onclick = ()=>{ selectRace(parseInt(rno)); };
    bar.appendChild(btn);
  });
}

function doRefresh(){
  const btn = document.getElementById('refresh-btn');
  if(btn) btn.classList.add('spinning');

  // 現在の状態を保存してリロード後に復元
  sessionStorage.setItem('refresh_venue',   currentVenue || 'NONE');
  sessionStorage.setItem('refresh_race',    String(selectedRace || '0'));
  sessionStorage.setItem('refresh_tab',     currentTabName() || 'detail');
  sessionStorage.setItem('refresh_scrollY', String(window.scrollY || 0));
  sessionStorage.setItem('refresh_flag',    '1');

  // location.reload() でリロード（sessionStorage は同一オリジンで保持される）
  setTimeout(()=>{ location.reload(true); }, 150);
}

function updatePersistentBanners(rno){
  if(!DATA) return;
  const rd = DATA.races[String(rno)];
  const container = document.getElementById('persistent-banners');
  if(!container) return;
  if(!rd){ container.innerHTML = ''; return; }
  const boats = [...rd.boats].sort((a,b)=>a.boat-b.boat);
  let html = '';
  // 進入変更バナー
  html += buildCourseOrderBanner(rno, boats);
  // データ不足バナー
  const insuffBoats = boats.filter(bt => bt.dq === 'insufficient');
  if(insuffBoats.length > 0){
    const circles = insuffBoats.map(bt =>
      `<span class="boat-circle b${bt.boat}" style="width:20px;height:20px;font-size:10px;line-height:20px;display:inline-flex;align-items:center;justify-content:center">${bt.boat}</span>`
    ).join('');
    html += `<div class="insufficient-banner">⚠ ${circles}<span class="insuf-boats"></span>コースデータ不足 — 展開分析精度が低下しています</div>`;
  }
  container.innerHTML = html;
}

function selectRace(rno){
  if(!DATA) return;
  selectedRace = rno;
  updatePersistentBanners(rno);
  document.querySelectorAll('.race-btn').forEach(c=>c.classList.remove('active'));
  const btn = document.getElementById(`rc-${rno}`);
  if(btn){ btn.classList.add('active'); btn.scrollIntoView({behavior:'smooth',block:'nearest',inline:'center'}); }
  const tabName = currentTabName();
  if(tabName==='detail')        renderDetail(rno);
  else if(tabName==='detail2')  renderBuy(rno);
  else if(tabName==='buy')      renderBuy(rno);
  else if(tabName==='comment')  renderComment(rno);
  else if(tabName==='result')   renderResult(rno);
  else if(tabName==='odds')     renderOdds(rno);
  else renderDetail(rno);
}

// ── TOAST ──
function showToast(msg){
  const t=document.getElementById('toast');
  t.textContent=msg;
  t.classList.add('show');
  setTimeout(()=>t.classList.remove('show'),2800);
}

// ── 期待値計算（オッズ入力連動）──
//
// 期待値 = final_prob（絶対値確率） × 単勝オッズ
//   > 1.0: 期待値プラス（緑）
//   0.8〜1.0: やや割高（オレンジ）
//   < 0.8: 割高（赤）
//
// 展示データなし → final_prob = tenkai_prob（相対値）で代用
// この場合、合計は1.0になるため厳密な期待値ではなく目安として扱う。
//
function updateEV(){
  document.querySelectorAll('.ev-cell').forEach(cell => {
    const boat = cell.dataset.boat;
    const fp   = parseFloat(cell.dataset.fp);
    const oddsEl = document.getElementById(`odds-${boat}`);
    if(!oddsEl) return;
    const odds = parseFloat(oddsEl.value);
    if(isNaN(odds) || odds <= 0){
      cell.textContent = '—';
      cell.style.color = 'var(--text3)';
      cell.style.fontWeight = '';
      return;
    }
    const ev = fp * odds;
    cell.textContent = ev.toFixed(2);
    if(ev >= 1.0){
      cell.style.color = 'var(--green)';
      cell.style.fontWeight = '700';
    } else if(ev >= 0.8){
      cell.style.color = 'var(--orange)';
      cell.style.fontWeight = '600';
    } else {
      cell.style.color = 'var(--red)';
      cell.style.fontWeight = '';
    }
  });
}

// ── 初期化 ──
(async function(){
  // フェーズ2: JSON fetchを先に完了させてからUIを構築する
  // 失敗しても埋め込みデータで動作継続（フォールバック保証）
  try { await fetchAndMergeJsonData(); } catch(e) { console.warn('[init] fetchAndMergeJsonData failed:', e); }

  try {
  const isRefresh    = sessionStorage.getItem('refresh_flag') === '1';
  const goTopAfterRefresh = sessionStorage.getItem('go_top_after_refresh') === '1';
  const restoreVenue = sessionStorage.getItem('refresh_venue') || '';
  const restoreRace  = parseInt(sessionStorage.getItem('refresh_race') || '0') || 0;
  const restoreTab   = sessionStorage.getItem('refresh_tab') || 'detail';
  const restoreScrollY = parseInt(sessionStorage.getItem('refresh_scrollY') || '0') || 0;

  // ★ デバッグ: 復元前の値をコンソールに出力

  // 復元キーは使い捨て（次回通常起動と区別するため即座にクリア）
  sessionStorage.removeItem('refresh_flag');
  sessionStorage.removeItem('refresh_venue');
  sessionStorage.removeItem('refresh_race');
  sessionStorage.removeItem('refresh_tab');
  sessionStorage.removeItem('refresh_scrollY');
  sessionStorage.removeItem('go_top_after_refresh');

  if(isRefresh && goTopAfterRefresh){
    currentVenue = '';
    DATA         = null;
    buildVenueTabs();
    updateDateNav();
    document.getElementById('race-bar').innerHTML = '';
    document.getElementById('inline-detail').innerHTML =
      '<div style="padding:2rem;text-align:center;color:var(--text3)">会場を選択してください</div>';
    showTopPage();
  } else if(isRefresh){
    // ── 更新ボタン後: 会場・レース・タブを完全復元 ──
    // ALL_DATA[venue] は null（データなし）か object（データあり）かの2択。
    // undefined はキー自体が存在しない（無効な会場名）なので復元不可とする。
    const hasVenue = restoreVenue && restoreVenue !== 'NONE'
                     && Object.prototype.hasOwnProperty.call(ALL_DATA, restoreVenue)
                     && ALL_DATA[restoreVenue] !== null;

    if(hasVenue){
      currentVenue = restoreVenue;
      DATA         = ALL_DATA[restoreVenue];
      selectedRace = restoreRace;
    } else {
      currentVenue = '';
      DATA         = null;
      selectedRace = 0;
    }

    buildVenueTabs();
    buildRaceBar();
    updateDateNav();

    if(hasVenue){
      document.getElementById('header-meta').innerHTML = `<strong>${restoreVenue}</strong> — ${DATA.date||''}`;

      // タブUIを先に切り替える
      const TAB_NAMES = ['detail','detail2','buy','comment','result','odds'];
      const safeTab = TAB_NAMES.includes(restoreTab) ? restoreTab : 'detail';
      TAB_NAMES.forEach(t=>{
        document.getElementById(`tab-${t}`).style.display = t === safeTab ? '' : 'none';
      });
      document.querySelectorAll('.tab-btn').forEach(b=>{
        b.classList.toggle('active', b.dataset.tab === safeTab);
      });

      // レースバーを構築してアクティブ表示
      if(restoreRace){
        selectedRace = restoreRace;
        document.querySelectorAll('.race-btn').forEach(c=>c.classList.remove('active'));
        const raceBtn = document.getElementById(`rc-${restoreRace}`);
        if(raceBtn){ raceBtn.classList.add('active'); raceBtn.scrollIntoView({behavior:'auto',block:'nearest',inline:'center'}); }
      }

      // FLYING_DATAはauto_pushで埋め込み済みのためfetch不要
      const doRender = () => {
        if(restoreRace){
          if(safeTab === 'detail')        renderDetail(restoreRace);
          else if(safeTab === 'detail2')  renderBuy(restoreRace);
          else if(safeTab === 'buy')      renderBuy(restoreRace);
          else if(safeTab === 'comment')  renderComment(restoreRace);
          else                            renderDetail(restoreRace);
        }
      };
      if(IS_SERVER && DATA.date){
        fetchTenjiAll(restoreVenue, DATA.date).then(doRender);
      } else {
        doRender();
      }
      // スクロール位置を復元
      if(restoreScrollY > 0){
        requestAnimationFrame(()=>{
          requestAnimationFrame(()=>{ window.scrollTo(0, restoreScrollY); });
        });
      }

    } else {
      document.getElementById('race-bar').innerHTML = '';
      document.getElementById('inline-detail').innerHTML =
        '<div style="padding:2rem;text-align:center;color:var(--text3)">会場を選択してください</div>';
    }

  } else {
    // ── 通常起動: TOPページを表示 ──
    currentVenue = '';
    DATA         = null;
    buildVenueTabs();
    updateDateNav();
    document.getElementById('race-bar').innerHTML = '';
    document.getElementById('inline-detail').innerHTML =
      '<div style="padding:2rem;text-align:center;color:var(--text3)">会場を選択してください</div>';
    showTopPage();
  }

  } catch(e) {
    console.error('[INIT] error:', e);
  } finally {
    // 初期化の成否に関わらずアラートを起動
    updateAlertStrip();

    // ── 60秒ごとに締め切りアラート＋現在タブを自動更新 ──
    setInterval(function(){
      updateAlertStrip();
      autoRefreshCurrentView();
    }, 60 * 1000);
  }
})();

// ── TOP PAGE: AI予想成績計算 ──
//
// 集計ロジック:
//   ① RESULT_DATA が存在するレースのみ対象（未確定レースは除外）
//   ② データ不足バナー（dq==='insufficient'の艇を含む）→ 除外
//   ③ 進入変更バナー（is_normal_course===falseの艇を含む）→ 除外
//   ④ 残りのレースで renderBuy 相当の buy3（3連単）を生成し的中チェック
//   ⑤ 的中率 = 的中レース数 / 集計対象レース数
//   ⑥ 回収率 = 的中配当合計 / (集計レース数 × 1点100円 × buy3点数の平均)
//      ※ 点数は各レースの buy3 点数で個別に計算
//
// 進入変更チェック（buildCourseOrderBanner 相当の判定）
function hasCourseOrderChange(rno, vdata) {
  const rd = vdata.races[String(rno)];
  if (!rd || !rd.boats) return false;
  const venue = vdata.venue;
  const slug = SLUG_MAP[venue] || venue;
  const key = tenjiKey(slug, vdata.date, rno);
  const cached = _tenjiCache[key];
  if (!cached) return false; // 展示データなし → バナー出ない
  const boats = rd.boats;
  const entries = boats.map(b => {
    const d = cached[String(b.boat)];
    const course = d?.course ?? null;
    const is_normal = d?.is_normal_course != null
      ? d.is_normal_course
      : (course != null ? course === b.boat : null);
    return { frame: b.boat, course, is_normal };
  });
  if (entries.some(e => e.course == null)) return false;
  return entries.some(e => e.is_normal === false);
}

// データ不足チェック
function hasInsufficient(rd) {
  return rd.boats && rd.boats.some(b => b.dq === 'insufficient');
}

// buy3 生成（renderBuy の買い目計算を再現するシンプル版）
// ※ renderBuy と同一ロジックで計算するため、一時的に DATA をセットして呼び出す
function getBuy3ForRace(venue, vdata, rno) {
    // renderBuy は DATA / selectedRace / currentVenue を参照するグローバル関数なので
    // 一時的に保存・セット・復元する
    const savedDATA   = DATA;
    const savedVenue  = currentVenue;
    const savedRace   = selectedRace;
    // detail2-panel の中身を壊さないよう退避
    const panel = document.getElementById('detail2-panel');
    const savedInner = panel ? panel.innerHTML : '';

    DATA = vdata;
    currentVenue = venue;
    selectedRace = rno;

    let buy3Result = [];
    try {
      renderBuy(rno);
      // renderBuy が detail2-panel に書き込んだ HTML から buy3 情報を復元するのは困難なため、
      // renderBuy 内で生成される buy3 配列を直接取得する別アプローチを使用
    } catch(e) { /* ignore */ }

    // 復元
    DATA = savedDATA;
    currentVenue = savedVenue;
    selectedRace = savedRace;
    if (panel) panel.innerHTML = savedInner;

    return buy3Result;
  }

  // buy3を直接計算する純粋関数版（renderBuy の buy3 生成部分を独立化）
function computeBuy3(venue, vdata, rno, buyMode = 'hit') {
    const rd = vdata.races[String(rno)];
    if (!rd) return [];
    const slug = SLUG_MAP[venue] || venue;
    const tKey = tenjiKey(slug, vdata.date, rno);
    const tenjiData = _tenjiCache[tKey] || null;

    // 一時的に DATA / currentVenue をセットして calcTenkaiProbs 等を利用
    const savedDATA  = DATA;
    const savedVenue = currentVenue;
    DATA = vdata;
    currentVenue = venue;

    // 買い目上限（バックテスト用）: buyMode 別に opt_points_hit/rec を参照
    // 見送り推奨（pass_reason あり）は集計から除外されるため 0 が来ることはないが念のため10点フォールバック
    // ※ synthチェックの try ブロックからも参照するため function スコープで定義
    const BUY_MAX_POINTS_BT = buyMode === 'rec'
      ? (rd.opt_points_rec != null && rd.opt_points_rec > 0 ? rd.opt_points_rec : (rd.opt_points != null ? rd.opt_points : 10))
      : (rd.opt_points_hit != null && rd.opt_points_hit > 0 ? rd.opt_points_hit : (rd.opt_points != null ? rd.opt_points : 10));

    let buy3 = [];
    try {
      const arek = rd.arek ?? 54.7;
      const rawBoats = rd.boats;
      const ranked = calcTenkaiProbs(rawBoats, arek);

      // 展示スコア
      let tenjiScoreMap = null;
      if (tenjiData) tenjiScoreMap = calcTenjiScore(ranked, tenjiData, venue, arek);

      // final_prob 計算（指数重み方式 / FINAL_PROB_WEIGHTS と同一ロジック）
      const probTotal = ranked.reduce((s, b) => s + b.prob, 0) || 1;
      const useMaster = hasMasterExt() && !!(MASTER_EXT.venue_kimari && MASTER_EXT.venue_kimari[venue]);
      // arek連動動的重みを取得（renderBuy と同一ロジック）
      const { wBase: _wBase, wTenkai: _wTenkai, wTenji: _wTenji } = calcDynamicWeights(arek);
      const tenkaiOnlyTotal = ranked.reduce((s, x) => s + (x.tenkai_score ?? x.tenkai_prob), 0) || 1;
      // 前コース参照マップ（renderBuy と同一）
      const boatByNo_bt = {};
      rawBoats.forEach(b => { boatByNo_bt[b.boat] = b; });
      // 展示タイム生データ（renderBuy と同一）
      const tenjiRawMap_bt = {};
      if (tenjiData) {
        Object.keys(tenjiData).filter(k => /^\d+$/.test(k)).forEach(k => {
          const entry = tenjiData[k];
          if (entry && typeof entry.tenji === 'number') tenjiRawMap_bt[parseInt(k)] = entry.tenji;
        });
      }
      ranked.forEach(b => {
        const baseNorm = b.prob / probTotal;
        const prevBoat = boatByNo_bt[b.boat - 1] || null;
        // 展開補正 + ST順位相対差補正（renderBuy と同一）
        let tenkaiCoef = 1.0;
        if (useMaster && baseNorm > 0) {
          const tenkaiNorm = (b.tenkai_score ?? b.tenkai_prob) / tenkaiOnlyTotal;
          tenkaiCoef = Math.min(3.0, Math.max(0.3, tenkaiNorm / baseNorm));
        }
        if (prevBoat) {
          const myStRank   = MASTER_EXT?.course_master?.[b.name]?.[String(b.boat)]?.st_rank;
          const prevStRank = MASTER_EXT?.course_master?.[prevBoat.name]?.[String(prevBoat.boat)]?.st_rank;
          if (myStRank != null && prevStRank != null) {
            tenkaiCoef = Math.min(3.0, Math.max(0.3, tenkaiCoef + (prevStRank - myStRank) * 0.10));
          }
        }
        // 展示補正 + 展示タイム相対差補正（renderBuy と同一）
        let tenjiCoef = 1.0;
        if (tenjiScoreMap) tenjiCoef = tenjiScoreMap[`__coef_${b.boat}`] ?? 1.0;
        if (prevBoat && tenjiData) {
          const myTenji   = tenjiRawMap_bt[b.boat]        ?? null;
          const prevTenji = tenjiRawMap_bt[prevBoat.boat] ?? null;
          if (myTenji != null && prevTenji != null) {
            tenjiCoef = Math.min(2.0, Math.max(0.5, tenjiCoef + (prevTenji - myTenji) * 0.50));
          }
        }
        const _wTenjiCourse = _wTenji * (TENJI_WEIGHT_BY_COURSE[b.boat] ?? 1.0);
        b._multi_score = Math.pow(baseNorm, _wBase) *
                         Math.pow(tenkaiCoef, _wTenkai) *
                         Math.pow(tenjiCoef,  _wTenjiCourse);
      });
      const multiTotal = ranked.reduce((s, b) => s + b._multi_score, 0) || 1;
      ranked.forEach(b => { b.final_prob = b._multi_score / multiTotal; });
      ranked.sort((a, b) => b.final_prob - a.final_prob);

      // place2
      const place2Map = calcPlace2Probs(rawBoats, ranked);
      const ranked2 = ranked.map(b => ({ ...b, place2_prob: place2Map[b.boat] || 0 }));

      // シナリオ計算
      const sd = calcScenarioData(ranked2, rawBoats, tenjiScoreMap);

      // 以下 renderBuy と同じ buy3 生成ロジック
      const cRates_buy = (vdata.inn_data || {}).course_rates || [];
      const inn2Place_buy = (() => {
        const v = (vdata.inn_data || {}).inn_2place;
        if (v && typeof v === 'object' && !Array.isArray(v) && Object.keys(v).length > 0) return v;
        return MASTER_EXT?.venue_stats?.[venue]?.inn_2place || {};
      })();
      const venueAvg1_buy = cRates_buy[1] ?? 0.45;
      // 【改修】axisReliable: 1号艇 final_prob ≥ 場平均 かつ 最終確率順位が上位2艇以内
      const boat1ForAxis_bt   = ranked2.find(b => b.boat === 1);
      const boat1FinalProb_bt = boat1ForAxis_bt?.final_prob ?? 0;
      const boat1AboveAvg_bt  = boat1FinalProb_bt >= venueAvg1_buy;
      const boat1RankBt = [...ranked2]
        .sort((a, b) => (b.final_prob ?? 0) - (a.final_prob ?? 0))
        .findIndex(b => b.boat === 1);
      const boat1InTop2_bt = boat1RankBt <= 1;
      const axisReliable = boat1AboveAvg_bt && boat1InTop2_bt;

      const tenkaiRem_buy = (() => {
        const vLocal = MASTER_EXT?.venue_stats?.[venue]?.tenkai_remaining;
        if (vLocal && typeof vLocal === 'object' && Object.keys(vLocal).length > 0) return vLocal;
        return MASTER_EXT?.tenkai_remaining || null;
      })();
      const winnerCO_buy = MASTER_EXT?.winner_course_order || {};

      const buy3seen = new Set();

      // pick3rd_local: renderBuy の calc3rdScores + R3_MIN_THRESHOLD と完全同一ロジック
      // calc3rdScores はトップレベル関数のため computeBuy3 からも直接呼び出し可能
      const R3_MIN_THRESHOLD_BT = 0.03;
      function pick3rd_local(winnerBoat, kimari, secondBoat, buyMode) {
        const p3Target = (buyMode === 'hit') ? 0.80 : 0.70;
        // calc3rdScores を使って renderBuy と同一のスコアを算出
        // DATA / currentVenue は computeBuy3 冒頭で vdata にセット済み
        const thirdAll = calc3rdScores(ranked2, tenjiScoreMap, winnerBoat, kimari, secondBoat);
        if(thirdAll.length === 0) return [];
        const scoreTotal = thirdAll.reduce((s, x) => s + x.score, 0) || 1;
        const picked = []; let cum = 0;
        for(const x of thirdAll){
          if(x.r3 != null && x.r3 < R3_MIN_THRESHOLD_BT) continue; // 絶対値ガード
          picked.push(x.boat);
          cum += x.score / scoreTotal;
          if(cum >= p3Target) break;
        }
        return picked;
      }

      if (sd.valid) {
        const { scenarioProb, scenarioPlace2, kimariTypes } = sd;
        function kimariToLc(k) {
          return { '逃げ': 'bl-nige', '差し': 'bl-sashi', 'まくり': 'bl-makuri', 'まくり差し': 'bl-makusas', '抜き': 'bl-nuki' }[k] || 'bl-nuki';
        }
        const allScenPairs = [];
        for (const winner of ranked2) {
          for (const k of kimariTypes) {
            const p = scenarioProb[winner.boat]?.[k];
            if (p > 0.001) allScenPairs.push({ boat: winner.boat, kimari: k, prob: p });
          }
        }
        allScenPairs.sort((a, b) => b.prob - a.prob);
        const seenK = new Set();
        const top3Scen = [];
        for (const pair of allScenPairs) {
          if (seenK.has(pair.kimari)) continue;
          seenK.add(pair.kimari);
          top3Scen.push(pair);
          if (top3Scen.length >= 3) break;
        }
        // 【改修】2着閾値: hit=75% / rec=70%（renderBuy の PICK2_PROB_TARGET_HIT2/REC2 と統一）
        function pick2nd_local(winnerBoat, kimari, buyMode) {
          const p2Target = (buyMode === 'hit') ? 0.75 : 0.70;
          const list = scenarioPlace2[winnerBoat]?.[kimari] || [];
          if (list.length === 0) return [];
          // renderBuy の pick2nd と同一: 逃げ1号艇は inn2Place_buy で特殊ソート
          const isNige = (kimari === '逃げ' && winnerBoat === 1);
          let sorted;
          if (isNige && Object.keys(inn2Place_buy).length > 0) {
            const avgRate = Object.values(inn2Place_buy).reduce((s, v) => s + v, 0) / Object.keys(inn2Place_buy).length;
            sorted = [...list].sort((a, b) => {
              const aAbove = (inn2Place_buy[String(a.boat)] ?? 0) >= avgRate ? 1 : 0;
              const bAbove = (inn2Place_buy[String(b.boat)] ?? 0) >= avgRate ? 1 : 0;
              if (bAbove !== aAbove) return bAbove - aAbove;
              return b.p2 - a.p2;
            });
          } else {
            sorted = [...list].sort((a, b) => b.p2 - a.p2);
          }
          const picked = [];
          let cum = 0;
          for (const item of sorted) {
            if (item.boat === winnerBoat) continue;
            picked.push(item.boat);
            cum += item.p2;
            if (cum >= p2Target) break;
          }
          return picked;
        }
        // 【改修】バックテスト: モード別1着軸決定（renderBuy と完全同一仕様）
        const BT_MODE = buyMode;
        // isDualAxis: 乖離率が DIVERGENCE_THRESHOLD_HIT 未満なら僅差2頭軸
        const probDiff_bt    = ((ranked2[0]?.final_prob ?? 0) - (ranked2[1]?.final_prob ?? 0)) * 100;
        const isDualAxis_bt  = probDiff_bt < DIVERGENCE_THRESHOLD_HIT;
        const axisReliable_bt = !isDualAxis_bt; // 乖離率 ≥ 閾値のとき1艇固定軸
        let btScenariosToProcess;
        if(BT_MODE === 'hit'){
          if(axisReliable_bt){
            // 乖離率 ≥ 閾値: final_prob 1位艇を1艇固定軸
            const fp1stBoat_bt = ranked2[0];
            const boat1Scens_bt = top3Scen.filter(s => s.boat === fp1stBoat_bt.boat);
            if(boat1Scens_bt.length === 0){
              const fp1stBest_bt = allScenPairs.find(p => p.boat === fp1stBoat_bt.boat);
              btScenariosToProcess = fp1stBest_bt ? [fp1stBest_bt, ...top3Scen.filter(s => s.boat !== fp1stBoat_bt.boat)] : top3Scen;
            } else {
              btScenariosToProcess = [...boat1Scens_bt, ...top3Scen.filter(s => s.boat !== fp1stBoat_bt.boat)];
            }
          } else {
            // 乖離率 < 閾値（isDualAxis_bt）: final_prob 1位 + 2位の2軸展開
            const fp1stBoat_bt = ranked2[0];
            const fp2ndBoat_bt = ranked2[1];
            const dualAxes_bt  = [fp1stBoat_bt?.boat, fp2ndBoat_bt?.boat].filter(Boolean);
            const dualScens_bt = dualAxes_bt.map(ax => allScenPairs.find(p => p.boat === ax)).filter(Boolean);
            const dualRest_bt  = top3Scen.filter(s => !dualAxes_bt.includes(s.boat)).slice(0, 1);
            btScenariosToProcess = [...dualScens_bt, ...dualRest_bt];
          }
        } else {
          // rec: final_prob 1位が1号艇でないとき上位2艇軸展開（renderBuy と統一）
          const fp1stIsBoat1_bt = (ranked2[0]?.boat === 1);
          if(!fp1stIsBoat1_bt){
            const top2FPBoats_bt = [ranked2[0]?.boat, ranked2[1]?.boat].filter(Boolean);
            const recScens_bt    = allScenPairs.filter(p => top2FPBoats_bt.includes(p.boat)).slice(0, 4);
            btScenariosToProcess = recScens_bt.length > 0 ? recScens_bt : top3Scen;
          } else {
            btScenariosToProcess = top3Scen;
          }
        }
        btScenariosToProcess.forEach((topScen, scenIdx) => {
          const axisBoat = topScen.boat;
          const kimari = topScen.kimari;
          const lc = kimariToLc(kimari);
          const scenProb = scenarioProb[axisBoat]?.[kimari] ?? 0;
          const seconds = pick2nd_local(axisBoat, kimari, BT_MODE);
          seconds.forEach(s2 => {
            const thirdList = pick3rd_local(axisBoat, kimari, s2, BT_MODE);
            thirdList.forEach(t => {
              const key3 = `${axisBoat}-${s2}-${t}`;
              if (axisBoat !== s2 && s2 !== t && axisBoat !== t && !buy3seen.has(key3) && buy3.length < BUY_MAX_POINTS_BT) {
                buy3seen.add(key3);
                buy3.push({ c: `${axisBoat}−${s2}−${t}`, lc, scenarioGroup: scenIdx });
              }
              // 折り返し
              if (seconds.length === 1) {
                const keyRev = `${axisBoat}-${t}-${s2}`;
                if (axisBoat !== t && t !== s2 && axisBoat !== s2 && !buy3seen.has(keyRev) && buy3.length < BUY_MAX_POINTS_BT) {
                  buy3seen.add(keyRev);
                  buy3.push({ c: `${axisBoat}−${t}−${s2}`, lc, scenarioGroup: scenIdx });
                }
              }
            });
          });
        });
      } else {
        // MASTERなしフォールバック
        const A = ranked[0], B = ranked[1];
        const p2A = ranked2.filter(b => b.boat !== A.boat).sort((x, y) => y.place2_prob - x.place2_prob);
        const P2a = p2A[0] || B;
        const P2b = p2A[1] || ranked[2];
        const lbNige = arek < 40 ? '逃げ' : arek > 60 ? 'まくり' : '差し';
        const lcNige = arek < 40 ? 'bl-nige' : arek > 60 ? 'bl-makuri' : 'bl-sashi';
        [[A.boat, P2a.boat], [A.boat, P2b ? P2b.boat : null]].forEach(([first, second]) => {
          if (!second) return;
          pick3rd_local(first, null, second, 'hit').forEach(t => {
            const key = `${first}-${second}-${t}`;
            if (first !== second && second !== t && first !== t && !buy3seen.has(key) && buy3.length < BUY_MAX_POINTS_BT) {
              buy3seen.add(key);
              buy3.push({ c: `${first}−${second}−${t}`, lc: lcNige, scenarioGroup: 0 });
            }
          });
        });
      }
    } catch(e) {
      console.warn('[calcTopAIStats] computeBuy3 error:', e);
    }

    // ── renderBuy の checkSynthOdds と同一判定を適用 ──
    // 買い目は削らず、合成オッズが目標未満なら見送り（空配列）とする
    try {
      // ── オッズソース選択 ──
      // ODDS_DATA には締切前の暫定オッズが残る場合があり、
      // 最終オッズ（確定後）と乖離することがある。
      // ただし RESULT_DATA.sanrentan には的中組み合わせのオッズしか含まれないため、
      // 全買い目の合成オッズは計算できない。
      // → ODDS_DATA を引き続き使用しつつ、
      //    オッズが1点しか取れない（synthCount が極端に少ない）場合は
      //    判定を信頼せず ODDS_DATA 不完全として見送りにする。
      const raceOdds3t_trim = ODDS_DATA?.[vdata.date]?.[venue]?.[String(rno)]?.['3t'] ?? {};

      // rec合成オッズ基準: 4.0倍固定（hit: 2.5倍固定）
      const synthMin_trim   = buyMode === 'rec' ? 4.0 : 2.5;
      const maxPts_trim     = BUY_MAX_POINTS_BT;

      const candidates = buy3.slice(0, maxPts_trim);
      let synthDenom = 0, synthCount = 0;
      candidates.forEach(r => {
        const ov = raceOdds3t_trim[normalizeCombo(r.c)] ?? null;
        if (ov != null && ov > 0) { synthDenom += 1 / ov; synthCount++; }
      });

      // オッズが1点も取得できていない場合は見送り（参加しない）
      if (synthCount === 0 || synthDenom === 0) {
        buy3 = []; // オッズ未取得 → 見送り扱い
      } else {
        const so = 1 / synthDenom;
        buy3 = so >= synthMin_trim ? candidates : []; // 未達なら見送り
      }
    } catch(e) {
      console.warn('[computeBuy3] synth check error:', e);
    }

    DATA = savedDATA;
    currentVenue = savedVenue;
    return buy3;
  }

// ── 日付カードHTMLを生成するヘルパー ──
function buildDateCard(dateStr, label) {
  const { results: resultsHit } = collectResultsForDate(dateStr, 'hit');
  const { results: resultsRec, excludedList } = collectResultsForDate(dateStr, 'rec');

  if (resultsHit.length === 0 && resultsRec.length === 0 && excludedList.length === 0) return '';

  function modePanel(results, modeName, synthMin) {
    const total = results.length;
    if (total === 0) return `
      <div style="background:var(--bg3);border-radius:var(--radius-sm);padding:10px;border:1px solid var(--border)">
        <div style="font-size:10px;font-weight:700;color:var(--text3);text-align:center;margin-bottom:4px">${modeName}</div>
        <div style="font-size:10px;color:var(--text3);text-align:center;margin-bottom:4px">合成${synthMin}倍以上</div>
        <div style="color:var(--text3);font-size:11px;text-align:center;padding:0.3rem 0">集計対象なし</div>
      </div>`;
    const hitCount     = results.filter(r => r.isHit).length;
    const hitRate      = hitCount / total;
    const totalBet     = results.reduce((s, r) => s + r.buy3cnt * 100, 0);
    const totalReturn  = results.filter(r => r.isHit).reduce((s, r) => s + r.hitOdds, 0);
    const recoveryRate = totalBet > 0 ? totalReturn / totalBet : 0;
    const hitColor = hitRate      >= 0.7 ? 'var(--green)' : hitRate      >= 0.5 ? 'var(--orange)' : 'var(--text)';
    const recColor = recoveryRate >= 1.0 ? 'var(--green)' : recoveryRate >= 0.75 ? 'var(--orange)' : 'var(--text)';

    // 会場別内訳
    const venueMap = {};
    results.forEach(r => {
      if (!venueMap[r.venue]) venueMap[r.venue] = [];
      venueMap[r.venue].push(r);
    });
    const venueBlocks = VENUE_LIST.filter(v => venueMap[v]).map(v => {
      const vRaces   = venueMap[v];
      const vHit     = vRaces.filter(r => r.isHit).length;
      const vTotal   = vRaces.length;
      const vHitRate = vHit / vTotal;
      const vBet     = vRaces.reduce((s, r) => s + r.buy3cnt * 100, 0);
      const vReturn  = vRaces.filter(r => r.isHit).reduce((s, r) => s + r.hitOdds, 0);
      const vRec     = vBet > 0 ? vReturn / vBet : 0;
      const vHitCls  = vHitRate >= 0.7 ? 'hit' : vHitRate >= 0.5 ? 'warn' : '';
      const vRecCls  = vRec >= 1.0 ? 'over' : vRec >= 0.75 ? 'warn' : '';

      const raceDetails = vRaces.map(r => {
        const hitOddsStr = r.isHit && r.hitOdds ? `￥${r.hitOdds.toLocaleString()}` : '';
        // combo文字列（例: "1-2-4"）を枠番バッジ列に変換するローカルヘルパー
        const comboBadges = combo => (combo || '').split(/[-－−]/).map(n =>
          /^[1-6]$/.test(n.trim()) ? `<span class="boat-circle b${n.trim()}" style="width:20px;height:20px;font-size:10px;display:inline-flex;align-items:center;justify-content:center;flex-shrink:0">${n.trim()}</span>` : ''
        ).join('<span style="color:var(--text3);font-size:11px;margin:0 1px">−</span>');
        const resultStr = r.actualResult
          ? `<span style="display:inline-flex;align-items:center;gap:2px;margin-left:4px">${comboBadges(r.actualResult)}</span>`
          : '';
        const hitPart = r.isHit
          ? `<span class="ai-venue-race-hit" style="flex-shrink:0">🎯 的中</span>${resultStr}<span class="ai-venue-race-odds" style="flex-shrink:0">${hitOddsStr}</span>`
          : `<span class="ai-venue-race-miss" style="flex-shrink:0">—</span>${resultStr}`;
        return `<div class="ai-race-row" style="display:flex;align-items:center;gap:6px;padding:5px 8px;border-bottom:1px solid var(--border)">
          <span class="ai-venue-race-no" style="flex-shrink:0">${r.rno}R</span>
          <span class="ai-venue-race-cnt" style="flex-shrink:0">${r.buy3cnt}点</span>
          ${hitPart}
        </div>`;
      }).join('');

      return `<details class="ai-venue-details">
        <summary class="ai-venue-summary">
          <span class="ai-venue-summary-arrow">▶</span>
          <span class="ai-venue-name">${v}</span>
          <span class="ai-venue-stat">
            <span class="ai-venue-stat-label">的中率</span>
            <span class="ai-venue-stat-val ${vHitCls}">${(vHitRate*100).toFixed(0)}%</span>
            <span class="ai-venue-stat-sub">${vHit}/${vTotal}R</span>
          </span>
          <span class="ai-venue-stat">
            <span class="ai-venue-stat-label">回収率</span>
            <span class="ai-venue-stat-val ${vRecCls}">${(vRec*100).toFixed(0)}%</span>
          </span>
        </summary>
        <div class="ai-venue-race-list">${raceDetails}</div>
      </details>`;
    }).join('');

    const detailHtml = venueBlocks ? `
      <details style="margin-top:0.5rem">
        <summary style="font-size:11px;font-weight:700;color:var(--text3);cursor:pointer;letter-spacing:.06em;list-style:none;display:flex;align-items:center;gap:5px">
          <span style="font-size:10px">▶</span> 会場別内訳
        </summary>
        <div class="ai-venue-list" style="margin-top:0.5rem">${venueBlocks}</div>
      </details>` : '';

    return `
      <div style="background:var(--bg3);border-radius:var(--radius-sm);padding:10px;border:1px solid var(--border)">
        <div style="font-size:10px;font-weight:700;color:var(--text3);text-align:center;margin-bottom:2px">${modeName}</div>
        <div style="font-size:10px;color:var(--text3);text-align:center;margin-bottom:8px">合成${synthMin}倍以上</div>
        <div style="display:flex;flex-direction:column;gap:5px">
          <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);padding-bottom:4px">
            <span style="font-size:10px;color:var(--text3)">的中率</span>
            <span style="font-size:15px;font-weight:700;font-family:var(--mono);color:${hitColor}">${(hitRate*100).toFixed(0)}%</span>
          </div>
          <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);padding-bottom:4px">
            <span style="font-size:10px;color:var(--text3)">回収率</span>
            <span style="font-size:15px;font-weight:700;font-family:var(--mono);color:${recColor}">${(recoveryRate*100).toFixed(0)}%</span>
          </div>
          <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);padding-bottom:4px">
            <span style="font-size:10px;color:var(--text3)">集計R</span>
            <span style="font-size:12px;font-weight:700;font-family:var(--mono);color:var(--text)">${total}R</span>
          </div>
        </div>
        ${detailHtml}
      </div>`;
  }

  return `
    <div class="ai-stats-card" style="margin-bottom:0.6rem">
      <div style="font-size:11px;font-weight:700;color:var(--text3);letter-spacing:.06em;margin-bottom:0.75rem;display:flex;align-items:center;gap:6px">
        <span style="background:var(--bg4);border-radius:4px;padding:1px 7px;font-size:10px">${label}</span>
        <span style="font-size:11px;color:var(--text2)">${dateStr}</span>
      </div>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:10px">
        ${modePanel(resultsHit, '🎯 的中重視', 2.5)}
        ${modePanel(resultsRec, '💰 回収重視', 4.0)}
      </div>
    </div>`;
}

// ── AI予想成績を表示するメイン関数 ──
function calcTopAIStats() {
  const elToday   = document.getElementById('top-ai-stats-today');
  const elHistory = document.getElementById('top-ai-stats-history-summary');
  const elDetail  = document.getElementById('top-ai-stats');

  const allDates  = getAvailableDates().slice().reverse(); // 新しい順
  const todayDate = getAvailableDates().slice(-1)[0];
  const histDates = getAvailableDates().slice(0, -1).reverse(); // 過去日（新しい順）

  const noDataHtml = `<div class="ai-stats-card"><div style="color:var(--text3);font-size:12px;text-align:center;padding:0.5rem 0">データがありません</div></div>`;
  const noRaceHtml = `<div class="ai-stats-card"><div style="color:var(--text3);font-size:12px;text-align:center;padding:0.5rem 0">確定レースがまだありません</div></div>`;

  if (allDates.length === 0) {
    if (elToday)   elToday.innerHTML   = noDataHtml;
    if (elHistory) elHistory.innerHTML = noDataHtml;
    if (elDetail)  elDetail.innerHTML  = noDataHtml;
    return;
  }

  const dateLabels = { [todayDate]: '本日' };
  histDates.forEach((d, i) => { dateLabels[d] = `${i + 1}日前`; });

  // ── ① 本日エリア ──
  if (elToday) {
    const todayHtml = todayDate ? buildDateCard(todayDate, '本日') : '';
    elToday.innerHTML = todayHtml || noRaceHtml;
  }

  // ── ② 過去30日 集計サマリーエリア ──
  if (elHistory) {
    const past30 = histDates.slice(0, 30);
    if (past30.length === 0) {
      elHistory.innerHTML = `<div class="ai-stats-card"><div style="color:var(--text3);font-size:12px;text-align:center;padding:0.5rem 0">過去データがありません</div></div>`;
    } else {
      // ── 的中重視・回収重視 それぞれ集計 ──
      const allResultsHit = [];
      const allResultsRec = [];
      past30.forEach(d => {
        const { results: rh } = collectResultsForDate(d, 'hit');
        const { results: rr } = collectResultsForDate(d, 'rec');
        allResultsHit.push(...rh);
        allResultsRec.push(...rr);
      });

      if (allResultsHit.length === 0 && allResultsRec.length === 0) {
        elHistory.innerHTML = `<div class="ai-stats-card"><div style="color:var(--text3);font-size:12px;text-align:center;padding:0.5rem 0">確定レースがありません</div></div>`;
      } else {
        function mode30Panel(results, modeName, synthMin) {
          const total = results.length;
          if (total === 0) return `
            <div style="background:var(--bg3);border-radius:var(--radius-sm);padding:12px;border:1px solid var(--border)">
              <div style="font-size:10px;font-weight:700;color:var(--text3);text-align:center;margin-bottom:4px">${modeName}</div>
              <div style="font-size:10px;color:var(--text3);text-align:center;margin-bottom:4px">合成${synthMin}倍以上</div>
              <div style="color:var(--text3);font-size:11px;text-align:center;padding:0.3rem 0">集計対象なし</div>
            </div>`;
          const hitCount     = results.filter(r => r.isHit).length;
          const hitRate      = hitCount / total;
          const totalBet     = results.reduce((s, r) => s + r.buy3cnt * 100, 0);
          const totalReturn  = results.filter(r => r.isHit).reduce((s, r) => s + r.hitOdds, 0);
          const recoveryRate = totalBet > 0 ? totalReturn / totalBet : 0;
          const hitColor = hitRate      >= 0.7 ? 'var(--green)' : hitRate      >= 0.5 ? 'var(--orange)' : 'var(--text)';
          const recColor = recoveryRate >= 1.0 ? 'var(--green)' : recoveryRate >= 0.75 ? 'var(--orange)' : 'var(--text)';

          // 会場別内訳テーブル
          const venueMap30 = {};
          results.forEach(r => {
            if (!venueMap30[r.venue]) venueMap30[r.venue] = [];
            venueMap30[r.venue].push(r);
          });
          const venueRows30 = VENUE_LIST.filter(v => venueMap30[v]).map(v => {
            const vrs   = venueMap30[v];
            const vHit  = vrs.filter(r => r.isHit).length;
            const vTot  = vrs.length;
            const vBet  = vrs.reduce((s, r) => s + r.buy3cnt * 100, 0);
            const vRet  = vrs.filter(r => r.isHit).reduce((s, r) => s + r.hitOdds, 0);
            const vRec  = vBet > 0 ? vRet / vBet : 0;
            const vHitColor = (vHit/vTot) >= 0.7 ? 'var(--green)' : (vHit/vTot) >= 0.5 ? 'var(--orange)' : 'var(--text)';
            const vRecColor = vRec >= 1.0 ? 'var(--green)' : vRec >= 0.75 ? 'var(--orange)' : 'var(--text)';
            return `<tr style="border-bottom:1px solid var(--border)">
              <td style="padding:3px 6px;font-size:11px;color:var(--text2);white-space:nowrap">${v}</td>
              <td style="padding:3px 6px;text-align:right;font-size:11px;font-weight:700;color:${vHitColor}">${(vHit/vTot*100).toFixed(0)}%</td>
              <td style="padding:3px 6px;text-align:right;font-size:10px;color:var(--text3)">${vHit}/${vTot}R</td>
              <td style="padding:3px 6px;text-align:right;font-size:11px;font-weight:700;color:${vRecColor}">${(vRec*100).toFixed(0)}%</td>
            </tr>`;
          }).join('');

          const venueDetail30 = venueRows30 ? `
            <details style="margin-top:6px">
              <summary style="font-size:11px;font-weight:700;color:var(--text3);cursor:pointer;list-style:none;display:flex;align-items:center;gap:4px;padding:2px 0">
                <span style="font-size:10px">▶</span> 会場別内訳
              </summary>
              <div style="overflow-x:auto;margin-top:4px">
                <table style="width:100%;border-collapse:collapse">
                  <thead><tr style="border-bottom:1px solid var(--border)">
                    <th style="padding:3px 6px;text-align:left;font-size:10px;color:var(--text3);font-weight:500">会場</th>
                    <th style="padding:3px 6px;text-align:right;font-size:10px;color:var(--text3);font-weight:500">的中率</th>
                    <th style="padding:3px 6px;text-align:right;font-size:10px;color:var(--text3);font-weight:500">R数</th>
                    <th style="padding:3px 6px;text-align:right;font-size:10px;color:var(--text3);font-weight:500">回収率</th>
                  </tr></thead>
                  <tbody>${venueRows30}</tbody>
                </table>
              </div>
            </details>` : '';

          return `
            <div style="background:var(--bg3);border-radius:var(--radius-sm);padding:12px;border:1px solid var(--border)">
              <div style="font-size:10px;font-weight:700;color:var(--text3);text-align:center;margin-bottom:2px">${modeName}</div>
              <div style="font-size:10px;color:var(--text3);text-align:center;margin-bottom:10px">合成${synthMin}倍以上</div>
              <div style="display:flex;flex-direction:column;gap:6px">
                <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);padding-bottom:5px">
                  <span style="font-size:10px;color:var(--text3)">的中率</span>
                  <div style="text-align:right">
                    <span style="font-size:18px;font-weight:700;font-family:var(--mono);color:${hitColor}">${(hitRate*100).toFixed(0)}%</span>
                    <div style="font-size:10px;color:var(--text3)">${hitCount}/${total}R</div>
                  </div>
                </div>
                <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);padding-bottom:5px">
                  <span style="font-size:10px;color:var(--text3)">回収率</span>
                  <div style="text-align:right">
                    <span style="font-size:18px;font-weight:700;font-family:var(--mono);color:${recColor}">${(recoveryRate*100).toFixed(0)}%</span>
                    <div style="font-size:10px;color:var(--text3)">${totalReturn.toLocaleString()}円</div>
                  </div>
                </div>
                <div style="display:flex;justify-content:space-between;align-items:center">
                  <span style="font-size:10px;color:var(--text3)">集計R</span>
                  <span style="font-size:13px;font-weight:700;font-family:var(--mono);color:var(--text)">${total}R</span>
                </div>
              </div>
              ${venueDetail30}
            </div>`;
        }

        elHistory.innerHTML = `
          <div class="ai-stats-card" style="margin-bottom:0.6rem">
            <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:10px">
              ${mode30Panel(allResultsHit, '🎯 的中重視', 2.5)}
              ${mode30Panel(allResultsRec, '💰 回収重視', 4.0)}
            </div>
          </div>`;
      }
    }
  }

  // ── ③ 各日詳細エリア ──
  if (elDetail) {
    const cardsHtml = allDates.map(d => buildDateCard(d, dateLabels[d] || d)).filter(Boolean).join('');
    elDetail.innerHTML = cardsHtml || noRaceHtml;
  }
}

function normalizeCombo(s) { return (s || '').replace(/[－−\-]/g, '-'); }

// ── 1日分の集計を行うヘルパー ──
function collectResultsForDate(dateStr, buyMode = 'hit') {
  const dataForDate = getDataForDate(dateStr);
  const results = [];
  const excludedList = [];

  VENUE_LIST.forEach(venue => {
    const vdata = dataForDate[venue];
    if (!vdata || !vdata.races) return;
    const slug = SLUG_MAP[venue] || venue;

    // 江戸川は集計対象外
    if (venue === '江戸川') {
      excludedList.push({ venue, rno: null, reason: '※除外' });
      return;
    }

    Object.entries(vdata.races).sort((a, b) => +a[0] - +b[0]).forEach(([rnoStr, rd]) => {
      const rno = parseInt(rnoStr);
      if (!rd || !rd.boats) return;

      const rKey = resultKey(slug, vdata.date, rno);
      const resultRd = RESULT_DATA[rKey];
      if (!resultRd || !resultRd.sanrentan || resultRd.sanrentan.length === 0) return;

      if (hasInsufficient(rd)) {
        excludedList.push({ venue, rno, reason: 'データ不足' });
        return;
      }
      if (hasCourseOrderChange(rno, vdata)) {
        excludedList.push({ venue, rno, reason: '進入変更' });
        return;
      }

      // ── 見送り推奨パターン除外（成績集計・的中率・回収率の分母から除外）──
      const _passReason = buyMode === 'rec'
        ? (rd.opt_pass_reason_rec || '')
        : (rd.opt_pass_reason_hit || '');
      if (_passReason) {
        excludedList.push({ venue, rno, reason: `見送り推奨（${rd.opt_pattern || ''}）` });
        return;
      }

      const buy3 = computeBuy3(venue, vdata, rno, buyMode);

      // ── 見送りレース除外: computeBuy3 が空配列 = 合成オッズ未達または買い目なし ──
      // computeBuy3 は内部で trimToTargetSynth を実行済みであり、
      // 合成オッズ未達の場合は空配列を返す。ここで改めて合成オッズを再計算すると
      // 「合成オッズを満たしたレースだけ集計する」サバイバーシップバイアスが生じる。
      // → buy3 が空 = 見送り として除外し、非空 = 参加 として集計するだけでよい。
      if (buy3.length === 0) {
        excludedList.push({ venue, rno, reason: `合成オッズ未達（見送り）` });
        return;
      }

      // sanrentan[0] が確定着順。全件Setにすると誤マッチする
      const resultSan3 = resultRd.sanrentan[0] ? new Set([normalizeCombo(resultRd.sanrentan[0].combo)]) : new Set();
      let isHit = false;
      let hitOdds = 0;
      let hitCombo = '';
      for (const item of buy3) {
        const nc = normalizeCombo(item.c);
        if (resultSan3.has(nc)) {
          isHit = true;
          hitCombo = nc;
          const hitResult = resultRd.sanrentan[0]; // [0]が確定着順
          hitOdds = hitResult ? hitResult.odds : 0;
          break;
        }
      }

      // 指数値を収集（CSV出力用）
      // ── auto_push.py が boats[] に埋め込んだ値を直接JOINするだけ ──
      // calcTenkaiProbs / calcTenjiScore の再計算は行わない
      const probTotal_csv = rd.boats.reduce((s, b) => s + (b.prob ?? 0), 0) || 1;
      const tenkaiTotal_csv = rd.boats.reduce((s, b) => s + (b.tenkai_score ?? b.prob ?? 0), 0) || 1;
      const ranked_csv = rd.boats.map(b => {
        const baseNorm   = (b.prob ?? 0) / probTotal_csv;
        const tenkaiCoef = (baseNorm > 0 && b.tenkai_score != null)
          ? Math.min(3.0, Math.max(0.3, (b.tenkai_score / tenkaiTotal_csv) / baseNorm))
          : 1.0;
        const tenjiCoef  = (b.tenji_score != null) ? b.tenji_score : null;
        return { ...b, _csv_base: baseNorm, _csv_tenkai: tenkaiCoef, _csv_tenji: tenjiCoef };
      }).sort((a, b) => (b.prob ?? 0) - (a.prob ?? 0));

      const predTop3 = ranked_csv
        ? ranked_csv.slice(0, 3).map(b => b.boat).join('-')
        : '';
      const boat1data = ranked_csv?.find(b => b.boat === 1);

      results.push({
        venue, rno, buy3cnt: buy3.length, isHit, hitOdds, hitCombo,
        buy3combos: buy3.map(x => x.c).join(' / '),
        predTop3,
        actualResult: resultRd.sanrentan?.[0]?.combo || '',
        actualKimari: resultRd.kimari || '',
        arek: (rd.arek ?? 54.7).toFixed(1),
        hasTenji: !!(ranked_csv && ranked_csv[0]?._csv_tenji !== null),
        pred1boat:    ranked_csv?.[0]?.boat || '',
        pred1_base:   ranked_csv?.[0]?._csv_base   != null ? ranked_csv[0]._csv_base.toFixed(4)   : '',
        pred1_tenkai: ranked_csv?.[0]?._csv_tenkai  != null ? ranked_csv[0]._csv_tenkai.toFixed(4)  : '',
        pred1_tenji:  ranked_csv?.[0]?._csv_tenji   != null ? ranked_csv[0]._csv_tenji.toFixed(4)   : '',
        boat1_base:   boat1data?._csv_base   != null ? boat1data._csv_base.toFixed(4)   : '',
        boat1_tenkai: boat1data?._csv_tenkai  != null ? boat1data._csv_tenkai.toFixed(4)  : '',
        boat1_tenji:  boat1data?._csv_tenji   != null ? boat1data._csv_tenji.toFixed(4)   : '',
        opt_pattern:  rd.opt_pattern || '',
        opt_points:   rd.opt_points  != null ? rd.opt_points : 10,
      });
    });
  });

  return { results, excludedList };
}

// ── バックテスト CSV エクスポート ──
// ── CSV 生成共通ヘルパー ──
function _buildBacktestRows(buyMode) {
  const allDates  = getAvailableDates().slice().reverse();
  const todayDate = getAvailableDates().slice(-1)[0];
  const dateLabels = { [todayDate]: '本日' };
  getAvailableDates().slice(0, -1).reverse().forEach((d, i) => {
    dateLabels[d] = `${i+1}日前`;
  });

  const output = [];
  allDates.forEach(dateStr => {
    const { results } = collectResultsForDate(dateStr, buyMode);
    results.forEach(r => {
      output.push({
        日付: dateStr,
        日前: dateLabels[dateStr] || '',
        会場: r.venue,
        R番号: r.rno,
        あれ指数: r.arek || '',
        展示あり: r.hasTenji ? '○' : '×',
        予想TOP3: r.predTop3 || '',
        予想1位艇: r.pred1boat || '',
        予想1位_base: r.pred1_base || '',
        予想1位_tenkai: r.pred1_tenkai || '',
        予想1位_tenji: r.pred1_tenji || '',
        '1号艇_base': r.boat1_base || '',
        '1号艇_tenkai': r.boat1_tenkai || '',
        '1号艇_tenji': r.boat1_tenji || '',
        パターン: r.opt_pattern || '',
        推奨点数: r.opt_points != null ? r.opt_points : '',
        買い目点数: r.buy3cnt,
        買い目組合せ: r.buy3combos || '',
        的中: r.isHit ? '的中' : '外れ',
        払戻金: r.isHit ? r.hitOdds : '',
        的中組合せ: r.hitCombo || '',
        実際の結果: r.actualResult || '',
        実際の決まり手: r.actualKimari || '',
      });
    });
  });
  return output;
}

function _rowsToCSVBlob(rows) {
  if (rows.length === 0) return null;
  const headers = Object.keys(rows[0]);
  const csvRows = [
    headers.join(','),
    ...rows.map(row =>
      headers.map(h => {
        let val = row[h] ?? '';
        val = String(val).replace(/"/g, '""');
        return `"${val}"`;
      }).join(',')
    )
  ];
  return new Blob(['\uFEFF' + csvRows.join('\n')], { type: 'text/csv;charset=utf-8;' });
}

function _triggerDownload(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// ── 的中重視 CSV エクスポート ──
function exportBacktestCSV_hit() {
  const rows = _buildBacktestRows('hit');
  const blob = _rowsToCSVBlob(rows);
  if (!blob) { alert('エクスポートできるデータがありません。'); return; }
  const date = new Date().toISOString().slice(0,10).replace(/-/g,'');
  _triggerDownload(blob, `backtest_hit_${date}.csv`);
}

// ── 回収重視 CSV エクスポート ──
function exportBacktestCSV_rec() {
  const rows = _buildBacktestRows('rec');
  const blob = _rowsToCSVBlob(rows);
  if (!blob) { alert('エクスポートできるデータがありません。'); return; }
  const date = new Date().toISOString().slice(0,10).replace(/-/g,'');
  _triggerDownload(blob, `backtest_rec_${date}.csv`);
}

// ── 両方同時ダウンロード（少し間を置いて連続ダウンロード）──
function exportBacktestCSV_both() {
  const rowsHit = _buildBacktestRows('hit');
  const rowsRec = _buildBacktestRows('rec');
  if (rowsHit.length === 0 && rowsRec.length === 0) {
    alert('エクスポートできるデータがありません。');
    return;
  }
  const date = new Date().toISOString().slice(0,10).replace(/-/g,'');
  const blobHit = _rowsToCSVBlob(rowsHit);
  if (blobHit) _triggerDownload(blobHit, `backtest_hit_${date}.csv`);
  // ブラウザが連続ダウンロードをブロックしないよう 300ms ずらす
  setTimeout(() => {
    const blobRec = _rowsToCSVBlob(rowsRec);
    if (blobRec) _triggerDownload(blobRec, `backtest_rec_${date}.csv`);
  }, 300);
}

// 旧関数: 後方互換のため残す（hit モードと同等）
function exportBacktestCSV() {
  exportBacktestCSV_hit();
}

// ── TOP PAGE ──
function goTopAndRefresh() {
  sessionStorage.setItem('refresh_flag',    '1');
  sessionStorage.setItem('refresh_venue',   'NONE');
  sessionStorage.setItem('refresh_race',    '0');
  sessionStorage.setItem('refresh_tab',     'detail');
  sessionStorage.setItem('refresh_scrollY', '0');
  sessionStorage.setItem('go_top_after_refresh', '1');
  const btn = document.getElementById('refresh-btn');
  if (btn) btn.classList.add('spinning');
  setTimeout(() => { location.reload(true); }, 150);
}

function showTopPage() {
  document.getElementById('top-page').style.display = 'block';
  document.querySelector('.container').style.display = 'none';
  document.querySelector('.sticky-nav').style.display = 'none';
  document.getElementById('header-meta').textContent = '';
  buildTopVenueChips();
  updateTopAlertStrip();
  buildTopPickupRaces();
  calcTopAIStats();
}

function hideTopPage() {
  document.getElementById('top-page').style.display = 'none';
  document.querySelector('.container').style.display = '';
  document.querySelector('.sticky-nav').style.display = '';
}

// ── ピックアップレース ──
// 以下の条件のいずれかに該当するレースを締め切り順・横スクロールカードで表示する。
//   A/B: 1号艇の基準1着率 or 最終確率が会場平均を下回る → イン否定
//   C/D: 1号艇の基準1着率 or 最終確率が70%以上          → イン鉄板
//   E:   まくりアラート（前艇比 平均ST順0.5以上早い＋展示タイム0.1秒以上早い）
// ※ 発走済みレースは除外、当日データのみ対象
function buildTopPickupRaces() {
  const section  = document.getElementById('top-pickup-section');
  const cardsEl  = document.getElementById('top-pickup-cards');
  if (!section || !cardsEl) return;

  const dataForDate = getDataForDate(null); // 当日のみ
  const pickups = [];

  const SLUG_P = {
    "桐生":"kiryu","戸田":"toda","江戸川":"edogawa","平和島":"heiwajima",
    "多摩川":"tamagawa","浜名湖":"hamanako","蒲郡":"gamagori","常滑":"tokoname",
    "津":"tsu","三国":"mikuni","びわこ":"biwako","住之江":"suminoe",
    "尼崎":"amagasaki","鳴門":"naruto","丸亀":"marugame","児島":"kojima",
    "宮島":"miyajima","徳山":"tokuyama","下関":"shimonoseki","若松":"wakamatsu",
    "芦屋":"ashiya","福岡":"fukuoka","唐津":"karatsu","大村":"omura"
  };

  VENUE_LIST.forEach(venue => {
    const vdata = dataForDate[venue];
    if (!vdata || !vdata.races) return;

    const venueAvg1 = (vdata.inn_data || {}).course_rates?.[1] ?? null;
    const slug      = SLUG_P[venue] || venue;
    const date      = vdata.date || '';

    Object.entries(vdata.races).sort((a,b)=>+a[0]-+b[0]).forEach(([rnoStr, rd]) => {
      if (!rd || !rd.boats || rd.boats.length < 2) return;
      if (isRacePast(rd.time)) return;
      if (rd.boats.some(b => b.dq === 'insufficient')) return;

      const rno   = parseInt(rnoStr);
      const boats = [...rd.boats].sort((a,b)=>a.boat-b.boat);
      const boat1 = boats.find(b => b.boat === 1);
      if (!boat1) return;

      // ── 最終確率 & 基準確率(display_base): DATA/currentVenue を一時差し替えて計算 ──
      // base1: 6艇のprobを正規化した相対1着率（AI予想タブ「基準」列と同一）
      let base1      = null;
      let finalProb1 = null;
      try {
        const arek   = rd.arek ?? 54.7;
        const ranked = calcTenkaiProbs_pickup(boats, arek, venue, vdata);
        const tenjiData = _tenjiCache[tenjiKey(slug, date, rno)] || null;
        let tenjiScoreMap = null;
        if (tenjiData) {
          const _pd = DATA, _pv = currentVenue;
          DATA = vdata; currentVenue = venue;
          try { tenjiScoreMap = calcTenjiScore(ranked, tenjiData, venue, arek); } catch(e){}
          DATA = _pd; currentVenue = _pv;
        }
        const probTotal = ranked.reduce((s,b)=>s+b.prob,0)||1;
        // base1: AI予想「基準」列と同じ正規化確率
        base1 = (ranked.find(b=>b.boat===1)?.prob ?? 0) / probTotal;
        const { wBase, wTenkai, wTenji } = calcDynamicWeights(arek);
        const tenkaiOnlyTotal = ranked.reduce((s,x)=>s+(x.tenkai_score??x.tenkai_prob),0)||1;
        const boatByNo_p = {}; boats.forEach(b=>{ boatByNo_p[b.boat]=b; });
        const tenjiRawMap_p = {};
        if (tenjiData) {
          Object.keys(tenjiData).filter(k=>/^\d+$/.test(k)).forEach(k=>{
            const e=tenjiData[k]; if(e&&typeof e.tenji==='number') tenjiRawMap_p[parseInt(k)]=e.tenji;
          });
        }
        const useMaster = hasMasterExt() && !!(MASTER_EXT.venue_kimari && MASTER_EXT.venue_kimari[venue]);
        ranked.forEach(b=>{
          const baseNorm = b.prob/probTotal;
          const prev     = boatByNo_p[b.boat-1]||null;
          let tenkaiCoef = 1.0;
          if(useMaster && baseNorm>0){
            const tn=(b.tenkai_score??b.tenkai_prob)/tenkaiOnlyTotal;
            tenkaiCoef=Math.min(3.0,Math.max(0.3,tn/baseNorm));
          }
          if(prev){
            const my=MASTER_EXT?.course_master?.[b.name]?.[String(b.boat)]?.st_rank;
            const pr=MASTER_EXT?.course_master?.[prev.name]?.[String(prev.boat)]?.st_rank;
            if(my!=null&&pr!=null) tenkaiCoef=Math.min(3.0,Math.max(0.3,tenkaiCoef+(pr-my)*0.10));
          }
          let tenjiCoef=1.0;
          if(tenjiScoreMap) tenjiCoef=tenjiScoreMap[`__coef_${b.boat}`]??1.0;
          if(prev&&tenjiData){
            const my=tenjiRawMap_p[b.boat]??null, pr=tenjiRawMap_p[prev.boat]??null;
            if(my!=null&&pr!=null) tenjiCoef=Math.min(2.0,Math.max(0.5,tenjiCoef+(pr-my)*0.50));
          }
          const wTenjiC=wTenji*(TENJI_WEIGHT_BY_COURSE[b.boat]??1.0);
          b._multi_score=Math.pow(baseNorm,wBase)*Math.pow(tenkaiCoef,wTenkai)*Math.pow(tenjiCoef,wTenjiC);
        });
        const multiTotal=ranked.reduce((s,b)=>s+b._multi_score,0)||1;
        ranked.forEach(b=>{ b.final_prob=b._multi_score/multiTotal; });
        finalProb1=ranked.find(b=>b.boat===1)?.final_prob??null;
      } catch(e) { finalProb1 = null; }

      // ── まくりアラート ──
      const makuriBoats = [];
      const tenjiDataForRace = _tenjiCache[tenjiKey(slug, date, rno)] || null;
      for (let bn = 2; bn <= 6; bn++) {
        const thisB = boats.find(b=>b.boat===bn);
        const prevB = boats.find(b=>b.boat===bn-1);
        if (!thisB||!prevB) continue;
        const myStR  = MASTER_EXT?.course_master?.[thisB.name]?.[String(bn)]?.st_rank ?? null;
        const prStR  = MASTER_EXT?.course_master?.[prevB.name]?.[String(bn-1)]?.st_rank ?? null;
        const stOk   = (myStR!=null&&prStR!=null) ? (prStR-myStR>=0.5) : false;
        let tenjiOk  = false;
        if (tenjiDataForRace) {
          const myT=tenjiDataForRace[String(bn)]?.tenji??null;
          const prT=tenjiDataForRace[String(bn-1)]?.tenji??null;
          if(myT!=null&&prT!=null) tenjiOk=(prT-myT>=0.1);
        }
        if(stOk&&tenjiOk) makuriBoats.push(bn);
      }

      // ── タグ構築 ──
      const tags = [];
      const avgStr = venueAvg1!=null ? `${(venueAvg1*100).toFixed(1)}%` : null;

      // イン否定（基準 or 最終が場平均以下）
      const belowBase  = base1!=null && venueAvg1!=null && base1 < venueAvg1;
      const belowFinal = finalProb1!=null && venueAvg1!=null && finalProb1 < venueAvg1;
      if (belowBase || belowFinal) {
        const subParts = [];
        if (belowBase)  subParts.push(`基準 ${(base1*100).toFixed(1)}%`);
        if (belowFinal) subParts.push(`最終 ${(finalProb1*100).toFixed(1)}%`);
        if (avgStr) subParts.push(`場平均 ${avgStr}`);
        tags.push({ type:'in_neg', label:'イン否定', sub: subParts.join(' ／ '), color:'var(--orange)' });
      }

      // イン鉄板（基準 or 最終が70%以上）
      const strongBase  = base1!=null && base1>=0.70;
      const strongFinal = finalProb1!=null && finalProb1>=0.70;
      if (strongBase || strongFinal) {
        const subParts = [];
        if (strongBase)  subParts.push(`基準 ${(base1*100).toFixed(1)}%`);
        if (strongFinal) subParts.push(`最終 ${(finalProb1*100).toFixed(1)}%`);
        tags.push({ type:'in_tetsup', label:'イン鉄板', sub: subParts.join(' ／ '), color:'var(--accent2)' });
      }

      // まくりアラート
      if (makuriBoats.length > 0) {
        tags.push({ type:'makuri', label:`まくりアラート(${makuriBoats.join('・')}号艇)`, sub:'', color:'#e60012' });
      }

      if (tags.length === 0) return;

      // 締め切り時刻を分単位に変換（ソート用）
      let timeMin = 9999;
      if (rd.time && /^\d{1,2}:\d{2}$/.test(rd.time.trim())) {
        const [h,m] = rd.time.trim().split(':').map(Number);
        timeMin = h*60+m;
      }

      pickups.push({ venue, rno, time: rd.time||'', timeMin, tags });
    });
  });

  // 締め切り順（同時刻は会場名順）
  pickups.sort((a,b) => a.timeMin!==b.timeMin ? a.timeMin-b.timeMin : a.venue.localeCompare(b.venue,'ja'));

  if (pickups.length === 0) {
    section.style.display = 'none';
    return;
  }

  section.style.display = 'block';

  cardsEl.innerHTML = pickups.map(p => {
    // タグバッジ（ラベルのみ）
    const badgesHtml = p.tags.map(t =>
      `<div style="
        font-size:10px;font-weight:700;letter-spacing:.03em;
        background:${t.color}22;color:${t.color};
        border:1px solid ${t.color}55;
        border-radius:4px;padding:2px 6px;
        white-space:nowrap;line-height:1.4;
        text-align:center;
      ">${t.label}</div>`
    ).join('');

    return `
      <div onclick="jumpToPickup('${p.venue}',${p.rno})"
           style="
             flex:0 0 auto;
             min-width:90px;max-width:110px;
             box-sizing:border-box;
             background:var(--bg2);border:1px solid var(--border);
             border-radius:var(--radius-sm);
             padding:8px 10px;
             cursor:pointer;transition:background 0.15s;
             display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px;
           "
           onmouseover="this.style.background='var(--bg3)'"
           onmouseout="this.style.background='var(--bg2)'">
        <div style="font-size:10px;color:var(--text3);letter-spacing:.04em;white-space:nowrap">${p.time} 発走</div>
        <div style="white-space:nowrap">
          <span style="font-size:15px;font-weight:700;color:var(--text)">${p.venue}</span>
          <span style="font-size:13px;font-weight:700;color:var(--accent2);margin-left:3px">${p.rno}R</span>
        </div>
        <div style="display:flex;flex-direction:column;align-items:center;gap:3px;width:100%">
          ${badgesHtml}
        </div>
      </div>`;
  }).join('');
}

// calcTenkaiProbs の pickup 専用ラッパー（DATA/currentVenue を一時差し替え）
function calcTenkaiProbs_pickup(boats, arek, venue, vdata) {
  const _prevData = DATA; const _prevVenue = currentVenue;
  DATA = vdata; currentVenue = venue;
  let result;
  try { result = calcTenkaiProbs(boats, arek); } catch(e) { result = [...boats].map(b=>({...b,tenkai_prob:b.prob,tenkai_score:b.prob})); }
  DATA = _prevData; currentVenue = _prevVenue;
  return result;
}

// ピックアップカードから直接レースへジャンプ
function jumpToPickup(venue, rno) {
  const dataForDate = getDataForDate(null);
  const vdata = dataForDate[venue];
  if (!vdata) return;
  hideTopPage();
  currentVenue = venue;
  DATA = vdata;
  buildVenueTabs();
  buildRaceBar();
  updateDateNav();
  selectedRace = rno;
  document.querySelectorAll('.race-btn').forEach(c=>c.classList.remove('active'));
  const btn = document.getElementById(`rc-${rno}`);
  if(btn){ btn.classList.add('active'); btn.scrollIntoView({behavior:'auto',block:'nearest',inline:'center'}); }
  document.getElementById('header-meta').innerHTML = `<strong>${venue}</strong> — ${vdata.date||''}`;
  switchTab('detail');
  renderDetail(rno);
}

function isVenueFinished(vdata) {
  if (!vdata || !vdata.races) return false;
  const entries = Object.values(vdata.races);
  if (entries.length === 0) return false;
  return entries.every(rd => isRacePast(rd.time));
}

function buildTopVenueChips() {
  const area = document.getElementById('top-venue-chips');
  if (!area) return;
  const dataForDate = getDataForDate(viewDate);
  const venues = VENUE_LIST.filter(v => dataForDate && dataForDate[v] != null);

  // 日付ラベルを更新
  const dates = getAvailableDates();
  const todayDate = dates[dates.length - 1];
  const currentDate = viewDate || todayDate;
  const labelEl = document.getElementById('top-venue-date-label');
  if (labelEl) {
    // YYYY-MM-DD → YYYY/MM/DD
    const displayDate = currentDate ? currentDate.replace(/-/g, '/') : '';
    const isToday = currentDate === todayDate;
    labelEl.textContent = `🏟 ${isToday ? '本日' : displayDate}の開催場`;
  }

  // トップページの日付ナビゲーターを更新
  const topNav = document.getElementById('top-date-nav');
  if (topNav) {
    if (dates.length <= 1) {
      topNav.style.display = 'none';
    } else {
      topNav.style.display = 'flex';
      const idx = dates.indexOf(currentDate);
      document.getElementById('top-date-nav-label').textContent = currentDate;
      document.getElementById('top-date-prev').disabled = idx <= 0;
      document.getElementById('top-date-next').disabled = idx >= dates.length - 1;
    }
  }

  if (venues.length === 0) {
    area.innerHTML = '<span style="color:var(--text3);font-size:12px">この日の開催情報なし</span>';
    return;
  }
  const gradeClass = { SG: 'cg-sg', G1: 'cg-g1', G2: 'cg-g2', G3: 'cg-g3' };
  area.innerHTML = venues.map(v => {
    const finished = isVenueFinished(dataForDate[v]);
    const style = finished
      ? 'opacity:0.4;filter:grayscale(0.6);'
      : '';
    // 当日はRACE_INDEX_DATA、過去日はhistoryデータのrace_infoを使用
    const _dates2 = getAvailableDates();
    const _todayDate2 = _dates2[_dates2.length - 1];
    const _isToday2 = (viewDate || _todayDate2) === _todayDate2;
    const info = _isToday2
      ? ((RACE_INDEX_DATA && RACE_INDEX_DATA.venues) ? (RACE_INDEX_DATA.venues[v] || null) : null)
      : (dataForDate[v] ? (dataForDate[v].race_info || null) : null);
    const grade      = info ? (info.grade || '') : '';
    const isJoshi    = !!(info && info.is_joshi);
    const day        = info ? (info.day || '') : '';
    const totalDays  = info ? (info.total_days ?? null) : null;

    // ── バッジ構築 ──
    // グレードバッジ（G1/G2/G3/SG）
    const gcls = gradeClass[grade] || '';
    const gradeBadge = gcls
      ? `<span class="chip-grade ${gcls}">${grade}</span>`
      : '';
    // 女子バッジ
    const joshiBadge = isJoshi
      ? `<span class="chip-grade cg-joshi">女子</span>`
      : '';
    // 一般バッジ（グレードなし・女子なし の場合のみ）
    const ippanBadge = (!gcls && !isJoshi)
      ? `<span class="chip-grade cg-ippan">一般</span>`
      : '';

    const badgesHtml  = `<span class="chip-badges">${gradeBadge}${joshiBadge}${ippanBadge}</span>`;
    const nameHtml    = `<span class="chip-name">${v}</span>`;
    const totalStr    = totalDays ? `${totalDays}日間開催` : '';
    const dayHtml     = (day || totalStr)
      ? `<span class="chip-day" style="display:block;text-align:center;font-size:10px;color:var(--text3);line-height:1.6;margin-top:1px">${[day, totalStr].filter(Boolean).join('<br>')}</span>`
      : '';

    return `<span class="top-venue-chip" onclick="jumpToVenueForDate('${v}')" style="${style}">${badgesHtml}${nameHtml}${dayHtml}</span>`;
  }).join('');
}

// トップページ用の日付シフト
function topShiftDate(delta) {
  const dates = getAvailableDates();
  const todayDate = dates[dates.length - 1];
  const current = viewDate || todayDate;
  const idx = dates.indexOf(current);
  const newIdx = idx + delta;
  if (newIdx < 0 || newIdx >= dates.length) return;
  viewDate = dates[newIdx];
  buildTopVenueChips();
  updateTopAlertStrip();
  buildTopPickupRaces();
  calcTopAIStats();
}

// トップページから日付を考慮して会場へジャンプ
function jumpToVenueForDate(venue) {
  const dataForDate = getDataForDate(viewDate);
  if (!dataForDate[venue]) return;
  hideTopPage();
  currentVenue = venue;
  DATA = dataForDate[venue];
  buildVenueTabs();
  buildRaceBar();
  updateDateNav();
  if (DATA && DATA.races && Object.keys(DATA.races).length > 0) {
    const targetRace = findCurrentRace(DATA.races);
    selectedRace = targetRace;
    document.querySelectorAll('.race-btn').forEach(c => c.classList.remove('active'));
    const btn = document.getElementById(`rc-${targetRace}`);
    if (btn) { btn.classList.add('active'); btn.scrollIntoView({behavior:'auto',block:'nearest',inline:'center'}); }
    document.getElementById('header-meta').innerHTML = `<strong>${venue}</strong> — ${DATA.date||''}`;
    switchTab('detail');
    renderDetail(targetRace);
  }
}

function updateTopAlertStrip(){
  const strip   = document.getElementById('top-alert-strip');
  const cardsEl = document.getElementById('top-alert-cards');
  const dotEl   = document.getElementById('top-alert-dot');
  if(!strip || !cardsEl) return;

  const now    = new Date();
  const nowMin = now.getHours() * 60 + now.getMinutes();
  const LIMIT  = 15;

  const hits = [];
  const dataForDate = getDataForDate(viewDate);

  VENUE_LIST.forEach(venue => {
    const vdata = dataForDate[venue];
    if(!vdata || !vdata.races) return;
    Object.entries(vdata.races).forEach(([rno, rd]) => {
      if(!rd || !rd.time) return;
      const t = String(rd.time).trim();
      const match = t.match(/^(\d{1,2}):(\d{2})$/);
      if(!match) return;
      const raceMin = parseInt(match[1]) * 60 + parseInt(match[2]);
      const diff = raceMin - nowMin;
      if(diff >= 0 && diff <= LIMIT){
        hits.push({ venue, rno: parseInt(rno), time: t, diff });
      }
    });
  });

  hits.sort((a, b) => a.diff - b.diff);

  if(hits.length === 0){
    strip.style.display = 'none';
    return;
  }

  const hasUrgent = hits.some(h => h.diff <= 5);
  if(dotEl) dotEl.className = 'alert-dot' + (hasUrgent ? ' urgent' : '');

  strip.style.display = 'block';
  cardsEl.innerHTML = hits.map(h => {
    const urgent = h.diff <= 5;
    const dotCls = urgent ? 'alert-dot urgent' : 'alert-dot';
    const label  = h.diff <= 0 ? '発走直前' : `残り ${h.diff}分`;
    return `<div class="alert-card${urgent?' urgent':''}" onclick="jumpToAlert('${h.venue}',${h.rno})">
      <div class="alert-card-badge"><span class="${dotCls}"></span>${label}</div>
      <div class="alert-card-venue">${h.venue}</div>
      <div class="alert-card-race">${h.rno}R</div>
      <div class="alert-card-time">${h.time} 発走</div>
    </div>`;
  }).join('');
}

function jumpToVenue(venue) {
  if (!ALL_DATA[venue]) return;
  hideTopPage();
  currentVenue = venue;
  DATA = ALL_DATA[venue];
  buildVenueTabs();
  buildRaceBar();
  updateDateNav();
  if (DATA && DATA.races && Object.keys(DATA.races).length > 0) {
    // 次の締め切りに近いレース（未来の最初）を選択。全部終了なら最終レース
    const targetRace = findCurrentRace(DATA.races);
    selectedRace = targetRace;
    document.querySelectorAll('.race-btn').forEach(c => c.classList.remove('active'));
    const btn = document.getElementById(`rc-${targetRace}`);
    if (btn) { btn.classList.add('active'); btn.scrollIntoView({behavior:'auto',block:'nearest',inline:'center'}); }
    document.getElementById('header-meta').innerHTML = `<strong>${venue}</strong> — ${DATA.date||''}`;
    // detail タブをアクティブ化して出走表を表示
    switchTab('detail');
    renderDetail(targetRace);
  }
}

function goToRaceList(tab) {
  hideTopPage();
  // 会場が未選択ならそのままメイン画面へ（venue tabs が表示される）
  if (tab && currentVenue && DATA) {
    switchTab(tab);
  } else if (tab) {
    // 会場選択後にタブを切り替えるよう要求を記憶
    sessionStorage.setItem('pending_tab', tab);
  }
}

// ── 現在表示中のタブ・レースを再レンダリング（水面気象・展示・モーター情報の自動更新）──
function autoRefreshCurrentView(){
  if(!DATA || !selectedRace) return;
  const tab = currentTabName();
  // スナップショット（非同期完了前に selectedRace / DATA が変わっても旧値で描画しない）
  const snapRace  = selectedRace;
  const snapData  = DATA;
  const snapVenue = currentVenue;
  try {
    if(tab === 'detail'){
      renderDetail(snapRace);
    } else if(tab === 'buy'){
      renderBuy(snapRace);
    } else if(tab === 'detail2'){
      renderBuy(snapRace);
    } else if(tab === 'comment'){
      if(IS_SERVER && snapData.date){
        // Promise チェーンのエラーも必ず catch する
        fetchTenjiAll(snapVenue, snapData.date)
          .then(() => {
            if(selectedRace === snapRace && DATA === snapData) renderComment(snapRace);
          })
          .catch(e => console.warn('[autoRefresh] fetchTenjiAll error:', e));
      } else {
        renderComment(snapRace);
      }
    } else if(tab === 'result'){
      renderResult(snapRace);
    } else if(tab === 'odds'){
      renderOdds(snapRace);
    }
    // 進入変更バナーも更新（odds タブ含む全タブ共通）
    updatePersistentBanners(snapRace);
  } catch(e) {
    console.warn('[autoRefresh] error:', e);
  }
}
// ══════════════════════════════════════════════════════
//  展開シミュモーダル v2
//  prob × コース有利 × 平均ST補正 × 展示タイム補正
// ══════════════════════════════════════════════════════
const COURSE_ADV_SIM = [1.0, 0.72, 0.58, 0.45, 0.38, 0.30];

function simBoatColor(n){
  return ['','#cc0000','#111111','#cc6600','#0055cc','#999900','#009944'][n] || '#888';
}

// 平均ST順位 → 補正係数（1位=早い=高係数）
function getStCoef(boatName, courseNo){
  const stRank = MASTER_EXT?.course_master?.[boatName]?.[String(courseNo)]?.st_rank;
  if(stRank == null) return 1.0;
  const table = {1:1.15, 2:1.07, 3:1.0, 4:0.93, 5:0.87, 6:0.82};
  return table[Math.round(stRank)] ?? Math.max(0.75, 1.0 - (stRank - 3) * 0.07);
}

// 展示タイム補正係数を取得（既存calcTenjiScoreの__coef_Nを流用）
function getTenjiCoefs(boats, rno){
  const SLUG = {
    "桐生":"kiryu","戸田":"toda","江戸川":"edogawa","平和島":"heiwajima",
    "多摩川":"tamagawa","浜名湖":"hamanako","蒲郡":"gamagori","常滑":"tokoname",
    "津":"tsu","三国":"mikuni","びわこ":"biwako","住之江":"suminoe",
    "尼崎":"amagasaki","鳴門":"naruto","丸亀":"marugame","児島":"kojima",
    "宮島":"miyajima","徳山":"tokuyama","下関":"shimonoseki","若松":"wakamatsu",
    "芦屋":"ashiya","福岡":"fukuoka","唐津":"karatsu","大村":"omura"
  };
  const slug     = SLUG[DATA.venue] || DATA.venue || '';
  const key      = tenjiKey(slug, DATA.date, rno);
  const tenjiData = _tenjiCache[key];
  if(!tenjiData) return null;
  const arek = DATA.races[String(rno)]?.arek ?? 54.7;
  return calcTenjiScore(boats, tenjiData, DATA.venue, arek);
}

function openSimModal(rno){
  const rd = DATA && DATA.races && DATA.races[String(rno)];
  if(!rd || !rd.boats) return;
  const boats = [...rd.boats].sort((a,b) => a.boat - b.boat);
  document.getElementById('sim-modal-overlay').classList.add('open');
  document.body.style.overflow = 'hidden';
  renderSimModal(boats, rno);
}

function closeSimModal(){
  document.getElementById('sim-modal-overlay').classList.remove('open');
  document.body.style.overflow = '';
}

function renderSimModal(boats, rno){
  const modal = document.getElementById('sim-modal');
  modal.querySelector('#sim-modal-header h3').textContent =
    `⚡ 展開シミュ — ${DATA.venue||''} ${rno}R`;

  const tenjiCoefs = getTenjiCoefs(boats, rno);
  const hasTenji   = !!tenjiCoefs;

  // 艇ごとのST・展示係数を事前計算
  const boatMeta = boats.map((b, i) => ({
    stCoef:    getStCoef(b.name, b.boat),
    tenjiCoef: hasTenji ? (tenjiCoefs[`__coef_${b.boat}`] ?? 1.0) : 1.0,
    hasTenji,
  }));

  const scenarios = runSimScenarios(boats, rno, tenjiCoefs);
  drawSimCanvas(document.getElementById('sim-canvas'), boats, scenarios[0], boatMeta);

  // 凡例（ST早/遅・展示上下バッジ付き）
  document.getElementById('sim-legend').innerHTML = boats.map((b, i) => {
    const { stCoef, tenjiCoef, hasTenji } = boatMeta[i];
    const stBadge  = stCoef  >= 1.08 ? '⚡ST早' : stCoef  <= 0.88 ? '🐢ST遅' : '';
    const tjBadge  = hasTenji
      ? (tenjiCoef >= 1.08 ? '🔥展示↑' : tenjiCoef <= 0.92 ? '❄展示↓' : '') : '';
    const badges   = [stBadge, tjBadge].filter(Boolean).join(' ');
    return `<div class="sim-legend-item" style="align-items:baseline">
      <div class="sim-legend-dot" style="background:${simBoatColor(b.boat)};margin-top:3px;flex-shrink:0"></div>
      <span>${b.boat}号 ${b.name}${badges
        ? `<span style="font-size:10px;color:#0055cc;margin-left:4px">${badges}</span>`
        : ''}</span>
    </div>`;
  }).join('');

  // 展示データ有無バッジ
  document.getElementById('sim-data-badge').innerHTML = hasTenji
    ? `<span style="font-size:10px;padding:1px 6px;border-radius:4px;background:rgba(0,102,255,.1);color:#0066ff">展示込み</span>`
    : `<span style="font-size:10px;padding:1px 6px;border-radius:4px;background:rgba(120,120,120,.1);color:#888">展示なし</span>`;

  // 展開パターンTOP5
  document.getElementById('sim-patterns-list').innerHTML = scenarios.map((sc, ri) => {
    const first  = sc.order[0] + 1;
    const badges = sc.order.map(idx => {
      const n = idx + 1;
      return `<span class="boat-circle b${n}" style="width:20px;height:20px;font-size:10px;line-height:20px;display:inline-flex;align-items:center;justify-content:center">${n}</span>`;
    }).join(`<span style="color:#bbb;font-size:10px;margin:0 1px">-</span>`);
    return `<div class="sim-pat-row" style="border-left-color:${simBoatColor(first)}">
      <span class="sim-pat-no">${ri + 1}</span>
      <span class="sim-pat-boats">${badges}</span>
      <span class="sim-pat-desc">${simDesc(sc.order, boats, sc.reason)}</span>
      <span class="sim-pat-prob">${sc.prob}%</span>
    </div>`;
  }).join('');

  document.getElementById('sim-resim-btn').onclick = () => renderSimModal(boats, rno);
}

function simDesc(order, boats, reason){
  const n    = order[0] + 1;
  const name = (boats[order[0]] || {}).name || '';
  const tag  = reason
    ? `<span style="font-size:10px;color:#888;margin-left:4px">${reason}</span>` : '';
  if(n === 1) return `①${name}が逃げ切り。${tag}`;
  if(n === 2) return `②${name}が①を差してリード奪取。${tag}`;
  return `${n}号艇${name}がまくりで主導権。${tag}`;
}

// スコア計算: prob × コース有利 × ST補正 × 展示補正
function runSimScenarios(boats, rno, tenjiCoefs){
  const hasTenji = !!tenjiCoefs;

  // ── 展示タイム生データを取得（シミュ用） ──
  const tenjiRawSim = {};
  if(hasTenji){
    const SLUG_SIM = {
      "桐生":"kiryu","戸田":"toda","江戸川":"edogawa","平和島":"heiwajima",
      "多摩川":"tamagawa","浜名湖":"hamanako","蒲郡":"gamagori","常滑":"tokoname",
      "津":"tsu","三国":"mikuni","びわこ":"biwako","住之江":"suminoe",
      "尼崎":"amagasaki","鳴門":"naruto","丸亀":"marugame","児島":"kojima",
      "宮島":"miyajima","徳山":"tokuyama","下関":"shimonoseki","若松":"wakamatsu",
      "芦屋":"ashiya","福岡":"fukuoka","唐津":"karatsu","大村":"omura"
    };
    const slugSim = SLUG_SIM[DATA?.venue] || DATA?.venue || '';
    const tk = tenjiKey(slugSim, DATA?.date, rno);
    const td = _tenjiCache[tk];
    if(td){
      Object.keys(td).filter(k => /^\d+$/.test(k)).forEach(k => {
        if(typeof td[k]?.tenji === 'number') tenjiRawSim[parseInt(k)] = td[k].tenji;
      });
    }
  }

  // ── 艇番マップ（1つ前コース参照用） ──
  const boatMapSim = {};
  boats.forEach(b => { boatMapSim[b.boat] = b; });

  const baseScores = boats.map((b, i) => {
    const p         = typeof b.prob === 'number' ? b.prob : 1/6;
    const courseAdv = COURSE_ADV_SIM[i] ?? 0.25;
    const stCoef    = getStCoef(b.name, b.boat);
    const tjCoef    = hasTenji
      ? Math.min(1.35, Math.max(0.75, tenjiCoefs[`__coef_${b.boat}`] ?? 1.0)) : 1.0;
    return p * courseAdv * stCoef * tjCoef;
  });

  // ── STオフセット: スコアベース + 隣艇相対差補正 ──
  // 基本: スコアが高い艇ほどスタートが前（Xが小さい）
  const maxScore  = Math.max(...baseScores);
  const stOffsets = baseScores.map((s, i) => {
    let offset = (1 - s / maxScore) * 0.22;

    const b        = boats[i];
    const prevBoat = boatMapSim[b.boat - 1] ?? null;
    if(prevBoat){
      // ST順位差補正: 0.5位早い(差=-0.5)ごとに半艇身前(offset -0.025)
      const myStRank   = MASTER_EXT?.course_master?.[b.name]?.[String(b.boat)]?.st_rank;
      const prevStRank = MASTER_EXT?.course_master?.[prevBoat.name]?.[String(prevBoat.boat)]?.st_rank;
      if(myStRank != null && prevStRank != null){
        // prevStRank - myStRank > 0 → 自艇が早い → offsetを縮める（前に出る）
        const stAdj = (prevStRank - myStRank) * 0.05;  // 0.5位差→−0.025
        offset = Math.max(0, offset - stAdj);
      }
      // 展示タイム差補正: 枠番別強度で前コース艇との差を反映
      // 3〜5枠は差し・まくりの爆発力に直結するため強めに補正
      if(hasTenji){
        const myTenji   = tenjiRawSim[b.boat]        ?? null;
        const prevTenji = tenjiRawSim[prevBoat.boat] ?? null;
        if(myTenji != null && prevTenji != null){
          // prevTenji - myTenji > 0 → 自艇が速い → offsetを縮める（前に出る）
          const SIM_TENJI_MULT = { 1:0.15, 2:0.20, 3:0.35, 4:0.40, 5:0.35, 6:0.25 };
          const mult     = SIM_TENJI_MULT[b.boat] ?? 0.25;
          const tenjiAdj = (prevTenji - myTenji) * mult;
          offset = Math.max(0, offset - tenjiAdj);
        }
      }
    }
    return offset;
  });

  const buckets = {};
  for(let s = 0; s < 300; s++){
    const scores = baseScores.map(base => base + (Math.random() * 0.05 - 0.025));
    const order  = boats.map((_, i) => ({i, score: scores[i]}))
      .sort((a, b) => b.score - a.score).map(x => x.i);
    const key = order.join('-');
    buckets[key] ? buckets[key].count++ : (buckets[key] = {order, count:1, stOffsets});
  }

  return Object.values(buckets).sort((a, b) => b.count - a.count).slice(0, 5)
    .map(sc => {
      const b0   = boats[sc.order[0]];
      const fi   = sc.order[0];
      const stC  = getStCoef(b0.name, b0.boat);
      const tjC  = hasTenji ? (tenjiCoefs[`__coef_${b0.boat}`] ?? 1.0) : null;
      let reason = '';
      if(fi === 0 && stC >= 1.08)        reason = 'ST◎';
      else if(fi === 0 && tjC >= 1.08)   reason = '展示◎';
      else if(fi !== 0 && stC >= 1.08)   reason = 'ST差し';
      else if(fi !== 0 && tjC >= 1.08)   reason = '展示優位';
      return { ...sc, prob: (sc.count / 300 * 100).toFixed(1), reason };
    });
}

// キャンバス描画
function drawSimCanvas(canvas, boats, scenario, boatMeta){
  const W = canvas.parentElement.clientWidth || 340;
  const H = Math.round(W * 0.52);
  canvas.width = W; canvas.height = H;
  const ctx = canvas.getContext('2d');

  // 背景
  const bg = ctx.createLinearGradient(0, 0, 0, H);
  bg.addColorStop(0, '#060f1e'); bg.addColorStop(1, '#0d2a4a');
  ctx.fillStyle = bg; ctx.fillRect(0, 0, W, H);
  ctx.strokeStyle = 'rgba(0,180,255,0.06)'; ctx.lineWidth = 1;
  for(let y = 0; y < H; y += 20){
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke();
  }

  const PL=52, PR=72, PT=36, PB=42;
  const TW = W-PL-PR, TH = H-PT-PB, laneH = TH/6;

  // レーンライン
  for(let i = 0; i <= 6; i++){
    const y = PT + i * laneH;
    ctx.strokeStyle = i===0||i===6 ? 'rgba(0,212,255,0.4)' : 'rgba(0,212,255,0.1)';
    ctx.lineWidth   = i===0||i===6 ? 1.5 : 0.7;
    ctx.setLineDash([]);
    ctx.beginPath(); ctx.moveTo(PL, y); ctx.lineTo(W-PR, y); ctx.stroke();
  }

  // スタートライン
  ctx.strokeStyle = 'rgba(255,220,50,0.65)'; ctx.lineWidth = 1.5; ctx.setLineDash([5,4]);
  ctx.beginPath(); ctx.moveTo(PL, PT); ctx.lineTo(PL, H-PB); ctx.stroke();
  ctx.setLineDash([]);
  ctx.fillStyle = 'rgba(255,220,50,0.7)';
  ctx.font = `bold ${Math.max(9, Math.round(W*0.011))}px sans-serif`;
  ctx.textAlign = 'center'; ctx.fillText('START', PL, PT-6);

  // 1マーク
  ctx.strokeStyle = 'rgba(255,100,0,0.7)'; ctx.lineWidth = 1.5;
  ctx.beginPath(); ctx.moveTo(W-PR, PT); ctx.lineTo(W-PR, H-PB); ctx.stroke();
  ctx.fillStyle = 'rgba(255,100,0,0.7)';
  ctx.font = `bold ${Math.max(9, Math.round(W*0.011))}px sans-serif`;
  ctx.textAlign = 'center'; ctx.fillText('1M', W-PR, PT-6);

  const order     = scenario.order;
  const stOffsets = scenario.stOffsets || boats.map(() => 0.1);

  boats.forEach((boat, idx) => {
    const laneY  = PT + (idx + 0.5) * laneH;
    const rank   = order.indexOf(idx);
    const finalY = PT + (rank + 0.5) * laneH;
    const color  = simBoatColor(boat.boat);
    const startX = PL + stOffsets[idx] * TW;

    // 軌跡
    ctx.beginPath(); ctx.moveTo(startX, laneY);
    ctx.bezierCurveTo(startX + TW*0.38, laneY, W-PR - TW*0.18, finalY, W-PR, finalY);
    ctx.strokeStyle  = color;
    ctx.lineWidth    = rank === 0 ? 3 : 1.8;
    ctx.globalAlpha  = rank === 0 ? 0.95 : 0.72;
    ctx.stroke(); ctx.globalAlpha = 1;

    // 艇番マーク
    const r = Math.max(7, Math.round(W * 0.014));
    ctx.beginPath(); ctx.arc(startX, laneY, r, 0, Math.PI*2);
    ctx.fillStyle = color; ctx.fill();
    ctx.strokeStyle = '#fff'; ctx.lineWidth = 1; ctx.stroke();
    ctx.fillStyle = '#fff';
    ctx.font = `bold ${Math.round(r * 1.05)}px sans-serif`;
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillText(boat.boat, startX, laneY);
    ctx.textBaseline = 'alphabetic';

    // ST早/遅アイコン
    if(boatMeta){
      const stC = boatMeta[idx]?.stCoef ?? 1.0;
      if(stC >= 1.08 || stC <= 0.88){
        ctx.font = `${Math.max(9, Math.round(W*0.013))}px sans-serif`;
        ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        ctx.fillText(stC >= 1.08 ? '⚡' : '🐢', startX, laneY - r - 6);
        ctx.textBaseline = 'alphabetic';
      }
    }

    // 1マーク着順ラベル
    ctx.fillStyle = color;
    ctx.font = `bold ${Math.max(9, Math.round(W*0.011))}px sans-serif`;
    ctx.textAlign = 'left';
    ctx.fillText(`${rank+1}着`, W-PR+5, finalY+4);
  });

  // コース番号（左端）
  boats.forEach((boat, idx) => {
    const y = PT + (idx + 0.5) * laneH;
    ctx.fillStyle = simBoatColor(boat.boat);
    ctx.font = `bold ${Math.max(10, Math.round(W*0.015))}px sans-serif`;
    ctx.textAlign = 'center';
    ctx.fillText(boat.boat, PL-18, y+4);
  });
}

// ── CSV ダウンロードボタンの onclick を新関数に差し替え ──
// index.html 側のボタン onclick="exportBacktestCSV()" を
// hit/rec 分離版・両方同時版に上書きする。
(function _initCsvButtons() {
  function wire() {
    // data-csv-mode 属性で対象ボタンを特定する（推奨）
    document.querySelectorAll('[data-csv-mode]').forEach(btn => {
      const m = btn.getAttribute('data-csv-mode');
      if (m === 'hit')  btn.onclick = exportBacktestCSV_hit;
      if (m === 'rec')  btn.onclick = exportBacktestCSV_rec;
      if (m === 'both') btn.onclick = exportBacktestCSV_both;
    });

    // data-csv-mode がない場合はボタンのテキストで判定（後方互換）
    document.querySelectorAll('button').forEach(btn => {
      const t = btn.textContent || '';
      if (t.includes('的中重視') && t.includes('CSV') && !btn.getAttribute('data-csv-mode'))
        btn.onclick = exportBacktestCSV_hit;
      if (t.includes('回収重視') && t.includes('CSV') && !btn.getAttribute('data-csv-mode'))
        btn.onclick = exportBacktestCSV_rec;
      if ((t.includes('両方') || t.includes('両方ダウンロード')) && !btn.getAttribute('data-csv-mode'))
        btn.onclick = exportBacktestCSV_both;
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', wire);
  } else {
    wire();
  }
})();

