import csv
import hashlib
import sys
from pathlib import Path

# Force UTF-8 on stdout
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

SCRIPT_DIR = Path(__file__).resolve().parent
CHAMBER_ROOT = SCRIPT_DIR.parent
ARCHIVE_DIR = CHAMBER_ROOT / "_archive_pre_reorg"
REPORT_CSV = SCRIPT_DIR / "verify_report.csv"

def sha256(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()

def main():
    if not ARCHIVE_DIR.exists():
        print(f"ERROR: Archive directory not found: {ARCHIVE_DIR}")
        return 1

    print("Step 1/2: Indexing current files outside archive...")
    # Index files outside archive by (name, size) to quickly locate them
    current_index = {}
    for p in CHAMBER_ROOT.rglob("*"):
        if not p.is_file():
            continue
        if ARCHIVE_DIR in p.parents:
            continue
        # Also skip temporary files created by tools, _conflicts, etc. if needed,
        # but indexing everything is safe.
        key = (p.name, p.stat().st_size)
        if key not in current_index:
            current_index[key] = []
        current_index[key].append(p)

    print("Step 2/2: Verifying archive files against current files...")
    results = []
    missing_count = 0
    mismatch_count = 0
    match_count = 0

    archive_files = [p for p in ARCHIVE_DIR.rglob("*") if p.is_file()]
    total = len(archive_files)

    for i, arc_path in enumerate(archive_files, 1):
        if i % 1000 == 0:
            print(f"  Processed {i}/{total} files...")

        key = (arc_path.name, arc_path.stat().st_size)
        candidates = current_index.get(key, [])
        
        rel_arc = arc_path.relative_to(CHAMBER_ROOT)

        if not candidates:
            # Maybe the file was completely renamed or size changed? Unlikely in this reorg.
            results.append({"archive_path": str(rel_arc), "status": "MISSING", "target_path": "", "note": "No file with same name and size found."})
            missing_count += 1
            continue

        # Hash the archive file
        arc_hash = sha256(arc_path)
        
        # Check if any candidate has the same hash
        matched_target = None
        for cand in candidates:
            cand_hash = sha256(cand)
            if cand_hash == arc_hash:
                matched_target = cand
                break
        
        if matched_target:
            results.append({"archive_path": str(rel_arc), "status": "OK", "target_path": str(matched_target.relative_to(CHAMBER_ROOT)), "note": ""})
            match_count += 1
        else:
            results.append({"archive_path": str(rel_arc), "status": "MISMATCH", "target_path": "", "note": "Candidates found but SHA256 hashes differ."})
            mismatch_count += 1

    print("\nWriting report...")
    with open(REPORT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["archive_path", "status", "target_path", "note"])
        w.writeheader()
        w.writerows(results)

    print("-" * 60)
    print(f"VERIFICATION COMPLETE")
    print(f"Total archive files: {total}")
    print(f"Matches (OK)       : {match_count}")
    print(f"Missing            : {missing_count}")
    print(f"Hash Mismatches    : {mismatch_count}")
    print(f"Report saved to    : {REPORT_CSV}")
    print("-" * 60)

    if missing_count > 0 or mismatch_count > 0:
        print("WARNING: Data loss or corruption detected. Please review the report.")
        return 1
    
    print("SUCCESS: All original files safely exist in the new structure.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
