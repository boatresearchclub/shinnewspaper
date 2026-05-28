# -*- coding: utf-8 -*-
"""
scrape_program.py
=================
boatrace.jp の番組表ページからモーター2連対率を取得し、
当日の番組CSVに「モーター2連対率」列を追加して上書き保存する。

【lzh_to_csv.py との連携】
  lzh_to_csv.py が出力した番組CSVにモーター2連対率が含まれない場合、
  本スクリプトがそれを補完する。
  run_daily.py の STEP2.5 として lzh_to_csv の直後に実行する。

【単体実行】
  python scrape_program.py                    # 当日分
  python scrape_program.py --date 20260409    # 日付指定
  python scrape_program.py --venue 大村       # 1会場のみ
  python scrape_program.py --dry-run          # 取得内容を表示のみ

【出力】
  lzh_to_csv.py が生成した番組CSVに「モーター2連対率」列を追加して上書き。
  CSVが見つからない場合は motor_YYYYMMDD.csv として別途保存。

【依存ライブラリ】
  pip install requests beautifulsoup4 --break-system-packages
"""

import os, sys, time, argparse, csv, re
from datetime import datetime, timedelta
from pathlib import Path

try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from lr_config import VENUE_JCD_MAP, DATA_CSV_DIR
except ImportError:
    VENUE_JCD_MAP = {
        "桐生": "01", "戸田": "02", "江戸川": "03", "平和島": "04",
        "多摩川": "05", "浜名湖": "06", "蒲郡": "07", "常滑": "08",
        "津":   "09", "三国":  "10", "びわこ": "11", "住之江": "12",
        "尼崎": "13", "鳴門":  "14", "丸亀":  "15", "児島":  "16",
        "宮島": "17", "徳山":  "18", "下関":  "19", "若松":  "20",
        "芦屋": "21", "福岡":  "22", "唐津":  "23", "大村":  "24",
    }
    DATA_CSV_DIR = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data_csv"
    )

# ── 設定 ──────────────────────────────────────────────────────────────────
BASE_URL         = "https://www.boatrace.jp/owpc/pc/race"
PROGRAM_URL      = BASE_URL + "/racelist?jcd={jcd}&hd={hd}"
ENTRY_URL        = BASE_URL + "/raceentry?rno={rno}&jcd={jcd}&hd={hd}"
REQUEST_INTERVAL = 1.2
MAX_RACES        = 12
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; BoatraceResearcher/1.0)",
    "Accept-Language": "ja,en;q=0.9",
}

# モーター2連対率の列名（lr_calc.py の _motor2_raw 取得キーと一致させる）
MOTOR_COL = "モーター2連対率"


def _get(url, session, dry_run=False):
    if dry_run:
        print(f"  [DRY] {url}")
        return None
    try:
        resp = session.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        resp.encoding = "utf-8"
        time.sleep(REQUEST_INTERVAL)
        return resp.text
    except Exception as e:
        print(f"  [WARN] GET失敗: {url}  ({e})")
        return None


def parse_motor_rates(html, venue, race_no):
    """
    raceentry ページから各艇のモーター2連対率を取得する。

    Returns
    -------
    dict : {艇番(str): モーター2連対率(float)} 例 {"1": 42.5, "2": 38.0, ...}
    """
    if not html:
        return {}
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        motor_map = {}

        # 出走表テーブルを探す
        # boatrace.jp の出走表は class="is-fs12" などに選手・モーター情報が並ぶ
        for tbl in soup.find_all("table"):
            rows = tbl.find_all("tr")
            for row in rows:
                cells = row.find_all("td")
                if len(cells) < 4:
                    continue

                # 艇番を取得（1〜6）
                tei_text = cells[0].get_text(strip=True)
                if not re.match(r'^[1-6]$', tei_text):
                    continue

                # モーター2連対率を探す
                # 典型的な配置: 艇番 | 選手名 | ... | モーター番号 | モーター2連 | ボート番号 | ボート2連
                # セル内のテキストから "XX.XX%" 形式のパーセント値を抽出
                motor_rate = None
                for i, cell in enumerate(cells):
                    cell_text = cell.get_text(strip=True)
                    # "XX.XX" または "XX%" 形式を探す（モーター2連対率の典型値: 20〜65%）
                    m = re.search(r'(\d{2,3}\.\d{1,2})', cell_text)
                    if m:
                        val = float(m.group(1))
                        # モーター2連対率の妥当範囲: 15〜70%
                        if 15.0 <= val <= 70.0:
                            motor_rate = val
                            break

                if motor_rate is not None:
                    motor_map[tei_text] = motor_rate

        return motor_map

    except ImportError:
        print("  [ERROR] beautifulsoup4 が必要: pip install beautifulsoup4 --break-system-packages")
        return {}
    except Exception as e:
        print(f"  [WARN] モーター率パース失敗 {venue}{race_no}R: {e}")
        return {}


