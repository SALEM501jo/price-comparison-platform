import { useCallback, useEffect, useMemo, useState } from 'react';
import { ThemeContext } from './theme-context';

const STORAGE_KEY = 'theme';

function initialTheme() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === 'dark' || stored === 'light') return stored;
  } catch {
    // Private mode denies localStorage; fall through to the OS preference.
  }
  // No explicit choice yet: follow the operating system. Someone whose
  // machine is in dark mode has already told us their preference once.
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches
    ? 'dark'
    : 'light';
}

/**
 * Light or dark, remembered.
 *
 * Tailwind is configured with darkMode: 'class', so the whole thing is one
 * class on <html>. index.html sets it before React mounts -- deciding here
 * alone would paint the page white and then flip it, which is worse than not
 * having the feature.
 */
export function ThemeProvider({ children }) {
  const [theme, setTheme] = useState(initialTheme);

  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark');
    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      // Choice not remembered next visit; the app still works this one.
    }
  }, [theme]);

  // Follow the OS while the visitor has never chosen for themselves. Once
  // they have, their choice wins -- changing it under them because they
  // switched their laptop to night mode would be taking it back.
  useEffect(() => {
    let stored = null;
    try {
      stored = localStorage.getItem(STORAGE_KEY);
    } catch {
      // Storage denied: treat it as "never chose", and follow the OS.
    }
    if (stored) return undefined;

    const media = window.matchMedia?.('(prefers-color-scheme: dark)');
    if (!media) return undefined;
    const onChange = (event) => setTheme(event.matches ? 'dark' : 'light');
    media.addEventListener('change', onChange);
    return () => media.removeEventListener('change', onChange);
  }, []);

  const toggleTheme = useCallback(() => {
    setTheme((current) => (current === 'dark' ? 'light' : 'dark'));
  }, []);

  const value = useMemo(
    () => ({ theme, isDark: theme === 'dark', setTheme, toggleTheme }),
    [theme, toggleTheme],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}
