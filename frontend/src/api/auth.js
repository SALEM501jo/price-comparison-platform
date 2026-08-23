import api, { clearAccessToken, setAccessToken } from './axios';

/**
 * Auth API.
 *
 * Note what is NOT here: any handling of the refresh token. It is delivered
 * and returned as an httpOnly cookie, so this layer never sees it and cannot
 * leak it. Only the short-lived access token passes through JavaScript, and
 * that is held in memory rather than written to storage.
 */

export const register = async (email, password) => {
  const { data } = await api.post('/auth/register', { email, password });
  setAccessToken(data.access_token);
  return data;
};

export const login = async (email, password) => {
  const { data } = await api.post('/auth/login', { email, password });
  setAccessToken(data.access_token);
  return data;
};

/**
 * Log out on the server, then locally.
 *
 * The server call is what actually ends the session: it revokes every refresh
 * token for the user and clears the cookie. Dropping the in-memory token alone
 * would only make this tab forget, leaving the cookie valid for its full
 * lifetime.
 *
 * Local state is cleared regardless of the outcome -- a user who clicks logout
 * must end up logged out even if the network is down.
 */
export const logout = async () => {
  try {
    await api.post('/auth/logout');
  } catch {
    // Already expired, revoked, or unreachable -- nothing more to do.
  } finally {
    clearAccessToken();
  }
};

export const getMe = async () => {
  const { data } = await api.get('/auth/me');
  return data;
};
