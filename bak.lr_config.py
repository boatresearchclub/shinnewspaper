# -*- coding: utf-8 -*-
"""
lr_config.py  ─  パス定数 / グローバル設定 / 会場コードマップ
分割元: load_race.py
"""
import pathlib
import sys
import pandas as pd

_SCRIPT_VERSION = "2026-03-27_fix①②③④_v6.10"  # ← このバージョン文字列が起動時に表示されれば正しいファイルを実行中

# ── 【修正①】safe_float の重複定義を除去し lr_utils から import ──────────────
# 旧: lr_config.py と lr_utils.py に全く同じ safe_float が定義されており、
#     将来の修正時に片方だけ変わる「定義ズレ」リスクがあった。
# 新: lr_utils.py を唯一の定義元とし、ここでは import のみ行う。
# ※ lr_utils → lr_config の循環importは発生しない（lr_utils は lr_config を import しない）
from lr_utils import safe_float  # noqa: E402（パス定数より前に import するため）

# ============================================================
# パス設定
# ============================================================
BASE_DIR    = pathlib.Path(__file__).parent.parent
CSV_DIR     = pathlib.Path(__file__).parent / "csv_output"
EXCEL_FILE  = BASE_DIR / "ボートリサーチ新聞_軽量版.xlsx"
MASTER_FILE = BASE_DIR / "ボートリサーチ_マスタ.xlsx"
# 会場別コースマスタのCSVキャッシュ（update_master.py が生成）
VENUE_COURSE_CSV = BASE_DIR / "data" / "venue_course_master.csv"
# 展開別残存マスタのCSVキャッシュ（update_master.py が生成）
TENKAI_VENUE_CSV    = BASE_DIR / "data" / "tenkai_survival_venue.csv"
TENKAI_NATIONAL_CSV = BASE_DIR / "data" / "tenkai_survival_national.csv"

# ── ②ST差×決まり手 閾値マスタ（update_master.py calc_st_kimete_threshold で生成）──
ST_KIMETE_CSV = BASE_DIR / "data" / "st_kimete_threshold.csv"

# ── ③コース開放連鎖マスタ（update_master.py calc_kaiho_chain_master で生成）──
KAIHO_VENUE_CSV    = BASE_DIR / "data" / "kaiho_chain_venue.csv"
KAIHO_NATIONAL_CSV = BASE_DIR / "data" / "kaiho_chain_national.csv"

# ── グレード別CSVキャッシュ（update_master.py --grade g1 / --grade sg で生成）──
# ファイルが存在しない場合は一般戦マスタにフォールバックする
VENUE_COURSE_CSV_G1 = BASE_DIR / "data" / "venue_course_master_g1.csv"
VENUE_COURSE_CSV_SG = BASE_DIR / "data" / "venue_course_master_sg.csv"
TENKAI_VENUE_CSV_G1    = BASE_DIR / "data" / "tenkai_survival_venue_g1.csv"
TENKAI_NATIONAL_CSV_G1 = BASE_DIR / "data" / "tenkai_survival_national_g1.csv"
TENKAI_VENUE_CSV_SG    = BASE_DIR / "data" / "tenkai_survival_venue_sg.csv"
TENKAI_NATIONAL_CSV_SG = BASE_DIR / "data" / "tenkai_survival_national_sg.csv"

