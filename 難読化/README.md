# JS Obfuscator ツール

JavaScript ファイルを一括難読化する Python ツールです。

---

## ファイル構成

```
js_obfuscator/
├── js_obfuscator.py        ← メインスクリプト（これを実行）
├── obfuscate_runner.js     ← Node.js 難読化エンジン（自動で使われる）
└── README.md               ← このファイル
```

---

## 必要なもの

| ツール | 確認コマンド |
|--------|-------------|
| Python 3.8 以上 | `python --version` |
| Node.js 14 以上 | `node --version` |
| npm | `npm --version` |

> `javascript-obfuscator` パッケージは **初回起動時に自動インストール** されます。

---

## 基本的な使い方

### ① フォルダに .js ファイルを置く

```
my_project/
├── top_stats.js
├── main.js
└── utils.js
```

### ② Python を起動する

```bash
# カレントディレクトリの .js を全て処理
python js_obfuscator.py

# 特定のフォルダを指定
python js_obfuscator.py ./my_project

# 出力先フォルダを別に指定
python js_obfuscator.py ./src ./dist
```

### ③ 出力確認

デフォルトでは元ファイル名に `_obf` が付いたファイルが生成されます。

```
my_project/
├── top_stats.js        ← 元ファイル（そのまま）
├── top_stats_obf.js    ← 難読化済み ✅
├── main.js
├── main_obf.js         ← 難読化済み ✅
...
```

---

## オプション一覧

```
python js_obfuscator.py [入力フォルダ] [出力フォルダ] [オプション]
```

| オプション | 説明 | 例 |
|-----------|------|-----|
| `--level` | 難読化レベル (`low` / `medium` / `high`) | `--level high` |
| `--suffix` | 出力ファイル名のサフィックス | `--suffix .min` |
| `--overwrite` | 元ファイルを上書き | `--overwrite` |
| `--recursive` | サブフォルダも再帰的に処理 | `--recursive` |
| `--exclude` | 除外するファイル名 | `--exclude bundle.js` |
| `--options` | 追加の難読化オプション (JSON) | `--options '{"seed":42}'` |

---

## 難読化レベルの違い

| レベル | 変換内容 | ファイルサイズ増加 | 実行速度への影響 |
|--------|---------|-----------------|----------------|
| `low` | 文字列配列化のみ | 小 | ほぼなし |
| `medium` (デフォルト) | 文字列 RC4 暗号化 + ヘックス識別子 | 中 | 軽微 |
| `high` | フロー難読化 + デッドコード注入 + セルフディフェンス | 大 | やや低下 |

---

## 使用例

```bash
# src フォルダを dist に出力（medium レベル）
python js_obfuscator.py ./src ./dist

# 高レベル難読化、元ファイルを上書き
python js_obfuscator.py ./src --level high --overwrite

# サブフォルダも含めて処理、特定ファイルを除外
python js_obfuscator.py ./src --recursive --exclude vendor.js polyfill.js

# カスタムオプションを追加（シード固定）
python js_obfuscator.py ./src --options '{"seed": 12345}'
```
