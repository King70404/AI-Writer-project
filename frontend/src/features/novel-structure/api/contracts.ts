export interface OutlineResponse {
  readonly outline_id: string;
  readonly project_id: string;
  readonly current_revision_id: string;
  readonly revision_number: number;
  readonly concurrency_version: number;
  readonly title: string;
  readonly summary: string;
  readonly created_at: string;
  readonly updated_at: string;
  readonly revision_created_at: string;
}

export interface VolumeResponse {
  readonly volume_id: string;
  readonly project_id: string;
  readonly current_revision_id: string;
  readonly revision_number: number;
  readonly concurrency_version: number;
  readonly title: string;
  readonly summary: string;
  readonly position: number;
  readonly created_at: string;
  readonly updated_at: string;
  readonly revision_created_at: string;
}

export interface ChapterResponse {
  readonly chapter_id: string;
  readonly project_id: string;
  readonly volume_id: string;
  readonly current_revision_id: string;
  readonly revision_number: number;
  readonly concurrency_version: number;
  readonly title: string;
  readonly summary: string;
  readonly position: number;
  readonly created_at: string;
  readonly updated_at: string;
  readonly revision_created_at: string;
}

export interface StructureTextInput {
  readonly title: string;
  readonly summary: string;
}

export interface PositionedStructureInput extends StructureTextInput {
  readonly position: number;
}

export interface VersionedResource<T> {
  readonly resource: T;
  readonly etag: string;
  readonly version: number;
}

export type VersionedOutline = VersionedResource<OutlineResponse>;
export type VersionedVolume = VersionedResource<VolumeResponse>;
export type VersionedChapter = VersionedResource<ChapterResponse>;
