export interface ProjectResponse {
  readonly project_id: string;
  readonly current_revision_id: string;
  readonly revision_number: number;
  readonly concurrency_version: number;
  readonly title: string;
  readonly description: string;
  readonly created_at: string;
  readonly updated_at: string;
  readonly revision_created_at: string;
  readonly head_updated_at: string;
}

export interface ProjectListItemResponse {
  readonly project_id: string;
  readonly current_revision_id: string;
  readonly revision_number: number;
  readonly concurrency_version: number;
  readonly title: string;
  readonly created_at: string;
  readonly updated_at: string;
  readonly revision_created_at: string;
}

export interface ProjectListResponse {
  readonly items: readonly ProjectListItemResponse[];
  readonly next_cursor: string | null;
  readonly has_more: boolean;
}

export interface CreateProjectRequest {
  readonly title: string;
  readonly description: string;
}

export interface ReviseProjectRequest {
  readonly title: string;
  readonly description: string;
}

export interface VersionedProjectResource {
  readonly project: ProjectResponse;
  readonly etag: string;
  readonly version: number;
}

export interface SecuritySessionResponse {
  readonly csrf_token: string;
  readonly expires_in_seconds: number;
}

export interface BackendProjectErrorEnvelope {
  readonly error: {
    readonly code: string;
    readonly message: string;
    readonly details: Readonly<Record<string, unknown>>;
    readonly retryable: boolean;
    readonly suggested_action: string | null;
  };
  readonly request_id: string;
}
