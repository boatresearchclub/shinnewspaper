# -*- coding: utf-8 -*-
"""
export_indices_csv.py  ─  指数蓄積スクリプト【CSV直接保存版】

【保存方式】
  ・保存フォーマット: CSV（会場別ファイル）
      数値蓄積/{会場名}.csv に直接読み書き
  ・更新方式: 同一（日付・会場・レース番号・枠番）キーは常に上書き
      ※ 過去日付も含めて再実行すれば最新の計算結果に差し替わる

【ファイル構成】
  数値蓄積/
    {会場名}.csv      ← 会場ごとのCSVファイル（直接保存）

【後方互換】
  append_race_indices() / append_all_races() / get_existing_keys()
  のシグネチャはすべて旧版と同一なので呼び出し側の変更不要。

【evaluate_all_with_scores の戻り値構造（evaluate_jizen.py 実コード確認済み）】
  {
    "in_nige"             : list[str]  × 6  ← 記号（◎○△空白）
    "aisho"               : list[str]  × 6  ← 記号
    "kiryoku"             : list[str]  × 6  ← 機力記号（A/B/C/D/E）
    "jizaisei"            : list[str]  × 6  ← 安定性記号
    "tenkai"              : list[str]  × 6  ← 展開記号（4〜6枠のみ）
    "aisho_raw_scores"    : list[float|None] × 6  ← 相性生スコア
    "tenkai_raw_scores"   : list[float|None] × 6  ← 展開生スコア
    "jizaisei_raw_scores" : list[float|None] × 6  ← 安定性生スコア
    "in_nige_score"       : float            ← 1号艇逃げ合成スコア
  }
  ※ "scores" キーは存在しない（前バージョンの誤り）
"""

import csv
import math
import pathlib
import sys

import pandas as pd

try:
    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    from lr_config import CSV_DIR
    OUTPUT_CSV = CSV_DIR / "indices_log.csv"
    CSV_SAVE_DIR = CSV_DIR          # 数値蓄積フォルダと同じ場所に .csv を置く
except ImportError:
    OUTPUT_CSV = pathlib.Path(__file__).parent / "indices_log.csv"
    CSV_SAVE_DIR = pathlib.Path(__file__).parent


# ════════════════════════════════════════════════════════════════
# ヘッダー定義（旧版と完全同一）
# ════════════════════════════════════════════════════════════════

RACE_COLS = ["日付", "会場", "レース番号"]

PLAYER_KEYS = [
    ("waku",         "枠番"),
    ("name",         "選手名"),
    ("kumi",         "級別"),
    ("motor2",       "モーター2連率"),
    ("course",       "進入コース"),
    ("honmei",       "印"),
    ("rel_win1",     "オリジナル1着率"),
    ("circle_pct",   "イン逃げ2着率"),
    ("idx3",         "3着指数"),
    ("abs_win3",     "3連対率"),
    ("avg_st",       "平均ST"),
    ("avg_st_rank",  "平均ST順位"),
    ("tenji_time",   "展示タイム"),
    ("tenji_hensa",  "展示偏差値"),
    ("fly_count",    "FLY数"),
    ("fly_label",    "FLY影響"),
    ("late_count",   "出遅れ数"),
    ("data_missing", "データ不足"),
    ("kimari",       "決まり手傾向"),
    ("kosetsu",      "今節成績"),
    ("vc_trust",     "会場別信頼度"),
    ("sanren_idx",       "3連対指数"),
    ("sanren_raw_ratio", "3連対補正比"),
]

JIZEN_SYM_KEYS = [
    ("in_nige",  "イン逃げ評価"),
    ("aisho",    "相性評価"),
    ("kiryoku",  "機力評価"),
    ("jizaisei", "S安定評価"),
    ("tenkai",   "展開評価"),
]

JIZEN_RAW_KEYS = [
    ("aisho_raw_scores",    "相性生スコア"),
    ("jizaisei_raw_scores", "安定性生スコア"),
    ("tenkai_raw_scores",   "展開生スコア"),
]

JIZEN_SCALAR_KEYS = [
    ("in_nige_score", "逃げ合成スコア"),
]

