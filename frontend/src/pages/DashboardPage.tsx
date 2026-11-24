import { useTranslation } from "react-i18next";
import { Bar, BarChart, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Navigate } from "../App";
import { Card, Chip, ErrorBox, Spinner, Stat } from "../components/ui";
import { api } from "../lib/api";
import { daysUntil, fmtDate, fmtHours, fmtShortDay, fmtShortDayOf, fmtTime, taskColor } from "../lib/format";
import { useLoad } from "../lib/useLoad";

export default function DashboardPage({ navigate }: { navigate: Navigate }) {
  const { t, i18n } = useTranslation();
  const { data, error, loading, reload } = useLoad(() => api.dashboard(), [i18n.language]);

  if (loading && !data) return <Spinner />;
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return null;

  const chart = data.week.map((d) => ({
    day: fmtShortDay(d.date),
    hours: +(d.minutes / 60).toFixed(1),
    rest: d.is_rest_day,
    over: data.overloaded_days.includes(d.date),
  }));
  type Attention = { key: string; text: string; draft?: string; button?: string };
  const when = (s: { start: string; end: string }) => `${fmtShortDayOf(s.start)} ${fmtTime(s.start)}–${fmtTime(s.end)}`;
  const attention: Attention[] = [
    ...data.unreported_sessions.map((s) => ({
      key: `u${s.id}`,
      text: t("dashboard.unreported", { title: s.task_title, when: when(s) }),
      draft: t("dashboard.reportDraft", { task: s.task_title, when: when(s) }),
      button: t("dashboard.reportInChat"),
    })),
    ...data.needs_scheduling.map((v) => ({
      key: `s${v.id}`,
      text: t("dashboard.needsScheduling", { title: v.title }),
      draft: t("dashboard.scheduleDraft", { task: v.title }),
      button: t("dashboard.scheduleInChat"),
    })),
    ...data.idle_open_tasks.map((v) => ({ key: `o${v.id}`, text: t("dashboard.idleOpen", { title: v.title }) })),
    ...data.overloaded_days.map((d) => ({ key: `d${d}`, text: t("dashboard.overloaded", { day: fmtDate(d) }) })),
  ];

  return (
    <div className="flex flex-col gap-6">
      <header className="fade-in">
        <h1 className="text-2xl font-bold text-slate-800">{t("dashboard.hello")}</h1>
        <p className="mt-1 text-slate-500">
          {fmtDate(data.today)} · {data.hebrew_date_tonight ? t("dashboard.tonight", { date: data.hebrew_date_tonight }) : data.hebrew_date}
        </p>
      </header>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat label={t("dashboard.active")} value={data.counts.active} tone="brand" />
        <Stat label={t("dashboard.scheduled")} value={data.counts.scheduled} tone="sky" />
        <Stat label={t("dashboard.open")} value={data.counts.open} tone="emerald" />
        <Stat label={t("dashboard.recurring")} value={data.counts.recurring} tone="amber" />
      </div>

      <div className="grid gap-6 lg:grid-cols-5">
        <Card title={t("dashboard.todayPlan")} icon="🗓️" className="lg:col-span-2">
          {data.today_sessions.length === 0 ? (
            <p className="text-sm text-slate-500">{t("dashboard.noSessions")}</p>
          ) : (
            <ul className="flex flex-col gap-2">
              {data.today_sessions.map((s) => (
                <li key={s.id} className="flex items-center gap-3 rounded-xl bg-slate-50 p-3">
                  <span className="h-8 w-1.5 rounded-full" style={{ background: taskColor(s.task_id) }} />
                  <div className="flex-1">
                    <div className="font-medium">{s.task_title}</div>
                    <div className="text-xs text-slate-500" dir="ltr">
                      {fmtTime(s.start)}–{fmtTime(s.end)}
                    </div>
                  </div>
                  {s.status !== "planned" && <Chip tone="emerald">{s.status}</Chip>}
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title={t("dashboard.week")} icon="📊" className="lg:col-span-3">
          <div className="h-52" dir="ltr">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={i18n.language === "he" ? [...chart].reverse() : chart}>
                <XAxis dataKey="day" tick={{ fontSize: 12 }} />
                <YAxis width={28} tick={{ fontSize: 12 }} />
                <Tooltip formatter={(v) => [`${v}`, "h"]} />
                <ReferenceLine y={data.daily_max_minutes / 60} stroke="#f43f5e" strokeDasharray="4 4" label={{ value: t("dashboard.limit"), fontSize: 11, fill: "#f43f5e" }} />
                <Bar dataKey="hours" radius={[6, 6, 0, 0]}>
                  {(i18n.language === "he" ? [...chart].reverse() : chart).map((d, i) => (
                    <Cell key={i} fill={d.rest ? "#c4b5fd" : d.over ? "#fb7185" : "#6366f1"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title={t("dashboard.deadlines")} icon="⏰">
          {data.upcoming_deadlines.length === 0 ? (
            <p className="text-sm text-slate-500">{t("dashboard.noDeadlines")}</p>
          ) : (
            <ul className="flex flex-col gap-2">
              {data.upcoming_deadlines.map((v) => {
                const n = daysUntil(v.deadline!);
                return (
                  <li key={v.id} className="flex items-center justify-between rounded-xl bg-slate-50 p-3">
                    <div>
                      <div className="font-medium">{v.title}</div>
                      <div className="text-xs text-slate-500">
                        {fmtDate(v.deadline!)} · {fmtHours(v.remaining_minutes || 0)}
                      </div>
                    </div>
                    <Chip tone={n <= 1 ? "rose" : n <= 3 ? "amber" : "brand"}>
                      {n <= 0 ? t("common.today") : n === 1 ? t("common.tomorrow") : t("common.inDays", { count: n })}
                    </Chip>
                  </li>
                );
              })}
            </ul>
          )}
        </Card>

        <Card title={t("dashboard.attention")} icon="🔔">
          {attention.length === 0 ? (
            <p className="text-sm text-emerald-600">{t("dashboard.allGood")}</p>
          ) : (
            <ul className="flex flex-col gap-2">
              {attention.map((a) => (
                <li key={a.key} className="flex items-center justify-between gap-3 rounded-xl bg-amber-50 p-3 text-sm text-amber-800">
                  <span>{a.text}</span>
                  {a.draft && (
                    <button className="btn-ghost shrink-0 !py-1" onClick={() => navigate("chat", a.draft!)}>
                      {a.button}
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}
