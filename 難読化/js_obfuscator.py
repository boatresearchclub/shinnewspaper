#!/usr/bin/env python3
"""
js_obfuscator.py
================
フォルダ内の .js ファイルを一括難読化するツール。

使い方:
    python js_obfuscator.py                        # カレントディレクトリの .js を処理
    python js_obfuscator.py ./src                  # ./src フォルダを処理
    python js_obfuscator.py ./src ./dist           # 出力先を ./dist に指定
    python js_obfuscator.py ./src --suffix _obf    # ファイル名に _obf を付ける
    python js_obfuscator.py ./src --overwrite      # 元ファイルを上書き
    python js_obfuscator.py ./src --level high     # 難読化レベルを変更 (low/medium/high)
    python js_obfuscator.py ./src --exclude min.js # 特定ファイルを除外
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# ──────────────────────────────────────────
# 難読化レベル別オプション
# ──────────────────────────────────────────
OBFUSCATION_PROFILES = {
    "low": {
        "compact": True,
        "controlFlowFlattening": False,
        "deadCodeInjection": False,
        "identifierNamesGenerator": "hexadecimal",
        "stringArray": True,
        "stringArrayCallsTransform": False,
        "stringArrayEncoding": [],
        "stringArrayThreshold": 0.5,
        "renameGlobals": False,
        "selfDefending": False,
    },
    "medium": {
        "compact": True,
        "controlFlowFlattening": False,
        "deadCodeInjection": False,
        "identifierNamesGenerator": "hexadecimal",
        "stringArray": True,
        "stringArrayCallsTransform": True,
        "stringArrayEncoding": ["rc4"],
        "stringArrayIndexShift": True,
        "stringArrayRotate": True,
        "stringArrayShuffle": True,
        "stringArrayWrappersCount": 1,
        "stringArrayWrappersChainedCalls": True,
        "stringArrayWrappersParametersMaxCount": 2,
        "stringArrayWrappersType": "variable",
        "stringArrayThreshold": 0.75,
        "renameGlobals": False,
        "selfDefending": False,
        "simplify": True,
        "unicodeEscapeSequence": False,
    },
    "high": {
        "compact": True,
        "controlFlowFlattening": True,
        "controlFlowFlatteningThreshold": 0.75,
        "deadCodeInjection": True,
        "deadCodeInjectionThreshold": 0.4,
        "identifierNamesGenerator": "hexadecimal",
        "stringArray": True,
        "stringArrayCallsTransform": True,
        "stringArrayEncoding": ["rc4"],
        "stringArrayIndexShift": True,
        "stringArrayRotate": True,
        "stringArrayShuffle": True,
        "stringArrayWrappersCount": 2,
        "stringArrayWrappersChainedCalls": True,
        "stringArrayWrappersParametersMaxCount": 4,
        "stringArrayWrappersType": "function",
        "stringArrayThreshold": 1.0,
        "renameGlobals": False,
        "selfDefending": True,
        "simplify": True,
        "unicodeEscapeSequence": False,
        "numbersToExpressions": True,
        "splitStrings": True,
        "splitStringsChunkLength": 10,
    },
}

# ──────────────────────────────────────────
# ユーティリティ
# ──────────────────────────────────────────
def find_node() -> str:
    """node コマンドのパスを返す。見つからなければ終了。"""
    node = shutil.which("node")
    if not node:
        print("❌ Node.js が見つかりません。https://nodejs.org からインストールしてください。")
        sys.exit(1)
    return node


def find_runner_js() -> Path:
    """obfuscate_runner.js のパスを返す（このスクリプトと同じディレクトリ）。"""
    script_dir = Path(__file__).parent
    runner = script_dir / "obfuscate_runner.js"
    if not runner.exists():
        print(f"❌ obfuscate_runner.js が見つかりません: {runner}")
        print("   js_obfuscator.py と同じフォルダに obfuscate_runner.js を置いてください。")
        sys.exit(1)
    return runner


def ensure_npm_package(node: str, package_dir: Path):
    """javascript-obfuscator がインストールされているか確認し、なければ自動インストール。"""
    node_modules = package_dir / "node_modules" / "javascript-obfuscator"
    if node_modules.exists():
        return
    print("📦 javascript-obfuscator をインストール中...")
    npm = shutil.which("npm")
    if not npm:
        print("❌ npm が見つかりません。Node.js を再インストールしてください。")
        sys.exit(1)
    result = subprocess.run(
        [npm, "install", "javascript-obfuscator", "--prefix", str(package_dir)],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print("❌ npm install に失敗しました:")
        print(result.stderr)
        sys.exit(1)
    print("✅ インストール完了")


def obfuscate_file(node: str, runner: Path, input_path: Path, output_path: Path,
                   options: dict) -> dict:
    """1ファイルを難読化して結果 dict を返す。"""
    options_json = json.dumps(options)
    result = subprocess.run(
        [node, str(runner), str(input_path), str(output_path), options_json],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding='utf-8',
        errors='replace',
        timeout=120
    )
    stdout = result.stdout or ""
    stderr = result.stderr or ""
    if result.returncode == 0:
        try:
            return json.loads(stdout.strip())
        except json.JSONDecodeError:
            return {"success": True, "input": str(input_path), "output": str(output_path)}
    else:
        # 出力ファイルが実際に生成されていれば成功とみなす
        if output_path.exists() and output_path.stat().st_size > 0:
            return {
                "success": True,
                "input": str(input_path),
                "output": str(output_path),
                "input_size": input_path.stat().st_size,
                "output_size": output_path.stat().st_size,
            }
        err_msg = stderr.strip() or stdout.strip() or "不明なエラー"
        try:
            return json.loads(err_msg)
        except json.JSONDecodeError:
            return {"success": False, "input": str(input_path), "error": err_msg}


def collect_js_files(input_dir: Path, recursive: bool, exclude: list[str]) -> list[Path]:
    """ディレクトリから .js ファイルを収集する。"""
    pattern = "**/*.js" if recursive else "*.js"
    files = [
        f for f in input_dir.glob(pattern)
        if f.is_file() and f.name not in exclude
    ]
    return sorted(files)


def format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024*1024):.1f} MB"


# ──────────────────────────────────────────
# メイン処理
# ──────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="JavaScript ファイルを一括難読化するツール",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument("input_dir", nargs="?", default=".",
                        help="処理するフォルダ (デフォルト: カレントディレクトリ)")
    parser.add_argument("output_dir", nargs="?", default=None,
                        help="出力先フォルダ (省略時は input_dir と同じ)")
    parser.add_argument("--suffix", default="_obf",
                        help="出力ファイル名に付けるサフィックス (デフォルト: _obf)")
    parser.add_argument("--overwrite", action="store_true",
                        help="元ファイルを上書きする (--suffix を無視)")
    parser.add_argument("--level", choices=["low", "medium", "high"], default="medium",
                        help="難読化レベル (デフォルト: medium)")
    parser.add_argument("--recursive", "-r", action="store_true",
                        help="サブフォルダも再帰的に処理する")
    parser.add_argument("--exclude", nargs="*", default=[],
                        help="除外するファイル名 (例: --exclude min.js bundle.js)")
    parser.add_argument("--options", default=None,
                        help="追加の難読化オプション JSON 文字列")
    args = parser.parse_args()

    # パスの設定
    input_dir = Path(args.input_dir).resolve()
    if not input_dir.is_dir():
        print(f"❌ フォルダが見つかりません: {input_dir}")
        sys.exit(1)

    output_dir = Path(args.output_dir).resolve() if args.output_dir else input_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    # Node.js / runner の確認
    node = find_node()
    runner = find_runner_js()
    runner_dir = runner.parent
    ensure_npm_package(node, runner_dir)

    # 難読化オプションの組み立て
    options = dict(OBFUSCATION_PROFILES[args.level])
    if args.options:
        try:
            custom = json.loads(args.options)
            options.update(custom)
        except json.JSONDecodeError as e:
            print(f"❌ --options の JSON が不正です: {e}")
            sys.exit(1)

    # ファイル収集
    js_files = collect_js_files(input_dir, args.recursive, args.exclude)
    if not js_files:
        print(f"⚠️  処理対象の .js ファイルが見つかりません: {input_dir}")
        sys.exit(0)

    print(f"\n🔐 JS Obfuscator")
    print(f"   入力フォルダ : {input_dir}")
    print(f"   出力フォルダ : {output_dir}")
    print(f"   難読化レベル : {args.level}")
    print(f"   対象ファイル : {len(js_files)} 件")
    print(f"   上書きモード : {'はい' if args.overwrite else 'いいえ (サフィックス: ' + args.suffix + ')'}")
    print()

    # 難読化ループ
    success_count = 0
    fail_count = 0
    total_in = 0
    total_out = 0

    for js_file in js_files:
        # 出力パスの決定
        rel = js_file.relative_to(input_dir)
        if args.overwrite:
            out_path = output_dir / rel
        else:
            stem   = js_file.stem
            suffix = js_file.suffix
            out_path = output_dir / rel.parent / f"{stem}{args.suffix}{suffix}"

        out_path.parent.mkdir(parents=True, exist_ok=True)

        label = str(rel)
        print(f"  ▶ {label}", end=" ... ", flush=True)

        report = obfuscate_file(node, runner, js_file, out_path, options)

        if report.get("success"):
            in_sz  = report.get("input_size",  js_file.stat().st_size)
            out_sz = report.get("output_size", out_path.stat().st_size)
            ratio  = out_sz / in_sz * 100 if in_sz > 0 else 0
            total_in  += in_sz
            total_out += out_sz
            print(f"✅  {format_size(in_sz)} → {format_size(out_sz)} ({ratio:.0f}%)")
            success_count += 1
        else:
            err = report.get("error", "不明なエラー")
            print(f"❌  失敗: {err}")
            # エラーログをファイルに書き出す
            log_path = output_dir / "error_log.txt"
            with open(log_path, "a", encoding="utf-8") as lf:
                lf.write(f"[FAILED] {js_file}\n{err}\n\n")
            fail_count += 1

    # サマリー
    print()
    print("─" * 50)
    print(f"  完了: {success_count} 件  失敗: {fail_count} 件")
    if success_count > 0:
        ratio = total_out / total_in * 100 if total_in > 0 else 0
        print(f"  合計サイズ: {format_size(total_in)} → {format_size(total_out)} ({ratio:.0f}%)")
    print(f"  出力先: {output_dir}")
    print()


if __name__ == "__main__":
    import traceback
    log_path = Path(__file__).parent / "error_log.txt"
    try:
        main()
    except Exception as e:
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(traceback.format_exc())
        print(f"\n❌ エラーが発生しました。詳細は error_log.txt を確認してください。")
        print(f"   {log_path}")
    input("\nEnterキーで閉じる...")
