"""Exact new public operations; legacy inventory assertions remain explicit."""

AI_WORKFLOW_OPERATIONS = {
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
