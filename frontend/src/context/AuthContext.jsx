import { useCallback, useEffect, useState } from 'react';
import { AuthContext } from './auth-context';
import { clearAccessToken, refreshAccessToken } from '../api/axios';
import {
  login as loginApi,
  logout as logoutApi,
  register as registerApi,
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
    loading,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
