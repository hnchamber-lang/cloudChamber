"""
chamber_gui.py — PyQt5 GUI for building a Chamber project namelist.

Lets the user:
    * Fill project metadata (name, title, PI, operators, dates, site, note)
    * Select instruments from instruments.yaml (grouped by model, multi-SN units
      shown as separate selectable rows)
    * Set per-instrument use_period (defaults to project dates)
    * Choose copy mode (copy / hardlink / symlink) and overwrite flag
    * Save / load a namelist.yaml
    * Preview (dry-run) file counts and total size
    * Execute — calls build_project.py in a subprocess and streams its log

Requires:   pip install pyyaml PyQt5
Run:        python chamber_gui.py
"""

from __future__ import annotations

import sys
import subprocess
from dataclasses import dataclass
from datetime import datetime, date
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.stderr.write("ERROR: PyYAML not installed. Run:  pip install pyyaml\n")
    sys.exit(1)

try:
    from PyQt5 import QtCore, QtGui, QtWidgets
except ImportError:
    sys.stderr.write("ERROR: PyQt5 not installed. Run:  pip install PyQt5\n")
    sys.exit(1)


SCRIPT_DIR = Path(__file__).resolve().parent
CHAMBER_ROOT = SCRIPT_DIR.parent
CATALOG_PATH = SCRIPT_DIR / "instruments.yaml"
BUILDER = SCRIPT_DIR / "build_project.py"


# ---------------------------------------------------------------------------
# Catalog loading
# ---------------------------------------------------------------------------

@dataclass
class CatalogEntry:
    code: str
    model: str
    serial: str
    category: str
    note: str


def load_catalog() -> list[CatalogEntry]:
    with open(CATALOG_PATH, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    out = []
    for e in raw.get("instruments", []):
        out.append(CatalogEntry(
            code=e["code"], model=e.get("model", ""), serial=e.get("serial", ""),
            category=e.get("category", ""), note=e.get("note", ""),
        ))
    return out


# ---------------------------------------------------------------------------
# Instrument selection table
# ---------------------------------------------------------------------------

class InstrumentTable(QtWidgets.QTableWidget):
    """One row per catalog entry: [use?, model, serial, category, start, end, note]."""

    COLS = ("Use", "Model", "Serial", "Category", "Start", "End", "Note")

    def __init__(self, entries: list[CatalogEntry], parent=None):
        super().__init__(len(entries), len(self.COLS), parent)
        self.entries = entries
        self.setHorizontalHeaderLabels(self.COLS)
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)

        for row, e in enumerate(entries):
            chk = QtWidgets.QTableWidgetItem()
            chk.setCheckState(QtCore.Qt.Unchecked)
            chk.setFlags(chk.flags() | QtCore.Qt.ItemIsUserCheckable)
            self.setItem(row, 0, chk)
            self.setItem(row, 1, QtWidgets.QTableWidgetItem(e.model))
            serial_item = QtWidgets.QTableWidgetItem(e.serial or "(unknown)")
            if not e.serial:
                serial_item.setForeground(QtGui.QBrush(QtGui.QColor("#b00")))
            self.setItem(row, 2, serial_item)
            self.setItem(row, 3, QtWidgets.QTableWidgetItem(e.category))

            start_edit = QtWidgets.QDateEdit(calendarPopup=True)
            start_edit.setDisplayFormat("yyyy-MM-dd")
            end_edit = QtWidgets.QDateEdit(calendarPopup=True)
            end_edit.setDisplayFormat("yyyy-MM-dd")
            today = QtCore.QDate.currentDate()
            start_edit.setDate(today)
            end_edit.setDate(today)
            self.setCellWidget(row, 4, start_edit)
            self.setCellWidget(row, 5, end_edit)

            note_item = QtWidgets.QTableWidgetItem(e.note)
            note_item.setToolTip(e.note)
            self.setItem(row, 6, note_item)

        self.resizeColumnsToContents()
        self.horizontalHeader().setStretchLastSection(True)

    def apply_project_dates(self, start: QtCore.QDate, end: QtCore.QDate) -> None:
        """Set every row's start/end to project-level dates."""
        for row in range(self.rowCount()):
            self.cellWidget(row, 4).setDate(start)
            self.cellWidget(row, 5).setDate(end)

    def selected_items(self) -> list[dict]:
        out = []
        for row, e in enumerate(self.entries):
            if self.item(row, 0).checkState() != QtCore.Qt.Checked:
                continue
            s = self.cellWidget(row, 4).date().toString("yyyy-MM-dd")
            t = self.cellWidget(row, 5).date().toString("yyyy-MM-dd")
            out.append({"code": e.code, "use_period": [s, t]})
        return out

    def apply_loaded(self, instruments: list[dict]) -> None:
        """Tick rows and set dates from a loaded namelist."""
        by_code = {it["code"]: it for it in instruments}
        for row, e in enumerate(self.entries):
            it = by_code.get(e.code)
            if not it:
                self.item(row, 0).setCheckState(QtCore.Qt.Unchecked)
                continue
            self.item(row, 0).setCheckState(QtCore.Qt.Checked)
            s, t = it["use_period"]
            self.cellWidget(row, 4).setDate(QtCore.QDate.fromString(str(s)[:10], "yyyy-MM-dd"))
            self.cellWidget(row, 5).setDate(QtCore.QDate.fromString(str(t)[:10], "yyyy-MM-dd"))


