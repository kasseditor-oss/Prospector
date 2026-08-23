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

/** CSV for the columns a user actually pastes into a CRM. */
export function toCsv(channels: Channel[]): string {
  const cols = [
    "title", "handle", "url", "subscribers", "score", "email",
    "uploads_per_month", "cadence_trend", "days_since_last_upload",
    "country", "niche",
  ] as const;
  const escape = (value: unknown) => {
    const s = value === null || value === undefined ? "" : String(value);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  // Socials flatten into one cell of URLs: a CRM import wants the links, not a
  // column per network that would be empty on most rows.
  const rows = channels.map((c) =>
    [
      ...cols.map((col) =>
        escape(col === "score" ? c.score.total : c[col as keyof Channel]),
      ),
      escape((c.socials ?? []).map((s) => s.url).join(" ")),
    ].join(","),
  );
  return [[...cols, "redes"].join(","), ...rows].join("\n");
}
