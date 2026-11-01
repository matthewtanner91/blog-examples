"""Download the three version-pinned libraries from Maven Central."""
import hashlib
import json
from pathlib import Path
import urllib.request

root = Path(__file__).resolve().parent
(root / "lib").mkdir(exist_ok=True)
for item in json.loads((root / "dependencies.json").read_text()):
    path = root / "lib" / item["file"]
    if path.exists():
        data = path.read_bytes()
    else:
        with urllib.request.urlopen(item["url"], timeout=60) as response:
            data = response.read()
    if hashlib.sha256(data).hexdigest() != item["sha256"]:
        raise SystemExit(f"Checksum mismatch: {item['file']}")
    if not path.exists():
        path.write_bytes(data)
    print(f"Verified {item['file']}")
