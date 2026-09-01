import { useEffect, useMemo, useRef, useState } from 'react';
import { useLocale } from '../../hooks/useLocale';

/**
 * Choose a photo, see it immediately, change your mind.
 *
 * WHY THE PREVIEW IS LOCAL AND INSTANT: the file is shown from the browser's
 * own copy, before anything is uploaded. A shop owner adding a listing on a
 * phone in their shop should see the picture the moment they pick it, not
 * after a round trip they may be too impatient to wait for -- and if they
 * picked the wrong one, they find out before spending their upload.
 *
 * THE CHECKS HERE ARE A COURTESY, NOT A CONTROL. The server re-decodes and
 * re-encodes every upload and enforces the same limits; nothing a browser
 * says about a file is trusted. These exist so a merchant learns their photo
 * is too big while looking at the form, rather than after submitting it.
 */

// Kept in step with services/images.py. A mismatch is not dangerous -- the
// server wins either way -- but a limit that is looser here means a merchant
// is told "fine" and then refused.
const MAX_BYTES = 8 * 1024 * 1024;
const ACCEPTED = ['image/jpeg', 'image/png', 'image/webp'];

export default function PhotoPicker({
  file,
  onPick,
  existingUrl = null,
  onRemoveExisting = null,
  disabled = false,
}) {
  const { t } = useLocale();
  const inputRef = useRef(null);
  const [error, setError] = useState(null);

  // Derived during render, revoked on the way out. `file` is a prop, so the
  // url cannot be minted in this component's own change handler -- the parent
  // can replace the file without going through it.
  //
  // The revoke is not optional: without it every re-pick leaves the previous
  // image held in memory for the life of the tab.
  const preview = useMemo(
    () => (file ? URL.createObjectURL(file) : null),
    [file],
  );
  useEffect(
    () => () => {
      if (preview) URL.revokeObjectURL(preview);
    },
    [preview],
  );

  const choose = (picked) => {
    if (!picked) return;

    if (!ACCEPTED.includes(picked.type)) {
      setError(t('photo.errorType'));
      return;
    }
    if (picked.size > MAX_BYTES) {
      setError(t('photo.errorSize', { mb: MAX_BYTES / (1024 * 1024) }));
      return;
    }
    setError(null);
    onPick(picked);
  };

  const clear = () => {
    setError(null);
    onPick(null);
    // The input keeps its value after a pick, so re-choosing the SAME file
    // fires no change event and the picker looks broken.
    if (inputRef.current) inputRef.current.value = '';
    if (!file && existingUrl && onRemoveExisting) onRemoveExisting();
  };

  const shown = preview ?? existingUrl;

  return (
    <div>
      <div className="flex items-start gap-3">
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          disabled={disabled}
          className="group relative h-24 w-24 shrink-0 overflow-hidden rounded-lg border-2 border-dashed border-gray-300 bg-gray-50 transition hover:border-brand-400 hover:bg-brand-50 disabled:opacity-50 dark:border-gray-700 dark:bg-gray-800/60 dark:hover:border-brand-600 dark:hover:bg-gray-800"
          aria-label={shown ? t('photo.change') : t('photo.add')}
        >
          {shown ? (
            <img
              src={shown}
              alt=""
              className="h-full w-full bg-white object-contain dark:bg-gray-900"
            />
          ) : (
            <span className="flex h-full w-full flex-col items-center justify-center gap-1 text-gray-400 dark:text-gray-500">
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                className="h-6 w-6"
                aria-hidden="true"
              >
                <path d="M12 5v14M5 12h14" strokeLinecap="round" />
              </svg>
              <span className="px-1 text-[11px] leading-tight">
                {t('photo.add')}
              </span>
            </span>
          )}
        </button>

        <div className="min-w-0 flex-1 pt-0.5">
          <p className="text-sm font-medium text-gray-700 dark:text-gray-300">
            {t('photo.label')}
          </p>
          <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
            {t('photo.hint', { mb: MAX_BYTES / (1024 * 1024) })}
          </p>

          {shown && (
            <div className="mt-2 flex flex-wrap gap-3">
              <button
                type="button"
                onClick={() => inputRef.current?.click()}
                disabled={disabled}
                className="text-xs font-medium text-brand-600 hover:underline disabled:opacity-50 dark:text-brand-400"
              >
                {t('photo.change')}
              </button>
              <button
                type="button"
                onClick={clear}
                disabled={disabled}
                className="text-xs font-medium text-red-600 hover:underline disabled:opacity-50 dark:text-red-400"
              >
                {t('photo.remove')}
              </button>
            </div>
          )}
        </div>
      </div>

      {error && (
        <p className="mt-2 text-xs text-red-600 dark:text-red-400" role="alert">
          {error}
        </p>
      )}

      <input
        ref={inputRef}
        type="file"
        accept={ACCEPTED.join(',')}
        className="sr-only"
        // The label is on the button that opens this; the input itself is
        // never seen, and a second visible control for one action reads as
        // two different things a merchant has to understand.
        tabIndex={-1}
        onChange={(event) => choose(event.target.files?.[0])}
      />
    </div>
  );
}
