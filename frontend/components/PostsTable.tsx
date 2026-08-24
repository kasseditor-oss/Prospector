"use client";

/**
 * The hiring posts, shared by the X search and the saved base.
 *
 * This is not the channels table with different labels. A channel is judged on
 * what it is — size, rhythm, reachability — and it will still be that channel
 * next month. A hiring post is judged on when it was written and how many
 * people have already answered it, and it is worthless by Friday. So the two
 * things the eye lands on first are the age and the reply count, and the
 * request itself gets the width, because reading it is the actual work.
 */

import { useMemo, useState } from "react";

import { Avatar } from "@/components/Avatar";
import { Icons } from "@/components/Icons";
import { SortableTh } from "@/components/SortableTh";
import { StatusCell } from "@/components/StatusCell";
import {
  ageBand,
  formatAge,
  formatSubscribers,
  postAge,
  scoreColor,
  toPostsCsv,
  type Post,
  type Status,
} from "@/lib/api";

export type PostSortKey = "score" | "age" | "author_followers" | "replies";

type Props = {
  posts: Post[];
  notify: (message: string) => void;
  heading: React.ReactNode;
  actions?: React.ReactNode;
  onDelete?: (post: Post) => void;
  regionLabel?: string;
  /** When given, each row can be moved along the funnel. */
  onStatus?: (post: Post, status: Status) => Promise<void>;
  /** The funnel's words, as the backend spells them. */
  statusNames?: Record<string, string>;
};

export function PostsTable({
  posts,
  notify,
  heading,
  actions,
  onDelete,
  regionLabel = "Pedidos",
  onStatus,
  statusNames = {},
}: Props) {
  const [sortKey, setSortKey] = useState<PostSortKey>("score");
  const [sortDir, setSortDir] = useState<-1 | 1>(-1);

  const sorted = useMemo(() => {
    // One clock for the whole sort. Reading Date.now() per comparison would
    // let the ordering shift underneath the comparator.
    const now = Date.now();
    const rows = [...posts];
    rows.sort((a, b) => {
      if (sortKey === "age") {
        // Undated posts sort to the far end rather than to zero: "no date" is
        // not a claim that it was posted this second.
        const av = postAge(a, now) ?? Number.MAX_SAFE_INTEGER;
        const bv = postAge(b, now) ?? Number.MAX_SAFE_INTEGER;
        // Newest first when the arrow points down, because that is what
        // someone hunting fresh work expects the default to mean.
        return (bv - av) * sortDir;
      }
      return (a[sortKey] - b[sortKey]) * sortDir;
    });
    return rows;
  }, [posts, sortKey, sortDir]);

  function sortBy(key: PostSortKey) {
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
              void navigator.clipboard.writeText(toPostsCsv(sorted));
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
              <SortableTh label="Urgência" k="score" sortKey={sortKey} sortDir={sortDir} onSort={sortBy} />
              <SortableTh label="Idade" k="age" sortKey={sortKey} sortDir={sortDir} onSort={sortBy} />
              <SortableTh label="Quem pediu" k="author_followers" sortKey={sortKey} sortDir={sortDir} onSort={sortBy} />
              {onStatus ? <th scope="col">Status</th> : null}
              <th scope="col">O pedido</th>
              <SortableTh label="Respostas" k="replies" sortKey={sortKey} sortDir={sortDir} onSort={sortBy} />
              <th scope="col">
                <span className="sr">Ações</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((p) => {
              const hours = postAge(p);
              return (
                <tr key={p.id}>
                  <td>
                    <div className="score" title={`urgência ${p.score} de 99`}>
                      <div className="score-track">
                        <i style={{ width: `${p.score}%`, background: scoreColor(p.score) }} />
                      </div>
                      <b>{p.score}</b>
                    </div>
                  </td>
                  <td>
                    <span className={`age age--${ageBand(hours)}`}>{formatAge(hours)}</span>
                  </td>
                  <td>
                    <div className="ch">
                      <Avatar src={null} title={p.author_name || p.author} />
                      <div style={{ minWidth: 0 }}>
                        <div className="ch-name">
                          <a href={p.author_url} target="_blank" rel="noopener noreferrer">
                            {p.author_name || p.author}
                          </a>
                        </div>
                        <div className="ch-sub">
                          @{p.author} · {formatSubscribers(p.author_followers)}
                        </div>
                      </div>
                    </div>
                  </td>
                  {onStatus ? (
                    <td>
                      <StatusCell
                        value={p.status ?? "novo"}
                        label={`@${p.author}`}
                        names={statusNames}
                        onChange={(next) => onStatus(p, next)}
                      />
                    </td>
                  ) : null}
                  <td>
                    <p className="pcell">
                      <Highlighted text={p.text} phrase={p.matched} />
                    </p>
                    {p.budget || p.ongoing ? (
                      <p className="psig" style={{ marginTop: 6 }}>
                        {p.budget ? <span className="pill pill-money">paga</span> : null}
                        {p.ongoing ? <span className="pill pill-loop">recorrente</span> : null}
                      </p>
                    ) : null}
                  </td>
                  <td>
                    <span
                      className={`replies ${
                        p.replies === 0 ? "replies--none" : p.replies > 10 ? "replies--many" : ""
                      }`}
                      title={
                        p.replies === 0
                          ? "Ninguém respondeu ainda"
                          : `${p.replies} respostas até agora`
                      }
                    >
                      {p.replies}
                    </span>
                  </td>
                  <td>
                    <div style={{ display: "flex", gap: 4 }}>
                      <a
                        className="copy-btn"
                        href={p.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        title="Abrir no X"
                        aria-label={`Abrir o pedido de @${p.author} no X (abre em nova aba)`}
                      >
                        <Icons.External size={13} />
                      </a>
                      <button
                        className="copy-btn"
                        aria-label={`Copiar o link do pedido de @${p.author}`}
                        title="Copiar link"
                        onClick={() => {
                          void navigator.clipboard.writeText(p.url);
                          notify("Link copiado");
                        }}
                      >
                        <Icons.Copy size={13} />
                      </button>
                      {onDelete ? (
                        <button
                          className="copy-btn"
                          aria-label={`Remover o pedido de @${p.author} da base`}
                          title="Remover da base"
                          onClick={() => onDelete(p)}
                        >
                          <Icons.Trash size={13} />
                        </button>
                      ) : null}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}

/**
 * The post, with the phrase that classified it marked in place.
 *
 * The classifier is a pile of regexes and it is wrong about roughly one post
 * in four. Showing which words convinced it turns that from something the
 * reader has to trust into something they can check at a glance.
 *
 * The phrase comes from a cleaned copy of the text, so it does not always
 * appear verbatim in the original. When it does not, the text is shown plain
 * rather than approximately.
 */
function Highlighted({ text, phrase }: { text: string; phrase: string }) {
  if (!phrase) return <>{text}</>;
  const at = text.toLowerCase().indexOf(phrase.toLowerCase());
  if (at === -1) return <>{text}</>;
  return (
    <>
      {text.slice(0, at)}
      <mark>{text.slice(at, at + phrase.length)}</mark>
      {text.slice(at + phrase.length)}
    </>
  );
}
