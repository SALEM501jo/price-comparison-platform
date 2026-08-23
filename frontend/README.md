# Frontend

React 19 + Vite + Tailwind. See the [project README](../README.md) for the
architecture and the problem this solves.

```bash
npm install
npm run dev      # http://localhost:5173
npm run lint
npm run build
```

The backend must be running on port 8000. Set `VITE_API_URL` in `.env.local` to
point elsewhere — copy `.env.example` to start.

## Structure

```
src/
  api/
    axios.js       instance with token refresh; access token held IN MEMORY
    auth.js        register / login / logout / me
    products.js    tiered search, product detail, price history
  components/
    search/        TierSection, ProductResultCard, MatchBadge,
                   QueryInterpretation
    prices/        StorePriceTable
  context/
    auth-context.js   the context object, split out so AuthContext.jsx
                      exports only components (React Fast Refresh)
    AuthContext.jsx   provider; restores the session from the refresh cookie
  pages/           Home, Results, ProductDetail, Login, Register
  utils/           constants, formatting, API error extraction
```

## Two things worth knowing

**No tokens in `localStorage`.** The refresh token is an httpOnly cookie the
browser sends automatically and JavaScript cannot read. The access token lives
in a module variable in `api/axios.js`, so it dies with the tab. A page reload
loses it and the app silently exchanges the cookie for a new one on start-up —
that round trip is why `AuthProvider` starts in a loading state.

This is also why `withCredentials: true` is set on the axios instance: without
it the browser will not send the cookie cross-origin (`:5173` to `:8000`).

**Errors come from `fields`, not `detail`.** A 422 returns
`{"detail": "Invalid input data", "fields": [{"field": "password", "message":
"Password must contain an uppercase letter"}]}`. Reading only `detail` shows
every validation failure as the same useless sentence; `utils/errors.js`
prefers `fields`.
