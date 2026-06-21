"""
prob_scenario_engine.py  —  確率計算・展開補正エンジン
========================================================
auto_push.py から計算ロジックを分離したモジュール。
GitHub連携・ファイル監視には一切関与しない。

【提供する機能】
  - マスタ読み込み・ホットリロード（load_master / apply_kimari_tuning / rebuild_master）
  - 基準確率計算（calc_prob_from_master）
  - 展示スコア計算（_calc_tenji_scores_for_race / _inject_tenji_scores）
  - 展開スコア計算（_calc_tenkai_scores）
  - ST補正・調子補正（st_rank_to_correction / form_correction）

【auto_push.py 側の変更方法】
  from prob_scenario_engine import (
      load_master, apply_kimari_tuning, rebuild_master,
      calc_prob_from_master, _inject_tenji_scores,
      normalize_name, resolve_player_name,
      MASTER,   # ← 参照のみ。更新は rebuild_master() 経由で行う
  )
"""

import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime

# ── パス定義（auto_push.py と同じ規則）──────────────────────────────
SCRIPTS_DIR      = Path(__file__).parent
DATA_COLLECT_DIR = Path(r"C:\Users\user\Desktop\データ収集\scripts")

MASTER_JSON        = DATA_COLLECT_DIR / "master_data.json"
KIMARI_TUNING_JSON = DATA_COLLECT_DIR / "kimari_tuning.json"
TENJI_DIR          = DATA_COLLECT_DIR / "tenji_data"
XLSX_PATH          = DATA_COLLECT_DIR.parent / "ボートリサーチ_マスタ.xlsx"
BUILD_MASTER_PY    = SCRIPTS_DIR / "build_master_json.py"

# 会場名 → fetch_tenji.py のURLスラッグ（auto_push.py と同一マップ）
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


# ══════════════════════════════════════════════════════════════════
# ログ（auto_push.py の log() に依存しない独立実装）
# ══════════════════════════════════════════════════════════════════
def _log(msg: str) -> None:
    print(f"[prob_engine] {msg}", flush=True)


# ══════════════════════════════════════════════════════════════════
# マスタ読み込み・ホットリロード
# ══════════════════════════════════════════════════════════════════

def load_master() -> dict:
    if MASTER_JSON.exists():
        with open(MASTER_JSON, encoding="utf-8") as f:
            return json.load(f)
    return {}


