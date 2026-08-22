"use client";

import { useEffect, useState } from "react";
import { Icons } from "./Icons";

const STORAGE_KEY = "prospector.theme";

/**
 * Light/dark switch.
 *
 * The stored choice is applied by an inline script in the layout before first
 * paint; this component only reads the resulting state and flips it. It
 * renders a stable placeholder until mounted so the server and client markup
 * agree — a mismatch here is the classic hydration warning.
 */
export function ThemeToggle() {
  const [dark, setDark] = useState<boolean | null>(null);

  useEffect(() => {
    const stored = (() => {
      try {
        return localStorage.getItem(STORAGE_KEY);
      } catch {
        return null;
      }
    })();
    if (stored === "dark" || stored === "light") {
      setDark(stored === "dark");
      return;
    }
    setDark(window.matchMedia("(prefers-color-scheme: dark)").matches);
  }, []);

  function toggle() {
    const next = !dark;
    setDark(next);
    document.documentElement.setAttribute("data-theme", next ? "dark" : "light");
    try {
      localStorage.setItem(STORAGE_KEY, next ? "dark" : "light");
    } catch {
      // A browser blocking site data is not a reason to break the toggle.
    }
  }

  return (
    <button
      type="button"
      className="btn btn-ghost btn-icon"
      onClick={toggle}
      aria-label={dark ? "Usar tema claro" : "Usar tema escuro"}
    >
      {dark ? <Icons.Sun size={17} /> : <Icons.Moon size={17} />}
    </button>
  );
}
