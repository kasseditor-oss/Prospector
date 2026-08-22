"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Icons } from "@/components/Icons";
import { ThemeToggle } from "@/components/ThemeToggle";
import { CadenceStrip, TrendTag } from "@/components/CadenceStrip";
import {
  ApiError,
  api,
  formatDays,
  formatSubscribers,
  scoreColor,
  toCsv,
  type ApiKey,
  type Channel,
  type Quota,
  type SearchFilters,
} from "@/lib/api";

const COUNTRIES: Record<string, string> = {
  BR: "Brasil", US: "Estados Unidos", PT: "Portugal", MX: "México",
  AR: "Argentina", ES: "Espanha", FR: "França", DE: "Alemanha",
  IT: "Itália", GB: "Reino Unido", CA: "Canadá", AU: "Austrália",
};

type Page = "search" | "keys";
type SortKey = "score" | "subscribers" | "title" | "uploads_per_month" | "days_since_last_upload";

export default function Dashboard() {
  const [page, setPage] = useState<Page>("search");
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [quota, setQuota] = useState<Quota | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const notify = useCallback((message: string) => {
    setToast(message);
    window.setTimeout(() => setToast(null), 2800);
  }, []);

  const refreshKeys = useCallback(async () => {
    try {
      const [k, q] = await Promise.all([api.listKeys(), api.quota()]);
      setKeys(k);
      setQuota(q);
    } catch {
      // The backend being down is surfaced by the search panel, not here.
    }
  }, []);

  useEffect(() => {
    void refreshKeys();
  }, [refreshKeys]);

  return (
    <>
      <a className="skip" href="#conteudo">Pular para o conteúdo</a>
      <header className="transport">
        <div className="transport-in">
          <Link className="brand" href="/">
            <Icons.Logo />
            <span>Prospector</span>
          </Link>
          <div className="transport-tools" style={{ marginLeft: "auto" }}>
            <ThemeToggle />
            <Link className="btn btn-ghost btn-sm" href="/">
              Ver o site
            </Link>
          </div>
        </div>
      </header>

      <div className="app">
        <nav className="rail" aria-label="Seções do app">
          <p className="rail-lbl">Trabalho</p>
          <button
            type="button"
            aria-current={page === "search" ? "page" : undefined}
            onClick={() => setPage("search")}
          >
            <Icons.Search size={17} />
            <span>Buscar</span>
          </button>
          <p className="rail-lbl">Configuração</p>
          <button
            type="button"
            aria-current={page === "keys" ? "page" : undefined}
            onClick={() => setPage("keys")}
          >
            <Icons.Key size={17} />
            <span>Chaves de API</span>
            <span className="count">{keys.length}</span>
          </button>
          <div style={{ marginTop: "auto", padding: 10 }}>
            <QuotaMeter quota={quota} />
          </div>
        </nav>

        <div className="main" id="conteudo">
          {page === "search" ? (
            <SearchPanel keys={keys} onSpent={refreshKeys} notify={notify} goKeys={() => setPage("keys")} />
          ) : (
            <KeysPanel keys={keys} onChange={refreshKeys} notify={notify} />
          )}
        </div>
      </div>

      <div id="toasts" aria-live="polite">
        {toast ? (
          <div className="toast">
            <Icons.Check size={15} />
            <span>{toast}</span>
          </div>
        ) : null}
      </div>
    </>
  );
}

function QuotaMeter({ quota }: { quota: Quota | null }) {
  const total = quota?.units_total ?? 0;
  const left = quota?.units_remaining ?? 0;
  const pct = total > 0 ? (left / total) * 100 : 0;
  const cls = pct < 15 ? "meter crit" : pct < 40 ? "meter warn" : "meter";
  return (
    <>
      <div className="quota">
        <div className={cls}>
          <i style={{ width: `${total > 0 ? pct : 0}%` }} />
        </div>
      </div>
      <p style={{ fontSize: 11, color: "var(--ink-3)", marginTop: 6 }}>
        <span className="num">{left.toLocaleString("pt-BR")}</span> unidades hoje
      </p>
    </>
  );
}

/* ------------------------------------------------------------------ search */

