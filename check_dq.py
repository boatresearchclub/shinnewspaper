import json, glob, sys

files = glob.glob('data/history_*.json')
if not files:
    print("data/history_*.json が見つかりません")
    sys.exit()

f = sorted(files)[0]
print("確認ファイル:", f)
d = json.load(open(f, encoding='utf-8'))
v = list(d.keys())[0]
print("会場:", v)
r1 = d[v]['races']['1']
for b in r1['boats']:
    print("  艇", b['boat'], "dq=", b['dq'], "base_rate=", b.get('base_rate'))