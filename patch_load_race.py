# patch_load_race.py
# ==================
# load_race.py への3施策パッチ適用スクリプト
# 実行: python patch_load_race.py
#
# 【変更箇所】
#   変更① _SKIP_VENUES / _NIGE_SKIP_VENUES 定数ブロック置き換え（3645〜3655行付近）
#   変更② _should_skip_race 内の条件④を拡張（3703〜3705行付近）
#   変更③ _suggest_3rentan 末尾 参加見送り判定の直前に逃げ点数上限を追加（4579〜4587行付近）
#   変更④ main() ループ内 bet_suggestions確定直後に1〜3R見送りを追加（7531〜7532行付近）

import pathlib
import sys

TARGET = pathlib.Path(__file__).parent / "load_race.py"
if not TARGET.exists():
    print(f"❌ {TARGET} が見つかりません。同じディレクトリに置いてください。")
    sys.exit(1)

src = TARGET.read_text(encoding="utf-8")

# ============================================================
# 変更① : _SKIP_VENUES を廃止し、逃げ専用の許可リストに置き換える
# ============================================================
OLD_SKIP_VENUES = """\
# 参加見送り判定（バックテスト結果に基づく精度向上フィルタ）
# ============================================================
# 【根拠】バックテスト8,526R分析（2025-12〜2026-02）
#   逃げ軸流し: 4,665R / ROI 27.1% / 損益 −377万  ← 全損失の152%
#   悪会場10会場: ROI 34〜67%帯 / 合計大赤字
#   逃げ除外だけで ROI 130.4% → 黒字転換
# ============================================================
_SKIP_VENUES = {
    '大村', '多摩川', '住之江', '芦屋', '福岡',
    '丸亀', '蒲郡', '津', '児島', '尼崎',
}"""

NEW_SKIP_VENUES = """\
# 参加見送り判定（バックテスト結果に基づく精度向上フィルタ）
# ============================================================
# 【根拠】バックテスト8,458R分析（2025-12〜2026-02）
#   逃げシナリオ:  4,627R / ROI 26.8% / 損益 −376万  ← 全損失の153%
#   逃げ以外:      3,831R / ROI 130.9%/ 損益 +131万
#
#   施策シミュレーション結果:
#     ①逃げ会場フィルタのみ   → ROI 111.4% / +62万  (現状比 +307万)
#     ①+②1〜3R見送り         → ROI 122.1% / +87万  (現状比 +332万)
#     ①+②+③逃げ5点上限      → ROI 132.5% / +112万 (現状比 +357万)
#
# 逃げシナリオ参加許可会場（BT実績ROI 30%以上の会場のみ）:
#   宮島(59.2%), 江戸川(45.6%), 下関(37.1%), 浜名湖(33.2%), 多摩川(30.9%)
#
# ※ _SKIP_VENUES は後方互換のため残す（旧・全シナリオ会場フィルタ）
# ============================================================
_SKIP_VENUES = set()  # 旧・全シナリオ会場フィルタ → 現在は無効化（逃げ専用フィルタに移行）

# 逃げシナリオで参加を許可する会場（BT実績ROI30%以上のみ）
# ここに入っていない会場の「逃げ軸流し」は自動見送り
_NIGE_ALLOWED_VENUES = {
    '宮島',   # ROI 59.2%
    '江戸川', # ROI 45.6%
    '下関',   # ROI 37.1%
    '浜名湖', # ROI 33.2%
    '多摩川', # ROI 30.9%
}

# 逃げシナリオの最大買い目点数（BT分析：点数を絞っても的中率は変わらないため
# 投資額削減を優先。上位5点に絞ることで回収率が改善）
_NIGE_MAX_BETS = 5"""

if OLD_SKIP_VENUES not in src:
    print("❌ 変更①: 対象文字列が見つかりません。load_race.py のバージョンを確認してください。")
    sys.exit(1)

