"use client";

import { useState } from "react";

/**
 * A channel's profile picture, with its initials as the fallback.
 *
 * Served straight from YouTube's CDN with a plain <img> rather than
 * next/image: a result page holds ~100 rows, and routing every one of them
 * through the optimiser would put a hundred fetches on our own server to
 * resize images that arrive at 88px and are drawn at 32px.
 *
 * A dead thumbnail URL must never leave a hole in the row, so a failed load
 * falls back to the initials instead of a broken-image glyph.
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
        loading="lazy"
        decoding="async"
        referrerPolicy="no-referrer"
        onError={() => setFailed(true)}
      />
    </div>
  );
}
