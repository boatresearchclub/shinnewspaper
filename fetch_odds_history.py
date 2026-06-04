"""
fetch_odds_history.py  【高速化版 v2 - aiohttp完全非同期化】
=============================================================
過去30日分のオッズを一括取得して odds_data/ に保存するスクリプト。

【v2での高速化ポイント】
  ・urllib.request（同期ブロッキング）→ aiohttp（完全非同期）
  ・1レース内の5種別を並列取得（従来は直列 × 3秒 = 15秒/レース）
  ・レース間も非同期並列（最大3レース同時）
  ・差分取得：既存ファイルはスキップ（--overwriteで上書き）

【速度改善の目安】
  旧版  : 80時間（逐次 urllib × 3秒インターバル）
  v1版  : 約27時間（3並列スレッド + 差分取得）
  v2版  : 約4〜8時間（aiohttp完全非同期 + 5種別並列）

【使い方】
  python fetch_odds_history.py               # 過去30日・全会場（差分のみ）
  python fetch_odds_history.py --days 7      # 過去7日に絞る
  python fetch_odds_history.py --dry-run     # 対象一覧だけ表示（取得しない）
  python fetch_odds_history.py --overwrite   # 既存ファイルも上書き

【必要ライブラリ】
  pip install aiohttp
"""

from __future__ import annotations

import argparse
import asyncio
import glob
import json
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import aiohttp
import pandas as pd

# ── パス設定 ─────────────────────────────────────────────────────────────────
SCRIPTS_DIR = Path(__file__).parent
CSV_DIR     = SCRIPTS_DIR / "csv_output"
ODDS_DIR    = SCRIPTS_DIR / "odds_data"

# ── 並列・待機設定（公式サイトへの負荷を抑える値） ─────────────────────────
CONCURRENT_RACES = 3      # 最大並列レース数
SAME_VENUE_WAIT  = 1.0    # 同一会場への連続リクエスト間隔（秒）
INTRA_RACE_WAIT  = 0.3    # 1レース内・種別間の最小ずらし間隔（秒）
RETRY_COUNT      = 2      # エラー時リトライ回数
RETRY_WAIT       = 5.0    # リトライ前の待機（秒）
FETCH_TIMEOUT    = 15     # HTTPタイムアウト（秒）
HISTORY_DAYS     = 30

# ── fetch_odds.py から必要な定数・パーサーのみインポート ──────────────────
try:
    from fetch_odds import (
        VENUE_SLUG,
        VENUE_JCD,
        ODDS_TYPES,
        HEADERS,
        _parse_odds_page,
        _save_odds,
    )
except ImportError:
    print("❌ fetch_odds.py が見つかりません。同じフォルダに置いてください。")
    sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# aiohttp による非同期HTMLフェッチ
# ─────────────────────────────────────────────────────────────────────────────

async def _fetch_html_async(session: aiohttp.ClientSession, url: str) -> str:
    """URLからHTMLを非同期取得（リトライ付き）"""
    last_err: Optional[Exception] = None
    for attempt in range(1, RETRY_COUNT + 2):
        try:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=FETCH_TIMEOUT)
            ) as resp:
                resp.raise_for_status()
                raw = await resp.read()
                try:
                    return raw.decode("utf-8")
                except UnicodeDecodeError:
                    return raw.decode("shift_jis", errors="replace")
        except Exception as e:
            last_err = e
            if attempt <= RETRY_COUNT:
                await asyncio.sleep(RETRY_WAIT)
    raise ConnectionError(f"取得失敗({RETRY_COUNT}回): {last_err}  URL: {url}")


# ─────────────────────────────────────────────────────────────────────────────
# 1レース・1種別を非同期取得
# ─────────────────────────────────────────────────────────────────────────────

async def _fetch_one_odds_async(
    session: aiohttp.ClientSession,
    jcd: str,
    rno: int,
    date_nd: str,
    ot: dict,
) -> tuple[str, dict]:
    """1種別のオッズを取得して (odds_key, result_dict) を返す"""
    url = (
        f"https://www.boatrace.jp/owpc/pc/race/{ot['endpoint']}"
        f"?rno={rno}&jcd={jcd}&hd={date_nd}"
    )
    try:
        html   = await _fetch_html_async(session, url)
        result = _parse_odds_page(html, ot["key"])
        return ot["key"], result
    except Exception:
        return ot["key"], {}


# ─────────────────────────────────────────────────────────────────────────────
# 1レース・全5種別を並列取得
# ─────────────────────────────────────────────────────────────────────────────

