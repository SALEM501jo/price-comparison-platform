import { Link, NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../../hooks/useAuth';

const linkClass = ({ isActive }) =>
  `text-sm ${isActive ? 'font-medium text-blue-600' : 'text-gray-600 hover:text-gray-900'}`;

export default function Navbar() {
  const { user, isAuthenticated, isAdmin, logout, loading } = useAuth();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    // navigate() keeps this a single-page transition. window.location.href
    // reloads the whole app and throws away every bit of client state.
    navigate('/');
  };

  return (
    <nav className="border-b bg-white shadow-sm">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3">
        <div className="flex items-center gap-6">
          <Link to="/" className="text-xl font-bold text-blue-600">
            PriceCompare
          </Link>

          {isAuthenticated && (
            <div className="flex items-center gap-4">
              <NavLink to="/wishlist" className={linkClass}>
                Wishlist
              </NavLink>
              <NavLink to="/alerts" className={linkClass}>
                Alerts
              </NavLink>
              {isAdmin && (
                <NavLink to="/admin" className={linkClass}>
                  Admin
                </NavLink>
              )}
            </div>
          )}
        </div>

        <div className="flex items-center gap-4">
          {/* While the refresh cookie is being exchanged, render neither
              state. Showing "Login" first makes the navbar flicker on every
              page load for users who are in fact signed in. */}
          {loading ? (
            <span className="h-5 w-24 animate-pulse rounded bg-gray-100" />
          ) : isAuthenticated ? (
            <>
              <span className="hidden text-sm text-gray-600 sm:inline">
                {user?.email}
              </span>
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
