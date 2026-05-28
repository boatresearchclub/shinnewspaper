"""
fetch_result.py  —  boatrace.jp から払戻結果を取得して JSON 保存
=================================================================
対象URL: https://www.boatrace.jp/owpc/pc/race/raceresult
         ?jcd={場コード}&hd={YYYYMMDD}&rno={R番号}

保存先: result_data/result_{venue}_{YYYYMMDD}_R{rno:02d}.json

JSON 構造:
    {
        "venue":       "芦屋",
        "venue_slug":  "ashiya",
        "date":        "20260507",
        "race":        1,
        "fetched_at":  "2026-05-07 12:34:56",
        "kimari":      "まくり差し",
        "henkan":      [5, 6],
        "tansho": [
            {"combo": "4", "odds": 810, "ninki": null}
        ],
        "sanrentan": [
            {"combo": "4-1-2", "odds": 4240, "ninki": 11}
        ],
        "nirentan": [
            {"combo": "4-1", "odds": 1920, "ninki": 6}
        ],
        "fukusho": [
            {"combo": "4", "odds": 140, "ninki": null},
            {"combo": "1", "odds": 100, "ninki": null}
        ]
    }

使い方:
    python fetch_result.py --venue ashiya --date 20260507 --race 1 --out ./result_data
    python fetch_result.py --venue ashiya --date 20260507 --all   --out ./result_data
"""

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("依存パッケージ不足: pip install requests beautifulsoup4")
    sys.exit(1)

# ── 会場スラッグ → 場コード（jcd）────────────────────
VENUE_JCD = {
    "kiryu":       "01", "toda":        "02", "edogawa":     "03",
    "heiwajima":   "04", "tamagawa":    "05", "hamanako":    "06",
    "gamagori":    "07", "tokoname":    "08", "tsu":         "09",
    "mikuni":      "10", "biwako":      "11", "suminoe":     "12",
    "amagasaki":   "13", "naruto":      "14", "marugame":    "15",
    "kojima":      "16", "miyajima":    "17", "tokuyama":    "18",
    "shimonoseki": "19", "wakamatsu":   "20", "ashiya":      "21",
    "fukuoka":     "22", "karatsu":     "23", "omura":       "24",
}

# 会場スラッグ → 日本語会場名（結果JSON用）
VENUE_JA = {
    "kiryu": "桐生", "toda": "戸田", "edogawa": "江戸川",
    "heiwajima": "平和島", "tamagawa": "多摩川", "hamanako": "浜名湖",
    "gamagori": "蒲郡", "tokoname": "常滑", "tsu": "津",
    "mikuni": "三国", "biwako": "びわこ", "suminoe": "住之江",
    "amagasaki": "尼崎", "naruto": "鳴門", "marugame": "丸亀",
    "kojima": "児島", "miyajima": "宮島", "tokuyama": "徳山",
    "shimonoseki": "下関", "wakamatsu": "若松", "ashiya": "芦屋",
    "fukuoka": "福岡", "karatsu": "唐津", "omura": "大村",
}

BASE_URL = "https://www.boatrace.jp/owpc/pc/race/raceresult"
HEADERS  = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "ja,en-US;q=0.9",
    "Referer": "https://www.boatrace.jp/owpc/pc/race/pay",
}


def fetch_html(url: str, params: dict, retry: int = 3) -> str | None:
    for i in range(retry):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=15)
            if r.status_code == 200:
                return r.text
            time.sleep(2)
        except Exception as e:
            print(f"  リクエストエラー ({i+1}/{retry}): {e}")
            time.sleep(3)
    return None


def parse_odds(text: str) -> int | None:
    """「¥1,230」「120円」→ 整数（円）。取得不可は None。"""
    if not text:
        return None
    cleaned = re.sub(r"[^\d]", "", text.strip())
    return int(cleaned) if cleaned else None


def parse_ninki(text: str) -> int | None:
    """人気順（整数）。空欄は None。"""
    if not text:
        return None
    cleaned = text.strip()
    return int(cleaned) if cleaned.isdigit() else None


