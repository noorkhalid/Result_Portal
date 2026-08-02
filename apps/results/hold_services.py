from __future__ import annotations

from collections.abc import Iterable

from results.models import HoldCategory, SemesterResult


def hold_category_map(codes: Iterable[str] | None = None) -> dict[str, HoldCategory]:
    """Return configured categories keyed by code."""

    queryset = HoldCategory.objects.all()
    if codes is not None:
        cleaned_codes = {
            (code or "").strip().lower()
            for code in codes
            if (code or "").strip()
        }
        queryset = queryset.filter(code__in=cleaned_codes)
    return {category.code: category for category in queryset}


def hold_label_for_code(
    code: str | None,
    *,
    categories: dict[str, HoldCategory] | None = None,
) -> str:
    """Resolve a hold code to its configured label without hard-coded categories."""

    normalised = (code or SemesterResult.HOLD_NONE).strip().lower()
    if normalised == SemesterResult.HOLD_NONE:
        return ""

    if categories is None:
        category = HoldCategory.objects.filter(code=normalised).first()
    else:
        category = categories.get(normalised)
    return category.name if category else normalised
