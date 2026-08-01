export interface CreateCharacterRequest {
  readonly name: string;
  readonly role: string;
  readonly profile: string;
}

export interface ReviseCharacterRequest {
  readonly name: string;
  readonly role: string;
  readonly profile: string;
}

export interface CharacterResponse {
  readonly character_id: string;
  readonly project_id: string;
  readonly current_revision_id: string;
  readonly revision_number: number;
  readonly concurrency_version: number;
  readonly name: string;
  readonly role: string;
  readonly profile: string;
  readonly created_at: string;
  readonly updated_at: string;
  readonly revision_created_at: string;
  readonly head_updated_at: string;
}

export interface CharacterListItemResponse {
  readonly character_id: string;
  readonly current_revision_id: string;
  readonly revision_number: number;
  readonly concurrency_version: number;
  readonly name: string;
  readonly role: string;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface CharacterListPageResponse {
  readonly project_id: string;
  readonly items: readonly CharacterListItemResponse[];
  readonly next_cursor: string | null;
  readonly has_more: boolean;
}

export interface VersionedCharacterResource {
  readonly character: CharacterResponse;
  readonly etag: string;
  readonly version: number;
}
