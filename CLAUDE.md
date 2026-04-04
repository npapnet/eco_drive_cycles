# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Fuel EKO Wars** — a telematics system for analyzing OBD-II vehicle data to compute eco-driving scores.

This repo is a **knowledge base**, not a product repo. Its primary purpose is to consolidate, understand, and refine early-stage student work related to the Fuel Eco Wars concept. The student contributions (mainly `students/DriveGUI/`) represent a first working prototype that needs significant refinement before it can serve as a reliable foundation for further development.

Raw driving-cycle data (`_data/`) was collected via the Torque app and exported as CSV/XLSX.

## Running the Code

```bash
# Launch the main GUI
cd students/DriveGUI
python driving_cycles_calculatorV1.py

# Run a single visualization module standalone
python average_speed.py
```

No build system, test framework, or linter is configured. This is a known gap and a current priority.

## Development Priorities

The student code works but mixes concerns heavily — calculation logic and presentation (Matplotlib charts, Tkinter GUI) are interleaved throughout. Refining this is the first major engineering task.

Ordered priorities:

1. **Separate calculation from presentation.** Extract pure computation (speed smoothing, acceleration derivation, metric aggregation, representative-route scoring) into standalone functions with no GUI or chart dependencies. The 13 visualization modules each re-implement data loading and metric computation inline — this logic should live in a shared calculation layer.

2. **Add unit tests.** Once calculation logic is isolated, write unit tests against it. Tests are the safety net that makes all future refactoring safe. Start with `calculations.py` core transforms (time conversion, smoothing, acceleration splitting) and the similarity scoring in `representative_route.py`.

3. **Add a linter.** Configure a linter (e.g. `ruff`) to enforce code style and catch obvious errors. This should be set up before new code is written, not after.

4. **Incrementally improve the student code** with the above infrastructure in place.

When suggesting or making changes, always ask: does this respect the calculation/presentation boundary? Is it testable in isolation?

## Architecture

### Data Pipeline (`students/DriveGUI/`)

```
Raw .xlsx (OBD-II)
  → calculations.py          # Cleans & derives metrics → writes calculations_log_*.xlsx
  → <metric>_chart.py (×13)  # Each reads the log and renders a Matplotlib chart
```

**`calculations.py`** is the processing core:
- Converts GPS Time to elapsed seconds
- Smooths speed with a rolling mean (window=4, center=True)
- Converts km/h → m/s, differentiates to get acceleration
- Splits acceleration into positive/negative columns
- Outputs one Excel sheet per session under `INPUT/log/`

**`driving_cycles_calculatorV1.py`** is the Tkinter GUI entry point. It orchestrates folder selection and calls `calculations.py`, then dynamically loads the 13 visualization modules.

**13 visualization modules** (one metric each): `average_speed`, `average_acceleration`, `average_deceleration`, `max_speed`, `stop_percentage`, `number_of_stops`, `total_stop_percentage`, `engine_load`, `fuel_consumption_chart`, `co2_chart`, `representative_route`, `speed_profile`, and one more. Each is ~110 lines and follows the same pattern: load the calculations log → compute the metric → render a grouped bar chart.

**`representative_route.py`** scores each session against the average across 7 metrics to nominate the most representative trip for driving-cycle research (similarity score = `100 − |session − avg| / |avg| × 100`).

### Data (`_data/`)

- `complete_extract/` — CSVs organised by driver name (ladikas, kalyvas, stefanakis, galatas, …)
- `load_file.py` — CSV parsing helpers
- Primary dataset is on Google Drive (see `DATA.md` for link); local files are a subset

**Known data-quality issues**:
- Galatas file: repeated header rows (potential corruption)
- Stefanakis dataset: inconsistent column names across files
- Kalyvas/9.9.24: different format than other sessions
- Separator (``,``, `;``, ``\t``) and decimal separator (``,`` vs ``.``) vary across files

### Required OBD-II columns (input XLSX)

`GPS Time`, `Speed (OBD)(km/h)`, `CO₂ in g/km (Average)(g/km)`, `Engine Load(%)`, `Fuel flow rate/hour(l/hr)`

## Key Documentation

- `students/DriveGUI/ARCHITECTURE.md` — module-by-module documentation
- `students/DriveGUI/PROCESSING_LOGIC.md` — mathematical formulas and filtering details
- `docs/data_schema/data_schema.md` — Entity-Relationship Diagram for the full system
- `DATA.md` — data collection notes and Google Drive link

## Language Note

Variable names, UI labels, and Excel column headers frequently use **Greek** (e.g., `Διάρκεια (sec)`, `Ταχ m/s`). This is intentional — do not rename them without checking all downstream references.

## Skill routing

When the user's request matches an available skill, ALWAYS invoke it using the Skill
tool as your FIRST action. Do NOT answer directly, do NOT use other tools first.
The skill has specialized workflows that produce better results than ad-hoc answers.

Key routing rules:
- Product ideas, "is this worth building", brainstorming → invoke office-hours
- Bugs, errors, "why is this broken", 500 errors → invoke investigate
- Ship, deploy, push, create PR → invoke ship
- QA, test the site, find bugs → invoke qa
- Code review, check my diff → invoke review
- Update docs after shipping → invoke document-release
- Weekly retro → invoke retro
- Design system, brand → invoke design-consultation
- Visual audit, design polish → invoke design-review
- Architecture review → invoke plan-eng-review
- Save progress, checkpoint, resume → invoke checkpoint
- Code quality, health check → invoke health
