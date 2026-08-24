"use client";

import { useState } from "react";

/**
 * Someone's profile picture, with their initials as the fallback.
 *
 * Served straight from the source CDN with a plain <img> rather than
 * next/image: a result page holds ~100 rows, and routing every one of them
 * through the optimiser would put a hundred fetches on our own server to
 * resize images that arrive at 88px and are drawn at 32px.
 *
 * Loaded eagerly, not lazily. `loading="lazy"` was here and simply never
 * fired: inside the table's scroll container, a row rendered by a filter or a
 * new search kept `complete === false` with no network request at all, even
 * sitting 432px down a 900px window — measured, with the same image loading
 * instantly the moment the attribute was switched off. Every picture is a few
 * kilobytes at 73px, so the honest trade is a handful of extra requests for a
 * column that actually draws.
 *
 * A dead URL must never leave a hole in the row, so a failed load falls back
 * to the initials instead of a broken-image glyph.
 */
export function Avatar({ src, title }: { src: string | null; title: string }) {
  const [failed, setFailed] = useState(false);

  // Strip emoji and punctuation so a channel called "🔥 Gamer" reads "GA".
  const initials =
    title
      .replace(/[^\p{L}\p{N} ]/gu, "")
      .trim()
      .slice(0, 2)
      .toUpperCase() || "?";

  if (!src || failed) {
    return (
      <div className="av" style={{ background: "var(--signal-soft)", color: "var(--signal)" }}>
        {initials}
      </div>
    );
  }

  return (
    <div className="av av-photo">
      {/* Decorative: the channel name sits right beside it, so announcing the
          picture too would just repeat the name to a screen reader. */}
      <img
        src={src}
        alt=""
        width={32}
        height={32}
        decoding="async"
        referrerPolicy="no-referrer"
        onError={() => setFailed(true)}
      />
    </div>
  );
}
