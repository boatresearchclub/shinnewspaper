"""
test_fetch_race_index.py  —  fetch_race_index.py の動作確認
=============================================================
使い方:
  python test_fetch_race_index.py

公式サイトから取得した結果を表示します。
"""
import json
import sys
from pathlib import Path

# fetch_race_index.py が同じフォルダにある前提
script_dir = Path(__file__).parent
sys.path.insert(0, str(script_dir))

try:
    from fetch_race_index import fetch
except ImportError as e:
    print(f"インポートエラー: {e}")
    print("fetch_race_index.py と同じフォルダに置いてください")
    sys.exit(1)

print("=" * 55)
print("  ボートレース公式 開催グレード情報 取得テスト")
print("=" * 55)

data = fetch()

if not data:
    print("✕ 取得失敗")
    sys.exit(1)

print(f"  日付      : {data['date']}")
print(f"  取得時刻  : {data['fetched_at']}")
print(f"  開催会場数: {len(data['venues'])}会場")
print()
print(f"  {'会場':4s}  {'グレード':6s}  {'タイトル':25s}  {'期間':12s}  {'日次'}")
print("  " + "-" * 65)
for venue, info in data["venues"].items():
    title_short = info["title"][:23] + ".." if len(info["title"]) > 25 else info["title"]
    print(f"  {venue:4s}  {info['grade']:6s}  {title_short:25s}  {info['period']:12s}  {info['day']}")

print()
print("  JSON プレビュー:")
print(json.dumps(data, ensure_ascii=False, indent=2)[:800])
print("  ...")
