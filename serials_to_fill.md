# Serials To Fill — Unknown Instrument Serial Numbers

Generated: 2026-04-24
Source scan: `D:\Chamber` (file headers + filenames)

This checklist lists instruments whose **serial number was not found** in any data
file. After confirming the serial from the physical device label, manual, purchase
record, or calibration certificate, update `instruments.yaml` **and** rename the
corresponding folder under `01_instruments/`.

---

## How to fill

1. Inspect the instrument's label / rear panel / calibration certificate.
2. Record the serial in the table below.
3. Edit `instruments.yaml`:
   - Update the `serial:` field.
   - Update the `code:` field to `MODEL_SN{serial}` (e.g., `CPI_SN` → `CPI_SNABC1234`).
   - Update the `path:` to match.
4. Run:  `python reorganize.py --update-serials`
   (this renames the folder in `01_instruments/` to match the new code).

---

## Checklist (9 instruments)

| # | Instrument | Current folder (after reorg) | Source of data that lacked SN | Filled serial |
|---|---|---|---|---|
| 1 | **DMT CAS-DPOL** (Cloud Aerosol Spectrometer) | `01_instruments/CASDPOL_SN` | PADS_Data CSV has no SN line in header | `____________` |
| 2 | **DMT CCN-200 (2022 unit)** | `01_instruments/CCN200_SN` | 2022 firmware — no SN row in CSV header | `____________` |
| 3 | **CD5N** | `01_instruments/CD5N_SN` | Data-only CSV, no metadata | `____________` |
| 4 | **CIMON** solar radiation sensor | `01_instruments/CIMON_SN` | Sensor log only | `____________` |
| 5 | **SPEC CPI** (Cloud Particle Imager) | `01_instruments/CPI_SN` | Binary `.roi/.cpi` — no readable metadata | `____________` |
| 6 | **FTM06D** | `01_instruments/FTM06D_SN` | Simple sensor CSV | `____________` |
| 7 | **Hygrometer 1011** | `01_instruments/HYGRO1011_SN` | Data-only CSV | `____________` |
| 8 | **Metrohm MARGA 2060** | `01_instruments/MARGA2060_SN` | Only model code `2060` in filename | `____________` |
| 9 | **GRIMM Sky-OPC** | `01_instruments/SkyOPC_SN` | Binary `.dat` | `____________` |

---

## Known serials (reference — no action needed)

| Instrument | Serial | Where found |
|---|---|---|
| DMT CCN-200 (NEW) | `2310-057` | CSV header line 3 |
| TSI CPC 3750 (0103 / AC) | `3750230103` | CSV `Serial:` |
| TSI CPC 3750 (1103 / CC) | `3750221103` | CSV `Serial:` |
| TSI CPC 3750 (1105 / AC) | `3750221105` | CSV `Serial:` |
| GRAPHTEC GL840 | `0505170C` | `.gbd` binary header |
| LI-COR LI-7500 (0807) | `75D-4824` | Header `SN:` |
| LI-COR LI-7500 (0808) | `75D-4831` | Header `SN:` |
| Bilfinger PINE 06-03 | `06-03` | Filename + config |
| Palas Promo 2000 (AC) | `15639` | Filename `DATA_auto_15639_...` |
| Palas Promo 2000 (NEW) | `22659` | Filename `DATA_auto_22659_...` |
| Palas Promo 3000 | `18803` | Filename `DATA_auto_18803_...` |
| TSI SMPS (3082 DMA) | `7002` / `7003` | TXT header `Detector S/N` + folder name |

---

## Notes

- Folder names with an empty serial keep the trailing underscore: `XXX_SN`.
  This reserves the position so a simple string append completes the name once
  the serial is confirmed.
- For CCN200_SN (2022 unit), if the physical unit no longer exists, tag the
  `note:` field in `instruments.yaml` as `legacy_unit: true` and leave the
  serial empty.
- After each fill, commit or back up `instruments.yaml` so the catalog history
  is preserved.
