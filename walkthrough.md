# Chamber Reorganization & Project Builder — Walkthrough

> Paired with [`사용설명서.md`](./사용설명서.md) (Korean). Same content, English tone.

## TL;DR

Double-click the `.bat` files in `D:\Chamber\_reorg\` — that's the whole workflow.

---

## One-time setup

### 1. Verify Python
In `cmd`:
```
python --version
```
Must be 3.10+. If missing, install from <https://www.python.org/> and **check "Add Python to PATH"**.

### 2. External backup (strongly recommended)
```
robocopy D:\Chamber  E:\Chamber_backup_20260424  /MIR /XJ
```

### 3. Install Python dependencies
From `D:\Chamber\_reorg\`:
```
python -m pip install -r requirements.txt
```
(Pinned: PyYAML 6.x, PyQt5 5.15.x — see `requirements.txt`)

---

## The pipeline (run in order)

### ① Inventory — `run_preflight.bat`
- Scans every folder under `D:\Chamber`
- Reports where each folder will land after reorg, plus file counts, sizes, and date ranges
- Output: `preflight_report.csv` — open in Excel to review

### ② Date-parse validation — `python validator.py`
- Confirms that the `date_regex` / `date_format` rules in `instruments.yaml` actually match real files
- Look for the line `All instruments parse dates correctly.` before proceeding
- If something fails, run `python validator.py --verbose` to see un-parsed file samples

### ③ Reorganization plan — `run_dryrun.bat`
- Generates `rename_plan.csv` (no actual changes)
- Open in Excel; review all 36 rename / merge / move steps

### ④ Real reorganization — `run_reorg.bat`
- Type `yes` at the prompt
- Originals are auto-archived to `D:\Chamber\_archive_pre_reorg\`
- A pre-execution disk-space guard aborts if free space is insufficient (use `--force` to bypass, `--no-archive` to skip backup)
- Result:
  ```
  D:\Chamber\
   ├─ 00_tools\           ← was: etc
   ├─ 00_resources\       ← was: files
   ├─ 01_instruments\     ← per-instrument folders (MODEL_SN<serial>)
   ├─ 02_archives\        ← was: POST, thai_old_*
   ├─ 02_campaigns_legacy\← was: YSU, PNU, unist
   └─ 03_projects\        ← (created in step ⑥)
  ```

### ⑤ Fill unknown serials (optional)
1. Open `serials_to_fill.md` — checklist of 9 instruments without confirmed SN
2. Read each instrument's physical label and record the serial
3. Edit `instruments.yaml`:
   - `serial: "<actual>"`
   - `code:  "<MODEL>_SN<actual>"`
   - `path:  "01_instruments/<MODEL>_SN<actual>"`
4. Double-click `run_update_serials.bat` — folders rename automatically

### ⑥ Build the first project — `run_gui.bat`

**Using the GUI:**

1. **Project section**: Name, title, PI, operators, start/end date, site, note
2. Click **"Apply to all instruments"** to push the project period to every instrument
3. **Instruments table**:
   - Tick the **"Use"** column to include an instrument
   - Override per-instrument Start/End if its actual period differs from the project window
4. **Options**:
   - `hardlink` (default): saves disk (same drive only)
   - `copy`: full copy — safest, but consumes the full size
   - `symlink`: requires Windows Developer Mode
5. **Save namelist…** persists the configuration for re-use
6. **Preview (dry-run)** counts files without copying
7. **Build project ▶** materializes the project

**Result:**
```
D:\Chamber\03_projects\<project_name>\
 ├─ namelist.yaml           ← exact configuration used
 ├─ README.md               ← auto-generated summary
 ├─ _log\
 │   ├─ copy_manifest.csv   ← every linked file with its hash
 │   └─ run.log             ← build log
 ├─ CCN200_SN2310-057\      ← per-instrument data (date-filtered)
 ├─ CPC3750_SN3750221105\
 └─ ...
```

---

## Troubleshooting

### Roll back the reorganization
```
run_rollback.bat
```
Restores everything from `_archive_pre_reorg\`.

### GUI won't open
```
cd D:\Chamber\_reorg
python -m pip install -r requirements.txt
python chamber_gui.py
```

### Project built incorrectly
```
python build_project.py <namelist.yaml> --rollback
```
Deletes only that one project folder.

### `hardlink` fell back to `copy`
- Hardlinks require source and destination on the same drive
- Use `copy` mode, or move the project root to the same drive

### A specific instrument shows `NO_DATA` or `partial`
See `TROUBLESHOOTING.md` — a cookbook of every parsing edge case encountered during the 8 iterations of validator stabilization.

---

## File reference

| File / folder | Purpose |
|---|---|
| `instruments.yaml` | **Instrument catalog** (single source of truth) |
| `serials_to_fill.md` | Unknown-SN checklist |
| `walkthrough.md` | This document (English) |
| `사용설명서.md` | Same content, Korean |
| `README.md` | Project README |
| `TROUBLESHOOTING.md` | Edge-case cookbook |
| `requirements.txt` | Python dependencies (pinned) |
| `run_preflight.bat` | ① Inventory |
| `run_dryrun.bat` | ③ Plan only |
| `run_reorg.bat` | ④ Reorganize |
| `run_update_serials.bat` | ⑤ Sync SN changes to folder names |
| `run_gui.bat` | ⑥ Launch GUI |
| `run_rollback.bat` | Emergency restore |
| `run_verify.bat` | SHA256 integrity check (post-reorg) |
| `validator.py` | Date-parse validator (legacy structure) |
| `validator_new.py` | Date-parse validator (current `01_instruments/` structure) |
| `verify_integrity.py` | Compares `_archive_pre_reorg` ↔ `01_instruments` hashes |
| `test_e2e.py` | End-to-end synthetic-data regression test |
| `tests/` | Unit tests (parse_date, namelist) |
| `preflight_report.csv` | Inventory output |
| `rename_plan.csv` | Reorganization plan |

---

## Command-line (advanced)

```bash
cd D:\Chamber\_reorg

# Catalog validation
python validator.py
python validator.py --verbose                     # show un-parsed samples
python validator.py --code CPI_SN                 # one instrument only

# Reorganization
python reorganize.py --dry-run
python reorganize.py --execute
python reorganize.py --execute --no-archive       # skip backup (faster, riskier)
python reorganize.py --execute --force            # bypass disk-space guard
python reorganize.py --update-serials
python reorganize.py --rollback

# Project builder
python build_project.py namelist.MYPROJECT.yaml --preview
python build_project.py namelist.MYPROJECT.yaml
python build_project.py namelist.MYPROJECT.yaml --rollback

# Inventory / verification
python preflight.py
python verify_integrity.py                        # post-reorg SHA256 check
python test_e2e.py                                # synthetic-data regression
python -m unittest discover tests/                # unit tests
```

---

## Safety guarantees

1. **`reorganize.py --execute` always copies originals to `_archive_pre_reorg\` first** before any rename / merge.
2. **`build_project.py` never modifies `01_instruments\`** — it only reads, and writes new content to `03_projects\`.
3. **Every action is logged** — `_reorg/run.log`, `01_instruments/_meta/merge_log.csv`, and `03_projects/<proj>/_log/copy_manifest.csv`.
4. **Conflict detection** — during merges, identical filenames with different SHA256 contents are preserved under `_conflicts/`.
5. **Disk-space guard** — `--execute` aborts if `_archive_pre_reorg` would not fit; bypass only with `--force` or `--no-archive`.
