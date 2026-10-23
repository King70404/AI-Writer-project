"""Exact new public operations; legacy inventory assertions remain explicit."""

AI_WORKFLOW_OPERATIONS = {
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
    ("GET", "/api/v1/projects/{project_id}/workspace"),
    ("GET", "/api/v1/projects/{project_id}/workspace/chapters"),
    ("GET", "/api/v1/projects/{project_id}/workspace/actions"),
    ("GET", "/api/v1/chapters/{chapter_id}/editorial-state"),
    ("PUT", "/api/v1/chapters/{chapter_id}/editorial-state"),
}

USAGE_OPERATIONS = {
    ("GET", "/api/v1/projects/{project_id}/usage"),
}
