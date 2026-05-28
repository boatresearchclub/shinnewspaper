# -*- coding: utf-8 -*-
"""
make_grade_master.py  (改良版)
====================
ボートレース公式サイトのグレードスケジュールページから
コピペしたテキストを読み込み、grade_master.csv を生成する。

【使い方】
  1. https://www.boatrace.jp/owpc/pc/race/gradesch?year=2025&hcd=01 を開く
  2. ページ全体をCtrl+Aで選択 → Ctrl+Cでコピー
  3. このスクリプトと同じフォルダに paste_sg.txt として貼り付けて保存
  4. G1タブ→paste_g1.txt、G2タブ→paste_g2.txt、G3タブ→paste_g3.txt、女子→paste_ladies.txt
  5. python make_grade_master.py
  6. grade_master.csv が生成される → data/raw/ に置く

【生成されるCSV】
  会場名,開始日,終了日,グレード,タイトル
  桐生,2025-01-01,2025-01-06,G3,桐生周年記念
  ...
"""

import re, csv, os
from datetime import datetime

# 入力ファイルとグレードの対応
INPUT_FILES = [
    ("paste_sg.txt",      "SG"),
    ("paste_g1.txt",      "G1"),
    ("paste_g2.txt",      "G2"),
    ("paste_g3.txt",      "G3"),
    ("paste_ladies.txt",  "女子戦"),
    ("paste_rookie.txt",  "ルーキーS"),
    ("paste_masters.txt", "マスターズL"),
]

OUTPUT_CSV = "grade_master.csv"
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data_csv")

# 全24会場
VENUE_NAMES = [
    "桐生", "戸田", "江戸川", "平和島", "多摩川", "浜名湖", "蒲郡", "常滑",
    "津", "三国", "びわこ", "住之江", "尼崎", "鳴門", "丸亀", "児島",
    "宮島", "徳山", "下関", "若松", "芦屋", "福岡", "唐津", "大村",
]

VENUE_MAP = {
    # 短縮表記
    "桐生": "桐生", "戸田": "戸田", "江戸川": "江戸川", "平和島": "平和島",
    "多摩川": "多摩川", "浜名湖": "浜名湖", "蒲郡": "蒲郡", "常滑": "常滑",
    "津": "津", "三国": "三国", "びわこ": "びわこ", "住之江": "住之江",
    "尼崎": "尼崎", "鳴門": "鳴門", "丸亀": "丸亀", "児島": "児島",
    "宮島": "宮島", "徳山": "徳山", "下関": "下関", "若松": "若松",
    "芦屋": "芦屋", "福岡": "福岡", "唐津": "唐津", "大村": "大村",
    # ボートレース〇〇 表記
    "ボートレース桐生": "桐生", "ボートレース戸田": "戸田",
    "ボートレース江戸川": "江戸川", "ボートレース平和島": "平和島",
    "ボートレース多摩川": "多摩川", "ボートレース浜名湖": "浜名湖",
    "ボートレース蒲郡": "蒲郡", "ボートレース常滑": "常滑",
    "ボートレース津": "津", "ボートレース三国": "三国",
    "ボートレースびわこ": "びわこ", "ボートレース住之江": "住之江",
    "ボートレース尼崎": "尼崎", "ボートレース鳴門": "鳴門",
    "ボートレース丸亀": "丸亀", "ボートレース児島": "児島",
    "ボートレース宮島": "宮島", "ボートレース徳山": "徳山",
    "ボートレース下関": "下関", "ボートレース若松": "若松",
    "ボートレース芦屋": "芦屋", "ボートレース福岡": "福岡",
    "ボートレース唐津": "唐津", "ボートレース大村": "大村",
}

# 長い表記を先にマッチさせるため降順ソート
VENUE_MAP_SORTED = sorted(VENUE_MAP.items(), key=lambda x: -len(x[0]))


def normalize_for_search(text):
    """検索用に全角スペース・半角スペースを除去して正規化"""
    return re.sub(r'[\s\u3000]+', '', text)


def find_venue_in_text(text):
    """テキスト中から会場名を検索。スペース除去後でもマッチ。見つかったら正規化名を返す"""
    # スペースなし版でも検索できるよう両方試す
    text_nospace = normalize_for_search(text)
    for k, v in VENUE_MAP_SORTED:
        k_nospace = normalize_for_search(k)
        if k_nospace in text_nospace:
            return v
    return ""


def parse_date(raw, year):
    """'MM/DD' → 'YYYY-MM-DD'"""
    try:
        parts = raw.split('/')
        m, d = int(parts[0]), int(parts[1])
        return f"{year}-{m:02d}-{d:02d}"
    except Exception:
        return None


def clean_title(text):
    """タイトルから不要な文字列を除去"""
    text = re.sub(r'レース結果.*$', '', text)
    text = re.sub(r'優勝[者者].*$', '', text)
    text = re.sub(r'https?://\S+', '', text)
    # ナイター記号（C、🌙など）除去
    text = re.sub(r'[Ｃc🌙☾\u25D4]', '', text)
    # G1/G2/G3/SG バッジ文字が混入した場合も除去
    text = re.sub(r'\b(SG|G[123])\b', '', text)
    # 人名っぽいもの（姓＋名のスペース区切り2〜4文字×2）を除去
    text = re.sub(r'[\u4e00-\u9fff]{1,4}[\s　][\u4e00-\u9fff]{1,4}$', '', text)
    text = re.sub(r'[\s　]+', ' ', text).strip()
    return text


