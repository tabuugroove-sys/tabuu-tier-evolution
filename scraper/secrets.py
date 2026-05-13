"""
Secret retrieval via Bitwarden CLI.

Usage:
    from secrets import get_secret
    api_key = get_secret("TABUU Upload-Post API")

Requires:
    - `bw` CLI installed and logged in (`bw login`)
    - BW_SESSION env var set, OR `bw unlock` was run in current shell
"""
import os
import subprocess
import sys


def _bw_session():
    """Get an unlocked BW session token. Falls back to interactive unlock."""
    if os.environ.get("BW_SESSION"):
        return os.environ["BW_SESSION"]

    # Check status: if locked, ask user to unlock
    status = subprocess.run(
        ["bw", "status"], capture_output=True, text=True
    )
    if '"status":"unauthenticated"' in status.stdout:
        print("[secrets] Bitwarden CLI is not logged in.", file=sys.stderr)
        print("[secrets] Run once:  bw login", file=sys.stderr)
        sys.exit(1)
    if '"status":"locked"' in status.stdout:
        print("[secrets] Vault is locked. Unlock it:", file=sys.stderr)
        print('[secrets]   export BW_SESSION="$(bw unlock --raw)"', file=sys.stderr)
        sys.exit(1)
    return None  # unlocked, no explicit session needed


def get_secret(item_name, field="password"):
    """
    Fetch a secret from Bitwarden by item name.

    field: "password" (default), "username", or any custom field name.
    """
    session = _bw_session()
    env = os.environ.copy()
    if session:
        env["BW_SESSION"] = session

    if field in ("password", "username"):
        cmd = ["bw", "get", field, item_name]
    else:
        # Custom field — fetch full item JSON, parse it
        import json
        cmd = ["bw", "get", "item", item_name]
        result = subprocess.run(cmd, capture_output=True, text=True, env=env)
        if result.returncode != 0:
            raise RuntimeError(f"bw get failed: {result.stderr}")
        item = json.loads(result.stdout)
        for f in item.get("fields", []) or []:
            if f.get("name") == field:
                return f["value"]
        raise KeyError(f"Custom field '{field}' not found on item '{item_name}'")

    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        raise RuntimeError(f"bw get {field} '{item_name}' failed: {result.stderr.strip()}")
    return result.stdout.strip()


if __name__ == "__main__":
    # Quick smoke test: python3 secrets.py "Item Name"
    if len(sys.argv) < 2:
        print("Usage: python3 secrets.py <item_name> [field]")
        sys.exit(0)
    name = sys.argv[1]
    field = sys.argv[2] if len(sys.argv) > 2 else "password"
    print(get_secret(name, field))
