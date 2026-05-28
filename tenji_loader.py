"""
tenji_loader.py  —  fetch_tenji.py が保存したデータを既存システムに橋渡し
=============================================================================
使い方（load_race.py 内から）:

    from tenji_loader import load_tenji_data

    # 平和島 2026-04-25 の1Rデータを取得
    tenji = load_tenji_data("heiwajima", "2026-04-25", race=1)
    # → {1: {"tenji": 6.84, "lap1": 37.29, ...}, 2: {...}, ...}

    # DataFrameとして取得
    df = load_tenji_df("heiwajima", "2026-04-25")
"""

import json
from pathlib import Path
from datetime import datetime

# デフォルトのデータ保存先（fetch_tenji.py の --out と合わせる）
DEFAULT_DATA_DIR = Path("./tenji_data")


def load_tenji_data(venue: str, date: str, race: int,
                    data_dir: Path = DEFAULT_DATA_DIR) -> dict:
    """
    指定したレースのテン展示データをdict形式で返す。
    キー: 枠番(1〜6)
    値:  {"frame", "racer", "grade", "lap1", "mawari", "chokusen", "tenji", "fetched_at"}

    データが存在しない場合は空dictを返す。
    """
    # JSON（レース別）を優先して読む
    json_path = data_dir / f"tenji_{venue}_{date.replace('-','')}_R{race:02d}.json"
    if json_path.exists():
        with open(json_path, encoding="utf-8") as f:
            rows = json.load(f)
        return {r["frame"]: r for r in rows}

    # CSV（日別）からフィルタ
    csv_path = data_dir / f"tenji_{venue}_{date.replace('-','')}.csv"
    if csv_path.exists():
        import pandas as pd
        df = pd.read_csv(csv_path)
        df = df[(df["date"] == date) & (df["race"] == race)]
        return {int(r["frame"]): r.to_dict() for _, r in df.iterrows()}

    return {}


def load_tenji_df(venue: str, date: str,
                  data_dir: Path = DEFAULT_DATA_DIR):
    """
    指定日の全レース展示データをDataFrameで返す。
    """
    import pandas as pd
    csv_path = data_dir / f"tenji_{venue}_{date.replace('-','')}.csv"
    if csv_path.exists():
        return pd.read_csv(csv_path)
    # JSONから再構築
    rows = []
    for race in range(1, 13):
        d = load_tenji_data(venue, date, race, data_dir)
        rows.extend(d.values())
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def tenji_freshness(venue: str, date: str, race: int,
                    data_dir: Path = DEFAULT_DATA_DIR,
                    max_age_minutes: int = 10) -> bool:
    """
    テン展示データが max_age_minutes 以内に取得済みかを確認。
    True = フレッシュ（再取得不要）/ False = 古い or 存在しない
    """
    d = load_tenji_data(venue, date, race, data_dir)
    if not d:
        return False
    # 最初の艇のfetched_atを確認
    sample = next(iter(d.values()))
    fetched_str = sample.get("fetched_at", "")
    if not fetched_str:
        return False
    try:
        fetched_at = datetime.strptime(fetched_str, "%Y-%m-%d %H:%M:%S")
        age = (datetime.now() - fetched_at).total_seconds() / 60
        return age <= max_age_minutes
    except Exception:
        return False


def get_or_fetch_tenji(venue: str, date: str, race: int,
                       data_dir: Path = DEFAULT_DATA_DIR,
                       max_age_minutes: int = 10) -> dict:
    """
    キャッシュがフレッシュなら返し、古ければ自動で再取得する。
    load_race.py の中から呼び出す想定。
    """
    if tenji_freshness(venue, date, race, data_dir, max_age_minutes):
        return load_tenji_data(venue, date, race, data_dir)

    # 自動取得
    print(f"[tenji_loader] テン展示を自動取得: {venue} {date} {race}R")
    try:
        from fetch_tenji import fetch_html, parse_tenji, save_csv, save_json
        from fetch_tenji import build_url
        url = build_url(venue, date, race)
        html = fetch_html(url)
        rows = parse_tenji(html, venue, date, race)
        if rows:
            save_csv(rows, data_dir, venue, date, race)
            save_json(rows, data_dir, venue, date, race)
            return {r["frame"]: r for r in rows}
    except Exception as e:
        print(f"[tenji_loader] 取得エラー: {e}")
    return {}
