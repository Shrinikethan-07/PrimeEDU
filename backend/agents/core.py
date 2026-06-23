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

    def get_recap_visuals(self, sessions, tasks, user_balls=0, journal_count=0, user_streak=0) -> dict:
        completed_sessions = [s for s in sessions if s.get('status') == 'completed']
        total_focus_minutes = 0
        for s in completed_sessions:
            if s.get('duration_minutes') is not None:
                total_focus_minutes += float(s['duration_minutes'])
            else:
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
        
        total_focus_hours = total_focus_minutes / 60.0
        
        # Determine user role dynamically
        if len(completed_sessions) == 0 and user_balls == 0:
            role = "JUST CHILLING"
            role_title = "JUST CHILLING"
            role_subtitle = "Surgical Precision: 0% Effort"
            role_image = "assets/recap_chilling.jpg"
            role_desc = "Time to forge your discipline."
        else:
            night_count = 0
            for s in completed_sessions:
                try:
                    t_str = s.get('start_time')
                    if t_str:
                        if isinstance(t_str, str) and t_str.endswith('Z'):
                            t_str = t_str[:-1] + '+00:00'
                        dt = datetime.fromisoformat(t_str)
                        if dt.tzinfo and dt.tzinfo != timezone(timedelta(hours=5, minutes=30)):
                            dt = dt.astimezone(timezone(timedelta(hours=5, minutes=30)))
                        h = dt.hour
                        if h >= 21 or h < 5:
                            night_count += 1
                except Exception:
                    pass
            
            subject_counts = {}
            for s in completed_sessions:
                subj = s.get('subject') or 'General'
                subject_counts[subj] = subject_counts.get(subj, 0) + 1
            
            max_subj_count = max(subject_counts.values()) if subject_counts else 0
            max_subj_ratio = (max_subj_count / len(completed_sessions)) if completed_sessions else 0
            
            if user_balls >= 1000 or len(completed_sessions) >= 50:
                role = "THE KNOWLEDGE SAGE"
                role_title = "THE KNOWLEDGE SAGE"
                role_subtitle = "Master of All Domains"
                role_image = "assets/recap_sage.jpg"
                role_desc = "You dominate the arena with grand wisdom."
            elif (len(completed_sessions) > 0 and (night_count / len(completed_sessions)) >= 0.5) or user_balls >= 500:
                role = "GHOST OF UCHIHA"
                role_title = "GHOST OF UCHIHA"
                role_subtitle = "Warrior of the Night"
                role_image = "assets/recap_uchiha.jpg"
                role_desc = "Your training is forged in the shadows of the night."
            elif (len(completed_sessions) > 0 and max_subj_ratio >= 0.65) or user_balls >= 200:
                role = "SHARINGAN SIGHT"
                role_title = "SHARINGAN SIGHT"
                role_subtitle = "Laser-Focused Precision"
                role_image = "assets/recap_sharingan.jpg"
                role_desc = "Laser focus on a single domain to achieve mastery."
            else:
                role = "THE MULTITASKER"
                role_title = "THE MULTITASKER"
                role_subtitle = "Versatile Scholar"
                role_image = "assets/recap_multitasker.jpg"
                role_desc = "Perfect balance of discipline across all tasks."

        if len(completed_sessions) == 0:
            reason = "You have completed 0 focus sessions so far. Start your first focus session today to build your streak!"
        else:
            reason = f"You completed {len(completed_sessions)} focus sessions, logging {int(round(total_focus_minutes))} minutes of deep work. Excellent dedication."

        if len(completed_sessions) == 0:
            rating_val = 0.0
            tier = "TIER E"
        else:
            rating_val = min(10.0, 5.0 + (user_streak * 0.2) + (total_focus_minutes / 600.0))
            if rating_val >= 9.5:
                tier = "TIER S+"
            elif rating_val >= 8.5:
                tier = "TIER S"
            elif rating_val >= 7.0:
                tier = "TIER A"
            elif rating_val >= 5.0:
                tier = "TIER B"
            else:
                tier = "TIER C"
            
        return {
            "reason": reason,
            "image": "consistency_v2.png",
            "highlight_stat": str(user_balls),
            "label": "EARNED",
            "role": role,
            "role_title": role_title,
            "role_subtitle": role_subtitle,
            "role_image": role_image,
            "role_desc": role_desc,
            "total_focus_minutes": int(round(total_focus_minutes)),
            "total_focus_hours": int(round(total_focus_hours)),
            "journal_count": journal_count,
            "prime_rating": f"{rating_val:.1f}",
            "prime_tier": tier
        }

