import { useCallback, useEffect, useRef, useState } from "react";
import { AIWritingError, type AIOperation } from "../api/ai-writing";
import {
  aiWorkflowClient,
  type AIWorkflowClient,
  type ModelProfile,
  type WorkflowCandidate,
  type WorkflowRun,
} from "../api/ai-workflow";
import type { SelectionSnapshot } from "./useAIWriting";
import type { useChapterWriting } from "./useChapterWriting";

export function useAIWorkflow(
  chapterId: string,
  writing: ReturnType<typeof useChapterWriting>,
  client: AIWorkflowClient = aiWorkflowClient,
) {
  const [models, setModels] = useState<readonly ModelProfile[]>([]);
  const [runs, setRuns] = useState<readonly WorkflowRun[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [errorRunId, setErrorRunId] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [upgradeRequired, setUpgradeRequired] = useState(false);
  const [upgrading, setUpgrading] = useState(false);
  const [upgradeMessage, setUpgradeMessage] = useState("");
  const lock = useRef(false);
  const alive = useRef(false);
  const modelRevision = useRef(0);
  const keys = useRef(new Map<string, string>());
  const paused = useRef(false);
  const publish = useCallback((run: WorkflowRun) => {
    if (!alive.current) return;
    setRuns((current) => [
      run,
      ...current.filter((item) => item.run_id !== run.run_id),
    ]);
    setActiveId(run.run_id);
  }, []);
  const refresh = useCallback(async () => {
    const requestedModelRevision = modelRevision.current;
    const [nextModels, nextRuns] = await Promise.allSettled([
      client.models(),
      client.list(chapterId),
    ]);
    if (!alive.current) return;
    if (
      [nextModels, nextRuns].some(
        (result) =>
          result.status === "rejected" &&
          result.reason instanceof AIWritingError &&
          result.reason.code === "AI_WORKFLOW_SCHEMA_REQUIRED",
      )
    )
      setUpgradeRequired(true);
    if (
      nextModels.status === "fulfilled" &&
      requestedModelRevision === modelRevision.current
    )
      setModels(nextModels.value);
    if (nextRuns.status === "fulfilled") {
      setRuns(nextRuns.value);
      setActiveId((id) =>
        nextRuns.value.some((run) => run.run_id === id)
          ? id
          : (nextRuns.value[0]?.run_id ?? null),
      );
    }
    if (nextModels.status === "rejected") throw nextModels.reason;
    if (nextRuns.status === "rejected") throw nextRuns.reason;
    setUpgradeRequired(false);
  }, [chapterId, client]);
  useEffect(() => {
    alive.current = true;
    queueMicrotask(() => {
      if (!alive.current) return;
      void refresh()
        .catch((failure: unknown) => {
          if (alive.current)
            setError(
              failure instanceof AIWritingError
                ? failure.message
                : "协作任务读取失败，请点击刷新；手动写作仍可使用。",
            );
        })
        .finally(() => {
          if (alive.current) setLoading(false);
        });
    });
    return () => {
      alive.current = false;
    };
  }, [refresh]);
  const execute = async (
    action: () => Promise<void>,
    taskId: string | null = null,
  ) => {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setError("");
    setErrorRunId(null);
    try {
      await action();
    } catch (failure) {
      if (alive.current) {
        setErrorRunId(taskId);
        if (
          failure instanceof AIWritingError &&
          failure.code === "AI_WORKFLOW_SCHEMA_REQUIRED"
        )
          setUpgradeRequired(true);
        setError(
          failure instanceof Error
            ? failure.message
            : "操作失败，请刷新后重试。",
        );
      }
    } finally {
      lock.current = false;
      if (alive.current) setBusy(false);
    }
  };
  const active = runs.find((run) => run.run_id === activeId) ?? null;
  const requestGeneration = async (run: WorkflowRun) => {
    setGenerating(true);
    try {
      publish(await client.action(chapterId, run.run_id, "generate"));
    } catch (failure) {
      // A failed or lost response may have changed the persisted task. Only
      // read its result; another provider call requires a new author action.
      if (alive.current) {
        setErrorRunId(run.run_id);
        setError(
          failure instanceof Error
            ? failure.message
            : "生成失败，请刷新确认任务状态。",
        );
        setGenerating(false);
      }
      try {
        const latest = await client.list(chapterId);
        const updated = latest.find((item) => item.run_id === run.run_id);
        if (updated) publish(updated);
      } catch {
        // Preserve the generation failure if reading its status also fails.
      }
      throw failure;
    } finally {
      if (alive.current) setGenerating(false);
    }
  };
  const prepare = (
    operation: AIOperation,
    profileId: string,
    instruction: string,
    maxSteps: number,
    selection: SelectionSnapshot | null,
  ) =>
    execute(async () => {
      if (!profileId) throw new AIWritingError("请先添加或选择模型。");
      if (!(await writing.flush()))
        throw new AIWritingError("请先保存当前正文并处理版本冲突。");
      if (
        operation === "rewrite" &&
        (!selection?.text.trim() ||
          writing.getContent().slice(selection.start, selection.end) !==
            selection.text)
      )
        throw new AIWritingError("选区已经改变，请重新选择正文。");
      const steps = operation === "rewrite" ? 1 : maxSteps;
      const result = await client.create(chapterId, {
        operation,
        profile_id: profileId,
        instruction,
        selected_text: operation === "rewrite" ? selection!.text : "",
        selection_start: operation === "rewrite" ? selection!.start : null,
        selection_end: operation === "rewrite" ? selection!.end : null,
        max_steps: steps,
        max_output_characters: steps * 300,
      });
      paused.current = false;
      publish(result);
    });
  const generate = (run = active) =>
    execute(async () => {
      if (!run) return;
      if (writing.state.status !== "saved")
        throw new AIWritingError(
          "正文有未保存修改，请先保存，再为最新正文准备任务。",
        );
      paused.current = false;
      await requestGeneration(run);
    }, run?.run_id);
  const adopt = (candidate: WorkflowCandidate, continueAfter: boolean) =>
    execute(async () => {
      if (!active) return;
      const key =
        keys.current.get(candidate.candidate_id) ?? crypto.randomUUID();
      keys.current.set(candidate.candidate_id, key);
      let result: WorkflowRun | null = null;
      const accepted = await writing.acceptExternal(async () => {
        result = await client.candidate(
          chapterId,
          candidate.candidate_id,
          "adopt",
          key,
          active.current_version,
        );
        publish(result);
      });
      if (!accepted)
        throw new AIWritingError("请先保存或处理正文冲突，再确认采纳。");
      // Only this explicit author action can advance the next step.
      const next = result as WorkflowRun | null;
      if (
        continueAfter &&
        next &&
        next.status === "ready" &&
        !paused.current &&
        alive.current
      )
        await requestGeneration(next);
    }, active?.run_id);
  const pause = async () => {
    if (!active) return;
    paused.current = true;
    try {
      publish(await client.action(chapterId, active.run_id, "pause"));
    } catch (failure) {
      setErrorRunId(active.run_id);
      setError(
        failure instanceof Error
          ? failure.message
          : "暂停失败，请刷新确认状态。",
      );
    }
  };
  return {
    models,
    runs,
    active,
    busy,
    loading,
    error,
    errorRunId,
    generating,
    upgradeRequired,
    upgrading,
    upgradeMessage,
    upgrade: () =>
      execute(async () => {
        setUpgradeMessage("");
        if (!(await writing.flush()))
          throw new AIWritingError(
            "请先保存当前正文并处理版本冲突，再启用 AI 协作。",
          );
        setUpgrading(true);
        try {
          await client.upgrade();
          await refresh();
          if (alive.current)
            setUpgradeMessage("AI 协作已启用，可以保存模型配置。");
        } finally {
          if (alive.current) setUpgrading(false);
        }
      }),
    modelError: (failure: AIWritingError) => {
      if (!alive.current) return;
      setUpgradeRequired(true);
      setUpgradeMessage("");
      setError(failure.message);
      setErrorRunId(null);
    },
    prepare,
    generate,
    adopt,
    pause,
    select: (id: string) => {
      if (!lock.current) {
        setActiveId(id);
        setError("");
        setErrorRunId(null);
      }
    },
    refresh: () => execute(refresh),
    resume: () =>
      execute(async () => {
        if (active) {
          paused.current = false;
          publish(await client.action(chapterId, active.run_id, "resume"));
        }
      }, active?.run_id),
    discard: (candidate: WorkflowCandidate) =>
      execute(
        async () =>
          publish(
            await client.candidate(
              chapterId,
              candidate.candidate_id,
              "discard",
            ),
          ),
        active?.run_id,
      ),
    modelSaved: (saved: ModelProfile) => {
      if (!alive.current) return;
      modelRevision.current += 1;
      setModels((current) => [
        saved,
        ...current.filter((item) => item.id !== saved.id),
      ]);
    },
  };
}
