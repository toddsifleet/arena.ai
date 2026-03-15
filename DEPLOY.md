# Deploy Guide

This project includes deployment configuration files, but no deployment is performed automatically.

## Included Files

- `railway.json` for backend deployment on Railway
- `frontend/netlify.toml` for frontend deployment on Netlify
- `frontend/public/_redirects` for SPA routing fallback

## Backend (Railway)

1. Create a new Railway project and connect this repository.
2. Set root directory to project root (or keep default).
3. Ensure start command uses:

```bash
cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

4. Set environment variables:
   - `MINIRTC_CORS_ORIGINS=https://your-frontend-domain`

5. Verify:
   - `GET /health` returns 200.

## Frontend (Netlify)

1. Create a new Netlify site from this repository.
2. Set base directory to `frontend`.
3. Build command:

```bash
npm run build
```

4. Publish directory:

```bash
dist
```

5. Set environment variable:
   - `VITE_WEBSOCKET_URL=wss://your-backend-domain` (used for WebSocket connections; HTTP goes through the `/api` proxy)
   - `BACKEND_URL=https://your-backend-domain` (used by Netlify to proxy `/api/*` requests)

6. Verify:
   - SPA routes (like `/room/<id>`) resolve via redirect fallback.

## Post-Deploy Validation Checklist

- Create room from `/`.
- Open room URL in a second tab/device.
- Confirm call establishes with audio even if camera is denied.
- Toggle mute/unmute.
- Leave and reconnect.
- Check `/dashboard` shows room/presence events.
