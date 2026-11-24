import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { applyLanguage } from "./i18n";
import { api } from "./lib/api";
import CalendarPage from "./pages/CalendarPage";
import ChatPage from "./pages/ChatPage";
import DashboardPage from "./pages/DashboardPage";
import ProgressPage from "./pages/ProgressPage";
import SettingsPage from "./pages/SettingsPage";
import TasksPage from "./pages/TasksPage";

export type Page = "dashboard" | "calendar" | "tasks" | "chat" | "progress" | "settings";
export type Navigate = (page: Page, chatDraft?: string) => void;

const NAV: { page: Page; icon: string }[] = [
  { page: "dashboard", icon: "🏠" },
  { page: "calendar", icon: "📅" },
  { page: "tasks", icon: "✅" },
  { page: "chat", icon: "💬" },
  { page: "progress", icon: "📈" },
  { page: "settings", icon: "⚙️" },
];

function pageFromHash(): Page {
  const value = window.location.hash.replace("#/", "") as Page;
  return NAV.some((n) => n.page === value) ? value : "dashboard";
}

export default function App() {
  const { t } = useTranslation();
  const [page, setPage] = useState<Page>(pageFromHash());
  const [chatDraft, setChatDraft] = useState("");

  useEffect(() => {
    api.me().then((me) => applyLanguage(me.ui_language)).catch(() => applyLanguage("he"));
    const onHash = () => setPage(pageFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const navigate: Navigate = (next, draft) => {
    if (draft !== undefined) setChatDraft(draft);
    window.location.hash = `#/${next}`;
    setPage(next);
  };

  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-e border-slate-200 bg-white p-4 md:flex">
        <div className="mb-8 flex items-center gap-3 px-2">
          <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-linear-to-br from-indigo-500 to-violet-500 text-xl text-white shadow">
            🧭
          </div>
          <div>
            <div className="text-lg font-bold text-slate-800">{t("app.name")}</div>
            <div className="text-xs text-slate-500">{t("app.tagline")}</div>
          </div>
        </div>
        <nav className="flex flex-col gap-1">
          {NAV.map((n) => (
            <button
              key={n.page}
              onClick={() => navigate(n.page)}
              className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-start text-sm font-medium transition ${
                page === n.page ? "bg-indigo-50 text-indigo-700" : "text-slate-600 hover:bg-slate-50"
              }`}
            >
              <span aria-hidden>{n.icon}</span>
              {t(`nav.${n.page}`)}
            </button>
          ))}
        </nav>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        {/* תפריט במסך צר */}
        <nav className="flex gap-1 overflow-x-auto border-b border-slate-200 bg-white p-2 md:hidden">
          {NAV.map((n) => (
            <button
              key={n.page}
              onClick={() => navigate(n.page)}
              className={`whitespace-nowrap rounded-lg px-3 py-1.5 text-sm ${page === n.page ? "bg-indigo-50 text-indigo-700" : "text-slate-600"}`}
            >
              {n.icon} {t(`nav.${n.page}`)}
            </button>
          ))}
        </nav>
        <main className="mx-auto w-full max-w-6xl flex-1 p-4 md:p-8">
          {page === "dashboard" && <DashboardPage navigate={navigate} />}
          {page === "calendar" && <CalendarPage />}
          {page === "tasks" && <TasksPage navigate={navigate} />}
          {page === "chat" && <ChatPage draft={chatDraft} onDraftUsed={() => setChatDraft("")} />}
          {page === "progress" && <ProgressPage />}
          {page === "settings" && <SettingsPage />}
        </main>
      </div>
    </div>
  );
}
