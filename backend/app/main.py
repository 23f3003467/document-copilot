from typing import Annotated, Any

import uvicorn
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.chat import router as chat_router
from app.auth.dependencies import get_current_user
from app.config import settings

# The app begins at this module. Each request follows the same pattern:
# 1) CORS validates the incoming origin,
# 2) the route handler executes, and
# 3) protected routes explicitly depend on `get_current_user` to verify the
#    Bearer token before doing anything else.
app = FastAPI(title="Document Copilot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)


@app.get("/health")
async def health() -> dict[str, str]:
    """Simple availability check used by deployment and smoke tests."""
    return {"status": "ok"}


@app.get("/auth/me")
async def me(
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> dict[str, Any]:
    """Return the authenticated user payload after JWT validation succeeds."""
    return {
        "id": current_user.get("id"),
        "email": current_user.get("email"),
        "last_sign_in_at": current_user.get("last_sign_in_at"),
    }


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000)
