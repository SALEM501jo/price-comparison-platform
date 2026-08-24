import api from './axios';

// --- Wishlist ---

export const getWishlist = async (config = {}) => {
  const { data } = await api.get('/prices/wishlist', config);
  return data;
};

export const addToWishlist = async (productId) => {
  const { data } = await api.post(`/prices/wishlist/${productId}`);
  return data;
};

export const removeFromWishlist = async (productId) => {
  await api.delete(`/prices/wishlist/${productId}`);
};

// --- Price alerts ---

export const getAlerts = async (config = {}) => {
  const { data } = await api.get('/prices/alerts', config);
  return data;
};

export const createAlert = async (productId, targetPrice) => {
  const { data } = await api.post('/prices/alerts', {
    product_id: productId,
    target_price: targetPrice,
  });
  return data;
};

export const deleteAlert = async (alertId) => {
  await api.delete(`/prices/alerts/${alertId}`);
};
