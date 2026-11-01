"""Compare detector roots and test a removal in a disposable copy."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent
work = Path(tempfile.mkdtemp(prefix="dead-code-", dir=ROOT))
knip = ROOT / "node_modules/.bin/knip"

def run(args, cwd=ROOT, expected=0):
    result = subprocess.run(list(map(str, args)), cwd=cwd, capture_output=True, text=True, timeout=30)
    assert result.returncode == expected, (args, result.returncode, result.stderr, result.stdout)
    return result.stdout

def analyze(config, label, cwd=ROOT, expected=1):
    output = run([knip, "--config", config, "--reporter", "json"], cwd, expected)
    (work / f"{label}.json").write_text(output)
    report = json.loads(output)
    exports = {v["name"] for issue in report["issues"] for v in issue.get("exports", [])}
    files = {v["name"] for issue in report["issues"] for v in issue.get("files", [])}
    return exports, files

def behavior(cwd, label):
    app = run(["node", "src/index.ts"], cwd)
    job = run(["node", "jobs/reconcile.ts"], cwd)
    (work / f"{label}.txt").write_text(app + job)
    return app + job

before = behavior(ROOT, "before")
exports, files = analyze("knip.incomplete.json", "incomplete")
assert exports == {"reconcileLedger", "obsoleteCsvPath"}
assert files == {"jobs/reconcile.ts"}
print("Incomplete roots: jobs/reconcile.ts; reconcileLedger; obsoleteCsvPath")
exports, files = analyze("knip.complete.json", "complete")
assert exports == {"obsoleteCsvPath"} and files == set()
print("Complete roots: obsoleteCsvPath only")
copy = work / "after-removal"
copy.mkdir()
for name in ("src", "jobs"):
    shutil.copytree(ROOT / name, copy / name)
for name in ("package.json", "knip.complete.json"):
    shutil.copy2(ROOT / name, copy / name)
(copy / "node_modules").symlink_to(ROOT / "node_modules", target_is_directory=True)
source = copy / "src/billing.ts"
obsolete = '\nexport function obsoleteCsvPath(): string {\n  return "legacy-invoices.csv";\n}\n'
text = source.read_text()
assert text.count(obsolete) == 1
source.write_text(text.replace(obsolete, ""))
exports, files = analyze("knip.complete.json", "after-removal", copy, 0)
assert exports == set() and files == set()
assert behavior(copy, "after") == before
print("After removal: no Knip issues")
print(before.strip())
print("Before/after application and scheduled-job outputs match.")
print(f"Reports and edited copy: {work.name}/")
