import { Link } from 'react-router-dom';

export default function PriceTable({ products }) {
  return (
    <div className="overflow-x-auto rounded-lg shadow">
      <table className="min-w-full bg-white">
        <thead className="bg-gray-100">
          <tr>
            <th className="px-4 py-3 text-left text-sm font-semibold text-gray-700">Product</th>
            <th className="px-4 py-3 text-left text-sm font-semibold text-gray-700">Lowest Price</th>
            <th className="px-4 py-3 text-left text-sm font-semibold text-gray-700">Stores</th>
            <th className="px-4 py-3 text-left text-sm font-semibold text-gray-700">Best Deal</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-200">
          {products.map((product) => (
            <tr key={product.id} className="hover:bg-gray-50">
              <td className="px-4 py-3">
                <Link
                  to={`/product/${product.id}`}
                  className="text-blue-600 hover:underline font-medium"
                >
                  {product.canonical_name}
                </Link>
                <p className="text-xs text-gray-400">{product.brand}</p>
              </td>
              <td className="px-4 py-3 font-bold text-gray-900">
                {product.lowest_price.toFixed(2)} JOD
              </td>
              <td className="px-4 py-3 text-sm text-gray-600">
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