"""
tune_kimari.py  —  venue_kimari 自動チューニング
=======================================================
results.csv の実績と master_data.json を照合し、
会場別・決まり手別の「予測ズレ」を測定して
kimari_tuning.json に補正オフセットを保存する。

【設計思想】
  - Excelから生成される master_data.json（生の venue_kimari）は触らない
  - 補正値は kimari_tuning.json に分離して保存
  - auto_push.py が起動時に重ねて適用するので、
    Excelを更新しても補正値はリセットされない
  - データが増えたら再実行するだけで補正値が更新される

【補正の仕組み】
  results.csv の決まり手列から「実際の決まり手比率」を会場別に集計し、
  master_data.json の venue_kimari（予測比率）とのズレを算出。
  ズレをそのまま上書きするのではなく、
  元の値と実績値の加重平均（信頼度付き）で補正する。

  補正後の kimari[k] = 元の値 × (1 - trust) + 実績値 × trust
    trust = min(実績レース数 / MIN_RACES_FOR_FULL_TRUST, 1.0)

【使い方】
  python tune_kimari.py

  # パスを明示する場合
  python tune_kimari.py <results_csv_dir> <master_json_path> [output_tuning_json]

【出力】
  kimari_tuning.json : 会場別の補正済み venue_kimari
                       auto_push.py が読んで MASTER に重ねる

【results.csv の想定列】
  日付, 会場名, レース番号, レース種別, 距離, 天候, 風向, 風速,
  波高, 決まり手, 着順, 艇番, 登録番号, 選手名, ...
"""

import sys
import json
import csv
import glob
import os
from pathlib import Path
from collections import defaultdict


# ── 列インデックス ──────────────────────────────────────
COL_DATE   = 0
COL_VENUE  = 1
COL_RACE   = 2
COL_KIMARI = 9   # 決まり手
COL_RANK   = 10  # 着順
COL_FRAME  = 11  # 艇番

# ── チューニングパラメータ ──────────────────────────────
# この件数に達したら実績値を100%信頼（それ未満は元の値に引き寄せる）
MIN_RACES_FOR_FULL_TRUST = 200

# 対象とする決まり手（恵まれは転覆等による繰り上がりで予測不可のため除外）
VALID_KIMARI = {"逃げ", "差し", "まくり", "まくり差し", "抜き"}

# 補正の上下限（元の値から何倍まで動かすか）
TUNE_MIN_RATIO = 0.5   # 元の値の最小50%まで
TUNE_MAX_RATIO = 2.0   # 元の値の最大200%まで


# ──────────────────────────────────────────────────────────────────
# ユーティリティ
# ──────────────────────────────────────────────────────────────────

def safe_int(v, default=None):
    try:
        return int(str(v).strip())
    except (ValueError, TypeError):
        return default


def log(msg):
    print(msg, flush=True)


# ──────────────────────────────────────────────────────────────────
# results.csv 読み込み（決まり手の集計のみ）
# ──────────────────────────────────────────────────────────────────

def load_kimari_stats(csv_dir: str) -> dict:
    """
    results.csv から会場別・決まり手別の実績レース数を集計する。

    戻り値:
        {
            "鳴門": {
                "total": 120,
                "逃げ":  60,
                "差し":  25,
                "まくり": 20,
                "まくり差し": 12,
                "抜き":  3,
            },
            ...
        }
    """
    pattern = os.path.join(csv_dir, "*_results.csv")
    files = sorted(glob.glob(pattern))
    if not files:
        pattern = os.path.join(csv_dir, "**", "*_results.csv")
        files = sorted(glob.glob(pattern, recursive=True))

    if not files:
        log(f"警告: {csv_dir} に *_results.csv が見つかりません")
        return {}

    log(f"  results CSV: {len(files)} ファイル")

    # 重複カウント防止: (date, venue, race_no) でユニーク管理
    seen_races   = set()
    # venue -> kimari -> count
    venue_kimari = defaultdict(lambda: defaultdict(int))
    venue_total  = defaultdict(int)

    for fpath in files:
        for enc in ["utf-8", "shift_jis", "cp932", "utf-8-sig"]:
            try:
                with open(fpath, encoding=enc, newline="") as f:
                    reader = csv.reader(f)
                    next(reader, None)
                    for row in reader:
                        if len(row) <= max(COL_KIMARI, COL_RANK):
                            continue
                        date    = row[COL_DATE].strip()
                        venue   = row[COL_VENUE].strip()
                        race_no = safe_int(row[COL_RACE])
                        rank    = safe_int(row[COL_RANK])
                        kimari  = row[COL_KIMARI].strip() if len(row) > COL_KIMARI else ""

                        if not all([date, venue, race_no]):
                            continue

                        # 1着行のみ（決まり手は1着の行に記録されている）
                        if rank != 1:
                            continue

                        race_key = (date, venue, race_no)
                        if race_key in seen_races:
                            continue
                        seen_races.add(race_key)

                        if not kimari or kimari not in VALID_KIMARI:
                            continue

                        venue_kimari[venue][kimari] += 1
                        venue_total[venue]          += 1
                break
            except (UnicodeDecodeError, LookupError):
                continue

    # 比率に変換
    result = {}
    for venue, counts in venue_kimari.items():
        total = venue_total[venue]
        if total == 0:
            continue
        result[venue] = {
            "total": total,
            **{k: v for k, v in counts.items()},
        }

    log(f"  集計会場数: {len(result)}")
    for v, d in sorted(result.items()):
        parts = [f"{k}:{d[k]}" for k in VALID_KIMARI if k in d]
        log(f"    {v}: 計{d['total']}レース  {' / '.join(parts)}")

    return result


