import pandas as pd
import pathlib

pkl_path = pathlib.Path(r"C:\Users\user\Desktop\データ収集\scripts\数値蓄積\びわこ.pkl")
csv_path = pkl_path.with_suffix(".csv")

df = pd.read_pickle(pkl_path)
df.to_csv(csv_path, index=False, encoding="utf-8-sig")
print(f"完了: {len(df)}行 → {csv_path.name}")