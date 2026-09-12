import { screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { renderWithProviders as render } from '../../test/render';
import Footer from './Footer';
import Privacy from '../../pages/Privacy';
import Terms from '../../pages/Terms';

/**
 * The footer and the two pages it is the only route to.
 *
 * NOTHING ELSE LINKS HERE. The privacy policy and the terms are reachable
 * from exactly one place in the whole app, so a footer link that loses its
 * destination does not degrade the site -- it removes the policy from it, and
 * every page still renders perfectly while it happens. That is why the
 * assertions are on hrefs and on ids, not on whether something drew.
 *
 * The account-deletion assertions are here for a different reason: the policy
 * promises a delete button that a separate piece of work builds. A promise
 * and its implementation living in different files is exactly the pair that
 * drifts apart quietly, so the promise is pinned to the route.
 */

const show = (ui, options) => render(<MemoryRouter>{ui}</MemoryRouter>, options);

describe('<Footer>', () => {
  it('points each link at the page it names', () => {
    show(<Footer />);

    expect(screen.getByRole('link', { name: 'Privacy' })).toHaveAttribute(
      'href',
      '/privacy',
    );
    expect(screen.getByRole('link', { name: 'Terms' })).toHaveAttribute('href', '/terms');
    expect(screen.getByRole('link', { name: 'Contact us' })).toHaveAttribute(
      'href',
      '/contact',
    );
  });

  it('says the site is not a shop', () => {
    // The single most common wrong assumption about this product: people
    // wait for a cart. The footer is where that is answered on every page.
    show(<Footer />);
    expect(screen.getByText(/We sell nothing/i)).toBeInTheDocument();
  });

  it('reads entirely in Arabic for an Arabic reader', () => {
    // Arabic is the default locale, so an untranslated footer would be the
    // version most visitors actually see. Asserted as "no Latin letters"
    // rather than as pinned strings, so rewording the copy is not a
    // false regression.
    const { container } = show(<Footer />, { locale: 'ar' });

    expect(container.textContent).not.toMatch(/[A-Za-z]/);
    expect(container.querySelectorAll('a')).toHaveLength(3);
  });

  it('keeps the same destinations in either language', () => {
    const { container } = show(<Footer />, { locale: 'ar' });
    const hrefs = [...container.querySelectorAll('a')].map((a) => a.getAttribute('href'));
    expect(hrefs).toEqual(['/privacy', '/terms', '/contact']);
  });
});

describe('<Privacy>', () => {
  it('tells the reader how to delete their account, and where', () => {
    // The policy claims a right the account page has to honour. If that page
    // moves or never ships, this fails instead of the promise quietly
    // becoming false.
    show(<Privacy />);

    // getAll, not get: the policy speaks about deletion in more than one
    // place -- the right itself, and what happens to a linked Google or Apple
    // sign-in. The link below is the real guard here; this only checks the
    // right is stated at all.
    expect(screen.getAllByText(/Deleting your account/i).length).toBeGreaterThan(0);
    expect(
      screen.getByRole('link', { name: /Open your account page to delete/i }),
    ).toHaveAttribute('href', '/account');
  });

  it('is honest about what survives a deletion', () => {
    // Support messages outlive the account on purpose. A policy that omits
    // that is inaccurate, not merely incomplete.
    show(<Privacy />);
    expect(screen.getByText(/What survives deletion/i)).toBeInTheDocument();
  });

  it('explains the cookies rather than asking consent for them', () => {
    show(<Privacy />);
    expect(screen.getByText(/no cookie consent banner/i)).toBeInTheDocument();
  });

  it('renders in Arabic too', () => {
    const { container } = show(<Privacy />, { locale: 'ar' });
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(/\p{Script=Arabic}/u);
    expect(container.querySelectorAll('h2').length).toBeGreaterThan(5);
  });

  it('shows the operator the blanks it cannot fill in for them', () => {
    // An unfilled placeholder that ships is worse than a missing policy, so
    // it gets a panel at the top rather than a marker inside paragraph nine.
    show(<Privacy />);
    const notice = screen.getByRole('note');
    expect(within(notice).getByText(/Legal name of the entity/i)).toBeInTheDocument();
    expect(within(notice).getByText(/Email address for data requests/i)).toBeInTheDocument();
  });

  it('has a contents entry for every section, and a section for every entry', () => {
    // A mistyped anchor scrolls nowhere and looks exactly like a working
    // link. Nothing else would catch it.
    expectContentsResolve(show(<Privacy />).container);
  });
});

describe('<Terms>', () => {
  it('says the platform sells nothing and takes no payment', () => {
    show(<Terms />);
    expect(screen.getByText(/We are not a shop/i)).toBeInTheDocument();
  });

  it("tells a shopper the shop's own price is the one that counts", () => {
    // Prices here are scraped or merchant-entered and can be stale. This is
    // the sentence that keeps a wrong price from becoming a promise.
    show(<Terms />);
    expect(screen.getByText(/price that counts is the shop/i)).toBeInTheDocument();
  });

  it('makes photo ownership a condition of listing', () => {
    show(<Terms />);
    expect(screen.getByText(/a photo you upload is yours/i)).toBeInTheDocument();
  });

  it('lets a merchant leave, and says so with a link', () => {
    show(<Terms />);
    expect(screen.getByRole('link', { name: /Open your account page/i })).toHaveAttribute(
      'href',
      '/account',
    );
  });

  it('renders in Arabic too', () => {
    const { container } = show(<Terms />, { locale: 'ar' });
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(/\p{Script=Arabic}/u);
    expect(container.querySelectorAll('h2').length).toBeGreaterThan(5);
  });

  it('has a contents entry for every section, and a section for every entry', () => {
    expectContentsResolve(show(<Terms />).container);
  });
});

/** Every in-page anchor in the contents list lands on a heading that exists. */
function expectContentsResolve(container) {
  const anchors = [...container.querySelectorAll('a[href^="#"]')];
  expect(anchors.length).toBeGreaterThan(5);

  const targets = anchors.map((a) => a.getAttribute('href').slice(1));
  for (const id of targets) {
    expect(container.querySelector(`#${id}`), `nothing on the page has id ${id}`).toBeTruthy();
  }
  expect(container.querySelectorAll('section[id]')).toHaveLength(targets.length);
}
