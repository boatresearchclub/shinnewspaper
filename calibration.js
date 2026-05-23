// calibration.js — 確率推定キャリブレーション（完全外付けモジュール）
//
// 【設計方針】
//   既存コード（backtest.js / top_stats.js）への変更はゼロ。
//   collectResultsForDateScen(d, true) が返す results[] を受け取るだけ。
//   必要なフィールド: hitProbEst (number|null), isHit (boolean)
//
// 【使い方】
//   _renderHistory30 の elHistory.innerHTML 代入の直前に1行追加するだけ:
//
//     _renderCalibrationPanel(allResultsScenAll);   // ← これだけ追加
//     elHistory.innerHTML = `...`;                  // 既存行はそのまま
//
//   描画先 DOM は自動生成。id="top-ai-calibration-panel" が存在しない場合は
//   top-ai-stats-history-summary の直後に自動挿入する。
//
// ─────────────────────────────────────────────────────────────────────

(function () {

  // calibration.js の先頭に追加
  const _isAdmin = new URLSearchParams(location.search).has('admin');
  if (!_isAdmin) return; // adminパラメータがなければ何もしない

  // ── ビン定義 ──
  // hitProbEst の値域 [0, 1] を6段階に分割
  const BINS = [
    { label: '0–10%',  min: 0.00, max: 0.10 },
    { label: '10–20%', min: 0.10, max: 0.20 },
    { label: '20–30%', min: 0.20, max: 0.30 },
    { label: '30–40%', min: 0.30, max: 0.40 },
    { label: '40–60%', min: 0.40, max: 0.60 },
    { label: '60%+',   min: 0.60, max: 1.01 },
  ];

  // ── メイン集計関数 ──
  // results[]: collectResultsForDateScen(d, true) の返り値を30日分結合したもの
  // 戻り値: ビン別統計の配列
  function calcCalibration(results) {
    const valid = results.filter(r => r.hitProbEst != null);

    return BINS.map(bin => {
      const inBin   = valid.filter(r => r.hitProbEst >= bin.min && r.hitProbEst < bin.max);
      const total   = inBin.length;
      const hits    = inBin.filter(r => r.isHit).length;
      const actual  = total > 0 ? hits / total : null;
      const estAvg  = total > 0
        ? inBin.reduce((s, r) => s + r.hitProbEst, 0) / total
        : null;
      return { label: bin.label, total, hits, actual, estAvg };
    });
  }

  // ── キャリブレーション品質スコア ──
  // 各ビンの |推定 − 実績| を加重平均（サンプル数重み）
  // 0に近いほど良い。0.05以下なら優秀、0.10超は要見直し
  function calcCalibrationError(binStats) {
    const valid = binStats.filter(b => b.total > 0 && b.actual != null && b.estAvg != null);
    if (valid.length === 0) return null;
    const totalN  = valid.reduce((s, b) => s + b.total, 0);
    const wErr    = valid.reduce((s, b) => s + Math.abs(b.estAvg - b.actual) * b.total, 0);
    return wErr / totalN;
  }

  // ── 単調性チェック ──
  // 推定値が上がるほど実際の的中率も上がっているか（理想的な予測モデルの条件）
  // 有効ビン間で「逆転」が何回起きているかを返す
  function countMonotonicViolations(binStats) {
    const valid = binStats.filter(b => b.total >= 5 && b.actual != null);
    let violations = 0;
    for (let i = 1; i < valid.length; i++) {
      if (valid[i].actual < valid[i - 1].actual - 0.02) violations++;
    }
    return violations;
  }

  // ── HTML生成 ──
  function buildCalibrationHTML(binStats, calError, violations, totalValid) {
    if (totalValid < 30) {
      return `
        <div style="background:var(--bg3);border-radius:var(--radius-sm);padding:12px;border:1px solid var(--border)">
          <div style="font-size:10px;font-weight:700;color:var(--text3);text-align:center;margin-bottom:4px">📐 確率キャリブレーション</div>
          <div style="color:var(--text3);font-size:11px;text-align:center;padding:0.3rem 0">
            データ不足（${totalValid}件）<br>30件以上で表示
          </div>
        </div>`;
    }

    // 品質判定
    const errLabel  = calError == null   ? '—'
                    : calError <= 0.05   ? '優秀'
                    : calError <= 0.10   ? '良好'
                    : calError <= 0.15   ? '要注意'
                    : '問題あり';
    const errColor  = calError == null   ? 'var(--text3)'
                    : calError <= 0.05   ? 'var(--green)'
                    : calError <= 0.10   ? 'var(--green)'
                    : calError <= 0.15   ? 'var(--orange)'
                    : 'var(--red, #e05)';
    const errStr    = calError != null ? `${(calError * 100).toFixed(1)}%誤差・${errLabel}` : '—';

    const monLabel  = violations === 0 ? '✓ 単調増加（理想的）'
                    : violations === 1 ? `△ 軽微な逆転あり（${violations}箇所）`
                    : `✗ 逆転${violations}箇所（要確認）`;
    const monColor  = violations === 0 ? 'var(--green)'
                    : violations === 1 ? 'var(--orange)'
                    : 'var(--red, #e05)';

    // バーチャート行
    const maxBar = 120; // px
    const rows = binStats.map(b => {
      if (b.total === 0) {
        return `
          <tr style="border-bottom:1px solid var(--border)">
            <td style="padding:3px 6px;font-size:10px;color:var(--text3);white-space:nowrap">${b.label}</td>
            <td colspan="4" style="padding:3px 6px;font-size:10px;color:var(--text3);text-align:center">—</td>
          </tr>`;
      }
      const estPct    = b.estAvg  != null ? (b.estAvg  * 100).toFixed(0) + '%' : '—';
      const actPct    = b.actual  != null ? (b.actual  * 100).toFixed(0) + '%' : '—';
      const actWidth  = b.actual  != null ? Math.round(b.actual  * maxBar) : 0;
      const estWidth  = b.estAvg  != null ? Math.round(b.estAvg  * maxBar) : 0;
      const diff      = (b.actual != null && b.estAvg != null) ? b.actual - b.estAvg : null;
      const diffStr   = diff != null
        ? (diff >= 0 ? `+${(diff*100).toFixed(0)}` : `${(diff*100).toFixed(0)}`) + '%'
        : '—';
      const diffColor = diff == null       ? 'var(--text3)'
                      : Math.abs(diff) <= 0.05 ? 'var(--green)'
                      : Math.abs(diff) <= 0.10 ? 'var(--orange)'
                      : 'var(--red, #e05)';
      const lowN = b.total < 10;

      return `
        <tr style="border-bottom:1px solid var(--border)">
          <td style="padding:4px 6px;font-size:10px;color:var(--text3);white-space:nowrap">${b.label}</td>
          <td style="padding:4px 6px;min-width:90px">
            <div style="position:relative;height:14px;background:var(--bg2);border-radius:2px;overflow:hidden">
              <div style="position:absolute;left:0;top:0;height:100%;width:${estWidth}px;background:var(--border);border-radius:2px;opacity:0.6"></div>
              <div style="position:absolute;left:0;top:0;height:100%;width:${actWidth}px;background:${actWidth >= estWidth ? 'var(--green)' : 'var(--orange)'};border-radius:2px;opacity:0.85"></div>
            </div>
          </td>
          <td style="padding:4px 6px;text-align:right;font-size:10px;color:var(--text3)">${estPct}</td>
          <td style="padding:4px 6px;text-align:right;font-size:11px;font-weight:700;color:var(--text${lowN ? '3' : ''})">${actPct}${lowN ? '<span style="font-size:9px;color:var(--text3)">*</span>' : ''}</td>
          <td style="padding:4px 6px;text-align:right;font-size:10px;font-weight:700;color:${diffColor}">${diffStr}</td>
        </tr>`;
    }).join('');

    return `
      <div style="background:var(--bg3);border-radius:var(--radius-sm);padding:12px;border:1px solid var(--border)">
        <div style="font-size:10px;font-weight:700;color:var(--text3);text-align:center;margin-bottom:2px">📐 確率キャリブレーション</div>
        <div style="font-size:10px;color:var(--text3);text-align:center;margin-bottom:8px">推定的中率 vs 実績的中率（${totalValid}件）</div>

        <div style="display:flex;flex-direction:column;gap:4px;margin-bottom:8px">
          <div style="display:flex;justify-content:space-between;border-bottom:1px solid var(--border);padding-bottom:3px">
            <span style="font-size:10px;color:var(--text3)">加重平均誤差</span>
            <span style="font-size:11px;font-weight:700;color:${errColor}">${errStr}</span>
          </div>
          <div style="display:flex;justify-content:space-between">
            <span style="font-size:10px;color:var(--text3)">単調性</span>
            <span style="font-size:10px;font-weight:700;color:${monColor}">${monLabel}</span>
          </div>
        </div>

        <div style="overflow-x:auto">
          <table style="width:100%;border-collapse:collapse">
            <thead>
              <tr style="border-bottom:1px solid var(--border)">
                <th style="padding:3px 6px;text-align:left;font-size:9px;color:var(--text3);font-weight:500">推定帯</th>
                <th style="padding:3px 6px;text-align:left;font-size:9px;color:var(--text3);font-weight:500">バー</th>
                <th style="padding:3px 6px;text-align:right;font-size:9px;color:var(--text3);font-weight:500">推定</th>
                <th style="padding:3px 6px;text-align:right;font-size:9px;color:var(--text3);font-weight:500">実績</th>
                <th style="padding:3px 6px;text-align:right;font-size:9px;color:var(--text3);font-weight:500">差</th>
              </tr>
            </thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
        <div style="font-size:9px;color:var(--text3);margin-top:4px">
          灰バー=推定、色バー=実績　* N&lt;10の参考値
        </div>
      </div>`;
  }

  // ── DOM への描画 ──
  function _ensureContainer() {
    let el = document.getElementById('top-ai-calibration-panel');
    if (el) return el;
    el = document.createElement('div');
    el.id = 'top-ai-calibration-panel';
    const ref = document.getElementById('top-ai-stats-history-summary');
    if (ref && ref.parentNode) {
      ref.parentNode.insertBefore(el, ref.nextSibling);
    } else {
      document.body.appendChild(el);
    }
    return el;
  }

  // ── 公開関数（これだけ既存コードから呼ぶ）──
  window._renderCalibrationPanel = function (allResultsScenAll) {
    try {
      const container  = _ensureContainer();
      const binStats   = calcCalibration(allResultsScenAll || []);
      const calError   = calcCalibrationError(binStats);
      const violations = countMonotonicViolations(binStats);
      const totalValid = (allResultsScenAll || []).filter(r => r.hitProbEst != null).length;
      container.innerHTML = `
        <div class="ai-stats-card" style="margin-bottom:0.6rem">
          <div style="display:grid;grid-template-columns:1fr;gap:10px">
            ${buildCalibrationHTML(binStats, calError, violations, totalValid)}
          </div>
        </div>`;
    } catch (e) {
      console.warn('[calibration] render error:', e);
    }
  };

})();
