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
        // Expired or revoked. Drop the tokens so the app shows a logged-out
        // state rather than retrying credentials that will never work. Local
        // only -- calling the API here would just 401 again.
        if (!cancelled) {
          localStorage.removeItem('access_token');
          localStorage.removeItem('refresh_token');
        }
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

  const logout = useCallback(async () => {
    // logoutApi revokes the refresh token server-side and always clears local
    // storage, so this cannot leave the UI signed in with dead credentials.
    await logoutApi();
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
