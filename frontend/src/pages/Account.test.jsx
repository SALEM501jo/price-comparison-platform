import { startTransition, useState } from 'react';
import { fireEvent, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { renderWithProviders as render } from '../test/render';
import { AuthContext } from '../context/auth-context';
import RequireAuth from '../components/auth/RequireAuth';
import Account from './Account';

/**
 * The account page, and the only irreversible action in the product.
 *
 * WHAT THIS GUARDS. Three failures, none of which any other test would see:
 *
 *  1. A confirmation that rejects the address the user actually typed. The
 *     server compares case-insensitively and ignores surrounding space
 *     precisely because a phone keyboard capitalises the first letter of the
 *     field; a button gated on an exact compare would sit dead with nothing
 *     on screen explaining why, and it would sit dead only on phones.
 *  2. Being dumped on the login page after deleting an account. The page
 *     lives behind RequireAuth, so the moment the session is forgotten the
 *     wrapper starts redirecting -- and a login form is exactly what a
 *     successful deletion must not look like.
 *  3. A confirm button reachable without the consequences having been shown.
 *     The list is the honest part; the summary is the part everybody already
 *     assumes.
 *
 * NO NETWORK IS MOCKED. The session is supplied as data through AuthContext,
 * the same way AuthCallback's tests supply it, and the harness below forgets
 * the user for real when the deletion resolves -- that state change is what
 * makes RequireAuth start racing the navigation, so faking it away would
 * remove the thing worth testing.
 */

const USER = {
  id: 7,
  email: 'sami@example.com',
  role: 'buyer',
  email_verified_at: '2026-03-04T09:00:00.000Z',
  created_at: '2026-03-04T09:00:00.000Z',
};

function Landing() {
  const { state } = useLocation();
  return <p>{state?.accountDeleted ? 'home page, account deleted' : 'home page'}</p>;
}

function Harness({ onDelete = vi.fn(), user = USER, auth = {} }) {
  const [current, setCurrent] = useState(user);

  return (
    <MemoryRouter initialEntries={['/account']}>
      <AuthContext.Provider
        value={{
          loading: false,
          user: current,
          isAuthenticated: Boolean(current),
          isAdmin: false,
          isMerchant: false,
          // Mirrors AuthProvider exactly, callback and transition included:
          // the page leaves the protected route between the network call and
          // the session being forgotten, and the forgetting is scheduled at
          // the same priority React Router gives its location change. Both
          // halves of that are what this file is here to hold in place.
          deleteAccount: async (email, onDeleted) => {
            await onDelete(email);
            onDeleted?.();
            startTransition(() => setCurrent(null));
          },
          ...auth,
        }}
      >
        <Routes>
          <Route
            path="/account"
            element={
              <RequireAuth>
                <Account />
              </RequireAuth>
            }
          />
          <Route path="/" element={<Landing />} />
          <Route path="/login" element={<p>login page</p>} />
          <Route path="/merchant" element={<p>shop page</p>} />
        </Routes>
      </AuthContext.Provider>
    </MemoryRouter>
  );
}

const show = (props = {}, options) => render(<Harness {...props} />, options);

const arm = () => fireEvent.click(screen.getByRole('button', { name: 'Delete my account' }));
const field = () => screen.getByLabelText('Your email address');
const confirm = () =>
  screen.getByRole('button', { name: 'Delete my account permanently' });
const type = (value) => fireEvent.change(field(), { target: { value } });

describe('<Account>', () => {
  it('shows what the account is before it shows how to destroy it', () => {
    show();

    expect(screen.getByText('sami@example.com')).toBeInTheDocument();
    expect(screen.getByText('Confirmed')).toBeInTheDocument();
    expect(screen.getByText('Shopper')).toBeInTheDocument();
    expect(screen.getByText('4 March 2026')).toBeInTheDocument();
  });

  it('says the address is unconfirmed instead of pretending otherwise', () => {
    show({ user: { ...USER, email_verified_at: null } });

    expect(screen.getByText('Not confirmed')).toBeInTheDocument();
    expect(screen.getByText(/only sent to a confirmed address/i)).toBeInTheDocument();
  });

  it('keeps no confirmation field on screen until deletion is asked for', () => {
    // The danger section is calm until somebody opens it. A confirm button
    // sitting in the page furniture is the version people press by accident.
    show();

    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Delete my account permanently' }),
    ).not.toBeInTheDocument();
  });

  it('lists what is deleted, what is kept and what is untouched, before confirming', () => {
    show();
    arm();

    expect(screen.getByText(/free to register again straight away/i)).toBeInTheDocument();
    expect(screen.getByText(/wishlist and every price alert/i)).toBeInTheDocument();
    expect(screen.getByText(/Every sign-in session on every device/i)).toBeInTheDocument();
    // The two nobody guesses.
    expect(screen.getByText(/Support messages you sent keep their text/i)).toBeInTheDocument();
    // Deliberately NOT worded as billing. Nothing on this platform charges a
    // merchant today, and the onboarding copy says listing is free -- a
    // deletion screen asserting shops "are billed" contradicted it on the one
    // screen where a user is deciding whether to trust what they are told.
    expect(
      screen.getByText(/tell a shop how many shoppers asked for its number/i),
    ).toBeInTheDocument();
  });

  it('leaves the confirm button dead until the account address is typed', () => {
    show();
    arm();

    expect(confirm()).toBeDisabled();

    type('');
    expect(confirm()).toBeDisabled();

    type('someone.else@example.com');
    expect(confirm()).toBeDisabled();

    // A prefix of the real address must not count either.
    type('sami@example.co');
    expect(confirm()).toBeDisabled();

    type('sami@example.com');
    expect(confirm()).toBeEnabled();
  });

  it('accepts the address a phone keyboard would have produced', () => {
    // Capitalised first letter, and a trailing space from a paste. Neither is
    // a different address, and the server accepts both -- a stricter check
    // here would block a deletion the API would have allowed.
    show();
    arm();

    type('  Sami@Example.COM  ');
    expect(confirm()).toBeEnabled();
  });

  it('sends the shopper home with word that it happened, not to the login page', async () => {
    // The session is gone the moment this resolves, and RequireAuth starts
    // redirecting to /login the render after that. Landing on a login form is
    // indistinguishable from having been signed out by a crash.
    const onDelete = vi.fn().mockResolvedValue(undefined);
    show({ onDelete });
    arm();
    type('sami@example.com');
    fireEvent.click(confirm());

    expect(await screen.findByText('home page, account deleted')).toBeInTheDocument();
    expect(screen.queryByText('login page')).not.toBeInTheDocument();
    expect(onDelete).toHaveBeenCalledWith('sami@example.com');
  });

  it('says a refused confirmation in the reader’s language, not the server’s', async () => {
    // The API answers the mismatch with an English sentence because it cannot
    // know what language the reader is in. This is the one refusal the page
    // can name itself.
    const onDelete = vi.fn().mockRejectedValue({ response: { status: 400 } });
    show({ onDelete }, { locale: 'ar' });
    fireEvent.click(screen.getByRole('button', { name: /\p{Script=Arabic}/u }));
    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: 'sami@example.com' },
    });
    fireEvent.click(screen.getAllByRole('button').find((b) => b.type === 'submit'));

    expect(await screen.findByRole('alert')).toHaveTextContent(/\p{Script=Arabic}/u);
    expect(screen.queryByText(/not the email address on this account/i)).toBeNull();
  });

  it('keeps the user on the page when the deletion fails', async () => {
    const onDelete = vi.fn().mockRejectedValue({ response: { status: 500 } });
    show({ onDelete });
    arm();
    type('sami@example.com');
    fireEvent.click(confirm());

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'We could not delete the account. Try again.',
    );
    expect(screen.queryByText('home page, account deleted')).not.toBeInTheDocument();
    expect(confirm()).toBeEnabled();
  });

  it('warns a shop owner what happens to the shop, and offers a look first', () => {
    // A merchant must not discover afterwards that the photographs are gone
    // and the shop name has been released back to whoever registers next.
    show({ auth: { isMerchant: true } });
    arm();

    expect(screen.getByText(/it is retired/i)).toBeInTheDocument();
    expect(screen.getByText(/Every product photo you uploaded is deleted/i)).toBeInTheDocument();
    expect(screen.getByText(/belong to the catalogue/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Look at your shop first' })).toHaveAttribute(
      'href',
      '/merchant',
    );
  });

  it('says nothing about a shop to somebody who has none', () => {
    show();
    arm();

    expect(screen.queryByText(/it is retired/i)).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Look at your shop first' })).toBeNull();
  });

  it('reads in Arabic for the readers who are the default', () => {
    // Asserted as "written in Arabic script" rather than as pinned strings, so
    // rewording the copy is not a false regression. The consequence list is
    // exempt: "Google" and "Apple" are Latin in both languages.
    show({}, { locale: 'ar' });

    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(/\p{Script=Arabic}/u);
    expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent(/\p{Script=Arabic}/u);
    expect(screen.getAllByRole('button')[0]).toHaveTextContent(/\p{Script=Arabic}/u);
  });

  it('writes the date in the Western digits the rest of the site uses', () => {
    // ar-JO renders Arabic-Indic numerals unless asked otherwise, and a date
    // in ٤ beside a price in 4 is two number systems on one screen. The rest
    // of the site forces Latin digits in CSS; a formatted date has to be
    // asked for them in the locale tag.
    const { container } = show({}, { locale: 'ar' });

    expect(container.textContent).not.toMatch(/[٠-٩]/);
    expect(container.textContent).toContain('2026');
  });

  it('keeps the address left-to-right inside a right-to-left page', () => {
    // An address left to the page's direction runs the domain in front of the
    // local part, which reads as a different address.
    show({}, { locale: 'ar' });
    expect(screen.getByText('sami@example.com')).toHaveAttribute('dir', 'ltr');
  });

  it('is not reachable without a session', () => {
    // Client-side gating is a convenience and the API enforces the same rule,
    // but an anonymous visitor landing on a delete-my-account form is its own
    // kind of alarming.
    show({ user: null });

    expect(screen.getByText('login page')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Your account' })).toBeNull();
  });
});
