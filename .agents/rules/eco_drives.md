---
trigger: always_on
---

# Antigravity Rules for Eco Drive Cycles

These rules dictate how Antigravity (and other agents) should interact with this repository based on its structure and conventions.

## 1. Project Organization & Scope
- **`src/drive_cycle_calculator/`**: This is the active calculation layer package. All new business logic must go here. Use **English** variable and column names (e.g., `elapsed_s`, `speed_ms`, `smooth_speed_kmh`).
- **`students/DriveGUI/`**: This is a **FROZEN** historical reference application. Do NOT add new features, package imports, or modify its functionality. It relies on **Greek** column names (`Διάρκεια (sec)`, `Ταχ m/s`, etc.); do not change them.
- **`examples/`**: Contains thin CLI (`ingest.py`, `analyze.py`) and GUI (`main.py`) wrappers over `TripCollection`. Ensure no core calculation logic leaks into here.
- **`_data/`**: Contains raw exported driving-cycle files (CSV/XLSX). Be mindful of data-quality issues such as varying decimal separators, inconsistent headers, and corrupt files.
- **`docs/designs`**: contains the design intent (sometimes might not be up to date). 
- **`brainstorming`**: Contains folders and md files, which should not used by agents. This is a sandbox, and any worthy ideas will be promoted to `docs/designs`.

## 2. Tech Stack & Tooling
- **Python**: `>= 3.12`
- **Dependency Management**: Use `uv` workspaces (`uv sync`).
- **Testing**: Run tests via `uv run pytest`. Always maintain and run the test suite to verify changes.
- **Linting & Formatting**: Use `ruff` as configured in `pyproject.toml` (100 line length, Py312 target).

## 3. Skills and Workflows
- **Skills**: Task-specific instructions or code snippets are located in `.agents/skills/`.
- **Workflows**: Multi-step procedures are located in `.agents/workflows/`.
- When tasked with a process, always check `skills` and `workflows` first for existing patterns or utilities before answering ad-hoc.

## 4. Architectural Rules
- The separation of calculation and presentation must be strictly maintained.
- `TripCollection` is the primary entry point for managing multiple trips (`from_folder`, `to_parquet`, `to_duckdb_catalog`).
- `Trip` handles single trip metrics with lazy loading.