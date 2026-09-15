"""Check local prerequisites for the sfdc-mcp-poc lab.

Prints pass/fail per check. Never prints secret values (tokens, keys) --
only presence/absence of required environment variables.

Usage:
    python scripts/verify_environment.py --org devOrg1
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys

MIN_PYTHON = (3, 11)
SF_CMD = shutil.which("sf")  # PATHEXT (sf.cmd) isn't resolved without this on Windows


def check_python_version() -> bool:
    ok = sys.version_info >= MIN_PYTHON
    got = f"{sys.version_info.major}.{sys.version_info.minor}"
    print(f"[{'OK' if ok else 'FAIL'}] Python >= {'.'.join(map(str, MIN_PYTHON))} (found {got})")
    return ok


def check_sf_cli() -> bool:
    if SF_CMD is None:
        print("[FAIL] sf CLI not found on PATH")
        return False
    proc = subprocess.run([SF_CMD, "--version"], capture_output=True, text=True)
    ok = proc.returncode == 0
    print(f"[{'OK' if ok else 'FAIL'}] sf CLI installed ({proc.stdout.strip()})")
    return ok


def check_org_auth(org: str) -> bool:
    if SF_CMD is None:
        print("[FAIL] sf CLI not found on PATH")
        return False
    proc = subprocess.run([SF_CMD, "org", "display", "-o", org, "--json"], capture_output=True, text=True)
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        print(f"[FAIL] sf org display -o {org} did not return JSON")
        return False
    connected = payload.get("status") == 0 and payload.get("result", {}).get("connectedStatus") == "Connected"
    print(f"[{'OK' if connected else 'FAIL'}] Salesforce org '{org}' connected")
    return connected


def check_env_vars(required: list[str]) -> bool:
    all_ok = True
    for var in required:
        present = bool(os.environ.get(var))
        print(f"[{'OK' if present else 'MISSING'}] env var {var} set")
        all_ok = all_ok and present
    return all_ok


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--org", default="devOrg1", help="sf CLI org alias or username")
    args = parser.parse_args()

    results = [
        check_python_version(),
        check_sf_cli(),
        check_org_auth(args.org),
    ]

    if not all(results):
        print("\nOne or more checks failed.")
        sys.exit(1)
    print("\nAll checks passed.")


if __name__ == "__main__":
    main()
