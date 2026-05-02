# CLAUDE.md

This file provides guidance to Claude Code when working in this repository.

@architecture.md

---

## Context Boundaries

Do not read `brainstorming/` unless explicitly directed by the user (e.g., via `@` reference or direct instruction).

## Constraints

⚠️ **`students/DriveGUI/` is FROZEN** — do not add package imports, new features, or
modify anything here unless explicitly asked. Must run standalone forever regardless of
package API changes.

**Placement:** Does a change belong in `src/drive_cycle_calculator/` (calculation) or
`examples/` (thin wrapper)? Never add business logic to `students/DriveGUI/`.

---

## Task Tracking (3-Tier)

| File | Role |
|---|---|
| `TODOS.md` | Live working memory — only `## Immediate Next Steps` and `## Backlog (Unscheduled)` headings |
| `CHANGELOG.md` | High-level version release notes |
| `architecture.md` | Current condensed system state |

**On completing work:** delete chores/bugs from `TODOS.md`; append features to
`CHANGELOG.md`; update `architecture.md` for any structural or API changes.

---

## Skill Routing

When the user's request matches a skill, invoke it FIRST before any other action.

| Trigger | Skill / Workflow |
|---|---|
| Sprint wrap-up, distill architecture | `distill_architecture` (`.agents/workflows/`) |
| Sync architecture doc to current src | `sync_architecture` (`.agents/workflows/`) |
| Learn a preference | `knowledge-learner` (`.agents/skills/`) |
| Product ideas, brainstorming | `office-hours` |
| Bugs, errors, broken behaviour | `investigate` |
| Ship, deploy, create PR | `ship` |
| Code review | `review` |

---

## Running the Code

```bash
uv run pytest                              # full test suite
uv run dcc config-init <raw_dir>           # generate metadata template
uv run dcc ingest <raw_dir> <out_dir>      # raw → archive Parquet (no DuckDB)
uv run dcc extract <data_dir>              # Parquets → DuckDB / CSV / XLSX
uv run dcc analyze <data_dir>              # similarity scores, representative trip
uv run dcc gui                             # launch GUI
```

Stack: Python >= 3.12, `uv` workspaces, `pytest`, `ruff`. Run `uv sync` to install.
