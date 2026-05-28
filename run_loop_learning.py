# -*- coding: utf-8 -*-
"""
run_loop_learning.py  ★v2修正版★  ― バックテスト学習ループ自動実行
==========================================================
【v2 修正内容】
  修正①: ループの役割を「補正係数の精度確認」に限定
          ・旧版: apply_correction → backtest --force を繰り返す
          ・新版: backtest --force のみを繰り返す
          ・理由: apply_correction が蓄積CSVの買い目を書き換えないため
            (apply_correction.py v3 修正②)、ループ内で apply_correction を
            呼ぶ意味がなくなった。correction_table.json の更新のみを繰り返す。

  修正②: 収束判定の基準を「補正前的中率」に固定
          ・correction_table.json の base_hit_rate は補正前の値であり、
            ループを回しても変化しないはずの安定した数値。
          ・ループで変化を確認すべきは「回収率（base_recovery）」と
            「スコア閾値（score_threshold）」の安定性。
          ・旧版の的中率変化ベース収束判定を回収率・閾値ベースに変更。

  修正③: 過学習チェックロジックを改善
          ・旧版は「回収率がピーク比-1%で強制終了」だったが、
            補正前データから計算するため回収率は安定している。
          ・代わりに「スコア閾値が前回から変化しなくなったら収束」と判定。

【使い方】
  python run_loop_learning.py                # デフォルト設定で実行
  python run_loop_learning.py --max-iter 5   # 最大5回
  python run_loop_learning.py --venue びわこ  # 特定会場のみ

【収束判定】
  ・score_threshold の変化が 0 かつ
    base_recovery の変化が --threshold（デフォルト 0.001）未満 → 収束
  ・または --max-iter に達したら停止。

【ログ出力】
  scripts/loop_learning_log.jsonl に各イテレーションの結果を記録。
"""

import argparse
import json
import subprocess
import sys
import time
import pathlib
from datetime import datetime

SCRIPTS_DIR     = pathlib.Path(__file__).parent
BASE_DIR        = SCRIPTS_DIR.parent
LOG_FILE        = SCRIPTS_DIR / "loop_learning_log.jsonl"
CORRECTION_JSON = SCRIPTS_DIR / "correction_table.json"

BACKTEST_SCRIPT = SCRIPTS_DIR / "backtest_engine.py"

PY = sys.executable


def sep(c="=", w=60):
    print(c * w)


def _load_correction_values() -> dict:
    """correction_table.json から収束判定に使う値をまとめて取得する"""
    if not CORRECTION_JSON.exists():
        return {"hit_rate": 0.0, "recovery": 0.0, "threshold": 0, "roi": 0.0}
    try:
        with open(str(CORRECTION_JSON), encoding="utf-8") as f:
            d = json.load(f)
        return {
            "hit_rate":  float(d.get("base_hit_rate",   0)),
            "recovery":  float(d.get("base_recovery",   0)),
            "threshold": int(d.get("score_threshold",   0)),
            "roi":       float(d.get("base_roi",        0)),
            # 補正後的中率（参考値）
            "corrected_hit_rate": d.get("corrected_hit_rate"),
            "corrected_roi":      d.get("corrected_roi"),
        }
    except Exception:
        return {"hit_rate": 0.0, "recovery": 0.0, "threshold": 0, "roi": 0.0}


