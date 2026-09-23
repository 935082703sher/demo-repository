"""Admin KPI dashboard, protected by HTTP Basic auth.

Access requires ADMIN_PASSWORD to be configured; without it the admin routes are
refused (503) so the dashboard is never accidentally public. Credentials are
compared in constant time.
"""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.core.config import Settings
from app.services.audit_log import AuditLog

router = APIRouter(tags=["admin"])

_security = HTTPBasic()
_ADMIN_PAGE = Path(__file__).parent.parent.parent / "static" / "admin.html"

Credentials = Annotated[HTTPBasicCredentials, Depends(_security)]


def require_admin(request: Request, credentials: Credentials) -> None:
    """Allow only the configured admin; refuse entirely when unconfigured."""
    settings = cast(Settings, request.app.state.settings)
    secret = settings.admin_password
    if secret is None or not secret.get_secret_value():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="admin_not_configured",
        )
    user_ok = secrets.compare_digest(credentials.username, settings.admin_user)
    password_ok = secrets.compare_digest(credentials.password, secret.get_secret_value())
    if not (user_ok and password_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_credentials",
            headers={"WWW-Authenticate": "Basic"},
        )


AdminGuard = Annotated[None, Depends(require_admin)]


@router.get("/admin", include_in_schema=False)
def admin_page(_: AdminGuard) -> FileResponse:
    """Serve the KPI dashboard (Basic-auth protected)."""
    return FileResponse(_ADMIN_PAGE)


@router.get("/admin/metrics")
async def admin_metrics(request: Request, _: AdminGuard) -> dict[str, object]:
    """Return the pilot KPIs for the dashboard (Basic-auth protected)."""
    audit = cast(AuditLog, request.app.state.audit_log)
    return await audit.metrics()
