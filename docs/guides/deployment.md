# Deployment

The deployment uses a Docker Space for the FastAPI backend and Vercel for the
Vite frontend. Supabase remains the hosted database and auth provider.

## 1. Prepare and deploy the backend

The Hugging Face Space repository must contain the contents of `backend/` at
its root. `backend/README.md` supplies the Docker Space metadata and sets the
public app port to `8000`; `backend/Dockerfile` already binds Uvicorn to
`0.0.0.0` and uses the platform-provided `PORT` when available.

1. Create a Docker Space on Hugging Face.
2. Upload or push the contents of this repository's `backend/` directory to
   the Space repository root. Do not upload `.env`, `.venv`, or local data.
3. Add these runtime variables in the Space settings:

   | Variable | Value |
   | --- | --- |
   | `SUPABASE_URL` | Supabase project URL |
   | `SUPABASE_ANON_KEY` | Supabase anon/public key |
   | `SUPABASE_SERVICE_ROLE_KEY` | Supabase service-role key; secret |
   | `DATABASE_URL` | Direct Supabase Postgres URL; secret |
   | `DATABASE_RUNTIME_URL` | Optional runtime connection URL; use the Supabase session pooler on port `5432` if direct DB connectivity is unavailable |
   | `GEMINI_API_KEY` | Gemini API key; secret |
   | `GEMINI_CHAT_MODEL` | `gemini-3.8-flash` |
   | `GEMINI_EMBEDDING_MODEL` | `gemini-embedding-001` |
   | `GEMINI_EMBEDDING_DIMENSIONS` | `768` |
   | `BASE_URL` | `https://generativelanguage.googleapis.com/v1beta/openai/` |
   | `ALLOWED_ORIGINS` | Comma-separated browser origins; include the Vercel production URL in the frontend step |

   Keep service-role, database, and Gemini credentials in Space secrets. Never
   commit them or place them in the frontend.

4. Apply migrations from a trusted local environment using the direct
   `DATABASE_URL`:

   ```powershell
   cd backend
   uv run alembic upgrade head
   ```

5. Wait for the Space build to complete, then verify
   `https://<space-host>/health` returns `{"status":"ok"}`. Record the Space
   URL; the frontend will use it as `VITE_API_BASE_URL`.

The app's chat routes require Supabase-authenticated requests. The Space must
be publicly reachable by the browser frontend; keep access control in the
existing Supabase authentication and backend authorization, not in Space
visibility.

## 2. Deploy and wire the frontend

This is the next step after the backend health check passes:

1. Import the GitHub repository into Vercel and set the project root to
   `frontend`.
2. Set `VITE_API_BASE_URL` to the backend Space URL and set
   `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` to the Supabase public
   values. Vite embeds these values at build time.
3. Deploy the frontend. Add its production origin (and any preview origin you
   intend to support) to the backend's `ALLOWED_ORIGINS`, then restart or
   redeploy the Space.
4. Verify sign-in, a chat request, and the streamed response from the deployed
   frontend.
