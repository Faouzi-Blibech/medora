"""Pilot impact dashboard (api.md 1.18): aggregates only, admin only."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.deps import require_roles
from app.db import get_db
from app.models import User
from app.services import impact as I

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/impact")
def impact(days: int = Query(30, ge=1, le=365), _: User = Depends(require_roles("admin")),
           db: Session = Depends(get_db)) -> dict:
    return I.impact(db, days)
