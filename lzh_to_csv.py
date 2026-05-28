# ============================================================
#  ボートレース番組表  LZH → CSV 変換スクリプト
#
#  【特徴】
#  - 1つのTXTに全場・全レースが入っている形式に対応
#  - 会場ごとに個別CSVを出力
#  - LZHは7-Zipで自動解凍
#  - 各レースの締め切り時刻をCSVに出力
#  - 複数LZHを一括処理し、LZHファイル名から日付を取得して正しく出力
#
#  【使い方】
#  1. このスクリプトを .lzh ファイルと同じフォルダに置く
#  2. コマンドプロンプトで: python lzh_to_csv.py
#  3. csv_output フォルダに会場ごと・日付ごとのCSVが出力される
# ============================================================

import subprocess, os, csv, re, glob, sys, shutil

# ============================================================
# ★ 設定（必要に応じて変更してください）
# ============================================================

# 7-Zipのパス
SEVENZIP_PATH = r"C:\Program Files\7-Zip\7z.exe"

# スクリプトと同じフォルダ
INPUT_FOLDER  = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FOLDER = os.path.join(INPUT_FOLDER, "csv_output")
TEMP_FOLDER   = os.path.join(INPUT_FOLDER, "_temp_extract")

# ============================================================
# 会場コード対応表
# ============================================================
VENUE_CODES = {
    "01": "桐生",   "02": "戸田",   "03": "江戸川", "04": "平和島",
    "05": "多摩川", "06": "浜名湖", "07": "蒲郡",   "08": "常滑",
    "09": "津",     "10": "三国",   "11": "びわこ", "12": "住之江",
    "13": "尼崎",   "14": "鳴門",   "15": "丸亀",   "16": "児島",
    "17": "宮島",   "18": "徳山",   "19": "下関",   "20": "若松",
    "21": "芦屋",   "22": "福岡",   "23": "唐津",   "24": "大村",
}

# ============================================================
# フィールド定義（バイト位置・長さ）
# ============================================================
FIELDS = [
    ("艇番",     0,  1),
    ("登番",     2,  4),
    ("選手名",   6, 10),  # 全角5文字（10バイト）まで対応
    ("年齢",    14,  2),
    ("支部",    16,  4),
    ("体重",    20,  2),
    ("級別",    22,  2),
    ("全国勝率", 25,  4),
    ("全国2率",  30,  5),
    ("当地勝率", 36,  4),
    ("当地2率",  41,  4),
    ("M番",     47,  2),
    ("M2率",    50,  5),
    ("B番",     56,  2),
    ("B2率",    59,  5),
    ("今節成績", 65,  6),
    ("早見",    77,  2),
]

# ============================================================
# ユーティリティ
# ============================================================
def zen2han(s):
    """全角数字・記号・コロンを半角に変換"""
    for z, h in zip("０１２３４５６７８９ＲＡＢ：", "0123456789RAB:"):
        s = s.replace(z, h)
    return s

def decode_line(raw):
    """バイト列をcp932でデコード（失敗時は置換）"""
    return raw.decode("cp932", errors="replace")

def extract_field(raw, start, length):
    """バイト列の指定位置からフィールドを取り出す"""
    chunk = raw[start:start + length]
    try:
        return chunk.decode("cp932").strip()
    except:
        return chunk.decode("cp932", errors="replace").strip()

# ============================================================
# ステップ1: 7-ZipでLZH解凍
# ============================================================
def extract_lzh(lzh_path, out_dir):
    if not os.path.exists(SEVENZIP_PATH):
        print(f"\n❌ 7-Zipが見つかりません: {SEVENZIP_PATH}")
        print("   https://7-zip.org/ からインストールするか")
        print("   スクリプト上部の SEVENZIP_PATH を修正してください")
        sys.exit(1)

    os.makedirs(out_dir, exist_ok=True)
    cmd = [SEVENZIP_PATH, "e", lzh_path, f"-o{out_dir}", "-y"]
    result = subprocess.run(cmd, capture_output=True)

    if result.returncode != 0:
        print(f"❌ 解凍失敗: {os.path.basename(lzh_path)}")
        return None

    txt_files = glob.glob(os.path.join(out_dir, "*.TXT")) + \
                glob.glob(os.path.join(out_dir, "*.txt"))
    if not txt_files:
        print(f"⚠️  TXTファイルが見つかりません")
        return None

    print(f"   解凍: {os.path.basename(txt_files[0])}")
    return txt_files[0]