def apply_kimari_tuning(master: dict) -> dict:
    """
    kimari_tuning.json が存在すれば tune_kimari.py が算出した
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
        master = dict(master)
        original = master.get("venue_kimari", {})
        merged   = {**original, **tuned_kimari}
        master["venue_kimari"] = merged
        built_at = tuning.get("built_at", "不明")
        _log(f"✓ kimari_tuning.json 適用: {len(tuned_kimari)}会場 (生成日時: {built_at})")
    except Exception as e:
        _log(f"⚠ kimari_tuning.json 読み込みエラー: {e} → 生の値を使用")
    return master


# モジュール読み込み時に1度だけロード
MASTER: dict = apply_kimari_tuning(load_master())


def rebuild_master() -> bool:
    """
    ボートリサーチ_マスタ.xlsx から master_data.json を再ビルドし
    グローバルの MASTER をホットリロードする。
    auto_push.py のメインループから Excelマスタ変更検知時に呼ぶ。
    """
    global MASTER
    if not XLSX_PATH.exists():
        _log(f"⚠ {XLSX_PATH.name} が見つかりません → マスタ再ビルドスキップ")
        return False
    if not BUILD_MASTER_PY.exists():
        _log(f"⚠ {BUILD_MASTER_PY.name} が見つかりません → マスタ再ビルドスキップ")
        return False

    _log("Excelマスタ更新検知 → master_data.json を再ビルド中...")
    result = subprocess.run(
        [sys.executable, str(BUILD_MASTER_PY), str(XLSX_PATH), str(MASTER_JSON)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if result.returncode != 0:
        _log(f"✕ 再ビルド失敗: {result.stderr.strip()}")
        return False

    MASTER = apply_kimari_tuning(load_master())
    _log(f"✓ マスタ再ビルド完了 / 選手数: {len(MASTER.get('course_master', {}))}")
    return True


# ══════════════════════════════════════════════════════════════════
# 名前正規化・選手名解決
# ══════════════════════════════════════════════════════════════════

def normalize_name(name: str) -> str:
    return str(name).replace("\u3000", "").replace(" ", "").strip()


def resolve_player_name(raw_name: str, reg_no) -> tuple[str, str]:
    id_map  = MASTER.get("player_id_map", {})
    reg_str = str(reg_no).strip() if reg_no else ""
    if reg_str and reg_str in id_map:
        return id_map[reg_str], "id"
    normalized = normalize_name(raw_name)
    for official in MASTER.get("course_master", {}):
        if official.startswith(normalized):
            return official, "prefix"
    return normalize_name(raw_name), "unresolved"


# ══════════════════════════════════════════════════════════════════
# ST補正・調子補正
# ══════════════════════════════════════════════════════════════════

def st_rank_to_correction(st_rank) -> float:
    """
    コース別ST順位 → 補正係数（rank=1→1.2 / rank=3.0→1.0 / rank=6→0.7）
    """
    if st_rank is None:
        return 1.0
    raw = 1.0 + (3.0 - st_rank) * (0.2 / 2.5)
    return max(0.7, min(1.2, raw))


def form_correction(player_idx: dict | None, overall_win) -> float:
    """
    選手の調子補正係数を返す。
    FLY明け補正（最優先）→ bayesian_win ベース4段階評価。
    """
    if not player_idx:
        return 1.0
    # ① FLY明け補正
    fly_days       = player_idx.get("fly_days")
    fly_after_runs = player_idx.get("fly_after_runs") or 0
    if fly_days is not None and fly_after_runs < 10:
        return 0.85
    # ② bayesian_win
    bayesian = player_idx.get("bayesian_win")
    base     = overall_win or player_idx.get("overall_win")
    if bayesian is None or not base or base <= 0:
        return 1.0
    ratio = bayesian / base
    if   ratio >= 1.20: return 1.12
    elif ratio >= 1.08: return 1.06
    elif ratio <= 0.80: return 0.88
    elif ratio <= 0.92: return 0.94
    else:               return 1.00


# ══════════════════════════════════════════════════════════════════
# 会場別 被kimari補正強度
# ⚠️ SYNC REQUIRED: sample.js の VENUE_HI_KIMARI_STRENGTH と同一に保つこと
# ══════════════════════════════════════════════════════════════════

_VENUE_HI_KIMARI_STRENGTH = {
    "大村": 1.5, "常滑": 1.5, "丸亀": 1.5, "尼崎": 1.5,
    "住之江": 1.5, "桐生": 1.5, "下関": 1.5,
    "戸田": 2.5, "三国": 2.5, "平和島": 2.5, "浜名湖": 2.5, "蒲郡": 2.5,
    "江戸川": 2.0,
    "_default": 2.0,
}


def _get_hi_kimari_strength(venue: str) -> float:
    return _VENUE_HI_KIMARI_STRENGTH.get(venue, _VENUE_HI_KIMARI_STRENGTH["_default"])


# ══════════════════════════════════════════════════════════════════
# 展示スコア計算
# ⚠️ SYNC REQUIRED: sample.js の VENUE_TENJI_CONFIG と同一に保つこと
# ══════════════════════════════════════════════════════════════════

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


def _resolve_tenji_weights(venue: str) -> dict:
    """sample.js resolveWeights() の完全移植。"""
    cfg   = _VENUE_TENJI_CONFIG.get(venue, _VENUE_TENJI_CONFIG["_default"])
    base  = dict(cfg["weight"])
    avail = cfg["available"]
    for f in _TENJI_FIELDS:
        if avail.get(f) is False:
            base[f] = 0.0
    total = sum(base.values()) or 1.0
    return {f: base[f] / total for f in _TENJI_FIELDS}


def _time_to_coef(h: float) -> float:
    """sample.js timeToCoef() の完全移植。"""
    if h >= 60: return 1.15
    if h >= 55: return 1.08
    if h >= 45: return 1.00
    if h >= 40: return 0.93
    return 0.85


def _field_coefs(boats: list, tenji_by_frame: dict, field: str) -> list | None:
    """sample.js fieldCoefs() の完全移植。"""
    vals       = [tenji_by_frame.get(b["boat"], {}).get(field) for b in boats]
    valid_vals = [v for v in vals if v is not None]
    if not valid_vals:
        return None
    fill_avg = sum(valid_vals) / len(valid_vals)
    filled   = [v if v is not None else fill_avg for v in vals]
    avg      = sum(filled) / len(filled)
    variance = sum((v - avg) ** 2 for v in filled) / len(filled)
    std      = variance ** 0.5
    if std == 0:
        return [1.0] * len(filled)
    return [_time_to_coef(50 + ((avg - v) / std) * 10) for v in filled]


def _calc_tenji_scores_for_race(boats: list, tenji_by_frame: dict, venue: str) -> None:
    """
    各 boat dict に tenji_score・tenji_score_coef を付与する（インプレース）。
    展示データがない場合は何もしない。
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
        return

    composite = []
    for i in range(len(boats)):
        score, w_total = 0.0, 0.0
        for f in _TENJI_FIELDS:
            if f not in coefs_map:
                continue
            score   += w[f] * coefs_map[f][i]
            w_total += w[f]
        composite.append(score / w_total if w_total > 0 else 1.0)

    coef_total = sum(composite) or 1.0
    coef_avg   = coef_total / len(boats)

    for i, bt in enumerate(boats):
        bt["tenji_score"] = round(composite[i] / coef_total, 6)
        bt["tenji_score_coef"] = round(
            min(2.0, max(0.5, composite[i] / coef_avg)) if coef_avg > 0 else 1.0, 4
        )


