# Architecture fitness functions

Test one dependency rule: classes in `example.domain` must not depend on classes in `example.persistence`. Then freeze existing debt and show which later changes fail.

## Run the example

Use a JDK 21 installation (including the `jdk.compiler` module) and Python 3.10 or newer on macOS or Linux. Setup downloads three pinned JARs from Maven Central, about 5 MB in total. The checks themselves run locally, without accounts, containers, or a database.

From this directory:

```sh
java -version
python3 setup.py
python3 run.py
```

`setup.py` verifies the hashes recorded in `dependencies.json`. `run.py` compiles each fixture separately, runs the checks, and retains logs plus the violation store in a new `fitness-.../` directory. It leaves the source files unchanged. Remove that generated directory when you no longer need the evidence.

## Read the code

- `ArchitectureCheck.java` is the complete runnable class, with imports and the dependency rule. It uses ArchUnit's core API rather than a JUnit runner.
- `fixtures/clean/` has empty domain classes and passes the plain rule.
- `fixtures/legacy/` adds an `OrderRepository`-typed field to `OrderService`. That field violates the rule, even without calling a database.
- `fixtures/regression/` adds the same dependency to `CheckoutService`.

The runner compiles with the JDK compiler module, equivalent to `javac`. Its Java classpath includes the compiled fixture and the three JARs. Calling `ArchitectureCheck plain` runs the ordinary rule; `ArchitectureCheck frozen` wraps it with `FreezingArchRule.freeze(rule)`.

The baseline is created only in step 3 with `-Darchunit.freeze.store.default.allowStoreCreation=true`. Later steps use the same store with creation disabled. Step 6 removes the fixed violation; step 7 proves that restoring it fails again. Steps 8 and 9 deliberately demonstrate ways to weaken that protection: changing the rule description or refreezing current violations. Do not copy those operations into an automatic response to a failing CI job.

## Expected result

See `observed-output.txt` for output captured from the example on OpenJDK 21.0.12.1. All 10 checks should match their expected exit codes. A listed exit 1 is an intentional negative test, not a broken setup.

The raw failure for the legacy fixture names:

```text
Field <example.domain.OrderService.repository> has type <example.persistence.OrderRepository> in (OrderService.java:0)
```

Field dependencies lack a source line number in the class file, so this message reports line 0. The field and target type identify the offending edge. After baselining that field, the regression step reports only the new `CheckoutService.repository` violation.

The final locked-store check expects `StoreUpdateFailedException`: repairing debt requires removing it from the stored baseline, which a read-only store prevents.

These checks inspect the fixture's compiled classes. They do not measure traffic, latency, or a running Catio deployment.

## Dependencies and reference

ArchUnit 1.5.1 and SLF4J API/NOP 2.0.19 are pinned. For a larger project, declare `com.tngtech.archunit:archunit:1.5.1` through your build tool instead of maintaining the small download script. See the [ArchUnit user guide](https://www.archunit.org/userguide/html/000_Index.html#_freezing_arch_rules) for JUnit integration and freezing configuration.
