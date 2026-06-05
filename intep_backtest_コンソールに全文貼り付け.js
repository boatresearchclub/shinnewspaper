// ══════════════════════════════════════════════════════════════════════
// イン鉄板 新ロジック バックテスト スクリプト
//
// 【使い方】
//   ブラウザのコンソールに貼り付けて実行するだけ。
//   キャッシュを参照せず全レース再計算するため、
//   旧ロジック vs 新ロジックの比較が可能。
//
// 【出力】
//   コンソールにサマリーテーブルを表示 +
//   ページ内に比較パネルを挿入
//
// 【パラメータ（必要に応じて変更）】
//   DAYS         : 集計日数（デフォルト30日）
//   IT_P2_DIVERGE_MIN : 2着乖離率閾値（1.2 = 20%上振れ以上）
//   IT_P3_TAIL_RATIO  : 3着最下位カット比率（平均の0.5倍未満）
//   IT_P3_ABS_MIN     : 3着最下位カット絶対値（10%未満）
//   IT_EV_MIN         : EV除外ガード閾値（0.75未満で除外）
// ══════════════════════════════════════════════════════════════════════

(function() {

const DAYS             = 30;
const IT_P2_DIVERGE_MIN = 1.2;
const IT_P3_TAIL_RATIO  = 0.5;
const IT_P3_ABS_MIN     = 0.10;
const IT_EV_MIN         = 0.75;

// ── ユーティリティ ──
function _normC(c) { return (c || '').replace(/[－−–—―‐‑‒\-]/g, '-'); }

function _calcSynth(comboStrs, oddsMap) {
  if (!comboStrs || comboStrs.length === 0) return null;
  let denom = 0, cnt = 0;
  comboStrs.forEach(c => {
    const ov = oddsMap[_normC(c)] ?? null;
    if (ov != null && ov > 0) { denom += 1 / ov; cnt++; }
  });
  return (cnt > 0 && denom > 0) ? 1 / denom : null;
}

function _digitsOnly(s) { return (s || '').replace(/[^1-6]/g, ''); }

// ── 新ロジック: イン鉄板買い目生成 ──
function computeInTepNew(venue, vdata, rno) {
  const saved = (typeof window._setDataForCalc === 'function')
    ? window._setDataForCalc(vdata, venue) : null;

  try {
    const rd = vdata?.races?.[String(rno)];
    if (!rd || !rd.boats || rd.boats.length < 2) return [];

    if (typeof calcTenkaiProbs !== 'function' ||
        typeof calcScenarioData !== 'function') return [];

    const arek = (typeof rd.arek === 'number' && rd.arek > 0) ? rd.arek : 54.7;
    const rawBoats = rd.boats;

    // final_prob 計算
    let ranked2;
    try {
      ranked2 = calcTenkaiProbs(rawBoats, arek);
      if (!ranked2 || ranked2.length < 2) return [];
      const probTotal = ranked2.reduce((s, b) => s + b.prob, 0) || 1;
      ranked2.forEach(b => { b.final_prob = b.prob / probTotal; });
      ranked2.sort((a, b) => b.final_prob - a.final_prob);
    } catch(e) { return []; }

    // 1号艇 final_prob が 0.75 未満 → 条件不成立
    const boat1 = ranked2.find(b => b.boat === 1);
    if (!boat1 || (boat1.final_prob ?? 0) < 0.75) return [];

    // シナリオデータ
    let sd;
    try {
      const place2Map = (typeof calcPlace2Probs === 'function')
        ? calcPlace2Probs(rawBoats, ranked2) : {};
      const ranked2w = ranked2.map(b => ({ ...b, place2_prob: place2Map[b.boat] || 0 }));
      sd = calcScenarioData(ranked2w, rawBoats, null, venue, vdata);
    } catch(e) { return []; }

    if (!sd || !sd.valid) return [];

    // inn_2place 取得
    const _inn2p = (() => {
      const v = (vdata.inn_data || {}).inn_2place;
      if (v && typeof v === 'object' && !Array.isArray(v) && Object.keys(v).length > 0) return v;
      return (typeof MASTER_EXT !== 'undefined')
        ? MASTER_EXT?.venue_stats?.[venue]?.inn_2place || null : null;
    })();

    // シナリオ加重2着確率マップ
    function getP2WeightedMap(winnerBoat) {
      if (!sd.scenarioPlace2?.[winnerBoat]) {
        const m = {};
        ranked2.filter(r => r.boat !== winnerBoat)
          .forEach(r => { m[r.boat] = r.final_prob ?? 0; });
        return m;
      }
      const totals = {};
      let ws = 0;
      for (const [kimari, list] of Object.entries(sd.scenarioPlace2[winnerBoat])) {
        const sp = sd.scenarioProb?.[winnerBoat]?.[kimari] ?? 0;
        ws += sp;
        (list || []).forEach(x => {
          totals[x.boat] = (totals[x.boat] ?? 0) + x.p2 * sp;
        });
      }
      if (ws > 0) Object.keys(totals).forEach(k => { totals[k] /= ws; });
      return totals;
    }

    // 2着軸リスト（乖離率フィルタ付き）
    function getP2Axis() {
      const wMap = getP2WeightedMap(1);
      const boats = Object.entries(wMap)
        .map(([b, w]) => ({ boat: parseInt(b), w }))
        .filter(x => x.boat !== 1 && !isNaN(x.boat))
        .sort((a, b) => b.w - a.w);

      if (boats.length === 0) return [];

      if (_inn2p) {
        const diverged = boats.filter(x => {
          const avg = _inn2p[String(x.boat)] ?? _inn2p[x.boat] ?? null;
          if (avg == null || avg <= 0) return true;
          return (x.w / avg) >= IT_P2_DIVERGE_MIN;
        });
        return (diverged.length > 0 ? diverged : boats.slice(0, 1)).map(x => x.boat);
      }
      return boats.map(x => x.boat);
    }

    // 3着候補（最下位カット付き）
    function getP3(secondBoat) {
      let list;
      const thirdAll = sd.merged3rdMap?.[1]?.[secondBoat] || [];
      if (thirdAll.length > 0) {
        list = thirdAll.filter(x => x.boat !== 1 && x.boat !== secondBoat)
          .map(x => ({ boat: x.boat, r3: x.r3 ?? 0 }));
      } else {
        list = ranked2.filter(r => r.boat !== 1 && r.boat !== secondBoat)
          .sort((a, b) => (b.final_prob ?? 0) - (a.final_prob ?? 0))
          .map(r => ({ boat: r.boat, r3: r.final_prob ?? 0 }));
      }
      if (list.length >= 2) {
        const avg = list.reduce((s, x) => s + x.r3, 0) / list.length;
        const tail = list[list.length - 1];
        if (tail.r3 < avg * IT_P3_TAIL_RATIO && tail.r3 < IT_P3_ABS_MIN) {
          list = list.slice(0, -1);
        }
      }
      return list.map(x => x.boat).slice(0, 3);
    }

    const p2Axes = getP2Axis();
    if (p2Axes.length === 0) return [];

    const seen = new Set();
    const combos = [];
    p2Axes.forEach(second => {
      const thirds = getP3(second);
      thirds.forEach(t => {
        if (t === 1 || t === second) return;
        const fwd = `1-${second}-${t}`;
        const bwd = `1-${t}-${second}`;
        if (!seen.has(fwd)) { seen.add(fwd); combos.push(fwd); }
        if (!seen.has(bwd)) { seen.add(bwd); combos.push(bwd); }
      });
    });

    return combos;

  } finally {
    if (saved && typeof window._restoreDataForCalc === 'function') {
      window._restoreDataForCalc(saved);
    }
  }
}

// ── 旧ロジック: キャッシュ or computeInTepCombos を使う ──
function computeInTepOld(venue, vdata, rno) {
  // computeInTepCombos が定義されていれば呼ぶ
  if (typeof computeInTepCombos === 'function') {
    try {
      return computeInTepCombos(venue, vdata, rno) || [];
    } catch(e) { return []; }
  }
  // 未定義の場合は空を返す（比較不可）
  return null; // null = 比較不可を示す
}

// ── 日付リスト取得 ──
function getTargetDates() {
  const dates = (typeof getAvailableDates === 'function')
    ? getAvailableDates()
    : Object.keys(ALL_DATA_HISTORY || {}).sort();
  return dates.slice(-DAYS);
}

// ── 集計メイン ──
function runBacktest() {
  const dates = getTargetDates();
  if (dates.length === 0) { console.error('日付データなし'); return; }

  // 旧/新それぞれの集計バケット
  const newStats = { total: 0, hit: 0, bet: 0, ret: 0, excluded: 0, noOdds: 0 };
  const oldStats = { total: 0, hit: 0, bet: 0, ret: 0, excluded: 0, noOdds: 0 };
  const rows = []; // 詳細行

  let processed = 0;

  dates.forEach(dateStr => {
    const dataForDate = (typeof getDataForDate === 'function')
      ? getDataForDate(dateStr)
      : (ALL_DATA_HISTORY?.[dateStr] || {});

    const dateNd = dateStr.replace(/-/g, '');

    (typeof VENUE_LIST !== 'undefined' ? VENUE_LIST : Object.keys(dataForDate))
      .forEach(venue => {
        if (venue === '江戸川') return;
        const vdata = dataForDate?.[venue];
        if (!vdata || !vdata.races) return;

        const slug = (typeof SLUG_MAP !== 'undefined' ? SLUG_MAP[venue] : null) || venue;

        Object.keys(vdata.races).sort((a, b) => +a - +b).forEach(rnoStr => {
          const rno = parseInt(rnoStr);
          const rd  = vdata.races[rnoStr];
          if (!rd || !rd.boats || rd.boats.length < 2) return;

          // 結果なし（未確定）→ スキップ
          const rKey   = `${slug}_${dateNd}_${rno}`;
          const result = (typeof RESULT_DATA !== 'undefined') ? RESULT_DATA?.[rKey] : null;
          if (!result || !result.sanrentan || result.sanrentan.length === 0) return;

          // 除外条件チェック
          if (typeof hasInsufficient === 'function' && hasInsufficient(rd)) return;
          if (typeof hasCourseOrderChange === 'function' && hasCourseOrderChange(rno, vdata)) return;
          if (typeof hasNoLapTime === 'function' && hasNoLapTime(rno, vdata)) return;

          processed++;

          // 確定結果
          const actualRaw    = result.sanrentan[0]?.combo ?? null;
          const actualResult = actualRaw ? _normC(actualRaw) : null;
          const actualDigits = actualResult ? _digitsOnly(actualResult) : null;

          // オッズマップ（RESULT_DATA から再構築）
          const oddsMap = {};
          (result?.sanrentan || []).forEach(s => {
            if (s?.combo && s?.odds != null && s.odds > 0) {
              const ov = s.odds >= 100 ? s.odds / 100 : s.odds;
              oddsMap[_normC(s.combo)] = ov;
            }
          });

          const isHitCheck = (comboStrs) => !!(actualResult && (
            comboStrs.some(c => c === actualResult) ||
            (actualDigits && actualDigits.length === 3 &&
              comboStrs.some(c => _digitsOnly(c) === actualDigits))
          ));

          const getHitOdds = () => {
            const _m = (result?.sanrentan || []).find(s =>
              s?.combo && _normC(s.combo) === actualResult
            ) || result.sanrentan[0];
            const rdOdds = _m?.odds ?? null;
            if (rdOdds != null && rdOdds > 0) {
              return rdOdds < 100 ? Math.round(rdOdds * 100) : rdOdds;
            }
            return 0;
          };

          // ── 新ロジック集計 ──
          const newCombos = computeInTepNew(venue, vdata, rno);
          if (newCombos.length > 0) {
            const synth = _calcSynth(newCombos, oddsMap);
            // EVガード: synth取得済みかつ EV < IT_EV_MIN → 除外カウント
            const hitProbEst = null; // バックテストでは確率計算省略（EV算出不可）
            // EV除外は synth のみでは判断不可（hitProbEst が必要）→ ガードはスキップ
            // ※ 画面側では hitProbEst を使うが、ここではシンプルに点数・的中のみ集計

            const isHit = isHitCheck(newCombos);
            newStats.total++;
            if (isHit) {
              newStats.hit++;
              newStats.ret += getHitOdds();
            }
            newStats.bet += newCombos.length * 100;
            if (synth == null) newStats.noOdds++;

            rows.push({
              date: dateStr, venue, rno,
              newPts: newCombos.length,
              newHit: isHit,
              newCombos: newCombos.join(' / '),
              actual: actualResult,
            });
          }

          // ── 旧ロジック集計 ──
          const oldCombos = computeInTepOld(venue, vdata, rno);
          if (oldCombos === null) return; // computeInTepCombos 未定義 → 旧比較スキップ
          if (oldCombos.length > 0) {
            const isHitOld = isHitCheck(oldCombos);
            oldStats.total++;
            if (isHitOld) {
              oldStats.hit++;
              oldStats.ret += getHitOdds();
            }
            oldStats.bet += oldCombos.length * 100;
          }
        });
      });
  });

  // ── 結果表示 ──
  const fmt = (n, d) => n == null ? '—' : n.toFixed(d);
  const pct = (a, b) => b > 0 ? (a / b * 100).toFixed(1) + '%' : '—';

  console.group('🔒 イン鉄板 新ロジック バックテスト結果');
  console.log(`集計期間: ${dates[0]} 〜 ${dates[dates.length-1]}  (${dates.length}日間)`);
  console.log(`処理レース数（全条件前）: ${processed}R`);
  console.log('');
  console.log('【新ロジック（乖離率フィルタ + 3着最下位カット）】');
  console.log(`  対象R数  : ${newStats.total}R`);
  console.log(`  的中R数  : ${newStats.hit}R`);
  console.log(`  的中率   : ${pct(newStats.hit, newStats.total)}`);
  console.log(`  総投資   : ¥${newStats.bet.toLocaleString()}`);
  console.log(`  総回収   : ¥${newStats.ret.toLocaleString()}`);
  console.log(`  回収率   : ${pct(newStats.ret, newStats.bet)}`);
  console.log(`  平均点数 : ${newStats.total > 0 ? fmt(newStats.bet / newStats.total / 100, 1) : '—'}点`);

  if (oldStats.total > 0) {
    console.log('');
    console.log('【旧ロジック（フィルタなし）】');
    console.log(`  対象R数  : ${oldStats.total}R`);
    console.log(`  的中R数  : ${oldStats.hit}R`);
    console.log(`  的中率   : ${pct(oldStats.hit, oldStats.total)}`);
    console.log(`  総投資   : ¥${oldStats.bet.toLocaleString()}`);
    console.log(`  総回収   : ¥${oldStats.ret.toLocaleString()}`);
    console.log(`  回収率   : ${pct(oldStats.ret, oldStats.bet)}`);
    console.log(`  平均点数 : ${oldStats.total > 0 ? fmt(oldStats.bet / oldStats.total / 100, 1) : '—'}点`);
  }
  console.groupEnd();

  // ── ページ内パネル挿入 ──
  const panelId = 'intep-bt-panel';
  const existing = document.getElementById(panelId);
  if (existing) existing.remove();

  const newHitRate  = newStats.total > 0 ? newStats.hit / newStats.total : null;
  const newRecRate  = newStats.bet  > 0 ? newStats.ret  / newStats.bet  : null;
  const oldHitRate  = oldStats.total > 0 ? oldStats.hit / oldStats.total : null;
  const oldRecRate  = oldStats.bet  > 0 ? oldStats.ret  / oldStats.bet  : null;

  const col = (v, lo, hi) => v == null ? '#888'
    : v >= hi ? '#4caf50' : v >= lo ? '#ff9800' : '#f44336';

  const statRow = (label, val, lo, hi, sub) => `
    <div style="display:flex;justify-content:space-between;align-items:center;
      padding:5px 0;border-bottom:1px solid rgba(255,255,255,.08)">
      <span style="font-size:11px;color:#aaa">${label}</span>
      <span style="font-size:15px;font-weight:700;font-family:monospace;color:${col(val,lo,hi)}">
        ${val == null ? '—' : (val*100).toFixed(1) + '%'}
        ${sub ? `<span style="font-size:10px;color:#888;font-weight:400"> ${sub}</span>` : ''}
      </span>
    </div>`;

  const numRow = (label, val) => `
    <div style="display:flex;justify-content:space-between;align-items:center;
      padding:5px 0;border-bottom:1px solid rgba(255,255,255,.08)">
      <span style="font-size:11px;color:#aaa">${label}</span>
      <span style="font-size:13px;font-weight:700;font-family:monospace;color:#ddd">${val}</span>
    </div>`;

  const oldBlock = oldStats.total > 0 ? `
    <div style="flex:1;min-width:150px">
      <div style="font-size:11px;font-weight:700;color:#aaa;text-align:center;margin-bottom:8px">
        旧ロジック
      </div>
      ${statRow('的中率', oldHitRate, 0.5, 0.7, `${oldStats.hit}/${oldStats.total}R`)}
      ${statRow('回収率', oldRecRate, 0.75, 1.0)}
      ${numRow('総投資', '¥' + oldStats.bet.toLocaleString())}
      ${numRow('総回収', '¥' + oldStats.ret.toLocaleString())}
      ${numRow('平均点数', oldStats.total > 0 ? (oldStats.bet / oldStats.total / 100).toFixed(1) + '点' : '—')}
    </div>` : '';

  const panel = document.createElement('div');
  panel.id = panelId;
  panel.style.cssText = `
    position:fixed;bottom:16px;right:16px;z-index:99999;
    background:#1e1e2e;border:1px solid #444;border-radius:10px;
    padding:14px 16px;min-width:320px;max-width:640px;
    box-shadow:0 4px 24px rgba(0,0,0,.6);color:#ddd;
  `;
  panel.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
      <span style="font-size:13px;font-weight:700;color:#fff">
        🔒 イン鉄板 バックテスト
        <span style="font-size:10px;font-weight:400;color:#888">
          ${dates[0].slice(5)} 〜 ${dates[dates.length-1].slice(5)}
        </span>
      </span>
      <button onclick="document.getElementById('${panelId}').remove()"
        style="background:none;border:none;color:#888;font-size:16px;cursor:pointer;padding:0 4px">×</button>
    </div>
    <div style="display:flex;gap:16px;flex-wrap:wrap">
      <div style="flex:1;min-width:150px">
        <div style="font-size:11px;font-weight:700;color:#4da8ff;text-align:center;margin-bottom:8px">
          新ロジック（乖離率${IT_P2_DIVERGE_MIN}倍 / 最下位カット）
        </div>
        ${statRow('的中率', newHitRate, 0.5, 0.7, `${newStats.hit}/${newStats.total}R`)}
        ${statRow('回収率', newRecRate, 0.75, 1.0)}
        ${numRow('総投資', '¥' + newStats.bet.toLocaleString())}
        ${numRow('総回収', '¥' + newStats.ret.toLocaleString())}
        ${numRow('平均点数', newStats.total > 0 ? (newStats.bet / newStats.total / 100).toFixed(1) + '点' : '—')}
      </div>
      ${oldBlock}
    </div>
    <div style="margin-top:8px;font-size:10px;color:#666;text-align:center">
      ※ EVガードはhitProbEst要・本集計はオッズのみで算出
    </div>
  `;
  document.body.appendChild(panel);

  return { newStats, oldStats, rows };
}

// 実行
const _bt = runBacktest();
console.log('詳細行は _bt.rows で参照できます（例: copy(JSON.stringify(_bt.rows))）');
window._intepBtResult = _bt;

})();
