<<<<<<< HEAD
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

  // admin 判定（body.admin-mode クラスがある場合のみパネルを描画）
  // ※ 関数定義自体は必ず行う（top_stats.js から呼ばれるため）
  const _isAdmin = document.body.classList.contains('admin-mode');

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
    const valid = binStats.filter(b => b.total >= 10 && b.actual != null); // 修正: N<10は参考値のため単調性チェックから除外
    let violations = 0;
    for (let i = 1; i < valid.length; i++) {
      if (valid[i].actual < valid[i - 1].actual - 0.02) violations++;
    }
    return violations;
  }

  // ══════════════════════════════════════════════════════════════════
  // 2着 calibration
  // ──────────────────────────────────────────────────────────────────
  // results[] の各レースで「実際の2着枠番が予測リストの何位だったか」を集計する。
  // pred2ndRank: top_stats.js の collectResultsForDateScen が付与するフィールド。
  //   1 = 買い目中で最多出現の2着枠番と一致（予測1位的中）
  //   2 = 2番目に多い2着枠番と一致
  //   null = 買い目に実際の2着枠番が含まれていない or データなし
  function calcPlace2Calibration(results) {
    const valid = results.filter(r => r.pred2ndRank != null || r.actual2nd != null);
    const total = valid.length;
    if (total === 0) return null;
    const rank1 = valid.filter(r => r.pred2ndRank === 1).length;
    const top2  = valid.filter(r => r.pred2ndRank != null && r.pred2ndRank <= 2).length;
    const top3  = valid.filter(r => r.pred2ndRank != null && r.pred2ndRank <= 3).length;
    const miss  = valid.filter(r => r.pred2ndRank == null).length;
    return { rank1Rate: rank1/total, top2Rate: top2/total, top3Rate: top3/total, missRate: miss/total, total };
  }

  // ══════════════════════════════════════════════════════════════════
  // 3着 calibration
  // ──────────────────────────────────────────────────────────────────
  // pred3rdRank と同様の集計。3着は選択肢が多い（4〜5枠番）ため
  // top3Rate が実用上の下限目標になる。
  function calcPlace3Calibration(results) {
    const valid = results.filter(r => r.pred3rdRank != null || r.actual3rd != null);
    const total = valid.length;
    if (total === 0) return null;
    const rank1 = valid.filter(r => r.pred3rdRank === 1).length;
    const top2  = valid.filter(r => r.pred3rdRank != null && r.pred3rdRank <= 2).length;
    const top3  = valid.filter(r => r.pred3rdRank != null && r.pred3rdRank <= 3).length;
    const miss  = valid.filter(r => r.pred3rdRank == null).length;
    return { rank1Rate: rank1/total, top2Rate: top2/total, top3Rate: top3/total, missRate: miss/total, total };
  }

  // ── 2着・3着 calibration HTML生成 ──
  function buildPlace2CalibHTML(p2, p3) {
    function barRow(label, rate, threshGood, threshWarn, note) {
      if (rate == null) return '';
      const pct   = (rate * 100).toFixed(0) + '%';
      const color = rate >= threshGood ? 'var(--green)'
                  : rate >= threshWarn ? 'var(--orange)'
                  : 'var(--red, #e05)';
      const w     = Math.round(rate * 120);
      return `
        <tr style="border-bottom:1px solid var(--border)">
          <td style="padding:3px 6px;font-size:10px;color:var(--text3);white-space:nowrap">${label}</td>
          <td style="padding:3px 6px;min-width:96px">
            <div style="height:14px;background:var(--bg2);border-radius:2px;overflow:hidden">
              <div style="height:100%;width:${w}px;background:${color};border-radius:2px;opacity:0.85"></div>
            </div>
          </td>
          <td style="padding:3px 6px;text-align:right;font-size:11px;font-weight:700;color:${color}">${pct}</td>
          <td style="padding:3px 6px;font-size:9px;color:var(--text3)">${note}</td>
        </tr>`;
    }
    const p2Section = p2 ? `
      <div style="font-size:10px;font-weight:700;color:var(--text3);margin:6px 0 2px">2着予測精度（${p2.total}件）</div>
      <table style="width:100%;border-collapse:collapse"><tbody>
        ${barRow('1位的中', p2.rank1Rate, 0.50, 0.35, '目標50%+')}
        ${barRow('2位以内', p2.top2Rate,  0.70, 0.55, '目標70%+')}
        ${barRow('3位以内', p2.top3Rate,  0.85, 0.70, '目標85%+')}
        ${barRow('買い目外', p2.missRate, 0,    0.15, '低いほど良')}
      </tbody></table>` : '<div style="font-size:10px;color:var(--text3);padding:4px 0">2着データ不足</div>';
    const p3Section = p3 ? `
      <div style="font-size:10px;font-weight:700;color:var(--text3);margin:8px 0 2px">3着予測精度（${p3.total}件）</div>
      <table style="width:100%;border-collapse:collapse"><tbody>
        ${barRow('1位的中', p3.rank1Rate, 0.40, 0.28, '目標40%+')}
        ${barRow('2位以内', p3.top2Rate,  0.60, 0.45, '目標60%+')}
        ${barRow('3位以内', p3.top3Rate,  0.75, 0.60, '目標75%+')}
        ${barRow('買い目外', p3.missRate, 0,    0.25, '低いほど良')}
      </tbody></table>` : '<div style="font-size:10px;color:var(--text3);padding:4px 0">3着データ不足</div>';
    const p2ok  = p2 && p2.rank1Rate >= 0.50;
    const p3ok  = p3 && p3.top3Rate  >= 0.75;
    const judge = (!p2 && !p3)   ? null
                : (p2ok && p3ok) ? { text: '2着・3着ともに良好',       color: 'var(--green)'      }
                : (!p2ok&&!p3ok) ? { text: '2着・3着とも要改善',       color: 'var(--red, #e05)'  }
                : p2ok           ? { text: '2着良好・3着は要確認',     color: 'var(--orange)'     }
                :                  { text: '2着要改善・3着は許容範囲', color: 'var(--orange)'     };
    return `
      <div style="background:var(--bg3);border-radius:var(--radius-sm);padding:12px;border:1px solid var(--border)">
        <div style="font-size:10px;font-weight:700;color:var(--text3);text-align:center;margin-bottom:2px">📊 2着・3着 予測精度</div>
        <div style="font-size:10px;color:var(--text3);text-align:center;margin-bottom:6px">買い目内での的中順位分布</div>
        ${judge ? `<div style="font-size:11px;font-weight:700;color:${judge.color};text-align:center;margin-bottom:6px;padding:3px 0;border-bottom:1px solid var(--border)">${judge.text}</div>` : ''}
        <div style="overflow-x:auto">${p2Section}${p3Section}</div>
        <div style="font-size:9px;color:var(--text3);margin-top:5px">
          予測順位=買い目中の枠番出現頻度で判定　買い目外=実際の着順枠が買い目に含まれていなかった割合
        </div>
      </div>`;
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

=======
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

  // admin 判定（body.admin-mode クラスがある場合のみパネルを描画）
  // ※ 関数定義自体は必ず行う（top_stats.js から呼ばれるため）
  const _isAdmin = document.body.classList.contains('admin-mode');

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
    const valid = binStats.filter(b => b.total >= 10 && b.actual != null); // 修正: N<10は参考値のため単調性チェックから除外
    let violations = 0;
    for (let i = 1; i < valid.length; i++) {
      if (valid[i].actual < valid[i - 1].actual - 0.02) violations++;
    }
    return violations;
  }

  // ══════════════════════════════════════════════════════════════════
  // 2着 calibration
  // ──────────────────────────────────────────────────────────────────
  // results[] の各レースで「実際の2着枠番が予測リストの何位だったか」を集計する。
  // pred2ndRank: top_stats.js の collectResultsForDateScen が付与するフィールド。
  //   1 = 買い目中で最多出現の2着枠番と一致（予測1位的中）
  //   2 = 2番目に多い2着枠番と一致
  //   null = 買い目に実際の2着枠番が含まれていない or データなし
  function calcPlace2Calibration(results) {
    const valid = results.filter(r => r.pred2ndRank != null || r.actual2nd != null);
    const total = valid.length;
    if (total === 0) return null;
    const rank1 = valid.filter(r => r.pred2ndRank === 1).length;
    const top2  = valid.filter(r => r.pred2ndRank != null && r.pred2ndRank <= 2).length;
    const top3  = valid.filter(r => r.pred2ndRank != null && r.pred2ndRank <= 3).length;
    const miss  = valid.filter(r => r.pred2ndRank == null).length;
    return { rank1Rate: rank1/total, top2Rate: top2/total, top3Rate: top3/total, missRate: miss/total, total };
  }

  // ══════════════════════════════════════════════════════════════════
  // 3着 calibration
  // ──────────────────────────────────────────────────────────────────
  // pred3rdRank と同様の集計。3着は選択肢が多い（4〜5枠番）ため
  // top3Rate が実用上の下限目標になる。
  function calcPlace3Calibration(results) {
    const valid = results.filter(r => r.pred3rdRank != null || r.actual3rd != null);
    const total = valid.length;
    if (total === 0) return null;
    const rank1 = valid.filter(r => r.pred3rdRank === 1).length;
    const top2  = valid.filter(r => r.pred3rdRank != null && r.pred3rdRank <= 2).length;
    const top3  = valid.filter(r => r.pred3rdRank != null && r.pred3rdRank <= 3).length;
    const miss  = valid.filter(r => r.pred3rdRank == null).length;
    return { rank1Rate: rank1/total, top2Rate: top2/total, top3Rate: top3/total, missRate: miss/total, total };
  }

  // ── 2着・3着 calibration HTML生成 ──
  function buildPlace2CalibHTML(p2, p3) {
    function barRow(label, rate, threshGood, threshWarn, note) {
      if (rate == null) return '';
      const pct   = (rate * 100).toFixed(0) + '%';
      const color = rate >= threshGood ? 'var(--green)'
                  : rate >= threshWarn ? 'var(--orange)'
                  : 'var(--red, #e05)';
      const w     = Math.round(rate * 120);
      return `
        <tr style="border-bottom:1px solid var(--border)">
          <td style="padding:3px 6px;font-size:10px;color:var(--text3);white-space:nowrap">${label}</td>
          <td style="padding:3px 6px;min-width:96px">
            <div style="height:14px;background:var(--bg2);border-radius:2px;overflow:hidden">
              <div style="height:100%;width:${w}px;background:${color};border-radius:2px;opacity:0.85"></div>
            </div>
          </td>
          <td style="padding:3px 6px;text-align:right;font-size:11px;font-weight:700;color:${color}">${pct}</td>
          <td style="padding:3px 6px;font-size:9px;color:var(--text3)">${note}</td>
        </tr>`;
    }
    const p2Section = p2 ? `
      <div style="font-size:10px;font-weight:700;color:var(--text3);margin:6px 0 2px">2着予測精度（${p2.total}件）</div>
      <table style="width:100%;border-collapse:collapse"><tbody>
        ${barRow('1位的中', p2.rank1Rate, 0.50, 0.35, '目標50%+')}
        ${barRow('2位以内', p2.top2Rate,  0.70, 0.55, '目標70%+')}
        ${barRow('3位以内', p2.top3Rate,  0.85, 0.70, '目標85%+')}
        ${barRow('買い目外', p2.missRate, 0,    0.15, '低いほど良')}
      </tbody></table>` : '<div style="font-size:10px;color:var(--text3);padding:4px 0">2着データ不足</div>';
    const p3Section = p3 ? `
      <div style="font-size:10px;font-weight:700;color:var(--text3);margin:8px 0 2px">3着予測精度（${p3.total}件）</div>
      <table style="width:100%;border-collapse:collapse"><tbody>
        ${barRow('1位的中', p3.rank1Rate, 0.40, 0.28, '目標40%+')}
        ${barRow('2位以内', p3.top2Rate,  0.60, 0.45, '目標60%+')}
        ${barRow('3位以内', p3.top3Rate,  0.75, 0.60, '目標75%+')}
        ${barRow('買い目外', p3.missRate, 0,    0.25, '低いほど良')}
      </tbody></table>` : '<div style="font-size:10px;color:var(--text3);padding:4px 0">3着データ不足</div>';
    const p2ok  = p2 && p2.rank1Rate >= 0.50;
    const p3ok  = p3 && p3.top3Rate  >= 0.75;
    const judge = (!p2 && !p3)   ? null
                : (p2ok && p3ok) ? { text: '2着・3着ともに良好',       color: 'var(--green)'      }
                : (!p2ok&&!p3ok) ? { text: '2着・3着とも要改善',       color: 'var(--red, #e05)'  }
                : p2ok           ? { text: '2着良好・3着は要確認',     color: 'var(--orange)'     }
                :                  { text: '2着要改善・3着は許容範囲', color: 'var(--orange)'     };
    return `
      <div style="background:var(--bg3);border-radius:var(--radius-sm);padding:12px;border:1px solid var(--border)">
        <div style="font-size:10px;font-weight:700;color:var(--text3);text-align:center;margin-bottom:2px">📊 2着・3着 予測精度</div>
        <div style="font-size:10px;color:var(--text3);text-align:center;margin-bottom:6px">買い目内での的中順位分布</div>
        ${judge ? `<div style="font-size:11px;font-weight:700;color:${judge.color};text-align:center;margin-bottom:6px;padding:3px 0;border-bottom:1px solid var(--border)">${judge.text}</div>` : ''}
        <div style="overflow-x:auto">${p2Section}${p3Section}</div>
        <div style="font-size:9px;color:var(--text3);margin-top:5px">
          予測順位=買い目中の枠番出現頻度で判定　買い目外=実際の着順枠が買い目に含まれていなかった割合
        </div>
      </div>`;
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

>>>>>>> 71977d02f21aaedfa25a5b188fdbd7816e489bfd
  // ══════════════════════════════════════════════════════════════════
  // コース別 勝率キャリブレーション（本物版）
  // ──────────────────────────────────────────────────────────────────
  // 各レースの全艇 boatProbs（final_prob）を展開し、
  // 「モデルが各枠番に与えた予測勝率の平均」vs「実際の勝率」を比較する。
  //
  // 集計単位: 艇（boat）× レース
  //   - 推定: boatProbs[boat] = その艇の final_prob（モデル予測勝率）
  //   - 実績: actualResult の1着枠番が boat と一致するか（0 or 1）
  //
  // これにより「1コースをモデルが過小評価しているか」が正確にわかる。
  // ══════════════════════════════════════════════════════════════════
  function calcCalibrationByCourse(results) {
    const courses = [1, 2, 3, 4, 5, 6];

    // 各コース（枠番）ごとに全レースの boatProbs を展開して集計
    return courses.map(course => {
      let sumEst   = 0;  // 予測勝率の合計
      let sumAct   = 0;  // 実際に勝った回数
      let count    = 0;  // boatProbs にデータがあった艇×レース数

      results.forEach(r => {
        const bp = r.boatProbs;
        if (!bp || bp[course] == null) return; // このレースにデータなし

        const est = bp[course]; // モデルのこの枠番の予測勝率
        const won = (() => {
          if (!r.actualResult) return null;
          const first = parseInt((r.actualResult + '').split(/[-－−]/)[0]);
          return first === course ? 1 : 0;
        })();
        if (won === null) return;

        sumEst += est;
        sumAct += won;
        count++;
      });

      const estAvg = count > 0 ? sumEst / count : null; // 平均予測勝率
      const actual = count > 0 ? sumAct / count : null; // 実際の勝率

      return { course, count, estAvg, actual };
    });
  }

  // コース別勝率キャリブレーション HTML生成
  function buildCoursCalibHTML(courseStats, totalAll) {
    const maxBar = 100; // px（バーの最大幅px）
    const maxProb = 0.7; // バーのスケール最大値（70%で満幅）
    const courseBg   = ['','#d8d8d8','#333','#e33','#36c','#fa0','#2a9'];
    const courseText = ['','#333','#fff','#fff','#fff','#333','#fff'];

    const rows = courseStats.map(s => {
      if (s.count === 0) {
        return `
          <tr style="border-bottom:1px solid var(--border)">
            <td style="padding:4px 6px;white-space:nowrap">
              <span style="display:inline-flex;align-items:center;justify-content:center;width:20px;height:20px;border-radius:50%;background:${courseBg[s.course]};color:${courseText[s.course]};font-size:10px;font-weight:700">${s.course}</span>
            </td>
            <td colspan="4" style="padding:4px 6px;font-size:10px;color:var(--text3);text-align:center">—</td>
          </tr>`;
      }

      const actPct  = s.actual  != null ? (s.actual  * 100).toFixed(1) + '%' : '—';
      const estPct  = s.estAvg  != null ? (s.estAvg  * 100).toFixed(1) + '%' : '—';
      const actWidth = s.actual  != null ? Math.round(Math.min(s.actual  / maxProb, 1) * maxBar) : 0;
      const estWidth = s.estAvg  != null ? Math.round(Math.min(s.estAvg  / maxProb, 1) * maxBar) : 0;
      const diff    = (s.actual != null && s.estAvg != null) ? s.actual - s.estAvg : null;
      const diffStr = diff != null
        ? (diff >= 0 ? '+' : '') + (diff * 100).toFixed(1) + '%'
        : '—';
      const diffColor = diff == null           ? 'var(--text3)'
                      : Math.abs(diff) <= 0.03  ? 'var(--green)'
                      : Math.abs(diff) <= 0.07  ? 'var(--orange)'
                      : 'var(--red,#e05)';
      const lowN = s.count < 50;
      // 実績 > 推定なら過小評価（緑）、実績 < 推定なら過大評価（橙）
      const barColor = (diff == null || Math.abs(diff) < 0.01) ? 'var(--green)'
                     : diff > 0 ? 'var(--green)' : 'var(--orange)';

      return `
        <tr style="border-bottom:1px solid var(--border)">
          <td style="padding:4px 6px;white-space:nowrap">
            <span style="display:inline-flex;align-items:center;justify-content:center;width:20px;height:20px;border-radius:50%;background:${courseBg[s.course]};color:${courseText[s.course]};font-size:10px;font-weight:700">${s.course}</span>
            <span style="font-size:9px;color:var(--text3);margin-left:2px">${s.count}R</span>
          </td>
          <td style="padding:4px 6px;min-width:${maxBar}px">
            <div style="position:relative;height:14px;background:var(--bg2);border-radius:2px;overflow:hidden">
              <div style="position:absolute;left:0;top:0;height:100%;width:${estWidth}px;background:var(--border);border-radius:2px;opacity:0.7"></div>
              <div style="position:absolute;left:0;top:0;height:100%;width:${actWidth}px;background:${barColor};border-radius:2px;opacity:0.85"></div>
            </div>
          </td>
          <td style="padding:4px 6px;text-align:right;font-size:10px;color:var(--text3)">${estPct}</td>
          <td style="padding:4px 6px;text-align:right;font-size:11px;font-weight:700;color:var(--text)">${actPct}${lowN ? '<span style="font-size:9px;color:var(--text3)">*</span>' : ''}</td>
          <td style="padding:4px 6px;text-align:right;font-size:10px;font-weight:700;color:${diffColor}">${diffStr}</td>
        </tr>`;
    }).join('');

    return `
      <div style="background:var(--bg3);border-radius:var(--radius-sm);padding:12px;border:1px solid var(--border)">
        <div style="font-size:10px;font-weight:700;color:var(--text3);text-align:center;margin-bottom:2px">🚤 コース別 勝率キャリブレーション</div>
        <div style="font-size:10px;color:var(--text3);text-align:center;margin-bottom:8px">枠番別 予測勝率 vs 実際の勝率（計${totalAll}件）</div>
        <div style="overflow-x:auto">
          <table style="width:100%;border-collapse:collapse">
            <thead>
              <tr style="border-bottom:1px solid var(--border)">
                <th style="padding:3px 6px;text-align:left;font-size:9px;color:var(--text3);font-weight:500">枠</th>
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
          灰バー=推定勝率、色バー=実勝率　緑=過小評価、橙=過大評価　* N&lt;50の参考値
        </div>
      </div>`;
  }

  // ══════════════════════════════════════════════════════════════════
  // 30〜40%帯 過大評価 内訳調査パネル（管理者専用）
  // ──────────────────────────────────────────────────────────────────
  function buildOverestimateAnalysisHTML(results) {
    // 30〜40%帯のレースだけ抽出
    const band = results.filter(r => r.hitProbEst != null && r.hitProbEst >= 0.30 && r.hitProbEst < 0.40);
    if (band.length === 0) return '';

    // ── 会場別集計 ──
    const venueMap = {};
    band.forEach(r => {
      const v = r.venue || '不明';
      if (!venueMap[v]) venueMap[v] = { total: 0, hits: 0 };
      venueMap[v].total++;
      if (r.isHit) venueMap[v].hits++;
    });
    const venueRows = Object.entries(venueMap)
      .map(([v, s]) => ({ venue: v, ...s, actual: s.hits / s.total }))
      .sort((a, b) => a.actual - b.actual); // 的中率低い順

    // ── レース番号別集計 ──
    const rnoMap = {};
    band.forEach(r => {
      const rno = r.rno != null ? `${r.rno}R` : '不明';
      if (!rnoMap[rno]) rnoMap[rno] = { total: 0, hits: 0 };
      rnoMap[rno].total++;
      if (r.isHit) rnoMap[rno].hits++;
    });
    const rnoRows = Object.entries(rnoMap)
      .map(([rno, s]) => ({ rno, ...s, actual: s.hits / s.total }))
      .sort((a, b) => {
        const na = parseInt(a.rno); const nb = parseInt(b.rno);
        return na - nb;
      });

    // ── EV帯別集計（synth × hitProbEst）──
    const evMap = { '〜0.9': { total:0,hits:0 }, '0.9〜1.0': { total:0,hits:0 }, '1.0〜1.1': { total:0,hits:0 }, '1.1〜1.3': { total:0,hits:0 }, '1.3〜': { total:0,hits:0 } };
    band.forEach(r => {
      const ev = r.ev;
      if (ev == null) return;
      const key = ev < 0.9 ? '〜0.9' : ev < 1.0 ? '0.9〜1.0' : ev < 1.1 ? '1.0〜1.1' : ev < 1.3 ? '1.1〜1.3' : '1.3〜';
      evMap[key].total++;
      if (r.isHit) evMap[key].hits++;
    });

    const totalBand = band.length;
    const hitsBand  = band.filter(r => r.isHit).length;
    const actBand   = hitsBand / totalBand;

    // ── 会場テーブル HTML ──
    const vHtml = venueRows.map(s => {
      const pct = (s.actual * 100).toFixed(0) + '%';
      const color = s.actual < 0.25 ? 'var(--red,#e05)' : s.actual < 0.35 ? 'var(--orange)' : 'var(--green)';
      return `<tr style="border-bottom:1px solid var(--border)">
        <td style="padding:3px 5px;font-size:10px">${s.venue}</td>
        <td style="padding:3px 5px;font-size:10px;text-align:right;color:var(--text3)">${s.total}件</td>
        <td style="padding:3px 5px;font-size:10px;text-align:right;font-weight:700;color:${color}">${pct}</td>
      </tr>`;
    }).join('');

    // ── レース番号テーブル HTML ──
    const rHtml = rnoRows.map(s => {
      const pct = (s.actual * 100).toFixed(0) + '%';
      const color = s.actual < 0.25 ? 'var(--red,#e05)' : s.actual < 0.35 ? 'var(--orange)' : 'var(--green)';
      return `<tr style="border-bottom:1px solid var(--border)">
        <td style="padding:3px 5px;font-size:10px">${s.rno}</td>
        <td style="padding:3px 5px;font-size:10px;text-align:right;color:var(--text3)">${s.total}件</td>
        <td style="padding:3px 5px;font-size:10px;text-align:right;font-weight:700;color:${color}">${pct}</td>
      </tr>`;
    }).join('');

    // ── EV帯テーブル HTML ──
    const eHtml = Object.entries(evMap).map(([key, s]) => {
      if (s.total === 0) return `<tr style="border-bottom:1px solid var(--border)">
        <td style="padding:3px 5px;font-size:10px">EV${key}</td>
        <td colspan="2" style="padding:3px 5px;font-size:10px;text-align:center;color:var(--text3)">—</td>
      </tr>`;
      const pct = (s.hits / s.total * 100).toFixed(0) + '%';
      const color = (s.hits/s.total) < 0.25 ? 'var(--red,#e05)' : (s.hits/s.total) < 0.35 ? 'var(--orange)' : 'var(--green)';
      return `<tr style="border-bottom:1px solid var(--border)">
        <td style="padding:3px 5px;font-size:10px">EV${key}</td>
        <td style="padding:3px 5px;font-size:10px;text-align:right;color:var(--text3)">${s.total}件</td>
        <td style="padding:3px 5px;font-size:10px;text-align:right;font-weight:700;color:${color}">${pct}</td>
      </tr>`;
    }).join('');

    const thStyle = `padding:3px 5px;text-align:left;font-size:9px;color:var(--text3);font-weight:500;border-bottom:1px solid var(--border)`;
    const mkTable = (title, rows) => `
      <div>
        <div style="font-size:10px;font-weight:700;color:var(--text3);margin-bottom:4px">${title}</div>
        <table style="width:100%;border-collapse:collapse">
          <thead><tr>
            <th style="${thStyle}">区分</th>
            <th style="${thStyle};text-align:right">件数</th>
            <th style="${thStyle};text-align:right">実績</th>
          </tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;

    return `
      <div class="admin-only" style="margin-top:8px">
        <div style="background:var(--bg3);border-radius:var(--radius-sm);padding:12px;border:1px solid var(--orange,#f80)">
          <div style="font-size:10px;font-weight:700;color:var(--orange,#f80);text-align:center;margin-bottom:2px">
            🔍 30〜40%帯 過大評価 内訳調査
          </div>
          <div style="font-size:10px;color:var(--text3);text-align:center;margin-bottom:8px">
            推定30〜40%の${totalBand}件 → 実績的中率 <strong style="color:${actBand < 0.30 ? 'var(--red,#e05)' : 'var(--orange)'}">${(actBand*100).toFixed(1)}%</strong>（目標35%）
          </div>
          <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px">
            ${mkTable('会場別', vHtml)}
            ${mkTable('レース番号別', rHtml)}
            ${mkTable('EV帯別', eHtml)}
          </div>
        </div>
      </div>`;
  }

  // ══════════════════════════════════════════════════════════════════
  // 2着・3着 データvs買い目 切り分け診断（管理者専用）
  // ──────────────────────────────────────────────────────────────────
  // 「予測が機能していない」原因を切り分ける：
  //   データが悪い → 1位予測と2位予測の的中率がほぼ同率（識別力なし）
  //   買い目が悪い → 1位予測の的中率が低く、かつ2位以下に偏っている
  // ──────────────────────────────────────────────────────────────────
  function buildDiagnosisHTML(results) {
    const valid2 = results.filter(r => r.actual2nd != null && r.pred2ndRank != null);
    const valid3 = results.filter(r => r.actual3rd != null && r.pred3rdRank != null);
    if (valid2.length === 0 && valid3.length === 0) return '';

    // ── 予測順位分布（2着・3着）──
    function rankDist(arr, rankField) {
      const dist = {};
      arr.forEach(r => {
        const k = r[rankField] <= 4 ? r[rankField] : 5; // 5位以下まとめ
        dist[k] = (dist[k] ?? 0) + 1;
      });
      return dist;
    }
    const dist2 = rankDist(valid2, 'pred2ndRank');
    const dist3 = rankDist(valid3, 'pred3rdRank');
    const total2 = valid2.length;
    const total3 = valid3.length;

    // ── 識別力スコア（1位と2位の差）──
    // 差が大きいほど予測が機能している
    // 差が小さい（≤5%）→ データが悪い可能性大
    const r2_1 = (dist2[1] ?? 0) / total2;
    const r2_2 = (dist2[2] ?? 0) / total2;
    const r3_1 = (dist3[1] ?? 0) / total3;
    const r3_2 = (dist3[2] ?? 0) / total3;
    const disc2 = r2_1 - r2_2; // 識別力（2着）
    const disc3 = r3_1 - r3_2; // 識別力（3着）

    // ── 診断判定 ──
    function diagnose(disc, rank1, name) {
      if (disc >= 0.08) return { verdict: `✅ ${name}予測は機能している`, color: 'var(--green)',   detail: `1位と2位に${(disc*100).toFixed(0)}%差あり` };
      if (disc >= 0.03) return { verdict: `🟡 ${name}予測は弱い識別力`,   color: 'var(--orange)', detail: `1位と2位の差が${(disc*100).toFixed(0)}%のみ` };
      return                   { verdict: `🔴 ${name}予測は機能していない`, color: 'var(--red,#e05)', detail: `1位と2位がほぼ同率 → データ品質を疑う` };
    }
    const diag2 = diagnose(disc2, r2_1, '2着');
    const diag3 = diagnose(disc3, r3_1, '3着');

    // ── 1着コース別の2着1位的中率 ──
    // 逃げ（1着=1枠）とそれ以外で分けて見る
    function courseGroup(r) {
      if (!r.actualResult) return null;
      const first = parseInt((r.actualResult + '').split(/[-－−]/)[0]);
      return first === 1 ? '1コース(逃げ系)' : `${first}コース`;
    }
    const byWinner2 = {};
    valid2.forEach(r => {
      const g = courseGroup(r);
      if (!g) return;
      if (!byWinner2[g]) byWinner2[g] = { total: 0, rank1: 0 };
      byWinner2[g].total++;
      if (r.pred2ndRank === 1) byWinner2[g].rank1++;
    });
    const courseRows2 = Object.entries(byWinner2)
      .sort((a, b) => b[1].total - a[1].total)
      .slice(0, 6)
      .map(([g, s]) => {
        const rate = s.rank1 / s.total;
        const color = rate >= 0.40 ? 'var(--green)' : rate >= 0.28 ? 'var(--orange)' : 'var(--red,#e05)';
        return `<tr style="border-bottom:1px solid var(--border)">
          <td style="padding:3px 5px;font-size:10px">${g}</td>
          <td style="padding:3px 5px;font-size:10px;text-align:right;color:var(--text3)">${s.total}件</td>
          <td style="padding:3px 5px;font-size:10px;text-align:right;font-weight:700;color:${color}">${(rate*100).toFixed(0)}%</td>
        </tr>`;
      }).join('');

    // ── レース番号別の2着1位的中率 ──
    const byRno2 = {};
    valid2.forEach(r => {
      const g = r.rno != null ? `${r.rno}R` : null;
      if (!g) return;
      if (!byRno2[g]) byRno2[g] = { total: 0, rank1: 0, rno: r.rno };
      byRno2[g].total++;
      if (r.pred2ndRank === 1) byRno2[g].rank1++;
    });
    const rnoRows2 = Object.entries(byRno2)
      .sort((a, b) => a[1].rno - b[1].rno)
      .map(([g, s]) => {
        const rate = s.rank1 / s.total;
        const color = rate >= 0.40 ? 'var(--green)' : rate >= 0.28 ? 'var(--orange)' : 'var(--red,#e05)';
        return `<tr style="border-bottom:1px solid var(--border)">
          <td style="padding:3px 5px;font-size:10px">${g}</td>
          <td style="padding:3px 5px;font-size:10px;text-align:right;color:var(--text3)">${s.total}件</td>
          <td style="padding:3px 5px;font-size:10px;text-align:right;font-weight:700;color:${color}">${(rate*100).toFixed(0)}%</td>
        </tr>`;
      }).join('');

    // ── 予測順位分布バー ──
    function distBars(dist, total, maxRank) {
      return Array.from({ length: maxRank }, (_, i) => i + 1).map(rank => {
        const label = rank === maxRank ? `${rank}位以下` : `${rank}位`;
        const cnt   = dist[rank] ?? 0;
        const rate  = cnt / total;
        const w     = Math.round(rate * 100);
        const color = rank === 1 ? 'var(--green)' : rank === 2 ? 'var(--orange)' : 'var(--text3)';
        return `<div style="display:flex;align-items:center;gap:6px;margin-bottom:3px">
          <span style="font-size:9px;color:var(--text3);width:36px;flex-shrink:0">${label}</span>
          <div style="flex:1;height:10px;background:var(--bg2);border-radius:2px;overflow:hidden">
            <div style="height:100%;width:${w}%;background:${color};opacity:0.8;border-radius:2px"></div>
          </div>
          <span style="font-size:9px;font-weight:700;color:${color};width:28px;text-align:right">${(rate*100).toFixed(0)}%</span>
        </div>`;
      }).join('');
    }

    const thStyle = `padding:3px 5px;text-align:left;font-size:9px;color:var(--text3);font-weight:500;border-bottom:1px solid var(--border)`;

    return `
      <div class="admin-only" style="margin-top:8px">
        <div style="background:var(--bg3);border-radius:var(--radius-sm);padding:12px;border:1px solid var(--border)">
          <div style="font-size:10px;font-weight:700;color:var(--text3);text-align:center;margin-bottom:8px">
            🔬 2着・3着 データvs買い目 切り分け診断
          </div>

          <!-- 診断サマリー -->
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:10px">
            <div style="background:var(--bg2);border-radius:4px;padding:8px;border-left:3px solid ${diag2.color}">
              <div style="font-size:10px;font-weight:700;color:${diag2.color};margin-bottom:2px">${diag2.verdict}</div>
              <div style="font-size:9px;color:var(--text3)">${diag2.detail}</div>
            </div>
            <div style="background:var(--bg2);border-radius:4px;padding:8px;border-left:3px solid ${diag3.color}">
              <div style="font-size:10px;font-weight:700;color:${diag3.color};margin-bottom:2px">${diag3.verdict}</div>
              <div style="font-size:9px;color:var(--text3)">${diag3.detail}</div>
            </div>
          </div>

          <!-- 予測順位分布 -->
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px">
            <div>
              <div style="font-size:9px;font-weight:700;color:var(--text3);margin-bottom:4px">2着 予測順位分布（${total2}件）</div>
              ${distBars(dist2, total2, 5)}
            </div>
            <div>
              <div style="font-size:9px;font-weight:700;color:var(--text3);margin-bottom:4px">3着 予測順位分布（${total3}件）</div>
              ${distBars(dist3, total3, 5)}
            </div>
          </div>

          <!-- 1着コース別・レース番号別 -->
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
            <div>
              <div style="font-size:9px;font-weight:700;color:var(--text3);margin-bottom:4px">1着コース別 2着1位的中率</div>
              <table style="width:100%;border-collapse:collapse">
                <thead><tr>
                  <th style="${thStyle}">1着</th>
                  <th style="${thStyle};text-align:right">件数</th>
                  <th style="${thStyle};text-align:right">的中率</th>
                </tr></thead>
                <tbody>${courseRows2}</tbody>
              </table>
            </div>
            <div>
              <div style="font-size:9px;font-weight:700;color:var(--text3);margin-bottom:4px">レース番号別 2着1位的中率</div>
              <table style="width:100%;border-collapse:collapse">
                <thead><tr>
                  <th style="${thStyle}">R</th>
                  <th style="${thStyle};text-align:right">件数</th>
                  <th style="${thStyle};text-align:right">的中率</th>
                </tr></thead>
                <tbody>${rnoRows2}</tbody>
              </table>
            </div>
          </div>

          <div style="font-size:9px;color:var(--text3);margin-top:6px">
            識別力=1位と2位の的中率の差。差が小さい→データ品質の問題。差が大きく1位が低い→買い目ロジックの問題。
          </div>
        </div>
      </div>`;
  }

<<<<<<< HEAD
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
  // 関数は常に定義する。admin でない場合は中でスキップするだけ。
  window._renderCalibrationPanel = function (allResultsScenAll) {
    // 診断ログ: _isAdmin チェックより前に出力し、admin 未設定でも件数が確認できる
    // console.debug は Chrome デフォルトで非表示のため console.log に変更
    const _diagAll   = (allResultsScenAll || []).length;
    const _diagValid = (allResultsScenAll || []).filter(r => r.hitProbEst != null).length;
    console.log('[calibration] allResultsScenAll:', _diagAll, '件 / hitProbEst有効:', _diagValid, '件');

    // 呼び出し時点で再判定（defer読み込みのタイミング問題を回避）
    if (!document.body.classList.contains('admin-mode')) return;
    try {
      const container = _ensureContainer();
      const all       = allResultsScenAll || [];
      const totalAll  = all.length;
      const totalValid = _diagValid;

      // 修正: allResultsScenAll が [] のまま呼ばれたとき（非同期計算完了前）は
      // 「集計中」表示にしてデータ不足と区別する
      if (totalAll === 0) {
        container.innerHTML = `
          <div class="ai-stats-card" style="margin-bottom:0.6rem">
            <div style="display:grid;grid-template-columns:1fr;gap:10px">
              <div style="background:var(--bg3);border-radius:var(--radius-sm);padding:12px;border:1px solid var(--border)">
                <div style="font-size:10px;font-weight:700;color:var(--text3);text-align:center;margin-bottom:4px">📐 確率キャリブレーション</div>
                <div style="color:var(--text3);font-size:11px;text-align:center;padding:0.3rem 0">集計中...</div>
              </div>
            </div>
          </div>`;
        return;
      }

      // ―― 生データで集計（補正前）→ 補正テーブル更新 ――
      const binStatsRaw = calcCalibration(all);
      if (typeof updateCalibPoints === 'function') updateCalibPoints(binStatsRaw);

      // ―― 補正後の hitProbEst で再集計してパネルに表示 ――
      let binStats = binStatsRaw;
      if (typeof calibrateProb === 'function') {
        const allCorrected = all.map(r => r.hitProbEst != null
          ? Object.assign({}, r, { hitProbEst: calibrateProb(r.hitProbEst) })
          : r
        );
        binStats = calcCalibration(allCorrected);
      }

      const calError   = calcCalibrationError(binStats);
      const violations = countMonotonicViolations(binStats);
      const p2stats    = calcPlace2Calibration(all);
      const p3stats    = calcPlace3Calibration(all);
      // コース別キャリブレーション
      const courseStats = calcCalibrationByCourse(all);

      container.innerHTML = `
        <div class="ai-stats-card" style="margin-bottom:0.6rem">
          <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:10px">
            ${buildCalibrationHTML(binStats, calError, violations, totalValid)}
            ${buildPlace2CalibHTML(p2stats, p3stats)}
            <div class="admin-only">${buildCoursCalibHTML(courseStats, all.length)}</div>
          </div>
          ${buildOverestimateAnalysisHTML(all)}
          ${buildDiagnosisHTML(all)}
        </div>`;
    } catch (e) {
      console.warn('[calibration] render error:', e);
    }
  };

})();
=======
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
  // 関数は常に定義する。admin でない場合は中でスキップするだけ。
  window._renderCalibrationPanel = function (allResultsScenAll) {
    // 診断ログ: _isAdmin チェックより前に出力し、admin 未設定でも件数が確認できる
    // console.debug は Chrome デフォルトで非表示のため console.log に変更
    const _diagAll   = (allResultsScenAll || []).length;
    const _diagValid = (allResultsScenAll || []).filter(r => r.hitProbEst != null).length;
    console.log('[calibration] allResultsScenAll:', _diagAll, '件 / hitProbEst有効:', _diagValid, '件');

    // 呼び出し時点で再判定（defer読み込みのタイミング問題を回避）
    if (!document.body.classList.contains('admin-mode')) return;
    try {
      const container = _ensureContainer();
      const all       = allResultsScenAll || [];
      const totalAll  = all.length;
      const totalValid = _diagValid;

      // 修正: allResultsScenAll が [] のまま呼ばれたとき（非同期計算完了前）は
      // 「集計中」表示にしてデータ不足と区別する
      if (totalAll === 0) {
        container.innerHTML = `
          <div class="ai-stats-card" style="margin-bottom:0.6rem">
            <div style="display:grid;grid-template-columns:1fr;gap:10px">
              <div style="background:var(--bg3);border-radius:var(--radius-sm);padding:12px;border:1px solid var(--border)">
                <div style="font-size:10px;font-weight:700;color:var(--text3);text-align:center;margin-bottom:4px">📐 確率キャリブレーション</div>
                <div style="color:var(--text3);font-size:11px;text-align:center;padding:0.3rem 0">集計中...</div>
              </div>
            </div>
          </div>`;
        return;
      }

      // ―― 生データで集計（補正前）→ 補正テーブル更新 ――
      const binStatsRaw = calcCalibration(all);
      if (typeof updateCalibPoints === 'function') updateCalibPoints(binStatsRaw);

      // ―― 補正後の hitProbEst で再集計してパネルに表示 ――
      let binStats = binStatsRaw;
      if (typeof calibrateProb === 'function') {
        const allCorrected = all.map(r => r.hitProbEst != null
          ? Object.assign({}, r, { hitProbEst: calibrateProb(r.hitProbEst) })
          : r
        );
        binStats = calcCalibration(allCorrected);
      }

      const calError   = calcCalibrationError(binStats);
      const violations = countMonotonicViolations(binStats);
      const p2stats    = calcPlace2Calibration(all);
      const p3stats    = calcPlace3Calibration(all);
      // コース別キャリブレーション
      const courseStats = calcCalibrationByCourse(all);

      container.innerHTML = `
        <div class="ai-stats-card" style="margin-bottom:0.6rem">
          <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:10px">
            ${buildCalibrationHTML(binStats, calError, violations, totalValid)}
            ${buildPlace2CalibHTML(p2stats, p3stats)}
            <div class="admin-only">${buildCoursCalibHTML(courseStats, all.length)}</div>
          </div>
          ${buildOverestimateAnalysisHTML(all)}
          ${buildDiagnosisHTML(all)}
        </div>`;
    } catch (e) {
      console.warn('[calibration] render error:', e);
    }
  };

})();
>>>>>>> 71977d02f21aaedfa25a5b188fdbd7816e489bfd
