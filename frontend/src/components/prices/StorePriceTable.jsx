import { formatPrice } from '../../utils/format';

/**
 * Every store's price for one product, cheapest total first.
 *
 * The backend already sorts by total cost, but the sort is repeated here so
 * the component is correct on its own rather than depending on the caller.
 */
export default function StorePriceTable({ prices }) {
  if (!prices?.length) {
    return (
      <p className="rounded-lg border border-dashed border-gray-300 px-4 py-8 text-center text-sm text-gray-500">
        No stores are currently listing this product.
      </p>
    );
  }

  const rows = [...prices].sort((a, b) => a.total_cost - b.total_cost);
  const cheapest = rows.find((row) => row.availability);

  return (
    <div className="overflow-x-auto rounded-lg border border-gray-200">
      <table className="min-w-full bg-white text-sm">
        <thead className="bg-gray-50 text-left text-gray-600">
          <tr>
            <th className="px-4 py-3 font-medium">Store</th>
            <th className="px-4 py-3 font-medium">Price</th>
            <th className="px-4 py-3 font-medium">Delivery</th>
            <th className="px-4 py-3 font-medium">Total</th>
            <th className="px-4 py-3 font-medium">Availability</th>
            <th className="px-4 py-3" />
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {rows.map((row) => {
            const isBest = row === cheapest;
            return (
              <tr
                key={`${row.store_name}-${row.price}`}
                className={isBest ? 'bg-green-50/60' : undefined}
              >
                <td className="px-4 py-3">
                  <span className="font-medium text-gray-900">{row.store_name}</span>
                  {isBest && (
                    <span className="ml-2 rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-800">
                      Best deal
                    </span>
                  )}
                </td>
                <td className="px-4 py-3 text-gray-700">{formatPrice(row.price)}</td>
                <td className="px-4 py-3 text-gray-500">
                  {row.delivery_cost > 0 ? formatPrice(row.delivery_cost) : 'Free'}
                </td>
                <td className="px-4 py-3 font-semibold text-gray-900">
                  {formatPrice(row.total_cost)}
                </td>
                <td className="px-4 py-3">
                  {row.availability ? (
                    <span className="text-green-700">In stock</span>
                  ) : (
                    <span className="text-gray-400">Out of stock</span>
                  )}
                </td>
                <td className="px-4 py-3 text-right">
                  {row.store_product_url && (
                    <a
                      href={row.store_product_url}
                      target="_blank"
                      // noreferrer/noopener stops the opened store page from
                      // reaching back into this tab via window.opener.
                      rel="noopener noreferrer"
                      className="text-blue-600 hover:underline"
                    >
                      Visit
                    </a>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
