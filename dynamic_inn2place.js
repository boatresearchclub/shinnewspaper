// dynamic_inn2place.js — 動的 inn_2place 補正モジュール
//
// 【設計方針】
//   既存コード（sample.js / top_stats.js）への変更は最小限。
//   _renderHistory30 の冒頭に1行追加するだけで動作する。
//
//     _applyDynamicInn2Place(allResultsScenAll); // ← これだけ追加
//
// 【何をするか】
//   過去30日の collectResultsForDateScen 結果（allResultsScenAll）から
//   会場別・1号艇1着時の2着枠番出現率を実績集計し、
//   MASTER_EXT.venue_stats[venue].inn_2place を動的値でブレンド更新する。
//
//   優先順位（既存コードの参照順と同一）:
//     ① DATA.inn_data.inn_2place  ← 当日レース表示時に使用（触らない）
//     ② MASTER_EXT.venue_stats[venue].inn_2place ← ここを動的更新
//
//   ① は個別レース表示時にのみ参照され、30日集計には使われない。
//   ② を更新することで calcScenarioData / calcPlace2Probs の両方に反映される。
//
// 【ブレンド式】
//   動的値 = 実績値(直近30日) × W_DYNAMIC + 静的マスタ × (1 - W_DYNAMIC)
//   W_DYNAMIC: サンプル数に応じて 0〜MAX_W_DYNAMIC に線形増加
//   MIN_SAMPLES: これ未満の会場は補正しない（静的マスタをそのまま使用）
//
// 【安全策】
//   - MASTER_EXT が null / venue_stats がない場合は何もしない
//   - サンプル不足会場（< MIN_SAMPLES）はスキップ
//   - 元の静的マスタを _inn2PlaceOriginal にバックアップ → リロードで復元
//   - 本モジュールは「表示・買い目生成」には影響しない
//     （当日レースは DATA.inn_data.inn_2place が優先されるため）
// ─────────────────────────────────────────────────────────────────────

