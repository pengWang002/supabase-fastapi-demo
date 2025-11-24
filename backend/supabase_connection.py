"""
Basic Supabase connectivity checks using the current backend/.env.
Run: python test_supabase_connection.py

Steps:
- Load required env vars (SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY).
- Hit Supabase auth health endpoint.
- Fetch JWKS using the same fallbacks as the FastAPI app.
- Query the profiles table with the service role key (read-only select, no mutations).
Exit code is non-zero if any step fails.
"""

import os
from typing import Dict, Optional, Tuple

import httpx
from dotenv import load_dotenv
from supabase import Client, create_client

REQUIRED_VARS = ["SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY"]


def mask(value: Optional[str]) -> str:
    """Mask secrets when printing."""
    if not value:
        return "<empty>"
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}***{value[-4:]}"


def load_env() -> Dict[str, str]:
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))
    env = {k: os.getenv(k, "") for k in REQUIRED_VARS}
    missing = [k for k, v in env.items() if not v]
    if missing:
        raise RuntimeError(f"Missing env vars: {', '.join(missing)}")
    env["SUPABASE_URL"] = env["SUPABASE_URL"].rstrip("/")
    return env


def check_health(url: str, anon_key: str) -> Dict:
    health_url = f"{url}/auth/v1/health"
    resp = httpx.get(health_url, headers={"apikey": anon_key}, timeout=5.0)
    resp.raise_for_status()
    return resp.json()


def fetch_jwks(url: str, anon_key: str) -> Tuple[str, Dict]:
    candidates = [
        os.getenv("SUPABASE_JWKS_URL"),
        f"{url}/auth/v1/keys",
        f"{url}/auth/v1/jwks",
        f"{url}/.well-known/jwks.json",
    ]
    headers = {"apikey": anon_key} if anon_key else {}
    last_error: Optional[Exception] = None
    for candidate in candidates:
        if not candidate:
            continue
        try:
            resp = httpx.get(candidate, headers=headers, timeout=5.0)
            resp.raise_for_status()
            jwks = resp.json()
            if jwks.get("keys"):
                return candidate, jwks
        except Exception as exc:  # pylint: disable=broad-except
            last_error = exc
            continue
    raise RuntimeError(f"Failed to fetch JWKS: {last_error}")


def check_profiles_table(client: Client) -> int:
    res = client.table("profiles").select("id").limit(1).execute()
    return len(res.data or [])


def main() -> int:
    try:
        env = load_env()
    except Exception as exc:  # pylint: disable=broad-except
        print(f"[env] ❌ {exc}")
        return 1

    print("[env] ✅ loaded required vars")
    for key, value in env.items():
        print(f"  - {key}: {mask(value)}")

    supabase_url = env["SUPABASE_URL"]
    anon_key = env["SUPABASE_ANON_KEY"]
    service_role_key = env["SUPABASE_SERVICE_ROLE_KEY"]

    try:
        health = check_health(supabase_url, anon_key)
        print(f"[health] ✅ {supabase_url}/auth/v1/health -> {health}")
    except Exception as exc:  # pylint: disable=broad-except
        print(f"[health] ❌ {exc}")
        return 1

    try:
        jwks_url, jwks = fetch_jwks(supabase_url, anon_key)
        print(f"[jwks] ✅ fetched from {jwks_url}, keys={len(jwks.get('keys', []))}")
    except Exception as exc:  # pylint: disable=broad-except
        print(f"[jwks] ❌ {exc}")
        return 1

    try:
        client = create_client(supabase_url, service_role_key)
        rows = check_profiles_table(client)
        print(f"[database] ✅ profiles table reachable (rows previewed: {rows})")
    except Exception as exc:  # pylint: disable=broad-except
        print(f"[database] ❌ {exc}")
        return 1

    print("All Supabase connectivity checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
