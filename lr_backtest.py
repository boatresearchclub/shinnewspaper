# -*- coding: utf-8 -*-
"""
lr_backtest_fixed.py  ― lr_backtest.py の修正版
==================================================
【修正④】fill_logs_from_csv() の着順Top3取得で '進入コース' を使っていたバグを修正。
  旧: tw = top3.pivot_table(... values='進入コース' ...)
  新: tw = top3.pivot_table(... values='艇番' ...)

  競艇では「艇番」＝枠番（1〜6の固定）であり、
  「進入コース」はスタート時のコース番号（枠番と異なる場合がある）。
  3連単の組み合わせは艇番で表記するため、艇番を使うのが正しい。

【その他の改善】
  ・analyze_and_export() の correction に grade 別統計を追加
  ・run_daily.py から --all で呼べるよう引数なし起動に対応
"""

import json, glob, pathlib, argparse, sys
from datetime import datetime

try:
    import pandas as pd
    import numpy as np
    _PANDAS_OK = True
except ImportError:
    _PANDAS_OK = False
    print("[!] pandas が見つかりません: pip install pandas")

# ── 定数（lr_backtest.py と同じ）──────────────────────────────────────────
VENUE_C1_RATE = {
    '芦屋':0.653,'大村':0.651,'児島':0.641,'下関':0.623,'徳山':0.620,
    '丸亀':0.608,'若松':0.605,'尼崎':0.601,'蒲郡':0.592,'唐津':0.590,
    '浜名湖':0.573,'津':0.569,'江戸川':0.561,'福岡':0.557,'宮島':0.556,
    '住之江':0.550,'常滑':0.524,'平和島':0.506,'三国':0.497,'びわこ':0.485,
    '多摩川':0.482,'桐生':0.440,'鳴門':0.417,'戸田':0.406,
}
RANK_PATTERNS = {
    'S': ['1-2-3','1-3-2','1-2-5','1-4-5','1-5-2','1-3-4','1-2-6','1-3-6'],
    'A': ['1-2-3','1-3-2','1-2-4','1-3-4','1-2-5','1-3-5','1-4-2','1-4-3'],
    'B': ['1-2-3','1-3-2','1-2-4','1-3-4','1-2-5','1-3-5','1-4-2','1-4-3','1-4-5','1-5-2'],
    'C': ['1-2-3','1-3-2','1-2-4','1-3-4','1-2-5','1-3-5','1-4-2','1-4-3',
          '1-4-5','1-5-2','1-5-3','1-6-2'],
    'D': [],
    'mismatch': ['1-2-3','1-3-2','1-2-4','1-3-4','1-2-5'],
}
MAKURI_VENUES  = {'宮島','江戸川','常滑','びわこ','多摩川','桐生','鳴門','戸田','福岡'}
MAKURI_EXTRA   = ['2-1-3','2-1-4','3-1-2','3-1-4']
RANK_ROI_ACTUAL = {'S':104.3, 'A':82.2, 'B':87.9, 'C':69.4, 'D':0.0}


# ════════════════════════════════════════════════════════════
# ① 予想ログへの結果自動記入（修正④: 進入コース→艇番）
# ════════════════════════════════════════════════════════════