def _inject_tenji_scores(races: dict, venue: str, date_str: str) -> None:
    """
    tenji_data/*.json を読み込み各レースの boats に tenji_score を付与する。
    parse_csv() の return 直前から呼ぶ。
    """
    slug    = VENUE_SLUG.get(venue, venue)
    date_nd = date_str.replace("-", "")
    loaded  = 0

    for rno, rd in races.items():
        fpath = TENJI_DIR / f"tenji_{slug}_{date_nd}_R{rno}.json"
        if not fpath.exists():
            continue
        try:
            with open(fpath, encoding="utf-8") as f:
                rows = json.load(f)
        except Exception:
            continue
        tenji_by_frame = {r["frame"]: r for r in rows}
        _calc_tenji_scores_for_race(rd["boats"], tenji_by_frame, venue)
        loaded += 1

    if loaded:
        _log(f"✓ 展示スコア付与: {venue} {date_str}  {loaded}R分")


# ══════════════════════════════════════════════════════════════════
# 展開スコア計算（sample.js calcTenkaiProbs の Python移植）
# ══════════════════════════════════════════════════════════════════

def _calc_tenkai_scores(boats: list, venue: str) -> list:
    """
    各 boat dict に tenkai_score を付与して返す。
    MASTER の venue_kimari・course_master を参照する。
    """
    venue_kimari_all = MASTER.get("venue_kimari", {})
    course_master    = MASTER.get("course_master", {})

    if not venue_kimari_all:
        for bt in boats:
            bt["tenkai_score"] = bt["prob"]
        return boats

    vKimari = venue_kimari_all.get(venue)
    if not vKimari:
        for bt in boats:
            bt["tenkai_score"] = bt["prob"]
        return boats

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
    RELATIVE_MIN           = 0.3
    RELATIVE_MAX           = 3.0
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
            return get_personal_kimari(bt["name"], wc, kimari) >= soft[wc]
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
            attack = get_personal_kimari(winner["name"], wc, "まくり差し")
            def1   = get_personal_hi_kimari(boat1["name"], "捲り差され")
            boat2  = next((b for b in boats if int(b["boat"]) == 2), None)
            def2   = get_personal_hi_kimari(boat2["name"], "捲り差され") if boat2 else None
            if def1 is not None and def2 is not None:
                combined_def = (def1 * def2) ** 0.5
                return attack * combined_def if attack else combined_def
            elif def1 is not None:
                return (attack * def1) if def1 is not None else (attack or 1.0)
            else:
                return attack or 1.0
        return 1.0

    boat1 = next((b for b in boats if int(b["boat"]) == 1), None)

    # 被kimari率で adjustedVKimari を動的補正
    hi_strength     = _get_hi_kimari_strength(venue)
    adjustedVKimari = dict(vKimari)

    if boat1:
        name1      = boat1["name"]
        hi_kimari  = (course_master.get(name1, {}).get("1", {}).get("被kimari"))
        boat1_runs = (course_master.get(name1, {}).get("1", {}).get("runs", 0) or 0)
        if hi_kimari and boat1_runs >= 30:
            hi_trust        = min(boat1_runs / 100, 1.0)
            sasare_rate     = hi_kimari.get("差され")
            makurare_rate   = hi_kimari.get("捲られ")
            makurisasare_r  = hi_kimari.get("捲り差され")
            if sasare_rate is not None:
                adjustedVKimari["差し"] = (
                    vKimari.get("差し", 0) * (1 + hi_trust * sasare_rate * hi_strength))
            if makurare_rate is not None:
                adjustedVKimari["まくり"] = (
                    vKimari.get("まくり", 0) * (1 + hi_trust * makurare_rate * hi_strength))
            if makurisasare_r is not None:
                adjustedVKimari["まくり差し"] = (
                    vKimari.get("まくり差し", 0) * (1 + hi_trust * makurisasare_r * hi_strength))
            total_hi  = ((sasare_rate or 0) + (makurare_rate or 0) + (makurisasare_r or 0))
            nige_rate = get_personal_kimari(name1, "1", "逃げ")
            if nige_rate > 0:
                nige_boost = nige_rate / max(nige_rate + total_hi, 0.01)
                adjustedVKimari["逃げ"] = (
                    vKimari.get("逃げ", 0) * (0.5 + 0.5 * nige_boost * 2))
            adj_total = sum(adjustedVKimari.values())
            if adj_total > 0:
                adjustedVKimari = {k: v / adj_total for k, v in adjustedVKimari.items()}

    kimari_types = [k for k, v in adjustedVKimari.items()
                    if v > 0 and k in KIMARI_HARD_EXCLUDE]

    def blend_personal_kimari(bt, base_vkimari):
        name   = bt["name"]
        course = str(int(bt["boat"]))
        cm     = course_master.get(name, {}).get(course, {})
        if not cm:
            return base_vkimari
        runs = cm.get("runs", 0) or 0
        if runs < 30:
            return base_vkimari
        trust           = min(runs / 100, 1.0) * PERSONAL_BLEND_STRENGTH
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

    boat_vkimari    = {bt["boat"]: blend_personal_kimari(bt, adjustedVKimari) for bt in boats}
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
            raw_coef    = calc_relative_coef(bt, kimari, boat1)
            kimari_runs = (course_master.get(bt["name"], {})
                                        .get(str(int(bt["boat"])), {})
                                        .get("runs", 0) or 0)
            personal_trust         = min(kimari_runs / 100, 1.0)
            rel_coefs[bt["boat"]]  = raw_coef * personal_trust + 1.0 * (1 - personal_trust)

        avg_coef = sum(rel_coefs[b["boat"]] for b in valid_boats) / len(valid_boats)
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
                kimari_prob = adjustedVKimari.get(kimari, 0)
                kimari_coef_sum[bt["boat"]] += kimari_prob * RELATIVE_MIN

    raw_scores = {bt["boat"]: bt["prob"] * (kimari_coef_sum[bt["boat"]] or RELATIVE_MIN)
                  for bt in boats}
    total_ts   = sum(raw_scores.values()) or 1.0
    for bt in boats:
        bt["tenkai_score"] = round(raw_scores[bt["boat"]] / total_ts, 6)
    return boats


