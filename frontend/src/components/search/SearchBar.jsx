import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

const EXAMPLES = ['iPhone 15 128GB Black', 'Galaxy S24 256GB', 'MacBook Air M3'];

export default function SearchBar({ initialQuery = '', showExamples = false }) {
  const [query, setQuery] = useState(initialQuery);
  const navigate = useNavigate();

  // NOTE: this box does not sync itself to `initialQuery` with an effect.
  // Syncing state to a prop that way causes a cascading re-render; React's
  // recommended approach is to remount instead, so Results passes key={query}.

  const submit = (value) => {
    const trimmed = value.trim();
    if (trimmed) navigate(`/results?q=${encodeURIComponent(trimmed)}`);
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    submit(query);
  };

  return (
    <div className="w-full max-w-2xl">
      <form onSubmit={handleSubmit}>
        <div className="flex gap-2">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search — try including storage and colour"
            aria-label="Search for a product"
            className="flex-1 rounded-lg border border-gray-300 px-4 py-3 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <button
            type="submit"
            className="rounded-lg bg-blue-600 px-6 py-3 font-medium text-white hover:bg-blue-700"
          >
            Search
          </button>
        </div>
      </form>

      {showExamples && (
        <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
          <span className="text-gray-400">Try:</span>
          {EXAMPLES.map((example) => (
            <button
              key={example}
              type="button"
              onClick={() => submit(example)}
              className="rounded-full bg-gray-100 px-3 py-1 text-gray-600 hover:bg-gray-200"
            >
              {example}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
