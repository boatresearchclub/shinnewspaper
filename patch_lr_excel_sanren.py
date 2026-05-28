    # ★追加: 3連対指数（会場×コース補正付き相対スコア 0〜100）
    # ────────────────────────────────────────────────────────────────────
    # 挿入位置:
    #   「# オリジナル3連対率」の write_item_block + row += 6 の直後、
    #   「# イン逃げ時2着率」の write_item_block の直前
    #
    # 色分けルール:
    #   70以上 = 薄緑（このメンバー内で有利）
    #   40〜69 = 白  （標準）
    #   39以下 = 薄橙（不利・データ不足）
    # ────────────────────────────────────────────────────────────────────
    def _sanren_idx_fill(val):
        v = safe_float(val)
        if v is None:
            return FILL_MISSING
        if v >= 70:
            return "FFE2EFDA"   # 薄緑
        if v >= 40:
            return "FFFFFFFF"   # 白
        return "FFFCE4D6"       # 薄橙

    for _i in range(6):
        _waku = _i + 1
        _dr   = row + _i
        if _waku == 1:
            wc(_dr, 1, "数値指標",
               fill=sf(FILL_SEC_B), font=fn(bold=True, color="FFFFFFFF"), align=al())
            wc(_dr, 2, "3連対指数",
               fill=sf(FILL_ITEM_B), font=fn(bold=True, color="FF000000"), align=al("left"))
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
    # ★追加ここまで ─────────────────────────────────────────────────────
