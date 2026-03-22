## 🧾 LedgerX — Automated Bills Fetching & Processing API

**LedgerX** is a lightweight automation system that fetches, processes, and organizes billing data from multiple sources — designed for reliability, simplicity, and easy deployment.

Built with **FastAPI + async processing**, it eliminates manual tracking by turning billing workflows into a single API call.

---

## ⚡ Key Features

* 🔄 **Automated bill fetching** across multiple sources
* ⚙️ **Async processing pipeline** with controlled concurrency
* 🧠 **Structured data extraction** (ready for analytics / storage)
* 🚀 **Deployable on Render** with cron-based automation
* 🔌 **API-first design** for easy integration

---

## 🧠 How It Works

1. Trigger `/fetch_bills`
2. System:

   * Loads sources
   * Processes each source sequentially with concurrency control
   * Organizes outputs into structured folders/data
3. Returns when all processing is complete

---

## 🛠️ Tech Stack

* **FastAPI** — backend API
* **AsyncIO** — concurrency & task control
* **Pandas** — data handling
* **Docker** — containerized deployment
* **GitHub Actions** — scheduled automation
* **Render** — hosting

---

## 🚀 Usage

### Run locally

```bash
uvicorn main:app --reload
```

### Trigger automation

```bash
curl http://localhost:8000/fetch_bills
```

---

## ⏱️ Automation

Runs via GitHub Actions (cron):

* Daily scheduled fetch
* No polling required (blocking execution)

---

## 🎯 Why LedgerX?

* Removes manual bill tracking
* Simple but scalable architecture
* Works even on free-tier infrastructure
* Easily extendable to analytics / dashboards / ML

---

## 🔮 Future Improvements

* Task queue (Redis / Celery) for distributed processing
* Dashboard for monitoring
* Smart classification (ML / LLM)
* Notification system (email / Slack)