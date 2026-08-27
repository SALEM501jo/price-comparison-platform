import api from './axios';

// --- The merchant's own store ---
//
// None of these take a store id. The server resolves the store from the
// signed-in account, so there is no id for this client to get wrong and no
// id for anyone to tamper with.

export const registerStore = async (payload) => {
  const { data } = await api.post('/merchant/store', payload);
  return data;
};

export const getMyStore = async (config = {}) => {
  const { data } = await api.get('/merchant/store', config);
  return data;
};

export const updateMyStore = async (payload) => {
  const { data } = await api.patch('/merchant/store', payload);
  return data;
};

// --- Listings ---

export const getMyListings = async (config = {}) => {
  const { data } = await api.get('/merchant/listings', config);
  return data;
};

export const createListing = async (payload) => {
  const { data } = await api.post('/merchant/listings', payload);
  return data;
};

export const updateListing = async (listingId, payload) => {
  const { data } = await api.patch(`/merchant/listings/${listingId}`, payload);
  return data;
};

export const deleteListing = async (listingId) => {
  await api.delete(`/merchant/listings/${listingId}`);
};

// --- Admin-side verification ---

export const getStores = async ({ pendingOnly = false } = {}, config = {}) => {
  const { data } = await api.get('/admin/stores', {
    ...config,
    params: { pending_only: pendingOnly },
  });
  return data;
};

export const verifyStore = async (storeId) => {
  const { data } = await api.post(`/admin/stores/${storeId}/verify`);
  return data;
};

export const unverifyStore = async (storeId) => {
  const { data } = await api.post(`/admin/stores/${storeId}/unverify`);
  return data;
};

/** Everything one store lists — for an admin reviewing a claim. */
export const getStoreListings = async (storeId, config = {}) => {
  const { data } = await api.get(`/admin/stores/${storeId}/listings`, config);
  return data;
};
