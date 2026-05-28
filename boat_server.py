"""
ボートリサーチ倶楽部 — データサーバー
起動: python boat_server.py
"""
import os, json, glob, threading, time
from pathlib import Path
from flask import Flask, jsonify, send_from_directory, request
from flask_cors import CORS
import pandas as pd

# ── 設定 ──────────────────────────────────────────────
BASE_DIR    = Path(__file__).parent
CSV_DIR     = Path(r"C:\Users\user\Desktop\データ収集\scripts\csv_output")
MASTER_JSON = BASE_DIR / "master_data.json"
XLSX_PATH   = Path(r"C:\Users\user\Desktop\データ収集\ボートリサーチ_マスタ.xlsx")
FLYING_DIR  = Path(r"C:\Users\user\Desktop\データ収集\scripts")  # flying_YYYYMMDD.xlsx の格納先

app = Flask(__name__, static_folder=str(BASE_DIR), static_url_path="")
CORS(app)

# ── マスターデータ読み込み ─────────────────────────────
def load_master():
    if MASTER_JSON.exists():
        with open(MASTER_JSON, encoding="utf-8") as f:
            return json.load(f)
    return {
        "course_master": {},
        "venue_course_master": {},
        "venue_stats": {},
        "player_index": {},
    }

MASTER = load_master()

def normalize_name(name: str) -> str:
    return str(name).replace("\u3000", "").replace(" ", "").strip()


def resolve_player_name(raw_name: str, reg_no: str) -> tuple:
    """
    CSV の選手名（4文字省略）と登録番号から正式名を解決する。

    解決の優先順位:
      1. 登録番号（登番）で player_id_map を引く  → 最も確実
      2. 正規化した省略名でマスタの正式名に前方一致を試みる
      3. 解決不能の場合は省略名のままとし dq_name="unresolved" を返す

    戻り値: (正式名, 解決方法)
      解決方法: "id" | "prefix" | "unresolved"
    """
    id_map = MASTER.get("player_id_map", {})

    # ① 登録番号で解決（最優先）
    reg_str = str(reg_no).strip() if reg_no else ""
    if reg_str and reg_str in id_map:
        return id_map[reg_str], "id"

    # ② 省略名の前方一致（登録番号がマスタにない場合の補助）
    normalized = normalize_name(raw_name)
    for official in MASTER.get("course_master", {}):
        if official.startswith(normalized):
            return official, "prefix"

    # ③ 解決不能 → 省略名のまま使用
    return normalize_name(raw_name), "unresolved"


# ── 確率計算（新設計）────────────────────────────────
#
# ⚠️ 以下のCSVフィールドは期初め・使い始めに偏りが大きいため計算に使用しない:
#   - win_rate（全国勝率）  : 期初めは極少数のレースで算出され信頼できない
#   - local_rate（当地勝率）: 同上
#   - motor2（モーター2連率）: 使い始めは信頼できない
# → 代わりにマスタの蓄積・時系列補正済み実績値を使用する
#
# スコア構造:
#   score = ベース1着率 × ST補正 × フォーム補正
#
# ベース1着率の優先順位（上位が信頼できる場合に採用）:
#   優先1: 会場別コースマスタ（選手×会場×コース）信頼度>0 かつ 出走数>=10
#   優先2: コース別マスタ（選手×コース・全国）出走数>=20 → 時系列補正1着率を使用
#   優先3: 会場統計（会場×コース×R番号別1着率）
#   ⚠️不足: 上記すべて閾値未満 → 選手個人のコース1着率（生値）を参考値として使用
#           相対評価は不成立のため dq="insufficient" を付与
#
# ST補正（コース別ST順位から算出）:
#   ST補正 = 0.7 〜 1.2 の範囲にクリップ
#   データなし → ST補正 = 1.0（中立）
#
# フォーム補正（選手指数マスタの直近5走1着率 vs 通算1着率）:
#   好調（+15%以上）→ × 1.10
#   不調（-15%以下）→ × 0.90
#   FLY明け（経過日数あり かつ FLY後走数が少ない）→ × 0.85
#   通常 → × 1.00

VENUE_COURSE_MIN_RUNS  = 10
COURSE_MASTER_MIN_RUNS = 20

