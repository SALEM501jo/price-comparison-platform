import { useState } from 'react';
import { resendVerification } from '../../api/auth';
import { useAuth } from '../../hooks/useAuth';
import { useLocale } from '../../hooks/useLocale';

/**
 * Prompt for a signed-in user who has not confirmed their address.
 *
 * Shown rather than blocking: browsing and comparing prices needs no verified
 * address, and locking a new user out of the whole app over an unclicked link
 * loses them for no security gain. What verification actually gates is
 * outbound email -- price alerts are never sent to an unconfirmed address.
 */
export default function VerifyBanner() {
  const { user, isAuthenticated } = useAuth();
  const { t } = useLocale();
  const [sent, setSent] = useState(false);
  const [sending, setSending] = useState(false);

  if (!isAuthenticated || user?.email_verified_at) return null;

  const handleResend = async () => {
    setSending(true);
    try {
      await resendVerification(user.email);
      setSent(true);
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="border-b border-amber-200 bg-amber-50 dark:border-amber-900/50 dark:bg-amber-950/40">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2 text-sm">
        <span className="text-amber-900 dark:text-amber-200">
          {t('auth.verifyBanner')}
        </span>
        {sent ? (
          <span className="font-medium text-amber-900 dark:text-amber-200">
            {t('auth.linkSent')}
          </span>
        ) : (
          <button
            onClick={handleResend}
            disabled={sending}
            className="font-medium text-amber-900 underline hover:no-underline disabled:opacity-50 dark:text-amber-200"
          >
            {sending ? t('auth.sending') : t('auth.resendLink')}
          </button>
        )}
      </div>
    </div>
  );
}
