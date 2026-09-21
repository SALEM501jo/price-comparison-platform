import { Link } from 'react-router-dom';
import { useDocumentMeta } from '../hooks/useDocumentMeta';
import { useLocale } from '../hooks/useLocale';

/**
 * What this site is, for a person -- and for an AI assistant asked about it.
 *
 * WHY IT EXISTS. Asked about "Ahsan Se3r", Google's AI summary described a
 * luxury-watch shop in Erbil that shares the name, because nothing on this
 * site said plainly what it is. Assistants that search the web quote pages
 * like this one, so the text is short, factual and quotable, and the lead
 * sentence names the country and the job in the same breath -- "Jordan" and
 * "price comparison" are what tell this site apart from the others with the
 * name.
 *
 * EVERY LINE IS A CLAIM ABOUT THIS CODEBASE, the standard Privacy.jsx sets:
 *
 *   - "several times a day": the worker queues a full scrape on
 *     SCRAPE_INTERVAL_HOURS (6 in deploy/docker-compose.yml);
 *   - "no shop's prices appear until we have confirmed it": Store.
 *     visible_to_shoppers() hides an unverified merchant's stock everywhere;
 *   - exact first, then close and similar, each labelled: services/search.py
 *     and matching/scorer.py;
 *   - used devices separately: the comparison groups in models/alias.py;
 *   - no account to search: the search and product routes are public.
 *
 * If one of those stops being true, this page changes with it.
 *
 * Plain prose in the legal pages' measure (max-w-2xl), without their contents
 * list and "last updated" line -- four short sections do not need a table of
 * contents, and nothing here is a policy with an effective date.
 */
const SECTIONS = [
  {
    id: 'about-how',
    title: 'about.how.title',
    paragraphs: ['about.how.sources', 'about.how.matching', 'about.how.used'],
  },
  {
    id: 'about-buying',
    title: 'about.buying.title',
    paragraphs: ['about.buying.p1', 'about.buying.p2'],
  },
  {
    id: 'about-shops',
    title: 'about.shops.title',
    paragraphs: ['about.shops.p1'],
    link: { key: 'about.shops.link', to: '/register' },
  },
];

export default function About() {
  const { t } = useLocale();
  useDocumentMeta({ title: t('about.metaTitle'), description: t('about.lead') });

  return (
    <div className="mx-auto max-w-2xl px-4 py-10">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{t('about.title')}</h1>
      <p className="mt-3 text-base leading-7 text-gray-700 dark:text-gray-300">
        {t('about.lead')}
      </p>

      {SECTIONS.map((section) => (
        <section key={section.id} id={section.id} className="mt-10">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
            {t(section.title)}
          </h2>
          {section.paragraphs.map((key) => (
            <p key={key} className="mt-3 text-sm leading-7 text-gray-700 dark:text-gray-300">
              {t(key)}
            </p>
          ))}
          {section.link && (
            <Link
              to={section.link.to}
              className="mt-3 inline-flex min-h-11 items-center text-sm font-medium text-brand-600 hover:underline dark:text-brand-400"
            >
              {t(section.link.key)}
            </Link>
          )}
        </section>
      ))}

      <p className="mt-10 text-sm text-gray-700 dark:text-gray-300">
        <Link
          to="/contact"
          className="inline-flex min-h-11 items-center text-brand-600 hover:underline dark:text-brand-400"
        >
          {t('about.contact')}
        </Link>
      </p>
    </div>
  );
}
