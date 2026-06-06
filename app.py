from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_cors import CORS
import os
import json
import psycopg2
from datetime import datetime, timedelta, timezone
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

def get_ist_now():
    return datetime.now(timezone(timedelta(hours=5, minutes=30)))

def get_ist_iso():
    return get_ist_now().isoformat()

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def prune_old_data(db):
    now_ist = get_ist_now()
    
    # 1. Prune sessions older than 2 days (48 hours)
    if 'sessions' in db:
        new_sessions = []
        for s in db['sessions']:
            try:
                t_str = s.get('end_time') or s.get('start_time')
                if t_str:
                    t = datetime.fromisoformat(t_str)
                    if t.tzinfo is None:
                        t = t.replace(tzinfo=timezone(timedelta(hours=5, minutes=30)))
                    else:
                        t = t.astimezone(timezone(timedelta(hours=5, minutes=30)))
                    if now_ist - t <= timedelta(days=2):
                        new_sessions.append(s)
                else:
                    new_sessions.append(s)
            except Exception:
                new_sessions.append(s)
        db['sessions'] = new_sessions

    # 2. Prune journals older than 7 days (1 week)
    if 'journal' in db:
        new_journals = []
        for j in db['journal']:
            try:
                t_str = j.get('timestamp')
                if t_str:
                    t = datetime.fromisoformat(t_str)
                    if t.tzinfo is None:
                        t = t.replace(tzinfo=timezone(timedelta(hours=5, minutes=30)))
                    else:
                        t = t.astimezone(timezone(timedelta(hours=5, minutes=30)))
                    if now_ist - t <= timedelta(days=7):
                        new_journals.append(j)
                else:
                    new_journals.append(j)
            except Exception:
                new_journals.append(j)
        db['journal'] = new_journals

def sanitize_timestamps(db):
    updated = False
    if 'user_profiles' in db:
        for email, profile in db['user_profiles'].items():
            for key in ['creation_date', 'last_login']:
                val = profile.get(key)
                if val and isinstance(val, str):
                    if 'T' in val and '+' not in val and '-' not in val[-6:] and not val.endswith('Z'):
                        profile[key] = val + '+05:30'
                        updated = True
    return updated

DATABASE_URL = os.environ.get('DATABASE_URL')

