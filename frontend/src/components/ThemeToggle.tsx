import type { Theme } from "../hooks/useTheme";

interface ThemeToggleProps {
  theme: Theme;
  onToggle: () => void;
}

export function ThemeToggle({ theme, onToggle }: ThemeToggleProps) {
  const dark = theme === "dark";

  return (
    <button
      type="button"
      className="theme-toggle"
      role="switch"
      aria-checked={dark}
      aria-label="Dark mode"
      title={dark ? "Switch to light mode" : "Switch to dark mode"}
      onClick={onToggle}
    >
      <span className="theme-toggle__track">
        <span className="theme-toggle__icon" aria-hidden="true">
          ☀
        </span>
        <span className="theme-toggle__icon" aria-hidden="true">
          ☾
        </span>
        <span className="theme-toggle__knob" />
      </span>
    </button>
  );
}
