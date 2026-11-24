import heLocale from "@fullcalendar/core/locales/he";
import type { DatesSetArg, DayHeaderContentArg, EventInput } from "@fullcalendar/core";
import FullCalendar from "@fullcalendar/react";
import timeGridPlugin from "@fullcalendar/timegrid";
import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";
import { Card, ErrorBox } from "../components/ui";
import { api, type CalendarData } from "../lib/api";
import { addDays, taskColor } from "../lib/format";

export default function CalendarPage() {
  const { t, i18n } = useTranslation();
  const [data, setData] = useState<CalendarData | null>(null);
  const [error, setError] = useState<unknown>(null);
  const he = i18n.language === "he";

  const onDates = useCallback((arg: DatesSetArg) => {
    const start = arg.startStr.slice(0, 10);
    const end = addDays(arg.endStr.slice(0, 10), -1);
    setError(null);
    api.calendar(start, end).then(setData).catch(setError);
  }, []);

  const events: EventInput[] = [];
  if (data) {
    for (const b of data.blocks) {
      events.push({
        start: b.start,
        end: b.end,
        title: b.label,
        display: "background",
        classNames: [b.kind === "rest" ? "block-rest" : b.kind === "event" ? "block-event" : "block-busy"],
      });
    }
    for (const s of data.sessions) {
      const color = taskColor(s.task_id);
      events.push({
        id: String(s.id),
        start: s.start,
        end: s.end,
        title: s.task_title,
        backgroundColor: s.status === "planned" ? color : "#94a3b8",
        borderColor: color,
      });
    }
  }
  const dayInfo = new Map(data?.days.map((d) => [d.date, d]) ?? []);

  const renderHeader = (arg: DayHeaderContentArg) => {
    const iso = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Jerusalem" }).format(arg.date);
    const info = dayInfo.get(iso);
    return (
      <div className="flex flex-col items-center py-1 leading-tight">
        <span className="font-semibold">{arg.text}</span>
        {info && <span className="text-[0.68rem] font-normal text-slate-500">{info.hebrew_date}</span>}
        {info?.holiday && <span className="text-[0.68rem] font-medium text-violet-600">{info.holiday}</span>}
      </div>
    );
  };

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-bold text-slate-800">{t("nav.calendar")}</h1>
      {error ? <ErrorBox error={error} /> : null}
      <Card>
        <div className="mb-3 flex flex-wrap gap-4 text-xs text-slate-600">
          <Legend className="bg-indigo-500" label={t("calendar.legendSession")} />
          <Legend className="bg-violet-200" label={t("calendar.legendRest")} />
          <Legend className="bg-slate-200" label={t("calendar.legendBusy")} />
          <Legend className="bg-amber-200" label={t("calendar.legendEvent")} />
        </div>
        <FullCalendar
          key={i18n.language}
          plugins={[timeGridPlugin]}
          initialView="timeGridWeek"
          locales={[heLocale]}
          locale={he ? "he" : "en"}
          direction={he ? "rtl" : "ltr"}
          firstDay={0}
          headerToolbar={{ start: "prev,next today", center: "title", end: "timeGridWeek,timeGridDay" }}
          buttonText={{ today: t("calendar.today"), week: t("calendar.week"), day: t("calendar.day") }}
          slotMinTime="07:00:00"
          slotMaxTime="23:30:00"
          allDaySlot={false}
          nowIndicator
          height="auto"
          expandRows
          events={events}
          datesSet={onDates}
          dayHeaderContent={renderHeader}
          eventTimeFormat={{ hour: "2-digit", minute: "2-digit", hour12: false }}
          slotLabelFormat={{ hour: "2-digit", minute: "2-digit", hour12: false }}
        />
      </Card>
    </div>
  );
}

function Legend({ className, label }: { className: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className={`h-3 w-3 rounded ${className}`} />
      {label}
    </span>
  );
}
