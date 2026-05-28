import requests
from pathlib import Path
from datetime import datetime

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}

hd = datetime.now().strftime("%Y%m%d")

resp = requests.get(
    "https://www.boatrace.jp/owpc/pc/race/index",
    headers=HEADERS,
    params={"hd": hd},
    timeout=20
)

Path("debug_index.html").write_text(resp.text, encoding="utf-8")

print(resp.status_code, "保存完了")

path = Path("debug_index.html")
path.write_text(resp.text, encoding="utf-8")

print("保存場所:", path.resolve())