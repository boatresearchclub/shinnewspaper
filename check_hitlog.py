# -*- coding: utf-8 -*-
import json, pathlib

data = json.loads(pathlib.Path('hit_log.json').read_text(encoding='utf-8'))
records = data['records']
known   = sum(1 for r in records if r.get('result_known'))
unknown = len(records) - known

print(f"総レコード数      : {len(records)}")
print(f"result_known=True : {known}")
print(f"result_known=False: {unknown}")
print()

if records:
    print("=== サンプル（先頭3件）===")
    for r in records[:3]:
        print(r)
