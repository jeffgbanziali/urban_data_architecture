import { createContext, useContext, type ReactNode } from "react";
import { useTheme } from "../hooks/useTheme";

interface ThemeCtx { isDark: boolean; toggle: () => void; }

const ThemeContext = createContext<ThemeCtx>({ isDark: false, toggle: () => {} });

export function ThemeProvider({ children }: { children: ReactNode }) {
    const theme = useTheme();
    return <ThemeContext.Provider value={theme}>{children}</ThemeContext.Provider>;
}

export const useThemeContext = () => useContext(ThemeContext);
