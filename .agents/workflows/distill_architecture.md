---
description: Automates the "Delete or Distill" rule to clear task buffers and update core system state.
---

---
trigger: manual, "run sprint wrapup", "finish sprint"
---
Step 1: Audit Active Tasks
Read the todos.md file and identify any tasks that have been completed during the current session or sprint. You must cross-reference the git commit history to verify exactly what was successfully built and merged before proceeding.

Step 2: The "Delete or Distill" Execution
For every completed task identified, apply the following logic strictly:

- Bug Fixes & Chores: Delete the task from todos.md entirely. Git maintains the granular history.

- Features: Append a high-level summary to changelog.md under the current unreleased version.

- Architecture / State Changes: If the completed task changed how the system operates (e.g., new schemas, routing logic, package dependencies, or Pydantic models), update the root architecture.md file to reflect this new reality. If a specific point-in-time design document exists in docs/designs/, update that as well.

Step 3: Archive (Optional)
If the project maintains a `todos_archive.md` file, cut the identified completed tasks from todos.md and append them to the bottom of the archive file under a heading for today's date. If no such file exists, skip this step.

Step 4: Purge & Reset todos.md
Erase all completed, strikethrough (~~), or finished items from todos.md.

Ensure todos.md strictly retains only two active headings:

- ## Immediate Next Steps
- ## Backlog (Unscheduled)

Save the file. The working memory must be left lean and optimized for the next sprint..