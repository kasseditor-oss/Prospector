/**
 * Typed client for the Python API.
 *
 * Requests go to same-origin `/api/*`, which `next.config.mjs` rewrites to the
 * FastAPI service. Nothing here ever sees a YouTube API key — that lives on
 * the server, which is the whole reason this app has a backend at all.
 */

export type ScoreDetail = {
  total: number;
  reachability: number;
  rhythm: number;
  recency: number;
  fit: number;
};

export type Channel = {
  id: string;
  title: string;
  handle: string | null;
  url: string;
  subscribers: number;
  subscribers_hidden: boolean;
  video_count: number;
  country: string | null;
  thumbnail: string | null;
  email: string | null;
  /** Other networks the channel published in its description, fixed order. */
  socials: { network: string; handle: string; url: string }[];
  uploads_per_month: number;
  /** Uploads per month, oldest first. Shorter than 12 when the channel
   *  published enough to exhaust one page of API history. */
  cadence: number[];
  /** Last quarter over the preceding three. 0 = not enough history. */
  cadence_trend: number;
  days_since_last_upload: number | null;
  last_upload_at: string | null;
  niche: string;
  score: ScoreDetail;
};

export type SearchFilters = {
  niches: string[];
  country: string;
  language: string | null;
  min_subscribers: number;
  max_subscribers: number;
  activity_days: 0 | 30 | 90 | 365;
  email_only: boolean;
  deep: boolean;
};

export type SearchResponse = {
  channels: Channel[];
  units_spent: number;
  units_remaining: number;
  examined: number;
  filtered_out: number;
  /** Channels in this result that were not already in the lead base. */
  saved_new: number;
  /** Channels that were already there and had their numbers refreshed. */
  saved_updated: number;
  /** Size of the whole base after this search. */
  total_saved: number;
};

export type EstimateResponse = {
  units: number;
  units_remaining: number;
  affordable: boolean;
};

export type ApiKey = {
  label: string;
  masked: string;
  used: number;
  remaining: number;
  disabled_reason: string | null;
};

export type Quota = {
  keys: number;
  units_remaining: number;
  units_total: number;
  quota_day: string;
  /** What actually happens to a key between launches, in plain words. */
  key_storage: string;
};

/* ------------------------------------------------------------ X / pedidos */

/** A hiring post. Deliberately not a Channel: they share almost no column,
 *  and they go stale at completely different speeds. */
export type Post = {
  id: string;
  source: string;
  author: string;
  author_name: string;
  author_followers: number;
  author_url: string;
  text: string;
  url: string;
  posted_at: string | null;
  replies: number;
  likes: number;
  /** The post names money. */
  budget: boolean;
  /** The post reads like recurring work. */
  ongoing: boolean;
  /** The phrase that made this a lead, so the reader can judge the judgement. */
  matched: string;
  query: string;
  score: number;
  hours_old: number | null;
  first_seen?: string | null;
  last_seen?: string | null;
};

export type XSearchFilters = {
  /** Empty means the backend's built-in phrase list. */
  terms: string[];
  days: number;
  max_items: number;
  min_followers: number;
};

export type XSearchResponse = {
  posts: Post[];
  /** Tweets read before filtering. */
  examined: number;
  /** Rejected as editors advertising themselves. */
  competitors: number;
  /** Neither hiring nor offering. */
  unrelated: number;
  saved_new: number;
  saved_updated: number;
  total_saved: number;
  remaining_usd: number | null;
};

export type PostsResponse = { posts: Post[]; total: number };

export type PostQuery = {
  q?: string;
  sort?: string;
  withBudget?: boolean;
  minFollowers?: number;
  limit?: number;
};

/** The Apify token as the screen is allowed to know it. */
export type ApifyToken = {
  configured: boolean;
  masked: string;
  remaining_usd: number | null;
  total_usd: number | null;
  error: string | null;
};

