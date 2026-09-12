import api, { clearAccessToken, setAccessToken } from './axios';

/**
 * Auth API.
 *
 * Note what is NOT here: any handling of the refresh token. It is delivered
 * and returned as an httpOnly cookie, so this layer never sees it and cannot
 * leak it. Only the short-lived access token passes through JavaScript, and
 * that is held in memory rather than written to storage.
 */

export const register = async (email, password, accountType = 'buyer') => {
  // account_type is 'buyer' or 'merchant' only. The server maps it to a role
  // rather than accepting a role name, so this value can never name a
  // privileged one however it is tampered with.
  const { data } = await api.post('/auth/register', {
    email,
    password,
    account_type: accountType,
  });
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

/**
 * Delete the signed-in account. Permanent: there is no soft delete and no
 * tombstone, and the address is free to register again immediately.
 *
 * The confirmation is the account's own address rather than its password,
 * because an account created through Google has no password to type --
 * password_hash is nullable for exactly those users, so a password prompt
 * would be unusable by the people most likely to be removing a social login
 * they never meant to create. The body goes under `data` because that is the
 * only way axios sends one on a DELETE.
 *
 * THE TOKEN IS DROPPED ONLY ON SUCCESS. Clearing it in a `finally` would sign
 * out a user whose deletion was REFUSED for a mistyped address -- the one
 * outcome where they still have an account to be signed in to.
 */
export const deleteAccount = async (email) => {
  await api.delete('/auth/me', { data: { email } });
  // The server has revoked every refresh token and cleared the cookie; this
  // is the in-memory half of the same thing.
  clearAccessToken();
};

/** Redeem a verification link. Unauthenticated: the link is opened from an
 *  email client, often in a different browser from the one that signed up. */
export const verifyEmail = async (token) => {
  const { data } = await api.post('/auth/verify-email', { token });
  return data;
};

/** Request a fresh link. Always resolves — the API returns 202 whether or not
 *  the address exists, so that it cannot be used to test who has an account. */
export const resendVerification = async (email) => {
  await api.post('/auth/resend-verification', { email });
};

/** Ask for a password reset link. Always resolves -- the API never says whether the address exists. */
export const forgotPassword = async (email) => {
  const { data } = await api.post('/auth/forgot-password', { email });
  return data;
};

/** Spend a reset link. Deliberately does NOT sign the user in. */
export const resetPassword = async (token, password) => {
  const { data } = await api.post('/auth/reset-password', { token, password });
  return data;
};

/**
 * Which social sign-ins this deployment can actually complete.
 *
 * Asked rather than hard-coded because a provider with no credentials does not
 * exist as far as the API is concerned: /auth/oauth/apple/start answers 404,
 * with nothing on screen to explain it. Sign in with Apple needs a paid Apple
 * Developer account, so "Google alone" is the shipping configuration and
 * "Google and Apple" has to become true without a frontend change.
 *
 * Returns [{ id, start_url }]. start_url is a path on the API, not on the app.
 */
export const getAuthProviders = async (config = {}) => {
  const { data } = await api.get('/auth/providers', config);
  return data.providers ?? [];
};
