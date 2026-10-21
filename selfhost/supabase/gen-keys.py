#!/usr/bin/env python3
"""Generate the secrets the self-hosted stack needs (JEG-792). Stdlib only.

    python3 gen-keys.py --write .env     # create .env from .env.example (mode 600)
    python3 gen-keys.py                  # print KEY=VALUE lines to stdout
    python3 gen-keys.py --verify .env    # check the JWTs in .env against JWT_SECRET

Generates POSTGRES_PASSWORD, JWT_SECRET, and two HS256 JWTs signed with it:
ANON_KEY (role anon) and SERVICE_ROLE_KEY (role service_role), shaped like
Supabase's legacy API keys (iss "supabase", iat, exp). PostgREST switches to
the role in the `role` claim; service_role bypasses RLS.

--write refuses to overwrite an existing file. Nothing is sent anywhere.
"""

import argparse
import base64
import hashlib
import hmac
import json
import os
import secrets
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEN_YEARS = 10 * 365 * 24 * 3600


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def b64url_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def sign_jwt(payload: dict, secret: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    signing_input = (b64url(json.dumps(header, separators=(",", ":")).encode()) + "."
                     + b64url(json.dumps(payload, separators=(",", ":")).encode()))
    sig = hmac.new(secret.encode(), signing_input.encode(), hashlib.sha256).digest()
    return signing_input + "." + b64url(sig)


def verify_jwt(token: str, secret: str) -> dict:
    """Return the payload if the HS256 signature and exp are valid, else raise."""
    try:
        h, p, s = token.split(".")
    except ValueError:
        raise ValueError("not a three-part JWT")
    if json.loads(b64url_decode(h)).get("alg") != "HS256":
        raise ValueError("alg is not HS256")
    expected = hmac.new(secret.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(expected, b64url_decode(s)):
        raise ValueError("bad signature")
    payload = json.loads(b64url_decode(p))
    if payload.get("exp", 0) <= time.time():
        raise ValueError("expired")
    return payload


def generate() -> dict:
    jwt_secret = secrets.token_urlsafe(48)  # 64 chars; PostgREST needs >= 32
    now = int(time.time())

    def key(role):
        return sign_jwt({"iss": "supabase", "role": role, "iat": now,
                         "exp": now + TEN_YEARS}, jwt_secret)

    return {
        "POSTGRES_PASSWORD": secrets.token_urlsafe(32),
        "JWT_SECRET": jwt_secret,
        "ANON_KEY": key("anon"),
        "SERVICE_ROLE_KEY": key("service_role"),
    }


def read_env(path: Path) -> dict:
    out = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def verify_env(path: Path) -> int:
    env = read_env(path)
    secret = env.get("JWT_SECRET", "")
    if len(secret) < 32 or secret.startswith("<"):
        print("JWT_SECRET missing or shorter than 32 chars", file=sys.stderr)
        return 1
    ok = True
    for name, role in (("ANON_KEY", "anon"), ("SERVICE_ROLE_KEY", "service_role")):
        try:
            payload = verify_jwt(env.get(name, ""), secret)
        except Exception as e:  # noqa: BLE001
            print(f"{name}: INVALID ({e})", file=sys.stderr)
            ok = False
            continue
        if payload.get("role") != role:
            print(f"{name}: role claim is {payload.get('role')!r}, want {role!r}", file=sys.stderr)
            ok = False
        else:
            print(f"{name}: ok (role={role}, exp={time.strftime('%Y-%m-%d', time.gmtime(payload['exp']))})")
    return 0 if ok else 1


def write_env(path: Path, values: dict) -> int:
    if path.exists():
        print(f"{path} exists; not overwriting. Move it aside first.", file=sys.stderr)
        return 1
    template = (HERE / ".env.example").read_text()
    lines = []
    for line in template.splitlines():
        k = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else None
        lines.append(f"{k}={values[k]}" if k in values else line)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"wrote {path} (mode 600). SERVICE_ROLE_KEY is the value for the "
          "SUPABASE_SERVICE_KEY GitHub secret.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--write", metavar="PATH", help="create an env file from .env.example")
    g.add_argument("--verify", metavar="PATH", help="verify the JWTs in an env file")
    args = ap.parse_args()
    if args.verify:
        return verify_env(Path(args.verify))
    values = generate()
    if args.write:
        return write_env(Path(args.write), values)
    for k, v in values.items():
        print(f"{k}={v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
