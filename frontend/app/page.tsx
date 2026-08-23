"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Icons } from "@/components/Icons";
import { ThemeToggle } from "@/components/ThemeToggle";
import { ChannelTable } from "@/components/ChannelTable";
import {
  ApiError,
  COUNTRIES,
  api,
  type ApiKey,
  type Channel,
  type Lead,
  type Quota,
  type SearchFilters,
} from "@/lib/api";

type Page = "search" | "saved" | "keys";

export default function Dashboard() {
  const [page, setPage] = useState<Page>("search");
  const [savedCount, setSavedCount] = useState(0);
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
    // The rail shows the base size, so it has to be known before the base is
    // ever opened. limit=1 keeps this to a count, not a full download.
    api
      .listLeads({ limit: 1 })
      .then((data) => setSavedCount(data.total))
      .catch(() => {});
  }, [refreshKeys]);

  return (
    <>
      <a className="skip" href="#conteudo">Pular para o conteúdo</a>
      <header className="transport">
        <div className="transport-in">
          <div className="brand">
            <Icons.Logo />
            <span>Prospector</span>
          </div>
          <div className="transport-tools" style={{ marginLeft: "auto" }}>
            <ThemeToggle />
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
          <button
            type="button"
            aria-current={page === "saved" ? "page" : undefined}
            onClick={() => setPage("saved")}
          >
            <Icons.Board size={17} />
            <span>Base</span>
            <span className="count">{savedCount}</span>
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
          <div className="rail-status">
            <QuotaMeter quota={quota} goKeys={() => setPage("keys")} />
          </div>
        </nav>

        <div className="main" id="conteudo">
          {page === "search" ? (
            <SearchPanel
              keys={keys}
              onSpent={refreshKeys}
              notify={notify}
              goKeys={() => setPage("keys")}
              onSaved={setSavedCount}
            />
          ) : page === "saved" ? (
            <SavedPanel
              notify={notify}
              onCountChange={setSavedCount}
              goSearch={() => setPage("search")}
            />
          ) : (
            <KeysPanel keys={keys} quota={quota} onChange={refreshKeys} notify={notify} />
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

/**
 * Units a search costs with the default filters: one niche, two pages, with
 * the recency data the activity filter needs. Mirrors estimate_search_cost in
 * backend/app/keyring.py — 2 x (100 + 1) + 2 x 50.
 */
const UNITS_PER_SEARCH = 302;

/** Hours until the YouTube quota rolls over.
 *
 * Reset is midnight US/Pacific. The backend pins the offset at -8 so a reset
 * is never announced earlier than it happens; matching that here keeps the
 * two from contradicting each other on screen.
 */
function hoursUntilReset(now: Date = new Date()): number {
  const shifted = new Date(now.getTime() - 8 * 3_600_000);
  const nextMidnight = Date.UTC(
    shifted.getUTCFullYear(),
    shifted.getUTCMonth(),
    shifted.getUTCDate() + 1,
  );
  return Math.max(1, Math.ceil((nextMidnight + 8 * 3_600_000 - now.getTime()) / 3_600_000));
}

/**
 * Credits left on the API key, at the foot of the rail.
 *
 * "9.698 unidades" is not a number anyone can act on. The one that matters is
 * how many searches it buys, so that is what the panel leads with; the raw
 * count stays for whoever wants it.
 */
function QuotaMeter({ quota, goKeys }: { quota: Quota | null; goKeys: () => void }) {
  const total = quota?.units_total ?? 0;
  const left = quota?.units_remaining ?? 0;

  if (total === 0) {
    return (
      <div className="credits">
        <p className="credits-lbl">Créditos de hoje</p>
        <p className="credits-none">Nenhuma chave cadastrada.</p>
        <button className="btn btn-ghost btn-sm" onClick={goKeys}>
          <Icons.Plus size={14} />
          Adicionar chave
        </button>
      </div>
    );
  }

  const pct = (left / total) * 100;
  const level = pct < 15 ? " meter--crit" : pct < 40 ? " meter--warn" : "";
  const searches = Math.floor(left / UNITS_PER_SEARCH);
  const hours = hoursUntilReset();

  return (
    <div className="credits">
      <p className="credits-lbl">Créditos de hoje</p>
      <p className="credits-n">
        {left.toLocaleString("pt-BR")}
        <small>de {total.toLocaleString("pt-BR")}</small>
      </p>
      {/* Decorative: every number it encodes is written out below it. */}
      <div className={`meter meter-full${level}`} aria-hidden="true">
        <i style={{ width: `${pct}%` }} />
      </div>
      <p className="credits-sub">
        {searches > 0 ? (
          <>
            dá para <b>{searches}</b> {searches === 1 ? "busca" : "buscas"}
          </>
        ) : (
          <span className="credits-out">não dá para outra busca</span>
        )}
      </p>
      <p className="credits-reset">zera em {hours}h</p>
    </div>
  );
}

/* ------------------------------------------------------------------ search */

function SearchPanel({
  keys,
  onSpent,
  notify,
  goKeys,
  onSaved,
}: {
  keys: ApiKey[];
  onSpent: () => void;
  notify: (m: string) => void;
  goKeys: () => void;
  onSaved: (total: number) => void;
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
      onSaved(response.total_saved);
      // Say what the base gained, not just what the screen shows: the point of
      // saving is that the numbers below are cumulative.
      const gained =
        response.saved_new > 0
          ? `${response.saved_new} novos na base`
          : "nenhum canal novo";
      notify(
        `${response.channels.length} canais · ${gained} · ${response.units_spent} unidades`,
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
        <div className="field field-lead">
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

        <div className="filters">
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
            <label htmlFor="mail">E-mail</label>
            <select id="mail" value={emailOnly ? "only" : "all"}
              onChange={(e) => setEmailOnly(e.target.value === "only")}>
              <option value="all">Todos os canais</option>
            <option value="only">Só com e-mail público</option>
          </select>
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

      {results && results.length > 0 ? (
        <ChannelTable
          channels={results}
          notify={notify}
          regionLabel="Resultados da busca"
          heading={<><span className="num">{results.length}</span> canais encontrados</>}
        />
      ) : results ? (
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

/* -------------------------------------------------------------------- base */

/**
 * The lead base: everything every search has ever found, kept on disk.
 *
 * A search costs quota, so its results outlive the tab that ran it. This view
 * reads the saved base rather than the last search.
 */
function SavedPanel({
  notify, onCountChange, goSearch,
}: {
  notify: (m: string) => void;
  onCountChange: (n: number) => void;
  goSearch: () => void;
}) {
  const [leads, setLeads] = useState<Lead[] | null>(null);
  const [total, setTotal] = useState(0);
  const [query, setQuery] = useState("");
  const [emailOnly, setEmailOnly] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const data = await api.listLeads({ q: query, withEmail: emailOnly });
      setLeads(data.leads);
      setTotal(data.total);
      onCountChange(data.total);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Não foi possível ler a base.");
    }
  }, [query, emailOnly, onCountChange]);

  useEffect(() => {
    // Debounced so typing in the filter does not fire a request per keystroke.
    const timer = setTimeout(() => void load(), 220);
    return () => clearTimeout(timer);
  }, [load]);

  async function remove(lead: Lead) {
    try {
      await api.removeLead(lead.id);
      notify(`${lead.title} removido da base`);
      void load();
    } catch {
      notify("Não foi possível remover");
    }
  }

  async function clearAll() {
    // Deleting the base throws away work that cost quota, so it asks first.
    if (!window.confirm(`Apagar os ${total} canais da base? Isso não tem volta.`)) return;
    try {
      const { removed } = await api.clearLeads();
      notify(`${removed} canais apagados`);
      void load();
    } catch {
      notify("Não foi possível apagar a base");
    }
  }

  const filtering = query.trim().length > 0 || emailOnly;

  return (
    <section>
      <div className="page-head">
        <div>
          <h2>Base de canais</h2>
          <p>Tudo que suas buscas já encontraram. Fica salvo no seu computador.</p>
        </div>
      </div>

      {error ? (
        <div className="banner" style={{ background: "var(--danger-soft)", color: "var(--danger)" }}>
          <Icons.Info size={17} />
          <div>{error}</div>
        </div>
      ) : null}

      <div className="panel" style={{ padding: "var(--s4)", marginBottom: "var(--s4)" }}>
        <div className="grid-2">
          <div className="field">
            <label htmlFor="lead-q">Filtrar</label>
            <input
              id="lead-q"
              type="search"
              placeholder="nome do canal, @handle ou nicho"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          <div className="field" style={{ justifyContent: "flex-end" }}>
            <label
              style={{
                display: "flex", gap: 9, alignItems: "center",
                cursor: "pointer", fontSize: 14, marginTop: 24,
              }}
            >
              <input
                type="checkbox"
                checked={emailOnly}
                onChange={(e) => setEmailOnly(e.target.checked)}
                style={{ width: 16, height: 16, accentColor: "var(--signal)" }}
              />
              <span>Só com e-mail</span>
            </label>
          </div>
        </div>
      </div>

      {leads === null ? (
        <div className="empty panel">
          <Icons.Board size={42} />
          <h3>Carregando a base…</h3>
        </div>
      ) : leads.length > 0 ? (
        <ChannelTable
          channels={leads}
          notify={notify}
          regionLabel="Base de canais salvos"
          heading={
            <>
              <span className="num">{leads.length}</span>
              {filtering ? ` de ${total} canais` : " canais salvos"}
            </>
          }
          onDelete={(c) => void remove(c as Lead)}
          actions={
            <button className="btn btn-ghost btn-sm" onClick={() => void clearAll()}>
              <Icons.Trash size={15} />
              Limpar base
            </button>
          }
        />
      ) : filtering ? (
        <div className="empty panel">
          <Icons.Search size={42} />
          <h3>Nada na base bate com esse filtro</h3>
          <p>Limpe o filtro para ver os {total} canais salvos.</p>
        </div>
      ) : (
        <div className="empty panel">
          <Icons.Board size={42} />
          <h3>A base está vazia</h3>
          <p>Toda busca guarda o que encontrar aqui automaticamente.</p>
          <button className="btn btn-sm" onClick={goSearch}>
            <Icons.Search size={15} />
            Fazer a primeira busca
          </button>
        </div>
      )}
    </section>
  );
}


/* -------------------------------------------------------------------- keys */

function KeysPanel({
  keys, quota, onChange, notify,
}: {
  keys: ApiKey[];
  quota: Quota | null;
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
          <p>
            {quota?.key_storage ?? "Carregando…"}. Adicione mais de uma para o
            rodízio automático.
          </p>
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
