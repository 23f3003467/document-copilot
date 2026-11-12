---
title: Document Copilot API
emoji: 📄
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 8000
---

# Document Copilot API

FastAPI backend for Document Copilot. The Dockerfile in this Space repository
must be the backend's `Dockerfile` at the repository root.

Configure the required runtime variables and secrets in the Space settings
before starting the app. Apply Alembic migrations to Supabase before sending
production traffic; migrations are not run automatically at container startup.
