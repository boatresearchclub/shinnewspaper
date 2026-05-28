// top_page.js — TOP PAGE UI（sample.js から分離）

// ── ピックアップレース CSVダウンロード ──────────────────────────────
// type: 'in_tetsup'（イン鉄板）| 'in_neg'（イン否定）| null（全件）
function exportPickupCSV(type) {
  if (!_lastPickups || _lastPickups.length === 0) {
    if (typeof showToast === 'function') showToast('ピックアップデータがありません');
    return;
  }

  // タイプでフィルタ
  const rows = type
    ? _lastPickups.filter(p => p.tags.some(t => t.type === type))
    : _lastPickups;

  if (rows.length === 0) {
    const label = type === 'in_tetsup' ? 'イン鉄板' : type === 'in_neg' ? 'イン否定' : '';
    if (typeof showToast === 'function') showToast(`${label}の対象レースがありません`);
    return;
  }

  const header = ['会場', 'レース', '発走時刻', 'タグ', '期待値', '合成オッズ', '想定的中率', '点数'];
  const body = rows.map(p => {
    const tagLabel = p.tags.map(t => t.label).join(' / ');
    const ev    = p.scenEV    != null ? p.scenEV.toFixed(3)    : '';
    const synth = p.scenSynth != null ? p.scenSynth.toFixed(2) : '';
    const hit   = p.scenHit   != null ? (p.scenHit * 100).toFixed(1) + '%' : '';
    const pts   = p.scenPts   != null ? String(p.scenPts) : '';
    return [p.venue, `${p.rno}R`, p.time, tagLabel, ev, synth, hit, pts];
  });

  const csv = [header, ...body]
    .map(r => r.map(v => `"${String(v).replace(/"/g, '""')}"`).join(','))
    .join('\r\n');

  // BOM付きUTF-8でExcelでも文字化けしない
  const bom  = '\uFEFF';
  const blob = new Blob([bom + csv], { type: 'text/csv;charset=utf-8;' });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  const typeLabel = type === 'in_tetsup' ? 'イン鉄板' : type === 'in_neg' ? 'イン否定' : 'ピックアップ全件';
  a.href     = url;
  a.download = `pickup_${typeLabel}_${new Date().toISOString().slice(0,10)}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
// ピックアップレース最終計算結果（jumpToPickup がタグ種別を参照するために保持）
let _lastPickups = [];

// ── 過去30日 全戦略 結果集計データ保持（_renderHistory30 から書き込む）─────
// top_stats.js の _renderHistory30 が計算完了後に各配列をここへ格納する
let _lastStatsHit     = [];  // 的中重視
let _lastStatsRec     = [];  // 回収重視
let _lastStatsScen    = [];  // シナリオ買い（合成2.0倍以上）
let _lastStatsScenAll = [];  // シナリオ買い（フィルターなし）
let _lastStatsInTep   = [];  // イン鉄板
let _lastStatsInNeg   = [];  // イン否定

// ── 共通: 日付正規化ヘルパー ──────────────────────────────────────────
function _normDate(raw) {
  const s = raw || '';
  if (s.length === 8 && !s.includes('-'))
    return `${s.slice(0,4)}-${s.slice(4,6)}-${s.slice(6,8)}`;
  return s;
}

// ── 共通: 曜日ヘルパー ────────────────────────────────────────────────
function _weekday(dateStr) {
  try {
    return ['日','月','火','水','木','金','土'][new Date(dateStr).getDay()];
  } catch(e) { return ''; }
}

// ── 共通: 合成オッズ帯ヘルパー ───────────────────────────────────────
function _synthBand(synth) {
  if (synth == null) return '';
  if (synth <  2.0) return '2.0未満';
  if (synth <  3.0) return '2.0-3.0';
  if (synth <  5.0) return '3.0-5.0';
  if (synth < 10.0) return '5.0-10.0';
  return '10.0以上';
}

// ── 共通: CSVダウンロード実行 ────────────────────────────────────────
function _downloadCSV(rows, filename) {
  const bom  = '\uFEFF';
  const csv  = rows.map(r => r.map(v => `"${String(v ?? '').replace(/"/g,'""')}"`).join(',')).join('\r\n');
  const blob = new Blob([bom + csv], { type: 'text/csv;charset=utf-8;' });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// ── イン鉄板 / イン否定 単体CSV（既存ボタン用）──────────────────────