# ══════════════════════════════════════════════════════════════════
# 基準確率計算（コース別1着率 → prob）
# ══════════════════════════════════════════════════════════════════

def calc_prob_from_master(
    boats: list,
    venue: str,
    race_no: int = 0,
    is_joshi: bool = False,
    grade: str = "一般",
) -> list:
    """
    選手ごとのコース別1着率 → prob を計算して boats に付与する。

    grade 優先順位:
      SG / G1  → course_master_g1（reliable=False は一般マスタにフォールバック）
      女子戦   → course_master_joshi
      その他   → course_master（一般戦）
    """
    course_master_g1    = MASTER.get("course_master_g1", {})
    course_master_joshi = MASTER.get("course_master_joshi", {})
    course_master_base  = MASTER.get("course_master", {})

    IS_GRADE_MODE = grade in ("SG", "G1") and bool(course_master_g1)

    def _get_course_entry(name, c):
        if IS_GRADE_MODE:
            entry_g1 = course_master_g1.get(name, {}).get(c)
            if entry_g1 and entry_g1.get("reliable", False):
                return entry_g1
            return course_master_base.get(name, {}).get(c)
        if is_joshi and course_master_joshi:
            entry_j = course_master_joshi.get(name, {}).get(c)
            if entry_j and entry_j.get("reliable", False):
                return entry_j
            return course_master_base.get(name, {}).get(c)
        return course_master_base.get(name, {}).get(c)

    if IS_GRADE_MODE:
        course_master = course_master_g1
    elif is_joshi and course_master_joshi:
        course_master = course_master_joshi
    else:
        course_master = course_master_base

    venue_course_master = MASTER.get("venue_course_master", {})
    venue_stats         = MASTER.get("venue_stats", {}).get(venue, {})
    player_index        = MASTER.get("player_index", {})
    race_key            = str(race_no) if race_no else None
    race_course_rates   = (
        venue_stats.get("race_course_rates", {}).get(race_key, {})
        if race_key else {}
    )
    venue_course_rates  = venue_stats.get("course_rates", {})
    scores, dq_list, base_rates = [], [], []
    has_insufficient = False

    for bt in boats:
        name   = normalize_name(bt.get("name", ""))
        course = int(bt.get("boat", 1))
        c      = str(course)
        base_rate, dq = None, None

        vc = venue_course_master.get(name, {}).get(venue, {}).get(c)
        cm = _get_course_entry(name, c)

        venue_rate    = (vc.get("ts_win_rate") or vc.get("win_rate")) if vc and vc.get("reliable") else None
        national_rate = (cm.get("ts_win_rate") or cm.get("win_rate")) if cm and cm.get("reliable") else None
        venue_trust   = vc.get("trust", 0.0) if vc else 0.0

        if venue_rate is not None and national_rate is not None:
            base_rate = venue_rate * venue_trust + national_rate * (1.0 - venue_trust)
            dq = "venue_local"
        elif venue_rate is not None:
            base_rate = venue_rate
            dq = "venue_local"
        elif national_rate is not None:
            base_rate = national_rate
            dq = "course_national"

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
            pi      = player_index.get(name, {})
            st_rank = pi.get("st_rank", {}).get(c)

        st_corr   = st_rank_to_correction(st_rank)
        pi        = player_index.get(name)
        overall_w = pi.get("overall_win") if pi else None
        form_corr = form_correction(pi, overall_w)
        scores.append(base_rate * st_corr * form_corr)
        dq_list.append(dq)

        raw_win_rate = (cm.get("ts_win_rate") or cm.get("win_rate")) if cm else None
        base_rates.append(raw_win_rate)

    total = sum(scores) or 1.0
    for i, bt in enumerate(boats):
        bt["prob"]       = round(scores[i] / total, 4)
        bt["base_score"] = round(scores[i], 4)
        bt["score"]      = round(scores[i], 4)   # 後方互換
        bt["base_rate"]  = round(base_rates[i], 4) if base_rates[i] is not None else None
        bt["dq"]         = dq_list[i]
    if has_insufficient:
        for bt in boats:
            bt["prob_warning"] = True

    # 展開スコアを付与
    boats = _calc_tenkai_scores(boats, venue)
    return boats
