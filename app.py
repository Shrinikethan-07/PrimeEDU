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
from backend.agents.core import FocusForgeAgent, DisciplineAgent, JournalEntry, VisualizerAgent

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
            },
            "clans": {}
        }
        save_db(_DB_CACHE)
    else:
        with open(DB_PATH, 'r') as f:
            _DB_CACHE = json.load(f)
        if "clans" not in _DB_CACHE:
            _DB_CACHE["clans"] = {}
            save_db(_DB_CACHE)

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
            if 'clan_id' not in profile: profile['clan_id'] = None
            if 'is_clan_leader' not in profile: profile['is_clan_leader'] = False
            if 'banned_clans' not in profile: profile['banned_clans'] = []
            if 'balls' not in profile: profile['balls'] = 0
            if 'streak' not in profile: profile['streak'] = 0
            return profile, uid
    return None, None

# --- Gamification Engine ---
def check_streak_and_login(user):
    last_login = user.get('last_login')
    now = datetime.now()
    if last_login:
        try:
            last_date = datetime.fromisoformat(last_login)
        except Exception:
            last_date = now - timedelta(days=2)
        # Use calendar date comparison, not timedelta
        days_diff = (now.date() - last_date.date()).days
        
        # Streak logic based on calendar days
        if days_diff == 1:
            # Exactly the next calendar day — increment streak
            user['streak'] = user.get('streak', 0) + 1
            if user['streak'] == 7: user['balls'] = user.get('balls', 0) + 20
            elif user['streak'] == 30: user['balls'] = user.get('balls', 0) + 100
            elif user['streak'] == 365: user['balls'] = user.get('balls', 0) + 1000
        elif days_diff > 1:
            # Missed a day — reset streak to 1 today
            user['streak'] = 1
        elif days_diff == 0:
            if user.get('streak', 0) == 0:
                user['streak'] = 1
        # If days_diff == 0, streak stays unchanged
    else:
        user['streak'] = 1
            
    user['last_login'] = now.isoformat()
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
visual_agent = VisualizerAgent()

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
    email = (data.get('email') or '').strip().lower()
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
        "creation_date": datetime.now().isoformat(),
        "clan_id": None,
        "is_clan_leader": False,
        "banned_clans": []
    }
    save_db(db)
    return jsonify({"status": "success"})

@app.route('/api/auth/login', methods=['POST'])
def login():
    db = load_db()
    data = request.json
    email = (data.get('email') or '').strip().lower()
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
    email = (request.json.get('email') or '').strip().lower()
    if email not in db['user_profiles']:
        return jsonify({"status": "error", "message": "Email not found"}), 404
        
    otp = str(random.randint(1000, 9999))
    db['user_profiles'][email]['reset_otp'] = otp
    save_db(db)
    
    print(f"\n{'='*40}\n[OTP SIMULATOR] OTP for {email}: {otp}\n{'='*40}\n")
    return jsonify({"status": "success", "message": "OTP sent to email"})

@app.route('/api/auth/otp/verify', methods=['POST'])
def verify_otp():
    db = load_db()
    data = request.json
    email = (data.get('email') or '').strip().lower()
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
    visuals = visual_agent.get_recap_visuals(sessions, tasks)
    return jsonify(visuals)

# --- BALLS UPDATE ENDPOINT ---
@app.route('/api/balls/update', methods=['POST'])
def update_balls():
    db = load_db()
    user, uid = get_current_user(db)
    if not user:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    delta = request.json.get('delta', 0) if request.json else 0
    user['balls'] = max(0, user.get('balls', 0) + delta)
    save_db(db)
    return jsonify({"status": "success", "balls": user['balls']})

