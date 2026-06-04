// top_stats.js — TOP PAGE AI予想成績（sample.js から分離）
// ── TOP PAGE: AI予想成績計算 ──

// ── DATA / currentVenue セット/リストアヘルパー ──
// sample_obf.js 内の DATA 変数はローカルスコープのため window.DATA では書き換えられない。
// top_stats.js（obf化後も同スコープ）経由でセット/リストアすることで
// computeScenCombosWithEV.js 等の外部スクリプトから DATA を操作できるようにする。
window._setDataForCalc = function(vdata, venue) {
  const saved = { DATA: DATA, venue: currentVenue };
  DATA = Object.assign({}, vdata, { venue: venue });
  currentVenue = venue;
  return saved;
};
window._restoreDataForCalc = function(saved) {
  DATA = saved.DATA;
  currentVenue = saved.venue;
};
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
  _ensureTenjiCache();
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

// 1周タイム欠損チェック（周回短縮判定）
// lap1 が null = 周回短縮レース → 集計除外
// tenjiData が存在しない場合も除外
function hasNoLapTime(rno, vdata) {
  _ensureTenjiCache();
  const venue = vdata.venue;
  const slug = SLUG_MAP[venue] || venue;
  const key = tenjiKey(slug, vdata.date, rno);
  const cached = _tenjiCache[key];
  if (!cached) return true; // 展示データなし → 除外
  const rd = vdata.races[String(rno)];
  if (!rd || !rd.boats) return true;
  // 出走艇全艇の lap1 が正の数値で揃っているか確認
  // lap1: null = 周回短縮（1周タイム未計測）→ 除外
  // tenji（展示タイム）は周回短縮でも計測されるため判定に使わない
  return rd.boats.some(b => {
    const entry = cached[String(b.boat)];
    return !entry || typeof entry.lap1 !== 'number' || entry.lap1 <= 0;
  });
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
    _ensureTenjiCache();
    const rd = vdata.races[String(rno)];
    if (!rd) return [];
    const slug = SLUG_MAP[venue] || venue;
    const tKey = tenjiKey(slug, vdata.date, rno);
    const tenjiData = _tenjiCache[tKey] || null;

    // 一時的に DATA / currentVenue をセットして calcTenkaiProbs 等を利用
    const savedDATA  = DATA;
    const savedVenue = currentVenue;
    // [2026-06-01 修正] vdata は ALL_DATA_HISTORY[date][venue] の値で .venue を持たない。
    // calc3rdScores / calcPlace2Probs が DATA.venue をグローバル参照するため
    // DATA = vdata 前に venue を付与しておく（元の vdata は変更しない）。
    const _vdataWithVenue = (vdata.venue === venue) ? vdata : Object.assign({}, vdata, { venue });
    DATA = _vdataWithVenue;
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
      // ── [2026-05-31 修正] renderBuy と完全同一の加算ボーナス方式 2パス ──
      // 旧: Math.pow 乗算方式（指数重み）→ prob が低い外枠艇への補正が死んでいた
      // 新: baseNorm + tenkaiBonus + tenjiBonus + slitBonus - slitPenalty
      //     スリット補正（slitBonus/slitPenalty）も追加
      // wSlit を calcDynamicWeights から受け取る
      const { wBase: _wBase, wTenkai: _wTenkai, wTenji: _wTenji, wSlit: _wSlit } = calcDynamicWeights(arek);
      const BONUS_BASE_TENKAI_BT = 0.15;
      const BONUS_BASE_TENJI_BT  = 0.15;
      const SLIT_BONUS_BASE_BT   = 0.15;
      const MAKURI_ALERT_BONUS_BT = 0.20;
      const hasTenji_bt = !!tenjiData;

      // 1パス目: 各係数と baseNorm を保存
      ranked.forEach(b => {
        const baseNorm = b.prob / probTotal;
        const prevBoat = boatByNo_bt[b.boat - 1] || null;

        // 展開補正 + ST順位相対差補正
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

        // 展示補正 + 展示タイム相対差補正
        let tenjiCoef = 1.0;
        if (tenjiScoreMap) tenjiCoef = tenjiScoreMap[`__coef_${b.boat}`] ?? 1.0;
        if (prevBoat && hasTenji_bt) {
          const myTenji   = tenjiRawMap_bt[b.boat]        ?? null;
          const prevTenji = tenjiRawMap_bt[prevBoat.boat] ?? null;
          if (myTenji != null && prevTenji != null) {
            tenjiCoef = Math.min(2.0, Math.max(0.5, tenjiCoef + (prevTenji - myTenji) * 0.50));
          }
        }

        // スリット補正（1パス目）
        let slitCoef = 1.0;
        if (prevBoat && hasTenji_bt && _wSlit > 0) {
          const myTenji    = tenjiRawMap_bt[b.boat]          ?? null;
          const prevTenji  = tenjiRawMap_bt[prevBoat.boat]   ?? null;
          const myStRank   = MASTER_EXT?.course_master?.[b.name]?.[String(b.boat)]?.st_rank         ?? null;
          const prevStRank = MASTER_EXT?.course_master?.[prevBoat.name]?.[String(prevBoat.boat)]?.st_rank ?? null;
          let slitDiff = null;
          if (myTenji != null && prevTenji != null && myStRank != null && prevStRank != null) {
            slitDiff = (prevTenji - myTenji) + (prevStRank - myStRank) * 0.02;
          } else if (myTenji != null && prevTenji != null) {
            slitDiff = prevTenji - myTenji;
          } else if (myStRank != null && prevStRank != null) {
            slitDiff = (prevStRank - myStRank) * 0.02;
          }
          if (slitDiff !== null) {
            const found   = SLIT_LAP_THRESHOLDS.find(t => slitDiff >= t.min);
            const rawCoef = found ? found.coef : 1.0;
            slitCoef = 1.0 + (rawCoef - 1.0) * _wSlit;
          }
          // まくりアラートボーナス
          const tenjiAlertDiff = (tenjiRawMap_bt[b.boat] != null && tenjiRawMap_bt[prevBoat.boat] != null)
            ? Math.round((tenjiRawMap_bt[prevBoat.boat] - tenjiRawMap_bt[b.boat]) * 100) / 100 : null;
          const tenjiAlertOk = tenjiAlertDiff != null && tenjiAlertDiff >= 0.10;
          const myStRankA  = MASTER_EXT?.course_master?.[b.name]?.[String(b.boat)]?.st_rank ?? null;
          const preStRankA = MASTER_EXT?.course_master?.[prevBoat.name]?.[String(prevBoat.boat)]?.st_rank ?? null;
          const stAlertOk = myStRankA != null && preStRankA != null && (preStRankA - myStRankA >= 0.5);
          if (tenjiAlertOk && stAlertOk) slitCoef += MAKURI_ALERT_BONUS_BT;
          slitCoef = Math.min(2.0, Math.max(0.5, slitCoef));
        }

        b._baseNorm   = baseNorm;
        b._tenkaiCoef = tenkaiCoef;
        b._tenjiCoef  = tenjiCoef;
        b._slitCoef   = slitCoef;
        b._wTenjiCourse = _wTenji;
      });

      // 2パス目: 加算ボーナス方式 + 後艇スリットペナルティ
      ranked.forEach(b => {
        const nextBoat = boatByNo_bt[b.boat + 1] || null;
        const tenkaiBonus = BONUS_BASE_TENKAI_BT * (b._tenkaiCoef - 1.0) * _wTenkai;
        const tenjiBonus  = BONUS_BASE_TENJI_BT  * (b._tenjiCoef  - 1.0) * b._wTenjiCourse;
        const slitBonus   = SLIT_BONUS_BASE_BT   * (b._slitCoef   - 1.0) * _wSlit;

        let slitPenalty = 0;
        if (nextBoat && hasTenji_bt && _wSlit > 0) {
          const myTenjiN  = tenjiRawMap_bt[b.boat]          ?? null;
          const nextTenji = tenjiRawMap_bt[nextBoat.boat]   ?? null;
          const myStRankN = MASTER_EXT?.course_master?.[b.name]?.[String(b.boat)]?.st_rank              ?? null;
          const nextStRank = MASTER_EXT?.course_master?.[nextBoat.name]?.[String(nextBoat.boat)]?.st_rank ?? null;
          let nextDiff = null;
          if (myTenjiN != null && nextTenji != null && myStRankN != null && nextStRank != null) {
            nextDiff = (myTenjiN - nextTenji) + (myStRankN - nextStRank) * 0.02;
          } else if (myTenjiN != null && nextTenji != null) {
            nextDiff = myTenjiN - nextTenji;
          } else if (myStRankN != null && nextStRank != null) {
            nextDiff = (myStRankN - nextStRank) * 0.02;
          }
          if (nextDiff !== null && nextDiff > 0) {
            const found    = SLIT_LAP_THRESHOLDS.find(t => nextDiff >= t.min);
            const nextCoef = found ? found.coef : 1.0;
            slitPenalty = SLIT_BONUS_BASE_BT * (nextCoef - 1.0) * _wSlit;
          }
          // まくりアラート追加ペナルティ
          const nextTenjiAlertOk = myTenjiN != null && nextTenji != null && (nextTenji - myTenjiN <= -0.10);
          const nxtStRankA = MASTER_EXT?.course_master?.[nextBoat.name]?.[String(nextBoat.boat)]?.st_rank ?? null;
          const myStRankA2 = MASTER_EXT?.course_master?.[b.name]?.[String(b.boat)]?.st_rank ?? null;
          const nextStAlertOk = myStRankA2 != null && nxtStRankA != null && (nxtStRankA - myStRankA2 <= -0.5);
          if (nextTenjiAlertOk && nextStAlertOk) slitPenalty += SLIT_BONUS_BASE_BT * 0.20 * _wSlit;
        }

        b._multi_score = Math.max(0.001,
          b._baseNorm + tenkaiBonus + tenjiBonus + slitBonus - slitPenalty
        );
      });

      const multiTotal = ranked.reduce((s, b) => s + b._multi_score, 0) || 1;
      ranked.forEach(b => { b.final_prob = b._multi_score / multiTotal; });
      ranked.sort((a, b) => b.final_prob - a.final_prob);

      // place2
      const place2Map = calcPlace2Probs(rawBoats, ranked);
      const ranked2 = ranked.map(b => ({ ...b, place2_prob: place2Map[b.boat] || 0 }));

      // シナリオ計算（venueOverride を明示渡し: DATA.venue が正しくセットされていても二重保険）
      const sd = calcScenarioData(ranked2, rawBoats, tenjiScoreMap, venue, _vdataWithVenue);

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

      if (sd.valid) {
        const { scenarioProb, scenarioPlace2, kimariTypes, merged3rdMap } = sd;

        // pick3rd_local: merged3rdMap を直参照（renderBuy と完全同一）
        const R3_MIN_THRESHOLD_BT = 0.03;
        function pick3rd_local(winnerBoat, kimari, secondBoat, buyMode) {
          const p3Target = (buyMode === 'hit') ? 0.80 : 0.70;
          const thirdAll = merged3rdMap[winnerBoat]?.[secondBoat] || [];
          if(thirdAll.length === 0) return [];
          const scoreTotal = thirdAll.reduce((s, x) => s + x.score, 0) || 1;
          const picked = []; let cum = 0;
          for(const x of thirdAll){
            if(x.r3 != null && x.r3 < R3_MIN_THRESHOLD_BT) continue;
            picked.push(x.boat);
            cum += x.score / scoreTotal;
            if(cum >= p3Target) break;
          }
          return picked;
        }
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
          const p2Target = (buyMode === 'hit') ? 0.65 : 0.70;
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
          // rec: 1号艇 final_prob が場平均以下のとき穴軸展開（renderBuy と統一）
          // boat1AboveAvg_bt は上位スコープで定義済み（grep: boat1AboveAvg_bt）
          if(!boat1AboveAvg_bt){
            // 1号艇を除いた ranked2 の上位2艇を軸に展開シナリオを組み立てる
            const top2ExBoat1_bt = ranked2
              .filter(b => b.boat !== 1)
              .slice(0, 2)
              .map(b => b.boat);
            const recScens_bt = allScenPairs.filter(p => top2ExBoat1_bt.includes(p.boat)).slice(0, 4);
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
        const R3_MIN_BT_FB = 0.03;
        function pick3rd_fallback(winnerBoat, kimari, secondBoat, buyMode) {
          const p3Target = (buyMode === 'hit') ? 0.80 : 0.70;
          const thirdAll = calc3rdScores(ranked2, tenjiScoreMap, winnerBoat, kimari, secondBoat);
          if(thirdAll.length === 0) return [];
          const scoreTotal = thirdAll.reduce((s, x) => s + x.score, 0) || 1;
          const picked = []; let cum = 0;
          for(const x of thirdAll){
            if(x.r3 != null && x.r3 < R3_MIN_BT_FB) continue;
            picked.push(x.boat);
            cum += x.score / scoreTotal;
            if(cum >= p3Target) break;
          }
          return picked;
        }
        [[A.boat, P2a.boat], [A.boat, P2b ? P2b.boat : null]].forEach(([first, second]) => {
          if (!second) return;
          pick3rd_fallback(first, null, second, 'hit').forEach(t => {
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

      // rec合成オッズ基準: 4.0倍固定（hit: 2.0倍固定）
      const synthMin_trim   = buyMode === 'rec' ? 4.0 : 2.0;
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

// ══════════════════════════════════════════════════════════════════
// collectResultsForDateScen
//   シナリオ買いの全レース集計を返す。
//
//   includeAll = false（デフォルト）:
//     合成オッズ SCEN_SYNTH_MIN(2.0倍)以上のレースのみ対象
//     → 過去30日成績パネル（synthMin フィルタあり）
//   includeAll = true:
//     合成オッズ不問で全シナリオ買い対象レースを返す
//     → 的中速報（_buildHitSokuhoPanel）の速報カード生成
//
//   hitOdds の単位: 円（例: 28100 = 28100円）
//     ※ collectResultsForDate と同一単位
//     ※ 表示時は r.hitOdds / 100 で倍率、toLocaleString() でそのまま円表示
// ══════════════════════════════════════════════════════════════════
function collectResultsForDateScen(dateStr, includeAll = false) {
  const SCEN_SYNTH_MIN = 2.0;
  const dataForDate = getDataForDate(dateStr);
  const results = [];

  // コンボ正規化（区切り文字を統一）
  // U+FF0D 全角ハイフン、U+2212 MINUS SIGN、U+2013 EN DASH、U+2014 EM DASH、
  // U+2015 HORIZONTAL BAR、U+2010 HYPHEN、U+002D HYPHEN-MINUS すべて半角ハイフンに統一
  function _normC(c) { return (c || '').replace(/[－−–—―‐‑‒\-]/g, '-'); }

  // 合成オッズ計算ヘルパー
  function _calcSynth(comboStrs, oddsMap) {
    if (!comboStrs || comboStrs.length === 0) return null;
    let denom = 0, cnt = 0;
    comboStrs.forEach(c => {
      const ov = oddsMap[_normC(c)] ?? null;
      if (ov != null && ov > 0) { denom += 1 / ov; cnt++; }
    });
    return (cnt > 0 && denom > 0) ? 1 / denom : null;
  }

  VENUE_LIST.forEach(venue => {
    if (venue === '江戸川') return;
    const vdata = dataForDate?.[venue];
    if (!vdata || !vdata.races) return;

    // 既存の collectResultsForDate / resultKey と同一のスラグ解決方法
    const slug   = SLUG_MAP[venue] || venue;
    const dateNd = (vdata.date || '').replace(/-/g, '');

    Object.keys(vdata.races).sort((a, b) => +a - +b).forEach(rnoStr => {
      const rno = parseInt(rnoStr);
      const rd  = vdata.races[rnoStr];
      if (!rd || !rd.boats || rd.boats.length < 2) return;

      // RESULT_DATA が存在しないレースは未確定 → スキップ
      // キー形式は resultKey() と同一: "{slug}_{YYYYMMDD}_{rno}"（アンダースコア区切り）
      const rKey   = `${slug}_${dateNd}_${rno}`;
      const result = RESULT_DATA?.[rKey];
      if (!result || !result.sanrentan || result.sanrentan.length === 0) return;

      // データ不足チェック
      if (hasInsufficient(rd)) return;

      // 進入変更チェック（的中重視・回収重視と同一除外条件）
      if (hasCourseOrderChange(rno, vdata)) return;

      // 周回短縮チェック
      if (hasNoLapTime(rno, vdata)) return;

      // ── シナリオ買い買い目を取得 ──
      let combos = [], hitProbEst = null;
      try {
        if (typeof computeScenCombosWithEV === 'function') {
          const res  = computeScenCombosWithEV(venue, vdata, rno);
          combos     = res?.combos     || [];
          hitProbEst = res?.hitProbEst ?? null;
        } else if (typeof computeScenCombos === 'function') {
          combos = computeScenCombos(venue, vdata, rno);
        }
      } catch(e) {
        console.warn('[collectResultsForDateScen] combos取得エラー', venue, rno, e);
        return;
      }

      if (combos.length === 0) {
        if (typeof window._scenDebugCount === 'undefined') window._scenDebugCount = 0;
        if (window._scenDebugCount < 5) {
          console.warn('[collectResultsForDateScen] combos空', venue, vdata.date, rno,
            'computeScenCombosWithEV定義:', typeof computeScenCombosWithEV);
          window._scenDebugCount++;
        }
        return;
      }

      // combos は {c: "1-2-3"} オブジェクト配列 or 文字列配列の両対応
      const comboStrs = combos.map(c => _normC(typeof c === 'object' ? c.c : c));

      // ── 合成オッズ計算 ──
      // [修正] ODDS_DATA は過去日付分が存在しない。RESULT_DATA.sanrentan をフォールバックに使う。
      const raceOdds3t_live = ODDS_DATA?.[vdata.date]?.[venue]?.[String(rno)]?.['3t'] || {};
      const raceOdds3t_result = (() => {
        const map = {};
        (result?.sanrentan || []).forEach(s => {
          if (s?.combo && s?.odds != null && s.odds > 0) {
            map[_normC(s.combo)] = s.odds >= 100 ? s.odds / 100 : s.odds;
          }
        });
        return map;
      })();
      const raceOdds3t = Object.keys(raceOdds3t_live).length > 0 ? raceOdds3t_live : raceOdds3t_result;
      const synth = _calcSynth(comboStrs, raceOdds3t);

      if (synth == null) {
        if (typeof window._scenSynthDebugCount === 'undefined') window._scenSynthDebugCount = 0;
        if (window._scenSynthDebugCount < 5) {
          console.warn('[collectResultsForDateScen] synth=null', venue, vdata.date, rno,
            'liveKeys:', Object.keys(raceOdds3t_live).length,
            'resultKeys:', Object.keys(raceOdds3t_result).length,
            'combos:', comboStrs.slice(0,3));
          window._scenSynthDebugCount++;
        }
      }

      // includeAll=false のとき合成オッズ2.0未満は除外
      // ただし synth=null（過去日はODDS_DATAなしのため計算不可）は除外しない
      // → シナリオ買いパネルは synth 不問で集計し、EV は hitProbEst で代替
      if (!includeAll && synth != null && synth < SCEN_SYNTH_MIN) return;

      // ── 的中チェック ──
      // sanrentan[0] が1着−2着−3着の確定結果
      const actualRaw    = result.sanrentan[0]?.combo ?? null;
      const actualResult = actualRaw ? _normC(actualRaw) : null;
      const resultSet    = actualResult ? new Set([actualResult]) : null;
      // 数字列に変換した正規化（例: '3-1-4' → '314'）で照合するフォールバックを追加
      // 区切り文字の取りこぼしによる isHit ミスを防ぐ
      const _digitsOnly  = s => (s || '').replace(/[^1-6]/g, '');
      const actualDigits = actualResult ? _digitsOnly(actualResult) : null;
      const isHit        = !!(resultSet && (
        comboStrs.some(c => resultSet.has(c)) ||
        (actualDigits && actualDigits.length === 3 &&
          comboStrs.some(c => _digitsOnly(c) === actualDigits))
      ));

      // 的中配当（単位: 円 = collectResultsForDate と同一）
      // RESULT_DATA の sanrentan[0].odds は「倍率」→ ×100 で円換算
      // ただし既に円単位で入っている場合もあるため、100以上の場合はそのまま使う
      let hitOddsVal = 0;
      if (isHit) {
        // sanrentan 全体から actualResult に一致するオッズを探す
        // （sanrentan[0] が確定1位とは限らないケースへの保険）
        const _matchedSan = (result?.sanrentan || []).find(s =>
          s?.combo && _normC(s.combo) === actualResult
        ) || result.sanrentan[0];
        const rdOdds = _matchedSan?.odds ?? null;
        if (rdOdds != null && rdOdds > 0) {
          // odds が 100 未満なら「倍率」として扱い ×100、以上なら円単位とみなす
          hitOddsVal = rdOdds < 100 ? Math.round(rdOdds * 100) : rdOdds;
        } else if (actualResult) {
          // RESULT_DATAにoddsがない場合 ODDS_DATA から取得（倍率→円換算）
          const ov = raceOdds3t[actualResult] ?? null;
          hitOddsVal = ov != null ? Math.round(ov * 100) : 0;
        }
      }

      // ── EV 計算（期待値 = 合成オッズ × 想定的中率）──
      // synth が取れた場合: synth × hitProbEst
      // synth=null（過去日はODDS_DATAなし）の場合:
      //   的中配当(円)÷100 を合成オッズ代替として使用（1点買い相当の概算）
      //   → 厳密ではないが EV1.1フィルタの参考値として機能する
      let ev = null;
      if (synth != null && hitProbEst != null) {
        ev = synth * hitProbEst;
      }
      // ※ _scenEVCache 参照は削除: 当日分のみ有効でバックテスト用途では常に null

      // ── 2着・3着 calibration 用フィールド ──
      // actualResult = "1-2-3" 形式。split('-')[1] が2着、[2] が3着の枠番
      const _actParts  = actualResult ? actualResult.split('-') : [];
      const actual2nd  = _actParts.length >= 2 ? parseInt(_actParts[1]) : null;
      const actual3rd  = _actParts.length >= 3 ? parseInt(_actParts[2]) : null;

      // シナリオ買い目から「予測2着順位」を算出（何番目に高い2着予測だったか）
      // computeScenCombosWithEV の sd は外から参照できないため、
      // combo文字列リストから頻度で推定（2着枠番の出現頻度が高いほど上位予測）
      let pred2ndRank = null;
      if (actual2nd != null && comboStrs.length > 0) {
        // 各2着枠番の出現数を集計
        const freq2nd = {};
        comboStrs.forEach(c => {
          const p = c.split('-');
          if (p.length >= 2) {
            const n = parseInt(p[1]);
            if (!isNaN(n)) freq2nd[n] = (freq2nd[n] || 0) + 1;
          }
        });
        // 出現数降順でソートし、actual2nd の順位を特定
        const sorted2nd = Object.entries(freq2nd)
          .sort((a, b) => b[1] - a[1])
          .map(([boat]) => parseInt(boat));
        const rankIdx = sorted2nd.indexOf(actual2nd);
        pred2ndRank = rankIdx >= 0 ? rankIdx + 1 : null; // 1-indexed
      }

      // 同様に予測3着順位を算出
      let pred3rdRank = null;
      if (actual3rd != null && comboStrs.length > 0) {
        const freq3rd = {};
        comboStrs.forEach(c => {
          const p = c.split('-');
          if (p.length >= 3) {
            const n = parseInt(p[2]);
            if (!isNaN(n)) freq3rd[n] = (freq3rd[n] || 0) + 1;
          }
        });
        const sorted3rd = Object.entries(freq3rd)
          .sort((a, b) => b[1] - a[1])
          .map(([boat]) => parseInt(boat));
        const rankIdx3 = sorted3rd.indexOf(actual3rd);
        pred3rdRank = rankIdx3 >= 0 ? rankIdx3 + 1 : null;
      }

      results.push({
        venue,
        date     : vdata.date,
        rno,
        buy3cnt  : combos.length,
        isHit,
        hitOdds  : hitOddsVal,   // 単位: 円
        actualResult,
        actual2nd,               // 実際の2着枠番（calibration用）
        actual3rd,               // 実際の3着枠番（calibration用）
        pred2ndRank,             // 予測2着枠番の順位（1=最多出現、null=計算不可）
        pred3rdRank,             // 予測3着枠番の順位（1=最多出現、null=計算不可）
        synth,
        hitRate    : hitProbEst,   // _buildScenEV30Panel 等で r.hitRate として参照
        hitProbEst,                // calibration.js が r.hitProbEst として参照
        ev,                      // 期待値（synth × hitRate）
      });
    });
  });

  return results;
}

// ══════════════════════════════════════════════════════════════════
// シナリオ買いパネル（日付カード用・当日表示用）
// _buildScenEVPanel_dateCard  : 期待値1.1フィルタ結果パネル
// _buildScenPanel_dateCard    : 合成オッズ2.0以上パネル
// ══════════════════════════════════════════════════════════════════
function _buildScenEVPanel_dateCard(resultsScenAll) {
  const EV_MIN = 1.1;
  // r.ev は collectResultsForDateScen 内で計算済み（synth × hitRate）
  const evResults = (resultsScenAll || []).filter(r => {
    const ev = r.ev ?? (r.synth != null && r.hitRate != null ? r.synth * r.hitRate : null);
    return ev != null && ev >= EV_MIN;
  });

  const title    = '📈 期待値1.1';
  const subtitle = 'シナリオ買い × 期待値フィルター';

  if (evResults.length === 0) return `
    <div style="background:var(--bg3);border-radius:var(--radius-sm);padding:10px;border:1px solid var(--border)">
      <div style="font-size:10px;font-weight:700;color:var(--text3);text-align:center;margin-bottom:2px">${title}</div>
      <div style="font-size:10px;color:var(--text3);text-align:center;margin-bottom:8px">${subtitle}</div>
      <div style="color:var(--text3);font-size:11px;text-align:center;padding:0.3rem 0">集計対象なし</div>
    </div>`;

  const hitCount     = evResults.filter(r => r.isHit).length;
  const hitRate      = hitCount / evResults.length;
  const totalBet     = evResults.reduce((s, r) => s + r.buy3cnt * 100, 0);
  const totalReturn  = evResults.filter(r => r.isHit).reduce((s, r) => s + r.hitOdds, 0);
  const recoveryRate = totalBet > 0 ? totalReturn / totalBet : 0;
  const hitColor = hitRate      >= 0.7 ? 'var(--green)' : hitRate      >= 0.5 ? 'var(--orange)' : 'var(--text)';
  const recColor = recoveryRate >= 1.0 ? 'var(--green)' : recoveryRate >= 0.75 ? 'var(--orange)' : 'var(--text)';

  // 平均期待値・平均合成オッズ・平均想定的中率
  const evArr   = evResults.map(r =>
    r.ev ?? (r.synth != null && r.hitRate != null ? r.synth * r.hitRate : null)
  ).filter(v => v != null);
  const avgEV    = evArr.length > 0 ? evArr.reduce((s, v) => s + v, 0) / evArr.length : null;
  const synthArr = evResults.map(r => r.synth).filter(v => v != null);
  const avgSynth = synthArr.length > 0 ? synthArr.reduce((s, v) => s + v, 0) / synthArr.length : null;
  const hitRateArr = evResults.map(r => r.hitRate).filter(v => v != null);
  const avgHitRate = hitRateArr.length > 0 ? hitRateArr.reduce((s, v) => s + v, 0) / hitRateArr.length : null;

  // 会場別内訳
  const venueMapEV = {};
  evResults.forEach(r => { if (!venueMapEV[r.venue]) venueMapEV[r.venue] = []; venueMapEV[r.venue].push(r); });

  const comboBadgesEV = combo => (combo || '').split(/[-－−]/).map(n =>
    /^[1-6]$/.test(n.trim())
      ? `<span class="boat-circle b${n.trim()}" style="width:20px;height:20px;font-size:10px;display:inline-flex;align-items:center;justify-content:center;flex-shrink:0">${n.trim()}</span>`
      : ''
  ).join('<span style="color:var(--text3);font-size:11px;margin:0 1px">−</span>');

  const venueBlocksEV = VENUE_LIST.filter(v => venueMapEV[v]).map(v => {
    const vrs  = venueMapEV[v];
    const vHit = vrs.filter(r => r.isHit).length;
    const vTot = vrs.length;
    const vHR  = vHit / vTot;
    const vBet = vrs.reduce((s, r) => s + r.buy3cnt * 100, 0);
    const vRet = vrs.filter(r => r.isHit).reduce((s, r) => s + r.hitOdds, 0);
    const vRec = vBet > 0 ? vRet / vBet : 0;
    const vHC  = vHR >= 0.7 ? 'hit' : vHR >= 0.5 ? 'warn' : '';
    const vRC  = vRec >= 1.0 ? 'over' : vRec >= 0.75 ? 'warn' : '';

    const raceDetails = vrs.map(r => {
      const hitOddsStr = r.isHit && r.hitOdds ? `￥${r.hitOdds.toLocaleString()}` : '';
      const resultStr  = r.actualResult
        ? `<span style="display:inline-flex;align-items:center;gap:2px;flex-shrink:0">${comboBadgesEV(r.actualResult)}</span>`
        : '';
      const hitPart = r.isHit
        ? `<span style="display:inline-flex;align-items:center;gap:4px;flex-shrink:0;flex-wrap:nowrap"><span class="ai-venue-race-hit">🎯 的中</span>${resultStr}<span class="ai-venue-race-odds">${hitOddsStr}</span></span>`
        : `<span style="display:inline-flex;align-items:center;gap:4px;flex-shrink:0;flex-wrap:nowrap"><span class="ai-venue-race-miss">—</span>${resultStr}</span>`;
      return `<div class="ai-race-row" style="display:flex;align-items:center;gap:6px;padding:5px 8px;border-bottom:1px solid var(--border);flex-wrap:nowrap;overflow:hidden">
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
          <span class="ai-venue-stat-val ${vHC}">${(vHR*100).toFixed(0)}%</span>
          <span class="ai-venue-stat-sub">${vHit}/${vTot}R</span>
        </span>
        <span class="ai-venue-stat">
          <span class="ai-venue-stat-label">回収率</span>
          <span class="ai-venue-stat-val ${vRC}">${(vRec*100).toFixed(0)}%</span>
        </span>
      </summary>
      <div class="ai-venue-race-list">${raceDetails}</div>
    </details>`;
  }).join('');

  const detailHtmlEV = venueBlocksEV ? `
    <details style="margin-top:0.5rem">
      <summary style="font-size:11px;font-weight:700;color:var(--text3);cursor:pointer;letter-spacing:.06em;list-style:none;display:flex;align-items:center;gap:5px">
        <span style="font-size:10px">▶</span> 会場別内訳
      </summary>
      <div class="ai-venue-list" style="margin-top:0.5rem">${venueBlocksEV}</div>
    </details>` : '';

  return `
    <div style="background:var(--bg3);border-radius:var(--radius-sm);padding:10px;border:1px solid var(--border)">
      <div style="font-size:10px;font-weight:700;color:var(--text3);text-align:center;margin-bottom:2px">${title}</div>
      <div style="font-size:10px;color:var(--text3);text-align:center;margin-bottom:8px">${subtitle}</div>
      <div style="display:flex;flex-direction:column;gap:5px">
        <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);padding-bottom:4px">
          <span style="font-size:10px;color:var(--text3)">的中率</span>
          <span style="font-size:15px;font-weight:700;font-family:var(--mono);color:${hitColor}">${(hitRate*100).toFixed(0)}%
            <span style="font-size:10px;font-weight:400;color:var(--text3)">${hitCount}/${evResults.length}R</span>
          </span>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);padding-bottom:4px">
          <span style="font-size:10px;color:var(--text3)">回収率</span>
          <span style="font-size:15px;font-weight:700;font-family:var(--mono);color:${recColor}">${(recoveryRate*100).toFixed(0)}%</span>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);padding-bottom:4px">
          <span style="font-size:10px;color:var(--text3)">総投資</span>
          <span style="font-size:12px;font-weight:700;font-family:var(--mono);color:var(--text)">${totalBet.toLocaleString()}円</span>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);padding-bottom:4px">
          <span style="font-size:10px;color:var(--text3)">総回収</span>
          <span style="font-size:12px;font-weight:700;font-family:var(--mono);color:${recColor}">${totalReturn.toLocaleString()}円</span>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);padding-bottom:4px">
          <span style="font-size:10px;color:var(--text3)">集計R</span>
          <span style="font-size:12px;font-weight:700;font-family:var(--mono);color:var(--text)">${evResults.length}R</span>
        </div>
        ${avgEV    != null ? `<div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);padding-bottom:4px"><span style="font-size:10px;color:var(--text3)">平均期待値</span><span style="font-size:12px;font-weight:700;font-family:var(--mono);color:var(--orange)">${avgEV.toFixed(2)}</span></div>` : ''}
        ${avgSynth != null ? `<div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);padding-bottom:4px"><span style="font-size:10px;color:var(--text3)">平均合成オッズ</span><span style="font-size:12px;font-weight:700;font-family:var(--mono);color:var(--text)">${avgSynth.toFixed(1)}倍</span></div>` : ''}
        ${avgHitRate != null ? `<div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);padding-bottom:4px"><span style="font-size:10px;color:var(--text3)">平均想定的中率</span><span style="font-size:12px;font-weight:700;font-family:var(--mono);color:var(--text)">${(avgHitRate*100).toFixed(1)}%</span></div>` : ''}
      </div>
      ${detailHtmlEV}
    </div>`;
}

// シナリオ買い 合成オッズ2.0以上パネル（日付カード用）
function _buildScenPanel_dateCard(resultsScen, resultsScenAll) {
  const title    = '🎲 シナリオ買い';
  const subtitle = '合成オッズ2.0倍以上';

  // フォールバックしない: 合成オッズ2.0倍以上が0件なら「集計対象なし」を主表示とし、
  // フィルターなし全件は常に折りたたみ参照として追加する
  const targetData = resultsScen;

  if (targetData.length === 0) {
    // フィルターなし参照（折りたたみ）を付与して返す
    const allTotal = (resultsScenAll || []).length;
    const noFilterRefEmpty = allTotal > 0 ? (() => {
      const allHit      = (resultsScenAll || []).filter(r => r.isHit).length;
      const allTotalBet = (resultsScenAll || []).reduce((s, r) => s + r.buy3cnt * 100, 0);
      const allTotalRet = (resultsScenAll || []).filter(r => r.isHit).reduce((s, r) => s + r.hitOdds, 0);
      const allRecovery = allTotalBet > 0 ? allTotalRet / allTotalBet : 0;
      const allHitColor = (allHit/allTotal) >= 0.7 ? 'var(--green)' : (allHit/allTotal) >= 0.5 ? 'var(--orange)' : 'var(--text)';
      const allRecColor = allRecovery >= 1.0 ? 'var(--green)' : allRecovery >= 0.75 ? 'var(--orange)' : 'var(--text)';
      return `
      <details style="margin-top:0.5rem">
        <summary style="font-size:11px;font-weight:700;color:var(--text3);cursor:pointer;list-style:none;display:flex;align-items:center;gap:4px;padding:2px 0">
          <span style="font-size:10px">▶</span> フィルターなし参照
        </summary>
        <div style="display:flex;flex-direction:column;gap:4px;margin-top:6px">
          <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);padding-bottom:3px">
            <span style="font-size:10px;color:var(--text3)">的中率</span>
            <span style="font-size:12px;font-weight:700;font-family:var(--mono);color:${allHitColor}">${(allHit/allTotal*100).toFixed(0)}%
              <span style="font-size:10px;font-weight:400;color:var(--text3)">${allHit}/${allTotal}R</span>
            </span>
          </div>
          <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);padding-bottom:3px">
            <span style="font-size:10px;color:var(--text3)">回収率</span>
            <span style="font-size:12px;font-weight:700;font-family:var(--mono);color:${allRecColor}">${(allRecovery*100).toFixed(0)}%</span>
          </div>
          <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);padding-bottom:3px">
            <span style="font-size:10px;color:var(--text3)">総投資</span>
            <span style="font-size:11px;font-weight:700;font-family:var(--mono);color:var(--text)">${allTotalBet.toLocaleString()}円</span>
          </div>
          <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);padding-bottom:3px">
            <span style="font-size:10px;color:var(--text3)">総回収</span>
            <span style="font-size:11px;font-weight:700;font-family:var(--mono);color:${allRecColor}">${allTotalRet.toLocaleString()}円</span>
          </div>
          <div style="display:flex;justify-content:space-between;align-items:center">
            <span style="font-size:10px;color:var(--text3)">集計R</span>
            <span style="font-size:11px;font-weight:700;font-family:var(--mono);color:var(--text)">${allTotal}R</span>
          </div>
        </div>
      </details>`;
    })() : '';
    return `
    <div style="background:var(--bg3);border-radius:var(--radius-sm);padding:10px;border:1px solid var(--border)">
      <div style="font-size:10px;font-weight:700;color:var(--text3);text-align:center;margin-bottom:2px">${title}</div>
      <div style="font-size:10px;color:var(--text3);text-align:center;margin-bottom:8px">${subtitle}</div>
      <div style="color:var(--text3);font-size:11px;text-align:center;padding:0.3rem 0">集計対象なし</div>
      ${noFilterRefEmpty}
    </div>`;
  }

  const total        = targetData.length;
  const hitCount     = targetData.filter(r => r.isHit).length;
  const hitRate      = hitCount / total;
  const totalBet     = targetData.reduce((s, r) => s + r.buy3cnt * 100, 0);
  const totalReturn  = targetData.filter(r => r.isHit).reduce((s, r) => s + r.hitOdds, 0);
  const recoveryRate = totalBet > 0 ? totalReturn / totalBet : 0;
  const hitColor = hitRate      >= 0.7 ? 'var(--green)' : hitRate      >= 0.5 ? 'var(--orange)' : 'var(--text)';
  const recColor = recoveryRate >= 1.0 ? 'var(--green)' : recoveryRate >= 0.75 ? 'var(--orange)' : 'var(--text)';

  // 合成オッズ平均（集計対象のみ）
  const synthArr = targetData.map(r => r.synth).filter(v => v != null);
  const avgSynth = synthArr.length > 0 ? synthArr.reduce((s, v) => s + v, 0) / synthArr.length : null;

  // 会場別内訳（_buildCondBuyPanel_dateCard と同一構造）
  const venueMap = {};
  targetData.forEach(r => { if (!venueMap[r.venue]) venueMap[r.venue] = []; venueMap[r.venue].push(r); });

  const comboBadges = combo => (combo || '').split(/[-－−]/).map(n =>
    /^[1-6]$/.test(n.trim())
      ? `<span class="boat-circle b${n.trim()}" style="width:20px;height:20px;font-size:10px;display:inline-flex;align-items:center;justify-content:center;flex-shrink:0">${n.trim()}</span>`
      : ''
  ).join('<span style="color:var(--text3);font-size:11px;margin:0 1px">−</span>');

  const venueBlocks = VENUE_LIST.filter(v => venueMap[v]).map(v => {
    const vrs  = venueMap[v];
    const vHit = vrs.filter(r => r.isHit).length;
    const vTot = vrs.length;
    const vHR  = vHit / vTot;
    const vBet = vrs.reduce((s, r) => s + r.buy3cnt * 100, 0);
    const vRet = vrs.filter(r => r.isHit).reduce((s, r) => s + r.hitOdds, 0);
    const vRec = vBet > 0 ? vRet / vBet : 0;
    const vHC  = vHR >= 0.7 ? 'hit' : vHR >= 0.5 ? 'warn' : '';
    const vRC  = vRec >= 1.0 ? 'over' : vRec >= 0.75 ? 'warn' : '';

    const raceDetails = vrs.map(r => {
      const hitOddsStr = r.isHit && r.hitOdds ? `￥${r.hitOdds.toLocaleString()}` : '';
      const resultStr  = r.actualResult
        ? `<span style="display:inline-flex;align-items:center;gap:2px;flex-shrink:0">${comboBadges(r.actualResult)}</span>`
        : '';
      const hitPart = r.isHit
        ? `<span style="display:inline-flex;align-items:center;gap:4px;flex-shrink:0;flex-wrap:nowrap"><span class="ai-venue-race-hit">🎯 的中</span>${resultStr}<span class="ai-venue-race-odds">${hitOddsStr}</span></span>`
        : `<span style="display:inline-flex;align-items:center;gap:4px;flex-shrink:0;flex-wrap:nowrap"><span class="ai-venue-race-miss">—</span>${resultStr}</span>`;
      return `<div class="ai-race-row" style="display:flex;align-items:center;gap:6px;padding:5px 8px;border-bottom:1px solid var(--border);flex-wrap:nowrap;overflow:hidden">
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
          <span class="ai-venue-stat-val ${vHC}">${(vHR*100).toFixed(0)}%</span>
          <span class="ai-venue-stat-sub">${vHit}/${vTot}R</span>
        </span>
        <span class="ai-venue-stat">
          <span class="ai-venue-stat-label">回収率</span>
          <span class="ai-venue-stat-val ${vRC}">${(vRec*100).toFixed(0)}%</span>
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

  // フィルターなし参照（常に折りたたみで表示）
  // 過去30日版（_buildScen30Panel）と同等の充実した表示
  const allTotal = (resultsScenAll || []).length;
  const noFilterRef = (allTotal > 0) ? (() => {
    const allHit        = (resultsScenAll || []).filter(r => r.isHit).length;
    const allTotalBet   = (resultsScenAll || []).reduce((s, r) => s + r.buy3cnt * 100, 0);
    const allTotalRet   = (resultsScenAll || []).filter(r => r.isHit).reduce((s, r) => s + r.hitOdds, 0);
    const allRecovery   = allTotalBet > 0 ? allTotalRet / allTotalBet : 0;
    const allHitColor   = (allHit/allTotal) >= 0.7 ? 'var(--green)' : (allHit/allTotal) >= 0.5 ? 'var(--orange)' : 'var(--text)';
    const allRecColor   = allRecovery >= 1.0 ? 'var(--green)' : allRecovery >= 0.75 ? 'var(--orange)' : 'var(--text)';

    // 会場別テーブル行
    const allVenueMap = {};
    (resultsScenAll || []).forEach(r => {
      if (!allVenueMap[r.venue]) allVenueMap[r.venue] = [];
      allVenueMap[r.venue].push(r);
    });
    const allVenueRows = VENUE_LIST.filter(v => allVenueMap[v]).map(v => {
      const vrs  = allVenueMap[v];
      const vHit = vrs.filter(r => r.isHit).length;
      const vTot = vrs.length;
      const vBet = vrs.reduce((s, r) => s + r.buy3cnt * 100, 0);
      const vRet = vrs.filter(r => r.isHit).reduce((s, r) => s + r.hitOdds, 0);
      const vRec = vBet > 0 ? vRet / vBet : 0;
      const vHC  = (vHit/vTot) >= 0.7 ? 'var(--green)' : (vHit/vTot) >= 0.5 ? 'var(--orange)' : 'var(--text)';
      const vRC  = vRec >= 1.0 ? 'var(--green)' : vRec >= 0.75 ? 'var(--orange)' : 'var(--text)';
      return `<tr style="border-bottom:1px solid var(--border)">
        <td style="padding:3px 6px;font-size:11px;color:var(--text2);white-space:nowrap">${v}</td>
        <td style="padding:3px 6px;text-align:right;font-size:11px;font-weight:700;color:${vHC}">${(vHit/vTot*100).toFixed(0)}%</td>
        <td style="padding:3px 6px;text-align:right;font-size:10px;color:var(--text3)">${vHit}/${vTot}R</td>
        <td style="padding:3px 6px;text-align:right;font-size:11px;font-weight:700;color:${vRC}">${(vRec*100).toFixed(0)}%</td>
      </tr>`;
    }).join('');

    return `
    <details style="margin-top:0.5rem">
      <summary style="font-size:11px;font-weight:700;color:var(--text3);cursor:pointer;list-style:none;display:flex;align-items:center;gap:4px;padding:2px 0">
        <span style="font-size:10px">▶</span> フィルターなし参照
      </summary>
      <div style="display:flex;flex-direction:column;gap:5px;margin-top:6px">
        <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);padding-bottom:4px">
          <span style="font-size:10px;color:var(--text3)">的中率</span>
          <span style="font-size:13px;font-weight:700;font-family:var(--mono);color:${allHitColor}">${(allHit/allTotal*100).toFixed(0)}%
            <span style="font-size:10px;font-weight:400;color:var(--text3)">${allHit}/${allTotal}R</span>
          </span>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);padding-bottom:4px">
          <span style="font-size:10px;color:var(--text3)">回収率</span>
          <span style="font-size:13px;font-weight:700;font-family:var(--mono);color:${allRecColor}">${(allRecovery*100).toFixed(0)}%</span>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);padding-bottom:4px">
          <span style="font-size:10px;color:var(--text3)">総投資</span>
          <span style="font-size:12px;font-weight:700;font-family:var(--mono);color:var(--text)">${allTotalBet.toLocaleString()}円</span>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);padding-bottom:4px">
          <span style="font-size:10px;color:var(--text3)">総回収</span>
          <span style="font-size:12px;font-weight:700;font-family:var(--mono);color:${allRecColor}">${allTotalRet.toLocaleString()}円</span>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center">
          <span style="font-size:10px;color:var(--text3)">集計R</span>
          <span style="font-size:12px;font-weight:700;font-family:var(--mono);color:var(--text)">${allTotal}R</span>
        </div>
      </div>
      ${allVenueRows ? `
      <div style="overflow-x:auto;margin-top:6px">
        <table style="width:100%;border-collapse:collapse">
          <thead><tr style="border-bottom:1px solid var(--border)">
            <th style="padding:3px 6px;text-align:left;font-size:10px;color:var(--text3);font-weight:500">会場</th>
            <th style="padding:3px 6px;text-align:right;font-size:10px;color:var(--text3);font-weight:500">的中率</th>
            <th style="padding:3px 6px;text-align:right;font-size:10px;color:var(--text3);font-weight:500">R数</th>
            <th style="padding:3px 6px;text-align:right;font-size:10px;color:var(--text3);font-weight:500">回収率</th>
          </tr></thead>
          <tbody>${allVenueRows}</tbody>
        </table>
      </div>` : ''}
    </details>`;
  })() : '';

  return `
    <div style="background:var(--bg3);border-radius:var(--radius-sm);padding:10px;border:1px solid var(--border)">
      <div style="font-size:10px;font-weight:700;color:var(--text3);text-align:center;margin-bottom:2px">${title}</div>
      <div style="font-size:10px;color:var(--text3);text-align:center;margin-bottom:8px">${subtitle}</div>
      <div style="display:flex;flex-direction:column;gap:5px">
        <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);padding-bottom:4px">
          <span style="font-size:10px;color:var(--text3)">的中率</span>
          <span style="font-size:15px;font-weight:700;font-family:var(--mono);color:${hitColor}">${(hitRate*100).toFixed(0)}%
            <span style="font-size:10px;font-weight:400;color:var(--text3)">${hitCount}/${total}R</span>
          </span>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);padding-bottom:4px">
          <span style="font-size:10px;color:var(--text3)">回収率</span>
          <span style="font-size:15px;font-weight:700;font-family:var(--mono);color:${recColor}">${(recoveryRate*100).toFixed(0)}%</span>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);padding-bottom:4px">
          <span style="font-size:10px;color:var(--text3)">総投資</span>
          <span style="font-size:12px;font-weight:700;font-family:var(--mono);color:var(--text)">${totalBet.toLocaleString()}円</span>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);padding-bottom:4px">
          <span style="font-size:10px;color:var(--text3)">総回収</span>
          <span style="font-size:12px;font-weight:700;font-family:var(--mono);color:${recColor}">${totalReturn.toLocaleString()}円</span>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);padding-bottom:4px">
          <span style="font-size:10px;color:var(--text3)">集計R</span>
          <span style="font-size:12px;font-weight:700;font-family:var(--mono);color:var(--text)">${total}R</span>
        </div>
        ${avgSynth != null ? `<div style="display:flex;justify-content:space-between;align-items:center"><span style="font-size:10px;color:var(--text3)">合成オッズ</span><span style="font-size:12px;font-weight:700;font-family:var(--mono);color:var(--text)">${avgSynth.toFixed(1)}倍</span></div>` : ''}
      </div>
      ${detailHtml}
      ${noFilterRef}
    </div>`;
}

// ══════════════════════════════════════════════════════════════════
// シナリオ買いパネル（過去30日集計用）
// _buildScenEV30Panel : 期待値1.1フィルタ × 30日
// _buildScen30Panel   : 合成オッズ2.0以上 × 30日
// ══════════════════════════════════════════════════════════════════
function _buildScenEV30Panel(allResultsScenAll) {
  const EV_MIN = 1.1;
  // r.ev は collectResultsForDateScen 内で計算済み（synth × hitRate）
  // _scenEVCache は当日分のみ有効なため過去30日分は r.ev を使う
  const evResults = (allResultsScenAll || []).filter(r => {
    const ev = r.ev ?? (r.synth != null && r.hitRate != null ? r.synth * r.hitRate : null);
    return ev != null && ev >= EV_MIN;
  });

  const title    = '📈 期待値1.1';
  const subtitle = 'シナリオ買い × 期待値フィルター';
  const total = evResults.length;

  if (total === 0) return `
    <div style="background:var(--bg3);border-radius:var(--radius-sm);padding:12px;border:1px solid var(--border)">
      <div style="font-size:10px;font-weight:700;color:var(--text3);text-align:center;margin-bottom:4px">${title}</div>
      <div style="font-size:10px;color:var(--text3);text-align:center;margin-bottom:4px">${subtitle}</div>
      <div style="color:var(--text3);font-size:11px;text-align:center;padding:0.3rem 0">集計対象なし</div>
    </div>`;

  const hitCount     = evResults.filter(r => r.isHit).length;
  const hitRate      = hitCount / total;
  const totalBet     = evResults.reduce((s, r) => s + r.buy3cnt * 100, 0);
  const totalReturn  = evResults.filter(r => r.isHit).reduce((s, r) => s + r.hitOdds, 0);
  const recoveryRate = totalBet > 0 ? totalReturn / totalBet : 0;
  const hitColor = hitRate      >= 0.7 ? 'var(--green)' : hitRate      >= 0.5 ? 'var(--orange)' : 'var(--text)';
  const recColor = recoveryRate >= 1.0 ? 'var(--green)' : recoveryRate >= 0.75 ? 'var(--orange)' : 'var(--text)';

  const synthArr   = evResults.map(r => r.synth).filter(v => v != null);
  const avgSynth   = synthArr.length > 0 ? synthArr.reduce((s, v) => s + v, 0) / synthArr.length : null;
  const evArr      = evResults.map(r =>
    r.ev ?? (r.synth != null && r.hitRate != null ? r.synth * r.hitRate : null)
  ).filter(v => v != null);
  const avgEV      = evArr.length > 0 ? evArr.reduce((s, v) => s + v, 0) / evArr.length : null;
  const hitRateArr = evResults.map(r => r.hitRate).filter(v => v != null);
  const avgHitRate = hitRateArr.length > 0 ? hitRateArr.reduce((s, v) => s + v, 0) / hitRateArr.length : null;

  // 会場別内訳（テーブル形式）
  const venueMap30 = {};
  evResults.forEach(r => { if (!venueMap30[r.venue]) venueMap30[r.venue] = []; venueMap30[r.venue].push(r); });
  const venueRows30 = VENUE_LIST.filter(v => venueMap30[v]).map(v => {
    const vrs  = venueMap30[v];
    const vHit = vrs.filter(r => r.isHit).length;
    const vTot = vrs.length;
    const vBet = vrs.reduce((s, r) => s + r.buy3cnt * 100, 0);
    const vRet = vrs.filter(r => r.isHit).reduce((s, r) => s + r.hitOdds, 0);
    const vRec = vBet > 0 ? vRet / vBet : 0;
    const vHC  = (vHit/vTot) >= 0.7 ? 'var(--green)' : (vHit/vTot) >= 0.5 ? 'var(--orange)' : 'var(--text)';
    const vRC  = vRec >= 1.0 ? 'var(--green)' : vRec >= 0.75 ? 'var(--orange)' : 'var(--text)';
    return `<tr style="border-bottom:1px solid var(--border)">
      <td style="padding:3px 6px;font-size:11px;color:var(--text2);white-space:nowrap">${v}</td>
      <td style="padding:3px 6px;text-align:right;font-size:11px;font-weight:700;color:${vHC}">${(vHit/vTot*100).toFixed(0)}%</td>
      <td style="padding:3px 6px;text-align:right;font-size:10px;color:var(--text3)">${vHit}/${vTot}R</td>
      <td style="padding:3px 6px;text-align:right;font-size:11px;font-weight:700;color:${vRC}">${(vRec*100).toFixed(0)}%</td>
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
      <div style="font-size:10px;font-weight:700;color:var(--text3);text-align:center;margin-bottom:2px">${title}</div>
      <div style="font-size:10px;color:var(--text3);text-align:center;margin-bottom:10px">${subtitle}</div>
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
          </div>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);padding-bottom:5px">
          <span style="font-size:10px;color:var(--text3)">総投資</span>
          <span style="font-size:13px;font-weight:700;font-family:var(--mono);color:var(--text)">${totalBet.toLocaleString()}円</span>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);padding-bottom:5px">
          <span style="font-size:10px;color:var(--text3)">総回収</span>
          <span style="font-size:13px;font-weight:700;font-family:var(--mono);color:${recColor}">${totalReturn.toLocaleString()}円</span>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center${avgEV || avgSynth || avgHitRate ? ';border-bottom:1px solid var(--border);padding-bottom:5px' : ''}">
          <span style="font-size:10px;color:var(--text3)">集計R</span>
          <span style="font-size:13px;font-weight:700;font-family:var(--mono);color:var(--text)">${total}R</span>
        </div>
        ${avgEV    != null ? `<div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);padding-bottom:5px"><span style="font-size:10px;color:var(--text3)">平均期待値</span><span style="font-size:13px;font-weight:700;font-family:var(--mono);color:var(--orange)">${avgEV.toFixed(2)}</span></div>` : ''}
        ${avgSynth != null ? `<div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);padding-bottom:5px"><span style="font-size:10px;color:var(--text3)">平均合成オッズ</span><span style="font-size:13px;font-weight:700;font-family:var(--mono);color:var(--text)">${avgSynth.toFixed(1)}倍</span></div>` : ''}
        ${avgHitRate != null ? `<div style="display:flex;justify-content:space-between;align-items:center"><span style="font-size:10px;color:var(--text3)">平均想定的中率</span><span style="font-size:13px;font-weight:700;font-family:var(--mono);color:var(--text)">${(avgHitRate*100).toFixed(1)}%</span></div>` : ''}
      </div>
      ${venueDetail30}
    </div>`;
}

// シナリオ買い 合成オッズ2.0以上パネル（過去30日集計用）
function _buildScen30Panel(allResultsScen, allResultsScenAll) {
  const title    = '🎲 シナリオ買い';
  const subtitle = '合成オッズ2.0倍以上';
  const results  = allResultsScen || [];
  const total    = results.length;

  if (total === 0) return `
    <div style="background:var(--bg3);border-radius:var(--radius-sm);padding:12px;border:1px solid var(--border)">
      <div style="font-size:10px;font-weight:700;color:var(--text3);text-align:center;margin-bottom:4px">${title}</div>
      <div style="font-size:10px;color:var(--text3);text-align:center;margin-bottom:4px">${subtitle}</div>
      <div style="color:var(--text3);font-size:11px;text-align:center;padding:0.3rem 0">集計対象なし</div>
    </div>`;

  const hitCount     = results.filter(r => r.isHit).length;
  const hitRate      = hitCount / total;
  const totalBet     = results.reduce((s, r) => s + r.buy3cnt * 100, 0);
  const totalReturn  = results.filter(r => r.isHit).reduce((s, r) => s + r.hitOdds, 0);
  const recoveryRate = totalBet > 0 ? totalReturn / totalBet : 0;
  const hitColor = hitRate      >= 0.7 ? 'var(--green)' : hitRate      >= 0.5 ? 'var(--orange)' : 'var(--text)';
  const recColor = recoveryRate >= 1.0 ? 'var(--green)' : recoveryRate >= 0.75 ? 'var(--orange)' : 'var(--text)';

  const synthArr = results.map(r => r.synth).filter(v => v != null);
  const avgSynth = synthArr.length > 0 ? synthArr.reduce((s, v) => s + v, 0) / synthArr.length : null;

  // 会場別内訳
  const venueMap30 = {};
  results.forEach(r => { if (!venueMap30[r.venue]) venueMap30[r.venue] = []; venueMap30[r.venue].push(r); });
  const venueRows30 = VENUE_LIST.filter(v => venueMap30[v]).map(v => {
    const vrs  = venueMap30[v];
    const vHit = vrs.filter(r => r.isHit).length;
    const vTot = vrs.length;
    const vBet = vrs.reduce((s, r) => s + r.buy3cnt * 100, 0);
    const vRet = vrs.filter(r => r.isHit).reduce((s, r) => s + r.hitOdds, 0);
    const vRec = vBet > 0 ? vRet / vBet : 0;
    const vHC  = (vHit/vTot) >= 0.7 ? 'var(--green)' : (vHit/vTot) >= 0.5 ? 'var(--orange)' : 'var(--text)';
    const vRC  = vRec >= 1.0 ? 'var(--green)' : vRec >= 0.75 ? 'var(--orange)' : 'var(--text)';
    return `<tr style="border-bottom:1px solid var(--border)">
      <td style="padding:3px 6px;font-size:11px;color:var(--text2);white-space:nowrap">${v}</td>
      <td style="padding:3px 6px;text-align:right;font-size:11px;font-weight:700;color:${vHC}">${(vHit/vTot*100).toFixed(0)}%</td>
      <td style="padding:3px 6px;text-align:right;font-size:10px;color:var(--text3)">${vHit}/${vTot}R</td>
      <td style="padding:3px 6px;text-align:right;font-size:11px;font-weight:700;color:${vRC}">${(vRec*100).toFixed(0)}%</td>
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

  // フィルターなし参照（会場別内訳付き）
  const allTotal   = (allResultsScenAll || []).length;
  const allHit     = (allResultsScenAll || []).filter(r => r.isHit).length;

  // フィルターなし用の会場別テーブル行を生成
  const allVenueMap30 = {};
  (allResultsScenAll || []).forEach(r => {
    if (!allVenueMap30[r.venue]) allVenueMap30[r.venue] = [];
    allVenueMap30[r.venue].push(r);
  });
  const allVenueRows30 = VENUE_LIST.filter(v => allVenueMap30[v]).map(v => {
    const vrs  = allVenueMap30[v];
    const vHit = vrs.filter(r => r.isHit).length;
    const vTot = vrs.length;
    const vBet = vrs.reduce((s, r) => s + r.buy3cnt * 100, 0);
    const vRet = vrs.filter(r => r.isHit).reduce((s, r) => s + r.hitOdds, 0);
    const vRec = vBet > 0 ? vRet / vBet : 0;
    const vHC  = (vHit/vTot) >= 0.7 ? 'var(--green)' : (vHit/vTot) >= 0.5 ? 'var(--orange)' : 'var(--text)';
    const vRC  = vRec >= 1.0 ? 'var(--green)' : vRec >= 0.75 ? 'var(--orange)' : 'var(--text)';
    return `<tr style="border-bottom:1px solid var(--border)">
      <td style="padding:3px 6px;font-size:11px;color:var(--text2);white-space:nowrap">${v}</td>
      <td style="padding:3px 6px;text-align:right;font-size:11px;font-weight:700;color:${vHC}">${(vHit/vTot*100).toFixed(0)}%</td>
      <td style="padding:3px 6px;text-align:right;font-size:10px;color:var(--text3)">${vHit}/${vTot}R</td>
      <td style="padding:3px 6px;text-align:right;font-size:11px;font-weight:700;color:${vRC}">${(vRec*100).toFixed(0)}%</td>
    </tr>`;
  }).join('');

  // フィルターなし全体集計（的中率・回収率・総投資・総回収・集計R）
  const allTotalBet    = (allResultsScenAll || []).reduce((s, r) => s + r.buy3cnt * 100, 0);
  const allTotalReturn = (allResultsScenAll || []).filter(r => r.isHit).reduce((s, r) => s + r.hitOdds, 0);
  const allRecovery    = allTotalBet > 0 ? allTotalReturn / allTotalBet : 0;
  const allHitColor    = (allHit/allTotal) >= 0.7 ? 'var(--green)' : (allHit/allTotal) >= 0.5 ? 'var(--orange)' : 'var(--text)';
  const allRecColor    = allRecovery >= 1.0 ? 'var(--green)' : allRecovery >= 0.75 ? 'var(--orange)' : 'var(--text)';

  const noFilterRef = allTotal > 0 ? `
    <details style="margin-top:6px">
      <summary style="font-size:11px;font-weight:700;color:var(--text3);cursor:pointer;list-style:none;display:flex;align-items:center;gap:4px;padding:2px 0">
        <span style="font-size:10px">▶</span> フィルターなし参照
      </summary>
      <div style="display:flex;flex-direction:column;gap:5px;margin-top:6px">
        <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);padding-bottom:4px">
          <span style="font-size:10px;color:var(--text3)">的中率</span>
          <span style="font-size:13px;font-weight:700;font-family:var(--mono);color:${allHitColor}">${(allHit/allTotal*100).toFixed(0)}%
            <span style="font-size:10px;font-weight:400;color:var(--text3)">${allHit}/${allTotal}R</span>
          </span>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);padding-bottom:4px">
          <span style="font-size:10px;color:var(--text3)">回収率</span>
          <span style="font-size:13px;font-weight:700;font-family:var(--mono);color:${allRecColor}">${(allRecovery*100).toFixed(0)}%</span>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);padding-bottom:4px">
          <span style="font-size:10px;color:var(--text3)">総投資</span>
          <span style="font-size:12px;font-weight:700;font-family:var(--mono);color:var(--text)">${allTotalBet.toLocaleString()}円</span>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);padding-bottom:4px">
          <span style="font-size:10px;color:var(--text3)">総回収</span>
          <span style="font-size:12px;font-weight:700;font-family:var(--mono);color:${allRecColor}">${allTotalReturn.toLocaleString()}円</span>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center">
          <span style="font-size:10px;color:var(--text3)">集計R</span>
          <span style="font-size:12px;font-weight:700;font-family:var(--mono);color:var(--text)">${allTotal}R</span>
        </div>
      </div>
      ${allVenueRows30 ? `
      <div style="overflow-x:auto;margin-top:6px">
        <table style="width:100%;border-collapse:collapse">
          <thead><tr style="border-bottom:1px solid var(--border)">
            <th style="padding:3px 6px;text-align:left;font-size:10px;color:var(--text3);font-weight:500">会場</th>
            <th style="padding:3px 6px;text-align:right;font-size:10px;color:var(--text3);font-weight:500">的中率</th>
            <th style="padding:3px 6px;text-align:right;font-size:10px;color:var(--text3);font-weight:500">R数</th>
            <th style="padding:3px 6px;text-align:right;font-size:10px;color:var(--text3);font-weight:500">回収率</th>
          </tr></thead>
          <tbody>${allVenueRows30}</tbody>
        </table>
      </div>` : ''}
    </details>` : '';

  return `
    <div style="background:var(--bg3);border-radius:var(--radius-sm);padding:12px;border:1px solid var(--border)">
      <div style="font-size:10px;font-weight:700;color:var(--text3);text-align:center;margin-bottom:2px">${title}</div>
      <div style="font-size:10px;color:var(--text3);text-align:center;margin-bottom:10px">${subtitle}</div>
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
          </div>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);padding-bottom:5px">
          <span style="font-size:10px;color:var(--text3)">総投資</span>
          <span style="font-size:13px;font-weight:700;font-family:var(--mono);color:var(--text)">${totalBet.toLocaleString()}円</span>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);padding-bottom:5px">
          <span style="font-size:10px;color:var(--text3)">総回収</span>
          <span style="font-size:13px;font-weight:700;font-family:var(--mono);color:${recColor}">${totalReturn.toLocaleString()}円</span>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);padding-bottom:5px">
          <span style="font-size:10px;color:var(--text3)">集計R</span>
          <span style="font-size:13px;font-weight:700;font-family:var(--mono);color:var(--text)">${total}R</span>
        </div>
        ${avgSynth != null ? `<div style="display:flex;justify-content:space-between;align-items:center"><span style="font-size:10px;color:var(--text3)">合成オッズ</span><span style="font-size:13px;font-weight:700;font-family:var(--mono);color:var(--text)">${avgSynth.toFixed(1)}倍</span></div>` : '<div style="display:flex;justify-content:space-between;align-items:center"><span style="font-size:10px;color:var(--text3)">合成オッズ</span><span style="font-size:13px;color:var(--text3)">—</span></div>'}
      </div>
      ${venueDetail30}
      ${noFilterRef}
    </div>`;
}

// ── 日付カードHTMLを生成するヘルパー ──
function buildDateCard(dateStr, label) {
  const { results: resultsHit } = collectResultsForDate(dateStr, 'hit');
  const { results: resultsRec, excludedList } = collectResultsForDate(dateStr, 'rec');
  const resultsScen    = collectResultsForDateScen(dateStr);
  const resultsScenAll = collectResultsForDateScen(dateStr, true);
  const resultsInTep   = collectResultsForDateInTep(dateStr);
  const resultsInNeg   = collectResultsForDateInNeg(dateStr);

  if (resultsHit.length === 0 && resultsRec.length === 0 && excludedList.length === 0 && resultsScen.length === 0 && resultsScenAll.length === 0 && resultsInTep.length === 0 && resultsInNeg.length === 0) return '';

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
          ? `<span style="display:inline-flex;align-items:center;gap:2px;flex-shrink:0">${comboBadges(r.actualResult)}</span>`
          : '';
        const hitPart = r.isHit
          ? `<span style="display:inline-flex;align-items:center;gap:4px;flex-shrink:0;flex-wrap:nowrap"><span class="ai-venue-race-hit">🎯 的中</span>${resultStr}<span class="ai-venue-race-odds">${hitOddsStr}</span></span>`
          : `<span style="display:inline-flex;align-items:center;gap:4px;flex-shrink:0;flex-wrap:nowrap"><span class="ai-venue-race-miss">—</span>${resultStr}</span>`;
        return `<div class="ai-race-row" style="display:flex;align-items:center;gap:6px;padding:5px 8px;border-bottom:1px solid var(--border);flex-wrap:nowrap;overflow:hidden">
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
            <span style="font-size:10px;color:var(--text3)">総投資</span>
            <span style="font-size:12px;font-weight:700;font-family:var(--mono);color:var(--text)">${totalBet.toLocaleString()}円</span>
          </div>
          <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);padding-bottom:4px">
            <span style="font-size:10px;color:var(--text3)">総回収</span>
            <span style="font-size:12px;font-weight:700;font-family:var(--mono);color:${recColor}">${totalReturn.toLocaleString()}円</span>
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
        ${_buildScenEVPanel_dateCard(resultsScenAll)}
        ${_buildScenPanel_dateCard(resultsScen, resultsScenAll)}
        ${resultsInTep.length > 0 ? _buildCondBuyPanel_dateCard(resultsInTep, '🔒 イン鉄板', '1号艇確率75%以上') : ''}
        ${resultsInNeg.length > 0 ? _buildCondBuyPanel_dateCard(resultsInNeg, '⚡ イン否定', '1号艇確率が場平均-Nσ以下（σなし時:10%pt固定）') : ''}
        ${modePanel(resultsHit, '🎯 的中重視', 2.0)}
        ${modePanel(resultsRec, '💰 回収重視', 4.0)}
      </div>
    </div>`;
}

// ── AI予想成績を表示するメイン関数 ──
function calcTopAIStats() {
  const elToday   = document.getElementById('top-ai-stats-today');
  const elHistory = document.getElementById('top-ai-stats-history-summary');
  const elDetail  = document.getElementById('top-ai-stats');

  // getAvailableDates() を1回だけ呼んで使い回す（3回→1回）
  const _allDatesAsc = getAvailableDates();
  const allDates  = _allDatesAsc.slice().reverse(); // 新しい順
  const todayDate = _allDatesAsc[_allDatesAsc.length - 1];
  const histDates = _allDatesAsc.slice(0, -1).reverse(); // 過去日（新しい順）

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
      // histDates が空 = ALL_DATA_HISTORY がまだ読み込まれていない可能性がある。
      // fetch完了後に autoRefreshCurrentView → calcTopAIStats が再実行されるため、
      // 「読込中...」と表示してそちらに任せる。
      elHistory.innerHTML = `<div class="ai-stats-card"><div style="color:var(--text3);font-size:12px;text-align:center;padding:0.5rem 0">読込中...</div></div>`;
      // ※ fetch完了前に本当にデータが0件の場合でも、fetch後に再実行して確定させる
    } else {
      // 計算開始前にローディング表示（キャッシュヒット時は一瞬で上書きされる）
      elHistory.innerHTML = `<div class="ai-stats-card"><div style="color:var(--text3);font-size:12px;text-align:center;padding:0.5rem 0">集計中...</div></div>`;

      // ── 過去30日集計キャッシュ（sessionStorage）──
      // キャッシュキー: 当日日付 + 対象日付リストのハッシュ
      // 翌日になると todayDate が変わり自動的に再計算される
      // 対象日が変わった場合（新データ追加時）も past30 の末尾変化で再計算される
      let allResultsHit = [];
      let allResultsRec = [];
      let allResultsScen = [];
      let allResultsScenAll = [];
      let allResultsInTep = [];
      let allResultsInNeg = [];

      // [2026-06-01] v6→v7: ev=null が混入したキャッシュを自動破棄するためバージョン更新
      const _cacheKey = 'aiStats30_' + todayDate + '_' + past30[0] + '_' + past30[past30.length - 1] + '_' + past30.length + '_v10';
      let _cacheHit = false;
      try {
        const _cached = sessionStorage.getItem(_cacheKey);
        if (_cached) {
          const _parsed = JSON.parse(_cached);
          // 修正: _parsed.scenAll が空配列 [] のとき falsy になり
          // キャッシュミス扱いになるバグを修正。Array.isArray で存在確認する。
          if (_parsed
              && Array.isArray(_parsed.hit)
              && Array.isArray(_parsed.rec)
              && Array.isArray(_parsed.scen)
              && Array.isArray(_parsed.scenAll)) {
            allResultsHit     = _parsed.hit;
            allResultsRec     = _parsed.rec;
            allResultsScen    = _parsed.scen;
            allResultsScenAll = _parsed.scenAll;
            allResultsInTep   = _parsed.inTep  || [];
            allResultsInNeg   = _parsed.inNeg  || [];
            _cacheHit = true;
          }
        }
      } catch(e) { /* sessionStorage 読み取り失敗時はそのまま再計算 */ }

      if (!_cacheHit) {
        // ── キャッシュミス時は非同期で計算（改善③）──
        // 1日処理するごとに await setTimeout(0) でブラウザに制御を返し
        // メインスレッドをブロックしない。
        // ※ return を使わず Promise チェーンで後続処理（各日詳細）も確実に実行する
        (async function calcAsync() {
          try {
            for (const d of past30) {
              // 1日ごとにブラウザに制御を返す
              await new Promise(r => setTimeout(r, 0));
              const { results: rh } = collectResultsForDate(d, 'hit');
              const { results: rr } = collectResultsForDate(d, 'rec');
              const rs    = collectResultsForDateScen(d);
              const rsAll = collectResultsForDateScen(d, true);
              const rIt   = collectResultsForDateInTep(d);
              const rIn   = collectResultsForDateInNeg(d);
              allResultsHit.push(...rh);
              allResultsRec.push(...rr);
              allResultsScen.push(...rs);
              allResultsScenAll.push(...rsAll);
              allResultsInTep.push(...rIt);
              allResultsInNeg.push(...rIn);
            }
            try {
              // [2026-06-01 修正] 全30日の計算が完了した場合のみキャッシュ保存する。
              // 途中でページ離脱・例外が起きた場合は for ループが完走しないため
              // ここには到達しない → 空/途中データがキャッシュされるバグを防止。
              // さらに scenAll が空の場合も保存しない（データ取得失敗の可能性）。
              const _isComplete = allResultsScenAll.length > 0 || allResultsHit.length > 0;
              if (_isComplete) {
                Object.keys(sessionStorage)
                  .filter(k => k.startsWith('aiStats30_'))
                  .forEach(k => sessionStorage.removeItem(k));
                sessionStorage.setItem(_cacheKey, JSON.stringify({
                  hit: allResultsHit,
                  rec: allResultsRec,
                  scen: allResultsScen,
                  scenAll: allResultsScenAll,
                  inTep: allResultsInTep,
                  inNeg: allResultsInNeg
                }));
              }
            } catch(e) { /* sessionStorage 書き込み失敗（容量超過等）は無視 */ }
            _renderHistory30(allResultsHit, allResultsRec, allResultsScen, allResultsScenAll, allResultsInTep, allResultsInNeg);
          } catch(e) { console.warn('[calcTopAIStats] 30日集計エラー:', e); }
        })();
        // ※ ここで return しない → 各日詳細エリア（③）の処理を続行する
      } else {
        // キャッシュヒット時はそのまま描画
        _renderHistory30(allResultsHit, allResultsRec, allResultsScen, allResultsScenAll, allResultsInTep, allResultsInNeg);
      }
    }
  }

  // ── ③ 各日詳細エリア（改善③: 非同期で1日ずつ描画）──
  // ② の非同期計算中でも必ずここに到達する（上で return しないため）
  if (elDetail) {
    elDetail.innerHTML = `<div class="ai-stats-card"><div style="color:var(--text3);font-size:12px;text-align:center;padding:0.5rem 0">集計中...</div></div>`;
    (async function buildDetailAsync() {
      try {
        const htmlParts = [];
        for (const d of allDates) {
          await new Promise(r => setTimeout(r, 0));
          const card = buildDateCard(d, dateLabels[d] || d);
          if (card) htmlParts.push(card);
        }
        elDetail.innerHTML = htmlParts.join('') || noRaceHtml;
      } catch(e) {
        console.warn('[calcTopAIStats] 詳細カード生成エラー:', e);
      }
    })();
  }

  // ── ④ 的中速報セクション（6種類・的中のみ・確定新しい順） ──
  const elScenEV = document.getElementById('top-scen-ev-section');
  if (elScenEV && todayDate) {
    // _scenEVCacheReady が true ならキャッシュ充填済み → 即時描画
    // false（prefillScenEVCache 未完了）なら暫定描画 + リトライを仕掛ける
    elScenEV.innerHTML = _buildHitSokuhoPanel(todayDate);

    if (!_scenEVCacheReady) {
      // prefillScenEVCache の完了を最大30秒・500msごとにポーリングして再描画
      // （prefill 完了コールバック側でも再描画するが、そちらが失敗した場合の保険）
      let _retryCount = 0;
      const _retryMax = 60; // 500ms × 60 = 30秒
      const _retryId = setInterval(() => {
        _retryCount++;
        if (_scenEVCacheReady || _retryCount >= _retryMax) {
          clearInterval(_retryId);
          if (_scenEVCacheReady) {
            // TOPページが今も表示中の場合のみ再描画
            const _tp = document.getElementById('top-page');
            const _ev = document.getElementById('top-scen-ev-section');
            const _isVisible = _tp &&
              _tp.style.display !== 'none' &&
              _tp.offsetParent !== null;
            if (_isVisible && _ev) {
              _ev.innerHTML = _buildHitSokuhoPanel(todayDate);
            }
          }
        }
      }, 500);
    }
  }
}

// ── 的中速報パネル生成 ──
// 6種類の結果を全取得 → 的中のみ抽出 → 発走時刻降順（新しい順）でカード表示
function _buildHitSokuhoPanel(dateStr) {
  // キャッシュ件数をデバッグログに出力（空キャッシュで呼ばれた場合に検出できる）
  const _cacheSize = Object.keys(_scenEVCache || {}).length;
  if (_cacheSize === 0 && !_scenEVCacheReady) {
    console.warn('[_buildHitSokuhoPanel] _scenEVCache が空です（prefillScenEVCache 未完了）。' +
      'calcTopAIStats のリトライ機構により prefill 完了後に再描画されます。');
  }

  const labeledResults = [];

  try {
    const { results: rsHit } = collectResultsForDate(dateStr, 'hit');
    rsHit.forEach(r => { if (r.isHit) labeledResults.push({ ...r, _sokuhoLabel: '🎯 的中重視' }); });
  } catch(e) {}

  try {
    const { results: rsRec } = collectResultsForDate(dateStr, 'rec');
    rsRec.forEach(r => { if (r.isHit) labeledResults.push({ ...r, _sokuhoLabel: '💰 回収重視' }); });
  } catch(e) {}

  try {
    // _scenEVCache に依存せず直接計算する（イン鉄板・イン否定と同じ構造）
    // _scenEVCache は obfuscate でキーが壊れる場合があり信頼できないため
    const SCEN_SYNTH_MIN = 2.0;
    const SCEN_EV_MIN    = 1.1;
    const rsScenAll = collectResultsForDateScen(dateStr, true);
    const _dataFD = getDataForDate(dateStr);
    rsScenAll.forEach(r => {
      if (!r.isHit) return;

      // _scenEVCache を試みる（ヒットすればそれを使う）
      const rDateRaw = r.date || dateStr;
      const rDate = (typeof rDateRaw === 'string' && rDateRaw.length === 8 && !rDateRaw.includes('-'))
        ? `${rDateRaw.slice(0,4)}-${rDateRaw.slice(4,6)}-${rDateRaw.slice(6,8)}`
        : rDateRaw;
      const evKey1 = r.venue + '_' + rDate + '_' + r.rno;
      const cache  = _scenEVCache?.[evKey1] ?? null;

      let synth = cache?.synth ?? null;
      let ev    = cache?.ev    ?? null;

      // キャッシュミス or ev/synth が null → 直接計算（_synthOdds はローカル関数なので使えない）
      if (synth == null || ev == null) {
        try {
          const vdata = _dataFD?.[r.venue];
          if (vdata && typeof computeScenCombosWithEV === 'function') {
            const res        = computeScenCombosWithEV(r.venue, vdata, r.rno);
            const combos     = res?.combos     || [];
            const hitProbEst = res?.hitProbEst ?? null;
            if (combos.length > 0) {
              // インラインで合成オッズを計算
              const _od3t = ODDS_DATA?.[vdata.date]?.[r.venue]?.[String(r.rno)]?.['3t'] || {};
              let _den = 0, _cnt = 0;
              combos.forEach(c => {
                const _key = (typeof c === 'object' ? (c.c || '') : (c || '')).replace(/[－−\-]/g, '-');
                const _ov  = _od3t[_key] ?? null;
                if (_ov != null && _ov > 0) { _den += 1 / _ov; _cnt++; }
              });
              if (_cnt > 0 && _den > 0) synth = 1 / _den;
              ev = (synth != null && hitProbEst != null) ? synth * hitProbEst : null;
            }
          }
        } catch(_e) {}
      }

      // synth=null（確定後はODDS_DATA消滅）の場合: hitOdds÷100÷買い目数 で合成オッズを概算
      if (synth == null && r.buy3cnt > 0) {
        const hitOddsVal = r.hitOdds ?? 0;
        if (hitOddsVal > 0) synth = (hitOddsVal / 100) / r.buy3cnt;
      }
      // ev=null かつ hitRate があれば再計算
      if (ev == null && synth != null && r.hitRate != null) {
        ev = synth * r.hitRate;
      }

      // 合成オッズ 2.0倍以上 or synth不明 → 「シナリオ買い」
      if (synth == null || synth >= SCEN_SYNTH_MIN) {
        labeledResults.push({ ...r, _sokuhoLabel: '🎲 シナリオ買い' });
      }
      // EV 1.1以上 → 「期待値1.1」
      if (ev != null && ev >= SCEN_EV_MIN) {
        labeledResults.push({ ...r, _sokuhoLabel: '📈 期待値1.1' });
      }
    });
  } catch(e) {}

  try {
    const rsInTep = collectResultsForDateInTep(dateStr);
    rsInTep.forEach(r => { if (r.isHit) labeledResults.push({ ...r, _sokuhoLabel: '🔒 イン鉄板' }); });
  } catch(e) {}

  try {
    const rsInNeg = collectResultsForDateInNeg(dateStr);
    rsInNeg.forEach(r => { if (r.isHit) labeledResults.push({ ...r, _sokuhoLabel: '⚡ イン否定' }); });
  } catch(e) {}

  // 当日の確定レースが1件もなければ「集計中」表示
  const dateNd = (dateStr || '').replace(/-/g, '');
  const hasAnyResult = Object.keys(RESULT_DATA || {}).some(k => k.includes(`_${dateNd}_`));
  if (!hasAnyResult) {
    return '<div style="color:var(--text3);font-size:12px;padding:0.3rem 0.1rem">⏳ 確定レースはまだありません</div>';
  }

  // 的中がなければ空文字（タイトルはHTML側に固定のため何も返さない）
  if (labeledResults.length === 0) return '<div style="color:var(--text3);font-size:12px;padding:0.3rem 0.1rem">対象レースはありません</div>';

  // 発走時刻を vdata から逆引きして降順ソート（新しい順）
  const dataForDate = getDataForDate(dateStr);
  function getRaceTimeMin(r) {
    try {
      const t = dataForDate?.[r.venue]?.races?.[String(r.rno)]?.time || '';
      const m = t.trim().match(/^(\d{1,2}):(\d{2})$/);
      return m ? parseInt(m[1]) * 60 + parseInt(m[2]) : r.rno;
    } catch(e) { return r.rno; }
  }

  // 同じ venue+rno+label の重複を除去してからソート
  const seen = new Set();
  const unique = labeledResults.filter(r => {
    const key = `${r.venue}_${r.rno}_${r._sokuhoLabel}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });

  unique.sort((a, b) => getRaceTimeMin(b) - getRaceTimeMin(a));

  // 枠番バッジ変換ヘルパー（小さめサイズ）
  const comboBadges = combo => (combo || '').split(/[-－−]/).map(n =>
    /^[1-6]$/.test(n.trim())
      ? `<span class="boat-circle b${n.trim()}" style="width:18px;height:18px;font-size:10px;display:inline-flex;align-items:center;justify-content:center;flex-shrink:0">${n.trim()}</span>`
      : ''
  ).join('<span style="color:var(--text3);font-size:10px;margin:0 1px">−</span>');

  const cards = unique.map(r => {
    const oddsVal = r.hitOdds ? r.hitOdds / 100 : null;
    const oddsStr = oddsVal != null ? `${oddsVal.toFixed(1)}倍` : '';
    // 100倍超えは赤、それ以外は通常テキスト色
    const oddsColor = oddsVal != null && oddsVal > 100 ? 'var(--red)' : 'var(--text)';
    const comboHtml = r.actualResult
      ? `<div style="display:flex;align-items:center;gap:2px;margin:3px 0">${comboBadges(r.actualResult)}</div>`
      : '';
    const oddsHtml = oddsStr
      ? `<div style="font-size:13px;font-weight:700;font-family:var(--mono);color:${oddsColor}">${oddsStr}</div>`
      : '';
    return `<div style="background:var(--bg2);border:1px solid var(--border);border-left:3px solid var(--green);border-radius:8px;padding:8px 12px;display:flex;flex-direction:column;gap:2px;min-width:120px;flex-shrink:0">
        <div style="font-size:12px;font-weight:700;color:var(--text)">${r.venue} ${r.rno}R 🎯</div>
        ${comboHtml}
        ${oddsHtml}
        <div style="font-size:10px;color:var(--text3);margin-top:1px">${r._sokuhoLabel}</div>
      </div>`;
  }).join('');

  return `<div style="display:flex;flex-direction:row;gap:8px;overflow-x:auto;padding-bottom:4px;scrollbar-width:none;-webkit-overflow-scrolling:touch">${cards}</div>`;
}

// ── 過去30日集計の描画処理（calcTopAIStats から分離）──
// キャッシュヒット時・非同期計算完了時のどちらからも呼ばれる
function _renderHistory30(allResultsHit, allResultsRec, allResultsScen, allResultsScenAll, allResultsInTep = [], allResultsInNeg = []) {
  // 動的 inn_2place 補正（dynamic_inn2place.js が定義している場合のみ実行）
  if (typeof _applyDynamicInn2Place === 'function') _applyDynamicInn2Place(allResultsScenAll);
  const elHistory = document.getElementById('top-ai-stats-history-summary');
  if (!elHistory) return;

  // ── 過去30日集計結果をグローバルに保持（exportStatsCSV / exportAnalysisCSV から参照）──
  // top_page.js の _lastStats* 変数に書き込む（typeof チェックでロード順に依存しない）
  if (typeof _lastStatsHit     !== 'undefined') _lastStatsHit     = allResultsHit.slice();
  if (typeof _lastStatsRec     !== 'undefined') _lastStatsRec     = allResultsRec.slice();
  if (typeof _lastStatsScen    !== 'undefined') _lastStatsScen    = allResultsScen.slice();
  if (typeof _lastStatsScenAll !== 'undefined') _lastStatsScenAll = allResultsScenAll.slice();
  if (typeof _lastStatsInTep   !== 'undefined') _lastStatsInTep   = allResultsInTep.slice();
  if (typeof _lastStatsInNeg   !== 'undefined') _lastStatsInNeg   = allResultsInNeg.slice();

  function updateHistoryTimestamp() {
    const el = document.getElementById('top-ai-stats-history-updated');
    if (!el) return;
    const now = new Date();
    const mm  = String(now.getMonth() + 1).padStart(2, '0');
    const dd  = String(now.getDate()).padStart(2, '0');
    const hh  = String(now.getHours()).padStart(2, '0');
    const min = String(now.getMinutes()).padStart(2, '0');
    el.textContent = `更新：${mm}/${dd} ${hh}:${min}`;
  }

  if (allResultsHit.length === 0 && allResultsRec.length === 0
      && allResultsScen.length === 0 && allResultsScenAll.length === 0
      && allResultsInTep.length === 0 && allResultsInNeg.length === 0) {
    elHistory.innerHTML = `<div class="ai-stats-card"><div style="color:var(--text3);font-size:12px;text-align:center;padding:0.5rem 0">確定レースがありません</div></div>`;
    updateHistoryTimestamp();
    return;
  }

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
            </div>
          </div>
          <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);padding-bottom:5px">
            <span style="font-size:10px;color:var(--text3)">総投資</span>
            <span style="font-size:13px;font-weight:700;font-family:var(--mono);color:var(--text)">${totalBet.toLocaleString()}円</span>
          </div>
          <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);padding-bottom:5px">
            <span style="font-size:10px;color:var(--text3)">総回収</span>
            <span style="font-size:13px;font-weight:700;font-family:var(--mono);color:${recColor}">${totalReturn.toLocaleString()}円</span>
          </div>
          <div style="display:flex;justify-content:space-between;align-items:center">
            <span style="font-size:10px;color:var(--text3)">集計R</span>
            <span style="font-size:13px;font-weight:700;font-family:var(--mono);color:var(--text)">${total}R</span>
          </div>
        </div>
        ${venueDetail30}
      </div>`;
  }

  _renderCalibrationPanel(allResultsScenAll);

  // ── 直近3日集計用データ生成 ──
  const _allDatesPool3 = [
    ...allResultsScenAll, ...allResultsHit, ...allResultsRec,
    ...allResultsInTep, ...allResultsInNeg
  ];
  const _recentDates3 = [...new Set(_allDatesPool3.map(r => r.date).filter(Boolean))]
    .sort().slice(-3);
  const _filter3 = arr => arr.filter(r => _recentDates3.includes(r.date));
  const _scenAll3 = _filter3(allResultsScenAll);
  const _scen3    = _filter3(allResultsScen);
  const _hit3     = _filter3(allResultsHit);
  const _rec3     = _filter3(allResultsRec);
  const _inTep3   = _filter3(allResultsInTep);
  const _inNeg3   = _filter3(allResultsInNeg);
  const _3dayLabel = _recentDates3.length > 0
    ? `直近3日（${_recentDates3[0].slice(5)}〜${_recentDates3[_recentDates3.length-1].slice(5)}）`
    : '直近3日';

  // ── 日別集計カード生成（直近7日） ──
  const _recentDates7 = [...new Set(_allDatesPool3.map(r => r.date).filter(Boolean))]
    .sort().slice(-7).reverse();
  const _dailyCards = _recentDates7.map(d => {
    const _d3    = allResultsScenAll.filter(r => r.date === d);
    const _dHit  = allResultsHit.filter(r => r.date === d);
    const _dRec  = allResultsRec.filter(r => r.date === d);
    const _total = _d3.length;
    if (_total === 0) return '';
    const EV_MIN = 1.1;
    const _evR   = _d3.filter(r => {
      const ev = r.ev ?? (r.synth != null && r.hitRate != null ? r.synth * r.hitRate : null);
      return ev != null && ev >= EV_MIN;
    });
    const _evHit  = _evR.filter(r => r.isHit).length;
    const _evBet  = _evR.reduce((s, r) => s + r.buy3cnt * 100, 0);
    const _evRet  = _evR.filter(r => r.isHit).reduce((s, r) => s + r.hitOdds, 0);
    const _evRec  = _evBet > 0 ? _evRet / _evBet : 0;
    const _hc     = (_evR.length > 0 && _evHit/_evR.length >= 0.5) ? 'var(--green)' : 'var(--text)';
    const _rc     = _evRec >= 1.0 ? 'var(--green)' : _evRec >= 0.75 ? 'var(--orange)' : 'var(--text)';
    const _wd     = ['日','月','火','水','木','金','土'][new Date(d).getDay()];
    return `<div style="background:var(--bg3);border-radius:var(--radius-sm);padding:8px 10px;border:1px solid var(--border);min-width:120px;flex-shrink:0">
      <div style="font-size:10px;font-weight:700;color:var(--text3);margin-bottom:4px">${d.slice(5)}（${_wd}）</div>
      <div style="font-size:9px;color:var(--text3);margin-bottom:4px">EV1.1+ ${_evR.length}R</div>
      <div style="display:flex;justify-content:space-between;gap:6px">
        <div style="text-align:center">
          <div style="font-size:9px;color:var(--text3)">的中率</div>
          <div style="font-size:13px;font-weight:700;font-family:var(--mono);color:${_hc}">${_evR.length > 0 ? (_evHit/_evR.length*100).toFixed(0) : '—'}%</div>
        </div>
        <div style="text-align:center">
          <div style="font-size:9px;color:var(--text3)">回収率</div>
          <div style="font-size:13px;font-weight:700;font-family:var(--mono);color:${_rc}">${_evBet > 0 ? (_evRec*100).toFixed(0) : '—'}%</div>
        </div>
        <div style="text-align:center">
          <div style="font-size:9px;color:var(--text3)">損益</div>
          <div style="font-size:11px;font-weight:700;font-family:var(--mono);color:${_evRet-_evBet>=0?'var(--green)':'var(--red)'}">${_evBet>0?((_evRet-_evBet>=0?'+':'')+(_evRet-_evBet).toLocaleString()):'—'}</div>
        </div>
      </div>
    </div>`;
  }).join('');

  const _isAdminStats = document.body.classList.contains('admin-mode');
  const _adminOnlyBlocks = _isAdminStats ? `
    <div class="ai-stats-card" style="margin-bottom:0.6rem">
      <div style="font-size:11px;font-weight:700;color:var(--text3);letter-spacing:.06em;margin-bottom:0.5rem">📅 日別集計（直近7日 / EV1.1+）</div>
      <div style="display:flex;gap:8px;overflow-x:auto;padding-bottom:4px;scrollbar-width:none;-webkit-overflow-scrolling:touch">
        ${_dailyCards || '<div style="color:var(--text3);font-size:11px">データなし</div>'}
      </div>
    </div>
    <div class="ai-stats-card" style="margin-bottom:0.6rem">
      <div style="font-size:11px;font-weight:700;color:var(--text3);letter-spacing:.06em;margin-bottom:0.5rem">📊 ${_3dayLabel}</div>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:10px">
        ${_buildScenEV30Panel(_scenAll3)}
        ${_buildScen30Panel(_scen3, _scenAll3)}
        ${_inTep3.length > 0 ? _buildCondBuyPanel30(_inTep3, '🔒 イン鉄板', '1号艇確率75%以上') : ''}
        ${_inNeg3.length > 0 ? _buildCondBuyPanel30(_inNeg3, '⚡ イン否定', '1号艇確率が場平均-Nσ以下（σなし時:10%pt固定）') : ''}
        ${mode30Panel(_hit3, '🎯 的中重視', 2.0)}
        ${mode30Panel(_rec3, '💰 回収重視', 4.0)}
      </div>
    </div>` : '';
  elHistory.innerHTML = _adminOnlyBlocks + `
    <div class="ai-stats-card" style="margin-bottom:0.6rem">
      <div style="font-size:11px;font-weight:700;color:var(--text3);letter-spacing:.06em;margin-bottom:0.5rem">📈 過去30日集計</div>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:10px">
        ${_buildScenEV30Panel(allResultsScenAll)}
        ${_buildScen30Panel(allResultsScen, allResultsScenAll)}
        ${allResultsInTep.length > 0 ? _buildCondBuyPanel30(allResultsInTep, '🔒 イン鉄板', '1号艇確率75%以上') : ''}
        ${allResultsInNeg.length > 0 ? _buildCondBuyPanel30(allResultsInNeg, '⚡ イン否定', '1号艇確率が場平均-Nσ以下（σなし時:10%pt固定）') : ''}
        ${mode30Panel(allResultsHit, '🎯 的中重視', 2.0)}
        ${mode30Panel(allResultsRec, '💰 回収重視', 4.0)}
      </div>
    </div>`;
  updateHistoryTimestamp();
}

// ── TOP PAGE ──

// ════════════════════════════════════════════════════════════════
// 🔒 イン鉄板 / ⚡ イン否定 パネル描画（日別カード用）
// ════════════════════════════════════════════════════════════════
// results: collectResultsForDateInTep / collectResultsForDateInNeg の結果配列
// title:   表示タイトル ('🔒 イン鉄板' など)
// subtitle: 条件説明 ('1号艇確率75%以上' など)
// bgColor / borderColor: テーマ色
function _buildCondBuyPanel_dateCard(results, title, subtitle) {
  const total = results.length;
  if (total === 0) return `
    <div style="background:var(--bg3);border-radius:var(--radius-sm);padding:10px;border:1px solid var(--border)">
      <div style="font-size:10px;font-weight:700;color:var(--text3);text-align:center;margin-bottom:4px">${title}</div>
      <div style="font-size:10px;color:var(--text3);text-align:center;margin-bottom:4px">${subtitle}</div>
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
  results.forEach(r => { if (!venueMap[r.venue]) venueMap[r.venue] = []; venueMap[r.venue].push(r); });

  const comboBadges = combo => (combo || '').split(/[-－−]/).map(n =>
    /^[1-6]$/.test(n.trim())
      ? `<span class="boat-circle b${n.trim()}" style="width:20px;height:20px;font-size:10px;display:inline-flex;align-items:center;justify-content:center;flex-shrink:0">${n.trim()}</span>`
      : ''
  ).join('<span style="color:var(--text3);font-size:11px;margin:0 1px">−</span>');

  const venueBlocks = VENUE_LIST.filter(v => venueMap[v]).map(v => {
    const vrs  = venueMap[v];
    const vHit = vrs.filter(r => r.isHit).length;
    const vTot = vrs.length;
    const vHR  = vHit / vTot;
    const vBet = vrs.reduce((s, r) => s + r.buy3cnt * 100, 0);
    const vRet = vrs.filter(r => r.isHit).reduce((s, r) => s + r.hitOdds, 0);
    const vRec = vBet > 0 ? vRet / vBet : 0;
    const vHC  = vHR >= 0.7 ? 'hit' : vHR >= 0.5 ? 'warn' : '';
    const vRC  = vRec >= 1.0 ? 'over' : vRec >= 0.75 ? 'warn' : '';

    const raceDetails = vrs.map(r => {
      const hitOddsStr = r.isHit && r.hitOdds ? `￥${r.hitOdds.toLocaleString()}` : '';
      const resultStr  = r.actualResult
        ? `<span style="display:inline-flex;align-items:center;gap:2px;flex-shrink:0">${comboBadges(r.actualResult)}</span>`
        : '';
      const hitPart = r.isHit
        ? `<span style="display:inline-flex;align-items:center;gap:4px;flex-shrink:0;flex-wrap:nowrap"><span class="ai-venue-race-hit">🎯 的中</span>${resultStr}<span class="ai-venue-race-odds">${hitOddsStr}</span></span>`
        : `<span style="display:inline-flex;align-items:center;gap:4px;flex-shrink:0;flex-wrap:nowrap"><span class="ai-venue-race-miss">—</span>${resultStr}</span>`;
      return `<div class="ai-race-row" style="display:flex;align-items:center;gap:6px;padding:5px 8px;border-bottom:1px solid var(--border);flex-wrap:nowrap;overflow:hidden">
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
          <span class="ai-venue-stat-val ${vHC}">${(vHR*100).toFixed(0)}%</span>
          <span class="ai-venue-stat-sub">${vHit}/${vTot}R</span>
        </span>
        <span class="ai-venue-stat">
          <span class="ai-venue-stat-label">回収率</span>
          <span class="ai-venue-stat-val ${vRC}">${(vRec*100).toFixed(0)}%</span>
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
      <div style="font-size:10px;font-weight:700;color:var(--text3);text-align:center;margin-bottom:2px">${title}</div>
      <div style="font-size:10px;color:var(--text3);text-align:center;margin-bottom:8px">${subtitle}</div>
      <div style="display:flex;flex-direction:column;gap:5px">
        <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);padding-bottom:4px">
          <span style="font-size:10px;color:var(--text3)">的中率</span>
          <span style="font-size:15px;font-weight:700;font-family:var(--mono);color:${hitColor}">${(hitRate*100).toFixed(0)}%
            <span style="font-size:10px;font-weight:400;color:var(--text3)">${hitCount}/${total}R</span>
          </span>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);padding-bottom:4px">
          <span style="font-size:10px;color:var(--text3)">回収率</span>
          <span style="font-size:15px;font-weight:700;font-family:var(--mono);color:${recColor}">${(recoveryRate*100).toFixed(0)}%</span>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);padding-bottom:4px">
          <span style="font-size:10px;color:var(--text3)">総投資</span>
          <span style="font-size:12px;font-weight:700;font-family:var(--mono);color:var(--text)">${totalBet.toLocaleString()}円</span>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);padding-bottom:4px">
          <span style="font-size:10px;color:var(--text3)">総回収</span>
          <span style="font-size:12px;font-weight:700;font-family:var(--mono);color:${recColor}">${totalReturn.toLocaleString()}円</span>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center">
          <span style="font-size:10px;color:var(--text3)">集計R</span>
          <span style="font-size:12px;font-weight:700;font-family:var(--mono);color:var(--text)">${total}R</span>
        </div>
      </div>
      ${detailHtml}
    </div>`;
}

// ════════════════════════════════════════════════════════════════
// 🔒 イン鉄板 / ⚡ イン否定 パネル描画（30日集計用）
// ════════════════════════════════════════════════════════════════
function _buildCondBuyPanel30(results, title, subtitle) {
  const total = results.length;
  if (total === 0) return `
    <div style="background:var(--bg3);border-radius:var(--radius-sm);padding:12px;border:1px solid var(--border)">
      <div style="font-size:10px;font-weight:700;color:var(--text3);text-align:center;margin-bottom:4px">${title}</div>
      <div style="font-size:10px;color:var(--text3);text-align:center;margin-bottom:4px">${subtitle}</div>
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
  const venueMap30 = {};
  results.forEach(r => { if (!venueMap30[r.venue]) venueMap30[r.venue] = []; venueMap30[r.venue].push(r); });
  const venueRows30 = VENUE_LIST.filter(v => venueMap30[v]).map(v => {
    const vrs  = venueMap30[v];
    const vHit = vrs.filter(r => r.isHit).length;
    const vTot = vrs.length;
    const vBet = vrs.reduce((s, r) => s + r.buy3cnt * 100, 0);
    const vRet = vrs.filter(r => r.isHit).reduce((s, r) => s + r.hitOdds, 0);
    const vRec = vBet > 0 ? vRet / vBet : 0;
    const vHC  = (vHit/vTot) >= 0.7 ? 'var(--green)' : (vHit/vTot) >= 0.5 ? 'var(--orange)' : 'var(--text)';
    const vRC  = vRec >= 1.0 ? 'var(--green)' : vRec >= 0.75 ? 'var(--orange)' : 'var(--text)';
    return `<tr style="border-bottom:1px solid var(--border)">
      <td style="padding:3px 6px;font-size:11px;color:var(--text2);white-space:nowrap">${v}</td>
      <td style="padding:3px 6px;text-align:right;font-size:11px;font-weight:700;color:${vHC}">${(vHit/vTot*100).toFixed(0)}%</td>
      <td style="padding:3px 6px;text-align:right;font-size:10px;color:var(--text3)">${vHit}/${vTot}R</td>
      <td style="padding:3px 6px;text-align:right;font-size:11px;font-weight:700;color:${vRC}">${(vRec*100).toFixed(0)}%</td>
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
      <div style="font-size:10px;font-weight:700;color:var(--text3);text-align:center;margin-bottom:2px">${title}</div>
      <div style="font-size:10px;color:var(--text3);text-align:center;margin-bottom:10px">${subtitle}</div>
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
          </div>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);padding-bottom:5px">
          <span style="font-size:10px;color:var(--text3)">総投資</span>
          <span style="font-size:13px;font-weight:700;font-family:var(--mono);color:var(--text)">${totalBet.toLocaleString()}円</span>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);padding-bottom:5px">
          <span style="font-size:10px;color:var(--text3)">総回収</span>
          <span style="font-size:13px;font-weight:700;font-family:var(--mono);color:${recColor}">${totalReturn.toLocaleString()}円</span>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center">
          <span style="font-size:10px;color:var(--text3)">集計R</span>
          <span style="font-size:13px;font-weight:700;font-family:var(--mono);color:var(--text)">${total}R</span>
        </div>
      </div>
      ${venueDetail30}
    </div>`;
}
