"""
build_project.py — Namelist-driven project folder builder.

Reads a `namelist.yaml` authored by the user (or via chamber_gui.py) and
materializes a project folder under D:\\Chamber\\03_projects\\{project_name}\\
containing the exact subset of observation data relevant to the experiment.

Namelist schema (example)
-------------------------
    project:
      name: "ASIA_AQ_2026_JWCHA"
      title: "Asia AQ Campaign - JWCHA experiment"
      pi: "Cha Ju-Won"
      operators: ["Hong Gildong", "Kim Yeongu"]
      start_date: "2026-04-21"
      end_date:   "2026-04-23"
      site: "Jeju Gosan"
      note: "Dust event case"
    instruments:
      - code: CCN200_SN2310-057
        use_period: ["2026-04-21", "2026-04-23"]
      - code: CPC3750_SN3750221105
        use_period: ["2026-04-21", "2026-04-23"]
      - code: SMPS_SN7002_CPC3750221105
        use_period: ["2026-04-21 09:00", "2026-04-23"]
    options:
      copy_mode: "hardlink"      # copy | hardlink | symlink
      overwrite: false
      include_raw: true

Usage
-----
    python build_project.py namelist.yaml               # build
    python build_project.py namelist.yaml --preview     # dry-run (just count)
    python build_project.py namelist.yaml --rollback    # delete built project

Requires:  PyYAML       ->   pip install pyyaml
"""

from __future__ import annotations

import argparse
import csv
import fnmatch
import hashlib
import logging
import os
import re
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime, time
from pathlib import Path
from typing import Iterable

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")    # type: ignore[attr-defined]
    except Exception:                                              # noqa: BLE001
        pass

try:
    import yaml
except ImportError:
    sys.stderr.write("ERROR: PyYAML not installed.  Run:  pip install pyyaml\n")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Paths / catalog
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
CHAMBER_ROOT = SCRIPT_DIR.parent
CATALOG_PATH = SCRIPT_DIR / "instruments.yaml"

INSTR_ROOT = CHAMBER_ROOT / "01_instruments"
PROJ_ROOT = CHAMBER_ROOT / "03_projects"


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

log = logging.getLogger("build_project")


