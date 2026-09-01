import { useState } from 'react';
import { useLocale } from '../../hooks/useLocale';
import { Link } from 'react-router-dom';
import { addToWishlist, createAlert } from '../../api/prices';
import { useAuth } from '../../hooks/useAuth';
import { extractApiError } from '../../utils/errors';
import { DEFAULT_CURRENCY } from '../../utils/constants';

/**
 * Save to wishlist / set a price alert.
 *
 * Both need an account, so logged-out visitors get a prompt rather than a
 * button that fails with a 401 after they click it.
 */
export default function ProductActions({ productId, lowestTotal }) {
  const { t } = useLocale();
  const { isAuthenticated } = useAuth();

  const [saved, setSaved] = useState(false);
  const [savingWishlist, setSavingWishlist] = useState(false);

  const [showAlertForm, setShowAlertForm] = useState(false);
  // Default to just under the current best price -- a sensible starting point
  // and a hint about what the number means.
  const [target, setTarget] = useState(
    lowestTotal ? Math.floor(lowestTotal * 0.9) : '',
  );
  const [alertSet, setAlertSet] = useState(false);
  const [savingAlert, setSavingAlert] = useState(false);

  const [message, setMessage] = useState(null);

  if (!isAuthenticated) {
    return (
      <div className="rounded-lg border border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-900 px-4 py-3 text-sm text-gray-600 dark:text-gray-400">
        <Link to="/login" className="font-medium text-brand-600 dark:text-brand-400 hover:underline">
          Log in
        </Link>{' '}
        to save this product or set a price alert.
      </div>
    );
  }

  const handleSave = async () => {
    setSavingWishlist(true);
    setMessage(null);
    try {
      await addToWishlist(productId);
      setSaved(true);
    } catch (err) {
      // 409 means it is already there, which is a success from the user's
      // point of view -- they wanted it saved and it is saved.
      if (err.response?.status === 409) {
        setSaved(true);
      } else {
        setMessage(extractApiError(err, t('actions.saveError')));
      }
    } finally {
      setSavingWishlist(false);
    }
  };

  const handleCreateAlert = async (e) => {
    e.preventDefault();
    setSavingAlert(true);
    setMessage(null);
    try {
      await createAlert(productId, Number(target));
      setAlertSet(true);
      setShowAlertForm(false);
    } catch (err) {
      setMessage(extractApiError(err, t('actions.alertError')));
    } finally {
      setSavingAlert(false);
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        <button
          onClick={handleSave}
          disabled={savingWishlist || saved}
          className={`inline-flex min-h-11 items-center rounded-lg px-4 text-sm font-medium ${
            saved
              ? 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300'
              : 'bg-brand-600 text-white hover:bg-brand-700 disabled:opacity-50'
          }`}
        >
          {saved
            ? t('actions.saved')
            : savingWishlist
              ? t('actions.saving')
              : t('actions.save')}
        </button>

        {alertSet ? (
          <span className="inline-flex min-h-11 items-center rounded-lg bg-green-100 px-4 text-sm font-medium text-green-800 dark:bg-green-900/40 dark:text-green-300">
            {t('actions.alertSet')}
          </span>
        ) : (
          <button
            onClick={() => setShowAlertForm((open) => !open)}
            className="rounded-lg border border-gray-300 dark:border-gray-700 px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-50"
          >
            {showAlertForm ? t('actions.cancel') : t('actions.setAlert')}
          </button>
        )}

        {saved && (
          <Link
            to="/wishlist"
            className="self-center text-sm text-brand-600 dark:text-brand-400 hover:underline"
          >
            {t('actions.viewWishlist')}
          </Link>
        )}
        {alertSet && (
          <Link to="/alerts" className="self-center text-sm text-brand-600 dark:text-brand-400 hover:underline">
            {t('actions.viewAlerts')}
          </Link>
        )}
      </div>

      {showAlertForm && (
        <form
          onSubmit={handleCreateAlert}
          className="flex flex-wrap items-end gap-3 rounded-lg border border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-900 p-4"
        >
          <div>
            <label
              htmlFor="target-price"
              className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300"
            >
              {t('actions.tellMeBelow')}
            </label>
            <div className="flex items-center gap-2">
              <input
                id="target-price"
                type="number"
                min="1"
                step="0.01"
                value={target}
                onChange={(e) => setTarget(e.target.value)}
                required
                className="w-36 rounded-lg border border-gray-300 dark:border-gray-700 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-brand-500"
              />
              <span className="text-sm text-gray-500 dark:text-gray-400">{DEFAULT_CURRENCY}</span>
            </div>
          </div>
          <button
            type="submit"
            disabled={savingAlert}
            className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
          >
            {savingAlert ? t('actions.settingAlert') : t('actions.createAlert')}
          </button>
        </form>
      )}

      {message && (
        <p role="alert" className="text-sm text-red-600 dark:text-red-400">
          {message}
        </p>
      )}
    </div>
  );
}
