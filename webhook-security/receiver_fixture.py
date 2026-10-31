"""Loopback-only synthetic fixture. Not a production server or provider SDK.

GitHub-style signatures wrap an application-owned synthetic envelope, not a
real GitHub event schema. The timestamped route models Stripe's documented
signed input, with an explicit additional future-skew policy of 30 seconds.
The timestamped route is not a complete Stripe verifier. No account is used.
"""
import concurrent.futures
import hashlib
import hmac
import http.client
import json
import platform
import re
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from verify_github import valid_github_signature

SECRET = b"LOCAL_FIXTURE_ONLY_NOT_A_PRODUCTION_SECRET"
OLD_SECRET = b"RETIRED_LOCAL_FIXTURE_SECRET"
NOW = 1_700_000_000  # injected clock, not wall-clock freshness
MAX_BODY = 4096
TOLERANCE = 300
FUTURE_SKEW = 30


def github_signature(raw, secret=SECRET):
    return "sha256=" + hmac.new(secret, raw, hashlib.sha256).hexdigest()


def timestamp_signature(raw, timestamp=NOW, secret=SECRET):
    signed = str(timestamp).encode("ascii") + b"." + raw
    digest = hmac.new(secret, signed, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={digest}"


def verify_timestamped(raw, header, secrets):
    # Narrow fixture accepts one timestamp and one v1 signature only.
    match = re.fullmatch(r"t=([0-9]{1,12}),v1=([0-9a-f]{64})", header)
    if not match:
        return False
    timestamp = int(match[1])
    signed = match[1].encode("ascii") + b"." + raw
    authenticated = any(hmac.compare_digest(
        hmac.new(secret, signed, hashlib.sha256).hexdigest(), match[2]
    ) for secret in secrets)
    return authenticated and -FUTURE_SKEW <= NOW - timestamp <= TOLERANCE


class State:
    def __init__(self):
        self.lock = threading.Lock()
        self.reset()

    def reset(self):
        self.effects = []
        self.seen = set()
        self.secrets = (SECRET,)
        self.fail_before_commit = False
        self.bytes_read = 0


STATE = State()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def respond(self, code, outcome):
        body = json.dumps({"outcome": outcome}).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        self.connection.settimeout(2)
        if self.path not in ("/github", "/timestamped"):
            return self.respond(404, "unknown_route")
        if self.headers.get("Transfer-Encoding"):
            return self.respond(400, "unsupported_framing")
        length = self.headers.get("Content-Length", "")
        if not length.isascii() or not length.isdecimal():
            return self.respond(411, "length_required")
        length = int(length)
        if length > MAX_BODY:
            return self.respond(413, "body_too_large")
        try:
            raw = self.rfile.read(length)
        except TimeoutError:
            return self.respond(408, "read_timeout")
        with STATE.lock:
            STATE.bytes_read += len(raw)
        if len(raw) != length:
            return self.respond(400, "incomplete_body")
        if self.path == "/github":
            header = self.headers.get("X-Hub-Signature-256", "")
            verified = any(valid_github_signature(raw, header, s) for s in STATE.secrets)
        else:
            header = self.headers.get("Stripe-Signature", "")
            verified = verify_timestamped(raw, header, STATE.secrets)
        if not verified:
            return self.respond(401, "authentication_rejected")
        try:
            event = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            return self.respond(400, "json_rejected")
        required = {"event_id", "account", "type", "version", "label"}
        if (not isinstance(event, dict) or set(event) != required
                or any(not isinstance(event[k], str) for k in required - {"version"})
                or type(event["version"]) is not int
                or event["version"] != 1
                or event["type"] != "fixture.invoice_paid"
                or not event["event_id"]):
            return self.respond(422, "schema_rejected")
        if event["account"] != "acct_demo":
            return self.respond(403, "account_rejected")
        key = (event["account"], event["event_id"])
        with STATE.lock:
            if key in STATE.seen:
                outcome, code = "duplicate", 200
            elif STATE.fail_before_commit:
                outcome, code = "retryable_failure", 503
            else:
                STATE.seen.add(key)
                STATE.effects.append(key)
                outcome, code = "applied", 200
        return self.respond(code, outcome)


def payload(**changes):
    event = {"event_id": "evt_local_001", "account": "acct_demo",
             "type": "fixture.invoice_paid", "version": 1, "label": "café"}
    event.update(changes)
    return json.dumps(event, ensure_ascii=False, separators=(",", ":")).encode()


def run():
    rows = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_port

    def request(raw, signature, path="/github"):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        header = "X-Hub-Signature-256" if path == "/github" else "Stripe-Signature"
        headers = {"Content-Type": "application/json"}
        if signature is not None:
            headers[header] = signature
        try:
            conn.request("POST", path, body=raw, headers=headers)
            response = conn.getresponse()
            return {"status": response.status, **json.loads(response.read())}
        finally:
            conn.close()

    def case(name, raw, signature, expected, effects=0, path="/github"):
        STATE.reset()
        actual = request(raw, signature, path)
        row = {"case": name, "expected_status": expected, **actual,
               "expected_effects": effects, "actual_effects": len(STATE.effects),
               "bytes_read": STATE.bytes_read}
        row["pass"] = actual["status"] == expected and len(STATE.effects) == effects
        rows.append(row)
        assert row["pass"], row

    raw = payload()
    sig = github_signature(raw)
    try:
        case("valid_utf8_positive", raw, sig, 200, 1)
        case("altered_body", raw.replace(b"paid", b"void"), sig, 401)
        case("wrong_secret", raw, github_signature(raw, OLD_SECRET), 401)
        case("missing_signature", raw, None, 401)
        case("malformed_signature", raw, "sha256=not-hex", 401)
        case("unsupported_scheme", raw, sig.replace("sha256=", "sha1="), 401)
        case("whitespace_change", raw + b"\n", sig, 401)
        reencoded = json.dumps(json.loads(raw), ensure_ascii=True).encode()
        case("json_reserialized", reencoded, sig, 401)
        case("truncated_signature", raw, sig[:-1], 401)
        case("positive_after_negatives", raw, sig, 200, 1)
        case("signed_malformed_json", b"{", github_signature(b"{"), 400)
        for name, obj in [
            ("missing_field", {k:v for k,v in json.loads(raw).items() if k != "version"}),
            ("extra_field", {**json.loads(raw), "admin": True}),
            ("wrong_type", {**json.loads(raw), "version": "1"}),
            ("unsupported_version", {**json.loads(raw), "version": 2}),
            ("unexpected_event", {**json.loads(raw), "type": "fixture.user_deleted"}),
        ]:
            body = json.dumps(obj).encode()
            case(name, body, github_signature(body), 422)
        other = payload(account="acct_other_synthetic")
        case("signed_cross_account", other, github_signature(other), 403)
        large = b"x" * (MAX_BODY + 1)
        case("early_oversized_rejection", large, github_signature(large), 413)
        assert rows[-1]["bytes_read"] == 0
        for name, delta, expected in [
            ("timestamp_current", 0, 200),
            ("timestamp_inside_window", -299, 200),
            ("timestamp_at_boundary", -300, 200),
            ("timestamp_outside_window", -301, 401),
            ("future_at_fixture_skew_limit", 30, 200),
            ("future_outside_fixture_skew_limit", 31, 401),
        ]:
            case(name, raw, timestamp_signature(raw, NOW + delta), expected,
                 int(expected == 200), "/timestamped")
        altered_time = timestamp_signature(raw, NOW - 301).replace(str(NOW - 301), str(NOW))
        case("modified_signed_timestamp", raw, altered_time, 401, path="/timestamped")
        STATE.reset()
        first = request(raw, timestamp_signature(raw), "/timestamped")
        retry = request(raw, timestamp_signature(raw, NOW + 1), "/timestamped")
        row = {"case": "freshly_signed_retry_same_event", "responses": [first, retry],
               "actual_effects": len(STATE.effects), "expected_effects": 1}
        row["pass"] = first["outcome"] == "applied" and retry["outcome"] == "duplicate" and len(STATE.effects) == 1
        rows.append(row)
        assert row["pass"], row
        STATE.reset()
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            responses = list(executor.map(lambda _: request(raw, sig), range(8)))
        row = {"case": "concurrent_duplicate_deliveries", "requests": 8,
               "applied": sum(x["outcome"] == "applied" for x in responses),
               "duplicates": sum(x["outcome"] == "duplicate" for x in responses),
               "actual_effects": len(STATE.effects), "expected_effects": 1}
        row["pass"] = row["applied"] == 1 and row["duplicates"] == 7 and len(STATE.effects) == 1
        rows.append(row)
        assert row["pass"], row
        STATE.reset()
        STATE.secrets = (OLD_SECRET, SECRET)
        old = request(raw, github_signature(raw, OLD_SECRET))
        STATE.secrets = (SECRET,)
        retired = request(payload(event_id="evt_local_002"), github_signature(payload(event_id="evt_local_002"), OLD_SECRET))
        current = request(payload(event_id="evt_local_002"), github_signature(payload(event_id="evt_local_002")))
        row = {"case": "fixture_rotation_overlap_then_retirement", "responses": [old, retired, current],
               "actual_effects": len(STATE.effects), "expected_effects": 2}
        row["pass"] = [x["status"] for x in row["responses"]] == [200, 401, 200] and len(STATE.effects) == 2
        rows.append(row)
        assert row["pass"], row
        STATE.reset()
        STATE.fail_before_commit = True
        failed = request(raw, sig)
        before = len(STATE.effects)
        STATE.fail_before_commit = False
        recovered = request(raw, sig)
        row = {"case": "failure_then_legitimate_retry", "responses": [failed, recovered],
               "effects_after_failure": before, "actual_effects": len(STATE.effects)}
        row["pass"] = failed["status"] == 503 and recovered["outcome"] == "applied" and before == 0 and len(STATE.effects) == 1
        rows.append(row)
        assert row["pass"], row
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    report = {"captured_utc": datetime.now(timezone.utc).isoformat(),
              "python": platform.python_version(), "system": platform.platform(),
              "scope": "Loopback synthetic fixture; no provider account, provider SDK, production target or StackHawk scanner",
              "clock": NOW, "past_tolerance_seconds": TOLERANCE,
              "future_skew_seconds_fixture_policy": FUTURE_SKEW,
              "body_limit_bytes": MAX_BODY, "server_stopped": not thread.is_alive(),
              "cases": rows, "passed": sum(x["pass"] for x in rows), "total": len(rows)}
    assert report["server_stopped"]
    output = Path(__file__).parent / "runtime-results.json"
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    run()