def scrape_day(target_date, venues=None, dry_run=False):
    """
    指定日の番組表からモーター2連対率を取得し、既存番組CSVに列を追加する。

    Parameters
    ----------
    target_date : str  'YYYYMMDD' 形式
    venues      : list[str] or None
    dry_run     : bool
    """
    try:
        import requests
        session = requests.Session()
    except ImportError:
        print("[ERROR] requests が必要: pip install requests --break-system-packages")
        sys.exit(1)

    target_venues = venues or list(VENUE_JCD_MAP.keys())
    dt = datetime.strptime(target_date, "%Y%m%d")

    print(f"\n[scrape_program] {target_date}  対象会場: {len(target_venues)}場")

    # 会場×レース×艇番のモーター2連対率を収集
    # motor_data[venue][race_no][tei] = rate
    motor_data: dict[str, dict[str, dict[str, float]]] = {}

    for venue in target_venues:
        jcd = VENUE_JCD_MAP.get(venue)
        if not jcd:
            continue

        # 開催確認
        prog_html = _get(PROGRAM_URL.format(jcd=jcd, hd=target_date), session, dry_run)
        if prog_html and "開催なし" in prog_html:
            continue

        motor_data[venue] = {}
        held = 0

        for rno in range(1, MAX_RACES + 1):
            html = _get(ENTRY_URL.format(rno=rno, jcd=jcd, hd=target_date), session, dry_run)
            rates = parse_motor_rates(html, venue, rno)
            if rates:
                motor_data[venue][str(rno)] = rates
                held += 1

        print(f"  {venue}({jcd}): {held}R分 取得")

    if dry_run:
        # dry_runの場合は取得内容を表示して終了
        for venue, races in motor_data.items():
            for rno, rates in races.items():
                print(f"  {venue} {rno}R: {rates}")
        return motor_data

    # 番組CSVへの書き込み
    # data_csv/ 内の当日番組CSV（形式: YYYYMMDD_program.csv or 日別CSVなど）を探して更新
    _update_program_csv(target_date, motor_data)
    return motor_data


def _update_program_csv(target_date, motor_data):
    """
    motor_data の内容を番組CSVの「モーター2連対率」列に書き込む。
    CSVが見つからない場合は motor_YYYYMMDD.csv として保存する。
    """
    # 番組CSVの候補パスを探索
    csv_candidates = [
        os.path.join(DATA_CSV_DIR, f"{target_date}_program.csv"),
        os.path.join(DATA_CSV_DIR, f"{target_date}.csv"),
    ]
    program_csv = next((p for p in csv_candidates if os.path.exists(p)), None)

    if program_csv:
        # 既存CSVにモーター2連対率列を追加
        rows = []
        try:
            with open(program_csv, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                fieldnames = list(reader.fieldnames or [])
                if MOTOR_COL not in fieldnames:
                    fieldnames.append(MOTOR_COL)
                for row in reader:
                    venue  = row.get("会場名", "")
                    rno    = str(int(row.get("レース番号", 0) or 0))
                    tei    = str(row.get("艇番", row.get("枠", "")))
                    rate   = motor_data.get(venue, {}).get(rno, {}).get(tei)
                    row[MOTOR_COL] = f"{rate:.1f}" if rate is not None else ""
                    rows.append(row)

            with open(program_csv, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(rows)

            filled = sum(1 for r in rows if r.get(MOTOR_COL))
            print(f"  番組CSV更新: {os.path.basename(program_csv)}  ({filled}/{len(rows)}艇にモーター率付与)")

        except Exception as e:
            print(f"  [WARN] 番組CSV更新失敗: {e}")

    else:
        # 番組CSVがない場合 → motor_YYYYMMDD.csv として単独保存
        out_path = os.path.join(DATA_CSV_DIR, f"motor_{target_date}.csv")
        os.makedirs(DATA_CSV_DIR, exist_ok=True)
        rows = []
        for venue, races in motor_data.items():
            for rno, rates in races.items():
                for tei, rate in rates.items():
                    rows.append({
                        "日付":           target_date,
                        "会場名":         venue,
                        "レース番号":     rno,
                        "艇番":           tei,
                        MOTOR_COL:        f"{rate:.1f}",
                    })
        if rows:
            with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=["日付","会場名","レース番号","艇番",MOTOR_COL])
                writer.writeheader()
                writer.writerows(rows)
            print(f"  motor CSV保存: {out_path}  ({len(rows)}行)")
        else:
            print("  [INFO] 取得データなし（開催なし or スクレイプ失敗）")


def main():
    parser = argparse.ArgumentParser(description="番組表からモーター2連対率を取得")
    parser.add_argument("--date",    default=None, help="取得日 YYYYMMDD（省略時: 当日）")
    parser.add_argument("--venue",   default=None, help="会場名（省略時: 全24会場）")
    parser.add_argument("--dry-run", action="store_true", help="表示のみ、保存しない")
    args = parser.parse_args()

    target_date = args.date or datetime.now().strftime("%Y%m%d")
    venues = [args.venue] if args.venue else None
    scrape_day(target_date, venues=venues, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
