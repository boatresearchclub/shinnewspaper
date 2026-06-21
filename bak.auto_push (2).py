"""
auto_push.py  —  CSV・展示情報JSON・index.html を GitHub に自動push
====================================================================
【監視対象】
  csv_output/*.csv     → pushしてスマホで番組表を表示
  tenji_data/*.json    → pushしてスマホで展示情報を表示
  index.html           → 常に含める

【使い方】
  python auto_push.py

【初回セットアップ済み前提】
  git init / git remote add origin ... / git push -u origin master
"""

import subprocess, time, json, glob, os, re, sys, queue
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from datetime import datetime
import pandas as pd

# ── Windows CP932 対策: stdout/stderr を UTF-8 に強制 ──────────────
# PowerShell/コマンドプロンプトのデフォルトエンコードがCP932の場合、
# ✓ ⚠ 🟢 などのUnicode文字でUnicodeEncodeErrorが発生してプロセスが
# 即終了するのを防ぐ。
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1)
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
    sys.stderr = open(sys.stderr.fileno(), mode="w", encoding="utf-8", buffering=1)

# ── 買い目点数最適化ロジック ──────────────────────────────
try:
    from betting_optimizer import classify_race as _classify_race
    _OPTIMIZER_AVAILABLE = True
except ImportError:
    _OPTIMIZER_AVAILABLE = False
    print("[警告] betting_optimizer.py が見つかりません。推奨点数は全レース10点になります。")

SCRIPTS_DIR = Path(__file__).parent
TENJI_DIR   = SCRIPTS_DIR / "tenji_data"
COMMENT_DIR = SCRIPTS_DIR / "comment_data"
RESULT_DIR  = SCRIPTS_DIR / "result_data"
ODDS_DIR = SCRIPTS_DIR / "odds_data"
DATA_DIR = SCRIPTS_DIR / "data"          # フェーズ1: JSON分離用ディレクトリ

# オッズ取得間隔（秒）: 出走表到着後・5分ごとの結果取得と同じリズムで動かす
ODDS_FETCH_INTERVAL = 300   # 5分ごと

CSV_DIR     = SCRIPTS_DIR / "csv_output"
INDEX_HTML      = SCRIPTS_DIR / "index.html"
CSS_FILE        = SCRIPTS_DIR / "sample.css"
JS_FILE         = SCRIPTS_DIR / "sample.js"
JS_FILE_OBF     = SCRIPTS_DIR / "sample_obf.js"   # obfuscate済み。GitHubにはこちらをpush
PARAMS_JS       = SCRIPTS_DIR / "params.js"
PARAMS_JS_OBF   = SCRIPTS_DIR / "params_obf.js"   # params.js のobfuscate済み。GitHubにはこちらをpush
CSV_EXPORT_JS     = SCRIPTS_DIR / "csv_export.js"
CSV_EXPORT_JS_OBF = SCRIPTS_DIR / "csv_export_obf.js"
SIM_JS            = SCRIPTS_DIR / "sim.js"
SIM_JS_OBF        = SCRIPTS_DIR / "sim_obf.js"
BACKTEST_JS        = SCRIPTS_DIR / "backtest.js"
BACKTEST_JS_OBF    = SCRIPTS_DIR / "backtest_obf.js"
TOP_STATS_JS       = SCRIPTS_DIR / "top_stats.js"
TOP_STATS_JS_OBF   = SCRIPTS_DIR / "top_stats_obf.js"
TOP_PAGE_JS        = SCRIPTS_DIR / "top_page.js"
TOP_PAGE_JS_OBF    = SCRIPTS_DIR / "top_page_obf.js"
CALIBRATION_JS        = SCRIPTS_DIR / "calibration.js"
COMPUTE_SCEN_JS       = SCRIPTS_DIR / "computeScenCombosWithEV.js"
DYNAMIC_INN2PLACE_JS  = SCRIPTS_DIR / "dynamic_inn2place.js"
DATA_JS         = SCRIPTS_DIR / "data.js"
PLAYER_ID_MAP   = SCRIPTS_DIR / "player_id_map.json"
VIEWER_HTML         = SCRIPTS_DIR / "展開別残存ビューア.html"
FETCH_TENJI_PY      = SCRIPTS_DIR / "fetch_tenji.py"
FETCH_RESULT_PY     = SCRIPTS_DIR / "fetch_result.py"
FETCH_RACE_INDEX_PY = SCRIPTS_DIR / "fetch_race_index.py"
RACE_INDEX_JSON     = SCRIPTS_DIR / "race_index.json"  # 後方互換用（当日分）

def get_race_index_path(date_str=None):
    """
    日付別の race_index_{YYYYMMDD}.json のパスを返す。
    date_str は "YYYY-MM-DD" または "YYYYMMDD"。
    省略時は当日。該当ファイルがなければ後方互換で race_index.json を返す。
    """
    if date_str:
        hd = date_str.replace("-", "")
    else:
        hd = datetime.now().strftime("%Y%m%d")
    p = SCRIPTS_DIR / f"race_index_{hd}.json"
    if p.exists():
        return p
    # フォールバック: 旧来の race_index.json
    return RACE_INDEX_JSON
CHECK_INTERVAL = 2   # 秒（展示・オッズ検知を高速化）★ 10→5→2秒に短縮

# 過去データの保持・表示日数
HISTORY_DAYS = 30  # 過去日数（日付ナビ・AI予想成績・展示・コメント・JSONファイル）
RESULT_DAYS  = 30  # result_data/*.json 保持日数（バックテスト用 / HTMLへの埋め込みはフェーズ3で停止）

# 会場名 → fetch_tenji.py のURLスラッグ（fetch_tenji.py と同一マップ）
VENUE_SLUG = {
    "桐生":   "kiryu",    "戸田":   "toda",     "江戸川": "edogawa",
    "平和島": "heiwajima","多摩川": "tamagawa", "浜名湖": "hamanako",
    "蒲郡":   "gamagori", "常滑":   "tokoname", "津":     "tsu",
    "三国":   "mikuni",   "びわこ": "biwako",   "住之江": "suminoe",
    "尼崎":   "amagasaki","鳴門":   "naruto",   "丸亀":   "marugame",
    "児島":   "kojima",   "宮島":   "miyajima", "徳山":   "tokuyama",
    "下関":   "shimonoseki","若松":  "wakamatsu","芦屋":   "ashiya",
    "福岡":   "fukuoka",  "唐津":   "karatsu",  "大村":   "omura",
}

# ── Excelマスタ監視 ────────────────────────────────────
XLSX_PATH        = SCRIPTS_DIR.parent / "ボートリサーチ_マスタ.xlsx"
BUILD_MASTER_PY  = SCRIPTS_DIR / "build_master_json.py"

# ── マスタ読み込み ─────────────────────────────────────
MASTER_JSON         = SCRIPTS_DIR / "master_data.json"
KIMARI_TUNING_JSON  = SCRIPTS_DIR / "kimari_tuning.json"

def load_master():
    if MASTER_JSON.exists():
        with open(MASTER_JSON, encoding="utf-8") as f:
            return json.load(f)
    return {}

def apply_kimari_tuning(master: dict) -> dict:
    """
    kimari_tuning.json が存在すれば、tune_kimari.py が算出した
    補正済み venue_kimari を master に上書きして返す。
    ファイルがなければ master をそのまま返す（無害）。
    """
    if not KIMARI_TUNING_JSON.exists():
        return master
    try:
        with open(KIMARI_TUNING_JSON, encoding="utf-8") as f:
            tuning = json.load(f)
        tuned_kimari = tuning.get("venue_kimari", {})
        if not tuned_kimari:
            return master
        # venue_kimari を補正済みの値で上書き（他のキーは維持）
        master = dict(master)
        original = master.get("venue_kimari", {})
        merged = {**original, **tuned_kimari}   # 補正値がある会場だけ上書き
        master["venue_kimari"] = merged
        built_at = tuning.get("built_at", "不明")
        print(f"  ✓ kimari_tuning.json 適用: {len(tuned_kimari)}会場 (生成日時: {built_at})", flush=True)
    except Exception as e:
        print(f"  ⚠ kimari_tuning.json 読み込みエラー: {e} → 生の値を使用", flush=True)
    return master

MASTER = apply_kimari_tuning(load_master())

