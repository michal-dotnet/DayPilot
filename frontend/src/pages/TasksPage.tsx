import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { Navigate } from "../App";
import { Card, Chip, ErrorBox, ProgressBar, Spinner } from "../components/ui";
import { api, type TaskType, type TaskView } from "../lib/api";
import { daysUntil, fmtDate, fmtHours, taskColor } from "../lib/format";
import { useLoad } from "../lib/useLoad";

const GROUPS: { type: TaskType; icon: string }[] = [
  { type: "scheduled", icon: "🎯" },
  { type: "recurring", icon: "🔁" },
  { type: "open", icon: "📝" },
];

export default function TasksPage({ navigate }: { navigate: Navigate }) {
  const { t, i18n } = useTranslation();
  const [showDone, setShowDone] = useState(false);
  const { data, error, loading, reload } = useLoad(() => api.tasks(showDone), [showDone, i18n.language]);

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">{t("tasks.title")}</h1>
          <p className="text-sm text-slate-500">{t("tasks.hint")}</p>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-sm text-slate-600">
            <input type="checkbox" checked={showDone} onChange={(e) => setShowDone(e.target.checked)} />
            {t("tasks.showDone")}
          </label>
          <button className="btn-primary" onClick={() => navigate("chat")}>
            💬 {t("nav.chat")}
          </button>
        </div>
      </div>

      {loading && !data && <Spinner />}
      {error ? <ErrorBox error={error} onRetry={reload} /> : null}
      {data && data.length === 0 && <Card><p className="text-slate-500">{t("tasks.empty")}</p></Card>}

      {data &&
        GROUPS.map(({ type, icon }) => {
          const items = data.filter((x) => x.task_type === type);
          if (items.length === 0) return null;
          return (
            <Card key={type} title={`${t(`tasks.${type}`)} (${items.length})`} icon={icon}>
              <div className="grid gap-3 md:grid-cols-2">
                {items.map((task) => (
                  <TaskCard key={task.id} task={task} />
                ))}
              </div>
            </Card>
          );
        })}
    </div>
  );
}

function TaskCard({ task }: { task: TaskView }) {
  const { t } = useTranslation();
  const total = task.estimated_minutes || 0;
  const done = Math.max(0, total - (task.remaining_minutes ?? total));
  const left = task.deadline ? daysUntil(task.deadline) : null;
  const color = taskColor(task.id);
  return (
    <div className={`rounded-xl border border-slate-200 p-4 ${task.status === "done" ? "opacity-60" : ""}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="h-3 w-3 rounded-full" style={{ background: color }} />
          <h3 className="font-semibold">{task.title}</h3>
        </div>
        {task.status === "done" ? (
          <Chip tone="emerald">{t("tasks.statusDone")}</Chip>
        ) : left !== null ? (
          <Chip tone={left <= 1 ? "rose" : left <= 3 ? "amber" : "brand"}>
            {left < 0 ? t("common.overdue") : left === 0 ? t("common.today") : left === 1 ? t("common.tomorrow") : t("common.inDays", { count: left })}
          </Chip>
        ) : null}
      </div>

      {task.deadline && (
        <p className="mt-1 text-xs text-slate-500">
          {t("tasks.deadline")}: {fmtDate(task.deadline)}
        </p>
      )}

      {task.task_type === "scheduled" && total > 0 && (
        <div className="mt-3">
          <ProgressBar
            total={total}
            parts={[
              { value: done, color: "#10b981" },
              { value: Math.min(task.scheduled_minutes, total - done), color: `${color}88` },
            ]}
          />
          <div className="mt-1.5 flex justify-between text-xs text-slate-500">
            <span>{t("tasks.done", { done: fmtHours(done), total: fmtHours(total) })}</span>
            <span>{t("tasks.planned", { value: fmtHours(task.scheduled_minutes) })}</span>
          </div>
        </div>
      )}

      <div className="mt-3 flex flex-wrap gap-2">
        {task.task_type === "scheduled" && (
          <Chip tone={task.work_style === "exam" ? "rose" : "brand"}>
            {t(task.work_style === "exam" ? "tasks.styleExam" : "tasks.styleAssignment")}
          </Chip>
        )}
        <Chip>{t("tasks.importance")}: {"★".repeat(task.importance)}</Chip>
        {task.recurrence_rule && <Chip tone="brand" >{task.recurrence_rule}</Chip>}
        {task.postponed_count >= 2 && <Chip tone="amber">{t("tasks.postponed", { count: task.postponed_count })}</Chip>}
      </div>

      {task.assumptions.length > 0 && (
        <details className="mt-3 text-xs text-slate-500">
          <summary className="cursor-pointer">{t("tasks.assumptions")}</summary>
          <ul className="mt-1 list-disc ps-5">
            {task.assumptions.map((a, i) => (
              <li key={i}>{a}</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
