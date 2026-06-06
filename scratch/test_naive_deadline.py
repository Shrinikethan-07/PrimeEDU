import unittest
import json
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import app, load_db, save_db

class TestNaiveDeadline(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        db = load_db()
        self.email = "test_naive@test.com"
        self.token = "token_naive"
        db['user_profiles'][self.email] = {
            "name": "Naive Test",
            "email": self.email,
            "password_hash": "mock",
            "active_tokens": [self.token],
            "balls": 10,
            "massive_goals": [
                {
                    "title": "Expired Naive Goal",
                    "deadline": "2020-01-01T12:00:00" # Naive ISO format
                }
            ]
        }
        save_db(db)

    def test_naive_deadline_cancellation(self):
        response = self.client.post('/api/user/destiny/cancel', json={
            "goal_index": 0
        }, headers={
            'Authorization': f'Bearer {self.token}'
        })
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data.decode('utf-8'))
        # If it failed to parse safely, it will catch the TypeError and keep is_early = True,
        # thereby deducting 5 balls. Since they had 10 balls, it would return 5 balls.
        # But since the goal is clearly expired (2020), there should be NO penalty and it should return 10 balls.
        print("Balls returned after canceling expired naive goal:", data['balls'])
        self.assertEqual(data['balls'], 10)

if __name__ == '__main__':
    unittest.main()