def fill_logs_from_csv(results_csv: str, payouts_csv: str, logs_dir: str = None):
    """
    results_csv と payouts_csv を読み込み、
    logs/*.json の result_1st/result_2nd/result_3rd/hit/dividend を自動記入する。

    【修正④】
    着順Top3の pivot_table で values に '艇番' を使う（旧: '進入コース'）。
    '進入コース' は枠番（艇番）と一致しないケースがあるため誤った突合になる。
    """
    if not _PANDAS_OK:
        return

    logs_path = pathlib.Path(logs_dir) if logs_dir else pathlib.Path(__file__).parent.parent / "logs"
    log_files = sorted(logs_path.glob("*.json"))
    if not log_files:
        print(f"[!] ログファイルが見つかりません: {logs_path}")
        return

    r = pd.read_csv(results_csv, encoding='utf-8-sig')
    p = pd.read_csv(payouts_csv, encoding='utf-8-sig')

    p3 = p[p['券種'] == '３連単'].copy()
    p3['組み合わせ'] = p3['組み合わせ'].str.replace("'", "", regex=False).str.strip()
    p3['払戻金'] = pd.to_numeric(p3['払戻金'], errors='coerce')

    # ── 【修正④】'艇番' 列を使う（旧コード: values='進入コース'）──────────
    # 列名ゆれに対応: '艇番' がなければ '枠番' を試みる
    rank_col  = '着順'
    waku_col  = '艇番' if '艇番' in r.columns else ('枠番' if '枠番' in r.columns else None)

    if waku_col is None:
        print("[!] 結果CSVに '艇番' / '枠番' 列が見つかりません。突合をスキップします。")
        return

    top3 = r[r[rank_col].isin([1, 2, 3])].sort_values(['日付', '会場名', 'レース番号', rank_col])
    tw = top3.pivot_table(
        index=['日付', '会場名', 'レース番号'],
        columns=rank_col,
        values=waku_col,   # ← 修正箇所（旧: '進入コース'）
        aggfunc='first'
    ).reset_index()
    tw.columns = ['日付', '会場名', 'レース番号', '1着', '2着', '3着']
    tw = tw.dropna(subset=['1着', '2着', '3着'])
    tw['正解'] = tw[['1着', '2着', '3着']].astype(int).astype(str).apply('-'.join, axis=1)

    pay_map = p3.set_index(['日付', '会場名', 'レース番号', '組み合わせ'])['払戻金'].to_dict()

    filled = skipped = 0
    for log_file in log_files:
        try:
            with open(log_file, encoding='utf-8') as f:
                log_data = json.load(f)
        except Exception as e:
            print(f"[!] 読み込みエラー: {log_file.name} ({e})")
            continue

        venue    = log_data.get('venue', '')
        date_str = log_data.get('date', '')
        modified = False

        for entry in log_data.get('races', []):
            race_no = str(entry.get('race_no', ''))
            if entry.get('dividend') is not None:
                skipped += 1
                continue

            mask = (
                (tw['日付'] == date_str) &
                (tw['会場名'] == venue) &
                (tw['レース番号'].astype(str) == race_no)
            )
            row = tw[mask]
            if row.empty:
                continue

            ans = row.iloc[0]
            entry['result_1st'] = int(ans['1着'])
            entry['result_2nd'] = int(ans['2着'])
            entry['result_3rd'] = int(ans['3着'])

            buy_list = entry.get('buy_list', [])
            correct  = ans['正解']
            hit = any(str(b).replace(' ', '') == correct for b in buy_list)
            entry['hit'] = hit

            pay_key  = (date_str, venue, int(race_no), correct)
            dividend = pay_map.get(pay_key)
            entry['dividend'] = int(dividend) if dividend and not pd.isna(dividend) else 0

            modified = True
            filled += 1

        if modified:
            with open(log_file, 'w', encoding='utf-8') as f:
                json.dump(log_data, f, ensure_ascii=False, indent=2)

    print(f"[OK] 自動記入完了: {filled}R記入 / {skipped}R既記入済み")


# ════════════════════════════════════════════════════════════
# ② ROI集計 + 補正パラメータ算出（grade 別統計を追加）
# ════════════════════════════════════════════════════════════

