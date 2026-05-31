// ══════════════════════════════════════════════════════════════════════════════
// quality_filter_patch.js  — 買い目品質向上パッチ
//
// 【概要】
//   2着・3着候補を「確率の絶対値と断絶」で絞り込み、
//   予想家らしい「根拠のある目だけ買う」買い目構成を実現する。
//
// 【修正内容】
//
//   修正① getPlace2Ranking / getP2Ranking に閾値フィルターを追加
//     - 断絶検出 (GAP) : 1位との差が P2_GAP_THRESHOLD 以上 → そこで打ち切り
//     - 絶対足切り      : P2_MIN_RATE 未満の艇を除外
//     - 2着1位が P2_DOMINANT_THRESHOLD 以上 → 2位以下を自動カット（1本釣り）
//
//   修正② getPlace3Ranking / getP3Ranking に絶対足切りを追加
//     - P3_MIN_RATE 未満の3着候補を除外
//
//   修正③ 閾値はすべて冒頭の定数で一元管理（バックテスト後に調整可）
//
// 【読み込み順】
//   <script src="sample.js"></script>
//   <script src="top_stats.js"></script>
//   <script src="calibration.js"></script>
//   <script src="computeScenCombosWithEV.js"></script>
//   <script src="quality_filter_patch.js"></script>  ← 最後に追加
//
// 【既存ファイルへの変更】
//   sample.js / computeScenCombosWithEV.js の変更は一切不要。
//   このファイルがモンキーパッチで両方の内部関数を上書きする。
//
// ══════════════════════════════════════════════════════════════════════════════

