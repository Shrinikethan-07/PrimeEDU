import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import unittest
from datetime import datetime, timedelta, timezone
from app import app, load_db, save_db, check_streak_and_login, recalculate_user_streak, get_ist_now, get_ist_iso, mark_user_active_today

class TestStreakLogic(unittest.TestCase):
    def setUp(self):
        self.db_backup = "data/db.json.bak"
        if os.path.exists("data/db.json"):
            import shutil
            shutil.copy2("data/db.json", self.db_backup)
        
        # Load database and reset
        db = load_db()
        db['user_profiles'] = {}
        db['sessions'] = []
        db['journal'] = []
        save_db(db)

    def tearDown(self):
        if os.path.exists(self.db_backup):
            import shutil
            shutil.copy2(self.db_backup, "data/db.json")
            os.remove(self.db_backup)
        elif os.path.exists("data/db.json"):
            os.remove("data/db.json")

    def test_new_user_active_days(self):
        db = load_db()
        email = "streak_test@test.com"
        now_ist = get_ist_now()
        
        # Simulating registration on June 5, 2026
        reg_time = (now_ist - timedelta(days=2))
        db['user_profiles'][email] = {
            "name": "Streak Tester",
            "email": email,
            "streak": 0,
            "last_login": reg_time.isoformat(),
            "creation_date": reg_time.isoformat(),
            "active_tokens": ["mock_token"]
        }
        save_db(db)
        
        # 1. On June 5 (day of registration), they logged in.
        # Let's check recalculate_user_streak for June 5.
        user = db['user_profiles'][email]
        mark_user_active_today(user) # Adds today (June 7) to active_days
        
        # Backpopulate June 5 and June 6 as active days to simulate logins on those days
        user['active_days'] = [
            (now_ist - timedelta(days=2)).date().isoformat(), # June 5
            (now_ist - timedelta(days=1)).date().isoformat(), # June 6
            now_ist.date().isoformat()                        # June 7
        ]
        save_db(db)
        
        # Re-load
        db = load_db()
        user = db['user_profiles'][email]
        
        # Recalculate streak
        streak = recalculate_user_streak(user, db)
        self.assertEqual(streak, 3)
        print("OK: Recalculate streak counted 3 consecutive calendar days!")
        
        # 2. Check check_streak_and_login heals/maintains this
        user = check_streak_and_login(user, db)
        self.assertEqual(user['streak'], 3)
        print("OK: check_streak_and_login healed/updated streak to 3!")

if __name__ == '__main__':
    unittest.main()
