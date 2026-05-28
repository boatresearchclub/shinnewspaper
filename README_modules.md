# load_race モジュール分割ガイド

## 分割の概要

`load_race.py`（元 12,487行）を機能単位で 8 ファイルに分割しました。

```
scripts/
├── load_race.py        ← エントリポイント（main のみ・813行）
├── lr_config.py        ← パス定数 / グローバル設定（213行）
├── lr_utils.py         ← 汎用ユーティリティ / Excel書式ヘルパー（85行）
├── lr_masters.py       ← マスタ / CSV 読み込み（697行）
├── lr_calc.py          ← 指数計算 / 展開分析（2,821行）
├── lr_probs.py         ← 3連単確率計算 / EV計算（1,958行）
├── lr_suggest.py       ← 買い目提案 / 本命判定（3,239行）
├── lr_excel.py         ← Excel書き込み / 数値シート（2,247行）
└── lr_log.py           ← 予想ログ / ROIバックテスト（327行）
```

## 各ファイルの役割

| ファイル | 主な関数 | 説明 |
|---|---|---|
| `lr_config.py` | `build_odds_url`, `_load_venue_course_adj` | パス定数・会場コードマップ・グレード別CSVマップ・シート名定数 |
| `lr_utils.py` | `sep`, `safe_float`, `make_fill`, `write_cell` | 共通ユーティリティ・openpyxl書式ヘルパー |
| `lr_masters.py` | `load_masters`, `load_csv`, `load_motor_csv` | Excelマスタ・CSV の読み込み処理 |
| `lr_calc.py` | `calc_race_indices`, `_judge_race_type`, `_judge_ryotate` | 選手指数計算・第1ターン予測・展開分析・レース判定 |
| `lr_probs.py` | `_calc_3rentan_probs_v2`, `calc_ev_from_actual_odds`, `suggest_by_ev` | 3連単確率計算（v2）・EV計算・ケリー基準 |
| `lr_suggest.py` | `_suggest_3rentan`, `build_jizen_members`, `_calc_venue_stats` | 買い目提案・本命スコア・脱出判定・ヒモ荒れ判定 |
| `lr_excel.py` | `write_race_flat`, `write_numeric_sheet`, `_make_st_boat_chart` | Excelシート書き込み・ST舟図生成 |
| `lr_log.py` | `_flush_prediction_log`, `calc_roi_from_logs` | 予想ログ保存・ROIバックテスト集計 |
| `load_race.py` | `main` | CLI引数解析・ループ制御・外部スクリプト呼び出し |

## 削除した不要コード

| 関数名 | 元の行 | 削除理由 |
|---|---|---|
| `_calc_3rentan_probs` | L3846–3906（61行） | v2 に完全移行済み。どこからも呼ばれていない旧版。 |
| `clone_sample_layout` | L9083–9107（25行） | DEPRECATED 明記。`main()` から未使用。 |
| `write_race_to_sample_layout` | L9108–9213（106行） | DEPRECATED 明記。`main()` から未使用。 |

合計 **192行削除**。コメントアウト済みの import（`copy`, `tempfile`, `GradientFill`, `DifferentialStyle`）も整理済み。

## 実行方法（変更なし）

```bash
python scripts/load_race.py --venue 大村
python scripts/load_race.py --venue 大村 --race 5
python scripts/load_race.py --venue 大村 --date 2026-02-15
python scripts/load_race.py --venue 大村 --date 2026-02-15 --race 5
python scripts/load_race.py   # csv_output/ の最新ファイルを自動検出
```

外部スクリプト（`fill_newspaper.py`, `xlsx_to_png_interactive.py` など）との連携は
**変更なし**。`load_race.py` を実行するだけで従来通り動作します。

## 他スクリプトからのインポート例

```python
# ROIバックテストを単体実行する場合
from lr_log import calc_roi_from_logs
summary = calc_roi_from_logs()

# 確率計算だけ使いたい場合
from lr_probs import _calc_3rentan_probs_v2

# 会場設定だけ参照したい場合
from lr_config import VENUE_JCD_MAP, EXCEL_FILE
```

## import 依存関係

```
load_race.py
├── lr_config.py   (依存なし)
├── lr_utils.py    (依存なし)
├── lr_masters.py  → lr_config, lr_utils
├── lr_calc.py     → lr_config, lr_utils
├── lr_probs.py    → lr_utils
├── lr_suggest.py  → lr_utils
├── lr_excel.py    → lr_config, lr_utils
└── lr_log.py      → lr_utils
```

循環 import なし。`lr_config` と `lr_utils` が最下層。
