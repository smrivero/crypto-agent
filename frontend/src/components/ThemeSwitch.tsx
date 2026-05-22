interface ThemeSwitchProps {
  theme: 'light' | 'dark';
  onToggle: () => void;
}

export function ThemeSwitch({ theme, onToggle }: ThemeSwitchProps) {
  return (
    <div className="theme-switch-row" title="Appearance">
      <span className="theme-switch-label" aria-hidden="true">☀</span>
      <label className="theme-switch">
        <input
          type="checkbox"
          checked={theme === 'light'}
          onChange={onToggle}
          aria-label="Light mode"
        />
        <span className="theme-switch-slider" />
      </label>
      <span className="theme-switch-label" aria-hidden="true">☾</span>
    </div>
  );
}
