import api from './axios';

/** Send a support message. Works signed in or not. */
export const sendSupportMessage = async ({ email, subject, body }) => {
  const { data } = await api.post('/support/contact', {
    email,
    subject: subject || null,
    body,
  });
  return data;
};