def init_postgres():
    if not DATABASE_URL:
        print("[INFO] No DATABASE_URL set. Storing data locally.")
        return
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS primeedu_db (
                id INT PRIMARY KEY,
                data JSONB
            );
        """)
        cur.execute("SELECT COUNT(*) FROM primeedu_db WHERE id = 1;")
        if cur.fetchone()[0] == 0:
            template = {
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
            cur.execute("INSERT INTO primeedu_db (id, data) VALUES (1, %s);", (json.dumps(template),))
        conn.commit()
        cur.close()
        conn.close()
        print("[INFO] PostgreSQL database initialized successfully.")
    except Exception as e:
        print(f"[ERROR] Failed to initialize PostgreSQL database: {e}")

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
        with open(DB_PATH, 'w') as f:
            json.dump(_DB_CACHE, f, indent=4)
    else:
        with open(DB_PATH, 'r') as f:
            _DB_CACHE = json.load(f)
        if "clans" not in _DB_CACHE:
            _DB_CACHE["clans"] = {}
            with open(DB_PATH, 'w') as f:
                json.dump(_DB_CACHE, f, indent=4)

def load_db():
    global _DB_CACHE
    if DATABASE_URL:
        try:
            conn = psycopg2.connect(DATABASE_URL)
            cur = conn.cursor()
            cur.execute("SELECT data FROM primeedu_db WHERE id = 1;")
            row = cur.fetchone()
            if row:
                _DB_CACHE = row[0]
                if "clans" not in _DB_CACHE:
                    _DB_CACHE["clans"] = {}
                
                # Prune and save if changed
                old_len_s = len(_DB_CACHE.get('sessions', []))
                old_len_j = len(_DB_CACHE.get('journal', []))
                prune_old_data(_DB_CACHE)
                sanitized = sanitize_timestamps(_DB_CACHE)
                if len(_DB_CACHE.get('sessions', [])) != old_len_s or len(_DB_CACHE.get('journal', [])) != old_len_j or sanitized:
                    cur.execute("UPDATE primeedu_db SET data = %s WHERE id = 1;", (json.dumps(_DB_CACHE),))
                    conn.commit()
                
                cur.close()
                conn.close()
                return _DB_CACHE
            cur.close()
            conn.close()
        except Exception as e:
            print(f"[ERROR] Failed to load from PostgreSQL, falling back to local file: {e}")
            
    if _DB_CACHE is None:
        init_db()
        
    old_len_s = len(_DB_CACHE.get('sessions', []))
    old_len_j = len(_DB_CACHE.get('journal', []))
    prune_old_data(_DB_CACHE)
    sanitized = sanitize_timestamps(_DB_CACHE)
    if len(_DB_CACHE.get('sessions', [])) != old_len_s or len(_DB_CACHE.get('journal', [])) != old_len_j or sanitized:
        with open(DB_PATH, 'w') as f:
            json.dump(_DB_CACHE, f, indent=4)
            
    return _DB_CACHE

def save_db(data):
    global _DB_CACHE
    _DB_CACHE = data
    if DATABASE_URL:
        try:
            conn = psycopg2.connect(DATABASE_URL)
            cur = conn.cursor()
            cur.execute("UPDATE primeedu_db SET data = %s WHERE id = 1;", (json.dumps(data),))
            conn.commit()
            cur.close()
            conn.close()
            return
        except Exception as e:
            print(f"[ERROR] Failed to save to PostgreSQL: {e}")
            
    with open(DB_PATH, 'w') as f:
        json.dump(data, f, indent=4)

init_db()
init_postgres()

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
    now = get_ist_now()
    if last_login:
        try:
            last_date = datetime.fromisoformat(last_login)
            if last_date.tzinfo is None:
                last_date = last_date.replace(tzinfo=timezone(timedelta(hours=5, minutes=30)))
            else:
                last_date = last_date.astimezone(timezone(timedelta(hours=5, minutes=30)))
        except Exception:
            last_date = now - timedelta(days=2)
        # Use calendar date comparison in IST
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
            
    user['last_login'] = get_ist_iso()
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
@app.route('/api/auth/register/request_otp', methods=['POST'])
def register_request_otp_route():
    db = load_db()
    data = request.json or {}
    email = (data.get('email') or '').strip().lower()
    
    if not email:
        return jsonify({"status": "error", "message": "Email is required"}), 400
        
    if email in db.get('user_profiles', {}):
        return jsonify({"status": "error", "message": "Email already registered"}), 400
        
    otp = str(random.randint(1000, 9999))
    
    if 'pending_register_otps' not in db:
        db['pending_register_otps'] = {}
        
    db['pending_register_otps'][email] = {
        "otp": otp,
        "timestamp": get_ist_iso()
    }
    save_db(db)
    
    sent = send_otp_email(email, otp, is_registration=True)
    if sent:
        return jsonify({"status": "success", "message": "Verification OTP sent to your email."})
    else:
        return jsonify({"status": "success", "message": "Verification OTP sent (Console Fallback)." })

@app.route('/api/auth/register', methods=['POST'])
def register():
    db = load_db()
    data = request.json or {}
    email = (data.get('email') or '').strip().lower()
    password = data.get('password')
    name = data.get('name', 'Warrior')
    otp = data.get('otp')
    
    if not email or not password or not otp:
        return jsonify({"status": "error", "message": "Email, password, and OTP required"}), 400
        
    if email in db.get('user_profiles', {}):
        return jsonify({"status": "error", "message": "Email already registered"}), 400
        
    # Check pending registration OTP
    pending = db.get('pending_register_otps', {}).get(email)
    if not pending or pending.get('otp') != otp:
        return jsonify({"status": "error", "message": "Invalid verification OTP"}), 400
        
    # Remove OTP from pending list
    db['pending_register_otps'].pop(email, None)
    
    db['user_profiles'][email] = {
        "name": name,
        "leaderboard_name": name,
        "email": email,
        "password_hash": hash_password(password),
        "active_tokens": [],
        "balls": 0,
        "streak": 0,
        "last_login": get_ist_iso(),
        "massive_goals": [],
        "avatar": "itachi",
        "creation_date": get_ist_iso(),
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
        user = check_streak_and_login(user)
        save_db(db)
        return jsonify({"status": "success", "token": token, "name": user.get('name')})
        
    return jsonify({"status": "error", "message": "Invalid credentials"}), 401

def send_otp_email(to_email, otp, is_registration=False):
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    
    smtp_email = os.environ.get('SMTP_EMAIL')
    smtp_password = os.environ.get('SMTP_PASSWORD')
    
    if not smtp_email or not smtp_password:
        print(f"\n{'='*40}\n[OTP FALLBACK] SMTP not configured. OTP for {to_email}: {otp}\n{'='*40}\n")
        return False
        
    try:
        msg = MIMEMultipart()
        msg['From'] = smtp_email
        msg['To'] = to_email
        
        if is_registration:
            msg['Subject'] = "PrimeEDU - Warrior Registration Verification OTP"
            body = f"""Greetings Warrior!

