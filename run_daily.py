# -*- coding: utf-8 -*-
"""
run_daily.py
============
毎朝の全自動処理をまとめて実行するマスタースクリプト。
Windows タスクスケジューラから起動することを想定。

【実行順序】
  STEP 1: download_b.py          ← mbrace から番組表 LZH をダウンロード
  STEP 2: lzh_to_csv.py          ← LZH → CSV 変換（scripts/ フォルダを自動検出）
  STEP 3: scrape_flying.py       ← 全場フライング情報を Web 取得
  STEP 4: sync_flying_to_master.py ← フライングデータをマスタ Excel に反映
  STEP 5: load_race.py --all     ← 指数計算・新聞・PNG 出力（フラグ込み）

【使い方】
  python scripts/run_daily.py                 # 当日分を全自動実行
  python scripts/run_daily.py --date 2026-04-03   # 日付指定
  python scripts/run_daily.py --skip-download     # LZH ダウンロードをスキップ
  python scripts/run_daily.py --skip-flying       # フライング取得をスキップ
  python scripts/run_daily.py --from-step 3       # STEP3 から再開

【タスクスケジューラ設定例】
  プログラム: C:\\Python312\\python.exe
  引数      : C:\\Users\\user\\Desktop\\データ収集\\scripts\\run_daily.py
  作業フォルダ: C:\\Users\\user\\Desktop\\データ収集\\scripts
  トリガー  : 毎朝 08:30（番組表配信後を想定）

【ログ出力先】
  C:\\Users\\user\\Desktop\\データ収集\\scripts\\logs\\YYYYMMDD.log
"""

import sys
import os
import subprocess
import pathlib
import argparse
import time
import logging
from datetime import datetime

# ============================================================
# パス設定
# ============================================================
SCRIPTS_DIR  = pathlib.Path(__file__).parent
BASE_DIR     = SCRIPTS_DIR.parent
LOG_DIR      = SCRIPTS_DIR / "logs"

# 各スクリプトのパス
DOWNLOAD_B       = SCRIPTS_DIR / "download_b.py"
DOWNLOAD_RESULTS = SCRIPTS_DIR / "download_results.py"   # 【追加】前日結果CSV自動取得
LZH_TO_CSV       = SCRIPTS_DIR / "lzh_to_csv.py"
SCRAPE_PROGRAM   = SCRIPTS_DIR / "scrape_program.py"     # 【追加】番組表モーター2連対率取得
SCRAPE_FLYING    = (
    BASE_DIR / "scrape_flying.py"
    if (BASE_DIR / "scrape_flying.py").exists()
    else SCRIPTS_DIR / "scrape_flying.py"
)
SYNC_FLYING      = SCRIPTS_DIR / "sync_flying_to_master.py"
LOAD_RACE        = SCRIPTS_DIR / "load_race.py"
DISCORD_POST     = SCRIPTS_DIR / "discord_post_newspaper.py"
LR_BACKTEST      = SCRIPTS_DIR / "lr_backtest.py"         # 【追加】日次バックテスト突合

# Discord 投稿のデフォルト時刻
DISCORD_POST_TIME = "06:30"

# ============================================================
# ロギング設定（コンソール + ファイル同時出力）
# ============================================================
def setup_logging(date_str: str):
    LOG_DIR.mkdir(exist_ok=True)
    log_file = LOG_DIR / f"{date_str}.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(str(log_file), encoding="utf-8"),
        ]
    )
    return log_file


