import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import RequireAuth from './components/auth/RequireAuth';
import Navbar from './components/layout/Navbar';
import Home from './pages/Home';
import Results from './pages/Results';
import ProductDetail from './pages/ProductDetail';
import Wishlist from './pages/Wishlist';
import Alerts from './pages/Alerts';
import Admin from './pages/Admin';
import Login from './pages/Login';
import Register from './pages/Register';

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <div className="min-h-screen bg-gray-50">
          <Navbar />
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/results" element={<Results />} />
            <Route path="/product/:productId" element={<ProductDetail />} />
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />

            {/* Client-side gating only. Every one of these endpoints enforces
                the same rule server-side; this just avoids rendering a page
                that would immediately fill with 401s. */}
            <Route
              path="/wishlist"
              element={
                <RequireAuth>
                  <Wishlist />
                </RequireAuth>
              }
            />
            <Route
              path="/alerts"
              element={
                <RequireAuth>
                  <Alerts />
                </RequireAuth>
              }
            />
            <Route
              path="/admin"
              element={
                <RequireAuth requireAdmin>
                  <Admin />
                </RequireAuth>
              }
            />

            <Route
              path="*"
              element={
                <div className="mx-auto max-w-4xl px-4 py-16 text-center">
                  <h1 className="text-xl font-semibold text-gray-900">
                    Page not found
                  </h1>
                  <a href="/" className="mt-2 inline-block text-blue-600 hover:underline">
                    Back to search
                  </a>
                </div>
              }
            />
          </Routes>
        </div>
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
