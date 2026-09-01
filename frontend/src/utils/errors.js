/**
 * Turn an API error into something worth showing a person.
 *
 * The backend returns 422 as:
 *   { detail: "Invalid input data",
 *     fields: [{ field: "password", message: "Password must contain a number" }] }
 *
 * Reading only `detail` gives "Invalid input data", which tells the user
 * nothing about what to change -- the specific reason is in `fields`.
 */
export function extractApiError(error, fallback = 'Something went wrong.') {
  if (error?.code === 'ERR_NETWORK') {
    return 'Cannot reach the server. Is the backend running?';
  }

  const data = error?.response?.data;
  if (!data) return fallback;

  if (Array.isArray(data.fields) && data.fields.length > 0) {
    return data.fields
      .map((item) => (typeof item === 'string' ? item : item.message))
      .filter(Boolean)
      .join('. ');
  }

  if (typeof data.detail === 'string') return data.detail;

  return fallback;
}

/**
 * The password rules enforced by the API, checked here too so the user is told
 * before a round trip. Kept in one place: duplicating them across the register
 * form and the API client is how the two drift apart.
 */
export const PASSWORD_RULES = [
  { test: (v) => v.length >= 8, label: 'At least 8 characters' },
  { test: (v) => /[A-Z]/.test(v), label: 'One uppercase letter' },
  { test: (v) => /[a-z]/.test(v), label: 'One lowercase letter' },
  { test: (v) => /[0-9]/.test(v), label: 'One number' },
];

export function passwordProblems(password) {
  return PASSWORD_RULES.filter((rule) => !rule.test(password)).map((r) => r.label);
}

/**
 * The reason a photo upload was refused, in the reader's language.
 *
 * The photo endpoints answer with `detail: {code, message}` rather than a
 * sentence, for the same reason match differences carry fields rather than
 * prose: the server does not know what language the shop owner reads. The
 * CODE is the contract; the message is the fallback for a code this table has
 * not caught up with.
 *
 * extractApiError deliberately returns its fallback for an object-shaped
 * detail, so it cannot be used here -- it would swallow the one thing worth
 * telling somebody, which is which of half a dozen rules their file broke.
 */
export function extractPhotoError(error, t, fallbackKey = 'photo.uploadError') {
  if (error?.code === 'ERR_NETWORK') return t('common.networkError');

  const detail = error?.response?.data?.detail;
  if (detail && typeof detail === 'object' && detail.code) {
    const key = `photo.error.${detail.code}`;
    const translated = t(key);
    if (translated !== key) return translated;
    if (typeof detail.message === 'string') return detail.message;
  }
  if (typeof detail === 'string') return detail;
  return t(fallbackKey);
}