# グレード → CSVパスのマッピング（load_masters / main で参照）
_GRADE_CSV_MAP = {
    "一般": {
        "venue_course":      VENUE_COURSE_CSV,
        "tenkai_venue":      TENKAI_VENUE_CSV,
        "tenkai_national":   TENKAI_NATIONAL_CSV,
        "sheet_master":      "📊コース別マスタ",
        "sheet_ininage":     "イン逃げ分析",
    },
    "G1": {
        "venue_course":      VENUE_COURSE_CSV_G1,
        "tenkai_venue":      TENKAI_VENUE_CSV_G1,
        "tenkai_national":   TENKAI_NATIONAL_CSV_G1,
        "sheet_master":      "📊コース別マスタ_G1",   # update_master.py が生成するシート名
        "sheet_ininage":     "イン逃げ分析_G1",
    },
    "SG": {
        "venue_course":      VENUE_COURSE_CSV_SG,
        "tenkai_venue":      TENKAI_VENUE_CSV_SG,
        "tenkai_national":   TENKAI_NATIONAL_CSV_SG,
        "sheet_master":      "📊コース別マスタ_SG",
        "sheet_ininage":     "イン逃げ分析_SG",
    },
}
# G2・G3 は独立マスタ
_GRADE_CSV_MAP["G2"] = {
    "venue_course":      BASE_DIR / "data" / "venue_course_master_g2.csv",
    "tenkai_venue":      BASE_DIR / "data" / "tenkai_survival_venue_g2.csv",
    "tenkai_national":   BASE_DIR / "data" / "tenkai_survival_national_g2.csv",
    "sheet_master":      "📊コース別マスタ_G2",
    "sheet_ininage":     "イン逃げ分析_G2",
}
# 【修正④】G3はG2マスタを流用するが、dict を共有参照するとG3専用の識別が不可能になるため
# コピーを作成し "_uses_g2_master" フラグを付与。load_masters がログ出力に使用する。
_GRADE_CSV_MAP["G3"] = dict(_GRADE_CSV_MAP["G2"])
_GRADE_CSV_MAP["G3"]["_uses_g2_master"] = True  # ログ識別フラグ（G3→G2流用を明示）
# ※ SGは専用マスタを優先使用（SG専用CSVが未生成の場合は load_masters 内でG1にフォールバック）

# 【⑤追加】会場別コース距離補正値CSVキャッシュ（update_master.py が生成）
VENUE_COURSE_ADJ_CSV = BASE_DIR / "data" / "venue_course_adj.csv"

# 【修正③】信頼度フィルタ閾値を定数化（旧: _load_venue_course_adj 内にハードコード 0.3）
# 他の閾値定数（_GRADE_TRUST_THRESHOLD 等）と同様に明示的に定義する。
VENUE_COURSE_ADJ_TRUST_MIN: float = 0.3  # これ未満の信頼度レコードは固定値を使用

# 【⑤追加】会場別コース距離補正値をCSVから読み込む
# キー: 会場名 / 値: {コース番号str: 補正秒数float}
# CSVが存在しない場合は空dictを返し、_predict_first_turnが固定値にフォールバック

def _load_venue_course_adj() -> dict:
    if not VENUE_COURSE_ADJ_CSV.exists():
        return {}
    try:
        df = pd.read_csv(str(VENUE_COURSE_ADJ_CSV), encoding="utf-8-sig", dtype=str)
        result = {}
        for row in df.to_dict(orient="records"):
            venue = str(row.get("会場名", "") or "").strip()
            trust = safe_float(row.get("信頼度"), 0.0) or 0.0
            if not venue or trust < VENUE_COURSE_ADJ_TRUST_MIN:
                continue  # 【修正③】定数参照に統一（旧: ハードコード 0.3）
            adj_map = {}
            for c in range(2, 7):
                v = safe_float(row.get(f"{c}C補正"))
                if v is not None:
                    adj_map[str(c)] = v
            if adj_map:
                result[venue] = adj_map
        print(f"  ✓ 会場別コース距離補正値読込: {len(result)}会場")
        return result
    except Exception as e:
        print(f"  [!]  会場別コース距離補正値読込失敗（固定値を使用）: {e}")
        return {}

# 起動時に一度だけ読み込む
_VENUE_COURSE_ADJ: dict = _load_venue_course_adj()
# ─── オッズ設定 ───────────────────────────────────────────────────────────
# 【方法A】boatrace.jp のURLを指定（推奨）
#   レース直前にURLを貼るだけで実際のオッズを自動取得してEV計算
#   例: ACTUAL_ODDS_URL = "https://www.boatrace.jp/owpc/pc/race/odds3t?rno=3&jcd=01&hd=20240601"
#   ※ レース番号(rno)と場コード(jcd)と日付(hd)を書き換えて使用
#   ※ Noneにすると方法Bにフォールバック
ACTUAL_ODDS_URL = None  # ← ここにURLを貼る（レースごとに書き換え）

