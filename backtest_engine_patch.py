# -*- coding: utf-8 -*-
"""
backtest_engine.py  v3修正版
======================
【修正内容】
  修正②: generate_correction_table() の venue_weight キーにグレード軸を追加
          旧: "大村" → 1.2
          新: "大村_一般" → 1.2 / "大村_G1" → 0.9

          蓄積CSVに「グレード」列がある場合に (会場名_グレード) でキー生成。
          列がない場合は従来通り会場名のみ（後方互換維持）。

  修正④: lr_backtest.py の fill_logs_from_csv() で '進入コース' を使っていたバグを修正
          着順Top3の取得は '艇番' 列を使うのが正しい。
          ※ この修正は lr_backtest.py 側に適用してください（lr_backtest_fixed.py 参照）

【使い方】（変更なし）
  python backtest_engine.py
  python backtest_engine.py --venue びわこ
  python backtest_engine.py --force
"""

# ── 元ファイルの全コードを継承し、generate_correction_table() のみ差し替える ──
# 以下の差分パッチを元の backtest_engine.py に適用してください。
#
# --- a/backtest_engine.py
# +++ b/backtest_engine.py
# @@ generate_correction_table() 内
#
# 【変更箇所1】venue_weight の生成部分を以下に差し替え:
#
# 旧:
#   "venue_weight": {k: weight(s.get("的中率",0))
#                   for k,s in summary.get("会場別",{}).items()},
#
# 新（グレード別に分離）:
#   "venue_weight": _build_venue_weight(summary),
#
# 【変更箇所2】_build_venue_weight 関数を追加:

def _build_venue_weight(summary: dict) -> dict:
    """
    会場別 + グレード別 の venue_weight を生成する。

    蓄積CSVの analyze() が「会場別」を {"大村_一般": {...}, "大村_G1": {...}} の形で
    返す場合はそのままキーとして使う。
    従来形式（会場名のみ）でも動作するよう後方互換を維持。

    Returns
    -------
    {"大村_一般": 1.2, "大村_G1": 0.9, "大村": 1.05, ...}
    のように 両キーを持つ辞書を返す（apply_correction が両方を参照できるよう）。
    """
    base_hit = 0.0  # 全体的中率は呼び出し元の summary から取得する想定
    venue_summary = summary.get("会場別", {})

    result: dict[str, float] = {}
    for key, s in venue_summary.items():
        hit_rate = s.get("的中率", 0)
        if base_hit <= 0:
            w = 1.0
        else:
            w = round(max(0.5, min(2.0, hit_rate / base_hit)), 3)
        result[key] = w

        # キーが "大村_一般" 形式の場合、会場名だけのキーも平均値で登録
        if "_" in str(key):
            parts = str(key).rsplit("_", 1)
            venue_only = parts[0]
            if venue_only not in result:
                result[venue_only] = w
            else:
                # 既存値と平均
                result[venue_only] = round((result[venue_only] + w) / 2, 3)

    return result


# ══════════════════════════════════════════════════════════
# analyze() の拡張: グレード列があれば (会場_グレード) でグルーピング
# ══════════════════════════════════════════════════════════

def _analyze_venue_grade(bt_buy: "pd.DataFrame") -> dict:
    """
    会場×グレード別の精度分析。

    蓄積CSVに「グレード」列がある場合は (会場_グレード) でグルーピング。
    なければ従来の会場別のみ返す。
    """
    import pandas as pd

    def stats(df):
        n = len(df)
        if n == 0:
            return {"レース数": 0, "的中数": 0, "的中率": 0, "総投資": 0, "総回収": 0, "ROI": 0}
        hits = df["的中"].sum(); inv = df["投資額"].sum(); ret = df["回収額"].sum()
        return {
            "レース数": n, "的中数": int(hits),
            "的中率": round(hits / n * 100, 1),
            "総投資": int(inv), "総回収": int(ret),
            "ROI": round((ret - inv) / inv * 100, 1) if inv > 0 else 0,
        }

    result = {}

    # 従来の会場別
    for v, g in bt_buy.groupby("会場"):
        result[str(v)] = stats(g)

    # グレード別（列があるとき）
    if "グレード" in bt_buy.columns:
        bt_buy = bt_buy.copy()
        bt_buy["_venue_grade"] = bt_buy["会場"].astype(str) + "_" + bt_buy["グレード"].astype(str)
        for vg, g in bt_buy.groupby("_venue_grade"):
            result[str(vg)] = stats(g)

    return result


