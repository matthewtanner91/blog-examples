# Dead code detection

A scheduled job can use an export even when the application's entry point does not. This small TypeScript project shows why the detector's roots matter before you delete code.

## Setup

Use Node.js 24 and Python 3.10 or newer on macOS or Linux. This example was tested with Node.js 24.22.1, npm 11.9.0, and Knip 6.44.0. Node runs these simple TypeScript files directly; no compilation step is needed.

```sh
npm ci --ignore-scripts --no-audit --no-fund
node src/index.ts
node jobs/reconcile.ts
```

The application should print `Application check passed: invoice total = 75`. The separately invoked job should print `Scheduled-job check passed: reconciled total = 100`. Each entry includes an assertion, so incorrect fixture behavior fails instead of merely printing a result.

## Compare the entry points

```sh
./node_modules/.bin/knip --config knip.incomplete.json --reporter json
./node_modules/.bin/knip --config knip.complete.json --reporter json
```

Both commands intentionally return exit code 1 because unused code remains. Do not chain them with `&&` if you want to see both reports.

With only `src/index.ts` as an entry, the report lists `jobs/reconcile.ts` as unused and flags `reconcileLedger` and `obsoleteCsvPath`. The complete configuration adds `jobs/reconcile.ts`; only `obsoleteCsvPath` remains. The job's code did not change. Its consumer became visible to the analyzer.

Inspect `src/billing.ts`: `obsoleteCsvPath` only returns a string, and neither entry calls it. For this constructed project, that is the candidate to remove. A real application's public consumers and side effects need their own review.

## Verify the removal

```sh
python3 verify.py
```

The verifier runs both entry checks, asserts the exact before/after Knip findings, creates a copy under a new `dead-code-.../` directory, and removes only `obsoleteCsvPath` there. It then requires Knip to exit 0 and both entry outputs to remain unchanged. The original source stays intact. The generated directory contains the JSON reports and edited copy; remove it when finished reviewing.

See `observed-output.txt` for the captured result. This is a local fixture, not a live scheduler or a Sourcegraph execution. For the entry-point model and its limitations, see [Knip configuration](https://knip.dev/explanations/entry-files).
