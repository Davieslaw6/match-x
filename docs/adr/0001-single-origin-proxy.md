# 0001 Single-origin via Next.js rewrites
Context: cookies are SameSite=Lax and HttpOnly; CORS must be exact-origin.
Decision: browser talks only to Next.js; next.config rewrites /api/* to BACKEND_URL.
Consequences: no cross-site cookies; backend URL stays server-side; Vercel needs BACKEND_URL set.
