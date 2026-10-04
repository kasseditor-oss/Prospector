"use client";

/**
 * Writing to the channels that published an address.
 *
 * Three blocks, in the order the work happens: the mailbox the messages leave
 * from, the message itself, and who gets it. The batch is paced from here, one
 * request per lead, so it can be stopped between any two messages and a
 * failure names the one channel it happened on. The daily ceiling is not
 * enforced here — the backend holds it, so a bug in this loop cannot exceed it.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Icons } from "@/components/Icons";
import {
  ApiError,
  api,
  formatSubscribers,
  renderTemplate,
  type Lead,
  type MailState,
} from "@/lib/api";

/** Seconds between two messages. A burst of identical mail is what a spam
 *  filter is built to notice, so there is no "as fast as possible". */
const PACE_OPTIONS = [30, 60, 120, 300];

type LogLine = { title: string; ok: boolean; note: string };

export function MailPanel({
  notify,
  goSearch,
}: {
  notify: (m: string) => void;
  goSearch: () => void;
}) {
  const [state, setState] = useState<MailState | null>(null);
  const [leads, setLeads] = useState<Lead[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  // -- account form
  const [editing, setEditing] = useState(false);
  const [user, setUser] = useState("");
  const [password, setPassword] = useState("");
  const [fromName, setFromName] = useState("");
  const [host, setHost] = useState("");
  const [port, setPort] = useState(0);
  const [limit, setLimit] = useState(40);
  const [savingAccount, setSavingAccount] = useState(false);
  const [testing, setTesting] = useState(false);

  // -- message
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");

  // -- batch
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [pace, setPace] = useState(60);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState({ done: 0, of: 0, wait: 0 });
  const [log, setLog] = useState<LogLine[]>([]);
  const stop = useRef(false);

  const adopt = useCallback((next: MailState) => {
    setState(next);
    setUser(next.user);
    setFromName(next.from_name);
    setHost(next.host);
    setPort(next.port);
    setLimit(next.daily_limit);
    setPassword("");
  }, []);

  useEffect(() => {
    api
      .mail()
      .then((next) => {
        adopt(next);
        setSubject(next.subject);
        setBody(next.body);
      })
      .catch(() => setError("Não foi possível ler a configuração de e-mail."));
    api
      .listLeads({ withEmail: true, sort: "score", limit: 2000 })
      .then((data) => setLeads(data.leads))
      .catch(() => setError("Não foi possível ler a base."));
  }, [adopt]);

  // Leaving the screen mid-batch stops it: a loop that keeps sending with
  // nothing on screen to show it is the one nobody can stop.
  useEffect(() => () => { stop.current = true; }, []);

  // Who can still be written to: an address, and no message from the app yet.
  // A lead marked by hand as contacted is left out too — the user already
  // wrote to it some other way.
  const pending = useMemo(
    () => (leads ?? []).filter((l) => l.email && !l.emailed_at && l.status === "novo"),
    [leads],
  );
  const alreadySent = (leads ?? []).filter((l) => l.emailed_at).length;
  const remaining = state?.remaining_today ?? 0;
  const chosen = pending.filter((l) => picked.has(l.id));
  const dirty = state !== null && (subject !== state.subject || body !== state.body);
  const sample = chosen[0] ?? pending[0] ?? null;

  function pickFirst(count: number) {
    setPicked(new Set(pending.slice(0, count).map((l) => l.id)));
  }

  function toggle(id: string) {
    setPicked((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function saveAccount() {
    setSavingAccount(true);
    setError(null);
    try {
      adopt(
        await api.saveMailAccount({
          user: user.trim(),
          password,
          host: host.trim(),
          port,
          from_name: fromName.trim(),
          daily_limit: limit,
        }),
      );
      setEditing(false);
      notify("Conta de e-mail salva");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Não foi possível salvar.");
    } finally {
      setSavingAccount(false);
    }
  }

  async function removeAccount() {
    if (!window.confirm("Remover a conta de e-mail deste computador?")) return;
    await api.removeMailAccount();
    adopt(await api.mail());
    notify("Conta removida");
  }

  /** Save the message if it changed. False when it could not be saved. */
  async function saveTemplate(): Promise<boolean> {
    if (!subject.trim() || !body.trim()) {
      setError("A mensagem precisa de assunto e de texto.");
      return false;
    }
    if (!dirty) return true;
    try {
      setState(await api.saveMailTemplate(subject, body));
      return true;
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Não foi possível salvar a mensagem.");
      return false;
    }
  }

  async function sendTest() {
    setTesting(true);
    setError(null);
    try {
      if (!(await saveTemplate())) return;
      await api.sendMailTest();
      notify(`Teste enviado para ${state?.user}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Não foi possível enviar o teste.");
    } finally {
      setTesting(false);
    }
  }

  async function run() {
    const batch = chosen;
    if (batch.length === 0) return;
    if (
      !window.confirm(
        `Enviar a mensagem para ${batch.length} ${batch.length === 1 ? "canal" : "canais"}, ` +
          `um a cada ${pace} segundos? Depois de enviado não tem volta.`,
      )
    ) {
      return;
    }
    setError(null);
    if (!(await saveTemplate())) return;

    stop.current = false;
    setRunning(true);
    setLog([]);
    setProgress({ done: 0, of: batch.length, wait: 0 });
    let delivered = 0;

    for (let i = 0; i < batch.length && !stop.current; i += 1) {
      const lead = batch[i];
      try {
        const sent = await api.sendMail(lead.id);
        delivered += 1;
        const now = new Date().toISOString();
        setLeads((rows) =>
          rows
            ? rows.map((r) =>
                r.id === lead.id ? { ...r, emailed_at: now, status: "contatado" } : r,
              )
            : rows,
        );
        setState((s) =>
          s ? { ...s, sent_today: sent.sent_today, remaining_today: sent.remaining_today } : s,
        );
        setLog((lines) => [...lines, { title: lead.title, ok: true, note: sent.to }]);
      } catch (err) {
        const message = err instanceof ApiError ? err.message : "Sem resposta do aplicativo.";
        setLog((lines) => [...lines, { title: lead.title, ok: false, note: message }]);
        // One bad address is a reason to skip a lead. Anything else — the
        // account, the limit, the connection — would fail the same way for
        // every lead left, so the batch ends here.
        const skippable = err instanceof ApiError && [404, 409, 422].includes(err.status);
        if (!skippable) {
          setError(message);
          break;
        }
      }
      setProgress({ done: i + 1, of: batch.length, wait: 0 });

      if (i < batch.length - 1) {
        for (let left = pace; left > 0 && !stop.current; left -= 1) {
          setProgress({ done: i + 1, of: batch.length, wait: left });
          await new Promise((resolve) => window.setTimeout(resolve, 1000));
        }
      }
    }

    setRunning(false);
    setPicked(new Set());
    notify(
      delivered === 1 ? "1 e-mail enviado" : `${delivered} e-mails enviados`,
    );
  }

  const showForm = state !== null && (!state.configured || editing);

  return (
    <section>
      <div className="page-head">
        <div>
          <h2>Enviar e-mails</h2>
          <p>
            Escreve para os canais da base que publicaram um endereço. Sai da sua
            própria conta, uma mensagem por canal.
          </p>
        </div>
      </div>

      {error ? (
        <div className="banner" style={{ background: "var(--danger-soft)", color: "var(--danger)" }}>
          <Icons.Info size={17} />
          <div>{error}</div>
        </div>
      ) : null}

      {/* ------------------------------------------------------------ conta */}
      <div className="panel">
        <p className="panel-title">
          <Icons.Key size={16} />
          <span>Conta de envio</span>
        </p>

        {state?.configured && !editing ? (
          <div className="keyrow">
            <span className="credkind" title="Conta de e-mail">
              <Icons.Mail size={15} />
            </span>
            <div style={{ minWidth: 0, flex: 1 }}>
              <div className="kname">{state.from_name || state.user}</div>
              <div className="kval">
                {state.user} · {state.host}:{state.port}
              </div>
            </div>
            <div className="quota">
              <span className="num">
                {state.sent_today} de {state.daily_limit} em 24h
              </span>
              <div className="meter">
                <i style={{ width: `${Math.min(100, (state.sent_today / state.daily_limit) * 100)}%` }} />
              </div>
            </div>
            <button className="btn btn-ghost btn-sm" onClick={() => setEditing(true)} disabled={running}>
              Alterar
            </button>
            <button
              className="btn btn-quiet btn-icon"
              aria-label="Remover a conta de e-mail"
              onClick={() => void removeAccount()}
              disabled={running}
            >
              <Icons.Trash size={15} />
            </button>
          </div>
        ) : null}

        {showForm ? (
          <>
            <div className="grid-2">
              <div className="field">
                <label htmlFor="mail-user">Seu e-mail</label>
                <input
                  id="mail-user"
                  type="email"
                  value={user}
                  autoComplete="off"
                  placeholder="voce@gmail.com"
                  onChange={(e) => setUser(e.target.value)}
                />
              </div>
              <div className="field">
                <label htmlFor="mail-pass">Senha de app</label>
                <input
                  id="mail-pass"
                  type="password"
                  value={password}
                  autoComplete="new-password"
                  placeholder={state?.configured ? "deixe vazio para manter a atual" : "abcd efgh ijkl mnop"}
                  onChange={(e) => setPassword(e.target.value)}
                />
                <span className="hint">
                  Não é a senha da conta. Fica cifrada neste computador, igual às chaves de API.
                </span>
              </div>
              <div className="field">
                <label htmlFor="mail-name">Nome que aparece para quem recebe</label>
                <input
                  id="mail-name"
                  type="text"
                  value={fromName}
                  autoComplete="off"
                  placeholder="Seu nome"
                  onChange={(e) => setFromName(e.target.value)}
                />
              </div>
              <div className="field">
                <label htmlFor="mail-limit">Limite em 24 horas</label>
                <input
                  id="mail-limit"
                  type="number"
                  min={1}
                  max={300}
                  value={limit}
                  onChange={(e) => setLimit(Math.max(1, Math.min(300, Number(e.target.value) || 1)))}
                />
                <span className="hint">
                  Conta nova: comece com 20 a 40. Muito envio igual de uma vez cai em spam.
                </span>
              </div>
            </div>

            <details className="credmore">
              <summary>Servidor (só para provedor que não seja Gmail, Outlook, Yahoo, iCloud ou Zoho)</summary>
              <div className="grid-2" style={{ marginTop: "var(--s4)" }}>
                <div className="field">
                  <label htmlFor="mail-host">Servidor SMTP</label>
                  <input
                    id="mail-host"
                    type="text"
                    value={host}
                    autoComplete="off"
                    placeholder="deixe vazio para descobrir pelo e-mail"
                    onChange={(e) => setHost(e.target.value)}
                  />
                </div>
                <div className="field">
                  <label htmlFor="mail-port">Porta</label>
                  <input
                    id="mail-port"
                    type="number"
                    min={0}
                    max={65535}
                    value={port || ""}
                    placeholder="465 ou 587"
                    onChange={(e) => setPort(Number(e.target.value) || 0)}
                  />
                </div>
              </div>
            </details>

            <div className="mail-run">
              <button
                className="btn btn-primary"
                onClick={() => void saveAccount()}
                disabled={savingAccount || !user.includes("@") || (!password && !state?.configured)}
              >
                <Icons.Check size={16} />
                <span>{savingAccount ? "Salvando…" : "Salvar conta"}</span>
              </button>
              {editing ? (
                <button
                  className="btn btn-ghost"
                  onClick={() => {
                    if (state) adopt(state);
                    setEditing(false);
                  }}
                >
                  Cancelar
                </button>
              ) : null}
            </div>
          </>
        ) : null}
      </div>

      {state !== null && !state.configured ? (
        <div className="panel">
          <p className="panel-title">
            <Icons.Doc size={16} />
            <span>Como gerar a senha de app no Gmail (2 minutos)</span>
          </p>
          <ol style={{ margin: 0, paddingLeft: 20, display: "grid", gap: 10, fontSize: 14, color: "var(--ink-2)" }}>
            <li>Entre em <strong>myaccount.google.com → Segurança</strong> e ative a <strong>verificação em duas etapas</strong>. Sem ela o Google não libera senha de app.</li>
            <li>Abra <strong>myaccount.google.com/apppasswords</strong>, dê um nome (por exemplo, Prospector) e clique em Criar.</li>
            <li>Copie as 16 letras que aparecem e cole no campo <strong>Senha de app</strong> acima.</li>
            <li>No Outlook e no Yahoo o caminho é o mesmo: segurança da conta → senha de app.</li>
          </ol>
        </div>
      ) : null}

      {/* --------------------------------------------------------- mensagem */}
      <div className="panel">
        <p className="panel-title">
          <Icons.Doc size={16} />
          <span>Mensagem</span>
        </p>
        <div className="field field-lead">
          <label htmlFor="mail-subject">Assunto</label>
          <input
            id="mail-subject"
            type="text"
            value={subject}
            maxLength={200}
            disabled={running}
            onChange={(e) => setSubject(e.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="mail-body">Texto</label>
          <textarea
            id="mail-body"
            className="mail-body"
            value={body}
            maxLength={10000}
            disabled={running}
            onChange={(e) => setBody(e.target.value)}
          />
          <span className="hint">
            Trocados por canal:{" "}
            {(state?.placeholders ?? []).map((name) => `{${name}}`).join("  ")}. Mantenha o
            último parágrafo: dizer de onde veio o endereço e como parar de receber é o que a
            LGPD pede.
          </span>
        </div>

        {sample ? (
          <div className="mail-preview">
            <b>
              Como {sample.title} vai receber — {renderTemplate(subject, sample)}
            </b>
            {renderTemplate(body, sample)}
          </div>
        ) : null}

        <div className="mail-run">
          <button
            className="btn btn-ghost"
            onClick={() => void saveTemplate().then((ok) => ok && notify("Mensagem salva"))}
            disabled={!dirty || running}
          >
            <Icons.Check size={16} />
            <span>Salvar mensagem</span>
          </button>
          <button
            className="btn btn-ghost"
            onClick={() => void sendTest()}
            disabled={!state?.configured || testing || running}
          >
            <Icons.Mail size={16} />
            <span>{testing ? "Enviando…" : "Enviar um teste para mim"}</span>
          </button>
        </div>
      </div>

      {/* ----------------------------------------------------- destinatários */}
      <div className="panel">
        <p className="panel-title">
          <Icons.Board size={16} />
          <span>Destinatários</span>
        </p>

        {leads === null ? (
          <p style={{ color: "var(--ink-3)", fontSize: 14 }}>Carregando a base…</p>
        ) : pending.length === 0 ? (
          <div className="empty" style={{ padding: "var(--s5) 0" }}>
            <Icons.Mail size={36} />
            <h3>Ninguém na fila</h3>
            <p>
              {alreadySent > 0
                ? `Os ${alreadySent} canais com e-mail da base já receberam a sua mensagem.`
                : "Nenhum canal da base publicou um e-mail ainda."}{" "}
              Uma busca com o filtro &quot;só com e-mail público&quot; traz mais.
            </p>
            <button className="btn btn-sm" onClick={goSearch}>
              <Icons.Search size={15} />
              Buscar canais
            </button>
          </div>
        ) : (
          <>
            <p style={{ fontSize: 14, color: "var(--ink-2)", marginBottom: "var(--s3)" }}>
              <b className="num">{pending.length}</b> canais com e-mail ainda não contatados
              {alreadySent > 0 ? `, ${alreadySent} já receberam` : ""}. Ordenados pelo score.
            </p>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: "var(--s3)" }}>
              <button
                className="btn btn-ghost btn-sm"
                disabled={running || remaining === 0}
                onClick={() => pickFirst(Math.min(remaining, pending.length))}
              >
                Marcar os {Math.min(remaining, pending.length)} melhores
              </button>
              <button
                className="btn btn-ghost btn-sm"
                disabled={running || picked.size === 0}
                onClick={() => setPicked(new Set())}
              >
                Desmarcar todos
              </button>
            </div>

            <div className="tbl-wrap mail-list" tabIndex={0} role="region" aria-label="Canais na fila de e-mail">
              <table>
                <thead>
                  <tr>
                    <th scope="col"><span className="sr">Enviar</span></th>
                    <th scope="col">Canal</th>
                    <th scope="col">E-mail</th>
                    <th scope="col">Nicho</th>
                    <th scope="col">Inscritos</th>
                    <th scope="col">Score</th>
                  </tr>
                </thead>
                <tbody>
                  {pending.map((lead) => (
                    <tr key={lead.id}>
                      <td>
                        <input
                          type="checkbox"
                          aria-label={`Enviar para ${lead.title}`}
                          checked={picked.has(lead.id)}
                          disabled={running}
                          onChange={() => toggle(lead.id)}
                        />
                      </td>
                      <td>{lead.title}</td>
                      <td><span className="mailcell">{lead.email}</span></td>
                      <td>{lead.niche}</td>
                      <td className="num">
                        {lead.subscribers_hidden ? "oculto" : formatSubscribers(lead.subscribers)}
                      </td>
                      <td className="num">{lead.score.total}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="mail-run">
              <div className="field" style={{ minWidth: 190 }}>
                <label htmlFor="mail-pace">Intervalo entre envios</label>
                <select
                  id="mail-pace"
                  value={pace}
                  disabled={running}
                  onChange={(e) => setPace(Number(e.target.value))}
                >
                  {PACE_OPTIONS.map((seconds) => (
                    <option key={seconds} value={seconds}>
                      {seconds < 60 ? `${seconds} segundos` : `${seconds / 60} min`}
                    </option>
                  ))}
                </select>
              </div>
              <div style={{ marginLeft: "auto", display: "flex", gap: "var(--s3)", alignItems: "center" }}>
                {running ? (
                  <>
                    <span className="num" style={{ fontSize: 14 }} aria-live="polite">
                      {progress.done} de {progress.of}
                      {progress.wait > 0 ? ` · próximo em ${progress.wait}s` : " · enviando…"}
                    </span>
                    <button className="btn btn-ghost" onClick={() => { stop.current = true; }}>
                      Parar
                    </button>
                  </>
                ) : (
                  <button
                    className="btn btn-primary"
                    onClick={() => void run()}
                    disabled={!state?.configured || chosen.length === 0 || chosen.length > remaining}
                  >
                    <Icons.Mail size={16} />
                    <span>
                      Enviar para {chosen.length} {chosen.length === 1 ? "canal" : "canais"}
                    </span>
                  </button>
                )}
              </div>
            </div>

            <p className="hint" style={{ marginTop: "var(--s3)", fontSize: 12, color: "var(--ink-3)" }}>
              {!state?.configured
                ? "Configure a conta de envio acima para liberar o botão."
                : chosen.length > remaining
                  ? `Você marcou ${chosen.length}, mas só restam ${remaining} envios nas próximas 24 horas.`
                  : `Restam ${remaining} envios nas próximas 24 horas. Mantenha esta tela aberta: sair dela interrompe o envio. Cada canal enviado passa para Contatado na base.`}
            </p>
          </>
        )}

        {log.length > 0 ? (
          <div className="mail-log" aria-live="polite">
            {log.map((line, index) => (
              <div key={index} className={line.ok ? undefined : "fail"}>
                {line.ok ? "Enviado" : "Falhou"} · {line.title} · {line.note}
              </div>
            ))}
          </div>
        ) : null}
      </div>
    </section>
  );
}
