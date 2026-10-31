# JUnit 4 to JUnit 5 migration companion

Run a small mixed-engine suite, migrate its legacy tests, then remove Vintage and JUnit 4 while checking that the same tests and outcomes remain. The negative control demonstrates why a green build alone does not prove that all tests ran.

## Requirements

- JDK 17 and Maven 3.9.12. The runner checks both, including the JDK Maven uses.
- Python 3.7 or newer with its standard library; the recorded run used Python 3.13.7. The minimum reflects the APIs used, not a claim that every Python version was tested.
- A Unix-like shell for the `ci.sh` replay. Recorded platform: macOS arm64, OpenJDK 17.0.19.
- Network access to Maven Central for pinned dependencies not already cached. No account, API key, server or paid service is used.

The POM pins the JUnit BOM to 5.14.4, JUnit 4 to 4.13.2, Surefire to 3.5.3 and the compiler plugin to 3.14.1. Compilation targets Java 8 bytecode; this does not claim a Java 8 runtime test.

## Run

Clone or extract this repository into a new directory whose full path contains no whitespace. The runner passes its Maven-cache path through `MAVEN_ARGS` without quoting, so paths containing spaces are not supported by this unchanged tested source. From the repository root, run:

```sh
cd junit4-to-junit5
java -version
mvn -version
python3 --version
python3 run_checks.py --run
```

The script creates `run-output/` with disposable projects, a local Maven cache, command logs, Surefire XML and result summaries. It refuses an existing `run-output/`; use another fresh extracted copy for a second run. Do not run with Python optimization (`-O`). Keep normal TLS validation enabled if dependency downloads fail.

## Read the results

Each stage runs `mvn -B -ntp clean verify`; the local CI replay invokes the same command through `baseline/ci.sh`.

| Stage | Expected passed | Expected skipped/aborted | What it verifies |
|---|---:|---:|---|
| Mixed baseline | 5 | 2 | Both classes run |
| Local CI-script replay | 5 | 2 | Same identities/outcomes |
| Legacy category filter | 1 | 0 | Only `LegacyTest.doublesQuantity` |
| Jupiter-only negative control | 3 | 0 | Legacy tests disappear despite a green build |
| Converted, with Vintage | 5 | 2 | Converted cases preserve the contract |
| Converted tag filter | 1 | 0 | Same selected case |
| Converted, without Vintage | 5 | 2 | Full contract remains |
| Converted, without JUnit 4 | 5 | 2 | Full contract remains |

All eight stages were observed locally on October 30, 2026. `observed/` contains the original result values, case identities and Maven output; personal task-directory paths in logs are replaced with `<fixture-root>`. These are recorded results, not a new run performed when the ZIP was packaged. A complete run preserves both `intentional fixture skip` and `no integration target`. Parameter indexes `[1]` and `[2]` come from XML; the input values are defined by `@ValueSource`.

When running a filter manually, quote `'-Dgroups=example.LegacyTest$Smoke'` so the shell does not expand `$Smoke`.

## Files and boundaries

`baseline/` contains the POM, CI script and original two test classes. `LegacyTest.converted.java` contains the migrated legacy class. `run_checks.py` constructs each stage without modifying those sources. `SHA256SUMS.json` covers every delivered file except itself.

This fixture tests its own cases and build settings. It does not establish compatibility for arbitrary runners, Spring transactions, integration tests, Failsafe, hosted CI or a production application. Review those separately before removing a legacy engine from a real project. No screenshots are required to reproduce this command-line fixture; the machine-readable cases and actual logs expose the evidence directly.
