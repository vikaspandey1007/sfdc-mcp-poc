"""Seed the connected Salesforce org with sample Account/Opportunity/Task data.

Idempotent: re-running skips records that already exist (matched by Name,
or by WhatId+Subject for Tasks) instead of creating duplicates.

Shells out to the `sf` CLI (already authenticated via `sf org login web`)
rather than adding a Salesforce SDK dependency this early in the project.
Run from PowerShell on Windows -- `sf data`/`sf api` subcommands hit a
path-quoting bug under Git Bash/MSYS on this machine (see docs/gate-0-plan.md,
Open Questions operational note); invoking via Python's subprocess (no shell)
sidesteps that either way, but PowerShell is the tested path.

Usage:
    python scripts/seed_data.py --org devOrg1
    python scripts/seed_data.py --org devOrg1 --dry-run
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_DATA_DIR = REPO_ROOT / "salesforce" / "sample-data"

# On Windows, `sf` resolves to `sf.cmd` via PATHEXT, which plain
# subprocess.run(["sf", ...]) does not do without shell=True. Resolving the
# concrete path up front avoids needing shell=True (and its quoting risks).
SF_CMD = shutil.which("sf")
if SF_CMD is None:
    raise RuntimeError("sf CLI not found on PATH")

# Recent tasks get an ActivityDate a couple of days old; stale ones look
# genuinely stale (>14 days), matching the Gate 6 policy's staleness rule.
RECENT_ACTIVITY_DATE = "2026-09-13"
STALE_ACTIVITY_DATE = "2026-08-15"


def run_sf(args: list[str]) -> dict:
    """Run an `sf ... --json` command and return the parsed result payload."""
    proc = subprocess.run(
        [SF_CMD, *args, "--json"],
        capture_output=True,
        text=True,
    )
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        print(f"Non-JSON output from: sf {' '.join(args)}", file=sys.stderr)
        print(proc.stdout, file=sys.stderr)
        print(proc.stderr, file=sys.stderr)
        raise
    if payload.get("status") != 0:
        raise RuntimeError(
            f"sf {' '.join(args)} failed: {payload.get('message', payload)}"
        )
    return payload["result"]


def find_existing_id(org: str, sobject: str, name: str) -> str | None:
    escaped = name.replace("'", "\\'")
    query = f"SELECT Id FROM {sobject} WHERE Name = '{escaped}' LIMIT 1"
    result = run_sf(["data", "query", "-q", query, "-o", org])
    records = result.get("records", [])
    return records[0]["Id"] if records else None


def create_record(org: str, sobject: str, fields: dict) -> str:
    values = " ".join(f"{k}='{str(v).replace(chr(39), chr(92) + chr(39))}'" for k, v in fields.items())
    result = run_sf(
        ["data", "create", "record", "--sobject", sobject, "--values", values, "-o", org]
    )
    return result["id"]


def seed_accounts(org: str, dry_run: bool) -> dict[str, str]:
    name_to_id: dict[str, str] = {}
    with open(SAMPLE_DATA_DIR / "accounts.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            existing = find_existing_id(org, "Account", row["Name"])
            if existing:
                print(f"  [skip] Account already exists: {row['Name']} ({existing})")
                name_to_id[row["Name"]] = existing
                continue
            if dry_run:
                print(f"  [dry-run] would create Account: {row['Name']}")
                continue
            fields = {
                "Name": row["Name"],
                "Industry": row["Industry"],
                "Rating": row["Rating"],
                "BillingCity": row["BillingCity"],
                "BillingCountry": row["BillingCountry"],
            }
            new_id = create_record(org, "Account", fields)
            print(f"  [created] Account: {row['Name']} ({new_id})")
            name_to_id[row["Name"]] = new_id
    return name_to_id


def seed_opportunities(
    org: str, account_ids: dict[str, str], dry_run: bool
) -> list[tuple[str, str, bool]]:
    """Returns list of (OpportunityId, OpportunityName, is_stale)."""
    created: list[tuple[str, str, bool]] = []
    with open(SAMPLE_DATA_DIR / "opportunities.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            is_stale = row["Stale"].strip().lower() == "true"
            existing = find_existing_id(org, "Opportunity", row["Name"])
            if existing:
                print(f"  [skip] Opportunity already exists: {row['Name']} ({existing})")
                created.append((existing, row["Name"], is_stale))
                continue
            if dry_run:
                print(f"  [dry-run] would create Opportunity: {row['Name']}")
                continue
            account_id = account_ids.get(row["AccountName"])
            if not account_id:
                raise RuntimeError(
                    f"No Account id resolved for '{row['AccountName']}' "
                    f"(needed by Opportunity '{row['Name']}')"
                )
            fields = {
                "Name": row["Name"],
                "AccountId": account_id,
                "Amount": row["Amount"],
                "StageName": row["StageName"],
                "CloseDate": row["CloseDate"],
            }
            new_id = create_record(org, "Opportunity", fields)
            print(f"  [created] Opportunity: {row['Name']} ({new_id})")
            created.append((new_id, row["Name"], is_stale))
    return created


def seed_tasks(org: str, opportunities: list[tuple[str, str, bool]], dry_run: bool) -> None:
    for opp_id, opp_name, is_stale in opportunities:
        subject = "Initial discovery call" if is_stale else "Follow-up call"
        activity_date = STALE_ACTIVITY_DATE if is_stale else RECENT_ACTIVITY_DATE

        escaped_id = opp_id.replace("'", "\\'")
        query = (
            f"SELECT Id FROM Task WHERE WhatId = '{escaped_id}' "
            f"AND Subject = '{subject}' LIMIT 1"
        )
        existing = run_sf(["data", "query", "-q", query, "-o", org]).get("records", [])
        if existing:
            print(f"  [skip] Task already exists for {opp_name}: {subject}")
            continue
        if dry_run:
            print(f"  [dry-run] would create Task for {opp_name}: {subject} ({activity_date})")
            continue
        fields = {
            "WhatId": opp_id,
            "Subject": subject,
            "ActivityDate": activity_date,
            "Status": "Completed",
        }
        new_id = create_record(org, "Task", fields)
        print(f"  [created] Task for {opp_name}: {subject} ({new_id})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--org", required=True, help="sf CLI org alias or username")
    parser.add_argument("--dry-run", action="store_true", help="print actions without writing")
    args = parser.parse_args()

    print(f"Seeding org: {args.org}{' (dry run)' if args.dry_run else ''}")

    print("\n== Accounts ==")
    account_ids = seed_accounts(args.org, args.dry_run)

    print("\n== Opportunities ==")
    opportunities = seed_opportunities(args.org, account_ids, args.dry_run)

    print("\n== Tasks (staleness signal) ==")
    seed_tasks(args.org, opportunities, args.dry_run)

    print("\nDone.")


if __name__ == "__main__":
    main()
