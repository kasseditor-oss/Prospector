/**
 * The other networks a channel links to from its description.
 *
 * For someone selling editing work this is a routing decision, not trivia: a
 * Discord invite is a faster way in than a business email, and a channel that
 * already runs Instagram and TikTok is buying short-form edits from someone.
 *
 * Every icon here is a link the creator published. Nothing is inferred, so an
 * empty cell honestly means "this channel listed nothing", not "we didn't look".
 */

import { ExternalLink } from "@/components/ExternalLink";

export type Social = { network: string; handle: string; url: string };

type Brand = { label: string; path: React.ReactNode };

// Colours live in CSS as --br-<network> so each theme can carry its own value:
// TikTok cyan and Kick green disappear on white, and their dark equivalents
// disappear on near-black. A row is scannable because the marks look like
// themselves, but shape and an accessible name carry the meaning too, so
// colour is never the only cue. Facebook keeps its own blue rather than
// borrowing --signal, which would make a logo read as interface chrome.
const BRANDS: Record<string, Brand> = {
  instagram: {
    label: "Instagram",
    path: (
      <>
        <rect x="3" y="3" width="18" height="18" rx="5" fill="none" stroke="currentColor" strokeWidth="2" />
        <circle cx="12" cy="12" r="4" fill="none" stroke="currentColor" strokeWidth="2" />
        <circle cx="17.4" cy="6.6" r="1.3" />
      </>
    ),
  },
  tiktok: {
    label: "TikTok",
    path: <path d="M15.2 3h-3v13a2.3 2.3 0 1 1-2.3-2.3c.2 0 .5 0 .7.1v-3a5.3 5.3 0 1 0 4.6 5.2V9.6c1.2.8 2.6 1.3 4.1 1.3V7.9a4.2 4.2 0 0 1-4.1-4.9z" />,
  },
  x: {
    label: "X",
    path: <path d="M4 3h4.2l4 5.5L16.9 3H20l-6.3 7.4L20.4 21h-4.2l-4.3-5.9L6.6 21H3.5l6.6-7.8L4 3z" />,
  },
  discord: {
    label: "Discord",
    path: (
      <>
        <path d="M18.9 6.5A15.4 15.4 0 0 0 15.1 5.3l-.24.5a13.9 13.9 0 0 1 2.1.9 12.9 12.9 0 0 0-9.9 0c.66-.36 1.36-.66 2.1-.9l-.24-.5A15.4 15.4 0 0 0 5.1 6.5C2.7 10 2.1 13.4 2.4 16.8a15.6 15.6 0 0 0 4.7 2.4l1-1.6a10 10 0 0 1-1.6-.8l.4-.3a11.1 11.1 0 0 0 9.2 0l.4.3a10 10 0 0 1-1.6.8l1 1.6a15.6 15.6 0 0 0 4.7-2.4c.36-4-.62-7.3-2.7-10.3z" />
        <circle cx="9.3" cy="13" r="1.4" fill="var(--panel)" />
        <circle cx="14.7" cy="13" r="1.4" fill="var(--panel)" />
      </>
    ),
  },
  twitch: {
    label: "Twitch",
    path: <path d="M4.3 3h15.4v11l-4.3 4.3h-3.1L9.2 21H7v-2.7H4.3V3zm2.1 2.1v11.1h3.1v2.7l2.7-2.7h3.4l3-3V5.1H6.4zm5.1 2.5h2.1v5.1h-2.1V7.6zm5.1 0h2.1v5.1h-2.1V7.6z" />,
  },
  telegram: {
    label: "Telegram",
    path: <path d="M21.8 4.4 2.9 11.7c-1 .4-1 1.6.03 1.9l4.8 1.5 1.8 5.5c.3.9 1.4 1.1 2 .4l2.5-2.6 4.8 3.5c.8.6 1.9.1 2.1-.8l3.2-15.3c.2-1-.7-1.8-1.6-1.4zM8.6 14.3l8.7-5.4-7.1 6.4-.4 3.4-1.2-4.4z" />,
  },
  threads: {
    label: "Threads",
    path: (
      <path
        d="M12 21c-5.3 0-8.4-3.4-8.4-9S6.7 3 12 3c4 0 6.7 1.9 7.8 5.2M9 9.6c.8-1 2-1.5 3.2-1.5 2.4 0 3.8 1.4 4 4.1M12.6 12c3.1 0 5 1.2 5 3.4 0 1.9-1.6 3.1-3.4 3.1-2 0-3.2-1.2-3.2-2.6 0-1.4 1.3-2.2 3.1-2.2 2.6 0 4.5 1.4 4.5 4"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.9"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    ),
  },
  facebook: {
    label: "Facebook",
    path: <path d="M13.6 21v-8h2.7l.4-3.1h-3.1V7.9c0-.9.25-1.5 1.6-1.5h1.7V3.6c-.3 0-1.3-.13-2.5-.13-2.4 0-4.1 1.5-4.1 4.2v2.3H7.5V13h2.8v8h3.3z" />,
  },
  linkedin: {
    label: "LinkedIn",
    path: <path d="M5 3.5a2.4 2.4 0 1 0 0 4.9 2.4 2.4 0 0 0 0-4.9zM3.1 9.6h3.8V21H3.1V9.6zm6.2 0H13v1.6h.05c.5-1 1.8-1.9 3.6-1.9 3.8 0 4.5 2.4 4.5 5.5V21h-3.8v-5.5c0-1.3 0-3-1.9-3s-2.2 1.4-2.2 2.9V21H9.3V9.6z" />,
  },
  kick: {
    label: "Kick",
    path: <path d="M3 3h5.2v5.2h2.6V5.6h2.6V3h5.2v5.2h-2.6v2.6h-2.6v2.6h2.6v2.6h2.6V21h-5.2v-2.6h-2.6v-2.6H8.2V21H3V3z" />,
  },
};

export function SocialLinks({ socials }: { socials: Social[] }) {
  if (!socials || socials.length === 0) {
    return <span className="socials-none" title="O canal não publicou outras redes na descrição">—</span>;
  }

  return (
    <span className="socials">
      {socials.map((s) => {
        const brand = BRANDS[s.network];
        if (!brand) return null;
        return (
          <ExternalLink
            key={s.network}
            href={s.url}
            className="social"
            style={{ color: `var(--br-${s.network})` }}
            title={`${brand.label}: ${s.handle}`}
            aria-label={`${brand.label} do canal: ${s.handle} (abre em nova aba)`}
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              {brand.path}
            </svg>
          </ExternalLink>
        );
      })}
    </span>
  );
}