# ============================================================
# ステップ2: TXTを会場ブロックに分割
# ============================================================
def split_by_venue(raw_lines):
    """
    XX BBGN ～ XX BEND で囲まれたブロックを会場ごとに分割して返す
    戻り値: [(venue_code, venue_name, [行リスト]), ...]
    """
    blocks = []
    current_code = None
    block_lines = []

    for raw in raw_lines:
        s = decode_line(raw).strip()

        m_start = re.match(r"^(\d{2})BBGN$", s)
        m_end   = re.match(r"^(\d{2})BEND$", s)

        if m_start:
            current_code = m_start.group(1)
            block_lines = []
        elif m_end and current_code:
            name = VENUE_CODES.get(current_code, f"会場{current_code}")
            blocks.append((current_code, name, block_lines))
            current_code = None
            block_lines = []
        elif current_code is not None:
            block_lines.append(raw.rstrip(b"\r"))

    return blocks

# ============================================================
# ステップ3: 各ブロックの選手データを解析
# ============================================================
def is_player_line(raw):
    """選手データ行を判定（先頭: 艇番1〜6 + スペース + 4桁登番）"""
    try:
        s = raw[:6].decode("cp932", errors="replace")
        return bool(re.match(r"^[1-6] \d{4}", s))
    except:
        return False

def parse_race_header(raw):
    """
    レースヘッダー行を解析して (レース番号, 締め切り時刻) を返す。
    例: 　１Ｒ  一般　　 進入固定 … 電話投票締切予定１５：２０
    レース番号が見つからなければ (None, None) を返す。
    """
    try:
        s = zen2han(decode_line(raw))
    except:
        return None, None

    m_race = re.search(r"(\d+)R", s)
    if not m_race:
        return None, None
    race_no = int(m_race.group(1))

    deadline = None
    m_time = re.search(r"締切[^\d]*(\d{1,2}:\d{2})", s)
    if m_time:
        deadline = m_time.group(1)

    return race_no, deadline

def parse_date(block_lines):
    """ブロック内から開催日付を取得（LZHファイル名が使えない場合のフォールバック）"""
    for raw in block_lines[:15]:
        s = zen2han(decode_line(raw))
        m = re.search(r"(\d{4})年\D*?(\d{1,2})月\D*?(\d{1,2})日", s)
        if m:
            y, mo, d = m.groups()
            return f"{y}/{int(mo):02d}/{int(d):02d}"
    return "不明"

def date_from_lzh_name(lzh_path):
    """
    LZHファイル名 bYYMMDD.lzh から日付文字列を返す（最優先）。
    例: b260117.lzh → "2026/01/17"
    取得できない場合は None。

    ★ TXT内の日付ヘッダーは期初(1/1)のままのことがあり信頼できないため、
      LZHファイル名を正とする。
    """
    if not lzh_path:
        return None
    m = re.search(r"[Bb](\d{2})(\d{2})(\d{2})", os.path.basename(lzh_path))
    if m:
        yy, mo, d = m.groups()
        return f"20{yy}/{mo}/{d}"
    return None

def parse_block(venue_code, venue_name, block_lines):
    """1会場分のブロックを解析して選手レコードのリストを返す"""
    date = parse_date(block_lines)
    records = []
    current_race     = None
    current_deadline = None

    for raw in block_lines:
        race_no, deadline = parse_race_header(raw)
        if race_no is not None:
            current_race     = race_no
            current_deadline = deadline
            continue

        if is_player_line(raw):
            row = {
                "会場コード": venue_code,
                "会場":       venue_name,
                "日付":       date,
                "レース":     current_race,
                "締切時刻":   current_deadline,
            }
            for fname, start, length in FIELDS:
                val = extract_field(raw, start, length)
                if fname not in ("選手名", "支部", "今節成績"):
                    val = zen2han(val)
                row[fname] = val

            name = row.get("選手名", "")
            age  = row.get("年齢", "")
            m_fix = re.match(r"^(.+?)\s*(\d{2})$", name)
            if m_fix:
                row["選手名"] = m_fix.group(1).strip()
                if not age.isdigit():
                    row["年齢"] = m_fix.group(2)

            records.append(row)

    return records

