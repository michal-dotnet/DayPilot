import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import ApprovalCard from "../components/ApprovalCard";
import { ErrorBox } from "../components/ui";
import { api, type Approval, type ChatMessage, type Turn } from "../lib/api";
import { tList } from "../lib/format";

const LAST_THREAD = "daypilot.lastThread";

function remember(id: string | null) {
  try {
    if (id) localStorage.setItem(LAST_THREAD, id);
    else localStorage.removeItem(LAST_THREAD);
  } catch {
    /* אחסון הדפדפן לא זמין: לא נורא */
  }
}

function recall(): string | null {
  try {
    return localStorage.getItem(LAST_THREAD);
  } catch {
    return null;
  }
}

export default function ChatPage({ draft, onDraftUsed }: { draft: string; onDraftUsed: () => void }) {
  const { t } = useTranslation();
  const [threads, setThreads] = useState<{ id: string; title: string }[]>([]);
  const [threadId, setThreadId] = useState<string | null>(recall());
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [approval, setApproval] = useState<Approval | null>(null);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const bottom = useRef<HTMLDivElement>(null);

  const loadThreads = () => api.threads().then(setThreads).catch(setError);

  useEffect(() => {
    loadThreads();
  }, []);

  useEffect(() => {
    if (draft) {
      setInput(draft);
      onDraftUsed();
    }
  }, [draft, onDraftUsed]);

  useEffect(() => {
    if (!threadId) {
      setMessages([]);
      setApproval(null);
      return;
    }
    remember(threadId);
    api
      .thread(threadId)
      .then((th) => {
        setMessages(th.messages);
        setApproval(th.approval);
      })
      .catch(setError);
  }, [threadId]);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, approval, busy]);

  const applyTurn = (turn: Turn) => {
    if (turn.reply) setMessages((m) => [...m, { role: "assistant", content: turn.reply! }]);
    setApproval(turn.approval);
  };

  const send = async (text: string) => {
    const clean = text.trim();
    if (!clean || busy) return;
    setError(null);
    setBusy(true);
    let id = threadId;
    try {
      if (!id) {
        id = (await api.newThread()).id;
        setThreadId(id);
      }
      setMessages((m) => [...m, { role: "user", content: clean }]);
      setInput("");
      applyTurn(await api.send(id, clean));
      loadThreads();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  const decide = async (action: "approve" | "reject" | "revise", feedback = "") => {
    if (!threadId) return;
    setError(null);
    setBusy(true);
    const label = action === "approve" ? t("chat.approve") : action === "reject" ? t("chat.reject") : `${t("chat.revise")}: ${feedback}`;
    setMessages((m) => [...m, { role: "user", content: label }]);
    setApproval(null);
    try {
      applyTurn(await api.decide(threadId, action, feedback));
    } catch (e) {
      setError(e);
      api.thread(threadId).then((th) => setApproval(th.approval)).catch(() => undefined);
    } finally {
      setBusy(false);
    }
  };

  const removeThread = async () => {
    if (!threadId || !window.confirm(t("chat.confirmDelete"))) return;
    await api.deleteThread(threadId).catch(setError);
    setThreadId(null);
    remember(null);
    loadThreads();
  };

  return (
    <div className="flex h-[calc(100vh-6rem)] gap-4">
      <aside className="card hidden w-56 shrink-0 flex-col gap-2 !p-3 lg:flex">
        <button className="btn-primary w-full" onClick={() => { setThreadId(null); remember(null); }}>
          ＋ {t("chat.newChat")}
        </button>
        <div className="mt-2 px-1 text-xs font-medium text-slate-400">{t("chat.history")}</div>
        <div className="flex flex-col gap-1 overflow-y-auto">
          {threads.map((th) => (
            <button
              key={th.id}
              onClick={() => setThreadId(th.id)}
              className={`truncate rounded-lg px-2 py-1.5 text-start text-sm ${th.id === threadId ? "bg-indigo-50 text-indigo-700" : "text-slate-600 hover:bg-slate-50"}`}
              title={th.title}
            >
              {th.title || th.id}
            </button>
          ))}
        </div>
      </aside>

      <section className="card flex min-w-0 flex-1 flex-col !p-0">
        <header className="flex items-center justify-between border-b border-slate-100 px-5 py-3">
          <h1 className="font-semibold text-slate-700">💬 {t("nav.chat")}</h1>
          {threadId && messages.length > 0 && (
            <button className="text-xs text-slate-400 hover:text-rose-600" onClick={removeThread}>
              🗑 {t("chat.deleteChat")}
            </button>
          )}
        </header>

        <div className="flex-1 space-y-3 overflow-y-auto p-5">
          {messages.length === 0 && !busy && (
            <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
              <div className="text-4xl">🧭</div>
              <p className="text-lg font-medium text-slate-600">{t("chat.empty")}</p>
              <div className="flex flex-wrap justify-center gap-2">
                {tList("chat.examples").map((ex) => (
                  <button key={ex} className="btn-ghost !rounded-full !text-xs" onClick={() => send(ex)}>
                    {ex}
                  </button>
                ))}
              </div>
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} className={`fade-in flex ${m.role === "user" ? "justify-start" : "justify-end"}`}>
              <div
                className={`max-w-[80%] whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-sm leading-6 ${
                  m.role === "user" ? "bg-indigo-600 text-white" : "bg-slate-100 text-slate-800"
                }`}
              >
                {m.content}
              </div>
            </div>
          ))}
          {approval && <ApprovalCard approval={approval} busy={busy} onDecide={decide} />}
          {busy && (
            <div className="flex items-center gap-2 text-sm text-slate-500">
              <span className="h-2 w-2 animate-bounce rounded-full bg-indigo-400" />
              {t("chat.thinking")}
            </div>
          )}
          {error ? <ErrorBox error={error} /> : null}
          <div ref={bottom} />
        </div>

        <form
          className="flex gap-2 border-t border-slate-100 p-3"
          onSubmit={(e) => {
            e.preventDefault();
            send(input);
          }}
        >
          <input
            className="input flex-1"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={t("chat.placeholder")}
            disabled={busy || !!approval}
            maxLength={4000}
          />
          <button className="btn-primary" disabled={busy || !!approval || !input.trim()}>
            {t("chat.send")}
          </button>
        </form>
      </section>
    </div>
  );
}
