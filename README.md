# Blog examples

Eight self-contained tutorial companions. Read each example's requirements, run instructions and limitations before running it in a disposable local copy.

| Example | What it demonstrates |
| --- | --- |
| [JUnit 4 to JUnit 5](junit4-to-junit5/) | Migrate a mixed-engine test suite while preserving test identities and outcomes. |
| [Javax to Jakarta](javax-to-jakarta/) | Check source, binary, resource and runtime migration boundaries. |
| [Webhook security](webhook-security/) | Exercise local signature validation, replay handling, rotation and retry behavior. |
| [Debugging microservices](debugging-microservices/) | Trace synthetic requests across local services and compare deployed revisions. |
| [DSPy tutorial](dspy-tutorial/) | Optimize a typed classifier with validation and held-out evaluation, or replay the recorded requests offline. |
| [Dead code detection](dead-code-detection/) | Compare analyzer entry points and verify removal of an unused export. |
| [Architecture fitness functions](architecture-fitness-functions/) | Enforce a dependency rule and test a frozen baseline of existing violations. |
| [AIPerf CPU example](aiperf/) | Profile four local streaming model requests and verify token accounting, saved results and cleanup. |

The first three examples include recorded outputs and SHA-256 manifests. Those records describe prior runs; cloning this repository does not run or revalidate them. The microservices fixture generates fresh local evidence when run. Platform requirements differ by example.

Use a checkout path without whitespace for the JUnit example. Run the commands in each example's README from the stated directory. These fixtures use synthetic data and are educational examples, not production services.

## License

[MIT](LICENSE), copyright 2026 Matt Tanner.
