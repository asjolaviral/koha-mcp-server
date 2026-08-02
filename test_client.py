#!/usr/bin/env python3
"""
test_client.py - quick self-test for the Koha MCP Server.

Runs a few representative tools directly (no MCP client needed) to confirm
the installation works. Requires a valid config.json first.

Usage:
    .venv/bin/python test_client.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import koha_mcp_server as k  # noqa: E402


def show(name, fn):
    try:
        out = fn()
        parsed = json.loads(out) if isinstance(out, str) else out
        print(f"[OK]   {name}: {json.dumps(parsed)[:180]}")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] {name}: {type(exc).__name__}: {exc}")
        return False


def main() -> int:
    print(f"Target Koha API: {k.BASE_URL}")
    print(f"Instance:        {k.INSTANCE}")
    print(f"Branchcode:      {k.BRANCHCODE}")
    print()

    ok = True
    ok &= show("list_libraries", k.list_libraries)
    ok &= show("search_patrons(userid=viral)", lambda: k.search_patrons("viral", field="userid"))
    ok &= show("search_catalogue(title=advertising)", lambda: k.search_catalogue("advertising", field="title"))
    ok &= show("get_public_biblio(4)", lambda: k.get_public_biblio(4))

    print()
    if ok:
        print("All self-tests passed.")
        return 0
    print("Some checks failed - review the messages above.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
