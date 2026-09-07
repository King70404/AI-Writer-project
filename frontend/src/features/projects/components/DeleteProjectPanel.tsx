import { useState } from "react";
import { useNavigate } from "react-router";

import type {
  ProjectDeleteApiClient,
  ProjectDetailApiClient,
} from "../api/client";
import type { VersionedProjectResource } from "../api/contracts";
import { ProjectApiError } from "../api/errors";

export function DeleteProjectPanel({
  resource,
  client,
}: {
  readonly resource: VersionedProjectResource;
  readonly client: ProjectDeleteApiClient & ProjectDetailApiClient;
}) {
  const navigate = useNavigate();
  const [confirmation, setConfirmation] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const title = resource.project.title;
  const confirmed = confirmation === title;

  const deleteProject = async (): Promise<void> => {
    if (!confirmed || deleting) return;
    setDeleting(true);
    setError(null);
    try {
      await client.deleteProject({
        projectId: resource.project.project_id,
        etag: resource.etag,
      });
      await navigate("/projects", { replace: true });
    } catch (reason) {
      setError(
        reason instanceof ProjectApiError
          ? reason.message
          : "删除小说未能完成，请重新加载后再试。",
      );
      setDeleting(false);
    }
  };

  return (
    <section className="project-delete" aria-labelledby="project-delete-title">
      <p className="section-kicker">项目设置</p>
      <h3 id="project-delete-title">删除小说</h3>
      <p>
        删除后，这本小说会从正常项目列表和创作入口中移除。为保护历史数据，
        已有不可变版本记录不会被强行破坏。
      </p>
      <p>
        如确定删除，请输入完整书名：<strong>{title}</strong>
      </p>
      <label htmlFor="project-delete-confirmation">确认书名</label>
      <input
        id="project-delete-confirmation"
        name="delete-confirmation"
        type="text"
        autoComplete="off"
        value={confirmation}
        onChange={(event) => setConfirmation(event.target.value)}
        disabled={deleting}
      />
      <button
        type="button"
        disabled={!confirmed || deleting}
        onClick={() => void deleteProject()}
      >
        {deleting ? "正在删除…" : "删除小说"}
      </button>
      {error === null ? null : <p role="alert">{error}</p>}
    </section>
  );
}
