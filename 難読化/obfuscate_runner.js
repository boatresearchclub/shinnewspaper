const JavaScriptObfuscator = require('javascript-obfuscator');
const fs = require('fs');
const path = require('path');

const args = process.argv.slice(2);

if (args.length < 2) {
  console.log('Usage: node obfuscate_runner.js <inputFile> <outputFile> [optionsJSON]');
  process.exit(1);
}

const inputFile = args[0];
const outputFile = args[1];
const optionsArg = args[2] || null;
const logFile = path.join(path.dirname(outputFile), 'node_error_log.txt');

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
  stringArrayEncoding: ['base64'],
  stringArrayIndexShift: true,
  stringArrayRotate: true,
  stringArrayShuffle: true,
  stringArrayWrappersCount: 1,
  stringArrayWrappersChainedCalls: true,
  stringArrayWrappersParametersMaxCount: 2,
  stringArrayWrappersType: 'function',
  stringArrayThreshold: 0.75,
  unicodeEscapeSequence: false,
  seed: 0,
};

let options = defaultOptions;

if (optionsArg) {
  try {
    const custom = JSON.parse(optionsArg);
    options = Object.assign({}, defaultOptions, custom);
  } catch (_) {
    console.error('Warning: Failed to parse options JSON. Using default options.');
  }
}

try {
  const sourceCode = fs.readFileSync(inputFile, 'utf8');
  const result = JavaScriptObfuscator.obfuscate(sourceCode, options);
  const obfCode = result.getObfuscatedCode();
  fs.writeFileSync(outputFile, obfCode, 'utf8');

  const report = {
    success: true,
    input: inputFile,
    output: outputFile,
    input_size: Buffer.byteLength(sourceCode, 'utf8'),
    output_size: Buffer.byteLength(obfCode, 'utf8'),
  };

  process.stdout.write(JSON.stringify(report) + '\n');
  process.exit(0);
} catch (err) {
  const detail =
    '[ERROR] ' +
    new Date().toISOString() +
    '\nInput: ' +
    inputFile +
    '\n' +
    (err.stack || err.message) +
    '\n';

  try {
    fs.writeFileSync(logFile, detail, 'utf8');
  } catch (_) {}

  const report = {
    success: false,
    input: inputFile,
    error: err.message,
  };

  process.stderr.write(JSON.stringify(report) + '\n');
  process.exit(1);
}
