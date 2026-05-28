// csv_export.js — バックテストCSV生成・エクスポート（sample.js から分離）
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
        日付:           dateStr,
        日前:           dateLabels[dateStr] || '',
        会場:           r.venue,
        R番号:          r.rno,
        あれ指数:       r.arek || '',
        展示あり:       r.hasTenji ? '○' : '×',
        予想TOP3:       r.predTop3 || '',
        予想1位艇:      r.pred1boat || '',
        予想1位_base:   r.pred1_base || '',
        予想1位_tenkai: r.pred1_tenkai || '',
        予想1位_tenji:  r.pred1_tenji || '',
        '1号艇_base':   r.boat1_base || '',
        '1号艇_tenkai': r.boat1_tenkai || '',
        '1号艇_tenji':  r.boat1_tenji || '',
        パターン:       r.opt_pattern || '',
        推奨点数:       r.opt_points != null ? r.opt_points : '',
        買い目点数:     r.buy3cnt,
        買い目組合せ:   r.buy3combos || '',
        的中:           r.isHit ? '的中' : '外れ',
        払戻金:         r.isHit ? r.hitOdds : '',
        的中組合せ:     r.hitCombo || '',
        実際の結果:     r.actualResult || '',
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

// ── 全モード同時ダウンロード（少し間を置いて連続ダウンロード）──
function exportBacktestCSV_both() {
  const rowsHit  = _buildBacktestRows('hit');
  const rowsRec  = _buildBacktestRows('rec');
  const rowsScen = _buildScenBacktestRows(false);
  if (rowsHit.length === 0 && rowsRec.length === 0 && rowsScen.length === 0) {
    alert('エクスポートできるデータがありません。');
    return;
  }
  const date = new Date().toISOString().slice(0, 10).replace(/-/g, '');
  const blobHit = _rowsToCSVBlob(rowsHit);
  if (blobHit) _triggerDownload(blobHit, `backtest_hit_${date}.csv`);
  // ブラウザが連続ダウンロードをブロックしないよう 300ms ずらす
  setTimeout(() => {
    const blobRec = _rowsToCSVBlob(rowsRec);
    if (blobRec) _triggerDownload(blobRec, `backtest_rec_${date}.csv`);
  }, 300);
  setTimeout(() => {
    const blobScen = _rowsToCSVBlob(rowsScen);
    if (blobScen) _triggerDownload(blobScen, `backtest_scen_${date}.csv`);
  }, 600);
}

// ── シナリオ買い CSV 行データ生成 ──
function _buildScenBacktestRows(includeAll = false) {
  const allDates   = getAvailableDates().slice().reverse();
  const todayDate  = getAvailableDates().slice(-1)[0];
  const dateLabels = { [todayDate]: '本日' };
  getAvailableDates().slice(0, -1).reverse().forEach((d, i) => {
    dateLabels[d] = `${i + 1}日前`;
  });

  const output = [];
  allDates.forEach(dateStr => {
    const results = collectResultsForDateScen(dateStr, includeAll);
    results.forEach(r => {
      const invest = r.buyCnt * 100;
      const ret    = r.isHit ? r.hitOdds : 0;
      const pnl    = ret - invest;
      output.push({
        日付:           dateStr,
        日前:           dateLabels[dateStr] || '',
        会場:           r.venue,
        R番号:          r.rno,
        あれ指数:       r.arek || '',
        展示あり:       r.hasTenji ? '○' : '×',
        予想TOP3:       r.predTop3 || '',
        予想1位艇:      r.pred1boat || '',
        予想1位_base:   r.pred1_base || '',
        予想1位_tenkai: r.pred1_tenkai || '',
        予想1位_tenji:  r.pred1_tenji || '',
        '1号艇_base':   r.boat1_base || '',
        '1号艇_tenkai': r.boat1_tenkai || '',
        '1号艇_tenji':  r.boat1_tenji || '',
        合成オッズ:     r.avgOdds != null ? r.avgOdds.toFixed(2) : '',
        買い目点数:     r.buyCnt,
        買い目組合せ:   r.buyCombos || '',
        的中:           r.isHit ? '的中' : '外れ',
        投資額:         invest,
        払戻金:         ret || '',
        損益:           pnl,
        的中組合せ:     r.hitCombo || '',
        実際の結果:     r.actualResult || '',
        実際の決まり手: r.actualKimari || '',
      });
    });
  });
  return output;
}

// ── シナリオ買い CSV エクスポート（合成オッズフィルターあり）──
function exportBacktestCSV_scen() {
  const rows = _buildScenBacktestRows(false);
  const blob = _rowsToCSVBlob(rows);
  if (!blob) { alert('エクスポートできるデータがありません。'); return; }
  const date = new Date().toISOString().slice(0, 10).replace(/-/g, '');
  _triggerDownload(blob, `backtest_scen_${date}.csv`);
}

// 旧関数: 後方互換のため残す（hit モードと同等）
function exportBacktestCSV() {
  exportBacktestCSV_hit();
}

