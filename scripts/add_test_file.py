"""Register your own (deliberately awful) supplier file as a sixth vendor and test the
pipeline on it.

  .venv/bin/python scripts/add_test_file.py ~/Downloads/ugly_quote.pdf
  .venv/bin/python scripts/add_test_file.py photo.jpg another_sheet.xlsx   # multiple files

Then click "Process →" on "Test Supplier" in the UI (or: .venv/bin/python -m backend.pipeline TEST).
Supported by extension: .xlsx .pdf .docx .jpg .jpeg .png .txt .csv

Cleanup before recording:  .venv/bin/python -m backend.make_vendor_files   (restores the
five real vendors + pristine artifacts)  then  scripts/stage_demo.py
"""
import json
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
FILES = ROOT / "data" / "vendor_files"
REG = ROOT / "data" / "vendors.json"

OK = {".xlsx", ".pdf", ".docx", ".jpg", ".jpeg", ".png", ".txt", ".csv"}

paths = [pathlib.Path(p).expanduser() for p in sys.argv[1:]]
if not paths:
    raise SystemExit(__doc__)
names = []
for p in paths:
    if not p.exists():
        raise SystemExit(f"not found: {p}")
    if p.suffix.lower() not in OK:
        raise SystemExit(f"unsupported extension {p.suffix} (supported: {sorted(OK)})")
    shutil.copy(p, FILES / p.name)
    names.append(p.name)

reg = json.loads(REG.read_text())
reg["TEST"] = {"name": "Test Supplier", "files": names,
               "contact": "You", "email": "test@local"}
REG.write_text(json.dumps(reg, indent=1))
print(f"Registered TEST vendor with: {', '.join(names)}")
print("Now: click 'Process →' on Test Supplier in the UI, or run:")
print("  .venv/bin/python -m backend.pipeline TEST")