# --- LEADERBOARD ENDPOINT ---
@app.route('/api/leaderboard', methods=['GET'])
def get_leaderboard():
    db = load_db()
    sort_by = request.args.get('sort_by', 'balls')
    
    users_list = []
    for uid, profile in db.get('user_profiles', {}).items():
        user_sessions = [s for s in db.get('sessions', []) if s.get('user_id') == uid and s.get('status') == 'completed']
        sessions_count = len(user_sessions)
        focus_duration_minutes = 0
        for s in user_sessions:
            try:
                start = datetime.fromisoformat(s['start_time'])
                end = datetime.fromisoformat(s['end_time'])
                diff = (end - start).total_seconds() / 60.0
                focus_duration_minutes += max(0.0, diff)
            except Exception:
                pass
        focus_duration_minutes = round(focus_duration_minutes, 1)
        
        users_list.append({
            "name": profile.get("leaderboard_name") or profile.get("name") or "Warrior",
            "email": profile.get("email") or uid,
            "balls": profile.get("balls", 0),
            "streak": profile.get("streak", 0),
            "avatar": profile.get("avatar", "itachi"),
            "sessions_count": sessions_count,
            "focus_duration_minutes": focus_duration_minutes
        })
        
    if sort_by == 'streak':
        users_list.sort(key=lambda x: x['streak'], reverse=True)
    elif sort_by == 'sessions':
        users_list.sort(key=lambda x: x['sessions_count'], reverse=True)
    elif sort_by == 'focus_duration':
        users_list.sort(key=lambda x: x['focus_duration_minutes'], reverse=True)
    else: # default 'balls'
        users_list.sort(key=lambda x: x['balls'], reverse=True)
        
    return jsonify(users_list)

# --- ADMIN ENDPOINT ---
@app.route('/api/admin/users', methods=['GET'])
def admin_users():
    db = load_db()
    user, uid = get_current_user(db)
    if not user or uid.lower() != 'buvanavel.m01@gmail.com':
        return jsonify({"status": "error", "message": "Unauthorized. Admin access required."}), 403
    
    users_data = []
    for email, profile in db.get('user_profiles', {}).items():
        users_data.append({
            "email": email,
            "name": profile.get("name", "Unknown"),
            "creation_date": profile.get("creation_date", ""),
            "last_login": profile.get("last_login", "")
        })
    
    users_data.sort(key=lambda x: x.get('creation_date', ''), reverse=True)
    return jsonify({"status": "success", "users": users_data})

# --- CLAN ENDPOINTS ---
@app.route('/api/clan/create', methods=['POST'])
def create_clan():
    db = load_db()
    user, uid = get_current_user(db)
    if not user:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
        
    if user.get('clan_id'):
        return jsonify({"status": "error", "message": "Already in a clan"}), 400
        
    name = request.json.get('name', '').strip() if request.json else ''
    if not name:
        return jsonify({"status": "error", "message": "Clan name required"}), 400
        
    import string
    chars = string.ascii_uppercase + string.digits
    invite_code = ''.join(random.choice(chars) for _ in range(6))
    while any(c.get('invite_code') == invite_code for c in db.get('clans', {}).values()):
        invite_code = ''.join(random.choice(chars) for _ in range(6))
        
    clan_id = "clan_" + str(int(datetime.now().timestamp()))
    
    db['clans'][clan_id] = {
        "id": clan_id,
        "name": name,
        "leader_email": uid,
        "invite_code": invite_code,
        "members": [uid],
        "max_members": 20,
        "terms": "",
        "created_at": datetime.now().isoformat(),
        "challenges": []
    }
    
    user['clan_id'] = clan_id
    user['is_clan_leader'] = True
    save_db(db)
    
    return jsonify({"status": "success", "clan": db['clans'][clan_id]})

@app.route('/api/clan/join', methods=['POST'])
def join_clan():
    db = load_db()
    user, uid = get_current_user(db)
    if not user:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
        
    if user.get('clan_id'):
        return jsonify({"status": "error", "message": "Already in a clan"}), 400
        
    code = (request.json.get('invite_code', '') if request.json else '').strip().upper()
    clan = None
    clan_id = None
    for cid, c in db.get('clans', {}).items():
        if c.get('invite_code', '').upper() == code:
            clan = c
            clan_id = cid
            break
            
    if not clan:
        return jsonify({"status": "error", "message": "Invalid invite code"}), 400
        
    if clan_id in user.get('banned_clans', []):
        return jsonify({"status": "error", "message": "You are banned from this clan"}), 403
        
    if len(clan.get('members', [])) >= clan.get('max_members', 20):
        return jsonify({"status": "error", "message": "Clan is full"}), 400
        
    if uid not in clan['members']:
        clan['members'].append(uid)
        
    user['clan_id'] = clan_id
    user['is_clan_leader'] = False
    save_db(db)
    
    return jsonify({"status": "success", "clan_id": clan_id})