RACE_JUDGMENT_KEYS = [
    ("rank",              "レースランク"),
    ("score",             "レーススコア"),
    ("skip",              "見送り推奨"),
    ("strategy",          "戦略"),
    ("venue_c1_win_rate", "会場1C勝率"),
    ("himo_are",          "ヒモ荒れ"),
]

RYOTATE_KEYS = [
    ("label",      "両立て判定"),
    ("tobi_type",  "飛びタイプ"),
    ("tobi_score", "飛びスコア"),
    ("verdict",    "3択verdict"),
]

AFFINITY_KEYS = [
    ("threat_total",        "脅威合計"),
    ("boat1_vulnerability", "1号艇脆弱性"),
    ("dominant_attacker",   "最大脅威艇"),
]

# ── bet_suggestions から取得する実買い目カラム ──────────────────────
# レース単位（全艇共通）で枠番=1の行にのみ書き込み、他の艇行は空文字
#
# candidates の構造（lr_suggest.py / scenario_engine.py 共通）:
#   [{"combo":"2-1-3", "prob":0.085, "prob_pct":8.5,
#     "himo_score":0.623, "scenario":"逃げ本線",
#     "is_orkaeshi":False, "is_orkaeshi_23":False,
#     "is_sc_bet":False, "is_fallback_bet":False, "is_dh_bet":False,
#     "reason":"..."}, ...]
#
# 保存方針:
#   買い目          : combo のみパイプ区切り（バックテスト突合用）
#   買い目_確率     : combo:prob_pct% 形式（精度分析用）
#   買い目_シナリオ : combo:scenario 形式（シナリオ別精度用）
#   見送りフラグ    : skip=True→"1" / False→"0"
#   ※ is_fallback_bet / is_dh_bet は除外（本命買い目のみで突合）
BET_KEYS = [
    ("買い目",          "買い目"),          # 本命combo パイプ区切り（突合用）
    ("買い目_全",       "買い目_全"),        # 全combo（fallback/DH含む）パイプ区切り
    ("買い目_確率",     "買い目_確率"),      # combo:prob_pct% 形式
    ("買い目_シナリオ", "買い目_シナリオ"),  # combo:scenario 形式
    ("点数",            "点数"),            # 本命点数
    ("点数_全",         "点数_全"),          # 全点数
    ("1号艇1着確率",    "1号艇1着確率"),    # s1_prob
    ("見送りフラグ",    "見送りフラグ"),    # 1=見送り
    ("見送り理由",      "見送り理由"),      # skip_reason
    ("シナリオ種別",    "シナリオ種別"),    # scenario_type
    ("展開パターン",    "展開パターン"),    # tenkai_pattern (A/B/C/D)
]

RAW_CM_KIMETE_KEYS = [
    ("逃げ%",       "逃げ%"),
    ("差し%",       "差し%"),
    ("まくり%",     "まくり%"),
    ("まくり差し%", "まくり差し%"),
    ("抜き%",       "抜き%"),
    ("差され%",     "差され%"),
    ("捲られ%",     "まくられ%"),
    ("捲り差され%", "まくり差され%"),
]

ALL_HEADERS = (
    list(RACE_COLS)
    + [col for _, col in PLAYER_KEYS]
    + [col for _, col in RAW_CM_KIMETE_KEYS]
    + [col for _, col in JIZEN_SYM_KEYS]
    + [col for _, col in JIZEN_RAW_KEYS]
    + [col for _, col in JIZEN_SCALAR_KEYS]
    + [col for _, col in RACE_JUDGMENT_KEYS]
    + [col for _, col in RYOTATE_KEYS]
    + [col for _, col in AFFINITY_KEYS]
    + [col for _, col in BET_KEYS]        # ← 実買い目カラム追加
)

# upsertのキー列（この組み合わせが一致したら上書き）
UPSERT_KEY = ["日付", "会場", "レース番号", "枠番"]


# ════════════════════════════════════════════════════════════════
# ユーティリティ
# ════════════════════════════════════════════════════════════════

def _s(v) -> str:
    if v is None:
        return ""
    try:
        if isinstance(v, float) and math.isnan(v):
            return ""
    except Exception:
        pass
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, float):
        return f"{v:.4f}".rstrip("0").rstrip(".")
    return str(v).strip()