# ============================================================
# サブプロセス実行ヘルパー
# ============================================================
def run_step(
    step_no: int,
    label: str,
    cmd: list[str],
    cwd: pathlib.Path = None,
    timeout: int = 3600,
    allow_fail: bool = False,
    stdin_input: str = None,
) -> bool:
    """
    サブプロセスを実行し、成否を返す。
    allow_fail=True のとき、失敗しても処理を続行する。
    stdin_input を指定すると、対話プロンプトに自動入力する。
    """
    sep = "─" * 50
    logging.info(sep)
    logging.info(f"  STEP {step_no}: {label}")
    logging.info(sep)

    start = time.perf_counter()
    try:
        result = subprocess.run(
            cmd,
            cwd=str(cwd or SCRIPTS_DIR),
            timeout=timeout,
            check=False,           # 終了コードは自分で確認
            encoding="utf-8",
            errors="replace",
            input=stdin_input,     # 対話プロンプトへの自動入力（None のときは無効）
        )
        elapsed = time.perf_counter() - start

        if result.returncode == 0:
            logging.info(f"  ✅ STEP {step_no} 完了  ({elapsed:.1f}秒)")
            return True
        else:
            msg = f"  ⚠️  STEP {step_no} 終了コード {result.returncode}  ({elapsed:.1f}秒)"
            if allow_fail:
                logging.warning(msg + "  → 続行します")
                return True   # allow_fail なので処理は続ける
            else:
                logging.error(msg)
                logging.error(f"  ❌ STEP {step_no} 失敗。処理を中断します。")
                return False

    except subprocess.TimeoutExpired:
        logging.error(f"  ❌ STEP {step_no} タイムアウト ({timeout}秒)")
        return allow_fail

    except FileNotFoundError as e:
        logging.error(f"  ❌ STEP {step_no} スクリプトが見つかりません: {e}")
        return allow_fail

    except Exception as e:
        logging.error(f"  ❌ STEP {step_no} 予期せぬエラー: {e}")
        return allow_fail


