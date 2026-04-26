"""
validator_legacy.py — PRE-REORG / archive-mirror validator.

Points at the original folder layout. Uses each instrument's
`legacy_paths` from `instruments.yaml` and walks
`D:\\Chamber\\_archive_pre_reorg\\<legacy_path>\\`.

For the POST-reorg `01_instruments/<code>/` layout, use the canonical
`validator.py` instead.

When to use this:
  * To diff archived originals against the reorganized tree (sanity
    check that nothing was lost in the merge).
  * As a historical reference for how the catalog mapped to the
    legacy folder names.

For each instrument, walks legacy_paths and parses dates using the
catalog rules (`date_source` + `date_regex` + `date_format`). Reports
matched / unmatched / non-pattern counts plus min/max observed date.

Usage
-----
    python validator_legacy.py
    python validator_legacy.py --verbose
    python validator_legacy.py --code CCN200_SN2310-057
"""

from __future__ import annotations

import argparse
import fnmatch
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.stderr.write("ERROR: PyYAML not installed.  Run:  pip install pyyaml\n")
    sys.exit(1)

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:                                            # noqa: BLE001
        pass


SCRIPT_DIR = Path(__file__).resolve().parent
CHAMBER_ROOT = SCRIPT_DIR.parent / "_archive_pre_reorg"
CATALOG_PATH = SCRIPT_DIR / "instruments.yaml"


# ---------------------------------------------------------------------------

def parse_date_from(text: str, fmt: str) -> datetime | None:
    formats = [fmt] if fmt else []
    formats += [
        "%Y%m%d", "%Y%m", "%Y-%m-%d", "%Y_%m_%d",
        "%Y%m%d%H%M%S", "%y%m%d%H%M%S",
        "%Y%m%d-%H%M%S", "%Y%m%d_%H%M%S",
        "%Y-%m-%d-%H%M%S", "%Y-%m-%dT%H%M%S",
        "%Y-%m-%d %H%M%S",
    ]
    for f in formats:
        if not f:
            continue
        try:
            return datetime.strptime(text, f)
        except ValueError:
            continue
    return None


def file_date(ins: dict, root: Path, path: Path) -> datetime | None:
    """Mirror build_project.file_date — try all strategies regardless of date_source."""
    rel = path.relative_to(root)
    regex = ins.get("date_regex", "")
    fmt = ins.get("date_format", "")
    ds = ins.get("date_source", "folder")

    if regex:
        m = re.search(regex, path.name)
        if m:
            captured = "".join(m.groups()) if len(m.groups()) > 1 else m.group(1)
            dt = parse_date_from(captured, fmt)
            if dt:
                return dt

    for part in rel.parts[:-1]:
        dt = parse_date_from(part, fmt)
        if dt:
            return dt

    dt = parse_date_from(path.stem, fmt)
    if dt:
        return dt

    if ds == "file_mtime":
        try:
            return datetime.fromtimestamp(path.stat().st_mtime)
        except OSError:
            return None
    return None


def match_patterns(path: Path, patterns: list[str]) -> bool:
    if not patterns:
        return True
    name = path.name
    return any(fnmatch.fnmatch(name, p) or fnmatch.fnmatch(name.lower(), p.lower())
               for p in patterns)


# ---------------------------------------------------------------------------

def check_instrument(ins: dict, *, verbose: bool) -> dict:
    patterns = ins.get("file_patterns", [])
    hit_dates: list[datetime] = []
    miss_samples: list[str] = []
    matched_files = 0
    unmatched_files = 0
    other_skipped = 0

    for lp in ins.get("legacy_paths", []):
        root = CHAMBER_ROOT / lp
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            if not match_patterns(p, patterns):
                other_skipped += 1
                continue
            dt = file_date(ins, root, p)
            if dt is None:
                unmatched_files += 1
                if len(miss_samples) < 5:
                    miss_samples.append(str(p.relative_to(CHAMBER_ROOT)))
            else:
                matched_files += 1
                hit_dates.append(dt)

    return {
        "code": ins["code"],
        "matched": matched_files,
        "unmatched": unmatched_files,
        "non_pattern": other_skipped,
        "date_min": min(hit_dates) if hit_dates else None,
        "date_max": max(hit_dates) if hit_dates else None,
        "miss_samples": miss_samples,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true",
                    help="List up to 5 unparsed filenames per instrument.")
    ap.add_argument("--code", default="",
                    help="Validate only one instrument (by code).")
    args = ap.parse_args()

    with open(CATALOG_PATH, encoding="utf-8") as f:
        catalog = yaml.safe_load(f)

    instruments = catalog.get("instruments", [])
    if args.code:
        instruments = [i for i in instruments if i["code"] == args.code]
        if not instruments:
            print(f"No instrument with code '{args.code}'")
            return 2

    print(f"{'Instrument code':<35} {'Matched':>8} {'Unmatched':>10} "
          f"{'NonPat':>8} {'Date range':>27}   {'Status'}")
    print("-" * 115)

    total_problems = 0
    for ins in instruments:
        r = check_instrument(ins, verbose=args.verbose)
        rng = ""
        if r["date_min"] and r["date_max"]:
            rng = f"{r['date_min'].date()}..{r['date_max'].date()}"

        if r["matched"] == 0 and r["unmatched"] == 0:
            status = "NO_DATA"
        elif r["unmatched"] > 0 and r["matched"] == 0:
            status = "PARSE_FAIL"
            total_problems += 1
        elif r["unmatched"] > r["matched"]:
            status = "PARTIAL (majority unparsed)"
            total_problems += 1
        elif r["unmatched"] > 0:
            status = f"partial ({r['unmatched']} unparsed)"
        else:
            status = "OK"

        print(f"{r['code']:<35} {r['matched']:>8,} {r['unmatched']:>10,} "
              f"{r['non_pattern']:>8,} {rng:>27}   {status}")

        if args.verbose and r["miss_samples"]:
            for sample in r["miss_samples"]:
                print(f"    unparsed: {sample}")

    print()
    if total_problems:
        print(f"{total_problems} instrument(s) need catalog fixes.")
        print("Run with --verbose to see examples, then edit instruments.yaml")
        print("(adjust date_regex / date_format / date_source).")
        return 1
    print("All instruments parse dates correctly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