def _idx_val(lst, waku_str: str) -> str:
    if not lst:
        return ""
    try:
        idx = int(waku_str) - 1
        return _s(lst[idx]) if 0 <= idx < len(lst) else ""
    except (ValueError, TypeError):
        return ""


def _csv_path(venue: str, base_dir: pathlib.Path = None) -> pathlib.Path:
    """会場名 → CSVファイルパス"""
    d = pathlib.Path(base_dir) if base_dir else CSV_SAVE_DIR
    return d / f"{venue}.csv"


# ════════════════════════════════════════════════════════════════
# 行データ構築（旧版 build_rows と同一ロジック）
# ════════════════════════════════════════════════════════════════

def _build_bet_vals(bet_suggestions: dict, is_first_row: bool) -> dict:
    """
    bet_suggestions から実買い目カラムを生成する。
    枠番=1（先頭艇）の行にのみ書き込み、他の艇行は空文字。

    candidates の構造（lr_suggest.py 確認済み）:
      [{"combo":"2-1-3", "prob":0.085, "prob_pct":8.5,
        "scenario":"逃げ本線", "is_fallback_bet":False,
        "is_dh_bet":False, "is_sc_bet":False, ...}, ...]
    """
    empty = {col: "" for col, _ in BET_KEYS}  # BET_KEYSは(key,col)形式
    # ↑ BET_KEYSのタプルは(日本語キー, 日本語カラム名)で同一なので cols で統一
    empty = {col: "" for _, col in BET_KEYS}

    if not is_first_row:
        return empty

    bs = bet_suggestions or {}
    cands = bs.get("candidates") or []

    # ── 本命買い目（fallback / DH を除いた主力買い目）──────────────
    honmei_cands = [
        c for c in cands
        if c.get("combo")
        and not c.get("is_fallback_bet")
        and not c.get("is_dh_bet")
    ]
    # ── 全買い目（fallback / DH 含む全体）──────────────────────────
    all_cands = [c for c in cands if c.get("combo")]

    # combo 文字列リスト
    honmei_combos = [c["combo"] for c in honmei_cands]
    all_combos    = [c["combo"] for c in all_cands]

    # combo:prob_pct% 形式（例: "2-1-3:8.50%|2-1-5:6.20%"）
    prob_str = "|".join(
        f"{c['combo']}:{c.get('prob_pct', round(c.get('prob',0)*100, 2))}%"
        for c in honmei_cands
    )

    # combo:scenario 形式（例: "2-1-3:逃げ本線|2-1-5:逃げ本線"）
    scenario_str = "|".join(
        f"{c['combo']}:{c.get('scenario','')}"
        for c in honmei_cands
    )

    # skip フラグ
    skip_val = bs.get("skip") or False
    skip_str = "1" if skip_val else "0"

    return {
        "買い目":          "|".join(honmei_combos),
        "買い目_全":       "|".join(all_combos),
        "買い目_確率":     prob_str,
        "買い目_シナリオ": scenario_str,
        "点数":            _s(len(honmei_combos)),
        "点数_全":         _s(len(all_combos)),
        "1号艇1着確率":   _s(bs.get("s1_prob")),
        "見送りフラグ":    skip_str,
        "見送り理由":      _s(bs.get("skip_reason")),
        "シナリオ種別":    _s(bs.get("scenario_type") or bs.get("scenario_verdict")),
        "展開パターン":    _s(bs.get("tenkai_pattern")),
    }


