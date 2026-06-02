from fastapi import FastAPI, HTTPException, Depends
from typing import List
from datetime import datetime
from .agents.core import FocusForgeAgent, DisciplineAgent, JournalEntry, RecapCard

app = FastAPI(title="FocusForge Backend API")

# Initialize Agents
journal_agent = FocusForgeAgent(api_key="MOCK_KEY")
discipline_agent = DisciplineAgent()

@app.post("/journal/entry", response_model=RecapCard)
async def submit_journal(entry: JournalEntry):
    """
    Submits a journal entry and returns an AI-analyzed recap or advice.
    """
    try:
        analysis = await journal_agent.analyze_journal(entry)
        # Store in DB (Future implementation with SQLAlchemy/Pydantic)
        
        # For simplicity in this demo, we return a mock recap card if it's a 'milestone' entry
        recap = await journal_agent.generate_recap_card([entry], period="Daily")
        return recap
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/discipline/penalty")
async def apply_penalty(user_id: str, minutes: int, intensity: int):
    """
    Endpoint called by the browser extension when a distraction is detected.
    Strictly deducts points from the user's gamified score.
    """
    penalty = discipline_agent.calculate_penalty(minutes, intensity)
    # Update user score in DB
    return {"deduction": penalty, "message": "Discipline breach detected. Score updated."}

@app.get("/stats/recap/{period}")
async def get_period_recap(user_id: str, period: str):
    """
    Generates a Weekly, Monthly, or Yearly recap narrative.
    """
    # Fetch entries from DB for user_id and period
    mock_entries = [
        JournalEntry(user_id=user_id, content="Struggled today but finished 20 problems", timestamp=datetime.now(), mood_score=6)
    ]
    recap = await journal_agent.generate_recap_card(mock_entries, period=period)
    return recap

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
