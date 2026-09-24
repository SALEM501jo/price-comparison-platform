import { useLocale } from '../../hooks/useLocale';
import { attributeName } from '../../utils/matchDifference';
import ScoreBar from './ScoreBar';

/**
 * What a listing is scored on before any listing is scored: the category's
 * full 100 points from rules.py, the three bar states, and the tier ladder.
 * It is the key to every bar below it, so it sits above them.
 */
function Swatch({ className }) {
  return <span aria-hidden="true" className={`inline-block h-3 w-5 shrink-0 rounded-sm ${className}`} />;
}

export default function WeightsLegend({ weights, category }) {
  const { t } = useLocale();
  const scoring = weights.filter((w) => !w.gate && w.weight > 0);
  const gates = weights.filter((w) => w.gate);
  const reference = scoring.map((w) => ({ ...w, state: 'reference', comparison: null }));

  return (
    <div className="mt-4 rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900">
      <p className="text-sm leading-6 text-gray-700 dark:text-gray-300">
        {t('lab.weights.lead', { category: t(`category.${category}`) })}
      </p>
      <div className="mt-3">
        <ScoreBar segments={reference} label={t('lab.weights.barLabel')} />
      </div>
      <p className="mt-2 text-xs text-gray-600 dark:text-gray-400">
        {scoring
          .map((w) => `${attributeName(w.attribute, t, w.label)} ${w.weight}`)
          .join(' · ')}
      </p>
      {gates.length > 0 && (
        <p className="mt-2 text-sm text-gray-700 dark:text-gray-300">
          {t('lab.weights.gate', {
            attributes: gates.map((w) => attributeName(w.attribute, t, w.label)).join(t('lab.listSeparator')),
          })}
        </p>
      )}

      <ul className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-xs text-gray-700 dark:text-gray-300">
        <li className="flex items-center gap-2">
          <Swatch className="bg-brand-600 dark:bg-brand-600" />
          {t('lab.legend.kept')}
        </li>
        <li className="flex items-center gap-2">
          <Swatch className="bg-red-600/10 ring-2 ring-inset ring-red-600 dark:bg-red-500/15 dark:ring-red-500" />
          {t('lab.legend.lost')}
        </li>
        <li className="flex items-center gap-2">
          <Swatch className="bg-gray-100 dark:bg-gray-800" />
          {t('lab.legend.unasked')}
        </li>
      </ul>
      <p className="mt-3 text-xs text-gray-500 dark:text-gray-400">{t('lab.ladder')}</p>
    </div>
  );
}
