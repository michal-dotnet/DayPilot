import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card, ErrorBox, Spinner, Stat } from "../components/ui";
import { api } from "../lib/api";
import { fmtHours, fmtShortDay } from "../lib/format";
import { useLoad } from "../lib/useLoad";

export default function ProgressPage() {
  const { t, i18n } = useTranslation();
  const [days, setDays] = useState(14);
  const { data, error, loading, reload } = useLoad(() => api.progress(days), [days, i18n.language]);
  const he = i18n.language === "he";

  if (loading && !data) return <Spinner />;
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return null;

  const daily = data.daily_minutes.map((d) => ({ day: fmtShortDay(d.date), minutes: d.minutes }));
  const byTask = data.tasks.map((x) => ({
    name: x.title,
    [t("progress.doneLabel")]: +(x.done_minutes / 60).toFixed(1),
    [t("progress.plannedLabel")]: +(x.scheduled_minutes / 60).toFixed(1),
    [t("progress.remainingLabel")]: +(Math.max(0, x.remaining_minutes - x.scheduled_minutes) / 60).toFixed(1),
  }));

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-slate-800">{t("progress.title")}</h1>
        <select className="input !w-auto" value={days} onChange={(e) => setDays(Number(e.target.value))}>
          {[7, 14, 30].map((n) => (
            <option key={n} value={n}>
              {t("progress.range", { count: n })}
            </option>
          ))}
        </select>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat label={t("progress.totalTime")} value={fmtHours(data.total_minutes)} tone="brand" />
        <Stat label={t("progress.sessionsDone")} value={data.sessions_done} tone="emerald" />
        <Stat label={t("progress.completion")} value={data.completion_rate === null ? "—" : `${Math.round(data.completion_rate * 100)}%`} tone="sky" />
        <Stat label={t("progress.completed")} value={data.tasks_completed} tone="amber" />
      </div>

      <Card title={t("progress.daily")} icon="📊">
        {data.total_minutes === 0 ? (
          <p className="text-sm text-slate-500">{t("progress.noData")}</p>
        ) : (
          <div className="h-56" dir="ltr">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={he ? [...daily].reverse() : daily}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="day" tick={{ fontSize: 11 }} />
                <YAxis width={32} tick={{ fontSize: 11 }} />
                <Tooltip />
                <Bar dataKey="minutes" fill="#10b981" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </Card>

      {byTask.length > 0 && (
        <Card title={t("progress.byTask")} icon="🎯">
          <div style={{ height: 60 + byTask.length * 44 }} dir="ltr">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={byTask} layout="vertical" margin={{ left: 20 }}>
                <XAxis type="number" tick={{ fontSize: 11 }} />
                <YAxis type="category" dataKey="name" width={140} tick={{ fontSize: 12 }} orientation={he ? "right" : "left"} />
                <Tooltip />
                <Legend />
                <Bar dataKey={t("progress.doneLabel")} stackId="a" fill="#10b981" />
                <Bar dataKey={t("progress.plannedLabel")} stackId="a" fill="#818cf8" />
                <Bar dataKey={t("progress.remainingLabel")} stackId="a" fill="#e2e8f0" radius={[0, 6, 6, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      )}
    </div>
  );
}
