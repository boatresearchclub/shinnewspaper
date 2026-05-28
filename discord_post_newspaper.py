"""
discord_post_newspaper.py
ボートリサーチ新聞PNG → Discord 各場チャンネルへ自動投稿

使い方:
    python discord_post_newspaper.py                        # 今日・即時投稿
    python discord_post_newspaper.py --time 08:30           # 今日・8:30に投稿
    python discord_post_newspaper.py --date 2026-03-30      # 日付指定・即時投稿
    python discord_post_newspaper.py --date 2026-03-30 --time 08:30  # 日付＋時間指定
    python discord_post_newspaper.py --dry-run              # 投稿せず確認のみ

必要ライブラリ:
    pip install requests
"""

import re
import time
import argparse
import requests
from datetime import datetime
from pathlib import Path

# ============================================================
# ★ 設定エリア（ここだけ編集すればOK）
# ============================================================

# PNGが入っている日付フォルダの親ディレクトリ
BASE_DIR = r"C:\Users\user\Pictures\ボートリサーチ新聞\ボートリサーチ新聞_出力"

# 各場チャンネルのWebhook URL
WEBHOOK_MAP = {
    "桐生":   "https://discord.com/api/webhooks/1487874724645179604/Gq3sfV2y3mhPcP1mBNfJxNZELQokLu-hZljT7YhAvmK-osZLj8GzVHW-9db6hfWvFuHi",
    "戸田":   "https://discord.com/api/webhooks/1487873881099337850/duuEiF-ap9fEw9yZM-x0KPlk1ZYuRutKvtihMtFNjKJ6G2toGqVoOg_t3jytBj6DdaDW",
    "江戸川": "https://discord.com/api/webhooks/1491966001011757179/iFKqoqGFK5CIOC4d35zGF05EL6X5TlB9C0iyEA6XtDyfMhJ4oFrFtGEZDLZxxgYVGG0X",
    "平和島": "https://discord.com/api/webhooks/1487874028403298306/2M86zAMDQDxyWgvLPr9RvWx_exRZdQyfWPx6vkIH8nq-kOIVkx5cERUGXyPoSHSiE_Zw",
    "多摩川": "https://discord.com/api/webhooks/1487874144983842939/JgFc_CRgSVehketBxgW6Y7tAntQWjmbm_CpqkxHr4U2TvbG3HdnfOFVqpajhaucsukD1",
    "浜名湖": "https://discord.com/api/webhooks/1487874239007559904/QfWxVPjqG1PgzTkQ_Ou9xEbT0XXaYZRir28LKl0j7y6c0qC9OaLrDhCEKvjttyzJtVIy",
    "蒲郡":   "https://discord.com/api/webhooks/1487874344515407935/F0VX-03l7vHZscO4DXr78hjHTzfgerDxUqhLKfluYLQZa14qrCLCfngU0lzYDGmFoWRC",
    "常滑":   "https://discord.com/api/webhooks/1487874451503714526/vMuBwPOTtbHVWPQoiN8kbIITYgy0N3ckBujbqRqn4ytmY16vqEfAe4DSsqy2UgZvwJeo",
    "津":     "https://discord.com/api/webhooks/1487874546941038693/CfjfzPRcAV7buCF84HedEbFcaAZxNxFigTQNa8e8eBB3dnWFHCxFKe0tnLg_6PDxbwvG",
    "三国":   "https://discord.com/api/webhooks/1487872846297301132/62vXOyYJmp8tguhGMinxoz2cXNd_MhdEnY2eZnTW7yqKJfF4Q1UmZ79261PirUtYo7_U",
    "びわこ": "https://discord.com/api/webhooks/1491965814801174760/7lvaVjOOPnyQMLJt_F_qi26xDDYmW_EVRQ_rVdoP1NSnqatay3reEFldLrzkD4B_nSSa",
    "住之江": "https://discord.com/api/webhooks/1487874744480170174/yEq6U41L9n8L2aMeTFRn6k-EIgHb-l27Hgk6QEzod9K2oXE9iBcv92muWNfip677jGlO",
    "尼崎":   "https://discord.com/api/webhooks/1487874880501186734/IRdEBfJARJan0ES4kBJbhJU2u9T1QZfcoXMkM3DH_F8eYfk0kmWHEtfPufVlVoATpy0R",
    "鳴門":   "https://discord.com/api/webhooks/1487874992887824522/dwHKiaJismuSxp5P68gh48e62Ol3Ro8AcDCzOYL7xszQzt6FuqneZHcPYVNunhkSXhzu",
    "丸亀":   "https://discord.com/api/webhooks/1487875263155933204/cu2LgP9wklYDzxEIskZ9IB6DfItOkkRyCtBnwCXxBf3vwVPPTKRypKSco1JifgX4o52E",
    "児島":   "https://discord.com/api/webhooks/1487875358127554771/kB-j1J8Gb8Mecjuey-ni04LtrIq3p3gXjxkvbvGX2Nbot9JW5uyeoI6NV0Z3xliRN29m",
    "宮島":   "https://discord.com/api/webhooks/1487875445650358324/ssfbZ4uDp7HOj34zdp_qRZJ0xdNezwvP-BYlV3ns_GM9dPPVi0l37SXYPqfPXvvOpZUM",
    "徳山":   "https://discord.com/api/webhooks/1487875553141719073/gR5WKYODwVvbpNmvxS21GIWd3hIQZpRbkwdX1KGs1RVcuI8itZczgvYYESuP9sYkjGFJ",
    "下関":   "https://discord.com/api/webhooks/1487875651804336270/bwTTxIzCDGKjewXW9E0YjhiLDh9SnLTs948qodfWNDcdGmm1T2UWaIdiBOZopuWpnPzu",
    "若松":   "https://discord.com/api/webhooks/1487875737359876217/LK_Cg1h1jI8gP2ftM4K7Osfmamqdb_a8SKAeNFBL15C39V7dH8hltxeNKxxFgvj_Y1uE",
    "芦屋":   "https://discord.com/api/webhooks/1487875832532832268/fZORiuNLZ11YuZgKcWKHTqbBc1gVDRtkRmFooG5jAnqFMO0ok3fgzNGiM78cCLeSl5bh",
    "福岡":   "https://discord.com/api/webhooks/1487875944852095037/PVVWYtfIQeG2eTyXFWApIvg-nHobGRpWMZ7YYBlxW9mZ4vBg2YbG2dxI2YO8tXyB3X5H",
    "唐津":   "https://discord.com/api/webhooks/1487876038678544495/kQ8EmA7unxZE6v67qFFuCfDwev-fh_Sgx3Fzc1GJerCsiHtVvLAmhEYAAO-czKO0-oF8",
    "大村":   "https://discord.com/api/webhooks/1487876145150955711/5dWUIckNWB4h53WvC7TvdRaMTIX6Bhh7nS0KKS91ApGON7oqgaFsj9R3osYpg9HDGLRr",
}

