# Technical improvement backlog

## Restore `@/` alias resolution in the Vite development server

- **Problem:** `npm run dev` currently fails during dependency scanning because Vite does not resolve the TypeScript `@/` path alias, even though the production build succeeds.
- **Why it matters:** local browser development and exploratory QA cannot reliably use the dev server and must fall back to a production preview.
- **Suggested direction:** configure an explicit Vite `resolve.alias` (or a maintained TypeScript-paths plugin), then verify both `npm run dev` and `npm run build` from a clean checkout.
