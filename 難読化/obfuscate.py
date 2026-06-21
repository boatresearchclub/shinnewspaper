#!/usr/bin/env python3
"""
obfuscate.py - ダブルクリックで起動、同フォルダ内のJSを自動難読化する
"""

import sys
import json
import subprocess
from pathlib import Path

RUNNER_JS = Path(__file__).parent / "obfuscate_runner.js"
EXCLUDE_DIR_NAMES = {"node_modules", ".git"}


def obfuscate(input_file: str, output_file: str) -> dict:
    if not RUNNER_JS.exists():
        raise FileNotFoundError(f"obfuscate_runner.js が見つかりません: {RUNNER_JS}")
    cmd = ["node", str(RUNNER_JS), input_file, output_file]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    output = (result.stdout or "").strip() or (result.stderr or "").strip()
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return {"success": False, "input": input_file, "error": output or "不明なエラー"}


def collect_js_files(root_dir: Path) -> list:
    files = []
    try:
        runner_resolved = RUNNER_JS.resolve()
    except OSError:
        runner_resolved = RUNNER_JS

    for path in root_dir.rglob("*.js"):
        if any(part in EXCLUDE_DIR_NAMES for part in path.relative_to(root_dir).parts[:-1]):
            continue
        try:
            if path.resolve() == runner_resolved:
                continue
        except OSError:
            pass
        files.append(path)
    return files


def main():
    input_dir = Path(__file__).parent
    output_dir = Path(r"C:\Users\user\Desktop\データ収集\scripts\難読化")

    js_files = collect_js_files(input_dir)

    if not js_files:
        print("対象となる .js ファイルが見つかりませんでした。")
        input("Enterキーで終了...")
        return

    print(f"{len(js_files)} 個の .js ファイルを難読化します。")
    print(f"出力先: {output_dir}\n")

    success_count = 0
    fail_count = 0
    total_in = 0
    total_out = 0
    errors = []

    for in_path in js_files:
        rel_path = in_path.relative_to(input_dir)
        out_path = output_dir / rel_path.parent / (in_path.stem + "_obf.js")
        out_path.parent.mkdir(parents=True, exist_ok=True)

        print(f"処理中: {rel_path} ...", end=" ")
        report = obfuscate(str(in_path), str(out_path))

        if report.get("success"):
            success_count += 1
            total_in += report.get("input_size", 0)
            total_out += report.get("output_size", 0)
            print("OK")
        else:
            fail_count += 1
            errors.append(f"{rel_path}: {report.get('error', '不明なエラー')}")
            print("失敗")

    ratio = (total_out / total_in * 100) if total_in > 0 else 0
    print(f"\n完了: 成功 {success_count} / {len(js_files)}、失敗 {fail_count}")
    print(f"サイズ: {total_in:,} bytes → {total_out:,} bytes ({ratio:.1f}%)")
    print(f"出力先: {output_dir}")

    if errors:
        print("\n--- エラー詳細 ---")
        for e in errors[:10]:
            print(e)

    input("\nEnterキーで終了...")


if __name__ == "__main__":
    main()
