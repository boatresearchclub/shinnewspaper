// ══════════════════════════════════════════════════════════════════════════════
// manshu_hunter.js  — 万舟ハンター（管理者専用モジュール）
//
// 【設計方針】
//   ・既存ファイル（sample.js / top_page.js / top_stats.js / computeScenCombosWithEV.js）
//     に一切手を加えない。完全独立・非破壊。
//   ・document.body.classList.contains('admin-mode') を既存と共通の認証ゲートウェイとして使用。
//   ・表示場所: トップページ (#top-page) の末尾に管理者専用セクションを動的注入。
//   ・非管理者にはDOM要素自体が存在しない（display:none ではなくDOM注入しない）。
//
// 【機能一覧】
//   § 1  マーケット乖離スコア   — AI確率 vs オッズ逆数の乖離率トップ買い目
//   § 2  万舟発生条件スキャナー — 当日レースの「混戦度」「逆転確率」スコアリング
//   § 3  高配当履歴アナライザー — 過去的中の万舟・高配当をフィルターして特徴抽出
//   § 4  マーケット乖離バックテスト — 乖離スコア戦略の過去30日損益
//
// 【読み込み方法】
//   既存の </body> 直前に以下を追加するだけ（他ファイルより後に読む）:
//   <script src="manshu_hunter.js"></script>
// ══════════════════════════════════════════════════════════════════════════════

