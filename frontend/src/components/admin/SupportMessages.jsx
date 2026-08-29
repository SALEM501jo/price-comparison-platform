import { useEffect, useState } from 'react';
import { getSupportMessages, setSupportMessageHandled } from '../../api/admin';
import { extractApiError } from '../../utils/errors';

/**
 * Messages sent through the contact form.
 *
 * WHY THIS SCREEN HAD TO EXIST: the contact form has always stored its
 * messages -- the row is the record and the email is only a notification about
 * it -- but nothing ever read them back. In development the console mail
 * backend throws the notification away, and SUPPORT_EMAIL is optional in
 * production, so for anyone without SMTP wired up a support request went into
 * the database and was never seen by a human. That is worse than having no
 * contact form at all, because the person who wrote in is waiting.
 *
 * The reply-to address is shown separately from the account, because they are
 * deliberately allowed to differ: somebody locked out of their account writes
 * in from whatever address they can still reach.
 */
export default function SupportMessages() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [showHandled, setShowHandled] = useState(false);

  const load = (includeHandled) => {
    getSupportMessages(includeHandled ? {} : { handled: false })
      .then(setData)
      .catch((err) =>
        setError(extractApiError(err, 'Could not load the messages.')),
      );
  };

  useEffect(() => {
    load(showHandled);
  }, [showHandled]);

  const toggle = async (message) => {
    try {
      await setSupportMessageHandled(message.id, !message.handled);
      load(showHandled);
    } catch (err) {
      setError(extractApiError(err, 'Could not update that message.'));
    }
  };

  const messages = data?.messages ?? [];

  return (
    <section className="mb-8">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
          Contact messages
          {data?.unhandled > 0 && (
            <span className="ml-2 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800 dark:bg-amber-900/40 dark:text-amber-300">
              {data.unhandled} unread
            </span>
          )}
        </h2>
        <label className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
          <input
            type="checkbox"
            checked={showHandled}
            onChange={(e) => setShowHandled(e.target.checked)}
          />
          Show handled
        </label>
      </div>

      {error && (
        <p className="mb-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
          {error}
        </p>
      )}

      {messages.length === 0 ? (
        <p className="rounded-lg border border-dashed border-gray-300 px-4 py-6 text-center text-sm text-gray-500 dark:border-gray-700 dark:text-gray-400">
          Nothing waiting.
        </p>
      ) : (
        <ul className="space-y-2">
          {messages.map((message) => (
            <li
              key={message.id}
              className={`rounded-lg border p-3 ${
                message.handled
                  ? 'border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900'
                  : 'border-amber-200 bg-amber-50/60 dark:border-amber-900/50 dark:bg-amber-950/30'
              }`}
            >
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <div className="min-w-0">
                  <span className="font-medium text-gray-900 dark:text-white">
                    {message.subject || 'No subject'}
                  </span>
                  {/* mailto, because replying is the whole point of the
                      screen and retyping the address invites a typo. */}
                  <a
                    href={`mailto:${message.email}?subject=${encodeURIComponent(
                      `Re: ${message.subject || 'your message'}`,
                    )}`}
                    className="ml-2 text-sm text-brand-600 hover:underline dark:text-brand-400"
                  >
                    {message.email}
                  </a>
                  {message.account_email &&
                    message.account_email !== message.email && (
                      <span className="ml-2 text-xs text-gray-400 dark:text-gray-500">
                        (account: {message.account_email})
                      </span>
                    )}
                </div>
                <button
                  type="button"
                  onClick={() => toggle(message)}
                  className="shrink-0 rounded-md border border-gray-300 px-2.5 py-1 text-xs font-medium text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800"
                >
                  {message.handled ? 'Reopen' : 'Mark handled'}
                </button>
              </div>
              <p className="mt-2 whitespace-pre-wrap text-sm text-gray-700 dark:text-gray-300">
                {message.body}
              </p>
              <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
                {new Date(message.created_at).toLocaleString()}
              </p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
