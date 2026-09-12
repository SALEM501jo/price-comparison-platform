import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { renderWithProviders as render } from '../../test/render';
import { API_BASE_URL } from '../../utils/constants';
import SocialButtons from './SocialButtons';

/**
 * The social sign-in buttons.
 *
 * WHAT THIS GUARDS: a button whose provider is not configured on this
 * deployment. /auth/oauth/apple/start answers 404 when there are no Apple
 * credentials, and Sign in with Apple needs a paid Apple Developer account --
 * so "Google alone" is what ships, and an Apple button rendered on faith is a
 * dead end with nothing on screen to explain it. Nothing else catches that:
 * the button draws perfectly, and only a click finds out.
 *
 * The destinations are asserted rather than the markup because they are the
 * whole contract. The start URL is a path on the API, and it is the one string
 * here that a refactor can quietly get wrong while the page still looks right.
 */

const GOOGLE = { id: 'google', start_url: '/auth/oauth/google/start' };
const APPLE = { id: 'apple', start_url: '/auth/oauth/apple/start' };

describe('<SocialButtons>', () => {
  it('draws a button only for a provider the API says is enabled', () => {
    render(<SocialButtons providers={[GOOGLE]} />);

    expect(screen.getByRole('link', { name: /Continue with Google/ })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Apple/ })).not.toBeInTheDocument();
  });

  it('gains the Apple button with no code change once it is configured', () => {
    // The point of asking the API instead of hard-coding the list: this is
    // the only difference between the shipping deployment and one with an
    // Apple Developer account.
    render(<SocialButtons providers={[GOOGLE, APPLE]} />);

    expect(screen.getAllByRole('link')).toHaveLength(2);
    expect(screen.getByRole('link', { name: /Sign in with Apple/ })).toBeInTheDocument();
  });

  it('sends each button to that provider start endpoint on the API', () => {
    render(<SocialButtons providers={[GOOGLE, APPLE]} />);

    expect(screen.getByRole('link', { name: /Google/ })).toHaveAttribute(
      'href',
      `${API_BASE_URL}/auth/oauth/google/start`,
    );
    expect(screen.getByRole('link', { name: /Apple/ })).toHaveAttribute(
      'href',
      `${API_BASE_URL}/auth/oauth/apple/start`,
    );
  });

  it('ignores a provider id it has no mark or label for', () => {
    // A new provider added server-side reaches this list before the frontend
    // knows about it. Dropping it beats rendering an unlabelled rectangle
    // that still navigates.
    render(<SocialButtons providers={[GOOGLE, { id: 'facebook', start_url: '/x' }]} />);
    expect(screen.getAllByRole('link')).toHaveLength(1);
  });

  it('renders nothing at all when no provider is configured', () => {
    // Not an empty divider over an empty gap: with no providers the email
    // form is the only way in, and it should look like the only way in.
    const { container } = render(<SocialButtons providers={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('holds a button-sized space while the list is still in flight', () => {
    // Rendering nothing and then buttons pushes the email form down under
    // the user's cursor. Google alone is the shipping configuration, so
    // reserving one button height makes the swap a replacement, not a jump.
    const { container } = render(<SocialButtons providers={null} />);

    expect(screen.queryAllByRole('link')).toHaveLength(0);
    expect(container.querySelector('.animate-pulse')).toBeTruthy();
  });

  it('keeps the divider away from a screen reader', () => {
    // A lone "or" announced between two groups a screen reader cannot see
    // conveys nothing. The buttons and the form already name themselves.
    render(<SocialButtons providers={[GOOGLE]} />);
    expect(screen.getByText('or').closest('[aria-hidden="true"]')).toBeTruthy();
  });

  it('reads in Arabic, with the brand names still in Latin', () => {
    // Arabic is the default locale, so an untranslated label is the version
    // most visitors actually see. Both companies require their name
    // unaltered, so this asserts the label is translated AROUND the mark
    // rather than asserting there is no Latin at all.
    const { container } = render(<SocialButtons providers={[GOOGLE, APPLE]} />, {
      locale: 'ar',
    });

    const labels = [...container.querySelectorAll('a')].map((a) => a.textContent);
    expect(labels).toHaveLength(2);
    for (const label of labels) {
      expect(label).toMatch(/\p{Script=Arabic}/u);
    }
    expect(labels.join(' ')).toContain('Google');
    expect(labels.join(' ')).toContain('Apple');
  });

  it('keeps the mark on the leading side in either direction', () => {
    // Physical margins are what break this: an ms-/me- pair or a gap is
    // direction-aware, an ml-2 pins the mark to the left of an Arabic label.
    // The mark leads in the DOM, so flex + gap puts it on the right in RTL.
    render(<SocialButtons providers={[GOOGLE]} />, { locale: 'ar' });

    const link = screen.getByRole('link');
    expect(link.firstElementChild.tagName.toLowerCase()).toBe('svg');
    expect(link.className).not.toMatch(/\b[mp][lr]-/);
  });
});