@app.route('/api/clan/info', methods=['GET'])
def get_clan_info():
    db = load_db()
    user, uid = get_current_user(db)
    if not user:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
        
    clan_id = user.get('clan_id')
    if not clan_id:
        return jsonify({"status": "no_clan"})
        
    clan = db.get('clans', {}).get(clan_id)
    if not clan:
        user['clan_id'] = None
        user['is_clan_leader'] = False
        save_db(db)
        return jsonify({"status": "no_clan"})
        
    is_leader = (clan.get('leader_email') == uid)
    
    member_details = []
    for member_email in clan.get('members', []):
        m_profile = db.get('user_profiles', {}).get(member_email, {})
        member_details.append({
            "name": m_profile.get("name", "Warrior"),
            "email": member_email,
            "balls": m_profile.get("balls", 0),
            "streak": m_profile.get("streak", 0),
            "avatar": m_profile.get("avatar", "itachi")
        })
        
    response_data = {
        "status": "success",
        "id": clan_id,
        "name": clan.get("name"),
        "leader_email": clan.get("leader_email"),
        "members": member_details,
        "max_members": clan.get("max_members", 20),
        "terms": clan.get("terms", ""),
        "created_at": clan.get("created_at"),
        "challenges": clan.get("challenges", []),
        "is_leader": is_leader
    }
    
    if is_leader:
        response_data["invite_code"] = clan.get("invite_code")
        
    return jsonify(response_data)

@app.route('/api/clan/leave', methods=['POST'])
def leave_clan():
    db = load_db()
    user, uid = get_current_user(db)
    if not user:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
        
    clan_id = user.get('clan_id')
    if not clan_id:
        return jsonify({"status": "error", "message": "Not in a clan"}), 400
        
    clan = db.get('clans', {}).get(clan_id)
    if not clan:
        user['clan_id'] = None
        user['is_clan_leader'] = False
        save_db(db)
        return jsonify({"status": "success"})
        
    if clan.get('leader_email') == uid:
        # Disband clan
        for m_email in clan.get('members', []):
            m_profile = db.get('user_profiles', {}).get(m_email)
            if m_profile:
                m_profile['clan_id'] = None
                m_profile['is_clan_leader'] = False
        db.get('clans', {}).pop(clan_id, None)
    else:
        # Just leave
        if uid in clan.get('members', []):
            clan['members'].remove(uid)
        user['clan_id'] = None
        user['is_clan_leader'] = False
        
    save_db(db)
    return jsonify({"status": "success"})

@app.route('/api/clan/dismiss', methods=['POST'])
def dismiss_member():
    db = load_db()
    user, uid = get_current_user(db)
    if not user:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
        
    clan_id = user.get('clan_id')
    if not clan_id:
        return jsonify({"status": "error", "message": "Not in a clan"}), 400
        
    clan = db.get('clans', {}).get(clan_id)
    if not clan or clan.get('leader_email') != uid:
        return jsonify({"status": "error", "message": "Unauthorized. Clan leader only."}), 403
        
    member_email = (request.json.get('member_email', '') if request.json else '').strip().lower()
    if not member_email:
        return jsonify({"status": "error", "message": "Member email required"}), 400
        
    if member_email == uid:
        return jsonify({"status": "error", "message": "Cannot dismiss yourself"}), 400
        
    if member_email in clan.get('members', []):
        clan['members'].remove(member_email)
        
    m_profile = db.get('user_profiles', {}).get(member_email)
    if m_profile:
        m_profile['clan_id'] = None
        m_profile['is_clan_leader'] = False
        banned = m_profile.get('banned_clans', [])
        if clan_id not in banned:
            banned.append(clan_id)
        m_profile['banned_clans'] = banned
        
    save_db(db)
    return jsonify({"status": "success"})

@app.route('/api/clan/terms', methods=['POST'])
def update_terms():
    db = load_db()
    user, uid = get_current_user(db)
    if not user:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
        
    clan_id = user.get('clan_id')
    if not clan_id:
        return jsonify({"status": "error", "message": "Not in a clan"}), 400
        
    clan = db.get('clans', {}).get(clan_id)
    if not clan or clan.get('leader_email') != uid:
        return jsonify({"status": "error", "message": "Unauthorized. Clan leader only."}), 403
        
    terms = request.json.get('terms', '') if request.json else ''
    clan['terms'] = terms
    save_db(db)
    return jsonify({"status": "success"})