# ──────────────────────────────────────────────────────────────────
# 補正値の計算
# ──────────────────────────────────────────────────────────────────

def calc_tuning(kimari_stats: dict, master: dict) -> dict:
    """
    実績比率と master の venue_kimari を比較し、補正済みの venue_kimari を返す。

    補正式:
        trust = min(実績レース数 / MIN_RACES_FOR_FULL_TRUST, 1.0)
        補正後[k] = 元の値[k] × (1 - trust) + 実績比率[k] × trust

    補正後は再正規化して合計を1.0に揃える。
    上下限クリップ（TUNE_MIN_RATIO〜TUNE_MAX_RATIO）で暴れを防ぐ。
    """
    venue_kimari_master = master.get("venue_kimari", {})
    tuned = {}

    log("\n【補正計算】")

    for venue, stats in kimari_stats.items():
        original = venue_kimari_master.get(venue)
        if not original:
            log(f"  {venue}: master に venue_kimari なし → スキップ")
            continue

        total = stats["total"]
        trust = min(total / MIN_RACES_FOR_FULL_TRUST, 1.0)

        log(f"  {venue}: {total}レース  信頼度={trust:.2f}")

        # 実績比率を計算
        actual_rates = {}
        actual_total = sum(stats.get(k, 0) for k in VALID_KIMARI)
        if actual_total == 0:
            log(f"    → 有効決まり手なし スキップ")
            continue

        for k in VALID_KIMARI:
            actual_rates[k] = stats.get(k, 0) / actual_total

        # 加重平均で補正
        blended = {}
        for k in VALID_KIMARI:
            orig = original.get(k, 0.0)
            actual = actual_rates.get(k, 0.0)
            raw = orig * (1 - trust) + actual * trust

            # 上下限クリップ（元の値が0の場合はスキップ）
            if orig > 0:
                raw = max(orig * TUNE_MIN_RATIO, min(orig * TUNE_MAX_RATIO, raw))

            blended[k] = raw

            # ログ：ズレが大きいものだけ表示
            gap = actual - orig
            if abs(gap) >= 0.02:
                direction = "↑過小評価" if gap > 0 else "↓過大評価"
                log(f"    {k}: master={orig:.3f} 実績={actual:.3f} "
                    f"gap={gap:+.3f} {direction} → 補正後={raw:.3f}")

        # 再正規化
        blend_total = sum(blended.values())
        if blend_total <= 0:
            continue

        tuned[venue] = {k: round(v / blend_total, 4) for k, v in blended.items()}

    log(f"\n  補正完了: {len(tuned)} 会場")
    return tuned


# ──────────────────────────────────────────────────────────────────
# メイン
# ──────────────────────────────────────────────────────────────────

def main():
    _here = Path(__file__).resolve().parent
    _root = _here.parent

    DEFAULT_CSV_DIR     = _root / "data_csv"
    DEFAULT_MASTER_PATH = _here / "master_data.json"
    DEFAULT_OUT_PATH    = _here / "kimari_tuning.json"

    if len(sys.argv) == 1:
        csv_dir     = str(DEFAULT_CSV_DIR)
        master_path = str(DEFAULT_MASTER_PATH)
        out_path    = DEFAULT_OUT_PATH
        log("[デフォルトパスで実行]")
        log(f"  CSV フォルダ  : {csv_dir}")
        log(f"  マスタ JSON   : {master_path}")
        log(f"  出力先        : {out_path}")
    elif len(sys.argv) >= 3:
        csv_dir     = sys.argv[1]
        master_path = sys.argv[2]
        out_path    = Path(sys.argv[3]) if len(sys.argv) >= 4 else DEFAULT_OUT_PATH
    else:
        log("使い方:")
        log("  引数なし  : python tune_kimari.py")
        log("  パス指定  : python tune_kimari.py <csv_dir> <master_json> [out_json]")
        sys.exit(1)

    if not Path(master_path).exists():
        log(f"エラー: master_data.json が見つかりません → {master_path}")
        sys.exit(1)

    log("決まり手実績を集計中...")
    kimari_stats = load_kimari_stats(csv_dir)

    if not kimari_stats:
        log("エラー: 集計できるデータがありませんでした")
        sys.exit(1)

    log("\nmaster_data.json を読み込み中...")
    with open(master_path, encoding="utf-8") as f:
        master = json.load(f)

    tuned = calc_tuning(kimari_stats, master)

    if not tuned:
        log("補正値が生成できませんでした")
        sys.exit(1)

    # 出力
    output = {
        "built_at":      __import__("time").strftime("%Y-%m-%d %H:%M:%S"),
        "min_races":     MIN_RACES_FOR_FULL_TRUST,
        "venue_kimari":  tuned,
    }

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    log(f"\n✓ 出力完了: {out_path}")
    log("  → auto_push.py を再起動すると次回プッシュから反映されます")


if __name__ == "__main__":
    main()
