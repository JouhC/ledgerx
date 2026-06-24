# LedgerX

LedgerX is a lightweight automation API for fetching, processing, and organizing billing data from multiple sources. It is designed around reliable scheduled execution, simple deployment, and structured outputs that can later feed analytics or dashboards.

## Features

- Automated bill fetching across multiple sources.
- Async processing pipeline with controlled concurrency.
- Structured data extraction for storage or analysis.
- API-first workflow triggered through a single endpoint.
- Render-friendly deployment with scheduled GitHub Actions automation.

## How It Works

1. Trigger `/fetch_bills`.
2. The service loads configured sources.
3. Sources are processed with concurrency control.
4. Outputs are organized into structured folders or data records.
5. The API responds when processing completes.

## Tech Stack

- FastAPI
- AsyncIO
- Pandas
- Docker
- GitHub Actions
- Render

## Run Locally

```bash
uvicorn main:app --reload
```

Trigger automation:

```bash
curl http://localhost:8000/fetch_bills
```

## Automation

LedgerX can run from GitHub Actions on a cron schedule, so billing workflows can execute daily without manual polling.

## Roadmap

- Task queue support with Redis or Celery.
- Monitoring dashboard.
- Smart classification with ML or LLMs.
- Email or Slack notifications.

## Portfolio Note

LedgerX is featured in my portfolio as a practical FastAPI automation system that turns recurring operational work into a repeatable backend workflow.
