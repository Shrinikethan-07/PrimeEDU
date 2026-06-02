# FocusForge Backend - AI Agents & Logic

This directory contains the Python-based logic for the FocusForge ecosystem, specifically the AI Agents and Discipline Enforcement system.

## Components

### 1. `agents/core.py`
The brain of the system.
- **FocusForgeAgent**: Uses LLMs (Gemini/OpenAI) to provide empathetic mentorship. It processes journal entries to find emotional resonance and generates "Recap Cards" (Weekly/Monthly/Yearly narratives).
- **DisciplineAgent**: Manages the "Regain" penalty system and point economy. It ensures that skipping focus blocks results in significant, psychologically impactful point deductions (including negative scores).

### 2. `main.py`
A FastAPI-based web server that exposes endpoints for:
- Journal submission and AI analysis.
- Discipline penalty application (triggered by the browser extension).
- Narrative recap generation.

## Future Integration (B2B Expansion)
The architecture is designed to support `Organizations` and `Teams` from Day 1. The database schema (to be implemented with SQLAlchemy/PostgreSQL) will allow HR managers to see aggregate consistency scores while maintaining strict end-to-end encryption for individual journal content.

## Setup
To run the backend (requires Python 3.9+):
```bash
pip install fastapi uvicorn pydantic
python -m backend.main
```

*Note: In the current environment, Python is not pre-installed, but this codebase is ready for deployment to a cloud environment (e.g., AWS, GCP, or a dedicated VPS).*
