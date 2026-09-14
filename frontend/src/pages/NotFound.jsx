import { Link } from 'react-router-dom';
import { useDocumentMeta } from '../hooks/useDocumentMeta';
import { useLocale } from '../hooks/useLocale';

export default function NotFound() {
  const { t } = useLocale();
  // The server answers an unknown path with the app and a 200, not a 404, so
  // to a crawler this is a real page that happens to say "not found" -- a
  // soft 404. noindex is the only way this page can say what the status
  // code does not.
  useDocumentMeta({ title: t('common.notFound'), noindex: true });

  return (
    <div className="mx-auto max-w-4xl px-4 py-16 text-center">
      <h1 className="text-xl font-semibold text-gray-900 dark:text-white">
        {t('common.notFound')}
      </h1>
      <Link
        to="/"
        className="mt-2 inline-flex min-h-11 items-center text-brand-600 hover:underline dark:text-brand-400"
      >
        {t('common.backHome')}
      </Link>
    </div>
  );
}
