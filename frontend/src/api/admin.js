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
