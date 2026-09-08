# AIWebNovel refactor roadmap

This document is the repository copy of the approved RF execution order. `PLAN.md` tracks current status; this file tracks the long-term order.

## Ordered tasks

1. RF-00 — lock the single verified GitHub baseline.
2. RF-01 — freeze the new product specification and module contracts.
3. RF-02 — refactor test contracts and global inventories.
4. RF-03 — add scenes and plot progression points.
5. RF-04 — add structured Story Assets.
6. RF-05 — add a versioned Skills library.
7. RF-06 — add a secure Model Gateway and API Key settings while preserving local models.
8. RF-07 — rebuild explainable ContextPack assembly.
9. RF-08 — persist single-step AI writing runs and candidates.
10. RF-09 — implement author-safe, idempotent candidate adoption.
11. RF-10 — add resumable 200–300-character continuous generation.
12. RF-11 — add Story Memory and fact confirmation.
13. RF-12 — add consistency review and targeted rewrite candidates.
14. RF-13 — add cross-chapter recall and invalidation propagation.
15. RF-14 — consolidate the author workspace.
16. RF-15 — finish upgrade, backup and restore safety.
17. RF-16 — perform writing-quality, cost and long-form evaluation.
18. RF-17 — perform formal release acceptance.

## Execution rule

Only one numbered RF task may be active for implementation at a time. Do not implement RF-03 through RF-17 as one repository-wide change. Every code task owns its applicable implementation, tests, errors and documentation, followed by a candidate-bound validation round.

The current detailed status and blocker are maintained in root `PLAN.md` and the active GitHub Issues.
