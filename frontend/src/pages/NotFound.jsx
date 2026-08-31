import { Link } from 'react-router-dom';
import { useLocale } from '../hooks/useLocale';

export default function NotFound() {
  const { t } = useLocale();
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