def _run(cmd: list, label: str, timeout: int = 3600) -> bool:
    print(f"\n  [{label}]  実行中...")
    print(f"  コマンド: {' '.join(str(c) for c in cmd)}")
    start = time.perf_counter()
    try:
        result = subprocess.run(
            cmd, check=False, encoding="utf-8", errors="replace", timeout=timeout
        )
        elapsed = time.perf_counter() - start
        if result.returncode == 0:
            print(f"  [OK] {label}  ({elapsed:.1f}秒)")
            return True
        else:
            print(f"  [NG] {label} 終了コード {result.returncode}  ({elapsed:.1f}秒)")
            return False
    except subprocess.TimeoutExpired:
        print(f"  [NG] {label} タイムアウト ({timeout}秒)")
        return False
    except Exception as e:
        print(f"  [NG] {label} エラー: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="バックテスト学習ループ自動実行 v2修正版")
    parser.add_argument("--max-iter",  type=int,   default=5,
                        help="最大イテレーション数（デフォルト:5）")
    parser.add_argument("--threshold", type=float, default=0.001,
                        help="収束判定閾値（回収率変化、デフォルト:0.001）")
    parser.add_argument("--venue",     type=str,   default=None,
                        help="会場名フィルタ")
    args = parser.parse_args()

    if not BACKTEST_SCRIPT.exists():
        print(f"  [NG] {BACKTEST_SCRIPT.name} が見つかりません: {BACKTEST_SCRIPT}")
        sys.exit(1)

    sep()
    print("  バックテスト学習ループ  v2修正版")
    print(f"  最大 {args.max_iter} イテレーション / 収束閾値（回収率） {args.threshold}")
    print()
    print("  【ループの役割】")
    print("    backtest --force を繰り返し、EMA平滑化された補正係数が")
    print("    安定（収束）するまで correction_table.json を更新する。")
    print("    apply_correction は買い目列を書き換えないため、")
    print("    ループ内で apply_correction を呼ぶ必要はない。")
    sep()

    prev = _load_correction_values()
    print(f"\n  開始時点:")
    print(f"    補正前的中率  : {prev['hit_rate']:.1f}%")
    print(f"    補正前回収率  : {prev['recovery']:.4f}")
    print(f"    スコア閾値    : {prev['threshold']}")
    print(f"    補正前ROI     : {prev['roi']:.1f}%")
    if prev.get("corrected_hit_rate") is not None:
        print(f"    補正後的中率  : {prev['corrected_hit_rate']}%（参考）")

    history = []

    for i in range(1, args.max_iter + 1):
        sep("-")
        print(f"  ▶ ITERATION {i}/{args.max_iter}")
        sep("-")
        iter_start = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # ── backtest --force のみ実行 ────────────────────────────────────
        # ★修正①: apply_correction はループ内では呼ばない。
        #   理由: apply_correction.py v3 は蓄積CSVの買い目を書き換えないため、
        #         apply_correction を実行しても蓄積CSVのハッシュは変化せず、
        #         backtest_engine のキャッシュが有効のままになる。
        #         したがって --force で必ず再計算させる。
        bt_cmd = [PY, str(BACKTEST_SCRIPT), "--force"]
        if args.venue:
            bt_cmd += ["--venue", args.venue]

        ok = _run(bt_cmd, f"backtest_engine --force (iter={i})")
        if not ok:
            print(f"  [!] backtest_engine が失敗しました。ループを中断します。")
            break

        # ── 収束チェック ────────────────────────────────────────────────
        curr = _load_correction_values()

        # 補正前統計は毎回ほぼ同じはず（変化があるとすればデータ追加時のみ）
        delta_recovery  = abs(curr["recovery"]  - prev["recovery"])
        delta_threshold = abs(curr["threshold"] - prev["threshold"])
        delta_roi       = curr["roi"] - prev["roi"]

        history.append({
            "iteration":        i,
            "executed_at":      iter_start,
            "hit_rate":         curr["hit_rate"],
            "recovery":         curr["recovery"],
            "prev_recovery":    prev["recovery"],
            "delta_recovery":   round(delta_recovery,  5),
            "score_threshold":  curr["threshold"],
            "prev_threshold":   prev["threshold"],
            "delta_threshold":  delta_threshold,
            "roi":              curr["roi"],
            "roi_change":       round(delta_roi, 4),
            "corrected_hit_rate": curr.get("corrected_hit_rate"),
            "corrected_roi":    curr.get("corrected_roi"),
        })

        print(f"\n  補正前的中率  : {curr['hit_rate']:.1f}%（変化なし＝正常）")
        print(f"  補正前回収率  : {prev['recovery']:.4f} → {curr['recovery']:.4f}"
              f"  (Δ{delta_recovery:+.5f})")
        print(f"  スコア閾値    : {prev['threshold']} → {curr['threshold']}"
              f"  (Δ{delta_threshold:+.0f})")
        print(f"  補正前ROI     : {prev['roi']:+.1f}% → {curr['roi']:+.1f}%"
              f"  (Δ{delta_roi:+.2f}%)")
        if curr.get("corrected_hit_rate") is not None:
            print(f"  補正後的中率  : {curr['corrected_hit_rate']}%（参考）")
            print(f"  補正後ROI     : {curr['corrected_roi']}%（参考）")

        # ログ記録
        try:
            with open(str(LOG_FILE), "a", encoding="utf-8") as f:
                f.write(json.dumps(history[-1], ensure_ascii=False) + "\n")
        except Exception:
            pass

        # ★修正③: スコア閾値と回収率が両方安定したら収束
        threshold_stable = delta_threshold == 0
        recovery_stable  = delta_recovery  < args.threshold

        if threshold_stable and recovery_stable:
            print(f"\n  ★ 収束しました")
            print(f"    スコア閾値変化: {delta_threshold}（0＝安定）")
            print(f"    回収率変化: {delta_recovery:.5f} < {args.threshold}")
            break
        else:
            if not threshold_stable:
                print(f"  → スコア閾値が変化中（{prev['threshold']} → {curr['threshold']}）。継続します。")
            if not recovery_stable:
                print(f"  → 回収率が変化中（Δ={delta_recovery:.5f} ≥ {args.threshold}）。継続します。")

        prev = curr

    # ── 結果サマリー ──────────────────────────────────────────────────
    sep()
    print("  学習ループ完了")
    sep()
    if history:
        print(f"  実行イテレーション : {len(history)}")
        first = history[0]
        last  = history[-1]
        print()
        print("  ■ 補正前（生データ）の推移")
        print(f"    的中率  : {first['hit_rate']:.1f}%（全イテレーション通じて安定が正常）")
        print(f"    回収率  : {first['prev_recovery']:.4f} → {last['recovery']:.4f}")
        print(f"    閾値    : {first['prev_threshold']} → {last['score_threshold']}")
        print(f"    ROI     : {first['roi']:+.1f}%")
        print()
        print("  ■ 補正後（参考値）の推移")
        for h in history:
            crr = h.get("corrected_hit_rate", "N/A")
            cro = h.get("corrected_roi", "N/A")
            print(f"    [{h['iteration']}] 的中率:{crr}%  ROI:{cro}%"
                  f"  閾値:{h['score_threshold']}  回収率:{h['recovery']:.4f}"
                  f"(Δ{h['delta_recovery']:+.5f})")
        print()
        print("  【重要】補正前的中率がイテレーションを通じて変化している場合は")
        print("  蓄積CSVが外部から書き換えられている可能性があります。")
        print("  apply_correction.py v3（買い目列書き換えなし）を使用しているか確認してください。")
    print()
    print(f"  ログ: {LOG_FILE}")
    print(f"  補正テーブル: {CORRECTION_JSON}")
    sep()


if __name__ == "__main__":
    main()
