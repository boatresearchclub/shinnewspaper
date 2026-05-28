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

  // admin 判定（URLに ?admin or #admin が含まれる場合のみパネルを描画）
  // ※ 関数定義自体は必ず行う（top_stats.js から呼ばれるため）
  const _isAdmin = location.search.includes('admin') || location.hash.includes('admin');

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

    if (!_isAdmin) return; // adminパラメータがなければ描画しない（ログは上で出力済み）
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

      const binStats   = calcCalibration(all);
      // キャリブレーション補正テーブルを自動更新（computeScenCombosWithEV.js と連携）
      if (typeof updateCalibPoints === 'function') updateCalibPoints(binStats);
      const calError   = calcCalibrationError(binStats);
      const violations = countMonotonicViolations(binStats);
      const p2stats    = calcPlace2Calibration(all);
      const p3stats    = calcPlace3Calibration(all);
      container.innerHTML = `
        <div class="ai-stats-card" style="margin-bottom:0.6rem">
          <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:10px">
            ${buildCalibrationHTML(binStats, calError, violations, totalValid)}
            ${buildPlace2CalibHTML(p2stats, p3stats)}
          </div>
        </div>`;
    } catch (e) {
      console.warn('[calibration] render error:', e);
    }
  };

})();
