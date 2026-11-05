# Protake Backend

A single-process FastAPI application implementing the full Protake AI
Construction Quantity Takeoff pipeline:

```
Upload PDF -> Geometry Analysis -> OCR -> Rule Engine -> Trade Engines
    -> AI Validation -> Human Review -> Estimate -> Report
```

Geometry (OpenCV + Shapely + NetworkX) is the deterministic source of
truth for every quantity. OCR (PaddleOCR) and AI validation (YOLOv11 +
SAM2, via the Ultralytics unified API) only label, cross-check, and
flag — they never calculate a quantity.

## Setup

```bash
cd "fast api/backend"
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
copy .env.example .env
```

Runs on SQLite out of the box (`storage/protake.db`, auto-created on
first launch). To use PostgreSQL instead, just change `DATABASE_URL` in
`.env` — no code changes anywhere.

## Run

```bash
uvicorn app.main:app --reload --port 8000
```

Docs at `http://localhost:8000/docs`.

## Migrations

The dev server auto-creates tables on SQLite for convenience. For a
real deployment, use Alembic instead:

```bash
alembic revision --autogenerate -m "description"
alembic upgrade head
```

## AI Assistant

Requires `ANTHROPIC_API_KEY` in `.env`. Without it, `/api/v1/assistant/query`
returns a 503 explaining the assistant isn't configured — every other
endpoint works fine without it.

## AI Validation (YOLOv11 / SAM2) and OCR (PaddleOCR)

These are large, optional dependencies, loaded lazily on first real
use. If `ultralytics` or `paddleocr` aren't installed (or fail to
initialize on this machine), the rest of the API keeps working — only
`/pages/{id}/ai-validate` and `/pages/{id}/ocr` will return a clear
error until they're available.

There are no pretrained construction-specific weights bundled here.
`app/ai/training/` contains a real dataset builder (bootstraps a YOLO
dataset from your own approved review data) and training script for
fine-tuning `YOLO_MODEL_PATH` once you have enough reviewed projects.

## Tests

```bash
pytest
```
