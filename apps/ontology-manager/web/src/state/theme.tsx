/** Light / dark / system theme, persisted per browser. Charts subscribe to `resolved` to re-theme. */

import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

type Mode = "system" | "light" | "dark";
type Ctx = { mode: Mode; resolved: "light" | "dark"; cycle: () => void };

const ThemeContext = createContext<Ctx | null>(null);
const KEY = "pranay360.theme";
const LEGACY_KEY = "glucose-studio.theme"; // pre-rename; read once so the saved theme carries over

function readMode(): Mode {
  try {
    const v = localStorage.getItem(KEY) ?? localStorage.getItem(LEGACY_KEY);
    return v === "light" || v === "dark" ? v : "system";
  } catch {
    return "system";
  }
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setMode] = useState<Mode>(readMode);
  const media = useMemo(() => window.matchMedia("(prefers-color-scheme: light)"), []);
  const [systemLight, setSystemLight] = useState(media.matches);

  useEffect(() => {
    const on = (e: MediaQueryListEvent) => setSystemLight(e.matches);
    media.addEventListener("change", on);
    return () => media.removeEventListener("change", on);
  }, [media]);

  useEffect(() => {
    const root = document.documentElement;
    if (mode === "system") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", mode);
    try {
      localStorage.setItem(KEY, mode);
    } catch {
      /* private mode: theme just won't persist */
    }
  }, [mode]);

  const resolved = mode === "system" ? (systemLight ? "light" : "dark") : mode;
  const cycle = () => setMode((m) => (m === "system" ? (resolved === "dark" ? "light" : "dark") : m === "dark" ? "light" : "system"));

  return <ThemeContext.Provider value={{ mode, resolved, cycle }}>{children}</ThemeContext.Provider>;
}

export function useTheme(): Ctx {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used inside <ThemeProvider>");
  return ctx;
}
