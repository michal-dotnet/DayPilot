import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Card, ErrorBox, Spinner } from "../components/ui";
import { applyLanguage } from "../i18n";
import { api, ApiError, type Me } from "../lib/api";
import { tList } from "../lib/format";

const KINDS = ["class", "work", "commitment", "active_hours", "preferred_study"];

export default function SettingsPage() {
  const { t, i18n } = useTranslation();
  const [me, setMe] = useState<Me | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [saved, setSaved] = useState(false);
  const [quitMsg, setQuitMsg] = useState("");
  const [prefs, setPrefs] = useState({ min_session_minutes: 60, max_session_minutes: 120, daily_max_minutes: 360 });
  const [rule, setRule] = useState({ weekday: 0, start_time: "09:00", end_time: "14:00", kind: "class", label: "" });

  const load = () =>
    api
      .me()
      .then((m) => {
        setMe(m);
        setPrefs({
          min_session_minutes: m.preferences.min_session_minutes,
          max_session_minutes: m.preferences.max_session_minutes,
          daily_max_minutes: m.preferences.daily_max_minutes,
        });
      })
      .catch(setError);

  useEffect(() => {
    load();
  }, []);

  if (error && !me) return <ErrorBox error={error} onRetry={load} />;
  if (!me) return <Spinner />;

  const update = async (data: Parameters<typeof api.updateSettings>[0]) => {
    setError(null);
    try {
      setMe(await api.updateSettings(data));
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e) {
      setError(e);
    }
  };

  const setLanguage = async (lng: "he" | "en") => {
    applyLanguage(lng);
    await update({ ui_language: lng });
  };

  const weekdays = tList("weekdays");

  const quit = async () => {
    if (!window.confirm(t("settings.quitConfirm"))) return;
    try {
      await api.shutdown();
      setQuitMsg(t("settings.stopped"));
    } catch (e) {
      if (e instanceof ApiError && e.code === "not_supported") setQuitMsg(t("settings.quitManual"));
      else setError(e);
    }
  };

  if (quitMsg && quitMsg === t("settings.stopped")) {
    return (
      <div className="flex h-[60vh] flex-col items-center justify-center gap-3 text-center">
        <div className="text-4xl">👋</div>
        <p className="text-lg text-slate-600">{quitMsg}</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center gap-3">
        <h1 className="text-2xl font-bold text-slate-800">{t("settings.title")}</h1>
        {saved && <span className="fade-in text-sm text-emerald-600">✓ {t("settings.saved")}</span>}
      </div>
      {error ? <ErrorBox error={error} /> : null}

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title={t("settings.language")} icon="🌐">
          <div className="flex gap-2">
            {(["he", "en"] as const).map((lng) => (
              <button key={lng} className={i18n.language === lng ? "btn-primary" : "btn-ghost"} onClick={() => setLanguage(lng)}>
                {lng === "he" ? "עברית" : "English"}
              </button>
            ))}
          </div>
        </Card>

        <Card title={t("settings.rest")} icon="🕯️">
          <label className="mb-1 block text-sm text-slate-600">{t("settings.city")}</label>
          <select className="input" value={me.city ?? ""} onChange={(e) => update({ city_key: e.target.value })}>
            {me.cities.map((c) => (
              <option key={c.key} value={c.key}>
                {i18n.language === "he" ? c.name_he : c.name_en}
              </option>
            ))}
          </select>
          <p className="mt-3 text-sm text-slate-500">
            {t("settings.restInfo", {
              hours: me.preferences.shabbat_buffer_minutes / 60,
              cholHamoed: me.preferences.block_chol_hamoed ? t("settings.blocked") : t("settings.notBlocked"),
            })}
          </p>
        </Card>

        <Card title={t("settings.sessions")} icon="⏱️">
          <div className="grid grid-cols-3 gap-3">
            {([
              ["min_session_minutes", "settings.minSession"],
              ["max_session_minutes", "settings.maxSession"],
              ["daily_max_minutes", "settings.dailyMax"],
            ] as const).map(([key, label]) => (
              <label key={key} className="text-xs text-slate-600">
                {t(label)}
                <input
                  type="number"
                  className="input mt-1"
                  value={prefs[key]}
                  min={15}
                  step={15}
                  onChange={(e) => setPrefs({ ...prefs, [key]: Number(e.target.value) })}
                />
              </label>
            ))}
          </div>
          <button className="btn-primary mt-4" onClick={() => update(prefs)}>
            {t("settings.save")}
          </button>
        </Card>

        <Card title={t("settings.rules")} icon="📌">
          <ul className="mb-4 flex flex-col gap-2">
            {me.rules.map((r) => (
              <li key={r.id} className="flex items-center justify-between rounded-xl bg-slate-50 px-3 py-2 text-sm">
                <span>
                  {weekdays[r.weekday]} ·{" "}
                  <span dir="ltr">
                    {r.start_time}–{r.end_time}
                  </span>{" "}
                  · {t(`settings.kinds.${r.kind}`)}
                  {r.label ? ` · ${r.label}` : ""}
                </span>
                <button className="text-slate-400 hover:text-rose-600" onClick={() => api.deleteRule(r.id).then(load).catch(setError)}>
                  ✕
                </button>
              </li>
            ))}
          </ul>
          <div className="grid grid-cols-2 gap-2 md:grid-cols-5">
            <select className="input" value={rule.weekday} onChange={(e) => setRule({ ...rule, weekday: Number(e.target.value) })}>
              {weekdays.map((w, i) => (
                <option key={i} value={i}>
                  {w}
                </option>
              ))}
            </select>
            <input type="time" className="input" value={rule.start_time} onChange={(e) => setRule({ ...rule, start_time: e.target.value })} />
            <input type="time" className="input" value={rule.end_time} onChange={(e) => setRule({ ...rule, end_time: e.target.value })} />
            <select className="input" value={rule.kind} onChange={(e) => setRule({ ...rule, kind: e.target.value })}>
              {KINDS.map((k) => (
                <option key={k} value={k}>
                  {t(`settings.kinds.${k}`)}
                </option>
              ))}
            </select>
            <button
              className="btn-primary"
              onClick={() =>
                api
                  .addRule(rule)
                  .then(load)
                  .catch(setError)
              }
            >
              {t("settings.addRule")}
            </button>
          </div>
          <p className="mt-3 text-xs text-slate-500">{t("settings.replanHint")}</p>
        </Card>

        <Card title={t("settings.quit")} icon="⏻">
          <p className="mb-3 text-sm text-slate-500">{t("settings.quitInfo")}</p>
          <button className="btn-danger" onClick={quit}>
            {t("settings.quit")}
          </button>
          {quitMsg && <p className="mt-3 text-sm text-amber-700">{quitMsg}</p>}
        </Card>
      </div>
    </div>
  );
}
