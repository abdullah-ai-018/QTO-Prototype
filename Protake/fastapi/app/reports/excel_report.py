import io

import pandas as pd

from app.reports.data import ReportData


def generate_excel(data: ReportData) -> bytes:
    buffer = io.BytesIO()

    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        summary_rows = [
            {"Field": "Project", "Value": data.project_name},
            {"Field": "Client", "Value": data.client_name or ""},
            {"Field": "Location", "Value": data.location or ""},
            {"Field": "Version", "Value": data.version},
            {"Field": "Generated", "Value": data.generated_at},
            {"Field": "Material Cost", "Value": data.material_cost},
            {"Field": "Labor Cost", "Value": data.labor_cost},
            {"Field": "Direct Cost", "Value": data.direct_cost},
            {"Field": f"Overhead ({data.overhead_pct}%)", "Value": data.overhead_amount},
            {"Field": f"Contingency ({data.contingency_pct}%)", "Value": data.contingency_amount},
            {"Field": f"Profit ({data.profit_pct}%)", "Value": data.profit_amount},
            {"Field": "Final Bid Price", "Value": data.final_bid_price},
        ]
        pd.DataFrame(summary_rows).to_excel(writer, sheet_name="Summary", index=False)

        for section in data.trades:
            rows = [
                {"Line Item": item.label, "Quantity": item.quantity, "Unit": item.unit, "Unit Cost": item.unit_cost, "Total Cost": item.total_cost}
                for item in section.items
            ]
            rows.append({"Line Item": "TRADE DIRECT COST", "Quantity": "", "Unit": "", "Unit Cost": "", "Total Cost": section.direct_cost})
            sheet_name = section.trade[:31]  # Excel sheet name limit
            pd.DataFrame(rows).to_excel(writer, sheet_name=sheet_name, index=False)

    return buffer.getvalue()
