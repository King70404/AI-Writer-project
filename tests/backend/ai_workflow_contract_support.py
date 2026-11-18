"""Exact new public operations; legacy inventory assertions remain explicit."""

AI_WORKFLOW_OPERATIONS = {
    ("POST", "/api/v1/ai/models/{profile_id}/connection-check"),
    ("POST", "/api/v1/ai/workflow-setup/upgrade"),
    ("GET", "/api/v1/ai/models"),
    ("POST", "/api/v1/ai/models"),
    ("PUT", "/api/v1/ai/models/{profile_id}"),
    ("DELETE", "/api/v1/ai/models/{profile_id}"),
    ("GET", "/api/v1/chapters/{chapter_id}/ai/runs"),
    ("POST", "/api/v1/chapters/{chapter_id}/ai/runs"),
    ("GET", "/api/v1/chapters/{chapter_id}/ai/runs/{run_id}"),
    ("POST", "/api/v1/chapters/{chapter_id}/ai/runs/{run_id}/generate"),
    ("POST", "/api/v1/chapters/{chapter_id}/ai/runs/{run_id}/pause"),
    ("POST", "/api/v1/chapters/{chapter_id}/ai/runs/{run_id}/resume"),
    ("POST", "/api/v1/chapters/{chapter_id}/ai/candidates/{candidate_id}/adopt"),
    ("POST", "/api/v1/chapters/{chapter_id}/ai/candidates/{candidate_id}/discard"),
}

WRITING_PREPARATION_OPERATIONS = {
    ("GET", "/api/v1/projects/{project_id}/writing/references/{reference_id}/estimate"),
    ("POST", "/api/v1/projects/{project_id}/writing/method-trials"),
    ("GET", "/api/v1/projects/{project_id}/writing/method-trials"),
    ("GET", "/api/v1/projects/{project_id}/writing/method-trials/{trial_id}"),
    ("GET", "/api/v1/projects/{project_id}/writing/method-trials/{trial_id}/estimate/{slot}"),
    ("POST", "/api/v1/projects/{project_id}/writing/method-trials/{trial_id}/send"),
    ("POST", "/api/v1/projects/{project_id}/writing/method-trials/{trial_id}/rate"),
    ("POST", "/api/v1/projects/{project_id}/writing/method-annotations"),
    ("GET", "/api/v1/projects/{project_id}/writing/method-annotations/{chapter_id}"),
    ("POST", "/api/v1/projects/{project_id}/writing/method-templates"),
    ("GET", "/api/v1/projects/{project_id}/writing/method-templates"),
    ("DELETE", "/api/v1/projects/{project_id}/writing/method-templates/{template_id}"),
    ("POST", "/api/v1/projects/{project_id}/writing/method-templates/{template_id}/copy"),
    ("GET", "/api/v1/projects/{project_id}/writing/references"),
    ("POST", "/api/v1/projects/{project_id}/writing/references"),
    ("GET", "/api/v1/projects/{project_id}/writing/references/{reference_id}"),
    ("POST", "/api/v1/projects/{project_id}/writing/references/{reference_id}/analyze"),
    ("GET", "/api/v1/projects/{project_id}/writing/rules"),
    ("POST", "/api/v1/projects/{project_id}/writing/rules"),
    ("POST", "/api/v1/projects/{project_id}/writing/rules/{rule_id}/versions"),
    ("GET", "/api/v1/chapters/{chapter_id}/planning"),
    ("PUT", "/api/v1/chapters/{chapter_id}/planning"),
}

STORY_MEMORY_OPERATIONS = {
    ("GET", "/api/v1/chapters/{chapter_id}/memory/reviews/{review_id}/estimate"),
    ("GET", "/api/v1/chapters/{chapter_id}/memory"),
    ("POST", "/api/v1/chapters/{chapter_id}/memory/facts"),
    ("PUT", "/api/v1/chapters/{chapter_id}/memory/facts/{fact_id}"),
    ("POST", "/api/v1/chapters/{chapter_id}/memory/reviews"),
    ("POST", "/api/v1/chapters/{chapter_id}/memory/reviews/{review_id}/send"),
}

BACKUP_OPERATIONS = {
    ("GET", "/api/v1/backups"),
    ("POST", "/api/v1/backups"),
    ("POST", "/api/v1/backups/{backup_id}/verify"),
    ("GET", "/api/v1/backups/{backup_id}/download"),
    ("POST", "/api/v1/backups/{backup_id}/restore"),
}

