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
 * Each product carries match_score, match_tier and `differences`: one entry
 * per attribute that did not match, as
 * { attribute, label, query_value, candidate_value }. Structured rather than
 * prose so the sentence can be written in the reader's language --
 * see utils/matchDifference.js.
 */
export const searchProducts = async (query, options = {}, config = {}) => {
  const { sort, page, limit, category, correct } = options;
  const { data } = await api.get('/products/search', {
    params: {
      q: query,
      ...(sort ? { sort } : {}),
      ...(page ? { page } : {}),
      ...(limit ? { limit } : {}),
      ...(category ? { category } : {}),
      // Only sent when switching it OFF, so the ordinary request keeps the
      // cache key it has always had.
      ...(correct === false ? { correct: false } : {}),
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

/**
 * Type-ahead suggestions, drawn from the catalogue itself.
 *
 * Every suggestion is a real product, so clicking one is guaranteed to lead
 * somewhere -- and it teaches by example that stating the variant
 * ("iPhone 15 128GB Black") is what this site rewards.
 */
export const getSuggestions = async (query, config = {}) => {
  const { data } = await api.get('/products/suggest', {
    ...config,
    params: { q: query, limit: 8 },
  });
  return data;
};

/**
 * Record a shopper tapping Call, WhatsApp or Facebook on a shop's listing.
 *
 * FIRE AND FORGET, deliberately. This runs as the visitor leaves for their
 * phone app, so it must never delay or block that -- and a failure here is a
 * missing row in an analytics table, not something worth interrupting
 * somebody's purchase for. Errors are swallowed for the same reason.
 */
export const recordContactTap = async (storeId, productId, channel) => {
  try {
    await api.post('/products/contact-event', {
      store_id: storeId,
      product_id: productId ?? null,
      channel,
    });
  } catch {
    // Analytics must never break the thing being measured.
  }
};
