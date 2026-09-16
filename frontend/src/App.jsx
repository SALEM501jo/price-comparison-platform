import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import { LocaleProvider } from './context/LocaleContext';
import { ThemeProvider } from './context/ThemeContext';
import RequireAuth from './components/auth/RequireAuth';
import Navbar from './components/layout/Navbar';
import ScrollToTop from './components/layout/ScrollToTop';
import Footer from './components/layout/Footer';
import VerifyBanner from './components/auth/VerifyBanner';
import NotFound from './pages/NotFound';
import Home from './pages/Home';
import Results from './pages/Results';
import Browse from './pages/Browse';
import ProductDetail from './pages/ProductDetail';
import Wishlist from './pages/Wishlist';
import Alerts from './pages/Alerts';
import Merchant from './pages/Merchant';
import Admin from './pages/Admin';
import Login from './pages/Login';
import Register from './pages/Register';
import ForgotPassword from './pages/ForgotPassword';
import ResetPassword from './pages/ResetPassword';
import Contact from './pages/Contact';
import Privacy from './pages/Privacy';
import Terms from './pages/Terms';
import VerifyEmail from './pages/VerifyEmail';
import AuthCallback from './pages/AuthCallback';
import Account from './pages/Account';

function App() {
  return (
    <BrowserRouter>
      {/* Locale and theme wrap auth because the login and loading screens
          need translating and colouring too. */}
      <LocaleProvider>
        <ThemeProvider>
          <AuthProvider>
            {/* A column with the routes taking the slack, so the footer sits
                at the bottom of the viewport on a short page -- a 404, an
                empty wishlist -- instead of floating halfway up it. */}
            <div className="flex min-h-screen flex-col bg-gray-50 transition-colors dark:bg-gray-950">
              <ScrollToTop />
              <Navbar />
              <VerifyBanner />
              <main className="flex-1">
                <Routes>
                  <Route path="/" element={<Home />} />
                  <Route path="/results" element={<Results />} />
                  <Route path="/browse/:category" element={<Browse />} />
                  <Route path="/product/:productId" element={<ProductDetail />} />
                  <Route path="/login" element={<Login />} />
                  <Route path="/register" element={<Register />} />
                  {/* Public: these links are opened from an email client,
                      often in a different browser from the one that signed up. */}
                  <Route path="/verify-email" element={<VerifyEmail />} />
                  <Route path="/forgot-password" element={<ForgotPassword />} />
                  <Route path="/reset-password" element={<ResetPassword />} />
                  {/* Where Google and Apple hand the browser back. Top-level
                      rather than under /auth for the same reason as the two
                      above: the API answers an unmatched /auth path with a
                      JSON 404 instead of the app shell, so a route there
                      would 404 on a hard refresh of a built deploy. */}
                  <Route path="/oauth/callback" element={<AuthCallback />} />
                  {/* Open to anyone: the people who most need support are the
                      ones who cannot sign in. */}
                  <Route path="/contact" element={<Contact />} />
                  {/* Reachable without an account and without JavaScript
                      state: someone deciding whether to sign up at all is
                      exactly who reads these. */}
                  <Route path="/privacy" element={<Privacy />} />
                  <Route path="/terms" element={<Terms />} />

                  {/* Client-side gating only. Every one of these endpoints
                      enforces the same rule server-side; this just avoids
                      rendering a page that would immediately fill with 401s. */}
                  {/* The privacy policy and the terms both send readers
                      here for the deletion right, so this path is part of
                      what those documents promise. */}
                  <Route
                    path="/account"
                    element={
                      <RequireAuth>
                        <Account />
                      </RequireAuth>
                    }
                  />
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
                  {/* Any signed-in account may open this: it is where someone
                      BECOMES a merchant, so gating on the role would make the
                      role unreachable. */}
                  <Route
                    path="/merchant"
                    element={
                      <RequireAuth>
                        <Merchant />
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

                  <Route path="*" element={<NotFound />} />
                </Routes>
              </main>
              <Footer />
            </div>
          </AuthProvider>
        </ThemeProvider>
      </LocaleProvider>
    </BrowserRouter>
  );
}

export default App;
