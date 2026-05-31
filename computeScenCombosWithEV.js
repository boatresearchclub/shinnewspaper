// ══════════════════════════════════════════════════════════════════════════════
// computeScenCombosWithEV.js  — シナリオ買い目 + EV + 2着/3着予測（完全実装版）
//
// 【解決する問題】
//
//   問題① pred2ndRank / pred3rdRank が「頻度ベース」で誤判定
//          → scenarioPlace2 の p2 × シナリオ重み の加重確率ベースに変更
//
//   問題② computeScenCombosWithEV が未実装
//          → calcScenarioData / calcScenarioComboProb を内部で呼び出し正式実装
//
//   問題③ hitProbEst が系統的に過小評価（実測で +10〜17% のズレ）
//          → Platt Scaling 的なビン補間キャリブレーションで補正
//
//   問題④ 買い目点数が buildScenarioBuyPanel と食い違う（常に2軸18点で固定）
//          → _confRank（HIGH/MID/LOW）と _allow2ndAxis（fp差ゲート）を追加し
//            buildScenarioBuyPanel 通常モードと完全一致させた
//            HIGH(HHI≥0.55 かつ fp≥0.50): 1軸最大12点
//            MID/LOW かつ fp差>15%pt     : 1軸最大12点
//            MID/LOW かつ fp差≤15%pt     : 2軸最大18点（重複除去後16〜18点）
//
// 【使い方】
//   このファイルを sample.js / top_stats.js より後に <script> で読み込むだけ。
//   既存コードの変更は一切不要。
//
//   top_stats.js の collectResultsForDateScen から呼ばれる:
//     computeScenCombosWithEV(venue, vdata, rno)
//   戻り値:
//     {
//       combos      : string[],          // 買い目文字列（例: "1-2-3"）
//       hitProbEst  : number|null,       // キャリブレーション補正済み的中確率
//       synthOdds   : number|null,       // 合成オッズ（参考）
//       ev          : number|null,       // 期待値 = synthOdds × hitProbEst
//       pred2ndRank : number|null,       // 実際の2着枠番が「加重確率」で何位だったか
//       pred3rdRank : number|null,       // 実際の3着枠番が「加重確率」で何位だったか
//       weighted2nd : object,            // { boat: 加重確率合計 } デバッグ用
//       weighted3rd : object,            // { boat: 加重確率合計 } デバッグ用
//     }
//
// ══════════════════════════════════════════════════════════════════════════════

