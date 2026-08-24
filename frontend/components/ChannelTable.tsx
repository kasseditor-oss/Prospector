"use client";

/**
 * The results table, shared by the search view and the saved base.
 *
 * Both views show the same channels and the reader should be able to sort and
 * read them identically, so the table lives here rather than being written
 * twice and drifting apart.
 */

import { useMemo, useState } from "react";

import { Avatar } from "@/components/Avatar";
import { CadenceStrip, TrendTag } from "@/components/CadenceStrip";
import { ExternalLink } from "@/components/ExternalLink";
import { Icons } from "@/components/Icons";
import { SocialLinks } from "@/components/SocialLinks";
import { SortableTh } from "@/components/SortableTh";
import { StatusCell } from "@/components/StatusCell";
import {
  COUNTRIES,
  formatDays,
  formatSubscribers,
  scoreColor,
  toCsv,
  type Channel,
  type Status,
} from "@/lib/api";

export type SortKey =
  | "score"
  | "subscribers"
  | "title"
  | "uploads_per_month"
  | "days_since_last_upload";

type Props = {
  channels: Channel[];
  notify: (message: string) => void;
  /** Heading above the table, e.g. "42 canais encontrados". */
  heading: React.ReactNode;
  /** Controls placed left of the CSV button. */
  actions?: React.ReactNode;
  /** When given, each row gets a remove button. */
  onDelete?: (channel: Channel) => void;
  /** Label for the scroll region, announced to screen readers. */
  regionLabel?: string;
  /** When given, each row can be moved along the funnel. */
  onStatus?: (channel: Channel, status: Status) => Promise<void>;
  /** The funnel's words, as the backend spells them. */
  statusNames?: Record<string, string>;
};

export function ChannelTable({
  channels,
  notify,
  heading,
  actions,
  onDelete,
  regionLabel = "Resultados",
  onStatus,
  statusNames = {},
}: Props) {
  const [sortKey, setSortKey] = useState<SortKey>("score");
  const [sortDir, setSortDir] = useState<-1 | 1>(-1);

  const sorted = useMemo(() => {
    const rows = [...channels];
    rows.sort((a, b) => {
      if (sortKey === "title") {
        return a.title.localeCompare(b.title) * (sortDir === -1 ? -1 : 1);
      }
      if (sortKey === "score") return (a.score.total - b.score.total) * sortDir;
      // A missing value sorts to the far end rather than to zero: "never
      // posted" is not the same claim as "posted today".
      const av = (a[sortKey] ?? Number.MAX_SAFE_INTEGER) as number;
      const bv = (b[sortKey] ?? Number.MAX_SAFE_INTEGER) as number;
      return (av - bv) * sortDir;
    });
    return rows;
  }, [channels, sortKey, sortDir]);

  function sortBy(key: SortKey) {
    if (key === sortKey) setSortDir((d) => (d === 1 ? -1 : 1));
    else {
      setSortKey(key);
      setSortDir(-1);
    }
  }

  return (
    <>
      <div className="page-head" style={{ marginBottom: "var(--s3)" }}>
        <div>
          <h3 style={{ fontFamily: "var(--display)", fontSize: 17, fontWeight: 700 }}>
            {heading}
          </h3>
        </div>
        <div className="spacer" style={{ display: "flex", gap: 8, alignItems: "center" }}>
          {actions}
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => {
              // Exports what is on screen, in the order shown.
              void navigator.clipboard.writeText(toCsv(sorted));
              notify("CSV copiado");
            }}
          >
            <Icons.Download size={15} />
            CSV
          </button>
        </div>
      </div>

      <div className="tbl-wrap" tabIndex={0} role="region" aria-label={regionLabel}>
        <table>
          <thead>
            <tr>
              <SortableTh label="Canal" k="title" sortKey={sortKey} sortDir={sortDir} onSort={sortBy} />
              <SortableTh label="Inscritos" k="subscribers" sortKey={sortKey} sortDir={sortDir} onSort={sortBy} />
              <SortableTh label="Score" k="score" sortKey={sortKey} sortDir={sortDir} onSort={sortBy} />
              {onStatus ? <th scope="col">Status</th> : null}
              <th scope="col">E-mail</th>
              <th scope="col">Redes</th>
              <th scope="col">Cadência · 12m</th>
              <SortableTh label="Ritmo" k="uploads_per_month" sortKey={sortKey} sortDir={sortDir} onSort={sortBy} />
              <SortableTh label="Último vídeo" k="days_since_last_upload" sortKey={sortKey} sortDir={sortDir} onSort={sortBy} />
              {onDelete ? (
                <th scope="col">
                  <span className="sr">Remover</span>
                </th>
              ) : null}
            </tr>
          </thead>
          <tbody>
            {sorted.map((c) => (
              <tr key={c.id}>
                <td>
                  <div className="ch">
                    <Avatar src={c.thumbnail} title={c.title} />
                    <div style={{ minWidth: 0 }}>
                      <div className="ch-name">
                        <ExternalLink href={c.url}>
                          {c.title}
                        </ExternalLink>
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
                  <div
                    className="score"
                    title={`contato ${c.score.reachability} · ritmo ${c.score.rhythm} · recência ${c.score.recency} · porte ${c.score.fit}`}
                  >
                    <div className="score-track">
                      <i style={{ width: `${c.score.total}%`, background: scoreColor(c.score.total) }} />
                    </div>
                    <b>{c.score.total}</b>
                  </div>
                </td>
                {onStatus ? (
                  <td>
                    <StatusCell
                      value={(c as { status?: Status }).status ?? "novo"}
                      label={c.title}
                      names={statusNames}
                      onChange={(next) => onStatus(c, next)}
                    />
                  </td>
                ) : null}
                <td>
                  {c.email ? (
                    <>
                      <span className="mailcell">{c.email}</span>{" "}
                      <button
                        className="copy-btn"
                        aria-label={`Copiar e-mail de ${c.title}`}
                        onClick={() => {
                          void navigator.clipboard.writeText(c.email as string);
                          notify("E-mail copiado");
                        }}
                      >
                        <Icons.Copy size={13} />
                      </button>
                    </>
                  ) : (
                    <span className="mailcell none">não publicado</span>
                  )}
                </td>
                <td>
                  <SocialLinks socials={c.socials} />
                </td>
                <td>
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <CadenceStrip cadence={c.cadence} trend={c.cadence_trend} />
                    <TrendTag trend={c.cadence_trend} />
                  </div>
                </td>
                <td className="num">{c.uploads_per_month.toFixed(1)}/mês</td>
                <td>{formatDays(c.days_since_last_upload)}</td>
                {onDelete ? (
                  <td>
                    <button
                      className="copy-btn"
                      aria-label={`Remover ${c.title} da base`}
                      title="Remover da base"
                      onClick={() => onDelete(c)}
                    >
                      <Icons.Trash size={13} />
                    </button>
                  </td>
                ) : null}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
