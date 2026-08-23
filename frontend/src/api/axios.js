import axios from 'axios';
import { API_BASE_URL } from '../utils/constants';

/**
 * Access token storage.
 *
 * Deliberately a module variable, not localStorage. The refresh token now
 * lives in an httpOnly cookie that JavaScript cannot read, so the only thing
 * an XSS payload could steal from this app is whatever the JS layer holds --
 * and a value in memory dies with the tab rather than sitting in a store the
 * attacker can read on any future visit.
 *
 * The cost is that a page refresh loses the access token. That is fine: the
 * cookie survives, so the app exchanges it for a new one on start-up.
 */
let accessToken = null;

export const setAccessToken = (token) => {
  accessToken = token;
};

export const getAccessToken = () => accessToken;

export const clearAccessToken = () => {
  accessToken = null;
};

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10000,
  headers: { 'Content-Type': 'application/json' },
  // Required for the refresh cookie to be sent cross-origin (the app is on
  // :5173, the API on :8000). The API's CORS allow-list is what makes this
  // safe -- withCredentials against a wildcard origin is rejected by browsers.
  withCredentials: true,
});

// Endpoints where a 401 means "wrong credentials", not "expired token".
// Refreshing on these fires a pointless request on every failed login.
const NO_REFRESH_PATHS = ['/auth/login', '/auth/register', '/auth/refresh'];
const isAuthEndpoint = (url = '') => NO_REFRESH_PATHS.some((p) => url.includes(p));

api.interceptors.request.use((config) => {
  if (accessToken) {
    config.headers.Authorization = `Bearer ${accessToken}`;
  }
  return config;
});

// One in-flight refresh shared by every waiting request. Without it, five
// concurrent 401s start five refreshes; the first rotates the token and the
// rest present one that has just been burned -- which the server correctly
// treats as replay and responds to by revoking the entire session.
let refreshPromise = null;

export function refreshAccessToken() {
  if (!refreshPromise) {
    // Plain axios, not `api`: going through this instance would re-enter the
    // interceptor and recurse if the refresh itself returned 401.
    refreshPromise = axios
      .post(`${API_BASE_URL}/auth/refresh`, {}, { withCredentials: true })
      .then(({ data }) => {
        setAccessToken(data.access_token);
        return data.access_token;
      })
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config;

    const shouldRefresh =
      error.response?.status === 401 &&
      original &&
      !original._retry &&
      !isAuthEndpoint(original.url);

    if (!shouldRefresh) return Promise.reject(error);

    original._retry = true;

    try {
      const token = await refreshAccessToken();
      original.headers.Authorization = `Bearer ${token}`;
      return api(original);
    } catch (refreshError) {
      // The session is genuinely over. Clear local state and let the caller
      // decide what to show; a hard redirect here would discard whatever the
      // page was trying to tell the user.
      clearAccessToken();
      return Promise.reject(refreshError);
    }
  },
);

export default api;
