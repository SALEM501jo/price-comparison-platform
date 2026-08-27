import { createContext } from 'react';

// Own file so LocaleContext.jsx exports only components -- mixing a component
// and a non-component export breaks React Fast Refresh.
export const LocaleContext = createContext(null);
