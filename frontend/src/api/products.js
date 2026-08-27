import api from './axios';

/**
 * Search products, grouped by how well they match the query.
 *
 * Returns the backend's tiered shape:
 *   {
 *     interpretation: { query, category, attributes, structured },
 *     exact:   [ ...MatchedProduct ],
 *     close:   [ ... ],
 *     similar: [ ... ],
 *     total:   number
 *   }
 *
 * Each product carries match_score, match_tier and `differences` -- the
 * plain-English reasons it is not an exact match, e.g.
 * "different colour (blue, not black)".
 */
export const searchProducts = async (query, options = {}, config = {}) => {
  const { sort, page, limit, category } = options;
  const { data } = await api.get('/products/search', {
    params: {
      q: query,
      ...(sort ? { sort } : {}),
      ...(page ? { page } : {}),
      ...(limit ? { limit } : {}),
      ...(category ? { category } : {}),
    },
    ...config, // carries an AbortSignal so stale requests can be cancelled
  });
  return data;
};

export const getProduct = async (productId, config = {}) => {
  const { data } = await api.get(`/products/${productId}`, config);
  return data;
};

export const getPriceHistory = async (productId, config = {}) => {
  const { data } = await api.get(`/products/${productId}/history`, config);
  return data;
};

/**
 * Products where shopping around saves the most.
 *
 * Not a discount off a list price -- we have no list price. It is the gap
 * between the cheapest and dearest shop selling the same thing right now.
 */
export const getDeals = async (limit = 8, config = {}) => {
  const { data } = await api.get('/products/deals', { ...config, params: { limit } });
  return data;
};
