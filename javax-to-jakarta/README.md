# Javax to Jakarta migration companion

A five-file synthetic fixture demonstrates a servlet migration across source, binary, resource and runtime boundaries. It runs Tomcat 9.0.123 / Servlet 4 and Tomcat 10.1.61 / Servlet 6, both on JDK 17. Tomcat is not a complete Jakarta EE platform implementation.

## Requirements and run

Use macOS or another Unix-like environment, JDK 17 (both `java` and `javac`), Maven 3.6.3 or newer, and Python 3.7 or newer with its standard library. The Python minimum reflects required APIs, not testing of every supported version. Timeout cleanup uses Unix process groups. The recorded macOS run used OpenJDK 17.0.19, Maven 3.9.12 and Python 3.13.7; other environments are not represented as tested here. No Docker, GPU, account or API key is needed.

From the root of a fresh repository copy:

```sh
cd javax-to-jakarta
java -version
mvn -version
python3 --version
python3 verify.py
```

Maven downloads pinned public dependencies through normal HTTPS if they are not cached. The dependency plugin is pinned to 3.8.1. Keep TLS verification enabled. If Maven selects another JDK, select your existing JDK 17 for this shell before running; do not alter the source to hide a version failure.

The script creates `work/` and `evidence/`, refuses to overwrite an existing `work/`, and binds application listeners only to `127.0.0.1` on ephemeral ports. Use a fresh extracted copy for another run. Do not use Python `-O`, which disables assertions. Each subprocess has a 180-second timeout and process-group cleanup.

## Expected and observed outcomes

The positive response for both runtimes is:

```text
name=pilot;sql=javax.sql.DataSource;initializer=discovered
```

The v3 run on October 30, 2026 completed all 18 recorded command checks in 23.63 seconds. The deliberate invalid Java SE compile returned exit 1; the remaining 17 commands returned 0. A negative test passing means the intended failure was observed, not that the broken application is healthy.

| Mutation | Observed result |
|---|---|
| Replace retained `javax.sql` with invalid `jakarta.sql` | Compilation rejected |
| Retain stale reflection property | HTTP 500, `REFLECTION_MISSING` |
| Retain stale service-provider filename | HTTP 200, `initializer=null` |
| Retain old shared binary | HTTP 500, `NoSuchMethodError` |

`observed/results.json` and corresponding logs preserve the actual results. Personal task paths have been replaced with `<fixture-root>` or `<user-home>`. No run was repeated to package this download.

The v3 runtime logs contain no `SEVERE` startup errors. They do contain three module-access shutdown warnings for each of five probes (15 total). These are retained rather than suppressed; the fixture does not broaden JVM module access. Recorded cleanup left no owned processes or listeners. An earlier v2 run with startup-configuration errors is not the evidence delivered here.

## What the code covers

The driver resolves runtime dependencies, compiles the shared JAR, servlet and runner separately, builds WAR resources, and probes the actual packaged application. `WEB-INF/lib` contains the shared library rather than container API JARs. The runner creates the Host appBase and disables unused default embedded mappings while retaining application `web.xml` and service-provider processing.

Only `javax.servlet.` in the three relevant Java sources is transformed. Resource names, XML namespace/version and runtime versions are generated explicitly. `javax.sql` remains unchanged. This is a bounded demonstrator, not a general migration algorithm, production acceptance suite, transformation-tool benchmark or binary redistribution recommendation. It does not cover a database, persistence, CDI, JSP/EL, authentication or external services.

All five executable/source files are byte-identical to the verified v3 run. `SHA256SUMS.json` covers delivered files. The article's boundary diagram is explanatory; machine-readable outputs and actual logs are the execution evidence.