async def _fetch_race_async(
    session: aiohttp.ClientSession,
    race_sem: asyncio.Semaphore,
    venue_locks: dict,
    venue_name: str,
    slug: str,
    date_nd: str,
    rno: int,
    overwrite: bool,
    counter: dict,
) -> tuple[bool, bool]:
    """
    1レース分（5種別）を並列取得して保存。
    Returns: (success, skipped)
    """
    fpath = ODDS_DIR / f"odds_{slug}_{date_nd}_R{rno:02d}.json"

    # 既存ファイルスキップ
    if not overwrite and fpath.exists() and fpath.stat().st_size > 100:
        counter["skip"] += 1
        return True, True

    async with race_sem:
        # 同一会場への連続アクセスを制御（ロック＋インターバル）
        lock = venue_locks[venue_name]
        async with lock:
            await asyncio.sleep(SAME_VENUE_WAIT)

            jcd = VENUE_JCD.get(venue_name)
            if not jcd:
                counter["error"] += 1
                return False, False

            # 5種別を少しずつずらして並列発射（同時集中を避ける）
            coros = []
            for i, ot in enumerate(ODDS_TYPES):
                async def _delayed(ot=ot, delay=i * INTRA_RACE_WAIT):
                    await asyncio.sleep(delay)
                    return await _fetch_one_odds_async(session, jcd, rno, date_nd, ot)
                coros.append(_delayed())

            results = await asyncio.gather(*coros, return_exceptions=True)

        result: dict = {}
        fetch_ok = True
        for item in results:
            if isinstance(item, Exception) or not isinstance(item, tuple):
                fetch_ok = False
                continue
            key, data = item
            result[key] = data
            if not data:
                fetch_ok = False

        result["fetched_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        result["final"] = True

        _save_odds(slug, date_nd, rno, result)

        if fetch_ok:
            counter["ok"] += 1
        else:
            counter["partial"] += 1

        return fetch_ok, False


# ─────────────────────────────────────────────────────────────────────────────
# CSV から「会場名 × 日付」リストを収集
# ─────────────────────────────────────────────────────────────────────────────

def collect_venue_dates(days: int) -> list[tuple[str, str]]:
    today = datetime.now().date()
    target_dates = {
        (today - timedelta(days=d)).strftime("%Y-%m-%d")
        for d in range(0, days + 1)  # 0を含めて当日分も対象
    }

    found: list[tuple[str, str]] = []
    seen:  set[tuple[str, str]]  = set()

    for csv_path in sorted(glob.glob(str(CSV_DIR / "*.csv"))):
        fname = Path(csv_path).name
        matched_date = next((d for d in target_dates if d in fname), None)
        if matched_date is None:
            continue
        try:
            try:
                df = pd.read_csv(csv_path, encoding="utf-8")
            except UnicodeDecodeError:
                df = pd.read_csv(csv_path, encoding="shift_jis")

            if "会場" not in df.columns:
                continue

            for col in ("日付",):
                if col in df.columns:
                    raw = str(df.iloc[0][col]).strip().replace("/", "-")
                    if len(raw) == 8 and raw.isdigit():
                        raw = f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
                    if raw in target_dates:
                        matched_date = raw
                    break

            vname = str(df.iloc[0]["会場"]).strip()
            if vname not in VENUE_SLUG:
                continue

            key = (vname, matched_date)
            if key not in seen:
                seen.add(key)
                found.append(key)

        except Exception as e:
            print(f"  ⚠ CSV読込スキップ {fname}: {e}", flush=True)

    return found


def collect_today_deadlines() -> dict:
    """
    今日のCSVから締切済みレース番号を取得する。
    戻り値: {(venue_name, date_str): {締め切り済みrno, ...}}
    今日以外の日付は対象外（過去日は全レース対象のため不要）。
    """
    today_str = datetime.now().date().strftime("%Y-%m-%d")
    now_time  = datetime.now().strftime("%H:%M")
    result = {}

    for csv_path in sorted(glob.glob(str(CSV_DIR / "*.csv"))):
        if today_str not in Path(csv_path).name:
            continue
        try:
            try:
                df = pd.read_csv(csv_path, encoding="utf-8")
            except UnicodeDecodeError:
                df = pd.read_csv(csv_path, encoding="shift_jis")

            if "会場" not in df.columns or "締切時刻" not in df.columns:
                continue

            vname = str(df.iloc[0]["会場"]).strip()
            if vname not in VENUE_SLUG:
                continue

            closed = set()
            for _, row in df.iterrows():
                rno_raw = row.get("レース", "")
                dl_raw  = str(row.get("締切時刻", "")).strip()
                if not str(rno_raw).isdigit() or not dl_raw or dl_raw == "nan":
                    continue
                dl = dl_raw[:5]  # "HH:MM" に正規化
                if dl <= now_time:
                    closed.add(int(rno_raw))

            result[(vname, today_str)] = closed

        except Exception as e:
            print(f"  ⚠ 締切時刻CSV読込スキップ {Path(csv_path).name}: {e}", flush=True)

    return result


# ─────────────────────────────────────────────────────────────────────────────
# 進捗表示ヘルパー
# ─────────────────────────────────────────────────────────────────────────────

def _progress_bar(done: int, total: int, width: int = 28) -> str:
    ratio  = done / total if total else 0
    filled = int(width * ratio)
    bar    = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {ratio*100:5.1f}%"


def _format_eta(start: float, done_actual: int, need_fetch: int) -> str:
    if done_actual <= 0:
        return ""
    elapsed  = time.time() - start
    per_task = elapsed / done_actual
    remain   = per_task * (need_fetch - done_actual)
    h, rem   = divmod(int(max(remain, 0)), 3600)
    m, s     = divmod(rem, 60)
    speed    = done_actual / elapsed * 60
    if h > 0:
        return f"残 約{h}h{m:02d}m  {speed:.1f}件/分"
    return f"残 約{m}m{s:02d}s  {speed:.1f}件/分"


# ─────────────────────────────────────────────────────────────────────────────
# メイン非同期処理
# ─────────────────────────────────────────────────────────────────────────────

async def fetch_history_async(
    days: int = HISTORY_DAYS,
    dry_run: bool = False,
    overwrite: bool = False,
) -> None:
    print(f"\n{'='*62}")
    print(f"  過去オッズ一括取得 v2（aiohttp完全非同期）")
    print(f"  過去{days}日 / 全5種別並列 / {'上書き' if overwrite else '差分のみ'}")
    print(f"  並列レース数: {CONCURRENT_RACES}  同一会場間隔: {SAME_VENUE_WAIT}s")
    print(f"{'='*62}\n")

    venue_dates = collect_venue_dates(days)
    if not venue_dates:
        print("⚠ 対象となるCSVが見つかりませんでした。")
        print(f"  確認先: {CSV_DIR}")
        return

    venue_dates.sort(key=lambda x: x[1], reverse=True)

    # 今日分は締め切り済みレースのみ対象（未来レースは auto_push.py に任せる）
    today_str     = datetime.now().date().strftime("%Y-%m-%d")
    today_closed  = collect_today_deadlines()  # {(venue, date): {rno, ...}}

    tasks_info: list[tuple[str, str, str, int]] = []
    skipped_future = 0
    for venue_name, date_str in venue_dates:
        slug    = VENUE_SLUG[venue_name]
        date_nd = date_str.replace("-", "")
        for rno in range(1, 13):
            # 今日分：締め切り済みレースのみ追加
            if date_str == today_str:
                closed = today_closed.get((venue_name, today_str), set())
                if rno not in closed:
                    skipped_future += 1
                    continue
            tasks_info.append((venue_name, slug, date_nd, rno))

    if skipped_future:
        print(f"  ℹ 今日の未締切レース {skipped_future}件はスキップ（締切後に自動取得されます）")

    total    = len(tasks_info)
    existing = sum(
        1 for _, slug, date_nd, rno in tasks_info
        if (ODDS_DIR / f"odds_{slug}_{date_nd}_R{rno:02d}.json").exists()
    ) if not overwrite else 0
    need_fetch = total - existing

    print(f"対象: {len(venue_dates)}会場×日付 / {total}レース分")
    print(f"  取得済みスキップ: {existing}件  新規取得予定: {need_fetch}件\n")

    est_sec = need_fetch * (SAME_VENUE_WAIT + INTRA_RACE_WAIT * len(ODDS_TYPES)) / CONCURRENT_RACES
    est_h, est_rem = divmod(int(est_sec), 3600)
    est_m = est_rem // 60
    if est_h > 0:
        print(f"  推定所要時間: 約{est_h}時間{est_m}分（目安）\n")
    else:
        print(f"  推定所要時間: 約{est_m}分（目安）\n")

    if dry_run:
        print("【dry-run モード: 取得は行いません】\n")
        cur_date = None
        for venue_name, slug, date_nd, rno in tasks_info:
            d = f"{date_nd[:4]}-{date_nd[4:6]}-{date_nd[6:]}"
            exists = (ODDS_DIR / f"odds_{slug}_{date_nd}_R{rno:02d}.json").exists()
            if d != cur_date:
                print(f"  ── {d} ──")
                cur_date = d
            st = "SKIP " if (exists and not overwrite) else "FETCH"
            print(f"    [{st}] {venue_name} R{rno:02d}  → odds_{slug}_{date_nd}_R{rno:02d}.json")
        print(f"\n合計: {total}レース  スキップ: {existing}  取得: {need_fetch}")
        return

    ODDS_DIR.mkdir(exist_ok=True)

    race_sem    = asyncio.Semaphore(CONCURRENT_RACES)
    venue_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
    counter     = {"ok": 0, "partial": 0, "error": 0, "skip": 0}
    start_time  = time.time()
    completed   = 0
    lock_print  = asyncio.Lock()

    connector = aiohttp.TCPConnector(
        limit=CONCURRENT_RACES * len(ODDS_TYPES),
        ttl_dns_cache=300,
        force_close=False,
    )

    async with aiohttp.ClientSession(connector=connector, headers=dict(HEADERS)) as session:

        async def run_one(info: tuple) -> None:
            nonlocal completed
            venue_name, slug, date_nd, rno = info
            ok, skipped = await _fetch_race_async(
                session, race_sem, venue_locks,
                venue_name, slug, date_nd, rno,
                overwrite, counter,
            )
            completed += 1

            async with lock_print:
                done_actual = counter["ok"] + counter["partial"] + counter["error"]
                bar    = _progress_bar(completed, total)
                eta    = _format_eta(start_time, done_actual, need_fetch) if not skipped else ""
                counts = (f"✅{counter['ok']} ⚠{counter['partial']} "
                          f"❌{counter['error']} ⏭{counter['skip']}")

                if not skipped:
                    d_str = f"{date_nd[:4]}-{date_nd[4:6]}-{date_nd[6:]}"
                    st    = "✅" if ok else "⚠ 一部失敗"
                    print(
                        f"{bar}  [{completed:>4}/{total}]  {counts}\n"
                        f"  └─ {st} {venue_name} {d_str} R{rno:02d}  {eta}",
                        flush=True,
                    )
                elif counter["skip"] % 200 == 0:
                    print(
                        f"{bar}  [{completed:>4}/{total}]  {counts}  (スキップ中...)",
                        flush=True,
                    )

        await asyncio.gather(*[run_one(info) for info in tasks_info])

    elapsed = time.time() - start_time
    h, rem  = divmod(int(elapsed), 3600)
    m, s    = divmod(rem, 60)
    elapsed_str = f"{h}h{m:02d}m{s:02d}s" if h > 0 else f"{m}m{s:02d}s"

    print(f"\n{'='*62}")
    print(f"  完了!")
    print(f"  ✅ 成功: {counter['ok']}件  ⚠ 一部失敗: {counter['partial']}件  "
          f"❌ エラー: {counter['error']}件  ⏭ スキップ: {counter['skip']}件")
    print(f"  経過時間: {elapsed_str}  合計: {total}レース")
    print(f"{'='*62}\n")


# ─────────────────────────────────────────────────────────────────────────────
# エントリポイント
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="過去30日分のオッズを一括取得して odds_data/ に保存する（v2 高速化版）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  python fetch_odds_history.py             # 過去30日・全会場（差分のみ）
  python fetch_odds_history.py --days 7    # 過去7日に絞る
  python fetch_odds_history.py --dry-run   # 対象一覧だけ表示（取得しない）
  python fetch_odds_history.py --overwrite # 既存ファイルも上書き
        """,
    )
    parser.add_argument(
        "--days", type=int, default=HISTORY_DAYS,
        help=f"取得する過去日数（デフォルト: {HISTORY_DAYS}日）",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="取得せず対象レース一覧だけ表示する",
    )
    parser.add_argument(
        "--overwrite", action="store_true",
        help="既存ファイルがあっても上書き取得する",
    )
    args = parser.parse_args()

    asyncio.run(fetch_history_async(
        days=args.days,
        dry_run=args.dry_run,
        overwrite=args.overwrite,
    ))


if __name__ == "__main__":
    main()
