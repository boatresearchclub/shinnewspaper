/**
 * obfuscate_runner.js
 * Pythonから呼び出される難読化実行スクリプト
 * 引数: <input_file> <output_file> [options_json]
 */

const JavaScriptObfuscator = require('javascript-obfuscator');
const fs = require('fs');
const path = require('path');

const args = process.argv.slice(2);
if (args.length < 2) {
  console.error('Usage: node obfuscate_runner.js <input> <output> [options_json]');
  process.exit(1);
}

const inputFile  = args[0];
const outputFile = args[1];
const optionsArg = args[2] || null;

// エラーログの書き出し先（出力ファイルと同じフォルダ）
const logFile = path.join(path.dirname(outputFile), 'node_error_log.txt');

// デフォルトオプション（元の難読化ファイルと同等のスタイル）
const defaultOptions = {
  compact: true,
  controlFlowFlattening: false,
  deadCodeInjection: false,
  debugProtection: false,
  disableConsoleOutput: false,
  identifierNamesGenerator: 'hexadecimal',
  log: false,
  numbersToExpressions: false,
  renameGlobals: false,
  selfDefending: false,
  simplify: true,
  splitStrings: false,
  stringArray: true,
  stringArrayCallsTransform: true,
  stringArrayEncoding: ['rc4'],
  stringArrayIndexShift: true,
  stringArrayRotate: true,
  stringArrayShuffle: true,
  stringArrayWrappersCount: 1,
  stringArrayWrappersChainedCalls: true,
  stringArrayWrappersParametersMaxCount: 2,
  stringArrayWrappersType: 'variable',
  stringArrayThreshold: 0.75,
  unicodeEscapeSequence: false,
  seed: 0
};

// カスタムオプションがあればマージ
let options = defaultOptions;
if (optionsArg) {
  try {
    const custom = JSON.parse(optionsArg);
    options = Object.assign({}, defaultOptions, custom);
  } catch (e) {
    console.error('Warning: Failed to parse options JSON, using defaults.');
  }
}

try {
  const sourceCode = fs.readFileSync(inputFile, 'utf8');
  const result = JavaScriptObfuscator.obfuscate(sourceCode, options);
  const obfCode = result.getObfuscatedCode();
  fs.writeFileSync(outputFile, obfCode, 'utf8');

  // 成功レポートをJSONで出力
  const report = {
    success: true,
    input: inputFile,
    output: outputFile,
    input_size: Buffer.byteLength(sourceCode, 'utf8'),
    output_size: Buffer.byteLength(obfCode, 'utf8')
  };
  process.stdout.write(JSON.stringify(report) + '\n');
  process.exit(0);
} catch (err) {
  // エラー内容をログファイルに書き出す
  const detail = `[ERROR] ${new Date().toISOString()}\nFile: ${inputFile}\n${err.stack || err.message}\n`;
  try { fs.writeFileSync(logFile, detail, 'utf8'); } catch(_) {}

  const report = {
    success: false,
    input: inputFile,
    error: err.message
  };
  process.stderr.write(JSON.stringify(report) + '\n');
  process.exit(1);
}
