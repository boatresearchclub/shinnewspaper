"""
merge_odds.py — odds_data/ の個別JSONを data/odds_YYYYMMDD.json に統合
=======================================================================
【使い方】
  # 今日分を統合
  python merge_odds.py

  # 日付指定
  python merge_odds.py --date 2026-06-20

【動作】
  odds_data/odds_{slug}_{YYYYMMDD}_R{XX}.json を読み込み
  → data/odds_{YYYYMMDD}.json に以下の形式で書き出す

  {
    "常滑": { "1": {...}, "2": {...}, ... },
    "びわこ": { "1": {...}, ... },
    ...
  }

  renderer.js が ODDS_DATA[dateKey][venue][rno] 構造で読む仕様に合わせた形式。

【main_loop等からの呼び出し例】
  import subprocess
  subprocess.run(["python", "merge_odds.py"], check=True)
"""

import argparse
import json
import re
from datetime import date as date_cls
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent
ODDS_DIR    = SCRIPTS_DIR / "odds_data"
DATA_DIR    = SCRIPTS_DIR / "data"

# スラッグ → 会場名（fetch_odds.pyのVENUE_SLUGの逆引き）
SLUG_VENUE = {
    "kiryu": "桐生", "toda": "戸田", "edogawa": "江戸川",
    "heiwajima": "平和島", "tamagawa": "多摩川", "hamanako": "浜名湖",
    "gamagori": "蒲郡", "tokoname": "常滑", "tsu": "津",
    "mikuni": "三国", "biwako": "びわこ", "suminoe": "住之江",
    "amagasaki": "尼崎", "naruto": "鳴門", "marugame": "丸亀",
    "kojima": "児島", "miyajima": "宮島", "tokuyama": "徳山",
    "shimonoseki": "下関", "wakamatsu": "若松", "ashiya": "芦屋",
    "fukuoka": "福岡", "karatsu": "唐津", "omura": "大村",
}


def merge(date_nd: str) -> dict:
    """
    odds_data/odds_*_{date_nd}_R*.json を読み込んで統合dictを返す。
    戻り値: { 会場名: { レース番号(str): data } }
    """
    pattern = re.compile(rf"^odds_(.+)_{date_nd}_R(\d{{2}})\.json$")
    merged  = {}

    for fpath in sorted(ODDS_DIR.glob(f"odds_*_{date_nd}_R*.json")):
        m = pattern.match(fpath.name)
        if not m:
            continue
        slug = m.group(1)
        rno  = str(int(m.group(2)))  # "01" → "1"
        venue = SLUG_VENUE.get(slug, slug)  # 未知slugはそのまま使用

        try:
            with open(fpath, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"  [WARN] 読込失敗: {fpath.name}: {e}")
            continue

        if venue not in merged:
            merged[venue] = {}
        merged[venue][rno] = data

    return merged


def save(merged: dict, date_nd: str) -> Path:
    DATA_DIR.mkdir(exist_ok=True)
    out = DATA_DIR / f"odds_{date_nd}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, separators=(",", ":"))
    return out


def main():
    ap = argparse.ArgumentParser(description="odds_dataの個別JSONをdata/odds_YYYYMMDD.jsonに統合")
    ap.add_argument("--date", default=None, help="YYYY-MM-DD（省略時は今日）")
    args = ap.parse_args()

    date_str = args.date or date_cls.today().strftime("%Y-%m-%d")
    date_nd  = date_str.replace("-", "")

    print(f"[merge_odds] 対象日: {date_str}")
    merged = merge(date_nd)

    if not merged:
        print(f"  [WARN] {ODDS_DIR} に {date_nd} のファイルが見つかりませんでした")
        return

    venues = list(merged.keys())
    total  = sum(len(v) for v in merged.values())
    out    = save(merged, date_nd)
    print(f"  → {out}")
    print(f"  会場: {venues}")
    print(f"  合計: {total}レース分")


if __name__ == "__main__":
    main()
