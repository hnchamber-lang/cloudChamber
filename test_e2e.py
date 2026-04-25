"""
test_e2e.py — End-to-end smoke test for the Chamber pipeline.

Creates a *synthetic* Chamber root in a temp directory populated with tiny
fake data files that mimic the real layout, then runs:

    1. reorganize.py --dry-run    (plan)
    2. reorganize.py --execute    (rename/merge on the fake tree)
    3. build_project.py <nl>      (build a project from a synthetic namelist)

Asserts:
    * rename_plan.csv is produced
    * expected post-reorg folders exist under 01_instruments/
    * merged folders contain contributions from both sources
    * the built project has the correct per-instrument file counts
    * copy_manifest.csv and README.md are present in the project

Does NOT touch the real D:\\Chamber.  Run this before executing the real
reorganization to build confidence in the tooling.

Usage
-----
    python test_e2e.py
"""

from __future__ import annotations

import csv
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.stderr.write("ERROR: PyYAML not installed. Run:  pip install pyyaml\n")
    sys.exit(1)


HERE = Path(__file__).resolve().parent     # D:\Chamber\_reorg


# ---------------------------------------------------------------------------
# Synthetic Chamber tree
# ---------------------------------------------------------------------------

def mkfile(p: Path, content: str = "x") -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def build_fake_chamber(root: Path) -> None:
    """Mirror a minimal version of D:\\Chamber in `root`."""
    # CCN_200 (NEW)  -> CCN200_SN2310-057
    # Real format: CCN_200_Data_YYYYMMDD_HHMMSS.csv inside YYYYMM/YYYYMMDD/
    mkfile(root / "CCN_200 (NEW)" / "202604" / "20260421" /
           "CCN_200_Data_20260421_120000.csv",
           "S/N,2310-057\n2026-04-21 12:00,data")
    mkfile(root / "CCN_200 (NEW)" / "202604" / "20260422" /
           "CCN_200_Data_20260422_120000.csv",
           "S/N,2310-057\n2026-04-22 12:00,data")
    mkfile(root / "CCN_200 (NEW)" / "202605" / "20260510" /
           "CCN_200_Data_20260510_120000.csv",
           "S/N,2310-057\n2026-05-10 12:00,out-of-range")

    # CCN_200 (OLD)  -> CCN200_SN
    mkfile(root / "CCN_200 (OLD)" / "CCN-200 data 220413070000.csv", "old,data")

    # CPC — three detectors, with duplicates in NIMS folders
    mkfile(root / "CPC" / "CPC1105 (AC)" / "20260421" / "cpc_1.csv", "same")
    mkfile(root / "CPC" / "CPC1105 (AC)" / "20260422" / "cpc_2.csv", "same")
    mkfile(root / "NIMS_AC" / "CPC_1105" / "20260421" / "cpc_1.csv", "same")     # duplicate
    mkfile(root / "NIMS_AC" / "CPC_1105" / "20260423" / "cpc_3.csv", "unique-3")
    mkfile(root / "CPC" / "CPC1103 (CC)" / "20260421" / "cpc.csv", "x")
    mkfile(root / "CPC" / "CPC0103 (AC)" / "20260421" / "cpc.csv", "x")
    mkfile(root / "NIMS_Milo" / "CPC 0103" / "20260425" / "cpc.csv", "extra")

    # SMPS
    mkfile(root / "SMPS7002" / "20260421" / "scan.p82", "binary1")
    mkfile(root / "NIMS_AC" / "SMPS" / "20260422" / "scan.p82", "binary2")
    mkfile(root / "NIMS_Milo" / "SMPS_KCI" / "20260423" / "scan.p82", "binary3")
    mkfile(root / "SMPS7003" / "20260421" / "scan.p82", "b7003")

    # PROMO (uses filename-embedded serial + date)
    mkfile(root / "PROMO 2000 (AC)" / "DATA_auto_15639_2026_04_21.data.promo", "p-AC")
    mkfile(root / "PROMO 2000 (NEW)" / "202604" / "DATA_auto_22659_2026_04_21.promo", "p-NEW")
    mkfile(root / "PROMO 3000" / "202604" / "DATA_auto_18803_2026_04_21.promo", "p-3000")

    # LI-COR / GRAPHTEC / PINE
    mkfile(root / "LICOR0807" / "202604" / "a.csv", "licor1")
    mkfile(root / "LICOR0808" / "202604" / "b.csv", "licor2")
    mkfile(root / "GRAPHTEC" / "2026-04-21" / "g.csv", "graph")
    mkfile(root / "PINE07 (AC)" / "20260421" / "pine.csv", "pine")

    # Unknown-serial instruments (minimal)
    mkfile(root / "CASDPOL" / "20260421" / "cas.csv", "x")
    mkfile(root / "CDSN" / "sth_cd5n_20260421_120000.csv", "x")
    mkfile(root / "CIMON" / "202604" / "cimon.csv", "x")
    mkfile(root / "CPI" / "202604" / "img.cpi", "x")
    mkfile(root / "FTM06D" / "20260421" / "f.csv", "x")
    mkfile(root / "HYGRO1011" / "202604" / "h.csv", "x")
    mkfile(root / "MARGA" / "20260421-120000.idet", "x")
    mkfile(root / "Sky-OPC" / "kaolin_2026421_2026-04-21-C.dat", "x")

    # Non-instrument folders
    mkfile(root / "etc" / "fix.py", "# script")
    mkfile(root / "files" / "demo.gif", "\x00GIF")
    mkfile(root / "POST" / "CPC.zip", "\x00PK")
    mkfile(root / "thai_old_opc_calibrated_20250711" / "readme.txt", "x")
    mkfile(root / "YSU" / "20250808" / "a.csv", "x")
    mkfile(root / "PNU" / "x.csv", "x")
    mkfile(root / "unist" / "x.csv", "x")
    mkfile(root / "관측자료(2026.04.20.~)" / "asia_aq_jwcha_20260421" / "note.txt", "x")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def patch_scripts(tmp_reorg: Path, tmp_chamber: Path) -> None:
    """Copy the real scripts into tmp_reorg and patch their CHAMBER_ROOT to
    point at the synthetic tree instead of the real D:\\Chamber."""
    tmp_reorg.mkdir(parents=True, exist_ok=True)
    for name in ("instruments.yaml", "reorganize.py",
                 "build_project.py", "namelist.sample.yaml"):
        shutil.copy2(HERE / name, tmp_reorg / name)

    chamber_str = str(tmp_chamber).replace("\\", "/")

    for name in ("reorganize.py", "build_project.py"):
        p = tmp_reorg / name
        text = p.read_text(encoding="utf-8")
        text = text.replace(
            "CHAMBER_ROOT = SCRIPT_DIR.parent",
            f'CHAMBER_ROOT = Path(r"{tmp_chamber}")',
        )
        p.write_text(text, encoding="utf-8")

    # Update catalog's root key too, for any consumers that read it.
    cat = tmp_reorg / "instruments.yaml"
    text = cat.read_text(encoding="utf-8")
    text = text.replace('root: "D:/Chamber"', f'root: "{chamber_str}"')
    cat.write_text(text, encoding="utf-8")


