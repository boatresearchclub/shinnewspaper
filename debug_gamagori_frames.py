# debug_gamagori_frames.py
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_context(locale="ja-JP").new_page()
    page.goto(
        "https://www.gamagori-kyotei.com/asp/gamagori/kyogi/kyogihtml/index.htm?race=1",
        wait_until="networkidle",
        timeout=30000,
    )
    print(f"\nフレーム数: {len(page.frames)}")
    for i, frame in enumerate(page.frames):
        print(f"  [{i:02d}] {frame.url}")
        # td.commentがあるか即確認（タイムアウトなし）
        try:
            count = frame.eval_on_selector_all("td.comment", "els => els.length")
            if count > 0:
                print(f"       ★ td.comment が {count}個 ← ここ！")
        except Exception as e:
            print(f"       (eval失敗: {e})")
    browser.close()