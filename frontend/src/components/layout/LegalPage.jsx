import { Link } from 'react-router-dom';
import { useLocale } from '../../hooks/useLocale';

/**
 * The shell the privacy policy and the terms of use are both poured into.
 *
 * WHY THE MEASURE IS NARROWER THAN EVERY OTHER PAGE. These are the only two
 * pages in the app that are pure prose, and the containers the rest of the
 * site uses -- max-w-4xl for a list, max-w-6xl for a grid -- put roughly 130
 * characters on a line here. That is about twice the length an eye can track
 * back to the start of the next line, and it is why long policies go unread.
 * max-w-2xl with a 1.75 line-height lands near 80, in both scripts.
 *
 * A SECTION IS A TABLE ROW, NOT MARKUP. Each page hands over a list of
 * `{ id, title, blocks }`, where a block is one of three things:
 *
 *   'a.key'                 a paragraph
 *   ['a.key', 'b.key']      a bulleted list
 *   { key, to }             a paragraph that is a link to somewhere in the app
 *
 * so the pages stay a readable outline of the document and nothing but this
 * file knows what a policy section looks like. The ids are the anchors the
 * contents list at the top jumps to.
 */
export default function LegalPage({ title, blurb, sections, unfilled }) {
  const { t } = useLocale();

  return (
    <div className="mx-auto max-w-2xl px-4 py-10">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{t(title)}</h1>
      <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">{t(blurb)}</p>
      <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">{t('legal.updated')}</p>

      <UnfilledFields fields={unfilled} />

      <nav
        aria-label={t('legal.contents')}
        className="mt-8 rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900"
      >
        <p className="text-sm font-semibold text-gray-900 dark:text-white">
          {t('legal.contents')}
        </p>
        <ol className="mt-1 flex flex-col">
          {sections.map((section) => (
            <li key={section.id}>
              {/* A plain anchor, not a router Link: this goes to a heading on
                  the page that is already open, and routing it would push a
                  history entry for every jump. */}
              <a
                href={`#${section.id}`}
                className="inline-flex min-h-11 items-center text-sm text-brand-600 hover:underline dark:text-brand-400"
              >
                {t(section.title)}
              </a>
            </li>
          ))}
        </ol>
      </nav>

      {sections.map((section) => (
        <section key={section.id} id={section.id} className="mt-10 scroll-mt-4">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
            {t(section.title)}
          </h2>
          {section.blocks.map((block) => (
            <Block key={blockKey(block)} block={block} />
          ))}
        </section>
      ))}
    </div>
  );
}

const blockKey = (block) => {
  if (Array.isArray(block)) return block[0];
  return typeof block === 'string' ? block : block.key;
};

function Block({ block }) {
  const { t } = useLocale();

  if (Array.isArray(block)) {
    return (
      <ul className="mt-3 space-y-2.5">
        {block.map((item) => (
          <li key={item} className="flex gap-2.5 text-sm leading-7 text-gray-700 dark:text-gray-300">
            {/* A drawn dot rather than list-disc: a real marker needs padding
                on one side, and every one-sided utility in this codebase is a
                bug waiting for an Arabic reader. A flex row has no side. */}
            <span
              aria-hidden="true"
              className="mt-3 h-1.5 w-1.5 shrink-0 rounded-full bg-gray-400 dark:bg-gray-500"
            />
            <span>{t(item)}</span>
          </li>
        ))}
      </ul>
    );
  }

  if (typeof block === 'string') {
    return <p className="mt-3 text-sm leading-7 text-gray-700 dark:text-gray-300">{t(block)}</p>;
  }

  return (
    <p className="mt-3">
      <Link
        to={block.to}
        className="inline-flex min-h-11 items-center text-sm font-medium text-brand-600 hover:underline dark:text-brand-400"
      >
        {t(block.key)}
      </Link>
    </p>
  );
}

/**
 * The blanks the operator has to fill before this page is true.
 *
 * Deliberately the loudest thing on the page. A policy that ships with
 * "[company name]" sitting inside paragraph nine reads as boilerplate nobody
 * checked -- which is worse than having no policy, because it tells a reader
 * the promises were not meant either. Rendered as a panel at the top instead,
 * an unfilled field is impossible to miss and impossible to ship by accident.
 */
function UnfilledFields({ fields }) {
  const { t } = useLocale();
  if (!fields?.length) return null;

  // Each `legal.field.x` label is paired with a `legal.value.x` the operator
  // fills in. Both pages say things like "the operator is named at the top of
  // this page", and until this pairing existed there was no code path that
  // could ever put a name there -- the panel rendered a label and a blank
  // forever, so the cross-references pointed at nothing.
  //
  // t() echoes an unknown key back, which is how a missing string is spotted
  // in development; here an echo means "not filled in", same as an empty one.
  const valueOf = (field) => {
    const key = field.replace('legal.field.', 'legal.value.');
    const value = t(key);
    return value && value !== key ? value : null;
  };

  const missing = fields.filter((field) => !valueOf(field));
  const done = missing.length === 0;

  return (
    <div
      role="note"
      className={
        done
          ? 'mt-6 rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 dark:border-gray-800 dark:bg-gray-900'
          : 'mt-6 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 dark:border-amber-900/50 dark:bg-amber-950/40'
      }
    >
      {/* Loud only while something is missing. Once the operator has filled
          every field this is ordinary reference detail, and a permanent amber
          warning would train them to ignore the next real one. */}
      {!done && (
        <>
          <p className="text-sm font-semibold text-amber-900 dark:text-amber-200">
            {t('legal.todo.title')}
          </p>
          <p className="mt-1 text-sm text-amber-900 dark:text-amber-200">
            {t('legal.todo.blurb')}
          </p>
        </>
      )}
      <ul className={done ? 'space-y-3' : 'mt-3 space-y-3'}>
        {fields.map((field) => {
          const value = valueOf(field);
          return (
            <li key={field}>
              <span
                className={
                  done
                    ? 'text-sm font-medium text-gray-600 dark:text-gray-400'
                    : 'text-sm font-medium text-amber-900 dark:text-amber-200'
                }
              >
                {t(field)}
              </span>
              <span
                className={
                  value
                    ? 'mt-1 block text-sm font-medium text-gray-900 dark:text-white'
                    : 'mt-1 block rounded border border-dashed border-amber-300 px-3 py-2 text-sm text-amber-700 dark:border-amber-800 dark:text-amber-300'
                }
              >
                {value || t('legal.todo.blank')}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