def setup_logger(logfile: Path | None) -> None:
    log.handlers.clear()
    log.setLevel(logging.DEBUG)

    fmt = logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S")

    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(logging.INFO)
    sh.setFormatter(fmt)
    log.addHandler(sh)

    if logfile is not None:
        logfile.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(logfile, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        log.addHandler(fh)


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------

@dataclass
class InstrumentSpec:
    code: str
    model: str = ""
    serial: str = ""
    category: str = ""
    legacy_paths: list[str] = field(default_factory=list)
    file_patterns: list[str] = field(default_factory=list)
    date_source: str = "folder"   # filename | folder | file_mtime | header
    date_regex: str = ""
    date_format: str = ""
    detector_serial: str = ""
    note: str = ""

    @property
    def root(self) -> Path:
        return INSTR_ROOT / self.code


def load_catalog() -> dict[str, InstrumentSpec]:
    with open(CATALOG_PATH, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    out: dict[str, InstrumentSpec] = {}
    for entry in raw.get("instruments", []):
        spec = InstrumentSpec(**entry)
        out[spec.code] = spec
    return out


# ---------------------------------------------------------------------------
# Namelist
# ---------------------------------------------------------------------------

@dataclass
class NamelistInstrument:
    code: str
    use_period: tuple[datetime, datetime]


@dataclass
class Namelist:
    name: str
    title: str
    pi: str
    operators: list[str]
    start_date: datetime
    end_date: datetime
    site: str
    note: str
    instruments: list[NamelistInstrument]
    copy_mode: str = "copy"        # copy | hardlink | symlink
    overwrite: bool = False
    include_raw: bool = True


def _parse_dt(value, *, end: bool = False) -> datetime:
    """Parse YYYY-MM-DD or 'YYYY-MM-DD HH:MM'. For `end=True` without time,
    expand to end-of-day (23:59:59)."""
    if isinstance(value, datetime):
        return value
    if hasattr(value, "year") and not hasattr(value, "hour"):
        # date object from yaml
        dt = datetime.combine(value, time(23, 59, 59) if end else time(0, 0, 0))
        return dt
    s = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s, fmt)
            if fmt == "%Y-%m-%d" and end:
                dt = dt.replace(hour=23, minute=59, second=59)
            return dt
        except ValueError:
            continue
    raise ValueError(f"Cannot parse datetime: {value!r}")


def load_namelist(path: Path) -> Namelist:
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    p = raw.get("project", {})
    instr_raw = raw.get("instruments", [])
    opts = raw.get("options", {}) or {}

    instruments = []
    for entry in instr_raw:
        start, end = entry["use_period"]
        instruments.append(NamelistInstrument(
            code=entry["code"],
            use_period=(_parse_dt(start), _parse_dt(end, end=True)),
        ))

    return Namelist(
        name=p["name"].strip(),
        title=p.get("title", ""),
        pi=p.get("pi", ""),
        operators=p.get("operators", []) or [],
        start_date=_parse_dt(p["start_date"]),
        end_date=_parse_dt(p["end_date"], end=True),
        site=p.get("site", ""),
        note=p.get("note", ""),
        instruments=instruments,
        copy_mode=opts.get("copy_mode", "copy"),
        overwrite=bool(opts.get("overwrite", False)),
        include_raw=bool(opts.get("include_raw", True)),
    )


# ---------------------------------------------------------------------------
# Date extraction / filtering
# ---------------------------------------------------------------------------

def _parse_date_from(text: str, date_format: str) -> datetime | None:
    """Try common strftime formats plus the catalog-supplied one."""
    formats = [date_format] if date_format else []
    formats += [
        "%Y%m%d", "%Y%m", "%Y-%m-%d", "%Y_%m_%d",
        "%Y%m%d%H%M%S", "%y%m%d%H%M%S",
        "%Y%m%d-%H%M%S", "%Y%m%d_%H%M%S",
        "%Y-%m-%d-%H%M%S", "%Y-%m-%dT%H%M%S",
        "%Y-%m-%d %H%M%S",
    ]
    for fmt in formats:
        if not fmt:
            continue
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def file_date(spec: InstrumentSpec, path: Path) -> datetime | None:
    """Determine the observation date/time represented by a file.
    Strategy (always tried in this order, regardless of date_source):
        1. date_regex against the filename
        2. each parent folder name
        3. the filename stem
        4. file mtime  (only if date_source == 'file_mtime', else None)
    """
    rel = path.relative_to(spec.root)

    # 1. Filename regex (if provided)
    if spec.date_regex:
        m = re.search(spec.date_regex, path.name)
        if m:
            captured = "".join(m.groups()) if len(m.groups()) > 1 else m.group(1)
            dt = _parse_date_from(captured, spec.date_format)
            if dt:
                return dt

    # 2. Parent folder names
    for part in rel.parts[:-1]:
        dt = _parse_date_from(part, spec.date_format)
        if dt:
            return dt

    # 3. Filename stem (in case the date sits in the bare name)
    dt = _parse_date_from(path.stem, spec.date_format)
    if dt:
        return dt

    # 4. mtime — only when explicitly requested
    if spec.date_source == "file_mtime":
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


def select_files(spec: InstrumentSpec,
                 start: datetime, end: datetime) -> list[tuple[Path, datetime | None]]:
    """Return (file, date) tuples within [start, end]."""
    if not spec.root.exists():
        log.warning("Instrument folder missing: %s", spec.root)
        return []

    results: list[tuple[Path, datetime | None]] = []
    for p in spec.root.rglob("*"):
        if not p.is_file():
            continue
        if not match_patterns(p, spec.file_patterns):
            continue
        dt = file_date(spec, p)
        if dt is None:
            continue
        if start <= dt <= end:
            results.append((p, dt))
    results.sort(key=lambda t: (t[1] or datetime.min, t[0].name))
    return results


# ---------------------------------------------------------------------------
# Copying
# ---------------------------------------------------------------------------

def _sha256(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _same_volume(a: Path, b: Path) -> bool:
    try:
        return os.stat(a).st_dev == os.stat(b).st_dev
    except OSError:
        return False


def place_file(src: Path, dst: Path, mode: str, overwrite: bool) -> str:
    """Return a short tag describing what happened: 'copied'|'linked'|'skipped_exists'."""
    if dst.exists():
        if not overwrite:
            return "skipped_exists"
        dst.unlink()
    dst.parent.mkdir(parents=True, exist_ok=True)

    if mode == "hardlink" and _same_volume(src, dst.parent):
        try:
            os.link(src, dst)
            return "linked"
        except OSError:
            pass                               # fall through to copy
    if mode == "symlink":
        try:
            os.symlink(src, dst)
            return "symlinked"
        except OSError:
            pass
    shutil.copy2(src, dst)
    return "copied"


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def build(namelist_path: Path, *, preview: bool = False) -> int:
    nl = load_namelist(namelist_path)
    catalog = load_catalog()

    project_dir = PROJ_ROOT / nl.name
    log_dir = project_dir / "_log"
    setup_logger(None if preview else log_dir / "run.log")

    log.info("=" * 72)
    log.info("Project     : %s", nl.name)
    log.info("Title       : %s", nl.title)
    log.info("Period      : %s  ->  %s", nl.start_date, nl.end_date)
    log.info("PI          : %s", nl.pi)
    log.info("Operators   : %s", ", ".join(nl.operators))
    log.info("Site        : %s", nl.site)
    log.info("Copy mode   : %s", nl.copy_mode)
    log.info("Preview     : %s", preview)
    log.info("Target      : %s", project_dir)
    log.info("=" * 72)

    if project_dir.exists() and not nl.overwrite and not preview:
        log.error("Project folder already exists (set overwrite: true to replace): %s",
                  project_dir)
        return 2

    # Plan files per instrument
    manifest: list[dict] = []
    total_bytes = 0
    total_files = 0

    for item in nl.instruments:
        spec = catalog.get(item.code)
        if spec is None:
            log.error("Instrument code not in catalog: %s", item.code)
            return 3

        start = max(item.use_period[0], nl.start_date)
        end = min(item.use_period[1], nl.end_date)

        files = select_files(spec, start, end)
        log.info("  %-35s %5d files  (%s ~ %s)",
                 item.code, len(files), start.date(), end.date())

        for src, dt in files:
            rel = src.relative_to(spec.root)
            dst = project_dir / item.code / rel
            total_files += 1
            try:
                total_bytes += src.stat().st_size
            except OSError:
                pass
            manifest.append({
                "instrument_code": item.code,
                "observed": dt.isoformat() if dt else "",
                "src": str(src),
                "dst": str(dst),
                "size": src.stat().st_size if src.exists() else 0,
            })

    log.info("-" * 72)
    log.info("TOTAL       : %d files, %.2f GB",
             total_files, total_bytes / (1024 ** 3))
    log.info("-" * 72)

    if preview:
        return 0

    # Materialize
    project_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    # Place files
    stats = {"copied": 0, "linked": 0, "symlinked": 0, "skipped_exists": 0}
    manifest_rows: list[dict] = []

    for entry in manifest:
        src = Path(entry["src"])
        dst = Path(entry["dst"])
        tag = place_file(src, dst, nl.copy_mode, nl.overwrite)
        stats[tag] = stats.get(tag, 0) + 1
        row = dict(entry)
        row["result"] = tag
        if tag in ("copied", "linked", "symlinked") and dst.exists() \
                and dst.stat().st_size < 64 * 1024 * 1024:     # hash small files
            try:
                row["sha256"] = _sha256(dst)
            except Exception:                              # noqa: BLE001
                row["sha256"] = ""
        else:
            row["sha256"] = ""
        manifest_rows.append(row)

    # Copy namelist alongside results
    shutil.copy2(namelist_path, project_dir / "namelist.yaml")

    # Write manifest
    with open(log_dir / "copy_manifest.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["instrument_code", "observed",
                                          "src", "dst", "size",
                                          "result", "sha256"])
        w.writeheader()
        w.writerows(manifest_rows)

    # README
    readme = project_dir / "README.md"
    with open(readme, "w", encoding="utf-8") as f:
        f.write(render_readme(nl, manifest_rows, stats, total_bytes))

    log.info("DONE. copied=%d linked=%d symlinked=%d skipped=%d",
             stats.get("copied", 0), stats.get("linked", 0),
             stats.get("symlinked", 0), stats.get("skipped_exists", 0))
    log.info("Project at: %s", project_dir)
    return 0


def render_readme(nl: Namelist, rows: list[dict], stats: dict, total_bytes: int) -> str:
    from collections import Counter
    per_instr = Counter(r["instrument_code"] for r in rows)
    lines = [
        f"# {nl.name}",
        "",
        f"**Title**: {nl.title}",
        f"**PI**: {nl.pi}",
        f"**Operators**: {', '.join(nl.operators)}",
        f"**Site**: {nl.site}",
        f"**Period**: {nl.start_date.date()} to {nl.end_date.date()}",
        "",
        f"> {nl.note}" if nl.note else "",
        "",
        "## Contents",
        "",
        "| Instrument | Files |",
        "|---|---:|",
    ]
    for code, n in sorted(per_instr.items()):
        lines.append(f"| `{code}` | {n} |")
    lines += [
        "",
        f"**Total**: {sum(per_instr.values())} files, {total_bytes / (1024**3):.2f} GB",
        "",
        "## Build info",
        "",
        f"- Copy mode: `{nl.copy_mode}`",
        f"- copied: {stats.get('copied', 0)}",
        f"- linked: {stats.get('linked', 0)}",
        f"- symlinked: {stats.get('symlinked', 0)}",
        f"- skipped (already exists): {stats.get('skipped_exists', 0)}",
        f"- Built at: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "See `_log/copy_manifest.csv` for the per-file record.",
        "See `namelist.yaml` for the exact configuration used.",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Rollback (remove the project dir)
# ---------------------------------------------------------------------------

def rollback(namelist_path: Path) -> int:
    nl = load_namelist(namelist_path)
    project_dir = PROJ_ROOT / nl.name
    setup_logger(None)
    if not project_dir.exists():
        log.info("Nothing to remove: %s", project_dir)
        return 0
    log.warning("Removing %s ...", project_dir)
    resp = input("Type project name to confirm delete: ").strip()
    if resp != nl.name:
        log.info("Aborted.")
        return 1
    shutil.rmtree(project_dir)
    log.info("Deleted.")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build a Chamber project folder from a namelist")
    ap.add_argument("namelist", type=Path, help="Path to namelist.yaml")
    ap.add_argument("--preview", action="store_true",
                    help="Only report what would be copied (no changes).")
    ap.add_argument("--rollback", action="store_true",
                    help="Delete the project folder produced from this namelist.")
    args = ap.parse_args(argv)

    if args.rollback:
        return rollback(args.namelist)
    return build(args.namelist, preview=args.preview)


if __name__ == "__main__":
    sys.exit(main())