def parse_raceresult_page(html: str) -> dict:
    """
    raceresult ページを全パース。
    返り値:
      {
        "kimari":    "まくり差し" or None,
        "henkan":    [5, 6] or [],
        "racetime":  "1'48\"0" or None,     # 1着タイム
        "fly":       [5, 6] or [],            # フライング艇番リスト
        "order": [                            # 着順（1〜6着・F・L・K）
            {"rank":"1","boat":4,"name":"渡辺千草","reg_no":"3175","time":"1'48\"0"},
            ...
        ],
        "start": [                            # スタートタイミング
            {"boat":1,"st":0.14,"fly":false},
            ...
        ],
        "tansho":    [{"combo":..., "odds":..., "ninki":...}, ...],
        "fukusho":   [...],
        "nirentan":  [...],
        "sanrentan": [...],
      }
    """
    soup = BeautifulSoup(html, "html.parser")
    result = {
        "kimari":    None,
        "henkan":    [],
        "racetime":  None,
        "fly":       [],
        "order":     [],
        "start":     [],
        "tansho":    [],
        "fukusho":   [],
        "nirentan":  [],
        "sanrentan": [],
        "cancelled": False,
    }

    # 中止・不成立の検出（払戻テーブルなしかつ中止キーワードあり）
    full_text = soup.get_text()
    if any(kw in full_text for kw in ("レース中止", "不成立", "中止")):
        result["cancelled"] = True
        return result

    tables = soup.find_all("table")

    for table in tables:
        text = table.get_text()

        # ── 着順テーブル（着・枠・ボートレーサー・レースタイム）──
        if "ボートレーサー" in text and "レースタイム" in text:
            for row in table.find_all("tr"):
                cells = [td.get_text(strip=True) for td in row.find_all("td")]
                if len(cells) < 3:
                    continue
                rank_raw = cells[0]  # "１","２",...,"Ｆ","Ｌ","Ｋ"
                boat_raw = cells[1]  # "4"
                name_raw = cells[2]  # "3175渡辺　千草"
                time_raw = cells[3] if len(cells) >= 4 else ""

                # 全角数字→半角
                rank = rank_raw.translate(str.maketrans("１２３４５６ＦＬＫ", "123456FLK"))

                boat_m = re.search(r"\d", boat_raw)
                boat = int(boat_m.group()) if boat_m else None

                # 登録番号と選手名を分離（先頭4桁が登録番号）
                name_m = re.match(r"(\d{4})\s*(.+)", name_raw)
                if name_m:
                    reg_no = name_m.group(1)
                    name   = name_m.group(2).replace("　", "").replace(" ", "")
                else:
                    reg_no = None
                    name   = name_raw.replace("　", "").replace(" ", "")

                if boat:
                    result["order"].append({
                        "rank":   rank,
                        "boat":   boat,
                        "name":   name,
                        "reg_no": reg_no,
                        "time":   time_raw or None,
                    })
                    # 1着のレースタイムを保存
                    if rank == "1" and time_raw:
                        result["racetime"] = time_raw
                    # フライング艇番を収集
                    if rank == "F" and boat:
                        result["fly"].append(boat)

        # ── スタート情報テーブル ──────────────────────
        elif "スタート情報" in text:
            for row in table.find_all("tr"):
                cells = [td.get_text(strip=True) for td in row.find_all("td")]
                for cell in cells:
                    if not cell or cell == "スタート情報":
                        continue
                    # "4.04　まくり差し" や "5F.01" などを処理
                    cell_clean = cell.split()[0]  # 決まり手テキストを除去
                    m = re.match(r"(\d)(F?)\.(\d{2})", cell_clean)
                    if m:
                        boat   = int(m.group(1))
                        is_fly = m.group(2) == "F"
                        st_val = float(f"0.{m.group(3)}")
                        result["start"].append({
                            "boat": boat,
                            "st":   st_val,
                            "fly":  is_fly,
                        })

        # ── 払戻テーブル ──────────────────────────────
        elif "勝式" in text and "組番" in text and "払戻金" in text:
            TYPE_MAP = {
                "3連単": "sanrentan",
                "3連複": None,
                "2連単": "nirentan",
                "2連複": None,
                "拡連複": None,
                "単勝":  "tansho",
                "複勝":  "fukusho",
            }
            current_type = None
            for row in table.find_all("tr"):
                cells = [td.get_text(strip=True) for td in row.find_all("td")]
                if not cells or cells[0] == "勝式":
                    continue
                if len(cells) == 4:
                    label = cells[0]
                    for keyword, key in TYPE_MAP.items():
                        if keyword in label:
                            current_type = key
                            break
                    combo_text, odds_text, ninki_text = cells[1], cells[2], cells[3]
                elif len(cells) == 3:
                    combo_text, odds_text, ninki_text = cells[0], cells[1], cells[2]
                else:
                    continue

                if not current_type:
                    continue

                combo_norm = re.sub(r"[＝=]", "=", combo_text).strip()
                if current_type in ("sanrentan", "nirentan"):
                    combo_norm = re.sub(r"[＝=＞>→\-－]", "-", combo_text).strip("-")

                odds_val  = parse_odds(odds_text)
                ninki_val = parse_ninki(ninki_text)
                if combo_norm and odds_val:
                    result[current_type].append({
                        "combo": combo_norm,
                        "odds":  odds_val,
                        "ninki": ninki_val,
                    })

        # ── 決まり手テーブル ──────────────────────────
        elif "決まり手" in text and result["kimari"] is None:
            for row in table.find_all("tr"):
                t = row.get_text(strip=True)
                if t and t != "決まり手":
                    result["kimari"] = t
                    break

        # ── 返還テーブル ──────────────────────────────
        elif "返還" in text and result["henkan"] == []:
            for row in table.find_all("tr"):
                t = row.get_text(strip=True)
                if t and t != "返還":
                    nums = [int(c) for c in t if c.isdigit() and 1 <= int(c) <= 6]
                    if nums:
                        result["henkan"] = nums
                    break

    return result


