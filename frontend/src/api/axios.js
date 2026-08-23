import axios from 'axios';
import { API_BASE_URL } from '../utils/constants';

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10000,
  headers: { 'Content-Type': 'application/json' },
});

// Endpoints where a 401 means "those credentials are wrong", NOT "your access
// token expired". Refreshing on these is wrong twice over: it fires a pointless
// request on every failed login, and when the refresh also fails the handler
// below used to hard-redirect — reloading the page and destroying the error
// message before the user could read it.
const NO_REFRESH_PATHS = ['/auth/login', '/auth/register', '/auth/refresh'];

const isAuthEndpoint = (url = '') => NO_REFRESH_PATHS.some((p) => url.includes(p));

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// A single in-flight refresh shared by every waiting request. Without this,
// five concurrent 401s start five refreshes; the first rotates the token and
// the rest fail against a token that is no longer current.
let refreshPromise = null;

function refreshAccessToken() {
  if (!refreshPromise) {
    const refreshToken = localStorage.getItem('refresh_token');
    if (!refreshToken) return Promise.reject(new Error('No refresh token'));

    // Plain axios, not `api`: going through this instance would re-enter the
    // interceptor and recurse if the refresh itself returned 401.
    refreshPromise = axios
      .post(`${API_BASE_URL}/auth/refresh`, { refresh_token: refreshToken })
      .then(({ data }) => {
        localStorage.setItem('access_token', data.access_token);
        if (data.refresh_token) {
          localStorage.setItem('refresh_token', data.refresh_token);
        }
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
      !isAuthEndpoint(original.url) &&
      localStorage.getItem('refresh_token');

    if (!shouldRefresh) {
      return Promise.reject(error);
    }

    original._retry = true;

    try {
      const token = await refreshAccessToken();
      original.headers.Authorization = `Bearer ${token}`;
      return api(original);
    } catch (refreshError) {
      // The session is genuinely over. Clear it and let the caller decide what
      // to show; a hard redirect here would discard whatever the page was
      // trying to tell the user.
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      return Promise.reject(refreshError);
    }
  },
);

export default api;
