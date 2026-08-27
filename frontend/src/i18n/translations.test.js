import { describe, expect, it } from 'vitest';
import translations, { DEFAULT_LOCALE, LOCALES } from './translations';

/**
 * Nothing catches a missing translation until somebody sees a raw key like
 * "merchant.addProduct" printed on the page -- and because the lookup falls
 * back to the default locale, a missing English string shows Arabic to an
 * English reader instead of failing loudly. These tests are the only thing
 * standing between a half-translated build and production.
 */
describe('translations', () => {
  const locales = Object.keys(translations);

  it('covers every locale the switcher offers', () => {
    for (const code of Object.keys(LOCALES)) {
      expect(translations[code], `no table for ${code}`).toBeTruthy();
    }
  });

  it('has the same keys in every language', () => {
    const reference = new Set(Object.keys(translations[DEFAULT_LOCALE]));
    for (const code of locales) {
      if (code === DEFAULT_LOCALE) continue;
      const keys = new Set(Object.keys(translations[code]));
      const missing = [...reference].filter((key) => !keys.has(key));
      const extra = [...keys].filter((key) => !reference.has(key));
      expect(missing, `${code} is missing keys`).toEqual([]);
      expect(extra, `${code} has keys ${DEFAULT_LOCALE} does not`).toEqual([]);
    }
  });

  it('has no empty strings', () => {
    for (const code of locales) {
      for (const [key, value] of Object.entries(translations[code])) {
        expect(typeof value, `${code}.${key} is not a string`).toBe('string');
        expect(value.trim(), `${code}.${key} is empty`).not.toBe('');
      }
    }
  });

  it('uses the same placeholders in every language', () => {
    // "{count} shops" translated without its {count} silently drops the
    // number, and the sentence still reads as valid prose.
    const placeholders = (text) =>
      [...text.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();

    for (const [key, reference] of Object.entries(translations[DEFAULT_LOCALE])) {
      for (const code of locales) {
        if (code === DEFAULT_LOCALE) continue;
        expect(
          placeholders(translations[code][key]),
          `${code}.${key} placeholders differ`,
        ).toEqual(placeholders(reference));
      }
    }
  });

  it('leaves untranslated English out of the Arabic table', () => {
    // A copy-paste that never got translated is invisible in review: the app
    // renders it happily. Product names and brand words are legitimately
    // Latin, so this only flags entries that are ENTIRELY ASCII prose.
    const allowLatin = new Set([
      'brand.name',
      'common.currency',
      // Latin in the Arabic table ON PURPOSE: the switcher names the language
      // it takes you TO, so on the Arabic site the label reads "English". A
      // button labelled with the language you are already in reads as a
      // status display, and people do not press it.
      'nav.toggleLanguage',
    ]);
    const suspicious = Object.entries(translations.ar)
      .filter(([key]) => !allowLatin.has(key))
      .filter(([, value]) => /^[\x20-\x7E]+$/.test(value))
      .filter(([, value]) => /[a-zA-Z]{4,}/.test(value))
      .map(([key]) => key);

    expect(suspicious, 'these Arabic entries look like untranslated English').toEqual([]);
  });
});
