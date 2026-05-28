# -*- coding: utf-8 -*-
"""
sanren_idx_patch.py
===================
3連対指数を既存システムに組み込むためのパッチガイド。

このファイル自体は実行不要です。
各ファイルの「★ここを追加」コメント箇所を確認して修正してください。

【修正対象ファイルと箇所】
    1. lr_calc.py          → calc_race_indices() の末尾に calc_sanren_idx を呼ぶ
    2. lr_excel.py         → write_numeric_sheet() の数値指標セクションに1行追加
    3. export_indices_csv.py → PLAYER_KEYS / build_rows に2列追加
"""

# ============================================================
# パッチ1: lr_calc.py
# ============================================================
"""
【変更場所】
    calc_race_indices() 関数の return 直前

【追加するコード】
------------------------------------------------------------
    # ── 3連対指数（会場×コース補正付き相対評価） ────────────────────────
    try:
        from lr_sanren_idx import calc_sanren_idx as _calc_sanren_idx
        results = _calc_sanren_idx(
            results,
            venue,
            venue_course_master,
            venue_stats_master,
        )
    except Exception as _e:
        print(f"  [!]  3連対指数計算エラー（スキップ）: {_e}")
    # ─────────────────────────────────────────────────────────

    return results, slit, venue_stats, frame_2nd, race_judgment, bet_suggestions
------------------------------------------------------------

【注意】
    - venue_stats_master は calc_race_indices の引数として既に存在する
    - venue_course_master も同様に引数として渡されている
    - import は関数内に書いて循環importを防ぐ（または先頭に書いてtry/except）
"""


# ============================================================
# パッチ2: lr_excel.py  (write_numeric_sheet)
# ============================================================
"""
【変更場所】
    write_numeric_sheet() 内の「オリジナル3連対率」行（約823行目）の直後

【現在のコード（変更前）】
------------------------------------------------------------
    # オリジナル3連対率
    write_item_block(row, "数値指標", "コース別3連対率(%)", FILL_SEC_B, FILL_ITEM_B,
        build_waku_data(lambda rd: {
            int(r["waku"]): f"{round(r['abs_win3'], 1)}%" if r.get("abs_win3") is not None else None
            for r in rd.get("results", []) if str(r["waku"]).isdigit()
        }), missing_by_waku=missing_waku)
    row += 6

    # イン逃げ時2着率（1号艇は対象外のため表示なし）
------------------------------------------------------------

【変更後（「row += 6」の直後に以下を追加）】
------------------------------------------------------------
    # オリジナル3連対率
    write_item_block(row, "数値指標", "コース別3連対率(%)", FILL_SEC_B, FILL_ITEM_B,
        build_waku_data(lambda rd: {
            int(r["waku"]): f"{round(r['abs_win3'], 1)}%" if r.get("abs_win3") is not None else None
            for r in rd.get("results", []) if str(r["waku"]).isdigit()
        }), missing_by_waku=missing_waku)
    row += 6

    # ★追加: 3連対指数（会場×コース補正付き相対スコア 0〜100）
    # 色分け: 70以上=緑（有利）/ 40〜69=白（標準）/ 39以下=薄橙（不利）
    def _sanren_idx_fill(val):
        \"\"\"3連対指数の値に応じた背景色を返す\"\"\"
        v = safe_float(val)
        if v is None:
            return FILL_MISSING
        if v >= 70:
            return "FFE2EFDA"   # 薄緑（有利）
        if v >= 40:
            return "FFFFFFFF"   # 白（標準）
        return "FFFCE4D6"       # 薄橙（不利）

    # 通常の write_item_block は色分けに対応していないため直接書き込む
    for _i in range(6):
        _waku = _i + 1
        _dr   = row + _i
        if _waku == 1:
            wc(_dr, 1, "数値指標",    fill=sf(FILL_SEC_B),  font=fn(bold=True, color="FFFFFFFF"), align=al())
            wc(_dr, 2, "3連対指数",   fill=sf(FILL_ITEM_B), font=fn(bold=True, color="FF000000"), align=al("left"))
        else:
            wc(_dr, 1, None, fill=sf(FILL_SEC_B),  align=al())
            wc(_dr, 2, None, fill=sf(FILL_ITEM_B), align=al())
        wc(_dr, 3, str(_waku),
           fill=sf(BOAT_FILL[_waku]),
           font=fn(bold=True, color=BOAT_FONT[_waku]),
           align=al(), border=bdr)
        for _j, _rd in enumerate(all_race_data):
            _val = None
            for _r in _rd.get("results", []):
                if str(_r.get("waku")) == str(_waku):
                    _raw = _r.get("sanren_idx")
                    _val = f"{_raw:.0f}" if _raw is not None else None
                    break
            _fc = _sanren_idx_fill(_val)
            wc(_dr, 4 + _j, _val,
               fill=sf(_fc),
               font=fn(bold=(_val is not None and safe_float(_val, 0) >= 70), size=9),
               align=al(), border=bdr)
        ws.row_dimensions[_dr].height = 15.0
    row += 6
    # ★追加ここまで

    # イン逃げ時2着率（1号艇は対象外のため表示なし）
------------------------------------------------------------
"""


# ============================================================
# パッチ3: export_indices_csv.py
# ============================================================
"""
【変更場所①】PLAYER_KEYS リスト（約53行目付近）の末尾に2列追加

【変更前】
------------------------------------------------------------
    ("kimari",       "決まり手傾向"),
    ("kosetsu",      "今節成績"),
    ("vc_trust",     "会場別信頼度"),
]
------------------------------------------------------------

【変更後】
------------------------------------------------------------
    ("kimari",       "決まり手傾向"),
    ("kosetsu",      "今節成績"),
    ("vc_trust",     "会場別信頼度"),
    # ★追加: 3連対指数
    ("sanren_idx",      "3連対指数"),
    ("sanren_raw_ratio","3連対補正比"),
]
------------------------------------------------------------

【変更場所②】build_rows() 内の「# results キー」ブロック（自動的に出力される）
    PLAYER_KEYS に追加したキーは build_rows() 内の既存ループで自動的に処理されるため、
    build_rows() 自体への変更は不要。

【確認方法】
    python export_indices_csv.py  # 末尾の単体テストを実行
    → テスト出力の indices_log_test.csv に「3連対指数」「3連対補正比」列が
      追加されていることを確認する。
"""
