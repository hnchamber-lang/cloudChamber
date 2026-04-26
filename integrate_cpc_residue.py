"""integrate_cpc_residue.py
Distribute D:\\Chamber\\CPC\\CPC1105_CC and 'CPC3103 (CC)' into the
correct 01_instruments\\CPC3750_SN<sn>\\ folders, by reading the SN
from each CSV's header line.

Strategy
--------
* CSV files with a `Serial:,XXXX` header line: hardlink into
  01_instruments/CPC3750_SN<sn>/_legacy_<src>/relpath
* CSV files without such a header (the older `cpc3750a_*.csv` raw
  exports): NOT placed into any 01_instruments/ folder. They are left
  in the source folder until the script archives the whole source tree
  to _archive_pre_reorg/CPC/, where they remain available for future
  manual classification.

After successful distribution, the script copies the entire source
folder verbatim into _archive_pre_reorg/CPC/<name>/ (since the original
reorg never archived these — they were not in instruments.yaml at the
time). Finally, the source folder is removed.
"""
from __future__ import annotations
import os
import re
import shutil
import sys
from pathlib import Path

CHAMBER = Path(r"D:\Chamber")
ARCHIVE = CHAMBER / "_archive_pre_reorg" / "CPC"
INSTR = CHAMBER / "01_instruments"

SN_TO_CODE = {
    "3750213103": "CPC3750_SN3750213103",
    "3750221103": "CPC3750_SN3750221103",
    "3750221105": "CPC3750_SN3750221105",
    "3750230103": "CPC3750_SN3750230103",
}

SOURCES = [
    ("CPC/CPC1105_CC",   "CPC1105_CC"),     # mixed
    ("CPC/CPC3103 (CC)", "CPC3103_CC"),     # clean: all 3750213103
]

SN_RE = re.compile(r"^Serial:,\s*(\d+)", re.MULTILINE)


def read_sn(p: Path) -> str | None:
    try:
        head = p.read_bytes()[:512].decode("utf-8", errors="replace")
        m = SN_RE.search(head)
        return m.group(1) if m else None
    except Exception:
        return None


def link_or_copy(src: Path, dst: Path) -> str:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        return "skipped"
    try:
        os.link(src, dst)
        return "linked"
    except OSError:
        shutil.copy2(src, dst)
        return "copied"


def archive_tree(src: Path, dst: Path) -> int:
    """Mirror src into dst (destination must not exist). Return count."""
    if dst.exists():
        print(f"  archive already present, skipping: {dst}")
        return 0
    n = 0
    for f in src.rglob("*"):
        if f.is_file():
            rel = f.relative_to(src)
            tgt = dst / rel
            tgt.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, tgt)
            n += 1
    return n


def main() -> int:
    summary = {}
    no_header_total = 0

    for src_rel, src_label in SOURCES:
        src = CHAMBER / src_rel
        if not src.exists():
            print(f"  skip (no src): {src_rel}")
            continue

        # Distribute header-bearing files by SN
        per_sn = {sn: 0 for sn in SN_TO_CODE}
        no_header = 0
        for fp in src.rglob("*.csv"):
            sn = read_sn(fp)
            if sn is None:
                no_header += 1
                continue
            code = SN_TO_CODE.get(sn)
            if code is None:
                print(f"  WARN unknown SN {sn} in {fp}")
                continue
            rel = fp.relative_to(src)
            dst = INSTR / code / f"_legacy_{src_label}" / rel
            res = link_or_copy(fp, dst)
            if res == "linked":
                per_sn[sn] += 1

        no_header_total += no_header
        for sn, cnt in per_sn.items():
            if cnt:
                print(f"  {src_label:18s} -> {SN_TO_CODE[sn]:30s}  linked={cnt} (SN {sn})")
        if no_header:
            print(f"  {src_label:18s}  header-less files left in source: {no_header}")
        summary[src_rel] = per_sn

    print(f"\nTOTAL header-less files (will only be preserved in _archive_pre_reorg): {no_header_total}")

    # Archive the original folders into _archive_pre_reorg/CPC/
    print("\nArchiving original folders...")
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    for src_rel, src_label in SOURCES:
        src = CHAMBER / src_rel
        if not src.exists():
            continue
        # Use the original folder name (with parens etc.) inside _archive
        original_name = Path(src_rel).name
        dst = ARCHIVE / original_name
        n = archive_tree(src, dst)
        print(f"  archived {src_rel} -> {dst.relative_to(CHAMBER)}  ({n} files)")

    # Remove source folders
    print("\nRemoving source folders...")
    for src_rel, _ in SOURCES:
        src = CHAMBER / src_rel
        if src.exists():
            shutil.rmtree(src)
            print(f"  removed {src_rel}")

    # If D:\Chamber\CPC is empty after removal, remove that too
    cpc_root = CHAMBER / "CPC"
    if cpc_root.exists() and not any(cpc_root.iterdir()):
        cpc_root.rmdir()
        print(f"  removed empty CPC parent")

    return 0


if __name__ == "__main__":
    sys.exit(main())
