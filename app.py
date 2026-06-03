from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_cors import CORS
import os
import json
from datetime import datetime, timedelta
import asyncio
import secrets
import hashlib
import random
from apscheduler.schedulers.background import BackgroundScheduler
from backend.agents.core import FocusForgeAgent, DisciplineAgent, JournalEntry

app = Flask(__name__, static_folder='.', template_folder='.')
CORS(app)

DB_PATH = 'data/db.json'
_DB_CACHE = None

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def init_db():
    global _DB_CACHE
    if not os.path.exists('data'):
        os.makedirs('data')
    if not os.path.exists(DB_PATH):
        _DB_CACHE = {
            "user_profiles": {},
            "sessions": [],
            "tasks": [],
            "syllabus_progress": {},
            "topic_notes": {},
            "journal": [],
            "custom_syllabus": {
                "physics": [], "chemistry": [], "biology": [], "mathematics": []
            }
        }
        save_db(_DB_CACHE)
    else:
        with open(DB_PATH, 'r') as f:
            _DB_CACHE = json.load(f)

def load_db():
    return _DB_CACHE

def save_db(data):
    global _DB_CACHE
    _DB_CACHE = data
    with open(DB_PATH, 'w') as f:
        json.dump(data, f, indent=4)

init_db()

def get_current_user(db):
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return None, None
    token = auth_header.split(' ')[1]
    
    for uid, profile in db.get('user_profiles', {}).items():
        if token in profile.get('active_tokens', []):
            return profile, uid
    return None, None

# --- Gamification Engine ---
def check_streak_and_login(user):
    last_login = user.get('last_login')
    if last_login:
        last_date = datetime.fromisoformat(last_login)
        now = datetime.now()
        diff = now - last_date
        
        # Streak logic
        if diff.days == 1:
            user['streak'] += 1
            if user['streak'] == 7: user['balls'] += 20
            elif user['streak'] == 30: user['balls'] += 100
            elif user['streak'] == 365: user['balls'] += 1000
        elif diff.days > 1:
            user['streak'] = 0 # reset
            
    user['last_login'] = datetime.now().isoformat()
    return user

# --- Cron Job / Scheduler ---
def midnight_wipe():
    print("Running 24-Hour Automated Refresh...")
    db = load_db()
    db['tasks'] = [] # wipe daily routines
    save_db(db)

scheduler = BackgroundScheduler()
scheduler.add_job(func=midnight_wipe, trigger="cron", hour=0, minute=0)
scheduler.start()

journal_agent = FocusForgeAgent(api_key="LOCAL_DEV")
discipline_agent = DisciplineAgent()


@app.route('/')
def index():
    return send_from_directory('.', 'login.html')

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory('.', path)

# --- AUTH ENDPOINTS ---
@app.route('/api/auth/register', methods=['POST'])
def register():
    db = load_db()
    data = request.json
    email = data.get('email')
    password = data.get('password')
    name = data.get('name', 'Warrior')
    
    if not email or not password:
        return jsonify({"status": "error", "message": "Email and password required"}), 400
        
    if email in db['user_profiles']:
        return jsonify({"status": "error", "message": "Email already registered"}), 400
        
    db['user_profiles'][email] = {
        "name": name,
        "leaderboard_name": name,
        "email": email,
        "password_hash": hash_password(password),
        "active_tokens": [],
        "balls": 0,
        "streak": 0,
        "last_login": datetime.now().isoformat(),
        "massive_goals": [],
        "avatar": "itachi",
        "creation_date": datetime.now().isoformat()
    }
    save_db(db)
    return jsonify({"status": "success"})

@app.route('/api/auth/login', methods=['POST'])
def login():
    db = load_db()
    data = request.json
    email = data.get('email')
    password = data.get('password')
    
    user = db['user_profiles'].get(email)
    if user and user.get('password_hash') == hash_password(password):
        token = secrets.token_hex(32)
        if 'active_tokens' not in user:
            user['active_tokens'] = []
        user['active_tokens'].append(token)
        save_db(db)
        return jsonify({"status": "success", "token": token, "name": user.get('name')})
        
    return jsonify({"status": "error", "message": "Invalid credentials"}), 401

@app.route('/api/auth/otp/request', methods=['POST'])
def request_otp():
    db = load_db()
    email = request.json.get('email')
    if email not in db['user_profiles']:
        return jsonify({"status": "error", "message": "Email not found"}), 404
        
    otp = str(random.randint(1000, 9999))
    db['user_profiles'][email]['reset_otp'] = otp
    save_db(db)
    
    print(f"\n{'='*40}\n[EMAIL OTP SIMULATOR] OTP for {email}: {otp}\n{'='*40}\n")
    return jsonify({"status": "success", "message": "OTP sent to email"})

