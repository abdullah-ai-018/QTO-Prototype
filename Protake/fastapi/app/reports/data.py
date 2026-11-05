"""Shared, format-agnostic report data assembled from an Estimate. Every
exporter (PDF/CSV/Excel) renders from this same structure so the three
formats can never drift apart.
"""

from dataclasses import dataclass

from app.models.estimate import Estimate
from app.models.project import Project


@dataclass
class ReportLineItem:
    label: str
    quantity: float
    unit: str
    unit_cost: float
    total_cost: float


@dataclass
class ReportTradeSection:
    trade: str
    items: list[ReportLineItem]
    direct_cost: float


@dataclass
class ReportData:
    project_name: str
    client_name: str | None
    location: str | None
    version: str
    generated_at: str
    trades: list[ReportTradeSection]
    material_cost: float
    labor_cost: float
    direct_cost: float
    overhead_pct: float
    overhead_amount: float
    contingency_pct: float
    contingency_amount: float
    profit_pct: float
    profit_amount: float
    final_bid_price: float


def build_report_data(project: Project, estimate: Estimate) -> ReportData:
    from collections import defaultdict
    from datetime import datetime

    by_trade: dict[str, list[ReportLineItem]] = defaultdict(list)
    for item in estimate.items:
        by_trade[item.trade.value].append(
            ReportLineItem(label=item.label, quantity=item.quantity, unit=item.unit, unit_cost=item.unit_cost, total_cost=item.total_cost)
        )

    trades = [
        ReportTradeSection(trade=trade.title(), items=items, direct_cost=round(sum(i.total_cost for i in items), 2))
        for trade, items in by_trade.items()
    ]

    return ReportData(
        project_name=project.name,
        client_name=project.client_name,
        location=project.location,
        version=estimate.version,
        generated_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        trades=trades,
        material_cost=estimate.material_cost,
        labor_cost=estimate.labor_cost,
        direct_cost=estimate.direct_cost,
        overhead_pct=estimate.overhead_pct,
        overhead_amount=estimate.overhead_amount,
        contingency_pct=estimate.contingency_pct,
        contingency_amount=estimate.contingency_amount,
        profit_pct=estimate.profit_pct,
        profit_amount=estimate.profit_amount,
        final_bid_price=estimate.final_bid_price,
    )
