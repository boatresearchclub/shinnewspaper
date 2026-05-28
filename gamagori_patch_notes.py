"""
scrape_comments.py への蒲郡パッチ適用手順
==========================================

① gamagori_fetcher.py を scrape_comments.py と同じフォルダに置く

② scrape_comments.py の _fetch_gamagori_playwright 関数を
  下記の新実装に置き換える

③ scrape_one_race の蒲郡分岐コメントを更新する
  （"Playwright専用ルート" のコメントを削除）

==========================================================
【置き換え対象】 scrape_comments.py の L383〜L407
==========================================================
"""

# ── ここから scrape_comments.py に貼り付ける ──────────────

# ファイル冒頭の import 群に追加:
# from gamagori_fetcher import gamagori_scrape_one_race as _gamagori_fetch


# ── _fetch_gamagori_playwright を以下で完全置換 ────────────

def _fetch_gamagori_playwright(race_no: int, date_str: str) -> "dict | None":
    """
    蒲郡コメント取得（JS直接パース版・Playwright不要）。

    【確定構造（2026-05-25 解析済み）】
      ① comment/comment{YYYYMMDD}07{RR}.htm
           → 正規表現で枠番→登番マッピングを取得
             funcBeforeComment("XXXX") ... getElementById("comment{waku}_1")
      ② js/comment{YYYYMMDD}07.js（Shift-JIS）
           → funcToDayComment(登番) → 前検コメント文字列

    gamagori_fetcher.py に処理を委譲するだけ。
    """
    from gamagori_fetcher import scrape_gamagori
    return scrape_gamagori(race_no=race_no, date_str=date_str, verbose=True)


# ── scrape_one_race の蒲郡ブロック（L508〜L514）を以下で置換 ──

#   if venue_slug == "gamagori":
#       result = _fetch_gamagori_playwright(race_no, date_str)
#       if not result:
#           return None
#       # __fetched_at は scrape_gamagori 内で付与済み
#       return result

# ↑ コメントアウト不要。そのままで動く（__fetched_at の二重付与に注意）

# ── __fetched_at の二重付与を防ぐため、以下のように修正する ──
# scrape_one_race 内の gamagori ブロック:

# if venue_slug == "gamagori":
#     result = _fetch_gamagori_playwright(race_no, date_str)
#     if not result:
#         return None
#     if "__fetched_at" not in result:          # ← この行を追加
#         result["__fetched_at"] = datetime.now().strftime("%H:%M:%S")
#     return result

PATCH_SUMMARY = """
変更点まとめ
============
1. _fetch_gamagori_playwright
   → gamagori_fetcher.scrape_gamagori() を呼ぶだけのシンプルなラッパーに変更
   → Playwright・BeautifulSoup・HTMLパース完全不要

2. scrape_one_race の gamagori ブロック
   → __fetched_at の二重付与を防ぐ1行追加のみ

3. 新ファイル gamagori_fetcher.py を同フォルダに配置
   → scrape_gamagori()      : 1レース取得
   → scrape_gamagori_all()  : 全12R一括取得（JS は1回だけ取得）
   → python gamagori_fetcher.py --race 3 で単体テスト可能
"""