# ============================================================
# メイン
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="ボートリサーチ 全自動処理")
    parser.add_argument(
        "--date", type=str, default=None,
        help="処理対象日付 (例: 2026-04-03)。省略時は当日"
    )
    parser.add_argument(
        "--skip-download", action="store_true",
        help="STEP1 LZH ダウンロードをスキップ（既にダウンロード済みの場合）"
    )
    parser.add_argument(
        "--skip-flying", action="store_true",
        help="STEP3〜4 フライング取得・マスタ反映をスキップ"
    )
    parser.add_argument(
        "--from-step", type=int, default=0, choices=[0, 1, 2, 3, 4, 5, 6, 7],
        help="指定ステップから再開 (0〜7)  ※0=STEP0(結果取得)から開始"
    )
    parser.add_argument(
        "--grade", type=str, default="一般",
        choices=["一般", "G1", "G2", "G3", "SG"],
        help="レースグレード (デフォルト: 一般)"
    )
    parser.add_argument(
        "--skip-discord", action="store_true",
        help="STEP6 Discord投稿をスキップ"
    )
    parser.add_argument(
        "--discord-time", type=str, default=DISCORD_POST_TIME,
        help=f"Discord投稿時刻 (例: 06:30)。デフォルト: {DISCORD_POST_TIME}"
    )
    parser.add_argument(
        "--skip-results", action="store_true",
        help="STEP0 前日結果CSV取得をスキップ"
    )
    parser.add_argument(
        "--skip-backtest", action="store_true",
        help="STEP7 日次バックテスト突合をスキップ"
    )
    args = parser.parse_args()

    # 日付を確定
    if args.date:
        try:
            target_dt = datetime.strptime(args.date, "%Y-%m-%d")
        except ValueError:
            print(f"❌ 日付形式が正しくありません: {args.date}  (例: 2026-04-03)")
            sys.exit(1)
    else:
        target_dt = datetime.now()

    date_str      = target_dt.strftime("%Y%m%d")     # 20260403
    date_hyphen   = target_dt.strftime("%Y-%m-%d")   # 2026-04-03

    log_file = setup_logging(date_str)

    logging.info("=" * 55)
    logging.info("  ボートリサーチ 全自動処理")
    logging.info(f"  対象日付 : {date_hyphen}")
    logging.info(f"  ログ     : {log_file}")
    logging.info("=" * 55)

    # スクリプトの存在確認
    missing = []
    for path in [DOWNLOAD_B, LZH_TO_CSV, SCRAPE_FLYING, SYNC_FLYING, LOAD_RACE]:
        if not path.exists():
            missing.append(str(path))
    if missing:
        logging.error("❌ 以下のスクリプトが見つかりません:")
        for m in missing:
            logging.error(f"   {m}")
        # DOWNLOAD_B と SYNC_FLYING は新規追加スクリプトなので警告のみ
        critical = [m for m in missing if "load_race" in m or "lzh_to_csv" in m]
        if critical:
            sys.exit(1)

    py = sys.executable
    from_step = args.from_step
    ok = True

    # ──────────────────────────────────────────────────────────
    # STEP 0: 前日レース結果CSV自動取得  【追加】
    # download_results.py が存在する場合のみ実行。
    # 前日分（date_str の前日）を自動DL → data_csv/YYYYMM_results.csv に追記。
    # 失敗しても後続処理（当日の予想生成）は継続する（allow_fail=True）。
    # ──────────────────────────────────────────────────────────
    from datetime import timedelta
    prev_date_str = (target_dt - timedelta(days=1)).strftime("%Y%m%d")

    if from_step <= 0 and not args.skip_results:
        if DOWNLOAD_RESULTS.exists():
            ok_r = run_step(
                0, f"前日結果CSV取得 ({prev_date_str})",
                [py, str(DOWNLOAD_RESULTS), "--date", prev_date_str],
                timeout=300,
                allow_fail=True,   # 結果取得失敗でも当日予想は続行
            )
            if not ok_r:
                logging.warning("前日結果の取得に失敗しました。手動で確認してください。")
        else:
            logging.warning("  [!]   download_results.py が見つかりません → STEP0 スキップ")
            logging.warning("        scripts/download_results.py を配置してください。")
    elif args.skip_results:
        logging.info("  [SKIP] STEP0: 前日結果取得（--skip-results 指定）")

    # ──────────────────────────────────────────────────────────
    # STEP 1: 番組表 LZH ダウンロード
    # ──────────────────────────────────────────────────────────
    if from_step <= 1 and not args.skip_download and DOWNLOAD_B.exists():
        ok = run_step(
            1, "番組表 LZH ダウンロード",
            [py, str(DOWNLOAD_B), "--date", date_hyphen],
            timeout=120,
            allow_fail=False,   # 失敗したら中断（CSVの元がないため）
        )
        if not ok:
            logging.error("番組表のダウンロードに失敗しました。")
            logging.error("配信時刻前の可能性があります。時間をおいて再実行してください。")
            sys.exit(1)
    elif args.skip_download:
        logging.info("  [SKIP] STEP1: LZH ダウンロード（--skip-download 指定）")
    elif not DOWNLOAD_B.exists():
        logging.warning("  [!]   download_b.py が見つかりません → STEP1 スキップ")

    # ──────────────────────────────────────────────────────────
    # STEP 2: LZH → CSV 変換
    # ──────────────────────────────────────────────────────────
    if from_step <= 2:
        ok = run_step(
            2, "LZH → CSV 変換",
            [py, str(LZH_TO_CSV)],
            cwd=SCRIPTS_DIR,
            timeout=180,
            allow_fail=False,
        )
        if not ok:
            sys.exit(1)
    else:
        logging.info(f"  [SKIP] STEP2: --from-step {from_step} のためスキップ")

    # ──────────────────────────────────────────────────────────

    # ----------------------------------------------------------
    # STEP 2.5: Motor rate scraping  [ADDED]
    # ----------------------------------------------------------
    if from_step <= 2 and SCRAPE_PROGRAM.exists():
        run_step(
            3, "Motor 2-rate scraping",
            [py, str(SCRAPE_PROGRAM), "--date", date_str],
            timeout=300,
            allow_fail=True,
        )
    elif not SCRAPE_PROGRAM.exists():
        logging.info("  [INFO] STEP2.5: scrape_program.py not found")

    # STEP 3: フライング情報スクレイピング
    # ──────────────────────────────────────────────────────────
    if from_step <= 3 and not args.skip_flying:
        # scrape_flying.py は実行フォルダに flying_YYYYMMDD.xlsx を出力する
        # → SCRIPTS_DIR で実行して scripts/ に出力させる
        ok = run_step(
            3, "フライング情報取得 (全場)",
            [py, str(SCRAPE_FLYING)],
            cwd=SCRIPTS_DIR,
            timeout=1800,    # Selenium 全場スクレイピングは時間がかかる
            allow_fail=True, # Web 取得失敗でも続行（フライングなしで処理）
            stdin_input="\n",  # 終了時の「Enterキーを押すと終了...」を自動スキップ
        )
    elif args.skip_flying:
        logging.info("  [SKIP] STEP3: フライング取得（--skip-flying 指定）")

    # ──────────────────────────────────────────────────────────
    # STEP 4: フライングデータ → マスタ反映
    # ──────────────────────────────────────────────────────────
    if from_step <= 4 and not args.skip_flying and SYNC_FLYING.exists():
        ok = run_step(
            4, "フライングデータ → マスタ反映",
            [py, str(SYNC_FLYING), "--date", date_str],
            timeout=120,
            allow_fail=True,  # 反映失敗でも load_race は動かす
        )
    elif not SYNC_FLYING.exists():
        logging.warning("  [!]   sync_flying_to_master.py が見つかりません → STEP4 スキップ")

    # ──────────────────────────────────────────────────────────
    # STEP 5: load_race.py --all（指数計算・新聞・PNG）
    # ──────────────────────────────────────────────────────────
    if from_step <= 5:
        load_race_cmd = [
            py, str(LOAD_RACE),
            "--all",
            "--newspaper",
            "--png",
            "--grade", args.grade,
            "--date",  date_hyphen,
        ]
        ok = run_step(
            5, "指数計算・新聞・PNG 出力 (全場)",
            load_race_cmd,
            cwd=SCRIPTS_DIR,
            timeout=7200,    # 全場処理は最大2時間
            allow_fail=False,
            stdin_input="1\n\n",  # ①実行モード選択「1.通常処理」②終了時Enterを自動送信
        )
        if not ok:
            logging.error("load_race.py が失敗しました。ログを確認してください。")
            sys.exit(1)

    # ──────────────────────────────────────────────────────────
    # 完了通知
    # ──────────────────────────────────────────────────────────
    logging.info("=" * 55)
    logging.info(f"✅ 全処理完了！  ({date_hyphen})")
    logging.info(f"   ログ: {log_file}")
    logging.info("=" * 55)

    # ──────────────────────────────────────────────────────────
    # STEP 6: Discord 新聞投稿
    # ──────────────────────────────────────────────────────────
    if not args.skip_discord and DISCORD_POST.exists():
        logging.info(f"  Discord 投稿時刻: {args.discord_time}")
        ok = run_step(
            6, f"Discord 新聞投稿 ({args.discord_time} 予約)",
            [
                py, str(DISCORD_POST),
                "--date", date_hyphen,
                "--time", args.discord_time,
            ],
            timeout=86400,   # 最大24時間（時刻待機を含む）
            allow_fail=True, # 投稿失敗でも全体は成功扱い
        )
        if not ok:
            logging.warning("Discord 投稿でエラーが発生しました。手動で確認してください。")
    elif args.skip_discord:
        logging.info("  [SKIP] STEP6: Discord 投稿（--skip-discord 指定）")
    elif not DISCORD_POST.exists():
        logging.warning("  [!]   discord_post_newspaper.py が見つかりません → STEP6 スキップ")

    # ──────────────────────────────────────────────────────────
    # STEP 7: 日次バックテスト突合  【追加】
    # lr_backtest.py --all を実行し、前日予想ログ×結果CSVを突合して
    # correction_params.json を更新する。
    # STEP0 で前日結果が取得できていない場合もスキップせず実行する
    # （既存CSVがあれば突合できるため）。
    # 失敗しても全体処理は成功扱い（allow_fail=True）。
    # ──────────────────────────────────────────────────────────
    if not args.skip_backtest:
        if LR_BACKTEST.exists():
            ok_bt = run_step(
                7, "日次バックテスト突合 (lr_backtest --all)",
                [py, str(LR_BACKTEST), "--all"],
                timeout=600,
                allow_fail=True,
            )
            if not ok_bt:
                logging.warning("日次バックテスト突合でエラーが発生しました。手動で確認してください。")
            else:
                logging.info("  correction_params.json を更新しました。")
        else:
            logging.info("  [SKIP] STEP7: lr_backtest.py が見つかりません → スキップ")
            logging.info("         scripts/lr_backtest.py（lr_backtest_fixed.pyをリネーム）を配置してください。")
    else:
        logging.info("  [SKIP] STEP7: 日次バックテスト突合（--skip-backtest 指定）")

    # Windows トースト通知（win10toast がある場合）
    try:
        from win10toast import ToastNotifier
        ToastNotifier().show_toast(
            "ボートリサーチ新聞",
            f"{date_hyphen} 全自動処理完了",
            duration=10,
            threaded=True,
        )
    except Exception:
        pass


if __name__ == "__main__":
    main()