def rebuild_master():
    """
    ボートリサーチ_マスタ.xlsx から master_data.json を再ビルドし、
    グローバルの MASTER をホットリロードする。
    build_master_json.py が同フォルダにある前提。
    """
    global MASTER
    if not XLSX_PATH.exists():
        log(f"  ⚠ {XLSX_PATH.name} が見つかりません → マスタ再ビルドスキップ")
        return False
    if not BUILD_MASTER_PY.exists():
        log(f"  ⚠ {BUILD_MASTER_PY.name} が見つかりません → マスタ再ビルドスキップ")
        return False

    log("  Excelマスタ更新検知 → master_data.json を再ビルド中...")
    import sys as _sys
    result = subprocess.run(
        [_sys.executable, str(BUILD_MASTER_PY), str(XLSX_PATH), str(MASTER_JSON)],
        capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if result.returncode != 0:
        log(f"  ✕ 再ビルド失敗: {result.stderr.strip()}")
        return False

    MASTER = apply_kimari_tuning(load_master())
    log(f"  ✓ マスタ再ビルド完了 / 選手数: {len(MASTER.get('course_master', {}))}")
    return True

def normalize_name(name):
    return str(name).replace("\u3000", "").replace(" ", "").strip()

def resolve_player_name(raw_name, reg_no):
    id_map = MASTER.get("player_id_map", {})
    reg_str = str(reg_no).strip() if reg_no else ""
    if reg_str and reg_str in id_map:
        return id_map[reg_str], "id"
    normalized = normalize_name(raw_name)
    for official in MASTER.get("course_master", {}):
        if official.startswith(normalized):
            return official, "prefix"
    return normalize_name(raw_name), "unresolved"

def st_rank_to_correction(st_rank):
    if st_rank is None:
        return 1.0
    # 線形マッピング: rank=1→1.2, rank=3.0→1.0, rank=6→0.7
    # 基準を3.5→3.0に変更（実測平均ST順位に合わせた補正）
    raw = 1.0 + (3.0 - st_rank) * (0.2 / 2.5)
    return max(0.7, min(1.2, raw))

def form_correction(player_idx, overall_win):
    if not player_idx:
        return 1.0
    # ① FLY明け補正（最優先）
    fly_days = player_idx.get("fly_days")
    fly_after_runs = player_idx.get("fly_after_runs") or 0
    if fly_days is not None and fly_after_runs < 10:
        return 0.85
    # ② bayesian_winを使用（overall×20 + recent10×10）÷30
    bayesian = player_idx.get("bayesian_win")
    base = overall_win or player_idx.get("overall_win")
    if bayesian is None or not base or base <= 0:
        return 1.0
    # ③ 相対比率で4段階評価
    ratio = bayesian / base
    if   ratio >= 1.20: return 1.12   # 著しく好調
    elif ratio >= 1.08: return 1.06   # 好調
    elif ratio <= 0.80: return 0.88   # 著しく不調
    elif ratio <= 0.92: return 0.94   # 不調
    else:               return 1.00   # 通常

# ── 会場別 被kimari補正強度テーブル ──────────────────────────────────────────
# ⚠️  SYNC REQUIRED: sample.js の VENUE_HI_KIMARI_STRENGTH と必ず同一にすること。
#     sample.js を変更したら、このテーブルも同時に更新すること。
#     "_default" キーは未登録会場のフォールバック値（JS の ?? 演算子と同じ役割）。
# ─────────────────────────────────────────────────────────────────────────────
_VENUE_HI_KIMARI_STRENGTH = {
    # 逃げ強会場 → 弱め
    "大村": 1.5, "常滑": 1.5, "丸亀": 1.5, "尼崎": 1.5, "住之江": 1.5, "桐生": 1.5, "下関": 1.5,
    # 荒れ強会場 → 強め
    "戸田": 2.5, "三国": 2.5, "平和島": 2.5, "浜名湖": 2.5, "蒲郡": 2.5,
    # 特殊水面 → 中程度
    "江戸川": 2.0,
    # デフォルト（未登録会場はここを使用）← JS の "_default" キーと対応
    "_default": 2.0,
}

def _get_hi_kimari_strength(venue):
    # JS: VENUE_HI_KIMARI_STRENGTH[venue] ?? VENUE_HI_KIMARI_STRENGTH["_default"]
    return _VENUE_HI_KIMARI_STRENGTH.get(venue, _VENUE_HI_KIMARI_STRENGTH["_default"])

# ============================================================
# 展示スコア計算（sample.js calcTenjiScore の Python完全移植）
# [2026-05-17 追加] tenji_score を boat dict に付与するために新設
#
# 修正背景:
#   - auto_push.py の boat dict には tenji_score が付与されていなかった
#   - classify_race() に渡る boat1_tenji / pred1_tenji が常に 1.0（中立）
#   - betting_optimizer.py の案7/8（tenji補正）が全く機能していない状態
#   - 956R全件「展示なし」扱いになっていた根本原因
#
# 修正内容:
#   - parse_csv() の return 直前に _inject_tenji_scores() を呼び出す
#   - tenji_data/*.json から展示タイムを読み込み、JS と同一ロジックでスコア化
#   - boat dict に tenji_score（平均=1.0基準の係数）を付与
#   - classify_race() の pred1_tenji / boat1_tenji が正しい値で動作するようになる
# ============================================================

# sample.js VENUE_TENJI_CONFIG と完全同一
_VENUE_TENJI_CONFIG = {
    "江戸川": {
        "available": {"lap1": False,   "mawari": False, "chokusen": False, "tenji": True},
        "weight":    {"lap1": 0.0,     "mawari": 0.0,   "chokusen": 0.0,   "tenji": 1.0},
    },
    "桐生": {
        "available": {"lap1": "half",  "mawari": True,  "chokusen": True,  "tenji": True},
        "weight":    {"lap1": 2.25,    "mawari": 0.0,   "chokusen": 1.0,   "tenji": 2.0},
    },
    "尼崎": {
        "available": {"lap1": True,    "mawari": True,  "chokusen": False,  "tenji": True},
        "weight":    {"lap1": 4.5,     "mawari": 1.0,   "chokusen": 0.0,   "tenji": 2.0},
    },
    "住之江": {
        "available": {"lap1": True,    "mawari": True,  "chokusen": False,  "tenji": True},
        "weight":    {"lap1": 4.5,     "mawari": 1.0,   "chokusen": 0.0,   "tenji": 2.0},
    },
    "徳山": {
        "available": {"lap1": True,    "mawari": True,  "chokusen": False,  "tenji": True},
        "weight":    {"lap1": 4.5,     "mawari": 1.0,   "chokusen": 0.0,   "tenji": 2.0},
    },
    "蒲郡": {
        "available": {"lap1": True,    "mawari": True,  "chokusen": True,   "tenji": True},
        "weight":    {"lap1": 4.5,     "mawari": 0.0,   "chokusen": 1.0,   "tenji": 2.0},
    },
    "戸田": {
        "available": {"lap1": True,    "mawari": True,  "chokusen": True,   "tenji": True},
        "weight":    {"lap1": 4.5,     "mawari": 0.0,   "chokusen": 1.0,   "tenji": 2.0},
    },
    "三国": {
        "available": {"lap1": True,    "mawari": True,  "chokusen": True,   "tenji": True},
        "weight":    {"lap1": 4.5,     "mawari": 0.0,   "chokusen": 1.0,   "tenji": 2.0},
    },
    "平和島": {
        "available": {"lap1": True,    "mawari": True,  "chokusen": True,   "tenji": True},
        "weight":    {"lap1": 4.5,     "mawari": 0.0,   "chokusen": 1.0,   "tenji": 2.0},
    },
    "浜名湖": {
        "available": {"lap1": True,    "mawari": True,  "chokusen": True,   "tenji": True},
        "weight":    {"lap1": 4.5,     "mawari": 0.0,   "chokusen": 1.0,   "tenji": 2.0},
    },
    "宮島": {
        "available": {"lap1": True,    "mawari": True,  "chokusen": True,   "tenji": True},
        "weight":    {"lap1": 4.5,     "mawari": 1.0,   "chokusen": 0.0,   "tenji": 2.0},
    },
    "下関": {
        "available": {"lap1": True,    "mawari": True,  "chokusen": True,   "tenji": True},
        "weight":    {"lap1": 4.5,     "mawari": 1.0,   "chokusen": 0.0,   "tenji": 2.0},
    },
    "若松": {
        "available": {"lap1": True,    "mawari": True,  "chokusen": True,   "tenji": True},
        "weight":    {"lap1": 4.5,     "mawari": 1.0,   "chokusen": 0.0,   "tenji": 2.0},
    },
    "大村": {
        "available": {"lap1": True,    "mawari": True,  "chokusen": True,   "tenji": True},
        "weight":    {"lap1": 4.5,     "mawari": 1.0,   "chokusen": 0.0,   "tenji": 2.0},
    },
    "常滑": {
        "available": {"lap1": True,    "mawari": True,  "chokusen": True,   "tenji": True},
        "weight":    {"lap1": 4.5,     "mawari": 1.0,   "chokusen": 0.0,   "tenji": 2.0},
    },
    "丸亀": {
        "available": {"lap1": True,    "mawari": True,  "chokusen": True,   "tenji": True},
        "weight":    {"lap1": 4.5,     "mawari": 1.0,   "chokusen": 0.0,   "tenji": 2.0},
    },
    "_default": {
        "available": {"lap1": True,    "mawari": True,  "chokusen": True,   "tenji": True},
        "weight":    {"lap1": 4.5,     "mawari": 1.0,   "chokusen": 0.0,   "tenji": 2.0},
    },
}

_TENJI_FIELDS = ["lap1", "mawari", "chokusen", "tenji"]

# ── [2026-05-20 追加] Python/JS 間 VENUE_TENJI_CONFIG 整合チェック ────────────
# ⚠️  SYNC REQUIRED: sample.js の VENUE_TENJI_CONFIG と会場キー・weight・available が
#     一致していることを起動時に検証する。差分があれば WARNING ログを出す。
#
# 期待する会場キー（JS と完全一致であること）
_EXPECTED_TENJI_VENUES = {
    "江戸川","桐生","尼崎","住之江","徳山","蒲郡","戸田","三国",
    "平和島","浜名湖","宮島","下関","若松","大村","常滑","丸亀","_default",
}

def _check_tenji_config_sync() -> None:
    """
    _VENUE_TENJI_CONFIG のキーと weight 合計値が期待値と一致するかチェックする。
    不一致があれば WARNING を出して開発者に気づきを促す（処理は止めない）。

    チェック項目:
      1. 会場キーの過不足
      2. 各会場の weight 合計（ゼロ会場がないか）
      3. tenji フィールドが全会場で weight > 0 かつ available=True（tenji は必須）
    """
    py_keys   = set(_VENUE_TENJI_CONFIG.keys())
    extra     = py_keys - _EXPECTED_TENJI_VENUES
    missing   = _EXPECTED_TENJI_VENUES - py_keys

    if extra:
        log(f"[WARN] _VENUE_TENJI_CONFIG: JS未登録の会場が Python 側にあります → {sorted(extra)}")
        log(f"[WARN]   → sample.js の VENUE_TENJI_CONFIG にも追加してください")
    if missing:
        log(f"[WARN] _VENUE_TENJI_CONFIG: Python 側に未登録の会場があります → {sorted(missing)}")
        log(f"[WARN]   → _VENUE_TENJI_CONFIG に追加し、sample.js と同期してください")

    for venue, cfg in _VENUE_TENJI_CONFIG.items():
        w = cfg.get("weight", {})
        avail = cfg.get("available", {})
        w_total = sum(w.values())
        if w_total <= 0:
            log(f"[WARN] _VENUE_TENJI_CONFIG['{venue}']: weight の合計がゼロです（全フィールド無効）")
        if not avail.get("tenji", False):
            log(f"[WARN] _VENUE_TENJI_CONFIG['{venue}']: tenji が available=False です（tenji は必須フィールド）")
        if w.get("tenji", 0) <= 0 and avail.get("tenji", False):
            log(f"[WARN] _VENUE_TENJI_CONFIG['{venue}']: tenji の weight がゼロです")

    if not extra and not missing:
        log(f"[INFO] _VENUE_TENJI_CONFIG 整合チェック OK（{len(py_keys)} 会場）")



def _resolve_tenji_weights(venue: str) -> dict:
    """
    sample.js resolveWeights() の完全移植。
    会場設定から計測可能なフィールドのみ使い、正規化した重みを返す。
    """
    cfg = _VENUE_TENJI_CONFIG.get(venue, _VENUE_TENJI_CONFIG["_default"])
    base = dict(cfg["weight"])
    avail = cfg["available"]
    # 計測なし（False）のフィールドを0にする。"half"はTrue扱い（重みは既に半減済み）
    for f in _TENJI_FIELDS:
        if avail.get(f) is False:
            base[f] = 0.0
    total = sum(base.values()) or 1.0
    return {f: base[f] / total for f in _TENJI_FIELDS}


def _time_to_coef(h: float) -> float:
    """
    sample.js timeToCoef() の完全移植。
    偏差値スコア → 係数変換（小さい偏差値=遅い=低係数）
    """
    if h >= 60: return 1.15
    if h >= 55: return 1.08
    if h >= 45: return 1.00
    if h >= 40: return 0.93
    return 0.85


def _field_coefs(boats: list, tenji_by_frame: dict, field: str) -> list | None:
    """
    sample.js fieldCoefs() の完全移植。
    各艇の指定フィールドのタイム値を偏差値→係数に変換して返す。
    全艇欠損ならNone。欠損艇は有効艇の平均で補完。
    """
    vals = [tenji_by_frame.get(b["boat"], {}).get(field) for b in boats]
    valid_vals = [v for v in vals if v is not None]
    if not valid_vals:
        return None
    fill_avg = sum(valid_vals) / len(valid_vals)
    filled = [v if v is not None else fill_avg for v in vals]
    avg = sum(filled) / len(filled)
    variance = sum((v - avg) ** 2 for v in filled) / len(filled)
    std = variance ** 0.5
    if std == 0:
        return [1.0] * len(filled)
    return [_time_to_coef(50 + ((avg - v) / std) * 10) for v in filled]


def _calc_tenji_scores_for_race(boats: list, tenji_by_frame: dict, venue: str) -> None:
    """
    sample.js calcTenjiScore() の完全移植。
    各 boat dict に以下を付与する（インプレース変更）:
      tenji_score      : 正規化済みスコア（全艇合計=1.0）← classify_race に渡す
      tenji_score_coef : 平均=1.0基準の係数（UI表示用・betting_optimizer の tenji係数に相当）

    展示データがない場合は何も付与しない（tenji_score は None のまま）。
    """
    w = _resolve_tenji_weights(venue)

    coefs_map = {}
    for f in _TENJI_FIELDS:
        if w[f] <= 0:
            continue
        c = _field_coefs(boats, tenji_by_frame, f)
        if c is not None:
            coefs_map[f] = c

    if not coefs_map:
        # 展示データなし → tenji_score を付与しない
        return

    # 加重平均で各艇の合成係数を算出
    composite = []
    for i in range(len(boats)):
        score = 0.0
        w_total = 0.0
        for f in _TENJI_FIELDS:
            if f not in coefs_map:
                continue
            score  += w[f] * coefs_map[f][i]
            w_total += w[f]
        composite.append(score / w_total if w_total > 0 else 1.0)

    coef_total = sum(composite) or 1.0
    coef_avg   = coef_total / len(boats)  # 6艇均等なら各艇1/6 → coef_avg=1/6

    for i, bt in enumerate(boats):
        # tenji_score: 全艇合計=1.0 の正規化スコア（classify_race の tenji係数ではない）
        bt["tenji_score"] = round(composite[i] / coef_total, 6)
        # tenji_score_coef: 平均=1.0基準の係数（0.5〜2.0クリップ）
        # betting_optimizer の boat1_tenji / pred1_tenji にはこちらを使う
        bt["tenji_score_coef"] = round(
            min(2.0, max(0.5, composite[i] / coef_avg)) if coef_avg > 0 else 1.0, 4
        )


def _inject_tenji_scores(races: dict, venue: str, date_str: str) -> None:
    """
    tenji_data/*.json を読み込み、各レースの boats に tenji_score を付与する。
    展示JSONが存在しないレースはスキップ（副作用なし）。

    ファイル名規則: tenji_{slug}_{YYYYMMDD}_R{N}.json
    JSONキー: frame（艇番）, lap1, mawari, chokusen, tenji（各タイム値・秒）

    [2026-05-17 新設] auto_push.py の parse_csv() の return 直前から呼び出す。
    """
    slug    = VENUE_SLUG.get(venue, venue)
    date_nd = date_str.replace("-", "")
    loaded  = 0

    for rno, rd in races.items():
        # ファイル名: R番号はゼロ埋めなし（fetch_tenji.py の命名規則に合わせる）
        fpath = TENJI_DIR / f"tenji_{slug}_{date_nd}_R{rno}.json"
        if not fpath.exists():
            continue
        try:
            with open(fpath, encoding="utf-8") as f:
                rows = json.load(f)
        except Exception:
            continue

        # frame番号（艇番）→ 展示データ dict
        tenji_by_frame = {r["frame"]: r for r in rows}

        _calc_tenji_scores_for_race(rd["boats"], tenji_by_frame, venue)
        loaded += 1

    if loaded:
        log(f"  ✓ 展示スコア付与: {venue} {date_str}  {loaded}R分")


# ============================================================
# 以下既存コード
# ============================================================

def _calc_tenkai_scores(boats, venue):
    """
    sample.js の calcTenkaiProbs() を Python に移植。
    各 boat dict に tenkai_score キーを付与して返す。

    ロジック概要:
      1. MASTER から venue_kimari・course_master を取得
      2. 1コース選手の被kimari率で adjustedVKimari を動的補正（修正C相当）
      3. 各艇ごとに個人kimariをブレンドした boatVKimari を生成（修正D相当）
      4. 決まり手加重適性係数 kimariCoefSum を計算
      5. scores = prob × kimariCoefSum → 正規化 → tenkai_score
    """
    venue_kimari_all = MASTER.get("venue_kimari", {})
    course_master    = MASTER.get("course_master", {})

    # MASTER_EXT なし or 会場データなし → prob をそのまま tenkai_score に
    if not venue_kimari_all:
        for bt in boats:
            bt["tenkai_score"] = bt["prob"]
        return boats

    vKimari = venue_kimari_all.get(venue)
    if not vKimari:
        for bt in boats:
            bt["tenkai_score"] = bt["prob"]
        return boats

    # ── 定数（JS と同一）──
    KIMARI_HARD_EXCLUDE = {
        "逃げ":       {"2","3","4","5","6"},
        "差し":       {"1"},
        "まくり":     {"1"},
        "まくり差し": {"1","2"},
        "抜き":       set(),
    }
    KIMARI_SOFT_THRESHOLD = {
        "まくり": {"2": 0.05},
        "抜き":   {"1": 0.03},
    }
    RELATIVE_MIN = 0.3
    RELATIVE_MAX = 3.0
    PERSONAL_BLEND_STRENGTH = 0.7

    def get_personal_kimari(name, course_str, kimari_type):
        return (course_master.get(name, {})
                             .get(course_str, {})
                             .get("kimari", {})
                             .get(kimari_type, 0))

    def get_personal_hi_kimari(name, hi_type):
        return (course_master.get(name, {})
                             .get("1", {})
                             .get("被kimari", {})
                             .get(hi_type))

    def is_valid_first(bt, kimari):
        wc  = str(int(bt["boat"]))
        exc = KIMARI_HARD_EXCLUDE.get(kimari)
        if exc is None:
            return False
        if wc in exc:
            return False
        soft = KIMARI_SOFT_THRESHOLD.get(kimari, {})
        if wc in soft:
            threshold = soft[wc]
            personal  = get_personal_kimari(bt["name"], wc, kimari)
            return personal >= threshold
        return True

    def calc_relative_coef(winner, kimari, boat1):
        if boat1 is None:
            return 1.0
        wc = str(int(winner["boat"]))
        if kimari == "逃げ":
            nige = get_personal_kimari(winner["name"], "1", "逃げ")
            return nige if nige > 0 else 1.0
        if kimari == "差し":
            attack = get_personal_kimari(winner["name"], wc, "差し")
            def_r  = get_personal_hi_kimari(boat1["name"], "差され")
            return (attack * def_r) if def_r is not None else (attack or 1.0)
        if kimari == "まくり":
            attack = get_personal_kimari(winner["name"], wc, "まくり")
            def_r  = get_personal_hi_kimari(boat1["name"], "捲られ")
            return (attack * def_r) if def_r is not None else (attack or 1.0)
        if kimari == "まくり差し":
            # [2026-05-20 修正] まくり差しは1コース・2コースの両艇を抜く技。
            # 被kimariデータはコース"1"専用設計のため、
            # boat1（1コース）の 捲り差され率 をベースとしつつ、
            # 2コース艇（boat2）にも同キーが存在する場合は幾何平均で合成する。
            # → データがない場合は従来通り1コースのみで評価（後方互換）
            attack = get_personal_kimari(winner["name"], wc, "まくり差し")
            def1   = get_personal_hi_kimari(boat1["name"], "捲り差され")
            # 2コース艇を boats から取得（まくり差しのHARD_EXCLUDEで2コースは攻撃側に入れないため安全）
            boat2  = next((b for b in boats if int(b["boat"]) == 2), None)
            def2   = get_personal_hi_kimari(boat2["name"], "捲り差され") if boat2 else None
            if def1 is not None and def2 is not None:
                # 両方データあり → 幾何平均（√(def1 × def2)）で合成
                combined_def = (def1 * def2) ** 0.5
                return attack * combined_def if attack else combined_def
            elif def1 is not None:
                return (attack * def1) if def1 is not None else (attack or 1.0)
            else:
                return attack or 1.0
        return 1.0

    # 1コース艇
    boat1 = next((b for b in boats if int(b["boat"]) == 1), None)

    # ── 修正C: 被kimari率で adjustedVKimari を動的補正 ──
    hi_strength   = _get_hi_kimari_strength(venue)
    adjustedVKimari = dict(vKimari)

    if boat1:
        name1       = boat1["name"]
        hi_kimari   = (course_master.get(name1, {})
                                    .get("1", {})
                                    .get("被kimari"))
        boat1_runs  = (course_master.get(name1, {})
                                    .get("1", {})
                                    .get("runs", 0) or 0)
        if hi_kimari and boat1_runs >= 30:
            hi_trust        = min(boat1_runs / 100, 1.0)
            sasare_rate     = hi_kimari.get("差され")
            makurare_rate   = hi_kimari.get("捲られ")
            makurisasare_r  = hi_kimari.get("捲り差され")

            if sasare_rate is not None:
                adjustedVKimari["差し"] = (vKimari.get("差し", 0)
                    * (1 + hi_trust * sasare_rate * hi_strength))
            if makurare_rate is not None:
                adjustedVKimari["まくり"] = (vKimari.get("まくり", 0)
                    * (1 + hi_trust * makurare_rate * hi_strength))
            if makurisasare_r is not None:
                adjustedVKimari["まくり差し"] = (vKimari.get("まくり差し", 0)
                    * (1 + hi_trust * makurisasare_r * hi_strength))

            total_hi = ((sasare_rate or 0) + (makurare_rate or 0)
                        + (makurisasare_r or 0))
            nige_rate = get_personal_kimari(name1, "1", "逃げ")
            if nige_rate > 0:
                nige_boost = nige_rate / max(nige_rate + total_hi, 0.01)
                adjustedVKimari["逃げ"] = (vKimari.get("逃げ", 0)
                    * (0.5 + 0.5 * nige_boost * 2))

            adj_total = sum(adjustedVKimari.values())
            if adj_total > 0:
                adjustedVKimari = {k: v / adj_total for k, v in adjustedVKimari.items()}

    kimari_types = [k for k, v in adjustedVKimari.items()
                    if v > 0 and k in KIMARI_HARD_EXCLUDE]

    # ── 修正D: 個人ブレンド vKimari を艇ごとに生成 ──
    def blend_personal_kimari(bt, base_vkimari):
        name   = bt["name"]
        course = str(int(bt["boat"]))
        cm     = course_master.get(name, {}).get(course, {})
        if not cm:
            return base_vkimari
        runs = cm.get("runs", 0) or 0
        if runs < 30:
            return base_vkimari
        trust = min(runs / 100, 1.0) * PERSONAL_BLEND_STRENGTH
        personal_kimari = cm.get("kimari", {})
        BLEND_TARGETS   = ["差し", "まくり", "まくり差し", "抜き"]
        personal_total  = sum(personal_kimari.get(k, 0) for k in BLEND_TARGETS)
        if personal_total <= 0:
            return base_vkimari
        blend_base_sum = sum(base_vkimari.get(k, 0) for k in BLEND_TARGETS)
        blended = dict(base_vkimari)
        for k in BLEND_TARGETS:
            if k not in blended:
                continue
            personal_rate = (personal_kimari.get(k, 0) / personal_total) * blend_base_sum
            blended[k] = base_vkimari[k] * (1 - trust) + personal_rate * trust
        orig_total  = sum(base_vkimari.values())
        blend_total = sum(blended.values())
        if blend_total > 0:
            blended = {k: v / blend_total * orig_total for k, v in blended.items()}
        return blended

    boat_vkimari = {bt["boat"]: blend_personal_kimari(bt, adjustedVKimari) for bt in boats}

    # ── 決まり手加重適性係数 (kimariCoefSum) を算出 ──
    kimari_coef_sum = {bt["boat"]: 0.0 for bt in boats}

    for kimari in kimari_types:
        rel_coefs   = {}
        valid_boats = [b for b in boats if is_valid_first(b, kimari)]
        if not valid_boats:
            continue

        for bt in boats:
            if not is_valid_first(bt, kimari):
                rel_coefs[bt["boat"]] = 0.0
                continue
            raw_coef   = calc_relative_coef(bt, kimari, boat1)
            kimari_runs = (course_master.get(bt["name"], {})
                                        .get(str(int(bt["boat"])), {})
                                        .get("runs", 0) or 0)
            personal_trust = min(kimari_runs / 100, 1.0)
            rel_coefs[bt["boat"]] = raw_coef * personal_trust + 1.0 * (1 - personal_trust)

        avg_coef = (sum(rel_coefs[b["boat"]] for b in valid_boats)
                    / len(valid_boats))
        if avg_coef <= 0:
            continue

        for bt in boats:
            if is_valid_first(bt, kimari):
                kimari_prob = boat_vkimari[bt["boat"]].get(kimari, 0)
                if kimari_prob <= 0:
                    continue
                norm_coef = min(RELATIVE_MAX, max(RELATIVE_MIN,
                                rel_coefs[bt["boat"]] / avg_coef))
                kimari_coef_sum[bt["boat"]] += kimari_prob * norm_coef
            else:
                # ハード除外艇には会場平均 × RELATIVE_MIN を加算
                kimari_prob = adjustedVKimari.get(kimari, 0)
                kimari_coef_sum[bt["boat"]] += kimari_prob * RELATIVE_MIN

    # ── scores = prob × kimariCoefSum → 正規化 → tenkai_score ──
    raw_scores = {bt["boat"]: bt["prob"] * (kimari_coef_sum[bt["boat"]] or RELATIVE_MIN)
                  for bt in boats}
    total_ts   = sum(raw_scores.values()) or 1.0
    for bt in boats:
        bt["tenkai_score"] = round(raw_scores[bt["boat"]] / total_ts, 6)
    return boats


def calc_prob_from_master(boats, venue, race_no=0, is_joshi=False, grade="一般"):
    """
    選手ごとのコース別1着率 → prob を計算して boats に付与する。

    grade 優先順位（引継ぎポイント最重要事項）:
      SG / G1  → course_master_g1 を使用
                 reliable=False の選手は course_master にフォールバック
      女子戦   → course_master_joshi を使用
      その他   → course_master（一般戦）を使用
    """
    course_master_g1    = MASTER.get("course_master_g1", {})
    course_master_joshi = MASTER.get("course_master_joshi", {})
    course_master_base  = MASTER.get("course_master", {})

    IS_GRADE_MODE = grade in ("SG", "G1") and bool(course_master_g1)

    def _get_course_entry(name, c):
        """
        コースマスタエントリを返す。
        グレードモード: g1マスタ優先、reliable=False なら一般マスタにフォールバック。
        """
        if IS_GRADE_MODE:
            entry_g1 = course_master_g1.get(name, {}).get(c)
            if entry_g1 and entry_g1.get("reliable", False):
                return entry_g1
            # reliable=False（SGでも出場経験が少ない選手）→ 一般戦マスタに静かにフォールバック
            return course_master_base.get(name, {}).get(c)
        if is_joshi and course_master_joshi:
            entry_j = course_master_joshi.get(name, {}).get(c)
            if entry_j and entry_j.get("reliable", False):
                return entry_j
            return course_master_base.get(name, {}).get(c)
        return course_master_base.get(name, {}).get(c)

    # course_master: kimariCoefSum等のヘルパー参照用に設定
    if IS_GRADE_MODE:
        course_master = course_master_g1
    elif is_joshi and course_master_joshi:
        course_master = course_master_joshi
    else:
        course_master = course_master_base
    venue_course_master = MASTER.get("venue_course_master", {})
    venue_stats         = MASTER.get("venue_stats", {}).get(venue, {})
    player_index        = MASTER.get("player_index", {})
    race_key = str(race_no) if race_no else None
    race_course_rates = (
        venue_stats.get("race_course_rates", {}).get(race_key, {})
        if race_key else {}
    )
    venue_course_rates = venue_stats.get("course_rates", {})
    scores, dq_list, base_rates = [], [], []
    has_insufficient = False

    for bt in boats:
        name   = normalize_name(bt.get("name", ""))
        course = int(bt.get("boat", 1))
        c      = str(course)
        base_rate, dq = None, None

        # 会場別・全国のデータをそれぞれ取得
        vc = venue_course_master.get(name, {}).get(venue, {}).get(c)
        cm = _get_course_entry(name, c)

        venue_rate    = (vc.get("ts_win_rate") or vc.get("win_rate")) if vc and vc.get("reliable") else None
        national_rate = (cm.get("ts_win_rate") or cm.get("win_rate")) if cm and cm.get("reliable") else None
        venue_trust   = vc.get("trust", 0.0) if vc else 0.0

        if venue_rate is not None and national_rate is not None:
            # 両方ある → trustで加重ブレンド
            base_rate = venue_rate * venue_trust + national_rate * (1.0 - venue_trust)
            dq = "venue_local"
        elif venue_rate is not None:
            base_rate = venue_rate
            dq = "venue_local"
        elif national_rate is not None:
            base_rate = national_rate
            dq = "course_national"

        # 選手個人のコースデータが閾値未満かを独立判定
        has_personal_data = (
            (cm is not None and cm.get("reliable", False))
            or (vc is not None and vc.get("reliable", False))
        )

        if base_rate is None:
            rv = race_course_rates.get(c) or venue_course_rates.get(c)
            if rv is not None:
                base_rate = rv
                dq = "venue_stat"
        if base_rate is None:
            fallback_rate = None
            if vc:
                fallback_rate = vc.get("ts_win_rate") or vc.get("win_rate")
            if fallback_rate is None and cm:
                fallback_rate = cm.get("ts_win_rate") or cm.get("win_rate")
            base_rate = fallback_rate if fallback_rate is not None else 0.001
            dq = "insufficient"
            has_insufficient = True

        # 個人データ不足の場合は dq を insufficient に上書き
        if not has_personal_data:
            has_insufficient = True
            if dq != "insufficient":
                dq = "insufficient"

        base_rate = max(base_rate or 0.001, 0.001)
        st_rank = None
        cm_data = course_master.get(name, {}).get(c)
        if cm_data:
            st_rank = cm_data.get("st_rank")
        if st_rank is None:
            pi = player_index.get(name, {})
            st_rank = pi.get("st_rank", {}).get(c)
        st_corr   = st_rank_to_correction(st_rank)
        pi        = player_index.get(name)
        overall_w = pi.get("overall_win") if pi else None
        form_corr = form_correction(pi, overall_w)
        scores.append(base_rate * st_corr * form_corr)
        dq_list.append(dq)
        # 表示用生1着率: コース別マスタのraw値そのまま（ブレンド・補正なし）
        raw_win_rate = (cm.get("ts_win_rate") or cm.get("win_rate")) if cm else None
        base_rates.append(raw_win_rate)

    total = sum(scores) or 1.0
    for i, bt in enumerate(boats):
        bt["prob"]       = round(scores[i] / total, 4)
        bt["base_score"] = round(scores[i], 4)   # 正規化前の生スコア（展示補正の絶対値計算に使用）
        bt["score"]      = round(scores[i], 4)   # 後方互換のため残す
        bt["base_rate"]  = round(base_rates[i], 4) if base_rates[i] is not None else None  # マスタ生1着率（絶対値表示用）
        bt["dq"]         = dq_list[i]
    if has_insufficient:
        for bt in boats:
            bt["prob_warning"] = True

    # ── tenkai_score を付与（JS の calcTenkaiProbs 相当）────────────────
    boats = _calc_tenkai_scores(boats, venue)
    return boats

def parse_csv(filepath):
    try:
        try:
            df = pd.read_csv(filepath, encoding="utf-8")
        except UnicodeDecodeError:
            df = pd.read_csv(filepath, encoding="shift_jis")
    except Exception:
        return None
    if "会場" not in df.columns or "レース" not in df.columns:
        return None
    df = df.fillna("")
    venue = str(df.iloc[0]["会場"]).strip()
    date  = str(df.iloc[0].get("日付", "")).strip().replace("/", "-")
    venue_stats = MASTER.get("venue_stats", {}).get(venue, {})
    races = {}
    for _, row in df.iterrows():
        rno = int(row["レース"]) if str(row["レース"]).isdigit() else 0
        if rno == 0:
            continue
        if rno not in races:
            races[rno] = {
                "arek": venue_stats.get("arek_by_race", {}).get(rno,
                        venue_stats.get("arek_score", 54.7)),
                "time": str(row.get("締切時刻", "")),
                "boats": []
            }
        raw_name = str(row.get("選手名", "")).strip()
        reg_no   = str(row.get("登番", "")).strip()
        if raw_name:
            raw_name = re.sub(r'\d+$', '', raw_name).strip()
        if raw_name:
            name, name_dq = resolve_player_name(raw_name, reg_no)
        else:
            name, name_dq = f"艇{row.get('艇番', '?')}", "unresolved"
        # モーター番号
        # fetch_tenji.py が保存する列名は "motor_no"
        # 旧列名（モーター番号 / モーターNo / M番号）にもフォールバック
        motor_no_raw = row.get("motor_no",
                       row.get("モーター番号",
                       row.get("モーターNo",
                       row.get("M番号", None))))
        try:
            motor_no = int(float(motor_no_raw)) if motor_no_raw not in (None, "", "nan") else None
        except (ValueError, TypeError):
            motor_no = None

        # モーター2連対率
        # fetch_tenji.py が保存する列名は "motor_rate2"
        # 旧列名（M2率）にもフォールバック
        motor_rate2_raw = row.get("motor_rate2", row.get("M2率", None))
        try:
            motor_rate2 = float(motor_rate2_raw) if motor_rate2_raw not in (None, "", "nan") else 0.0
        except (ValueError, TypeError):
            motor_rate2 = 0.0

        # モーター3連対率
        motor_rate3_raw = row.get("motor_rate3", row.get("M3率", None))
        try:
            motor_rate3 = float(motor_rate3_raw) if motor_rate3_raw not in (None, "", "nan") else 0.0
        except (ValueError, TypeError):
            motor_rate3 = 0.0

        # モーター順位
        motor_rank_raw = row.get("motor_rank", None)
        try:
            motor_rank = int(float(motor_rank_raw)) if motor_rank_raw not in (None, "", "nan") else None
        except (ValueError, TypeError):
            motor_rank = None

        # 前節使用者
        # fetch_tenji.py が保存する列名は "prev_user"
        # 旧列名（前節使用者 / 前節使用）にもフォールバック
        prev_user_raw = row.get("prev_user",
                        row.get("前節使用者",
                        row.get("前節使用", None)))
        prev_user = str(prev_user_raw).strip() if prev_user_raw not in (None, "", "nan") else None

        races[rno]["boats"].append({
            "boat":       int(row.get("艇番", 0)),
            "reg_no":     reg_no,
            "name":       name,
            "name_dq":    name_dq,
            "grade":      str(row.get("級別", "B1")),
            "win_rate":   float(row.get("全国勝率", 0) or 0),
            "local_rate": float(row.get("当地勝率", 0) or 0),
            "motor2":     motor_rate2,    # ← motor_rate2 列から取得
            "motor_rate2": motor_rate2,   # ← sample.html の両方の参照に対応
            "motor_rate3": motor_rate3,
            "boat2":      float(row.get("B2率", 0) or 0),
            "results":    str(row.get("今節成績", "")),
            "hayami":     float(row.get("早見", 0) or 0) or None,
            "motor_no":   motor_no,
            "motor_rank": motor_rank,
            "prev_user":  prev_user,
            "score":      0,
            "dq":         "fallback",
            "prob":       1/6,
        })
    # ── 女子戦フラグ・グレードを race_index_{YYYYMMDD}.json から取得 ──
    is_joshi = False
    race_grade = "一般"   # "SG" / "G1" / "G2" / "G3" / "一般"
    try:
        _ri_path = get_race_index_path(date)
        if _ri_path.exists():
            with open(_ri_path, encoding="utf-8") as _f:
                _ri = json.load(_f)
            _vi = _ri.get("venues", {}).get(venue, {})
            _period = _vi.get("period", "")
            _period_match = False
            if _period and date:
                try:
                    from datetime import datetime as _dt
                    _year = _dt.now().year
                    _parts = _period.replace(" ", "").split("-")
                    if len(_parts) == 2:
                        _start = _dt.strptime(f"{_year}/{_parts[0]}", "%Y/%m/%d").date()
                        _end   = _dt.strptime(f"{_year}/{_parts[1]}", "%Y/%m/%d").date()
                        _csv_d = _dt.strptime(date, "%Y-%m-%d").date()
                        _period_match = _start <= _csv_d <= _end
                except Exception:
                    pass
            if _period_match:
                is_joshi   = bool(_vi.get("is_joshi", False))
                race_grade = str(_vi.get("grade", "一般"))
    except Exception:
        pass

    for rno, rd in races.items():
        rd["boats"] = calc_prob_from_master(rd["boats"], venue, race_no=rno,
                                            is_joshi=is_joshi, grade=race_grade)
        rd["boats"].sort(key=lambda b: -b["prob"])

    # ── 買い目点数最適化パターンを各レースに付与（v2対応）──────
    # 【変更点】
    #   ① boat1_tenkai / pred1_tenkai は分類判定用の raw値（cap しない）
    #   ② tenji係数（boat1_tenji / pred1_tenji）を新たに渡す → 補正専用・上限1.0キャップ
    #   ③ are_index（あれ指数）を渡す → まくりアラートフラグに使用
    #   ④ pat.flags からフラグ群を rd["opt_flags"] に格納（UI表示・将来拡張用）
    #   ⑤ [2026-05-17] buy_mode別にclassify_raceを2回呼び出し → opt_points_hit/rec に格納
    #      HIT: あれ>=55のSS他艇を不買い（的中率向上）
    #      REC: あれフィルターなし（高配当狙い維持）
    if _OPTIMIZER_AVAILABLE:
        for rno, rd in races.items():
            boats_sorted = rd["boats"]  # prob降順済み
            pred_rank1   = boats_sorted[0] if boats_sorted else None
            boat1_data   = next((b for b in boats_sorted if b["boat"] == 1), None)

            if pred_rank1 and boat1_data:
                # ── base係数 = prob（正規化済み基準確率）─────────────────
                pred1_base = pred_rank1.get("prob", 0.0)
                boat1_base = boat1_data.get("prob", 0.0)

                # ── tenkai係数（raw値）= 分類判定専用。cap しない ────────
                # tenkai_score が付与されていればそれ、なければ prob で代替
                pred1_tenkai = pred_rank1.get("tenkai_score", pred_rank1.get("prob", 0.0))
                boat1_tenkai = boat1_data.get("tenkai_score", boat1_data.get("prob", 0.0))

                # ── tenji係数 = 展示係数。補正専用（内部で上限1.0キャップ）
                # [2026-05-17 修正] tenji_score_coef（平均=1.0基準の係数）を使用する。
                # 旧: tenji_score（全艇合計=1.0の正規化値）を渡していた → 常に1.0フォールバック
                # 新: _inject_tenji_scores() が付与した tenji_score_coef（0.5〜2.0）を渡す
                #     tenji_score_coef がなければ 1.0（中立・展示データなし扱い）
                pred1_tenji = pred_rank1.get("tenji_score_coef") or 1.0
                boat1_tenji = boat1_data.get("tenji_score_coef") or 1.0

                # ── あれ指数（レース単位）= まくりアラートフラグ用 ────────
                are_index = float(rd.get("arek", 50.0))

                # [2026-05-17] HIT/REC 両モードで分類（buy_mode別に挙動が異なる）
                common_args = dict(
                    venue           = venue,
                    pred_rank1_boat = int(pred_rank1["boat"]),
                    boat1_base      = boat1_base,
                    boat1_tenkai    = boat1_tenkai,
                    pred1_base      = pred1_base,
                    pred1_tenkai    = pred1_tenkai,
                    boat1_tenji     = boat1_tenji,
                    pred1_tenji     = pred1_tenji,
                    are_index       = are_index,
                )
                pat_hit = _classify_race(**common_args, buy_mode="hit")
                pat_rec = _classify_race(**common_args, buy_mode="rec")

                # パターン名・フラグはHITを基準（両モードで同一のはずだが念のため）
                pat = pat_hit if pat_hit is not None else pat_rec

                # pat が None = 除外会場
                if pat is None:
                    rd["opt_pattern"]         = "除外会場"
                    rd["opt_points"]          = 0
                    rd["opt_points_hit"]      = 0
                    rd["opt_points_rec"]      = 0
                    rd["opt_pass_reason_hit"] = ""
                    rd["opt_pass_reason_rec"] = ""
                    rd["opt_flags"]           = {}
                else:
                    rd["opt_pattern"]         = pat.name
                    rd["opt_points"]          = pat.points           # 後方互換（HIT値）
                    rd["opt_points_hit"]      = pat_hit.points if pat_hit else 0
                    rd["opt_points_rec"]      = pat_rec.points if pat_rec else 0
                    rd["opt_pass_reason_hit"] = pat_hit.pass_reason if pat_hit else ""
                    rd["opt_pass_reason_rec"] = pat_rec.pass_reason if pat_rec else ""
                    # ── フラグ群を dict で格納（UI・将来拡張用）──────────
                    rd["opt_flags"] = {
                        "makuri_alert":   pat.flags.makuri_alert,    # まくり/まくり差しアラート
                        "sashi_alert":    pat.flags.sashi_alert,     # 差し/抜きアラート
                        "low_dividend":   pat.flags.low_dividend,    # 低配当罠フィルター
                        "sweet_spot":     pat.flags.sweet_spot,      # スイートスポット
                        "high_pop_zone":  pat.flags.high_pop_zone,   # 高人気圧縮ゾーン
                        "kimari_predict": pat.flags.kimari_predict,  # 将来: 決まり手予測
                    }
            else:
                rd["opt_pattern"]         = "中立1号艇"
                rd["opt_points"]          = 10
                rd["opt_points_hit"]      = 10
                rd["opt_points_rec"]      = 10
                rd["opt_pass_reason_hit"] = ""
                rd["opt_pass_reason_rec"] = ""
                rd["opt_flags"]           = {}
    else:
        for rno, rd in races.items():
            rd["opt_pattern"]         = "（未設定）"
            rd["opt_points"]          = 10
            rd["opt_pass_reason_hit"] = ""
            rd["opt_pass_reason_rec"] = ""
            rd["opt_flags"]           = {}

    # ── race_index_{YYYYMMDD}.json から開催情報を取得（period照合で正確に判定）──
    race_info = {}
    try:
        _ri_path2 = get_race_index_path(date)
        if _ri_path2.exists():
            with open(_ri_path2, encoding="utf-8") as _f:
                _ri = json.load(_f)
            _vi = _ri.get("venues", {}).get(venue, {})
            if _vi:
                _period = _vi.get("period", "")
                _period_match = False
                if _period and date:
                    try:
                        from datetime import datetime as _dt2
                        _year = _dt2.now().year
                        _parts = _period.replace(" ", "").split("-")
                        if len(_parts) == 2:
                            _start = _dt2.strptime(f"{_year}/{_parts[0]}", "%Y/%m/%d").date()
                            _end   = _dt2.strptime(f"{_year}/{_parts[1]}", "%Y/%m/%d").date()
                            _csv_d = _dt2.strptime(date, "%Y-%m-%d").date()
                            _period_match = _start <= _csv_d <= _end
                    except Exception:
                        pass
                if _period_match:
                    race_info = {
                        "grade":    _vi.get("grade", ""),
                        "is_joshi": bool(_vi.get("is_joshi", False)),
                        "title":    _vi.get("title", ""),
                        "period":   _period,
                        "day":      _vi.get("day", ""),
                    }
    except Exception:
        pass

    # ── [2026-05-17 追加] 展示スコアを boats に付与 ──────────────────────
    # tenji_data/*.json を読み込み、各艇に tenji_score / tenji_score_coef を付与。
    # classify_race() に渡る boat1_tenji / pred1_tenji が正しく機能するようになる。
    # 展示JSONが存在しないレースはスキップ（副作用なし）。
    _inject_tenji_scores(races, venue, date)

    return {
        "venue":     venue,
        "date":      date,
        "race_info": race_info,
        "inn_data": {
            "inn_rate":    venue_stats.get("inn_rate", 0.5),
            "arek_score":  venue_stats.get("arek_score", 50),
            "course_rates": [0] + [
                venue_stats.get("course_rates", {}).get(str(c), 0)
                for c in range(1, 7)
            ],
            "inn_2place": venue_stats.get("inn_2place", {}),
        },
        "races": {str(k): v for k, v in sorted(races.items())},
    }

# ── index.html への埋め込み ────────────────────────────
VENUE_LIST = [
    '桐生','戸田','江戸川','平和島','多摩川','浜名湖','蒲郡','常滑',
    '津','三国','びわこ','住之江','尼崎','鳴門','丸亀','児島',
    '宮島','徳山','下関','若松','芦屋','福岡','唐津','大村'
]

def inject_all_data_to_html():
    """当日CSVを全部parseしてindex.htmlのALL_DATAを書き換える"""
    # get_today_csvs() を使うことで深夜帯（0〜3時）も正しく当日CSVを取得できる
    # （today_str() は深夜帯に翌日付を返すため直接使わない）
    all_data = {v: None for v in VENUE_LIST}
    loaded = []

    for csv_path in get_today_csvs():
        data = parse_csv(csv_path)
        if data and data.get("venue") in all_data:
            all_data[data["venue"]] = data
            loaded.append(data["venue"])

    if not loaded:
        log("  ⚠ 当日CSVなし → ALL_DATA埋め込みスキップ")
        return False

    html_text = _data_js_read()

    # ALL_DATA の埋め込みブロックを正規表現で置換
    all_data_json = json.dumps(all_data, ensure_ascii=False, separators=(",", ":"))
    new_block = f"let ALL_DATA = {all_data_json};\n"

    # 既存の let ALL_DATA = {...}; を置換（複数行対応）
    pattern = r'(?:let|const) ALL_DATA = [\s\S]*?;[^\n]*\n'
    if re.search(pattern, html_text):
        html_text = re.sub(pattern, new_block, html_text)
    else:
        log("  ⚠ ALL_DATAの埋め込み位置が見つかりません")
        return False

    # ── タイムスタンプ埋め込み（差分を強制生成） ──────────
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    html_text = re.sub(r'<!-- auto_push_updated:.*?-->', '', html_text)
    html_text = html_text.replace(
        '</head>',
        f'<!-- auto_push_updated:{timestamp} --></head>',
        1
    )

    safe_text = html_text.replace('\x00', '')
    _data_js_write(safe_text)
    # [fix] ALL_DATA更新時に必ずキャッシュバスターを更新する。
    # update_cache_version() は index.html の /* __CACHE_VER__ */ を書き換えるため、
    # ブラウザが data.js を古いキャッシュから読むのを防ぐ。
    update_cache_version()
    log(f"  ✓ ALL_DATA埋め込み完了 ({timestamp}): {', '.join(loaded)}")
    return True


def inject_master_ext_to_html():
    """master_data.json の venue_kimari / tenkai_remaining を index.html に埋め込む"""
    if not MASTER_JSON.exists():
        log("  ⚠ master_data.json が見つかりません → MASTER_EXT埋め込みスキップ")
        return False

    master_ext = {
        "venue_kimari":        MASTER.get("venue_kimari", {}),
        "tenkai_remaining":    MASTER.get("tenkai_remaining", {}),
        "winner_course_order": MASTER.get("winner_course_order", {}),
        "venue_stats":         MASTER.get("venue_stats", {}),
        "course_master":       MASTER.get("course_master", {}),
        "course_master_joshi": MASTER.get("course_master_joshi", {}),  # 女子戦用コースマスタ
        "course_master_g1":    MASTER.get("course_master_g1", {}),     # SG/G1戦用コースマスタ
        "player_index":        MASTER.get("player_index", {}),
    }

    html_text = _data_js_read()
    master_ext_json = json.dumps(master_ext, ensure_ascii=False, separators=(",", ":"))
    new_block = f"let MASTER_EXT = {master_ext_json};\n"

    pattern = r'(?:let|const) MASTER_EXT = [\s\S]*?;[^\n]*\n'
    if re.search(pattern, html_text):
        html_text = re.sub(pattern, new_block, html_text)
        _data_js_write(html_text)
        vk = len(master_ext["venue_kimari"])
        tr = len(master_ext["tenkai_remaining"])
        log(f"  ✓ MASTER_EXT埋め込み完了: venue_kimari={vk}会場 tenkai_remaining={tr}会場")
        return True
    else:
        log("  ⚠ MASTER_EXTの埋め込み位置が見つかりません")
        return False


def inject_tenji_to_html(days_back=HISTORY_DAYS):
    """tenji_data/*.json を読んで index.html の TENJI_DATA を書き換える（過去日分も含む）"""
    from datetime import timedelta
    today = datetime.now().date()
    target_dates = [
        (today - timedelta(days=d)).strftime("%Y%m%d")
        for d in range(0, days_back + 1)
    ]
    tenji_all = {}  # { "venue_date_race": {frame: data, __weather: ..., ...} }

    # モーター情報キーのマッピング（JSONフィールド名 → 埋め込みキー名）
    MOTOR_KEYS = (
        ("motor_no",    "__motor_no"),
        ("motor_rate2", "__motor_rate2"),
        ("motor_rate3", "__motor_rate3"),
        ("motor_rank",  "__motor_rank"),
        ("prev_user",   "__prev_user"),
    )

    # 風情報キーのマッピング（JSONフィールド名 → 埋め込みキー名）
    WIND_KEYS = (
        ("weather",             "__weather"),
        ("weather_degree",      "__weather_degree"),
        ("water_degree",        "__water_degree"),
        ("wind_speed",          "__wind_speed"),
        ("wind_direction",      "__wind_direction"),
        ("wind_direction_text", "__wind_direction_text"),
        ("wave_height",         "__wave_height"),
    )

    # 風情報が欠落しているレースを記録（後でまとめて再取得）
    missing_wind = []  # [(fpath, venue, date_nd, race_int, embed_key), ...]

    for fpath in glob.glob(str(TENJI_DIR / "*.json")):
        fname = Path(fpath).name
        if not any(d in fname for d in target_dates):
            continue
        m = re.match(r"tenji_(.+)_(\d{8})_R?(\d+)\.json", fname)
        if not m:
            continue
        venue, date_nd, race = m.group(1), m.group(2), str(int(m.group(3)))
        embed_key = f"{venue}_{date_nd}_{race}"
        try:
            with open(fpath, encoding="utf-8") as f:
                rows = json.load(f)
            by_frame = {str(r["frame"]): r for r in rows}

            # 風情報を __プレフィックスで付与（rowsの先頭行から取得）
            wind_filled = False
            if rows:
                first = rows[0]
                for wind_key, ek_w in WIND_KEYS:
                    val = first.get(wind_key)
                    if val is not None:
                        by_frame[ek_w] = val
                        wind_filled = True

            # モーター情報を各フレームに付与（motor_no / motor_rate2 / motor_rate3 / prev_user）
            for r in rows:
                frame_key = str(r["frame"])
                if frame_key not in by_frame:
                    continue
                for motor_key, ek_m in MOTOR_KEYS:
                    val = r.get(motor_key)
                    if val is not None:
                        by_frame[frame_key][ek_m] = val

            tenji_all[embed_key] = by_frame

            # 風情報が欠落しているレースを記録（当日分のみ・展示データありの場合のみ）
            # 展示データなし（モーター情報だけのJSON）は再取得しない → 永遠に取れないため
            has_tenji = any(
                rows[i].get("lap1") is not None or rows[i].get("tenji") is not None
                for i in range(len(rows))
            ) if rows else False
            if not wind_filled and has_tenji and date_nd == today.strftime("%Y%m%d"):
                missing_wind.append((fpath, venue, date_nd, int(m.group(3)), embed_key))

        except Exception:
            continue

    # ── 風情報が欠落しているレースをバックグラウンドで再取得 ──────────────────
    # 展示データありのJSONのみ対象。pushはブロックしない。
    if missing_wind:
        log(f"  ⚠ 風情報未取得: {len(missing_wind)}レース（展示あり）→ バックグラウンドで再取得")
        import threading as _threading
        _threading.Thread(
            target=_refetch_wind_and_push,
            args=(missing_wind, tenji_all, WIND_KEYS),
            daemon=True,
        ).start()

    html_text = _data_js_read()
    tenji_json = json.dumps(tenji_all, ensure_ascii=False, separators=(",", ":"))
    new_block = f"let TENJI_DATA = {tenji_json};\n"

    pattern = r'(?:let|const) TENJI_DATA = [\s\S]*?;[^\n]*\n'
    if re.search(pattern, html_text):
        html_text = re.sub(pattern, new_block, html_text)
        _data_js_write(html_text)
        log(f"  ✓ 展示情報埋め込み完了: {len(tenji_all)}レース分")
        return True
    else:
        log("  ⚠ TENJI_DATAの埋め込み位置が見つかりません")
        return False


def _refetch_wind_and_push(missing_wind: list, tenji_all: dict, WIND_KEYS: tuple):
    """バックグラウンドで風情報を再取得し、取得できたらHTMLを更新してpush"""
    _refetch_wind(missing_wind, tenji_all, WIND_KEYS)

    has_wind = any(
        tenji_all.get(embed_key, {}).get("__wind_speed") is not None
        or tenji_all.get(embed_key, {}).get("__weather") is not None
        for _, _, _, _, embed_key in missing_wind
    )
    if not has_wind:
        log("  [BG] 風情報: 全レース取得できず → push スキップ")
        return

    log("  [BG] 風情報取得完了 → TENJI_DATA 再埋め込み＋push")
    html_text = _data_js_read()
    tenji_json = json.dumps(tenji_all, ensure_ascii=False, separators=(",", ":"))
    new_block = f"let TENJI_DATA = {tenji_json};\n"
    pattern = r'(?:let|const) TENJI_DATA = [\s\S]*?;[^\n]*\n'
    if re.search(pattern, html_text):
        html_text = re.sub(pattern, new_block, html_text)
        _data_js_write(html_text)
        git_push([INDEX_HTML])
        log("  [BG] ✓ 風情報 push 完了")
    else:
        log("  [BG] ⚠ TENJI_DATA埋め込み位置が見つかりません")


def _refetch_wind(missing_wind: list, tenji_all: dict, WIND_KEYS: tuple):
    """
    风情報が欠落しているレースを Playwright で再取得し、
    tenji_all と JSONファイルを上書きする。

    missing_wind: [(fpath, venue, date_nd, race_int, embed_key), ...]
    """
    try:
        from fetch_tenji import build_wind_url, fetch_html, parse_wind
    except ImportError:
        log("  ⚠ fetch_tenji.py が見つかりません → 風情報再取得スキップ")
        return

    for fpath, venue, date_nd, race_int, embed_key in missing_wind:
        # YYYYMMDD → YYYY-MM-DD
        date_str = f"{date_nd[:4]}-{date_nd[4:6]}-{date_nd[6:]}"
        wind_url = build_wind_url(venue, date_str, race_int)
        log(f"    再取得: {venue} {race_int}R  {wind_url}")

        wind = {}
        # 1回目: 10秒待機、2回目: 5秒だけ確認して諦める
        _poll = 10
        for attempt in range(1, 3):
            try:
                wind_html = fetch_html(
                    wind_url,
                    wait_for="CrawledRaceBeforeInfo",
                    poll_count=_poll,
                )
                wind = parse_wind(wind_html)
                if wind:
                    break
            except Exception as e:
                log(f"    [WARN] 再取得エラー ({attempt}回目): {e}")
            _poll = 5
            if attempt < 2:
                time.sleep(3)

        if not wind:
            log(f"    ✗ {venue} {race_int}R: 風情報取得できず（サイト未掲載の可能性）")
            continue

        # tenji_all の __プレフィックスキーを更新
        by_frame = tenji_all.get(embed_key, {})
        for wind_key, ek_w in WIND_KEYS:
            val = wind.get(wind_key)
            if val is not None:
                by_frame[ek_w] = val
        tenji_all[embed_key] = by_frame

        # JSONファイルも上書き（次回起動時に再取得不要にする）
        try:
            with open(fpath, encoding="utf-8") as f:
                rows = json.load(f)
            for r in rows:
                for wind_key, _ in WIND_KEYS:
                    val = wind.get(wind_key)
                    if val is not None:
                        r[wind_key] = val
            with open(fpath, "w", encoding="utf-8") as f:
                json.dump(rows, f, ensure_ascii=False, indent=2)
            log(f"    ✓ {venue} {race_int}R: 風情報取得・JSON更新完了 "
                f"({wind.get('weather','?')} {wind.get('wind_speed','?')}m/s"
                f" {wind.get('wind_direction_text','?')})")
        except Exception as e:
            log(f"    [WARN] JSON更新失敗: {e}")



def inject_comment_to_html(days_back=HISTORY_DAYS):
    """comment_data/*.json を読んで index.html の COMMENT_DATA を書き換える（過去日分も含む）"""
    from datetime import timedelta
    today = datetime.now().date()
    target_dates = [
        (today - timedelta(days=d)).strftime("%Y%m%d")
        for d in range(0, days_back + 1)
    ]
    comment_all = {}  # { "venue_date_race": {frame: data} }

    for fpath in glob.glob(str(COMMENT_DIR / "*.json")):
        fname = Path(fpath).name
        if not any(d in fname for d in target_dates):
            continue
        fname = Path(fpath).name
        # ファイル名: comment_{venue}_{date}_{race}.json or comment_{venue}_{date}_R{race}.json
        m = re.match(r"comment_(.+)_(\d{8})_R?(\d+)\.json", fname)
        if not m:
            continue
        venue, date_nd, race = m.group(1), m.group(2), str(int(m.group(3)))
        embed_key = f"{venue}_{date_nd}_{race}"
        try:
            with open(fpath, encoding="utf-8") as f:
                rows = json.load(f)
            # rows: list of {frame, comment, ...} or dict
            if isinstance(rows, list):
                by_frame = {str(r.get("frame", r.get("boat", ""))): r for r in rows}
            else:
                by_frame = rows
            comment_all[embed_key] = by_frame
        except Exception:
            continue

    html_text = _data_js_read()
    comment_json = json.dumps(comment_all, ensure_ascii=False, separators=(",", ":"))
    new_block = f"let COMMENT_DATA = {comment_json};\n"

    pattern = r'(?:let|const) COMMENT_DATA = [\s\S]*?;[^\n]*\n'
    if re.search(pattern, html_text):
        html_text = re.sub(pattern, new_block, html_text)
        _data_js_write(html_text)
        log(f"  ✓ COMMENT_DATA埋め込み完了: {len(comment_all)}レース分")
        return True
    else:
        # プレースホルダーが存在しない場合: ALL_DATA 宣言の直前に挿入する
        insert_pattern = r'(?=(?:let|const) ALL_DATA\s*=)'
        if re.search(insert_pattern, html_text):
            html_text = re.sub(insert_pattern, new_block, html_text, count=1)
            _data_js_write(html_text)
            log(f"  ✓ COMMENT_DATA埋め込み完了（ALL_DATA直前に挿入）: {len(comment_all)}レース分")
            return True
        else:
            log("  ⚠ COMMENT_DATAの埋め込み位置が見つかりません（ALL_DATAも見つからず）")
            return False


def inject_flying_to_html():
    """flying_YYYYMMDD.xlsx を読んで index.html の FLYING_DATA を書き換える"""
    # フライングデータは手動管理ファイルのため、today_str()（深夜補正あり）ではなく
    # 実際の今日の日付を使う
    today = datetime.now().strftime("%Y%m%d")
    flying_path = SCRIPTS_DIR / f"flying_{today}.xlsx"
    if not flying_path.exists():
        log(f"  ⚠ {flying_path.name} が見つかりません → FLYING_DATA埋め込みスキップ")
        return False

    try:
        df = pd.read_excel(str(flying_path), sheet_name="フライング一覧")
    except Exception as e:
        log(f"  ⚠ フライングExcel読込エラー: {e}")
        return False

    df.columns = [str(c).strip() for c in df.columns]
    required = {"会場", "レース", "枠", "選手名", "フライング", "合計F数"}
    if not required.issubset(set(df.columns)):
        log("  ⚠ フライングExcelの列が不足しています")
        return False

    # {会場: {レースno文字列: [{waku, name, flying, f_total}]}} に変換
    flying_all = {}
    for _, row in df.iterrows():
        venue  = str(row["会場"]).strip()
        race   = str(int(row["レース"])) if pd.notna(row["レース"]) else "0"
        waku   = str(row["枠"]).strip() if pd.notna(row["枠"]) else ""
        name   = str(row["選手名"]).strip() if pd.notna(row["選手名"]) else ""
        flying = str(row["フライング"]).strip() if pd.notna(row["フライング"]) else ""
        f_total = int(row["合計F数"]) if pd.notna(row["合計F数"]) else 1
        flying_all.setdefault(venue, {}).setdefault(race, []).append({
            "waku": waku, "name": name, "flying": flying, "f_total": f_total
        })

    html_text = _data_js_read()
    flying_json = json.dumps(flying_all, ensure_ascii=False, separators=(",", ":"))
    new_block = f"let FLYING_DATA = {flying_json};\n"

    pattern = r'(?:let|const) FLYING_DATA = [\s\S]*?;[^\n]*\n'
    if re.search(pattern, html_text):
        html_text = re.sub(pattern, new_block, html_text)
        _data_js_write(html_text)
        total = sum(len(v) for v in flying_all.values())
        log(f"  ✓ FLYING_DATA埋め込み完了: {len(flying_all)}会場 {total}レース分")
        return True
    else:
        log("  ⚠ FLYING_DATAの埋め込み位置が見つかりません")
        return False


def inject_result_to_html(days_back=RESULT_DAYS):
    """
    result_data/*.json を読んで index.html の RESULT_DATA を書き換える。
    RESULT_DATA = {
        "{venue}_{YYYYMMDD}_{rno}": {
            "sanrentan": [{"combo":"1-2-3","odds":4500}, ...],
            "nirentan":  [...],
            "tansho":    [...],
            "fukusho":   [...],
            "fetched_at": "..."
        }
    }
    """
    from datetime import timedelta
    today = datetime.now().date()
    target_dates = [
        (today - timedelta(days=d)).strftime("%Y%m%d")
        for d in range(0, days_back + 1)
    ]

    RESULT_DIR.mkdir(exist_ok=True)
    result_all = {}

    for fpath in glob.glob(str(RESULT_DIR / "*.json")):
        fname = Path(fpath).name
        if not any(d in fname for d in target_dates):
            continue
        m = re.match(r"result_(.+)_(\d{8})_R(\d+)\.json", fname)
        if not m:
            continue
        venue_slug, date_nd, race_str = m.group(1), m.group(2), str(int(m.group(3)))
        embed_key = f"{venue_slug}_{date_nd}_{race_str}"
        try:
            with open(fpath, encoding="utf-8") as f:
                data = json.load(f)
            result_all[embed_key] = {
                "sanrentan":  data.get("sanrentan", []),
                "nirentan":   data.get("nirentan", []),
                "tansho":     data.get("tansho", []),
                "fukusho":    data.get("fukusho", []),
                "kimari":     data.get("kimari", ""),
                "henkan":     data.get("henkan", []),
                "fetched_at": data.get("fetched_at", ""),
            }
        except Exception:
            continue

    html_text = _data_js_read()
    result_json = json.dumps(result_all, ensure_ascii=False, separators=(",", ":"))
    new_block = f"let RESULT_DATA = {result_json};\n"

    pattern = r'(?:let|const) RESULT_DATA = [\s\S]*?;[^\n]*\n'
    if re.search(pattern, html_text):
        html_text = re.sub(pattern, new_block, html_text)
        _data_js_write(html_text)
        log(f"  ✓ RESULT_DATA埋め込み完了: {len(result_all)}レース分")
        return True
    else:
        log("  ⚠ RESULT_DATAの埋め込み位置が見つかりません")
        return False


# ══════════════════════════════════════════════════════════════════
# フェーズ1: data/ ディレクトリへのJSON書き出し
#   - HTMLは一切変更しない（既存の埋め込みはそのまま継続）
#   - data/*.json を追加で書き出すだけ → 安全に並行稼働可能
#   - フェーズ2以降でHTMLのfetchローダーが参照し始める
# ══════════════════════════════════════════════════════════════════

def write_result_json(days_back=None):
    """
    result_data/*.json を data/result_YYYYMMDD.json として日付単位にまとめて書き出す。
    フェーズ1: HTMLへの埋め込み(inject_result_to_html)と並行稼働。干渉なし。

    出力フォーマット:
        data/result_20260511.json = {
            "{slug}_{rno}": {
                "sanrentan": [...], "nirentan": [...],
                "tansho": [...], "fukusho": [...],
                "kimari": "逃げ", "henkan": [], "fetched_at": "..."
            }, ...
        }
    """
    if days_back is None:
        days_back = RESULT_DAYS
    from datetime import timedelta
    today = datetime.now().date()

    DATA_DIR.mkdir(exist_ok=True)
    written = 0

    # 日付ごとにまとめる
    days_data: dict[str, dict] = {}
    for fpath in glob.glob(str(RESULT_DIR / "*.json")):
        fname = Path(fpath).name
        m = re.match(r"result_(.+)_(\d{8})_R(\d+)\.json", fname)
        if not m:
            continue
        venue_slug, date_nd, race_str = m.group(1), m.group(2), str(int(m.group(3)))

        # 対象日付か確認
        try:
            file_date = datetime.strptime(date_nd, "%Y%m%d").date()
        except ValueError:
            continue
        if (today - file_date).days > days_back:
            continue

        try:
            with open(fpath, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue

        race_key = f"{venue_slug}_{race_str}"
        days_data.setdefault(date_nd, {})[race_key] = {
            "sanrentan":  data.get("sanrentan", []),
            "nirentan":   data.get("nirentan", []),
            "tansho":     data.get("tansho", []),
            "fukusho":    data.get("fukusho", []),
            "kimari":     data.get("kimari", ""),
            "henkan":     data.get("henkan", []),
            "fetched_at": data.get("fetched_at", ""),
        }

    # 日付ごとにファイル書き出し
    for date_nd, races in days_data.items():
        out_path = DATA_DIR / f"result_{date_nd}.json"
        with open(out_path, 'w', encoding='utf-8') as _wf:
            _wf.write(json.dumps(races, ensure_ascii=False, separators=(",", ":")))
        written += 1

    # 対象期間外の古いファイルを削除
    cutoff = today - timedelta(days=days_back)
    for fpath in glob.glob(str(DATA_DIR / "result_*.json")):
        fname = Path(fpath).name
        m = re.match(r"result_(\d{8})\.json", fname)
        if m:
            try:
                fdate = datetime.strptime(m.group(1), "%Y%m%d").date()
                if fdate < cutoff:
                    Path(fpath).unlink()
                    log(f"  [JSON] 古い result_{m.group(1)}.json を削除")
            except ValueError:
                pass

    log(f"  [JSON] result_YYYYMMDD.json 書き出し完了: {written}日分")
    return written > 0


def write_history_json(days_back=None):
    """
    過去 days_back 日分のCSVを data/history_YYYYMMDD.json として書き出す。
    フェーズ1: inject_history_to_html() と並行稼働。干渉なし。

    出力フォーマット:
        data/history_20260510.json = {"鳴門": {...vdata...}, "桐生": {...}, ...}
    """
    if days_back is None:
        days_back = HISTORY_DAYS
    from datetime import timedelta
    today = datetime.now().date()

    DATA_DIR.mkdir(exist_ok=True)
    written = 0

    for d in range(1, days_back + 1):
        target = today - timedelta(days=d)
        target_str = target.strftime("%Y-%m-%d")
        date_nd    = target.strftime("%Y%m%d")

        # 既に出力済みのファイルはスキップ（起動時の重複パースを防ぐ）
        out_path = DATA_DIR / f"history_{date_nd}.json"
        if out_path.exists():
            continue

        day_data = {}

        for csv_path in glob.glob(str(CSV_DIR / "*.csv")):
            if target_str not in Path(csv_path).name:
                continue
            data = _cached_parse_csv(csv_path)
            if data and data.get("venue"):
                day_data[data["venue"]] = data

        if day_data:
            out_path = DATA_DIR / f"history_{date_nd}.json"
            with open(out_path, 'w', encoding='utf-8') as _wf:
                _wf.write(json.dumps(day_data, ensure_ascii=False, separators=(",", ":")))
            written += 1
            log(f"  [JSON] history_{date_nd}.json: {', '.join(day_data.keys())}")

    # 対象期間外を削除
    cutoff = today - timedelta(days=days_back)
    for fpath in glob.glob(str(DATA_DIR / "history_*.json")):
        fname = Path(fpath).name
        m = re.match(r"history_(\d{8})\.json", fname)
        if m:
            try:
                fdate = datetime.strptime(m.group(1), "%Y%m%d").date()
                if fdate < cutoff:
                    Path(fpath).unlink()
                    log(f"  [JSON] 古い history_{m.group(1)}.json を削除")
            except ValueError:
                pass

    log(f"  [JSON] history_YYYYMMDD.json 書き出し完了: {written}日分")
    return written > 0


def write_master_ext_json():
    """
    master_data.json の内容を data/master_ext.json として書き出す。
    フェーズ1: inject_master_ext_to_html() と並行稼働。干渉なし。
    """
    if not MASTER_JSON.exists():
        log("  [JSON] master_data.json なし → master_ext.json スキップ")
        return False

    DATA_DIR.mkdir(exist_ok=True)
    master_ext = {
        "venue_kimari":        MASTER.get("venue_kimari", {}),
        "tenkai_remaining":    MASTER.get("tenkai_remaining", {}),
        "winner_course_order": MASTER.get("winner_course_order", {}),
        "venue_stats":         MASTER.get("venue_stats", {}),
        "course_master":       MASTER.get("course_master", {}),
        "course_master_joshi": MASTER.get("course_master_joshi", {}),  # 女子戦用コースマスタ
        "player_index":        MASTER.get("player_index", {}),
    }
    out_path = DATA_DIR / "master_ext.json"
    with open(out_path, 'w', encoding='utf-8') as _wf:
        _wf.write(json.dumps(master_ext, ensure_ascii=False, separators=(",", ":")))
    log("  [JSON] master_ext.json 書き出し完了")
    return True


# ── CSVパースキャッシュ ─────────────────────────────────────────────────────
# write_all_json_files() の呼び出し内で同じCSVを複数回 parse_csv() するのを防ぐ。
# write_all_json_files() の先頭でクリアされる。
_csv_parse_cache: dict = {}

def _cached_parse_csv(filepath: str):
    """parse_csv() の結果をセッション内でキャッシュして返す"""
    if filepath not in _csv_parse_cache:
        _csv_parse_cache[filepath] = parse_csv(filepath)
    return _csv_parse_cache[filepath]


def write_today_json():
    """
    当日CSVを data/today_YYYYMMDD.json として書き出す。
    フェーズ1: inject_all_data_to_html() と並行稼働。干渉なし。

    出力フォーマット:
        data/today_20260512.json = {"鳴門": {...vdata...}, "桐生": {...}, ...}
    """
    today = today_str()
    today_nd = today.replace("-", "")
    today_data = {}

    for csv_path in glob.glob(str(CSV_DIR / "*.csv")):
        if today not in Path(csv_path).name:
            continue
        data = _cached_parse_csv(csv_path)
        if data and data.get("venue"):
            today_data[data["venue"]] = data

    if not today_data:
        log("  [JSON] 当日CSV なし → today_YYYYMMDD.json スキップ")
        return False

    DATA_DIR.mkdir(exist_ok=True)
    out_path = DATA_DIR / f"today_{today_nd}.json"
    with open(out_path, 'w', encoding='utf-8') as _wf:
        _wf.write(json.dumps(today_data, ensure_ascii=False, separators=(",", ":")))
    log(f"  [JSON] today_{today_nd}.json 書き出し完了: {', '.join(today_data.keys())}")
    return True


def write_tenji_json_file(days_back=HISTORY_DAYS):
    """
    tenji_data/*.json を読んで data/tenji_YYYYMMDD.json を書き出す。

    【目的】
    sample.js が 3分ごとに fetch する `data/tenji_YYYYMMDD.json` を生成する。
    inject_tenji_to_html() が data.js に埋め込む処理とは完全に独立しており、
    どちらの処理にも影響を与えない。

    【出力フォーマット】
        data/tenji_20260522.json = {
            "heiwajima_20260522_1": { "1": {...}, "__weather": ..., ... },
            "heiwajima_20260522_2": { ... },
            ...
        }
    inject_tenji_to_html() が構築する tenji_all dict と同一構造なので
    sample.js 側のパーサ変更は不要。
    """
    from datetime import timedelta
    today = datetime.now().date()
    target_dates = [
        (today - timedelta(days=d)).strftime("%Y%m%d")
        for d in range(0, days_back + 1)
    ]

    MOTOR_KEYS = (
        ("motor_no",    "__motor_no"),
        ("motor_rate2", "__motor_rate2"),
        ("motor_rate3", "__motor_rate3"),
        ("motor_rank",  "__motor_rank"),
        ("prev_user",   "__prev_user"),
    )
    WIND_KEYS = (
        ("weather",             "__weather"),
        ("weather_degree",      "__weather_degree"),
        ("water_degree",        "__water_degree"),
        ("wind_speed",          "__wind_speed"),
        ("wind_direction",      "__wind_direction"),
        ("wind_direction_text", "__wind_direction_text"),
        ("wave_height",         "__wave_height"),
    )

    # 日付ごとに tenji_all を仕分け
    tenji_by_date: dict[str, dict] = {}

    for fpath in glob.glob(str(TENJI_DIR / "*.json")):
        fname = Path(fpath).name
        # 対象日付かチェック
        matched_date = next((d for d in target_dates if d in fname), None)
        if not matched_date:
            continue
        m = re.match(r"tenji_(.+)_(\d{8})_R?(\d+)\.json", fname)
        if not m:
            continue
        venue, date_nd, race = m.group(1), m.group(2), str(int(m.group(3)))
        embed_key = f"{venue}_{date_nd}_{race}"

        try:
            with open(fpath, encoding="utf-8") as f:
                rows = json.load(f)
            by_frame = {str(r["frame"]): r for r in rows}

            if rows:
                first = rows[0]
                for wind_key, ek_w in WIND_KEYS:
                    val = first.get(wind_key)
                    if val is not None:
                        by_frame[ek_w] = val

            for r in rows:
                frame_key = str(r["frame"])
                if frame_key not in by_frame:
                    continue
                for motor_key, ek_m in MOTOR_KEYS:
                    val = r.get(motor_key)
                    if val is not None:
                        by_frame[frame_key][ek_m] = val

            tenji_by_date.setdefault(date_nd, {})[embed_key] = by_frame
        except Exception:
            continue

    if not tenji_by_date:
        log("  [JSON] tenji_data/ に対象ファイルなし → tenji_YYYYMMDD.json スキップ")
        return False

    DATA_DIR.mkdir(exist_ok=True)
    written = []
    for date_nd, tenji_all in tenji_by_date.items():
        out_path = DATA_DIR / f"tenji_{date_nd}.json"
        with open(out_path, 'w', encoding='utf-8') as _wf:
            _wf.write(json.dumps(tenji_all, ensure_ascii=False, separators=(",", ":")))
        written.append(f"tenji_{date_nd}.json({len(tenji_all)}R)")

    log(f"  [JSON] {', '.join(written)} 書き出し完了")
    return True


def write_data_index():
    """
    data/index.json を書き出す。
    存在する result_*.json / history_*.json の日付リストを記録し、
    ブラウザ側が「存在しない日付」に無駄なfetchをしないようにする。

    出力フォーマット:
        {
          "result_dates":  ["20260512", "20260511", ...],  // 新しい順
          "history_dates": ["20260511", "20260510", ...],  // 新しい順
          "updated": "2026-05-12 09:30:00"
        }
    """
    DATA_DIR.mkdir(exist_ok=True)

    result_dates = sorted(
        [re.sub(r"result_(\d{8})\.json", r"\1", Path(p).name)
         for p in glob.glob(str(DATA_DIR / "result_*.json"))
         if re.match(r"result_\d{8}\.json", Path(p).name)],
        reverse=True
    )
    history_dates = sorted(
        [re.sub(r"history_(\d{8})\.json", r"\1", Path(p).name)
         for p in glob.glob(str(DATA_DIR / "history_*.json"))
         if re.match(r"history_\d{8}\.json", Path(p).name)],
        reverse=True
    )

    index = {
        "result_dates":  result_dates,
        "history_dates": history_dates,
        "updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    out_path = DATA_DIR / "index.json"
    with open(out_path, 'w', encoding='utf-8') as _wf:
        _wf.write(json.dumps(index, ensure_ascii=False, separators=(",", ":")))
    log(f"  [JSON] data/index.json 更新: result={len(result_dates)}日 history={len(history_dates)}日")
    return True


def write_all_json_files():
    """
    フェーズ1: data/*.json を一括書き出しするエントリポイント。
    inject_*_to_html() の各呼び出しの直後に追加するだけで動作する。
    HTMLへの影響はゼロ。

    [最適化] 当日CSVのパース結果を _csv_parse_cache に保存し、
    write_today_json / write_history_json 間で重複 parse_csv() を避ける。
    """
    _csv_parse_cache.clear()  # 古いキャッシュをリセット
    write_today_json()
    write_history_json()
    write_result_json()
    try:
        write_master_ext_json()
    except Exception as _e:
        log(f"  ⚠ write_master_ext_json 失敗（スキップして続行）: {_e}")
    write_tenji_json_file()  # data/tenji_YYYYMMDD.json を出力（sample.js の fetch 対象）
    write_data_index()       # 最後にインデックスを更新


def get_data_dir_files():
    """git add 用に data/ 内の全JSONを返す"""
    if not DATA_DIR.exists():
        return []
    return list(DATA_DIR.glob("*.json"))


def fetch_result_for_venues(venues_in_csv: dict[str, str]) -> bool:
    """
    CSV到着済み会場の結果をバックグラウンドで随時取得する。
    メインループとは完全に独立したスレッドで動作するため、
    展示情報・コメントのpushを遅延させない。
    レース確定後でないと払戻が出ないため、既取得レースはスキップ。
    venues_in_csv: {会場名: "YYYY-MM-DD"} の辞書

    Returns
    -------
    True  : 全レースが確定済み（以降の呼び出し不要）
    False : 未確定レースが残っている（引き続き5分ごとに呼ぶ）
    """
    if not FETCH_RESULT_PY.exists():
        log(f"  ⚠ {FETCH_RESULT_PY.name} が見つかりません → 結果取得スキップ")
        return False

    RESULT_DIR.mkdir(exist_ok=True)

    def fetch_one(args):
        slug, date_nd, race = args
        fname = RESULT_DIR / f"result_{slug}_{date_nd}_R{race:02d}.json"
        # 取得済みはスキップ
        if fname.exists():
            try:
                with open(fname, encoding="utf-8") as f:
                    existing = json.load(f)
                if existing.get("sanrentan") or existing.get("cancelled"):
                    return slug, race, "skip"
            except Exception:
                pass
        result = subprocess.run(
            [sys.executable, str(FETCH_RESULT_PY),
             "--venue", slug, "--date", date_nd, "--race", str(race),
             "--out", str(RESULT_DIR)],
            capture_output=True, timeout=60
        )
        return slug, race, "ok" if result.returncode == 0 else "fail"

    tasks = []
    for venue_name, date_raw in venues_in_csv.items():
        slug = VENUE_SLUG.get(venue_name)
        if not slug:
            continue
        date_nd = date_raw.replace("-", "")
        for race in range(1, 13):
            tasks.append((slug, date_nd, race))

    if not tasks:
        return True

    log(f"  結果取得開始: {list(venues_in_csv.keys())} ({len(tasks)}R)")
    fetched = 0
    skipped = 0
    # max_workers=2 に抑えてサーバー負荷・タイムアウトを軽減
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {executor.submit(fetch_one, t): t for t in tasks}
        for f in as_completed(futures):
            try:
                slug, race, status = f.result()
                if status == "ok":
                    fetched += 1
                    log(f"    {slug} {race}R 結果取得✓")
                elif status == "skip":
                    skipped += 1
            except Exception as e:
                log(f"    結果取得エラー: {e}")

    if fetched > 0:
        # フェーズ3: HTMLへの埋め込みを停止 → data/*.json + fetchに完全移行
        # inject_result_to_html()
        write_result_json()    # data/result_YYYYMMDD.json を更新
        write_data_index()     # インデックスも更新
        # commit+pushはキューに委譲（他系統のpushと重ならないように）
        with _git_lock:
            run(["git", "add", str(INDEX_HTML)])
            code, out = _run_nolock(["git", "status", "--porcelain"])
            tracked = [l for l in out.strip().splitlines() if not l.startswith("??")]
            if tracked:
                msg = f"result update {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                _push_queue.put(("raw", None, msg))
                log(f"  結果取得完了: {fetched}レース → pushキューに追加")
            else:
                log(f"  結果取得完了: {fetched}レース → 変更なし（スキップ）")

    # 全タスクがスキップ（=全レース確定済み）なら True を返して以降の呼び出しを止める
    all_done = (skipped == len(tasks))
    if all_done:
        log("  ✅ 全レース結果確定済み → 結果取得ループ終了")
    return all_done


def inject_history_to_html(days_back=HISTORY_DAYS):
    """
    過去 days_back 日分のCSVを読んで index.html の ALL_DATA_HISTORY を書き換える。
    ALL_DATA_HISTORY = {"2026-05-04": {"鳴門": {...}, ...}, "2026-05-03": {...}}
    """
    from datetime import timedelta
    today = datetime.now().date()
    history = {}

    for d in range(1, days_back + 1):
        target = today - timedelta(days=d)
        target_str = target.strftime("%Y-%m-%d")  # YYYY-MM-DD
        all_data_day = {v: None for v in VENUE_LIST}
        loaded = []

        for csv_path in glob.glob(str(CSV_DIR / "*.csv")):
            fname = Path(csv_path).name
            if target_str not in fname:
                continue
            data = parse_csv(csv_path)
            if data and data.get("venue") in all_data_day:
                all_data_day[data["venue"]] = data
                loaded.append(data["venue"])

        if loaded:
            history[target_str] = all_data_day
            log(f"  history {target_str}: {', '.join(loaded)}")

    html_text = _data_js_read()
    history_json = json.dumps(history, ensure_ascii=False, separators=(",", ":"))
    new_block = f"let ALL_DATA_HISTORY = {history_json};\n"

    pattern = r'(?:let|const) ALL_DATA_HISTORY = [\s\S]*?;[^\n]*\n'
    if re.search(pattern, html_text):
        html_text = re.sub(pattern, new_block, html_text)
        _data_js_write(html_text)
        # [fix] data.js 書き換え後は index.html の v= も必ず更新する。
        # しないとブラウザが古い data.js をキャッシュし続け日付が切り替わらない。
        update_cache_version()
        log(f"  ✓ ALL_DATA_HISTORY埋め込み完了: {len(history)}日分")
        return True
    else:
        log("  ⚠ ALL_DATA_HISTORYの埋め込み位置が見つかりません")
        return False


def fetch_and_inject_race_index():
    """
    公式サイトから本日の開催グレード・タイトル情報を取得し、
    index.html の RACE_INDEX_DATA を書き換える。
    fetch_race_index.py を別プロセスで実行して race_index.json を生成し、
    その内容を HTML に埋め込む。
    """
    # fetch_race_index.py で race_index.json を生成
    if FETCH_RACE_INDEX_PY.exists():
        log("  公式サイトから開催グレード情報を取得中...")
        try:
            result = subprocess.run(
                [sys.executable, str(FETCH_RACE_INDEX_PY)],
                capture_output=True, timeout=120
                # text/encoding を指定しない → bytes で受け取りデコードエラーを回避
            )
            if result.returncode != 0:
                err = (result.stderr or b"").decode("utf-8", errors="replace")[:200]
                log(f"  ⚠ race_index 取得失敗: {err}")
            else:
                log("  ✓ race_index.json 生成完了")
        except Exception as e:
            log(f"  ⚠ race_index 取得中に例外: {e}")
    else:
        log(f"  ⚠ {FETCH_RACE_INDEX_PY.name} が見つかりません → スキップ")

    # race_index_{YYYYMMDD}.json を読んで HTML に埋め込む
    race_index_path = get_race_index_path()  # 当日分
    if not race_index_path.exists():
        log("  ⚠ race_index.json が見つかりません → RACE_INDEX_DATA埋め込みスキップ")
        return False

    try:
        with open(race_index_path, encoding="utf-8") as f:
            race_index = json.load(f)
    except Exception as e:
        log(f"  ⚠ race_index.json 読込エラー: {e}")
        return False

    html_text = _data_js_read()
    race_index_json = json.dumps(race_index, ensure_ascii=False, separators=(",", ":"))
    new_block = f"let RACE_INDEX_DATA = {race_index_json};\n"

    pattern = r'(?:let|const) RACE_INDEX_DATA = [^\n]*\n'
    if re.search(pattern, html_text):
        html_text = re.sub(pattern, new_block, html_text)
        _data_js_write(html_text)
        log(f"  ✓ RACE_INDEX_DATA埋め込み完了: {len(race_index.get('venues', {}))}会場")
        return True
    else:
        log("  ⚠ RACE_INDEX_DATAの埋め込み位置が見つかりません")
        return False


def inject_odds_to_html() -> bool:
    """
    odds_data/*.json を読み込んで index.html の ODDS_DATA を書き換える。

    index.html 内に以下のプレースホルダーが必要（RESULT_DATA の直前推奨）:
        /* __ODDS_DATA__ */
        const ODDS_DATA = {};

    埋め込み後の形式:
        const ODDS_DATA = {
          "常滑": {
            "6": {
              "3t":  {"1-2-3": 12.5, ...},
              "3f":  {...},
              "2t":  {...},
              "2f":  {...},
              "tan": {...}
            }
          }
        };
    """
    ODDS_DIR.mkdir(exist_ok=True)

    # odds_data/ から全JSONを読み込んで { 会場名: { レースno: {種別: {combo: odds} } } } に集約
    all_odds: dict = {}
    slug_venue = {v: k for k, v in VENUE_SLUG.items()}  # スラッグ→会場名の逆引き

    for fpath in sorted(ODDS_DIR.glob("odds_*.json")):
        # ファイル名: odds_{slug}_{YYYYMMDD}_R{XX}.json
        m = re.match(r"odds_([a-z]+)_(\d{8})_R(\d{2})\.json$", fpath.name)
        if not m:
            continue
        slug, _date_nd, rno_str = m.group(1), m.group(2), str(int(m.group(3)))
        venue = slug_venue.get(slug, slug)
        # 日付キー: YYYYMMDD → YYYY-MM-DD
        date_key = f"{_date_nd[:4]}-{_date_nd[4:6]}-{_date_nd[6:]}"

        try:
            # 空ファイル（書き込み途中で落ちた残骸）はスキップして削除
            if fpath.stat().st_size == 0:
                log(f"  ⚠ 空ファイルを削除: {fpath.name}")
                fpath.unlink(missing_ok=True)
                continue
            with open(fpath, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            log(f"  ⚠ オッズJSON読み込み失敗 {fpath.name}: {e}")
            continue

        # fetched_at はHTMLサイズ削減のため除外。final フラグはそのまま残す
        race_data = {k: v for k, v in data.items() if k != "fetched_at"}
        # 構造: {日付: {会場: {レースno: {...}}}} で過去日も正しく参照できるようにする
        all_odds.setdefault(date_key, {}).setdefault(venue, {})[rno_str] = race_data

    html_text = _data_js_read()
    odds_json  = json.dumps(all_odds, ensure_ascii=False, separators=(",", ":"))
    new_block  = f"const ODDS_DATA = {odds_json};"

    if "const ODDS_DATA" in html_text:
        # 既存の宣言をまるごと置換（ネストしたJSONに対応するため括弧の深さで終端を検出）
        start = html_text.index("const ODDS_DATA")
        brace_start = html_text.index("{", start)
        depth = 0
        i = brace_start
        while i < len(html_text):
            if html_text[i] == "{":
                depth += 1
            elif html_text[i] == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1  # "}" の次
                    if html_text[end:end+1] == ";":
                        end += 1  # ";" も含める
                    break
            i += 1
        html_text = html_text[:start] + new_block + html_text[end:]
    elif "/* __ODDS_DATA__ */" in html_text:
        html_text = html_text.replace(
            "/* __ODDS_DATA__ */",
            f"/* __ODDS_DATA__ */\n{new_block}",
        )
    else:
        log("  ⚠ ODDS_DATA のプレースホルダーが index.html に見つかりません")
        log("    index.html に以下を追加してください（RESULT_DATA の直前推奨）:")
        log("      /* __ODDS_DATA__ */")
        log("      const ODDS_DATA = {};")
        return False

    _data_js_write(html_text)
    total_races = sum(len(races) for venues in all_odds.values() for races in venues.values())
    log(f"  ✓ ODDS_DATA埋め込み完了: {len(all_odds)}日分 / {total_races}レース分")
    return True



def _build_deadline_map(venues_in_csv: dict) -> dict:
    """
    締め切り時刻マップ {venue名: {rno: "HH:MM"}} を構築して返す。

    取得優先順:
      1. 当日CSV の「締切時刻」列（最速・オフライン）
      2. boatrace.jp 公式サイト（CSVに列がない・空の場合のフォールバック）

    fetch_all_races() が期待する形式:
      {"常滑": {1: "10:00", 2: "10:30", ...}, "びわこ": {...}, ...}
    """
    deadline_map: dict = {}

    # ── Step1: CSVから読み込み ───────────────────────────────────────────────
    for csv_path in get_today_csvs():
        try:
            try:
                df = pd.read_csv(csv_path, encoding="utf-8")
            except UnicodeDecodeError:
                df = pd.read_csv(csv_path, encoding="shift_jis")

            if "会場" not in df.columns or "締切時刻" not in df.columns:
                continue

            venue = str(df.iloc[0]["会場"]).strip()
            if venue not in venues_in_csv:
                continue

            venue_map: dict = {}
            for _, row in df.iterrows():
                rno_raw = row.get("レース", "")
                dl_raw  = str(row.get("締切時刻", "")).strip()
                if not str(rno_raw).isdigit() or not dl_raw or dl_raw in ("nan", ""):
                    continue
                rno = int(rno_raw)
                if rno not in venue_map:
                    # "HH:MM" 形式に正規化（"15:20:00" → "15:20" なども対応）
                    venue_map[rno] = dl_raw[:5] if len(dl_raw) >= 5 else dl_raw

            if venue_map:
                deadline_map[venue] = venue_map

        except Exception:
            continue

    # CSVで全会場取得できていれば終了
    csv_venues = set(deadline_map.keys())
    missing_venues = [v for v in venues_in_csv if v not in csv_venues]
    if not missing_venues:
        log(f"  締め切り時刻マップ(CSV): {sum(len(v) for v in deadline_map.values())}レース分")
        return deadline_map

    # ── Step2: 公式サイトからフォールバック取得 ──────────────────────────────
    log(f"  CSVに締切時刻なし: {missing_venues} → boatrace.jp から取得中...")
    try:
        from fetch_deadlines import fetch_deadlines_official, VENUE_JCD as DL_VENUE_JCD
    except ImportError:
        log("  ⚠ fetch_deadlines.py が見つかりません → 締切時刻なしで続行")
        return deadline_map

    date_str = list(venues_in_csv.values())[0] if venues_in_csv else None

    for venue in missing_venues:
        if not date_str:
            continue
        # fetch_deadlines_officialはslugを受け取る
        slug = VENUE_SLUG.get(venue)
        if not slug:
            continue
        try:
            dl = fetch_deadlines_official(slug, date_str)
            if dl:
                deadline_map[venue] = dl   # {rno(int): "HH:MM"}
                log(f"  ✓ {venue}: {len(dl)}R分の締切時刻を公式から取得")
            else:
                log(f"  ⚠ {venue}: 公式サイトからも締切時刻取得失敗")
        except Exception as e:
            log(f"  ⚠ {venue}: 公式取得エラー: {e}")

    total = sum(len(v) for v in deadline_map.values())
    log(f"  締め切り時刻マップ確定: {len(deadline_map)}会場 / {total}レース分")
    return deadline_map


def fetch_odds_for_venues(venues_in_csv: dict) -> bool:
    """
    当日CSVに存在する会場のオッズを「1巡」取得して odds_data/ に保存する。

    fetch_odds.py の fetch_all_races() を呼び出す薄いラッパー。
    ループ制御は呼び出し元（_odds_loop_worker）が行う。
    失敗しても例外を外に投げず False を返す（メインループを止めない）。

    Returns
    -------
    True: 取得成功（アクティブレースの有無に関わらず）
    False: インポートエラー or 例外
    """
    try:
        from fetch_odds import fetch_all_races
    except ImportError:
        log("  ⚠ fetch_odds.py が見つかりません → オッズ取得スキップ")
        return False

    # CSVと公式サイトから締め切り時刻マップを構築
    deadline_map = _build_deadline_map(venues_in_csv)
    if not deadline_map:
        log("  ⚠ 締め切り時刻マップ取得不可 → レース番号順で取得")

    try:
        log(f"  オッズ取得開始（締め切り近い順）: {list(venues_in_csv.keys())}")
        saved, _wait, _has_active = fetch_all_races(
            venues_in_csv, verbose=True, deadline_map=deadline_map
        )
        log(f"  ✓ オッズ1巡完了: {len(saved)}ファイル保存")
        return True
    except Exception as e:
        log(f"  ✕ オッズ取得エラー: {e}")
        return False


# ── オッズ永続ループワーカー ───────────────────────────────────────────────────
# このスレッドが fetch_all_races() を繰り返し呼び出す。
# スレッドが例外で死んでもメインループが検知して再起動する。
import threading as _threading
_odds_worker_thread: Optional[_threading.Thread] = None
_odds_worker_stop   = _threading.Event()      # 停止シグナル
_odds_worker_done   = False                   # 正常終了フラグ（全締め切り後の再起動防止）

# data.js への書き込みを排他制御するロック
# 複数スレッドが同時に write_text() を呼ぶと Windows で OSError(22) が発生するため
_data_js_lock = _threading.Lock()

# ── git操作を排他制御するロック ───────────────────────────────────────────────
# 複数スレッド（メインループ・バックグラウンド買い目計算・オッズループ・結果取得）が
# 同時に git add/commit/push を実行すると index.lock の競合 (WinError 32) が発生する。
# すべての git 操作をこのロックで直列化して競合を防ぐ。
_git_lock = _threading.Lock()

# ── pushキュー: 全系統のpushをここに集約して直列処理 ──────────────────────────
# GitHub Pagesは短時間に複数pushが来ると前のデプロイをCancelledにする。
# 全pushをこのキューに入れ、専用ワーカーが順番に処理することで
# Cancelledを防ぐ。
#
# キューのアイテム形式:
#   ("files",  [Path, ...], commit_msg)   → 通常のファイルpush
#   ("raw",    None,        commit_msg)   → git add済み想定・commit+pushのみ
#
_push_queue: queue.Queue = queue.Queue()
_DEPLOY_WAIT_SEC = 130  # GitHub Pagesデプロイ完了までの待機秒数（約2分）

def _push_queue_worker():
    """
    pushキューを順番に処理する専用スレッド。
    前のpushから _DEPLOY_WAIT_SEC 秒待ってから次を実行することで
    GitHub Pages の Cancelled 連鎖を防ぐ。
    """
    last_push_time = 0.0
    while True:
        try:
            item = _push_queue.get(timeout=5)
        except queue.Empty:
            continue

        if item is None:  # 終了シグナル
            break

        kind, files, msg = item

        # 前のpushからの経過時間が足りなければ待機
        elapsed = time.time() - last_push_time
        if elapsed < _DEPLOY_WAIT_SEC and last_push_time > 0:
            wait = _DEPLOY_WAIT_SEC - elapsed
            log(f"  [PushQueue] ⏳ デプロイ完了待ち {wait:.0f}秒...")
            time.sleep(wait)

        try:
            with _git_lock:
                if kind == "files" and files:
                    for f in files:
                        _run_nolock(["git", "add", str(f)])

                code, out = _run_nolock(["git", "status", "--porcelain"])
                tracked = [l for l in out.strip().splitlines() if not l.startswith("??")]
                if not tracked:
                    log(f"  [PushQueue] 差分なし → スキップ ({msg})")
                    _push_queue.task_done()
                    continue

                _run_nolock(["git", "commit", "-m", msg])
                code, _ = _run_nolock(["git", "push", "origin", "main"])
                if code != 0:
                    code, _ = _run_nolock(["git", "push", "origin", "master"])

            if code == 0:
                last_push_time = time.time()
                log(f"  [PushQueue] ✓ push完了: {msg}")
            else:
                log(f"  [PushQueue] ✕ push失敗: {msg}")

        except Exception as e:
            log(f"  [PushQueue] ✕ 例外: {e}")

        _push_queue.task_done()

# ワーカースレッドを起動
_push_queue_thread = _threading.Thread(target=_push_queue_worker, daemon=True)
_push_queue_thread.start()



# data.js に必要なプレースホルダー宣言一覧
_DATA_JS_REQUIRED_VARS = [
    ("let",   "ALL_DATA",         "{}"),
    ("let",   "ALL_DATA_HISTORY", "{}"),
    ("let",   "TENJI_DATA",       "{}"),
    ("let",   "COMMENT_DATA",     "{}"),
    ("let",   "FLYING_DATA",      "{}"),
    ("let",   "MASTER_EXT",       "null"),
    ("let",   "RESULT_DATA",      "{}"),
    ("let",   "RACE_INDEX_DATA",  "{}"),
    ("const", "ODDS_DATA",        "{}"),
]

def _data_js_ensure_placeholders() -> None:
    """
    data.js を読み込み、必要な変数宣言が欠けていれば補完して書き直す。
    強制終了・初期化後に宣言が消えた場合の自動修復。
    """
    if not DATA_JS.exists():
        return
    try:
        text = DATA_JS.read_text(encoding="utf-8")
    except Exception:
        return
    added = []
    for kw, varname, default in _DATA_JS_REQUIRED_VARS:
        if re.search(r'(?:let|const)\s+' + re.escape(varname) + r'\s*=', text):
            continue
        text = f"{kw} {varname} = {default};\n" + text
        added.append(varname)
    if added:
        try:
            with open(DATA_JS, 'w', encoding='utf-8') as _wf:
                _wf.write(text)
            log(f"  [data.js] 欠損宣言を補完: {', '.join(added)}")
        except Exception as e:
            log(f"  [data.js] 補完書き込み失敗: {e}")

def _data_js_read() -> str:
    """ロックを取得してから data.js を読み込む"""
    with _data_js_lock:
        # DATA_JS が存在すればそちらを、なければ INDEX_HTML にフォールバック
        target = DATA_JS if DATA_JS.exists() else INDEX_HTML
        return target.read_text(encoding="utf-8")


def _data_js_write(text: str) -> None:
    """ロックを取得してから data.js に書き込む"""
    with _data_js_lock:
        target = DATA_JS if DATA_JS.exists() else INDEX_HTML
        # Windows の OSError: [Errno 22] 対策:
        # NUL文字(\x00)および他のWindows不正制御文字を除去する
        # （改行\x0a・タブ\x09・CR\x0dは正常なので残す）
        cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
        try:
            with open(target, 'w', encoding='utf-8') as _wf:
                _wf.write(cleaned)
        except OSError as e:
            log(f"  [data.js] ✕ 書き込み失敗: {e} → 一時ファイル経由でリトライ")
            import tempfile, shutil as _shutil
            with tempfile.NamedTemporaryFile('w', encoding='utf-8', delete=False,
                                            dir=str(target.parent), suffix='.tmp') as tf:
                tf.write(cleaned)
                tmp_path = tf.name
            _shutil.move(tmp_path, str(target))


def _check_missing_tenji_and_odds(venues: dict, deadline_map: dict) -> None:
    """
    全レース終了後に展示情報・オッズが取得できていないレースをチェックしてログ出力し、
    最新データを index.html に埋め込んで最終 git push する。

    venues: {会場名: 日付文字列}
    deadline_map: {会場名: {rno(int or str): "HH:MM"}}
    """
    log("  [終了チェック] 展示情報・オッズ 取得状況を確認中...")
    any_missing = False

    for venue, date_str in venues.items():
        slug    = VENUE_SLUG.get(venue, venue)
        date_nd = date_str.replace("-", "")
        race_nos = sorted(deadline_map.get(venue, {}).keys(), key=lambda x: int(x))

        if not race_nos:
            continue

        missing_tenji = []
        missing_odds  = []

        for rno in race_nos:
            rno_int = int(rno)   # int/str どちらでも対応

            # 展示チェック: tenji_{slug}_{date_nd}_R{N}.json  (ゼロ埋めなし)
            tenji_path = TENJI_DIR / f"tenji_{slug}_{date_nd}_R{rno_int}.json"
            if not tenji_path.exists():
                missing_tenji.append(rno_int)

            # オッズチェック: odds_{slug}_{date_nd}_R{NN}.json (2桁ゼロ埋め)
            odds_path = ODDS_DIR / f"odds_{slug}_{date_nd}_R{rno_int:02d}.json"
            if not odds_path.exists():
                missing_odds.append(rno_int)

        if missing_tenji:
            log(f"  [終了チェック] ⚠ {venue}: 展示情報なし → R{', R'.join(str(r) for r in missing_tenji)}")
            any_missing = True
        if missing_odds:
            log(f"  [終了チェック] ⚠ {venue}: オッズなし    → R{', R'.join(str(r) for r in missing_odds)}")
            any_missing = True

        if not missing_tenji and not missing_odds:
            log(f"  [終了チェック] ✅ {venue}: 展示・オッズ すべて取得済み ({len(race_nos)}R)")

    if not any_missing:
        log("  [終了チェック] ✅ 全会場・全レース 展示情報・オッズ 取得完了")
    else:
        log("  [終了チェック] ⚠ 上記の未取得レースがありました（手動確認推奨）")

    # ── 最終push: 最新のオッズ・展示・買い目を index.html に埋め込んでpush ──
    log("  [終了チェック] 最終データ埋め込み＋push 開始...")
    try:
        inject_odds_to_html()
        inject_tenji_to_html()
        inject_comment_to_html()
        inject_all_data_to_html()
        inject_master_ext_to_html()
        write_all_json_files()
        pushed = git_push([INDEX_HTML])
        if pushed:
            log("  [終了チェック] ✅ 最終push完了 → アプリに反映されました")
        else:
            log("  [終了チェック] 変更なし・pushスキップ（すでに最新）")
    except Exception as e:
        log(f"  [終了チェック] ✕ 最終push失敗: {e}")

    log("  [終了チェック] 完了 → auto_push.py は監視を継続します（Ctrl+C で終了）")


def _odds_loop_worker() -> None:
    """
    バックグラウンドで fetch_all_races() を繰り返し呼び出す永続ワーカー。

    【サーバー負荷対策】
      - リクエスト間隔は fetch_odds.py 側の優先度ロジックに従う
        （最優先1.5秒 / 通常3.0秒 / 低優先3.0秒）
      - 巡回間の待機は fetch_all_races() が返す next_wait_sec を使用
        （最優先30秒 / 通常90秒 / 低優先180秒）
      - 全レース締め切り or 確定済みになったらループ終了

    【エラー処理】
      - fetch_all_races() 内の例外はここでキャッチしてログ出力後リトライ
      - 連続エラー時は指数バックオフ（最大10分）でリトライ間隔を延ばす
    """
    try:
        from fetch_odds import fetch_all_races
    except ImportError:
        log("  [OddsLoop] ⚠ fetch_odds.py が見つかりません → ワーカー終了")
        return

    log("  [OddsLoop] 🟢 オッズ永続ループ開始")

    consecutive_errors = 0

    while not _odds_worker_stop.is_set():
        # 停止シグナル確認
        if _odds_worker_stop.is_set():
            break

        # 最新の会場リストと締め切りマップを都度取得（CSV追加・変更に対応）
        current_venues = get_venues_in_today_csvs()
        if not current_venues:
            log("  [OddsLoop] 当日CSV未着 → 60秒後に再確認")
            _odds_worker_stop.wait(60)
            continue

        deadline_map = _build_deadline_map(current_venues)

        # deadline_map が空の場合は互換モード（has_active=False）になって
        # ループが即終了してしまうため、リトライ待機する
        if not deadline_map:
            log("  [OddsLoop] ⚠ 締切時刻マップ取得失敗 → 60秒後に再試行")
            _odds_worker_stop.wait(60)
            continue

        try:
            saved, next_wait_sec, has_active = fetch_all_races(
                current_venues, verbose=True, deadline_map=deadline_map
            )
            consecutive_errors = 0   # 成功したらエラーカウントリセット

            # 取得したファイルがあれば【2段階push】
            # ① 軽量: odds_YYYYMMDD.json のみ即時push（data.js書き換えなし → 高速）
            # ② 通常: data.js への埋め込みpush（アプリ再起動時のフォールバック）
            if saved:
                _write_and_push_odds_json(saved)
                inject_odds_to_html()
                with _git_lock:
                    run(["git", "add", str(INDEX_HTML)])
                    if DATA_JS.exists():
                        run(["git", "add", str(DATA_JS)])
                    code, out = _run_nolock(["git", "status", "--porcelain"])
                    tracked = [l for l in out.strip().splitlines() if not l.startswith("??")]
                    if tracked:
                        msg = f"odds update {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                        _push_queue.put(("raw", None, msg))
                        log(f"  [OddsLoop] ✓ オッズpushキューに追加 ({len(saved)}件)")

            if not has_active:
                # deadline_map が正常に取れていた場合のみ真の終了とみなす
                # （空 deadline_map で互換モード終了した場合の誤終了を防ぐ）
                if deadline_map:
                    log("  [OddsLoop] ✅ 全レース締め切り済み・確定待ちなし → ループ終了")
                    _check_missing_tenji_and_odds(current_venues, deadline_map)
                    break
                else:
                    log("  [OddsLoop] ⚠ deadline_map なしで終了 → 60秒後にリトライ")
                    _odds_worker_stop.wait(60)
                    continue

            # 次巡まで待機（停止シグナルを受け取れるように wait を使用）
            if next_wait_sec > 0:
                _odds_worker_stop.wait(next_wait_sec)

        except Exception as e:
            consecutive_errors += 1
            # 指数バックオフ: 1回目60秒 → 2回目120秒 → … → 最大600秒
            backoff = min(60 * (2 ** (consecutive_errors - 1)), 600)
            log(f"  [OddsLoop] ✕ エラー({consecutive_errors}回連続): {e} → {backoff}秒後リトライ")
            _odds_worker_stop.wait(backoff)

    log("  [OddsLoop] 🔴 オッズ永続ループ終了")
    global _odds_worker_done
    _odds_worker_done = True


def _write_and_push_odds_json(saved_paths: list) -> bool:
    """
    オッズ取得直後に呼ぶ軽量push。
    data/odds_YYYYMMDD.json を更新してそのファイルだけgit push する。
    data.js（巨大）は触らないため push が高速に完了する。
    """
    if not saved_paths:
        return False

    DATA_DIR.mkdir(exist_ok=True)
    slug_venue = {v: k for k, v in VENUE_SLUG.items()}

    by_date: dict[str, dict] = {}
    for fpath in sorted(ODDS_DIR.glob("odds_*.json")):
        m = re.match(r"odds_([a-z]+)_(\d{8})_R(\d{2})\.json$", fpath.name)
        if not m:
            continue
        slug, date_nd, rno_str = m.group(1), m.group(2), str(int(m.group(3)))
        venue = slug_venue.get(slug, slug)
        try:
            if fpath.stat().st_size == 0:
                continue
            with open(fpath, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        race_data = {k: v for k, v in data.items() if k != "fetched_at"}
        by_date.setdefault(date_nd, {}).setdefault(venue, {})[rno_str] = race_data

    if not by_date:
        return False

    written_paths = []
    for date_nd, venues_data in by_date.items():
        out_path = DATA_DIR / f"odds_{date_nd}.json"
        with open(out_path, 'w', encoding='utf-8') as _wf:
            _wf.write(json.dumps(venues_data, ensure_ascii=False, separators=(",", ":")))
        written_paths.append(out_path)

    if not written_paths:
        return False

    with _git_lock:
        for p in written_paths:
            _run_nolock(["git", "add", str(p)])
        code, out = _run_nolock(["git", "status", "--porcelain"])
        tracked = [l for l in out.strip().splitlines() if not l.startswith("??")]
        if not tracked:
            return False
        total_races = sum(len(races) for venues in by_date.values() for races in venues.values())
        msg = f"odds json {datetime.now().strftime('%Y-%m-%d %H:%M')} ({total_races}R)"
        _push_queue.put(("raw", None, msg))
    log(f"  [OddsJSON] ✓ 軽量pushキューに追加: {[p.name for p in written_paths]}")
    return True


def _start_odds_loop_if_needed() -> None:
    """
    オッズ永続ループスレッドが未起動 or 死亡していれば再起動する。
    メインループから定期的に呼ばれる（死活監視＋自動再起動）。
    全締め切り後に正常終了した場合（_odds_worker_done=True）は再起動しない。
    ただし日付が変わった場合はフラグをリセットして翌日分を取得できるようにする。
    """
    global _odds_worker_thread, _odds_worker_stop, _odds_worker_done

    # 日付が変わっていたら「正常終了済み」フラグをリセット
    if not hasattr(_start_odds_loop_if_needed, '_done_date'):
        _start_odds_loop_if_needed._done_date = None
    today = today_str()
    if _odds_worker_done and _start_odds_loop_if_needed._done_date != today:
        log("  [OddsLoop] 日付変更を検知 → 正常終了フラグをリセット（翌日分取得を開始）")
        _odds_worker_done = False
        _start_odds_loop_if_needed._done_date = today

    # 正常終了済み（全レース締め切り）なら再起動しない
    if _odds_worker_done:
        return

    venues = get_venues_in_today_csvs()
    if not venues:
        return   # 当日CSVがなければ起動しない

    if _odds_worker_thread is not None and _odds_worker_thread.is_alive():
        return   # 正常稼働中 → 何もしない

    if _odds_worker_thread is not None:
        log("  [OddsLoop] ⚠ スレッド停止を検知 → 再起動します")

    # 停止シグナルをリセットして新スレッドを起動
    _odds_worker_stop.clear()
    _odds_worker_thread = _threading.Thread(
        target=_odds_loop_worker,
        daemon=True,
        name="OddsLoopWorker",
    )
    _odds_worker_thread.start()
    log("  [OddsLoop] 🟢 スレッド起動完了")


def inject_race_entry_to_viewer(csv_paths: list) -> bool:
    """
    出走表CSV到着時に「展開別残存ビューア.html」の会場名・選手名を書き換える。

    HTMLに以下のマーカーが埋め込まれていること:
      let raceVenue = venues[0]; // [AUTO_VENUE]
      // [AUTO_PLAYERS_START]
      const PLAYER_NAMES = {...};
      // [AUTO_PLAYERS_END]

    Returns: 書き換えが発生した場合 True
    """
    if not VIEWER_HTML.exists():
        log(f"  [viewer] {VIEWER_HTML.name} が見つかりません → スキップ")
        return False

    # 対象CSVから会場名・選手名を抽出
    venue = None
    players: dict[int, str] = {}

    for csv_path in csv_paths:
        try:
            try:
                df = pd.read_csv(csv_path, encoding="utf-8")
            except UnicodeDecodeError:
                df = pd.read_csv(csv_path, encoding="shift_jis")
        except Exception:
            continue

        if "会場" not in df.columns:
            continue

        _venue = str(df.iloc[0]["会場"]).strip()

        # 選手名列を検出（「選手名」列が必須）
        if "選手名" not in df.columns or "艇番" not in df.columns:
            log(f"  [viewer] {Path(csv_path).name}: 選手名/艇番列なし → スキップ")
            continue

        _players: dict[int, str] = {}
        for _, row in df.iterrows():
            try:
                waku = int(row["艇番"])
                raw  = str(row["選手名"]).strip()
                # 末尾の登録番号（数字）を除去して名前だけ残す
                name = re.sub(r'\d+$', '', raw).strip()
                if 1 <= waku <= 6 and name and name != "nan":
                    _players[waku] = name
            except (ValueError, TypeError):
                continue

        if _venue and _players:
            venue   = _venue
            players = _players
            break  # 最初の有効CSVで確定

    if not venue or not players:
        log("  [viewer] 有効な会場・選手情報が取得できませんでした → スキップ")
        return False

    html = VIEWER_HTML.read_text(encoding="utf-8")
    original = html

    # ── 1. 会場名を書き換え ──────────────────────────────────────────
    venue_js = venue.replace("'", "\\'")
    html = re.sub(
        r"let raceVenue = .*?; // \[AUTO_VENUE\]",
        f"let raceVenue = '{venue_js}'; // [AUTO_VENUE]",
        html,
    )

    # ── 2. 選手名マップを書き換え ─────────────────────────────────────
    names_entries = ", ".join(
        f"{waku}:'{players.get(waku, '')}'" for waku in range(1, 7)
    )
    new_block = (
        "// [AUTO_PLAYERS_START]\n"
        f"const PLAYER_NAMES = {{{names_entries}}};\n"
        "// [AUTO_PLAYERS_END]"
    )
    html = re.sub(
        r"// \[AUTO_PLAYERS_START\].*?// \[AUTO_PLAYERS_END\]",
        new_block,
        html,
        flags=re.DOTALL,
    )

    if html == original:
        log("  [viewer] HTML に変更なし → 書き込みスキップ")
        return False

    VIEWER_HTML.write_text(html, encoding="utf-8")
    log(f"  [viewer] ✓ {VIEWER_HTML.name} 更新: 会場={venue}, 選手={players}")
    return True


def fetch_motor_for_csv(csv_paths: list):
    """
    出走表CSV到着時にモーター情報だけを取得する。
    backfill_motor()の後継。起動時バックフィルは行わない。

    csv_paths: 変更を検知した当日CSVのPathリスト
    """
    if not FETCH_TENJI_PY.exists():
        log(f"  ⚠ {FETCH_TENJI_PY.name} が見つかりません → モーター取得スキップ")
        return

    today = today_str()
    TENJI_DIR.mkdir(exist_ok=True)

    # 対象CSVから会場・日付を収集
    venues_in_csv: dict[str, str] = {}
    for csv_path in csv_paths:
        if today not in Path(csv_path).name:
            continue
        try:
            try:
                df = pd.read_csv(csv_path, encoding="utf-8")
            except UnicodeDecodeError:
                df = pd.read_csv(csv_path, encoding="shift_jis")
            if "会場" in df.columns:
                venue_name = str(df.iloc[0]["会場"]).strip()
                date_raw   = str(df.iloc[0].get("日付", today)).strip().replace("/", "-")
                if venue_name and venue_name in VENUE_SLUG:
                    venues_in_csv[venue_name] = date_raw
        except Exception:
            continue

    if not venues_in_csv:
        log("  モーター取得: 対象会場なし → スキップ")
        return

    log(f"  モーター取得開始: {list(venues_in_csv.keys())}")

    def fetch_one_motor(args):
        slug, date, race = args
        result = subprocess.run(
            [sys.executable, str(FETCH_TENJI_PY),
             "--venue", slug,
             "--date",  date,
             "--race",  str(race),
             "--out",   str(TENJI_DIR),
             "--motor-only"],
            capture_output=True, timeout=120
        )
        return slug, race, result.returncode

    tasks = []
    for venue_name, date in venues_in_csv.items():
        slug = VENUE_SLUG[venue_name]
        date_nodash = date.replace("-", "")
        # 既取得レースはスキップ（モーター情報が既にあるもの）
        existing_races = set()
        for f in TENJI_DIR.glob(f"tenji_{slug}_{date_nodash}_R*.json"):
            m = re.search(r"_R(\d{2})\.json$", f.name)
            if m:
                import json as _json
                try:
                    with open(f, encoding="utf-8") as fp:
                        rows = _json.load(fp)
                    if rows and rows[0].get("motor_no") is not None:
                        existing_races.add(int(m.group(1)))
                except Exception:
                    pass
        missing = [r for r in range(1, 13) if r not in existing_races]
        if not missing:
            log(f"  {venue_name}: モーター情報取得済み → スキップ")
            continue
        log(f"  {venue_name}（{slug}）: {len(missing)}R分取得予定 {missing}")
        for race in missing:
            tasks.append((slug, date, race))

    if not tasks:
        log("  モーター取得: 全会場取得済み → スキップ")
        return

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(fetch_one_motor, t): t for t in tasks}
        for f in as_completed(futures):
            try:
                slug, race, code = f.result()
                log(f"    {slug} {race}R {'✓' if code == 0 else '✕'}")
            except Exception as e:
                log(f"    エラー: {e}")

    log("  モーター取得完了")


def fetch_tenji_for_csv(csv_paths: list):
    """
    出走表CSV到着時に展示情報（テンジ）をバックグラウンドで取得する。
    fetch_motor_for_csv と同構造だが --motor-only フラグを使わない。

    csv_paths: 変更を検知した当日CSVのPathリスト
    """
    if not FETCH_TENJI_PY.exists():
        log(f"  ⚠ {FETCH_TENJI_PY.name} が見つかりません → 展示取得スキップ")
        return

    today = today_str()
    TENJI_DIR.mkdir(exist_ok=True)

    # 対象CSVから会場・日付を収集
    venues_in_csv: dict[str, str] = {}
    for csv_path in csv_paths:
        if today not in Path(csv_path).name:
            continue
        try:
            try:
                df = pd.read_csv(csv_path, encoding="utf-8")
            except UnicodeDecodeError:
                df = pd.read_csv(csv_path, encoding="shift_jis")
            if "会場" in df.columns:
                venue_name = str(df.iloc[0]["会場"]).strip()
                date_raw   = str(df.iloc[0].get("日付", today)).strip().replace("/", "-")
                if venue_name and venue_name in VENUE_SLUG:
                    venues_in_csv[venue_name] = date_raw
        except Exception:
            continue

    if not venues_in_csv:
        log("  展示取得: 対象会場なし → スキップ")
        return

    log(f"  展示取得開始（バックグラウンド）: {list(venues_in_csv.keys())}")

    def fetch_one_tenji(args):
        slug, date, race = args
        result = subprocess.run(
            [sys.executable, str(FETCH_TENJI_PY),
             "--venue", slug,
             "--date",  date,
             "--race",  str(race),
             "--out",   str(TENJI_DIR)],
            capture_output=True, timeout=120
        )
        return slug, race, result.returncode

    def _bg_fetch():
        tasks = []
        for venue_name, date in venues_in_csv.items():
            slug = VENUE_SLUG[venue_name]
            date_nodash = date.replace("-", "")
            # 既取得レースはスキップ
            existing_races = set()
            for f in TENJI_DIR.glob(f"tenji_{slug}_{date_nodash}_R*.json"):
                m = re.search(r"_R(\d{2})\.json$", f.name)
                if m:
                    existing_races.add(int(m.group(1)))
            missing = [r for r in range(1, 13) if r not in existing_races]
            if not missing:
                log(f"  {venue_name}: 展示情報取得済み → スキップ")
                continue
            log(f"  {venue_name}（{slug}）: 展示 {len(missing)}R分取得予定 {missing}")
            for race in missing:
                tasks.append((slug, date, race))

        if not tasks:
            log("  展示取得: 全会場取得済み → スキップ")
            return

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(fetch_one_tenji, t): t for t in tasks}
            for f in as_completed(futures):
                try:
                    slug, race, code = f.result()
                    log(f"    [展示] {slug} {race}R {'✓' if code == 0 else '✕'}")
                except Exception as e:
                    log(f"    [展示] エラー: {e}")

        log("  展示取得完了")

    import threading as _threading
    _threading.Thread(target=_bg_fetch, daemon=True).start()


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def _wait_for_index_lock(timeout: int = 10) -> bool:
    """
    .git/index.lock が別プロセスに掴まれている間は最大 timeout 秒待機する。
    Windowsでは削除できないので「なくなるまで待つ」戦略を採用。
    timeout 秒経過しても消えなければ False を返す（強制削除は行わない）。
    """
    lock_file = SCRIPTS_DIR / ".git" / "index.lock"
    waited = 0
    while lock_file.exists() and waited < timeout:
        time.sleep(0.5)
        waited += 0.5
    return not lock_file.exists()

def _clear_git_lock():
    """強制終了後に残る .git/index.lock を自動削除する"""
    lock_file = SCRIPTS_DIR / ".git" / "index.lock"
    if not lock_file.exists():
        return
    # まず別プロセスが手放すのを最大5秒待つ（WinError 32 回避）
    if _wait_for_index_lock(timeout=5):
        return  # 自然に消えた
    # それでも残っていれば削除を試みる（本当の残骸の場合）
    try:
        lock_file.unlink()
        log("  [git] index.lock を削除しました（異常終了の残骸）")
    except Exception as e:
        log(f"  [git] index.lock 削除失敗（別プロセス使用中）: {e}")

def run(cmd):
    # git操作は _git_lock で直列化し、index.lock 競合 (WinError 32) を防ぐ
    if cmd[0] == "git":
        with _git_lock:
            if cmd[1] in ("commit", "add"):
                _clear_git_lock()
            r = subprocess.run(cmd, cwd=str(SCRIPTS_DIR),
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
            return r.returncode, (r.stdout + r.stderr).strip()
    r = subprocess.run(cmd, cwd=str(SCRIPTS_DIR),
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout + r.stderr).strip()

def get_mtimes(pattern):
    return {p: Path(p).stat().st_mtime for p in glob.glob(pattern)}

def today_str():
    """
    競艇営業日ベースの「今日」を返す。
    午前0時〜3時59分は「翌日（レース日）」の出走表がすでに到着している
    ため、その日付を返す。午前4時以降は通常の当日日付。
    例: 01:30 → 翌日付 / 09:00 → 当日付
    """
    now = datetime.now()
    if now.hour < 4:
        from datetime import timedelta
        return (now + timedelta(days=1)).strftime("%Y-%m-%d")
    return now.strftime("%Y-%m-%d")

def _race_date_candidates() -> list:
    """
    CSVを検索する日付候補リストを返す（最大2日分）。
    深夜帯（0〜3時）は「翌日付」＋「当日付」の両方を返すことで
    日付切り替わり直後に古いCSVを誤って除外しないようにする。
    通常時は当日付のみ。
    """
    now = datetime.now()
    from datetime import timedelta
    if now.hour < 4:
        next_day = (now + timedelta(days=1)).strftime("%Y-%m-%d")
        today    = now.strftime("%Y-%m-%d")
        return [next_day, today]   # 翌日付を優先
    return [now.strftime("%Y-%m-%d")]

def get_today_csvs():
    """
    競艇日付ベースで「今日のCSV」を返す。
    深夜1時に翌日付CSVが到着しても正しく検知できる。
    """
    candidates = _race_date_candidates()
    all_csvs = glob.glob(str(CSV_DIR / "*.csv"))
    result = []
    for date in candidates:
        matched = [p for p in all_csvs if date in Path(p).name]
        if matched:
            return matched   # 最初にマッチした日付のCSVを使用
    return result


def get_venues_in_today_csvs() -> dict:
    """
    当日CSVから {会場名: 日付} を抽出して返す
    例: {"常滑":"2026-05-09", "津":"2026-05-09"}
    """
    venues_in_csv = {}

    for csv_path in get_today_csvs():
        try:
            try:
                df = pd.read_csv(csv_path, encoding="utf-8")
            except UnicodeDecodeError:
                df = pd.read_csv(csv_path, encoding="shift_jis")

            if "会場" in df.columns:
                vname = str(df.iloc[0]["会場"]).strip()
                date_raw = str(df.iloc[0].get("日付", today_str())).strip().replace("/", "-")

                if vname in VENUE_SLUG:
                    venues_in_csv[vname] = date_raw

        except Exception:
            continue

    return venues_in_csv


def make_csv_index():
    """csv_output/index.json を生成（当日CSVのみ）"""
    files = sorted([Path(p).name for p in get_today_csvs()])
    idx_path = CSV_DIR / "index.json"
    with open(idx_path, 'w', encoding='utf-8') as _wf:
        _wf.write(json.dumps({"files": files, "updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
                   ensure_ascii=False))
    log(f"  index.json: {len(files)}件（当日分のみ）")
    return idx_path

def update_cache_version():
    """
    index.html のキャッシュバスター文字列を現在時刻で更新する。

    index.html 内の全 .js?v=XXXXXXXXXXXXXX (14桁) を新しいタイムスタンプに置換する。
    これにより data.js / sample_obf.js 等すべてのスクリプトがブラウザに再取得される。

    [fix] 旧実装の問題:
      - /* __CACHE_VER__ */ プレースホルダーは初回置換後に消えるため2回目以降は何もしない
      - 結果、再起動のたびにキャッシュが更新されずブラウザが古い data.js を使い続けていた

    [fix] 新実装:
      - index.html 内の全 .js?v=14桁 を置換（繰り返し確実に動作する）
      - /* __CACHE_VER__ */ プレースホルダーも初回互換で残す
    """
    import re as _re
    ver = datetime.now().strftime("%Y%m%d%H%M%S")
    try:
        text = INDEX_HTML.read_text(encoding="utf-8")
        # パターン1: 2回目以降 .js?v=XXXXXXXXXXXXXX (14桁) → 全スクリプト対象
        text2 = _re.sub(r"([.]js[?]v=)\d{14}", lambda m: m.group(1) + ver, text)
        # パターン2: 初回 /* __CACHE_VER__ */ プレースホルダー（後方互換）
        text2 = _re.sub(r"/[*] __CACHE_VER__ [*]/", ver, text2)
        if text2 != text:
            with open(INDEX_HTML, "w", encoding="utf-8") as _wf:
                _wf.write(text2)
            log(f"  ✓ キャッシュバスター更新: v={ver}")
        else:
            log(f"  [WARN] キャッシュバスター: index.html に置換対象なし (v={ver})")
    except Exception as e:
        log(f"  [WARN] cache version update failed: {e}")

def obfuscate_js(src_path, out_path):
    """
    sample.js をコメント除去 → obfuscate して out_path に書き出す。
    失敗時はオリジナルをそのまま使う（動作を絶対に止めない）。
    前提: npm install -g javascript-obfuscator
    """
    import shutil as _shutil, tempfile as _tempfile
    from pathlib import Path as _Path

    obf_cmd = _shutil.which("javascript-obfuscator")
    if not obf_cmd:
        log("[obfuscate] javascript-obfuscator が見つかりません → オリジナルを使用")
        _shutil.copy2(src_path, out_path)
        return out_path

    stripped_path = SCRIPTS_DIR / "_sample_stripped_tmp.js"

    strip_script = r"""
const src = require('fs').readFileSync(process.argv[2], 'utf8');
let result = '', i = 0, inStr = false, strChar = '', inTemplate = 0;
while (i < src.length) {
    const c = src[i];
    if (!inStr && c === '`') { inTemplate += (inTemplate > 0 ? -1 : 1); result += c; i++; continue; }
    if (inTemplate > 0) { result += c; i++; continue; }
    if (!inStr && (c === '"' || c === "'")) { inStr = true; strChar = c; result += c; i++; continue; }
    if (inStr && c === strChar && src[i - 1] !== '\\') { inStr = false; result += c; i++; continue; }
    if (inStr) { result += c; i++; continue; }
    if (c === '/' && src[i + 1] === '*') { while (i < src.length && !(src[i] === '*' && src[i + 1] === '/')) i++; i += 2; continue; }
    if (c === '/' && src[i + 1] === '/') { while (i < src.length && src[i] !== '\n') i++; continue; }
    result += c; i++;
}
require('fs').writeFileSync(process.argv[3], result);
"""
    with _tempfile.NamedTemporaryFile(suffix=".js", delete=False, mode="w", encoding="utf-8") as tf:
        strip_script_path = tf.name
        tf.write(strip_script)

    try:
        r = subprocess.run(
            ["node", strip_script_path, str(src_path), str(stripped_path)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30
        )
        if r.returncode != 0:
            raise RuntimeError(f"strip failed: {r.stderr}")
        log("[obfuscate] コメント除去完了")
    except Exception as e:
        log(f"[obfuscate] コメント除去失敗: {e} → オリジナルを使用")
        _shutil.copy2(src_path, out_path)
        return out_path
    finally:
        try:
            import os as _os; _os.unlink(strip_script_path)
        except Exception:
            pass

    try:
        r = subprocess.run(
            [
                obf_cmd, str(stripped_path),
                "--output", str(out_path),
                "--compact", "true",
                "--string-array", "true",
                "--string-array-encoding", "rc4",
                "--string-array-threshold", "1.0",
                "--dead-code-injection", "false",
                "--self-defending", "false",
            ],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120
        )
        if r.returncode != 0 or not _Path(out_path).exists():
            raise RuntimeError(f"obfuscate failed: {r.stderr}")
        log(f"[obfuscate] 難読化完了: {_Path(out_path).stat().st_size // 1024} KB")
    except Exception as e:
        log(f"[obfuscate] 難読化失敗: {e} → オリジナルを使用")
        _shutil.copy2(src_path, out_path)
    finally:
        try:
            stripped_path.unlink()
        except Exception:
            pass

    return out_path


def _summarize_push_targets(changed_files):
    """
    changed_files のファイル名から会場・レース番号を抽出して人間が読みやすい文字列を返す。

    ファイル名の想定パターン:
      tenji_data/tenji_{venue}_{YYYYMMDD}_R{rno}.json  → 会場+レース番号
      csv_output/{venue}_{YYYYMMDD}.csv                → 会場のみ
      data/index.json, data.js, index.html など        → その他

    戻り値例:
      "びわこR3, 丸亀R5, 唐津R7"
      "唐津 (CSV), index.html, data.js"
    """
    import re as _re
    venue_races = {}   # venue → set of race_no strings
    other_labels = []

    for f in changed_files:
        name = Path(str(f)).name
        # tenji_{venue}_{YYYYMMDD}_R{rno}.json
        m = _re.search(r"tenji_(.+?)_\d{8}_R(\d+)\.json$", name)
        if m:
            venue_races.setdefault(m.group(1), set()).add(m.group(2))
            continue
        # {venue}_{YYYYMMDD}.csv  (csv_output)
        m = _re.search(r"^(.+?)_\d{8}\.csv$", name)
        if m:
            venue_races.setdefault(m.group(1), set())   # レース番号なし
            continue
        # 結果: result_{venue}_{YYYYMMDD}_R{rno}.json
        m = _re.search(r"result_(.+?)_\d{8}_R(\d+)\.json$", name)
        if m:
            venue_races.setdefault(m.group(1), set()).add(m.group(2))
            continue
        # その他（index.html, data.js など）
        other_labels.append(name)

    parts = []
    for venue, races in sorted(venue_races.items()):
        if races:
            sorted_races = sorted(races, key=lambda x: int(x))
            parts.append(f"{venue} R{','.join(sorted_races)}")
        else:
            parts.append(f"{venue} (CSV)")
    parts.extend(other_labels)
    return ", ".join(parts) if parts else "（不明）"


def git_push(changed_files):
    # git add（難読化含む）はここで実施し、commit+push はキューに委譲する。
    # → 複数系統のpushが短時間に重なってGitHub PagesがCancelledになるのを防ぐ。
    with _git_lock:
        _git_add_locked(changed_files)
        push_summary = _summarize_push_targets(changed_files)
        msg = f"update {datetime.now().strftime('%Y-%m-%d %H:%M')} [{push_summary}]"
        code, out = _run_nolock(["git", "status", "--porcelain"])
        tracked = [l for l in out.strip().splitlines() if not l.startswith("??")]
        if not tracked:
            return False
        _push_queue.put(("raw", None, msg))
        log(f"  pushキューに追加 [{push_summary}]")
        return True

def _run_nolock(cmd):
    """_git_lock 取得済みの内部から呼ぶ git サブコマンド実行（ロックなし版）"""
    if cmd[0] == "git" and cmd[1] in ("commit", "add"):
        _clear_git_lock()
    r = subprocess.run(cmd, cwd=str(SCRIPTS_DIR),
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout + r.stderr).strip()

def _git_add_locked(changed_files):
    """_git_lock 保持中に呼ばれる。git add（難読化含む）だけ実施。commit/pushはしない。"""
    # 変更ファイルをadd
    for f in changed_files:
        _run_nolock(["git", "add", str(f)])

    # 常に含めるファイル（index.html / sample.css / data.js / player_id_map.json）
    _run_nolock(["git", "add", str(INDEX_HTML)])
    if CSS_FILE.exists():
        _run_nolock(["git", "add", str(CSS_FILE)])

    # params.js の難読化: params.js 自体が変更された時だけ実行
    if PARAMS_JS.exists():
        params_changed = any(Path(str(f)).resolve() == PARAMS_JS.resolve() for f in changed_files)
        if params_changed or not PARAMS_JS_OBF.exists():
            obf_path_params = obfuscate_js(PARAMS_JS, PARAMS_JS_OBF)
            update_cache_version()
            _run_nolock(["git", "add", str(obf_path_params)])
        else:
            _run_nolock(["git", "add", str(PARAMS_JS_OBF)])

    # csv_export.js の難読化
    if CSV_EXPORT_JS.exists():
        csv_changed = any(Path(str(f)).resolve() == CSV_EXPORT_JS.resolve() for f in changed_files)
        if csv_changed or not CSV_EXPORT_JS_OBF.exists():
            obf_csv = obfuscate_js(CSV_EXPORT_JS, CSV_EXPORT_JS_OBF)
            update_cache_version()
            _run_nolock(["git", "add", str(obf_csv)])
        else:
            _run_nolock(["git", "add", str(CSV_EXPORT_JS_OBF)])

    # sim.js の難読化
    if SIM_JS.exists():
        sim_changed = any(Path(str(f)).resolve() == SIM_JS.resolve() for f in changed_files)
        if sim_changed or not SIM_JS_OBF.exists():
            obf_sim = obfuscate_js(SIM_JS, SIM_JS_OBF)
            update_cache_version()
            _run_nolock(["git", "add", str(obf_sim)])
        else:
            _run_nolock(["git", "add", str(SIM_JS_OBF)])

    # backtest.js の難読化
    if BACKTEST_JS.exists():
        bt_changed = any(Path(str(f)).resolve() == BACKTEST_JS.resolve() for f in changed_files)
        if bt_changed or not BACKTEST_JS_OBF.exists():
            obf_bt = obfuscate_js(BACKTEST_JS, BACKTEST_JS_OBF)
            update_cache_version()
            _run_nolock(["git", "add", str(obf_bt)])
        else:
            _run_nolock(["git", "add", str(BACKTEST_JS_OBF)])

    # top_stats.js の難読化
    if TOP_STATS_JS.exists():
        ts_changed = any(Path(str(f)).resolve() == TOP_STATS_JS.resolve() for f in changed_files)
        if ts_changed or not TOP_STATS_JS_OBF.exists():
            obf_ts = obfuscate_js(TOP_STATS_JS, TOP_STATS_JS_OBF)
            update_cache_version()
            _run_nolock(["git", "add", str(obf_ts)])
        else:
            _run_nolock(["git", "add", str(TOP_STATS_JS_OBF)])

    # top_page.js の難読化
    if TOP_PAGE_JS.exists():
        tp_changed = any(Path(str(f)).resolve() == TOP_PAGE_JS.resolve() for f in changed_files)
        if tp_changed or not TOP_PAGE_JS_OBF.exists():
            obf_tp = obfuscate_js(TOP_PAGE_JS, TOP_PAGE_JS_OBF)
            update_cache_version()
            _run_nolock(["git", "add", str(obf_tp)])
        else:
            _run_nolock(["git", "add", str(TOP_PAGE_JS_OBF)])

    # calibration.js / dynamic_inn2place.js / computeScenCombosWithEV.js（難読化なし・そのままpush）
    if CALIBRATION_JS.exists():
        _run_nolock(["git", "add", str(CALIBRATION_JS)])
    if DYNAMIC_INN2PLACE_JS.exists():
        _run_nolock(["git", "add", str(DYNAMIC_INN2PLACE_JS)])
    if COMPUTE_SCEN_JS.exists():
        _run_nolock(["git", "add", str(COMPUTE_SCEN_JS)])

    # sample.js の難読化: sample.js 自体が変更された時だけ実行（毎回は重すぎる）
    if JS_FILE.exists():
        js_changed = any(Path(str(f)).resolve() == JS_FILE.resolve() for f in changed_files)
        if js_changed or not JS_FILE_OBF.exists():
            obf_path = obfuscate_js(JS_FILE, JS_FILE_OBF)
            update_cache_version()
            _run_nolock(["git", "add", str(obf_path)])
        else:
            _run_nolock(["git", "add", str(JS_FILE_OBF)])

    if DATA_JS.exists():
        _run_nolock(["git", "add", str(DATA_JS)])
    if PLAYER_ID_MAP.exists():
        _run_nolock(["git", "add", str(PLAYER_ID_MAP)])

    # フェーズ1: data/*.json を追加（存在すれば）
    if DATA_DIR.exists():
        for jf in DATA_DIR.glob("*.json"):
            _run_nolock(["git", "add", str(jf)])

    # addのみ。commit/pushは呼び出し元がキュー経由で実施する。

def get_past_venues_from_csvs(days_back: int = HISTORY_DAYS) -> dict:
    """
    csv_output/ 内の過去 days_back 日分のCSVを走査し、
    {会場名: 日付YYYY-MM-DD} の辞書を返す（当日は除く）。
    バックテスト用結果取得の入力として使う。
    """
    from datetime import timedelta
    today = datetime.now().date()
    target_dates = set(
        (today - timedelta(days=d)).strftime("%Y-%m-%d")
        for d in range(1, days_back + 1)
    )
    venues: dict = {}
    for csv_path in glob.glob(str(CSV_DIR / "*.csv")):
        fname = Path(csv_path).name
        # ファイル名に含まれる日付を検出
        matched_date = next((d for d in target_dates if d in fname), None)
        if not matched_date:
            continue
        try:
            try:
                df = pd.read_csv(csv_path, encoding="utf-8")
            except UnicodeDecodeError:
                df = pd.read_csv(csv_path, encoding="shift_jis")
            if "会場" in df.columns:
                vname = str(df.iloc[0]["会場"]).strip()
                if vname in VENUE_SLUG:
                    venues[vname] = matched_date
        except Exception:
            continue
    return venues


def backfill_past_results():
    """
    起動時に過去 HISTORY_DAYS 日分の result_data/*.json が揃っているか確認し、
    欠けているレースをバックグラウンドで取得する。
    fetch_result_for_venues() を日付単位で繰り返し呼ぶだけ。
    取得完了後にまとめて inject_result_to_html() → push する。
    """
    if not FETCH_RESULT_PY.exists():
        log(f"  ⚠ {FETCH_RESULT_PY.name} が見つかりません → バックフィルスキップ")
        return

    from datetime import timedelta
    today = datetime.now().date()

    # 日付ごとに会場リストを作成
    date_venues: dict[str, dict] = {}  # {"YYYY-MM-DD": {"会場名": "YYYY-MM-DD"}}
    for csv_path in glob.glob(str(CSV_DIR / "*.csv")):
        fname = Path(csv_path).name
        for d in range(1, HISTORY_DAYS + 1):
            target = (today - timedelta(days=d)).strftime("%Y-%m-%d")
            if target not in fname:
                continue
            try:
                try:
                    df = pd.read_csv(csv_path, encoding="utf-8")
                except UnicodeDecodeError:
                    df = pd.read_csv(csv_path, encoding="shift_jis")
                if "会場" in df.columns:
                    vname = str(df.iloc[0]["会場"]).strip()
                    if vname in VENUE_SLUG:
                        date_venues.setdefault(target, {})[vname] = target
            except Exception:
                continue

    if not date_venues:
        log("  バックフィル: 過去CSVなし → スキップ")
        return

    total_missing = 0
    tasks = []
    for date_str, venues in sorted(date_venues.items(), reverse=True):
        date_nd = date_str.replace("-", "")
        for venue_name, _ in venues.items():
            slug = VENUE_SLUG.get(venue_name)
            if not slug:
                continue
            for race in range(1, 13):
                fname = RESULT_DIR / f"result_{slug}_{date_nd}_R{race:02d}.json"
                if fname.exists():
                    try:
                        with open(fname, encoding="utf-8") as f:
                            existing = json.load(f)
                        if existing.get("sanrentan") or existing.get("cancelled"):
                            continue  # 取得済み or 中止登録済み
                    except Exception:
                        pass
                tasks.append((slug, date_nd, race))
                total_missing += 1

    if not tasks:
        log("  バックフィル: 全レース取得済み → スキップ")
        return

    log(f"  バックフィル開始: 過去{HISTORY_DAYS}日分 / 未取得 {total_missing}レース")

    def _do_backfill():
        fetched = 0
        # バッチサイズ制限: 起動時に一度に大量プロセスを生成しない
        # 1日あたり最大12レース×複数会場 → max_workers=2 で順次処理
        BACKFILL_BATCH = 48  # 1回のバックフィルで処理する最大レース数
        batch = tasks[:BACKFILL_BATCH]
        if len(tasks) > BACKFILL_BATCH:
            log(f"  バックフィル: 今回は {BACKFILL_BATCH}レースのみ処理（残り{len(tasks)-BACKFILL_BATCH}レースは次回起動時）")

        def fetch_one(args):
            slug, date_nd, race = args
            result = subprocess.run(
                [sys.executable, str(FETCH_RESULT_PY),
                 "--venue", slug, "--date", date_nd, "--race", str(race),
                 "--out", str(RESULT_DIR)],
                capture_output=True, timeout=60
            )
            return slug, date_nd, race, result.returncode

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {executor.submit(fetch_one, t): t for t in batch}
            for fut in as_completed(futures):
                try:
                    slug, date_nd, race, code = fut.result()
                    if code == 0:
                        fetched += 1
                        log(f"    [BF] {slug} {date_nd} {race}R ✓")
                    else:
                        log(f"    [BF] {slug} {date_nd} {race}R ✕（未確定または非公開）")
                except Exception as e:
                    log(f"    [BF] エラー: {e}")

        if fetched > 0:
            log(f"  バックフィル完了: {fetched}レース取得 → inject＋push")
            # フェーズ3: HTMLへの埋め込みを停止
            # inject_result_to_html()
            write_result_json()    # data/result_YYYYMMDD.json を更新
            write_data_index()     # インデックスも更新
            with _git_lock:
                _run_nolock(["git", "add", str(INDEX_HTML)])
                code, out = _run_nolock(["git", "status", "--porcelain"])
                tracked = [l for l in out.strip().splitlines() if not l.startswith("??")]
                if tracked:
                    msg = f"backfill result {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                    _push_queue.put(("raw", None, msg))
                    log("  ✓ バックフィル pushキューに追加")
                else:
                    log("  バックフィル: 変更なし（既に最新）")
        else:
            log("  バックフィル: 新規取得なし（全レース未確定または非公開）")

    import threading as _threading
    _threading.Thread(target=_do_backfill, daemon=True).start()


def main():
    log("=" * 50)
    log("  自動push監視 起動")
    log(f"  CSV監視  : {CSV_DIR}")
    log(f"  展示情報監視: {TENJI_DIR}")
    log(f"  間隔     : {CHECK_INTERVAL}秒")
    log("=" * 50)

    # 起動時に data.js の宣言欠損を自動補完（強制終了後の復旧）
    _data_js_ensure_placeholders()

    # [2026-05-20 追加] 起動時に Python/JS 間の設定整合をチェック
    _check_tenji_config_sync()

    TENJI_DIR.mkdir(exist_ok=True)
    CSV_DIR.mkdir(exist_ok=True)
    COMMENT_DIR.mkdir(exist_ok=True)
    RESULT_DIR.mkdir(exist_ok=True)

    # 深夜帯は翌日付CSVも監視（_race_date_candidates()に従う）
    prev_csv = {}
    for _pat in [str(CSV_DIR / f"*{d}*.csv") for d in _race_date_candidates()]:
        prev_csv.update(get_mtimes(_pat))
    prev_tenji = get_mtimes(str(TENJI_DIR / "*.json"))
    prev_comment = get_mtimes(str(COMMENT_DIR / "*.json")) if COMMENT_DIR.exists() else {}
    prev_result  = get_mtimes(str(RESULT_DIR / "*.json")) if RESULT_DIR.exists() else {}
    prev_xlsx_mtime = XLSX_PATH.stat().st_mtime if XLSX_PATH.exists() else None

    # 起動時: 当日CSVがあればindex.jsonを生成してpush
    today_csvs = get_today_csvs()
    if today_csvs:
        idx = make_csv_index()
        log(f"  起動時push: {len(today_csvs)}件（当日分）+ index.json")

        # ① 急ぎのデータを先にpush（展示・コメント・オッズ）
        inject_tenji_to_html()       # 起動時にも展示情報を埋め込む
        inject_comment_to_html()     # 起動時にコメントも埋め込む
        inject_flying_to_html()      # 起動時にフライングも埋め込む
        inject_odds_to_html()        # 前回取得済みオッズを起動時に反映
        # [fix] 起動時の最初のpushにもALL_DATAを含める。
        # 以前は inject_all_data_to_html() がBGスレッドのみで実行されていたため、
        # 7:25再起動など「CSVが既に存在する」ケースでindex.htmlの内容がGitHubと
        # 同じになり、BGスレッドのpushが「変更なし」でスキップされていた。
        inject_all_data_to_html()
        inject_master_ext_to_html()  # venue_kimari / tenkai_remaining を埋め込む
        # [fix] 起動時に ALL_DATA_HISTORY を再注入。
        # これにより data.js に過去日データが入り、index.html の v= も更新される。
        # ブラウザリロードだけで日付切り替えが反映される。
        inject_history_to_html()
        git_push([Path(p) for p in today_csvs] + [idx, INDEX_HTML, DATA_JS])
        log("  ✓ 展示・コメント・オッズ・ALL_DATA・ALL_DATA_HISTORY push完了（公式情報取得はバックグラウンドで実行中）")

        # ② 重い処理（公式レースインデックス取得・JSON書き出し）はバックグラウンドで実行 → 完了後に追加push
        import threading as _threading
        def _reprocess_bg():
            log("  [BG] 公式情報・JSONファイル更新 開始...")
            # [fix] inject_all_data_to_html / inject_master_ext_to_html は
            # 起動時の①で既に実行済み。BGでは公式インデックス取得とJSON書き出しのみ実行する。
            # これにより「BGが完了してもdata.jsに差分が生まれず git status が変更なし」
            # と判定されてpushがスキップされる問題を回避する。
            fetch_and_inject_race_index()    # 公式サイトから開催グレード情報を埋め込む
            write_all_json_files()           # フェーズ1: data/*.json を追加書き出し（HTML変更なし）
            # [fix] INDEX_HTML だけでなく DATA_JS も明示的に渡す。
            # git_push 内部で git add + git status --porcelain を行うため
            # data.js に差分があれば確実にcommit・pushされる。
            pushed = git_push([INDEX_HTML, DATA_JS])
            if pushed:
                log("  [BG] 公式情報・JSONファイル更新 完了 → push済み")
            else:
                log("  [BG] 公式情報・JSONファイル更新 完了（変更なし・pushスキップ）")
        _threading.Thread(target=_reprocess_bg, daemon=True).start()

        # オッズ永続ループをバックグラウンドで起動（起動時pushを遅らせない）
        _start_odds_loop_if_needed()
    else:
        log("  当日CSVなし → 深夜帯CSV到着監視モードで待機")
        # ── 深夜帯CSV待機スレッド ─────────────────────────────────
        # 午前1時頃に翌日付CSVが到着した瞬間を検知してpushする専用スレッド。
        # メインループが _race_date_candidates() を更新し始めるまでの橋渡し。
        import threading as _threading
        def _await_midnight_csv():
            log("  [深夜監視] 翌日付CSV到着を待機中（30秒ごとチェック）...")
            while True:
                time.sleep(30)
                arrived = get_today_csvs()
                if arrived:
                    log(f"  [深夜監視] 翌日付CSV {len(arrived)}件 到着 → 起動処理を実行")
                    idx = make_csv_index()
                    inject_tenji_to_html()
                    inject_comment_to_html()
                    inject_flying_to_html()
                    inject_odds_to_html()
                    # [fix] 深夜帯も同様に最初のpushにALL_DATAを含める
                    inject_all_data_to_html()
                    inject_master_ext_to_html()
                    git_push([Path(p) for p in arrived] + [idx, INDEX_HTML])  # [fix] INDEX_HTMLを明示的に含める
                    log("  [深夜監視] ✓ 翌日付CSV・ALL_DATA push完了（公式情報取得はバックグラウンドで実行）")
                    # [fix] BGでは公式インデックス取得とJSON書き出しのみ実行
                    def _bg():
                        fetch_and_inject_race_index()
                        write_all_json_files()
                        # [fix] 翌日CSV到着=日付切替。ALL_DATA_HISTORY 再注入で v= も更新。
                        inject_history_to_html()
                        pushed = git_push([INDEX_HTML, DATA_JS])
                        log("  [深夜監視][BG] 公式情報・JSONファイル更新 完了" + (" → push済み" if pushed else "（変更なし）"))
                    _threading.Thread(target=_bg, daemon=True).start()
                    _start_odds_loop_if_needed()
                    break  # CSV到着確認できたのでスレッド終了（メインループに引き継ぎ）
        _threading.Thread(target=_await_midnight_csv, daemon=True).start()

    # 過去HISTORY_DAYS日分の結果をバックグラウンドで補完（バックテスト用）
    backfill_past_results()

    try:
        while True:
            time.sleep(CHECK_INTERVAL)
            # 深夜帯は翌日付CSVも監視（_race_date_candidates()に従う）
            curr_csv = {}
            for _pat in [str(CSV_DIR / f"*{d}*.csv") for d in _race_date_candidates()]:
                curr_csv.update(get_mtimes(_pat))
            curr_tenji = get_mtimes(str(TENJI_DIR / "*.json"))
            curr_comment = get_mtimes(str(COMMENT_DIR / "*.json")) if COMMENT_DIR.exists() else {}
            curr_result  = get_mtimes(str(RESULT_DIR / "*.json")) if RESULT_DIR.exists() else {}

            changed = []

            # Excelマスタ変更チェック → 再ビルド＋MASTER ホットリロード
            curr_xlsx_mtime = XLSX_PATH.stat().st_mtime if XLSX_PATH.exists() else None
            if curr_xlsx_mtime and curr_xlsx_mtime != prev_xlsx_mtime:
                if rebuild_master():
                    prev_xlsx_mtime = curr_xlsx_mtime

            # CSV変更チェック
            csv_changed = False
            for p, mt in curr_csv.items():
                if p not in prev_csv or prev_csv[p] != mt:
                    changed.append(Path(p))
                    log(f"  CSV変更: {Path(p).name}")
                    csv_changed = True

            # 展示情報JSON変更チェック
            for p, mt in curr_tenji.items():
                if p not in prev_tenji or prev_tenji[p] != mt:
                    changed.append(Path(p))
                    log(f"  展示情報変更: {Path(p).name}")

            # コメントJSON変更チェック
            for p, mt in curr_comment.items():
                if p not in prev_comment or prev_comment[p] != mt:
                    changed.append(Path(p))
                    log(f"  コメント変更: {Path(p).name}")

            # 結果JSON変更チェック
            for p, mt in curr_result.items():
                if p not in prev_result or prev_result[p] != mt:
                    changed.append(Path(p))
                    log(f"  結果変更: {Path(p).name}")

            if changed:
                # CSVが変わったらindex.jsonも再生成＆ALL_DATA再埋め込み
                if csv_changed:
                    # 出走表到着 → モーター情報を同期取得 → 展示情報をバックグラウンド取得
                    changed_csv_paths = [p for p in changed if str(p).endswith(".csv")]
                    if changed_csv_paths:
                        log("  出走表更新 → モーター情報取得中...")
                        fetch_motor_for_csv(changed_csv_paths)
                        # 新規JSONが生成されたので prev_tenji を更新
                        prev_tenji = get_mtimes(str(TENJI_DIR / "*.json"))
                        # ★ 展示情報はバックグラウンドで取得
                        # （取得完了後にメインループが tenji_data/*.json の変更を検知して push）
                        # ★ 注意: fetch_tenji_for_csv は非同期のため、ここでは prev_tenji を
                        #    更新しない。スレッド完了後に次の10秒ループで変更を検知する。
                        fetch_tenji_for_csv(changed_csv_paths)
                        # ★ 展開別残存ビューアの会場・選手名を更新
                        if inject_race_entry_to_viewer(changed_csv_paths):
                            changed.append(VIEWER_HTML)
                    idx = make_csv_index()
                    changed.append(idx)
                    inject_all_data_to_html()
                    inject_master_ext_to_html()  # venue_kimari / tenkai_remaining を埋め込む

                # ── 展示・コメント変更時は data.js のみ先行push（高速・難読化なし） ──
                # ★ csv_changed のときも tenji JSON が変わっていれば先行pushする
                #    （fetch_tenji_for_csv が前回ループで完了した場合など）
                tenji_changed = any(
                    "tenji" in str(p) and str(p).endswith(".json")
                    for p in changed
                )
                comment_changed = any(
                    "comment" in str(p) and str(p).endswith(".json")
                    for p in changed
                )
                tenji_or_comment_changed = tenji_changed or comment_changed
                tenji_push_done = False  # ★ 先行push済みフラグ
                if tenji_or_comment_changed:
                    inject_tenji_to_html()
                    inject_comment_to_html()
                    inject_flying_to_html()
                    # git add だけここで実施し、commit+pushはキューに委譲
                    with _git_lock:
                        if DATA_JS.exists():
                            _run_nolock(["git", "add", str(DATA_JS)])
                        write_tenji_json_file()
                        for tj in DATA_DIR.glob("tenji_*.json"):
                            _run_nolock(["git", "add", str(tj)])
                        update_cache_version()
                        _run_nolock(["git", "add", str(INDEX_HTML)])
                        code2, out2 = _run_nolock(["git", "status", "--porcelain"])
                        tracked2 = [l for l in out2.strip().splitlines() if not l.startswith("??")]
                        if tracked2:
                            tenji_summary = _summarize_push_targets(changed)
                            msg2 = f"tenji update {datetime.now().strftime('%Y-%m-%d %H:%M')} [{tenji_summary}]"
                            _push_queue.put(("raw", None, msg2))
                            log(f"  ✓ 展示情報 pushキューに追加 [{tenji_summary}]")
                            tenji_push_done = True  # ★ キュー追加成功
                else:
                    inject_tenji_to_html()
                    inject_comment_to_html()
                    inject_flying_to_html()

                # ※ RESULT_DATAはバックグラウンドスレッドが独立してpushするためここでは呼ばない
                # フェーズ3: 停止 → data/history_YYYYMMDD.json でfetch配信
                # inject_history_to_html()

                # race_index取得は公式サイトへのHTTPアクセス（約30秒）を伴うため、
                # 開催グレード・タイトルが変わりうるCSV変更時のみ実行する。
                # 展示・コメント・結果変更時はスキップして先行pushの遅延を防ぐ。
                if csv_changed:
                    fetch_and_inject_race_index()  # 公式サイトから開催グレード情報を埋め込む
                write_all_json_files()    # フェーズ1: data/*.json を追加書き出し（HTML変更なし）

                # オッズ永続ループの死活監視 → 死んでいれば再起動
                _start_odds_loop_if_needed()

                # ★ 展示先行push済み かつ CSV変更なし → 通常push（obfuscate込み）をスキップ
                #　 CSV変更あり（出走表・index.html更新）は先行pushの有無に関わらず通常pushも実行
                if tenji_push_done and not csv_changed:
                    log("  展示のみ変更 → 先行push済みのため通常pushをスキップ")
                else:
                    git_push(changed)
                prev_csv     = curr_csv
                prev_tenji   = curr_tenji
                prev_comment = curr_comment
                prev_result  = curr_result

            # 結果バックグラウンド取得（5分ごと・CSVがある会場のみ・全確定後は停止）
            if not hasattr(main, '_last_result_fetch'):
                main._last_result_fetch = 0
            if not hasattr(main, '_result_fetch_done'):
                main._result_fetch_done = False
            if not main._result_fetch_done and time.time() - main._last_result_fetch > 300:
                main._last_result_fetch = time.time()
                venues_in_csv = {}
                for csv_path in get_today_csvs():
                    try:
                        try:
                            df = pd.read_csv(csv_path, encoding="utf-8")
                        except UnicodeDecodeError:
                            df = pd.read_csv(csv_path, encoding="shift_jis")
                        if "会場" in df.columns:
                            vname = str(df.iloc[0]["会場"]).strip()
                            date_raw = str(df.iloc[0].get("日付", today_str())).strip().replace("/", "-")
                            if vname in VENUE_SLUG:
                                venues_in_csv[vname] = date_raw
                    except Exception:
                        continue
                if venues_in_csv:
                    import threading as _threading
                    def _result_worker(venues):
                        all_done = fetch_result_for_venues(venues)
                        if all_done:
                            main._result_fetch_done = True
                    _threading.Thread(
                        target=_result_worker,
                        args=(venues_in_csv,),
                        daemon=True,
                    ).start()

            # オッズループの死活監視（CSVに変更がなくても定期的に確認）
            _start_odds_loop_if_needed()

    except KeyboardInterrupt:
        log("\n[終了]")
        _odds_worker_stop.set()   # オッズループに停止シグナルを送る

if __name__ == "__main__":
    main()