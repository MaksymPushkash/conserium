# Cortex Client

Next.js frontend for the Cortex backend.

## Local Start

```bash
cd client
npm install
cp .env.example .env.local
npm run dev
```

The app expects the backend at `NEXT_PUBLIC_API_BASE_URL`, defaulting to `http://localhost:8000`.

OAuth buttons start the backend OAuth flow at `/api/v1/auth/google` and `/api/v1/auth/github`. The frontend callback page also accepts `access_token` and `refresh_token` query parameters for token handoff if the backend is configured to redirect to `/auth/callback`.