# ---------------------------------------------------------------------------
# Subprocess runner (build_project.py)
# ---------------------------------------------------------------------------

class BuilderRunner(QtCore.QObject):
    output = QtCore.pyqtSignal(str)
    finished = QtCore.pyqtSignal(int)

    def __init__(self, namelist_path: Path, preview: bool):
        super().__init__()
        self.namelist_path = namelist_path
        self.preview = preview
        self._proc: subprocess.Popen | None = None

    def run(self) -> None:
        args = [sys.executable, str(BUILDER), str(self.namelist_path)]
        if self.preview:
            args.append("--preview")
        try:
            self._proc = subprocess.Popen(
                args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", bufsize=1,
            )
            assert self._proc.stdout is not None
            for line in self._proc.stdout:
                self.output.emit(line.rstrip())
            rc = self._proc.wait()
        except Exception as e:                           # noqa: BLE001
            self.output.emit(f"[runner error] {e}")
            rc = -1
        self.finished.emit(rc)


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Chamber Project Builder")
        self.resize(1200, 950)

        try:
            self.catalog = load_catalog()
        except FileNotFoundError:
            QtWidgets.QMessageBox.critical(
                self, "Catalog missing",
                f"instruments.yaml not found at:\n{CATALOG_PATH}")
            sys.exit(1)

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        root = QtWidgets.QVBoxLayout(central)

        root.addWidget(self._make_project_group())
        root.addWidget(self._make_instruments_group(), stretch=3)
        root.addWidget(self._make_options_group())
        root.addWidget(self._make_actions_row())
        root.addWidget(self._make_log_pane(), stretch=1)

        self.status = self.statusBar()
        self.status.showMessage("Ready")

        self._thread: QtCore.QThread | None = None
        self._runner: BuilderRunner | None = None

    # ------------- Project metadata -------------
    def _make_project_group(self) -> QtWidgets.QWidget:
        box = QtWidgets.QGroupBox("Project")
        grid = QtWidgets.QGridLayout(box)

        self.ed_name = QtWidgets.QLineEdit()
        self.ed_name.setPlaceholderText("e.g. ASIA_AQ_2026_JWCHA")
        self.ed_title = QtWidgets.QLineEdit()
        self.ed_pi = QtWidgets.QLineEdit()
        self.ed_operators = QtWidgets.QLineEdit()
        self.ed_operators.setPlaceholderText("comma-separated, e.g. Hong Gildong, Kim Yeongu")
        self.ed_site = QtWidgets.QLineEdit()
        self.ed_note = QtWidgets.QLineEdit()

        self.de_start = QtWidgets.QDateEdit(calendarPopup=True)
        self.de_start.setDisplayFormat("yyyy-MM-dd")
        self.de_start.setDate(QtCore.QDate.currentDate())
        self.de_end = QtWidgets.QDateEdit(calendarPopup=True)
        self.de_end.setDisplayFormat("yyyy-MM-dd")
        self.de_end.setDate(QtCore.QDate.currentDate())
        self.btn_apply_dates = QtWidgets.QPushButton("Apply to all instruments")
        self.btn_apply_dates.setToolTip("Set every instrument's Start/End to the project dates")

        grid.addWidget(QtWidgets.QLabel("Name *"),    0, 0); grid.addWidget(self.ed_name,    0, 1, 1, 3)
        grid.addWidget(QtWidgets.QLabel("Title"),     1, 0); grid.addWidget(self.ed_title,   1, 1, 1, 3)
        grid.addWidget(QtWidgets.QLabel("PI"),        2, 0); grid.addWidget(self.ed_pi,      2, 1)
        grid.addWidget(QtWidgets.QLabel("Operators"), 2, 2); grid.addWidget(self.ed_operators, 2, 3)
        grid.addWidget(QtWidgets.QLabel("Site"),      3, 0); grid.addWidget(self.ed_site,    3, 1)
        grid.addWidget(QtWidgets.QLabel("Note"),      3, 2); grid.addWidget(self.ed_note,    3, 3)
        grid.addWidget(QtWidgets.QLabel("Start date *"), 4, 0); grid.addWidget(self.de_start, 4, 1)
        grid.addWidget(QtWidgets.QLabel("End date *"),   4, 2); grid.addWidget(self.de_end,   4, 3)
        grid.addWidget(self.btn_apply_dates, 5, 0, 1, 4)

        self.btn_apply_dates.clicked.connect(self._apply_project_dates)
        return box

    # ------------- Instruments -------------
    def _make_instruments_group(self) -> QtWidgets.QWidget:
        box = QtWidgets.QGroupBox("Instruments (from instruments.yaml)")
        lay = QtWidgets.QVBoxLayout(box)
        self.tbl = InstrumentTable(self.catalog)
        lay.addWidget(self.tbl)
        return box

    # ------------- Options -------------
    def _make_options_group(self) -> QtWidgets.QWidget:
        box = QtWidgets.QGroupBox("Options")
        lay = QtWidgets.QHBoxLayout(box)

        lay.addWidget(QtWidgets.QLabel("Copy mode:"))
        self.cb_copymode = QtWidgets.QComboBox()
        self.cb_copymode.addItems(["hardlink", "copy", "symlink"])
        self.cb_copymode.setToolTip(
            "hardlink: saves disk space (same volume only)\n"
            "copy:     full duplicate (safest, largest)\n"
            "symlink:  pointer (Windows needs admin/developer-mode)")
        lay.addWidget(self.cb_copymode)

        self.chk_overwrite = QtWidgets.QCheckBox("Overwrite existing project")
        lay.addWidget(self.chk_overwrite)
        lay.addStretch()
        return box

    # ------------- Actions -------------
    def _make_actions_row(self) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        row = QtWidgets.QHBoxLayout(w)
        self.btn_load = QtWidgets.QPushButton("Load namelist…")
        self.btn_save = QtWidgets.QPushButton("Save namelist…")
        self.btn_preview = QtWidgets.QPushButton("Preview (dry-run)")
        self.btn_build = QtWidgets.QPushButton("Build project ▶")
        self.btn_build.setStyleSheet("font-weight: bold")

        row.addWidget(self.btn_load)
        row.addWidget(self.btn_save)
        row.addStretch()
        row.addWidget(self.btn_preview)
        row.addWidget(self.btn_build)

        self.btn_load.clicked.connect(self._load_namelist)
        self.btn_save.clicked.connect(self._save_namelist)
        self.btn_preview.clicked.connect(lambda: self._run_builder(preview=True))
        self.btn_build.clicked.connect(lambda: self._run_builder(preview=False))
        return w

    # ------------- Log pane -------------
    def _make_log_pane(self) -> QtWidgets.QWidget:
        box = QtWidgets.QGroupBox("Output")
        lay = QtWidgets.QVBoxLayout(box)
        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(QtGui.QFont("Consolas", 9))
        lay.addWidget(self.log)
        return box

    # =====================================================================
    # Actions
    # =====================================================================

    def _apply_project_dates(self) -> None:
        self.tbl.apply_project_dates(self.de_start.date(), self.de_end.date())
        self.status.showMessage("Applied project dates to all instruments.", 3000)

    def _collect_namelist(self) -> dict:
        operators = [x.strip() for x in self.ed_operators.text().split(",") if x.strip()]
        return {
            "project": {
                "name": self.ed_name.text().strip(),
                "title": self.ed_title.text().strip(),
                "pi": self.ed_pi.text().strip(),
                "operators": operators,
                "start_date": self.de_start.date().toString("yyyy-MM-dd"),
                "end_date":   self.de_end.date().toString("yyyy-MM-dd"),
                "site": self.ed_site.text().strip(),
                "note": self.ed_note.text().strip(),
            },
            "instruments": self.tbl.selected_items(),
            "options": {
                "copy_mode": self.cb_copymode.currentText(),
                "overwrite": self.chk_overwrite.isChecked(),
                "include_raw": True,
            },
        }

    def _validate(self, nl: dict) -> str | None:
        p = nl["project"]
        if not p["name"]:
            return "Project name is required."
        if " " in p["name"]:
            return "Project name must not contain spaces."
        if not nl["instruments"]:
            return "At least one instrument must be selected."
        if p["end_date"] < p["start_date"]:
            return "End date is before start date."
        return None

    def _save_namelist(self) -> Path | None:
        nl = self._collect_namelist()
        err = self._validate(nl)
        if err:
            QtWidgets.QMessageBox.warning(self, "Invalid", err)
            return None
        default = SCRIPT_DIR / f"namelist.{nl['project']['name'] or 'project'}.yaml"
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save namelist", str(default), "YAML (*.yaml)")
        if not path:
            return None
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(nl, f, sort_keys=False, allow_unicode=True)
        self.status.showMessage(f"Saved: {path}", 5000)
        return Path(path)

    def _load_namelist(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Load namelist", str(SCRIPT_DIR), "YAML (*.yaml)")
        if not path:
            return
        with open(path, encoding="utf-8") as f:
            nl = yaml.safe_load(f)

        p = nl.get("project", {})
        self.ed_name.setText(str(p.get("name", "")))
        self.ed_title.setText(str(p.get("title", "")))
        self.ed_pi.setText(str(p.get("pi", "")))
        self.ed_operators.setText(", ".join(p.get("operators", []) or []))
        self.ed_site.setText(str(p.get("site", "")))
        self.ed_note.setText(str(p.get("note", "")))
        if p.get("start_date"):
            self.de_start.setDate(QtCore.QDate.fromString(str(p["start_date"])[:10], "yyyy-MM-dd"))
        if p.get("end_date"):
            self.de_end.setDate(QtCore.QDate.fromString(str(p["end_date"])[:10], "yyyy-MM-dd"))

        self.tbl.apply_loaded(nl.get("instruments", []) or [])

        opts = nl.get("options", {}) or {}
        idx = self.cb_copymode.findText(opts.get("copy_mode", "hardlink"))
        if idx >= 0:
            self.cb_copymode.setCurrentIndex(idx)
        self.chk_overwrite.setChecked(bool(opts.get("overwrite", False)))

        self.status.showMessage(f"Loaded: {path}", 5000)

    def _run_builder(self, *, preview: bool) -> None:
        nl = self._collect_namelist()
        err = self._validate(nl)
        if err:
            QtWidgets.QMessageBox.warning(self, "Invalid", err)
            return

        # Save a temporary namelist next to the script so the builder can load it
        tmp = SCRIPT_DIR / f"_gui_tmp_namelist.yaml"
        with open(tmp, "w", encoding="utf-8") as f:
            yaml.safe_dump(nl, f, sort_keys=False, allow_unicode=True)

        self.log.clear()
        self.log.appendPlainText(f"[gui] running {'PREVIEW' if preview else 'BUILD'} ...")
        self._set_busy(True)

        self._thread = QtCore.QThread(self)
        self._runner = BuilderRunner(tmp, preview=preview)
        self._runner.moveToThread(self._thread)
        self._thread.started.connect(self._runner.run)
        self._runner.output.connect(self.log.appendPlainText)
        self._runner.finished.connect(self._on_builder_done)
        self._thread.start()

    def _on_builder_done(self, rc: int) -> None:
        self._set_busy(False)
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()
        msg = "completed successfully" if rc == 0 else f"FAILED (rc={rc})"
        self.log.appendPlainText(f"[gui] builder {msg}")
        self.status.showMessage(msg, 5000)

    def _set_busy(self, busy: bool) -> None:
        for b in (self.btn_load, self.btn_save, self.btn_preview, self.btn_build):
            b.setEnabled(not busy)


# ---------------------------------------------------------------------------

def main() -> int:
    app = QtWidgets.QApplication(sys.argv)
    w = MainWindow()
    w.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
