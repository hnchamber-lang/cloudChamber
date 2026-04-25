"""
reorganize.py — Chamber folder reorganizer.

Reorganizes D:\\Chamber into the standardized layout:

    D:\\Chamber\\
        00_tools\\            <- etc/ moved here
        00_resources\\        <- files/ moved here
        01_instruments\\      <- renamed instrument folders (MODEL_SN{serial})
            _meta\\
                instruments.yaml
                rename_plan.csv
                merge_log.csv
                run.log
        02_archives\\         <- POST, thai_old_*
        02_campaigns_legacy\\ <- YSU, PNU, unist
        03_projects\\         <- (created by build_project.py)
        _archive_pre_reorg\\  <- original layout snapshot (safety net)

Usage
-----
    # 1. Generate rename plan (no changes)
    python reorganize.py --dry-run

    # 2. After reviewing _reorg/rename_plan.csv, execute:
    python reorganize.py --execute

    # 3. Update folder names after filling unknown serials in instruments.yaml:
    python reorganize.py --update-serials

    # 4. Rollback (only if --execute was run and _archive_pre_reorg still exists):
    python reorganize.py --rollback

Requires:  PyYAML        ->   pip install pyyaml
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import logging
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable

# Force UTF-8 on stdout/stderr so non-ASCII log output never crashes on
# Windows consoles running under cp949 / cp1252.
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
# Configuration
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent                 # D:\Chamber\_reorg
CHAMBER_ROOT = SCRIPT_DIR.parent                             # D:\Chamber
CATALOG_PATH = SCRIPT_DIR / "instruments.yaml"

INSTR_ROOT = CHAMBER_ROOT / "01_instruments"
META_DIR = INSTR_ROOT / "_meta"
ARCHIVE_PRE_REORG = CHAMBER_ROOT / "_archive_pre_reorg"

RENAME_PLAN_CSV = SCRIPT_DIR / "rename_plan.csv"
MERGE_LOG_CSV = META_DIR / "merge_log.csv"
RUN_LOG = SCRIPT_DIR / "run.log"


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def setup_logger() -> logging.Logger:
    logger = logging.getLogger("reorganize")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    fmt = logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S")

    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(logging.INFO)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    RUN_LOG.parent.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(RUN_LOG, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    return logger


log = setup_logger()


# ---------------------------------------------------------------------------
# Catalog model
# ---------------------------------------------------------------------------

@dataclass
class Instrument:
    code: str
    model: str
    serial: str
    category: str = ""
    legacy_paths: list[str] = field(default_factory=list)
    file_patterns: list[str] = field(default_factory=list)
    date_source: str = "folder"
    date_regex: str = ""
    date_format: str = ""
    detector_serial: str = ""
    note: str = ""

    @property
    def target_path(self) -> Path:
        return INSTR_ROOT / self.code


@dataclass
class NonInstrumentRule:
    path: str
    action: str
    to: str = ""
    note: str = ""


def load_catalog() -> tuple[list[Instrument], list[NonInstrumentRule]]:
    with open(CATALOG_PATH, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    instruments = [Instrument(**entry) for entry in raw.get("instruments", [])]
    non_instr = [NonInstrumentRule(**entry)
                 for entry in raw.get("non_instrument_folders", [])]
    return instruments, non_instr


# ---------------------------------------------------------------------------
# Plan building
# ---------------------------------------------------------------------------

@dataclass
class PlanStep:
    """One reversible filesystem operation."""
    action: str           # rename | move | merge | archive | delete_empty_parent
    src: Path
    dst: Path | None
    note: str = ""

    def to_row(self) -> dict:
        return {
            "action": self.action,
            "src": str(self.src.relative_to(CHAMBER_ROOT))
                   if self.src.is_relative_to(CHAMBER_ROOT) else str(self.src),
            "dst": "" if self.dst is None
                   else (str(self.dst.relative_to(CHAMBER_ROOT))
                         if self.dst.is_relative_to(CHAMBER_ROOT)
                         else str(self.dst)),
            "note": self.note,
        }


def build_plan(instruments: list[Instrument],
               non_instr: list[NonInstrumentRule]) -> list[PlanStep]:
    steps: list[PlanStep] = []

    # 1) Instruments — rename / merge legacy_paths into target_path
    for ins in instruments:
        if not ins.legacy_paths:
            continue
        dst = ins.target_path
        for legacy in ins.legacy_paths:
            src = CHAMBER_ROOT / legacy
            if not src.exists():
                log.warning("Skipping missing legacy path: %s", src)
                continue
            if not dst.exists() and len(ins.legacy_paths) == 1:
                steps.append(PlanStep("rename", src, dst,
                                      note=f"{ins.model} (SN={ins.serial or 'unknown'})"))
            else:
                steps.append(PlanStep("merge", src, dst,
                                      note=f"Merge into {ins.code}"))

    # 2) Non-instrument folders
    for rule in non_instr:
        src = CHAMBER_ROOT / rule.path
        if not src.exists():
            log.warning("Skipping missing path: %s", src)
            continue

        if rule.action == "move":
            dst = CHAMBER_ROOT / rule.to
            steps.append(PlanStep("move", src, dst, note=rule.note))
        elif rule.action == "split_merge":
            # Parent folder is handled by its children's merge rules above.
            # Record a delete_empty_parent step to remove the (expected-empty) parent afterward.
            steps.append(PlanStep("delete_empty_parent", src, None,
                                  note=f"After children merged. {rule.note}"))
        else:
            log.warning("Unknown action '%s' for %s", rule.action, rule.path)

    return steps


def write_plan_csv(steps: list[PlanStep], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["action", "src", "dst", "note"])
        w.writeheader()
        for s in steps:
            w.writerow(s.to_row())
    log.info("Wrote plan -> %s  (%d steps)", path, len(steps))


# ---------------------------------------------------------------------------
# Execution helpers
# ---------------------------------------------------------------------------

def sha256(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def append_merge_log(src: Path, dst: Path, result: str, note: str = "") -> None:
    ensure_dir(MERGE_LOG_CSV.parent)
    new = not MERGE_LOG_CSV.exists()
    with open(MERGE_LOG_CSV, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["timestamp", "src", "dst", "result", "note"])
        w.writerow([datetime.now().isoformat(timespec="seconds"),
                    str(src), str(dst), result, note])


def safe_move_tree(src: Path, dst: Path) -> None:
    """Move src -> dst (rename). dst must not exist."""
    ensure_dir(dst.parent)
    if dst.exists():
        raise FileExistsError(f"Destination already exists: {dst}")
    shutil.move(str(src), str(dst))
    log.info("  rename  %s  ->  %s", src.name, dst.relative_to(CHAMBER_ROOT))


def merge_tree(src: Path, dst: Path) -> None:
    """Merge src/** into dst/**. On filename collision, compare SHA256:
       - identical  -> drop duplicate from src (logged)
       - different  -> keep both; collision kept under dst/_conflicts/<src_name>/
    """
    ensure_dir(dst)
    conflicts_dir = dst / "_conflicts" / src.name
    moved = collided_same = collided_diff = 0

    for sp in src.rglob("*"):
        if sp.is_dir():
            continue
        rel = sp.relative_to(src)
        target = dst / rel

        if not target.exists():
            ensure_dir(target.parent)
            shutil.move(str(sp), str(target))
            moved += 1
        else:
            try:
                same = sp.stat().st_size == target.stat().st_size and \
                       sha256(sp) == sha256(target)
            except Exception as e:                       # noqa: BLE001
                log.warning("  hash failed for %s: %s", sp, e)
                same = False

            if same:
                sp.unlink()
                collided_same += 1
                append_merge_log(sp, target, "duplicate_removed",
                                 f"identical content at {target}")
            else:
                cdst = conflicts_dir / rel
                ensure_dir(cdst.parent)
                shutil.move(str(sp), str(cdst))
                collided_diff += 1
                append_merge_log(sp, cdst, "conflict_kept",
                                 f"different content; original at {target}")

    # Remove now-empty src tree
    for p in sorted(src.rglob("*"), reverse=True):
        if p.is_dir():
            try:
                p.rmdir()
            except OSError:
                pass
    try:
        src.rmdir()
    except OSError:
        log.warning("  src not fully empty after merge: %s", src)

    log.info("  merge   %s -> %s  (moved=%d, dup_removed=%d, conflicts=%d)",
             src.name, dst.relative_to(CHAMBER_ROOT),
             moved, collided_same, collided_diff)


def archive_original(src: Path) -> None:
    """Mirror src into _archive_pre_reorg/ before any destructive change."""
    if not src.exists():
        return
    rel = src.relative_to(CHAMBER_ROOT)
    arc = ARCHIVE_PRE_REORG / rel
    if arc.exists():
        return
    ensure_dir(arc.parent)
    # Copy-mirror (kept until user confirms safe to delete).
    shutil.copytree(src, arc, symlinks=False)
    log.debug("  archive %s -> %s", rel, arc.relative_to(CHAMBER_ROOT))


# ---------------------------------------------------------------------------
# Execute a plan
# ---------------------------------------------------------------------------

def execute_plan(steps: list[PlanStep], *, archive_first: bool) -> None:
    ensure_dir(META_DIR)
    # Pre-create only the roots that are destinations for *merges* (so that the
    # target dir must exist before files land in it). Move-targets like
    # 00_tools / 00_resources are intentionally NOT pre-created — they are
    # produced by renaming their legacy folder (etc/, files/, ...) into place.
    for sub in ("01_instruments", "03_projects"):
        ensure_dir(CHAMBER_ROOT / sub)

    for i, step in enumerate(steps, 1):
        log.info("[%d/%d] %s  %s", i, len(steps), step.action, step.src.name)
        if not step.src.exists():
            log.warning("  skip (src missing): %s", step.src)
            continue
        if archive_first:
            archive_original(step.src)

        try:
            if step.action in ("rename", "move"):
                safe_move_tree(step.src, step.dst)
            elif step.action == "merge":
                merge_tree(step.src, step.dst)
            elif step.action == "delete_empty_parent":
                try:
                    step.src.rmdir()
                    log.info("  deleted empty parent: %s", step.src.name)
                except OSError as e:
                    log.warning("  parent not empty, left in place: %s (%s)",
                                step.src, e)
            else:
                log.error("  unknown action: %s", step.action)
        except Exception as e:                          # noqa: BLE001
            log.exception("  FAILED: %s", e)

    # Copy catalog + plan into _meta for provenance
    shutil.copy2(CATALOG_PATH, META_DIR / "instruments.yaml")
    if RENAME_PLAN_CSV.exists():
        shutil.copy2(RENAME_PLAN_CSV, META_DIR / "rename_plan.csv")
    log.info("Reorganization complete. Archive kept at: %s", ARCHIVE_PRE_REORG)


# ---------------------------------------------------------------------------
# Update-serials mode
# ---------------------------------------------------------------------------

def update_serial_folders(instruments: list[Instrument]) -> None:
    """Rename 01_instruments/{old_code} -> {new_code} when the YAML code changed
    (e.g., user filled a previously-empty serial)."""
    if not INSTR_ROOT.exists():
        log.error("01_instruments does not exist. Run --execute first.")
        return

    for ins in instruments:
        target = ins.target_path
        if target.exists():
            continue  # already matches catalog

        # Find any existing folder whose base model matches
        candidates = [d for d in INSTR_ROOT.iterdir()
                      if d.is_dir() and d.name.startswith(ins.code.split("_SN")[0] + "_SN")
                      and d.name != ins.code]
        if len(candidates) == 1:
            old = candidates[0]
            log.info("rename  %s  ->  %s", old.name, ins.code)
            old.rename(target)
        elif len(candidates) > 1:
            log.warning("Multiple candidates for %s: %s",
                        ins.code, [c.name for c in candidates])


# ---------------------------------------------------------------------------
# Rollback
# ---------------------------------------------------------------------------

def rollback() -> None:
    if not ARCHIVE_PRE_REORG.exists():
        log.error("No archive found at %s - cannot rollback.", ARCHIVE_PRE_REORG)
        return
    log.warning("Rolling back from %s ...", ARCHIVE_PRE_REORG)
    for item in ARCHIVE_PRE_REORG.iterdir():
        dst = CHAMBER_ROOT / item.name
        if dst.exists():
            log.info("  dest exists, skipping: %s", dst)
            continue
        shutil.move(str(item), str(dst))
        log.info("  restored %s", item.name)
    log.info("Rollback done. You may now delete %s manually.", ARCHIVE_PRE_REORG)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Chamber folder reorganizer")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true",
                   help="Build rename_plan.csv only; no changes on disk.")
    g.add_argument("--execute", action="store_true",
                   help="Apply the plan (copies originals to _archive_pre_reorg first).")
    g.add_argument("--update-serials", action="store_true",
                   help="Re-sync folder names with instruments.yaml (after filling SNs).")
    g.add_argument("--rollback", action="store_true",
                   help="Restore originals from _archive_pre_reorg.")
    ap.add_argument("--no-archive", action="store_true",
                    help="Skip copying originals to _archive_pre_reorg (faster, riskier).")
    args = ap.parse_args(argv)

    log.info("Chamber root     : %s", CHAMBER_ROOT)
    log.info("Catalog          : %s", CATALOG_PATH)

    instruments, non_instr = load_catalog()
    log.info("Loaded %d instruments, %d non-instrument rules",
             len(instruments), len(non_instr))

    if args.rollback:
        rollback()
        return 0

    if args.update_serials:
        update_serial_folders(instruments)
        return 0

    steps = build_plan(instruments, non_instr)
    write_plan_csv(steps, RENAME_PLAN_CSV)

    if args.dry_run:
        log.info("DRY RUN complete. Review: %s", RENAME_PLAN_CSV)
        return 0

    if args.execute:
        log.warning("EXECUTE mode - %d steps. Archive-first=%s",
                    len(steps), not args.no_archive)
        resp = input("Proceed?  Type 'yes' to continue: ").strip().lower()
        if resp != "yes":
            log.info("Aborted by user.")
            return 1
        execute_plan(steps, archive_first=not args.no_archive)
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
