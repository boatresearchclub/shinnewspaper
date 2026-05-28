# -*- coding: utf-8 -*-
"""
load_race_patch.py
──────────────────────────────────────────────────────────────
load_race.py に追加・変更する箇所を差分形式でまとめたパッチ。
コピペ場所を「★ PATCH」コメントで明示してある。

変更点は3箇所のみ:
  [A] インポート追加          (ファイル先頭 import ブロック末尾)
  [B] venue_c1_win_rate 補正 (calc_race_indices 呼び出し直前)
  [C] buy_list 補正適用      (bet_suggestions 確定直後・EV計算の前)
──────────────────────────────────────────────────────────────
"""

# ════════════════════════════════════════════════════════════
# [A] インポート追加
#     load_race.py の既存 import ブロックの末尾（lr_log import の直後あたり）に追加
# ════════════════════════════════════════════════════════════

# ★ PATCH [A] ─ ここから追加 ─────────────────────────────
try:
    from lr_backtest import (
        apply_correction_to_buy_list,
        get_venue_c1_rate,
        get_venue_kimete,
        load_correction_params,
    )
    _CORRECTION_AVAILABLE = True
    _correction_params = load_correction_params()  # 起動時1回だけ読み込み
    if _correction_params:
        print('[OK] correction_params.json 読込完了（買い目補正有効）')
    else:
        print('[!]  correction_params.json が見つかりません。補正なしで動作します。')
        print('     python lr_backtest.py --all --results <CSV> --payouts <CSV> で生成してください。')
except ImportError:
    _CORRECTION_AVAILABLE = False
    _correction_params = {}
    print('[!]  lr_backtest.py が見つかりません。補正なしで動作します。')
# ★ PATCH [A] ─ ここまで ────────────────────────────────


# ════════════════════════════════════════════════════════════
# [B] venue_c1_win_rate 補正
#     load_race.py の calc_race_indices() 呼び出し直前（約810行目）に追加
#     既存コード: results, slit, venue_stats, ... = calc_race_indices(...)
# ════════════════════════════════════════════════════════════

# ★ PATCH [B] ─ calc_race_indices 呼び出しの直前に追加 ────
# 補正パラメータから会場の実績 c1_win_rate を取得して
# race_judgment の venue_c1_win_rate を上書きする。
# これにより _calc_3rentan_probs_v2 が正確な会場特性を参照できる。
if _CORRECTION_AVAILABLE and _correction_params:
    _c1_rate_corrected = get_venue_c1_rate(venue, _correction_params)
    # calc_race_indices に渡す前に race_judgment の初期値として設定
    # （関数内で上書きされない場合のフォールバック用）
    _venue_c1_override = _c1_rate_corrected
else:
    _venue_c1_override = None
# ★ PATCH [B] ─ ここまで ────────────────────────────────

# 既存の calc_race_indices 呼び出しはそのまま（変更不要）
# results, slit, venue_stats, frame_2nd, race_judgment, bet_suggestions = calc_race_indices(
#     venue, race_no, players, ...
# )

# ── calc_race_indices 呼び出し直後に venue_c1_win_rate を補正値で上書き ──
# ★ PATCH [B2] ─ calc_race_indices の戻り値受け取り直後に追加 ──────────
if _venue_c1_override is not None:
    race_judgment['venue_c1_win_rate'] = _venue_c1_override
# ★ PATCH [B2] ─ ここまで ───────────────────────────────────────────


# ════════════════════════════════════════════════════════════
# [C] buy_list 補正適用
#     load_race.py の「⑥ 買い目再生成」直後（約950行目）
#     既存コード: bet_suggestions = _build_scenarios_new(...) の直後
#     EV計算（_calc_3rentan_probs_v2）の直前に挿入
# ════════════════════════════════════════════════════════════

# ★ PATCH [C] ─ bet_suggestions 確定直後・EV計算前に追加 ───────────────
if _CORRECTION_AVAILABLE and _correction_params:
    _rank_for_correction = race_judgment.get('rank', bet_suggestions.get('rank', 'C'))
    _mismatch            = race_judgment.get('honmei_prob_mismatch', False)
    _raw_buy_list        = bet_suggestions.get('buy_list', [])

    _corrected_buy_list = apply_correction_to_buy_list(
        buy_list             = list(_raw_buy_list),
        venue                = venue,
        rank                 = _rank_for_correction,
        honmei_prob_mismatch = _mismatch,
        params               = _correction_params,
    )

    if _corrected_buy_list != _raw_buy_list:
        _removed = [b for b in _raw_buy_list if b not in _corrected_buy_list]
        _added   = [b for b in _corrected_buy_list if b not in _raw_buy_list]
        print(f"  [補正] buy_list: {len(_raw_buy_list)}点 → {len(_corrected_buy_list)}点", end="")
        if _removed: print(f"  削除={_removed}", end="")
        if _added:   print(f"  追加={_added}", end="")
        if _mismatch: print(f"  ※honmei_prob_mismatch", end="")
        print()

    bet_suggestions['buy_list']    = _corrected_buy_list
    bet_suggestions['point_count'] = len(_corrected_buy_list)
# ★ PATCH [C] ─ ここまで ────────────────────────────────


# ════════════════════════════════════════════════════════════
# 使い方まとめ
# ════════════════════════════════════════════════════════════
"""
【初回セットアップ】

  1. lr_backtest.py を scripts/ フォルダに配置

  2. 過去CSVからログに結果を自動記入 + 補正パラメータ生成:
       python scripts/lr_backtest.py --all \\
           --results data_csv/202603_results.csv \\
           --payouts data_csv/202603_payouts.csv

     → scripts/correction_params.json が生成される

  3. load_race.py に [A][B][C] の3パッチを適用

  4. 通常通り load_race.py を実行:
       python scripts/load_race.py --venue 大村

【定期更新（月次）】

  新しい結果CSVが揃ったら:
  python scripts/lr_backtest.py --all \\
      --results data_csv/202604_results.csv \\
      --payouts data_csv/202604_payouts.csv

  → correction_params.json が更新され、次回 load_race.py 起動時に自動反映

【補正内容の確認】

  python scripts/lr_backtest.py --analyze

  → rank別・会場別 ROI を表示
     買い目点数の動的調整がどう変わったか確認できる
"""