/** An API error carrying the message the backend wanted the user to read. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });

  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") {
        detail = body.detail;
      } else if (Array.isArray(body.detail) && body.detail[0]?.msg) {
        // Pydantic validation errors arrive as a list.
        detail = body.detail[0].msg;
      }
    } catch {
      // Keep the generic message.
    }
    throw new ApiError(detail, response.status);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  health: () => request<{ status: string; quota_day: string }>("/health"),
  quota: () => request<Quota>("/quota"),
  listKeys: () => request<ApiKey[]>("/keys"),
  addKey: (key: string, label?: string) =>
    request<ApiKey>("/keys", {
      method: "POST",
      body: JSON.stringify({ key, label: label || null }),
    }),
  removeKey: (maskedSuffix: string) =>
    request<void>(`/keys/${encodeURIComponent(maskedSuffix)}`, { method: "DELETE" }),
  estimate: (filters: SearchFilters) =>
    request<EstimateResponse>("/search/estimate", {
      method: "POST",
      body: JSON.stringify(filters),
    }),
  search: (filters: SearchFilters) =>
    request<SearchResponse>("/search", {
      method: "POST",
      body: JSON.stringify(filters),
    }),
  listLeads: (params: LeadQuery = {}) => {
    const qs = new URLSearchParams();
    if (params.q) qs.set("q", params.q);
    if (params.sort) qs.set("sort", params.sort);
    if (params.withEmail) qs.set("with_email", "true");
    qs.set("limit", String(params.limit ?? 1000));
    return request<LeadsResponse>(`/leads?${qs.toString()}`);
  },
  removeLead: (id: string) =>
    request<void>(`/leads/${encodeURIComponent(id)}`, { method: "DELETE" }),
  clearLeads: () => request<{ removed: number }>("/leads", { method: "DELETE" }),

  xToken: () => request<ApifyToken>("/x/token"),
  saveXToken: (token: string, actor?: string) =>
    request<ApifyToken>("/x/token", {
      method: "POST",
      body: JSON.stringify({ token, actor: actor || null }),
    }),
  removeXToken: () => request<void>("/x/token", { method: "DELETE" }),
  // Read rather than repeated here: the phrase list is tuned against real
  // results, and a copy in the browser would quietly fall behind it.
  xTerms: () => request<{ terms: string[] }>("/x/terms"),
  searchX: (filters: XSearchFilters) =>
    request<XSearchResponse>("/x/search", {
      method: "POST",
      body: JSON.stringify(filters),
    }),
  listPosts: (params: PostQuery = {}) => {
    const qs = new URLSearchParams();
    if (params.q) qs.set("q", params.q);
    if (params.sort) qs.set("sort", params.sort);
    if (params.withBudget) qs.set("with_budget", "true");
    if (params.minFollowers) qs.set("min_followers", String(params.minFollowers));
    qs.set("limit", String(params.limit ?? 500));
    return request<PostsResponse>(`/posts?${qs.toString()}`);
  },
  removePost: (id: string) =>
    request<void>(`/posts/${encodeURIComponent(id)}`, { method: "DELETE" }),
  clearPosts: () => request<{ removed: number }>("/posts", { method: "DELETE" }),
};

export type LeadQuery = {
  q?: string;
  sort?: string;
  withEmail?: boolean;
  limit?: number;
};

/** A saved channel, plus when it entered the base and last refreshed. */
export type Lead = Channel & { first_seen: string; last_seen: string };

export type LeadsResponse = { leads: Lead[]; total: number };

/* ----------------------------------------------------------- formatting */

/** Countries the YouTube API accepts a region code for, in Portuguese. */
export const COUNTRIES: Record<string, string> = {
  BR: "Brasil", US: "Estados Unidos", PT: "Portugal", MX: "México",
  AR: "Argentina", ES: "Espanha", FR: "França", DE: "Alemanha",
  IT: "Itália", GB: "Reino Unido", CA: "Canadá", AU: "Austrália",
};

