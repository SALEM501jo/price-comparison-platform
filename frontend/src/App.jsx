import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import { LocaleProvider } from './context/LocaleContext';
import { ThemeProvider } from './context/ThemeContext';
import RequireAuth from './components/auth/RequireAuth';
import Navbar from './components/layout/Navbar';
import VerifyBanner from './components/auth/VerifyBanner';
import NotFound from './pages/NotFound';
import Home from './pages/Home';
import Results from './pages/Results';
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
import VerifyEmail from './pages/VerifyEmail';

function App() {
  return (
    <BrowserRouter>
      {/* Locale and theme wrap auth because the login and loading screens
          need translating and colouring too. */}
      <LocaleProvider>
        <ThemeProvider>
          <AuthProvider>
            <div className="min-h-screen bg-gray-50 transition-colors dark:bg-gray-950">
              <Navbar />
              <VerifyBanner />
              <Routes>
                <Route path="/" element={<Home />} />
                <Route path="/results" element={<Results />} />
                <Route path="/product/:productId" element={<ProductDetail />} />
                <Route path="/login" element={<Login />} />
                <Route path="/register" element={<Register />} />
                {/* Public: these links are opened from an email client,
                    often in a different browser from the one that signed up. */}
                <Route path="/verify-email" element={<VerifyEmail />} />
                <Route path="/forgot-password" element={<ForgotPassword />} />
                <Route path="/reset-password" element={<ResetPassword />} />
                {/* Open to anyone: the people who most need support are the
                    ones who cannot sign in. */}
                <Route path="/contact" element={<Contact />} />

                {/* Client-side gating only. Every one of these endpoints
                    enforces the same rule server-side; this just avoids
                    rendering a page that would immediately fill with 401s. */}
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
            </div>
          </AuthProvider>
        </ThemeProvider>
      </LocaleProvider>
    </BrowserRouter>
  );
}

export default App;
