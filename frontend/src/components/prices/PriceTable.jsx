import { Link } from 'react-router-dom';

export default function PriceTable({ products }) {
  return (
    <div className="overflow-x-auto rounded-lg shadow">
      <table className="min-w-full bg-white dark:bg-gray-900">
        <thead className="bg-gray-100 dark:bg-gray-800">
          <tr>
            <th className="px-4 py-3 text-left text-sm font-semibold text-gray-700 dark:text-gray-300">Product</th>
            <th className="px-4 py-3 text-left text-sm font-semibold text-gray-700 dark:text-gray-300">Lowest Price</th>
            <th className="px-4 py-3 text-left text-sm font-semibold text-gray-700 dark:text-gray-300">Stores</th>
            <th className="px-4 py-3 text-left text-sm font-semibold text-gray-700 dark:text-gray-300">Best Deal</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-200 dark:divide-gray-800">
          {products.map((product) => (
            <tr key={product.id} className="hover:bg-gray-50">
              <td className="px-4 py-3">
                <Link
                  to={`/product/${product.id}`}
                  className="text-brand-600 dark:text-brand-400 hover:underline font-medium"
                >
                  {product.canonical_name}
                </Link>
                <p className="text-xs text-gray-400 dark:text-gray-500">{product.brand}</p>
              </td>
              <td className="px-4 py-3 font-bold text-gray-900 dark:text-white">
                {product.lowest_price.toFixed(2)} JOD
              </td>
              <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-400">
                {product.store_count} stores
              </td>
              <td className="px-4 py-3 text-sm text-green-600">
                {product.best_deal_store || 'N/A'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}