import { useState } from 'react';
import { useLocale } from '../hooks/useLocale';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import SocialSignIn from '../components/auth/SocialSignIn';
import { extractApiError, PASSWORD_RULES, passwordProblems } from '../utils/errors';

export default function Register() {
  const { t } = useLocale();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  // Which side of the platform this account is for. Defaults to buyer:
  // most signups are shoppers, and a shopper who lands on a seller flow
  // has been handed somebody else's product.
  const [accountType, setAccountType] = useState('buyer');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { register } = useAuth();
  const navigate = useNavigate();

  const touched = password.length > 0;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    // Check the API's own rules here first. Without this the user submits,
    // waits, and gets a server error for something knowable instantly.
    const problems = passwordProblems(password);
    if (problems.length > 0) {
      setError(`Password needs: ${problems.join(', ').toLowerCase()}`);
      return;
    }

    if (password !== confirmPassword) {
      setError(t('auth.passwordsDoNotMatch'));
      return;
    }

    setLoading(true);
    try {
      await register(email, password, accountType);
      navigate('/');
    } catch (err) {
      setError(extractApiError(err, t('common.error')));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-[60vh] items-center justify-center px-4">
      <div className="w-full max-w-md rounded-lg bg-white dark:bg-gray-900 p-8 shadow">
        <h2 className="mb-6 text-center text-2xl font-bold text-gray-900 dark:text-white">{t('auth.register')}</h2>

        {error && (
          <div
            role="alert"
            className="mb-4 rounded bg-red-50 dark:bg-red-950/40 px-4 py-2 text-sm text-red-600 dark:text-red-400"
          >
            {error}
          </div>
        )}

        <SocialSignIn />

        <form onSubmit={handleSubmit} className="space-y-4">
          <fieldset>
            <legend className="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-300">
              {t('auth.whatBringsYou')}
            </legend>
            <div className="grid gap-2 sm:grid-cols-2">
              {[
                {
                  value: 'buyer',
                  title: t('auth.iAmShopping'),
                  blurb: t('auth.iAmShoppingBlurb'),
                },
                {
                  value: 'merchant',
                  title: t('auth.iHaveShop'),
                  blurb: t('auth.iHaveShopBlurb'),
                },
              ].map((option) => (
                <label
                  key={option.value}
                  className={`cursor-pointer rounded-lg border p-3 text-left ${
                    accountType === option.value
                      ? 'border-brand-600 bg-brand-50 dark:border-brand-500 dark:bg-brand-900/40'
                      : 'border-gray-300 hover:bg-gray-50 dark:border-gray-700 dark:hover:bg-gray-800'
                  }`}
                >
                  <input
                    type="radio"
                    name="account_type"
                    value={option.value}
                    checked={accountType === option.value}
                    onChange={(e) => setAccountType(e.target.value)}
                    className="sr-only"
                  />
                  <span className="block text-sm font-medium text-gray-900 dark:text-white">
                    {option.title}
                  </span>
                  <span className="mt-0.5 block text-xs text-gray-500 dark:text-gray-400">
                    {option.blurb}
                  </span>
                </label>
              ))}
            </div>
          </fieldset>

          <div>
            <label htmlFor="email" className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
              {t('auth.email')}
            </label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="w-full rounded-lg border px-3 py-2 focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
          </div>

          <div>
            <label htmlFor="password" className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
              {t('auth.password')}
            </label>
            <input
              id="password"
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="w-full rounded-lg border px-3 py-2 focus:outline-none focus:ring-2 focus:ring-brand-500"
            />

            {/* Live checklist: the rules are visible as they are met, rather
                than being revealed one at a time by failed submissions. */}
            <ul className="mt-2 space-y-0.5">
              {PASSWORD_RULES.map((rule) => {
                const ok = rule.test(password);
                return (
                  <li
                    key={rule.label}
                    className={`text-xs ${
                      !touched ? 'text-gray-400' : ok ? 'text-green-600' : 'text-gray-500'
                    }`}
                  >
                    {touched && ok ? '✓' : '•'} {rule.label}
                  </li>
                );
              })}
            </ul>
          </div>

          <div>
            <label
              htmlFor="confirmPassword"
              className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300"
            >
              {t('auth.confirmPassword')}
            </label>
            <input
              id="confirmPassword"
              type="password"
              autoComplete="new-password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
              className="w-full rounded-lg border px-3 py-2 focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
            {confirmPassword.length > 0 && confirmPassword !== password && (
              <p className="mt-1 text-xs text-red-600 dark:text-red-400">{t('auth.passwordsDoNotMatch')}</p>
            )}
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full min-h-11 rounded-lg bg-brand-600 py-2 font-medium text-white hover:bg-brand-700 disabled:opacity-50"
          >
            {loading ? t('merchant.registering') : t('auth.register')}
          </button>
        </form>

        <p className="mt-4 text-center text-sm text-gray-600 dark:text-gray-400">
          {t('auth.haveAccount')}{' '}
          <Link to="/login" className="text-brand-600 dark:text-brand-400 hover:underline">
            {t('auth.login')}
          </Link>
        </p>
      </div>
    </div>
  );
}