(function () {

  // ─────────────────────────────────────────────────────────────────────────
  // § 1  キャリブレーション補正テーブル
  //       実測データ（3096件）から構築した推定→実績のマッピング
  //       Platt Scaling / Isotonic Regression に相当する区分線形補間
  //
  //  【統計的根拠】
  //   モデルが確率を過小評価している原因:
  //     1. calcScenarioComboProb は kimari × p2 × r3 の三重積
  //        → 各確率が独立でないのに掛け合わせると系統的に低くなる
  //     2. scenarioProb の正規化前残差が圧縮されている
  //   補正により「実態に即した的中確率」を返すことで EV 計算の精度が上がる。
  //
  //  ビン定義: [推定平均, 実績率] の対応点（線形補間用）
  //  ※ 実測値に合わせて更新すること（calibration.js のパネルを参照）
  // ─────────────────────────────────────────────────────────────────────────
  // localStorage キー
  const _CALIB_LS_KEY = 'scen_calib_points_v1';

  // localStorage から復元を試みる（起動時に前回の実測値を即時反映）
  function _loadCalibFromLS() {
    try {
      const raw = localStorage.getItem(_CALIB_LS_KEY);
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed) && parsed.length >= 3) {
        console.log('[computeScenCombosWithEV] localStorage から補正テーブルを復元しました');
        return parsed;
      }
    } catch (_e) {}
    return null;
  }

  const CALIB_POINTS = _loadCalibFromLS() || [
    // [推定値(中心), 実績的中率]  ← calibration.js の estAvg / actual から転記
    [0.00,  0.00],   // 0–10% ビン（サンプル少のため外挿基準点）
    [0.17,  0.33],   // 10–20% ビン: 推定17% → 実績33%
    [0.27,  0.37],   // 20–30% ビン: 推定27% → 実績37%
    [0.36,  0.48],   // 30–40% ビン: 推定36% → 実績48%
    [0.47,  0.57],   // 40–60% ビン: 推定47% → 実績57%
    [0.64,  0.75],   // 60%+  ビン: 推定64% → 実績75%
    [1.00,  1.00],   // 外挿基準点
  ];

  /**
   * 区分線形補間でキャリブレーション補正を適用する。
   *
   * @param {number} rawProb  モデルの生確率 (0〜1)
   * @returns {number}        補正後の確率 (0〜1)
   *
   * 【設計方針】
   *   CALIB_POINTS は calibration.js パネルの実測値を手動転記する。
   *   将来的には localStorage に保存した binStats JSON から自動更新可能。
   *   補正は「一方向のみ上昇」ではなく双方向に対応（万一逆転が起きた場合も安全）。
   */
  window.calibrateProb = calibrateProb;
  function calibrateProb(rawProb) {
    if (rawProb == null || isNaN(rawProb)) return rawProb;
    const p = Math.max(0, Math.min(1, rawProb));

    // 左端・右端の外挿クランプ
    if (p <= CALIB_POINTS[0][0]) return CALIB_POINTS[0][1];
    if (p >= CALIB_POINTS[CALIB_POINTS.length - 1][0]) {
      return CALIB_POINTS[CALIB_POINTS.length - 1][1];
    }

    // 区間を探して線形補間
    for (let i = 1; i < CALIB_POINTS.length; i++) {
      const [x0, y0] = CALIB_POINTS[i - 1];
      const [x1, y1] = CALIB_POINTS[i];
      if (p <= x1) {
        const t = (p - x0) / (x1 - x0);
        return y0 + t * (y1 - y0);
      }
    }
    return p; // fallback（到達しないはず）
  }

  /**
   * キャリブレーション補正テーブルを外部から更新する。
   * calibration.js の binStats を渡すと自動更新できる。
   *
   * 呼び出し例（calibration.js の _renderCalibrationPanel 末尾に追加）:
   *   if (typeof updateCalibPoints === 'function') updateCalibPoints(binStats);
   *
   * @param {Array} binStats  calcCalibration() の戻り値
   */
  window.updateCalibPoints = function (binStats) {
    if (!Array.isArray(binStats)) return;
    const newPoints = [[0.00, 0.00]]; // 左端固定
    binStats.forEach(b => {
      if (b.total >= 10 && b.estAvg != null && b.actual != null) {
        newPoints.push([b.estAvg, b.actual]);
      }
    });
    newPoints.push([1.00, 1.00]); // 右端固定
    if (newPoints.length >= 3) {
      // x 昇順ソート（安全策）
      newPoints.sort((a, b) => a[0] - b[0]);
      CALIB_POINTS.length = 0;
      newPoints.forEach(pt => CALIB_POINTS.push(pt));
      // localStorage に永続化（リロード後も即時反映）
      try { localStorage.setItem(_CALIB_LS_KEY, JSON.stringify(CALIB_POINTS)); } catch (_e) {}
      console.log('[computeScenCombosWithEV] キャリブレーション補正テーブルを更新・保存しました:', CALIB_POINTS);
    }
  };


  // ─────────────────────────────────────────────────────────────────────────
  // § 2  加重確率ベースの 2着 / 3着 順位算出
  // ─────────────────────────────────────────────────────────────────────────

  /**
   * scenarioPlace2 と scenarioProb を使い、各艇の「加重2着確率」を計算する。
   *
   * 【旧実装との違い】
   *   旧: combo文字列の2着ポジションに現れた頻度をカウント
   *       → 買い目構成の都合で2号艇が多く含まれると誤って「2着最有力」になる
   *
   *   新: scenarioPlace2[winner][kimari][].p2 × scenarioProb[winner][kimari]
   *       で加重合計 → 真の2着確率に基づく順位付け
   *
   * @param {object} sd  calcScenarioData() の戻り値
   * @param {number} winnerBoat  軸（1着）艇番
   * @returns {{ weighted: {[boat]: number}, ranked: number[] }}
   *   weighted: 各艇の加重2着確率合計（正規化なし。比較用）
   *   ranked  : 加重確率降順の艇番配列
   */
  function calcWeighted2nd(sd, winnerBoat) {
    const { scenarioProb, scenarioPlace2, kimariTypes } = sd;
    if (!scenarioProb?.[winnerBoat] || !kimariTypes?.length) {
      return { weighted: {}, ranked: [] };
    }

    const weighted = {};
    let totalScenWeight = 0;

    for (const kimari of kimariTypes) {
      const scenW = scenarioProb[winnerBoat]?.[kimari] ?? 0;
      if (scenW <= 0) continue;
      totalScenWeight += scenW;

      const p2List = scenarioPlace2?.[winnerBoat]?.[kimari] || [];
      p2List.forEach(({ boat, p2 }) => {
        if (boat == null || isNaN(p2)) return;
        weighted[boat] = (weighted[boat] ?? 0) + scenW * p2;
      });
    }

    // totalScenWeight で割ることで「シナリオ確率の合計が1でない場合」も安全に正規化
    if (totalScenWeight > 0) {
      Object.keys(weighted).forEach(k => { weighted[k] /= totalScenWeight; });
    }

    const ranked = Object.entries(weighted)
      .sort((a, b) => b[1] - a[1])
      .map(([boat]) => parseInt(boat));

    return { weighted, ranked };
  }

  /**
   * merged3rdMap と scenarioProb を使い、各艇の「加重3着確率」を計算する。
   *
   * 【なぜ merged3rdMap を使うか】
   *   calc3rdScores は winner × kimari × second の三重ループで r3 を算出しており、
   *   すでに calcScenarioData 内で scenarioProb × p2 で加重平均済み。
   *   ここでは winner × second の全ペアに対して scenarioProb[winner][kimari] × p2
   *   で再度重み付けすることで、真の3着確率を推定する。
   *
   * @param {object} sd
   * @param {number} winnerBoat
   * @returns {{ weighted: {[boat]: number}, ranked: number[] }}
   */
  function calcWeighted3rd(sd, winnerBoat) {
    const { scenarioProb, scenarioPlace2, merged3rdMap, kimariTypes } = sd;
    if (!scenarioProb?.[winnerBoat] || !kimariTypes?.length) {
      return { weighted: {}, ranked: [] };
    }

    const weighted = {};
    let totalWeight = 0;

    for (const kimari of kimariTypes) {
      const scenW = scenarioProb[winnerBoat]?.[kimari] ?? 0;
      if (scenW <= 0) continue;

      const p2List = scenarioPlace2?.[winnerBoat]?.[kimari] || [];
      p2List.forEach(({ boat: secondBoat, p2 }) => {
        if (secondBoat == null || isNaN(p2) || p2 <= 0) return;
        const w2 = scenW * p2; // このシナリオ×2着艇の複合重み
        totalWeight += w2;

        const thirdList = merged3rdMap?.[winnerBoat]?.[secondBoat] || [];
        thirdList.forEach(({ boat: thirdBoat, r3 }) => {
          if (thirdBoat == null || r3 == null || isNaN(r3)) return;
          weighted[thirdBoat] = (weighted[thirdBoat] ?? 0) + w2 * r3;
        });
      });
    }

    if (totalWeight > 0) {
      Object.keys(weighted).forEach(k => { weighted[k] /= totalWeight; });
    }

    const ranked = Object.entries(weighted)
      .sort((a, b) => b[1] - a[1])
      .map(([boat]) => parseInt(boat));

    return { weighted, ranked };
  }


  // ─────────────────────────────────────────────────────────────────────────
  // § 3  computeScenCombosWithEV  本体
  // ─────────────────────────────────────────────────────────────────────────

  /**
   * シナリオ買い目・的中確率・期待値・2着/3着予測を一括返却する。
   *
   * 【設計方針】
   *   buildScenarioBuyPanel と同一のロジックで買い目を生成しつつ、
   *   calcScenarioComboProb で各買い目の真の的中確率を合算して hitProbEst を算出。
   *   さらに calibrateProb でキャリブレーション補正を適用する。
   *
   * @param {string} venue     会場名
   * @param {object} vdata     その会場・日付のデータオブジェクト（races含む）
   * @param {number} rno       レース番号（整数）
   * @returns {{
   *   combos      : string[],
   *   hitProbEst  : number|null,
   *   synthOdds   : number|null,
   *   ev          : number|null,
   *   pred2ndRank : number|null,
   *   pred3rdRank : number|null,
   *   weighted2nd : object,
   *   weighted3rd : object,
   * }}
   */
  window.computeScenCombosWithEV = function (venue, vdata, rno) {

    const _empty = {
      combos: [], hitProbEst: null, synthOdds: null, ev: null,
      pred2ndRank: null, pred3rdRank: null,
      weighted2nd: {}, weighted3rd: {},
    };

    try {
      // ── 引数バリデーション ──
      if (!venue || typeof venue !== 'string') return _empty;
      if (!vdata || typeof vdata !== 'object') return _empty;
      if (rno == null) return _empty;

      // ── 必要な関数の存在確認 ──
      if (typeof calcScenarioData         !== 'function') return _empty;
      if (typeof calcScenarioComboProb    !== 'function') return _empty;
      if (typeof calcTenkaiProbs          !== 'function') return _empty;

      // ── レースデータ取得 ──
      const rd = vdata?.races?.[String(rno)];
      if (!rd || !rd.boats || rd.boats.length < 2) return _empty;

      // ── 展示・最終確率の算出（sample.js の標準フロー再現）──
      const rawBoats = rd.boats;

      // tenjiScoreMap が必要。_ensureTenjiCache / tenjiKey は sample.js グローバル
      let tenjiScoreMap = {};
      try {
        if (typeof _ensureTenjiCache === 'function') _ensureTenjiCache();
        if (typeof tenjiKey === 'function' && typeof _tenjiCache !== 'undefined') {
          const slug = (typeof SLUG_MAP !== 'undefined' && SLUG_MAP[venue]) ? SLUG_MAP[venue] : venue;
          const tk = tenjiKey(slug, vdata.date, rno);
          tenjiScoreMap = _tenjiCache[tk] || {};
        }
      } catch (_e) { /* tenjiCache が利用不可でも続行 */ }

      // ── DATA / currentVenue を一時差し替え ──
      // calcTenkaiProbs / calcScenarioData が DATA.venue / currentVenue を参照するため
      const _origDATA    = window.DATA;
      const _origVenue   = window.currentVenue;
      const _tempData    = Object.assign({}, vdata, { venue: venue });
      if (!_tempData.venue) return _empty; // venue が空なら中断

      let ranked2, sd;
      try {
        window.DATA         = _tempData;
        window.currentVenue = venue;

        // calcTenkaiProbs で ranked2 を構築（arek は数値のみ渡す）
        const _arek = (typeof rd.arek === 'number' && rd.arek > 0) ? rd.arek : 54.7;
        ranked2 = calcTenkaiProbs(rawBoats, _arek, venue);  // venue を明示渡し（DATA.venue依存を排除）
        if (!ranked2 || ranked2.length < 2) return _empty;

        // シナリオデータ算出
        sd = calcScenarioData(ranked2, rawBoats, tenjiScoreMap);
      } finally {
        // 必ず元に戻す
        window.DATA         = _origDATA;
        window.currentVenue = _origVenue;
      }
      if (!sd || !sd.valid) return _empty;

      // ── 買い目生成（buildScenarioBuyPanel と同一ロジック）──
      // ※ DATA / _pickupRaceTagType はグローバル依存のため、
      //    prefill / top_stats 経由では通常モード（isInNeg=false, isInTep=false）で動作する

      const fp1st = ranked2[0]?.boat;
      const fp2nd = ranked2[1]?.boat;
      if (fp1st == null) return _empty;

      // ── 2着確率上位リスト取得（getPlace2Ranking の内部ロジックを再現）──
      function getP2Ranking(winnerBoat) {
        if (!sd.scenarioPlace2?.[winnerBoat]) return [];
        const totals = {};
        let weightSum = 0;
        for (const [kimari, list] of Object.entries(sd.scenarioPlace2[winnerBoat])) {
          const scenProb = sd.scenarioProb?.[winnerBoat]?.[kimari] ?? 0;
          weightSum += scenProb;
          (list || []).forEach(x => {
            totals[x.boat] = (totals[x.boat] ?? 0) + x.p2 * scenProb;
          });
        }
        if (weightSum > 0) Object.keys(totals).forEach(k => { totals[k] /= weightSum; });
        return Object.entries(totals)
          .sort((a, b) => b[1] - a[1])
          .map(([boat]) => parseInt(boat));
      }

      // ── inn_2place ベース（イン鉄板時）──
      function getInnTepP2Ranking() {
        const inn2p = sd.inn2Place || {};
        const sorted = Object.entries(inn2p)
          .map(([k, v]) => ({ boat: parseInt(k), rate: v }))
          .filter(x => !isNaN(x.boat) && x.boat !== 1)
          .sort((a, b) => b.rate - a.rate)
          .map(x => x.boat);
        return sorted.length > 0 ? sorted : getP2Ranking(1);
      }

      // ── 3着確率上位リスト ──
      function getP3Ranking(winnerBoat, secondBoat) {
        const thirdAll = sd.merged3rdMap?.[winnerBoat]?.[secondBoat] || [];
        if (thirdAll.length > 0) {
          return thirdAll
            .filter(x => x.boat !== winnerBoat && x.boat !== secondBoat)
            .slice(0, 3)
            .map(x => x.boat);
        }
        return ranked2
          .filter(r => r.boat !== winnerBoat && r.boat !== secondBoat)
          .sort((a, b) => (b.final_prob ?? 0) - (a.final_prob ?? 0))
          .map(r => r.boat)
          .slice(0, 3);
      }

      // ── makeBlock（forward + backward）──
      function makeBlock(winner, second, thirdCandidates) {
        const thirds = thirdCandidates.filter(t => t !== winner && t !== second);
        return [
          ...thirds.map(t => `${winner}-${second}-${t}`),
          ...thirds.map(t => `${winner}-${t}-${second}`),
        ];
      }

      // ── buildScenarioBuyPanel と同一の確信度ランク判定 ──
      // prefill / top_stats 経由では isInNeg / isInTep は常に false（通常モード）
      function _calcHHI(winnerBoat) {
        const probs = sd?.kimariTypes?.map(k => sd.scenarioProb?.[winnerBoat]?.[k] ?? 0) ?? [];
        const total = probs.reduce((s, p) => s + p, 0);
        if (total <= 0) return 0;
        return probs.reduce((s, p) => s + (p / total) ** 2, 0);
      }

      const SCEN_CONF_HIGH_HHI  = 0.55;
      const SCEN_CONF_HIGH_PROB = 0.50;
      const SCEN_CONF_MID_HHI   = 0.35;
      const SCEN_CONF_MID_PROB  = 0.40;
      const SCEN_AXIS2_FP_GAP   = 15.0; // %pt

      const _fp1stProb = ranked2.find(b => b.boat === fp1st)?.final_prob ?? 0;
      const _fp2ndProb = ranked2.find(b => b.boat === fp2nd)?.final_prob ?? 0;
      const _fpDiffPct = (_fp1stProb - _fp2ndProb) * 100;
      const _hhi = _calcHHI(fp1st);

      let _confRank;
      if (_hhi >= SCEN_CONF_HIGH_HHI && _fp1stProb >= SCEN_CONF_HIGH_PROB) {
        _confRank = 'HIGH';
      } else if (_hhi >= SCEN_CONF_MID_HHI || _fp1stProb >= SCEN_CONF_MID_PROB) {
        _confRank = 'MID';
      } else {
        _confRank = 'LOW';
      }
      const _allow2ndAxis = _fpDiffPct <= SCEN_AXIS2_FP_GAP;

      // ── ブロック生成（buildScenarioBuyPanel 通常モードと完全一致）──
      const p2r1 = getP2Ranking(fp1st);
      const second_A = p2r1[0];
      const second_B = p2r1[1];
      const block1 = second_A != null ? makeBlock(fp1st, second_A, getP3Ranking(fp1st, second_A)) : [];
      const block2 = second_B != null ? makeBlock(fp1st, second_B, getP3Ranking(fp1st, second_B)) : [];

      let block3;
      let second_C;
      if (_confRank === 'HIGH') {
        // 高確信: 1軸固定・block3なし（最大12点）
        second_C = null;
        block3 = [];
      } else if (_allow2ndAxis) {
        // MID/LOW かつ fp差 ≤ 15%pt: 2軸展開（最大18点）
        const p2r2 = getP2Ranking(fp2nd);
        second_C = p2r2[0];
        block3 = (fp2nd != null && second_C != null)
          ? makeBlock(fp2nd, second_C, getP3Ranking(fp2nd, second_C))
          : [];
      } else {
        // MID/LOW かつ fp差 > 15%pt: 2軸目なし
        second_C = null;
        block3 = [];
      }

      // 重複除去
      const allCombosSet = new Set();
      const allCombos = [];
      [block1, block2, block3].forEach(block => {
        block.forEach(c => {
          if (!allCombosSet.has(c)) { allCombosSet.add(c); allCombos.push(c); }
        });
      });

      if (allCombos.length === 0) return _empty;

      // ── hitProbEst 算出（各買い目の calcScenarioComboProb を合算）──
      let rawHitProb = 0;
      let knownCount = 0;
      allCombos.forEach(c => {
        const winner = parseInt(c.split('-')[0]);
        const p = calcScenarioComboProb(c, winner, sd);
        if (p != null && !isNaN(p)) {
          rawHitProb += p;
          knownCount++;
        }
      });

      // 確率が取れた買い目が1つ以上あれば hitProbEst を確定
      const rawHitProbEst = knownCount > 0 ? rawHitProb : null;

      // ── キャリブレーション補正 ──
      // rawHitProbEst は系統的に過小評価されているため CALIB_POINTS で補正する。
      // 補正後は「実際の的中率に近い確率」を返す。
      const hitProbEst = rawHitProbEst != null ? calibrateProb(rawHitProbEst) : null;

      // ── 加重確率ベースの 2着/3着 順位算出 ──
      //
      // 【改善ポイント】
      //   旧: combo の 2着ポジション出現頻度 → 買い目構成バイアスで誤判定
      //   新: scenarioProb × p2 の加重合計 → 真の2着確率に基づく順位
      //
      // top_stats.js の collectResultsForDateScen が actual2nd / actual3rd を持っている
      // ため、ここでは ranked 配列のみを返す。actual との照合は呼び出し側が行う。

      const { weighted: weighted2nd, ranked: ranked2ndList } = calcWeighted2nd(sd, fp1st);
      const { weighted: weighted3rd, ranked: ranked3rdList } = calcWeighted3rd(sd, fp1st);

      return {
        combos      : allCombos,
        hitProbEst,             // キャリブレーション補正済み
        _rawHitProbEst: rawHitProbEst, // デバッグ用（補正前）
        synthOdds   : null,     // 呼び出し側（top_stats.js）で ODDS_DATA から計算
        ev          : null,     // 同上（synthOdds が確定してから計算）
        // 2着/3着順位リスト（top_stats.js で actual2nd/3rd と照合して pred?ndRank を付与）
        ranked2ndList,          // [最有力艇, 2位艇, ...] 加重確率降順
        ranked3rdList,          // 同上（3着）
        // デバッグ用
        weighted2nd,
        weighted3rd,
        // pred?ndRank は呼び出し側で actual2nd/3rd と突き合わせるため
        // ここでは返さない（actual が不明なため）
        pred2ndRank : null,
        pred3rdRank : null,
      };

    } catch (e) {
      // console.warn('[computeScenCombosWithEV] エラー:', e);  // suppressed
      return {
        combos: [], hitProbEst: null, synthOdds: null, ev: null,
        pred2ndRank: null, pred3rdRank: null,
        weighted2nd: {}, weighted3rd: {},
      };
    }
  };


  // ─────────────────────────────────────────────────────────────────────────
  // § 4  top_stats.js の collectResultsForDateScen へのパッチ
  //
  //       top_stats.js の pred2ndRank / pred3rdRank 算出箇所（「頻度ベース」）を
  //       加重確率ベースに差し替えるモンキーパッチ。
  //
  //       【設計方針】
  //         top_stats.js を直接編集するのではなく、
  //         computeScenCombosWithEV の戻り値に ranked2ndList / ranked3rdList を
  //         持たせ、top_stats.js 側でそれを使って pred?ndRank を算出させる。
  //
  //         ただし top_stats.js は既存コードのため ranked2ndList を参照していない。
  //         そのため、collectResultsForDateScen をラップして
  //         results[] の各エントリに ranked2ndList を使った pred?ndRank を上書きする。
  //
  //       【適用条件】
  //         - collectResultsForDateScen が定義済みであること
  //         - まだラップされていないこと（二重ラップ防止）
  // ─────────────────────────────────────────────────────────────────────────

  function _applyPred2ndPatch() {
    if (typeof collectResultsForDateScen !== 'function') return;
    if (collectResultsForDateScen._patched) return; // 二重ラップ防止

    const _orig = collectResultsForDateScen;

    window.collectResultsForDateScen = function (dateStr, includeAll) {
      const results = _orig.call(this, dateStr, includeAll);
      if (!Array.isArray(results)) return results;

      // computeScenCombosWithEV の ranked2ndList / ranked3rdList を使って
      // pred2ndRank / pred3rdRank を加重確率ベースに上書き
      results.forEach(r => {
        // 再計算が必要かチェック（ranked2ndList が返ってきていない場合はスキップ）
        // top_stats.js 内ですでに computeScenCombosWithEV を呼んでいるが
        // ranked2ndList を使っていないため、ここで再度算出する。
        if (r.actual2nd == null && r.actual3rd == null) return;

        try {
          const dataForDate = (typeof getDataForDate === 'function')
            ? getDataForDate(dateStr) : null;
          if (!dataForDate) return;
          const vdata = dataForDate[r.venue];
          if (!vdata) return;

          const res = window.computeScenCombosWithEV(r.venue, vdata, r.rno);
          if (!res) return;

          // ── 加重確率ベースで pred2ndRank を上書き ──
          if (r.actual2nd != null && res.ranked2ndList?.length > 0) {
            const idx = res.ranked2ndList.indexOf(r.actual2nd);
            r.pred2ndRank = idx >= 0 ? idx + 1 : null;
          }

          // ── 加重確率ベースで pred3rdRank を上書き ──
          if (r.actual3rd != null && res.ranked3rdList?.length > 0) {
            const idx = res.ranked3rdList.indexOf(r.actual3rd);
            r.pred3rdRank = idx >= 0 ? idx + 1 : null;
          }

          // ── hitProbEst も更新（キャリブレーション補正済みの値で上書き）──
          if (res.hitProbEst != null) {
            r.hitProbEst = res.hitProbEst;
            r.hitRate    = res.hitProbEst; // hitRate は hitProbEst の別名
          }

        } catch (_e) { /* エラーは無視して元の値を保持 */ }
      });

      return results;
    };

    window.collectResultsForDateScen._patched = true;
    console.log('[computeScenCombosWithEV] collectResultsForDateScen パッチ適用済み（加重確率ベース pred2ndRank/pred3rdRank）');
  }

  // DOM 読み込み後に適用（top_stats.js が先に読み込まれている前提）
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _applyPred2ndPatch);
  } else {
    // 既に DOMContentLoaded 済み → 遅延実行で top_stats.js の定義を待つ
    setTimeout(_applyPred2ndPatch, 0);
  }

  console.log('[computeScenCombosWithEV] モジュール読み込み完了');

})();