def run(cmd: list[str], cwd: Path, stdin_text: str = "") -> tuple[int, str]:
    r = subprocess.run(cmd, cwd=cwd, input=stdin_text,
                       text=True, capture_output=True, encoding="utf-8")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


# ---------------------------------------------------------------------------
# Main test
# ---------------------------------------------------------------------------

def main() -> int:
    with tempfile.TemporaryDirectory(prefix="chamber_e2e_") as td:
        tmp = Path(td)
        tmp_chamber = tmp / "Chamber"
        tmp_reorg = tmp_chamber / "_reorg"

        print(f"[setup] synthetic root = {tmp_chamber}")
        build_fake_chamber(tmp_chamber)
        patch_scripts(tmp_reorg, tmp_chamber)

        failures: list[str] = []

        def check(cond: bool, msg: str) -> None:
            mark = "PASS" if cond else "FAIL"
            print(f"  [{mark}] {msg}")
            if not cond:
                failures.append(msg)

        # --- 1. dry-run
        print("\n[1] reorganize.py --dry-run")
        rc, out = run([sys.executable, "reorganize.py", "--dry-run"], cwd=tmp_reorg)
        print(out)
        check(rc == 0, "dry-run returned 0")
        plan_csv = tmp_reorg / "rename_plan.csv"
        check(plan_csv.exists(), "rename_plan.csv produced")

        # --- 2. execute (feed 'yes\n' to stdin)
        print("\n[2] reorganize.py --execute  (--no-archive for speed)")
        rc, out = run([sys.executable, "reorganize.py", "--execute", "--no-archive"],
                      cwd=tmp_reorg, stdin_text="yes\n")
        print(out)
        check(rc == 0, "execute returned 0")

        instr_root = tmp_chamber / "01_instruments"
        expected_codes = [
            "CCN200_SN2310-057", "CCN200_SN",
            "CPC3750_SN3750230103", "CPC3750_SN3750221103",
            "CPC3750_SN3750221105",
            "SMPS_SN7002_CPC3750221105", "SMPS_SN7003_CPC3750221103",
            "PROMO2000_SN15639", "PROMO2000_SN22659", "PROMO3000_SN18803",
            "LI7500_SN75D-4824", "LI7500_SN75D-4831",
            "GL840_SN0505170C", "PINE_SN06-03",
            "CASDPOL_SN", "CD5N_SN", "CIMON_SN", "CPI_SN",
            "FTM06D_SN", "HYGRO1011_SN", "MARGA2060_SN", "SkyOPC_SN",
        ]
        for code in expected_codes:
            check((instr_root / code).is_dir(), f"{code}/ exists")

        # CPC 1105 merge — expect cpc_1, cpc_2, cpc_3 (duplicate cpc_1 deduped)
        cpc1105_files = sorted(
            p.name for p in (instr_root / "CPC3750_SN3750221105").rglob("*.csv"))
        check(cpc1105_files == ["cpc_1.csv", "cpc_2.csv", "cpc_3.csv"],
              f"CPC1105 merged files: {cpc1105_files}")

        # SMPS 7002 merge — 3 contributing sources
        smps7002_files = list((instr_root / "SMPS_SN7002_CPC3750221105").rglob("*.p82"))
        check(len(smps7002_files) == 3,
              f"SMPS7002 merged into 3 files (got {len(smps7002_files)})")

        # NIMS_AC and NIMS_Milo parents should be gone (empty)
        check(not (tmp_chamber / "NIMS_AC").exists(), "NIMS_AC parent removed")
        check(not (tmp_chamber / "NIMS_Milo").exists(), "NIMS_Milo parent removed")

        check((tmp_chamber / "00_tools" / "fix.py").exists(),
              "etc/ renamed to 00_tools/ (contents preserved)")
        check((tmp_chamber / "02_campaigns_legacy" / "YSU_20250808").exists(),
              "YSU -> 02_campaigns_legacy/YSU_20250808")

        # --- 3. build a project from a synthetic namelist
        print("\n[3] build_project.py <namelist>")
        nl = {
            "project": {
                "name": "E2E_TEST",
                "title": "End-to-end test",
                "pi": "tester",
                "operators": ["alice", "bob"],
                "start_date": "2026-04-21",
                "end_date":   "2026-04-23",
                "site": "lab",
                "note": "synthetic",
            },
            "instruments": [
                {"code": "CCN200_SN2310-057",
                 "use_period": ["2026-04-21", "2026-04-23"]},
                {"code": "CPC3750_SN3750221105",
                 "use_period": ["2026-04-21", "2026-04-23"]},
                {"code": "SMPS_SN7002_CPC3750221105",
                 "use_period": ["2026-04-21", "2026-04-23"]},
                {"code": "PROMO2000_SN22659",
                 "use_period": ["2026-04-21", "2026-04-23"]},
            ],
            "options": {"copy_mode": "copy", "overwrite": True},
        }
        nl_path = tmp_reorg / "nl.yaml"
        with open(nl_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(nl, f, sort_keys=False, allow_unicode=True)

        rc, out = run([sys.executable, "build_project.py", str(nl_path)],
                      cwd=tmp_reorg)
        print(out)
        check(rc == 0, "build_project returned 0")

        proj = tmp_chamber / "03_projects" / "E2E_TEST"
        check(proj.is_dir(), "project folder created")
        check((proj / "namelist.yaml").exists(), "namelist.yaml preserved")
        check((proj / "README.md").exists(), "README.md generated")
        manifest = proj / "_log" / "copy_manifest.csv"
        check(manifest.exists(), "copy_manifest.csv generated")

        # Count files
        ccn_files = list((proj / "CCN200_SN2310-057").rglob("*.csv"))
        check(len(ccn_files) == 2,
              f"CCN in-range files = 2 (got {len(ccn_files)}) "
              f"[the 260510 file is filtered out]")

        cpc_files = list((proj / "CPC3750_SN3750221105").rglob("*.csv"))
        check(len(cpc_files) == 3,
              f"CPC 1105 files in project = 3 (got {len(cpc_files)})")

        smps_files = list((proj / "SMPS_SN7002_CPC3750221105").rglob("*.p82"))
        check(len(smps_files) == 3,
              f"SMPS 7002 files in project = 3 (got {len(smps_files)})")

        # Manifest sanity
        with open(manifest, encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        check(len(rows) >= 8, f"manifest rows >= 8 (got {len(rows)})")

        # --- Summary
        print("\n" + "=" * 60)
        if failures:
            print(f"FAILED  ({len(failures)} assertion(s))")
            for m in failures:
                print("  -", m)
            return 1
        print("ALL CHECKS PASSED")
        return 0


if __name__ == "__main__":
    sys.exit(main())
