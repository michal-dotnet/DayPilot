import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { Approval } from "../lib/api";
import { Chip } from "./ui";

// כרטיס ההצעה שממתינה לאישור. הכפתורים שולחים Command(resume=...) לגרף דרך ה-API.
export default function ApprovalCard({
  approval,
  busy,
  onDecide,
}: {
  approval: Approval;
  busy: boolean;
  onDecide: (action: "approve" | "reject" | "revise", feedback?: string) => void;
}) {
  const { t } = useTranslation();
  const [revising, setRevising] = useState(false);
  const [feedback, setFeedback] = useState("");
  const p = approval.proposal;

  return (
    <div className="fade-in rounded-2xl border-2 border-indigo-200 bg-indigo-50/60 p-4">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 className="font-semibold text-indigo-800">⏸️ {t("chat.approvalTitle")}</h3>
        {!p.feasible && <Chip tone="amber">{t("chat.notFeasible")}</Chip>}
      </div>
      <pre className="whitespace-pre-wrap rounded-xl bg-white p-3 font-sans text-sm leading-6 text-slate-700 ring-1 ring-indigo-100">
        {approval.display}
      </pre>

      {revising ? (
        <div className="mt-3 flex flex-col gap-2">
          <textarea
            className="input min-h-20"
            value={feedback}
            placeholder={t("chat.revisePlaceholder")}
            onChange={(e) => setFeedback(e.target.value)}
            autoFocus
          />
          <div className="flex gap-2">
            <button className="btn-primary" disabled={busy || !feedback.trim()} onClick={() => onDecide("revise", feedback.trim())}>
              {t("chat.sendRevise")}
            </button>
            <button className="btn-ghost" onClick={() => setRevising(false)}>
              ✕
            </button>
          </div>
        </div>
      ) : (
        <div className="mt-3 flex flex-wrap gap-2">
          <button className="btn-primary" disabled={busy} onClick={() => onDecide("approve")}>
            ✅ {t("chat.approve")}
          </button>
          <button className="btn-ghost" disabled={busy} onClick={() => setRevising(true)}>
            ✏️ {t("chat.revise")}
          </button>
          <button className="btn-danger" disabled={busy} onClick={() => onDecide("reject")}>
            ✕ {t("chat.reject")}
          </button>
        </div>
      )}
    </div>
  );
}