def parse_text(text, grade, year):
    """
    コピペテキストをパースしてレコードリストを返す。

    対応する主なフォーマット：
      ① 同一行: "01/23-01/26  桐生  タイトル"
      ② 複数行ブロック: 日付行の前後N行に会場名がある
      ③ タブ区切り: "01/23\t01/26\t桐生\tタイトル"
    """
    records = []

    # 日付範囲パターン（例: 01/23-01/26 / 01/23～01/26）
    DATE_RANGE_RE = re.compile(r'(\d{1,2}/\d{1,2})\s*[-～~]\s*(\d{1,2}/\d{1,2})')

    lines = text.split('\n')
    total = len(lines)

    for i, line in enumerate(lines):
        line_stripped = line.strip()
        if not line_stripped:
            continue

        m = DATE_RANGE_RE.search(line_stripped)
        if not m:
            continue

        start_raw = m.group(1)
        end_raw   = m.group(2)

        # 年またぎ判定
        start_m = int(start_raw.split('/')[0])
        end_m   = int(end_raw.split('/')[0])
        end_year = year + 1 if (start_m == 12 and end_m == 1) else year

        start_date = parse_date(start_raw, year)
        end_date   = parse_date(end_raw,   end_year)
        if not start_date or not end_date:
            continue

        # --- 会場名・タイトルの検索範囲 ---
        # 同一行（日付より後）＋前後2行をまとめて検索
        context_lines = []
        after_on_same_line = line_stripped[m.end():].strip()
        if after_on_same_line:
            context_lines.append(after_on_same_line)
        for delta in range(-2, 3):   # -2〜+2行
            idx = i + delta
            if 0 <= idx < total and idx != i:
                context_lines.append(lines[idx].strip())

        # 会場名を探す（各contextをすべて結合して検索）
        venue = ""
        title = ""
        for ctx in context_lines:
            found = find_venue_in_text(ctx)
            if found:
                venue = found
                # 会場名をctxから除去してタイトル候補に
                for k, v in VENUE_MAP_SORTED:
                    k_nospace = normalize_for_search(k)
                    ctx_nospace = normalize_for_search(ctx)
                    if k_nospace in ctx_nospace:
                        # 元のctxからスペース有り・無し両方のパターンで除去
                        title_candidate = re.sub(re.escape(k), '', ctx)
                        title_candidate = re.sub(r'\s*'.join(list(re.escape(k))), '', title_candidate)
                        title_candidate = DATE_RANGE_RE.sub("", title_candidate).strip()
                        if title_candidate:
                            title = clean_title(title_candidate)
                        break
                break

        # 会場名が見つからなかった場合のフォールバック
        # → 日付と同じ行のafterをそのままtitleにする
        if not venue and after_on_same_line:
            # afterの先頭が会場名かもしれない（部分一致で再チェック）
            for name in VENUE_NAMES:
                if after_on_same_line.startswith(name):
                    venue = name
                    title = clean_title(after_on_same_line[len(name):].strip())
                    break

        # タイトルの最終クリーニング
        title = clean_title(title)

        records.append({
            "会場名":  venue,
            "開始日":  start_date,
            "終了日":  end_date,
            "グレード": grade,
            "タイトル": title,
        })

        status = "✓" if venue else "⚠ 会場不明"
        print(f"  [{grade}] {start_date}〜{end_date}  {venue or '???'}  {title}  {status}")

    return records


def main():
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    all_records = []

    for filename, grade in INPUT_FILES:
        filepath = os.path.join(BASE_DIR, filename)
        if not os.path.exists(filepath):
            print(f"  [スキップ] {filename} が見つかりません")
            continue

        with open(filepath, encoding='utf-8', errors='replace') as f:
            text = f.read()

        # 年の抽出
        year_match = re.search(r'(20\d{2})年', text)
        year = int(year_match.group(1)) if year_match else datetime.now().year
        print(f"\n[{grade}] {filename}  (年={year})")

        records = parse_text(text, grade, year)
        all_records.extend(records)
        no_venue = sum(1 for r in records if not r["会場名"])
        print(f"  → {len(records)}件  (会場不明: {no_venue}件)")

    if not all_records:
        print("\n[ERROR] 有効なデータが見つかりませんでした。")
        print("  paste_sg.txt / paste_g1.txt などのファイルを作成してください。")
        return

    # 開始日でソート
    all_records.sort(key=lambda x: x["開始日"])

    # CSV書き出し
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, OUTPUT_CSV)
    with open(out_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=["会場名","開始日","終了日","グレード","タイトル"])
        writer.writeheader()
        writer.writerows(all_records)

    no_venue_total = sum(1 for r in all_records if not r["会場名"])
    print(f"\n✅ 完了: {out_path}  ({len(all_records)}件)")
    if no_venue_total:
        print(f"  ⚠ 会場名未取得: {no_venue_total}件 → paste_*.txt の形式を確認してください")
    else:
        print(f"  → 全件で会場名を取得できました")


if __name__ == "__main__":
    main()