def build_rows(race_data: dict) -> list:
    race_no    = _s(race_data.get("race_no"))
    venue      = _s(race_data.get("venue"))
    race_date  = _s(race_data.get("race_date"))
    results    = race_data.get("results") or []
    rj         = race_data.get("race_judgment") or {}
    jizen_eval = race_data.get("jizen_eval") or {}
    bs         = race_data.get("bet_suggestions") or {}   # ← 実買い目を受け取る

    rj_vals = {col: _s(rj.get(key)) for key, col in RACE_JUDGMENT_KEYS}

    ry = rj.get("ryotate") or {}
    ry = ry if isinstance(ry, dict) else {}
    ry_vals = {col: _s(ry.get(key)) for key, col in RYOTATE_KEYS}

    af = rj.get("affinity") or {}
    af = af if isinstance(af, dict) else {}
    af_vals = {col: _s(af.get(key)) for key, col in AFFINITY_KEYS}

    jizen_scalar_vals = {col: _s(jizen_eval.get(key)) for key, col in JIZEN_SCALAR_KEYS}

    rows = []
    for i, r in enumerate(results):
        if not isinstance(r, dict):
            continue
        waku_str = _s(r.get("waku"))

        # 買い目は枠番=1（先頭艇）の行にのみ書き込む
        is_first = (i == 0)
        bet_vals = _build_bet_vals(bs, is_first)

        row = {"日付": race_date, "会場": venue, "レース番号": race_no}

        for key, col in PLAYER_KEYS:
            row[col] = _s(r.get(key))

        raw_cm = r.get("raw_cm") or {}
        for cm_key, col in RAW_CM_KIMETE_KEYS:
            v = raw_cm.get(cm_key)
            row[col] = _s(v) if v is not None else ""

        for key, col in JIZEN_SYM_KEYS:
            row[col] = _idx_val(jizen_eval.get(key), waku_str)

        for key, col in JIZEN_RAW_KEYS:
            row[col] = _idx_val(jizen_eval.get(key), waku_str)

        row.update(jizen_scalar_vals)
        row.update(rj_vals)
        row.update(ry_vals)
        row.update(af_vals)
        row.update(bet_vals)   # ← 実買い目カラムをマージ

        rows.append(row)

    return rows


# ════════════════════════════════════════════════════════════════
# CSV 読み書きコア
# ════════════════════════════════════════════════════════════════

def _sort_df(df: pd.DataFrame) -> pd.DataFrame:
    """日付・レース番号・枠番でソート。数値列は数値として扱う。"""
    df = df.copy()
    for col in ["レース番号", "枠番"]:
        if col in df.columns:
            df[f"__{col}"] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    sort_cols = ["日付", "__レース番号", "__枠番"]
    sort_cols = [c for c in sort_cols if c in df.columns]
    df = df.sort_values(sort_cols).reset_index(drop=True)
    df = df.drop(columns=[c for c in df.columns if c.startswith("__")], errors="ignore")
    return df


def _load_venue_csv(venue: str, csv_dir: pathlib.Path = None) -> pd.DataFrame:
    """会場CSVを読み込む。なければ空DataFrameを返す。"""
    p = _csv_path(venue, csv_dir)
    if p.exists():
        try:
            return pd.read_csv(p, encoding="utf-8-sig", dtype=str).fillna("")
        except Exception as e:
            print(f"  [CSV] {p.name} 読み込みエラー（空DataFrameで代替）: {e}")
    return pd.DataFrame(columns=ALL_HEADERS)