src = src.replace(OLD_SKIP_VENUES, NEW_SKIP_VENUES)
print("✅ 変更① 適用: _NIGE_ALLOWED_VENUES / _NIGE_MAX_BETS 定数を追加")

# ============================================================
# 変更② : _should_skip_race の条件④を逃げ専用会場フィルタに置き換え
# ============================================================
OLD_SKIP_LOGIC = """\
    # ④ 低回収会場
    if venue and venue in _SKIP_VENUES:
        return True, f"⛔{venue}：ROI低会場見送り（BT実績ROI≤67%）"

    return False, \"\""""

NEW_SKIP_LOGIC = """\
    # ④ 逃げシナリオ × 非許可会場
    #    逃げ軸流しはROIが構造的に低い会場が多いため、
    #    BT実績でROI30%以上の会場のみ参加を許可する。
    scenario_type = bet_suggestions.get("scenario_type", "")
    if scenario_type == "逃げ軸流し" and venue and venue not in _NIGE_ALLOWED_VENUES:
        return True, (
            f"⛔逃げ軸・非許可会場（{venue}）→ 見送り\\n"
            f"BT実績: {venue}の逃げシナリオROIは30%未満。"
            f"許可会場: {', '.join(sorted(_NIGE_ALLOWED_VENUES))}"
        )

    # ⑤ 旧・全シナリオ会場フィルタ（現在は無効化済み。後方互換のため残す）
    if venue and venue in _SKIP_VENUES:
        return True, f"⛔{venue}：ROI低会場見送り（BT実績ROI≤67%）"

    return False, \"\""""

if OLD_SKIP_LOGIC not in src:
    print("❌ 変更②: 対象文字列が見つかりません。")
    sys.exit(1)

src = src.replace(OLD_SKIP_LOGIC, NEW_SKIP_LOGIC)
print("✅ 変更② 適用: _should_skip_race に逃げ会場フィルタ（条件④）を追加")

# ============================================================
# 変更③ : _suggest_3rentan 末尾の参加見送り判定直前に
#          逃げシナリオの点数上限（_NIGE_MAX_BETS）を追加
# ============================================================
OLD_SKIP_FLAG = """\
    # ── 参加見送り判定をフラグとして付与 ──
    # venue は race_judgment 経由で受け取る（_suggest_3rentan は venue を直接知らない）
    _venue   = (race_judgment or {}).get("venue", "")
    # himo_are を race_judgment から _result に渡す（_should_skip_race が参照するため）
    if "himo_are" not in _result:
        _result["himo_are"] = (race_judgment or {}).get("himo_are", {}) or {}
    _skip, _skip_reason = _should_skip_race(_result, _venue)
    _result["skip"]        = _skip
    _result["skip_reason"] = _skip_reason

    return _result"""

NEW_SKIP_FLAG = """\
    # ── 逃げシナリオ 点数上限（_NIGE_MAX_BETS）────────────────────────────
    # BT分析: 逃げは点数を絞っても的中率が改善しないため投資額を削減して回収率UP
    # シミュレーション: 5点上限で ROI 122% → 132% に改善（現状12点平均）
    _result_scenario = _result.get("scenario_type", "")
    if _result_scenario == "逃げ軸流し":
        _orig_buy = _result.get("buy_list", [])
        if len(_orig_buy) > _NIGE_MAX_BETS:
            _trimmed = _orig_buy[:_NIGE_MAX_BETS]
            _result["buy_list"]    = _trimmed
            _result["point_count"] = len(_trimmed)
            # candidates も同期
            _trimmed_set = set(_trimmed)
            _result["candidates"] = [
                c for c in _result.get("candidates", [])
                if c.get("combo") in _trimmed_set
            ]
            # theory_syn_odds を再計算
            _trim_combos = [
                c for c in _result.get("combos", [])
                if c["combo"] in _trimmed_set
            ]
            _trim_prob = sum(c["prob"] for c in _trim_combos)
            _result["theory_syn_odds"] = round(0.75 / _trim_prob, 1) if _trim_prob > 0 else None
            # ev_warning を再評価
            _tso2 = _result["theory_syn_odds"]
            _result["ev_warning"] = (_tso2 is not None and _tso2 < EV_THRESHOLD)
            _result["ev_warning_msg"] = (
                f"⚠ 理想合成オッズ{_tso2}倍（期待値基準{EV_THRESHOLD}倍を下回っています）\\n"
                f"  → 回収重視なら見送り推奨 / 的中重視なら参考買い目を使用可"
            ) if _result["ev_warning"] else ""

    # ── 参加見送り判定をフラグとして付与 ──
    # venue は race_judgment 経由で受け取る（_suggest_3rentan は venue を直接知らない）
    _venue   = (race_judgment or {}).get("venue", "")
    # himo_are を race_judgment から _result に渡す（_should_skip_race が参照するため）
    if "himo_are" not in _result:
        _result["himo_are"] = (race_judgment or {}).get("himo_are", {}) or {}
    _skip, _skip_reason = _should_skip_race(_result, _venue)
    _result["skip"]        = _skip
    _result["skip_reason"] = _skip_reason

    return _result"""

