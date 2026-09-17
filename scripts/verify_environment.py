"""Check local prerequisites for the sfdc-mcp-poc lab.

Prints pass/fail per check. Covers Python version, sf CLI presence, org auth,
and (Gate 3+) two tiers of env/import checks:

- Core Gate 3 (always checked, fatal if missing): SF_MY_DOMAIN_URL,
  SF_ECA_CONSUMER_KEY, SF_MCP_SERVER_URL, google-adk importable. These don't
  need GOOGLE_API_KEY and are expected to pass during Gate 3 Steps 1-2, before
  a Gemini key exists.
- Gemini runtime (checked, non-fatal by default): GOOGLE_API_KEY,
  GOOGLE_GENAI_MODEL. Missing either prints a warning, not a failure, unless
  --require-gemini is passed (use starting Gate 3 Step 3, once actually
  running `adk web`).

Usage:
    python scripts/verify_environment.py --org devOrg1
    python scripts/verify_environment.py --org devOrg1 --require-gemini
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys

from dotenv import load_dotenv

MIN_PYTHON = (3, 11)
SF_CMD = shutil.which("sf")  # PATHEXT (sf.cmd) isn't resolved without this on Windows

CORE_GATE3_VARS = ["SF_MY_DOMAIN_URL", "SF_ECA_CONSUMER_KEY", "SF_MCP_SERVER_URL"]
GEMINI_RUNTIME_VARS = ["GOOGLE_API_KEY", "GOOGLE_GENAI_MODEL"]


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


def check_env_vars_present(var_names: list[str]) -> bool:
    ok = True
    for name in var_names:
        present = bool(os.environ.get(name))
        print(f"[{'OK' if present else 'FAIL'}] {name} set (value not printed)")
        ok = ok and present
    return ok


def check_google_adk_importable() -> bool:
    try:
        import google.adk  # noqa: F401
    except ImportError as exc:
        print(f"[FAIL] google-adk importable ({exc})")
        return False
    print("[OK] google-adk importable")
    return True


def check_gemini_runtime(require: bool) -> bool:
    ok = True
    for name in GEMINI_RUNTIME_VARS:
        present = bool(os.environ.get(name))
        if present:
            print(f"[OK] {name} set (value not printed)")
        elif require:
            print(f"[FAIL] {name} not set")
            ok = False
        else:
            print(f"[WARN] {name} not set -- agent execution unavailable until it is")
    return ok


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--org", default="devOrg1", help="sf CLI org alias or username")
    parser.add_argument(
        "--require-gemini",
        action="store_true",
        help="fail if GOOGLE_API_KEY/GOOGLE_GENAI_MODEL are missing, instead of just warning",
    )
    args = parser.parse_args()

    load_dotenv()

    results = [
        check_python_version(),
        check_sf_cli(),
        check_org_auth(args.org),
        check_env_vars_present(CORE_GATE3_VARS),
        check_google_adk_importable(),
        check_gemini_runtime(require=args.require_gemini),
    ]

    if not all(results):
        print("\nOne or more checks failed.")
        sys.exit(1)
    print("\nAll checks passed.")


if __name__ == "__main__":
    main()
