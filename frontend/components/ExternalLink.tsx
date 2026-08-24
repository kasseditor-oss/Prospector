"use client";

import { safeHref } from "@/lib/links";

/**
 * A link out to somewhere the app does not control.
 *
 * One component for every outbound link so three habits can never drift apart
 * per call site: the address is checked (see lib/links), the new tab cannot
 * reach back through `window.opener`, and no referrer is handed to the site
 * being opened.
 *
 * An address that fails the check renders as plain text rather than a dead
 * link, because something that looks clickable and is not is the worse of the
 * two.
 */
type Props = Omit<React.AnchorHTMLAttributes<HTMLAnchorElement>, "href" | "target" | "rel"> & {
  href: string | null | undefined;
};

export function ExternalLink({ href, children, ...rest }: Props) {
  const safe = safeHref(href);
  if (!safe) {
    // Anchor-only attributes are dropped along with the anchor; what is left
    // is className, style and the accessible name, all valid on a span.
    return <span {...(rest as React.HTMLAttributes<HTMLSpanElement>)}>{children}</span>;
  }
  return (
    <a {...rest} href={safe} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  );
}
