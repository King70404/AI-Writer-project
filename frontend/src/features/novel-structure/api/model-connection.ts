import { postJson } from "../../../api/client";
import { securitySession } from "../../../api/security-session";

export interface ConnectionResult {
  readonly status: string;
  readonly configuration_version: string;
  readonly model_available: boolean;
}

export const modelConnectionClient = {
  async check(
    id: string,
    confirmation?: {
      readonly confirm_test_message: true;
      readonly configuration_version: string;
      readonly project_id: string;
    },
  ): Promise<ConnectionResult> {
    if (!/^[A-Za-z0-9_-]{1,80}$/u.test(id)) throw new Error("模型标识无效");
    const session = await securitySession.getValidSession();
    const response = await postJson(
      `ai/models/${id}/connection-check`,
      confirmation ?? {},
      (value) => {
        if (
          typeof value !== "object" ||
          value === null ||
          !("status" in value) ||
          typeof value.status !== "string" ||
          !("configuration_version" in value) ||
          typeof value.configuration_version !== "string" ||
          !("model_available" in value) ||
          typeof value.model_available !== "boolean"
        )
          throw new Error("连接检查结果无法读取");
        return value as ConnectionResult;
      },
      { headers: { "X-CSRF-Token": session.csrfToken } },
    );
    return response.data;
  },
};
