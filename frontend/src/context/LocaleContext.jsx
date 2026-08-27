import { useCallback, useEffect, useMemo, useState } from 'react';
import { LocaleContext } from './locale-context';
import translations, { DEFAULT_LOCALE, LOCALES } from '../i18n/translations';

const STORAGE_KEY = 'locale';

function initialLocale() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored && LOCALES[stored]) return stored;
  } catch {
    // Private mode denies localStorage. Fall through to the default rather
    // than letting a storage failure blank the whole app.
  }
  return DEFAULT_LOCALE;
}

/**
 * Language, writing direction, and the translation lookup.
 *
 * Arabic is the default, and the choice is remembered. index.html applies the
 * stored value to <html> before React mounts, so the first paint is already
 * in the right language and direction -- doing it here alone would render the
 * page in Arabic and then visibly flip it to English on load.
 */
export function LocaleProvider({ children }) {
  const [locale, setLocale] = useState(initialLocale);

  const dir = LOCALES[locale]?.dir ?? 'rtl';

  useEffect(() => {
    document.documentElement.lang = locale;
    document.documentElement.dir = dir;
    try {
      localStorage.setItem(STORAGE_KEY, locale);
    } catch {
      // Not being able to remember the choice is survivable; crashing is not.
    }
  }, [locale, dir]);

  /**
   * Look up a string, substituting {placeholders}.
   *
   * A missing key returns the key itself rather than an empty string: a
   * visible "merchant.addProduct" on the page is a bug someone reports, while
   * a blank space is a bug nobody notices.
   */
  const t = useCallback(
    (key, vars) => {
      const table = translations[locale] ?? translations[DEFAULT_LOCALE];
      let text = table[key];
      if (text === undefined) {
        text = translations[DEFAULT_LOCALE][key];
      }
      if (text === undefined) return key;
      if (!vars) return text;
      return Object.entries(vars).reduce(
        (out, [name, value]) => out.replaceAll(`{${name}}`, String(value)),
        text,
      );
    },
    [locale],
  );

  const toggleLocale = useCallback(() => {
    setLocale((current) => (current === 'ar' ? 'en' : 'ar'));
  }, []);

  const value = useMemo(
    () => ({ locale, dir, isRtl: dir === 'rtl', t, setLocale, toggleLocale }),
    [locale, dir, t, toggleLocale],
  );

  return (
    <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>
  );
}
