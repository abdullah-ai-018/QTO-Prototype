from typing import Literal

from app.models.estimate import Estimate
from app.models.project import Project
from app.reports.csv_report import generate_csv
from app.reports.data import build_report_data
from app.reports.excel_report import generate_excel
from app.reports.pdf_report import generate_pdf

ReportFormat = Literal["pdf", "csv", "xlsx"]

_CONTENT_TYPES: dict[ReportFormat, str] = {
    "pdf": "application/pdf",
    "csv": "text/csv",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def render_report(project: Project, estimate: Estimate, fmt: ReportFormat) -> tuple[bytes, str, str]:
    data = build_report_data(project, estimate)

    if fmt == "pdf":
        content = generate_pdf(data)
    elif fmt == "csv":
        content = generate_csv(data)
    elif fmt == "xlsx":
        content = generate_excel(data)
    else:  # pragma: no cover - fmt is constrained by the API's path enum
        raise ValueError(f"Unsupported report format: {fmt}")

    filename = f"protake-estimate-{estimate.version}.{fmt}"
    return content, _CONTENT_TYPES[fmt], filename
