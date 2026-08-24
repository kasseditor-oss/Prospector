"use client";

/**
 * Where a lead stands with you, changed in place.
 *
 * The control is a native `<select>`, because marking rows happens dozens of
 * times in a sitting and always mid-scroll: it has to open on one click, answer
 * to the keyboard, and never trap focus — the exact list a hand-rolled dropdown
 * gets wrong.
 *
 * But the select is invisible, laid over the pill, and the label beside the dot
 * is an ordinary span. Styling the select directly looked simpler and was not:
 * as a flex item it collapsed to the width of its own padding, measured at
 * 16px, leaving a dot and an arrow with no word between them. A span sizes the
 * way text sizes. So the span is what you see and the select is what you use.
 */

import { useState } from "react";

import { STATUS_ORDER, type Status } from "@/lib/api";

type Props = {
  value: Status;
  /** Announced to screen readers, so the control says which row it belongs to. */
  label: string;
  names: Record<string, string>;
  onChange: (next: Status) => Promise<void>;
};

export function StatusCell({ value, label, names, onChange }: Props) {
  // The row is redrawn from the caller's state, so until that lands the cell
  // shows what was picked. Waiting instead would make every change feel stuck.
  const [pending, setPending] = useState<Status | null>(null);
  const [failed, setFailed] = useState(false);
  const shown = pending ?? value;

  async function pick(next: Status) {
    setPending(next);
    setFailed(false);
    try {
      await onChange(next);
    } catch {
      // Put the old value back rather than leaving a lie on screen.
      setFailed(true);
    } finally {
      setPending(null);
    }
  }

  return (
    <span className={`stat stat--${shown}${failed ? " stat--failed" : ""}`}>
      {/* The dot repeats what the word says, on purpose: colour alone would
          leave the column meaningless to anyone who cannot separate four hues,
          and the word alone would make the base unscannable. */}
      <i className="stat-dot" aria-hidden="true" />
      {/* Hidden from screen readers because the select underneath already
          announces the same value, and hearing it twice is worse than once. */}
      <span className="stat-label" aria-hidden="true">
        {names[shown] ?? shown}
      </span>
      <select
        className="stat-input"
        value={shown}
        aria-label={`Status de ${label}`}
        onChange={(e) => void pick(e.target.value as Status)}
      >
        {STATUS_ORDER.map((key) => (
          <option key={key} value={key}>
            {names[key] ?? key}
          </option>
        ))}
      </select>
      {failed ? <span className="sr">Não foi possível salvar.</span> : null}
    </span>
  );
}
