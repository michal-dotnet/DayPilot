// עברית ואנגלית. השפה נשמרת בהגדרות המשתמשת בשרת, וכיוון הדף (RTL/LTR) מתעדכן בהתאם.
import i18n from "i18next";
import { initReactI18next } from "react-i18next";

const he = {
  app: { name: "DayPilot", tagline: "ניהול זמן, משימות ולמידה" },
  nav: { dashboard: "לוח בקרה", calendar: "לוח שנה", tasks: "משימות", chat: "צ'אט", progress: "התקדמות", settings: "הגדרות" },
  common: {
    hour: "שעה", hours: "{{value}} שעות", minutes: "{{count}} דק'", loading: "טוען...", retry: "נסי שוב",
    none: "אין", today: "היום", tomorrow: "מחר", inDays: "בעוד {{count}} ימים", overdue: "עבר המועד",
    serverDown: "אין חיבור לשרת. ודאי ש-python backend/run.py פועל.",
  },
  dashboard: {
    hello: "שלום!", todayPlan: "התוכנית להיום", noSessions: "אין מפגשים מתוכננים להיום.",
    week: "עומס בשבוע הקרוב", deadlines: "מועדי יעד קרובים", noDeadlines: "אין מועדים בשבוע הקרוב.",
    attention: "דורש תשומת לב", needsScheduling: "עוד לא שובצה במלואה: {{title}}",
    idleOpen: "משימה פתוחה שמחכה: {{title}}", overloaded: "יום עמוס: {{day}}", allGood: "הכל מסודר.",
    scheduleInChat: "לשבץ בצ'אט", active: "משימות פעילות", scheduled: "מתוזמנות", open: "פתוחות", recurring: "חוזרות",
    limit: "תקרה יומית", rest: "שבת/חג", scheduleDraft: "תשבצי לי זמן ל{{task}}", tonight: "אור ל{{date}}", unreported: "מפגש שעבר בלי דיווח: {{title}}, {{when}}",
    reportInChat: "לדווח בצ'אט", reportDraft: "עשיתי את המפגש של {{task}} ({{when}})",
  },
  calendar: { week: "שבוע", day: "יום", today: "היום", legendSession: "מפגש עבודה", legendRest: "שבת וחג",
    legendBusy: "לימודים, עבודה והתחייבויות", legendEvent: "אירוע קבוע" },
  tasks: {
    title: "המשימות שלי", showDone: "להציג גם משימות שהושלמו", empty: "אין משימות עדיין. אפשר להוסיף בצ'אט.",
    scheduled: "מתוזמנות", open: "פתוחות", recurring: "חוזרות", done: "בוצעו {{done}} מתוך {{total}}",
    planned: "משובצות {{value}}", deadline: "מועד יעד", importance: "חשיבות", postponed: "נדחתה {{count}} פעמים",
    assumptions: "הנחות", statusDone: "הושלמה", hint: "שינויים במשימות נעשים בצ'אט.",
    styleExam: "📚 לימוד למבחן", styleAssignment: "📝 מטלה",
  },
  chat: {
    newChat: "שיחה חדשה", history: "שיחות", placeholder: "כתבי הודעה, למשל: יש לי מבחן בעוד שבוע ואני צריכה 10 שעות",
    send: "שליחה", thinking: "DayPilot חושב...", empty: "במה אפשר לעזור?", deleteChat: "מחיקת השיחה",
    confirmDelete: "למחוק את היסטוריית השיחה? המשימות לא יימחקו.",
    approvalTitle: "הצעה שממתינה לאישור", approve: "אישור", reject: "דחייה", revise: "בקשת שינוי",
    revisePlaceholder: "מה לשנות? למשל: רק בערבים", sendRevise: "שליחת הבקשה", notFeasible: "אין מספיק זמן לכל המשימות",
    examples: ["יש לי מבחן בעוד שבוע ואני צריכה ללמוד 20 שעות", "מה יש לי מחר?", "אני צריכה לקנות מחברת"],
    missingKey: "חסר מפתח OpenAI בקובץ .env, ולכן האגנט לא זמין.",
  },
  progress: {
    title: "התקדמות", range: "ב-{{count}} הימים האחרונים", totalTime: "זמן עבודה", sessionsDone: "מפגשים שבוצעו",
    completion: "עמידה בתוכנית", completed: "משימות שהושלמו", daily: "דקות עבודה ביום", byTask: "התקדמות לפי משימה",
    doneLabel: "בוצע", plannedLabel: "משובץ", remainingLabel: "נשאר", noData: "עוד אין דיווחי התקדמות. אפשר לדווח בצ'אט.",
  },
  settings: {
    title: "הגדרות", language: "שפה", city: "עיר (לזמני שבת וחג)", sessions: "מפגשי עבודה",
    minSession: "מפגש קצר ביותר (דקות)", maxSession: "מפגש ארוך ביותר (דקות)", dailyMax: "תקרה יומית (דקות)",
    save: "שמירה", saved: "נשמר", rules: "שעות קבועות", addRule: "הוספה", weekday: "יום", from: "משעה", to: "עד שעה",
    kind: "סוג", label: "תיאור", rest: "שבת וחג", restInfo: "חסימה מ-{{hours}} שעות לפני הדלקת נרות. חול המועד: {{cholHamoed}}.",
    blocked: "חסום", notBlocked: "לא חסום", kinds: { active_hours: "שעות פעילות", preferred_study: "שעות למידה מועדפות",
      class: "לימודים", work: "עבודה", commitment: "התחייבות" },
    quit: "יציאה מ-DayPilot", quitInfo: "עוצר את השרת שפועל ברקע. כדי לפתוח שוב: לחיצה על האייקון.",
    quitConfirm: "לעצור את DayPilot?", stopped: "DayPilot נסגר. אפשר לסגור את הלשונית.",
    quitManual: "השרת הופעל מחלון CMD. כדי לעצור אותו: Ctrl+C בחלון.",
    replanHint: "שינוי בשעות לא מזיז מפגשים קיימים. כדי לעדכן את התוכנית, בקשי בצ'אט: \"תעדכני את התוכנית\".",
  },
  weekdays: ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"],
};