Welcome to PrimeEDU. To complete your identity forging and verify your Google email address, please use the following OTP:

Verification OTP: {otp}

Enter this code in the registration form to finalize your registration.

Stay focused on your journey!
- PrimeEDU System
"""
        else:
            msg['Subject'] = "PrimeEDU - Warrior Password Reset OTP"
            body = f"""Greetings Warrior!

You have requested a password reset for your PrimeEDU account.

Your Verification OTP is: {otp}

Enter this code in the app to forge a new password. If you did not request this, please ignore this email.

Stay focused on your journey!
- PrimeEDU System
"""
        msg.attach(MIMEText(body, 'plain'))
        
        # Support default smtp.gmail.com
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(smtp_email, smtp_password)
        server.sendmail(smtp_email, to_email, msg.as_string())
        server.quit()
        print(f"[SMTP] Successfully sent OTP email to {to_email}")
        return True
    except Exception as e:
        print(f"[SMTP ERROR] Failed to send OTP email: {e}")
        return False

@app.route('/api/auth/otp/request', methods=['POST'])
def request_otp():
    db = load_db()
    email = (request.json.get('email') or '').strip().lower()
    if email not in db['user_profiles']:
        return jsonify({"status": "error", "message": "Email not found"}), 404
        
    otp = str(random.randint(1000, 9999))
    db['user_profiles'][email]['reset_otp'] = otp
    save_db(db)
    
    sent = send_otp_email(email, otp)
    if sent:
        return jsonify({"status": "success", "message": "OTP sent to your email address."})
    else:
        return jsonify({"status": "success", "message": "OTP sent (Console Fallback)." })

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

@app.route('/api/user/change_password', methods=['POST'])
def change_password():
    db = load_db()
    user, uid = get_current_user(db)
    if not user:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
        
    data = request.json or {}
    current_password = data.get('current_password')
    new_password = data.get('new_password')
    
    if not current_password or not new_password:
        return jsonify({"status": "error", "message": "Current and new passwords required"}), 400
        
    if user.get('password_hash') != hash_password(current_password):
        return jsonify({"status": "error", "message": "Incorrect current password"}), 400
        
    user['password_hash'] = hash_password(new_password)
    user['active_tokens'] = [request.headers.get('Authorization').split(' ')[1]] # Log out other sessions
    save_db(db)
    return jsonify({"status": "success", "message": "Password updated successfully"})


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
    created = datetime.fromisoformat(user.get('creation_date', get_ist_iso()))
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone(timedelta(hours=5, minutes=30)))
    else:
        created = created.astimezone(timezone(timedelta(hours=5, minutes=30)))
    age_days = (get_ist_now() - created).days
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
        goal = goals[goal_index]
        deadline_str = goal.get('deadline')
        is_early = True
        if deadline_str:
            try:
                deadline_utc = datetime.fromisoformat(deadline_str.replace('Z', '+00:00'))
                now_utc = datetime.now(timezone.utc)
                if now_utc >= deadline_utc:
                    is_early = False
            except Exception as e:
                print(f"[ERROR] Failed to parse destiny deadline: {e}")
                
        goals.pop(goal_index)
        user['massive_goals'] = goals
        
        if is_early:
            user['balls'] = max(0, user.get('balls', 0) - 5)
            
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


def enforce_journal_limit(db, uid):
    user_journals = [j for j in db.get('journal', []) if j.get('user_id') == uid]
    if len(user_journals) > 7:
        def get_timestamp(x):
            try:
                t = datetime.fromisoformat(x.get('timestamp', ''))
                if t.tzinfo is None:
                    t = t.replace(tzinfo=timezone(timedelta(hours=5, minutes=30)))
                return t.timestamp()
            except Exception:
                return 0
        user_journals.sort(key=get_timestamp)
        to_delete_count = len(user_journals) - 7
        to_delete_ids = [j.get('id') for j in user_journals[:to_delete_count]]
        db['journal'] = [j for j in db['journal'] if not (j.get('user_id') == uid and j.get('id') in to_delete_ids)]

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
    enforce_journal_limit(db, uid)
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
    title = data.get('title', f"Entry_{get_ist_now().strftime('%Y%m%d_%H%M%S')}")
    
    # Restrict to one journal entry per calendar day in IST
    ist_now = get_ist_now()
    ist_today = ist_now.date()
    
    user_journals = [j for j in db.get('journal', []) if j.get('user_id') == uid]
    for j in user_journals:
        try:
            j_time = datetime.fromisoformat(j.get('timestamp'))
            if j_time.tzinfo is None:
                j_time = j_time.replace(tzinfo=timezone(timedelta(hours=5, minutes=30)))
            else:
                j_time = j_time.astimezone(timezone(timedelta(hours=5, minutes=30)))
            if j_ist_date := j_time.date():
                if j_ist_date == ist_today:
                    return jsonify({"status": "error", "message": "You can only write one journal entry per day."}), 400
        except Exception:
            pass
            
    entry_obj = JournalEntry(
        user_id=uid,
        content=content,
        timestamp=get_ist_now(),
        mood_score=7
    )
    
    db['journal'].append({
        "user_id": uid,
        "id": int(get_ist_now().timestamp()),
        "title": title,
        "content": content,
        "timestamp": get_ist_iso()
    })
    
    enforce_journal_limit(db, uid)
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
        "id": f"sess_{int(get_ist_now().timestamp())}",
        "user_id": uid,
        "subject": request.json.get("subject", "General") if request.json else "General",
        "mode": request.json.get("mode", "Custom duration") if request.json else "Custom duration",
        "start_time": get_ist_iso(),
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
            s['end_time'] = get_ist_iso()
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
            "name": profile.get("leaderboard_name") or profile.get("name") or "Unknown",
            "creation_date": profile.get("creation_date", ""),
            "last_login": profile.get("last_login", "")
        })
    
    users_data.sort(key=lambda x: x.get('creation_date', ''), reverse=True)
    return jsonify({"status": "success", "users": users_data})

@app.route('/api/admin/reset_fake_warriors', methods=['POST'])
def reset_fake_warriors():
    db = load_db()
    user, uid = get_current_user(db)
    if not user or uid.lower() != 'buvanavel.m01@gmail.com':
        return jsonify({"status": "error", "message": "Unauthorized. Admin access required."}), 403
    
    admin_email = 'buvanavel.m01@gmail.com'
    admin_profile = db.get('user_profiles', {}).get(admin_email)
    
    if not admin_profile:
        return jsonify({"status": "error", "message": "Admin profile not found."}), 500
    
    # Reset admin's clan status to clear them from any active duels/clans
    admin_profile['clan_id'] = None
    admin_profile['is_clan_leader'] = False
    admin_profile['banned_clans'] = []
    
    # Rebuild user_profiles with only the admin
    db['user_profiles'] = {
        admin_email: admin_profile
    }
    
    # Wipe all clans
    db['clans'] = {}
    
    # Filter study sessions
    if 'sessions' in db:
        db['sessions'] = [s for s in db['sessions'] if str(s.get('user_id', '')).lower() == admin_email]
        
    # Filter journals
    if 'journal' in db:
        db['journal'] = [j for j in db['journal'] if str(j.get('user_id', '')).lower() == admin_email]
        
    # Filter tasks
    if 'tasks' in db:
        db['tasks'] = [t for t in db['tasks'] if str(t.get('user_id', '')).lower() == admin_email]
        
    save_db(db)
    return jsonify({"status": "success", "message": "Fake warriors and associated data wiped successfully."})

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
        "leader_email": uid.strip().lower(),
        "invite_code": invite_code,
        "members": [uid.strip().lower()],
        "max_members": 20,
        "terms": "",
        "created_at": get_ist_iso(),
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
        
    members_lower = [m.strip().lower() for m in clan.get('members', [])]
    if uid.strip().lower() not in members_lower:
        clan['members'].append(uid.strip().lower())
        
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
        
    is_leader = (clan.get('leader_email', '').strip().lower() == uid.strip().lower())
    
    member_details = []
    for member_email in clan.get('members', []):
        m_profile = db.get('user_profiles', {}).get(member_email.strip().lower(), {})
        member_details.append({
            "name": m_profile.get("leaderboard_name") or m_profile.get("name") or "Warrior",
            "email": member_email.strip().lower(),
            "balls": m_profile.get("balls", 0),
            "streak": m_profile.get("streak", 0),
            "avatar": m_profile.get("avatar", "itachi")
        })
        
    # Resolve leader name
    leader_email = clan.get("leader_email", "").strip().lower()
    leader_profile = db.get('user_profiles', {}).get(leader_email, {})
    leader_name = leader_profile.get("leaderboard_name") or leader_profile.get("name") or "Commander"

    # Filter out expired open challenges & handle active challenges
    now_ist = get_ist_now()
    active_challenges = []
    db_updated = False
    
    for ch in clan.get('challenges', []):
        status = ch.get('status', 'open')
        
        # Backward compatibility / initialization check
        if 'accepted_members' not in ch:
            ch['accepted_members'] = []
            if ch.get('accepted_by'):
                ch['accepted_members'].append({
                    "email": ch['accepted_by'].strip().lower(),
                    "name": ch.get('accepted_by_name', 'Warrior'),
                    "accepted_at": ch.get('accepted_at') or get_ist_iso(),
                    "rewarded": False
                })
                ch['creator_accepted_at'] = ch.get('accepted_at') or get_ist_iso()
                ch['creator_rewarded'] = False
        
        # 1. Handle open challenges expiring (no acceptors and join window passes)
        if status == 'open':
            try:
                exp = datetime.fromisoformat(ch.get('expires_at', ''))
                if exp.tzinfo is None:
                    exp = exp.replace(tzinfo=timezone(timedelta(hours=5, minutes=30)))
                else:
                    exp = exp.astimezone(timezone(timedelta(hours=5, minutes=30)))
                if now_ist > exp:
                    ch['status'] = 'expired'
                    db_updated = True
                    continue  # skip expired open challenges
            except Exception:
                pass
                
        # 2. Handle active challenges
        elif status == 'active':
            try:
                duration = timedelta(minutes=int(ch.get('duration_minutes', 0)))
                
                # Check creator countdown completion
                creator_email = ch.get('creator_email', '').strip().lower()
                creator_start_str = ch.get('creator_accepted_at')
                if creator_start_str and not ch.get('creator_rewarded', False):
                    creator_start = datetime.fromisoformat(creator_start_str)
                    if creator_start.tzinfo is None:
                        creator_start = creator_start.replace(tzinfo=timezone(timedelta(hours=5, minutes=30)))
                    else:
                        creator_start = creator_start.astimezone(timezone(timedelta(hours=5, minutes=30)))
                    
                    if now_ist >= (creator_start + duration):
                        ch['creator_rewarded'] = True
                        db_updated = True
                        
                        # Create study session object for creator
                        creator_session = {
                            "id": f"sess_ch_{ch.get('id')}_{creator_email}",
                            "user_id": creator_email,
                            "subject": "Clan Duel",
                            "mode": f"Duel: {ch.get('title')}",
                            "start_time": creator_start.isoformat(),
                            "end_time": (creator_start + duration).isoformat(),
                            "status": "completed"
                        }
                        if 'sessions' not in db:
                            db['sessions'] = []
                        db['sessions'].append(creator_session)
                        
                        if creator_email in db.get('user_profiles', {}):
                            db['user_profiles'][creator_email]['balls'] = db['user_profiles'][creator_email].get('balls', 0) + 50
                            
                # Check each accepted member's countdown completion
                for m in ch.get('accepted_members', []):
                    m_email = m.get('email').strip().lower()
                    m_start_str = m.get('accepted_at')
                    if m_start_str and not m.get('rewarded', False):
                        m_start = datetime.fromisoformat(m_start_str)
                        if m_start.tzinfo is None:
                            m_start = m_start.replace(tzinfo=timezone(timedelta(hours=5, minutes=30)))
                        else:
                            m_start = m_start.astimezone(timezone(timedelta(hours=5, minutes=30)))
                            
                        if now_ist >= (m_start + duration):
                            m['rewarded'] = True
                            db_updated = True
                            
                            # Create study session object for competitor
                            m_session = {
                                "id": f"sess_ch_{ch.get('id')}_{m_email}",
                                "user_id": m_email,
                                "subject": "Clan Duel",
                                "mode": f"Duel: {ch.get('title')}",
                                "start_time": m_start.isoformat(),
                                "end_time": (m_start + duration).isoformat(),
                                "status": "completed"
                            }
                            if 'sessions' not in db:
                                db['sessions'] = []
                            db['sessions'].append(m_session)
                            
                            if m_email in db.get('user_profiles', {}):
                                db['user_profiles'][m_email]['balls'] = db['user_profiles'][m_email].get('balls', 0) + 50
                
                # Check if all participants have been rewarded AND the 5-minute joining window is over
                expires_str = ch.get('expires_at')
                expires = datetime.fromisoformat(expires_str)
                if expires.tzinfo is None:
                    expires = expires.replace(tzinfo=timezone(timedelta(hours=5, minutes=30)))
                else:
                    expires = expires.astimezone(timezone(timedelta(hours=5, minutes=30)))
                
                joining_window_closed = now_ist > expires
                all_rewarded = ch.get('creator_rewarded', False) and all(m.get('rewarded', False) for m in ch.get('accepted_members', []))
                
                if all_rewarded and joining_window_closed:
                    ch['status'] = 'completed'
                    ch['completed_at'] = now_ist.isoformat()
                    db_updated = True
            except Exception as e:
                print(f"Error completing challenge: {e}")
                
        # 3. Filter out completed challenges that completed more than 10 minutes ago
        elif status == 'completed':
            try:
                comp_at = datetime.fromisoformat(ch.get('completed_at', ''))
                if comp_at.tzinfo is None:
                    comp_at = comp_at.replace(tzinfo=timezone(timedelta(hours=5, minutes=30)))
                else:
                    comp_at = comp_at.astimezone(timezone(timedelta(hours=5, minutes=30)))
                if now_ist > comp_at + timedelta(minutes=10):
                    db_updated = True
                    continue  # skip completed challenges older than 10m
            except Exception:
                pass
                
        if ch.get('status') != 'expired':
            active_challenges.append(ch)
            
    clan['challenges'] = active_challenges
    if db_updated:
        save_db(db)

    response_data = {
        "status": "success",
        "id": clan_id,
        "name": clan.get("name"),
        "leader_email": leader_email,
        "leader_name": leader_name,
        "members": member_details,
        "max_members": clan.get("max_members", 20),
        "terms": clan.get("terms", ""),
        "created_at": clan.get("created_at"),
        "challenges": active_challenges,
        "is_leader": is_leader,
        "server_time": now_ist.isoformat()
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
        
    if clan.get('leader_email', '').strip().lower() == uid.strip().lower():
        # Disband clan
        for m_email in clan.get('members', []):
            m_profile = db.get('user_profiles', {}).get(m_email.strip().lower())
            if m_profile:
                m_profile['clan_id'] = None
                m_profile['is_clan_leader'] = False
        db.get('clans', {}).pop(clan_id, None)
    else:
        # Just leave
        members_lower = [m.strip().lower() for m in clan.get('members', [])]
        if uid.strip().lower() in members_lower:
            for m in clan.get('members', []):
                if m.strip().lower() == uid.strip().lower():
                    clan['members'].remove(m)
                    break
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
    if not clan or clan.get('leader_email', '').strip().lower() != uid.strip().lower():
        return jsonify({"status": "error", "message": "Unauthorized. Clan leader only."}), 403
        
    member_email = (request.json.get('member_email', '') if request.json else '').strip().lower()
    if not member_email:
        return jsonify({"status": "error", "message": "Member email required"}), 400
        
    if member_email == uid.strip().lower():
        return jsonify({"status": "error", "message": "Cannot dismiss yourself"}), 400
        
    members_lower = [m.strip().lower() for m in clan.get('members', [])]
    if member_email in members_lower:
        for m in clan.get('members', []):
            if m.strip().lower() == member_email:
                clan['members'].remove(m)
                break
        
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
    if not clan or clan.get('leader_email', '').strip().lower() != uid.strip().lower():
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
    if not clan or clan.get('leader_email', '').strip().lower() != uid.strip().lower():
        return jsonify({"status": "error", "message": "Unauthorized. Clan leader only."}), 403
        
    for m_email in clan.get('members', []):
        m_profile = db.get('user_profiles', {}).get(m_email.strip().lower())
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
        
    challenge_id = "ch_" + str(int(get_ist_now().timestamp()))
    
    challenge = {
        "id": challenge_id,
        "title": title,
        "duration_minutes": duration,
        "creator_email": uid.strip().lower(),
        "creator_name": user.get('leaderboard_name') or user.get('name', 'Warrior'),
        "created_at": get_ist_iso(),
        "expires_at": (get_ist_now() + timedelta(minutes=5)).isoformat(),
        "accepted_members": [],
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
        
    if challenge.get('status') not in ['open', 'active']:
        return jsonify({"status": "error", "message": "Challenge is closed or completed"}), 400
        
    try:
        expires = datetime.fromisoformat(challenge.get('expires_at'))
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone(timedelta(hours=5, minutes=30)))
        else:
            expires = expires.astimezone(timezone(timedelta(hours=5, minutes=30)))
            
        if get_ist_now() > expires:
            return jsonify({"status": "error", "message": "Challenge joining window has expired"}), 400
    except Exception:
        pass
        
    if challenge.get('creator_email', '').strip().lower() == uid.strip().lower():
        return jsonify({"status": "error", "message": "Cannot accept your own challenge"}), 400
        
    accepted_members = challenge.get('accepted_members', [])
    if any(m.get('email') == uid.strip().lower() for m in accepted_members):
        return jsonify({"status": "error", "message": "You have already joined this duel"}), 400
        
    if len(accepted_members) >= 3:
        return jsonify({"status": "error", "message": "Duel is full (max 3 competitors joined)"}), 400
        
    now_ist = get_ist_iso()
    if len(accepted_members) == 0:
        challenge['status'] = 'active'
        challenge['creator_accepted_at'] = now_ist
        challenge['creator_rewarded'] = False
        
    accepted_members.append({
        "email": uid.strip().lower(),
        "name": user.get('leaderboard_name') or user.get('name', 'Warrior'),
        "accepted_at": now_ist,
        "rewarded": False
    })
    challenge['accepted_members'] = accepted_members
    
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
