import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { ApiError } from "../lib/api";

export function Card({ title, icon, children, className = "", action }: {
  title?: string; icon?: string; children: ReactNode; className?: string; action?: ReactNode;
}) {
  return (
    <section className={`card fade-in ${className}`}>
      {title && (
        <header className="mb-4 flex items-center justify-between gap-2">
          <h2 className="flex items-center gap-2 text-base font-semibold text-slate-700">
            {icon && <span aria-hidden>{icon}</span>}
            {title}
          </h2>
          {action}
        </header>
      )}
      {children}
    </section>
  );
}

export function Stat({ label, value, tone = "brand" }: { label: string; value: ReactNode; tone?: "brand" | "emerald" | "amber" | "sky" | "rose" }) {
  const tones = {
    brand: "from-indigo-500 to-violet-500",
    emerald: "from-emerald-500 to-teal-500",
    amber: "from-amber-500 to-orange-500",
    sky: "from-sky-500 to-cyan-500",
    rose: "from-rose-500 to-pink-500",
  };
  return (
    <div className={`fade-in rounded-2xl bg-linear-to-br ${tones[tone]} p-4 text-white shadow-sm`}>
      <div className="text-sm opacity-90">{label}</div>
      <div className="mt-1 text-2xl font-bold">{value}</div>
    </div>
  );
}

export function Spinner({ label }: { label?: string }) {
  const { t } = useTranslation();
  return (
    <div className="flex items-center gap-3 py-6 text-slate-500">
      <span className="h-5 w-5 animate-spin rounded-full border-2 border-brand-500 border-t-transparent" />
      {label ?? t("common.loading")}
    </div>
  );
}

export function ErrorBox({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const { t } = useTranslation();
  const message =
    error instanceof ApiError && error.code === "server_unreachable"
      ? t("common.serverDown")
      : error instanceof ApiError && error.code === "missing_api_key"
        ? t("chat.missingKey")
        : error instanceof Error
          ? error.message
          : String(error);
  return (
    <div className="fade-in flex items-center justify-between gap-3 rounded-xl bg-rose-50 p-4 text-sm text-rose-700 ring-1 ring-rose-200">
      <span>{message}</span>
      {onRetry && (
        <button className="btn-ghost" onClick={onRetry}>
          {t("common.retry")}
        </button>
      )}
    </div>
  );
}

export function ProgressBar({ parts, total }: { parts: { value: number; color: string }[]; total: number }) {
  return (
    <div className="flex h-2.5 w-full overflow-hidden rounded-full bg-slate-100">
      {parts.map((p, i) => (
        <div
          key={i}
          style={{ width: `${total ? Math.min(100, (p.value / total) * 100) : 0}%`, background: p.color }}
          className="h-full transition-all duration-500"
        />
      ))}
    </div>
  );
}

export function Chip({ children, tone = "slate" }: { children: ReactNode; tone?: "slate" | "brand" | "emerald" | "amber" | "rose" }) {
  const tones = {
    slate: "bg-slate-100 text-slate-600",
    brand: "bg-indigo-50 text-indigo-700",
    emerald: "bg-emerald-50 text-emerald-700",
    amber: "bg-amber-50 text-amber-700",
    rose: "bg-rose-50 text-rose-700",
  };
  return <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${tones[tone]}`}>{children}</span>;
}
