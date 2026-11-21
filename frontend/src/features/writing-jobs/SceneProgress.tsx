import {
  sceneSummary,
  type SceneAction,
  type SceneStatus,
  type StepSceneProgress,
} from "./client";

const SCENE_STATUS: Record<SceneStatus, string> = {
  pending: "待写",
  done: "已完成",
  skipped: "已跳过",
};

export function SceneProgress({
  progress,
  editable,
  busy,
  onMark,
}: {
  readonly progress: StepSceneProgress;
  readonly editable: boolean;
  readonly busy: boolean;
  readonly onMark: (action: SceneAction, sceneId?: string) => void;
}) {
  const next = progress.scenes.find(
    (scene) => scene.scene_id === progress.next_scene_id,
  );
  const locked = !editable || busy || progress.needs_recheck;
  return (
    <section className="writing-jobs__scenes" aria-label="当前章节场景进度">
      {progress.total === 0 && !progress.needs_recheck ? (
        <p>本章还没有保存场景规划；可在章节规划中按顺序添加场景。</p>
      ) : (
        <p>
          {sceneSummary(progress)}（完成 {progress.done_count} · 跳过{" "}
          {progress.skipped_count}）
          {progress.plan_version !== null
            ? ` · 规划第 ${progress.plan_version} 版`
            : ""}
        </p>
      )}
      {progress.needs_recheck ? (
        <div role="note">
          <p>
            {progress.current_plan_version === null
              ? "本章规划已不可用，以下进度按原规划显示。"
              : `本章规划已更新为第 ${progress.current_plan_version} 版，以下进度仍按原规划显示，不会自动对应到新场景。`}
          </p>
          {progress.current_plan_revision_id !== null ? (
            <button
              type="button"
              disabled={!editable || busy}
              onClick={() => onMark("recheck")}
            >
              按新规划重新核对
            </button>
          ) : null}
        </div>
      ) : null}
      {!progress.needs_recheck && progress.total > 0 ? (
        <p>
          {next
            ? `下一场景：${next.title || next.scene_id}${
                progress.target_scene_id === next.scene_id ? "（本步目标）" : ""
              }`
            : "规划中的场景都已标记。"}
        </p>
      ) : null}
      {progress.scenes.length > 0 ? (
        <ol>
          {progress.scenes.map((scene) => {
            const name = scene.title || scene.scene_id;
            return (
              <li key={scene.scene_id}>
                {name} · {SCENE_STATUS[scene.status]}
                {progress.target_scene_id === scene.scene_id
                  ? " · 本步目标"
                  : ""}
                {scene.status === "pending" ? (
                  <>
                    {" "}
                    <button
                      type="button"
                      aria-label={`设为本步目标：${name}`}
                      disabled={
                        locked || progress.target_scene_id === scene.scene_id
                      }
                      onClick={() => onMark("target", scene.scene_id)}
                    >
                      设为本步目标
                    </button>{" "}
                    <button
                      type="button"
                      aria-label={`标记完成：${name}`}
                      disabled={locked || !progress.has_adopted}
                      onClick={() => onMark("done", scene.scene_id)}
                    >
                      标记完成
                    </button>{" "}
                    <button
                      type="button"
                      aria-label={`标记跳过：${name}`}
                      disabled={locked}
                      onClick={() => onMark("skipped", scene.scene_id)}
                    >
                      标记跳过
                    </button>
                  </>
                ) : (
                  <>
                    {" "}
                    <button
                      type="button"
                      aria-label={`恢复待写：${name}`}
                      disabled={locked}
                      onClick={() => onMark("pending", scene.scene_id)}
                    >
                      恢复待写
                    </button>
                  </>
                )}
              </li>
            );
          })}
        </ol>
      ) : null}
      {!progress.has_adopted && progress.total > 0 ? (
        <p>采用本章候选后才能标记场景完成。</p>
      ) : null}
      <p>场景标记只由你决定；生成或采用候选不会自动改变场景进度。</p>
    </section>
  );
}