// ══════════════════════════════════════════════════════════════════════════════
// 【使い方まとめ】
//
// 1. このファイルを以下の順序で HTML に読み込む:
//      <script src="sample.js"></script>
//      <script src="top_stats.js"></script>
//      <script src="calibration.js"></script>
//      <script src="dynamic_inn2place.js"></script>
//      <script src="computeScenCombosWithEV.js"></script>  ← 最後に追加
//
// 2. calibration.js の _renderCalibrationPanel 末尾に以下を追加すると
//    キャリブレーション補正テーブルが自動更新される:
//
//      // 補正テーブルを自動更新
//      const _binStats = calcCalibration(results);
//      if (typeof updateCalibPoints === 'function') updateCalibPoints(_binStats);
//
// 3. top_stats.js / sample.js の変更は一切不要。
//
// 【期待される改善効果】
//
//  ■ hitProbEst キャリブレーション
//    加重平均誤差: 10.6% → 目標 5% 以下
//    （実測 binStats を updateCalibPoints に渡し続けることで自動改善）
//
//  ■ 2着1位的中率
//    旧（頻度ベース）: 24% → 改善目標: 40〜45%
//    理由: 買い目構成バイアスを排除し、真の2着確率で順位付けするため
//
//  ■ 3着1位的中率
//    旧（頻度ベース）: 20% → 改善目標: 30〜35%
//    理由: merged3rdMap の r3 × p2 × scenarioProb で真の3着確率を算出するため
//
//  ■ 買い目点数の一致（修正④）
//    旧: 常に2軸18点で固定 → 画面表示（buildScenarioBuyPanel）と食い違うケースあり
//    新: _confRank（HIGH/MID/LOW）と _allow2ndAxis を追加
//        HIGH または fp差>15%pt → 1軸最大12点
//        MID/LOW かつ fp差≤15%pt → 2軸最大18点（重複除去後16〜18点）
//        → top_stats.js の集計点数・期待値が画面表示と完全に一致する
//

//    hitProbEst が実態に近づくことで EV = synthOdds × hitProbEst の精度が向上し、
//    EV フィルタ（例: EV ≥ 1.1）による買い目選別の正確性が上がる。
//    「高EV → 実際に高回収」の相関が強まり、長期的な回収率改善に寄与する。
//
// ══════════════════════════════════════════════════════════════════════════════
