"""Compile three small fixtures and demonstrate the reviewed-baseline ratchet."""
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent
work = Path(tempfile.mkdtemp(prefix="fitness-", dir=ROOT))
libs = os.pathsep.join(str(p) for p in sorted((ROOT / "lib").glob("*.jar")))
if len(list((ROOT / "lib").glob("*.jar"))) != 3:
    raise SystemExit("Run python3 setup.py first.")
results = []
for variant in ("clean", "legacy", "regression"):
    out = work / variant
    out.mkdir()
    sources = [ROOT / "ArchitectureCheck.java", *sorted((ROOT / "fixtures" / variant).rglob("*.java"))]
    subprocess.run(["java", "-m", "jdk.compiler/com.sun.tools.javac.Main", "-cp", libs,
                    "-d", str(out), *map(str, sources)], check=True, timeout=30)

def check(label, variant, expected, frozen=False, properties=None, renamed=False, contains=None):
    props = {"freeze.store.default.path": str(work / "store"),
             "freeze.store.default.allowStoreCreation": "false"}
    props.update(properties or {})
    cmd = ["java", *[f"-Darchunit.{k}={v}" for k, v in props.items()],
           "-cp", os.pathsep.join([str(work / variant), libs]), "ArchitectureCheck",
           "frozen" if frozen else "plain"]
    if renamed:
        cmd.append("renamed")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, cwd=work)
    (work / f"{label}.stdout.txt").write_text(result.stdout)
    (work / f"{label}.stderr.txt").write_text(result.stderr)
    assert result.returncode == expected, (label, result.returncode, result.stderr)
    if contains:
        assert contains in result.stderr, (label, result.stderr)
    if expected == 0:
        assert result.stdout.strip() == "PASS", (label, result.stdout)
    results.append({"step": label, "variant": variant, "exit": result.returncode})
    print(f"{label}: exit {result.returncode} (expected {expected})")
    return result

check("01-clean", "clean", 0)
check("02-violation", "legacy", 1, contains="OrderService.repository")
check("03-baseline", "legacy", 0, True, {"freeze.store.default.allowStoreCreation": "true"})
check("04-known-debt", "legacy", 0, True)
r = check("05-regression", "regression", 1, True, contains="CheckoutService.repository")
assert "OrderService.repository" not in r.stderr
check("06-repair", "clean", 0, True)
check("07-reintroduced", "legacy", 1, True, contains="OrderService.repository")
check("08-renamed", "legacy", 0, True, renamed=True)
check("09-refreeze", "regression", 0, True, {"freeze.refreeze": "true"})
check("10-locked-repair", "clean", 1, True,
      {"freeze.store.default.allowStoreUpdate": "false"}, contains="StoreUpdateFailedException")
(work / "results.json").write_text(json.dumps(results, indent=2) + "\n")
print("All 10 checks matched the expected result.")
print(f"Logs and violation store: {work.name}/")