// type: 'in_tetsup' | 'in_neg'
function exportStatsCSV(type) {
  const isInTep = type === 'in_tetsup';
  const label   = isInTep ? 'イン鉄板' : 'イン否定';
  const results = isInTep ? _lastStatsInTep : _lastStatsInNeg;

  if (!results || results.length === 0) {
    if (typeof showToast === 'function') showToast(`${label}の集計データがありません`);
    return;
  }

  const header = ['日付','曜日','会場','レース','点数','的中','着順','配当(円)','投資(円)','損益(円)'];
  const body = results.map(r => {
    const d   = _normDate(r.date);
    const bet = r.buy3cnt * 100;
    const ret = r.isHit ? (r.hitOdds || 0) : 0;
    return [d, _weekday(d), r.venue, `${r.rno}R`, r.buy3cnt,
            r.isHit ? '的中' : '', r.actualResult || '', r.isHit ? ret : '',
            bet, ret - bet];
  });

  _downloadCSV([header, ...body], `stats_${label}_${new Date().toISOString().slice(0,10)}.csv`);
}

// ── 改善分析CSV（全6戦略を1ファイルに統合）────────────────────────────
// 列: 日付 / 曜日 / 会場 / レース番号 / 戦略 / 点数 / 合成オッズ / 合成オッズ帯 /
//     期待値 / 想定的中率 / 的中 / 着順 / 配当(円) / 投資(円) / 損益(円)
// ピボット分析・フィルタリングで「どの会場・レース番号・オッズ帯が強いか」が判断できる
function exportAnalysisCSV() {
  const labeled = [
    ..._lastStatsHit.map(r     => ({ ...r, _strategy: '的中重視' })),
    ..._lastStatsRec.map(r     => ({ ...r, _strategy: '回収重視' })),
    ..._lastStatsScen.map(r    => ({ ...r, _strategy: 'シナリオ(合成2.0+)' })),
    ..._lastStatsScenAll.map(r => ({ ...r, _strategy: 'シナリオ(全)' })),
    ..._lastStatsInTep.map(r   => ({ ...r, _strategy: 'イン鉄板' })),
    ..._lastStatsInNeg.map(r   => ({ ...r, _strategy: 'イン否定' })),
  ];

  if (labeled.length === 0) {
    if (typeof showToast === 'function') showToast('集計データがありません。30日集計の読み込みをお待ちください。');
    return;
  }

  labeled.sort((a, b) => {
    const da = _normDate(a.date), db = _normDate(b.date);
    if (da !== db) return da < db ? -1 : 1;
    if (a.venue !== b.venue) return (a.venue || '').localeCompare(b.venue || '', 'ja');
    if (a.rno !== b.rno) return (a.rno || 0) - (b.rno || 0);
    return (a._strategy || '').localeCompare(b._strategy || '');
  });

  const header = [
    '日付', '曜日', '会場', 'レース番号', '戦略',
    '点数', '合成オッズ', '合成オッズ帯', '期待値', '想定的中率(%)',
    '的中', '着順', '配当(円)', '投資(円)', '損益(円)'
  ];

  const body = labeled.map(r => {
    const d       = _normDate(r.date);
    const synth   = r.synth   != null ? r.synth.toFixed(2)           : '';
    const ev      = r.ev      != null ? r.ev.toFixed(3)              : '';
    const hitRate = r.hitRate != null ? (r.hitRate * 100).toFixed(1) : '';
    const bet     = (r.buy3cnt || 0) * 100;
    const ret     = r.isHit ? (r.hitOdds || 0) : 0;
    return [
      d, _weekday(d), r.venue, r.rno, r._strategy,
      r.buy3cnt, synth, _synthBand(r.synth), ev, hitRate,
      r.isHit ? '的中' : '', r.actualResult || '', r.isHit ? ret : '',
      bet, ret - bet
    ];
  });

  _downloadCSV([header, ...body], `analysis_30days_${new Date().toISOString().slice(0,10)}.csv`);
}

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
  // sticky-nav は display:none にせず visibility+pointer-events+height で制御する。
  // display:none にするとPCでレイアウト再計算が乱れ、hideTopPage後も
  // クリックが効かなくなる問題が発生するため。
  document.querySelectorAll('.sticky-nav').forEach(_sn => {
    _sn.style.visibility = 'hidden'; _sn.style.pointerEvents = 'none';
    _sn.style.height = '0'; _sn.style.overflow = 'hidden';
  });
  document.getElementById('header-meta').textContent = '';
  const _rmb = document.getElementById('race-meta-bar');
  if (_rmb) _rmb.style.display = 'none';

  // 軽量なUIを先に描画してからheavyな処理を非同期実行
  // rAF でブラウザに1フレーム描画させてからコンテンツ構築する
  requestAnimationFrame(() => {
    buildTopVenueChips();
    updateTopAlertStrip();

    // ピックアップ（中程度の重さ）は次フレームで
    requestAnimationFrame(() => {
      buildTopPickupRaces();

      // calcTopAIStats は最重量のためアイドル時間に遅延実行
      // スマホ（iOS Safari含む）は requestIdleCallback が不安定なため
      // モバイル端末では setTimeout で確実に実行する
      const _isMobile = /iPhone|iPad|iPod|Android/i.test(navigator.userAgent);
      if (!_isMobile && typeof requestIdleCallback === 'function') {
        requestIdleCallback(() => calcTopAIStats(), { timeout: 2000 });
      } else {
        setTimeout(() => calcTopAIStats(), 300);
      }
    });
  });
}