(function () {
  'use strict';

  // ── 定数 ──────────────────────────────────────────────────────────────────
  const MODULE_ID      = 'manshu-hunter-root';
  const MANSHU_THRESH  = 10000;   // 万舟判定: 配当 10,000円（100倍）以上
  const HIGH_DIV_THRESH = 5000;   // 高配当判定: 5,000円（50倍）以上
  const DIVERGE_THRESH  = 1.8;    // 乖離スコア閾値（AI確率 / 市場確率 ≥ この値を"エッジあり"）
  const ENTROPY_LOW_THRESH = 1.8; // シャノンエントロピー閾値（これ以下 = 軸固定）
  const ENTROPY_HIGH_THRESH = 2.3;// これ以上 = 高混戦（万舟発生しやすい）

  // ── CSS変数は既存テーマを継承 ─────────────────────────────────────────────
  const STYLE = `
    #${MODULE_ID} {
      margin-top: 16px;
      padding: 0 4px 24px;
    }
    .mh-section-header {
      display: flex;
      align-items: center;
      gap: 6px;
      padding: 6px 0 8px;
      border-bottom: 2px solid var(--accent, #e84393);
      margin-bottom: 10px;
    }
    .mh-section-title {
      font-size: 11px;
      font-weight: 800;
      letter-spacing: .08em;
      color: var(--text, #f0f0f0);
      text-transform: uppercase;
    }
    .mh-admin-badge {
      font-size: 9px;
      font-weight: 700;
      background: rgba(232,67,147,.15);
      color: var(--accent, #e84393);
      border: 1px solid rgba(232,67,147,.3);
      border-radius: 3px;
      padding: 1px 5px;
      letter-spacing: .05em;
    }
    .mh-subsection {
      margin-bottom: 14px;
    }
    .mh-subsection-title {
      font-size: 10px;
      font-weight: 700;
      color: var(--text3, #888);
      letter-spacing: .06em;
      margin-bottom: 6px;
      display: flex;
      align-items: center;
      gap: 4px;
    }

    /* ── カード共通 ── */
    .mh-card {
      background: var(--bg3, #1e1e1e);
      border: 1px solid var(--border, #333);
      border-radius: var(--radius-sm, 6px);
      padding: 10px 12px;
      margin-bottom: 6px;
      cursor: pointer;
      transition: border-color .15s, background .15s;
    }
    .mh-card:hover {
      border-color: var(--accent, #e84393);
      background: rgba(232,67,147,.05);
    }
    .mh-card-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 4px;
    }
    .mh-card-row:last-child { margin-bottom: 0; }
    .mh-venue-race {
      font-size: 13px;
      font-weight: 700;
      color: var(--text, #f0f0f0);
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .mh-combo {
      font-family: var(--mono, monospace);
      font-size: 14px;
      font-weight: 700;
      color: var(--accent, #e84393);
      letter-spacing: .04em;
    }
    .mh-stat-row {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
    }
    .mh-stat {
      display: flex;
      align-items: center;
      gap: 3px;
    }
    .mh-stat-label {
      font-size: 9px;
      color: var(--text3, #888);
      font-weight: 600;
      letter-spacing: .04em;
    }
    .mh-stat-val {
      font-size: 11px;
      font-weight: 700;
      font-family: var(--mono, monospace);
      color: var(--text2, #ccc);
    }
    .mh-score-badge {
      font-size: 11px;
      font-weight: 800;
      font-family: var(--mono, monospace);
      padding: 2px 7px;
      border-radius: 4px;
    }
    .mh-score-hot   { background: rgba(232,67,147,.18); color: #ff6bac; border: 1px solid rgba(232,67,147,.35); }
    .mh-score-warm  { background: rgba(255,160,60,.18);  color: #ffb347; border: 1px solid rgba(255,160,60,.35); }
    .mh-score-cold  { background: rgba(100,150,255,.12); color: #88aaff; border: 1px solid rgba(100,150,255,.25); }

    /* ── エンプティステート ── */
    .mh-empty {
      text-align: center;
      color: var(--text3, #888);
      font-size: 11px;
      padding: 16px 0;
    }

    /* ── 高配当履歴テーブル ── */
    .mh-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 10px;
    }
    .mh-table th {
      color: var(--text3, #888);
      font-weight: 700;
      letter-spacing: .05em;
      text-align: left;
      padding: 3px 4px;
      border-bottom: 1px solid var(--border, #333);
    }
    .mh-table td {
      padding: 4px 4px;
      border-bottom: 1px solid rgba(255,255,255,.04);
      font-family: var(--mono, monospace);
      color: var(--text2, #ccc);
    }
    .mh-table tr:hover td { background: rgba(255,255,255,.03); }
    .mh-manshu-val { color: #ff6bac; font-weight: 800; }
    .mh-high-val   { color: #ffb347; font-weight: 700; }

    /* ── バックテストサマリー ── */
    .mh-bt-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 6px;
    }
    .mh-bt-cell {
      background: var(--bg3, #1e1e1e);
      border: 1px solid var(--border, #333);
      border-radius: var(--radius-sm, 6px);
      padding: 8px 10px;
      text-align: center;
    }
    .mh-bt-label { font-size: 9px; color: var(--text3, #888); font-weight: 600; letter-spacing: .04em; }
    .mh-bt-val   { font-size: 16px; font-weight: 800; font-family: var(--mono, monospace); margin-top: 2px; }
    .mh-green    { color: var(--green, #4caf50); }
    .mh-orange   { color: var(--orange, #ff9800); }
    .mh-red      { color: #f44336; }

    /* ── 混戦スコアバー ── */
    .mh-entropy-bar-wrap {
      height: 4px;
      background: var(--bg2, #2a2a2a);
      border-radius: 2px;
      overflow: hidden;
      margin-top: 2px;
    }
    .mh-entropy-bar {
      height: 100%;
      border-radius: 2px;
      transition: width .3s;
    }

    /* ── ローディング ── */
    .mh-loading {
      text-align: center;
      color: var(--text3, #888);
      font-size: 11px;
      padding: 12px 0;
      animation: mh-pulse 1.2s ease-in-out infinite;
    }
    @keyframes mh-pulse { 0%,100%{opacity:.4} 50%{opacity:1} }

    /* ── 折りたたみ ── */
    .mh-toggle-btn {
      background: none;
      border: 1px solid var(--border, #333);
      color: var(--text3, #888);
      font-size: 10px;
      font-weight: 700;
      padding: 3px 8px;
      border-radius: 4px;
      cursor: pointer;
      letter-spacing: .04em;
      margin-left: auto;
      display: block;
      margin-top: 6px;
    }
    .mh-toggle-btn:hover { border-color: var(--accent, #e84393); color: var(--accent, #e84393); }
  `;

  // ══════════════════════════════════════════════════════════════════════════
  // § ユーティリティ
  // ══════════════════════════════════════════════════════════════════════════

  function _isAdmin() {
    return document.body.classList.contains('admin-mode');
  }

  // final_prob を持つ ranked 配列から Shannon エントロピーを計算
  // エントロピー低 = 大本命集中, 高 = 混戦
  function _shannonEntropy(ranked) {
    if (!ranked || ranked.length === 0) return 0;
    const total = ranked.reduce((s, b) => s + (b.final_prob ?? b.prob ?? 0), 0);
    if (total <= 0) return 0;
    return -ranked.reduce((s, b) => {
      const p = (b.final_prob ?? b.prob ?? 0) / total;
      return s + (p > 0 ? p * Math.log2(p) : 0);
    }, 0);
  }

  // 3連単コンボ文字列 "w-s-t" のオッズを ODDS_DATA から取得
  function _getComboOdds(date, venue, rno, combo) {
    const normalize = c => (c || '').replace(/[－−\-]/g, '-');
    const raw = (typeof ODDS_DATA !== 'undefined')
      ? (ODDS_DATA?.[date]?.[venue]?.[String(rno)]?.['3t'] ?? {})
      : {};
    return raw[normalize(combo)] ?? null;
  }

  // combo "w-s-t" の AI結合確率を calcScenarioComboProb 経由で取得
  function _getComboAIProb(combo, winnerBoat, sd) {
    if (typeof calcScenarioComboProb !== 'function' || !sd) return null;
    try {
      return calcScenarioComboProb(combo, winnerBoat, sd);
    } catch (e) { return null; }
  }

  // 乖離スコア = AI確率 / (1/odds) = AI確率 × odds
  function _divergenceScore(aiProb, odds) {
    if (aiProb == null || odds == null || odds <= 0) return null;
    const marketProb = 1 / odds;
    if (marketProb <= 0) return null;
    return aiProb / marketProb; // > 1 = AIが市場より高く評価
  }

  // 日付文字列 YYYYMMDD or YYYY-MM-DD を YYYY-MM-DD に正規化
  function _normDate(raw) {
    const s = raw || '';
    if (s.length === 8 && !s.includes('-'))
      return `${s.slice(0,4)}-${s.slice(4,6)}-${s.slice(6,8)}`;
    return s;
  }

  // getDataForDate のラッパー（存在チェック付き）
  function _getDataForDate(dateStr) {
    if (typeof getDataForDate === 'function') return getDataForDate(dateStr);
    return {};
  }

  // VENUE_LIST が定義されていれば使う
  function _venueList() {
    return (typeof VENUE_LIST !== 'undefined') ? VENUE_LIST : [];
  }

  // 利用可能日付リスト
  function _availableDates() {
    return (typeof getAvailableDates === 'function') ? getAvailableDates() : [];
  }

  // ボートバッジHTML（既存スタイル互換）
  function _boatBadge(n) {
    return `<span class="boat-circle b${n}" style="width:17px;height:17px;font-size:10px;display:inline-flex;align-items:center;justify-content:center;flex-shrink:0;vertical-align:middle">${n}</span>`;
  }

  // 会場・レースへジャンプ（既存 jumpToPickup 相当）
  function _jumpToRace(venue, rno) {
    const dataFD = _getDataForDate(null);
    if (!dataFD[venue]) return;
    if (typeof hideTopPage === 'function') hideTopPage();
    if (typeof currentVenue !== 'undefined') window.currentVenue = venue;
    if (typeof DATA !== 'undefined') window.DATA = dataFD[venue];
    if (typeof buildVenueTabs === 'function') buildVenueTabs();
    if (typeof buildRaceBar === 'function') buildRaceBar();
    if (typeof updateDateNav === 'function') updateDateNav();
    if (typeof selectedRace !== 'undefined') window.selectedRace = rno;
    document.querySelectorAll('.race-btn').forEach(c => c.classList.remove('active'));
    const btn = document.getElementById(`rc-${rno}`);
    if (btn) { btn.classList.add('active'); btn.scrollIntoView({ behavior: 'auto', block: 'nearest', inline: 'center' }); }
    if (typeof updateHeaderMeta === 'function') updateHeaderMeta(venue, rno);
    if (typeof switchTab === 'function') switchTab('detail2');
    if (typeof renderBuy === 'function') renderBuy(rno);
  }

  // ══════════════════════════════════════════════════════════════════════════
  // § 1  マーケット乖離スキャン（当日・リアルタイム）
  //      全レース × 全コンボの AI確率 / 市場確率 を算出し上位を返す
  // ══════════════════════════════════════════════════════════════════════════

  /**
   * 当日の全レースで乖離スコア上位コンボを収集する。
   * @returns {Array} [{venue, rno, time, combo, aiProb, odds, diverge, entropy}]
   */
  function scanDivergence() {
    const results = [];
    const dataFD = _getDataForDate(null);

    _venueList().forEach(venue => {
      const vdata = dataFD[venue];
      if (!vdata || !vdata.races) return;
      const date = vdata.date || '';

      Object.entries(vdata.races).sort((a, b) => +a[0] - +b[0]).forEach(([rnoStr, rd]) => {
        if (!rd || !rd.boats || rd.boats.length < 2) return;
        if (rd.boats.some(b => b.dq === 'insufficient')) return;

        const rno = parseInt(rnoStr);
        const boats = [...rd.boats].sort((a, b) => a.boat - b.boat);

        // final_prob 計算（calcTenkaiProbs_pickup 経由で現在のシステムと同一ロジック）
        let ranked = null;
        let sd = null;
        try {
          const arek = rd.arek ?? 54.7;

          // DATA / currentVenue を一時差し替えて calcTenkaiProbs を呼ぶ
          const _savedData  = (typeof DATA !== 'undefined') ? DATA : null;
          const _savedVenue = (typeof currentVenue !== 'undefined') ? currentVenue : null;
          if (typeof DATA !== 'undefined') window.DATA = Object.assign({}, vdata, { venue });
          if (typeof currentVenue !== 'undefined') window.currentVenue = venue;

          try {
            ranked = (typeof calcTenkaiProbs === 'function')
              ? calcTenkaiProbs(boats, arek)
              : boats.map(b => ({ ...b, prob: b.prob ?? 1/6 }));

            // final_prob の簡易計算（展示スコアなし版）
            const probTotal = ranked.reduce((s, b) => s + (b.prob ?? 0), 0) || 1;
            ranked.forEach(b => { b.final_prob = (b.prob ?? 0) / probTotal; });

            // calcScenarioData が使えれば詳細2着/3着確率も取得
            if (typeof calcScenarioData === 'function') {
              const sortedByFinal = [...ranked].sort((a, b) => (b.final_prob ?? 0) - (a.final_prob ?? 0));
              sd = calcScenarioData(sortedByFinal, boats, null);
            }
          } finally {
            if (_savedData  !== null && typeof DATA !== 'undefined')  window.DATA  = _savedData;
            if (_savedVenue !== null && typeof currentVenue !== 'undefined') window.currentVenue = _savedVenue;
          }
        } catch (e) { return; }

        if (!ranked) return;

        const entropy = _shannonEntropy(ranked);
        const raceOdds = (typeof ODDS_DATA !== 'undefined')
          ? (ODDS_DATA?.[date]?.[venue]?.[String(rno)]?.['3t'] ?? {})
          : {};

        // 上位3艇の全順列コンボを評価
        const topBoats = [...ranked].sort((a, b) => (b.final_prob ?? 0) - (a.final_prob ?? 0)).slice(0, 5);
        const comboCandidates = [];
        topBoats.forEach(w => {
          topBoats.forEach(s => {
            if (s.boat === w.boat) return;
            topBoats.forEach(t => {
              if (t.boat === w.boat || t.boat === s.boat) return;
              comboCandidates.push(`${w.boat}-${s.boat}-${t.boat}`);
            });
          });
        });

        comboCandidates.forEach(combo => {
          const [wStr] = combo.split('-');
          const winnerBoat = parseInt(wStr);
          const odds = raceOdds[combo] ?? null;
          if (odds == null || odds < 10) return; // 10倍未満は除外（万舟ターゲット外）

          const aiProb = (sd && typeof calcScenarioComboProb === 'function')
            ? _getComboAIProb(combo, winnerBoat, sd)
            : (ranked.find(b => b.boat === winnerBoat)?.final_prob ?? null);

          const diverge = _divergenceScore(aiProb, odds);
          if (diverge == null || diverge < DIVERGE_THRESH) return;

          results.push({ venue, rno, time: rd.time || '', combo, aiProb, odds, diverge, entropy });
        });
      });
    });

    // 乖離スコア降順
    results.sort((a, b) => b.diverge - a.diverge);
    return results.slice(0, 20); // 上位20件
  }

  // ══════════════════════════════════════════════════════════════════════════
  // § 2  万舟発生条件スキャナー（当日・混戦スコア）
  //      エントロピー高 + オッズ分布偏り + 人気外艇の補正確率を総合評価
  // ══════════════════════════════════════════════════════════════════════════

  /**
   * 当日の全レースを混戦スコアでスコアリング
   * @returns {Array} [{venue, rno, time, entropy, topProb, outerAIProb, score, ...}]
   */
  function scanManshuCandidates() {
    const results = [];
    const dataFD = _getDataForDate(null);

    _venueList().forEach(venue => {
      const vdata = dataFD[venue];
      if (!vdata || !vdata.races) return;
      const date = vdata.date || '';

      Object.entries(vdata.races).sort((a, b) => +a[0] - +b[0]).forEach(([rnoStr, rd]) => {
        if (!rd || !rd.boats || rd.boats.length < 2) return;
        if (rd.boats.some(b => b.dq === 'insufficient')) return;
        if (typeof isRacePast === 'function' && isRacePast(rd.time)) return;

        const rno = parseInt(rnoStr);

        let ranked = null;
        try {
          const arek = rd.arek ?? 54.7;
          const boats = [...rd.boats].sort((a, b) => a.boat - b.boat);

          const _savedData  = (typeof DATA !== 'undefined') ? DATA : null;
          const _savedVenue = (typeof currentVenue !== 'undefined') ? currentVenue : null;
          if (typeof DATA !== 'undefined') window.DATA = Object.assign({}, vdata, { venue });
          if (typeof currentVenue !== 'undefined') window.currentVenue = venue;
          try {
            ranked = (typeof calcTenkaiProbs === 'function')
              ? calcTenkaiProbs(boats, arek)
              : boats.map(b => ({ ...b, prob: 1/6 }));
            const probTotal = ranked.reduce((s, b) => s + (b.prob ?? 0), 0) || 1;
            ranked.forEach(b => { b.final_prob = (b.prob ?? 0) / probTotal; });
          } finally {
            if (_savedData  !== null && typeof DATA !== 'undefined')  window.DATA  = _savedData;
            if (_savedVenue !== null && typeof currentVenue !== 'undefined') window.currentVenue = _savedVenue;
          }
        } catch (e) { return; }

        if (!ranked) return;

        const sortedByFP = [...ranked].sort((a, b) => (b.final_prob ?? 0) - (a.final_prob ?? 0));
        const entropy   = _shannonEntropy(ranked);
        const topProb   = sortedByFP[0]?.final_prob ?? 0;
        const boat1FP   = ranked.find(b => b.boat === 1)?.final_prob ?? 0;

        // 2〜6号艇の最大 AI 確率（イン以外が勝てる確率の指標）
        const outerMax = Math.max(
          ...ranked.filter(b => b.boat !== 1).map(b => b.final_prob ?? 0)
        );

        // 万舟スコア = エントロピー × (1-1号艇確率) × (外艇最大確率の補正)
        // エントロピーが高く、1号艇が弱く、外艇に勝ち目があるほど高スコア
        const score = entropy * (1 - boat1FP) * (1 + outerMax * 2);

        // スコアが一定以上のレースのみ
        if (score < 0.5) return;

        // 最有力外艇（1号艇以外でfinal_prob最大）
        const outerAxis = sortedByFP.find(b => b.boat !== 1);

        results.push({
          venue, rno,
          time: rd.time || '',
          entropy,
          topProb,
          boat1FP,
          outerBoat: outerAxis?.boat ?? null,
          outerAIProb: outerAxis?.final_prob ?? null,
          score,
          ranked: sortedByFP.slice(0, 4).map(b => ({ boat: b.boat, fp: b.final_prob ?? 0 })),
        });
      });
    });

    results.sort((a, b) => b.score - a.score);
    return results.slice(0, 15);
  }

  // ══════════════════════════════════════════════════════════════════════════
  // § 3  高配当履歴アナライザー（過去30日の万舟・高配当を抽出）
  // ══════════════════════════════════════════════════════════════════════════

  /**
   * 過去30日の全結果から万舟・高配当を抽出
   * @returns {Array} [{date, venue, rno, hitOdds, result, strategy}]
   */
  function collectHighDividends() {
    const allRecords = [];
    const dates = _availableDates();
    const today  = dates[dates.length - 1];

    // _lastStatsHit〜_lastStatsInNeg が top_page.js で定義されている場合に参照
    const strategies = [
      { key: '_lastStatsHit',     label: '的中重視' },
      { key: '_lastStatsRec',     label: '回収重視' },
      { key: '_lastStatsScen',    label: 'シナリオ(2.0+)' },
      { key: '_lastStatsScenAll', label: 'シナリオ(全)' },
      { key: '_lastStatsInTep',   label: 'イン鉄板' },
      { key: '_lastStatsInNeg',   label: 'イン否定' },
    ];

    strategies.forEach(({ key, label }) => {
      const arr = (typeof window !== 'undefined' && window[key]) ? window[key] : [];
      arr.forEach(r => {
        if (!r.isHit || !r.hitOdds) return;
        if (r.hitOdds < HIGH_DIV_THRESH) return;
        allRecords.push({
          date:     _normDate(r.date),
          venue:    r.venue,
          rno:      r.rno,
          hitOdds:  r.hitOdds,
          result:   r.actualResult || '',
          strategy: label,
          isManshu: r.hitOdds >= MANSHU_THRESH,
        });
      });
    });

    // 重複除去（同日・同会場・同レース）→ 最高配当を残す
    const seen = {};
    allRecords.forEach(r => {
      const k = `${r.date}_${r.venue}_${r.rno}`;
      if (!seen[k] || r.hitOdds > seen[k].hitOdds) seen[k] = r;
    });

    const deduped = Object.values(seen);
    deduped.sort((a, b) => b.hitOdds - a.hitOdds);
    return deduped.slice(0, 50);
  }

  // ══════════════════════════════════════════════════════════════════════════
  // § 4  マーケット乖離バックテスト（過去30日）
  //      collectResultsForDateScen が返す synth / hitRate / isHit / hitOdds を利用
  //      ＋ 乖離スコアが高い組み合わせが実際に勝ったかを評価
  // ══════════════════════════════════════════════════════════════════════════

  /**
   * 過去30日の結果を乖離スコア戦略でフィルターして集計
   * （ODDS_DATA が過去日に存在しないため synthOdds × hitRate を代用）
   */
  function calcDivergenceBacktest() {
    const dates = _availableDates();
    // 今日を除いた直近30日
    const pastDates = dates.slice(0, -1).slice(-30);

    let totalRaces = 0, hitCount = 0, totalBet = 0, totalReturn = 0;
    const manshuHits = [];

    pastDates.forEach(dateStr => {
      if (typeof collectResultsForDateScen !== 'function') return;
      let results;
      try { results = collectResultsForDateScen(dateStr, true); } catch (e) { return; }

      // ev >= 乖離相当（EV 1.5以上を "乖離エッジあり" の代理指標として使用）
      const candidates = (results || []).filter(r => r.ev != null && r.ev >= 1.5);

      candidates.forEach(r => {
        totalRaces++;
        const bet = (r.buy3cnt || 1) * 100;
        totalBet += bet;
        if (r.isHit && r.hitOdds) {
          hitCount++;
          totalReturn += r.hitOdds;
          if (r.hitOdds >= MANSHU_THRESH) {
            manshuHits.push({
              date:    _normDate(r.date),
              venue:   r.venue,
              rno:     r.rno,
              hitOdds: r.hitOdds,
              ev:      r.ev,
              synth:   r.synth,
            });
          }
        }
      });
    });

    const recoveryRate = totalBet > 0 ? totalReturn / totalBet : 0;
    const hitRate      = totalRaces > 0 ? hitCount / totalRaces : 0;

    manshuHits.sort((a, b) => b.hitOdds - a.hitOdds);
    return { totalRaces, hitCount, hitRate, totalBet, totalReturn, recoveryRate, manshuHits };
  }

  // ══════════════════════════════════════════════════════════════════════════
  // § UI レンダリング
  // ══════════════════════════════════════════════════════════════════════════

  function _renderDivergenceSection(items) {
    if (!items || items.length === 0) {
      return `<div class="mh-empty">現在オッズ取得中 or 乖離スコア閾値(${DIVERGE_THRESH}x)以上の買い目なし</div>`;
    }
    return items.map(item => {
      const d = item.diverge;
      const badgeCls = d >= 3.0 ? 'mh-score-hot' : d >= 2.2 ? 'mh-score-warm' : 'mh-score-cold';
      const parts = item.combo.split('-').map(Number);
      const comboHtml = parts.map(_boatBadge).join(
        `<span style="color:var(--text3);font-size:11px;margin:0 1px">-</span>`
      );
      const aiPct = item.aiProb != null ? (item.aiProb * 100).toFixed(1) + '%' : '—';
      const mktPct = item.odds != null ? (100 / item.odds).toFixed(1) + '%' : '—';
      const entropyPct = Math.min(100, (item.entropy / 3) * 100).toFixed(0);
      const eColor = item.entropy >= ENTROPY_HIGH_THRESH ? '#ff6bac'
                   : item.entropy >= ENTROPY_LOW_THRESH  ? '#ffb347'
                   : '#88aaff';
      return `
        <div class="mh-card" onclick="_mhJumpRace('${item.venue}',${item.rno})">
          <div class="mh-card-row">
            <span class="mh-venue-race">
              <span style="font-weight:800">${item.venue}</span>
              <span style="color:var(--text3);font-size:11px">${item.rno}R</span>
              <span style="color:var(--text3);font-size:10px">${item.time}</span>
            </span>
            <span class="mh-score-badge ${badgeCls}">乖離 ${d.toFixed(2)}x</span>
          </div>
          <div class="mh-card-row" style="margin-bottom:6px">
            <span class="mh-combo">${comboHtml}</span>
            <span style="font-family:var(--mono);font-size:13px;font-weight:700;color:var(--text2)">${item.odds != null ? item.odds.toFixed(1) + '倍' : '—'}</span>
          </div>
          <div class="mh-stat-row">
            <div class="mh-stat"><span class="mh-stat-label">AI確率</span><span class="mh-stat-val">${aiPct}</span></div>
            <div class="mh-stat"><span class="mh-stat-label">市場確率</span><span class="mh-stat-val">${mktPct}</span></div>
            <div class="mh-stat">
              <span class="mh-stat-label">混戦度</span>
              <span class="mh-stat-val" style="color:${eColor}">${item.entropy.toFixed(2)}</span>
            </div>
          </div>
        </div>`;
    }).join('');
  }

  function _renderScannerSection(items) {
    if (!items || items.length === 0) {
      return `<div class="mh-empty">発走前レースがないか、スコア閾値以上のレースなし</div>`;
    }
    return items.map(item => {
      const scoreCls = item.score >= 1.5 ? 'mh-score-hot' : item.score >= 0.9 ? 'mh-score-warm' : 'mh-score-cold';
      const entropyPct = Math.min(100, (item.entropy / 2.6) * 100);
      const eColor = item.entropy >= ENTROPY_HIGH_THRESH ? '#ff6bac'
                   : item.entropy >= ENTROPY_LOW_THRESH  ? '#ffb347'
                   : '#88aaff';
      const outerBadge = item.outerBoat != null
        ? `${_boatBadge(item.outerBoat)}<span style="font-size:10px;color:var(--text3);margin-left:3px">${item.outerAIProb != null ? (item.outerAIProb*100).toFixed(1)+'%' : ''}</span>`
        : '—';

      return `
        <div class="mh-card" onclick="_mhJumpRace('${item.venue}',${item.rno})">
          <div class="mh-card-row">
            <span class="mh-venue-race">
              <span style="font-weight:800">${item.venue}</span>
              <span style="color:var(--text3);font-size:11px">${item.rno}R</span>
              <span style="color:var(--text3);font-size:10px">${item.time}</span>
            </span>
            <span class="mh-score-badge ${scoreCls}">万舟スコア ${item.score.toFixed(2)}</span>
          </div>
          <div class="mh-stat-row" style="margin-bottom:4px">
            <div class="mh-stat"><span class="mh-stat-label">1号艇AI確率</span><span class="mh-stat-val" style="color:#88aaff">${(item.boat1FP*100).toFixed(1)}%</span></div>
            <div class="mh-stat"><span class="mh-stat-label">最有力外艇</span><span class="mh-stat-val">${outerBadge}</span></div>
          </div>
          <div class="mh-stat-row">
            <div class="mh-stat" style="flex-direction:column;align-items:flex-start;gap:2px;width:100%">
              <span class="mh-stat-label" style="color:${eColor}">混戦エントロピー ${item.entropy.toFixed(2)}</span>
              <div class="mh-entropy-bar-wrap" style="width:100%">
                <div class="mh-entropy-bar" style="width:${entropyPct.toFixed(0)}%;background:${eColor}"></div>
              </div>
            </div>
          </div>
        </div>`;
    }).join('');
  }

  function _renderHighDivTable(records) {
    if (!records || records.length === 0) {
      return `<div class="mh-empty">高配当記録なし（${HIGH_DIV_THRESH / 100}倍以上を対象）</div>`;
    }
    const rows = records.slice(0, 20).map(r => {
      const valCls = r.isManshu ? 'mh-manshu-val' : 'mh-high-val';
      return `<tr>
        <td>${r.date.slice(5)}</td>
        <td>${r.venue}</td>
        <td style="text-align:center">${r.rno}R</td>
        <td class="${valCls}" style="text-align:right">${(r.hitOdds / 100).toFixed(1)}倍</td>
        <td style="color:var(--text3)">${r.result}</td>
        <td style="color:var(--text3)">${r.strategy}</td>
      </tr>`;
    }).join('');
    return `
      <table class="mh-table">
        <thead>
          <tr><th>日付</th><th>会場</th><th>R</th><th style="text-align:right">配当</th><th>着順</th><th>戦略</th></tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>`;
  }

  function _renderBacktestSection(bt) {
    const recColor = bt.recoveryRate >= 1.0 ? 'mh-green' : bt.recoveryRate >= 0.7 ? 'mh-orange' : 'mh-red';
    const hitColor = bt.hitRate >= 0.5 ? 'mh-green' : bt.hitRate >= 0.3 ? 'mh-orange' : 'mh-red';
    const manshuRows = bt.manshuHits.slice(0, 5).map(r => `
      <div class="mh-stat-row" style="margin-top:4px">
        <span style="font-size:10px;color:var(--text3)">${r.date.slice(5)} ${r.venue} ${r.rno}R</span>
        <span style="font-family:var(--mono);font-size:11px;font-weight:700;color:#ff6bac;margin-left:auto">¥${r.hitOdds.toLocaleString()}</span>
      </div>`).join('');

    return `
      <div class="mh-bt-grid">
        <div class="mh-bt-cell">
          <div class="mh-bt-label">的中率</div>
          <div class="mh-bt-val ${hitColor}">${(bt.hitRate * 100).toFixed(0)}%</div>
          <div style="font-size:9px;color:var(--text3);margin-top:2px">${bt.hitCount}/${bt.totalRaces}R</div>
        </div>
        <div class="mh-bt-cell">
          <div class="mh-bt-label">回収率</div>
          <div class="mh-bt-val ${recColor}">${(bt.recoveryRate * 100).toFixed(0)}%</div>
        </div>
        <div class="mh-bt-cell">
          <div class="mh-bt-label">総投資</div>
          <div class="mh-bt-val" style="font-size:13px;color:var(--text2)">${bt.totalBet.toLocaleString()}円</div>
        </div>
        <div class="mh-bt-cell">
          <div class="mh-bt-label">総回収</div>
          <div class="mh-bt-val ${recColor}" style="font-size:13px">${bt.totalReturn.toLocaleString()}円</div>
        </div>
      </div>
      ${bt.manshuHits.length > 0 ? `
        <div style="margin-top:10px">
          <div class="mh-subsection-title">🎯 万舟的中履歴（過去30日）</div>
          ${manshuRows}
        </div>` : `<div class="mh-empty" style="margin-top:8px">過去30日の万舟的中なし</div>`}
      <div style="font-size:9px;color:var(--text3);margin-top:8px;text-align:center">
        ※ EV≥1.5のシナリオ買いを乖離エッジの代理指標として使用（ODDS_DATA未取得の過去日対応）
      </div>`;
  }

  // ══════════════════════════════════════════════════════════════════════════
  // § DOM 注入・メインレンダラー
  // ══════════════════════════════════════════════════════════════════════════

  function _injectStyles() {
    if (document.getElementById('mh-style')) return;
    const el = document.createElement('style');
    el.id = 'mh-style';
    el.textContent = STYLE;
    document.head.appendChild(el);
  }

  function _getOrCreateRoot() {
    let root = document.getElementById(MODULE_ID);
    if (!root) {
      const topPage = document.getElementById('top-page');
      if (!topPage) return null;
      root = document.createElement('div');
      root.id = MODULE_ID;
      topPage.appendChild(root);
    }
    return root;
  }

  function render() {
    if (!_isAdmin()) return; // 管理者以外は何もしない

    _injectStyles();
    const root = _getOrCreateRoot();
    if (!root) return;

    // ローディング状態を先に表示
    root.innerHTML = `
      <div class="mh-section-header">
        <span class="mh-section-title">🎯 万舟ハンター</span>
        <span class="mh-admin-badge">ADMIN ONLY</span>
      </div>
      <div class="mh-loading">スキャン中...</div>
    `;

    // 非同期で計算（UIをブロックしない）
    setTimeout(() => {
      try {
        const divergeItems  = scanDivergence();
        const scanItems     = scanManshuCandidates();
        const highDivs      = collectHighDividends();
        const bt            = calcDivergenceBacktest();
        const manshuCount   = highDivs.filter(r => r.isManshu).length;

        root.innerHTML = `
          <div class="mh-section-header">
            <span class="mh-section-title">🎯 万舟ハンター</span>
            <span class="mh-admin-badge">ADMIN ONLY</span>
          </div>

          <!-- § 1 マーケット乖離スキャン -->
          <div class="mh-subsection">
            <div class="mh-subsection-title">
              ⚡ マーケット乖離スキャン
              <span style="font-weight:400;color:var(--text3)">（AI確率 vs オッズ乖離 ≥ ${DIVERGE_THRESH}x）</span>
            </div>
            ${_renderDivergenceSection(divergeItems)}
          </div>

          <!-- § 2 万舟発生スキャナー -->
          <div class="mh-subsection">
            <div class="mh-subsection-title">
              🌊 万舟発生条件スキャナー
              <span style="font-weight:400;color:var(--text3)">（混戦エントロピー × 外艇強度）</span>
            </div>
            ${_renderScannerSection(scanItems)}
          </div>

          <!-- § 3 高配当履歴 -->
          <div class="mh-subsection">
            <div class="mh-subsection-title">
              💰 高配当的中履歴
              <span style="font-weight:400;color:var(--text3)">（${HIGH_DIV_THRESH/100}倍以上 ／ 万舟${manshuCount}件）</span>
            </div>
            <details>
              <summary style="font-size:10px;font-weight:700;color:var(--text3);cursor:pointer;list-style:none;display:flex;align-items:center;gap:4px;padding:4px 0">
                <span style="font-size:9px">▶</span> 一覧を表示（${highDivs.length}件）
              </summary>
              <div style="margin-top:6px">${_renderHighDivTable(highDivs)}</div>
            </details>
          </div>

          <!-- § 4 乖離戦略バックテスト -->
          <div class="mh-subsection">
            <div class="mh-subsection-title">
              📊 乖離戦略バックテスト
              <span style="font-weight:400;color:var(--text3)">（過去30日 EV≥1.5）</span>
            </div>
            ${_renderBacktestSection(bt)}
          </div>
        `;
      } catch (e) {
        console.error('[manshu_hunter] render error:', e);
        root.innerHTML = `<div class="mh-empty">⚠ 計算エラー: ${e.message}</div>`;
      }
    }, 50);
  }

  // ── グローバルから呼べるジャンプ関数（onclick から参照）──
  window._mhJumpRace = function (venue, rno) {
    try { _jumpToRace(venue, rno); } catch (e) { console.warn('[manshu_hunter] jump error:', e); }
  };

  // ══════════════════════════════════════════════════════════════════════════
  // § 既存 calcTopAIStats / showTopPage へのフック（非破壊パッチ）
  //   既存関数を上書きせず、完了後に render() を追加呼び出しするだけ。
  // ══════════════════════════════════════════════════════════════════════════

  function _patchWithGuard(fnName, afterFn) {
    const original = window[fnName];
    if (typeof original !== 'function') {
      // 定義されていなければポーリングで待つ（obfuscate後に定義される場合）
      let tries = 0;
      const poll = setInterval(() => {
        if (typeof window[fnName] === 'function') {
          clearInterval(poll);
          _patchWithGuard(fnName, afterFn);
        }
        if (++tries > 100) clearInterval(poll);
      }, 100);
      return;
    }
    window[fnName] = function (...args) {
      const result = original.apply(this, args);
      // Promise の場合は then で後処理
      if (result && typeof result.then === 'function') {
        result.then(() => { try { afterFn(); } catch (e) {} });
      } else {
        try { afterFn(); } catch (e) {}
      }
      return result;
    };
  }

  // calcTopAIStats 完了後に再描画（データ更新に追従）
  _patchWithGuard('calcTopAIStats', () => {
    if (_isAdmin()) render();
  });

  // showTopPage で初回表示時も描画
  _patchWithGuard('showTopPage', () => {
    if (_isAdmin()) {
      // showTopPage 内の requestAnimationFrame チェーンが完了するのを待つ
      setTimeout(() => { if (_isAdmin()) render(); }, 400);
    }
  });

  // ── admin-mode クラスの付与を MutationObserver で検知 ──────────
  // index.html の認証処理（SHA-256 async）が完了するタイミングは
  // DOMContentLoaded より後になるため、classの変化を直接監視する。
  function _watchAdminMode() {
    if (_isAdmin()) {
      setTimeout(render, 400);
      return;
    }
    const observer = new MutationObserver(() => {
      if (_isAdmin()) {
        observer.disconnect();
        setTimeout(render, 500);
      }
    });
    observer.observe(document.body, { attributes: true, attributeFilter: ['class'] });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _watchAdminMode);
  } else {
    _watchAdminMode();
  }

  // ── 公開API（デバッグ・外部連携用）──
  window.manshuHunter = {
    render,
    scanDivergence,
    scanManshuCandidates,
    collectHighDividends,
    calcDivergenceBacktest,
    /** 乖離スコア閾値を動的変更 */
    setDivergeThreshold: function (v) {
      if (typeof v === 'number' && v > 0) {
        // DIVERGE_THRESH はモジュールスコープ変数なので再定義
        console.log('[manshuHunter] setDivergeThreshold は closure変数のため直接変更できません。定数を更新して reload してください。');
      }
    },
  };

  console.log('[manshu_hunter.js] loaded. admin-mode:', _isAdmin());

})();
