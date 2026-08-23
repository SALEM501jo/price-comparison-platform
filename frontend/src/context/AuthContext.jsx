import { useCallback, useEffect, useState } from 'react';
import { AuthContext } from './auth-context';
import {
  login as loginApi,
  logout as logoutApi,
  register as registerApi,
  getMe,
} from '../api/auth';

const hasStoredToken = () => Boolean(localStorage.getItem('access_token'));

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);

  // Seed from whether a token exists rather than defaulting to true and
  // immediately calling setLoading(false) inside the effect. That pattern
  // triggers a cascading re-render, and eslint's react-hooks rule flags it.
  const [loading, setLoading] = useState(hasStoredToken);

  // Restore the session on a page refresh: a token in storage only proves one
  // was issued, so it has to be checked against the API before trusting it.
  useEffect(() => {
    if (!hasStoredToken()) return undefined;

    let cancelled = false;

    getMe()
      .then((data) => {
        if (!cancelled) setUser(data);
      })
      .catch(() => {
        // Expired or revoked. Clear it so the app shows a logged-out state
        // rather than retrying a token that will never work.
        if (!cancelled) logoutApi();
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

  const register = useCallback(async (email, password) => {
    const data = await registerApi(email, password);
    setUser(await getMe());
    return data;
  }, []);

  const logout = useCallback(() => {
    logoutApi();
    setUser(null);
  }, []);

  const value = {
    user,
    isAuthenticated: Boolean(user),
    isAdmin: user?.role === 'admin',
    login,
    register,
    logout,
    loading,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