const en: typeof he = {
  app: { name: "DayPilot", tagline: "Time, tasks and study planning" },
  nav: { dashboard: "Dashboard", calendar: "Calendar", tasks: "Tasks", chat: "Chat", progress: "Progress", settings: "Settings" },
  common: {
    hour: "1 hour", hours: "{{value}} hours", minutes: "{{count}} min", loading: "Loading...", retry: "Retry",
    none: "None", today: "Today", tomorrow: "Tomorrow", inDays: "In {{count}} days", overdue: "Overdue",
    serverDown: "Cannot reach the server. Make sure python backend/run.py is running.",
  },
  dashboard: {
    hello: "Hello!", todayPlan: "Today's plan", noSessions: "No sessions planned for today.",
    week: "Load this week", deadlines: "Upcoming deadlines", noDeadlines: "No deadlines this week.",
    attention: "Needs attention", needsScheduling: "Not fully scheduled: {{title}}",
    idleOpen: "Open task waiting: {{title}}", overloaded: "Busy day: {{day}}", allGood: "All set.",
    scheduleInChat: "Schedule in chat", active: "Active tasks", scheduled: "Scheduled", open: "Open", recurring: "Recurring",
    limit: "Daily limit", rest: "Shabbat/holiday", scheduleDraft: "Schedule time for {{task}}", tonight: "eve of {{date}}", unreported: "Past session not reported: {{title}}, {{when}}",
    reportInChat: "Report in chat", reportDraft: "I did the {{task}} session ({{when}})",
  },
  calendar: { week: "Week", day: "Day", today: "Today", legendSession: "Work session", legendRest: "Shabbat & holidays",
    legendBusy: "Classes, work & commitments", legendEvent: "Fixed event" },
  tasks: {
    title: "My tasks", showDone: "Show completed tasks", empty: "No tasks yet. Add them in the chat.",
    scheduled: "Scheduled", open: "Open", recurring: "Recurring", done: "{{done}} of {{total}} done",
    planned: "{{value}} scheduled", deadline: "Deadline", importance: "Importance", postponed: "Postponed {{count}} times",
    assumptions: "Assumptions", statusDone: "Done", hint: "Tasks are changed through the chat.",
    styleExam: "📚 Exam study", styleAssignment: "📝 Assignment",
  },
  chat: {
    newChat: "New chat", history: "Chats", placeholder: "Type a message, e.g. I have an exam in a week and need 10 hours",
    send: "Send", thinking: "DayPilot is thinking...", empty: "How can I help?", deleteChat: "Delete chat",
    confirmDelete: "Delete this chat history? Tasks are kept.",
    approvalTitle: "Proposal waiting for approval", approve: "Approve", reject: "Reject", revise: "Request a change",
    revisePlaceholder: "What should change? e.g. evenings only", sendRevise: "Send request", notFeasible: "Not enough time for everything",
    examples: ["I have an exam in a week and need 20 hours of study", "What do I have tomorrow?", "I need to buy a notebook"],
    missingKey: "OPENAI_API_KEY is missing in .env, so the agent is unavailable.",
  },
  progress: {
    title: "Progress", range: "Last {{count}} days", totalTime: "Work time", sessionsDone: "Sessions done",
    completion: "Plan adherence", completed: "Tasks completed", daily: "Work minutes per day", byTask: "Progress by task",
    doneLabel: "Done", plannedLabel: "Scheduled", remainingLabel: "Remaining", noData: "No progress yet. Report it in the chat.",
  },
  settings: {
    title: "Settings", language: "Language", city: "City (for Shabbat and holiday times)", sessions: "Work sessions",
    minSession: "Shortest session (minutes)", maxSession: "Longest session (minutes)", dailyMax: "Daily limit (minutes)",
    save: "Save", saved: "Saved", rules: "Fixed hours", addRule: "Add", weekday: "Day", from: "From", to: "To",
    kind: "Type", label: "Label", rest: "Shabbat & holidays", restInfo: "Blocked from {{hours}} hours before candle lighting. Chol HaMoed: {{cholHamoed}}.",
    blocked: "blocked", notBlocked: "not blocked", kinds: { active_hours: "Active hours", preferred_study: "Preferred study hours",
      class: "Classes", work: "Work", commitment: "Commitment" },
    quit: "Quit DayPilot", quitInfo: "Stops the background server. To open again: click the icon.",
    quitConfirm: "Stop DayPilot?", stopped: "DayPilot was closed. You can close this tab.",
    quitManual: "The server was started from a CMD window. To stop it: Ctrl+C in that window.",
    replanHint: "Changing hours does not move existing sessions. To update the plan, ask in the chat.",
  },
  weekdays: ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
};

i18n.use(initReactI18next).init({
  resources: { he: { translation: he }, en: { translation: en } },
  lng: "he",
  fallbackLng: "he",
  interpolation: { escapeValue: false },
});

export function applyLanguage(lng: "he" | "en") {
  i18n.changeLanguage(lng);
  document.documentElement.lang = lng;
  document.documentElement.dir = lng === "he" ? "rtl" : "ltr";
}

export default i18n;
