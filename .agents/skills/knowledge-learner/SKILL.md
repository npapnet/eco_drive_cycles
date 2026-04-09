---
name: knowledge-learner
description: "Use this skill when the user explicitly says 'learn this' or triggers the /learn command to save a preference, style, or formatting rule."
---

# Goal
Persist a user-defined preference into the workspace configuration to ensure future consistency.

# Instructions
1. Extract the core preference or rule from the conversation.
2. Determine a concise filename (e.g., `latex-formatting.md`).
3. Call the `scripts/learn_preference.py` script with the 'rule_content' and 'filename'.
   1. Confirm to the user that the rule has been "memorialized" in their `.agents/rules/` directory.