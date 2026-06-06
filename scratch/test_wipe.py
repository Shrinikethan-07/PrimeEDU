import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import unittest
import json
import shutil
from app import app, load_db, save_db

class TestAdminEndpoints(unittest.TestCase):
    def setUp(self):
        # Backup the current database file if it exists
        self.db_backup = "data/db.json.bak"
        if os.path.exists("data/db.json"):
            shutil.copy2("data/db.json", self.db_backup)
        
        # Load database and insert mock entries
        db = load_db()
        
        # Insert admin user
        self.admin_email = "buvanavel.m01@gmail.com"
        self.admin_token = "mock_admin_token_xyz"
        db['user_profiles'][self.admin_email] = {
            "name": "Admin Leader",
            "leaderboard_name": "Shrinikethan M S", # The user changed their name here
            "email": self.admin_email,
            "password_hash": "mock_hash",
            "active_tokens": [self.admin_token],
            "clan_id": "clan_test_123",
            "is_clan_leader": True
        }
        
        # Insert fake warriors
        db['user_profiles']['user_a@test.com'] = {
            "name": "Warrior A",
            "leaderboard_name": "Warrior A",
            "email": "user_a@test.com",
            "password_hash": "mock_hash",
            "active_tokens": ["token_a"]
        }
        db['user_profiles']['warrior2@test.com'] = {
            "name": "Warrior Two",
            "leaderboard_name": "Warrior Two",
            "email": "warrior2@test.com",
            "password_hash": "mock_hash",
            "active_tokens": ["token_two"]
        }
        
        # Insert mock clan
        db['clans'] = {
            "clan_test_123": {
                "id": "clan_test_123",
                "name": "Test Clan",
                "leader_email": self.admin_email,
                "members": [self.admin_email]
            }
        }
        
        # Insert mock sessions
        db['sessions'] = [
            {"id": "sess_1", "user_id": self.admin_email, "status": "completed"},
            {"id": "sess_2", "user_id": "user_a@test.com", "status": "completed"}
        ]
        
        # Insert mock journals
        db['journal'] = [
            {"id": 1, "user_id": self.admin_email, "title": "Admin Journal"},
            {"id": 2, "user_id": "user_a@test.com", "title": "Fake Journal"}
        ]
        
        # Insert mock tasks
        db['tasks'] = [
            {"id": "task_1", "user_id": self.admin_email, "title": "Admin Task"},
            {"id": "task_2", "user_id": "user_a@test.com", "title": "Fake Task"}
        ]
        
        save_db(db)
        self.client = app.test_client()

    def tearDown(self):
        # Restore the database backup
        if os.path.exists(self.db_backup):
            shutil.copy2(self.db_backup, "data/db.json")
            os.remove(self.db_backup)
        elif os.path.exists("data/db.json"):
            os.remove("data/db.json")

    def test_admin_users_display_name(self):
        # Call the admin users endpoint
        response = self.client.get('/api/admin/users', headers={
            'Authorization': f'Bearer {self.admin_token}'
        })
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data.decode('utf-8'))
        
        # Check that Shrinikethan M S is returned instead of Admin Leader
        users = data.get('users', [])
        admin_entry = next((u for u in users if u['email'] == self.admin_email), None)
        self.assertIsNotNone(admin_entry)
        self.assertEqual(admin_entry['name'], "Shrinikethan M S")
        print("OK: Admin users endpoint successfully resolved updated display name!")

    def test_reset_fake_warriors(self):
        # Call the reset fake warriors endpoint
        response = self.client.post('/api/admin/reset_fake_warriors', headers={
            'Authorization': f'Bearer {self.admin_token}'
        })
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data.decode('utf-8'))
        self.assertEqual(data['status'], 'success')
        
        # Load the database after wipe
        db = load_db()
        
        # Verify that only the admin remains
        self.assertEqual(list(db['user_profiles'].keys()), [self.admin_email])
        
        # Verify admin active tokens were kept (so admin stays logged in)
        self.assertEqual(db['user_profiles'][self.admin_email]['active_tokens'], [self.admin_token])
        
        # Verify admin clan settings were reset
        self.assertIsNone(db['user_profiles'][self.admin_email]['clan_id'])
        self.assertFalse(db['user_profiles'][self.admin_email]['is_clan_leader'])
        
        # Verify clans were wiped
        self.assertEqual(db['clans'], {})
        
        # Verify sessions, journals, and tasks were filtered
        self.assertEqual(len(db['sessions']), 1)
        self.assertEqual(db['sessions'][0]['id'], "sess_1")
        
        self.assertEqual(len(db['journal']), 1)
        self.assertEqual(db['journal'][0]['id'], 1)
        
        self.assertEqual(len(db['tasks']), 1)
        self.assertEqual(db['tasks'][0]['id'], "task_1")
        
        print("OK: Fake warriors reset endpoint successfully wiped fake entries while preserving admin's profile and token!")

if __name__ == '__main__':
    unittest.main()
