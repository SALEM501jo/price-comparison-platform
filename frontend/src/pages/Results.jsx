import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { searchProducts } from '../api/products';
import PriceTable from '../components/prices/PriceTable';
import Spinner from '../components/ui/Spinner';

export default function Results() {
  const [searchParams] = useSearchParams();
  const query = searchParams.get('q') || '';
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!query) return;
    
    const fetchData = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await searchProducts(query);
        setProducts(data);
      } catch (err) {
        console.error('AXIOS ERROR:', err.message, err.code, err.config?.url);
        setError('Failed to load results. Is the backend running?');
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [query]);

  return (
    <div className="max-w-5xl mx-auto px-4 py-8">
      <h2 className="text-2xl font-semibold text-gray-800 mb-6">
        Results for "{query}"
      </h2>
      
      {loading && <Spinner />}
      {error && <div className="text-red-500 mb-4">{error}</div>}
      
      {!loading && !error && products.length === 0 && (
        <p className="text-gray-500">No products found.</p>
      )}
      
      {!loading && products.length > 0 && <PriceTable products={products} />}
    </div>
  );
}