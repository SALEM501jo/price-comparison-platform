import api from './axios';

export const searchProducts = async (query, category = null, sortBy = 'price_asc', page = 1, limit = 20) => {
  const params = { q: query, sort_by: sortBy, page, limit };
  if (category) params.category = category;
  const { data } = await api.get('/products/search', { params });
  return data;
};

export const getProduct = async (productId) => {
  const { data } = await api.get(`/products/${productId}`);
  return data;
};

export const getPriceHistory = async (productId) => {
  const { data } = await api.get(`/products/${productId}/history`);
  return data;
};