# Webhook receiver security companion

Run a local HTTP fixture that checks payload integrity, schema and account validation, timestamp boundaries, duplicate delivery, rotation and retry behavior. It uses only synthetic events and public test-vector values.

## Requirements and run

Python 3.7 or newer with its standard library is required by the APIs used. The recorded run used CPython 3.12.14 on Linux x86_64; other Python versions are not represented as tested. No packages, credentials, provider account, cloud service or scanner are required.

Clone or extract this repository into a directory you can write to. From the repository root, run:

```sh
cd webhook-security
python3 --version
python3 verify_github.py
python3 receiver_fixture.py
```

Do not use Python `-O`; assertions are part of the checks. The first command script prints:

```text
PASS: public vector; changed bytes rejected; missing signature rejected
```

The receiver binds a temporary loopback listener, sends its own test requests, shuts down the server, prints JSON and writes `runtime-results.json` beside the source. That generated file is overwritten on a repeat run; the original recorded evidence in `observed/` is not changed.

## Read the results

Expect `passed: 29`, `total: 29` and `server_stopped: true`. Inspect each case's status, outcome and side-effect count; a rejected request must have no business effect. Positive controls run before and after negative cases. Eight concurrent duplicate deliveries produce one applied event and seven duplicate responses.

The 29-case observed result in `observed/runtime-results.json` was captured on October 30, 2026. The original JSON output and public-vector output are also included. Packaging did not rerun the test. `SHA256SUMS.json` covers all delivered files except itself; the two Python sources are unchanged from the verified fixture.

## Boundaries that matter

- `verify_github.py` implements GitHub-style HMAC-SHA256 validation over exact raw bytes and uses GitHub's public test vector. The receiver's JSON envelope is application-owned synthetic data, not a real GitHub event schema.
- The timestamped route models Stripe's signed-input shape with an injected clock. It accepts only one timestamp and one v1 signature and adds a fixture-specific 30-second future-skew limit. It is not a complete Stripe verifier or a universal webhook protocol.
- Synthetic constants labeled `LOCAL_FIXTURE_ONLY` and `RETIRED_LOCAL_FIXTURE_SECRET` are not credentials. Never use them in a deployed receiver.
- The timestamp tolerance is 300 seconds, the body limit is 4,096 bytes, and state is in memory. Production systems need provider-supported parsing, durable atomic idempotency and appropriate retention/retry rules.
- Tests cover authentication, schema, account authorization and business effects. They do not run StackHawk, call GitHub/Stripe, test a production service or prove end-to-end provider delivery.

There is no product UI to photograph in this fixture. The actual response/status and side-effect records are the useful output.
