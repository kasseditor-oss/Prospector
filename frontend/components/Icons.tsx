/**
 * Inline SVG icon set.
 *
 * Deliberately hand-rolled rather than pulled from a package: nine icons do
 * not justify a dependency, and inlining them means no extra request and no
 * flash of missing glyphs. Emoji are never used as icons — they render
 * differently per platform and are read aloud by screen readers.
 */

type IconProps = { size?: number; className?: string };

const base = (size: number) => ({
  width: size,
  height: size,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 2,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
});

const Search = ({ size = 18 }: IconProps) => (
  <svg {...base(size)}>
    <circle cx="11" cy="11" r="7" />
    <path d="M21 21l-4.3-4.3" />
  </svg>
);

const Board = ({ size = 18 }: IconProps) => (
  <svg {...base(size)}>
    <rect x="3" y="3" width="6" height="18" rx="1.5" />
    <rect x="11" y="3" width="6" height="11" rx="1.5" />
    <rect x="19" y="3" width="2" height="15" rx="1" />
  </svg>
);

const Key = ({ size = 18 }: IconProps) => (
  <svg {...base(size)}>
    <circle cx="7.5" cy="15.5" r="4.5" />
    <path d="M10.8 12.2L20 3m-3 0l3 3-2.5 2.5L15 6" />
  </svg>
);

const Mail = ({ size = 18 }: IconProps) => (
  <svg {...base(size)}>
    <rect x="2.5" y="4.5" width="19" height="15" rx="2.5" />
    <path d="M3 7l9 6 9-6" />
  </svg>
);

const Copy = ({ size = 18 }: IconProps) => (
  <svg {...base(size)}>
    <rect x="9" y="9" width="12" height="12" rx="2" />
    <path d="M5 15H4a1 1 0 01-1-1V4a1 1 0 011-1h10a1 1 0 011 1v1" />
  </svg>
);

const Check = ({ size = 18 }: IconProps) => (
  <svg {...base(size)} strokeWidth={2.5}>
    <path d="M20 6L9 17l-5-5" />
  </svg>
);

const Plus = ({ size = 18 }: IconProps) => (
  <svg {...base(size)}>
    <path d="M12 5v14M5 12h14" />
  </svg>
);

const Download = ({ size = 18 }: IconProps) => (
  <svg {...base(size)}>
    <path d="M12 3v12m0 0l-4-4m4 4l4-4M4 17v2a2 2 0 002 2h12a2 2 0 002-2v-2" />
  </svg>
);

const Gauge = ({ size = 18 }: IconProps) => (
  <svg {...base(size)}>
    <path d="M12 14l4-4" />
    <path d="M3.5 18a9 9 0 1117 0" />
  </svg>
);

const Spark = ({ size = 18 }: IconProps) => (
  <svg {...base(size)}>
    <path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z" />
    <path d="M18.5 15.5l.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8z" />
  </svg>
);

const Globe = ({ size = 18 }: IconProps) => (
  <svg {...base(size)}>
    <circle cx="12" cy="12" r="9" />
    <path d="M3 12h18M12 3c2.5 2.7 2.5 15.3 0 18M12 3c-2.5 2.7-2.5 15.3 0 18" />
  </svg>
);

const Shield = ({ size = 18 }: IconProps) => (
  <svg {...base(size)}>
    <path d="M12 3l7.5 3v6c0 4.5-3.1 7.9-7.5 9-4.4-1.1-7.5-4.5-7.5-9V6z" />
    <path d="M9.5 12l1.8 1.8 3.4-3.6" />
  </svg>
);

const Doc = ({ size = 18 }: IconProps) => (
  <svg {...base(size)}>
    <path d="M14 3H7a2 2 0 00-2 2v14a2 2 0 002 2h10a2 2 0 002-2V8z" />
    <path d="M14 3v5h5M9 13h6M9 17h4" />
  </svg>
);

const Info = ({ size = 18 }: IconProps) => (
  <svg {...base(size)}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 11v5M12 8h.01" />
  </svg>
);

const Trash = ({ size = 18 }: IconProps) => (
  <svg {...base(size)}>
    <path d="M4 7h16M9 7V5a1 1 0 011-1h4a1 1 0 011 1v2M6 7l1 13a1 1 0 001 1h8a1 1 0 001-1l1-13" />
  </svg>
);

const Sun = ({ size = 18 }: IconProps) => (
  <svg {...base(size)}>
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2v2m0 16v2M4.9 4.9l1.4 1.4m11.4 11.4l1.4 1.4M2 12h2m16 0h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
  </svg>
);

const Moon = ({ size = 18 }: IconProps) => (
  <svg {...base(size)}>
    <path d="M20 14.5A8.5 8.5 0 019.5 4a8.5 8.5 0 1010.5 10.5z" />
  </svg>
);

/**
 * The mark is the cadence strip itself: four rising bars and a playhead.
 * It says what the product measures, and it is the same shape the reader
 * meets on every lead row.
 */
const Logo = () => (
  <svg className="brand-mark" viewBox="0 0 32 32" fill="none" aria-hidden="true">
    <rect width="32" height="32" rx="6" fill="var(--panel-3)" />
    <rect x="6" y="19" width="3.5" height="7" rx="1" fill="var(--ink-3)" />
    <rect x="11.5" y="15" width="3.5" height="11" rx="1" fill="var(--ink-3)" />
    <rect x="17" y="11" width="3.5" height="15" rx="1" fill="var(--signal)" />
    <rect x="22.5" y="6" width="3.5" height="20" rx="1" fill="var(--signal)" />
    <rect x="27.5" y="5" width="1" height="22" rx=".5" fill="var(--signal)" />
  </svg>
);

const BY_NAME = {
  search: Search, board: Board, key: Key, mail: Mail, copy: Copy, check: Check,
  plus: Plus, download: Download, gauge: Gauge, spark: Spark, globe: Globe,
  shield: Shield, doc: Doc, info: Info, trash: Trash, sun: Sun, moon: Moon,
} as const;

export type IconName = keyof typeof BY_NAME;

const ByName = ({ name, size }: IconProps & { name: IconName }) => {
  const Component = BY_NAME[name];
  return <Component size={size} />;
};

export const Icons = {
  Search, Board, Key, Mail, Copy, Check, Plus, Download, Gauge, Spark, Globe,
  Shield, Doc, Info, Trash, Sun, Moon, Logo, ByName,
};
