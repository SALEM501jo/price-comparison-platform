import { describe, expect, it } from 'vitest';
import { resolveApiBaseUrl } from './constants';

/**
 * Where the browser sends API requests.
 *
 * THE REGRESSION THIS GUARDS shipped in the first production build: with no
 * VITE_API_URL set, the base fell back to http://localhost:8000 regardless of
 * the kind of build. The deployed page rendered its frame and nothing else --
 * no products, no deals, no session refresh, no merchant photos -- because a
 * visitor's browser has nothing on localhost and the CSP blocks it anyway.
 * Every API check made with curl passed throughout, since curl never runs the
 * built JavaScript. So this pins the rule directly.
 */
describe('resolveApiBaseUrl', () => {
  it('uses the same origin in a production build', () => {
    // The API serves the built app from its own domain, so requests must be
    // relative. Anything with a hostname in it is the bug coming back.
    expect(resolveApiBaseUrl({ PROD: true })).toBe('');
  });

  it('points at the separate API process in development', () => {
    expect(resolveApiBaseUrl({ PROD: false })).toBe('http://localhost:8000');
  });

  it('lets an explicit VITE_API_URL override either default', () => {
    expect(resolveApiBaseUrl({ PROD: true, VITE_API_URL: 'https://api.example.com' })).toBe(
      'https://api.example.com',
    );
    expect(resolveApiBaseUrl({ PROD: false, VITE_API_URL: 'https://api.example.com' })).toBe(
      'https://api.example.com',
    );
  });

  it('honours an explicit empty VITE_API_URL as same-origin, not as unset', () => {
    // A falsy check would treat "" as missing and fall through to localhost in
    // development -- the exact confusion between "empty" and "absent" that
    // produced the original bug.
    expect(resolveApiBaseUrl({ PROD: false, VITE_API_URL: '' })).toBe('');
  });
});
