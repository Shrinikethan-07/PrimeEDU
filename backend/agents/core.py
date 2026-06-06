import os
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional
from pydantic import BaseModel

class JournalEntry(BaseModel):
    user_id: str
    content: str
    timestamp: datetime
    mood_score: int # 1-10

class RecapCard(BaseModel):
    title: str
    content: str
    type: str # Weekly, Monthly, Yearly
    sentiment: str

class FocusForgeAgent:
    """
    The emotional core of FocusForge. 
    Acting as a highly empathetic, perceptive, and encouraging mentor.
    """
    def __init__(self, api_key: str, model_name: str = "gemini-1.5-pro"):
        self.api_key = api_key
        self.model_name = model_name
        # In a real implementation, you'd initialize the Gemini/OpenAI client here
        # self.client = genai.GenerativeModel(model_name)

    async def analyze_journal(self, entry: JournalEntry) -> Dict:
        """Analyzes a single journal entry for emotional state and struggles."""
        prompt = f"""
        Act as a perceptive mentor for a student/professional building discipline.
        Analyze the following journal entry:
        "{entry.content}"
        
        Identify:
        1. Primary emotional state.
        2. Specifically mentioned victories (even minor ones).
        3. Obstacles or distractions faced.
        """
        # mock_response = self.client.generate_content(prompt)
        return {
            "sentiment": "Resilient but slightly overwhelmed",
            "key_victory": "Pushing through Physics module despite struggle",
            "advice": "Break down tomorrow's Mechanics problems into sets of 5."
        }

    async def generate_recap_card(self, entries: List[JournalEntry], period: str = "Weekly") -> RecapCard:
        """
        Synthesizes multiple journal entries into an authentic, 
        emotionally resonant 'Recap Card'.
        """
        context = "\n".join([f"[{e.timestamp.date()}] {e.content}" for e in entries])
        
        prompt = f"""
        Generate a {period} Recap Card for FocusForge.
        
        Context from past entries:
        {context}
        
        The recap must:
        - Be highly authentic and emotionally resonant.
        - Highlight consistency streaks and resilience.
        - Use a narrative style celebrating the user's "art of being consistent."
        - Avoid generic corporate encouragement.
        """
        
        # This is where the AI 'magic' happens
        return RecapCard(
            title=f"{period} Resilience Report",
            content="You struggled with Physics on Tuesday, but you pushed through and finished the module by Friday. Your commitment to the 'Deep Work' protocol is showing tangible results in your comprehension speed. Keep building that momentum.",
            type=period,
            sentiment="Encouraging"
        )

class DisciplineAgent:
    """
    The enforcement agent for FocusForge.
    Handles point deductions and behavioral rewards.
    """
    def __init__(self):
        self.penalty_multiplier = 1.5

    def calculate_penalty(self, distraction_time_minutes: int, intensity_level: int) -> int:
        """
        Calculates strict point deductions for overriding web blockers.
        Scores are allowed to drop into the negative to ensure psychological impact.
        """
        base_penalty = 100
        total_deduction = int(base_penalty * distraction_time_minutes * intensity_level * self.penalty_multiplier)
        return -total_deduction

    def award_points(self, task_complexity: int, consistency_streak: int) -> int:
        """Awards points based on task completion and streaks."""
        return 50 + (task_complexity * 10) + (consistency_streak * 5)

class VisualizerAgent:
    """
    Synthesizes session logs and task completions into dynamic recap visualizations.
    """
    def __init__(self):
        pass

    def get_recap_visuals(self, sessions, tasks) -> dict:
        completed_sessions = [s for s in sessions if s.get('status') == 'completed']
        total_focus_minutes = 0
        for s in completed_sessions:
            try:
                start_str = s.get('start_time')
                end_str = s.get('end_time')
                if start_str and end_str:
                    if isinstance(start_str, str) and start_str.endswith('Z'):
                        start_str = start_str[:-1] + '+00:00'
                    if isinstance(end_str, str) and end_str.endswith('Z'):
                        end_str = end_str[:-1] + '+00:00'
                    start = datetime.fromisoformat(start_str)
                    end = datetime.fromisoformat(end_str)
                    if start.tzinfo is None:
                        start = start.replace(tzinfo=timezone(timedelta(hours=5, minutes=30)))
                    else:
                        start = start.astimezone(timezone(timedelta(hours=5, minutes=30)))
                    if end.tzinfo is None:
                        end = end.replace(tzinfo=timezone(timedelta(hours=5, minutes=30)))
                    else:
                        end = end.astimezone(timezone(timedelta(hours=5, minutes=30)))
                    total_focus_minutes += (end - start).total_seconds() / 60.0
            except Exception:
                pass
        
        balls_earned = len(completed_sessions) * 45
        
        return {
            "reason": f"You completed {len(completed_sessions)} focus sessions, logging {int(total_focus_minutes)} minutes of deep work. Excellent dedication to your goals.",
            "image": "consistency_v2.png",
            "highlight_stat": str(balls_earned),
            "label": "EARNED"
        }
