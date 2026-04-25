"""
preflight.py — Pre-execution inventory for the Chamber reorganization.

Scans the **current** layout of D:\\Chamber, maps every legacy folder to its
post-reorg destination (per instruments.yaml), and prints a table showing:

    - file count
    - total size
    - date range (from file mtimes)
    - planned destination code
    - planned action (rename / merge)

Also flags legacy paths that are declared in instruments.yaml but missing on
disk, and top-level folders that are not covered by any rule.

Writes:  _reorg/preflight_report.csv

Usage
-----
    python preflight.py
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.stderr.write("ERROR: PyYAML not installed. Run:  pip install pyyaml\n")
    sys.exit(1)


SCRIPT_DIR = Path(__file__).resolve().parent
CHAMBER_ROOT = SCRIPT_DIR.parent
CATALOG_PATH = SCRIPT_DIR / "instruments.yaml"
REPORT_CSV = SCRIPT_DIR / "preflight_report.csv"


@dataclass
class FolderStat:
    path: Path
    n_files: int
    total_bytes: int
    mtime_min: float | None
    mtime_max: float | None


def scan(path: Path) -> FolderStat:
    n = 0
    total = 0
    mn: float | None = None
    mx: float | None = None
    try:
        for p in path.rglob("*"):
            if p.is_file():
                try:
                    st = p.stat()
                except OSError:
                    continue
                n += 1
                total += st.st_size
                mn = st.st_mtime if mn is None else min(mn, st.st_mtime)
                mx = st.st_mtime if mx is None else max(mx, st.st_mtime)
    except PermissionError:
        pass
    return FolderStat(path=path, n_files=n, total_bytes=total,
                      mtime_min=mn, mtime_max=mx)


def fmt_bytes(b: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024:
            return f"{b:,.1f} {unit}"
        b /= 1024
    return f"{b:,.1f} PB"


def fmt_mtime(m: float | None) -> str:
    if m is None:
        return ""
    return datetime.fromtimestamp(m).strftime("%Y-%m-%d")


def main() -> int:
    with open(CATALOG_PATH, encoding="utf-8") as f:
        cat = yaml.safe_load(f)

    # (legacy_path -> (target_code, action))
    legacy_map: dict[str, tuple[str, str]] = {}
    for ins in cat.get("instruments", []):
        count = len(ins.get("legacy_paths", []))
        for lp in ins.get("legacy_paths", []):
            action = "rename" if count == 1 else "merge"
            legacy_map[lp] = (ins["code"], action)

    non_instr_map: dict[str, dict] = {}
    for rule in cat.get("non_instrument_folders", []):
        non_instr_map[rule["path"]] = rule

    # Scan everything listed in the catalog
    rows: list[dict] = []
    per_target: dict[str, dict] = defaultdict(
        lambda: {"files": 0, "bytes": 0, "sources": []})
    warnings: list[str] = []

    for lp, (code, action) in sorted(legacy_map.items()):
        src = CHAMBER_ROOT / lp
        if not src.exists():
            warnings.append(f"MISSING legacy path: {lp}")
            continue
        s = scan(src)
        per_target[code]["files"] += s.n_files
        per_target[code]["bytes"] += s.total_bytes
        per_target[code]["sources"].append(lp)
        rows.append({
            "category": "instrument",
            "legacy_path": lp,
            "n_files": s.n_files,
            "total_size": fmt_bytes(s.total_bytes),
            "mtime_min": fmt_mtime(s.mtime_min),
            "mtime_max": fmt_mtime(s.mtime_max),
            "action": action,
            "target": f"01_instruments/{code}",
        })

    for lp, rule in sorted(non_instr_map.items()):
        src = CHAMBER_ROOT / lp
        if not src.exists():
            warnings.append(f"MISSING non-instrument path: {lp}")
            continue
        s = scan(src)
        rows.append({
            "category": "non_instrument",
            "legacy_path": lp,
            "n_files": s.n_files,
            "total_size": fmt_bytes(s.total_bytes),
            "mtime_min": fmt_mtime(s.mtime_min),
            "mtime_max": fmt_mtime(s.mtime_max),
            "action": rule.get("action", ""),
            "target": rule.get("to", ""),
        })

    # Flag uncovered top-level folders
    covered = set(legacy_map.keys()) | set(non_instr_map.keys())
    # Also account for parent-of-subpath entries (e.g. "CPC" covers "CPC\\CPC0103")
    covered_tops = {Path(p).parts[0] for p in covered}
    for d in CHAMBER_ROOT.iterdir():
        if not d.is_dir():
            continue
        if d.name.startswith(("_", "0", "1", "2", "3")):
            continue                  # generated roots
        if d.name in covered_tops:
            continue
        warnings.append(f"UNCOVERED top-level folder: {d.name}")

    # Print summary
    print(f"{'Legacy path':<40} {'Files':>8} {'Size':>12} "
          f"{'From':>12} {'To':>12}  ->  Target")
    print("-" * 120)
    for r in rows:
        print(f"{r['legacy_path']:<40} {r['n_files']:>8,} "
              f"{r['total_size']:>12} {r['mtime_min']:>12} {r['mtime_max']:>12}  ->  "
              f"{r['target']}")

    print("\n=== Projected post-reorg instrument totals ===")
    for code, d in sorted(per_target.items()):
        src_tag = " + ".join(d["sources"])
        print(f"  {code:<35} {d['files']:>7,} files  "
              f"{fmt_bytes(d['bytes']):>12}   <-  {src_tag}")

    if warnings:
        print("\n=== Warnings ===")
        for w in warnings:
            print("  !", w)

    # Write CSV
    with open(REPORT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\nWrote: {REPORT_CSV}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
