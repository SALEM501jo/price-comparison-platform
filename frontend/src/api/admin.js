import api from './axios';

export const getStats = async (config = {}) => {
  const { data } = await api.get('/admin/stats', config);
  return data;
};

export const getUsers = async (config = {}) => {
  const { data } = await api.get('/admin/users', config);
  return data;
};

export const deleteUser = async (userId) => {
  await api.delete(`/admin/users/${userId}`);
};

/** Products whose price moved more than 50% in 24h -- possible scrape errors. */
export const getPriceAnomalies = async (config = {}) => {
  const { data } = await api.get('/admin/price-anomalies', config);
  return data;
};

/**
 * Edit ANY listing, whoever owns it.
 *
 * A separate route from the merchant's own, deliberately: the merchant route
 * resolves the store from the signed-in user and therefore cannot touch
 * someone else's data, and an `if admin` branch inside it would destroy that
 * guarantee. Every edit here is logged with the admin's id.
 */
export const adminUpdateListing = async (listingId, payload) => {
  const { data } = await api.patch(`/admin/listings/${listingId}`, payload);
  return data;
};

export const adminDeleteListing = async (listingId) => {
  await api.delete(`/admin/listings/${listingId}`);
};

// --- Contact-form messages ---
//
// The row is the record; the email is only a notification about it. Without
// this the messages went into the database and were never read by anybody.

export const getSupportMessages = async (params = {}, config = {}) => {
  const { data } = await api.get('/admin/support-messages', {
    ...config,
    params,
  });
  return data;
};

export const setSupportMessageHandled = async (messageId, handled = true) => {
  const { data } = await api.post(
    `/admin/support-messages/${messageId}/handled`,
    null,
    { params: { handled } },
  );
  return data;
};
