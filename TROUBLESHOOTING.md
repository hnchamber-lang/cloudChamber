# Chamber Builder Troubleshooting Cookbook

This document logs common issues and their solutions encountered when maintaining or using the Chamber Reorganization and Builder tools.

## 1. `validator.py` Reports `NO_DATA` for an Instrument
**Symptoms:** Running `python validator.py` shows `0` for Matched/Unmatched and `NO_DATA` status.
**Cause 1:** The `file_patterns` in `instruments.yaml` do not match the actual files.
**Solution 1:** Check the file extensions. Are they uppercase (`*.CSV`)? Are there other extensions? Add them to the `file_patterns` list in the catalog.
**Cause 2:** The folder is completely missing, or `legacy_paths` is pointing to an incorrect directory name.

## 2. Unparsed Files (`PARTIAL` or `PARSE_FAIL`)
**Symptoms:** `validator.py` shows unmatched files.
**Solution:** Run `python validator.py --verbose --code <INSTRUMENT_CODE>` to see the exact filenames failing.
- Check if the regex `date_regex` needs adjusting to capture the date group properly `( )`.
- Ensure `date_format` perfectly matches the extracted string.
- If the date is encoded differently in different files for the same instrument, consider simplifying the regex or relying on `date_source: folder`.

## 3. `build_project.py` Hardlink Failure (`ENOTSUP`)
**Symptoms:** Project build fails with an OS Error regarding hard links.
**Cause:** You are trying to build a project (`03_projects/`) on a different physical drive or volume than the source data (`01_instruments/`). Hard links only work on the same volume.
**Solution:** In `chamber_gui.py` or `namelist.yaml`, change `copy_mode: "hardlink"` to `copy_mode: "copy"`.

## 4. `reorganize.py --execute` Aborts Due to Disk Space
**Symptoms:** The script prints `Disk space guard aborted execution! Need ~80GB...`
**Cause:** The script automatically attempts to copy the entire `D:\Chamber` tree to `_archive_pre_reorg` before touching any files. Your D: drive lacks the required space.
**Solution:** 
- Free up space on D:.
- Run `python reorganize.py --execute --no-archive` (Riskier, disables the backup safety net).
- Or run `python reorganize.py --execute --force` to bypass the guard entirely.

## 5. Duplicate Files During Merge (SMPS or CPC)
**Symptoms:** `run.log` reports `conflict_kept` during a merge operation.
**Cause:** Two folders were merged (e.g., `SMPS7002` and `NIMS_AC/SMPS`), and they both contained a file with the exact same name, but differing contents (SHA256 mismatch).
**Solution:** The script safely keeps the differing file under `01_instruments/<instrument>/_conflicts/<original_folder>/`. You should manually review this `_conflicts` folder to determine which file is the correct one.