(function () {

  // ─────────────────────────────────────────────────────────────────────────
  // § 1  閾値定数（ここだけ変えればOK）
  //
  //  バックテストの目安:
  //    P2_GAP_THRESHOLD  : 0.15〜0.25  ← 小さくすると絞り込み緩和
  //    P2_MIN_RATE       : 0.10〜0.18  ← 小さくすると低確率も残す
  //    P2_DOMINANT       : 0.45〜0.55  ← 大きくすると1本釣り発動しにくくなる
  //    P3_MIN_RATE       : 0.12〜0.18  ← 3着の足切りライン
  // ─────────────────────────────────────────────────────────────────────────

  // 2着候補フィルター
  const P2_GAP_THRESHOLD       = 0.20;  // 1位との差がこれ以上 → 断絶とみなし打ち切り
  const P2_MIN_RATE            = 0.13;  // この確率未満の艇は問答無用で除外
  const P2_DOMINANT            = 0.50;  // 2着1位がこれ以上 → 2着は1艇のみに絞る（1本釣り）

  // 3着候補フィルター
  const P3_MIN_RATE            = 0.15;  // この確率未満の3着候補は除外

  // 1着・2軸目の最終確率フィルター
  // 【変更点】
  //   旧: fp差≤15%ptのとき2軸目を出す（差ベース）
  //   新: fp2ndの絶対値≥20%のとき2軸目を出す（絶対値ベース）
  //   理由: 52.6% vs 26.8% のように差は大きくても2位が有力なケースで
  //         旧ロジックは2軸目を出さなかった。絶対値で判断するのが実態に合う。
  const FP2ND_MIN_FOR_2AXIS    = 0.20;  // 2軸目(fp2nd)の最終確率がこれ以上なら2軸展開
  const FP1ST_MIN_FOR_BUY      = 0.25;  // 1着軸の最終確率がこれ未満なら買い目を出さない

  // ─────────────────────────────────────────────────────────────────────────
  // § 2  共通フィルター関数
  // ─────────────────────────────────────────────────────────────────────────

  /**
   * 2着候補リストを確率付きで受け取り、閾値フィルター後のリストを返す。
   *
   * @param {Array<{boat: number, prob: number}>} rankedWithProb
   *   [{boat, prob}] の降順配列（prob は正規化済み 0〜1）
   * @returns {number[]}  フィルター後の艇番配列（確率降順）
   *
   * 適用ルール（優先順）:
   *   1. P2_DOMINANT   : 1位確率 >= 0.50 → 1位のみ返す
   *   2. P2_MIN_RATE   : 各艇の確率が 0.13 未満 → 除外
   *   3. P2_GAP        : 前の艇との差が 0.20 以上 → そこで打ち切り
   */
  function filterP2Candidates(rankedWithProb) {
    if (!rankedWithProb || rankedWithProb.length === 0) return [];

    const top = rankedWithProb[0];

    // ルール1: 断然人気 → 1本釣り
    if (top.prob >= P2_DOMINANT) {
      return [top.boat];
    }

    const result = [];
    let prevProb = null;

    for (const { boat, prob } of rankedWithProb) {
      // ルール2: 絶対足切り
      if (prob < P2_MIN_RATE) break;

      // ルール3: 断絶検出（1位との差）
      if (top.prob - prob >= P2_GAP_THRESHOLD) break;

      result.push(boat);
      prevProb = prob;
    }

    return result;
  }

  /**
   * 3着候補リストを確率付きで受け取り、絶対足切りを適用して返す。
   *
   * @param {Array<{boat: number, r3: number}>} thirdList
   *   merged3rdMap の生リスト
   * @param {number} winnerBoat
   * @param {number} secondBoat
   * @returns {number[]}  フィルター後の艇番配列（上位3点まで）
   */
  function filterP3Candidates(thirdList, winnerBoat, secondBoat) {
    return thirdList
      .filter(x => x.boat !== winnerBoat && x.boat !== secondBoat)
      .filter(x => (x.r3 ?? 0) >= P3_MIN_RATE)
      .slice(0, 3)
      .map(x => x.boat);
  }


  // ─────────────────────────────────────────────────────────────────────────
  // § 3  sample.js の buildScenarioBuyPanel へのパッチ
  //
  //   buildScenarioBuyPanel は関数スコープ内に getPlace2Ranking /
  //   getPlace3Ranking を持つため直接上書きできない。
  //   代わりに呼び出し元の buildScenarioBuyPanel 自体をラップして、
  //   生成済み allCombos を「フィルター後ロジックで再構築」する方法は複雑になるため、
  //
  //   より確実な方法として:
  //     - window._qualityFilter_p2 / _qualityFilter_p3 を公開
  //     - buildScenarioBuyPanel 内の getPlace2Ranking / getPlace3Ranking が
  //       呼ばれた結果のランキング配列を、次のステップで再フィルターする
  //
  //   実装: buildScenarioBuyPanel をフルラップし、
  //         sd オブジェクトに事前フィルター済みのプロキシを渡す方式を採用。
  //
  // ─────────────────────────────────────────────────────────────────────────

  /**
   * scenarioPlace2 のプロキシを作り、各 p2 リストをフィルター済み結果に差し替える。
   * buildScenarioBuyPanel の getPlace2Ranking が内部で scenarioPlace2 を参照するため、
   * プロキシを渡すことで既存コードを一行も変えずにフィルターを注入できる。
   *
   * ただし getPlace2Ranking は kimari × p2 の加重平均を自前で計算するため、
   * p2 リストを差し替えても「最終ランキング」自体は内部で再計算される。
   *
   * → より直接的に: buildScenarioBuyPanel の返す HTML から allCombos を再計算するより、
   *   buildScenarioBuyPanel 自体をラップして内部の second_A/B/C を差し替える方が確実。
   *
   * 【採用方式】
   *   window.buildScenarioBuyPanel をラップし、
   *   呼び出し前に sd.scenarioPlace2 / sd.merged3rdMap を「フィルター適用済みコピー」に置換。
   *   呼び出し後に元に戻す（副作用なし）。
   */

  // ── 2着ランキング（加重確率付き）を計算するユーティリティ ──
  // buildScenarioBuyPanel 内部の getPlace2Ranking と同じロジック + 確率値を返す版
  function _calcP2RankedWithProb(sd, winnerBoat) {
    const scenarioPlace2 = sd?.scenarioPlace2;
    if (!scenarioPlace2?.[winnerBoat]) return [];

    const totals = {};
    let weightSum = 0;
    for (const [kimari, list] of Object.entries(scenarioPlace2[winnerBoat])) {
      const scenProb = sd.scenarioProb?.[winnerBoat]?.[kimari] ?? 0;
      weightSum += scenProb;
      (list || []).forEach(x => {
        totals[x.boat] = (totals[x.boat] ?? 0) + x.p2 * scenProb;
      });
    }
    if (weightSum > 0) {
      Object.keys(totals).forEach(k => { totals[k] /= weightSum; });
    }
    return Object.entries(totals)
      .sort((a, b) => b[1] - a[1])
      .map(([boat, prob]) => ({ boat: parseInt(boat), prob }));
  }

  // ── 3着ランキング（確率付き）を計算するユーティリティ ──
  function _calcP3RankedWithProb(sd, winnerBoat, secondBoat) {
    return (sd.merged3rdMap?.[winnerBoat]?.[secondBoat] || [])
      .filter(x => x.boat !== winnerBoat && x.boat !== secondBoat)
      .map(x => ({ boat: x.boat, r3: x.r3 ?? 0 }))
      .sort((a, b) => b.r3 - a.r3);
  }

  /**
   * sd の scenarioPlace2 / merged3rdMap をフィルター適用済みコピーで置換した
   * 新しい sd オブジェクトを返す。
   * 元の sd は変更しない（shallow clone）。
   */
  function _buildFilteredSd(sd, ranked2) {
    if (!sd) return sd;

    // ── 2着フィルター適用済み scenarioPlace2 の構築 ──
    // getPlace2Ranking が参照する p2 リストを「フィルター通過艇のみ」に差し替える。
    // 具体的には: 各 winnerBoat の加重2着ランキングを計算 → filterP2Candidates で絞り込み
    //             → 絞り込み後の艇のみ p2 を残した新リストに置換する。
    const filteredPlace2 = {};
    const allowedP2ByWinner = {}; // { winnerBoat: Set<boat> }

    if (sd.scenarioPlace2) {
      for (const [winnerStr, kimariMap] of Object.entries(sd.scenarioPlace2)) {
        const winnerBoat = parseInt(winnerStr);

        // 1. 加重確率付きランキングを計算
        const rankedWithProb = _calcP2RankedWithProb(sd, winnerBoat);

        // 2. フィルター適用
        const allowed = new Set(filterP2Candidates(rankedWithProb));
        allowedP2ByWinner[winnerBoat] = allowed;

        // 3. 通過艇のみ残した新 kimariMap を構築
        const newKimariMap = {};
        for (const [kimari, list] of Object.entries(kimariMap)) {
          const newList = (list || []).filter(x => allowed.has(x.boat));
          newKimariMap[kimari] = newList;
        }
        filteredPlace2[winnerStr] = newKimariMap;
      }
    }

    // ── 3着フィルター適用済み merged3rdMap の構築 ──
    const filteredMerged3rd = {};
    if (sd.merged3rdMap) {
      for (const [winnerStr, secondMap] of Object.entries(sd.merged3rdMap)) {
        const winnerBoat = parseInt(winnerStr);
        filteredMerged3rd[winnerStr] = {};
        for (const [secondStr, thirdList] of Object.entries(secondMap)) {
          const secondBoat = parseInt(secondStr);
          const filtered = filterP3Candidates(thirdList, winnerBoat, secondBoat);
          // filtered は artボート番号配列 → 元の r3 情報を保持した形に戻す
          const origMap = {};
          (thirdList || []).forEach(x => { origMap[x.boat] = x; });
          filteredMerged3rd[winnerStr][secondStr] = filtered.map(b => origMap[b]).filter(Boolean);
        }
      }
    }

    // sd のシャローコピーに差し替えた map を注入
    return Object.assign({}, sd, {
      scenarioPlace2: filteredPlace2,
      merged3rdMap  : filteredMerged3rd,
      // デバッグ用: フィルター前の元データも保持
      _orig_scenarioPlace2: sd.scenarioPlace2,
      _orig_merged3rdMap  : sd.merged3rdMap,
      _allowedP2ByWinner  : allowedP2ByWinner,
    });
  }


  // ─────────────────────────────────────────────────────────────────────────
  // § 4  buildScenarioBuyPanel のラップ
  // ─────────────────────────────────────────────────────────────────────────

  function _wrapBuildScenarioBuyPanel() {
    if (typeof buildScenarioBuyPanel !== 'function') return;
    if (buildScenarioBuyPanel._qualityPatched) return;

    const _orig = buildScenarioBuyPanel;

    window.buildScenarioBuyPanel = function (ranked2, sd, resultSan3, raceOdds3tEv, comboToBadges, normalizeCombo, rno) {
      // フィルター適用済み sd を構築して渡す
      const filteredSd = _buildFilteredSd(sd, ranked2);

      // 【変更】sample.js 内の SCEN_AXIS2_FP_GAP(15%pt差ベース) を上書きするため
      // ranked2 の fp2nd 絶対値が FP2ND_MIN_FOR_2AXIS 未満なら fp2nd を null に差し替え
      // → buildScenarioBuyPanel 内の _allow2ndAxis が false になる
      // また fp1st が FP1ST_MIN_FOR_BUY 未満なら ranked2 を空配列にして買い目なしにする
      const fp1stProb = ranked2[0]?.final_prob ?? 0;
      const fp2ndProb = ranked2[1]?.final_prob ?? 0;

      if (fp1stProb < FP1ST_MIN_FOR_BUY) {
        // 買い目なし: 空の ranked2 を渡して早期リターンさせる
        return _orig.call(this, [], filteredSd, resultSan3, raceOdds3tEv, comboToBadges, normalizeCombo, rno);
      }

      // fp2nd が閾値未満の場合: ranked2 から fp2nd エントリを除去して1軸に強制
      let filteredRanked2 = ranked2;
      if (fp2ndProb < FP2ND_MIN_FOR_2AXIS) {
        // fp2nd を末尾に移動（final_prob を 0 にして確信度判定に影響させない）
        filteredRanked2 = ranked2.map((b, i) =>
          i === 1 ? Object.assign({}, b, { final_prob: 0 }) : b
        );
      }

      return _orig.call(this, filteredRanked2, filteredSd, resultSan3, raceOdds3tEv, comboToBadges, normalizeCombo, rno);
    };

    window.buildScenarioBuyPanel._qualityPatched = true;
    console.log('[quality_filter_patch] buildScenarioBuyPanel にフィルターパッチを適用しました');
  }


  // ─────────────────────────────────────────────────────────────────────────
  // § 5  buildInTepBuyPanel のラップ（イン鉄板タブ用）
  //
  //   buildInTepBuyPanel は getPlace2Ranking2 / getPlace3List を内部で持つ。
  //   同様に sd をフィルター済みコピーで置換する。
  // ─────────────────────────────────────────────────────────────────────────

  function _wrapBuildInTepBuyPanel() {
    if (typeof buildInTepBuyPanel !== 'function') return;
    if (buildInTepBuyPanel._qualityPatched) return;

    const _orig = buildInTepBuyPanel;

    window.buildInTepBuyPanel = function (ranked2, sd, resultSan3, raceOdds3tEv, comboToBadges, normalizeCombo) {
      const filteredSd = _buildFilteredSd(sd, ranked2);
      return _orig.call(this, ranked2, filteredSd, resultSan3, raceOdds3tEv, comboToBadges, normalizeCombo);
    };

    window.buildInTepBuyPanel._qualityPatched = true;
    console.log('[quality_filter_patch] buildInTepBuyPanel にフィルターパッチを適用しました');
  }


  // ─────────────────────────────────────────────────────────────────────────
  // § 6  computeScenCombosWithEV のラップ（top_stats.js 集計用）
  //
  //   computeScenCombosWithEV は内部で getP2Ranking / getP3Ranking を持つ。
  //   こちらは sd を受け取る前に calcScenarioData を内部で呼ぶため、
  //   sd が確定した後のタイミングでフィルターを適用する必要がある。
  //
  //   → computeScenCombosWithEV 自体をラップし、
  //     内部で使う sd を差し替えることはできないため、
  //     戻り値の combos を「フィルター済みロジックで再計算した combos」で上書きする方式を採用。
  //
  //   実装:
  //     1. 元の computeScenCombosWithEV を呼び出す
  //     2. sd を再取得（calcScenarioData / calcTenkaiProbs を再実行は重いため
  //        戻り値の combos だけを filteredSd で再生成してすり替える）
  //
  //   ※ sd の再取得が必要なため、calcScenarioData が公開されている前提。
  //      未定義の場合は元の combos をそのまま返す（安全フォールバック）。
  // ─────────────────────────────────────────────────────────────────────────

  function _wrapComputeScenCombosWithEV() {
    if (typeof window.computeScenCombosWithEV !== 'function') return;
    if (window.computeScenCombosWithEV._qualityPatched) return;

    const _orig = window.computeScenCombosWithEV;

    window.computeScenCombosWithEV = function (venue, vdata, rno) {
      const result = _orig.call(this, venue, vdata, rno);
      if (!result || result.combos.length === 0) return result;

      // ── sd を再取得してフィルター済み combos を再構築 ──
      try {
        if (typeof calcScenarioData !== 'function' ||
            typeof calcTenkaiProbs  !== 'function') return result;

        const rd = vdata?.races?.[String(rno)];
        if (!rd || !rd.boats || rd.boats.length < 2) return result;

        // tenjiScoreMap の取得（computeScenCombosWithEV 本体と同じロジック）
        let tenjiScoreMap = {};
        try {
          if (typeof _ensureTenjiCache === 'function') _ensureTenjiCache();
          if (typeof tenjiKey === 'function' && typeof _tenjiCache !== 'undefined') {
            const slug = (typeof SLUG_MAP !== 'undefined' && SLUG_MAP[venue]) ? SLUG_MAP[venue] : venue;
            const tk = tenjiKey(slug, vdata.date, rno);
            tenjiScoreMap = _tenjiCache[tk] || {};
          }
        } catch (_e) {}

        const _origDATA  = window.DATA;
        const _origVenue = window.currentVenue;
        let ranked2, sd;
        try {
          window.DATA         = Object.assign({}, vdata, { venue });
          window.currentVenue = venue;
          const _arek = (typeof rd.arek === 'number' && rd.arek > 0) ? rd.arek : 54.7;
          ranked2 = calcTenkaiProbs(rd.boats, _arek);
          if (!ranked2 || ranked2.length < 2) return result;
          sd = calcScenarioData(ranked2, rd.boats, tenjiScoreMap);
        } finally {
          window.DATA         = _origDATA;
          window.currentVenue = _origVenue;
        }
        if (!sd || !sd.valid) return result;

        // ── フィルター適用済み sd で combos を再構築 ──
        const filteredSd = _buildFilteredSd(sd, ranked2);

        const fp1st = ranked2[0]?.boat;
        const fp2nd = ranked2[1]?.boat;
        if (fp1st == null) return result;

        // getP2Ranking（フィルター済み sd 版）
        function getP2RankingF(winnerBoat) {
          const rankedWithProb = _calcP2RankedWithProb(filteredSd, winnerBoat);
          return rankedWithProb.map(x => x.boat);
        }

        // getP3Ranking（フィルター済み sd 版）
        function getP3RankingF(winnerBoat, secondBoat) {
          const thirdAll = filteredSd.merged3rdMap?.[winnerBoat]?.[secondBoat] || [];
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

        function makeBlockF(winner, second, thirdCandidates) {
          const thirds = thirdCandidates.filter(t => t !== winner && t !== second);
          return [
            ...thirds.map(t => `${winner}-${second}-${t}`),
            ...thirds.map(t => `${winner}-${t}-${second}`),
          ];
        }

        // 確信度ランク再判定
        function calcHHIF(winnerBoat) {
          const probs = filteredSd?.kimariTypes?.map(k => filteredSd.scenarioProb?.[winnerBoat]?.[k] ?? 0) ?? [];
          const total = probs.reduce((s, p) => s + p, 0);
          if (total <= 0) return 0;
          return probs.reduce((s, p) => s + (p / total) ** 2, 0);
        }

        const _fp1stProb = ranked2.find(b => b.boat === fp1st)?.final_prob ?? 0;
        const _fp2ndProb = ranked2.find(b => b.boat === fp2nd)?.final_prob ?? 0;
        const _fpDiff    = (_fp1stProb - _fp2ndProb) * 100;
        const _hhi       = calcHHIF(fp1st);

        // 1着軸の最終確率が低すぎる場合は買い目なし
        if (_fp1stProb < FP1ST_MIN_FOR_BUY) return result;

        let _confRank;
        if (_hhi >= 0.55 && _fp1stProb >= 0.50) _confRank = 'HIGH';
        else if (_hhi >= 0.35 || _fp1stProb >= 0.40) _confRank = 'MID';
        else _confRank = 'LOW';

        // 【変更】2軸目の判定: fp差ベース → fp2nd絶対値ベース
        // fp2ndが FP2ND_MIN_FOR_2AXIS(20%) 以上あれば2軸展開
        const _allow2ndAxis = _fp2ndProb >= FP2ND_MIN_FOR_2AXIS;

        const p2r1 = getP2RankingF(fp1st);
        const second_A = p2r1[0];
        const second_B = p2r1[1];
        const block1 = second_A != null ? makeBlockF(fp1st, second_A, getP3RankingF(fp1st, second_A)) : [];
        const block2 = second_B != null ? makeBlockF(fp1st, second_B, getP3RankingF(fp1st, second_B)) : [];

        let block3 = [];
        if (_confRank !== 'HIGH' && _allow2ndAxis) {
          const p2r2 = getP2RankingF(fp2nd);
          const second_C = p2r2[0];
          block3 = second_C != null ? makeBlockF(fp2nd, second_C, getP3RankingF(fp2nd, second_C)) : [];
        }

        const allCombosSet = new Set();
        const newCombos = [];
        [block1, block2, block3].forEach(block => {
          block.forEach(c => {
            if (!allCombosSet.has(c)) { allCombosSet.add(c); newCombos.push(c); }
          });
        });

        if (newCombos.length === 0) return result; // フィルターで全滅なら元を返す

        return Object.assign({}, result, { combos: newCombos });

      } catch (e) {
        console.warn('[quality_filter_patch] computeScenCombosWithEV ラップ中エラー:', e);
        return result;
      }
    };

    window.computeScenCombosWithEV._qualityPatched = true;
    console.log('[quality_filter_patch] computeScenCombosWithEV にフィルターパッチを適用しました');
  }


  // ─────────────────────────────────────────────────────────────────────────
  // § 7  デバッグ用ユーティリティ
  //
  //   コンソールから呼び出して現在の閾値と効果を確認できる。
  //   例: qualityFilterDebug(sd, ranked2, 1)
  // ─────────────────────────────────────────────────────────────────────────

  window.qualityFilterDebug = function (sd, ranked2, winnerBoat) {
    console.group(`[quality_filter_patch] デバッグ: 1着 ${winnerBoat}号艇`);
    const rankedWithProb = _calcP2RankedWithProb(sd, winnerBoat);
    console.log('2着候補（フィルター前）:', rankedWithProb.map(x => `${x.boat}号(${(x.prob*100).toFixed(1)}%)`).join(', '));
    const filtered = filterP2Candidates(rankedWithProb);
    console.log('2着候補（フィルター後）:', filtered.join(', ') + '号');
    console.log('適用閾値:', { P2_GAP_THRESHOLD, P2_MIN_RATE, P2_DOMINANT, P3_MIN_RATE });
    console.groupEnd();
  };

  /**
   * 閾値を動的に変更する（バックテスト中に使用）。
   * 例: setQualityFilterThresholds({ P2_GAP_THRESHOLD: 0.18, P3_MIN_RATE: 0.12 })
   */
  window.setQualityFilterThresholds = function (opts) {
    // ※ const は再代入不可のためこの関数は参考実装
    // 実際にバックテストで動的変更する場合は § 1 の const を let に変更すること
    console.warn('[quality_filter_patch] 閾値の動的変更は § 1 の const を let に変えた上で再実装してください。現在の閾値:', { P2_GAP_THRESHOLD, P2_MIN_RATE, P2_DOMINANT, P3_MIN_RATE });
  };


  // ─────────────────────────────────────────────────────────────────────────
  // § 8  適用（DOMContentLoaded 後に実行）
  // ─────────────────────────────────────────────────────────────────────────

  function _applyPatches() {
    _wrapBuildScenarioBuyPanel();
    _wrapBuildInTepBuyPanel();
    _wrapComputeScenCombosWithEV();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _applyPatches);
  } else {
    setTimeout(_applyPatches, 0);
  }

  console.log('[quality_filter_patch] モジュール読み込み完了');

})();