@app.route('/api/auth/otp/verify', methods=['POST'])
def verify_otp():
    db = load_db()
    data = request.json
    email = data.get('email')
    otp = data.get('otp')
    new_password = data.get('new_password')
    
    user = db['user_profiles'].get(email)
    if user and user.get('reset_otp') == otp:
        user['password_hash'] = hash_password(new_password)
        user['reset_otp'] = None
        user['active_tokens'] = [] # Log out all devices on reset
        save_db(db)
        return jsonify({"status": "success", "message": "Password reset successful"})
        
    return jsonify({"status": "error", "message": "Invalid OTP"}), 400

@app.route('/api/auth/logout_all', methods=['POST'])
def logout_all():
    db = load_db()
    user, uid = get_current_user(db)
    if not user:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    
    current_token = request.headers.get('Authorization').split(' ')[1]
    db['user_profiles'][uid]['active_tokens'] = [current_token]
    save_db(db)
    return jsonify({"status": "success"})


# --- USER ENDPOINTS ---
@app.route('/api/user/profile', methods=['GET', 'POST'])
def handle_profile():
    db = load_db()
    user, uid = get_current_user(db)
    if not user:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
        
    user = check_streak_and_login(user)
    
    if request.method == 'POST':
        data = request.json
        if 'leaderboard_name' in data:
            user['leaderboard_name'] = data['leaderboard_name']
            
        if 'massive_goal' in data:
            new_goal = data['massive_goal']
            goals = user.get('massive_goals', [])
            
            if len(goals) >= 4:
                return jsonify({"status": "error", "message": "Max 4 concurrent destinies allowed."}), 403
            
            # Prevent overlapping end dates
            for g in goals:
                if g['deadline'][:10] == new_goal['deadline'][:10]:
                    return jsonify({"status": "error", "message": "Cannot have overlapping destinies ending on the same day."}), 403
                    
            goals.append(new_goal)
            user['massive_goals'] = goals
            user['balls'] += 50 # Reward
            
        save_db(db)
        return jsonify({"status": "success"})
        
    save_db(db)
    
    # Calculate account age for Recaps
    created = datetime.fromisoformat(user.get('creation_date', datetime.now().isoformat()))
    age_days = (datetime.now() - created).days
    user['account_age_days'] = age_days
    
    return jsonify(user)

@app.route('/api/user/destiny/cancel', methods=['POST'])
def cancel_destiny():
    db = load_db()
    user, uid = get_current_user(db)
    if not user:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
        
    data = request.json
    goal_index = data.get('goal_index')
    goals = user.get('massive_goals', [])
    
    if 0 <= goal_index < len(goals):
        goals.pop(goal_index)
        user['massive_goals'] = goals
        user['balls'] -= 5 # Cancellation penalty
        save_db(db)
        return jsonify({"status": "success", "balls": user['balls']})
    return jsonify({"status": "error", "message": "Goal not found"}), 404

@app.route('/api/user/avatar', methods=['GET', 'POST'])
def handle_avatar():
    db = load_db()
    user, uid = get_current_user(db)
    if not user:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
        
    if request.method == 'POST':
        avatar = request.json.get('avatar', 'itachi')
        user['avatar'] = avatar
        save_db(db)
        return jsonify({"status": "success", "avatar": avatar})
    return jsonify({"avatar": user.get('avatar', 'itachi')})


@app.route('/api/journal/sync', methods=['POST'])
def sync_journal():
    db = load_db()
    user, uid = get_current_user(db)
    if not user:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
    
    data = request.json
    entries = data.get('entries', [])
    for e in entries:
        e['user_id'] = uid
        
    db['journal'] = [j for j in db['journal'] if j.get('user_id') != uid] + entries
    save_db(db)
    return jsonify({'status': 'success'})

