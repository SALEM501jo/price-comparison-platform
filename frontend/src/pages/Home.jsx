import SearchBar from '../components/search/SearchBar';

export default function Home() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] px-4">
      <h1 className="text-4xl font-bold text-gray-900 mb-2">
        Jordan Price Comparison
      </h1>
      <p className="text-gray-500 mb-8 text-center max-w-md">
        Compare prices across Jordanian stores. Include storage and colour to get an exact match.
      </p>
      <SearchBar showExamples />
    </div>
  );
}