import re
from pathlib import Path
import pytest
from app.models.enums import TradeKey
from app.rules.default_trade_configs import DEFAULT_TRADE_CONFIGS


def test_frontend_estimating_constants_match_backend_defaults():
    """CI / Pytest Drift Guard:
    Verifies that frontend's estimating.ts labor rates and constants match
    backend's default_trade_configs.py to prevent future formula/constant drift.
    """
    estimating_ts_path = Path(__file__).parent.parent.parent / "frontend" / "src" / "lib" / "estimating.ts"
    assert estimating_ts_path.exists(), f"estimating.ts file not found at {estimating_ts_path}"

    content = estimating_ts_path.read_text(encoding="utf-8")

    # Extract TRADE_LABOR_RATES object from TS
    match = re.search(r"TRADE_LABOR_RATES:\s*Record<TradeId,\s*number>\s*=\s*(\{[\s\S]*?\});", content)
    assert match is not None, "Could not find TRADE_LABOR_RATES in estimating.ts"

    rates_block = match.group(1)
    
    # Parse rates from TS block
    ts_rates = {}
    for line in rates_block.splitlines():
        line_match = re.search(r"(\w+):\s*(\d+(?:\.\d+)?)", line)
        if line_match:
            ts_rates[line_match.group(1)] = float(line_match.group(2))

    # Verify against backend default_trade_configs.py
    backend_drywall_rate = DEFAULT_TRADE_CONFIGS[TradeKey.DRYWALL]["labor_rate_per_hour"]
    backend_painting_rate = DEFAULT_TRADE_CONFIGS[TradeKey.PAINTING]["labor_rate_per_hour"]
    backend_flooring_rate = DEFAULT_TRADE_CONFIGS[TradeKey.FLOORING]["labor_rate_per_hour"]
    backend_roofing_rate = DEFAULT_TRADE_CONFIGS[TradeKey.ROOFING]["labor_rate_per_hour"]

    assert ts_rates.get("drywall") == backend_drywall_rate, f"Drywall rate drift: TS={ts_rates.get('drywall')}, Backend={backend_drywall_rate}"
    assert ts_rates.get("painting") == backend_painting_rate, f"Painting rate drift: TS={ts_rates.get('painting')}, Backend={backend_painting_rate}"
    assert ts_rates.get("flooring") == backend_flooring_rate, f"Flooring rate drift: TS={ts_rates.get('flooring')}, Backend={backend_flooring_rate}"
    assert ts_rates.get("roofing") == backend_roofing_rate, f"Roofing rate drift: TS={ts_rates.get('roofing')}, Backend={backend_roofing_rate}"

    # Extract DEFAULT_DRYWALL_SETTINGS wallHeightFt
    wall_height_match = re.search(r"wallHeightFt:\s*(\d+(?:\.\d+)?)", content)
    assert wall_height_match is not None, "Could not find wallHeightFt in DEFAULT_DRYWALL_SETTINGS"
    ts_wall_height = float(wall_height_match.group(1))

    from app.models.wall import Wall
    backend_wall_height = Wall.__table__.columns["height_ft"].default.arg
    assert ts_wall_height == backend_wall_height, f"Wall height drift: TS={ts_wall_height}, Backend={backend_wall_height}"

    # Extract Screws Unit Cost in TS
    screw_cost_match = re.search(r"screws\s*\*\s*(\d+(?:\.\d+)?)", content)
    assert screw_cost_match is not None, "Could not find screws unit cost multiplier in estimating.ts"
    ts_screw_cost = float(screw_cost_match.group(1))

    dw_cov = DEFAULT_TRADE_CONFIGS[TradeKey.DRYWALL]
    backend_screw_cost = dw_cov["material_unit_costs"]["screws_per_100"] / 100.0
    assert abs(ts_screw_cost - backend_screw_cost) < 1e-5, f"Screw cost drift: TS={ts_screw_cost}, Backend={backend_screw_cost}"

    # Extract Joint Compound Coverage in TS
    compound_cov_match = re.search(r"wallAreaSqFt\s*/\s*(\d+(?:\.\d+)?)", content)
    assert compound_cov_match is not None, "Could not find joint compound coverage divisor in estimating.ts"
    ts_compound_coverage = float(compound_cov_match.group(1))

    backend_compound_coverage = float(dw_cov["coverage_rates"]["compound_coverage_sqft_per_bucket"])
    assert ts_compound_coverage == backend_compound_coverage, f"Compound coverage drift: TS={ts_compound_coverage}, Backend={backend_compound_coverage}"

