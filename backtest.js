// backtest.js — バックテスト集計系（sample.js から分離）
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
      if (hasNoLapTime(rno, vdata)) {
        excludedList.push({ venue, rno, reason: '1周タイムなし' });
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

// ============================================================
// シナリオ買い 集計用ヘルパー
// ============================================================

// ── シナリオコンボ生成（集計専用）──
// buildScenarioBuyPanel と同一ロジックを pure function 化。
// DATA を一時差し替えして calcScenarioData / calcTenkaiProbs を利用する。
// 戻り値: combo 文字列の配列（最大18点）
function computeScenCombos(venue, vdata, rno) {
  // ── キャッシュ優先参照（メモリ → localStorage → 再計算）──
  // メモリキャッシュ: 当日セッションで renderBuy を開いたレースはここでヒット
  // localStorageキャッシュ: リロード後・過去日もここでヒット（_initScenComboCache で復元済み）
  // 再計算: どちらもなければ従来通り計算（結果はキャッシュしない＝次回も再計算）
  const _ck = `${venue}_${(vdata && vdata.date) || ''}_${rno}`;
  if (_scenComboCache[_ck] && _scenComboCache[_ck].length > 0) {
    return _scenComboCache[_ck].slice();
  }
  // メモリになければ localStorage を直接確認（_initScenComboCache が走る前に
  // collectResultsForDateScen が呼ばれた場合のフォールバック）
  try {
    const _lsRaw = localStorage.getItem(`${_SCEN_CACHE_LS_PREFIX}${_ck}`);
    if (_lsRaw) {
      const _lsCombos = _lsRaw.split(',').filter(Boolean);
      if (_lsCombos.length > 0) {
        _scenComboCache[_ck] = _lsCombos; // メモリにも展開
        return _lsCombos.slice();
      }
    }
  } catch(_e) { /* localStorage 読み取り失敗は無視して再計算へ */ }

  _ensureTenjiCache();
  const rd = vdata.races[String(rno)];
  if (!rd || !rd.boats) return [];

  const slug     = SLUG_MAP[venue] || venue;
  const tKey     = tenjiKey(slug, vdata.date, rno);
  const tenjiData = _tenjiCache[tKey] || null;

  // DATA を一時差し替え（calcScenarioData が DATA.venue に依存）
  const savedDATA  = DATA;
  const savedVenue = currentVenue;
  DATA        = vdata;
  currentVenue = venue;

  let combos = [];
  try {
    const arek     = rd.arek ?? 54.7;
    const rawBoats = rd.boats;
    const ranked   = calcTenkaiProbs(rawBoats, arek);

    let tenjiScoreMap = null;
    if (tenjiData) tenjiScoreMap = calcTenjiScore(ranked, tenjiData, venue, arek);

    // final_prob 計算（renderBuy と同一の2パス加算ボーナス方式）
    // [2026-05-20 修正] 旧: 乗算方式（wSlit欠落）→ 新: renderBuy と完全同一の加算ボーナス方式
    const probTotal        = ranked.reduce((s, b) => s + b.prob, 0) || 1;
    const useMaster        = hasMasterExt() && !!(MASTER_EXT.venue_kimari && MASTER_EXT.venue_kimari[venue]);
    const { wBase, wTenkai, wTenji, wSlit } = calcDynamicWeights(arek);
    const tenkaiOnlyTotal  = ranked.reduce((s, x) => s + (x.tenkai_score ?? x.tenkai_prob), 0) || 1;
    const boatByNo         = {};
    rawBoats.forEach(b => { boatByNo[b.boat] = b; });
    const tenjiRawMap      = {};
    if (tenjiData) {
      Object.keys(tenjiData).filter(k => /^\d+$/.test(k)).forEach(k => {
        const e = tenjiData[k];
        if (e && typeof e.tenji === 'number') tenjiRawMap[parseInt(k)] = e.tenji;
      });
    }
    const hasTenji_sc = (tenjiData != null);

    // 1パス目: 各係数を計算して保存
    ranked.forEach(b => {
      const baseNorm = b.prob / probTotal;
      const prevBoat = boatByNo[b.boat - 1] || null;

      // 展開係数
      let tenkaiCoef = 1.0;
      if (useMaster && baseNorm > 0) {
        const tenkaiNorm = (b.tenkai_score ?? b.tenkai_prob) / tenkaiOnlyTotal;
        tenkaiCoef = Math.min(3.0, Math.max(0.3, tenkaiNorm / baseNorm));
      }
      if (prevBoat) {
        const myStRk = MASTER_EXT?.course_master?.[b.name]?.[String(b.boat)]?.st_rank;
        const pvStRk = MASTER_EXT?.course_master?.[prevBoat.name]?.[String(prevBoat.boat)]?.st_rank;
        if (myStRk != null && pvStRk != null)
          tenkaiCoef = Math.min(3.0, Math.max(0.3, tenkaiCoef + (pvStRk - myStRk) * 0.10));
      }

      // 展示係数
      let tenjiCoef = 1.0;
      if (tenjiScoreMap) tenjiCoef = tenjiScoreMap[`__coef_${b.boat}`] ?? 1.0;
      if (prevBoat && tenjiData) {
        const myTj = tenjiRawMap[b.boat]        ?? null;
        const pvTj = tenjiRawMap[prevBoat.boat] ?? null;
        if (myTj != null && pvTj != null) {
          const DIFF_MULT = { 1:0.0, 2:0.0, 3:0.3, 4:0.4, 5:0.35, 6:0.25 };
          tenjiCoef = Math.min(3.0, Math.max(0.3, tenjiCoef + (pvTj - myTj) * (DIFF_MULT[b.boat] ?? 0.2)));
        }
      }

      // スリット係数（renderBuy と同一ロジック）
      let slitCoef = 1.0;
      if (prevBoat && hasTenji_sc && wSlit > 0) {
        const myTenji   = tenjiRawMap[b.boat]          ?? null;
        const prevTenji = tenjiRawMap[prevBoat.boat]   ?? null;
        const myStRank  = MASTER_EXT?.course_master?.[b.name]?.[String(b.boat)]?.st_rank         ?? null;
        const pvStRank  = MASTER_EXT?.course_master?.[prevBoat.name]?.[String(prevBoat.boat)]?.st_rank ?? null;
        let slitDiff = null;
        if (myTenji != null && prevTenji != null && myStRank != null && pvStRank != null) {
          slitDiff = (prevTenji - myTenji) + (pvStRank - myStRank) * 0.02;
        } else if (myTenji != null && prevTenji != null) {
          slitDiff = prevTenji - myTenji;
        } else if (myStRank != null && pvStRank != null) {
          slitDiff = (pvStRank - myStRank) * 0.02;
        }
        if (slitDiff !== null) {
          const found   = SLIT_LAP_THRESHOLDS.find(t => slitDiff >= t.min);
          const rawCoef = found ? found.coef : 1.0;
          slitCoef = 1.0 + (rawCoef - 1.0) * wSlit;
        }
        // まくりアラートボーナス
        const MAKURI_ALERT_BONUS = 0.20;
        const tenjiAlertOk = (myTenji != null && prevTenji != null) && (prevTenji - myTenji >= 0.10);
        const stAlertOk    = (myStRank != null && pvStRank != null) && (pvStRank - myStRank >= 0.5);
        if (tenjiAlertOk && stAlertOk) slitCoef += MAKURI_ALERT_BONUS;
        slitCoef = Math.min(2.0, Math.max(0.5, slitCoef));
      }

      b._baseNorm   = baseNorm;
      b._tenkaiCoef = tenkaiCoef;
      b._tenjiCoef  = tenjiCoef;
      b._slitCoef   = slitCoef;
    });

    // 2パス目: 加算ボーナス方式で _multi_score を計算（後艇スリットペナルティ含む）
    const BONUS_BASE_TENKAI = 0.15;
    const BONUS_BASE_TENJI  = 0.15;
    const SLIT_BONUS_BASE   = 0.15;
    ranked.forEach(b => {
      const nextBoat = boatByNo[b.boat + 1] || null;
      const tenkaiBonus = BONUS_BASE_TENKAI * (b._tenkaiCoef - 1.0) * wTenkai;
      const tenjiBonus  = BONUS_BASE_TENJI  * (b._tenjiCoef  - 1.0) * wTenji;
      const slitBonus   = SLIT_BONUS_BASE   * (b._slitCoef   - 1.0) * wSlit;

      let slitPenalty = 0;
      if (nextBoat && hasTenji_sc && wSlit > 0) {
        const myTj   = tenjiRawMap[b.boat]          ?? null;
        const nextTj = tenjiRawMap[nextBoat.boat]   ?? null;
        const myStR  = MASTER_EXT?.course_master?.[b.name]?.[String(b.boat)]?.st_rank              ?? null;
        const nextStR= MASTER_EXT?.course_master?.[nextBoat.name]?.[String(nextBoat.boat)]?.st_rank ?? null;
        let nextDiff = null;
        if (myTj != null && nextTj != null && myStR != null && nextStR != null) {
          nextDiff = (myTj - nextTj) + (myStR - nextStR) * 0.02;
        } else if (myTj != null && nextTj != null) {
          nextDiff = myTj - nextTj;
        } else if (myStR != null && nextStR != null) {
          nextDiff = (myStR - nextStR) * 0.02;
        }
        if (nextDiff !== null && nextDiff > 0) {
          const found    = SLIT_LAP_THRESHOLDS.find(t => nextDiff >= t.min);
          const nextCoef = found ? found.coef : 1.0;
          slitPenalty = SLIT_BONUS_BASE * (nextCoef - 1.0) * wSlit;
        }
        // まくりアラート追加ペナルティ
        const nextTenjiAlertOk = (myTj != null && nextTj != null) && (nextTj - myTj <= -0.10);
        const nextStAlertOk    = (myStR != null && nextStR != null) && (nextStR - myStR <= -0.5);
        if (nextTenjiAlertOk && nextStAlertOk) slitPenalty += SLIT_BONUS_BASE * 0.20 * wSlit;
      }

      b._multi_score = Math.max(0.001, b._baseNorm + tenkaiBonus + tenjiBonus + slitBonus - slitPenalty);
    });

    const multiTotal = ranked.reduce((s, b) => s + b._multi_score, 0) || 1;
    ranked.forEach(b => { b.final_prob = b._multi_score / multiTotal; });
    const ranked2 = [...ranked].sort((a, b) => b.final_prob - a.final_prob);

    // scenarioData 計算
    const sd = calcScenarioData(ranked2, rawBoats, tenjiScoreMap);
    if (!sd || !sd.valid) { return; } // 修正: finally で復元されるため早期returnでも安全

    const { scenarioPlace2, scenarioProb } = sd;
    const fp1st = ranked2[0]?.boat;
    const fp2nd = ranked2[1]?.boat;

    function getP2Rank(winnerBoat) {
      if (!scenarioPlace2?.[winnerBoat]) return [];
      const totals = {}; let wSum = 0;
      for (const [k, list] of Object.entries(scenarioPlace2[winnerBoat])) {
        const p = scenarioProb?.[winnerBoat]?.[k] ?? 0; wSum += p;
        (list || []).forEach(x => { totals[x.boat] = (totals[x.boat] ?? 0) + x.p2 * p; });
      }
      if (wSum <= 0)
        return ranked2.filter(r => r.boat !== winnerBoat).sort((a, b) => (b.final_prob ?? 0) - (a.final_prob ?? 0)).map(r => r.boat);
      return Object.entries(totals).sort((a, b) => b[1] - a[1]).map(([b]) => parseInt(b));
    }
    function getP3Rank(w, s) {
      // buildScenarioBuyPanel の getPlace3Ranking と同一ロジック（修正: merged3rdMap参照）
      const thirdAll = sd.merged3rdMap?.[w]?.[s] || [];
      if (thirdAll.length > 0) {
        return thirdAll.filter(x => x.boat !== w && x.boat !== s).slice(0, 3).map(x => x.boat);
      }
      // フォールバック: merged3rdMap がない場合のみ final_prob 順
      return ranked2.filter(r => r.boat !== w && r.boat !== s)
        .sort((a, b) => (b.final_prob ?? 0) - (a.final_prob ?? 0)).map(r => r.boat).slice(0, 3);
    }
    function mkBlock(w, s, thirds) {
      const out = [];
      thirds.forEach(t => { if (t !== w && t !== s) { out.push(`${w}-${s}-${t}`); out.push(`${w}-${t}-${s}`); } });
      return out;
    }

    const p2r1   = getP2Rank(fp1st);
    const p2r2   = getP2Rank(fp2nd);
    const sA = p2r1[0], sB = p2r1[1], sC = p2r2[0];
    const b1 = sA != null ? mkBlock(fp1st, sA, getP3Rank(fp1st, sA)) : [];
    const b2 = sB != null ? mkBlock(fp1st, sB, getP3Rank(fp1st, sB)) : [];
    const b3 = sC != null ? mkBlock(fp2nd, sC, getP3Rank(fp2nd, sC)) : [];

    const seen = new Set();
    [b1, b2, b3].forEach(blk => blk.forEach(c => { if (!seen.has(c)) { seen.add(c); combos.push(c); } }));

  } catch(e) {
    console.warn('[computeScenCombos] error:', e);
    combos = [];
  } finally {
    // 修正: 例外・早期return どちらのパスでも必ず復元する
    DATA        = savedDATA;
    currentVenue = savedVenue;
  }
  return combos;
}

// ── computeScenCombos の拡張版：コンボ配列に加えて想定的中率も返す ──
// 戻り値: { combos: string[], hitProbEst: number|null }
// hitProbEst: 全コンボの calcScenarioComboProb 合算値（0〜1）。計算不可なら null
function computeScenCombosWithEV(venue, vdata, rno) {
  // キャッシュ確認（コンボは _scenComboCache から取得）
  const _ck = `${venue}_${(vdata && vdata.date) || ''}_${rno}`;

  // まずコンボを従来の computeScenCombos で取得
  const combos = computeScenCombos(venue, vdata, rno);
  if (!combos || combos.length === 0) return { combos: [], hitProbEst: null };

  // hitProbEst の計算: sd を再取得して calcScenarioComboProb を使う
  // （computeScenCombos 内で計算済みの sd に外からアクセスできないため再計算）
  _ensureTenjiCache();
  const rd = vdata.races[String(rno)];
  if (!rd || !rd.boats) return { combos, hitProbEst: null };

  const slug      = SLUG_MAP[venue] || venue;
  const tKey      = tenjiKey(slug, vdata.date, rno);
  const tenjiData = _tenjiCache[tKey] || null;

  const savedDATA  = DATA;
  const savedVenue = currentVenue;
  DATA        = vdata;
  currentVenue = venue;

  let hitProbEst = null;
  try {
    const arek    = rd.arek ?? 54.7;
    const ranked  = calcTenkaiProbs(rd.boats, arek);
    let tenjiScoreMap = null;
    if (tenjiData) tenjiScoreMap = calcTenjiScore(ranked, tenjiData, venue, arek);

    // final_prob を computeScenCombos と同一の2パス加算ボーナス方式で計算
    const probTotal       = ranked.reduce((s, b) => s + b.prob, 0) || 1;
    const useMaster       = hasMasterExt() && !!(MASTER_EXT.venue_kimari && MASTER_EXT.venue_kimari[venue]);
    const { wBase, wTenkai, wTenji, wSlit } = calcDynamicWeights(arek);
    const tenkaiOnlyTotal = ranked.reduce((s, x) => s + (x.tenkai_score ?? x.tenkai_prob), 0) || 1;
    const boatByNo        = {};
    rd.boats.forEach(b => { boatByNo[b.boat] = b; });
    const tenjiRawMap = {};
    if (tenjiData) {
      Object.keys(tenjiData).filter(k => /^\d+$/.test(k)).forEach(k => {
        const e = tenjiData[k];
        if (e && typeof e.tenji === 'number') tenjiRawMap[parseInt(k)] = e.tenji;
      });
    }
    const hasTenji_sc = (tenjiData != null);

    ranked.forEach(b => {
      const baseNorm = b.prob / probTotal;
      const prevBoat = boatByNo[b.boat - 1] || null;
      let tenkaiCoef = 1.0;
      if (useMaster && baseNorm > 0) {
        const tenkaiNorm = (b.tenkai_score ?? b.tenkai_prob) / tenkaiOnlyTotal;
        tenkaiCoef = Math.min(3.0, Math.max(0.3, tenkaiNorm / baseNorm));
      }
      if (prevBoat) {
        const myStRk = MASTER_EXT?.course_master?.[b.name]?.[String(b.boat)]?.st_rank;
        const pvStRk = MASTER_EXT?.course_master?.[prevBoat.name]?.[String(prevBoat.boat)]?.st_rank;
        if (myStRk != null && pvStRk != null)
          tenkaiCoef = Math.min(3.0, Math.max(0.3, tenkaiCoef + (pvStRk - myStRk) * 0.10));
      }
      let tenjiCoef = 1.0;
      if (tenjiScoreMap) tenjiCoef = tenjiScoreMap[`__coef_${b.boat}`] ?? 1.0;
      if (prevBoat && tenjiData) {
        const myTj = tenjiRawMap[b.boat] ?? null;
        const pvTj = tenjiRawMap[prevBoat.boat] ?? null;
        if (myTj != null && pvTj != null) {
          const DIFF_MULT = { 1:0.0, 2:0.0, 3:0.3, 4:0.4, 5:0.35, 6:0.25 };
          tenjiCoef = Math.min(3.0, Math.max(0.3, tenjiCoef + (pvTj - myTj) * (DIFF_MULT[b.boat] ?? 0.2)));
        }
      }
      let slitCoef = 1.0;
      if (prevBoat && hasTenji_sc && wSlit > 0) {
        const myTenji   = tenjiRawMap[b.boat]        ?? null;
        const prevTenji = tenjiRawMap[prevBoat.boat] ?? null;
        const myStRank  = MASTER_EXT?.course_master?.[b.name]?.[String(b.boat)]?.st_rank         ?? null;
        const pvStRank  = MASTER_EXT?.course_master?.[prevBoat.name]?.[String(prevBoat.boat)]?.st_rank ?? null;
        let slitDiff = null;
        if (myTenji != null && prevTenji != null && myStRank != null && pvStRank != null)
          slitDiff = (prevTenji - myTenji) + (pvStRank - myStRank) * 0.02;
        else if (myTenji != null && prevTenji != null)
          slitDiff = prevTenji - myTenji;
        else if (myStRank != null && pvStRank != null)
          slitDiff = (pvStRank - myStRank) * 0.02;
        if (slitDiff !== null) {
          const found   = SLIT_LAP_THRESHOLDS.find(t => slitDiff >= t.min);
          const rawCoef = found ? found.coef : 1.0;
          slitCoef = 1.0 + (rawCoef - 1.0) * wSlit;
        }
        const MAKURI_ALERT_BONUS = 0.20;
        const tenjiAlertOk = (myTenji != null && prevTenji != null) && (prevTenji - myTenji >= 0.10);
        const stAlertOk    = (myStRank != null && pvStRank != null) && (pvStRank - myStRank >= 0.5);
        if (tenjiAlertOk && stAlertOk) slitCoef += MAKURI_ALERT_BONUS;
        slitCoef = Math.min(2.0, Math.max(0.5, slitCoef));
      }
      b._baseNorm   = baseNorm;
      b._tenkaiCoef = tenkaiCoef;
      b._tenjiCoef  = tenjiCoef;
      b._slitCoef   = slitCoef;
    });

    const BONUS_BASE_TENKAI = 0.15;
    const BONUS_BASE_TENJI  = 0.15;
    const SLIT_BONUS_BASE   = 0.15;
    ranked.forEach(b => {
      const nextBoat    = boatByNo[b.boat + 1] || null;
      const tenkaiBonus = BONUS_BASE_TENKAI * (b._tenkaiCoef - 1.0) * wTenkai;
      const tenjiBonus  = BONUS_BASE_TENJI  * (b._tenjiCoef  - 1.0) * wTenji;
      const slitBonus   = SLIT_BONUS_BASE   * (b._slitCoef   - 1.0) * wSlit;
      let slitPenalty = 0;
      if (nextBoat && hasTenji_sc && wSlit > 0) {
        const myTj   = tenjiRawMap[b.boat]          ?? null;
        const nextTj = tenjiRawMap[nextBoat.boat]   ?? null;
        const myStR  = MASTER_EXT?.course_master?.[b.name]?.[String(b.boat)]?.st_rank              ?? null;
        const nextStR= MASTER_EXT?.course_master?.[nextBoat.name]?.[String(nextBoat.boat)]?.st_rank ?? null;
        let nextDiff = null;
        if (myTj != null && nextTj != null && myStR != null && nextStR != null)
          nextDiff = (myTj - nextTj) + (myStR - nextStR) * 0.02;
        else if (myTj != null && nextTj != null)
          nextDiff = myTj - nextTj;
        else if (myStR != null && nextStR != null)
          nextDiff = (myStR - nextStR) * 0.02;
        if (nextDiff !== null && nextDiff > 0) {
          const found    = SLIT_LAP_THRESHOLDS.find(t => nextDiff >= t.min);
          const nextCoef = found ? found.coef : 1.0;
          slitPenalty = SLIT_BONUS_BASE * (nextCoef - 1.0) * wSlit;
        }
        const nextTenjiAlertOk = (myTj != null && nextTj != null) && (nextTj - myTj <= -0.10);
        const nextStAlertOk    = (myStR != null && nextStR != null) && (nextStR - myStR <= -0.5);
        if (nextTenjiAlertOk && nextStAlertOk) slitPenalty += SLIT_BONUS_BASE * 0.20 * wSlit;
      }
      b._multi_score = Math.max(0.001, b._baseNorm + tenkaiBonus + tenjiBonus + slitBonus - slitPenalty);
    });

    const multiTotal = ranked.reduce((s, b) => s + b._multi_score, 0) || 1;
    ranked.forEach(b => { b.final_prob = b._multi_score / multiTotal; });
    const ranked2 = [...ranked].sort((a, b) => b.final_prob - a.final_prob);

    const sd = calcScenarioData(ranked2, rd.boats, tenjiScoreMap);
    if (sd && sd.valid) {
      // calcScenarioComboProb と同一ロジックで全コンボの合算的中率を計算
      let probSum  = 0;
      let hasAny   = false;
      const { scenarioProb, scenarioPlace2, merged3rdMap, kimariTypes } = sd;
      combos.forEach(c => {
        const parts = c.split('-').map(Number);
        const [first, second, third] = parts;
        if (!scenarioProb?.[first] || !kimariTypes?.length) return;
        for (const kimari of kimariTypes) {
          const scenP = scenarioProb[first]?.[kimari] ?? 0;
          if (scenP <= 0) continue;
          const p2Item = (scenarioPlace2?.[first]?.[kimari] || []).find(x => x.boat === second);
          const p2 = p2Item?.p2 ?? 0;
          if (p2 <= 0) continue;
          const r3Item = (merged3rdMap?.[first]?.[second] || []).find(x => x.boat === third);
          const r3 = r3Item?.r3 ?? null;
          if (r3 == null) continue;
          probSum += scenP * p2 * r3;
          hasAny = true;
        }
      });
      if (hasAny) hitProbEst = probSum;
    } else {
      // フォールバック: sd が取れない場合（過去日で展示キャッシュなし・MASTER未ロード等）
      // final_prob を使った独立試行近似で hitProbEst を推計する。
      // ※ 当日レース（sd.valid=true）には到達しないため既存動作に影響なし。
      // ※ キャリブレーション用の近似値であり、買い目生成には使わない。
      const fpMap = {};
      ranked2.forEach(b => { fpMap[b.boat] = b.final_prob ?? 0; });
      let fbSum = 0;
      let fbAny = false;
      combos.forEach(c => {
        const parts = c.split('-').map(Number);
        const [first, second, third] = parts;
        if (!first || !second || !third) return;
        const fp1 = fpMap[first]  ?? 0;
        const fp2 = fpMap[second] ?? 0;
        const fp3 = fpMap[third]  ?? 0;
        // 条件付き確率の近似: P(1着=first) × P(2着=second|first) × P(3着=third|first,second)
        // 分母から前着艇の確率を除いて正規化（独立試行近似）
        const rem2 = Math.max(1 - fp1, 0.001);
        const rem3 = Math.max(1 - fp1 - fp2, 0.001);
        fbSum += fp1 * (fp2 / rem2) * (fp3 / rem3);
        fbAny = true;
      });
      if (fbAny && fbSum > 0) hitProbEst = Math.min(1, fbSum);
    }
  } catch(e) {
    console.warn('[computeScenCombosWithEV] error:', e);
  } finally {
    // 修正: 例外・正常終了どちらのパスでも必ず復元する
    DATA        = savedDATA;
    currentVenue = savedVenue;
  }
  return { combos, hitProbEst };
}

// ── シナリオ買い 1日分集計（合成オッズ2.0倍以上）──
// ・合成オッズフィルター・見送り推奨フィルター なし
// ・データ不足・進入変更・結果未確定は除外（最低限の品質確保）
// includeAll=true のとき合成オッズフィルターをスキップ（フィルターなし全件集計用）
function collectResultsForDateScen(dateStr, includeAll = false) {
  const dataForDate = getDataForDate(dateStr);
  const results = [];

  VENUE_LIST.forEach(venue => {
    const vdata = dataForDate[venue];
    if (!vdata || !vdata.races) return;
    if (venue === '江戸川') return;

    const slug = SLUG_MAP[venue] || venue;

    Object.entries(vdata.races).sort((a, b) => +a[0] - +b[0]).forEach(([rnoStr, rd]) => {
      const rno = parseInt(rnoStr);
      if (!rd || !rd.boats) return;

      const rKey     = resultKey(slug, vdata.date, rno);
      const resultRd = RESULT_DATA[rKey];
      if (!resultRd || !resultRd.sanrentan || resultRd.sanrentan.length === 0) return;
      if (hasInsufficient(rd))             return;
      if (hasCourseOrderChange(rno, vdata)) return;
      if (hasNoLapTime(rno, vdata))         return;

      const { combos, hitProbEst } = computeScenCombosWithEV(venue, vdata, rno);
      if (!combos || combos.length === 0) return;

      const resultSan3 = resultRd.sanrentan[0]
        ? new Set([normalizeCombo(resultRd.sanrentan[0].combo)])
        : new Set();

      // ODDS_DATA からコンボごとのオッズを取得して合成オッズを計算
      // 合成オッズ = 1 / Σ(1/各コンボオッズ)  ← 的中率×合成オッズ≒回収率の分母
      const oddsMap3t = ODDS_DATA?.[vdata.date]?.[venue]?.[String(rno)]?.['3t'] ?? {};
      let synthDenom = 0, synthCount = 0;
      combos.forEach(c => {
        const ov = oddsMap3t[normalizeCombo(c)] ?? null;
        if (ov != null && ov > 0) { synthDenom += 1 / ov; synthCount++; }
      });
      const synthOdds = (synthCount > 0 && synthDenom > 0) ? 1 / synthDenom : null;

      // ── 合成オッズフィルター: 2.0倍未満は見送り ──
      // ODDS_DATA未取得(null)の場合は参加扱い（オッズ欠損で除外しすぎない）
      // includeAll=true のときはフィルターをスキップ
      const SCEN_SYNTH_MIN = 2.0;
      if (!includeAll && synthOdds !== null && synthOdds < SCEN_SYNTH_MIN) return;

      // 期待値 = 合成オッズ × 想定的中率（真の期待値フィルター）
      const expectedValue = (synthOdds != null && hitProbEst != null)
        ? synthOdds * hitProbEst
        : null;

      let isHit = false, hitOdds = 0, hitCombo = '';
      for (const c of combos) {
        const nc = normalizeCombo(c);
        if (resultSan3.has(nc)) {
          isHit    = true;
          hitCombo = nc;
          hitOdds  = resultRd.sanrentan[0]?.odds ?? 0;
          break;
        }
      }

      // ── 指数値・予想情報（hit/rec と同等に揃える）──
      const probTotal_sc = rd.boats.reduce((s, b) => s + (b.prob ?? 0), 0) || 1;
      const tenkaiTotal_sc = rd.boats.reduce((s, b) => s + (b.tenkai_score ?? b.prob ?? 0), 0) || 1;
      const ranked_sc = rd.boats.map(b => {
        const baseNorm   = (b.prob ?? 0) / probTotal_sc;
        const tenkaiCoef = (baseNorm > 0 && b.tenkai_score != null)
          ? Math.min(3.0, Math.max(0.3, (b.tenkai_score / tenkaiTotal_sc) / baseNorm))
          : 1.0;
        const tenjiCoef  = b.tenji_score != null ? b.tenji_score : null;
        return { ...b, _csv_base: baseNorm, _csv_tenkai: tenkaiCoef, _csv_tenji: tenjiCoef };
      }).sort((a, b) => (b.prob ?? 0) - (a.prob ?? 0));
      const boat1data_sc = ranked_sc.find(b => b.boat === 1);

      results.push({
        venue, rno,
        buyCnt: combos.length,
        buyCombos: combos.join(' / '),
        isHit, hitOdds, hitCombo,
        avgOdds: synthOdds,
        hitProbEst,
        expectedValue,
        arek:      (rd.arek ?? 54.7).toFixed(1),
        hasTenji:  !!(ranked_sc[0]?._csv_tenji !== null),
        predTop3:  ranked_sc.slice(0, 3).map(b => b.boat).join('-'),
        pred1boat:    ranked_sc[0]?.boat    || '',
        pred1_base:   ranked_sc[0]?._csv_base   != null ? ranked_sc[0]._csv_base.toFixed(4)   : '',
        pred1_tenkai: ranked_sc[0]?._csv_tenkai  != null ? ranked_sc[0]._csv_tenkai.toFixed(4)  : '',
        pred1_tenji:  ranked_sc[0]?._csv_tenji   != null ? ranked_sc[0]._csv_tenji.toFixed(4)   : '',
        boat1_base:   boat1data_sc?._csv_base   != null ? boat1data_sc._csv_base.toFixed(4)   : '',
        boat1_tenkai: boat1data_sc?._csv_tenkai  != null ? boat1data_sc._csv_tenkai.toFixed(4)  : '',
        boat1_tenji:  boat1data_sc?._csv_tenji   != null ? boat1data_sc._csv_tenji.toFixed(4)   : '',
        actualResult: resultRd.sanrentan?.[0]?.combo || '',
        actualKimari: resultRd.kimari || '',
      });
    });
  });

  return results;
}

// ── シナリオ買い フィルターなし参考サブセクション（日別カード用）──
// _buildScenAllSubSection30 と同等だが日別カード用にトップレベル関数として定義
function _buildScenAllSubSectionDay(rAll) {
  if (!rAll || rAll.length === 0) return '';
  const aTotal  = rAll.length;
  const aHit    = rAll.filter(r => r.isHit).length;
  const aRate   = aHit / aTotal;
  const aBet    = rAll.reduce((s, r) => s + r.buyCnt * 100, 0);
  const aReturn = rAll.filter(r => r.isHit).reduce((s, r) => s + r.hitOdds, 0);
  const aRec    = aBet > 0 ? aReturn / aBet : 0;
  const aHC     = aRate >= 0.7 ? 'var(--green)' : aRate >= 0.5 ? 'var(--orange)' : 'var(--text)';
  const aRC     = aRec  >= 1.0 ? 'var(--green)' : aRec  >= 0.75 ? 'var(--orange)' : 'var(--text)';
  const aSynth  = rAll.filter(r => r.avgOdds != null);
  const aAvgSO  = aSynth.length > 0 ? aSynth.reduce((s, r) => s + r.avgOdds, 0) / aSynth.length : null;
  const aSOStr  = aAvgSO != null ? `${aAvgSO.toFixed(1)}倍` : '—';

  // 会場別内訳
  const aVenueMap = {};
  rAll.forEach(r => { if (!aVenueMap[r.venue]) aVenueMap[r.venue] = []; aVenueMap[r.venue].push(r); });
  const aVenueRows = VENUE_LIST.filter(v => aVenueMap[v]).map(v => {
    const vrs  = aVenueMap[v];
    const vHit = vrs.filter(r => r.isHit).length;
    const vTot = vrs.length;
    const vBet = vrs.reduce((s, r) => s + r.buyCnt * 100, 0);
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
  const aVenueDetail = aVenueRows ? `
    <details style="margin-top:5px">
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
          <tbody>${aVenueRows}</tbody>
        </table>
      </div>
    </details>` : '';

  return `
    <details style="margin-top:6px">
      <summary style="font-size:11px;font-weight:700;color:var(--text3);cursor:pointer;list-style:none;display:flex;align-items:center;gap:4px;padding:2px 0">
        <span style="font-size:10px">▶</span> フィルターなし参考
      </summary>
      <div style="margin-top:5px;padding:7px 8px;background:var(--bg4);border-radius:6px;border:1px dashed var(--border);font-size:11px">
        <div style="display:flex;justify-content:space-between;border-bottom:1px solid var(--border);padding-bottom:3px;margin-bottom:3px">
          <span style="color:var(--text3)">的中率</span>
          <span style="font-weight:700;font-family:var(--mono);color:${aHC}">${(aRate*100).toFixed(0)}% <span style="font-size:10px;font-weight:400;color:var(--text3)">${aHit}/${aTotal}R</span></span>
        </div>
        <div style="display:flex;justify-content:space-between;border-bottom:1px solid var(--border);padding-bottom:3px;margin-bottom:3px">
          <span style="color:var(--text3)">回収率</span>
          <span style="font-weight:700;font-family:var(--mono);color:${aRC}">${(aRec*100).toFixed(0)}%</span>
        </div>
        <div style="display:flex;justify-content:space-between;border-bottom:1px solid var(--border);padding-bottom:3px;margin-bottom:3px">
          <span style="color:var(--text3)">総投資</span>
          <span style="font-family:var(--mono);color:var(--text)">${aBet.toLocaleString()}円</span>
        </div>
        <div style="display:flex;justify-content:space-between;border-bottom:1px solid var(--border);padding-bottom:3px;margin-bottom:3px">
          <span style="color:var(--text3)">総回収</span>
          <span style="font-family:var(--mono);color:${aRC}">${aReturn.toLocaleString()}円</span>
        </div>
        <div style="display:flex;justify-content:space-between;border-bottom:1px solid var(--border);padding-bottom:3px;margin-bottom:3px">
          <span style="color:var(--text3)">集計R</span>
          <span style="font-family:var(--mono);color:var(--text)">${aTotal}R</span>
        </div>
        <div style="display:flex;justify-content:space-between">
          <span style="color:var(--text3)">合成オッズ</span>
          <span style="font-family:var(--mono);color:var(--text)">${aSOStr}</span>
        </div>
        ${aVenueDetail}
      </div>
    </details>`;
}

// ── シナリオ買い 日別カード内パネル ──
// resultsAll: 合成オッズフィルターなしの全件（比較表示用）
function _buildScenPanel_dateCard(results, resultsAll) {
  const total = results.length;

  if (total === 0) return `
    <div style="background:var(--bg3);border-radius:var(--radius-sm);padding:10px;border:1px solid var(--border)">
      <div style="font-size:10px;font-weight:700;color:var(--text3);text-align:center;margin-bottom:4px">🎲 シナリオ買い</div>
      <div style="font-size:10px;color:var(--text3);text-align:center;margin-bottom:4px">合成オッズ2.0倍以上</div>
      <div style="color:var(--text3);font-size:11px;text-align:center;padding:0.3rem 0">集計対象なし</div>
      ${_buildScenAllSubSectionDay(resultsAll)}
    </div>`;

  const hitCount     = results.filter(r => r.isHit).length;
  const hitRate      = hitCount / total;
  const totalBet     = results.reduce((s, r) => s + r.buyCnt * 100, 0);
  const totalReturn  = results.filter(r => r.isHit).reduce((s, r) => s + r.hitOdds, 0);
  const recoveryRate = totalBet > 0 ? totalReturn / totalBet : 0;
  const hitColor = hitRate      >= 0.7 ? 'var(--green)' : hitRate >= 0.5 ? 'var(--orange)' : 'var(--text)';
  const recColor = recoveryRate >= 1.0 ? 'var(--green)' : recoveryRate >= 0.75 ? 'var(--orange)' : 'var(--text)';

  // 合成オッズの全レース平均（合成オッズが取れているレースだけ集計）
  // 合成オッズ = 1 / Σ(1/各コンボオッズ)  ← 各レースで collectResultsForDateScen が計算済み
  // ここでは「レース単位の合成オッズ」を算術平均して傾向を把握する
  const synthResults  = results.filter(r => r.avgOdds != null);
  const avgSynthOdds  = synthResults.length > 0
    ? synthResults.reduce((s, r) => s + r.avgOdds, 0) / synthResults.length
    : null;
  const synthOddsStr  = avgSynthOdds != null ? `${avgSynthOdds.toFixed(1)}倍` : '—';

  const venueMap = {};
  results.forEach(r => { if (!venueMap[r.venue]) venueMap[r.venue] = []; venueMap[r.venue].push(r); });
  const venueBlocks = VENUE_LIST.filter(v => venueMap[v]).map(v => {
    const vrs  = venueMap[v];
    const vHit = vrs.filter(r => r.isHit).length;
    const vTot = vrs.length;
    const vHR  = vHit / vTot;
    const vBet = vrs.reduce((s, r) => s + r.buyCnt * 100, 0);
    const vRet = vrs.filter(r => r.isHit).reduce((s, r) => s + r.hitOdds, 0);
    const vRec = vBet > 0 ? vRet / vBet : 0;
    const vHC  = vHR >= 0.7 ? 'hit' : vHR >= 0.5 ? 'warn' : '';
    const vRC  = vRec >= 1.0 ? 'over' : vRec >= 0.75 ? 'warn' : '';

    const comboBadges = combo => (combo || '').split(/[-－−]/).map(n =>
      /^[1-6]$/.test(n.trim())
        ? `<span class="boat-circle b${n.trim()}" style="width:20px;height:20px;font-size:10px;display:inline-flex;align-items:center;justify-content:center;flex-shrink:0">${n.trim()}</span>`
        : ''
    ).join('<span style="color:var(--text3);font-size:11px;margin:0 1px">−</span>');

    const raceDetails = vrs.map(r => {
      const hitOddsStr = r.isHit && r.hitOdds ? `￥${r.hitOdds.toLocaleString()}` : '';
      const resultStr  = r.actualResult ? `<span style="display:inline-flex;align-items:center;gap:2px;margin-left:4px">${comboBadges(r.actualResult)}</span>` : '';
      const hitPart    = r.isHit
        ? `<span class="ai-venue-race-hit" style="flex-shrink:0">🎯 的中</span>${resultStr}<span class="ai-venue-race-odds" style="flex-shrink:0">${hitOddsStr}</span>`
        : `<span class="ai-venue-race-miss" style="flex-shrink:0">—</span>${resultStr}`;
      return `<div class="ai-race-row" style="display:flex;align-items:center;gap:6px;padding:5px 8px;border-bottom:1px solid var(--border)">
        <span class="ai-venue-race-no" style="flex-shrink:0">${r.rno}R</span>
        <span class="ai-venue-race-cnt" style="flex-shrink:0">${r.buyCnt}点</span>
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
      <div style="font-size:10px;font-weight:700;color:var(--text3);text-align:center;margin-bottom:2px">🎲 シナリオ買い</div>
      <div style="font-size:10px;color:var(--text3);text-align:center;margin-bottom:8px">合成オッズ2.0倍以上</div>
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
        <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);padding-bottom:4px">
          <span style="font-size:10px;color:var(--text3)">合成オッズ</span>
          <span style="font-size:12px;font-weight:700;font-family:var(--mono);color:var(--text)">${synthOddsStr}</span>
        </div>
      </div>
      ${detailHtml}
      ${_buildScenAllSubSectionDay(resultsAll)}
    </div>`;
}

// ── シナリオ買い 30日集計サマリーパネル ──
// resultsAll: 合成オッズフィルターなしの全件（比較表示用）
function _buildScen30Panel(results, resultsAll) {
  const total = results.length;
  if (total === 0) return `
    <div style="background:var(--bg3);border-radius:var(--radius-sm);padding:12px;border:1px solid var(--border)">
      <div style="font-size:10px;font-weight:700;color:var(--text3);text-align:center;margin-bottom:4px">🎲 シナリオ買い</div>
      <div style="font-size:10px;color:var(--text3);text-align:center;margin-bottom:4px">合成オッズ2.0倍以上</div>
      <div style="color:var(--text3);font-size:11px;text-align:center;padding:0.3rem 0">集計対象なし</div>
      ${_buildScenAllSubSection30(resultsAll)}
    </div>`;

  const hitCount     = results.filter(r => r.isHit).length;
  const hitRate      = hitCount / total;
  const totalBet     = results.reduce((s, r) => s + r.buyCnt * 100, 0);
  const totalReturn  = results.filter(r => r.isHit).reduce((s, r) => s + r.hitOdds, 0);
  const recoveryRate = totalBet > 0 ? totalReturn / totalBet : 0;
  const hitColor = hitRate      >= 0.7 ? 'var(--green)' : hitRate >= 0.5 ? 'var(--orange)' : 'var(--text)';
  const recColor = recoveryRate >= 1.0 ? 'var(--green)' : recoveryRate >= 0.75 ? 'var(--orange)' : 'var(--text)';

  // 合成オッズの全レース平均（合成オッズが取れているレースだけ集計）
  const synthResults30    = results.filter(r => r.avgOdds != null);
  const avgSynthOdds30    = synthResults30.length > 0
    ? synthResults30.reduce((s, r) => s + r.avgOdds, 0) / synthResults30.length
    : null;
  const synthOddsStr30    = avgSynthOdds30 != null ? `${avgSynthOdds30.toFixed(1)}倍` : '—';

  const venueMap30 = {};
  results.forEach(r => { if (!venueMap30[r.venue]) venueMap30[r.venue] = []; venueMap30[r.venue].push(r); });
  const venueRows30 = VENUE_LIST.filter(v => venueMap30[v]).map(v => {
    const vrs  = venueMap30[v];
    const vHit = vrs.filter(r => r.isHit).length;
    const vTot = vrs.length;
    const vBet = vrs.reduce((s, r) => s + r.buyCnt * 100, 0);
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
      <div style="font-size:10px;font-weight:700;color:var(--text3);text-align:center;margin-bottom:2px">🎲 シナリオ買い</div>
      <div style="font-size:10px;color:var(--text3);text-align:center;margin-bottom:10px">合成オッズ2.0倍以上</div>
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
        <div style="display:flex;justify-content:space-between;align-items:center;border-top:1px solid var(--border);padding-top:5px">
          <span style="font-size:10px;color:var(--text3)">合成オッズ</span>
          <span style="font-size:13px;font-weight:700;font-family:var(--mono);color:var(--text)">${synthOddsStr30}</span>
        </div>
      </div>
      ${venueDetail30}
      ${_buildScenAllSubSection30(resultsAll)}
    </div>`;
}

// ── シナリオ買い 30日フィルターなしサブセクション ──
function _buildScenAllSubSection30(rAll) {
  if (!rAll || rAll.length === 0) return '';
  const aTotal  = rAll.length;
  const aHit    = rAll.filter(r => r.isHit).length;
  const aRate   = aHit / aTotal;
  const aBet    = rAll.reduce((s, r) => s + r.buyCnt * 100, 0);
  const aReturn = rAll.filter(r => r.isHit).reduce((s, r) => s + r.hitOdds, 0);
  const aRec    = aBet > 0 ? aReturn / aBet : 0;
  const aHC     = aRate >= 0.7 ? 'var(--green)' : aRate >= 0.5 ? 'var(--orange)' : 'var(--text)';
  const aRC     = aRec  >= 1.0 ? 'var(--green)' : aRec  >= 0.75 ? 'var(--orange)' : 'var(--text)';
  const aSynth  = rAll.filter(r => r.avgOdds != null);
  const aAvgSO  = aSynth.length > 0 ? aSynth.reduce((s, r) => s + r.avgOdds, 0) / aSynth.length : null;
  const aSOStr  = aAvgSO != null ? `${aAvgSO.toFixed(1)}倍` : '—';

  // 会場別内訳（フィルターなし）
  const aVenueMap = {};
  rAll.forEach(r => { if (!aVenueMap[r.venue]) aVenueMap[r.venue] = []; aVenueMap[r.venue].push(r); });
  const aVenueRows = VENUE_LIST.filter(v => aVenueMap[v]).map(v => {
    const vrs  = aVenueMap[v];
    const vHit = vrs.filter(r => r.isHit).length;
    const vTot = vrs.length;
    const vBet = vrs.reduce((s, r) => s + r.buyCnt * 100, 0);
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
  const aVenueDetail = aVenueRows ? `
    <details style="margin-top:5px">
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
          <tbody>${aVenueRows}</tbody>
        </table>
      </div>
    </details>` : '';

  return `
    <details style="margin-top:6px">
      <summary style="font-size:11px;font-weight:700;color:var(--text3);cursor:pointer;list-style:none;display:flex;align-items:center;gap:4px;padding:2px 0">
        <span style="font-size:10px">▶</span> フィルターなし参考
      </summary>
      <div style="margin-top:5px;padding:8px 10px;background:var(--bg4);border-radius:6px;border:1px dashed var(--border);font-size:11px;display:flex;flex-direction:column;gap:4px">
        <div style="display:flex;justify-content:space-between;border-bottom:1px solid var(--border);padding-bottom:3px">
          <span style="color:var(--text3)">的中率</span>
          <span style="font-weight:700;font-family:var(--mono);color:${aHC}">${(aRate*100).toFixed(0)}% <span style="font-size:10px;font-weight:400;color:var(--text3)">${aHit}/${aTotal}R</span></span>
        </div>
        <div style="display:flex;justify-content:space-between;border-bottom:1px solid var(--border);padding-bottom:3px">
          <span style="color:var(--text3)">回収率</span>
          <span style="font-weight:700;font-family:var(--mono);color:${aRC}">${(aRec*100).toFixed(0)}%</span>
        </div>
        <div style="display:flex;justify-content:space-between;border-bottom:1px solid var(--border);padding-bottom:3px">
          <span style="color:var(--text3)">総投資</span>
          <span style="font-family:var(--mono);color:var(--text)">${aBet.toLocaleString()}円</span>
        </div>
        <div style="display:flex;justify-content:space-between;border-bottom:1px solid var(--border);padding-bottom:3px">
          <span style="color:var(--text3)">総回収</span>
          <span style="font-family:var(--mono);color:${aRC}">${aReturn.toLocaleString()}円</span>
        </div>
        <div style="display:flex;justify-content:space-between;border-bottom:1px solid var(--border);padding-bottom:3px">
          <span style="color:var(--text3)">集計R</span>
          <span style="font-family:var(--mono);color:var(--text)">${aTotal}R</span>
        </div>
        <div style="display:flex;justify-content:space-between">
          <span style="color:var(--text3)">合成オッズ</span>
          <span style="font-family:var(--mono);color:var(--text)">${aSOStr}</span>
        </div>
        ${aVenueDetail}
      </div>
    </details>`;
}

// ════════════════════════════════════════════════════════════════
// ⚡ 期待値1.1 パネル（30日集計サマリー用）
// ════════════════════════════════════════════════════════════════
// resultsScenAll: collectResultsForDateScen(d, true) の全件配列（30日分を結合済み）
// 期待値 = avgOdds × hitProbEst >= 1.1 のレースのみ抽出して集計
function _buildScenEV30Panel(resultsScenAll) {
  const EV_THRESHOLD = 1.1;
  const results = resultsScenAll.filter(r =>
    r.expectedValue != null && r.expectedValue >= EV_THRESHOLD
  );
  const total = results.length;

  if (total === 0) return `
    <div style="background:var(--bg3);border-radius:var(--radius-sm);padding:12px;border:1px solid var(--border)">
      <div style="font-size:10px;font-weight:700;color:var(--text3);text-align:center;margin-bottom:4px">⚡ 期待値1.1</div>
      <div style="font-size:10px;color:var(--text3);text-align:center;margin-bottom:4px">シナリオ買い × 期待値フィルター</div>
      <div style="color:var(--text3);font-size:11px;text-align:center;padding:0.3rem 0">集計対象なし</div>
    </div>`;

  const hitCount     = results.filter(r => r.isHit).length;
  const hitRate      = hitCount / total;
  const totalBet     = results.reduce((s, r) => s + r.buyCnt * 100, 0);
  const totalReturn  = results.filter(r => r.isHit).reduce((s, r) => s + r.hitOdds, 0);
  const recoveryRate = totalBet > 0 ? totalReturn / totalBet : 0;
  const hitColor = hitRate      >= 0.7 ? 'var(--green)' : hitRate      >= 0.5 ? 'var(--orange)' : 'var(--text)';
  const recColor = recoveryRate >= 1.0 ? 'var(--green)' : recoveryRate >= 0.75 ? 'var(--orange)' : 'var(--text)';

  const evValid    = results.filter(r => r.expectedValue != null);
  const avgEV      = evValid.length > 0 ? evValid.reduce((s, r) => s + r.expectedValue, 0) / evValid.length : null;
  const synthValid = results.filter(r => r.avgOdds != null);
  const avgSynth   = synthValid.length > 0 ? synthValid.reduce((s, r) => s + r.avgOdds, 0) / synthValid.length : null;
  const hpValid    = results.filter(r => r.hitProbEst != null);
  const avgHP      = hpValid.length > 0 ? hpValid.reduce((s, r) => s + r.hitProbEst, 0) / hpValid.length : null;
  const avgEVStr   = avgEV    != null ? avgEV.toFixed(2)              : '—';
  const avgSOStr   = avgSynth != null ? `${avgSynth.toFixed(1)}倍`    : '—';
  const avgHPStr   = avgHP    != null ? `${(avgHP*100).toFixed(1)}%`  : '—';

  const venueMapEV = {};
  results.forEach(r => { if (!venueMapEV[r.venue]) venueMapEV[r.venue] = []; venueMapEV[r.venue].push(r); });
  const venueRowsEV = VENUE_LIST.filter(v => venueMapEV[v]).map(v => {
    const vrs  = venueMapEV[v];
    const vHit = vrs.filter(r => r.isHit).length;
    const vTot = vrs.length;
    const vBet = vrs.reduce((s, r) => s + r.buyCnt * 100, 0);
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

  const venueDetailEV = venueRowsEV ? `
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
          <tbody>${venueRowsEV}</tbody>
        </table>
      </div>
    </details>` : '';

  return `
    <div style="background:var(--bg3);border-radius:var(--radius-sm);padding:12px;border:1px solid var(--border)">
      <div style="font-size:10px;font-weight:700;color:var(--text3);text-align:center;margin-bottom:2px">⚡ 期待値1.1</div>
      <div style="font-size:10px;color:var(--text3);text-align:center;margin-bottom:10px">シナリオ買い × 期待値フィルター</div>
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
        <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);padding-bottom:5px">
          <span style="font-size:10px;color:var(--text3)">平均期待値</span>
          <span style="font-size:13px;font-weight:700;font-family:var(--mono);color:var(--green)">${avgEVStr}</span>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);padding-bottom:5px">
          <span style="font-size:10px;color:var(--text3)">平均合成オッズ</span>
          <span style="font-size:13px;font-weight:700;font-family:var(--mono);color:var(--text)">${avgSOStr}</span>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center">
          <span style="font-size:10px;color:var(--text3)">平均想定的中率</span>
          <span style="font-size:13px;font-weight:700;font-family:var(--mono);color:var(--text)">${avgHPStr}</span>
        </div>
      </div>
      ${venueDetailEV}
    </div>`;
}

// ════════════════════════════════════════════════════════════════
// ⚡ 期待値1.1 パネル（日別カード用）
// ════════════════════════════════════════════════════════════════
function _buildScenEVPanel_dateCard(resultsScenAll) {
  const EV_THRESHOLD = 1.1;
  const results = resultsScenAll.filter(r =>
    r.expectedValue != null && r.expectedValue >= EV_THRESHOLD
  );
  const total = results.length;

  if (total === 0) return `
    <div style="background:var(--bg3);border-radius:var(--radius-sm);padding:10px;border:1px solid var(--border)">
      <div style="font-size:10px;font-weight:700;color:var(--text3);text-align:center;margin-bottom:4px">⚡ 期待値1.1</div>
      <div style="font-size:10px;color:var(--text3);text-align:center;margin-bottom:4px">シナリオ買い × 期待値フィルター</div>
      <div style="color:var(--text3);font-size:11px;text-align:center;padding:0.3rem 0">集計対象なし</div>
    </div>`;

  const hitCount     = results.filter(r => r.isHit).length;
  const hitRate      = hitCount / total;
  const totalBet     = results.reduce((s, r) => s + r.buyCnt * 100, 0);
  const totalReturn  = results.filter(r => r.isHit).reduce((s, r) => s + r.hitOdds, 0);
  const recoveryRate = totalBet > 0 ? totalReturn / totalBet : 0;
  const hitColor = hitRate      >= 0.7 ? 'var(--green)' : hitRate      >= 0.5 ? 'var(--orange)' : 'var(--text)';
  const recColor = recoveryRate >= 1.0 ? 'var(--green)' : recoveryRate >= 0.75 ? 'var(--orange)' : 'var(--text)';

  const evValid    = results.filter(r => r.expectedValue != null);
  const avgEV      = evValid.length > 0 ? evValid.reduce((s, r) => s + r.expectedValue, 0) / evValid.length : null;
  const synthValid = results.filter(r => r.avgOdds != null);
  const avgSynth   = synthValid.length > 0 ? synthValid.reduce((s, r) => s + r.avgOdds, 0) / synthValid.length : null;
  const hpValid    = results.filter(r => r.hitProbEst != null);
  const avgHP      = hpValid.length > 0 ? hpValid.reduce((s, r) => s + r.hitProbEst, 0) / hpValid.length : null;
  const avgEVStr   = avgEV    != null ? avgEV.toFixed(2)             : '—';
  const avgSOStr   = avgSynth != null ? `${avgSynth.toFixed(1)}倍`   : '—';
  const avgHPStr   = avgHP    != null ? `${(avgHP*100).toFixed(1)}%` : '—';

  const venueMapEV = {};
  results.forEach(r => { if (!venueMapEV[r.venue]) venueMapEV[r.venue] = []; venueMapEV[r.venue].push(r); });
  const venueBlocksEV = VENUE_LIST.filter(v => venueMapEV[v]).map(v => {
    const vrs  = venueMapEV[v];
    const vHit = vrs.filter(r => r.isHit).length;
    const vTot = vrs.length;
    const vHR  = vHit / vTot;
    const vBet = vrs.reduce((s, r) => s + r.buyCnt * 100, 0);
    const vRet = vrs.filter(r => r.isHit).reduce((s, r) => s + r.hitOdds, 0);
    const vRec = vBet > 0 ? vRet / vBet : 0;
    const vHC  = vHR >= 0.7 ? 'hit' : vHR >= 0.5 ? 'warn' : '';
    const vRC  = vRec >= 1.0 ? 'over' : vRec >= 0.75 ? 'warn' : '';

    const comboBadges = combo => (combo || '').split(/[-－−]/).map(n =>
      /^[1-6]$/.test(n.trim())
        ? `<span class="boat-circle b${n.trim()}" style="width:20px;height:20px;font-size:10px;display:inline-flex;align-items:center;justify-content:center;flex-shrink:0">${n.trim()}</span>`
        : ''
    ).join('<span style="color:var(--text3);font-size:11px;margin:0 1px">−</span>');

    const raceDetails = vrs.map(r => {
      const hitOddsStr = r.isHit && r.hitOdds ? `￥${r.hitOdds.toLocaleString()}` : '';
      const resultStr  = r.actualResult
        ? `<span style="display:inline-flex;align-items:center;gap:2px;margin-left:4px">${comboBadges(r.actualResult)}</span>`
        : '';
      const hitPart    = r.isHit
        ? `<span class="ai-venue-race-hit" style="flex-shrink:0">🎯 的中</span>${resultStr}<span class="ai-venue-race-odds" style="flex-shrink:0">${hitOddsStr}</span>`
        : `<span class="ai-venue-race-miss" style="flex-shrink:0">—</span>${resultStr}`;
      return `<div class="ai-race-row" style="display:flex;align-items:center;gap:6px;padding:5px 8px;border-bottom:1px solid var(--border)">
        <span class="ai-venue-race-no" style="flex-shrink:0">${r.rno}R</span>
        <span class="ai-venue-race-cnt" style="flex-shrink:0">${r.buyCnt}点</span>

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

  const detailHtml = venueBlocksEV ? `
    <details style="margin-top:0.5rem">
      <summary style="font-size:11px;font-weight:700;color:var(--text3);cursor:pointer;letter-spacing:.06em;list-style:none;display:flex;align-items:center;gap:5px">
        <span style="font-size:10px">▶</span> 会場別内訳
      </summary>
      <div class="ai-venue-list" style="margin-top:0.5rem">${venueBlocksEV}</div>
    </details>` : '';

  return `
    <div style="background:var(--bg3);border-radius:var(--radius-sm);padding:10px;border:1px solid var(--border)">
      <div style="font-size:10px;font-weight:700;color:var(--text3);text-align:center;margin-bottom:2px">⚡ 期待値1.1</div>
      <div style="font-size:10px;color:var(--text3);text-align:center;margin-bottom:8px">シナリオ買い × 期待値フィルター</div>
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
        <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);padding-bottom:4px">
          <span style="font-size:10px;color:var(--text3)">平均期待値</span>
          <span style="font-size:12px;font-weight:700;font-family:var(--mono);color:var(--green)">${avgEVStr}</span>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);padding-bottom:4px">
          <span style="font-size:10px;color:var(--text3)">平均合成オッズ</span>
          <span style="font-size:12px;font-weight:700;font-family:var(--mono);color:var(--text)">${avgSOStr}</span>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center">
          <span style="font-size:10px;color:var(--text3)">平均想定的中率</span>
          <span style="font-size:12px;font-weight:700;font-family:var(--mono);color:var(--text)">${avgHPStr}</span>
        </div>
      </div>
      ${detailHtml}
    </div>`;
}

// ════════════════════════════════════════════════════════════════
// 🔒 イン鉄板 / ⚡ イン否定 集計系
// ════════════════════════════════════════════════════════════════

// ── イン鉄板・イン否定 共通: final_prob + ranked2 + sd を計算して返す ──
// computeScenCombos と同一の2パス加算ボーナス方式。
// 戻り値: { ranked2, sd, venueAvg1 } | null（エラー時）
function _computeRanked2AndSd(venue, vdata, rno) {
  _ensureTenjiCache();
  const rd = vdata.races[String(rno)];
  if (!rd || !rd.boats) return null;

  const slug      = SLUG_MAP[venue] || venue;
  const tKey      = tenjiKey(slug, vdata.date, rno);
  const tenjiData = _tenjiCache[tKey] || null;

  const savedDATA  = DATA;
  const savedVenue = currentVenue;
  DATA        = vdata;
  currentVenue = venue;

  let result = null;
  try {
    const arek     = rd.arek ?? 54.7;
    const rawBoats = rd.boats;
    const ranked   = calcTenkaiProbs(rawBoats, arek);

    let tenjiScoreMap = null;
    if (tenjiData) tenjiScoreMap = calcTenjiScore(ranked, tenjiData, venue, arek);

    const probTotal       = ranked.reduce((s, b) => s + b.prob, 0) || 1;
    const useMaster       = hasMasterExt() && !!(MASTER_EXT.venue_kimari && MASTER_EXT.venue_kimari[venue]);
    const { wBase, wTenkai, wTenji, wSlit } = calcDynamicWeights(arek);
    const tenkaiOnlyTotal = ranked.reduce((s, x) => s + (x.tenkai_score ?? x.tenkai_prob), 0) || 1;
    const boatByNo        = {};
    rawBoats.forEach(b => { boatByNo[b.boat] = b; });
    const tenjiRawMap = {};
    if (tenjiData) {
      Object.keys(tenjiData).filter(k => /^\d+$/.test(k)).forEach(k => {
        const e = tenjiData[k];
        if (e && typeof e.tenji === 'number') tenjiRawMap[parseInt(k)] = e.tenji;
      });
    }
    const hasTenji_r = (tenjiData != null);

    // 1パス目: 係数計算
    ranked.forEach(b => {
      const baseNorm = b.prob / probTotal;
      const prevBoat = boatByNo[b.boat - 1] || null;
      let tenkaiCoef = 1.0;
      if (useMaster && baseNorm > 0) {
        const tenkaiNorm = (b.tenkai_score ?? b.tenkai_prob) / tenkaiOnlyTotal;
        tenkaiCoef = Math.min(3.0, Math.max(0.3, tenkaiNorm / baseNorm));
      }
      if (prevBoat) {
        const myStRk = MASTER_EXT?.course_master?.[b.name]?.[String(b.boat)]?.st_rank;
        const pvStRk = MASTER_EXT?.course_master?.[prevBoat.name]?.[String(prevBoat.boat)]?.st_rank;
        if (myStRk != null && pvStRk != null)
          tenkaiCoef = Math.min(3.0, Math.max(0.3, tenkaiCoef + (pvStRk - myStRk) * 0.10));
      }
      let tenjiCoef = 1.0;
      if (tenjiScoreMap) tenjiCoef = tenjiScoreMap[`__coef_${b.boat}`] ?? 1.0;
      if (prevBoat && tenjiData) {
        const myTj = tenjiRawMap[b.boat]        ?? null;
        const pvTj = tenjiRawMap[prevBoat.boat] ?? null;
        if (myTj != null && pvTj != null) {
          const DIFF_MULT = { 1:0.0, 2:0.0, 3:0.3, 4:0.4, 5:0.35, 6:0.25 };
          tenjiCoef = Math.min(3.0, Math.max(0.3, tenjiCoef + (pvTj - myTj) * (DIFF_MULT[b.boat] ?? 0.2)));
        }
      }
      let slitCoef = 1.0;
      if (prevBoat && hasTenji_r && wSlit > 0) {
        const myTenji   = tenjiRawMap[b.boat]        ?? null;
        const prevTenji = tenjiRawMap[prevBoat.boat] ?? null;
        const myStRank  = MASTER_EXT?.course_master?.[b.name]?.[String(b.boat)]?.st_rank         ?? null;
        const pvStRank  = MASTER_EXT?.course_master?.[prevBoat.name]?.[String(prevBoat.boat)]?.st_rank ?? null;
        let slitDiff = null;
        if (myTenji != null && prevTenji != null && myStRank != null && pvStRank != null)
          slitDiff = (prevTenji - myTenji) + (pvStRank - myStRank) * 0.02;
        else if (myTenji != null && prevTenji != null)
          slitDiff = prevTenji - myTenji;
        else if (myStRank != null && pvStRank != null)
          slitDiff = (pvStRank - myStRank) * 0.02;
        if (slitDiff !== null) {
          const found = SLIT_LAP_THRESHOLDS.find(t => slitDiff >= t.min);
          slitCoef = 1.0 + ((found ? found.coef : 1.0) - 1.0) * wSlit;
        }
        const MAKURI_BONUS = 0.20;
        const tjOk = (myTenji != null && prevTenji != null) && (prevTenji - myTenji >= 0.10);
        const stOk = (myStRank != null && pvStRank != null) && (pvStRank - myStRank >= 0.5);
        if (tjOk && stOk) slitCoef += MAKURI_BONUS;
        slitCoef = Math.min(2.0, Math.max(0.5, slitCoef));
      }
      b._baseNorm   = baseNorm;
      b._tenkaiCoef = tenkaiCoef;
      b._tenjiCoef  = tenjiCoef;
      b._slitCoef   = slitCoef;
    });

    // 2パス目: 加算ボーナス方式
    const BB_TK = 0.15, BB_TJ = 0.15, BB_SL = 0.15;
    ranked.forEach(b => {
      const nextBoat    = boatByNo[b.boat + 1] || null;
      const tenkaiBonus = BB_TK * (b._tenkaiCoef - 1.0) * wTenkai;
      const tenjiBonus  = BB_TJ * (b._tenjiCoef  - 1.0) * wTenji;
      const slitBonus   = BB_SL * (b._slitCoef   - 1.0) * wSlit;
      let slitPenalty = 0;
      if (nextBoat && hasTenji_r && wSlit > 0) {
        const myTj   = tenjiRawMap[b.boat]          ?? null;
        const nextTj = tenjiRawMap[nextBoat.boat]   ?? null;
        const myStR  = MASTER_EXT?.course_master?.[b.name]?.[String(b.boat)]?.st_rank              ?? null;
        const nextStR= MASTER_EXT?.course_master?.[nextBoat.name]?.[String(nextBoat.boat)]?.st_rank ?? null;
        let nextDiff = null;
        if (myTj != null && nextTj != null && myStR != null && nextStR != null)
          nextDiff = (myTj - nextTj) + (myStR - nextStR) * 0.02;
        else if (myTj != null && nextTj != null)
          nextDiff = myTj - nextTj;
        else if (myStR != null && nextStR != null)
          nextDiff = (myStR - nextStR) * 0.02;
        if (nextDiff !== null && nextDiff > 0) {
          const found = SLIT_LAP_THRESHOLDS.find(t => nextDiff >= t.min);
          slitPenalty = BB_SL * ((found ? found.coef : 1.0) - 1.0) * wSlit;
        }
        const nextTjOk = (myTj != null && nextTj != null) && (nextTj - myTj <= -0.10);
        const nextStOk = (myStR != null && nextStR != null) && (nextStR - myStR <= -0.5);
        if (nextTjOk && nextStOk) slitPenalty += BB_SL * 0.20 * wSlit;
      }
      b._multi_score = Math.max(0.001, b._baseNorm + tenkaiBonus + tenjiBonus + slitBonus - slitPenalty);
    });

    const multiTotal = ranked.reduce((s, b) => s + b._multi_score, 0) || 1;
    ranked.forEach(b => { b.final_prob = b._multi_score / multiTotal; });
    const ranked2 = [...ranked].sort((a, b) => b.final_prob - a.final_prob);

    const sd = calcScenarioData(ranked2, rawBoats, tenjiScoreMap);

    // 場平均1コース1着率
    const venueAvg1 = ((vdata.inn_data || {}).course_rates || [])[1] ?? null;

    result = { ranked2, sd, venueAvg1 };
  } catch(e) {
    console.warn('[_computeRanked2AndSd] error:', e);
  } finally {
    // 修正: 例外・正常終了どちらのパスでも必ず復元する
    DATA        = savedDATA;
    currentVenue = savedVenue;
  }
  return result;
}

// ── イン鉄板コンボ計算（集計専用）──
// 条件: 1号艇 final_prob >= 0.75
// 買い目: buildInTepBuyPanel と同一ロジック
// 戻り値: combo 文字列の配列（条件不成立なら空配列）
function computeInTepCombos(venue, vdata, rno) {
  const base = _computeRanked2AndSd(venue, vdata, rno);
  if (!base || !base.sd || !base.sd.valid) return [];

  const { ranked2, sd } = base;
  const boat1 = ranked2.find(b => b.boat === 1);
  const fp1   = boat1?.final_prob ?? 0;
  if (fp1 < 0.75) return [];   // 条件不成立

  const { scenarioProb, scenarioPlace2, merged3rdMap } = sd;

  function getP2Rank(winnerBoat) {
    if (!scenarioPlace2?.[winnerBoat]) return [];
    const totals = {}; let wSum = 0;
    for (const [k, list] of Object.entries(scenarioPlace2[winnerBoat])) {
      const p = scenarioProb?.[winnerBoat]?.[k] ?? 0; wSum += p;
      (list || []).forEach(x => { totals[x.boat] = (totals[x.boat] ?? 0) + x.p2 * p; });
    }
    if (wSum <= 0)
      return ranked2.filter(r => r.boat !== winnerBoat)
        .sort((a, b) => (b.final_prob ?? 0) - (a.final_prob ?? 0)).map(r => r.boat);
    return Object.entries(totals).sort((a, b) => b[1] - a[1]).map(([b]) => parseInt(b));
  }

  function getP3Rank(w, s) {
    const all = merged3rdMap?.[w]?.[s] || [];
    if (all.length > 0)
      return all.filter(x => x.boat !== w && x.boat !== s).map(x => x.boat);
    return ranked2.filter(r => r.boat !== w && r.boat !== s)
      .sort((a, b) => (b.final_prob ?? 0) - (a.final_prob ?? 0)).map(r => r.boat);
  }

  // 2着率上位3艇（1号艇除く）
  const p2rank = getP2Rank(1).filter(b => b !== 1);
  const p2A = p2rank[0], p2B = p2rank[1], p2C = p2rank[2];
  if (p2A == null || p2B == null) return [];

  function makeTepBlock(winner, second, thirds) {
    const used = new Set(); const out = [];
    thirds.forEach(t => {
      if (t === winner || t === second) return;
      const fwd = `${winner}-${second}-${t}`;
      const bwd = `${winner}-${t}-${second}`;
      if (!used.has(fwd)) { used.add(fwd); out.push(fwd); }
      if (!used.has(bwd)) { used.add(bwd); out.push(bwd); }
    });
    return out;
  }

  const thirdsA = [p2B, p2C].filter(b => b != null && b !== 1 && b !== p2A);
  const thirdsB = [p2A, p2C].filter(b => b != null && b !== 1 && b !== p2B);
  const blockA  = makeTepBlock(1, p2A, thirdsA);
  const blockB  = makeTepBlock(1, p2B, thirdsB);

  const seen = new Set(); const combos = [];
  [...blockA, ...blockB].forEach(c => { if (!seen.has(c)) { seen.add(c); combos.push(c); } });
  return combos;
}

// ── イン否定コンボ計算（集計専用）──
// 条件: 1号艇 final_prob <= 場平均 - 0.10
// 買い目: buildInNegBuyPanel と同一ロジック
// 戻り値: combo 文字列の配列（条件不成立なら空配列）
function computeInNegCombos(venue, vdata, rno) {
  const base = _computeRanked2AndSd(venue, vdata, rno);
  if (!base || !base.sd || !base.sd.valid) return [];

  const { ranked2, sd, venueAvg1 } = base;
  const boat1 = ranked2.find(b => b.boat === 1);
  const fp1   = boat1?.final_prob ?? null;

  // 条件チェック: 場平均データなし or 条件未満 → 除外
  if (venueAvg1 === null || fp1 === null) return [];
  if (fp1 > venueAvg1 - 0.10) return [];   // 条件不成立

  const { scenarioProb, scenarioPlace2, merged3rdMap } = sd;

  function getP2Rank(winnerBoat) {
    if (!scenarioPlace2?.[winnerBoat]) return [];
    const totals = {}; let wSum = 0;
    for (const [k, list] of Object.entries(scenarioPlace2[winnerBoat])) {
      const p = scenarioProb?.[winnerBoat]?.[k] ?? 0; wSum += p;
      (list || []).forEach(x => { totals[x.boat] = (totals[x.boat] ?? 0) + x.p2 * p; });
    }
    if (wSum <= 0)
      return ranked2.filter(r => r.boat !== winnerBoat)
        .sort((a, b) => (b.final_prob ?? 0) - (a.final_prob ?? 0)).map(r => r.boat);
    return Object.entries(totals).sort((a, b) => b[1] - a[1]).map(([b]) => parseInt(b));
  }

  function getP3Rank(w, s) {
    const all = merged3rdMap?.[w]?.[s] || [];
    if (all.length > 0)
      return all.filter(x => x.boat !== w && x.boat !== s).map(x => x.boat);
    return ranked2.filter(r => r.boat !== w && r.boat !== s)
      .sort((a, b) => (b.final_prob ?? 0) - (a.final_prob ?? 0)).map(r => r.boat);
  }

  // 1着軸: 1号艇以外 final_prob 上位2艇
  const outerRanked = ranked2.filter(b => b.boat !== 1)
    .sort((a, b) => (b.final_prob ?? 0) - (a.final_prob ?? 0));
  const axisA = outerRanked[0]?.boat;
  const axisB = outerRanked[1]?.boat;
  if (axisA == null) return [];

  function makeNegBlock(winner) {
    const p2rank = getP2Rank(winner).filter(b => b !== winner);
    const sec1 = p2rank[0], sec2 = p2rank[1];
    if (sec1 == null) return [];
    const used = new Set(); const out = [];
    function add(c) {
      const parts = c.split('-').map(Number);
      if (new Set(parts).size !== parts.length) return; // 被り目除外
      if (!used.has(c)) { used.add(c); out.push(c); }
    }
    [sec1, sec2].filter(s => s != null).forEach(sec => {
      const thirds = getP3Rank(winner, sec).filter(b => b !== winner && b !== sec).slice(0, 3);
      thirds.forEach(t => {
        add(`${winner}-${sec}-${t}`);
        add(`${winner}-${t}-${sec}`);
      });
    });
    return out;
  }

  const blockA = makeNegBlock(axisA);
  const blockB = axisB != null ? makeNegBlock(axisB) : [];

  const seen = new Set(); const combos = [];
  [...blockA, ...blockB].forEach(c => { if (!seen.has(c)) { seen.add(c); combos.push(c); } });
  return combos;
}

// ── 共通集計ヘルパー（イン鉄板 / イン否定どちらにも使う）──
// computeFn: (venue, vdata, rno) => combo[] を受け取る
function _collectResultsForDateCondBuy(dateStr, computeFn) {
  const dataForDate = getDataForDate(dateStr);
  const results = [];

  VENUE_LIST.forEach(venue => {
    const vdata = dataForDate[venue];
    if (!vdata || !vdata.races) return;
    if (venue === '江戸川') return;

    const slug = SLUG_MAP[venue] || venue;

    Object.entries(vdata.races).sort((a, b) => +a[0] - +b[0]).forEach(([rnoStr, rd]) => {
      const rno = parseInt(rnoStr);
      if (!rd || !rd.boats) return;

      const rKey     = resultKey(slug, vdata.date, rno);
      const resultRd = RESULT_DATA[rKey];
      // 結果未確定は除外
      if (!resultRd || !resultRd.sanrentan || resultRd.sanrentan.length === 0) return;

      // 標準除外フィルター（collectResultsForDate と同一）
      if (hasInsufficient(rd))              return;
      if (hasCourseOrderChange(rno, vdata)) return;
      if (hasNoLapTime(rno, vdata))         return;

      // 条件判定 + コンボ生成
      const combos = computeFn(venue, vdata, rno);
      // 条件不成立（空配列）→ 集計対象外（見送り扱いではなく「対象外」）
      if (!combos || combos.length === 0) return;

      const resultSan3 = resultRd.sanrentan[0]
        ? new Set([normalizeCombo(resultRd.sanrentan[0].combo)])
        : new Set();

      let isHit = false, hitOdds = 0, hitCombo = '';
      for (const c of combos) {
        const nc = normalizeCombo(c);
        if (resultSan3.has(nc)) {
          isHit = true; hitCombo = nc;
          hitOdds = resultRd.sanrentan[0]?.odds ?? 0;
          break;
        }
      }

      results.push({
        venue, rno,
        buy3cnt: combos.length,
        buy3combos: combos.join(' / '),
        isHit, hitOdds, hitCombo,
        actualResult: resultRd.sanrentan?.[0]?.combo || '',
        actualKimari: resultRd.kimari || '',
        arek: (rd.arek ?? 54.7).toFixed(1),
      });
    });
  });

  return results;
}

// ── イン鉄板 1日分集計 ──
function collectResultsForDateInTep(dateStr) {
  return _collectResultsForDateCondBuy(dateStr, computeInTepCombos);
}

// ── イン否定 1日分集計 ──
function collectResultsForDateInNeg(dateStr) {
  return _collectResultsForDateCondBuy(dateStr, computeInNegCombos);
}
