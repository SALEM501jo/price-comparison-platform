import api from './axios';

/**
 * Ask the server how it reads a query and scores listings against it.
 *
 * Body: { query, listings: [{ title, store_category }], correct? }
 * Returns { query: {steps, corrections, category, attributes, weights},
 *           listings: [{ outcome, score, tier, comparisons, gate,
 *                        string_similarity, ... }] }
 *
 * The same code the search runs -- see backend/app/services/explain.py.
 */
export const explainSearch = async (body, config = {}) => {
  const { data } = await api.post('/products/explain', body, config);
  return data;
};
