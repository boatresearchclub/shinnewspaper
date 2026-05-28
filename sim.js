// sim.js — 展開シミュモーダル v2（sample.js から分離）
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
  _ensureTenjiCache();
  const slug     = VENUE_SLUG_MAP[DATA.venue] || DATA.venue || '';
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
  _ensureTenjiCache();
  const hasTenji = !!tenjiCoefs;

  // ── 展示タイム生データを取得（シミュ用） ──
  const tenjiRawSim = {};
  if(hasTenji){
    const slugSim = VENUE_SLUG_MAP[DATA?.venue] || DATA?.venue || '';
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
      if (m === 'scen') btn.onclick = exportBacktestCSV_scen;
      if (m === 'both') btn.onclick = exportBacktestCSV_both;
    });

    // data-csv-mode がない場合はボタンのテキストで判定（後方互換）
    document.querySelectorAll('button').forEach(btn => {
      const t = btn.textContent || '';
      if (t.includes('的中重視') && t.includes('CSV') && !btn.getAttribute('data-csv-mode'))
        btn.onclick = exportBacktestCSV_hit;
      if (t.includes('回収重視') && t.includes('CSV') && !btn.getAttribute('data-csv-mode'))
        btn.onclick = exportBacktestCSV_rec;
      if (t.includes('シナリオ') && t.includes('CSV') && !btn.getAttribute('data-csv-mode'))
        btn.onclick = exportBacktestCSV_scen;
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

