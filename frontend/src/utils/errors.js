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