# ST順位 → 補正係数（1位=1.2, 3〜4位=中立, 6位=0.7）
def st_rank_to_correction(st_rank: float | None) -> float:
    if st_rank is None:
        return 1.0
    # ST順位: 小さいほど早い（1位が最速）
    # 線形マッピング: rank=1→1.2, rank=3.0→1.0, rank=6→0.7
    # 基準を3.5→3.0に変更（実測平均ST順位に合わせた補正）
    raw = 1.0 + (3.0 - st_rank) * (0.2 / 2.5)
    return max(0.7, min(1.2, raw))

# 荒れスコアから確率上限を自動計算
def max_prob_by_arek(arek_score: float) -> float:
    """
    荒れスコアに応じて確率の上限を自動設定。
    arek_score: 39（荒れにくい=大村）〜 60（荒れやすい=戸田）
    → MAX_PROB: 0.82（荒れにくい）〜 0.72（荒れやすい）

    キャリブレーション結果（0.8〜1.0帯で+10〜16pt過大評価）に基づく補正。
    """
    norm = max(0.0, min((arek_score - 39.0) / (60.0 - 39.0), 1.0))
    return round(0.82 - norm * 0.10, 4)


# 直近フォームと通算から補正係数を計算
def form_correction(player_idx: dict | None, overall_win: float | None) -> float:
    if not player_idx:
        return 1.0

    # ① FLY明け補正（最優先: FLY経過日数あり かつ FLY後走数が少ない）
    fly_days       = player_idx.get("fly_days")
    fly_after_runs = player_idx.get("fly_after_runs") or 0
    if fly_days is not None and fly_after_runs < 10:
        return 0.85

    # ② bayesian_win（overall×20 + recent10×10）÷30 を使用
    #    → recent10の1〜2走ブレをノイズ除去済みのフォーム指標
    bayesian = player_idx.get("bayesian_win")
    base     = overall_win or player_idx.get("overall_win")
    if bayesian is None or not base or base <= 0:
        return 1.0

    # ③ 相対比率で判定（絶対値差ではなく通算に対する比率）
    #    → 通算0.20の選手も0.40の選手も同じ基準で評価できる
    ratio = bayesian / base
    if   ratio >= 1.20: return 1.12   # 著しく好調
    elif ratio >= 1.08: return 1.06   # 好調
    elif ratio <= 0.80: return 0.88   # 著しく不調
    elif ratio <= 0.92: return 0.94   # 不調
    else:               return 1.00   # 通常


