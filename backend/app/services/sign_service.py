from __future__ import annotations

from .constants import SIGNS
from ..models import ZodiacSign


def get_enabled_sign_keys() -> list[str]:
    rows = (
        ZodiacSign.query.filter_by(is_enabled=True)
        .order_by(ZodiacSign.sort_order.asc())
        .all()
    )
    return [row.key for row in rows] or list(SIGNS)