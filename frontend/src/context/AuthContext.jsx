import { startTransition, useCallback, useEffect, useState } from 'react';
import { AuthContext } from './auth-context';
import { clearAccessToken, refreshAccessToken } from '../api/axios';
import {
  login as loginApi,
  logout as logoutApi,
  register as registerApi,
  deleteAccount as deleteAccountApi,
  getMe,
} from '../api/auth';

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);

  // Always true initially: the access token lives in memory and is gone after
  // a reload, so whether a session exists can only be answered by asking the
  // server. There is no token in storage to check synchronously any more --
  // which is the point.
  const [loading, setLoading] = useState(true);

  // Restore the session from the httpOnly refresh cookie. If the browser holds
  // a valid one it is exchanged for a fresh access token; if not, the request
  // 401s and the app simply renders logged out.
  useEffect(() => {
    let cancelled = false;

    refreshAccessToken()
      .then(() => getMe())
      .then((data) => {
        if (!cancelled) setUser(data);
      })
      .catch(() => {
        // No cookie, expired, or revoked. Not an error worth surfacing --
        // it is the normal state for a first-time visitor.
        if (!cancelled) clearAccessToken();
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (email, password) => {
    const data = await loginApi(email, password);
    setUser(await getMe());
    return data;
  }, []);

  const register = useCallback(async (email, password, accountType = 'buyer') => {
    const data = await registerApi(email, password, accountType);
    setUser(await getMe());
    return data;
  }, []);

  const logout = useCallback(async () => {
    // Revokes every refresh token server-side and clears the cookie, then
    // drops the in-memory access token.
    await logoutApi();
    setUser(null);
  }, []);

  /**
   * Delete the account, then forget it here.
   *
   * It lives beside logout rather than being called straight from the page,
   * because ending a session is this provider's job: a page that deleted the
   * account through the API layer alone would leave `user` populated, and the
   * navbar would go on offering the wishlist of an account that no longer
   * exists until the next reload.
   *
   * WHY THERE IS A CALLBACK, AND WHY IT IS A TRANSITION. Dropping the user
   * makes RequireAuth render <Navigate to="/login">, and the only page that
   * calls this sits behind RequireAuth. React Router puts its own location
   * change in a transition, so an ordinary setUser here is the higher-priority
   * update and commits first -- with the app still standing on the protected
   * route, which redirects somebody who has just deleted their account to a
   * login form. Scheduling both as transitions in the same tick puts them in
   * one render pass, so the app leaves the route and forgets the session
   * together. (Measured: without this the successful-deletion test lands on
   * the login page every run, not intermittently.)
   *
   * No POST /auth/logout afterwards. The row is gone, so that request would
   * 401, and the 401 interceptor would spend a refresh round trip finding out
   * that the cookie it needs was cleared by the deletion itself.
   */
  const deleteAccount = useCallback(async (email, onDeleted) => {
    await deleteAccountApi(email);
    onDeleted?.();
    startTransition(() => setUser(null));
  }, []);

  const value = {
    user,
    isAuthenticated: Boolean(user),
    isAdmin: user?.role === 'admin',
    // Admins count as merchants so they can reach the shop screens without a
    // second account -- the API takes the same view. See require_merchant.
    isMerchant: user?.role === 'merchant' || user?.role === 'admin',
    login,
    register,
    logout,
    deleteAccount,
    loading,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
