"""
auto_push.py への追記パッチ
=============================
以下の内容を auto_push.py に追記・編集してください。

■ 変更点は3か所です:
  1. インポート追記（ファイル冒頭）
  2. inject_race_index_to_html() 関数を追加
  3. main() の inject_all_data_to_html() 呼び出しの直後に呼び出しを追加

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【変更 1】インポート（既存の import の末尾付近に追加）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  # ── fetch_race_index.py のパス ──────────────────────────
  FETCH_RACE_INDEX_PY = SCRIPTS_DIR / "fetch_race_index.py"
  RACE_INDEX_JSON     = SCRIPTS_DIR / "race_index.json"

（SCRIPTS_DIR の定義より後に配置してください）

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【変更 2】inject_race_index_to_html() 関数を追加
         （inject_history_to_html() 関数の直後に貼り付け）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

PATCH_FUNCTION = r'''
def fetch_and_inject_race_index():
    """
    公式サイトから本日の開催グレード・タイトル情報を取得し、
    index.html の RACE_INDEX_DATA を書き換える。

    fetch_race_index.py を別プロセスで実行して race_index.json を生成し、
    その内容を HTML に埋め込む（既存の inject_* と同じパターン）。
    """
    import sys as _sys

    # ── fetch_race_index.py で race_index.json を生成 ──
    if FETCH_RACE_INDEX_PY.exists():
        log("  公式サイトから開催グレード情報を取得中...")
        result = subprocess.run(
            [_sys.executable, str(FETCH_RACE_INDEX_PY),
             "--out", str(SCRIPTS_DIR)],
            capture_output=True, text=True, encoding="utf-8", timeout=30
        )
        if result.returncode != 0:
            log(f"  ⚠ race_index 取得失敗: {result.stderr.strip()[:200]}")
        else:
            log(f"  ✓ race_index.json 生成完了")
    else:
        log(f"  ⚠ {FETCH_RACE_INDEX_PY.name} が見つかりません → スキップ")

    # ── race_index.json を読んで HTML に埋め込む ──────────
    if not RACE_INDEX_JSON.exists():
        log("  ⚠ race_index.json が見つかりません → RACE_INDEX_DATA埋め込みスキップ")
        return False

    try:
        with open(RACE_INDEX_JSON, encoding="utf-8") as f:
            race_index = json.load(f)
    except Exception as e:
        log(f"  ⚠ race_index.json 読込エラー: {e}")
        return False

    html_text = INDEX_HTML.read_text(encoding="utf-8")
    race_index_json = json.dumps(race_index, ensure_ascii=False, separators=(",", ":"))
    new_block = f"let RACE_INDEX_DATA = {race_index_json};\n"

    pattern = r'(?:let|const) RACE_INDEX_DATA = [\s\S]*?;[^\n]*\n'
    if re.search(pattern, html_text):
        html_text = re.sub(pattern, new_block, html_text)
        INDEX_HTML.write_text(html_text, encoding="utf-8")
        log(f"  ✓ RACE_INDEX_DATA埋め込み完了: {len(race_index.get('venues', {}))}会場")
        return True
    else:
        log("  ⚠ RACE_INDEX_DATAの埋め込み位置が見つかりません")
        return False
'''

PATCH_CALL = """
# ── main() の inject_all_data_to_html() の直後（起動時push の中）──
# 以下2行を追加してください:

        inject_all_data_to_html()
        inject_master_ext_to_html()
        inject_tenji_to_html()
        inject_comment_to_html()
        inject_flying_to_html()
        inject_result_to_html()
        inject_history_to_html()
        fetch_and_inject_race_index()   # ← この行を追加

# ── main() のループ内（changed: がある場合の処理）──
# inject_history_to_html() の直後にも追加:

                inject_history_to_html()
                fetch_and_inject_race_index()   # ← この行を追加（CSVが更新されたタイミングで再取得）
"""

if __name__ == "__main__":
    print(PATCH_FUNCTION)
    print(PATCH_CALL)
