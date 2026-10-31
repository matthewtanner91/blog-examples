# Debugging microservices local fixture

Requires Python 3.12 and Git on Linux. No package installation, Docker, cloud account, API key, or external service is needed. Tested with Python 3.12.14 on Linux x86_64. Other platforms are not claimed tested; the harness uses Unix process groups and SIGALRM.

## Run

1. Extract this package into a disposable local directory.
2. Read `run.py`. It creates files and three Git repositories in a new `run-<UTC timestamp>` subdirectory, starts three loopback-only HTTP services per phase, and makes seven synthetic GET requests.
3. Run `python3 run.py` from this directory. Git must be on the system executable path.
4. Open the emitted `EVIDENCE_DIR` and inspect `receipt.json`. Success is `PASS_LOCAL_ONLY`, seven requests, `children_exited: true`, and all port checks `closed: true`.
5. Compare `requests.json`, `revisions.json`, `deployments/*/*/manifest.json`, service `events.jsonl`, `local-emitter-search.txt`, and `candidate-diff.txt`. The full local repositories are in `repos/`.

## Expected checks

- Baseline checkout: 200 and `can_order: true`.
- Changed warehouse representation: contract-specific 502.
- Direct warehouse probe: 200 with string `available: "7"`.
- Deliberately stopped warehouse: transport-specific 502.
- Restored integer representation: three checkout requests return 200.

Each run creates new commits and chooses new ports. Read its manifests rather than copying the article's original run SHAs. The harness records exact committed source hashes and cleans up its own children on normal completion, errors, SIGINT, and SIGTERM; it also sets a 45-second timeout. SIGKILL or a machine crash cannot run cleanup. If interrupted abruptly, inspect only the PIDs in your run's manifests and verify process identity before stopping anything. Remove your disposable run directory when finished.

## Safety and boundaries

All services bind to 127.0.0.1. They have no authentication and must not be exposed publicly. Requests use synthetic constant data; there is no real order, payment, inventory, database, or warehouse. Ambient proxies and HTTP redirects are disabled; child processes receive a minimal environment, not inherited credentials. Synthetic full-response logging is not a production logging policy.

The package executes local Git searches and HTTP checks only. It does not install Sourcegraph, connect or publish repositories, invoke Deep Search, or execute the separate public Sourcegraph application/SDK exercise. That exercise inspects source at pinned revisions; it is not deployment or runtime proof for this fixture.
