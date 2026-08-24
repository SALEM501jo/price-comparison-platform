import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../../hooks/useAuth';
import Spinner from '../ui/Spinner';

/**
 * Gate a route behind authentication.
 *
 * This is a convenience, NOT a security control -- anyone can edit client-side
 * JavaScript. Every protected endpoint enforces the same rule server-side; all
 * this does is avoid rendering a page that would only fill with 401s.
 *
 * `requireAdmin` gates on role for the same reason: /admin/* already returns
 * 403 to non-admins regardless of what the browser thinks.
 */
export default function RequireAuth({ children, requireAdmin = false }) {
  const { isAuthenticated, isAdmin, loading } = useAuth();
  const location = useLocation();

  // The session is restored asynchronously from the refresh cookie, so on the
  // first render we genuinely do not know yet. Redirecting here would bounce
  // signed-in users to the login page on every page load.
  if (loading) return <Spinner />;

  if (!isAuthenticated) {
    // `state` lets the login page send the user back where they were headed.
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  if (requireAdmin && !isAdmin) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-16 text-center">
        <h1 className="text-xl font-semibold text-gray-900">Admin only</h1>
        <p className="mt-2 text-sm text-gray-500">
          Your account does not have access to this page.
        </p>
      </div>
    );
  }

  return children;
}
