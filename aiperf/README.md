# A four-request AIPerf CPU example

This example serves a real small language model through an OpenAI-compatible local chat adapter, then profiles four streaming requests with NVIDIA AIPerf. It demonstrates configuration, token accounting, saved results and cleanup. Four requests cannot establish production performance, capacity or cache benefits. It does not use vLLM, CUDA, a GPU or a paid inference provider.

## Prerequisites

- Apple silicon Mac running macOS; the recorded run used macOS 26.6.2 and 36 GiB RAM.
- Python **3.13.7** available as `python3`, plus standard macOS `sh`, `curl`, `tar`, `shasum`, `sysctl`, `ps` and `memory_pressure` commands.
- Internet access for public Node, npm, Python and model downloads during setup. Inference uses local files and loopback only.
- Several GB of free disk space for the runtime, packages and model; normal OS memory pressure, at least 25% reported memory headroom, no competing inference workload, and port **18761** free. The clean-install check's sampled maximum server RSS was about 1.05 GiB; that is not a total-machine memory requirement.

The setup installs **Node 24.22.2** locally; it does not replace system Node. Dependencies are locked to the recorded npm graph and Python package versions: Transformers.js **3.8.1**, ONNX Runtime Node **1.21.0**, AIPerf **0.13.0**. The model is official `HuggingFaceTB/SmolLM2-135M-Instruct`, revision `12fd25f77366fa6b3b4b768ec3050bf629380bac`, with a 137,147,981-byte q8 ONNX weight. All eight model/tokenizer asset hashes are checked. No account or API key is needed.

## Install, run and verify

Start in a fresh unpacked copy of this directory. Do not install over an earlier run.

```sh
python3 --version
shasum -a 256 -c SHA256SUMS
sh setup.sh
.venv/bin/python run.py
```

Setup stops after installation and hash checks; it does not load a model. `run.py` prints the unique output directory, for example `runs/20261101T090000Z-ab12cd34`. Substitute the actual printed path below:

```sh
RUN='runs/20261101T090000Z-ab12cd34'
.venv/bin/python verify.py "$RUN"
.runtime/node-v24.22.2-darwin-arm64/bin/node verify-tokenizer.mjs "$RUN"
cat "$RUN/evidence/cleanup.json"
cat "$RUN/evidence/profile-measured/profile_export_console.txt"
```

These verifiers are offline; the tokenizer verifier does not load a model. Expected acceptance is four successful records, unchanged file hashes, a clean server exit, absent owned process groups, a closed endpoint and empty server stderr. If a command fails, preserve the run directory and inspect `failure.txt`, `server.stderr` and `profile.stdout` before deciding what to change. Do not treat process exit alone as proof of a successful profile.

## What the runnable example does

`server.mjs` is the complete 54-line adapter used in the recorded run. It loads the local tokenizer and q8 model with two CPU threads, applies the model's chat template, and streams decoded text through `TextStreamer`. Usage reports the actual input tensor length and generated token callback count. It rejects concurrent requests, more than five generations, prompts above 512 tokens, and outputs above 32 tokens. It binds **only `127.0.0.1:18761`**. This is a small demonstration adapter, not a production inference service.

`run.py` creates a fresh directory and performs this sequence automatically; the commands below explain its actions and should not be run as extra requests alongside it:

1. **Start:** invoke `.runtime/node-v24.22.2-darwin-arm64/bin/node server.mjs` with a fresh run directory as the working directory, containing `evidence/` and links to the model/cache. The runner resolves the source's absolute path itself, so installed dependencies resolve correctly.
2. **Health:** bounded GET requests to `http://127.0.0.1:18761/health`, requiring `{"ready":true,"count":0}`. These do not generate text.
3. **Readiness:** exactly one POST to `/v1/chat/completions` with the payload below, then save the response in `evidence/readiness.json`.
4. **Profile:** launch the AIPerf command below. It makes four measured requests with concurrency one and no warmup/model-wait generation.
5. **Cleanup:** send SIGTERM to the owned server, await HTTP closure and model disposal, and wait for natural exit. Verify the recorded process groups are absent and port 18761 is closed. The runner has a 600-second inference deadline and bounded cleanup; forced termination fails validation.

Equivalent readiness request (shown to explain the request the runner already sends):

