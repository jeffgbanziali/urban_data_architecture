import { Sun, Moon } from "lucide-react";

interface Props {
    isDark: boolean;
    toggle: () => void;
}

export function ThemeToggle({ isDark, toggle }: Props) {
    return (
        <button
            onClick={toggle}
            className="flex items-center justify-center w-8 h-8 rounded-lg border transition-all"
            style={{
                borderColor: "var(--border)",
                backgroundColor: "var(--surface-alt)",
                color: "var(--text-2)",
            }}
            title={isDark ? "Mode clair" : "Mode sombre"}
        >
            {isDark ? <Sun size={15} /> : <Moon size={15} />}
        </button>
    );
}