# ============================================================
# ステップ4: CSVに保存
# ============================================================
def save_csv(records, venue_name, date, out_folder):
    os.makedirs(out_folder, exist_ok=True)
    safe_date = date.replace("/", "-")
    filename  = f"{venue_name}_{safe_date}.csv"
    filepath  = os.path.join(out_folder, filename)

    if not records:
        return None

    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(records[0].keys()))
        writer.writeheader()
        writer.writerows(records)

    return filepath

# ============================================================
# メイン処理
# ============================================================
def process_txt(txt_path, lzh_path=None):
    """
    TXTファイルを解析して全会場のCSVを出力する。

    lzh_path が指定された場合、そのファイル名（bYYMMDD.lzh）から日付を取得し
    TXT内の日付ヘッダーより優先して使用する。
    → 複数LZHを一括処理しても日付が正しく振り分けられる。
    """
    with open(txt_path, "rb") as f:
        raw_lines = f.read().split(b"\n")

    blocks = split_by_venue(raw_lines)

    if not blocks:
        print("   ⚠️  会場ブロックが見つかりませんでした")
        return 0

    print(f"   {len(blocks)}会場分のデータを検出\n")
    count = 0

    # LZHファイル名から日付を取得（TXT内日付より信頼性が高い）
    lzh_date = date_from_lzh_name(lzh_path)

    for venue_code, venue_name, block_lines in blocks:
        records = parse_block(venue_code, venue_name, block_lines)
        if not records:
            print(f"   ⚠️  {venue_name}: データなし")
            continue

        # LZHファイル名の日付を最優先。取れなければTXT内の日付を使う
        date = lzh_date if lzh_date else records[0]["日付"]

        # records の「日付」列も統一して上書き
        if lzh_date:
            for r in records:
                r["日付"] = lzh_date

        csv_path = save_csv(records, venue_name, date, OUTPUT_FOLDER)
        if csv_path:
            races = sorted(set(r["レース"] for r in records if r["レース"]))
            print(f"   ✅ {venue_name:6s}  {len(records):3d}件  "
                  f"{len(races)}レース  → {os.path.basename(csv_path)}")
            count += 1

    return count

def main():
    print("=" * 55)
    print("  ボートレース番組表  LZH → CSV 変換ツール")
    print("=" * 55)

    # ファイル名でソートして古い日付から順に処理
    lzh_files = sorted(
        glob.glob(os.path.join(INPUT_FOLDER, "*.lzh")) +
        glob.glob(os.path.join(INPUT_FOLDER, "*.LZH"))
    )

    if not lzh_files:
        print(f"\n❌ LZHファイルが見つかりません")
        print(f"   フォルダ: {INPUT_FOLDER}")
        sys.exit(1)

    print(f"\n   {len(lzh_files)}件のLZHファイルを処理します\n")

    total = 0
    for lzh_path in lzh_files:
        print(f"\n▶ {os.path.basename(lzh_path)}")
        txt_path = extract_lzh(lzh_path, TEMP_FOLDER)
        if not txt_path:
            continue

        # lzh_path を渡すことでファイル名から正しい日付を取得
        total += process_txt(txt_path, lzh_path=lzh_path)

        # 一時フォルダ内を都度クリア（次のLZH解凍に備える）
        for f in glob.glob(os.path.join(TEMP_FOLDER, "*")):
            try:
                os.remove(f)
            except Exception:
                pass

    # 一時フォルダ削除
    if os.path.exists(TEMP_FOLDER):
        shutil.rmtree(TEMP_FOLDER)

    print("\n" + "=" * 55)
    print(f"✅ 完了！{total}会場のCSVを csv_output フォルダに保存しました")
    print("=" * 55)

if __name__ == "__main__":
    main()
