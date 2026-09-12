import { useEffect, useState } from 'react';
import { getAuthProviders } from '../../api/auth';
import SocialButtons from './SocialButtons';

/**
 * Asks the API which social sign-ins work here, and draws them.
 *
 * The list is fetched rather than hard-coded because Sign in with Apple needs
 * a paid Apple Developer account: this site ships with Google alone, and the
 * Apple button has to appear the day the credentials are configured without a
 * frontend change. A button for a provider that is not configured leads to a
 * bare 404.
 *
 * Split from SocialButtons so the visible half can be unit-tested with props
 * instead of a mocked network, which is how every other tested component in
 * this codebase is arranged.
 */
export default function SocialSignIn() {
  // null, not [], until the answer arrives: the two are drawn differently.
  // [] hides the block entirely, so starting there would show the email form
  // alone and then push it down a moment later.
  const [providers, setProviders] = useState(null);

  useEffect(() => {
    const controller = new AbortController();

    // Defined inside the effect rather than as a useCallback: the lint rule
    // react-hooks/set-state-in-effect flags a callback that setStates being
    // invoked straight from an effect body.
    const load = async () => {
      try {
        setProviders(await getAuthProviders({ signal: controller.signal }));
      } catch (err) {
        if (err.code === 'ERR_CANCELED') return;
        // Deliberately silent. Social sign-in is the alternative route, not
        // the route: an unreachable /auth/providers must cost the user the
        // buttons, not an error box over a login form that still works.
        setProviders([]);
      }
    };

    load();
    return () => controller.abort();
  }, []);

  return <SocialButtons providers={providers} />;
}
