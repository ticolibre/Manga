#!/usr/bin/env python3
"""
Build Spanish Mihon extension indexes from the Keiyoushi index.

Every output is a drop-in replacement for
https://raw.githubusercontent.com/keiyoushi/extensions/repo/index.json

Four stores are generated so users can pick how strict they want to be:

    index.json       full        every extension with a Spanish source (Safe + Mixed + NSFW)
    safe.json        safe        only CONTENT_WARNING_SAFE extensions
    safe-mixed.json  safe-mixed  Safe + Mixed, no NSFW
    mixed.json       mixed       only CONTENT_WARNING_MIXED extensions

No APKs are hosted: every entry keeps its upstream apkUrl (GitHub Releases),
and the upstream signingKey is preserved so Mihon still trusts the APKs.

Usage:
    python3 filter.py                    # write all four stores
    python3 filter.py --es-only          # same, but only all-Spanish extensions
    python3 filter.py --lists safe       # build a single store
    python3 filter.py --out-dir build    # write somewhere else
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

UPSTREAM = "https://raw.githubusercontent.com/keiyoushi/extensions/repo/index.json"
SAFE = "CONTENT_WARNING_SAFE"
MIXED = "CONTENT_WARNING_MIXED"

# key: (filename, store name, badge label, allowed contentWarnings or None for all)
LISTS = {
    "full": ("index.json", "Keiyoushi ES", "KEI-ES", None),
    "safe": ("safe.json", "Keiyoushi ES Safe", "KEI-ES-SAFE", {SAFE}),
    "safe-mixed": ("safe-mixed.json", "Keiyoushi ES Safe + Mixed", "KEI-ES-SM",
                   {SAFE, MIXED}),
    "mixed": ("mixed.json", "Keiyoushi ES Mixed", "KEI-ES-MIXED", {MIXED}),
}


def fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "mihon-es-store/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-url", default=UPSTREAM)
    ap.add_argument("--out-dir", default=".",
                    help="directory for the generated indexes (default: .)")
    ap.add_argument("--lists", default="full,safe,safe-mixed,mixed",
                    help="comma-separated stores to build: full, safe, safe-mixed, "
                         "mixed (default: all)")
    ap.add_argument("--langs", default="es",
                    help="base language code; regional variants like es-419 are included")
    ap.add_argument("--es-only", action="store_true",
                    help="keep only extensions that have no non-Spanish sources")
    args = ap.parse_args()

    requested = [x.strip().lower() for x in args.lists.split(",") if x.strip()]
    unknown = [x for x in requested if x not in LISTS]
    if unknown:
        print(f"error: unknown list(s): {', '.join(unknown)} "
              f"(choose from {', '.join(LISTS)})", file=sys.stderr)
        return 1
    if not requested:
        print("error: no lists requested", file=sys.stderr)
        return 1

    bases = {x.strip().lower() for x in args.langs.split(",") if x.strip()}

    def matches(language: str | None) -> bool:
        lang = (language or "").lower()
        return any(lang == b or lang.startswith(b + "-") for b in bases)

    upstream = fetch_json(args.source_url)

    # Fail loudly instead of publishing a store Mihon cannot read.
    for key in ("name", "signingKey", "extensionList"):
        if key not in upstream:
            print(f"error: upstream index is missing '{key}'", file=sys.stderr)
            return 1

    extensions = upstream["extensionList"]["extensions"]
    candidates = []
    for ext in extensions:
        sources = ext.get("sources") or []
        if not any(matches(s.get("language")) for s in sources):
            continue
        if args.es_only and any(not matches(s.get("language")) for s in sources):
            continue
        candidates.append(ext)

    if not candidates:
        print("error: filter produced an empty store, refusing to write", file=sys.stderr)
        return 1

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for key in requested:
        filename, name, badge, warning = LISTS[key]
        kept = candidates if warning is None else [
            e for e in candidates if e.get("contentWarning") in warning
        ]
        if not kept:
            print(f"error: '{key}' list is empty, refusing to write {filename}",
                  file=sys.stderr)
            return 1

        out = {
            **upstream,
            "name": name,
            "badgeLabel": badge,
            "extensionList": {"extensions": kept},
        }
        path = out_dir / filename
        path.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")),
                        encoding="utf-8")

        safe = sum(1 for e in kept if e.get("contentWarning") == SAFE)
        mixed = sum(1 for e in kept if e.get("contentWarning") == MIXED)
        nsfw = len(kept) - safe - mixed
        print(f"{key:5s} {len(kept):3d}/{len(candidates)} extensions "
              f"({safe} safe, {mixed} mixed, {nsfw} nsfw) -> {path} "
              f"({path.stat().st_size / 1024:.0f} KiB)")

    print(f"signingKey preserved: {upstream['signingKey'][:16]}...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