function hideTopPage() {
  document.getElementById('top-page').style.display = 'none';
  document.querySelector('.container').style.display = '';
  // showTopPage で visibility/pointerEvents/height を変えたので元に戻す
  document.querySelectorAll('.sticky-nav').forEach(_sn => {
    _sn.style.visibility = ''; _sn.style.pointerEvents = '';
    _sn.style.height = ''; _sn.style.overflow = '';
  });
  // 出走表表示に切り替わったので右上の日付ナビを更新
  if (typeof updateDateNav === 'function') updateDateNav();
}

// ── ピックアップレース ──
// 以下の条件のいずれかに該当するレースを締め切り順・横スクロールカードで表示する。
//   A/B: 1号艇の基準1着率 or 最終確率が会場平均を下回る → イン逃げ否定
//   C/D: 1号艇の基準1着率 or 最終確率が70%以上          → イン逃げ鉄板
//   E:   まくりアラート（前艇比 平均ST順0.5以上早い＋展示タイム0.1秒以上早い）
// ※ 発走済みレースは除外、当日データのみ対象
function buildTopPickupRaces() {
  _ensureTenjiCache();
  const section  = document.getElementById('top-pickup-section');
  const cardsEl  = document.getElementById('top-pickup-cards');
  if (!section || !cardsEl) return;

  const dataForDate = getDataForDate(null); // 当日のみ
  const pickups = [];

  VENUE_LIST.forEach(venue => {
    const vdata = dataForDate[venue];
    if (!vdata || !vdata.races) return;

    const venueAvg1 = (vdata.inn_data || {}).course_rates?.[1] ?? null;
    const slug      = VENUE_SLUG_MAP[venue] || venue;
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
      // classifyRaceJS 用: ranked 1位艇の情報
      let _rankTop = null;
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
          // [2026-05-18 修正] TENJI_WEIGHT_BY_COURSE 廃止 → コース別感度は calcTenjiScore 内で処理済み
          const wTenjiC=wTenji;
          b._multi_score=Math.pow(baseNorm,wBase)*Math.pow(tenkaiCoef,wTenkai)*Math.pow(tenjiCoef,wTenjiC);
        });
        const multiTotal=ranked.reduce((s,b)=>s+b._multi_score,0)||1;
        ranked.forEach(b=>{ b.final_prob=b._multi_score/multiTotal; });
        finalProb1=ranked.find(b=>b.boat===1)?.final_prob??null;

        // classifyRaceJS 用: final_prob 最大の艇情報を保存
        const sortedByFinal = [...ranked].sort((a,b)=>(b.final_prob??0)-(a.final_prob??0));
        const topB = sortedByFinal[0];
        if (topB) {
          const probTotalForBase = ranked.reduce((s,b)=>s+b.prob,0)||1;
          _rankTop = {
            boat:    topB.boat,
            base:    topB.prob / probTotalForBase,
            tenkai:  topB.tenkai_score ?? topB.tenkai_prob ?? 1.0,
            arek:    arek,
          };
        }
      } catch(e) { finalProb1 = null; }

      // ── タグ構築 ──
      const tags = [];
      const avgStr = venueAvg1!=null ? `${(venueAvg1*100).toFixed(1)}%` : null;

      // イン逃げ否定（基準 or 最終が場平均を10%以上下回る）
      const belowBase  = base1!=null && venueAvg1!=null && base1 < venueAvg1 - 0.10;
      const belowFinal = finalProb1!=null && venueAvg1!=null && finalProb1 < venueAvg1 - 0.10;
      if (belowBase || belowFinal) {
        const subParts = [];
        if (belowBase)  subParts.push(`基準 ${(base1*100).toFixed(1)}%`);
        if (belowFinal) subParts.push(`最終 ${(finalProb1*100).toFixed(1)}%`);
        if (avgStr) subParts.push(`場平均 ${avgStr}`);
        tags.push({ type:'in_neg', label:'イン逃げ否定', sub: subParts.join(' ／ '), color:'var(--orange)' });
      }

      // イン逃げ鉄板（最終確率が80%以上）
      const strongFinal = finalProb1!=null && finalProb1>=0.80;
      if (strongFinal) {
        const subParts = [];
        subParts.push(`最終 ${(finalProb1*100).toFixed(1)}%`);
        tags.push({ type:'in_tetsup', label:'イン逃げ鉄板', sub: subParts.join(' ／ '), color:'var(--accent2)' });
      }

      // イン逃げ否定・イン逃げ鉄板のいずれかがなければスキップ
      const hasInNeg = tags.some(t => t.type === 'in_neg');
      const hasInTep = tags.some(t => t.type === 'in_tetsup');
      if (!hasInNeg && !hasInTep) return;

      // ── シナリオ買い EV 先行計算 ──
      // イン逃げ否定・イン逃げ鉄板タグに応じた軸調整後の合成オッズ × 想定的中率
      // renderBuy(→buildScenarioBuyPanel) を開かなくても EV をカードに表示するための先行計算。
      let scenEV    = null;  // 期待値（null = 計算不可 or オッズなし）
      let scenSynth = null;  // 合成オッズ
      let scenHit   = null;  // 想定的中率
      let scenPts   = 0;     // 点数
      try {
        // タグ種別を確定
        const tagTypes  = tags.map(t => t.type);
        const isInNeg   = tagTypes.includes('in_neg');
        const isInTep   = tagTypes.includes('in_tetsup');

        // ranked はこのスコープで計算済みの final_prob ソート済みリスト
        const sortedByFinal = [...ranked].sort((a,b) => (b.final_prob??0) - (a.final_prob??0));

        // calcScenarioData: DATA/currentVenue を一時差し替えて呼び出す
        // finally で確実に復元し、例外でグローバル状態が壊れないようにする
        const _pd2 = DATA, _pv2 = currentVenue;
        let sd2 = null;
        try {
          DATA = vdata; currentVenue = venue;
          sd2 = calcScenarioData(sortedByFinal, boats, tenjiScoreMap || null);
        } catch(e) {
          // calcScenarioData エラーはサイレントに無視（EV計算をスキップ）
        } finally {
          DATA = _pd2; currentVenue = _pv2;  // 必ず元に戻す
        }

        if (sd2 && sd2.valid) {
          // ── 軸・2着をタグに応じて決定 ──
          const inn2PlacePU = (() => {
            const v = (vdata.inn_data || {}).inn_2place;
            if (v && typeof v === 'object' && !Array.isArray(v) && Object.keys(v).length > 0) return v;
            return MASTER_EXT?.venue_stats?.[venue]?.inn_2place || {};
          })();

          // 2着確率合算ヘルパー（buildScenarioBuyPanel の getPlace2Ranking と同一ロジック）
          function _getP2Rank(winnerBoat) {
            if (!sd2.scenarioPlace2?.[winnerBoat]) return [];
            const totals = {};
            let ws = 0;
            for (const [k, list] of Object.entries(sd2.scenarioPlace2[winnerBoat])) {
              const sp = sd2.scenarioProb?.[winnerBoat]?.[k] ?? 0;
              ws += sp;
              (list||[]).forEach(x => { totals[x.boat] = (totals[x.boat]??0) + x.p2 * sp; });
            }
            if (ws <= 0) {
              return sortedByFinal.filter(r=>r.boat!==winnerBoat).map(r=>r.boat);
            }
            return Object.entries(totals).sort((a,b)=>b[1]-a[1]).map(([b])=>parseInt(b));
          }

          // 3着候補ヘルパー（merged3rdMap 参照）
          function _getP3Rank(w, s) {
            const th = sd2.merged3rdMap?.[w]?.[s] || [];
            if (th.length > 0) return th.filter(x=>x.boat!==w&&x.boat!==s).slice(0,3).map(x=>x.boat);
            return sortedByFinal.filter(r=>r.boat!==w&&r.boat!==s).slice(0,3).map(r=>r.boat);
          }

          // 折り返し含む組合せ生成
          function _makeBlock(w, s, thirds) {
            const ts = thirds.filter(t=>t!==w&&t!==s);
            return [...ts.map(t=>`${w}-${s}-${t}`), ...ts.map(t=>`${w}-${t}-${s}`)];
          }

          let allCombos = [];
          const seen = new Set();
          function _addCombos(combos) {
            combos.forEach(c => { if (!seen.has(c)) { seen.add(c); allCombos.push(c); } });
          }

          if (isInNeg) {
            // イン逃げ否定: 1号艇を除いた final_prob 最上位を軸に
            const outerAxis = sortedByFinal.find(b => b.boat !== 1);
            if (outerAxis) {
              const ax = outerAxis.boat;
              const p2r = _getP2Rank(ax);
              _addCombos(_makeBlock(ax, p2r[0], _getP3Rank(ax, p2r[0])));
              if (p2r[1] != null) _addCombos(_makeBlock(ax, p2r[1], _getP3Rank(ax, p2r[1])));
              // fp2nd（ax以外の上位）を2軸目として追加
              const ax2 = sortedByFinal.find(b => b.boat !== 1 && b.boat !== ax);
              if (ax2) {
                const p2r2 = _getP2Rank(ax2.boat);
                _addCombos(_makeBlock(ax2.boat, p2r2[0], _getP3Rank(ax2.boat, p2r2[0])));
              }
            }
          } else if (isInTep) {
            // イン逃げ鉄板: 1号艇固定 + 2着を inn_2place 上位2艇に絞り込み
            const ax = 1;
            // inn_2place を降順ソートして上位2艇を取得
            const innSorted = Object.entries(inn2PlacePU)
              .map(([k,v]) => ({ boat: parseInt(k), rate: v }))
              .filter(x => !isNaN(x.boat) && x.boat !== 1)
              .sort((a,b) => b.rate - a.rate);
            const s1 = innSorted[0]?.boat ?? _getP2Rank(ax)[0];
            const s2 = innSorted[1]?.boat ?? _getP2Rank(ax)[1];
            if (s1 != null) _addCombos(_makeBlock(ax, s1, _getP3Rank(ax, s1)));
            if (s2 != null) _addCombos(_makeBlock(ax, s2, _getP3Rank(ax, s2)));
          }

          scenPts = allCombos.length;

          if (scenPts > 0) {
            // オッズ参照（ODDS_DATA 構造: [date][venue][rno][3t][combo]）
            const _oddsDate = date; // "YYYY-MM-DD"
            const raceOdds3t = ODDS_DATA?.[_oddsDate]?.[venue]?.[String(rno)]?.['3t'] || {};
            const normalize  = c => (c||'').replace(/[－−\-]/g, '-');

            // 合成オッズ = 1 / Σ(1/odds_i)
            let synthDenom = 0, synthCnt = 0;
            let hitRateSum = 0;
            allCombos.forEach(c => {
              const nc = normalize(c);
              const ov = raceOdds3t[nc] ?? null;
              if (ov != null && ov > 0) { synthDenom += 1/ov; synthCnt++; }
              // 想定的中率
              const winner = parseInt(c.split('-')[0]);
              const p = calcScenarioComboProb(c, winner, sd2);
              if (p != null) hitRateSum += p;
            });
            scenSynth = (synthCnt > 0 && synthDenom > 0) ? 1 / synthDenom : null;
            scenHit   = hitRateSum > 0 ? hitRateSum : null;
            scenEV    = (scenSynth != null && scenHit != null) ? scenSynth * scenHit : null;
          }
        }
      } catch(e) { /* EV計算失敗はサイレントに無視 */ }

      // 締め切り時刻を分単位に変換（ソート用）
      let timeMin = 9999;
      if (rd.time && /^\d{1,2}:\d{2}$/.test(rd.time.trim())) {
        const [h,m] = rd.time.trim().split(':').map(Number);
        timeMin = h*60+m;
      }

      pickups.push({ venue, rno, time: rd.time||'', timeMin, tags, scenEV, scenSynth, scenHit, scenPts });
    });
  });

  // 締め切り順（同時刻は会場名順）
  pickups.sort((a,b) => a.timeMin!==b.timeMin ? a.timeMin-b.timeMin : a.venue.localeCompare(b.venue,'ja'));

  // jumpToPickup でタグ種別を参照できるように保存
  _lastPickups = pickups;

  if (pickups.length === 0) {
    section.style.display = 'none';
    return;
  }

  section.style.display = 'block';

  cardsEl.innerHTML = pickups.map(p => {
    const t = p.tags[0];
    const badgeHtml = `<div class="alert-card-badge" style="background:${t.color}22;color:${t.color};border:1px solid ${t.color}55;border-radius:4px;padding:2px 6px;font-size:10px;font-weight:700;letter-spacing:.03em;white-space:nowrap;line-height:1.4;text-align:center">${t.label}</div>`;
    return `<div class="alert-card" onclick="jumpToPickup('${p.venue}',${p.rno})">
      ${badgeHtml}
      <div class="alert-card-venue">${p.venue}</div>
      <div class="alert-card-race">${p.rno}R</div>
      <div class="alert-card-time">${p.time} 発走</div>
    </div>`;
  }).join('');
}

