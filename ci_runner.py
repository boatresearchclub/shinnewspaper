"""
ci_runner.py  —  GitHub Actions 用 統合実行スクリプト
======================================================
race_index_YYYYMMDD.json（または race_index.json）を読み取り、
本日開催中の全会場に対して指定タスクを実行する。

使い方:
  python ci_runner.py --task tenji
  python ci_runner.py --task odds
  python ci_runner.py --task comments
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent


def load_race_index() -> dict:
    """本日分の race_index を読み込む。"""
    today = datetime.now().strftime("%Y%m%d")
    # 日付別ファイルを優先、なければ後方互換で race_index.json
    for path in [
        SCRIPTS_DIR / f"race_index_{today}.json",
        SCRIPTS_DIR / "race_index.json",
    ]:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            print(f"[ci_runner] race_index読み込み: {path.name}", flush=True)
            return data
    print("[ci_runner] race_index が見つかりません", flush=True)
    return {}


def run(cmd: list[str]) -> int:
    """サブプロセスを実行してリターンコードを返す。"""
    print(f"[ci_runner] 実行: {' '.join(cmd)}", flush=True)
    result = subprocess.run(cmd, text=True)
    return result.returncode


def task_tenji(venues: dict, today: str):
    """全会場の展示情報を取得（fetch_tenji.py --all）"""
    for venue_name, info in venues.items():
        slug = info.get("jcd", "")  # fetch_tenji は会場名で動くので venue_name を使う
        print(f"\n── {venue_name} 展示取得 ──", flush=True)
        run([
            sys.executable, "fetch_tenji.py",
            "--venue", venue_name,
            "--date",  today,
            "--all",
        ])


def task_odds(venues: dict, today: str):
    """全会場のオッズを取得（fetch_odds.py --jcd XX --hd YYYYMMDD）"""
    hd = today.replace("-", "")
    for venue_name, info in venues.items():
        jcd = info.get("jcd", "")
        if not jcd:
            continue
        print(f"\n── {venue_name} オッズ取得 jcd={jcd} ──", flush=True)
        run([
            sys.executable, "fetch_odds.py",
            "--jcd", jcd,
            "--hd",  hd,
        ])


def task_comments(venues: dict, today: str):
    """全会場のコメントを取得（scrape_comments.py --venue XX --date YYYY-MM-DD）"""
    for venue_name, info in venues.items():
        print(f"\n── {venue_name} コメント取得 ──", flush=True)
        run([
            sys.executable, "scrape_comments.py",
            "--venue", venue_name,
            "--date",  today,
        ])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--task",
        choices=["tenji", "odds", "comments"],
        required=True,
        help="実行するタスク",
    )
    args = ap.parse_args()

    data = load_race_index()
    if not data:
        print("[ci_runner] 開催情報なし → スキップ", flush=True)
        sys.exit(0)

    today = data.get("date", datetime.now().strftime("%Y-%m-%d"))
    venues = data.get("venues", {})

    if not venues:
        print("[ci_runner] 開催会場なし → スキップ", flush=True)
        sys.exit(0)

    print(f"[ci_runner] 本日の開催: {list(venues.keys())}", flush=True)

    if args.task == "tenji":
        task_tenji(venues, today)
    elif args.task == "odds":
        task_odds(venues, today)
    elif args.task == "comments":
        task_comments(venues, today)


if __name__ == "__main__":
    main()
