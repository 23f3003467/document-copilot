# Render + Vercel Deployment Plan

This plan deploys the FastAPI backend to Render, the Vite frontend to Vercel,
and keeps Supabase as the database and authentication provider. It describes
the deployment steps; it does not mean either service has been deployed.

## Deployment shape

```text
Browser
  ├── Vercel: React + Vite frontend
  ├── Render: FastAPI backend
  └── Supabase: Auth + Postgres
```

Deploy the backend first so its public URL is available for the frontend build
and CORS configuration.

## 1. Prepare Supabase

- Confirm the Supabase project has the required database extensions and schema
  migrations applied.
- Keep the direct Postgres connection string available for Alembic migrations.
  `DATABASE_URL` must be a direct connection, not a Supabase transaction-pooler
  URL.
- If the app needs a pooled runtime connection, use the Supabase **session
  pooler** on port `5432` for `DATABASE_RUNTIME_URL`. This setting is optional;
  when omitted, the app uses `DATABASE_URL` at runtime.
- In Supabase Auth URL configuration, set the production Vercel site URL and
  add any preview URLs that need to support sign-in.

## 2. Deploy the backend to Render

1. Create a Render **Web Service** from the GitHub repository.
2. Choose the backend's Docker configuration:
   - Root directory: `backend`
   - Runtime: Docker
   - Dockerfile path: `Dockerfile` (relative to the root directory)
   - Health check path: `/health`
3. Configure these environment variables in Render. Use secret values from
   Supabase and the model provider; do not commit them or add them to the
   frontend.

   | Variable | Value |
   | --- | --- |
   | `SUPABASE_URL` | Supabase project URL |
   | `SUPABASE_ANON_KEY` | Supabase anon/public key |
   | `SUPABASE_SERVICE_ROLE_KEY` | Supabase service-role key; secret |
   | `DATABASE_URL` | Direct Supabase Postgres URL; secret |
   | `DATABASE_RUNTIME_URL` | Optional Supabase session-pooler URL on port `5432`; secret |
   | `GEMINI_API_KEY` | Gemini API key; secret |
   | `GEMINI_CHAT_MODEL` | `gemini-3.8-flash` (optional; this is the app default) |
   | `GEMINI_EMBEDDING_MODEL` | Gemini embedding model |
   | `GEMINI_EMBEDDING_DIMENSIONS` | `768` |
   | `BASE_URL` | `https://generativelanguage.googleapis.com/v1beta/openai/` |
   | `ALLOWED_ORIGINS` | Comma-separated exact browser origins; set after Vercel is deployed |

   Render supplies `PORT`; the backend Dockerfile uses it automatically.
4. Apply migrations with the direct `DATABASE_URL` from a trusted environment
   that has the backend dependencies installed:

   ```powershell
   cd backend
   uv run alembic upgrade head
   ```

   Migrations are not run automatically when the container starts. Apply and
   review schema changes before routing production traffic to a release that
   requires them.
5. Deploy the service and check Render's build and runtime logs. Confirm
   `https://<render-service>.onrender.com/health` returns
   `{"status":"ok"}`. Record the service URL for the Vercel configuration.

## 3. Deploy the frontend to Vercel

1. Import the same GitHub repository as a Vercel project.
2. Set the project root directory to `frontend` and use the Vite preset.
   Confirm the build command is `pnpm build` and the output directory is
   `dist`.
3. Configure these Vercel environment variables for the environments where
   the app will run:

   | Variable | Value |
   | --- | --- |
   | `VITE_API_BASE_URL` | Render backend URL, without a trailing slash |
   | `VITE_SUPABASE_URL` | Supabase project URL |
   | `VITE_SUPABASE_ANON_KEY` | Supabase anon/public key |

   These `VITE_` values are included in browser assets at build time. Only use
   public client values here; never put the Supabase service-role key, database
   URL, or model API key in Vercel frontend variables.
4. Ensure direct navigation to React Router routes falls back to the SPA entry
   point. Add a Vercel rewrite to `/index.html` if Vercel does not already
   provide the required fallback behavior.
5. Deploy and record the production Vercel origin, for example
   `https://<project>.vercel.app`.

## 4. Connect and verify the services

1. Set Render's `ALLOWED_ORIGINS` to the exact Vercel production origin. Add
   only preview origins that should be allowed to call the API. Do not include
   paths or a trailing slash.
2. Save the Render environment change and redeploy/restart the backend so the
   CORS configuration takes effect.
3. If using a custom frontend domain, add it to both Render's
   `ALLOWED_ORIGINS` and Supabase Auth's allowed site/redirect URLs.
4. Verify the deployed application end to end:
   - The backend health endpoint responds successfully.
   - The frontend loads, including a direct refresh on a nested route.
   - Supabase email sign-in and sign-out work.
   - An authenticated chat request reaches Render without a CORS error.
   - The streamed answer and citations render successfully.
   - Render logs show no missing configuration, database, or model-provider
     errors.

## 5. Release and rollback checklist

- Keep Render and Vercel production deployments tied to the intended Git
  branch.
- Configure and verify preview deployments separately; update CORS and Supabase
  Auth URLs only for previews that need them.
- After changing a frontend `VITE_` variable, trigger a new Vercel build;
  changing the variable does not update already-built browser assets.
- Back up/inspect production data and review Alembic migrations before applying
  them. Prefer backward-compatible schema changes when frontend and backend
  deploys may overlap.
- If a release fails, redeploy the last known-good Render or Vercel build.
  Handle database rollback separately according to the reviewed migration; do
  not assume rolling back an application deploy reverses a database migration.