// calcTenkaiProbs の pickup 専用ラッパー（DATA/currentVenue を一時差し替え）
function calcTenkaiProbs_pickup(boats, arek, venue, vdata) {
  const _prevData = DATA; const _prevVenue = currentVenue;
  DATA = vdata; currentVenue = venue;
  let result;
  try {
    result = calcTenkaiProbs(boats, arek);
  } catch(e) {
    result = [...boats].map(b=>({...b,tenkai_prob:b.prob,tenkai_score:b.prob}));
  } finally {
    // 例外が発生してもグローバル状態を必ず復元する
    DATA = _prevData; currentVenue = _prevVenue;
  }
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
  updateHeaderMeta(venue, rno);

  // ピックアップタグ種別を buildScenarioBuyPanel に伝える
  // 締め切り後に buildTopPickupRaces が再計算しても上書きされるため、
  // renderBuy を呼ぶ直前にセットし、呼んだ直後にリセットする。
  const pickupCard = _lastPickups && _lastPickups.find(p => p.venue === venue && p.rno === rno);
  if (pickupCard) {
    const tagTypes = pickupCard.tags.map(t => t.type);
    _pickupRaceTagType = tagTypes.includes('in_neg')    ? 'in_neg'
                       : tagTypes.includes('in_tetsup') ? 'in_tetsup'
                       : null;
  } else {
    _pickupRaceTagType = null;
  }

  switchTab('detail2');
  renderBuy(rno);
  _pickupRaceTagType = null;  // 使い捨てリセット
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
    updateHeaderMeta(venue, targetRace);
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
    updateHeaderMeta(venue, targetRace);
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
  // TOPページが表示中なら calcTopAIStats を再実行（fetchAndMergeJsonData 完了後の再描画）
  const topPageEl = document.getElementById('top-page');
  if (topPageEl && topPageEl.style.display !== 'none') {
    try { calcTopAIStats(); } catch(e) { console.warn('[autoRefresh] calcTopAIStats error:', e); }
    return;
  }

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