export function formatSubscribers(n: number, locale = "pt-BR"): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1).replace(".", ",")}M`;
  if (n >= 1_000) return `${Math.round(n / 1_000)}k`;
  return n.toLocaleString(locale);
}

export function formatDays(days: number | null, locale = "pt-BR"): string {
  if (days === null) return locale === "pt-BR" ? "desconhecido" : "unknown";
  if (days === 0) return locale === "pt-BR" ? "hoje" : "today";
  if (days === 1) return locale === "pt-BR" ? "ontem" : "yesterday";
  if (days < 30) return `${days} ${locale === "pt-BR" ? "dias" : "days"}`;
  const months = Math.round(days / 30);
  if (locale === "pt-BR") return `${months} ${months > 1 ? "meses" : "mês"}`;
  return `${months} ${months > 1 ? "months" : "month"}`;
}

/** Meter bands: the score reads like a level meter, not a brand gradient. */
export function scoreColor(total: number): string {
  if (total >= 70) return "var(--meter-hi)";
  if (total >= 45) return "var(--meter-mid)";
  return "var(--meter-lo)";
}

/** How old a post is, read the way someone deciding whether to answer reads
 *  it: hours while that is the unit that matters, then days. */
export function formatAge(hours: number | null): string {
  if (hours === null || Number.isNaN(hours)) return "sem data";
  if (hours < 1) return "agora";
  if (hours < 24) return `${Math.floor(hours)}h`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d`;
  const weeks = Math.floor(days / 7);
  return weeks < 5 ? `${weeks}sem` : `${Math.floor(days / 30)}m`;
}

/** Freshness band. A hiring post collects replies within hours, so these
 *  boundaries are the same ones the backend scores on. */
export function ageBand(hours: number | null): string {
  if (hours === null) return "old";
  if (hours <= 6) return "now";
  if (hours <= 24) return "today";
  if (hours <= 168) return "week";
  return "old";
}

/** Apify bills in dollars and cents, so the screen does too. */
export function formatUsd(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `US$ ${value.toFixed(2).replace(".", ",")}`;
}

/** Age in hours from whatever the post carries.
 *
 * A post read back from the base arrives with `hours_old` already worked out;
 * one straight from a search does not, so the date is the fallback. Neither
 * path is allowed to leave the column blank when a date exists. */
export function postAge(post: Post, now: number = Date.now()): number | null {
  if (typeof post.hours_old === "number") return post.hours_old;
  if (!post.posted_at) return null;
  const stamp = Date.parse(post.posted_at);
  if (Number.isNaN(stamp)) return null;
  return Math.max(0, (now - stamp) / 3_600_000);
}

/** One CSV cell, quoted only when it has to be. Shared by both exports so a
 *  quote inside a tweet and a comma inside a channel name are escaped by the
 *  same rule. */
function csvCell(value: unknown): string {
  const s = value === null || value === undefined ? "" : String(value);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

/** CSV of the hiring posts, with the columns an outreach list needs. */
export function toPostsCsv(posts: Post[]): string {
  const header = [
    "score", "idade_h", "autor", "nome", "seguidores", "respostas",
    "paga", "recorrente", "texto", "link", "perfil", "postado_em",
  ];
  const rows = posts.map((p) =>
    [
      p.score,
      postAge(p) === null ? "" : Math.floor(postAge(p) as number),
      `@${p.author}`,
      p.author_name,
      p.author_followers,
      p.replies,
      p.budget ? "sim" : "nao",
      p.ongoing ? "sim" : "nao",
      // Newlines inside a tweet would otherwise break the row in two.
      p.text.replace(/\s+/g, " ").trim(),
      p.url,
      p.author_url,
      p.posted_at ?? "",
    ]
      .map(csvCell)
      .join(","),
  );
  return [header.join(","), ...rows].join("\n");
}

/** CSV for the columns a user actually pastes into a CRM. */
export function toCsv(channels: Channel[]): string {
  const cols = [
    "title", "handle", "url", "subscribers", "score", "email",
    "uploads_per_month", "cadence_trend", "days_since_last_upload",
    "country", "niche",
  ] as const;
  // Socials flatten into one cell of URLs: a CRM import wants the links, not a
  // column per network that would be empty on most rows.
  const rows = channels.map((c) =>
    [
      ...cols.map((col) =>
        csvCell(col === "score" ? c.score.total : c[col as keyof Channel]),
      ),
      csvCell((c.socials ?? []).map((s) => s.url).join(" ")),
    ].join(","),
  );
  return [[...cols, "redes"].join(","), ...rows].join("\n");
}
