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
};

/* ----------------------------------------------------------- formatting */

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
  const rows = channels.map((c) =>
    cols
      .map((col) => escape(col === "score" ? c.score.total : c[col as keyof Channel]))
      .join(","),
  );
  return [cols.join(","), ...rows].join("\n");
}
