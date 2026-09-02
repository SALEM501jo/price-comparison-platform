import { Link } from 'react-router-dom';
import ProductImage from '../ui/ProductImage';
import { formatPrice } from '../../utils/format';
import { useLocale } from '../../hooks/useLocale';

/**
 * One product as a grid tile: picture first, everything else under it.
 *
 * THE PICTURE LEADS, and at the full width of the card. The previous card put
 * a 56px thumbnail beside the title, which is the shape of a search result,
 * not of a shop front -- at that size a phone is a dark smudge and the tile
 * carries no more information than a line of text would. Somebody browsing
 * recognises a product by looking at it; somebody searching has already said
 * what they want in words. Two different jobs, two different cards.
 *
 * ONE COMPONENT FOR BOTH GRIDS. The savings row and the catalogue row differ
 * by exactly one thing -- whether there is a gap between shops worth naming --
 * so that is a prop, not a second component. Two near-identical cards is how
 * the two quietly drift until the front page looks like two websites.
 */
export default function ProductTile({ product, saving = null }) {
  const { t } = useLocale();
  const hasSaving = saving && saving.amount > 0;

  return (
    <Link
      to={`/product/${product.id}`}
      className="group flex flex-col overflow-hidden rounded-xl border border-gray-200 bg-white transition hover:border-brand-400 hover:shadow-md dark:border-gray-800 dark:bg-gray-900 dark:hover:border-brand-600"
    >
      {/* The image sits on its own light panel in BOTH themes. Product shots
          are photographed on white, so a dark tile behind a transparent PNG
          renders the handset as a black rectangle on black. */}
      <div className="relative bg-white dark:bg-gray-100">
        <ProductImage
          src={product.image_url}
          alt={product.canonical_name}
          size="tile"
          className="!border-0 bg-white p-3 dark:bg-gray-100"
        />

        {hasSaving && (
          // start-3, not left-3: this has to sit in the leading corner in
          // both writing directions, and a hard left corner reads as a
          // mistake on the Arabic site.
          <span className="absolute top-3 start-3 rounded-full bg-brand-600 px-2.5 py-1 text-xs font-bold text-white shadow-sm">
            {t('home.save')} {formatPrice(saving.amount)}
          </span>
        )}
      </div>

      <div className="flex flex-1 flex-col gap-1 border-t border-gray-100 p-3 dark:border-gray-800">
        {product.brand && (
          <p className="text-[11px] uppercase tracking-wide text-gray-400 dark:text-gray-500">
            {product.brand}
          </p>
        )}

        <h3 className="line-clamp-2 flex-1 text-sm font-medium leading-snug text-gray-900 dark:text-gray-100">
          {product.canonical_name}
        </h3>

        <p className="mt-1 text-lg font-bold text-gray-900 tnum dark:text-white">
          {formatPrice(product.lowest_total_cost)}
        </p>

        <p className="text-xs text-gray-500 dark:text-gray-400">
          {product.best_deal_store
            ? `${t('home.at')} ${product.best_deal_store}`
            : t('common.inclDelivery')}
        </p>

        {/* The dearest price is CONTEXT, not a struck-through "was". It is a
            real price at a real shop, and striking it through would be the
            invented-RRP pattern a comparison site exists to see past. */}
        {hasSaving && (
          <p className="text-xs text-gray-400 dark:text-gray-500">
            {t('home.upTo')} {formatPrice(saving.highest)} {t('home.elsewhere')}
            {' · '}
            {t('home.comparedAcross', { count: product.store_count })}
          </p>
        )}
      </div>
    </Link>
  );
}
