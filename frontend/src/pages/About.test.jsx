import { screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { renderWithProviders as render } from '../test/render';
import translations from '../i18n/translations';
import About from './About';

/**
 * The page an AI assistant quotes when asked what this site is.
 *
 * The copy is content and is checked by reading it; what is pinned here is
 * the part a refactor could break without anything looking wrong: that the
 * lead sentence carries the name, the country and the job, that it is also
 * what the tab and the search snippet say, and that the two ways onward --
 * opening a shop account, writing to us -- still go somewhere.
 */

const show = (options) => render(<MemoryRouter><About /></MemoryRouter>, options);

describe('<About>', () => {
  it('opens with what the site is, where, and that it is not a shop', () => {
    show();

    expect(screen.getByRole('heading', { level: 1, name: 'About Ahsan Se3r' })).toBeInTheDocument();
    expect(screen.getByText(translations.en['about.lead'])).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'We sell nothing' })).toBeInTheDocument();
  });

  it('names the site, the country and the job in its lead, in both languages', () => {
    // What separates this site from the others with the name. Both
    // spellings of the name, so either search finds the sentence.
    for (const locale of ['ar', 'en']) {
      const lead = translations[locale]['about.lead'];
      expect(lead).toContain('Ahsan Se3r');
      expect(lead).toContain('احسن سعر');
      expect(lead).toMatch(locale === 'ar' ? /الأردن/ : /Jordan/);
    }
  });

  it('keeps its lead short enough to be the search snippet whole', () => {
    for (const locale of ['ar', 'en']) {
      expect(translations[locale]['about.lead'].length).toBeLessThanOrEqual(160);
    }
  });

  it('titles the tab and describes itself with its own lead', () => {
    show();

    expect(document.title).toBe('About us — Ahsan Se3r');
    expect(document.head.querySelector('meta[name="description"]')).toHaveAttribute(
      'content',
      translations.en['about.lead'],
    );
  });

  it('sends a shop owner to sign up and anyone else to contact us', () => {
    show();

    expect(screen.getByRole('link', { name: 'Create a shop account' })).toHaveAttribute(
      'href',
      '/register',
    );
    expect(screen.getByRole('link', { name: /Write to us/ })).toHaveAttribute('href', '/contact');
  });

  it('reads entirely in Arabic for an Arabic reader, apart from the names it quotes', () => {
    // The brand's Latin spelling and the example search are deliberate; any
    // other Latin text would be an untranslated string.
    const { container } = show({ locale: 'ar' });
    const text = container.textContent
      .replaceAll('Ahsan Se3r', '')
      .replaceAll('iPhone 15 128GB Black', '');

    expect(text).not.toMatch(/[A-Za-z]/);
  });
});