def _save_venue_csv(df: pd.DataFrame, venue: str, csv_dir: pathlib.Path = None):
    """会場DataFrameをCSVに保存（完全上書き）。"""
    p = _csv_path(venue, csv_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(p, index=False, encoding="utf-8-sig")


def _upsert_venue(new_rows: list, venue: str, csv_dir: pathlib.Path = None):
    """
    new_rows（dict のリスト）を会場CSVにupsert。
    同一（日付, 会場, レース番号, 枠番）は上書き、それ以外はそのまま保持。
    過去日付も含めて再実行すれば最新の計算結果に差し替わる。
    """
    if not new_rows:
        return

    new_df = pd.DataFrame(new_rows, columns=ALL_HEADERS)

    existing = _load_venue_csv(venue, csv_dir)

    if existing.empty:
        merged = new_df
    else:
        # 既存から新規キーに該当する行を除外してマージ
        new_keys = set(
            zip(new_df["日付"], new_df["会場"], new_df["レース番号"], new_df["枠番"])
        )
        mask = ~existing.apply(
            lambda r: (r["日付"], r["会場"], r["レース番号"], r["枠番"]) in new_keys,
            axis=1,
        )
        merged = pd.concat([existing[mask], new_df], ignore_index=True)

    merged = _sort_df(merged)
    _save_venue_csv(merged, venue, csv_dir)


# ════════════════════════════════════════════════════════════════
# 公開 API（呼び出し側のシグネチャは旧版と同一）
# ════════════════════════════════════════════════════════════════

def get_existing_keys(output_path=None) -> set:
    """
    CSVに既に存在する（日付, 会場, レース番号, 枠番）のセットを返す。
    output_path には従来の indices_log.csv パスを渡せばそのディレクトリのCSVを参照する。
    """
    csv_dir = pathlib.Path(output_path).parent if output_path else CSV_SAVE_DIR
    keys = set()
    for csv_file in csv_dir.glob("*.csv"):
        try:
            df = pd.read_csv(csv_file, encoding="utf-8-sig", dtype=str).fillna("")
            if all(c in df.columns for c in ["日付", "会場", "レース番号", "枠番"]):
                for row in df[["日付", "会場", "レース番号", "枠番"]].itertuples(index=False):
                    keys.add(tuple(row))
        except Exception:
            pass
    return keys


def append_all_races(all_race_data: list, output_path=None):
    """
    全レースをCSVに保存（load_race.py から呼ぶ）。
    同一キーは上書き（過去日付も含む）。
    """
    csv_dir = pathlib.Path(output_path).parent if output_path else CSV_SAVE_DIR
    csv_dir.mkdir(parents=True, exist_ok=True)

    # 会場ごとにグルーピング
    venue_rows: dict[str, list] = {}
    for rd in all_race_data:
        rows = build_rows(rd)
        if not rows:
            continue
        venue = rows[0].get("会場", "unknown")
        venue_rows.setdefault(venue, []).extend(rows)

    if not venue_rows:
        print("  [CSV] 保存対象なし")
        return

    total = 0
    for venue, rows in venue_rows.items():
        _upsert_venue(rows, venue, csv_dir)
        total += len(rows)
        print(f"  [CSV] {venue} 保存完了 ({len(rows)}行) → {venue}.csv")

    print(f"  [CSV] 合計 {total}行 保存完了")


def append_race_indices(race_data: dict, output_path=None):
    """1レース分だけ保存（デバッグ用）。"""
    csv_dir = pathlib.Path(output_path).parent if output_path else CSV_SAVE_DIR
    csv_dir.mkdir(parents=True, exist_ok=True)

    rows = build_rows(race_data)
    if not rows:
        return
    venue = rows[0].get("会場", "unknown")
    _upsert_venue(rows, venue, csv_dir)
    print(f"  [CSV] {venue} {race_data.get('race_no')}R 保存 ({len(rows)}行)")


def overwrite_venue_all(venue: str, all_race_data: list, output_path=None):
    """
    指数ロジック改良後の再計算専用。
    その会場の全レースを渡すと CSV を完全上書き（マージなし）。

    使い方:
        # 例: びわこの指数を全部再計算した後
        overwrite_venue_all("びわこ", recalculated_race_data_list)
    """
    csv_dir = pathlib.Path(output_path).parent if output_path else CSV_SAVE_DIR
    csv_dir.mkdir(parents=True, exist_ok=True)

    all_rows = []
    for rd in all_race_data:
        all_rows.extend(build_rows(rd))

    if not all_rows:
        print(f"  [CSV] {venue}: 保存対象なし")
        return

    new_df = pd.DataFrame(all_rows, columns=ALL_HEADERS)
    new_df = _sort_df(new_df)
    _save_venue_csv(new_df, venue, csv_dir)
    print(f"  [CSV] {venue} 完全上書き完了 ({len(all_rows)}行)")


# ════════════════════════════════════════════════════════════════
# pickle → CSV 移行ユーティリティ
# ════════════════════════════════════════════════════════════════

def migrate_pickle_to_csv(pkl_dir=None, csv_dir=None):
    """
    既存の .pkl ファイルを会場別CSVに変換する。
    pkl → csv への移行時に一度だけ実行する。

    Args:
        pkl_dir  : pickleファイルのあるディレクトリ（省略時は CSV_SAVE_DIR）
        csv_dir  : CSV出力先ディレクトリ（省略時は pkl_dir と同じ）
    """
    in_dir  = pathlib.Path(pkl_dir)  if pkl_dir  else CSV_SAVE_DIR
    out_dir = pathlib.Path(csv_dir)  if csv_dir  else in_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    pkl_files = list(in_dir.glob("*.pkl"))
    if not pkl_files:
        print(f"  [移行] .pkl ファイルが見つかりません: {in_dir}")
        return

    total = 0
    for p in pkl_files:
        venue = p.stem
        try:
            df = pd.read_pickle(p)
            out_path = out_dir / f"{venue}.csv"
            df.to_csv(out_path, index=False, encoding="utf-8-sig")
            print(f"  [移行] {venue}: {len(df)}行 → {out_path.name}")
            total += len(df)
        except Exception as e:
            print(f"  [移行] {p.name} 変換エラー: {e}")

    print(f"  [移行] 完了 (合計 {total}行 / {len(pkl_files)}会場)")


# ════════════════════════════════════════════════════════════════
# 単体テスト
# ════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import time, tempfile

    dummy_races = [
        {
            "race_no": "3", "venue": "常滑", "race_date": "2026-03-28",
            "results": [
                {"waku":"1","name":"森永 淳","kumi":"A1","motor2":"42.5","course":"1",
                 "honmei":"◎","rel_win1":55.2,"circle_pct":None,"idx3":0,
                 "abs_win3":88.5,"avg_st":0.13,"tenji_time":None,"tenji_hensa":None,
                 "fly_count":0,"fly_label":"低","late_count":0,"vc_trust":0.7,
                 "data_missing":False,"kimari":"逃げ65%","kosetsu":"1-1-3"},
                {"waku":"2","name":"後藤孝義","kumi":"A2","motor2":"38.0","course":"2",
                 "honmei":"○","rel_win1":20.1,"circle_pct":42.3,"idx3":35,
                 "abs_win3":72.0,"avg_st":0.15,"tenji_time":None,"tenji_hensa":None,
                 "fly_count":0,"fly_label":"低","late_count":1,"vc_trust":0.4,
                 "data_missing":False,"kimari":"差し55%","kosetsu":"2-3-1"},
            ],
            "race_judgment": {
                "rank":"A","score":68,"skip":False,"strategy":"◎-○軸流し",
                "venue_c1_win_rate":0.62,"himo_are":False,
                "ryotate":{"label":"逃げ本線","tobi_type":"通常","tobi_score":25,"verdict":"逃げ"},
                "affinity":{"threat_total":55.0,"boat1_vulnerability":28.0,"dominant_attacker":"2"},
            },
            "jizen_eval": {
                "in_nige":             ["◎","","","","",""],
                "aisho":               ["","○","","","",""],
                "kiryoku":             ["B","A","C","B","D","E"],
                "jizaisei":            ["◎","○","△","","",""],
                "tenkai":              ["","","","◎","○",""],
                "aisho_raw_scores":    [None, 0.52, 0.38, 0.45, 0.30, 0.22],
                "tenkai_raw_scores":   [None, None, None, 0.61, 0.48, 0.35],
                "jizaisei_raw_scores": [0.85, 0.72, 0.60, 0.75, 0.50, 0.40],
                "in_nige_score":       0.48,
            },
        }
    ]

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = pathlib.Path(tmp)
        out_csv = tmp_dir / "indices_log.csv"

        # append_all_races テスト
        t0 = time.perf_counter()
        append_all_races(dummy_races, output_path=out_csv)
        t1 = time.perf_counter()
        print(f"append_all_races: {(t1-t0)*1000:.2f}ms")

        # get_existing_keys テスト
        keys = get_existing_keys(output_path=out_csv)
        print(f"get_existing_keys: {len(keys)}件")

        # 同じデータで再実行（上書き確認）
        t0 = time.perf_counter()
        append_all_races(dummy_races, output_path=out_csv)
        t1 = time.perf_counter()
        print(f"再実行（上書き）: {(t1-t0)*1000:.2f}ms")

        # overwrite_venue_all テスト
        t0 = time.perf_counter()
        overwrite_venue_all("常滑", dummy_races, output_path=out_csv)
        t1 = time.perf_counter()
        print(f"overwrite_venue_all: {(t1-t0)*1000:.2f}ms")

        # CSV確認
        result_csv = tmp_dir / "常滑.csv"
        if result_csv.exists():
            df = pd.read_csv(result_csv, encoding="utf-8-sig")
            print(f"CSV出力確認: {len(df)}行, 列数={len(df.columns)}")
            print(df[["日付", "会場", "レース番号", "枠番", "選手名"]].to_string())
