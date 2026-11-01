# Optimize a typed support-ticket classifier with DSPy

This example takes a small classifier through the full loop: run it, give GEPA feedback, compare the resulting program on validation data, then check the frozen choice on held-out tickets. You can inspect every request and score in the output directory.

## Set up

Use Python3.13 on macOS or Linux and an OpenAI API account with access to `gpt-6-luna`. The verified environment was Python3.13.7 on macOS ARM64. This example uses a hosted model, so you do not need Docker or a GPU. The CLI uses a Unix timeout signal; it is not a native Windows launcher.

From this downloaded example directory:

```sh
python3.13 -m venv .venv
.venv/bin/python -m pip install --only-binary=:all: -r requirements-lock.txt
.venv/bin/python -m pip check
```

The lock pins DSPy3.4.1, GEPA0.1.4 and the full tested dependency set. For the exact tested macOS ARM64 wheel hashes, replace the install command with:

```sh
.venv/bin/python -m pip install --only-binary=:all: --require-hashes -r requirements-macos-arm64-hashed.txt
```

## Give the model a small, explicit job

The complete runnable code is in `program.py`; `dataset.json` contains six training, three validation and three test tickets. Each ticket belongs to exactly one category. The typed signature makes that contract explicit:

```python
class TicketLabel(dspy.Signature):
    """Classify a support ticket as billing, technical, or account."""
    ticket: str = dspy.InputField()
    category: Literal["billing", "technical", "account"] = dspy.OutputField()
```

The program wraps this signature in `dspy.Predict` and uses `JSONAdapter`. Its metric checks the label and returns feedback such as “Incorrect. Expected billing for this support ticket.” GEPA uses that feedback to propose a more useful instruction.

Before compiling, the runner checks a duplicate-charge ticket and asks the actual InstructionProposer to revise an instruction from a deliberately incorrect billing example. These two checks confirm the model can produce the structured outputs the optimizer needs.

## Run the example

```sh
.venv/bin/python -I run.py results
```

Enter the key at the hidden prompt. The program uses the OpenAI Responses API with temperature0, reasoning disabled and response storage disabled. The key stays in memory and is excluded from saved program state and logs. The reusable transport enforces a maximum32 requests,4096 reserved output tokens and a $0.10 planning ceiling. Prices are pinned in `pricing.json`; check current OpenAI pricing before adapting the model or limits.

The optimizer uses this configuration:

```python
optimizer = dspy.GEPA(
    metric=metric,
    max_metric_calls=12,
    num_threads=1,
    reflection_lm=reflection,
    reflection_minibatch_size=2,
    skip_perfect_score=False,
    use_merge=False,
    track_stats=True,
    log_dir=None,
    use_wandb=False,
    use_mlflow=False,
    seed=42,
)
candidate = optimizer.compile(baseline, trainset=trainset, valset=valset)
```

`program.py` contains the complete metric, LM setup and orchestration behind this excerpt. It reuses GEPA's initial full-validation baseline scores only after checking the exact row IDs, inputs and metric. It then evaluates the returned candidate, keeps the baseline on a tie, records that decision, and finally evaluates both programs on the held-out set. Test results never influence the choice.

## Check what happened

After a successful run, the CLI prints:

```text
Completed. Read result.jsonl, selection-frozen.jsonl and evaluations.jsonl in the output directory.
```

Open the saved decision:

```sh
python3 -m json.tool results/selection-frozen.jsonl
```

In our run, the baseline and returned program both scored3/3 on validation. GEPA proposed three alternative instructions and evaluated each on a two-ticket batch, but none improved the score. The baseline therefore stayed selected. Baseline and selected program also answered all three held-out tickets correctly.

That is a useful outcome: the optimizer exercised the proposal-and-evaluation loop without replacing a working instruction merely because a longer one was available. Three test tickets are a quick functionality check. Before applying this to a real support queue, expand the examples to cover ambiguous requests and the mistakes your current classifier makes.

The pinned GEPA version recorded15 native metric calls with the nominal `max_metric_calls=12` setting because work is evaluated in batches. The transport's request/token limits are the independent spending controls. This example's recorded sequence used29 successful model calls,7191input tokens and661output tokens, costing about$0.00105 at the recorded prices. Your model outputs can differ.

The program saves credential-free JSON state and loads it into the same `Classifier` structure. It verifies the signature and demonstrations match and reattaches the in-memory LM without another model request. See DSPy's [state-only saving guide](https://dspy.ai/current/tutorials/saving/).

## Try the recorded sequence without an API key

```sh
.venv/bin/python -I test_replay.py
```

This runs native GEPA against saved responses with DNS/network calls blocked. It verifies all29 serialized requests match the real run byte-for-byte, plus selection and state loading. It is an offline replay, not a new model evaluation.

If the live run stops with an API-credit error, check the account's API billing. If it stops on structured output or a limit, inspect the saved diagnostic/result files before deciding whether to run a new experiment. The runner never retries a failed request automatically. Use a new output-directory name only when you intentionally want another paid run.

No background server or cloud resource remains after the command exits. You can delete this example's `.venv` and generated results when finished; keep any result/state files you want to compare later.