@app.route('/api/clan/delete', methods=['DELETE', 'POST'])
def delete_clan():
    db = load_db()
    user, uid = get_current_user(db)
    if not user:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
        
    clan_id = user.get('clan_id')
    if not clan_id:
        return jsonify({"status": "error", "message": "Not in a clan"}), 400
        
    clan = db.get('clans', {}).get(clan_id)
    if not clan or clan.get('leader_email') != uid:
        return jsonify({"status": "error", "message": "Unauthorized. Clan leader only."}), 403
        
    for m_email in clan.get('members', []):
        m_profile = db.get('user_profiles', {}).get(m_email)
        if m_profile:
            m_profile['clan_id'] = None
            m_profile['is_clan_leader'] = False
            
    db.get('clans', {}).pop(clan_id, None)
    save_db(db)
    return jsonify({"status": "success"})

@app.route('/api/clan/challenge', methods=['POST'])
def create_challenge():
    db = load_db()
    user, uid = get_current_user(db)
    if not user:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
        
    clan_id = user.get('clan_id')
    if not clan_id:
        return jsonify({"status": "error", "message": "Not in a clan"}), 400
        
    clan = db.get('clans', {}).get(clan_id)
    if not clan:
        return jsonify({"status": "error", "message": "Clan not found"}), 404
        
    data = request.json or {}
    title = data.get('title', 'Quick Focus Challenge').strip()
    try:
        duration = int(data.get('duration_minutes', 0))
    except ValueError:
        duration = 0
        
    challenge_id = "ch_" + str(int(datetime.now().timestamp()))
    
    challenge = {
        "id": challenge_id,
        "title": title,
        "duration_minutes": duration,
        "creator_email": uid,
        "creator_name": user.get('name', 'Warrior'),
        "created_at": datetime.now().isoformat(),
        "expires_at": (datetime.now() + timedelta(minutes=7)).isoformat(),
        "accepted_by": None,
        "status": "open"
    }
    
    if 'challenges' not in clan:
        clan['challenges'] = []
    clan['challenges'].append(challenge)
    save_db(db)
    
    return jsonify({"status": "success", "challenge": challenge})

@app.route('/api/clan/challenge/accept', methods=['POST'])
def accept_challenge():
    db = load_db()
    user, uid = get_current_user(db)
    if not user:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
        
    clan_id = user.get('clan_id')
    if not clan_id:
        return jsonify({"status": "error", "message": "Not in a clan"}), 400
        
    clan = db.get('clans', {}).get(clan_id)
    if not clan:
        return jsonify({"status": "error", "message": "Clan not found"}), 404
        
    challenge_id = (request.json.get('challenge_id', '') if request.json else '').strip()
    
    challenge = None
    for ch in clan.get('challenges', []):
        if ch.get('id') == challenge_id:
            challenge = ch
            break
            
    if not challenge:
        return jsonify({"status": "error", "message": "Challenge not found"}), 404
        
    if challenge.get('status') != 'open' or challenge.get('accepted_by'):
        return jsonify({"status": "error", "message": "Challenge already accepted or closed"}), 400
        
    try:
        expires = datetime.fromisoformat(challenge.get('expires_at'))
        if datetime.now() > expires:
            return jsonify({"status": "error", "message": "Challenge has expired"}), 400
    except Exception:
        pass
        
    if challenge.get('creator_email') == uid:
        return jsonify({"status": "error", "message": "Cannot accept your own challenge"}), 400
        
    challenge['accepted_by'] = uid
    challenge['status'] = 'active'
    save_db(db)
    
    return jsonify({"status": "success", "challenge": challenge})

@app.route('/api/clan/challenges', methods=['GET'])
def list_challenges():
    db = load_db()
    user, uid = get_current_user(db)
    if not user:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
        
    clan_id = user.get('clan_id')
    if not clan_id:
        return jsonify({"status": "error", "message": "Not in a clan"}), 400
        
    clan = db.get('clans', {}).get(clan_id)
    if not clan:
        return jsonify({"status": "error", "message": "Clan not found"}), 404
        
    return jsonify(clan.get('challenges', []))

if __name__ == '__main__':
    print("PrimeEDU Local Server Starting...")
    app.run(debug=True, host='0.0.0.0', port=5000)
