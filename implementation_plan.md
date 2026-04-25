# Step C: Code Quality & Stability Improvements

This plan outlines the implementation of the "P1" stability and quality tasks defined in the handoff document. These changes will make the Chamber project builder robust, maintainable, and safe for production use.

## User Review Required

Please review the proposed tasks below. Once approved, I will execute them.

> [!IMPORTANT]
> **Git Repository Initialization (P1-6):** The handoff document suggests initializing a Git repository to track code changes. 
> **Question:** Do you want me to run `git init` and create an initial commit for this workspace? (Yes/No)

## Proposed Changes

---

### Core Scripts

#### [MODIFY] [reorganize.py](file:///D:/Chamber/_reorg/reorganize.py)
- **P1-3 (Disk Space Guard):** Add a check before `--execute` to ensure there is enough free disk space (Total data size * 1.1) for the archive backup. Prevent execution if space is insufficient.
- **P1-5 (Log Rotation):** Upgrade the basic `logging.FileHandler` to `logging.handlers.RotatingFileHandler` (e.g., max 10MB, 5 backups) to prevent `run.log` from growing indefinitely.

#### [MODIFY] [build_project.py](file:///D:/Chamber/_reorg/build_project.py)
- **P1-5 (Log Rotation):** Apply the same `RotatingFileHandler` logic for consistency.

---

### New Tools & Verification

#### [NEW] [verify_integrity.py](file:///D:/Chamber/_reorg/verify_integrity.py)
- **P1-4 (Integrity Script):** Create a standalone script that walks through `_archive_pre_reorg/` and compares the SHA256 hashes of all files against their new locations in `01_instruments/`.
- Will generate a `verify_report.csv` indicating any missing or mismatched files.

#### [NEW] [run_verify.bat](file:///D:/Chamber/_reorg/run_verify.bat)
- A double-click launcher for the integrity verification script.

---

### Documentation & Dependencies

#### [NEW] [requirements.txt](file:///D:/Chamber/_reorg/requirements.txt)
- **P1-2:** Pin dependencies to ensure reproducible environments.
  ```text
  PyYAML>=6.0,<7.0
  PyQt5>=5.15,<6.0
  ```

#### [NEW] [TROUBLESHOOTING.md](file:///D:/Chamber/_reorg/TROUBLESHOOTING.md)
- **P1-7 (Cookbook):** Document common issues encountered during the 8 iterations of validator testing (e.g., `NO_DATA` fixes, format fallbacks, `hardlink` failures).

---

### Automated Testing

#### [NEW] [tests/test_parse_date.py](file:///D:/Chamber/_reorg/tests/test_parse_date.py)
- **P1-8 (Unit Tests):** Extract and test the `parse_date_from` logic against all 11 supported formats, regex captures, and edge cases.

#### [NEW] [tests/test_namelist.py](file:///D:/Chamber/_reorg/tests/test_namelist.py)
- **P1-8 (Unit Tests):** Test the namelist validation logic (missing fields, invalid date ranges, unrecognized instrument codes).

## Verification Plan

### Automated Tests
- Run `python -m unittest discover tests/` to ensure all new unit tests pass.
- Run `python test_e2e.py` to ensure the E2E regression test remains green after modifying the core scripts.

### Manual Verification
- Simulate a low-disk space scenario (by lowering the threshold) to verify the disk guard aborts correctly.
- Generate a large log output to confirm that `run.log` rotates correctly at 10MB.
