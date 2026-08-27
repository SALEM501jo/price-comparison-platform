import { describe, expect, it } from 'vitest';
import { describeAttributes, formatPrice, formatStoreCount } from './format';
import { extractApiError, passwordProblems } from './errors';
import translations from '../i18n/translations';

describe('formatPrice', () => {
  it('formats to two decimals with the currency', () => {
    expect(formatPrice(877.5)).toBe('877.50 JOD');
  });

  it('returns a dash rather than NaN when there is no price', () => {
    // A product with nothing in stock has no price. That is a normal state,
    // not an error, and the old table crashed on it with .toFixed of null.
    expect(formatPrice(null)).toBe('—');
    expect(formatPrice(undefined)).toBe('—');
    expect(formatPrice(NaN)).toBe('—');
  });

  it('formats zero as a price, not as missing', () => {
    expect(formatPrice(0)).toBe('0.00 JOD');
  });
});

describe('formatStoreCount', () => {
  // The English wording now lives in the translation table, so what this
  // function still decides is WHICH key applies -- singular, plural, or the
  // out-of-stock case. That choice is the logic worth pinning; the wording
  // is content.
  const t = (key, vars) => (vars ? `${key}:${vars.count}` : key);

  it('singularises one store', () => {
    expect(formatStoreCount(1, t)).toBe('common.storeOne');
  });

  it('pluralises more than one', () => {
    expect(formatStoreCount(4, t)).toBe('common.stores:4');
  });

  it('says not in stock for zero', () => {
    expect(formatStoreCount(0, t)).toBe('common.notInStock');
  });

  it('renders real English through the actual table', () => {
    const table = translations.en;
    const real = (key, vars) =>
      Object.entries(vars ?? {}).reduce(
        (out, [name, value]) => out.replaceAll(`{${name}}`, String(value)),
        table[key],
      );
    expect(formatStoreCount(4, real)).toBe('4 stores');
    expect(formatStoreCount(1, real)).toBe('1 store');
    expect(formatStoreCount(0, real)).toBe('Not in stock');
  });

  it('has an Arabic string for every one of those keys', () => {
    for (const key of ['common.storeOne', 'common.stores', 'common.notInStock']) {
      expect(translations.ar[key], `missing Arabic for ${key}`).toBeTruthy();
    }
  });
});

describe('describeAttributes', () => {
  it('joins the attributes a shopper cares about', () => {
    expect(
      describeAttributes({ model: 'iphone 15', storage: '128gb', color: 'black' }),
    ).toBe('iphone 15 · 128gb · black');
  });

  it('drops brand, which the model already implies', () => {
    expect(describeAttributes({ brand: 'apple', model: 'iphone 15' })).toBe(
      'iphone 15',
    );
  });

  it('drops the base variant, an internal default meaning "no Pro suffix"', () => {
    expect(describeAttributes({ model: 'iphone 15', variant: 'base' })).toBe(
      'iphone 15',
    );
  });

  it('keeps a real variant', () => {
    expect(describeAttributes({ model: 'iphone 15', variant: 'pro' })).toBe(
      'iphone 15 · pro',
    );
  });

  it('handles nothing at all', () => {
    expect(describeAttributes(null)).toBe('');
  });
});

describe('extractApiError', () => {
  it('prefers the specific field message over the generic detail', () => {
    // The bug this covers: reading only `detail` showed every validation
    // failure as "Invalid input data", so the user never learned which rule
    // they broke.
    const error = {
      response: {
        data: {
          detail: 'Invalid input data',
          fields: [
            { field: 'password', message: 'Password must contain an uppercase letter' },
          ],
        },
      },
    };
    expect(extractApiError(error)).toBe('Password must contain an uppercase letter');
  });

  it('joins several field errors', () => {
    const error = {
      response: {
        data: {
          fields: [
            { field: 'email', message: 'not a valid email' },
            { field: 'password', message: 'too short' },
          ],
        },
      },
    };
    expect(extractApiError(error)).toBe('not a valid email. too short');
  });

  it('falls back to detail when there are no fields', () => {
    const error = { response: { data: { detail: 'Invalid email or password' } } };
    expect(extractApiError(error)).toBe('Invalid email or password');
  });

  it('names the real problem when the backend is unreachable', () => {
    expect(extractApiError({ code: 'ERR_NETWORK' })).toMatch(/Cannot reach the server/);
  });

  it('uses the caller fallback when the shape is unrecognised', () => {
    expect(extractApiError({}, 'Something broke')).toBe('Something broke');
  });
});

describe('passwordProblems', () => {
  it('reports every unmet rule', () => {
    expect(passwordProblems('short')).toEqual([
      'At least 8 characters',
      'One uppercase letter',
      'One number',
    ]);
  });

  it('reports nothing for a valid password', () => {
    expect(passwordProblems('DemoPass123')).toEqual([]);
  });

  it('matches the rules the API enforces', () => {
    // These duplicate the server's policy on purpose, to tell the user before
    // a round trip. If they drift, the form rejects what the API accepts.
    expect(passwordProblems('nouppercase123')).toEqual(['One uppercase letter']);
    expect(passwordProblems('NOLOWERCASE123')).toEqual(['One lowercase letter']);
    expect(passwordProblems('NoDigitsHere')).toEqual(['One number']);
  });
});
