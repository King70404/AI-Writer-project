import {
  API_BASE_URL,
  getJson,
  joinApiPath,
  postJson,
} from "../../../api/client";
import { ApiError } from "../../../api/errors";
import { securitySession } from "../../../api/security-session";

export interface BackupCounts {
  readonly projects: number;
  readonly chapters: number;
  readonly chapter_revisions: number;
  readonly confirmed_facts: number;
  readonly workflow_runs: number;
}

export interface BackupSummary {
  readonly schema_revision: string;
  readonly requires_upgrade: boolean;
  readonly counts: BackupCounts;
}

export interface BackupItem {
  readonly backup_id: string;
  readonly file_bytes: number;
  readonly readable: boolean;
  readonly created_at: string | null;
  readonly summary: BackupSummary | null;
}

export interface BackupVerification {
  readonly backup_id: string;
  readonly status: "valid" | "corrupt" | "incompatible";
  readonly problem: string | null;
  readonly summary: BackupSummary | null;
}

export interface BackupRestore {
  readonly backup_id: string;
  readonly target_name: string;
  readonly summary: BackupSummary;
}

export class BackupError extends Error {
  readonly code: string;

  constructor(message: string, code: string) {
    super(message);
    this.name = "BackupError";
    this.code = code;
  }
}

const BACKUP_ID = /^\d{8}T\d{6}Z-[0-9a-f]{12}$/;
const COUNT_KEYS = [
  "projects",
  "chapters",
  "chapter_revisions",
  "confirmed_facts",
  "workflow_runs",
] as const;

const MESSAGES: Readonly<Record<string, string>> = {
  BACKUP_BUSY: "另一个备份任务正在进行，请稍候再试。",
  BACKUP_NOT_FOUND: "找不到这个备份，请刷新列表。",
  BACKUP_UNAVAILABLE: "当前数据暂时无法备份，请确认应用已正常就绪。",
  BACKUP_CORRUPT: "备份未通过完整性校验，不能用于恢复。",
  BACKUP_INCOMPATIBLE: "这个备份来自不兼容的版本，不能在当前版本恢复。",
  RESTORE_TARGET_INVALID:
    "请填写新的文件夹名称：只用文字、数字、点、短横线或下划线，不能以点或短横线开头或结尾。",
  RESTORE_TARGET_NOT_EMPTY:
    "该文件夹已存在且不是空文件夹。为保护已有内容，请换一个新名称。",
  RESTORE_CONFIRMATION_REQUIRED: "请先确认恢复为独立的新副本。",
  BACKUP_FAILED: "操作未完成，当前创作数据没有改变。请稍后重试。",
};

function invalid(): never {
  throw new BackupError("服务返回了无法读取的备份数据。", "INVALID_RESPONSE");
}

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function count(value: unknown): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0)
    invalid();
  return value;
}

function parseSummary(value: unknown): BackupSummary {
  if (
    !record(value) ||
    typeof value.schema_revision !== "string" ||
    typeof value.requires_upgrade !== "boolean" ||
    !record(value.counts)
  )
    invalid();
  const counts = value.counts;
  const parsed = Object.fromEntries(
    COUNT_KEYS.map((key) => [key, count(counts[key])]),
  ) as unknown as BackupCounts;
  return {
    schema_revision: value.schema_revision,
    requires_upgrade: value.requires_upgrade,
    counts: parsed,
  };
}

function backupId(value: unknown): string {
  if (typeof value !== "string" || !BACKUP_ID.test(value)) invalid();
  return value;
}

export function parseBackupItem(value: unknown): BackupItem {
  if (
    !record(value) ||
    typeof value.readable !== "boolean" ||
    (value.created_at !== null && typeof value.created_at !== "string")
  )
    invalid();
  return {
    backup_id: backupId(value.backup_id),
    file_bytes: count(value.file_bytes),
    readable: value.readable,
    created_at: value.created_at,
    summary: value.summary === null ? null : parseSummary(value.summary),
  };
}

function parseList(value: unknown): readonly BackupItem[] {
  if (!record(value) || !Array.isArray(value.items)) invalid();
  return value.items.map(parseBackupItem);
}

function parseVerification(value: unknown): BackupVerification {
  if (
    !record(value) ||
    !["valid", "corrupt", "incompatible"].includes(String(value.status)) ||
    (value.problem !== null && typeof value.problem !== "string")
  )
    invalid();
  return {
    backup_id: backupId(value.backup_id),
    status: value.status as BackupVerification["status"],
    problem: value.problem,
    summary: value.summary === null ? null : parseSummary(value.summary),
  };
}

function parseRestore(value: unknown): BackupRestore {
  if (!record(value) || typeof value.target_name !== "string") invalid();
  return {
    backup_id: backupId(value.backup_id),
    target_name: value.target_name,
    summary: parseSummary(value.summary),
  };
}

function translate(error: unknown): never {
  if (error instanceof BackupError) throw error;
  if (error instanceof ApiError) {
    if (error.status === 401 || error.status === 403) {
      securitySession.clear();
      throw new BackupError(
        "本地安全会话已失效，请刷新页面后重试。",
        error.code,
      );
    }
    if (error.code === "INVALID_RESPONSE") invalid();
    throw new BackupError(
      MESSAGES[error.code] ?? MESSAGES.BACKUP_FAILED,
      error.code,
    );
  }
  throw new BackupError(
    "无法连接本地服务，当前创作数据没有改变。",
    "NETWORK_ERROR",
  );
}

async function write<T>(
  path: string,
  body: unknown,
  decode: (value: unknown) => T,
): Promise<T> {
  try {
    const proof = await securitySession.getValidSession();
    const response = await postJson(path, body, decode, {
      headers: { "X-CSRF-Token": proof.csrfToken },
    });
    return response.data;
  } catch (error) {
    return translate(error);
  }
}

function checkedId(id: string): string {
  if (!BACKUP_ID.test(id))
    throw new BackupError("备份编号无效。", "INVALID_ID");
  return id;
}

export const backupClient = {
  async list(): Promise<readonly BackupItem[]> {
    try {
      return (await getJson("backups", parseList)).data;
    } catch (error) {
      return translate(error);
    }
  },
  create: (): Promise<BackupItem> => write("backups", {}, parseBackupItem),
  verify: async (id: string): Promise<BackupVerification> =>
    write(`backups/${checkedId(id)}/verify`, {}, parseVerification),
  restore: async (id: string, targetName: string): Promise<BackupRestore> =>
    write(
      `backups/${checkedId(id)}/restore`,
      { target_name: targetName, confirm_new_copy: true },
      parseRestore,
    ),
  downloadUrl: (id: string): string =>
    joinApiPath(API_BASE_URL, `backups/${checkedId(id)}/download`),
};

const TARGET_NAME = /^[\p{L}\p{N}_](?:[\p{L}\p{N}_.-]{0,62}[\p{L}\p{N}_])?$/u;
const RESERVED = /^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])$/i;

export function isPlainFolderName(name: string): boolean {
  return (
    name.normalize("NFC") === name &&
    TARGET_NAME.test(name) &&
    !RESERVED.test(name.split(".", 1)[0])
  );
}

export function backupErrorMessage(error: unknown): string {
  return error instanceof BackupError ? error.message : MESSAGES.BACKUP_FAILED;
}
