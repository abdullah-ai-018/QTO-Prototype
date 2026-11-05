import csv
import io

from app.reports.data import ReportData


def generate_csv(data: ReportData) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)

    writer.writerow(["Protake Estimate Report"])
    writer.writerow(["Project", data.project_name])
    writer.writerow(["Client", data.client_name or ""])
    writer.writerow(["Location", data.location or ""])
    writer.writerow(["Version", data.version])
    writer.writerow(["Generated", data.generated_at])
    writer.writerow([])

    writer.writerow(["Trade", "Line Item", "Quantity", "Unit", "Unit Cost", "Total Cost"])
    for section in data.trades:
        for item in section.items:
            writer.writerow([section.trade, item.label, item.quantity, item.unit, f"{item.unit_cost:.2f}", f"{item.total_cost:.2f}"])
        writer.writerow([section.trade, "Trade Direct Cost", "", "", "", f"{section.direct_cost:.2f}"])
    writer.writerow([])

    writer.writerow(["Cost Summary", ""])
    writer.writerow(["Material Cost", f"{data.material_cost:.2f}"])
    writer.writerow(["Labor Cost", f"{data.labor_cost:.2f}"])
    writer.writerow(["Direct Cost", f"{data.direct_cost:.2f}"])
    writer.writerow([f"Overhead ({data.overhead_pct}%)", f"{data.overhead_amount:.2f}"])
    writer.writerow([f"Contingency ({data.contingency_pct}%)", f"{data.contingency_amount:.2f}"])
    writer.writerow([f"Profit ({data.profit_pct}%)", f"{data.profit_amount:.2f}"])
    writer.writerow(["Final Bid Price", f"{data.final_bid_price:.2f}"])

    return buffer.getvalue().encode("utf-8")
