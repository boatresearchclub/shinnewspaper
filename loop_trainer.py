# -*- coding: utf-8 -*-
"""
loop_trainer.py
================
【機能】
  「バックテスト → 補正反映 → 再バックテスト」の学習ループを
  手動確認しながら1サイクルずつ実行する対話式管理スクリプト。

【1サイクルの流れ】
  Phase 1: python backtest_engine.py --force
           → correction_table.json 更新
  Phase 2: python apply_correction.py --dry-run
           → 変更内容をプレビュー（保存しない）
  Phase 3: 確認後に python apply_correction.py
           → 蓄積CSV の見送り推奨を更新
  Phase 4: python backtest_engine.py --force
           → 補正後の蓄積CSVで再バックテスト → 精度変化を確認

【使い方】
  python loop_trainer.py              # 対話式 1サイクル
  python loop_trainer.py --cycles 3   # 3サイクル連続（確認あり）
  python loop_trainer.py --phase 2    # 指定フェーズから再開
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# ══════════════════════════════════════════════════════════
# パス定数
# ══════════════════════════════════════════════════════════
BASE_DIR        = Path(r"C:\Users\user\Desktop\データ収集")
SCRIPTS_DIR     = BASE_DIR / "scripts"
CORRECTION_JSON = SCRIPTS_DIR / "correction_table.json"
HISTORY_FILE    = SCRIPTS_DIR / "loop_trainer_history.jsonl"

BACKTEST_SCRIPT  = SCRIPTS_DIR / "backtest_engine.py"
CORRECTION_SCRIPT = SCRIPTS_DIR / "apply_correction.py"


# ══════════════════════════════════════════════════════════
# ユーティリティ
# ══════════════════════════════════════════════════════════

def sep(c="=", w=55):
    print(c * w)


def _load_json(path) -> dict:
    if Path(path).exists():
        with open(str(path), encoding="utf-8") as f:
            return json.load(f)
    return {}


def _append_history(entry: dict):
    try:
        with open(str(HISTORY_FILE), "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _read_history() -> list:
    if not HISTORY_FILE.exists():
        return []
    entries = []
    with open(str(HISTORY_FILE), encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except Exception:
                    pass
    return entries


def ask(prompt: str, default_yes: bool = True) -> bool:
    """Y/n 確認プロンプト。Enterのみは default_yes に従う。"""
    hint = "[Y/n]" if default_yes else "[y/N]"
    while True:
        ans = input(f"\n  {prompt} {hint}: ").strip().lower()
        if ans == "" :
            return default_yes
        if ans in ("y", "yes"):
            return True
        if ans in ("n", "no"):
            return False
        print("  'y' か 'n' で答えてください。")


def run_cmd(cmd: list[str], label: str) -> int:
    """
    コマンドを実行し、終了コードを返す。
    標準出力はリアルタイムで表示する。
    """
    print()
    print(f"  ▶ {label}")
    print(f"    > {' '.join(cmd)}")
    print()
    result = subprocess.run(cmd, env=None)
    return result.returncode


def get_correction_snapshot() -> dict:
    """現在の correction_table.json の主要指標を取得する。"""
    corr = _load_json(CORRECTION_JSON)
    if not corr:
        return {}
    return {
        "generated_at": corr.get("generated_at", ""),
        "base_hit_rate": corr.get("base_hit_rate", 0),
        "base_roi": corr.get("base_roi", 0),
        "score_threshold": corr.get("score_threshold", 0),
        "rank_weight": corr.get("rank_weight", {}),
    }


def print_correction_diff(before: dict, after: dict):
    """補正前後の指標変化を表示する。"""
    if not before or not after:
        return
    print()
    print("  ┌──────────────────────────────────────────────┐")
    print("  │  補正前後 比較                                 │")
    print("  ├──────────────────────────────────────────────┤")

    bh = before.get("base_hit_rate", 0)
    ah = after.get("base_hit_rate", 0)
    br = before.get("base_roi", 0)
    ar = after.get("base_roi", 0)
    bt = before.get("score_threshold", 0)
    at = after.get("score_threshold", 0)

    def delta_str(b, a, fmt=".1f"):
        d = a - b
        sign = "+" if d >= 0 else ""
        return f"{b:{fmt}} → {a:{fmt}}  ({sign}{d:{fmt}})"

    print(f"  │  的中率        : {delta_str(bh, ah)}%")
    print(f"  │  ROI           : {delta_str(br, ar)}%")
    print(f"  │  スコア閾値    : {delta_str(bt, at, '.0f')}")
    print()

    # ランク重みの変化
    bw = before.get("rank_weight", {})
    aw = after.get("rank_weight", {})
    if bw or aw:
        print("  │  レースランク重み:")
        for rank in ["S", "A", "B", "C", "D"]:
            b_val = bw.get(rank, 1.0)
            a_val = aw.get(rank, 1.0)
            d = a_val - b_val
            change = f"  ({'+'if d>=0 else ''}{d:.3f})" if abs(d) > 0.001 else ""
            print(f"  │    {rank}: {b_val:.3f} → {a_val:.3f}{change}")

    print("  └──────────────────────────────────────────────┘")


# ══════════════════════════════════════════════════════════
# フェーズ実行
# ══════════════════════════════════════════════════════════

def phase1_backtest(python_exe: str, venue: str = None) -> int:
    """Phase 1: バックテスト実行 → correction_table.json 更新"""
    cmd = [python_exe, str(BACKTEST_SCRIPT), "--force"]
    if venue:
        cmd += ["--venue", venue]
    return run_cmd(cmd, "Phase 1: バックテスト実行（--force）")


def phase2_dry_run(python_exe: str, venue: str = None) -> int:
    """Phase 2: 補正のドライラン（変更プレビュー）"""
    cmd = [python_exe, str(CORRECTION_SCRIPT), "--dry-run"]
    if venue:
        cmd += ["--venue", venue]
    return run_cmd(cmd, "Phase 2: 補正プレビュー（--dry-run）")


def phase3_apply(python_exe: str, venue: str = None) -> int:
    """Phase 3: 補正を蓄積CSVに反映"""
    cmd = [python_exe, str(CORRECTION_SCRIPT)]
    if venue:
        cmd += ["--venue", venue]
    return run_cmd(cmd, "Phase 3: 補正を蓄積CSVに反映")


def phase4_rebacktest(python_exe: str, venue: str = None) -> int:
    """Phase 4: 補正後の蓄積CSVで再バックテスト"""
    cmd = [python_exe, str(BACKTEST_SCRIPT), "--force"]
    if venue:
        cmd += ["--venue", venue]
    return run_cmd(cmd, "Phase 4: 再バックテスト（補正後）")


# ══════════════════════════════════════════════════════════
# 1サイクル実行
# ══════════════════════════════════════════════════════════

def run_one_cycle(cycle_no: int, python_exe: str,
                  start_phase: int = 1, venue: str = None):
    """
    1サイクル（4フェーズ）を手動確認しながら実行する。
    """
    sep()
    print(f"  学習ループ  サイクル {cycle_no}")
    sep()

    # 開始前のスナップショット
    snapshot_before = get_correction_snapshot()
    if snapshot_before:
        print(f"\n  現在の指標: 的中率 {snapshot_before['base_hit_rate']}% / "
              f"ROI {snapshot_before['base_roi']}% / "
              f"閾値 {snapshot_before['score_threshold']}")

    cycle_log = {
        "cycle": cycle_no,
        "started_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "venue": venue or "全会場",
        "phases_completed": [],
        "before": snapshot_before,
        "after": {},
        "aborted": False,
    }

    # ── Phase 1: バックテスト ──────────────────────────────────────
    if start_phase <= 1:
        if not ask("Phase 1: バックテストを実行しますか？"):
            print("  → スキップします")
        else:
            rc = phase1_backtest(python_exe, venue)
            if rc != 0:
                print(f"\n  [!] Phase 1 がエラー終了しました（code={rc}）")
                if not ask("エラーを無視して続行しますか？", default_yes=False):
                    cycle_log["aborted"] = True
                    _append_history(cycle_log)
                    return False
            cycle_log["phases_completed"].append(1)

    # ── Phase 2: ドライラン ────────────────────────────────────────
    if start_phase <= 2:
        if not ask("Phase 2: 補正プレビュー（dry-run）を実行しますか？"):
            print("  → スキップします")
        else:
            rc = phase2_dry_run(python_exe, venue)
            if rc != 0:
                print(f"\n  [!] Phase 2 がエラー終了しました（code={rc}）")
            else:
                cycle_log["phases_completed"].append(2)

    # ── Phase 3: 補正反映 ──────────────────────────────────────────
    if start_phase <= 3:
        if not ask("Phase 3: 上記の補正内容を蓄積CSVに反映しますか？",
                   default_yes=False):
            print("  → 補正反映をスキップします。サイクルを終了します。")
            cycle_log["aborted"] = True
            _append_history(cycle_log)
            return False
        else:
            rc = phase3_apply(python_exe, venue)
            if rc != 0:
                print(f"\n  [!] Phase 3 がエラー終了しました（code={rc}）")
                if not ask("エラーを無視して続行しますか？", default_yes=False):
                    cycle_log["aborted"] = True
                    _append_history(cycle_log)
                    return False
            cycle_log["phases_completed"].append(3)

    # ── Phase 4: 再バックテスト ────────────────────────────────────
    if start_phase <= 4:
        if not ask("Phase 4: 補正後の蓄積CSVで再バックテストを実行しますか？"):
            print("  → 再バックテストをスキップします。")
        else:
            rc = phase4_rebacktest(python_exe, venue)
            if rc != 0:
                print(f"\n  [!] Phase 4 がエラー終了しました（code={rc}）")
            else:
                cycle_log["phases_completed"].append(4)

    # ── 結果比較 ───────────────────────────────────────────────────
    snapshot_after = get_correction_snapshot()
    cycle_log["after"] = snapshot_after
    print_correction_diff(snapshot_before, snapshot_after)

    # ── ログ保存 ───────────────────────────────────────────────────
    cycle_log["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    _append_history(cycle_log)

    sep()
    print(f"  サイクル {cycle_no} 完了")
    sep()
    return True


# ══════════════════════════════════════════════════════════
# 履歴表示
# ══════════════════════════════════════════════════════════

def show_history():
    history = _read_history()
    if not history:
        print("  履歴なし（loop_trainer_history.jsonl が存在しないか空です）")
        return

    print()
    sep()
    print("  学習ループ 実行履歴")
    sep()
    for h in history[-10:]:  # 直近10件
        cycle = h.get("cycle", "?")
        started = h.get("started_at", "")
        venue = h.get("venue", "")
        aborted = "中断" if h.get("aborted") else "完了"
        phases = h.get("phases_completed", [])

        before_hit = h.get("before", {}).get("base_hit_rate", 0)
        after_hit  = h.get("after", {}).get("base_hit_rate", 0)
        before_roi = h.get("before", {}).get("base_roi", 0)
        after_roi  = h.get("after", {}).get("base_roi", 0)

        delta_hit = after_hit - before_hit
        delta_roi = after_roi - before_roi
        delta_hit_str = f"{delta_hit:+.1f}%" if after_hit else "（未測定）"
        delta_roi_str = f"{delta_roi:+.1f}%" if after_roi else "（未測定）"

        print(f"\n  [サイクル {cycle}]  {started}  {venue}  {aborted}")
        print(f"    完了フェーズ: {phases}")
        print(f"    的中率変化 : {before_hit:.1f}% → {after_hit:.1f}%  {delta_hit_str}")
        print(f"    ROI 変化   : {before_roi:.1f}% → {after_roi:.1f}%  {delta_roi_str}")
    print()


# ══════════════════════════════════════════════════════════
# main
# ══════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="競艇バックテスト学習ループ管理")
    parser.add_argument("--cycles",  type=int, default=1,
                        help="実行サイクル数（デフォルト=1）")
    parser.add_argument("--phase",   type=int, default=1, choices=[1,2,3,4],
                        help="開始フェーズ（途中再開用）")
    parser.add_argument("--venue",   type=str, default=None,
                        help="会場名フィルタ（例: びわこ）")
    parser.add_argument("--python",  type=str, default=sys.executable,
                        help="Pythonインタープリタのパス（省略=現在のvenv）")
    parser.add_argument("--history", action="store_true",
                        help="実行履歴を表示して終了")
    args = parser.parse_args()

    if args.history:
        show_history()
        return

    # スクリプトの存在確認
    for path, name in [(BACKTEST_SCRIPT, "backtest_engine.py"),
                       (CORRECTION_SCRIPT, "apply_correction.py")]:
        if not path.exists():
            print(f"\n  [NG] {name} が見つかりません: {path}")
            print("  scripts/ フォルダに配置してください。")
            sys.exit(1)

    print()
    sep()
    print("  競艇バックテスト 学習ループ管理")
    sep()
    print(f"\n  サイクル数    : {args.cycles}")
    print(f"  開始フェーズ  : Phase {args.phase}")
    print(f"  会場フィルタ  : {args.venue or '全会場'}")
    print(f"  Python        : {args.python}")
    print()
    print("  【1サイクルの流れ】")
    print("    Phase 1: バックテスト → correction_table.json 更新")
    print("    Phase 2: 補正プレビュー（ドライラン）")
    print("    Phase 3: 補正を蓄積CSVに反映")
    print("    Phase 4: 補正後の蓄積CSVで再バックテスト")
    print()
    print("  ※ 各フェーズは確認後に実行します（スキップも可）")

    if not ask("学習ループを開始しますか？"):
        print("  中止しました。")
        return

    # ── 履歴から次のサイクル番号を決定 ──────────────────────────────
    history = _read_history()
    next_cycle = (max((h.get("cycle", 0) for h in history), default=0) + 1)

    # ── サイクルを実行 ─────────────────────────────────────────────
    for i in range(args.cycles):
        cycle_no = next_cycle + i
        start_phase = args.phase if i == 0 else 1  # 2サイクル目以降はPhase1から

        success = run_one_cycle(
            cycle_no=cycle_no,
            python_exe=args.python,
            start_phase=start_phase,
            venue=args.venue,
        )

        if not success:
            print(f"\n  サイクル {cycle_no} が中断されました。")
            break

        if i < args.cycles - 1:
            if not ask(f"次のサイクル（{cycle_no + 1}）に進みますか？",
                       default_yes=False):
                print("  ループを終了します。")
                break

    # ── 全体サマリー ────────────────────────────────────────────────
    print()
    print("  【履歴確認】")
    print(f"  python loop_trainer.py --history")
    print()


if __name__ == "__main__":
    main()