# 1投稿あたりの画像枚数
CHUNK_SIZE = 6

# 投稿間隔（秒）：Discord レート制限対策
POST_INTERVAL_SEC = 2.0

# ============================================================
# 時間待機
# ============================================================

def wait_until(target_time_str: str):
    """
    指定時刻（HH:MM）まで待機する
    例: "08:30" → 今日の8:30まで待つ
    """
    now = datetime.now()
    h, m = map(int, target_time_str.split(":"))
    target = now.replace(hour=h, minute=m, second=0, microsecond=0)

    if target <= now:
        print(f"⚠️ 指定時刻 {target_time_str} はすでに過ぎています。即時投稿します。")
        return

    wait_sec = (target - now).total_seconds()
    print(f"⏰ {target_time_str} まで待機中... （残り {int(wait_sec // 60)} 分 {int(wait_sec % 60)} 秒）")

    # 1分ごとに残り時間を表示
    while True:
        now = datetime.now()
        remaining = (target - now).total_seconds()
        if remaining <= 0:
            break
        if remaining > 60:
            time.sleep(60)
            remaining2 = (target - datetime.now()).total_seconds()
            print(f"   残り {int(remaining2 // 60)} 分 {int(remaining2 % 60)} 秒...")
        else:
            time.sleep(remaining)
            break

    print(f"✅ 時刻になりました。投稿を開始します。\n")

# ============================================================
# ファイル名パース
# ============================================================

def parse_filename(filename: str):
    """
    例: 芦屋_1R_20260330.png → ("芦屋", 1)
    戻り値: (venue_name, race_no) or None
    """
    stem = Path(filename).stem
    m = re.match(r"^(.+?)_(\d+)R_\d{8}$", stem)
    if m:
        return m.group(1), int(m.group(2))
    return None

# ============================================================
# Discord 投稿（複数画像まとめて）
# ============================================================

