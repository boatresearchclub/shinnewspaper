# -*- coding: utf-8 -*-
"""
hit_tracker.py  ─  的中率トラッキング

【機能】
  1. lr_log.py が出力した予想ログ（JSON）を読み込む              ← 従来
  2. 数値蓄積CSV（数値蓄積/{会場}.csv）の「買い目」列を読み込む  ← ★追加
  3. ボートリサーチ新聞_軽量版.xlsx の数値シートから買い目を取得 ← ★追加
  4. 結果CSV（公式LZH解析後のCSV）と突合して的中判定
  5. 当日分はboatrace.jp から着順をスクレイピングして補完
  6. hit_log.json を生成 → dashboard.html が読み込む

【使い方】
  # 全ソース統合（デフォルト）
  python hit_tracker.py

  # 数値蓄積CSVのみ
  python hit_tracker.py --source chikuseki

  # ボートリサーチ新聞_軽量版.xlsxのみ
  python hit_tracker.py --source excel

  # lr_log.py のJSONログのみ（従来通り）
  python hit_tracker.py --source lr_log

  # 当日のリアルタイム更新（スクレイピング込み）
  python hit_tracker.py --today

  # 特定日だけ再計算
  python hit_tracker.py --date 2026-04-10

  # 特定会場だけ
  python hit_tracker.py --venue 大村

【ファイル構成】
  hit_log.json                         ─ 出力（dashboardが読む）
  logs/prediction_log_*.json           ─ lr_log.py が出力した予想ログ
  csv_output/                          ─ 結果CSV（load_race.pyと同じ場所）
  数値蓄積/{会場}.csv                  ─ ★追加: 数値蓄積フォルダ
  ボートリサーチ新聞_軽量版.xlsx       ─ ★追加: 数値シートから買い目取得

【設定】
  スクリプト冒頭の CONFIG セクションでパスを調整してください。
"""

import os
import sys
import json
import glob
import re
import argparse
import pathlib
import logging
from datetime import datetime, date, timedelta

try:
    import requests
    from bs4 import BeautifulSoup
    SCRAPING_AVAILABLE = True
except ImportError:
    SCRAPING_AVAILABLE = False
    print("[!] requests / beautifulsoup4 がありません。pip install requests beautifulsoup4")

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False
    print("[!] pandas がありません。pip install pandas openpyxl")

# ════════════════════════════════════════════════════════════════════
# CONFIG  ─  パスをご自身の環境に合わせてください
# ════════════════════════════════════════════════════════════════════
_BASE = pathlib.Path(__file__).parent

CONFIG = {
    # 予想ログが置かれるフォルダ（lr_log.py の出力先）
    "log_dir":      _BASE.parent / "logs",

    # 結果CSV フォルダ（data_csv/YYYYMM_results.csv 形式）
    "csv_dir":      pathlib.Path(
        r"C:\Users\user\Desktop\データ収集\data_csv"
    ),

    # 払戻CSV フォルダ（data_csv/YYYYMM_payouts.csv 形式）
    # results.csv と同じフォルダに置いている場合は csv_dir と同じパスでOK
    "payout_dir":   pathlib.Path(
        r"C:\Users\user\Desktop\データ収集\data_csv"
    ),

    # ★追加: 数値蓄積フォルダ（会場名.csv が入っているフォルダ）
    # lr_config.py の CHIKUSEKI_DIR と同じパスに設定してください
    "chikuseki_dir": pathlib.Path(
        r"C:\Users\user\Desktop\データ収集\scripts\数値蓄積"
    ),

    # ★追加: ボートリサーチ新聞_軽量版.xlsx のパス
    "excel_file": pathlib.Path(
        r"C:\Users\user\Desktop\データ収集\ボートリサーチ新聞_軽量版.xlsx"
    ),

    # 出力先 JSON（dashboard.html と同じ場所に置く）
    "hit_log_path": _BASE / "hit_log.json",

    # 当日リアルタイム取得の対象会場コードマップ
    "venue_code": {
        "桐生": "01", "戸田": "02", "江戸川": "03", "平和島": "04",
        "多摩川": "05", "浜名湖": "06", "蒲郡": "07", "常滑": "08",
        "津":   "09", "三国": "10", "びわこ": "11", "住之江": "12",
        "尼崎": "13", "鳴門": "14", "丸亀": "15", "児島": "16",
        "宮島": "17", "徳山": "18", "下関": "19", "若松": "20",
        "芦屋": "21", "福岡": "22", "唐津": "23", "大村": "24",
    },
}
# ════════════════════════════════════════════════════════════════════


logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────
# 共通ユーティリティ
# ────────────────────────────────────────────────────────────────────

def _norm_combo(s: str) -> str:
    """1=2=3 / 1-2-3 / 123 を "1-2-3" に正規化"""
    s = str(s).strip().replace("=", "-").replace("/", "-").replace("\u3000", "")
    m = re.fullmatch(r"(\d)(\d)(\d)", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return s


def _parse_buy_list_pipe(buy_str: str) -> list[str]:
    """
    "1-2-3|1-3-2|2-1-3" のようなパイプ区切り文字列を
    ["1-2-3", "1-3-2", "2-1-3"] に変換する。
    """
    if not buy_str or str(buy_str).lower() in ("nan", "none", ""):
        return []
    return [_norm_combo(b) for b in str(buy_str).split("|") if b.strip()]


def _find_col(columns: list, *candidates) -> str | None:
    for c in candidates:
        if c in columns:
            return c
    return None


# ────────────────────────────────────────────────────────────────────
# ★追加: 数値蓄積CSV から買い目を読み込む
# ────────────────────────────────────────────────────────────────────

def load_predictions_from_chikuseki(
        chikuseki_dir: pathlib.Path,
        target_date: str = None,
        target_venue: str = None) -> list[dict]:
    """
    数値蓄積フォルダ内の {会場}.csv を読み込んで予想レコードを返す。

    CSVの主な列:
      日付, 会場, レース番号, 枠番, ..., 買い目, 買い目_全, 見送りフラグ, ...

    「買い目」列: "1-2-3|1-3-2|2-1-4" のようなパイプ区切り
    同一 (日付, 会場, レース番号) の先頭行のみ使用する（枠番行は重複するため）。
    """
    if not PANDAS_AVAILABLE:
        log.warning("pandas がないため数値蓄積CSVを読み込めません")
        return []

    if not chikuseki_dir.exists():
        log.warning(f"数値蓄積フォルダが見つかりません: {chikuseki_dir}")
        return []

    if target_venue:
        csv_files = list(chikuseki_dir.glob(f"{target_venue}.csv"))
    else:
        csv_files = list(chikuseki_dir.glob("*.csv"))

    if not csv_files:
        log.warning(f"数値蓄積CSVが見つかりません: {chikuseki_dir}")
        return []

    records = []
    for fpath in sorted(csv_files):
        try:
            df = pd.read_csv(fpath, encoding="utf-8-sig", dtype=str, low_memory=False)
        except Exception as e:
            log.warning(f"数値蓄積CSV読み込みエラー {fpath.name}: {e}")
            continue

        col_date  = _find_col(list(df.columns), "日付", "date", "DATE")
        col_venue = _find_col(list(df.columns), "会場", "venue", "VENUE")
        col_race  = _find_col(list(df.columns), "レース番号", "R", "race", "レースNo", "race_no")
        # 「買い目_全」を優先、なければ「買い目」を使う
        # 買い目_全 = 全点数（12点程度）、買い目 = 本線のみ（3〜4点）
        col_buy   = _find_col(list(df.columns), "買い目_全", "buy_list_all") \
                 or _find_col(list(df.columns), "買い目", "buy_list")
        # 「見送り推奨」= 実際に見送るか（0=買う, 1=見送り）
        # 「見送りフラグ」= システムが見送りを推奨しているか（常に1のため使わない）
        col_skip  = _find_col(list(df.columns), "見送り推奨", "skip")

        if not (col_date and col_race and col_buy):
            log.warning(f"必要な列(日付/レース番号/買い目)が見つかりません: {fpath.name}")
            continue

        venue_from_filename = fpath.stem  # "びわこ.csv" → "びわこ"

        key_cols = [c for c in [col_date, col_venue, col_race] if c]
        df_dedup = df.drop_duplicates(subset=key_cols, keep="first")

        for row in df_dedup.to_dict("records"):
            d = str(row.get(col_date, "")).replace("/", "-")[:10].strip()
            v = str(row.get(col_venue, venue_from_filename)).strip() if col_venue else venue_from_filename
            r = str(row.get(col_race, "")).strip()

            if not d or not r:
                continue
            if target_date and d != target_date:
                continue
            if target_venue and v != target_venue:
                continue

            buy_list = _parse_buy_list_pipe(row.get(col_buy, ""))

            skip_val = str(row.get(col_skip, "0")).strip() if col_skip else "0"
            # 買い目がある場合は見送り推奨が明示的に1のときだけスキップ
            is_skip  = (skip_val in ("1", "True", "true", "1.0")) and len(buy_list) == 0

            records.append({
                "date":     d,
                "venue":    v,
                "race":     r,
                "buy_list": buy_list,
                "skip":     is_skip,
                "source":   "chikuseki",
            })

    log.info(f"数値蓄積CSV: {len(records)}件 読み込み ({len(csv_files)}ファイル)")
    return records


# ────────────────────────────────────────────────────────────────────
# ★追加: ボートリサーチ新聞_軽量版.xlsx から買い目を読み込む
# ────────────────────────────────────────────────────────────────────

def load_predictions_from_excel(
        excel_path: pathlib.Path,
        target_date: str = None,
        target_venue: str = None) -> list[dict]:
    """
    ボートリサーチ新聞_軽量版.xlsx の「{会場}_数値」シートから買い目を読み込む。

    数値シートの構造:
      - A1セル: "ボートリサーチ数値データ　【会場名】　YYYY-MM-DD"  ← 日付・会場名を取得
      - 「買い目リスト（combo順・確率%）」行:
          C列〜N列（1R〜12R）に "1-2-3（4.6%）\n1-2-4（5.2%）..." が入っている
    """
    if not PANDAS_AVAILABLE:
        log.warning("pandas がないためExcelを読み込めません")
        return []

    if not excel_path.exists():
        log.warning(f"Excelファイルが見つかりません: {excel_path}")
        return []

    try:
        xl = pd.read_excel(excel_path, sheet_name=None, header=None, dtype=str)
    except Exception as e:
        log.warning(f"Excel読み込みエラー: {e}")
        return []

    records = []

    for sheet_name, df in xl.items():
        # "{会場}_数値" シートのみ対象
        if not sheet_name.endswith("_数値"):
            continue

        venue_from_sheet = sheet_name.replace("_数値", "")
        if target_venue and venue_from_sheet != target_venue:
            continue

        # A1セルから日付を取得
        # 例: "ボートリサーチ数値データ　【びわこ】　2026-04-11"
        header_cell = str(df.iloc[0, 0]) if len(df) > 0 else ""
        date_match  = re.search(r"(\d{4}-\d{2}-\d{2})", header_cell)
        sheet_date  = date_match.group(1) if date_match else ""

        if not sheet_date:
            log.debug(f"日付取得失敗: {sheet_name}")
            continue
        if target_date and sheet_date != target_date:
            continue

        # 「買い目リスト」行を探す（B列に該当キーワード）
        buy_list_row_idx = None
        for i, row in df.iterrows():
            cell_b = str(row.iloc[1]) if len(row) > 1 else ""
            if "買い目リスト" in cell_b or "買い目候補" in cell_b:
                buy_list_row_idx = i
                break

        if buy_list_row_idx is None:
            log.debug(f"買い目行が見つかりません: {sheet_name}")
            continue

        # C列以降（列インデックス2〜13）が 1R〜12R
        buy_row = df.iloc[buy_list_row_idx]
        for race_no in range(1, 13):
            col_idx = race_no + 1  # C列=2から
            if col_idx >= len(buy_row):
                continue

            cell_val = str(buy_row.iloc[col_idx])
            if cell_val.lower() in ("nan", "none", ""):
                continue

            # "1-2-3（4.6%）\n1-2-4（5.2%）..." から組み合わせだけ抽出
            combos   = re.findall(r"(\d-\d-\d)", cell_val)
            buy_list = [_norm_combo(c) for c in combos]

            records.append({
                "date":     sheet_date,
                "venue":    venue_from_sheet,
                "race":     str(race_no),
                "buy_list": buy_list,
                "skip":     len(buy_list) == 0,
                "source":   "excel",
            })

    log.info(f"Excel: {len(records)}件 読み込み")
    return records


# ────────────────────────────────────────────────────────────────────
# 予想ログ読み込み（従来: lr_log.py の出力）
# ────────────────────────────────────────────────────────────────────

def load_prediction_logs(log_dir: pathlib.Path,
                          target_date: str = None,
                          target_venue: str = None) -> list[dict]:
    """lr_log.py が出力した予想ログを読み込む（従来通り）"""
    records = []

    if not log_dir.exists():
        log.warning(f"予想ログが見つかりません: {log_dir}")
        return records

    files = sorted(log_dir.glob("*.json"))
    if not files:
        log.warning(f"予想ログが見つかりません: {log_dir}")
        return records

    for fpath in files:
        try:
            with open(fpath, encoding="utf-8") as f:
                log_data = json.load(f)
        except Exception as e:
            log.warning(f"予想ログ読み込みエラー {fpath.name}: {e}")
            continue

        if isinstance(log_data, list):
            stem = fpath.stem
            parts = stem.split("_", 1)
            file_date  = parts[0] if len(parts) >= 1 else ""
            file_venue = parts[1] if len(parts) >= 2 else ""
            for row in log_data:
                if not isinstance(row, dict):
                    continue
                d = str(row.get("date", file_date)).replace("/", "-")[:10].strip()
                v = str(row.get("venue", file_venue)).strip()
                r = str(row.get("race", row.get("race_no", ""))).strip()
                buy_list = [_norm_combo(b) for b in row.get("buy_list", [])]
                if not d or not v or not r:
                    continue
                if target_date and d != target_date:
                    continue
                if target_venue and v != target_venue:
                    continue
                records.append({
                    "date": d, "venue": v, "race": r,
                    "buy_list": buy_list,
                    "skip": len(buy_list) == 0,
                    "manual_result_1st": row.get("result_1st"),
                    "manual_result_2nd": row.get("result_2nd"),
                    "manual_result_3rd": row.get("result_3rd"),
                    "manual_hit": row.get("hit"),
                    "source": "lr_log",
                })
            continue

        v = str(log_data.get("venue", "")).strip()
        d = str(log_data.get("date",  "")).replace("/", "-")[:10].strip()
        if not d or not v:
            continue
        if target_date and d != target_date:
            continue
        if target_venue and v != target_venue:
            continue

        for race in log_data.get("races", []):
            r        = str(race.get("race_no", "")).strip()
            buy_list = [_norm_combo(b) for b in race.get("buy_list", [])]
            skip     = len(buy_list) == 0
            if not r:
                continue
            records.append({
                "date":  d, "venue": v, "race": r,
                "buy_list":  buy_list, "skip": skip,
                "manual_result_1st": race.get("result_1st"),
                "manual_result_2nd": race.get("result_2nd"),
                "manual_result_3rd": race.get("result_3rd"),
                "manual_hit":        race.get("hit"),
                "source": "lr_log",
            })

    log.info(f"予想ログ: {len(records)}件 読み込み ({len(files)}ファイル)")
    return records


# ────────────────────────────────────────────────────────────────────
# 結果CSV 読み込み
# ────────────────────────────────────────────────────────────────────

# ── YYYYMM_payouts.csv のキャッシュ ──────────────────────────────────
_PAYOUTS_CACHE: dict[str, dict] = {}  # key: "YYYYMM" → {(日付, 会場名, レース番号): 払戻金}


def _load_monthly_payouts(payout_dir: pathlib.Path, yyyymm: str) -> dict:
    """
    YYYYMM_payouts.csv を読んで
    {(日付, 会場名, レース番号): 払戻金(int)} の辞書を返す。
    対象券種: '３連単'
    組み合わせ列の先頭 ' はExcel対策のもので除去する。
    """
    if yyyymm in _PAYOUTS_CACHE:
        return _PAYOUTS_CACHE[yyyymm]

    fpath = payout_dir / f"{yyyymm}_payouts.csv"
    result = {}

    if not fpath.exists():
        log.debug(f"払戻CSVが見つかりません: {fpath}")
        _PAYOUTS_CACHE[yyyymm] = result
        return result

    try:
        import pandas as _pd
        df = _pd.read_csv(fpath, encoding="utf-8-sig", dtype=str)

        # 列名の候補を正規化（前後空白除去）
        df.columns = [c.strip() for c in df.columns]

        col_date   = _find_col(list(df.columns), "日付", "date")
        col_venue  = _find_col(list(df.columns), "会場名", "会場", "venue")
        col_race   = _find_col(list(df.columns), "レース番号", "R", "race")
        col_type   = _find_col(list(df.columns), "券種", "type")
        col_payout = _find_col(list(df.columns), "払戻金", "払戻", "payout")

        if not all([col_date, col_venue, col_race, col_type, col_payout]):
            log.warning(f"払戻CSV: 必要な列が見つかりません ({fpath.name})")
            _PAYOUTS_CACHE[yyyymm] = result
            return result

        # ３連単のみ抽出
        df_san = df[df[col_type].str.strip() == "３連単"].copy()

        for row in df_san.to_dict("records"):
            d = str(row[col_date]).strip().replace("/", "-")[:10]
            v = str(row[col_venue]).strip()
            r = str(row[col_race]).strip()
            # 払戻金: カンマ除去・先頭 ' 除去・整数化
            pay_str = str(row[col_payout]).strip().lstrip("'").replace(",", "")
            try:
                payout = int(float(pay_str))
            except (ValueError, TypeError):
                continue
            result[(d, v, r)] = payout

        log.info(f"払戻CSV読み込み: {fpath.name} ({len(result)}レース分の３連単払戻)")
    except Exception as e:
        log.warning(f"払戻CSV読み込みエラー {fpath}: {e}")

    _PAYOUTS_CACHE[yyyymm] = result
    return result


# ── data_csv の結果キャッシュ（月別CSVを何度も読まないよう保持）──────────
_RESULTS_CACHE: dict[str, dict] = {}  # key: "YYYYMM" → {(会場名,レース番号,日付): combo}


def _load_monthly_results(csv_dir: pathlib.Path, yyyymm: str) -> dict:
    """
    data_csv/YYYYMM_results.csv を読んで
    {(日付, 会場名, レース番号): {"combo": "1-2-3", "payout": 1234}} の辞書を返す。
    一度読んだ月はキャッシュする。

    払戻列の候補: "三連単払戻", "払戻金", "払戻", "payout", "三連単", "3連単払戻"
    """
    if yyyymm in _RESULTS_CACHE:
        return _RESULTS_CACHE[yyyymm]

    fpath = csv_dir / f"{yyyymm}_results.csv"
    result = {}

    if not fpath.exists():
        _RESULTS_CACHE[yyyymm] = result
        return result

    try:
        import pandas as _pd
        df = _pd.read_csv(fpath, encoding="utf-8-sig", dtype=str)

        # 払戻列を探す
        payout_col = _find_col(
            list(df.columns),
            "三連単払戻", "払戻金", "払戻", "payout",
            "三連単", "3連単払戻", "trifecta_payout",
        )

        # 着順1〜3だけ抽出してpivot（着順, 艇番）
        df_rank = df[df["着順"].isin(["1", "2", "3"])].copy()
        df_rank["着順"] = df_rank["着順"].astype(int)
        pv = df_rank.pivot_table(
            index=["日付", "会場名", "レース番号"],
            columns="着順",
            values="艇番",
            aggfunc="first",
        )
        pv.columns = [f"r{c}" for c in pv.columns]
        pv = pv.reset_index()

        # 払戻を同インデックスで取得（1着行を代表として使用）
        if payout_col:
            df_pay = df[df["着順"] == "1"][["日付", "会場名", "レース番号", payout_col]].copy()
            df_pay = df_pay.rename(columns={payout_col: "payout"})
            pv = pv.merge(df_pay, on=["日付", "会場名", "レース番号"], how="left")

        for row in pv.to_dict("records"):
            key = (str(row["日付"]).strip(),
                   str(row["会場名"]).strip(),
                   str(row["レース番号"]).strip())
            combo = f"{row.get('r1','')}-{row.get('r2','')}-{row.get('r3','')}"
            if "-" not in combo.replace(combo.replace("-",""), ""):
                continue
            # 払戻金（100円あたり。なければNone）
            payout = None
            if payout_col and "payout" in row:
                try:
                    payout = int(float(str(row["payout"]).replace(",", "")))
                except (ValueError, TypeError):
                    payout = None
            result[key] = {"combo": combo, "payout": payout}

        log.info(f"結果CSV読み込み: {fpath.name} ({len(result)}レース)"
                 + (f" ※払戻列='{payout_col}'" if payout_col else " ※払戻列なし"))
    except Exception as e:
        log.warning(f"結果CSV読み込みエラー {fpath}: {e}")

    _RESULTS_CACHE[yyyymm] = result
    return result


def load_result_csv(csv_dir: pathlib.Path,
                    venue: str, date_str: str) -> dict[str, dict]:
    """
    data_csv/YYYYMM_results.csv から指定会場・日付の
    {race_no: {"combo": "1-2-3", "payout": 1234}} 辞書を返す。
    payout は 100円あたりの払戻金額（列がなければ None）。
    """
    yyyymm = date_str[:7].replace("-", "")  # "2026-03-21" → "202603"
    monthly = _load_monthly_results(csv_dir, yyyymm)

    result = {}
    for (d, v, r), val in monthly.items():
        if d == date_str and v == venue:
            result[str(r)] = val
    return result


# ────────────────────────────────────────────────────────────────────
# boatrace.jp スクレイピング（当日リアルタイム）
# ────────────────────────────────────────────────────────────────────

def fetch_result_from_web(venue: str, date_str: str,
                           venue_code_map: dict) -> dict[str, str]:
    """boatrace.jp から {race_no: "1-2-3"} を取得する。"""
    if not SCRAPING_AVAILABLE:
        return {}

    jcd = venue_code_map.get(venue)
    if not jcd:
        log.warning(f"会場コード不明: {venue}")
        return {}

    date_compact = date_str.replace("-", "")
    results = {}
    headers = {"User-Agent": "Mozilla/5.0 (compatible; HitTracker/1.0)"}

    for race_no in range(1, 13):
        url = (
            f"https://www.boatrace.jp/owpc/pc/race/raceresult"
            f"?rno={race_no}&jcd={jcd}&hd={date_compact}"
        )
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")

            rank_cells = soup.select("table.is-w748 tbody tr td.is-fs14")
            if not rank_cells or len(rank_cells) < 3:
                rank_rows = soup.select(".table1 tbody tr")
                nums = []
                for row in rank_rows[:3]:
                    cells = row.find_all("td")
                    if cells:
                        txt = cells[0].get_text(strip=True)
                        if txt.isdigit():
                            nums.append(txt)
                if len(nums) >= 3:
                    results[str(race_no)] = {"combo": f"{nums[0]}-{nums[1]}-{nums[2]}", "payout": None}
            else:
                nums = [c.get_text(strip=True) for c in rank_cells[:3]]
                if len(nums) >= 3 and all(n.isdigit() for n in nums):
                    results[str(race_no)] = {"combo": f"{nums[0]}-{nums[1]}-{nums[2]}", "payout": None}

        except Exception as e:
            log.debug(f"スクレイピングエラー {venue} {race_no}R: {e}")
            continue

    log.info(f"Web取得: {venue} {date_str} → {len(results)}R")
    return results


# ────────────────────────────────────────────────────────────────────
# 的中判定
# ────────────────────────────────────────────────────────────────────

def judge_hit(buy_list: list[str], result_combo: str) -> bool:
    """buy_list に result_combo が含まれていれば的中"""
    if not result_combo or not buy_list:
        return False
    norm = _norm_combo(result_combo)
    return norm in [_norm_combo(b) for b in buy_list]


# ────────────────────────────────────────────────────────────────────
# hit_log.json 生成
# ────────────────────────────────────────────────────────────────────

def build_hit_log(predictions: list[dict],
                  csv_dir: pathlib.Path,
                  venue_code_map: dict,
                  fetch_web: bool = False,
                  payout_dir: pathlib.Path = None) -> list[dict]:
    """予想リストと結果を突合して hit_log レコードを返す"""

    _result_cache: dict[tuple, dict] = {}
    _payout_cache: dict[str, dict]   = {}  # key: yyyymm → {(日付,会場,レース): 払戻金}

    def get_results(date_str, venue):
        key = (date_str, venue)
        if key not in _result_cache:
            res = load_result_csv(csv_dir, venue, date_str)
            today = date.today().strftime("%Y-%m-%d")
            if not res and fetch_web and date_str == today:
                res = fetch_result_from_web(venue, date_str, venue_code_map)
            _result_cache[key] = res
        return _result_cache[key]

    def get_payout(date_str, venue, race):
        """YYYYMM_payouts.csv から３連単払戻金を取得する"""
        if payout_dir is None:
            return None
        yyyymm = date_str[:7].replace("-", "")
        if yyyymm not in _payout_cache:
            _payout_cache[yyyymm] = _load_monthly_payouts(payout_dir, yyyymm)
        return _payout_cache[yyyymm].get((date_str, venue, str(race)))

    BET_UNIT = 100  # 1点あたりの賭け金（円）

    records = []
    for pred in predictions:
        d, v, r = pred["date"], pred["venue"], pred["race"]

        m1 = pred.get("manual_result_1st")
        m2 = pred.get("manual_result_2nd")
        m3 = pred.get("manual_result_3rd")

        if m1 and m2 and m3:
            result_combo = f"{m1}-{m2}-{m3}"
            result_known = True
            manual_hit   = pred.get("manual_hit")
            hit = manual_hit if manual_hit is not None else judge_hit(pred["buy_list"], result_combo)
            payout = None  # 手動入力時は払戻不明
        else:
            results      = get_results(d, v)
            race_val     = results.get(str(r))
            # 新形式 {"combo":..., "payout":...} と旧形式 "1-2-3" の両対応
            if isinstance(race_val, dict):
                result_combo = race_val.get("combo", "")
                payout_from_results = race_val.get("payout")
            else:
                result_combo = race_val or ""
                payout_from_results = None
            result_known = bool(result_combo)
            hit = False if pred["skip"] else judge_hit(pred["buy_list"], result_combo)

            # 払戻: payouts.csv を優先、なければ results.csv のものを使う
            payout = get_payout(d, v, r)
            if payout is None:
                payout = payout_from_results

        buy_count = len(pred["buy_list"])
        invest    = buy_count * BET_UNIT  # 投資額（円）

        # 回収額・回収率
        if hit and payout is not None:
            # 払戻は「100円あたり」なので BET_UNIT/100 を掛ける
            returns     = int(payout * BET_UNIT / 100)
            roi_pct     = round(returns / invest * 100, 1) if invest > 0 else None
        elif pred["skip"] or not result_known:
            returns     = None
            roi_pct     = None
        else:
            # 外れ or 払戻データなし
            returns     = 0 if result_known else None
            roi_pct     = 0.0 if (result_known and invest > 0) else None

        records.append({
            "date":         d,
            "venue":        v,
            "race":         r,
            "buy_list":     pred["buy_list"],
            "buy_count":    buy_count,
            "result":       result_combo,
            "hit":          hit,
            "skip":         pred["skip"],
            "result_known": result_known,
            "source":       pred.get("source", "unknown"),
            # ── 回収率関連 ─────────────────────────────
            "invest":       invest if not pred["skip"] else 0,   # 投資額（円）
            "returns":      returns,   # 回収額（円）。データなし=None
            "roi_pct":      roi_pct,   # 回収率(%)。データなし=None
            "payout":       payout,    # 払戻金（100円あたり）。データなし=None
        })

    return records


def save_hit_log(records: list[dict], path: pathlib.Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "last_updated": datetime.now().isoformat(timespec="seconds"),
        "records":      records,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(f"hit_log.json を保存しました: {path} ({len(records)}件)")


# ────────────────────────────────────────────────────────────────────
# メイン
# ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="的中率トラッキング")
    parser.add_argument("--today",  action="store_true", help="当日のみ（Web取得あり）")
    parser.add_argument("--date",   type=str, default=None, help="特定日 (例: 2026-04-10)")
    parser.add_argument("--venue",  type=str, default=None, help="特定会場 (例: 大村)")
    parser.add_argument("--web",    action="store_true", help="強制的にWeb取得も実行")
    parser.add_argument(
        "--source",
        type=str, default="chikuseki",
        choices=["lr_log", "chikuseki", "excel", "all"],
        help=(
            "買い目の読み込みソース (デフォルト: all)\n"
            "  lr_log    : lr_log.py が出力したJSONログ（従来）\n"
            "  chikuseki : 数値蓄積フォルダの {会場}.csv\n"
            "  excel     : ボートリサーチ新聞_軽量版.xlsx の数値シート\n"
            "  all       : 上記すべてを統合（重複時は chikuseki > excel > lr_log を優先）"
        )
    )
    args = parser.parse_args()

    target_date  = args.date or (date.today().strftime("%Y-%m-%d") if args.today else None)
    target_venue = args.venue
    fetch_web    = args.today or args.web
    source       = args.source

    log_dir       = CONFIG["log_dir"]
    csv_dir       = CONFIG["csv_dir"]
    payout_dir    = CONFIG.get("payout_dir", CONFIG["csv_dir"])
    chikuseki_dir = CONFIG["chikuseki_dir"]
    excel_file    = CONFIG["excel_file"]
    out_path      = CONFIG["hit_log_path"]

    # ── 買い目読み込み ────────────────────────────────────────────────
    predictions = []

    if source in ("lr_log", "all"):
        predictions.extend(load_prediction_logs(log_dir, target_date, target_venue))

    if source in ("chikuseki", "all"):
        predictions.extend(load_predictions_from_chikuseki(chikuseki_dir, target_date, target_venue))

    if source in ("excel", "all"):
        predictions.extend(load_predictions_from_excel(excel_file, target_date, target_venue))

    # ── 重複排除（同じ日付・会場・レースが複数ソースにある場合）────────
    # 優先順位: chikuseki > excel > lr_log
    _SOURCE_PRIORITY = {"chikuseki": 0, "excel": 1, "lr_log": 2, "unknown": 3}
    seen: dict[tuple, dict] = {}
    for pred in predictions:
        key = (pred["date"], pred["venue"], pred["race"])
        if key not in seen:
            seen[key] = pred
        else:
            ep = _SOURCE_PRIORITY.get(seen[key].get("source", "unknown"), 99)
            np = _SOURCE_PRIORITY.get(pred.get("source", "unknown"), 99)
            if np < ep:
                seen[key] = pred
    predictions = list(seen.values())

    if not predictions:
        print("[!] 買い目データが見つかりませんでした。")
        print(f"    --source で読み込みソースを確認してください（現在: {source}）")
        print(f"    lr_log    : {log_dir}")
        print(f"    chikuseki : {chikuseki_dir}")
        print(f"    excel     : {excel_file}")
        print("\n  → デモ用サンプルデータで hit_log.json を生成します")
        predictions = _make_demo_predictions()

    log.info(f"合計予想レコード: {len(predictions)}件（重複排除後）")

    # ── 結果と突合 ────────────────────────────────────────────────────
    records = build_hit_log(predictions, csv_dir, CONFIG["venue_code"], fetch_web, payout_dir)

    # ── 既存 hit_log.json とマージ（新データで上書き＋追記）───────────
    # 今回読み込んだレコードを優先し、既存にしかないレコードは保持する
    if out_path.exists() and not (args.today or args.date):
        try:
            existing = json.loads(out_path.read_text(encoding="utf-8"))
            new_map = {
                (r["date"], r["venue"], r["race"]): r
                for r in records
            }
            only_in_existing = [
                r for r in existing.get("records", [])
                if (r["date"], r["venue"], r["race"]) not in new_map
            ]
            merged = only_in_existing + records
            updated = len(existing.get("records", [])) - len(only_in_existing)
            added   = len(records) - updated
            log.info(f"更新: {updated}件 / 新規追加: {added}件 / 合計: {len(merged)}件")
            records = merged
        except Exception as e:
            log.warning(f"既存 hit_log.json のマージに失敗（上書き）: {e}")

    save_hit_log(records, out_path)


def _make_demo_predictions() -> list[dict]:
    """動作確認用のサンプル予想データ"""
    import random
    random.seed(42)
    venues = ["大村", "桐生", "住之江", "蒲郡", "戸田"]
    records = []
    today = date.today()
    for day_offset in range(30):
        d = (today - timedelta(days=day_offset)).strftime("%Y-%m-%d")
        v = random.choice(venues)
        for r in range(1, 13):
            buy_list = []
            n_bets = random.randint(3, 8)
            used = set()
            for _ in range(n_bets):
                combo = f"{random.randint(1,4)}-{random.randint(1,6)}-{random.randint(1,6)}"
                parts = combo.split("-")
                if len(set(parts)) == 3 and combo not in used:
                    buy_list.append(combo)
                    used.add(combo)
            is_hit  = random.random() < 0.32
            is_skip = random.random() < 0.1
            invest  = len(buy_list) * 100
            payout  = random.choice([800, 1200, 2500, 4800, 9800, 15000, 32000]) if (is_hit and not is_skip) else None
            returns = payout if (payout is not None) else (0 if (not is_skip) else None)
            roi_pct = round(returns / invest * 100, 1) if (returns is not None and invest > 0) else None
            records.append({
                "date":         d,
                "venue":        v,
                "race":         str(r),
                "buy_list":     buy_list,
                "buy_count":    len(buy_list),
                "skip":         is_skip,
                "hit":          is_hit and not is_skip,
                "result":       f"{random.randint(1,6)}-{random.randint(1,6)}-{random.randint(1,6)}",
                "result_known": True,
                "source":       "demo",
                "invest":       invest if not is_skip else 0,
                "payout":       payout,
                "returns":      returns,
                "roi_pct":      roi_pct,
            })
    return records


if __name__ == "__main__":
    main()