function SearchPanel({
  keys,
  onSpent,
  notify,
  goKeys,
}: {
  keys: ApiKey[];
  onSpent: () => void;
  notify: (m: string) => void;
  goKeys: () => void;
}) {
  const [niches, setNiches] = useState<string[]>([]);
  const [draft, setDraft] = useState("");
  const [country, setCountry] = useState("BR");
  const [language, setLanguage] = useState<string>("pt");
  const [minSubs, setMinSubs] = useState(5000);
  const [maxSubs, setMaxSubs] = useState(200000);
  const [activity, setActivity] = useState<0 | 30 | 90 | 365>(90);
  const [emailOnly, setEmailOnly] = useState(false);
  const [deep, setDeep] = useState(false);

  const [estimate, setEstimate] = useState<number | null>(null);
  const [affordable, setAffordable] = useState(true);
  const [running, setRunning] = useState(false);
  const [results, setResults] = useState<Channel[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("score");
  const [sortDir, setSortDir] = useState<-1 | 1>(-1);
  const inputRef = useRef<HTMLInputElement>(null);

  const filters: SearchFilters = useMemo(
    () => ({
      niches,
      country,
      language: language || null,
      min_subscribers: minSubs,
      max_subscribers: maxSubs,
      activity_days: activity,
      email_only: emailOnly,
      deep,
    }),
    [niches, country, language, minSubs, maxSubs, activity, emailOnly, deep],
  );

  // Ask the backend what this search costs. It owns the unit table, so the
  // number on screen can never drift from what actually gets charged.
  useEffect(() => {
    if (niches.length === 0 || minSubs > maxSubs) {
      setEstimate(null);
      return;
    }
    let cancelled = false;
    const timer = window.setTimeout(async () => {
      try {
        const result = await api.estimate(filters);
        if (!cancelled) {
          setEstimate(result.units);
          setAffordable(result.affordable);
        }
      } catch {
        if (!cancelled) setEstimate(null);
      }
    }, 250);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [filters, niches.length, minSubs, maxSubs]);

  function addNiche() {
    const value = draft.trim();
    if (!value || niches.length >= 3 || niches.includes(value)) return;
    setNiches([...niches, value]);
    setDraft("");
  }

  async function run() {
    if (niches.length === 0) {
      notify("Adicione ao menos um nicho");
      inputRef.current?.focus();
      return;
    }
    if (minSubs > maxSubs) {
      notify("O mínimo de inscritos está maior que o máximo");
      return;
    }
    setRunning(true);
    setError(null);
    try {
      const response = await api.search(filters);
      setResults(response.channels);
      notify(
        `${response.channels.length} canais · ${response.units_spent} unidades gastas`,
      );
      onSpent();
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : "Não foi possível falar com a API.";
      setError(message);
      if (err instanceof ApiError && err.status === 428) goKeys();
    } finally {
      setRunning(false);
    }
  }

  const sorted = useMemo(() => {
    if (!results) return null;
    return [...results].sort((a, b) => {
      if (sortKey === "title") {
        return a.title.localeCompare(b.title) * (sortDir === -1 ? -1 : 1);
      }
      if (sortKey === "score") return (a.score.total - b.score.total) * sortDir;
      const av = (a[sortKey] ?? Number.MAX_SAFE_INTEGER) as number;
      const bv = (b[sortKey] ?? Number.MAX_SAFE_INTEGER) as number;
      return (av - bv) * sortDir;
    });
  }, [results, sortKey, sortDir]);

  function sortBy(key: SortKey) {
    if (key === sortKey) setSortDir((d) => (d === 1 ? -1 : 1));
    else {
      setSortKey(key);
      setSortDir(key === "title" ? 1 : -1);
    }
  }

  return (
    <section>
      <div className="page-head">
        <div>
          <h2>Buscar canais</h2>
          <p>Combine até 3 nichos. O custo estimado aparece antes de rodar.</p>
        </div>
      </div>

      {keys.length === 0 ? (
        <div className="banner banner-warn">
          <Icons.Info size={17} />
          <div>
            <strong>Nenhuma chave cadastrada.</strong> A busca precisa de uma API key do
            YouTube para consultar o Google.{" "}
            <button
              type="button"
              className="btn btn-sm btn-quiet"
              style={{ paddingLeft: 0, textDecoration: "underline" }}
              onClick={goKeys}
            >
              Adicionar chave
            </button>
          </div>
        </div>
      ) : null}

      <div className="panel">
        <div className="grid-2" style={{ alignItems: "start" }}>
          <div className="field">
            <label htmlFor="niche">Nichos (até 3)</label>
            <div className="chip-input" onClick={() => inputRef.current?.focus()}>
              {niches.map((n, i) => (
                <span className="chip" key={n}>
                  {n}
                  <button
                    type="button"
                    aria-label={`Remover ${n}`}
                    onClick={(e) => {
                      e.stopPropagation();
                      setNiches(niches.filter((_, index) => index !== i));
                    }}
                  >
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true">
                      <path d="M18 6L6 18M6 6l12 12" />
                    </svg>
                  </button>
                </span>
              ))}
              <input
                id="niche"
                ref={inputRef}
                type="text"
                value={draft}
                disabled={niches.length >= 3}
                placeholder={niches.length >= 3 ? "máximo de 3 nichos" : "ex.: finanças pessoais"}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    addNiche();
                  } else if (e.key === "Backspace" && !draft && niches.length) {
                    setNiches(niches.slice(0, -1));
                  }
                }}
              />
            </div>
            <span className="hint">
              Enter para adicionar. Termos amplos trazem mais canais e gastam mais quota.
            </span>
          </div>

          <div className="grid-2">
            <div className="field">
              <label htmlFor="country">País</label>
              <select id="country" value={country} onChange={(e) => setCountry(e.target.value)}>
                {Object.entries(COUNTRIES).map(([code, name]) => (
                  <option key={code} value={code}>{name}</option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="lang">Idioma</label>
              <select id="lang" value={language} onChange={(e) => setLanguage(e.target.value)}>
                <option value="pt">Português</option>
                <option value="en">Inglês</option>
                <option value="es">Espanhol</option>
                <option value="fr">Francês</option>
                <option value="de">Alemão</option>
                <option value="it">Italiano</option>
                <option value="">Qualquer</option>
              </select>
            </div>
            <div className="field">
              <label htmlFor="min">Inscritos (mín.)</label>
              <input id="min" type="number" min={0} step={1000} value={minSubs}
                onChange={(e) => setMinSubs(Number(e.target.value) || 0)} />
            </div>
            <div className="field">
              <label htmlFor="max">Inscritos (máx.)</label>
              <input id="max" type="number" min={1} step={1000} value={maxSubs}
                onChange={(e) => setMaxSubs(Number(e.target.value) || 1)} />
            </div>
            <div className="field">
              <label htmlFor="activity">Atividade</label>
              <select id="activity" value={activity}
                onChange={(e) => setActivity(Number(e.target.value) as 0 | 30 | 90 | 365)}>
                <option value={30}>Postou nos últimos 30 dias</option>
                <option value={90}>Postou nos últimos 90 dias</option>
                <option value={365}>Postou no último ano</option>
                <option value={0}>Qualquer</option>
              </select>
            </div>
            <div className="field">
              <label htmlFor="mail">E-mail</label>
              <select id="mail" value={emailOnly ? "only" : "all"}
                onChange={(e) => setEmailOnly(e.target.value === "only")}>
                <option value="all">Todos os canais</option>
                <option value="only">Só com e-mail público</option>
              </select>
            </div>
          </div>
        </div>

        <hr className="divider" style={{ margin: "var(--s5) 0" }} />

        <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--s4)", alignItems: "center" }}>
          <label style={{ display: "flex", gap: 9, alignItems: "center", cursor: "pointer", fontSize: 14 }}>
            <input type="checkbox" checked={deep} onChange={(e) => setDeep(e.target.checked)}
              style={{ width: 16, height: 16, accentColor: "var(--signal)" }} />
            <span>
              <strong>Modo intensivo</strong>{" "}
              <span style={{ color: "var(--ink-3)" }}>— varre mais fundo, gasta mais quota</span>
            </span>
          </label>
          <div style={{ marginLeft: "auto", display: "flex", gap: "var(--s4)", alignItems: "center" }}>
            <div style={{ textAlign: "right" }}>
              <p style={{ fontSize: 11, fontWeight: 700, letterSpacing: ".06em", textTransform: "uppercase", color: "var(--ink-3)" }}>
                Custo estimado
              </p>
              <p className="num" style={{ fontSize: 19, fontWeight: 700, color: affordable ? "var(--signal)" : "var(--danger)" }}>
                {estimate === null ? "—" : `${estimate.toLocaleString("pt-BR")} un.`}
              </p>
            </div>
            <button className="btn btn-primary" onClick={run} disabled={running}>
              <Icons.Search size={16} />
              <span>{running ? "Buscando…" : "Buscar canais"}</span>
            </button>
          </div>
        </div>
      </div>

      {error ? (
        <div className="banner" style={{ background: "var(--danger-soft)", color: "var(--danger)" }}>
          <Icons.Info size={17} />
          <div>{error}</div>
        </div>
      ) : null}

      {sorted && sorted.length > 0 ? (
        <>
          <div className="page-head" style={{ marginBottom: "var(--s3)" }}>
            <div>
              <h3 style={{ fontFamily: "var(--display)", fontSize: 17, fontWeight: 700 }}>
                <span className="num">{sorted.length}</span> canais encontrados
              </h3>
            </div>
            <div className="spacer">
              <button className="btn btn-ghost btn-sm"
                onClick={() => {
                  void navigator.clipboard.writeText(toCsv(sorted));
                  notify("CSV copiado");
                }}>
                <Icons.Download size={15} />
                CSV
              </button>
            </div>
          </div>
          <div className="tbl-wrap" tabIndex={0} role="region" aria-label="Resultados da busca">
            <table>
              <thead>
                <tr>
                  <Th label="Canal" k="title" sortKey={sortKey} sortDir={sortDir} onSort={sortBy} />
                  <Th label="Inscritos" k="subscribers" sortKey={sortKey} sortDir={sortDir} onSort={sortBy} />
                  <Th label="Score" k="score" sortKey={sortKey} sortDir={sortDir} onSort={sortBy} />
                  <th scope="col">E-mail</th>
                  <th scope="col">Cadência · 12m</th>
                  <Th label="Ritmo" k="uploads_per_month" sortKey={sortKey} sortDir={sortDir} onSort={sortBy} />
                  <Th label="Último vídeo" k="days_since_last_upload" sortKey={sortKey} sortDir={sortDir} onSort={sortBy} />
                </tr>
              </thead>
              <tbody>
                {sorted.map((c) => (
                  <tr key={c.id}>
                    <td>
                      <div className="ch">
                        <div className="av" style={{ background: "var(--signal-soft)", color: "var(--signal)" }}>
                          {c.title.slice(0, 2).toUpperCase()}
                        </div>
                        <div style={{ minWidth: 0 }}>
                          <div className="ch-name">
                            <a href={c.url} target="_blank" rel="noopener noreferrer">{c.title}</a>
                          </div>
                          <div className="ch-sub">
                            {c.handle ?? "—"} · {COUNTRIES[c.country ?? ""] ?? c.country ?? "—"}
                          </div>
                        </div>
                      </div>
                    </td>
                    <td className="num">
                      {c.subscribers_hidden ? "oculto" : formatSubscribers(c.subscribers)}
                    </td>
                    <td>
                      <div className="score" title={`contato ${c.score.reachability} · ritmo ${c.score.rhythm} · recência ${c.score.recency} · porte ${c.score.fit}`}>
                        <div className="score-track">
                          <i style={{ width: `${c.score.total}%`, background: scoreColor(c.score.total) }} />
                        </div>
                        <b>{c.score.total}</b>
                      </div>
                    </td>
                    <td>
                      {c.email ? (
                        <>
                          <span className="mailcell">{c.email}</span>{" "}
                          <button className="copy-btn" aria-label="Copiar e-mail"
                            onClick={() => {
                              void navigator.clipboard.writeText(c.email as string);
                              notify("E-mail copiado");
                            }}>
                            <Icons.Copy size={13} />
                          </button>
                        </>
                      ) : (
                        <span className="mailcell none">não publicado</span>
                      )}
                    </td>
                    <td>
                      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                        <CadenceStrip cadence={c.cadence} trend={c.cadence_trend} />
                        <TrendTag trend={c.cadence_trend} />
                      </div>
                    </td>
                    <td className="num">{c.uploads_per_month.toFixed(1)}/mês</td>
                    <td>{formatDays(c.days_since_last_upload)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : sorted ? (
        <div className="empty panel">
          <Icons.Search size={42} />
          <h3>Nenhum canal passou nos filtros</h3>
          <p>Tente ampliar a faixa de inscritos, desligar &quot;só com e-mail&quot; ou aceitar atividade mais antiga.</p>
        </div>
      ) : (
        <div className="empty panel">
          <Icons.Search size={42} />
          <h3>Nenhuma busca ainda</h3>
          <p>Escolha um nicho e uma faixa de inscritos acima para começar.</p>
        </div>
      )}
    </section>
  );
}

function Th({
  label, k, sortKey, sortDir, onSort,
}: {
  label: string;
  k: SortKey;
  sortKey: SortKey;
  sortDir: -1 | 1;
  onSort: (k: SortKey) => void;
}) {
  const active = sortKey === k;
  const order = active ? (sortDir === -1 ? "decrescente" : "crescente") : "sem ordenação";
  return (
    <th
      scope="col"
      className="sortable"
      aria-sort={active ? (sortDir === -1 ? "descending" : "ascending") : undefined}
    >
      {/* A real button, not a click handler on the cell: sorting has to be
          reachable by keyboard and announced as an action. */}
      <button type="button" className="th-btn" onClick={() => onSort(k)}>
        {label}
        <span className="arrow" aria-hidden="true">
          {active && sortDir === 1 ? "▲" : "▼"}
        </span>
        <span className="sr">Ordenar por {label}. Atualmente {order}.</span>
      </button>
    </th>
  );
}

/* -------------------------------------------------------------------- keys */

function KeysPanel({
  keys, onChange, notify,
}: {
  keys: ApiKey[];
  onChange: () => void;
  notify: (m: string) => void;
}) {
  const [value, setValue] = useState("");
  const [label, setLabel] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function add() {
    setError(null);
    try {
      await api.addKey(value.trim(), label.trim() || undefined);
      setValue("");
      setLabel("");
      notify("Chave adicionada");
      onChange();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Não foi possível salvar a chave.");
    }
  }

  return (
    <section>
      <div className="page-head">
        <div>
          <h2>Chaves de API</h2>
          <p>Ficam no servidor, nunca no navegador. Adicione mais de uma para o rodízio automático.</p>
        </div>
      </div>

      <div className="panel">
        <p className="panel-title">
          <Icons.Key size={16} />
          <span>Suas chaves</span>
        </p>
        {keys.length === 0 ? (
          <div className="empty" style={{ padding: "var(--s6) 0" }}>
            <Icons.Key size={36} />
            <h3>Nenhuma chave ainda</h3>
            <p>Sem chave a busca não consegue consultar o YouTube.</p>
          </div>
        ) : (
          keys.map((k) => (
            <div className="keyrow" key={k.masked}>
              <div style={{ minWidth: 0, flex: 1 }}>
                <div className="kname">
                  {k.label}
                  {k.disabled_reason ? (
                    <span className="pill st-new" style={{ marginLeft: 6 }}>
                      {k.disabled_reason === "quota" ? "sem quota" : "inválida"}
                    </span>
                  ) : null}
                </div>
                <div className="kval">{k.masked}</div>
              </div>
              <div className="quota">
                <div className="meter">
                  <i style={{ width: `${(k.remaining / 10000) * 100}%` }} />
                </div>
              </div>
              <button
                className="btn btn-quiet btn-icon"
                aria-label={`Remover ${k.label}`}
                onClick={async () => {
                  await api.removeKey(k.masked.slice(-4));
                  notify("Chave removida");
                  onChange();
                }}
              >
                <Icons.Trash size={15} />
              </button>
            </div>
          ))
        )}

        <hr className="divider" style={{ margin: "var(--s5) 0" }} />

        <div className="grid-2" style={{ alignItems: "end" }}>
          <div className="field">
            <label htmlFor="keyval">Nova chave</label>
            <input id="keyval" type="text" value={value} autoComplete="off"
              placeholder="AIzaSy..." onChange={(e) => setValue(e.target.value)} />
          </div>
          <div style={{ display: "flex", gap: "var(--s3)", alignItems: "end" }}>
            <div className="field" style={{ flex: 1 }}>
              <label htmlFor="keylabel">Apelido</label>
              <input id="keylabel" type="text" value={label}
                placeholder="Projeto principal" onChange={(e) => setLabel(e.target.value)} />
            </div>
            <button className="btn btn-primary" onClick={add} disabled={value.trim().length < 20}>
              <Icons.Plus size={16} />
              <span>Adicionar</span>
            </button>
          </div>
        </div>
        {error ? (
          <p style={{ color: "var(--danger)", fontSize: 13, marginTop: "var(--s3)" }}>{error}</p>
        ) : null}
      </div>

      <div className="panel">
        <p className="panel-title">
          <Icons.Doc size={16} />
          <span>Como gerar sua chave (2 minutos, sem cartão)</span>
        </p>
        <ol style={{ margin: 0, paddingLeft: 20, display: "grid", gap: 10, fontSize: 14, color: "var(--ink-2)" }}>
          <li>Entre no <strong>console.cloud.google.com</strong> com qualquer conta Google e crie um projeto novo.</li>
          <li>Vá em <strong>APIs e serviços → Biblioteca</strong>, procure por <strong>YouTube Data API v3</strong> e clique em Ativar.</li>
          <li>Vá em <strong>Credenciais → Criar credenciais → Chave de API</strong> e copie o código gerado.</li>
          <li>Opcional, mas recomendado: em <strong>Restringir chave</strong>, limite o uso à YouTube Data API v3.</li>
          <li>Cole aqui. Cada projeto rende 10.000 unidades por dia, e a contagem zera à meia-noite no horário do Pacífico.</li>
        </ol>
      </div>
    </section>
  );
}
