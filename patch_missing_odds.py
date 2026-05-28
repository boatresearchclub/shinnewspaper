"""
patch_missing_odds.py  —  取得漏れ・不完全オッズの補完ツール【非同期高速版】
=============================================================

【何をするか】
  odds_data/ にある全JSONを検査し、以下のいずれかに該当するレースを
  「補完対象」として再取得する。

  ① ファイルが存在しない（完全欠損）
  ② 種別ごとの件数が期待値の90%未満（部分欠損）
      3t: 120通り  3f: 20通り  2t: 30通り  2f: 15通り  tan: 6通り
  ③ "final": true フラグがない（確定オッズ未取得）
      ※ --check-final オプション指定時のみ対象にする

【速度】
  fetch_odds_history.py と同じ aiohttp 非同期方式を使用。
  欠損種別を複数レース並列で取得する（最大 CONCURRENT_RACES レース同時）。

【使い方】
  python patch_missing_odds.py --dry-run          # 欠損確認のみ
  python patch_missing_odds.py                    # 欠損を補完
  python patch_missing_odds.py --check-final      # finalフラグ未付与も補完
  python patch_missing_odds.py --venue 常滑 --date 20260520
  python patch_missing_odds.py --days 7

【必要ファイル】
  fetch_odds.py（同フォルダに配置）
  pip install aiohttp
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import aiohttp

# ── fetch_odds.py からインポート ─────────────────────────────────────────────
try:
    from fetch_odds import (
        ODDS_DIR,
        ODDS_TYPES,
        VENUE_JCD,
        VENUE_SLUG,
        SLUG_VENUE,
        HEADERS,
        _parse_odds_page,
        _save_odds,
    )
except ImportError:
    print("❌ fetch_odds.py が見つかりません。同じフォルダに置いてください。")
    raise SystemExit(1)

# ── 並列・待機設定（fetch_odds_history.py と同じ値） ─────────────────────────
CONCURRENT_RACES = 3      # 最大並列レース数
SAME_VENUE_WAIT  = 1.0    # 同一会場への連続リクエスト間隔（秒）
INTRA_RACE_WAIT  = 0.3    # 1レース内・種別間の最小ずらし間隔（秒）
RETRY_COUNT      = 2
RETRY_WAIT       = 5.0
FETCH_TIMEOUT    = 15

# ── 期待件数（90%以上で正常とみなす） ────────────────────────────────────────
EXPECTED_COUNT: dict[str, int] = {ot["key"]: ot["count"] for ot in ODDS_TYPES}
THRESHOLD = 0.90


# ─────────────────────────────────────────────────────────────────────────────
# 非同期 HTML フェッチ（fetch_odds_history.py と同実装）
# ─────────────────────────────────────────────────────────────────────────────

async def _fetch_html_async(session: aiohttp.ClientSession, url: str) -> str:
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
# 1レース・欠損種別を並列取得してマージ保存
# ─────────────────────────────────────────────────────────────────────────────

async def _patch_race_async(
    session: aiohttp.ClientSession,
    race_sem: asyncio.Semaphore,
    venue_locks: dict,
    info: dict,
    counter: dict,
) -> bool:
    """
    1レース分の欠損種別のみ非同期並列取得してマージ保存。
    Returns: True = 全欠損種別を取得成功
    """
    slug    = info["slug"]
    venue   = info["venue"]
    jcd     = info["jcd"]
    date_nd = info["date_nd"]
    rno     = info["rno"]
    missing = info["missing_keys"]  # 欠損している種別キーのリスト

    fpath = ODDS_DIR / f"odds_{slug}_{date_nd}_R{rno:02d}.json"

    # 取得対象の ODDS_TYPES エントリに絞る
    target_ots = [ot for ot in ODDS_TYPES if ot["key"] in missing]

    async with race_sem:
        lock = venue_locks[venue]
        async with lock:
            await asyncio.sleep(SAME_VENUE_WAIT)

            # 欠損種別を少しずつずらして並列発射
            coros = []
            for i, ot in enumerate(target_ots):
                async def _delayed(ot=ot, delay=i * INTRA_RACE_WAIT):
                    await asyncio.sleep(delay)
                    return await _fetch_one_odds_async(session, jcd, rno, date_nd, ot)
                coros.append(_delayed())

            results = await asyncio.gather(*coros, return_exceptions=True)

    # 既存JSONを読み込む（マージのため）
    existing: dict = {}
    if fpath.exists():
        try:
            with open(fpath, encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            existing = {}

    # 取得結果をマージ
    merged = dict(existing)
    fetch_ok = True
    for item in results:
        if isinstance(item, Exception) or not isinstance(item, tuple):
            fetch_ok = False
            continue
        key, data = item
        merged[key] = data
        if not data:
            fetch_ok = False

    merged["fetched_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 全種別揃っていたら final フラグを付与
    all_keys = {ot["key"] for ot in ODDS_TYPES}
    all_present = all(
        isinstance(merged.get(k), dict) and len(merged[k]) >= EXPECTED_COUNT[k] * THRESHOLD
        for k in all_keys
    )
    if all_present:
        merged["final"] = existing.get("final", False)  # 元の final を保持

    _save_odds(slug, date_nd, rno, merged)

    if fetch_ok:
        counter["ok"] += 1
    else:
        counter["partial"] += 1

    return fetch_ok


# ─────────────────────────────────────────────────────────────────────────────
# 欠損チェック
# ─────────────────────────────────────────────────────────────────────────────

def check_odds_file(fpath: Path, check_final: bool) -> list[str]:
    """欠損している種別キーのリストを返す。問題なければ空リスト。"""
    try:
        with open(fpath, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return [ot["key"] for ot in ODDS_TYPES]

    if check_final and not data.get("final"):
        return [ot["key"] for ot in ODDS_TYPES]

    missing = []
    for ot in ODDS_TYPES:
        key = ot["key"]
        odds_dict = data.get(key)
        if not isinstance(odds_dict, dict):
            missing.append(key)
            continue
        if len(odds_dict) < EXPECTED_COUNT[key] * THRESHOLD:
            missing.append(key)
    return missing


def _build_reason(fpath: Path, missing_keys: list[str], check_final: bool) -> str:
    """欠損理由の文字列を生成する"""
    try:
        with open(fpath, encoding="utf-8") as f:
            data = json.load(f)
        parts = []
        if check_final and not data.get("final"):
            parts.append("finalフラグなし")
        for k in missing_keys:
            d = data.get(k)
            if not isinstance(d, dict):
                parts.append(f"{k}=欠落")
            else:
                parts.append(f"{k}={len(d)}/{EXPECTED_COUNT[k]}件")
        return ", ".join(parts)
    except Exception:
        return "読み込みエラー"


# ─────────────────────────────────────────────────────────────────────────────
# 補完対象の収集
# ─────────────────────────────────────────────────────────────────────────────

def collect_missing(
    days: int,
    check_final: bool,
    filter_venue: Optional[str],
    filter_date: Optional[str],
) -> list[dict]:
    today  = datetime.now().date()
    cutoff = today - timedelta(days=days)

    # 既存ファイルから (slug, date_nd) の組み合わせを収集
    existing_combos: set[tuple[str, str]] = set()
    for fpath in ODDS_DIR.glob("odds_*.json"):
        m = re.match(r"odds_([a-z]+)_(\d{8})_R\d{2}\.json$", fpath.name)
        if not m:
            continue
        existing_combos.add((m.group(1), m.group(2)))

    missing_list: list[dict] = []

    for slug, date_nd in sorted(existing_combos):
        try:
            file_date = datetime.strptime(date_nd, "%Y%m%d").date()
        except ValueError:
            continue
        if file_date < cutoff or file_date >= today:
            continue
        if filter_date and date_nd != filter_date.replace("-", ""):
            continue

        venue = SLUG_VENUE.get(slug)
        if not venue:
            continue
        if filter_venue and venue != filter_venue:
            continue

        jcd = VENUE_JCD.get(venue)
        if not jcd:
            continue

        for rno in range(1, 13):
            fpath = ODDS_DIR / f"odds_{slug}_{date_nd}_R{rno:02d}.json"

            if not fpath.exists():
                missing_list.append({
                    "slug": slug, "venue": venue, "jcd": jcd,
                    "date_nd": date_nd, "rno": rno,
                    "missing_keys": [ot["key"] for ot in ODDS_TYPES],
                    "reason": "ファイルなし（完全欠損）",
                })
            else:
                missing_keys = check_odds_file(fpath, check_final)
                if missing_keys:
                    missing_list.append({
                        "slug": slug, "venue": venue, "jcd": jcd,
                        "date_nd": date_nd, "rno": rno,
                        "missing_keys": missing_keys,
                        "reason": _build_reason(fpath, missing_keys, check_final),
                    })

    return missing_list


# ─────────────────────────────────────────────────────────────────────────────
# 進捗表示
# ─────────────────────────────────────────────────────────────────────────────

def _progress_bar(done: int, total: int, width: int = 28) -> str:
    ratio  = done / total if total else 0
    filled = int(width * ratio)
    return f"[{'█' * filled}{'░' * (width - filled)}] {ratio*100:5.1f}%"


def _format_eta(start: float, done: int, total: int) -> str:
    if done <= 0:
        return ""
    elapsed = time.time() - start
    remain  = elapsed / done * (total - done)
    m, s    = divmod(int(max(remain, 0)), 60)
    speed   = done / elapsed * 60
    return f"残 約{m}m{s:02d}s  {speed:.1f}件/分"


# ─────────────────────────────────────────────────────────────────────────────
# サマリ表示
# ─────────────────────────────────────────────────────────────────────────────

def print_summary(missing_list: list[dict]) -> None:
    if not missing_list:
        print("\n✅ 欠損なし。補完対象レースは見つかりませんでした。\n")
        return

    print(f"\n{'='*64}")
    print(f"  補完対象: {len(missing_list)}レース")
    print(f"{'='*64}")

    cur_date = None
    for info in missing_list:
        d = f"{info['date_nd'][:4]}-{info['date_nd'][4:6]}-{info['date_nd'][6:]}"
        if d != cur_date:
            print(f"\n  ── {d} ──")
            cur_date = d
        print(
            f"    {info['venue']:6s} R{info['rno']:02d}  "
            f"[{', '.join(info['missing_keys'])}]  {info['reason']}"
        )

    key_count: dict[str, int] = {}
    for info in missing_list:
        for k in info["missing_keys"]:
            key_count[k] = key_count.get(k, 0) + 1
    print(f"\n  種別別欠損件数: " + "  ".join(f"{k}:{v}" for k, v in key_count.items()))
    print(f"{'='*64}\n")


# ─────────────────────────────────────────────────────────────────────────────
# メイン非同期処理
# ─────────────────────────────────────────────────────────────────────────────

async def patch_async(missing_list: list[dict]) -> None:
    total      = len(missing_list)
    counter    = {"ok": 0, "partial": 0}
    completed  = 0
    start_time = time.time()
    lock_print = asyncio.Lock()

    race_sem    = asyncio.Semaphore(CONCURRENT_RACES)
    venue_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    connector = aiohttp.TCPConnector(
        limit=CONCURRENT_RACES * len(ODDS_TYPES),
        ttl_dns_cache=300,
        force_close=False,
    )

    async with aiohttp.ClientSession(connector=connector, headers=dict(HEADERS)) as session:

        async def run_one(info: dict) -> None:
            nonlocal completed
            ok = await _patch_race_async(session, race_sem, venue_locks, info, counter)
            completed += 1

            async with lock_print:
                bar   = _progress_bar(completed, total)
                eta   = _format_eta(start_time, completed, total)
                date_str = f"{info['date_nd'][:4]}-{info['date_nd'][4:6]}-{info['date_nd'][6:]}"
                status = "✅" if ok else "⚠ 一部失敗"
                print(
                    f"{bar}  [{completed:>4}/{total}]  "
                    f"✅{counter['ok']} ⚠{counter['partial']}\n"
                    f"  └─ {status} {info['venue']} {date_str} R{info['rno']:02d}"
                    f"  [{', '.join(info['missing_keys'])}]  {eta}",
                    flush=True,
                )

        await asyncio.gather(*[run_one(info) for info in missing_list])

    elapsed = time.time() - start_time
    m, s    = divmod(int(elapsed), 60)
    print(f"\n{'='*64}")
    print(f"  完了!  ✅成功: {counter['ok']}件  ⚠一部失敗: {counter['partial']}件"
          f"  経過時間: {m}m{s:02d}s")
    print(f"{'='*64}\n")
    if counter["partial"] > 0:
        print("  ⚠ 失敗レースがあります。再度 --dry-run で確認してください。\n")


# ─────────────────────────────────────────────────────────────────────────────
# エントリポイント
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="取得漏れ・不完全オッズの補完ツール（非同期高速版）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  python patch_missing_odds.py --dry-run          # 欠損確認のみ
  python patch_missing_odds.py                    # 欠損を補完
  python patch_missing_odds.py --check-final      # finalフラグ未付与も補完
  python patch_missing_odds.py --venue 常滑 --date 20260520
  python patch_missing_odds.py --days 7
        """,
    )
    parser.add_argument("--dry-run",      action="store_true", help="取得せず欠損一覧だけ表示")
    parser.add_argument("--check-final",  action="store_true", help="finalフラグなしも補完対象にする")
    parser.add_argument("--venue",        default=None, help="会場名で絞り込み（例: 常滑）")
    parser.add_argument("--date",         default=None, help="日付で絞り込み（YYYYMMDD or YYYY-MM-DD）")
    parser.add_argument("--days",         type=int, default=30, help="対象にする過去日数（デフォルト: 30）")
    args = parser.parse_args()

    print(f"\n{'='*64}")
    print(f"  オッズ補完ツール【非同期高速版】")
    print(f"  対象: 過去{args.days}日 / 並列: {CONCURRENT_RACES}レース同時 / "
          f"finalチェック: {'あり' if args.check_final else 'なし'}")
    if args.venue:
        print(f"  会場フィルタ: {args.venue}")
    if args.date:
        print(f"  日付フィルタ: {args.date}")
    print(f"{'='*64}\n")

    print("🔍 欠損チェック中...", flush=True)
    missing_list = collect_missing(
        days=args.days,
        check_final=args.check_final,
        filter_venue=args.venue,
        filter_date=args.date,
    )

    print_summary(missing_list)

    if not missing_list or args.dry_run:
        if args.dry_run and missing_list:
            print("【dry-run モード: 取得は行いません】\n")
        return

    print(f"🔧 補完開始: {len(missing_list)}レース（最大{CONCURRENT_RACES}並列）\n")
    asyncio.run(patch_async(missing_list))


if __name__ == "__main__":
    main()