def calc_prob_from_master(boats: list, venue: str, race_no: int = 0) -> list:
    course_master       = MASTER.get("course_master", {})
    venue_course_master = MASTER.get("venue_course_master", {})
    venue_stats         = MASTER.get("venue_stats", {}).get(venue, {})
    player_index        = MASTER.get("player_index", {})

    # 会場×R番号別コース1着率（優先3で使用）
    race_key = str(race_no) if race_no else None
    race_course_rates = (
        venue_stats.get("race_course_rates", {}).get(race_key, {})
        if race_key else {}
    )
    # R別データがなければ会場×コース全体
    venue_course_rates = venue_stats.get("course_rates", {})

    scores   = []
    dq_list  = []
    has_insufficient = False

    for bt in boats:
        name   = normalize_name(bt.get("name", ""))
        course = int(bt.get("boat", 1))
        c      = str(course)

        # ── ベース1着率の決定 ──────────────────────────
        base_rate = None
        dq        = None

        # 会場別・全国のデータをそれぞれ取得
        vc = venue_course_master.get(name, {}).get(venue, {}).get(c)
        cm = course_master.get(name, {}).get(c)

        venue_rate    = (vc.get("ts_win_rate") or vc.get("win_rate")) if vc and vc.get("reliable") else None
        national_rate = (cm.get("ts_win_rate") or cm.get("win_rate")) if cm and cm.get("reliable") else None
        venue_trust   = vc.get("trust", 0.0) if vc else 0.0

        if venue_rate is not None and national_rate is not None:
            # 両方ある → trustで加重ブレンド（会場実績の信頼度に応じて配分）
            base_rate = venue_rate * venue_trust + national_rate * (1.0 - venue_trust)
            dq        = "venue_local"
        elif venue_rate is not None:
            # 会場のみ
            base_rate = venue_rate
            dq        = "venue_local"
        elif national_rate is not None:
            # 全国のみ
            base_rate = national_rate
            dq        = "course_national"

        # ── 選手個人のコースデータが閾値未満かを独立判定 ──────
        has_personal_data = (
            (cm is not None and cm.get("reliable", False))
            or (vc is not None and vc.get("reliable", False))
        )

        # 優先3: 会場統計（R×コース → 会場×コース）
        if base_rate is None:
            rv = race_course_rates.get(c) or venue_course_rates.get(c)
            if rv is not None:
                base_rate = rv
                dq        = "venue_stat"

        # ⚠️ 閾値未満: 選手個人コース1着率を参考値として使用
        if base_rate is None:
            fallback_rate = None
            # 会場別（信頼度低）
            if vc:
                fallback_rate = vc.get("ts_win_rate") or vc.get("win_rate")
            # 全国（信頼度低）
            if fallback_rate is None and cm:
                fallback_rate = cm.get("ts_win_rate") or cm.get("win_rate")
            base_rate = fallback_rate if fallback_rate is not None else 0.001
            dq        = "insufficient"
            has_insufficient = True

        # 個人データ不足フラグ（venue_statで代替した場合も含む）
        if not has_personal_data:
            has_insufficient = True

        base_rate = max(base_rate or 0.001, 0.001)

        # ── ST補正 ────────────────────────────────────
        # コース別マスタのST順位を優先、なければ選手指数マスタ
        st_rank = None
        cm_data = course_master.get(name, {}).get(c)
        if cm_data:
            st_rank = cm_data.get("st_rank")
        if st_rank is None:
            pi = player_index.get(name, {})
            st_rank = pi.get("st_rank", {}).get(c)

        st_corr = st_rank_to_correction(st_rank)

        # ── フォーム補正 ──────────────────────────────
        pi           = player_index.get(name)
        overall_win  = pi.get("overall_win") if pi else None
        form_corr    = form_correction(pi, overall_win)

        score = base_rate * st_corr * form_corr
        scores.append(score)
        # 個人データ不足の場合は dq を insufficient に上書き（venue_stat代替も含む）
        if not has_personal_data and dq != "insufficient":
            dq = "insufficient"
        dq_list.append(dq)

    # ── 正規化 + 確率圧縮（荒れスコア連動）────────────
    # insufficient が1艇でも混在する場合、相対評価が不成立のためフラグを立てる
    #
    # キャリブレーション結果（0.8〜1.0帯で+10〜16pt過大評価）に対応するため
    # 荒れスコアに応じた上限を設けて圧縮し、残りを他艇に再配分する。
    arek_score = venue_stats.get("arek_score", 50.0)
    max_prob   = max_prob_by_arek(arek_score)

    total = sum(scores)
    if total <= 0:
        total = 1.0

    # base_score: 正規化前の生スコア（後段の展示補正・期待値計算で使用）
    # prob      : 相対正規化 + 上限クリップ後の確率（表示・展開計算用）
    for i, bt in enumerate(boats):
        bt["base_score"] = round(scores[i], 4)       # 絶対値スコア（正規化前）
        bt["score"]      = round(scores[i], 4)       # 後方互換のため残す
        bt["prob"]       = min(scores[i] / total, max_prob)
        bt["dq"]         = dq_list[i]

    # 圧縮した分を残りの艇に比例再配分して合計を1.0に戻す
    prob_sum = sum(bt["prob"] for bt in boats)
    if prob_sum > 0:
        for bt in boats:
            bt["prob"] = round(bt["prob"] / prob_sum, 4)

    if has_insufficient:
        # レベルフラグ：フロントエンドで警告表示に使用
        for bt in boats:
            bt["prob_warning"] = True

    return boats


