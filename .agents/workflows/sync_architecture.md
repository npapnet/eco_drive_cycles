---
description: Synchronizes architecture.md to reflect the current state of src/drive_cycle_calculator/. Run after structural code changes to keep the architecture doc accurate.
trigger: manual, "sync architecture", "update architecture"
---

# Workflow: Sync Architecture

1. Read all source files in `src/drive_cycle_calculator/`.

2. Compare the current implementation against `architecture.md`:
   - Key classes and their public API (constructors, methods, properties)
   - Pydantic models and their fields
   - Pipeline stages and data flow
   - Processed DataFrame column names
   - CLI subcommands and their behaviour

3. Update `architecture.md` to match the current source. Reflect only what is currently implemented — no planned or speculative content.

4. Ask the user to review the changes before saving.
