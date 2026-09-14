import { renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { LocaleProvider } from './LocaleContext';
import { useLocale } from '../hooks/useLocale';

/**
 * t(key, vars) fills values that nobody here wrote: search queries from a
 * link, product names from scrapers and shop owners. It used replaceAll per
 * variable, which treated `$&` in a value as "the matched text" and filled a
 * placeholder that arrived inside an earlier value.
 */

const wrapper = ({ children }) => <LocaleProvider>{children}</LocaleProvider>;

function translator() {
  window.localStorage.setItem('locale', 'en');
  return renderHook(() => useLocale(), { wrapper }).result.current.t;
}

afterEach(() => window.localStorage.clear());

describe('t() substitution', () => {
  it('treats $ in a value as a dollar sign', () => {
    const t = translator();
    expect(t('search.resultsFor', { query: 'iPhone $& $$ $\'' })).toContain('iPhone $& $$ $\'');
  });

  it('never fills a placeholder that arrived inside a value', () => {
    const t = translator();
    const out = t('browse.showingOf', { shown: '{total}', total: 99 });
    expect(out).toContain('{total}');
  });
});