# ── CSV 読み込み & レース構築 ──────────────────────────
def parse_csv(filepath: str) -> dict | None:
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
    date  = str(df.iloc[0].get("日付", "")).strip()

    venue_stats = MASTER.get("venue_stats", {}).get(venue, {})
    races = {}

    for _, row in df.iterrows():
        rno = int(row["レース"]) if str(row["レース"]).isdigit() else 0
        if rno == 0:
            continue
        if rno not in races:
            races[rno] = {
                "arek":  venue_stats.get("arek_by_race", {}).get(rno,
                         venue_stats.get("arek_score", 54.7)),
                "time":  str(row.get("締切時刻", "")),
                "boats": []
            }
        import re
        raw_name = str(row.get("選手名", "")).strip()
        reg_no   = str(row.get("登番", "")).strip()
        if raw_name:
            raw_name = re.sub(r'\d+$', '', raw_name).strip()
        # 登番（登録番号）を使って正式名を解決。省略名問題を解消する。
        if raw_name:
            name, name_dq = resolve_player_name(raw_name, reg_no)
        else:
            name, name_dq = f"艇{row.get('艇番', '?')}", "unresolved"

        races[rno]["boats"].append({
            "boat":       int(row.get("艇番", 0)),
            "name":       name,
            "name_dq":    name_dq,   # "id" | "prefix" | "unresolved"
            "grade":      str(row.get("級別", "B1")),
            # ⚠️ 以下はCSV由来の参考値。期初め・使い始めに偏りが出るため確率計算には使用しない
            "win_rate":   float(row.get("全国勝率", 0) or 0),
            "local_rate": float(row.get("当地勝率", 0) or 0),
            "motor2":     float(row.get("M2率", 0) or 0),
            "boat2":      float(row.get("B2率", 0) or 0),
            "results":    str(row.get("今節成績", "")),
            "hayami":     float(row.get("早見", 0) or 0) or None,
            "score":      0,
            "dq":         "fallback",
            "prob":       1/6,
        })

    for rno, rd in races.items():
        rd["boats"] = calc_prob_from_master(rd["boats"], venue, race_no=rno)
        rd["boats"].sort(key=lambda b: -b["prob"])

    return {
        "venue":    venue,
        "date":     date,
        "inn_data": {
            "inn_rate":    venue_stats.get("inn_rate", 0.5),
            "arek_score":  venue_stats.get("arek_score", 50),
            "course_rates": [0] + [
                venue_stats.get("course_rates", {}).get(str(c), 0)
                for c in range(1, 7)
            ],
            # venue_stats["inn_2place"] は build_master_json.py が
            # {"1": 0.0, "2": 0.30, "3": 0.27, ...} 形式で生成する。
            # フォールバックは全国平均的な値をオブジェクト形式で用意。
            "inn_2place": venue_stats.get("inn_2place", {
                "2": 0.30, "3": 0.27, "4": 0.20, "5": 0.13, "6": 0.07
            }),
        },
        "races":    {str(k): v for k, v in sorted(races.items())},
        "loaded_at": time.strftime("%H:%M:%S"),
        "__file":   os.path.basename(filepath),
    }


# ── CSV キャッシュ ─────────────────────────────────────
_csv_cache: dict[str, dict] = {}

def get_csv_files():
    CSV_DIR.mkdir(exist_ok=True)
    return sorted(glob.glob(str(CSV_DIR / "*.csv")), reverse=True)

def load_csv_file(filepath: str) -> dict | None:
    mtime = os.path.getmtime(filepath)
    key   = f"{filepath}:{mtime}"
    if key not in _csv_cache:
        data = parse_csv(filepath)
        if data:
            _csv_cache[key] = data
    return _csv_cache.get(key)


# ── API エンドポイント ──────────────────────────────────
@app.route("/api/files")
def api_files():
    files = [os.path.basename(f) for f in get_csv_files()]
    return jsonify({"files": files})

@app.route("/api/load")
def api_load():
    fname = request.args.get("file", "")
    path  = str(CSV_DIR / fname)
    data  = load_csv_file(path)
    if data:
        return jsonify({"ok": True, "data": data})
    return jsonify({"ok": False, "error": "parse failed"}), 400

@app.route("/api/data")
def api_data():
    files = get_csv_files()
    if not files:
        return jsonify({"error": "no CSV found"}), 404
    data = load_csv_file(files[0])
    if data:
        return jsonify(data)
    return jsonify({"error": "parse failed"}), 500

@app.route("/api/master_stats")
def api_master_stats():
    cm = MASTER.get("course_master", {})
    vs = MASTER.get("venue_stats", {})
    pi = MASTER.get("player_index", {})
    return jsonify({
        "player_count": len(cm),
        "venue_count":  len(vs),
        "index_count":  len(pi),
        "venues":       list(vs.keys()),
        "built_at":     MASTER.get("built_at", ""),
    })

