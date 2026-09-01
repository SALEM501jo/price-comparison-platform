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

/**
 * How many shoppers asked for this shop's number.
 *
 * TAPS, not calls: a tap is someone pressing Call or WhatsApp. Whether the
 * phone rang, was answered, or led to a sale happens off this platform, and
 * every label here says so.
 */
export const getMyStats = async (config = {}) => {
  const { data } = await api.get('/merchant/stats', config);
  return data;
};

/**
 * Turn down a merchant claim.
 *
 * Not a delete: the shop, its listings and its history stay, and approving
 * later clears the rejection. It moves the claim out of the pending queue so
 * the same bad claim is not re-read on every visit.
 */
export const declineStore = async (storeId) => {
  const { data } = await api.post(`/admin/stores/${storeId}/decline`);
  return data;
};

// --- Listing photos ---
//
// PUT rather than POST: one photo per listing, so uploading again replaces
// the one that is there. That makes a retry after a dropped connection safe.
//
// The axios instance sets a JSON Content-Type on every request by default,
// which would overwrite the multipart boundary the browser needs to write.
// The request interceptor in axios.js strips it for FormData bodies -- see
// the note there; it is not something a caller should have to remember.

export const uploadListingPhoto = async (listingId, file, config = {}) => {
  const body = new FormData();
  body.append('file', file);
  await api.put(`/merchant/listings/${listingId}/photo`, body, config);
};

export const deleteListingPhoto = async (listingId) => {
  await api.delete(`/merchant/listings/${listingId}/photo`);
};

/**
 * Fetch a listing's own photo as a blob URL.
 *
 * NOT an <img src> pointing at the route. The access token lives in a module
 * variable rather than a cookie -- deliberately, so an XSS payload cannot
 * read it -- which means the browser cannot attach it to an image request it
 * makes on its own. An <img> aimed at this endpoint would simply 401.
 *
 * So the bytes come through axios, which does attach the token, and become an
 * object URL. The caller MUST revoke it when done or every re-render leaks a
 * blob for the lifetime of the tab.
 *
 * The public route has no such problem and needs no token -- but it refuses
 * to serve an unverified shop its own picture, which is exactly the shop that
 * most needs to see whether the upload worked.
 */
export const fetchMyListingPhoto = async (listingId, config = {}) => {
  const { data } = await api.get(`/merchant/listings/${listingId}/photo`, {
    ...config,
    responseType: 'blob',
  });
  return URL.createObjectURL(data);
};