```sh
curl --fail --max-time 30 http://127.0.0.1:18761/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"HuggingFaceTB/SmolLM2-135M-Instruct","messages":[{"role":"user","content":"What is the capital of France?"}],"max_tokens":16,"stream":false}'
```

Profile command executed by the runner, with `ROOT` resolved to the package directory and the fresh run directory as its working directory:

```sh
HF_HUB_OFFLINE=1 HF_HUB_CACHE="$ROOT/hf-cache" \
TOKENIZERS_PARALLELISM=false OMP_NUM_THREADS=2 \
"$ROOT/.venv/bin/aiperf" profile \
  --model HuggingFaceTB/SmolLM2-135M-Instruct \
  --url http://127.0.0.1:18761 --endpoint-type chat --streaming \
  --tokenizer HuggingFaceTB/SmolLM2-135M-Instruct \
  --tokenizer-revision 12fd25f77366fa6b3b4b768ec3050bf629380bac \
  --synthetic-input-tokens-mean 128 --synthetic-input-tokens-stddev 0 \
  --output-tokens-mean 32 --output-tokens-stddev 0 \
  --concurrency 1 --request-count 4 --request-timeout-seconds 30 \
  --random-seed 17 --workers-max 1 --record-processor-service-count 1 \
  --no-gpu-telemetry --wait-for-model-timeout 0 --use-server-token-count \
  --artifact-dir evidence/profile-measured --no-auto-plot
```

Warmup is disabled by omitting warmup options; `--warmup-request-count 0` is invalid in AIPerf 0.13.0. Setup places the exact tokenizer files both in `model/` and in the task-local Hugging Face cache snapshot. The recorded offline AIPerf loader required the repository ID plus pinned revision, rather than an absolute tokenizer directory. Do not replace that tokenizer with an unrelated built-in tokenizer.

Cleanup corresponds to `kill -TERM "$SERVER_PID"` followed by `wait "$SERVER_PID"`, where the runner tracks only the PID it created. Use the runner rather than copying a guessed PID. The adapter clears its timer, awaits server closure and `model.dispose()`, and sets `process.exitCode`; it does not force an immediate exit on the normal cleanup path.

## Actual observed output and its limits

`observed-output.txt` contains literal selected rows from the genuine 2026-10-31 console export. `observed-results.json` summarizes that historical run:

- One readiness response and four measured responses; all four measured requests succeeded.
- Each prompt had 128 raw tokens and 158 tokens after the chat template; each measured response generated 32 tokens (128 measured output tokens total).
- AIPerf and server exited 0; server stderr was empty; both process groups were absent and the endpoint closed. Total runner time including cleanup was 20.19 seconds.

TextStreamer can buffer tokens before emitting text. Here TTFT is client time to the first emitted text chunk, not an instrumented timestamp for the model's first generated token. AIPerf's ITL is a derived per-token interval, not a trace of individual token/kernel emission times. Do not interpret this tiny configuration check as a cache or throughput comparison.

The original offline verifier incorrectly compared `profiling_index` with each request's row number. AIPerf defines it as the index among profiling phases; all four requests in this single-phase run correctly have index 0. `verify-phase-index.patch` records the one-line correction. Ordered payloads and conversation IDs are still checked independently. The original failure and raw run evidence have not been rewritten. The corrected offline check passed against the existing evidence; it does not represent another inference run.

## Validation status of this package

A fresh copy of this package passed installation and one end-to-end run on November 1, 2026, using the macOS and runtime versions above. Setup downloaded and hash-checked the pinned assets, ran `npm ci`, and installed the exact Python lock. Both offline verifiers passed; source, model and cache integrity stayed unchanged.

That check made one readiness request and four measured requests in 22.12 seconds including cleanup. Each measured input had 128 raw / 158 chat-templated tokens and generated 32 tokens. The maximum sampled server RSS was 1,126,793,216 bytes (about 1.05 GiB), not a continuously measured peak. Server and profiler exited 0; server stderr was empty, owned process groups were absent and the endpoint was closed.

The observed-output files above preserve the separate October 31 run, rather than mixing its timings with this clean-install check. The adapter is byte-identical to that original measured source; runner changes are explanatory comments only. Node/model binaries and dependencies are downloaded by setup, not bundled here.