(function () {

  // ── パラメータ ──
  const MIN_SAMPLES    = 20;   // 会場ごとの最低サンプル数（逃げ1号艇1着レース）
  const MAX_W_DYNAMIC  = 0.60; // 動的値の最大ウェイト（サンプル数が十分な場合）
  const SATURATE_AT    = 100;  // このサンプル数でウェイトが MAX_W_DYNAMIC に達する

  // 静的マスタのバックアップ（初回呼び出し時に保存）
  let _inn2PlaceOriginal = null;
  let _applied = false;

  // ── 公開関数 ──
  window._applyDynamicInn2Place = function (allResultsScenAll) {
    try {
      if (!MASTER_EXT || !MASTER_EXT.venue_stats) return;

      // 初回のみ静的マスタをディープコピーしてバックアップ
      if (!_inn2PlaceOriginal) {
        _inn2PlaceOriginal = {};
        Object.keys(MASTER_EXT.venue_stats).forEach(venue => {
          const orig = MASTER_EXT.venue_stats[venue]?.inn_2place;
          if (orig && typeof orig === 'object') {
            _inn2PlaceOriginal[venue] = { ...orig };
          }
        });
      }

      // ── 実績集計 ──
      // actualResult = "1-2-3" 形式
      // 「1号艇が1着（actualResult の先頭が '1'）」のレースのみ対象
      const venueStats = {}; // { venue: { '2': count, '3': count, ... }, _total: N }

      (allResultsScenAll || []).forEach(r => {
        if (!r.actualResult || !r.venue) return;
        const parts = r.actualResult.split('-');
        if (parts.length < 2) return;
        const first  = parts[0]; // 1着枠番
        const second = parts[1]; // 2着枠番
        if (first !== '1') return; // 1号艇1着のみ対象

        if (!venueStats[r.venue]) venueStats[r.venue] = { _total: 0 };
        venueStats[r.venue]._total++;
        venueStats[r.venue][second] = (venueStats[r.venue][second] || 0) + 1;
      });

      // ── ブレンド更新 ──
      Object.keys(venueStats).forEach(venue => {
        const stat   = venueStats[venue];
        const total  = stat._total;
        if (total < MIN_SAMPLES) return; // サンプル不足はスキップ

        // ウェイト: サンプル数に応じて線形増加、SATURATE_AT で上限
        const wDynamic = Math.min(MAX_W_DYNAMIC, (total / SATURATE_AT) * MAX_W_DYNAMIC);
        const wStatic  = 1 - wDynamic;

        // 静的マスタ（バックアップから参照）
        const staticBase = _inn2PlaceOriginal[venue] || {};

        // 実績から各枠番の出現率を計算
        const dynamicRates = {};
        ['2', '3', '4', '5', '6'].forEach(boat => {
          dynamicRates[boat] = (stat[boat] || 0) / total;
        });

        // ブレンド
        const blended = {};
        ['2', '3', '4', '5', '6'].forEach(boat => {
          const dyn  = dynamicRates[boat];
          const stat_val = staticBase[boat] ?? null;
          if (stat_val != null) {
            blended[boat] = dyn * wDynamic + stat_val * wStatic;
          } else {
            // 静的マスタにない枠番は動的値のみ（静的が0扱い）
            blended[boat] = dyn * wDynamic;
          }
        });

        // 正規化（合計を1に揃える）
        const blendedTotal = Object.values(blended).reduce((s, v) => s + v, 0) || 1;
        Object.keys(blended).forEach(k => { blended[k] = blended[k] / blendedTotal; });

        // MASTER_EXT に書き込み
        if (!MASTER_EXT.venue_stats[venue]) MASTER_EXT.venue_stats[venue] = {};
        MASTER_EXT.venue_stats[venue].inn_2place = blended;

        console.log(`[dynamic_inn2place] ${venue}: N=${total} wDyn=${(wDynamic*100).toFixed(0)}%`,
          Object.fromEntries(
            ['2','3','4','5','6'].map(b => [b+'着', (blended[b]*100).toFixed(1)+'%'])
          )
        );
      });

      _applied = true;
      console.log('[dynamic_inn2place] 適用完了:', Object.keys(venueStats).filter(v => venueStats[v]._total >= MIN_SAMPLES).length, '会場');

    } catch (e) {
      console.warn('[dynamic_inn2place] エラー:', e);
    }
  };

  // ── 当日レース用ブレンド関数 ──
  // selectRace() の冒頭に以下を1行追加するだけで動作する:
  //   if (typeof _blendInnDataInn2Place === 'function') _blendInnDataInn2Place();
  //
  // DATA.inn_data.inn_2place（当日個別データ）と
  // MASTER_EXT.venue_stats[venue].inn_2place（動的補正済み会場値）を
  // W_LIVE_BLEND の比率でブレンドして DATA.inn_data.inn_2place を上書きする。
  //
  // W_LIVE_BLEND: 動的補正値のウェイト（0=当日データのみ、1=動的補正のみ）
  // 当日データの信頼性が高いため控えめな値を推奨。

  const W_LIVE_BLEND = 0.25; // 動的補正値のウェイト（25%）

  window._blendInnDataInn2Place = function () {
    try {
      if (!DATA || !DATA.inn_data) return;
      if (!MASTER_EXT?.venue_stats?.[DATA.venue]?.inn_2place) return;

      const liveVal = DATA.inn_data.inn_2place;
      if (!liveVal || typeof liveVal !== 'object' || Array.isArray(liveVal)) return;
      if (Object.keys(liveVal).length === 0) return;

      const dynamicVal = MASTER_EXT.venue_stats[DATA.venue].inn_2place;

      const blended = {};
      ['2', '3', '4', '5', '6'].forEach(boat => {
        const live = liveVal[boat] ?? null;
        const dyn  = dynamicVal[boat] ?? null;
        if (live != null && dyn != null) {
          blended[boat] = live * (1 - W_LIVE_BLEND) + dyn * W_LIVE_BLEND;
        } else if (live != null) {
          blended[boat] = live;
        } else if (dyn != null) {
          blended[boat] = dyn * W_LIVE_BLEND;
        }
      });

      // 正規化
      const total = Object.values(blended).reduce((s, v) => s + v, 0) || 1;
      Object.keys(blended).forEach(k => { blended[k] = blended[k] / total; });

      DATA.inn_data.inn_2place = blended;

    } catch (e) {
      console.warn('[dynamic_inn2place] _blendInnDataInn2Place エラー:', e);
    }
  };

  // ── リセット関数（デバッグ用）──
  // 静的マスタに戻したいときは _resetDynamicInn2Place() をコンソールで実行
  window._resetDynamicInn2Place = function () {
    if (!_inn2PlaceOriginal || !MASTER_EXT?.venue_stats) return;
    Object.keys(_inn2PlaceOriginal).forEach(venue => {
      if (MASTER_EXT.venue_stats[venue]) {
        MASTER_EXT.venue_stats[venue].inn_2place = { ..._inn2PlaceOriginal[venue] };
      }
    });
    _applied = false;
    console.log('[dynamic_inn2place] 静的マスタにリセットしました');
  };

})();
