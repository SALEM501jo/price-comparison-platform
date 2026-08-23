import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../../hooks/useAuth';

export default function Navbar() {
  const { user, isAuthenticated, logout, loading } = useAuth();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    // navigate() keeps this a single-page transition. window.location.href
    // reloads the whole app and throws away every bit of client state.
    navigate('/');
  };

  return (
    <nav className="border-b bg-white shadow-sm">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
        <Link to="/" className="text-xl font-bold text-blue-600">
          PriceCompare
        </Link>

        <div className="flex items-center gap-4">
          {/* While the stored token is being checked, render neither state.
              Showing "Login" first makes the navbar flicker on every refresh
              for users who are in fact signed in. */}
          {loading ? (
            <span className="h-5 w-24 animate-pulse rounded bg-gray-100" />
          ) : isAuthenticated ? (
            <>
              <span className="text-sm text-gray-600">{user?.email}</span>
              <button
                onClick={handleLogout}
                className="text-sm text-red-600 hover:text-red-700"
              >
                Logout
              </button>
            </>
          ) : (
            <Link to="/login" className="text-sm text-blue-600 hover:text-blue-700">
              Login
            </Link>
          )}
        </div>
      </div>
    </nav>
  );
}