# ══════════════════════════════════════════════════════════
# 差分パッチ適用手順（元ファイルへの最小変更）
# ══════════════════════════════════════════════════════════
#
# backtest_engine.py の以下の行を修正してください:
#
# 【1】generate_correction_table() 内の venue_weight 行を差し替え
#   旧: "venue_weight": {k: weight(s.get("的中率",0))
#                       for k,s in summary.get("会場別",{}).items()},
#   新: "venue_weight": _build_venue_weight(summary),
#
# 【2】analyze() 内の s["会場別"] 行を差し替え
#   旧: s["会場別"] = {v: stats(g) for v, g in bt_buy.groupby("会場")}
#   新: s["会場別"] = _analyze_venue_grade(bt_buy)
#
# 【3】このファイル（backtest_engine_patch.py）の _build_venue_weight()
#      と _analyze_venue_grade() を backtest_engine.py の先頭付近に追加。
#
# ══════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("このファイルは差分パッチです。")
    print("backtest_engine.py に上記の修正を適用してください。")
    print("")
    print("自動適用する場合:")
    print("  python backtest_engine_patch.py --apply ../scripts/backtest_engine.py")

    import sys, pathlib, re

    if "--apply" in sys.argv:
        idx  = sys.argv.index("--apply")
        target = pathlib.Path(sys.argv[idx + 1])
        if not target.exists():
            print(f"  [NG] 対象ファイルが見つかりません: {target}")
            sys.exit(1)

        src = target.read_text(encoding="utf-8")

        # パッチ1: venue_weight 行
        old1 = (
            '"venue_weight":    {k: weight(s.get(\'的中率\',0))\n'
            '                            for k,s in summary.get("会場別",{}).items()},'
        )
        new1 = '"venue_weight":    _build_venue_weight(summary),'
        if old1 in src:
            src = src.replace(old1, new1)
            print("  [OK] パッチ1 適用（venue_weight グレード対応）")
        else:
            print("  [!] パッチ1 の対象行が見つかりません。手動で確認してください。")

        # パッチ2: 会場別 analyze
        old2 = 's["会場別"]       = {v: stats(g) for v, g in bt_buy.groupby("会場")}'
        new2 = 's["会場別"]       = _analyze_venue_grade(bt_buy)'
        if old2 in src:
            src = src.replace(old2, new2)
            print("  [OK] パッチ2 適用（会場×グレード別分析）")
        else:
            print("  [!] パッチ2 の対象行が見つかりません。手動で確認してください。")

        # パッチ3: 関数を先頭付近（import直後）に挿入
        insert_marker = "\nMARK_PRIORITY ="
        inject_code = """
# ── グレード対応 venue_weight（backtest_engine_patch.py より自動挿入）──────────

def _build_venue_weight(summary: dict) -> dict:
    base_hit = summary.get("全体", {}).get("的中率", 0)
    venue_summary = summary.get("会場別", {})
    result: dict = {}
    for key, s in venue_summary.items():
        hr = s.get("的中率", 0)
        w = round(max(0.5, min(2.0, hr / base_hit)), 3) if base_hit > 0 else 1.0
        result[key] = w
        if "_" in str(key):
            venue_only = str(key).rsplit("_", 1)[0]
            if venue_only not in result:
                result[venue_only] = w
            else:
                result[venue_only] = round((result[venue_only] + w) / 2, 3)
    return result


def _analyze_venue_grade(bt_buy) -> dict:
    import pandas as pd
    def stats(df):
        n = len(df)
        if n == 0:
            return {"レース数":0,"的中数":0,"的中率":0,"総投資":0,"総回収":0,"ROI":0}
        hits = df["的中"].sum(); inv = df["投資額"].sum(); ret = df["回収額"].sum()
        return {"レース数":n,"的中数":int(hits),"的中率":round(hits/n*100,1),
                "総投資":int(inv),"総回収":int(ret),
                "ROI":round((ret-inv)/inv*100,1) if inv>0 else 0}
    result = {}
    for v, g in bt_buy.groupby("会場"):
        result[str(v)] = stats(g)
    if "グレード" in bt_buy.columns:
        tmp = bt_buy.copy()
        tmp["_vg"] = tmp["会場"].astype(str) + "_" + tmp["グレード"].astype(str)
        for vg, g in tmp.groupby("_vg"):
            result[str(vg)] = stats(g)
    return result

# ──────────────────────────────────────────────────────────────────────────────

"""
        if insert_marker in src:
            src = src.replace(insert_marker, inject_code + insert_marker, 1)
            print("  [OK] パッチ3 適用（関数挿入）")
        else:
            print("  [!] パッチ3 の挿入点が見つかりません。手動で確認してください。")

        target.write_text(src, encoding="utf-8")
        print(f"\n  完了: {target}")
