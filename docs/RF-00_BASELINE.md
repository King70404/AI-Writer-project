# RF-00 baseline lock status

Status: BLOCKED — V1-UX-1 recovery required before refactor baseline can be locked.

## Current coordination main

As of 2026-09-08, `main` includes coordination-only continuity commits through:

`3c6ca7acc41465eb9c99f732d669855f6d3316f0`

The product-code baseline under V1-UX-1 remains the pre-UX baseline plus PR #9 candidate history. Re-read GitHub before any action; do not hard-code this coordination SHA into future task logic.

## Open UX candidate

PR #9: `V1-UX-1 Author Usability Polish`

Candidate that failed formal acceptance:

`5cb13a549d46d53c2bfc1d166d980ef750e5d112`

## Formal acceptance result

Issue #10 (`V1-UX-1-Q1`) failed during the one allowed `IncludeE2E` run.

First real blocker:

`tests/e2e/integrated/project-detail-edit.spec.ts`

The locator:

`getByRole("textbox", { name: "书名" })`

matched both the author edit field "书名" and delete confirmation field "确认书名", causing Playwright strict-mode violation in E2E-INT-009. This was not a timeout. The acceptance round stopped immediately and did not execute launcher or isolated author UX/delete smoke.

## Required next action

Create and complete a narrow Development recovery task for the locator ambiguity. The recovery must fix the test locator, not weaken product behavior, timeouts, retries, assertions, coverage, or browser safety checks.

After recovery creates a new PR #9 candidate SHA, create a new formal acceptance issue bound to that new SHA. Do not reuse the failed #10 round as if it had never failed.

RF-00 cannot close and RF-01 cannot start until the new candidate passes formal acceptance and PR #9 is merged or explicitly excluded by a recorded decision.