WORKBENCH_OPERATIONS = {
    ("GET", "/api/v1/workspace/overview"),
    ("GET", "/api/v1/projects/{project_id}/workspace"),
    ("GET", "/api/v1/projects/{project_id}/workspace/chapters"),
    ("GET", "/api/v1/projects/{project_id}/workspace/actions"),
    ("GET", "/api/v1/chapters/{chapter_id}/editorial-state"),
    ("PUT", "/api/v1/chapters/{chapter_id}/editorial-state"),
}

USAGE_OPERATIONS = {
    ("GET", "/api/v1/projects/{project_id}/usage"),
}

CANDIDATE_BUDGET_OPERATIONS = {
    ("POST", "/api/v1/chapters/{chapter_id}/ai/candidates/{candidate_id}/edits"),
    ("GET", "/api/v1/chapters/{chapter_id}/ai/candidates/{candidate_id}/edits"),
    ("GET", "/api/v1/chapters/{chapter_id}/ai/runs/{run_id}/estimate"),
    ("GET", "/api/v1/ai/models/{profile_id}/price"),
    ("PUT", "/api/v1/ai/models/{profile_id}/price"),
    ("GET", "/api/v1/projects/{project_id}/budget"),
    ("PUT", "/api/v1/projects/{project_id}/budget"),
    ("GET", "/api/v1/storage-instance"),
}

STORY_CONTROL_OPERATIONS = {
    ("GET", "/api/v1/projects/{project_id}/arc-plans"),
    ("POST", "/api/v1/projects/{project_id}/arc-plans"),
    ("PUT", "/api/v1/projects/{project_id}/arc-plans/{goal_id}"),
    ("GET", "/api/v1/projects/{project_id}/timeline"),
    ("POST", "/api/v1/projects/{project_id}/plot-threads"),
    ("PUT", "/api/v1/projects/{project_id}/plot-threads/{thread_id}"),
    ("POST", "/api/v1/projects/{project_id}/story-events"),
    ("PUT", "/api/v1/projects/{project_id}/story-events/{event_id}"),
    ("POST", "/api/v1/projects/{project_id}/state-intervals"),
    ("PUT", "/api/v1/projects/{project_id}/state-intervals/{state_id}"),
    ("GET", "/api/v1/projects/{project_id}/facts/search"),
    ("GET", "/api/v1/chapters/{chapter_id}/story-guide"),
    ("GET", "/api/v1/chapters/{chapter_id}/recall-policy"),
    ("PUT", "/api/v1/chapters/{chapter_id}/recall-policy"),
    ("POST", "/api/v1/chapters/{chapter_id}/recall-preview"),
    ("GET", "/api/v1/projects/{project_id}/plan-proposals"),
    ("POST", "/api/v1/projects/{project_id}/plan-proposals"),
    ("GET", "/api/v1/projects/{project_id}/plan-proposals/{proposal_id}"),
    ("GET", "/api/v1/projects/{project_id}/plan-proposals/{proposal_id}/estimate"),
    ("POST", "/api/v1/projects/{project_id}/plan-proposals/{proposal_id}/send"),
    ("POST", "/api/v1/projects/{project_id}/plan-proposals/{proposal_id}/adopt"),
}

IMPORT_OPERATIONS = {
    ("POST", "/api/v1/imports/uploads"),
    ("PUT", "/api/v1/imports/uploads/{upload_id}/chunks"),
    ("POST", "/api/v1/imports/uploads/{upload_id}/finish"),
    ("GET", "/api/v1/imports/{preview_id}/preview"),
    ("PUT", "/api/v1/imports/{preview_id}/preview"),
    ("POST", "/api/v1/imports/{preview_id}/commit"),
    ("GET", "/api/v1/imports/{preview_id}/receipt"),
}


HANDOFF_OPERATIONS = {
    ("POST", "/api/v1/chapters/{chapter_id}/handoffs/preview"),
    ("POST", "/api/v1/chapters/{chapter_id}/handoffs"),
    ("GET", "/api/v1/chapters/{chapter_id}/handoffs"),
    ("GET", "/api/v1/chapters/{chapter_id}/handoffs/{handoff_id}/download"),
    ("POST", "/api/v1/chapters/{chapter_id}/handoffs/{handoff_id}/candidates"),
    ("POST", "/api/v1/chapters/{chapter_id}/handoffs/{handoff_id}/candidates/{candidate_id}/adopt"),
}
WRITING_JOB_OPERATIONS = {
    ("POST", "/api/v1/projects/{project_id}/writing-jobs"),
    ("GET", "/api/v1/projects/{project_id}/writing-jobs"),
    ("GET", "/api/v1/writing-jobs/{job_id}"),
    ("POST", "/api/v1/writing-jobs/{job_id}/bind-run"),
    ("POST", "/api/v1/writing-jobs/{job_id}/scene-progress"),
    ("POST", "/api/v1/writing-jobs/{job_id}/{action}"),
}
