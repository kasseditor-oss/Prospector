/**
 * Upload cadence for one channel — twelve months of real publishing history,
 * ending at a playhead.
 *
 * This is the one thing on a lead row that answers the editor's actual
 * question: is this channel shipping enough to need help, and is it speeding
 * up or going quiet? Every bar is a measured count, never a decorative shape.
 *
 * When the window is shorter than twelve months the channel published enough
 * to exhaust one page of API history, so the strip is drawn short rather than
 * padded with zeroes that would read as silence.
 */

type Props = {
  /** Uploads per month, oldest first. */
  cadence: number[];
  /** Last quarter over the preceding three. 0 means not enough history. */
  trend?: number;
  size?: "sm" | "lg";
  /** Draw the bars in on mount. Ignored under prefers-reduced-motion. */
  animate?: boolean;
};

const MONTHS_PT = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];

function monthLabel(offsetFromEnd: number): string {
  const now = new Date();
  const month = new Date(now.getFullYear(), now.getMonth() - offsetFromEnd, 1);
  return `${MONTHS_PT[month.getMonth()]}/${String(month.getFullYear()).slice(2)}`;
}

export function CadenceStrip({ cadence, trend = 0, size = "sm", animate = false }: Props) {
  if (cadence.length === 0) {
    return (
      <span className="binlabel" title="Sem histórico de uploads disponível">
        sem histórico
      </span>
    );
  }

  // The bars are sized in real pixels against a known track height. An earlier
  // version used percentages, which depend on the flex container resolving its
  // own height first; when that failed the bars painted over the rows above.
  const track = size === "lg" ? 68 : 26;
  const peak = Math.max(...cadence, 1);
  const total = cadence.reduce((sum, n) => sum + n, 0);
  // The last quarter is the part the reader is judging, so it carries the
  // accent while the older months stay quiet.
  const liveFrom = Math.max(0, cadence.length - 3);

  const summary =
    `${total} vídeos em ${cadence.length} ${cadence.length === 1 ? "mês" : "meses"}` +
    (trend > 1.25 ? ", acelerando" : trend > 0 && trend < 0.75 ? ", desacelerando" : "");

  return (
    <span
      className={`cadence${size === "lg" ? " cadence-lg" : ""}${animate ? " cadence-animate" : ""}`}
      role="img"
      aria-label={`Cadência de publicação: ${summary}`}
      title={summary}
    >
      {cadence.map((count, i) => {
        const offsetFromEnd = cadence.length - 1 - i;
        const isLive = i >= liveFrom;
        const height =
          count === 0 ? 2 : Math.min(track, Math.max(3, Math.round((count / peak) * track)));
        return (
          <span
            key={offsetFromEnd}
            // Modifiers are namespaced on purpose: a bare `empty` here once
            // collided with the `.empty` empty-state panel and every silent
            // month inherited its padding, blowing the bar up to 48x144.
            className={`cadence-bar${count === 0 ? " cadence-bar--zero" : isLive ? " cadence-bar--live" : ""}`}
            style={{
              height: `${height}px`,
              animationDelay: animate ? `${i * 34}ms` : undefined,
            }}
            // Native tooltip per bar: the reader can check any single month.
            title={`${monthLabel(offsetFromEnd)}: ${count} ${count === 1 ? "vídeo" : "vídeos"}`}
          />
        );
      })}
      <span className="cadence-playhead" aria-hidden="true" />
    </span>
  );
}

/** Arrow plus ratio, or a dash when there is not enough history to claim one. */
export function TrendTag({ trend }: { trend: number }) {
  if (!trend) return <span className="trend flat">—</span>;
  if (trend > 1.25) {
    return (
      <span className="trend up" title="Publicando mais que nos meses anteriores">
        ↑ {trend.toFixed(1)}×
      </span>
    );
  }
  if (trend < 0.75) {
    return (
      <span className="trend down" title="Publicando menos que nos meses anteriores">
        ↓ {trend.toFixed(1)}×
      </span>
    );
  }
  return (
    <span className="trend flat" title="Ritmo estável">
      = {trend.toFixed(1)}×
    </span>
  );
}
