import { screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders as render } from '../../test/render';
import { getAuthProviders } from '../../api/auth';
import SocialSignIn from './SocialSignIn';

/**
 * The half that asks the API which providers exist.
 *
 * WHAT THIS GUARDS: the login form going down with social sign-in. The buttons
 * are the alternative route in, never the route -- so an unreachable
 * /auth/providers has to cost the user the buttons and nothing else. An error
 * box thrown over a password form that still works, or a component that
 * throws, would take the whole page with it for a feature that is optional by
 * construction.
 *
 * This is the one place in the frontend suite that mocks the API, because the
 * behaviour under test IS the request: what is drawn before the answer, and
 * what is drawn when the answer never comes.
 */

vi.mock('../../api/auth', () => ({ getAuthProviders: vi.fn() }));

beforeEach(() => {
  vi.mocked(getAuthProviders).mockReset();
});

describe('<SocialSignIn>', () => {
  it('draws only what the API reports as enabled', async () => {
    getAuthProviders.mockResolvedValue([
      { id: 'google', start_url: '/auth/oauth/google/start' },
    ]);

    render(<SocialSignIn />);

    expect(await screen.findByRole('link', { name: /Google/ })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Apple/ })).not.toBeInTheDocument();
  });

  it('holds the space instead of flashing buttons in', async () => {
    // A never-resolving promise is the honest model of a slow network. What
    // must not happen is an empty block that later shoves the email form
    // down under the pointer.
    getAuthProviders.mockReturnValue(new Promise(() => {}));

    const { container } = render(<SocialSignIn />);

    expect(container.querySelector('.animate-pulse')).toBeTruthy();
    expect(screen.queryAllByRole('link')).toHaveLength(0);
  });

  it('disappears quietly when the list cannot be fetched', async () => {
    // Not an error box: the email form below is untouched and still works,
    // and telling someone their sign-in is broken when it is not is worse
    // than showing them one button fewer.
    getAuthProviders.mockRejectedValue(new Error('network'));

    const { container } = render(<SocialSignIn />);

    await waitFor(() => expect(container).toBeEmptyDOMElement());
  });

  it('asks with an abort signal so a quick unmount cancels the request', () => {
    getAuthProviders.mockResolvedValue([]);

    const { unmount } = render(<SocialSignIn />);
    const { signal } = getAuthProviders.mock.calls[0][0];

    expect(signal.aborted).toBe(false);
    unmount();
    expect(signal.aborted).toBe(true);
  });
});
