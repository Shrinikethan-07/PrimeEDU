import unittest
import json
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import app, load_db, save_db

class TestStrIndex(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        db = load_db()
        self.email = "test_str_index@test.com"
        self.token = "token_str_index"
        db['user_profiles'][self.email] = {
            "name": "Str Index Test",
            "email": self.email,
            "password_hash": "mock",
            "active_tokens": [self.token],
            "balls": 10,
            "massive_goals": [
                {
                    "title": "Some Goal",
                    "deadline": "2026-06-05T11:04:52.429884+00:00"
                }
            ]
        }
        save_db(db)

    def test_str_index_cancellation(self):
        response = self.client.post('/api/user/destiny/cancel', json={
            "goal_index": "0" # String representation of 0
        }, headers={
            'Authorization': f'Bearer {self.token}'
        })
        # If it raises TypeError, this will return 500 instead of 200 or 400
        print("Response status code for string index cancellation:", response.status_code)
        self.assertNotEqual(response.status_code, 500)

if __name__ == '__main__':
    unittest.main()