@app.route("/api/master_data")
def api_master_data():
    """master_data.json の展開推定マスタ部分を返す"""
    return jsonify({
        "tenkai_remaining":    MASTER.get("tenkai_remaining", {}),
        "winner_course_order": MASTER.get("winner_course_order", {}),
        "venue_kimari":        MASTER.get("venue_kimari", {}),
        "venue_stats":         MASTER.get("venue_stats", {}),
        "course_master":       MASTER.get("course_master", {}),
    })

@app.route("/api/parse_csv", methods=["POST"])
def api_parse_csv():
    import tempfile
    text = request.get_data(as_text=True)
    if not text:
        return jsonify({"ok": False, "error": "empty body"}), 400
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv',
                                     encoding='utf-8', delete=False) as tmp:
        tmp.write(text)
        tmp_path = tmp.name
    try:
        data = parse_csv(tmp_path)
    finally:
        os.unlink(tmp_path)
    if data:
        return jsonify({"ok": True, "data": data})
    return jsonify({"ok": False, "error": "parse failed"}), 400

@app.route("/api/reload_master")
def api_reload_master():
    """Excelが更新されたときに master_data.json を再生成"""
    global MASTER
    if not XLSX_PATH.exists():
        return jsonify({"ok": False, "error": "xlsx not found"}), 404
    import subprocess, sys
    result = subprocess.run(
        [sys.executable, str(BASE_DIR / "build_master_json.py"),
         str(XLSX_PATH), str(MASTER_JSON)],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        MASTER = load_master()
        return jsonify({
            "ok": True,
            "player_count": len(MASTER.get("course_master", {})),
            "built_at": MASTER.get("built_at", ""),
        })
    return jsonify({"ok": False, "error": result.stderr}), 500


# ── 静的ファイル配信 ───────────────────────────────────
@app.route("/")
def index():
    return send_from_directory(str(BASE_DIR), "index.html")


# ── テン展示データ API ────────────────────────────────
TENJI_DIR = BASE_DIR / "tenji_data"

@app.route("/api/tenji")
def api_tenji():
    venue = request.args.get("venue", "")
    date  = request.args.get("date", "")
    race  = request.args.get("race", "")

    if not venue or not date or not race:
        return jsonify({"ok": False, "error": "venue/date/race が必要です"}), 400

    date_nodash = date.replace("-", "")
    fname = f"tenji_{venue}_{date_nodash}_R{int(race):02d}.json"
    fpath = TENJI_DIR / fname

    if not fpath.exists():
        return jsonify({"ok": False, "reason": "not_yet"})

    try:
        with open(fpath, encoding="utf-8") as f:
            rows = json.load(f)
        by_frame = {str(r["frame"]): r for r in rows}
        return jsonify({
            "ok": True,
            "data": by_frame,
            "fetched_at": rows[0].get("fetched_at", "") if rows else ""
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/tenji_all")
def api_tenji_all():
    venue = request.args.get("venue", "")
    date  = request.args.get("date", "")

    if not venue or not date:
        return jsonify({"ok": False, "error": "venue/date が必要です"}), 400

    date_nodash = date.replace("-", "")
    TENJI_DIR.mkdir(exist_ok=True)
    pattern = str(TENJI_DIR / f"tenji_{venue}_{date_nodash}_R*.json")

    races = {}
    for fpath in glob.glob(pattern):
        try:
            with open(fpath, encoding="utf-8") as f:
                rows = json.load(f)
            import re as _re
            m = _re.search(r"_R(\d{2})\.json$", fpath)
            if m:
                rno = str(int(m.group(1)))
                races[rno] = {str(r["frame"]): r for r in rows}
        except Exception:
            continue

    return jsonify({"ok": True, "races": races, "count": len(races)})


# ── 選手コメント API ──────────────────────────────────
COMMENT_DIR = BASE_DIR / "comment_data"

@app.route("/api/comments")
def api_comments():
    venue = request.args.get("venue", "").strip()
    date  = request.args.get("date",  "").strip()
    race  = request.args.get("race",  "").strip()

    if not venue or not date or not race:
        return jsonify({"ok": False, "error": "venue / date / race が必要です"}), 400

    try:
        race_no = int(race)
    except ValueError:
        return jsonify({"ok": False, "error": "race は整数で指定してください"}), 400

    date_nodash = date.replace("-", "").replace("/", "")
    fname = f"comment_{venue}_{date_nodash}_R{race_no:02d}.json"
    fpath = COMMENT_DIR / fname

    if not fpath.exists():
        return jsonify({"ok": False, "reason": "not_yet"})

    try:
        with open(fpath, encoding="utf-8") as f:
            data = json.load(f)
        fetched_at = data.get("__fetched_at", "")
        payload = {k: v for k, v in data.items() if k != "__fetched_at"}
        return jsonify({"ok": True, "data": payload, "fetched_at": fetched_at})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/comments_all")
def api_comments_all():
    venue = request.args.get("venue", "").strip()
    date  = request.args.get("date",  "").strip()

    if not venue or not date:
        return jsonify({"ok": False, "error": "venue / date が必要です"}), 400

    date_nodash = date.replace("-", "").replace("/", "")
    pattern = str(COMMENT_DIR / f"comment_{venue}_{date_nodash}_R*.json")

    import re as _re
    races = {}
    for fpath in glob.glob(pattern):
        try:
            with open(fpath, encoding="utf-8") as f:
                data = json.load(f)
            m = _re.search(r"_R(\d{2})\.json$", fpath)
            if m:
                rno = str(int(m.group(1)))
                races[rno] = {k: v for k, v in data.items() if k != "__fetched_at"}
        except Exception:
            continue

    return jsonify({"ok": True, "races": races, "count": len(races)})


@app.route("/api/flying")
def api_flying():
    """
    フライング情報を返す。
    クエリパラメータ:
        date  : YYYYMMDD (省略時は当日)
        venue : 会場名（省略時は全会場）
    レスポンス例:
        {
          "ok": true,
          "date": "20260430",
          "data": {
            "常滑": {
              "3": [{"race": 5, "waku": "1", "name": "山田太郎",
                     "flying": "F1", "f_total": 1}]
            }
          }
        }
    """
    from datetime import datetime as _dt
    date = request.args.get("date", "").strip().replace("-", "").replace("/", "")
    if not date:
        date = _dt.now().strftime("%Y%m%d")

    venue_filter = request.args.get("venue", "").strip()

    xlsx = FLYING_DIR / f"flying_{date}.xlsx"
    if not xlsx.exists():
        return jsonify({"ok": False, "error": f"flying_{date}.xlsx が見つかりません", "date": date}), 404

    try:
        df = pd.read_excel(str(xlsx), sheet_name="フライング一覧")
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

    # 列名を正規化（余分なスペースを除去）
    df.columns = [str(c).strip() for c in df.columns]

    # 必須列の確認
    required = {"会場", "レース", "枠", "選手名", "フライング", "合計F数"}
    missing = required - set(df.columns)
    if missing:
        return jsonify({"ok": False, "error": f"列不足: {missing}"}), 500

    # 会場フィルタ
    if venue_filter:
        df = df[df["会場"] == venue_filter]

    # 構造を  {会場: {レース番号str: [record, ...]}} にまとめる
    result = {}
    for _, row in df.iterrows():
        venue  = str(row["会場"]).strip()
        race   = int(row["レース"]) if pd.notna(row["レース"]) else 0
        waku   = str(row["枠"]).strip() if pd.notna(row["枠"]) else ""
        name   = str(row["選手名"]).strip() if pd.notna(row["選手名"]) else ""
        flying = str(row["フライング"]).strip() if pd.notna(row["フライング"]) else ""
        f_total = int(row["合計F数"]) if pd.notna(row["合計F数"]) else 1

        result.setdefault(venue, {}).setdefault(str(race), []).append({
            "race":    race,
            "waku":    waku,
            "name":    name,
            "flying":  flying,
            "f_total": f_total,
        })

    return jsonify({"ok": True, "date": date, "data": result})


if __name__ == "__main__":
    CSV_DIR.mkdir(exist_ok=True)
    print(f"サーバー起動 http://localhost:5000")
    print(f"CSVフォルダ: {CSV_DIR}")
    print(f"Excelマスタ: {XLSX_PATH}")
    print(f"マスタ選手数: {len(MASTER.get('course_master', {}))}")
    print(f"player_id_map: {len(MASTER.get('player_id_map', {}))} 件")
    print(f"マスタ生成日時: {MASTER.get('built_at', '未生成')}")
    app.run(host="0.0.0.0", port=5000, debug=False)
