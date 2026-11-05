"""Regression tests for printed-scale parsing.

These lock in the behaviour fixed after a measured defect: `_parse_scale_ratio`
used to return 1/96 for ANY unrecognised text. That is not a harmless
default — the value is numerically identical to a legitimate 1/8"=1'-0"
sheet, so a parse failure was indistinguishable from a real reading, and it
propagated into Page.scale_ft_per_px flagged as calibrated.

The notations below are the ones actually printed on the validation sheets.
"""

import pytest

from app.ocr.parsers import _parse_scale_ratio
from app.geometry.metrics import scale_ft_per_px_from_ratio


@pytest.mark.parametrize(
    "text, expected",
    [
        # Metric ratio, colon form.
        ("1:100", 1 / 100),
        ("SCALE 1:50", 1 / 50),
        # Metric ratio, slash form with no "=" — the AUC sheet's own note.
        # Regression: this previously fell through to the fabricated 1/96
        # and reported a 1:96 scale for a 1:100 drawing.
        ("SC 1/100", 1 / 100),
        # Imperial fraction form (has "=").
        ('1/4" = 1\'-0"', 1 / 48),   # 2606
        ('1/8" = 1\'-0"', 1 / 96),   # 27 A10.2
        ('1/16" = 1\'-0"', 1 / 192),
        # Whole-inch form.
        ("1\" = 20'", 1 / 240),
    ],
)
def test_parses_real_printed_scales(text, expected):
    assert _parse_scale_ratio(text) == pytest.approx(expected)


@pytest.mark.parametrize(
    "text",
    [
        "PLAN NORTH",
        "SCALE:",
        "SCALE KEY PLAN",
        "",
        "NOT TO SCALE",
    ],
)
def test_unreadable_text_yields_no_scale(text):
    """Must be None, never a fabricated fallback — a sheet whose scale
    cannot be read has to stay uncalibrated (or fall through to the
    dimension-derived scale), not silently acquire an invented one.
    """
    assert _parse_scale_ratio(text) is None


def test_imperial_and_metric_slash_forms_are_not_confused():
    """The slash form is ambiguous between "1/4\" = 1'-0\"" and "1/100";
    the "=" plus a denominator bound separates them. Nothing real sits
    between the finest imperial denominator (16) and the coarsest metric
    ratio (20).
    """
    assert _parse_scale_ratio('1/4" = 1\'-0"') == pytest.approx(1 / 48)
    assert _parse_scale_ratio("1/4") is None       # bare imperial fraction: not a ratio
    assert _parse_scale_ratio("1/100") == pytest.approx(1 / 100)


def test_measured_sheet_scales_convert_to_expected_ft_per_px():
    """End-to-end against the two sheets whose true scale was derived
    independently: 2606 is 1/4"=1'-0" rasterised at 200 DPI, which is
    0.02 ft/px; AUC is 1:100 at 242 DPI.
    """
    assert scale_ft_per_px_from_ratio(_parse_scale_ratio('1/4" = 1\'-0"'), 200) == pytest.approx(0.02)
    auc = scale_ft_per_px_from_ratio(_parse_scale_ratio("SC 1/100"), 242)
    assert auc == pytest.approx(100 / 12 / 242, rel=1e-6)


# --- ScaleContext -----------------------------------------------------

from app.geometry.metrics import (  # noqa: E402
    SCALE_SOURCE_ASSUMED,
    SCALE_SOURCE_MEASURED,
    SCALE_SOURCE_PRINTED,
    ScaleContext,
)


def test_context_from_each_valid_printed_format():
    """The four formats the pipeline must handle, end to end into a context."""
    for text, dpi, expected_ft_per_px in [
        ("1:100", 242, 100 / 12 / 242),
        ("SC 1/100", 242, 100 / 12 / 242),
        ('1/4" = 1\'-0"', 200, 0.02),
        ('1/8" = 1\'-0"', 200, 0.04),
    ]:
        ctx = ScaleContext.from_printed_ratio(_parse_scale_ratio(text), dpi)
        assert ctx.is_calibrated is True
        assert ctx.source == SCALE_SOURCE_PRINTED
        assert ctx.confidence > 0
        assert ctx.ft_per_px == pytest.approx(expected_ft_per_px, rel=1e-6)


@pytest.mark.parametrize("text", ["PLAN NORTH", "SCALE:", "NOT TO SCALE"])
def test_unparseable_scale_yields_uncalibrated_context(text):
    """Requirement: never fabricate. An unreadable note must produce an
    explicitly uncalibrated context, not a confident wrong number.
    """
    ctx = ScaleContext.from_printed_ratio(_parse_scale_ratio(text), 200)
    assert ctx.is_calibrated is False
    assert ctx.source == SCALE_SOURCE_ASSUMED
    assert ctx.confidence == 0.0


def test_conversions_round_trip():
    ctx = ScaleContext.from_printed_ratio(_parse_scale_ratio('1/4" = 1\'-0"'), 200)
    assert ctx.ft_per_px == pytest.approx(0.02)
    # 100px at 0.02 ft/px = 2 ft = 24 in
    assert ctx.px_to_ft(100) == pytest.approx(2.0)
    assert ctx.px_to_in(100) == pytest.approx(24.0)
    assert ctx.ft_to_px(2.0) == pytest.approx(100.0)
    assert ctx.in_to_px(24.0) == pytest.approx(100.0)
    assert ctx.sqft_per_sqpx() == pytest.approx(0.0004)


def test_measured_scale_outranks_printed():
    """Precedence must stay as documented: a scale measured off the sheet's
    own dimensions is stronger evidence than the printed note.
    """
    printed = ScaleContext.from_ft_per_px(0.02, SCALE_SOURCE_PRINTED, dpi=200)
    measured = ScaleContext.from_ft_per_px(0.02, SCALE_SOURCE_MEASURED, dpi=200)
    assert measured.confidence > printed.confidence


def test_legacy_adapter_preserves_existing_callers():
    """Backward compatibility: the old (float, bool) convention must map to
    an equivalent context, including the uncalibrated case.
    """
    calibrated = ScaleContext.from_legacy(0.02, True, dpi=200)
    assert calibrated.is_calibrated is True and calibrated.ft_per_px == pytest.approx(0.02)

    assumed = ScaleContext.from_legacy(0.0267, False, dpi=200)
    assert assumed.is_calibrated is False and assumed.ft_per_px == pytest.approx(0.0267)

    missing = ScaleContext.from_legacy(None, False, dpi=200)
    assert missing.is_calibrated is False and missing.ft_per_px == pytest.approx(8.0 / 200)
