#!/usr/bin/env python3
"""
patch_mcp_obsidian.py

Makes the `mcp-obsidian` MCP server work with MULTIPLE Obsidian vaults at once.

THE BUG
-------
`mcp-obsidian` reads OBSIDIAN_API_KEY from the environment, but it silently
IGNORES OBSIDIAN_HOST and OBSIDIAN_PORT. Every request is hardcoded to
    https://127.0.0.1:27124
No matter what port you put in your Claude Desktop config, every vault's server
process connects to port 27124 (the first vault's REST server). Your second
vault therefore sends its own API key to the FIRST vault's server, which does
not recognise that key and replies:
    Error 40101: Authorization required
i.e. a 401 that looks like an auth/key problem but is really a port-routing bug.
(See docs/ROOT_CAUSE.md for the full analysis.)

THE FIX
-------
This script patches every installed copy of `mcp_obsidian/tools.py` so it reads
OBSIDIAN_HOST, OBSIDIAN_PORT and OBSIDIAN_PROTOCOL and passes them to the client.

It is SAFE to run repeatedly:
  * it makes a .bak backup of each file the first time it changes it
  * it skips files that are already patched
  * --dry-run shows what it would do without writing anything

USAGE
-----
    python patch_mcp_obsidian.py               # find and patch every copy
    python patch_mcp_obsidian.py --dry-run     # preview only, write nothing
    python patch_mcp_obsidian.py --path DIR     # also search an extra directory

NOTE: `uvx` runs mcp-obsidian from a cache that can be rebuilt when the package
updates or when you run `uv cache clean`. If multi-vault breaks again after an
update, just re-run this script.
"""

from __future__ import annotations

import argparse
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

API_KEY_LINE = re.compile(
    r'^(?P<indent>\s*)api_key\s*=\s*os\.getenv\(\s*["\']OBSIDIAN_API_KEY["\']'
)
CALL = "obsidian.Obsidian(api_key=api_key)"
PATCHED_CALL = (
    "obsidian.Obsidian(api_key=api_key, protocol=obsidian_protocol, "
    "host=obsidian_host, port=obsidian_port)"
)
ENV_BLOCK = (
    'obsidian_protocol = os.getenv("OBSIDIAN_PROTOCOL", "https")\n'
    'obsidian_host = os.getenv("OBSIDIAN_HOST", "127.0.0.1")\n'
    'obsidian_port = int(os.getenv("OBSIDIAN_PORT", "27124"))\n'
)
MARKER = "obsidian_port = int(os.getenv"


def candidate_roots(extra: list[str]) -> list[Path]:
    """Directories that might contain an installed mcp_obsidian package."""
    roots: list[Path] = []

    # 1. uv's cache (this is where `uvx mcp-obsidian` runs from)
    try:
        out = subprocess.run(
            ["uv", "cache", "dir"], capture_output=True, text=True, timeout=15
        )
        if out.returncode == 0 and out.stdout.strip():
            roots.append(Path(out.stdout.strip()))
    except (FileNotFoundError, subprocess.SubprocessError):
        pass

    # Fallback default uv cache locations if `uv` isn't on PATH
    system = platform.system()
    home = Path.home()
    if system == "Windows":
        local = os.environ.get("LOCALAPPDATA")
        if local:
            roots.append(Path(local) / "uv" / "cache")
    elif system == "Darwin":
        roots.append(home / "Library" / "Caches" / "uv")
    else:
        roots.append(home / ".cache" / "uv")

    # 2. Regular Python site-packages (pip / pipx installs)
    try:
        import site

        for p in site.getsitepackages():
            roots.append(Path(p))
        roots.append(Path(site.getusersitepackages()))
    except Exception:
        pass
    roots.append(Path(sys.prefix) / "lib")

    # 3. Anything the user explicitly passed
    roots.extend(Path(p) for p in extra)

    # De-dupe, keep only existing directories
    seen: set[Path] = set()
    result: list[Path] = []
    for r in roots:
        try:
            rp = r.resolve()
        except OSError:
            continue
        if rp in seen or not rp.is_dir():
            continue
        seen.add(rp)
        result.append(rp)
    return result


def find_tools_files(roots: list[Path]) -> list[Path]:
    found: set[Path] = set()
    for root in roots:
        try:
            for match in root.rglob("mcp_obsidian/tools.py"):
                if match.is_file():
                    found.add(match.resolve())
        except (OSError, PermissionError):
            continue
    return sorted(found)


def patch_text(text: str) -> tuple[str, bool]:
    """Return (new_text, changed)."""
    if MARKER in text:
        return text, False  # already patched
    if CALL not in text:
        return text, False  # nothing we recognise to patch

    lines = text.splitlines(keepends=True)
    out: list[str] = []
    inserted = False
    for line in lines:
        out.append(line)
        if not inserted and API_KEY_LINE.match(line):
            # Insert the env-reads right after the api_key line, matching indent
            indent = API_KEY_LINE.match(line).group("indent")
            for env_line in ENV_BLOCK.splitlines(keepends=True):
                out.append(indent + env_line)
            inserted = True

    new_text = "".join(out)
    if not inserted:
        # Couldn't find the api_key anchor; prepend a module-level block instead.
        new_text = ENV_BLOCK + new_text
    new_text = new_text.replace(CALL, PATCHED_CALL)
    return new_text, True


def main() -> int:
    ap = argparse.ArgumentParser(description="Patch mcp-obsidian for multi-vault use.")
    ap.add_argument("--dry-run", action="store_true", help="preview only, write nothing")
    ap.add_argument("--path", action="append", default=[], help="extra directory to search")
    args = ap.parse_args()

    roots = candidate_roots(args.path)
    print("Searching for installed mcp_obsidian copies in:")
    for r in roots:
        print(f"  - {r}")
    print()

    files = find_tools_files(roots)
    if not files:
        print("No mcp_obsidian/tools.py found.")
        print("Have you run `uvx mcp-obsidian` (or installed it) at least once?")
        return 1

    changed = 0
    already = 0
    for f in files:
        try:
            text = f.read_text(encoding="utf-8")
        except OSError as e:
            print(f"[skip] {f}  ({e})")
            continue

        new_text, did = patch_text(text)
        if not did:
            print(f"[ok  ] already patched: {f}")
            already += 1
            continue

        if args.dry_run:
            print(f"[would patch] {f}")
            changed += 1
            continue

        backup = f.with_suffix(f.suffix + ".bak")
        if not backup.exists():
            shutil.copy2(f, backup)
        f.write_text(new_text, encoding="utf-8")
        print(f"[patched] {f}  (backup: {backup.name})")
        changed += 1

    print()
    verb = "would patch" if args.dry_run else "patched"
    print(f"Done. {verb} {changed} file(s); {already} already patched.")
    if changed and not args.dry_run:
        print("Now fully restart Claude Desktop for the change to take effect.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