# 【修正⑤】会場名 → boatrace.jp 場コード（jcd）マッピング
# 公式場コード: 01=桐生 02=戸田 03=江戸川 04=平和島 05=多摩川 06=浜名湖
#              07=蒲郡 08=常滑 09=津  10=三国  11=びわこ 12=住之江
#              13=尼崎 14=鳴門 15=丸亀 16=児島 17=宮島  18=徳山
#              19=下関 20=若松 21=芦屋 22=福岡 23=唐津  24=大村
VENUE_JCD_MAP = {
    "桐生":   "01", "戸田":   "02", "江戸川": "03", "平和島": "04",
    "多摩川": "05", "浜名湖": "06", "蒲郡":   "07", "常滑":   "08",
    "津":     "09", "三国":   "10", "びわこ": "11", "住之江": "12",
    "尼崎":   "13", "鳴門":   "14", "丸亀":   "15", "児島":   "16",
    "宮島":   "17", "徳山":   "18", "下関":   "19", "若松":   "20",
    "芦屋":   "21", "福岡":   "22", "唐津":   "23", "大村":   "24",
}


def build_odds_url(venue: str, race_no, race_date: str) -> str | None:
    """
    【修正⑤】会場名・レース番号・日付から boatrace.jp の3連単オッズURLを自動生成。

    Parameters
    ----------
    venue     : str  会場名（例: "大村"）
    race_no   : int or str  レース番号（例: 3）
    race_date : str  日付文字列（例: "2026-03-08" または "20260308"）

    Returns
    -------
    str  URL文字列 / None（会場コード不明の場合）

    使用例
    ------
    url = build_odds_url("大村", 5, "2026-03-08")
    # → "https://www.boatrace.jp/owpc/pc/race/odds3t?rno=5&jcd=24&hd=20260308"
    """
    jcd = VENUE_JCD_MAP.get(str(venue).strip())
    if not jcd:
        return None
    rno = int(race_no) if str(race_no).isdigit() else race_no
    # 日付フォーマット統一（"2026-03-08" → "20260308"）
    hd = str(race_date).replace("-", "").replace("/", "")
    if len(hd) != 8 or not hd.isdigit():
        return None
    return f"https://www.boatrace.jp/owpc/pc/race/odds3t?rno={rno}&jcd={jcd}&hd={hd}"

# 【方法B】理論オッズExcel（全会場共通・固定ファイル）
#   URLが指定されていない場合のフォールバック
#   odds/ フォルダに「理想オッズ完成版.xlsx」を置くだけでOK
ODDS_DIR      = BASE_DIR / "odds"
ODDS_FILEPATH = ODDS_DIR / "理想オッズ完成版.xlsx"

# ── 数値蓄積フォルダ（load_race.py の --collect モードで参照）────────────
CHIKUSEKI_DIR = pathlib.Path(
    r"C:\Users\user\Desktop\データ収集\scripts\数値蓄積"
)
# ─────────────────────────────────────────────────────────────────────────────


SHEET_MASTER    = "📊コース別マスタ"
SHEET_PLAYER    = "選手指数マスタ"
SHEET_ININAGE   = "イン逃げ分析"
SHEET_OUTPUT    = "出力_新聞"
SHEET_SAMPLE    = "出力_新聞サンプル"

ROWS_PER_RACE = 30  # サンプル29行ブロック + 1空行

# 艇色（競艇公式カラー）
BOAT_COLORS = {
    1: {"bg": "FFFFFFFF", "fg": "FF000000"},  # 白
    2: {"bg": "FF111111", "fg": "FFFFFFFF"},  # 黒
    3: {"bg": "FFFF0000", "fg": "FFFFFFFF"},  # 赤
    4: {"bg": "FF00B0F0", "fg": "FFFFFFFF"},  # 青
    5: {"bg": "FFFFFF00", "fg": "FF000000"},  # 黄
    6: {"bg": "FF00B050", "fg": "FFFFFFFF"},  # 緑
}
BOAT_BG_LIGHT = {
    1: "FFFFFFFF",
    2: "FF555555",
    3: "FFFFCCCC",
    4: "FFCCE8FF",
    5: "FFFFFACC",
    6: "FFCCFFEE",
}

# ============================================================
# ユーティリティ
# ============================================================

