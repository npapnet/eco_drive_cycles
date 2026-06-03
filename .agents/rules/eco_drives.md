---
trigger: always_on
---

# Project Rules: Eco Drive Cycles

## 1. Project Organization & Scope

- **`src/drive_cycle_calculator/`** — active calculation layer. All new business logic goes here. Use English variable and column names (`elapsed_s`, `smooth_speed_kmh`, `acc_ms2`, etc.).
- **`students/DriveGUI/`** — ⚠️ FROZEN historical reference. Do not add features, package imports, or modify functionality. Must run standalone forever.
- **`examples/`** — thin wrappers and scratchpads over the package. No core calculation logic here.
- **`data/`**, **`_data/`**, **`raw_data/`** — data folders (Parquet, DuckDB, CSV, XLSX). Do not read or process unless explicitly directed.
- **`brainstorming/`** — sandbox for ideas not yet promoted to `notes/designs/`. Do not use as reference unless explicitly directed.
- **`notes/designs/`** — point-in-time design documents. May be stale after each iteration; `architecture.md` is the authoritative current state.

## 2. Tech Stack & Tooling

- **Python**: `>= 3.12`
- **Dependency management**: `uv` workspaces (`uv sync`)
- **Testing**: `uv run pytest` — always run tests to verify changes
- **Linting**: `ruff` as configured in `pyproject.toml` (100-char line length, Py312 target)

## 3. Skills & Workflows

Check `.agents/skills/` and `.agents/workflows/` before answering ad-hoc. Existing patterns take precedence.

| Trigger | File |
|---|---|
| Sprint wrap-up, finish sprint, delete or distill | `.agents/workflows/distill_architecture.md` |
| Sync architecture doc to current src state | `.agents/workflows/sync_architecture.md` |
| Learn a user preference | `.agents/skills/knowledge-learner/SKILL.md` |

## 4. Architectural Rules

- Calculation vs. presentation separation must be strictly maintained.
- **`OBDFile`** is the entry point for raw data: `from_xlsx`, `from_csv`, `from_parquet`.
- **`Trip`** handles single-trip metrics. **`TripCollection`** manages multiple trips (`from_folder`, `from_archive_parquets`).
- **`TripCollection.to_duckdb_catalog`** is removed — DuckDB is produced by `dcc extract`, not by library code.
- Parquet filenames use `obd.parquet_name` (canonical). `obd.name` (raw filename stem) is never used for Parquet paths or DuckDB keys.
- `speed_ms`, `acceleration_ms2`, `deceleration_ms2` no longer exist in processed output. Do not produce these columns.

See `architecture.md` at the repo root for the full current system state.

## 5. Task & Context Management (3-Tier System)

| File | Role |
|---|---|
| `TODOS.md` | Live working memory — only `## Immediate Next Steps` and `## Backlog (Unscheduled)`. Never store completed tasks here. |
| `CHANGELOG.md` | High-level version release notes |
| `architecture.md` | Current condensed system state |

**Delete or Distill rule** — when a task is complete:
1. Delete it from `TODOS.md`.
2. If it was a new feature, append a brief summary to `CHANGELOG.md`.
3. If it changed system architecture, update `architecture.md`. Update `notes/designs/` only if a specific point-in-time design doc exists for that area.