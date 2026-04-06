# GUI Example

Tkinter application demonstrating the two-step ingest → query workflow.

```bash
python examples/gui/main.py
```

**First run:** click "Select raw folder & ingest" to read raw `.xlsx` files and store
them in `./data/`.

**Subsequent runs:** click "Load from catalog" (or it auto-loads on startup). No
raw file reprocessing — loads from DuckDB instantly.

## Migration to PyQt6/PySide6

All business logic is in `TripCollection` — the GUI only calls the API. To migrate:
replace `tk.*` with `QWidget` equivalents. The `TripCollection` lines are identical.