// ══════════════════════════════════════════════════════════════════════════════
// 【修正サマリー】
//
//  修正① 2着候補の断絶検出
//    1位との差が 20%pt 以上で打ち切り。
//    例）2号45% / 3号20% → 差25%pt → 3号以降カット → 2着は2号のみ
//
//  修正② 2着候補の絶対足切り
//    確率が 13% 未満の艇は除外。
//    例）5号9% → カット
//
//  修正③ 2着1本釣り
//    2着1位が 50% 以上 → 1艇のみに絞り合成オッズを上げる。
//    先ほどの唐津12Rだと 2号45% は惜しくも未満だが
//    断絶検出が発動して事実上1本釣りと同結果になる。
//
//  修正④ 3着候補の絶対足切り
//    3着確率 15% 未満の候補を除外。薄い組み合わせを自動カット。
//
//  【期待される効果】
//    唐津12R（1号82.5%）の場合:
//      修正前: 1-2-{4,3,5} / 1-{4,3,5}-2 + 1-3-{4,2,5}... = 最大12点
//      修正後: 1-2-{4,3} / 1-{4,3}-2 = 4点（2号断然・3着5号は足切り）
//      → 合成オッズが上がり EV 向上
//
//  【バックテスト推奨手順】
//    1. top_stats.js の collectResultsForDateScen で的中率・回収率を計測
//    2. § 1 の閾値を変えて再計測
//    3. P2_GAP_THRESHOLD を 0.15〜0.25 で走査すると最適点が見つかりやすい
//
// ══════════════════════════════════════════════════════════════════════════════
