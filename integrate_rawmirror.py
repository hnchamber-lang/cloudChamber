"""integrate_rawmirror.py
Hardlink raw_mirror campaign data into 01_instruments/<code>/_jwcha_20260421/.
Run once after reorg, when build_project.py needs to see active campaign data.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

CHAMBER = Path(r"D:\Chamber")
SRC_ROOT = CHAMBER / "03_projects" / "ASIA_AQ_2026_JWCHA_rawmirror" / "asia_aq_jwcha_20260421"
DST_ROOT = CHAMBER / "01_instruments"
SUBDIR = "_jwcha_20260421"

MAPPING = {
    "CCN_057":          "CCN200_SN2310-057",
    "CPC_0103":         "CPC3750_SN3750230103",
    "CPC_1103":         "CPC3750_SN3750221103",
    "MARGA":            "MARGA2060_SN",
    "PINE_112":         "PINE_SN06-03",
    "PROMO2000_15639":  "PROMO2000_SN15639",
    "SMPS_7003":        "SMPS_SN7003_CPC3750221103",
    "Sky-OPC":          "SkyOPC_SN",
}


def main() -> int:
    if not SRC_ROOT.exists():
        print(f"ERROR: source missing: {SRC_ROOT}")
        return 1

    total_linked = 0
    total_skipped = 0
    total_fallback_copied = 0

    for src_name, dst_name in MAPPING.items():
        src_dir = SRC_ROOT / src_name
        dst_dir = DST_ROOT / dst_name / SUBDIR
        if not src_dir.exists():
            print(f"  skip (no src): {src_name}")
            continue
        dst_dir.mkdir(parents=True, exist_ok=True)

        linked = skipped = fallback = 0
        for src_file in src_dir.rglob("*"):
            if not src_file.is_file():
                continue
            rel = src_file.relative_to(src_dir)
            dst_file = dst_dir / rel
            if dst_file.exists():
                skipped += 1
                continue
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.link(src_file, dst_file)
                linked += 1
            except OSError as e:
                # fallback to copy if hardlink fails (e.g., across volumes)
                import shutil
                shutil.copy2(src_file, dst_file)
                fallback += 1

        print(f"  {src_name:20s} -> {dst_name:30s}  linked={linked}  skipped={skipped}  copied={fallback}")
        total_linked += linked
        total_skipped += skipped
        total_fallback_copied += fallback

    print(f"\nTOTAL  linked={total_linked}  skipped={total_skipped}  copied={total_fallback_copied}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