@app.route('/api/journal', methods=['POST'])
def submit_journal():
    db = load_db()
    user, uid = get_current_user(db)
    if not user:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
        
    data = request.json
    content = data.get('content')
    title = data.get('title', f"Entry_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    
    entry_obj = JournalEntry(
        user_id=uid,
        content=content,
        timestamp=datetime.now(),
        mood_score=7
    )
    
    db['journal'].append({
        "user_id": uid,
        "id": int(datetime.now().timestamp()),
        "title": title,
        "content": content,
        "timestamp": datetime.now().isoformat()
    })
    save_db(db)
    
    analysis = asyncio.run(journal_agent.analyze_journal(entry_obj))
    recap = asyncio.run(journal_agent.generate_recap_card([entry_obj], period="Daily"))
    
    return jsonify({"status": "success", "recap": {"title": recap.title, "content": recap.content, "sentiment": recap.sentiment}})

@app.route('/api/tasks', methods=['GET', 'POST'])
def handle_tasks():
    db = load_db()
    user, uid = get_current_user(db)
    if not user:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
        
    user_tasks = [t for t in db['tasks'] if t.get('user_id') == uid]
    if request.method == 'POST':
        task = request.json
        task['id'] = len(db['tasks']) + 1
        task['user_id'] = uid
        db['tasks'].append(task)
        save_db(db)
        return jsonify({"status": "success", "task": task})
    return jsonify(user_tasks)

@app.route('/api/tasks/sync', methods=['POST'])
def sync_tasks():
    db = load_db()
    user, uid = get_current_user(db)
    if not user:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
        
    data = request.json
    new_tasks = data.get('tasks', [])
    for t in new_tasks: t['user_id'] = uid
    
    # Remove old tasks for this user, insert new ones
    db['tasks'] = [t for t in db['tasks'] if t.get('user_id') != uid] + new_tasks
    
    # Very basic balls reward logic (simplified)
    new_completed = len([t for t in new_tasks if t.get('completed')])
    db['user_profiles'][uid]['balls'] += (new_completed * 2) # small reward
        
    save_db(db)
    return jsonify({"status": "success"})

@app.route('/api/sessions/start', methods=['POST'])
def start_session():
    db = load_db()
    user, uid = get_current_user(db)
    if not user:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
        
    session = {
        "id": f"sess_{int(datetime.now().timestamp())}",
        "user_id": uid,
        "subject": request.json.get("subject", "General") if request.json else "General",
        "mode": request.json.get("mode", "Custom duration") if request.json else "Custom duration",
        "start_time": datetime.now().isoformat(),
        "status": "running"
    }
    db['sessions'].append(session)
    save_db(db)
    return jsonify({"status": "success", "session": session})

@app.route('/api/sessions/end', methods=['POST'])
def end_session():
    db = load_db()
    user, uid = get_current_user(db)
    if not user:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
        
    data = request.json or {}
    session_id = data.get("session_id")
    early_exit = data.get("early_exit", False)
    
    for s in db['sessions']:
        if s['id'] == session_id and s.get('user_id') == uid:
            s['end_time'] = datetime.now().isoformat()
            s['status'] = "completed" if not early_exit else "early_exit"
            
            earned = 45 if not early_exit else 10
            db['user_profiles'][uid]['balls'] += earned
            save_db(db)
            return jsonify({"status": "success", "balls_earned": earned})
            
    return jsonify({"status": "error", "message": "Session not found"}), 404

@app.route('/api/recap/dynamic', methods=['GET'])
def get_dynamic_recap():
    db = load_db()
    user, uid = get_current_user(db)
    if not user:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
        
    sessions = [s for s in db.get('sessions', []) if s.get('user_id') == uid]
    tasks = [t for t in db.get('tasks', []) if t.get('user_id') == uid]
    visuals = {}
    return jsonify(visuals)


@app.route('/api/leaderboard', methods=['GET'])
def get_leaderboard():
    db = load_db()
    users = list(db.get('user_profiles', {}).values())
    users.sort(key=lambda x: x.get('balls', 0), reverse=True)
    
    leaderboard = []
    for u in users[:10]:
        leaderboard.append({
            "name": u.get("leaderboard_name", u.get("name", "Warrior")),
            "avatar": u.get("avatar", "itachi"),
            "balls": u.get("balls", 0),
            "streak": u.get("streak", 0)
        })
    return jsonify(leaderboard)

@app.route('/api/admin/users', methods=['GET'])
def admin_users():
    db = load_db()
    user, email = get_current_user(db)
    if not user or user.get('name', '').strip().lower() != 'shrinikethan m s' or email.strip().lower() != 'buvanavel.m01@gmail.com':
        return jsonify({"status": "error", "message": "Unauthorized. Admin access required."}), 403
    
    users_data = []
    for email, profile in db.get('user_profiles', {}).items():
        users_data.append({
            "email": email,
            "name": profile.get("name", "Unknown"),
            "balls": profile.get("balls", 0),
            "streak": profile.get("streak", 0),
            "creation_date": profile.get("creation_date", ""),
            "last_login": profile.get("last_login", "")
        })
    
    # Sort by creation date descending
    users_data.sort(key=lambda x: x.get('creation_date', ''), reverse=True)
    return jsonify({"status": "success", "users": users_data})

if __name__ == '__main__':
    print("PrimeEDU Local Server Starting...")
    app.run(debug=True, host='0.0.0.0', port=5000)
