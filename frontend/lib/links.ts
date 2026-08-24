/**
 * Letting only real web addresses become clickable links.
 *
 * Most of what this app shows was written by strangers. A tweet's URL comes
 * back from a scraper that reads whatever X served it, and a channel's social
 * links are parsed out of a description its owner controls. React escapes text
 * for us, so none of that can inject markup — but `href` is the one attribute
 * it does not police. `href="javascript:..."` still renders, still runs on
 * click, and it runs *inside this page*, which shares an origin with the API
 * and therefore with the whole lead base.
 *
 * So an address becomes a link only if it says http or https. Anything else —
 * `javascript:`, `data:`, `file:`, a scheme nobody has invented yet — comes
 * back null, and the caller shows plain text instead of a trap.
 */

/** The address, if it is a web address; otherwise null. */
export function safeHref(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    // Parsed with no base, so a relative path is rejected along with the rest:
    // every address this app displays arrives absolute, from YouTube or from X.
    // The parser also settles the tricks a hand-rolled check misses — leading
    // whitespace, "JaVaScRiPt:", embedded newlines and tabs.
    const scheme = new URL(url).protocol;
    return scheme === "http:" || scheme === "https:" ? url : null;
  } catch {
    // Not an address at all.
    return null;
  }
}