def post_images_to_discord(webhook_url: str, image_paths: list, content: str = "") -> bool:
    """
    複数画像を1投稿にまとめて送信（最大10枚）
    """
    try:
        opened = []
        files = {}
        for i, path in enumerate(image_paths):
            f = open(path, "rb")
            opened.append(f)
            files[f"files[{i}]"] = (path.name, f, "image/png")

        data = {"content": content} if content else {}
        resp = requests.post(webhook_url, files=files, data=data, timeout=30)

        for f in opened:
            f.close()

        if resp.status_code not in (200, 204):
            print(f"    ❌ HTTPエラー {resp.status_code}: {resp.text[:100]}")
            return False
        return True

    except Exception as e:
        print(f"    ❌ 送信エラー: {e}")
        return False

# ============================================================
# ファイル収集
# ============================================================

def collect_png_files(date_folder: Path) -> dict:
    """
    日付フォルダのPNGを場ごと・レース順に整理
    戻り値: {"芦屋": [(1, Path), (2, Path), ...], ...}
    """
    result = {}
    for f in sorted(date_folder.glob("*.png")):
        parsed = parse_filename(f.name)
        if parsed is None:
            print(f"  ⚠️ パース失敗（スキップ）: {f.name}")
            continue
        venue, race_no = parsed
        result.setdefault(venue, []).append((race_no, f))

    for venue in result:
        result[venue].sort(key=lambda x: x[0])

    return result

# ============================================================
# メイン投稿処理
# ============================================================

def run(date_str: str, dry_run: bool = False):
    date_folder = Path(BASE_DIR) / date_str

    if not date_folder.exists():
        print(f"❌ フォルダが見つかりません: {date_folder}")
        return

    print(f"📂 対象フォルダ: {date_folder}")
    venue_files = collect_png_files(date_folder)

    if not venue_files:
        print("⚠️ 投稿対象のPNGが見つかりませんでした。")
        return

    total_ok = 0
    total_ng = 0

    for venue, race_list in sorted(venue_files.items()):
        webhook_url = WEBHOOK_MAP.get(venue)

        if not webhook_url or "YOUR" in webhook_url:
            print(f"\n⚠️ [{venue}] Webhook未設定のためスキップ")
            continue

        print(f"\n🚤 [{venue}] {len(race_list)}枚を {CHUNK_SIZE}枚ずつ投稿")

        # CHUNK_SIZE枚ずつ分割
        chunks = [race_list[i:i+CHUNK_SIZE] for i in range(0, len(race_list), CHUNK_SIZE)]

        for chunk_idx, chunk in enumerate(chunks):
            paths = [img_path for _, img_path in chunk]
            labels = ", ".join(f"{r}R" for r, _ in chunk)

            # 1投稿目だけ日付を添える（例: 【3/30】）
            if chunk_idx == 0:
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                content = f"【{dt.month}/{dt.day}】"
            else:
                content = ""

            if dry_run:
                print(f"  [DRY-RUN] {labels} → {len(paths)}枚まとめて投稿{' 【日付付き】' if content else ''}")
                continue

            print(f"  📤 {labels} ({len(paths)}枚) ... ", end="", flush=True)
            ok = post_images_to_discord(webhook_url, paths, content=content)

            if ok:
                print("✅")
                total_ok += len(paths)
            else:
                total_ng += len(paths)

            time.sleep(POST_INTERVAL_SEC)

    if not dry_run:
        print(f"\n{'='*40}")
        print(f"✅ 成功: {total_ok}枚  ❌ 失敗: {total_ng}枚")

# ============================================================
# エントリーポイント
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ボートリサーチ新聞 Discord自動投稿")
    parser.add_argument(
        "--date",
        default=datetime.now().strftime("%Y-%m-%d"),
        help="対象日付 (例: 2026-03-30)。省略時は今日。",
    )
    parser.add_argument(
        "--time",
        default=None,
        help="投稿時刻 (例: 08:30)。省略時は即時投稿。",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="投稿せずにファイル一覧の確認のみ行う",
    )
    args = parser.parse_args()

    print(f"📰 ボートリサーチ新聞 Discord投稿スクリプト")
    print(f"   対象日付: {args.date}")
    if args.dry_run:
        print("   ※ DRY-RUNモード（実際には投稿しません）")
    print()

    # 時間指定（引数がなければ対話式で入力）
    post_time = args.time
    if not post_time and not args.dry_run:
        user_input = input("⏰ 投稿時刻を入力してください（例: 08:30）　即時投稿はそのままEnter: ").strip()
        if user_input:
            post_time = user_input

    if post_time:
        print(f"   投稿時刻: {post_time}")
    else:
        print(f"   投稿時刻: 即時")
    print()

    if post_time and not args.dry_run:
        wait_until(post_time)

    run(date_str=args.date, dry_run=args.dry_run)
