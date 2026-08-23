import api from './axios';

const storeTokens = ({ access_token, refresh_token }) => {
  localStorage.setItem('access_token', access_token);
  localStorage.setItem('refresh_token', refresh_token);
};

const clearTokens = () => {
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
};

export const register = async (email, password) => {
  const { data } = await api.post('/auth/register', { email, password });
  storeTokens(data);
  return data;
};

export const login = async (email, password) => {
  const { data } = await api.post('/auth/login', { email, password });
  storeTokens(data);
  return data;
};

/**
 * Log out on the server, then locally.
 *
 * Clearing localStorage alone only makes THIS browser forget the tokens -- the
 * refresh token stays valid on the server for its full 7 days, so anyone who
 * copied it (shared machine, XSS, a synced backup) keeps a working session
 * after the user believes they signed out. POST /auth/logout revokes it.
 *
 * Local state is cleared regardless of the call's outcome: a user who clicks
 * logout must end up logged out even if the network is down.
 */
export const logout = async () => {
  try {
    await api.post('/auth/logout');
  } catch {
    // Already expired, revoked, or unreachable -- nothing more to do here.
  } finally {
    clearTokens();
  }
};

export const getMe = async () => {
  const { data } = await api.get('/auth/me');
  return data;
};
