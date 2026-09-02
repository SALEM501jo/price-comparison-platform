import { useEffect, useRef, useState } from 'react';

import {
  deleteListingPhoto,
  fetchMyListingPhoto,
  uploadListingPhoto,
} from '../../api/merchant';
import { useLocale } from '../../hooks/useLocale';
import { extractPhotoError } from '../../utils/errors';

/**
 * The photo on one existing listing: see it, replace it, remove it.
 *
 * A merchant will not get every photo right on the first go -- the light was
 * bad, they photographed the wrong colour, the box is in the shot. Making
 * this fixable from the list they already use to correct prices is the
 * difference between a photo being a thing they maintain and a thing they
 * gave up on.
 *
 * The image is fetched as a blob rather than pointed at with an <img src>,
 * because the route is authenticated and the access token is not in a cookie
 * -- see fetchMyListingPhoto. That is also why this cannot be the shared
 * ProductImage component: that one loads public urls.
 */

const MAX_BYTES = 8 * 1024 * 1024;
const ACCEPTED = ['image/jpeg', 'image/png', 'image/webp'];

export default function ListingPhotoCell({ listing, onChanged }) {
  const { t } = useLocale();
  const inputRef = useRef(null);
  const [fetched, setFetched] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  // Bumped after an upload. The listing id does not change when a photo is
  // REPLACED, so without an explicit key the effect below has no reason to
  // re-run and the merchant keeps seeing the shot they just replaced.
  const [reloadKey, setReloadKey] = useState(0);

  const hasPhoto = Boolean(listing.has_photo);

  // Derived, not stored: when the photo is deleted, has_photo goes false and
  // this is null on the next render with no effect needed to clear it.
  const url = hasPhoto ? fetched : null;

  useEffect(() => {
    if (!hasPhoto) return undefined;

    let objectUrl = null;
    let cancelled = false;

    fetchMyListingPhoto(listing.id)
      .then((created) => {
        objectUrl = created;
        // The row can unmount, or the listing can lose its photo, while this
        // request is in flight. Setting state then would both warn and leak
        // the blob, since the cleanup below has already run.
        if (cancelled) {
          URL.revokeObjectURL(created);
          return;
        }
        setFetched(created);
      })
      .catch(() => {
        if (!cancelled) setFetched(null);
      });

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
    // Exactly the three things that change WHICH image this is. Re-fetching
    // on every render of the row would pull the bytes again on every price
    // keystroke.
  }, [listing.id, hasPhoto, reloadKey]);

  const upload = async (file) => {
    if (!file) return;
    if (!ACCEPTED.includes(file.type)) {
      setError(t('photo.errorType'));
      return;
    }
    if (file.size > MAX_BYTES) {
      setError(t('photo.errorSize', { mb: MAX_BYTES / (1024 * 1024) }));
      return;
    }

    setBusy(true);
    setError(null);
    try {
      await uploadListingPhoto(listing.id, file);
      onChanged({ ...listing, has_photo: true });
      // Replacing a photo leaves listing.id and has_photo untouched, so this
      // is what actually makes the new picture appear.
      setReloadKey((key) => key + 1);
    } catch (err) {
      setError(extractPhotoError(err, t));
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = '';
    }
  };

  const remove = async () => {
    setBusy(true);
    setError(null);
    try {
      await deleteListingPhoto(listing.id);
      onChanged({ ...listing, has_photo: false });
    } catch (err) {
      setError(extractPhotoError(err, t));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col items-center gap-1">
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        disabled={busy}
        aria-label={hasPhoto ? t('photo.change') : t('photo.add')}
        title={hasPhoto ? t('photo.change') : t('photo.add')}
        className="h-14 w-14 shrink-0 overflow-hidden rounded-md border border-dashed border-gray-300 bg-gray-50 transition hover:border-brand-400 disabled:opacity-50 dark:border-gray-700 dark:bg-gray-800/60 dark:hover:border-brand-600"
      >
        {url ? (
          <img
            src={url}
            alt=""
            className="h-full w-full bg-photo object-contain dark:bg-gray-900"
          />
        ) : (
          <span className="flex h-full w-full items-center justify-center text-gray-400 dark:text-gray-500">
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              className="h-5 w-5"
              aria-hidden="true"
            >
              <path d="M12 5v14M5 12h14" strokeLinecap="round" />
            </svg>
          </span>
        )}
      </button>

      {hasPhoto && (
        <button
          type="button"
          onClick={remove}
          disabled={busy}
          className="text-[11px] text-red-600 hover:underline disabled:opacity-40 dark:text-red-400"
        >
          {t('photo.remove')}
        </button>
      )}

      {error && (
        <span className="max-w-[7rem] text-center text-[11px] text-red-700 dark:text-red-300">
          {error}
        </span>
      )}

      <input
        ref={inputRef}
        type="file"
        accept={ACCEPTED.join(',')}
        className="sr-only"
        tabIndex={-1}
        onChange={(event) => upload(event.target.files?.[0])}
      />
    </div>
  );
}
