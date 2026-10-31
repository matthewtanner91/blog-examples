import hashlib
import hmac
import re


def valid_github_signature(raw_body, signature, secret):
    if not isinstance(signature, str):
        return False
    if not re.fullmatch(r"sha256=[0-9a-f]{64}", signature):
        return False
    expected = "sha256=" + hmac.new(
        secret, raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


if __name__ == "__main__":
    # Public GitHub test vector; never use this secret in production.
    secret = b"It's a Secret to Everybody"
    body = b"Hello, World!"
    signature = (
        "sha256=757107ea0eb2509fc211221cce984b8a3"
        "7570b6d7586c22c46f4379c8b043e17"
    )
    assert valid_github_signature(body, signature, secret)
    assert not valid_github_signature(body + b"\n", signature, secret)
    assert not valid_github_signature(body, "", secret)
    print("PASS: public vector; changed bytes rejected; missing signature rejected")
