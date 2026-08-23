import { createContext } from 'react';

// The context object lives in its own file so AuthContext.jsx exports only
// components. Mixing a component and a non-component export in one file
// breaks React Fast Refresh, which silently degrades hot reloading in dev.
export const AuthContext = createContext(null);