def analyze_and_export(logs_dir: str = None, output_json: str = None):
    if not _PANDAS_OK:
        return

    logs_path = pathlib.Path(logs_dir) if logs_dir else pathlib.Path(__file__).parent.parent / "logs"
    log_files = sorted(logs_path.glob("*.json"))
    if not log_files:
        print(f"[!] ログファイルが見つかりません: {logs_path}")
        return

    records = []
    for log_file in log_files:
        try:
            with open(log_file, encoding='utf-8') as f:
                log_data = json.load(f)
        except Exception:
            continue
        venue    = log_data.get('venue', '')
        date_str = log_data.get('date', '')
        for entry in log_data.get('races', []):
            if entry.get('dividend') is None:
                continue
            records.append({
                'date':        date_str,
                'venue':       venue,
                'grade':       entry.get('grade', '一般'),
                'race_no':     entry.get('race_no'),
                'rank':        entry.get('rank', '-'),
                'score':       entry.get('score', 0),
                'strategy':    entry.get('strategy', ''),
                'buy_list':    entry.get('buy_list', []),
                'point_count': entry.get('point_count', 0),
                'hit':         entry.get('hit', False),
                'dividend':    entry.get('dividend', 0),
                'result_1st':  entry.get('result_1st'),
            })

    if not records:
        print("[!] 結果記入済みレースがありません。先に --fill を実行してください。")
        return

    df = pd.DataFrame(records)
    df['cost']   = df['point_count'] * 100
    df['payout'] = df.apply(lambda r: int(r['dividend']) if r['hit'] else 0, axis=1)

    print("=" * 60)
    print("  ROI バックテスト結果（予想ログ × 結果CSV 突合）")
    print("=" * 60)
    print(f"  対象レース数 : {len(df)}")
    hit_rate = df['hit'].mean()
    roi_val  = df['payout'].sum() / df['cost'].sum() if df['cost'].sum() > 0 else 0
    print(f"  的中率       : {hit_rate*100:.1f}%")
    print(f"  回収率       : {roi_val*100:.1f}%")

    rank_stats  = {}
    venue_stats = {}
    grade_stats = {}

    for rank, grp in df.groupby('rank'):
        r_roi = grp['payout'].sum() / grp['cost'].sum() if grp['cost'].sum() > 0 else 0
        r_hit = grp['hit'].mean()
        rank_stats[rank] = {'roi': round(r_roi, 4), 'hit_rate': round(r_hit, 4), 'n': len(grp)}

    for venue, grp in df.groupby('venue'):
        v_roi = grp['payout'].sum() / grp['cost'].sum() if grp['cost'].sum() > 0 else 0
        v_hit = grp['hit'].mean()
        venue_stats[venue] = {'roi': round(v_roi, 4), 'hit_rate': round(v_hit, 4), 'n': len(grp)}

    # グレード別統計（追加）
    for grade, grp in df.groupby('grade'):
        g_roi = grp['payout'].sum() / grp['cost'].sum() if grp['cost'].sum() > 0 else 0
        g_hit = grp['hit'].mean()
        grade_stats[grade] = {'roi': round(g_roi, 4), 'hit_rate': round(g_hit, 4), 'n': len(grp)}

    # 会場×グレード別統計（backtest_engine の venue_weight と整合させるため）
    df['venue_grade'] = df['venue'] + '_' + df['grade']
    venue_grade_stats = {}
    for vg, grp in df.groupby('venue_grade'):
        vg_roi = grp['payout'].sum() / grp['cost'].sum() if grp['cost'].sum() > 0 else 0
        vg_hit = grp['hit'].mean()
        venue_grade_stats[vg] = {'roi': round(vg_roi, 4), 'hit_rate': round(vg_hit, 4), 'n': len(grp)}

    correction = {
        'generated_at':      datetime.now().strftime('%Y-%m-%d %H:%M'),
        'venue_c1_rate':     VENUE_C1_RATE,
        'rank_patterns':     RANK_PATTERNS,
        'makuri_venues':     list(MAKURI_VENUES),
        'makuri_extra':      MAKURI_EXTRA,
        'rank_roi_actual':   RANK_ROI_ACTUAL,
        'log_rank_stats':    rank_stats,
        'log_venue_stats':   venue_stats,
        'log_grade_stats':   grade_stats,           # 追加
        'log_venue_grade_stats': venue_grade_stats, # 追加（backtest_engine と整合）
        'rank_n_override':   _calc_rank_n_override(rank_stats),
        'mismatch_max_bets': 5,
        'skip_if_mismatch_and_rank': ['C', 'D'],
    }

    out_path = pathlib.Path(output_json) if output_json else pathlib.Path(__file__).parent / "correction_params.json"
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(correction, f, ensure_ascii=False, indent=2)
    print(f"\n[OK] 補正パラメータ保存: {out_path}")
    return correction


def _calc_rank_n_override(rank_stats: dict) -> dict:
    base_n = {'S': 8, 'A': 8, 'B': 10, 'C': 12, 'D': 0}
    override = {}
    for rank, base in base_n.items():
        if rank not in rank_stats:
            override[rank] = base
            continue
        roi = rank_stats[rank]['roi']
        if roi < 0.70:
            override[rank] = max(base - 2, 3)
        elif roi > 1.00:
            override[rank] = min(base + 2, 15)
        else:
            override[rank] = base
    return override


# ════════════════════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="予想ログ × 結果CSV 自動突合（修正版）")
    parser.add_argument('--fill',     action='store_true')
    parser.add_argument('--analyze',  action='store_true')
    parser.add_argument('--all',      action='store_true')
    parser.add_argument('--results',  type=str, default=None)
    parser.add_argument('--payouts',  type=str, default=None)
    parser.add_argument('--logs',     type=str, default=None)
    parser.add_argument('--output',   type=str, default=None)
    args = parser.parse_args()

    if args.fill or args.all:
        if not args.results or not args.payouts:
            print("[NG] --results と --payouts を指定してください")
            return
        fill_logs_from_csv(args.results, args.payouts, args.logs)

    if args.analyze or args.all:
        analyze_and_export(args.logs, args.output)


if __name__ == '__main__':
    main()
