export interface StoryBibleResponse {
  readonly story_bible_id: string;
  readonly project_id: string;
  readonly current_revision_id: string;
  readonly revision_number: number;
  readonly concurrency_version: number;
  readonly title: string;
  readonly content: string;
  readonly created_at: string;
  readonly updated_at: string;
  readonly revision_created_at: string;
  readonly head_updated_at: string;
}

export interface CreateStoryBibleRequest {
  readonly title: string;
  readonly content: string;
}

export interface ReviseStoryBibleRequest {
  readonly title: string;
  readonly content: string;
}

export interface VersionedStoryBibleResource {
  readonly storyBible: StoryBibleResponse;
  readonly etag: string;
  readonly version: number;
}

export interface StoryBibleRevisionHistoryItemResponse {
  readonly revision_id: string;
  readonly revision_number: number;
  readonly title: string;
  readonly created_at: string;
  readonly is_current: boolean;
}

export interface StoryBibleRevisionHistoryPageResponse {
  readonly story_bible_id: string;
  readonly project_id: string;
  readonly current_revision_number: number;
  readonly items: readonly StoryBibleRevisionHistoryItemResponse[];
  readonly next_cursor: string | null;
  readonly has_more: boolean;
}

export interface StoryBibleRevisionResponse {
  readonly story_bible_id: string;
  readonly project_id: string;
  readonly revision_id: string;
  readonly revision_number: number;
  readonly title: string;
  readonly content: string;
  readonly created_at: string;
  readonly is_current: boolean;
  readonly current_revision_number: number;
}