def fetch_result(venue_slug: str, date_nd: str, race_no: int, out_dir: Path) -> bool:
    """
    1レース分の払戻を取得して JSON 保存。
    Returns: True=成功, False=失敗 or データなし
    """
    jcd = VENUE_JCD.get(venue_slug)
    if not jcd:
        print(f"  未知の会場スラッグ: {venue_slug}")
        return False

    out_dir.mkdir(parents=True, exist_ok=True)
    fname = out_dir / f"result_{venue_slug}_{date_nd}_R{race_no:02d}.json"

    # 既存ファイルがあればスキップ（3連単が1件以上）
    if fname.exists():
        try:
            with open(fname, encoding="utf-8") as f:
                existing = json.load(f)
            if existing.get("sanrentan"):
                return True  # 取得済み
        except Exception:
            pass

    params = {"jcd": jcd, "hd": date_nd, "rno": str(race_no)}
    html = fetch_html(BASE_URL, params)
    if not html:
        print(f"  HTML取得失敗: {venue_slug} {date_nd} {race_no}R")
        return False

    pay_data = parse_raceresult_page(html)

    # 中止・不成立レース → フラグ付きファイルを保存して以降の取得を止める
    if pay_data.get("cancelled"):
        payload = {
            "venue":      VENUE_JA.get(venue_slug, venue_slug),
            "venue_slug": venue_slug,
            "date":       date_nd,
            "race":       race_no,
            "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "cancelled":  True,
            "sanrentan":  [],
        }
        with open(fname, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"  ✓ {venue_slug} {date_nd} {race_no}R → 中止レース（スキップ登録）")
        return True  # ファイルを作ったので次回以降スキップされる

    # 3連単が取れなければレース未確定（途中）
    if not pay_data["sanrentan"]:
        return False

    payload = {
        "venue":      VENUE_JA.get(venue_slug, venue_slug),
        "venue_slug": venue_slug,
        "date":       date_nd,
        "race":       race_no,
        "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        **pay_data,
    }

    with open(fname, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    san = pay_data["sanrentan"]
    combo_str = san[0]["combo"] if san else "?"
    odds_str  = f'{san[0]["odds"]:,}円' if san else "?"
    kimari    = pay_data.get("kimari") or ""
    henkan    = f' 返還:{pay_data["henkan"]}' if pay_data["henkan"] else ""
    print(f"  ✓ {venue_slug} {date_nd} {race_no}R → {combo_str} {odds_str} {kimari}{henkan}")
    return True


def fetch_all_races(venue_slug: str, date_nd: str, out_dir: Path,
                    max_race: int = 12) -> list[int]:
    """全レース（1〜max_race）を順次取得。成功したRno一覧を返す。"""
    done = []
    for rno in range(1, max_race + 1):
        ok = fetch_result(venue_slug, date_nd, rno, out_dir)
        if ok:
            done.append(rno)
        time.sleep(1.0)
    return done


# ── CLI ──────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="boatrace.jp 払戻スクレイパー")
    parser.add_argument("--venue", required=True, help="会場スラッグ (例: ashiya)")
    parser.add_argument("--date",  required=True, help="日付 YYYYMMDD")
    parser.add_argument("--race",  type=int,      help="レース番号 (--all と排他)")
    parser.add_argument("--all",   action="store_true", help="全レース取得")
    parser.add_argument("--out",   default=str(Path(__file__).parent / "result_data"), help="出力ディレクトリ")
    args = parser.parse_args()

    out_dir = Path(args.out)

    if args.all:
        done = fetch_all_races(args.venue, args.date, out_dir)
        print(f"完了: {len(done)}R取得")
        sys.exit(0 if done else 1)
    elif args.race:
        ok = fetch_result(args.venue, args.date, args.race, out_dir)
        sys.exit(0 if ok else 1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