if OLD_SKIP_FLAG not in src:
    print("❌ 変更③: 対象文字列が見つかりません。")
    sys.exit(1)

src = src.replace(OLD_SKIP_FLAG, NEW_SKIP_FLAG)
print("✅ 変更③ 適用: 逃げシナリオ 点数上限（_NIGE_MAX_BETS=5）を追加")

# ============================================================
# 変更④ : main() ループ内 例外キャッチの直後に 1〜3R 見送りを追加
# ============================================================
OLD_1TO3R = """\
        except Exception as e:
            print(f"  ⚠️  印・買い目確定エラー ({race_no}R): {e}")

        # 数値シート用にデータを蓄積"""

NEW_1TO3R = """\
        except Exception as e:
            print(f"  ⚠️  印・買い目確定エラー ({race_no}R): {e}")

        # ── 展示前レース（1〜3R）見送り ─────────────────────────────────────
        # BT分析: 1〜3Rは展示タイム・周回展示なしのため予測精度が低く ROI 54〜62%
        # 施策②: 全シナリオで見送りフラグを立てる
        # ※ bet_suggestions が None の場合（印・買い目エラー時）も安全に処理
        if race_no in (1, 2, 3) and isinstance(bet_suggestions, dict):
            if not bet_suggestions.get("skip"):  # 既に別理由で見送り済みなら上書きしない
                bet_suggestions["skip"]        = True
                bet_suggestions["skip_reason"] = (
                    f"⛔展示前レース（{race_no}R）→ 見送り\\n"
                    f"BT実績: 1〜3RのROIは54〜62%。展示タイム確認後に判断推奨。"
                )

        # 数値シート用にデータを蓄積"""

if OLD_1TO3R not in src:
    print("❌ 変更④: 対象文字列が見つかりません。")
    sys.exit(1)

src = src.replace(OLD_1TO3R, NEW_1TO3R)
print("✅ 変更④ 適用: 1〜3R 展示前レース見送りフラグを main() に追加")

# ============================================================
# 書き出し
# ============================================================
TARGET.write_text(src, encoding="utf-8")
print()
print(f"✅ パッチ適用完了: {TARGET}")
print()
print("【変更サマリ】")
print("  ① _NIGE_ALLOWED_VENUES 定数追加（逃げ許可会場: 宮島/江戸川/下関/浜名湖/多摩川）")
print("  ② _should_skip_race に逃げ会場フィルタ条件④ 追加")
print("  ③ _suggest_3rentan 末尾に逃げ点数上限（5点）追加")
print("  ④ main() ループに1〜3R展示前見送りフラグ追加")
print()
print("【期待ROI改善】 73.8% → 132.5%（BT8,458Rシミュレーション）")
print("【損益改善】   ▲245万 → +112万（現状比 +357万）")
