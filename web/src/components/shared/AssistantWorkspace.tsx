"use client";

// Sidebar "AI assistant" page for doctors and nurses. Conversations are stored on the server (GET/POST
// /ai/conversations). Typing @ mentions a patient: from then on the conversation answers from that patient's record
// (cited, audited) until another patient is mentioned or the patient is removed. Without a patient it answers
// general questions. `?patient=p-0001` (from a patient page) starts a new chat about that patient.
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useT } from "@/i18n/I18nProvider";
import {
  createConversation,
  deleteConversation,
  getConversation,
  getMyPatients,
  listConversations,
  sendConversationMessage,
  uploadReport,
} from "@/lib/api";
import { dayLabel, tunisTime } from "@/lib/time";
import type { Conversation, ConversationMessage, PatientRef, PatientSummary } from "@/lib/types";
import styles from "./AssistantWorkspace.module.css";

const MENTION = /@([^\s@]*)$/;
const fold = (s: string) => s.normalize("NFKD").replace(/\p{M}/gu, "").toLowerCase();

export function AssistantWorkspace({ role }: { role: "doctor" | "nurse" }) {
  const { t, lang } = useT();
  const params = useSearchParams();
  const [list, setList] = useState<Conversation[] | null>(null);
  const [listError, setListError] = useState(false);
  const [active, setActive] = useState<Conversation | null>(null);
  const [msgs, setMsgs] = useState<ConversationMessage[]>([]);
  const [patients, setPatients] = useState<PatientSummary[]>([]);
  /** The patient the next message is about: a fresh @mention, the conversation's patient, or none. */
  const [patient, setPatient] = useState<PatientRef | null>(null);
  const [mentioned, setMentioned] = useState(false);
  const [cleared, setCleared] = useState(false);
  const [input, setInput] = useState("");
  const [query, setQuery] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const [attach, setAttach] = useState<{ tone: "ok" | "warn" | "busy"; text: string } | null>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    listConversations().then(setList).catch(() => setListError(true));
    getMyPatients().then(setPatients).catch(() => setPatients([]));
  }, []);

  // ?patient=p-0001 from a patient page: a new chat about that patient.
  const wanted = params.get("patient");
  useEffect(() => {
    if (!wanted || !patients.length) return;
    const p = patients.find((x) => x.id === wanted);
    if (p) startNew({ id: p.id, name: `${p.first_name} ${p.last_name}` });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wanted, patients]);

  useEffect(() => {
    requestAnimationFrame(() => listRef.current?.scrollTo({ top: listRef.current.scrollHeight }));
  }, [msgs, busy]);

  const matches = useMemo(() => {
    if (query === null) return [];
    const q = fold(query);
    return patients
      .filter((p) => fold(`${p.first_name} ${p.last_name} ${p.bed ?? ""}`).includes(q))
      .slice(0, 6);
  }, [query, patients]);

  function startNew(p: PatientRef | null = null) {
    setActive(null);
    setMsgs([]);
    setPatient(p);
    setMentioned(!!p);
    setCleared(false);
    setError(false);
    inputRef.current?.focus();
  }

  async function open(c: Conversation) {
    if (busy) return;
    setError(false);
    try {
      const full = await getConversation(c.id);
      setActive(full);
      setMsgs(full.messages ?? []);
      setPatient(full.patient ?? null);
      setMentioned(false);
      setCleared(false);
    } catch {
      setError(true);
    }
  }

  async function remove(c: Conversation) {
    try {
      await deleteConversation(c.id);
      setList((l) => (l ?? []).filter((x) => x.id !== c.id));
      if (active?.id === c.id) startNew();
    } catch {
      setError(true);
    }
  }

  function onInput(value: string, caret: number) {
    setInput(value);
    const m = MENTION.exec(value.slice(0, caret));
    setQuery(m ? m[1] : null);
  }

  function pick(p: PatientSummary) {
    const el = inputRef.current;
    const caret = el?.selectionStart ?? input.length;
    const before = input.slice(0, caret).replace(MENTION, `@${p.first_name} ${p.last_name} `);
    setInput(before + input.slice(caret));
    setPatient({ id: p.id, name: `${p.first_name} ${p.last_name}` });
    setMentioned(true);
    setCleared(false);
    setQuery(null);
    el?.focus();
  }

  /** The + button (doctor): attach a report to the patient the conversation is about. */
  function pickFile() {
    if (!patient || cleared) {
      setAttach({ tone: "warn", text: t("shared.asstAttachNeedPatient") });
      inputRef.current?.focus();
      return;
    }
    fileRef.current?.click();
  }

  async function attachFile(file: File) {
    const target = patient && !cleared ? patient : null;
    if (!target) return;
    setAttach({ tone: "busy", text: t("shared.asstAttaching", { file: file.name }) });
    try {
      await uploadReport(target.id, file, file.name.replace(/\.[^.]+$/, "").slice(0, 120));
      setAttach({ tone: "ok", text: t("shared.asstAttached", { file: file.name, name: target.name }) });
    } catch {
      setAttach({ tone: "warn", text: t("shared.reportError") });
    } finally {
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function send() {
    const q = input.trim();
    if (!q || busy) return;
    setBusy(true);
    setError(false);
    setInput("");
    setQuery(null);
    const pending: ConversationMessage = { id: `local-${Date.now()}`, role: "user", text: q, patient, created_at: new Date().toISOString() };
    setMsgs((m) => [...m, pending]);
    try {
      const conv = active ?? (await createConversation());
      const r = await sendConversationMessage(conv.id, q, {
        patientId: mentioned && patient ? patient.id : undefined,
        clearPatient: cleared,
        lang,
      });
      setActive({ ...conv, ...r.conversation });
      setMsgs((m) => [...m, r.message]);
      setPatient(r.message.patient);
      setMentioned(false);
      setCleared(false);
      setList((l) => [r.conversation, ...(l ?? []).filter((x) => x.id !== r.conversation.id)]);
    } catch {
      setMsgs((m) => m.filter((x) => x.id !== pending.id));
      setInput(q);
      setError(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={styles.root}>
      <aside className={styles.side} aria-label={t("shared.asstHistory")}>
        <button type="button" className={styles.newBtn} onClick={() => startNew()} disabled={busy}>
          + {t("shared.asstNew")}
        </button>
        <span className={styles.sideHead}>{t("shared.asstHistory")}</span>
        {listError ? <span className={styles.muted}>{t("shared.asstLoadError")}</span> : null}
        {list && list.length === 0 ? <span className={styles.muted}>{t("shared.asstEmptyList")}</span> : null}
        <nav className={styles.convs}>
          {(list ?? []).map((c) => (
            <div key={c.id} className={`${styles.conv} ${active?.id === c.id ? styles.convOn : ""}`}>
              <button type="button" className={styles.convBtn} onClick={() => open(c)}>
                <span dir="auto" className={styles.convTitle}>{c.title || t("shared.asstUntitled")}</span>
                <span className={styles.convDate}>
                  {dayLabel(c.updated_at, undefined, lang)} {tunisTime(c.updated_at)}
                </span>
              </button>
              <button type="button" className={styles.del} aria-label={t("shared.asstDelete")} title={t("shared.asstDelete")} onClick={() => remove(c)}>
                ×
              </button>
            </div>
          ))}
        </nav>
      </aside>

      <section className={styles.main} aria-label={t("shared.navAssistant")}>
        <header className={styles.head}>
          <h1 className={styles.h1}>{t("shared.navAssistant")}</h1>
          <span className={styles.badge}>{t("shared.chatBadge")}</span>
          {patient && !cleared ? (
            <span className={styles.chip}>
              <span dir="auto">{t("shared.asstAbout", { name: patient.name })}</span>
              <button type="button" aria-label={t("shared.asstClearPatient")} title={t("shared.asstClearPatient")} onClick={() => {
                setCleared(true);
                setMentioned(false);
              }}>
                ×
              </button>
            </span>
          ) : (
            <span className={`${styles.chip} ${styles.chipGeneral}`}>{t("shared.asstGeneral")}</span>
          )}
        </header>

        <div ref={listRef} className={styles.thread} aria-live="polite">
          {msgs.length === 0 ? (
            <p className={styles.welcome}>{t(role === "doctor" ? "shared.asstWelcomeDoctor" : "shared.asstWelcomeNurse")}</p>
          ) : null}
          {msgs.map((m) =>
            m.role === "user" ? (
              <div key={m.id} className={styles.mine}>
                {m.patient ? <span className={styles.tag} dir="auto">@{m.patient.name}</span> : null}
                <div dir="auto" className={`${styles.bubble} ${styles.me}`}>{m.text}</div>
              </div>
            ) : (
              <Reply key={m.id} m={m} />
            ),
          )}
          {busy ? <div className={`${styles.bubble} ${styles.bot} ${styles.busy}`}>{t("shared.chatThinking")}</div> : null}
          {error ? <span role="alert" className={styles.warn}>{t("shared.chatError")}</span> : null}
        </div>
        {attach ? (
          <span role="status" dir="auto" className={attach.tone === "warn" ? styles.warn : styles.attachNote}>
            {attach.text}
          </span>
        ) : null}

        <form
          className={styles.composer}
          onSubmit={(e) => {
            e.preventDefault();
            send();
          }}
        >
          {query !== null ? (
            <div className={styles.mentions} role="listbox">
              {matches.length === 0 ? <span className={styles.muted}>{t("shared.asstNoMatch")}</span> : null}
              {matches.map((p) => (
                <button key={p.id} type="button" role="option" aria-selected="false" className={styles.mention} onMouseDown={(e) => {
                  e.preventDefault();
                  pick(p);
                }}>
                  <b dir="auto">{p.first_name} {p.last_name}</b>
                  <span>{[p.bed, p.age].filter((x) => x != null).join(" · ")}</span>
                </button>
              ))}
            </div>
          ) : null}
          {role === "doctor" ? (
            <>
              <button type="button" className={styles.plus} onClick={pickFile} disabled={attach?.tone === "busy"}
                aria-label={t("shared.asstAttach")} title={t("shared.asstAttach")}>
                +
              </button>
              <input ref={fileRef} type="file" hidden
                accept=".pdf,.jpg,.jpeg,.png,.txt,application/pdf,image/jpeg,image/png,text/plain"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) void attachFile(f);
                }} />
            </>
          ) : null}
          <textarea
            ref={inputRef}
            rows={2}
            dir="auto"
            value={input}
            maxLength={2000}
            placeholder={t("shared.asstPlaceholder")}
            aria-label={t("shared.asstPlaceholder")}
            className={styles.input}
            onChange={(e) => onInput(e.target.value, e.target.selectionStart ?? e.target.value.length)}
            onKeyDown={(e) => {
              if (query !== null && matches.length && (e.key === "Enter" || e.key === "Tab")) {
                e.preventDefault();
                pick(matches[0]);
                return;
              }
              if (e.key === "Escape") setQuery(null);
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
          />
          <button type="submit" className={styles.send} disabled={busy || !input.trim()}>
            {t("shared.chatSend")}
          </button>
        </form>
      </section>
    </div>
  );
}

/** **bold** inside a line. */
function inline(text: string) {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**") ? <strong key={i}>{part.slice(2, -2)}</strong> : part,
  );
}

/** The assistant's plain-text answer: "- " bullets, **bold**, and table rows (older answers) as plain lines. */
function RichText({ text }: { text: string }) {
  const blocks: ReactNode[] = [];
  let items: string[] = [];
  const flush = () => {
    if (items.length) blocks.push(<ul key={`ul-${blocks.length}`} className={styles.ul}>{items.map((x, i) => <li key={i}>{inline(x)}</li>)}</ul>);
    items = [];
  };
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (/^\|?\s*:?-{3,}/.test(line)) continue; // markdown table separator
    const bullet = /^([-*•]|\d+[.)])\s+(.*)$/.exec(line);
    if (bullet) {
      items.push(bullet[2]);
      continue;
    }
    flush();
    if (!line) continue;
    const cells = line.startsWith("|") ? line.split("|").map((c) => c.trim()).filter(Boolean).join(" · ") : line;
    blocks.push(<p key={`p-${blocks.length}`} className={styles.p}>{inline(cells.replace(/^#+\s*/, ""))}</p>);
  }
  flush();
  return <>{blocks}</>;
}

function Reply({ m }: { m: ConversationMessage }) {
  const { t } = useT();
  return (
    <div className={styles.answer}>
      <div dir="auto" className={`${styles.bubble} ${styles.bot} ${styles.rich}`}><RichText text={m.text} /></div>
      {m.source === "rules" && m.citations?.length ? <span className={styles.muted}>{t("shared.chatOffline")}</span> : null}
      {m.unverified?.length ? (
        <span role="note" className={styles.warn}>{t("shared.chatUnverified", { values: m.unverified.join(", ") })}</span>
      ) : null}
      {m.citations?.length ? (
        <details className={styles.sources}>
          <summary>
            {t("shared.chatSources")} ({m.citations.length})
          </summary>
          {m.citations.map((c, i) => (
            <div key={`${c.source_id}-${i}`} className={styles.cite}>
              <b dir="auto">
                {c.n ? `[${c.n}] ` : ""}
                {c.title}
              </b>
              <span dir="auto">{c.text}</span>
            </div>
          ))}
        </details>
      ) : null}
    </div>
  );
}

export default AssistantWorkspace;
