import { render } from '@testing-library/react';
import { LocaleProvider } from '../context/LocaleContext';

/**
 * Render a component inside the providers it now depends on.
 *
 * ENGLISH IN TESTS, ARABIC IN THE PRODUCT. The site defaults to Arabic, but a
 * test that asserts on "أفضل سعر" is unreadable to anyone maintaining it from
 * the English source, and a mistranslation would look identical to a broken
 * component. Tests pin the locale to English and check behaviour; the Arabic
 * strings are content, checked by reading them, not by assertion.
 */
export function renderWithProviders(ui, { locale = 'en' } = {}) {
  window.localStorage.setItem('locale', locale);
  const result = render(<LocaleProvider>{ui}</LocaleProvider>);

  // Testing Library's own rerender replaces the WHOLE tree, providers
  // included, so a bare rerender(<Thing/>) unmounts LocaleProvider and the
  // component throws "must be used within LocaleProvider". Re-wrapping here
  // keeps rerender meaning what a caller expects: same providers, new props.
  return {
    ...result,
    rerender: (next) => result.rerender(<LocaleProvider>{next}</LocaleProvider>),
  };
}

// Deliberately NOT re-exporting all of @testing-library/react from here.
// `export *` trips the react-refresh lint rule, which cannot see whether the
// re-exported names are components, and tests import screen/within from the
// library directly anyway.
