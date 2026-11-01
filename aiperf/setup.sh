#!/bin/sh
set -eu
[ "$(uname -s)" = Darwin ] && [ "$(uname -m)" = arm64 ] || { echo 'Requires Apple silicon macOS'; exit 1; }
[ "$(python3 --version)" = 'Python 3.13.7' ] || { echo 'Use Python 3.13.7 for this recipe'; exit 1; }
for entry in .runtime .venv model hf-cache node_modules receipts; do
  [ ! -e "$entry" ] || { echo "Use a fresh unpacked directory: $entry already exists"; exit 1; }
done
mkdir .runtime model
curl -fL --max-time 180 https://nodejs.org/dist/v24.22.2/node-v24.22.2-darwin-arm64.tar.gz -o .runtime/node.tar.gz
printf '%s  %s\n' aa9549349e47dffaa42dcf95d6e06ade8c4bdafc980979883b88767670df385a .runtime/node.tar.gz | shasum -a 256 -c -
tar -xzf .runtime/node.tar.gz -C .runtime
export PATH="$PWD/.runtime/node-v24.22.2-darwin-arm64/bin:$PATH"
[ "$(node --version)" = v24.22.2 ]
export npm_config_cache="$PWD/.runtime/npm-cache"
export PIP_CACHE_DIR="$PWD/.runtime/pip-cache"
npm ci
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock.txt
base=https://huggingface.co/HuggingFaceTB/SmolLM2-135M-Instruct/resolve/12fd25f77366fa6b3b4b768ec3050bf629380bac
mkdir model/onnx
while read -r hash file; do curl -fL --max-time 180 "$base/$file" -o "model/$file"; done < model-SHASUMS256.txt
(cd model && shasum -a 256 -c ../model-SHASUMS256.txt)
snapshot=hf-cache/models--HuggingFaceTB--SmolLM2-135M-Instruct/snapshots/12fd25f77366fa6b3b4b768ec3050bf629380bac
mkdir -p "$snapshot"
for file in config.json generation_config.json tokenizer.json tokenizer_config.json special_tokens_map.json merges.txt vocab.json; do cp "model/$file" "$snapshot/$file"; done
mkdir receipts
node --version > receipts/node-version.txt
.venv/bin/python --version > receipts/python-version.txt
.venv/bin/python -m pip freeze > receipts/python-packages.txt
npm ls --all --json > receipts/npm-packages.json
shasum -a 256 server.mjs run.py setup.sh package-lock.json > receipts/source-before.sha256
