/** The workspace uses light glass surfaces and black typography in every OS theme. */
import { createContext, useContext, useLayoutEffect, type ReactNode } from "react";

type Ctx = { resolved: "light" };
const ThemeContext = createContext<Ctx | null>(null);
const light: Ctx = { resolved: "light" };

export function ThemeProvider({ children }: { children: ReactNode }) {
  useLayoutEffect(() => {
    document.documentElement.setAttribute("data-theme", "light");
  }, []);
  return <ThemeContext.Provider value={light}>{children}</ThemeContext.Provider>;
}

export function useTheme(): Ctx {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used inside <ThemeProvider>");
  return ctx;
}
