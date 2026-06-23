from flask import Flask, render_template, request, jsonify, send_from_directory, send_file, g, has_app_context
from flask_cors import CORS
import os
import json
import psycopg2
import sqlite3
import copy
from datetime import datetime, timedelta, timezone
import asyncio
import secrets
import hashlib
import random
import threading
from PIL import Image, ImageDraw, ImageFont
import io
from apscheduler.schedulers.background import BackgroundScheduler
from backend.agents.core import FocusForgeAgent, DisciplineAgent, JournalEntry, VisualizerAgent

app = Flask(__name__, static_folder='.', template_folder='.')
CORS(app)

DB_PATH = 'data/db.json'
_DB_CACHE = None
db_lock = threading.RLock()

def get_ist_now():
    return datetime.now(timezone(timedelta(hours=5, minutes=30)))

def get_ist_iso():
    return get_ist_now().isoformat()

def parse_ist_datetime(dt_str):
    if not dt_str:
        return None
    try:
        if isinstance(dt_str, str) and dt_str.endswith('Z'):
            dt_str = dt_str[:-1] + '+00:00'
        dt = datetime.fromisoformat(str(dt_str))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone(timedelta(hours=5, minutes=30)))
        else:
            dt = dt.astimezone(timezone(timedelta(hours=5, minutes=30)))
        return dt
    except Exception:
        return None

def is_in_period(completed_at_str, start, end):
    if not completed_at_str:
        return start <= get_ist_now() <= end
    t = parse_ist_datetime(completed_at_str)
    return start <= t <= end if t else False

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def prune_old_data(db):
    now_ist = get_ist_now()
    
    # 1. Prune sessions older than 365 days
    if 'sessions' in db:
        new_sessions = []
        for s in db['sessions']:
            try:
                t_str = s.get('end_time') or s.get('start_time')
                if t_str:
                    t = parse_ist_datetime(t_str)
                    if t and now_ist - t <= timedelta(days=365):
                        new_sessions.append(s)
                else:
                    new_sessions.append(s)
            except Exception:
                new_sessions.append(s)
        db['sessions'] = new_sessions

    # 2. Prune journals older than 365 days
    if 'journal' in db:
        new_journals = []
        for j in db['journal']:
            try:
                t_str = j.get('timestamp')
                if t_str:
                    t = parse_ist_datetime(t_str)
                    if t and now_ist - t <= timedelta(days=365):
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

TABLES_SCHEMA = {
    "user_profiles": "email",
    "sessions": "id",
    "tasks": "id",
    "syllabus_progress": "email",
    "topic_notes": "email",
    "journal": "id",
    "custom_syllabus": "subject",
    "clans": "clan_id",
    "echoes": "id",
    "synergy_pairs": "duo_id"
}

def init_normalized_tables(conn):
    cur = conn.cursor()
    data_type = "JSONB" if DATABASE_URL else "TEXT"
    for table_name, pk_col in TABLES_SCHEMA.items():
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                {pk_col} TEXT PRIMARY KEY,
                data {data_type}
            );
        """)
    conn.commit()
    cur.close()

def execute_upsert_internal(cur, table, key_col, key_val, data_val):
    if DATABASE_URL:
        sql = f"""
            INSERT INTO {table} ({key_col}, data)
            VALUES (%s, %s)
            ON CONFLICT ({key_col}) DO UPDATE SET data = EXCLUDED.data;
        """
        cur.execute(sql, (key_val, json.dumps(data_val)))
    else:
        sql = f"""
            INSERT OR REPLACE INTO {table} ({key_col}, data)
            VALUES (?, ?);
        """
        cur.execute(sql, (key_val, json.dumps(data_val)))

def migrate_legacy_data(conn):
    legacy_data = None
    
    # Check Postgres legacy data
    if DATABASE_URL:
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'primeedu_db'
                );
            """)
            if cur.fetchone()[0]:
                cur.execute("SELECT data FROM primeedu_db WHERE id = 1;")
                row = cur.fetchone()
                if row:
                    legacy_data = row[0]
                    if isinstance(legacy_data, str):
                        legacy_data = json.loads(legacy_data)
            cur.close()
        except Exception as e:
            print(f"[ERROR] Checking legacy Postgres DB: {e}")
            
    # Check SQLite/local file legacy data
    if not legacy_data and os.path.exists(DB_PATH):
        try:
            with open(DB_PATH, 'r') as f:
                legacy_data = json.load(f)
        except Exception as e:
            print(f"[ERROR] Reading legacy local DB file: {e}")
            
    if not legacy_data:
        return
        
    print("[INFO] Migrating legacy database to normalized tables...")
    try:
        cur = conn.cursor()
        for table_name, pk_col in TABLES_SCHEMA.items():
            legacy_val = legacy_data.get(table_name)
            if not legacy_val:
                continue
                
            if isinstance(legacy_val, dict):
                for pk_val, item_data in legacy_val.items():
                    execute_upsert_internal(cur, table_name, pk_col, str(pk_val), item_data)
            elif isinstance(legacy_val, list):
                for item in legacy_val:
                    pk_val = item.get(pk_col)
                    if pk_val is not None:
                        execute_upsert_internal(cur, table_name, pk_col, str(pk_val), item)
                        
        conn.commit()
        cur.close()
        print("[INFO] Migration completed successfully!")
        
        # Clean up legacy database
        if DATABASE_URL:
            try:
                cur = conn.cursor()
                cur.execute("DROP TABLE IF EXISTS primeedu_db;")
                conn.commit()
                cur.close()
                print("[INFO] Dropped legacy primeedu_db table.")
            except Exception as e:
                print(f"[ERROR] Failed to drop legacy table: {e}")
        else:
            try:
                backup_path = DB_PATH + ".bak"
                if os.path.exists(DB_PATH):
                    os.rename(DB_PATH, backup_path)
                    print(f"[INFO] Renamed legacy DB file to {backup_path}")
            except Exception as e:
                print(f"[ERROR] Failed to rename legacy DB file: {e}")
                
    except Exception as e:
        print(f"[ERROR] Migration failed: {e}")
        conn.rollback()

def get_conn():
    if has_app_context():
        if not hasattr(g, 'db_conn'):
            if DATABASE_URL:
                g.db_conn = psycopg2.connect(DATABASE_URL)
            else:
                g.db_conn = sqlite3.connect('data/primeedu.db')
        return g.db_conn
    else:
        if DATABASE_URL:
            return psycopg2.connect(DATABASE_URL)
        else:
            if not os.path.exists('data'):
                os.makedirs('data')
            return sqlite3.connect('data/primeedu.db')

@app.teardown_appcontext
def close_db_connection(exception):
    conn = getattr(g, 'db_conn', None)
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass

def load_db_normalized(conn):
    db_dict = {
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
    cur = conn.cursor()
    for table_name, pk_col in TABLES_SCHEMA.items():
        try:
            cur.execute(f"SELECT {pk_col}, data FROM {table_name};")
            rows = cur.fetchall()
            for pk_val, data_val in rows:
                if isinstance(data_val, str):
                    data_val = json.loads(data_val)
                
                if table_name in ["user_profiles", "syllabus_progress", "topic_notes", "clans"]:
                    db_dict[table_name][pk_val] = data_val
                elif table_name == "custom_syllabus":
                    db_dict[table_name][pk_val] = data_val
                else:  # sessions, tasks, journal
                    db_dict[table_name].append(data_val)
        except Exception as e:
            print(f"[ERROR] Failed to load table {table_name}: {e}")
    cur.close()
    return db_dict

def save_db_normalized(conn, new_db, old_db):
    cur = conn.cursor()
    for table_name, pk_col in TABLES_SCHEMA.items():
        new_val = new_db.get(table_name)
        old_val = old_db.get(table_name) if old_db else None
        
        if table_name in ["user_profiles", "syllabus_progress", "topic_notes", "custom_syllabus", "clans"]:
            new_dict = new_val or {}
            old_dict = old_val or {}
            
            for key, val in new_dict.items():
                if key not in old_dict or old_dict[key] != val:
                    execute_upsert_internal(cur, table_name, pk_col, str(key), val)
                    
            for key in old_dict.keys():
                if key not in new_dict:
                    cur.execute(f"DELETE FROM {table_name} WHERE {pk_col} = %s" if DATABASE_URL else f"DELETE FROM {table_name} WHERE {pk_col} = ?", (str(key),))
        else:
            new_list = new_val or []
            old_list = old_val or []
            
            new_map = {str(item.get(pk_col)): item for item in new_list if item.get(pk_col) is not None}
            old_map = {str(item.get(pk_col)): item for item in old_list if item.get(pk_col) is not None}
            
            for key, item in new_map.items():
                if key not in old_map or old_map[key] != item:
                    execute_upsert_internal(cur, table_name, pk_col, key, item)
                    
            for key in old_map.keys():
                if key not in new_map:
                    cur.execute(f"DELETE FROM {table_name} WHERE {pk_col} = %s" if DATABASE_URL else f"DELETE FROM {table_name} WHERE {pk_col} = ?", (key,))
    conn.commit()
    cur.close()

def load_db():
    global _DB_CACHE
    with db_lock:
        if has_app_context() and hasattr(g, 'db_cache'):
            return g.db_cache
            
        conn = get_conn()
        try:
            db_data = load_db_normalized(conn)
            if has_app_context():
                g.original_db_cache = copy.deepcopy(db_data)
                g.db_cache = db_data
            _DB_CACHE = db_data
            
            # Prune and sanitize
            old_len_s = len(_DB_CACHE.get('sessions', []))
            old_len_j = len(_DB_CACHE.get('journal', []))
            prune_old_data(_DB_CACHE)
            sanitized = sanitize_timestamps(_DB_CACHE)
            if len(_DB_CACHE.get('sessions', [])) != old_len_s or len(_DB_CACHE.get('journal', [])) != old_len_j or sanitized:
                save_db(_DB_CACHE)
                
            return _DB_CACHE
        except Exception as e:
            print(f"[ERROR] Failed to load database: {e}")
            if _DB_CACHE is None:
                _DB_CACHE = {
                    "user_profiles": {}, "sessions": [], "tasks": [],
                    "syllabus_progress": {}, "topic_notes": {}, "journal": [],
                    "custom_syllabus": {"physics": [], "chemistry": [], "biology": [], "mathematics": []},
                    "clans": {}
                }
            return _DB_CACHE
        finally:
            if not has_app_context():
                conn.close()

def save_db(data):
    global _DB_CACHE
    with db_lock:
        conn = get_conn()
        try:
            old_db = None
            if has_app_context():
                old_db = getattr(g, 'original_db_cache', None)
            
            save_db_normalized(conn, data, old_db)
            
            if has_app_context():
                g.original_db_cache = copy.deepcopy(data)
                g.db_cache = data
            _DB_CACHE = data
        except Exception as e:
            print(f"[ERROR] Failed to save database: {e}")
        finally:
            if not has_app_context():
                conn.close()

# Initialize tables and migrate legacy data on startup
with app.app_context():
    startup_conn = get_conn()
    try:
        init_normalized_tables(startup_conn)
        migrate_legacy_data(startup_conn)
    except Exception as startup_err:
        print(f"[ERROR] Startup DB init/migration failed: {startup_err}")
    finally:
        startup_conn.close()

def get_current_user(db):
    auth_header = request.headers.get('Authorization')
    token = None
    if auth_header and auth_header.startswith('Bearer '):
        token = auth_header.split(' ')[1]
    else:
        token = request.args.get('token')
        
    if not token:
        return None, None
    
    for uid, profile in db.get('user_profiles', {}).items():
        if token in profile.get('active_tokens', []):
            if 'clan_id' not in profile: profile['clan_id'] = None
            if 'is_clan_leader' not in profile: profile['is_clan_leader'] = False
            if 'banned_clans' not in profile: profile['banned_clans'] = []
            if 'balls' not in profile: profile['balls'] = 0
            if 'streak' not in profile: profile['streak'] = 0
            if 'partner_id' not in profile: profile['partner_id'] = None
            if 'aura_balance' not in profile: profile['aura_balance'] = 0
            if 'synergy_symbol' not in profile: profile['synergy_symbol'] = None
            return profile, uid
    return None, None

def mark_user_active_today(user):
    if 'active_days' not in user:
        user['active_days'] = []
    today_str = get_ist_now().date().isoformat()
    if today_str not in user['active_days']:
        user['active_days'].append(today_str)
        if len(user['active_days']) > 365:
            user['active_days'] = user['active_days'][-365:]

def recalculate_user_streak(user, db):
    from datetime import date
    uid = user.get('email')
    if not uid:
        return 1
    active_dates = set()
    
    # 1. Load creation date (registration day counts as active)
    creation_str = user.get('creation_date')
    if creation_str:
        ct = parse_ist_datetime(creation_str)
        if ct:
            active_dates.add(ct.date())
            
    # 2. Load persistent active_days list
    for d_str in user.get('active_days', []):
        try:
            d = date.fromisoformat(d_str)
            active_dates.add(d)
        except Exception:
            pass
            
    # 3. Check completed or early exit sessions (backup)
    for s in db.get('sessions', []):
        if s.get('user_id') == uid and s.get('status') in ('completed', 'early_exit'):
            t = parse_ist_datetime(s.get('start_time'))
            if t:
                active_dates.add(t.date())
                
    # 4. Check journal entries (backup)
    for j in db.get('journal', []):
        if j.get('user_id') == uid:
            t = parse_ist_datetime(j.get('timestamp'))
            if t:
                active_dates.add(t.date())
                
    # 5. Add current date (IST) as active if online now
    now_ist = get_ist_now()
    active_dates.add(now_ist.date())
    
    # Count back consecutive days starting from today
    streak = 0
    curr_date = now_ist.date()
    while curr_date in active_dates:
        streak += 1
        curr_date -= timedelta(days=1)
        
    return max(1, streak)

# --- Gamification Engine ---
def check_streak_and_login(user, db=None):
    if db is None:
        db = load_db()
        
    mark_user_active_today(user)
    
    last_login = user.get('last_login')
    now = get_ist_now()
    
    # Auto-recalculate/heal user streak based on activity logs
    healed_streak = recalculate_user_streak(user, db)
    
    if last_login:
        last_date = parse_ist_datetime(last_login)
        if last_date is None:
            last_date = now - timedelta(days=2)
        # Use calendar date comparison in IST
        days_diff = (now.date() - last_date.date()).days
        
        # Streak logic based on calendar days
        if days_diff == 1:
            # Exactly the next calendar day — increment streak
            user['streak'] = max(healed_streak, user.get('streak', 0) + 1)
            if user['streak'] == 7: user['balls'] = user.get('balls', 0) + 20
            elif user['streak'] == 30: user['balls'] = user.get('balls', 0) + 100
            elif user['streak'] == 365: user['balls'] = user.get('balls', 0) + 1000
            user['last_login'] = get_ist_iso()
        elif days_diff > 1:
            # Missed a day — reset streak to healed_streak instead of 1 if activity was logged
            user['streak'] = healed_streak
            user['last_login'] = get_ist_iso()
        elif days_diff == 0:
            # If days_diff == 0, streak stays unchanged, but heal it if it's lagging
            if user.get('streak', 0) < healed_streak:
                user['streak'] = healed_streak
    else:
        user['streak'] = healed_streak
        user['last_login'] = get_ist_iso()
            
    return user

# --- Cron Job / Scheduler ---
def midnight_wipe():
    print("Running 24-Hour Automated Refresh...")
    db = load_db()
    db['tasks'] = [] # wipe daily routines
    save_db(db)

def synergy_penalty_check():
    """Runs every 6 hours — deducts 20 Aura from both partners if no Synergy activity in 48h."""
    print("[SYNERGY] Running penalty check...")
    try:
        conn = get_conn()
        try:
            db = load_db_normalized(conn)
        finally:
            if not has_app_context():
                conn.close()
        db = load_db()
        now_ist = get_ist_now()
        cutoff = now_ist - timedelta(hours=48)
        changed = False
        for duo_id, pair_data in db.get('synergy_pairs', {}).items():
            if not pair_data.get('is_active'):
                continue
            last_act_str = pair_data.get('last_activity')
            if not last_act_str:
                continue
            last_act = parse_ist_datetime(last_act_str)
            if last_act and last_act < cutoff:
                a_id = pair_data.get('partner_a_id')
                b_id = pair_data.get('partner_b_id')
                pair_data['aura_a'] = pair_data.get('aura_a', 0) - 20
                pair_data['aura_b'] = pair_data.get('aura_b', 0) - 20
                if a_id and a_id in db.get('user_profiles', {}):
                    db['user_profiles'][a_id]['aura_balance'] = db['user_profiles'][a_id].get('aura_balance', 0) - 20
                if b_id and b_id in db.get('user_profiles', {}):
                    db['user_profiles'][b_id]['aura_balance'] = db['user_profiles'][b_id].get('aura_balance', 0) - 20
                pair_data['last_penalty_at'] = get_ist_iso()
                db['synergy_pairs'][duo_id] = pair_data
                changed = True
                print(f"[SYNERGY] Penalty applied to {a_id} & {b_id}: -20 Aura each")
        if changed:
            save_db(db)
    except Exception as e:
        print(f"[SYNERGY PENALTY ERROR] {e}")


scheduler = BackgroundScheduler(timezone=timezone(timedelta(hours=5, minutes=30)))
scheduler.add_job(func=midnight_wipe, trigger="cron", hour=0, minute=0)
scheduler.add_job(func=synergy_penalty_check, trigger="cron", hour="*/6", minute=0)
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
        "timestamp": get_ist_iso(),
        "attempts": 0
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
        
    if not isinstance(password, str) or len(password.strip()) < 6:
        return jsonify({"status": "error", "message": "Password must be at least 6 characters long"}), 400
        
    if email in db.get('user_profiles', {}):
        return jsonify({"status": "error", "message": "Email already registered"}), 400
        
    # Check pending registration OTP
    pending = db.get('pending_register_otps', {}).get(email)
    if not pending:
        return jsonify({"status": "error", "message": "No active registration request found"}), 400
        
    # Check attempts
    attempts = pending.get('attempts', 0)
    if attempts >= 3:
        db['pending_register_otps'].pop(email, None)
        save_db(db)
        return jsonify({"status": "error", "message": "Too many failed attempts. Please request a new OTP."}), 400
        
    # Check expiry (10 minutes)
    timestamp_str = pending.get('timestamp')
    if timestamp_str:
        ts = parse_ist_datetime(timestamp_str)
        if ts and (get_ist_now() - ts).total_seconds() > 600:
            db['pending_register_otps'].pop(email, None)
            save_db(db)
            return jsonify({"status": "error", "message": "OTP has expired. Please request a new one."}), 400

    if str(pending.get('otp')).strip() != str(otp).strip():
        pending['attempts'] = attempts + 1
        save_db(db)
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
    data = request.json or {}
    email = (data.get('email') or '').strip().lower()
    password = data.get('password')
    
    if not email or not password or not isinstance(password, str):
        return jsonify({"status": "error", "message": "Email and password are required"}), 400
        
    user = db['user_profiles'].get(email)
    if user and user.get('password_hash') == hash_password(password):
        token = secrets.token_hex(32)
        if 'active_tokens' not in user:
            user['active_tokens'] = []
        user['active_tokens'].append(token)
        user = check_streak_and_login(user, db)
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
            msg['Subject'] = "MavX Mndset - Warrior Registration Verification OTP"
            body = f"""Greetings Warrior!

Welcome to MavX Mndset. To complete your identity forging and verify your Google email address, please use the following OTP:

Verification OTP: {otp}

Enter this code in the registration form to finalize your registration.

Stay focused on your journey!
- MavX Mndset System
"""
        else:
            msg['Subject'] = "MavX Mndset - Warrior Password Reset OTP"
            body = f"""Greetings Warrior!

You have requested a password reset for your MavX Mndset account.

Your Verification OTP is: {otp}

Enter this code in the app to forge a new password. If you did not request this, please ignore this email.

Stay focused on your journey!
- MavX Mndset System
"""
        msg.attach(MIMEText(body, 'plain'))
        
        # Support custom SMTP server (e.g. Brevo on port 2525 to bypass Render blocks)
        smtp_host = os.environ.get('SMTP_HOST', 'smtp.gmail.com')
        try:
            smtp_port = int(os.environ.get('SMTP_PORT', '587'))
        except ValueError:
            smtp_port = 587
            
        server = None
        try:
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=10.0)
            server.starttls()
            smtp_user = os.environ.get('SMTP_USER', smtp_email)
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_email, to_email, msg.as_string())
            print(f"[SMTP] Successfully sent OTP email to {to_email}")
            return True
        except Exception as smtp_err:
            print(f"[SMTP ERROR] SMTP connection/sending failed: {smtp_err}")
            raise smtp_err
        finally:
            if server:
                try:
                    server.quit()
                except Exception:
                    pass
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
    db['user_profiles'][email]['reset_otp_timestamp'] = get_ist_iso()
    db['user_profiles'][email]['reset_otp_attempts'] = 0
    save_db(db)
    
    sent = send_otp_email(email, otp)
    if sent:
        return jsonify({"status": "success", "message": "OTP sent to your email address."})
    else:
        return jsonify({"status": "success", "message": "OTP sent (Console Fallback)." })

@app.route('/api/auth/otp/verify', methods=['POST'])
def verify_otp():
    db = load_db()
    data = request.json or {}
    email = (data.get('email') or '').strip().lower()
    otp = data.get('otp')
    new_password = data.get('new_password')
    
    if not email or not otp or not new_password:
        return jsonify({"status": "error", "message": "Email, OTP, and new password are required"}), 400
        
    if not isinstance(new_password, str) or len(new_password.strip()) < 6:
        return jsonify({"status": "error", "message": "Password must be at least 6 characters long"}), 400

    user = db['user_profiles'].get(email)
    if not user or user.get('reset_otp') is None:
        return jsonify({"status": "error", "message": "No active password reset request found"}), 400
        
    # Check attempts
    attempts = user.get('reset_otp_attempts', 0)
    if attempts >= 3:
        user['reset_otp'] = None
        user['reset_otp_timestamp'] = None
        user['reset_otp_attempts'] = 0
        save_db(db)
        return jsonify({"status": "error", "message": "Too many failed attempts. Please request a new OTP."}), 400
        
    # Check expiry (5 minutes)
    timestamp_str = user.get('reset_otp_timestamp')
    if timestamp_str:
        ts = parse_ist_datetime(timestamp_str)
        if ts and (get_ist_now() - ts).total_seconds() > 300:
            user['reset_otp'] = None
            user['reset_otp_timestamp'] = None
            user['reset_otp_attempts'] = 0
            save_db(db)
            return jsonify({"status": "error", "message": "OTP has expired. Please request a new one."}), 400

    if user.get('reset_otp') == str(otp).strip():
        user['password_hash'] = hash_password(new_password)
        user['reset_otp'] = None
        user['reset_otp_timestamp'] = None
        user['reset_otp_attempts'] = 0
        user['active_tokens'] = [] # Log out all devices on reset
        save_db(db)
        return jsonify({"status": "success", "message": "Password reset successful"})
    else:
        user['reset_otp_attempts'] = attempts + 1
        save_db(db)
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
        
    user = check_streak_and_login(user, db)
    
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
    
    created = parse_ist_datetime(user.get('creation_date', get_ist_iso())) or get_ist_now()
    age_days = (get_ist_now().date() - created.date()).days + 1
    if uid and uid.strip().lower() == 'buvanavel.m01@gmail.com':
        age_days = 365
    user['account_age_days'] = age_days
    
    save_db(db)
    return jsonify(user)

@app.route('/api/user/destiny/cancel', methods=['POST'])
def cancel_destiny():
    db = load_db()
    user, uid = get_current_user(db)
    if not user:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
        
    data = request.json or {}
    try:
        goal_index = int(data.get('goal_index'))
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "Invalid goal_index"}), 400
        
    goals = user.get('massive_goals', [])
    
    if 0 <= goal_index < len(goals):
        goal = goals[goal_index]
        deadline_str = goal.get('deadline')
        is_early = True
        if deadline_str:
            deadline_ist = parse_ist_datetime(deadline_str)
            if deadline_ist:
                if get_ist_now() >= deadline_ist:
                    is_early = False
                
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
            t = parse_ist_datetime(x.get('timestamp', ''))
            return t.timestamp() if t else 0
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
    
    mark_user_active_today(user)
    data = request.json or {}
    entries = data.get('entries', [])
    for e in entries:
        e['user_id'] = uid
        if not e.get('timestamp'):
            e['timestamp'] = get_ist_iso()
        if not e.get('id'):
            e['id'] = f"jn_{int(get_ist_now().timestamp())}_{random.randint(1000, 9999)}"
        
    # Remove same-day duplicates in incoming synced entries (enforce daily limit during sync)
    seen_dates = set()
    unique_entries = []
    for e in entries:
        t = parse_ist_datetime(e.get('timestamp'))
        if t:
            date_str = t.date().isoformat()
            if date_str not in seen_dates:
                seen_dates.add(date_str)
                unique_entries.append(e)
        else:
            unique_entries.append(e)
        
    db['journal'] = [j for j in db['journal'] if j.get('user_id') != uid] + unique_entries
    enforce_journal_limit(db, uid)
    save_db(db)
    return jsonify({'status': 'success'})

@app.route('/api/journal', methods=['POST'])
def submit_journal():
    db = load_db()
    user, uid = get_current_user(db)
    if not user:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
        
    mark_user_active_today(user)
    data = request.json or {}
    content = data.get('content')
    if not content or not isinstance(content, str) or not content.strip():
        return jsonify({"status": "error", "message": "Journal content cannot be empty"}), 400
        
    title = data.get('title', f"Entry_{get_ist_now().strftime('%Y%m%d_%H%M%S')}")
    
    # Restrict to one journal entry per calendar day in IST
    ist_now = get_ist_now()
    ist_today = ist_now.date()
    
    user_journals = [j for j in db.get('journal', []) if j.get('user_id') == uid]
    for j in user_journals:
        j_time = parse_ist_datetime(j.get('timestamp'))
        if j_time and j_time.date() == ist_today:
            return jsonify({"status": "error", "message": "You can only write one journal entry per day."}), 400
            
    entry_id = f"jn_{int(ist_now.timestamp())}_{random.randint(1000, 9999)}"
    
    entry_obj = JournalEntry(
        user_id=uid,
        content=content,
        timestamp=ist_now,
        mood_score=7
    )
    
    db['journal'].append({
        "user_id": uid,
        "id": entry_id,
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
        
    mark_user_active_today(user)
    data = request.json or {}
    new_tasks = data.get('tasks', [])
    for t in new_tasks: t['user_id'] = uid
    
    # Track which tasks have already been rewarded to prevent double-spending/duplication rewards
    new_completed_rewards = 0
    
    # Let's check against currently stored tasks to find which tasks were already completed and rewarded
    rewarded_task_ids = {t.get('id') for t in db.get('tasks', []) if t.get('user_id') == uid and t.get('completed') and t.get('rewarded')}
    
    for t in new_tasks:
        if t.get('completed'):
            if t.get('id') not in rewarded_task_ids:
                # Newly completed task! Reward it and mark it as rewarded
                t['rewarded'] = True
                t['completed_at'] = get_ist_iso()
                new_completed_rewards += 1
            else:
                # Keep it marked as rewarded
                t['rewarded'] = True
                # Get existing completed_at if present
                existing_t = next((et for et in db.get('tasks', []) if et.get('id') == t.get('id') and et.get('user_id') == uid), None)
                if existing_t and existing_t.get('completed_at'):
                    t['completed_at'] = existing_t.get('completed_at')
                else:
                    t['completed_at'] = get_ist_iso()
        else:
            t['rewarded'] = False # If they uncheck it, reset
            t['completed_at'] = None
            
    # Remove old tasks for this user, insert new ones
    db['tasks'] = [t for t in db['tasks'] if t.get('user_id') != uid] + new_tasks
    
    # Reward 2 Dragon Balls per newly completed task
    db['user_profiles'][uid]['balls'] += (new_completed_rewards * 2)
        
    save_db(db)
    return jsonify({
        "status": "success",
        "balls": db['user_profiles'][uid]['balls']
    })

@app.route('/api/sessions/start', methods=['POST'])
def start_session():
    db = load_db()
    user, uid = get_current_user(db)
    if not user:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
        
    mark_user_active_today(user)
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
        
    mark_user_active_today(user)
    data = request.json or {}
    session_id = data.get("session_id")
    early_exit = data.get("early_exit", False)
    
    for s in db['sessions']:
        if s['id'] == session_id and s.get('user_id') == uid:
            # Prevent double-ending sessions and double-spending rewards
            if s.get('status') in ["completed", "early_exit"]:
                return jsonify({
                    "status": "success", 
                    "balls_earned": 0,
                    "balls": db['user_profiles'][uid]['balls']
                })
                
            s['end_time'] = get_ist_iso()
            s['status'] = "completed" if not early_exit else "early_exit"
            
            # Calculate actual duration focused (use client value if provided)
            duration_mins = data.get("duration_minutes")
            if duration_mins is None:
                start = parse_ist_datetime(s.get('start_time'))
                end = parse_ist_datetime(s.get('end_time'))
                duration_mins = 0.0
                if start and end:
                    duration_mins = max(0.0, (end - start).total_seconds() / 60.0)
            else:
                duration_mins = max(0.0, float(duration_mins))
            
            s['duration_minutes'] = duration_mins
            
            # Proportional rewards: 1 Dragon Ball per minute focused
            if not early_exit:
                earned = max(1, int(round(duration_mins)))
            else:
                earned = max(1, int(round(duration_mins * 0.5))) # 50% reward for early exit
                
            db['user_profiles'][uid]['balls'] += earned
            save_db(db)
            return jsonify({
                "status": "success", 
                "balls_earned": earned,
                "balls": db['user_profiles'][uid]['balls']
            })
            
    return jsonify({"status": "error", "message": "Session not found"}), 404

def auto_close_running_sessions(db, uid):
    now_ist = get_ist_now()
    updated = False
    for s in db.get('sessions', []):
        if s.get('user_id') == uid and s.get('status') == 'running':
            try:
                start_t = parse_ist_datetime(s.get('start_time'))
                if start_t:
                    diff_hours = (now_ist - start_t).total_seconds() / 3600.0
                    # If it's been running for more than 4 hours, auto-end it
                    if diff_hours > 4.0:
                        s['status'] = 'early_exit'
                        s['end_time'] = (start_t + timedelta(hours=4)).isoformat()
                        duration_mins = 240.0
                        s['duration_minutes'] = duration_mins
                        earned = max(1, int(round(duration_mins * 0.5)))
                        if uid in db.get('user_profiles', {}):
                            db['user_profiles'][uid]['balls'] += earned
                        updated = True
            except Exception:
                pass
    if updated:
        save_db(db)

@app.route('/api/sessions', methods=['GET'])
def get_user_sessions():
    db = load_db()
    user, uid = get_current_user(db)
    if not user:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
        
    auto_close_running_sessions(db, uid)
    
    user_sessions = [s for s in db.get('sessions', []) if s.get('user_id') == uid]
    user_sessions = [s for s in user_sessions if s.get('status') in ['completed', 'early_exit']]
    user_sessions.sort(key=lambda x: x.get('start_time') or '', reverse=True)
    return jsonify(user_sessions)

# --- ACTIVE FOCUSING ENDPOINT ---
@app.route('/api/sessions/active', methods=['GET'])
def get_active_focusing_warriors():
    db = load_db()
    user, uid = get_current_user(db)
    if not user:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
        
    now_ist = get_ist_now()
    active_warriors = []
    seen_users = set()
    
    for s in db.get('sessions', []):
        if s.get('status') == 'running':
            s_uid = s.get('user_id')
            if s_uid and s_uid not in seen_users:
                try:
                    start_time = parse_ist_datetime(s.get('start_time'))
                    # Consider active if started within the last 4 hours
                    if start_time and (now_ist - start_time).total_seconds() < 4 * 3600:
                        seen_users.add(s_uid)
                        profile = db.get('user_profiles', {}).get(s_uid, {})
                        active_warriors.append({
                            "name": profile.get("leaderboard_name") or profile.get("name") or "Warrior",
                            "avatar": profile.get("avatar") or "itachi",
                            "subject": s.get("subject") or "General"
                        })
                except Exception:
                    pass
                    
    return jsonify({
        "count": len(active_warriors),
        "warriors": active_warriors
    })

def get_study_hours_by_day(sessions, days_count):
    now_ist = get_ist_now()
    hours = [0.0] * days_count
    labels = []
    
    # Calculate dates
    dates = []
    for i in range(days_count - 1, -1, -1):
        d = now_ist.date() - timedelta(days=i)
        dates.append(d)
        labels.append(d.strftime('%m/%d'))
        
    for s in sessions:
        if s.get('status') == 'completed':
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
                        
                    if s.get('duration_minutes') is not None:
                        duration_hrs = float(s['duration_minutes']) / 60.0
                    else:
                        duration_hrs = max(0.0, (end - start).total_seconds() / 3600.0)
                    s_date = start.date()
                    if s_date in dates:
                        idx = dates.index(s_date)
                        hours[idx] += duration_hrs
            except Exception:
                pass
                
    return hours, labels

def get_study_hours_by_month(sessions):
    now_ist = get_ist_now()
    hours = [0.0] * 12
    labels = []
    
    months = []
    curr_y, curr_m = now_ist.year, now_ist.month
    for i in range(11, -1, -1):
        m = curr_m - i
        y = curr_y
        while m <= 0:
            m += 12
            y -= 1
        months.append((y, m))
        dt = datetime(y, m, 1)
        labels.append(dt.strftime('%b'))
        
    for s in sessions:
        if s.get('status') == 'completed':
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
                        
                    if s.get('duration_minutes') is not None:
                        duration_hrs = float(s['duration_minutes']) / 60.0
                    else:
                        duration_hrs = max(0.0, (end - start).total_seconds() / 3600.0)
                    s_ym = (start.year, start.month)
                    if s_ym in months:
                        idx = months.index(s_ym)
                        hours[idx] += duration_hrs
            except Exception:
                pass
                
    return hours, labels

def get_study_hours_by_subject(sessions, days_count=30):
    now_ist = get_ist_now()
    cutoff_date = now_ist.date() - timedelta(days=days_count)
    
    subject_hours = {}
    
    for s in sessions:
        if s.get('status') == 'completed':
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
                        
                    if start.date() >= cutoff_date:
                        if s.get('duration_minutes') is not None:
                            duration_hrs = float(s['duration_minutes']) / 60.0
                        else:
                            duration_hrs = max(0.0, (end - start).total_seconds() / 3600.0)
                        subj = s.get('subject') or 'General'
                        subj = subj.strip().capitalize()
                        subject_hours[subj] = subject_hours.get(subj, 0.0) + duration_hrs
            except Exception:
                pass
                
    if not subject_hours:
        subject_hours = {
            "Physics": 0.0,
            "Chemistry": 0.0,
            "Maths": 0.0,
            "Biology": 0.0
        }
        
    sorted_subjs = sorted(subject_hours.items(), key=lambda x: x[1], reverse=True)[:5]
    categories = [x[0] for x in sorted_subjs]
    values = [x[1] for x in sorted_subjs]
    
    return categories, values

def generate_line_graph(data_points, labels):
    width, height = 500, 320
    img = Image.new('RGBA', (width, height), color=(0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    margin_l, margin_r = 45, 20
    margin_t, margin_b = 30, 40
    plot_w = width - margin_l - margin_r
    plot_h = height - margin_t - margin_b
    
    max_val = max(data_points) if data_points else 0
    max_y = max(4.0, max_val * 1.2)
    
    num_grids = 4
    for i in range(num_grids + 1):
        y_val = max_y * i / num_grids
        y_pos = int(margin_t + plot_h - (y_val / max_y) * plot_h)
        draw.line([(margin_l, y_pos), (width - margin_r, y_pos)], fill=(255, 255, 255, 15))
        draw.text((10, y_pos - 5), f"{y_val:.1f}h", fill=(120, 120, 150, 255))
        
    n = len(data_points)
    points = []
    for i in range(n):
        x_pos = int(margin_l + (i / (n - 1) if n > 1 else 0.5) * plot_w)
        y_pos = int(margin_t + plot_h - (data_points[i] / max_y) * plot_h)
        points.append((x_pos, y_pos))
        
    if len(points) > 1:
        area_points = [(margin_l, margin_t + plot_h)] + points + [(margin_l + plot_w, margin_t + plot_h)]
        draw.polygon(area_points, fill=(0, 243, 255, 30))
        
    if len(points) > 1:
        draw.line(points, fill=(0, 243, 255, 255), width=3)
        
    for i in range(n):
        x_pos, y_pos = points[i]
        draw.ellipse([(x_pos - 4, y_pos - 4), (x_pos + 4, y_pos + 4)], fill=(255, 42, 133, 255), outline=(255, 255, 255, 255))
        
        step = 1
        if n > 14:
            step = 5
        elif n > 7:
            step = 2
            
        if i % step == 0 or i == n - 1:
            draw.text((x_pos - 10, margin_t + plot_h + 10), labels[i], fill=(120, 120, 150, 255))
            
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return buf

def generate_bar_graph(categories, values):
    width, height = 500, 320
    img = Image.new('RGBA', (width, height), color=(0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    margin_l, margin_r = 45, 20
    margin_t, margin_b = 30, 40
    plot_w = width - margin_l - margin_r
    plot_h = height - margin_t - margin_b
    
    max_val = max(values) if values else 0
    max_y = max(4.0, max_val * 1.2)
    
    num_grids = 4
    for i in range(num_grids + 1):
        y_val = max_y * i / num_grids
        y_pos = int(margin_t + plot_h - (y_val / max_y) * plot_h)
        draw.line([(margin_l, y_pos), (width - margin_r, y_pos)], fill=(255, 255, 255, 15))
        draw.text((10, y_pos - 5), f"{y_val:.1f}h", fill=(120, 120, 150, 255))
        
    n = len(categories)
    if n > 0:
        bar_gap = 12
        total_gaps_w = bar_gap * (n + 1)
        bar_w = (plot_w - total_gaps_w) // n
        
        for i in range(n):
            x_start = margin_l + bar_gap + i * (bar_w + bar_gap)
            x_end = x_start + bar_w
            y_pos = int(margin_t + plot_h - (values[i] / max_y) * plot_h)
            
            draw.rectangle([(x_start, y_pos), (x_end, margin_t + plot_h)], fill=(157, 0, 255, 200), outline=(0, 243, 255, 255))
            draw.text((x_start + (bar_w - 12) // 2, y_pos - 15), f"{values[i]:.1f}", fill=(255, 255, 255, 255))
            
            label = categories[i]
            if len(label) > 6:
                label = label[:5] + "."
            draw.text((x_start + (bar_w - len(label)*5) // 2, margin_t + plot_h + 10), label, fill=(120, 120, 150, 255))
            
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return buf

@app.route('/api/recap/dynamic', methods=['GET'])
def get_dynamic_recap():
    db = load_db()
    user, uid = get_current_user(db)
    if not user:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
        
    sessions = [s for s in db.get('sessions', []) if s.get('user_id') == uid]
    tasks = [t for t in db.get('tasks', []) if t.get('user_id') == uid]
    journal_entries = [j for j in db.get('journal', []) if j.get('user_id') == uid]
    
    weekly_offset = int(request.args.get('weekly_offset', 0))
    monthly_offset = int(request.args.get('monthly_offset', 0))
    yearly_offset = int(request.args.get('yearly_offset', 0))
    
    ist_now = get_ist_now()
    
    # 1. Weekly bounds
    current_week_start = (ist_now - timedelta(days=ist_now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    w_start = current_week_start - timedelta(weeks=weekly_offset)
    w_end = w_start + timedelta(days=7) - timedelta(microseconds=1)
    
    # 2. Monthly bounds
    w_y = ist_now.year
    w_m = ist_now.month - monthly_offset
    while w_m <= 0:
        w_m += 12
        w_y -= 1
    m_start = datetime(w_y, w_m, 1, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    ny = w_y
    nm = w_m + 1
    if nm > 12:
        nm = 1
        ny += 1
    m_end = datetime(ny, nm, 1, tzinfo=timezone(timedelta(hours=5, minutes=30))) - timedelta(microseconds=1)
    
    # 3. Yearly bounds
    y_year = ist_now.year - yearly_offset
    y_start = datetime(y_year, 1, 1, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    y_end = datetime(y_year + 1, 1, 1, tzinfo=timezone(timedelta(hours=5, minutes=30))) - timedelta(microseconds=1)
    
    def get_period_balls(p_sessions, p_tasks, p_journals):
        balls = 0
        for s in p_sessions:
            if s.get('status') in ['completed', 'early_exit']:
                duration_mins = s.get('duration_minutes', 0)
                if duration_mins is None:
                    duration_mins = 0
                early_exit = (s.get('status') == 'early_exit')
                if not early_exit:
                    earned = max(1, int(round(duration_mins)))
                else:
                    earned = max(1, int(round(duration_mins * 0.5)))
                balls += earned
        
        balls += len([t for t in p_tasks if t.get('completed')]) * 2
        balls += len(p_journals) * 50
        return balls

    # Filter for Weekly
    w_sessions = [s for s in sessions if (t := parse_ist_datetime(s.get('start_time'))) and w_start <= t <= w_end]
    w_tasks = [t for t in tasks if t.get('completed') and is_in_period(t.get('completed_at'), w_start, w_end)]
    w_journals = [j for j in journal_entries if (t := parse_ist_datetime(j.get('timestamp'))) and w_start <= t <= w_end]
    w_balls = get_period_balls(w_sessions, w_tasks, w_journals)
    
    # Filter for Monthly
    m_sessions = [s for s in sessions if (t := parse_ist_datetime(s.get('start_time'))) and m_start <= t <= m_end]
    m_tasks = [t for t in tasks if t.get('completed') and is_in_period(t.get('completed_at'), m_start, m_end)]
    m_journals = [j for j in journal_entries if (t := parse_ist_datetime(j.get('timestamp'))) and m_start <= t <= m_end]
    m_balls = get_period_balls(m_sessions, m_tasks, m_journals)
    
    # Filter for Yearly
    y_sessions = [s for s in sessions if (t := parse_ist_datetime(s.get('start_time'))) and y_start <= t <= y_end]
    y_tasks = [t for t in tasks if t.get('completed') and is_in_period(t.get('completed_at'), y_start, y_end)]
    y_journals = [j for j in journal_entries if (t := parse_ist_datetime(j.get('timestamp'))) and y_start <= t <= y_end]
    y_balls = get_period_balls(y_sessions, y_tasks, y_journals)
    
    weekly_visuals = visual_agent.get_recap_visuals(
        w_sessions, 
        w_tasks, 
        user_balls=w_balls,
        journal_count=len(w_journals),
        user_streak=user.get('streak', 0) if weekly_offset == 0 else 0
    )
    
    monthly_visuals = visual_agent.get_recap_visuals(
        m_sessions, 
        m_tasks, 
        user_balls=m_balls,
        journal_count=len(m_journals),
        user_streak=user.get('streak', 0) if monthly_offset == 0 else 0
    )
    
    yearly_visuals = visual_agent.get_recap_visuals(
        y_sessions, 
        y_tasks, 
        user_balls=y_balls,
        journal_count=len(y_journals),
        user_streak=user.get('streak', 0) if yearly_offset == 0 else 0
    )
    
    return jsonify({
        "weekly": weekly_visuals,
        "monthly": monthly_visuals,
        "yearly": yearly_visuals
    })

@app.route('/api/recap/graph/<graph_type>')
def get_recap_graph(graph_type):
    db = load_db()
    user, uid = get_current_user(db)
    if not user:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
        
    sessions = [s for s in db.get('sessions', []) if s.get('user_id') == uid]
    offset = int(request.args.get('offset', 0))
    ist_now = get_ist_now()

    if graph_type == 'weekly_grit':
        current_week_start = (ist_now - timedelta(days=ist_now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        start = current_week_start - timedelta(weeks=offset)
        end = start + timedelta(days=7) - timedelta(microseconds=1)
        
        period_sessions = [s for s in sessions if (t := parse_ist_datetime(s.get('start_time'))) and start <= t <= end]
        
        hours = [0.0] * 7
        labels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        week_dates = [start.date() + timedelta(days=i) for i in range(7)]
        
        for s in period_sessions:
            if s.get('status') == 'completed':
                try:
                    start_t = parse_ist_datetime(s.get('start_time'))
                    if start_t:
                        s_date = start_t.date()
                        if s_date in week_dates:
                            idx = week_dates.index(s_date)
                            duration_mins = s.get('duration_minutes', 0)
                            if duration_mins is None:
                                duration_mins = 0
                            hours[idx] += float(duration_mins) / 60.0
                except Exception:
                    pass
        buf = generate_line_graph(hours, labels)
        
    elif graph_type == 'consistency_monthly':
        import calendar
        w_y = ist_now.year
        w_m = ist_now.month - offset
        while w_m <= 0:
            w_m += 12
            w_y -= 1
        _, num_days = calendar.monthrange(w_y, w_m)
        start = datetime(w_y, w_m, 1, tzinfo=timezone(timedelta(hours=5, minutes=30)))
        ny = w_y
        nm = w_m + 1
        if nm > 12:
            nm = 1
            ny += 1
        end = datetime(ny, nm, 1, tzinfo=timezone(timedelta(hours=5, minutes=30))) - timedelta(microseconds=1)
        
        period_sessions = [s for s in sessions if (t := parse_ist_datetime(s.get('start_time'))) and start <= t <= end]
        
        hours = [0.0] * num_days
        labels = [str(i) for i in range(1, num_days + 1)]
        month_dates = [datetime(w_y, w_m, i).date() for i in range(1, num_days + 1)]
        
        for s in period_sessions:
            if s.get('status') == 'completed':
                try:
                    start_t = parse_ist_datetime(s.get('start_time'))
                    if start_t:
                        s_date = start_t.date()
                        if s_date in month_dates:
                            idx = month_dates.index(s_date)
                            duration_mins = s.get('duration_minutes', 0)
                            if duration_mins is None:
                                duration_mins = 0
                            hours[idx] += float(duration_mins) / 60.0
                except Exception:
                    pass
        buf = generate_line_graph(hours, labels)
        
    elif graph_type == 'knowledge_monthly':
        w_y = ist_now.year
        w_m = ist_now.month - offset
        while w_m <= 0:
            w_m += 12
            w_y -= 1
        start = datetime(w_y, w_m, 1, tzinfo=timezone(timedelta(hours=5, minutes=30)))
        ny = w_y
        nm = w_m + 1
        if nm > 12:
            nm = 1
            ny += 1
        end = datetime(ny, nm, 1, tzinfo=timezone(timedelta(hours=5, minutes=30))) - timedelta(microseconds=1)
        
        period_sessions = [s for s in sessions if (t := parse_ist_datetime(s.get('start_time'))) and start <= t <= end]
        
        subject_hours = {}
        for s in period_sessions:
            if s.get('status') == 'completed':
                try:
                    subj = s.get('subject') or 'General'
                    duration_mins = s.get('duration_minutes', 0)
                    if duration_mins is None:
                        duration_mins = 0
                    subject_hours[subj] = subject_hours.get(subj, 0.0) + (float(duration_mins) / 60.0)
                except Exception:
                    pass
        
        if not subject_hours:
            categories, values = ["No Data"], [0.0]
        else:
            categories = list(subject_hours.keys())
            values = list(subject_hours.values())
        buf = generate_bar_graph(categories, values)
        
    elif graph_type == 'legacy_yearly':
        y_year = ist_now.year - offset
        start = datetime(y_year, 1, 1, tzinfo=timezone(timedelta(hours=5, minutes=30)))
        end = datetime(y_year + 1, 1, 1, tzinfo=timezone(timedelta(hours=5, minutes=30))) - timedelta(microseconds=1)
        
        period_sessions = [s for s in sessions if (t := parse_ist_datetime(s.get('start_time'))) and start <= t <= end]
        
        hours = [0.0] * 12
        labels = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        for s in period_sessions:
            if s.get('status') == 'completed':
                try:
                    start_t = parse_ist_datetime(s.get('start_time'))
                    if start_t:
                        idx = start_t.month - 1
                        duration_mins = s.get('duration_minutes', 0)
                        if duration_mins is None:
                            duration_mins = 0
                        hours[idx] += float(duration_mins) / 60.0
                except Exception:
                    pass
        buf = generate_line_graph(hours, labels)
        
    elif graph_type == 'growth_yearly':
        y_year = ist_now.year - offset
        start = datetime(y_year, 1, 1, tzinfo=timezone(timedelta(hours=5, minutes=30)))
        end = datetime(y_year + 1, 1, 1, tzinfo=timezone(timedelta(hours=5, minutes=30))) - timedelta(microseconds=1)
        
        period_sessions = [s for s in sessions if (t := parse_ist_datetime(s.get('start_time'))) and start <= t <= end]
        
        subject_hours = {}
        for s in period_sessions:
            if s.get('status') == 'completed':
                try:
                    subj = s.get('subject') or 'General'
                    duration_mins = s.get('duration_minutes', 0)
                    if duration_mins is None:
                        duration_mins = 0
                    subject_hours[subj] = subject_hours.get(subj, 0.0) + (float(duration_mins) / 60.0)
                except Exception:
                    pass
        
        if not subject_hours:
            categories, values = ["No Data"], [0.0]
        else:
            categories = list(subject_hours.keys())
            values = list(subject_hours.values())
        buf = generate_bar_graph(categories, values)
        
    else:
        return jsonify({"status": "error", "message": "Invalid graph type"}), 400
        
    return send_file(buf, mimetype='image/png')

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

# --- PERIOD LEADERBOARD ENDPOINT ---
@app.route('/api/leaderboard/period', methods=['GET'])
def get_period_leaderboard():
    db = load_db()
    user, uid = get_current_user(db)
    if not user:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
        
    period = request.args.get('period', 'weekly') # weekly, monthly, yearly
    ist_now = get_ist_now()
    
    if period == 'weekly':
        start = (ist_now - timedelta(days=ist_now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=7) - timedelta(microseconds=1)
    elif period == 'monthly':
        start = datetime(ist_now.year, ist_now.month, 1, tzinfo=timezone(timedelta(hours=5, minutes=30)))
        ny = ist_now.year
        nm = ist_now.month + 1
        if nm > 12:
            nm = 1
            ny += 1
        end = datetime(ny, nm, 1, tzinfo=timezone(timedelta(hours=5, minutes=30))) - timedelta(microseconds=1)
    else: # yearly
        start = datetime(ist_now.year, 1, 1, tzinfo=timezone(timedelta(hours=5, minutes=30)))
        end = datetime(ist_now.year + 1, 1, 1, tzinfo=timezone(timedelta(hours=5, minutes=30))) - timedelta(microseconds=1)
        
    users_list = []
    for user_id, profile in db.get('user_profiles', {}).items():
        p_sessions = [s for s in db.get('sessions', []) if s.get('user_id') == user_id and s.get('status') in ['completed', 'early_exit']]
        p_sessions = [s for s in p_sessions if (t := parse_ist_datetime(s.get('start_time'))) and start <= t <= end]
        
        p_tasks = [t for t in db.get('tasks', []) if t.get('user_id') == user_id and t.get('completed') and is_in_period(t.get('completed_at'), start, end)]
        p_journals = [j for j in db.get('journal', []) if j.get('user_id') == user_id and (t := parse_ist_datetime(j.get('timestamp'))) and start <= t <= end]
        
        balls = 0
        focus_mins = 0.0
        for s in p_sessions:
            duration_mins = s.get('duration_minutes', 0)
            if duration_mins is None:
                duration_mins = 0
            if s.get('status') == 'completed':
                focus_mins += float(duration_mins)
                balls += max(1, int(round(duration_mins)))
            else: # early_exit
                balls += max(1, int(round(duration_mins * 0.5)))
                
        balls += len(p_tasks) * 2
        balls += len(p_journals) * 50
        
        users_list.append({
            "name": profile.get("leaderboard_name") or profile.get("name") or "Warrior",
            "email": profile.get("email") or user_id,
            "balls": balls,
            "focus_hours": round(focus_mins / 60.0, 1),
            "sessions_count": len(p_sessions),
            "avatar": profile.get("avatar", "itachi")
        })
        
    users_list.sort(key=lambda x: x['balls'], reverse=True)
    return jsonify(users_list)

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
            start = parse_ist_datetime(s.get('start_time'))
            end = parse_ist_datetime(s.get('end_time'))
            if start and end:
                diff = (end - start).total_seconds() / 60.0
                focus_duration_minutes += max(0.0, diff)
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
                exp = parse_ist_datetime(ch.get('expires_at', ''))
                if exp and now_ist > exp:
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
                    creator_start = parse_ist_datetime(creator_start_str)
                    
                    if creator_start and now_ist >= (creator_start + duration):
                        session_id = f"sess_ch_{ch.get('id')}_{creator_email}"
                        session_exists = any(s.get('id') == session_id for s in db.get('sessions', []))
                        
                        ch['creator_rewarded'] = True
                        db_updated = True
                        
                        if not session_exists:
                            # Create study session object for creator
                            creator_session = {
                                "id": session_id,
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
                        m_start = parse_ist_datetime(m_start_str)
                            
                        if m_start and now_ist >= (m_start + duration):
                            session_id = f"sess_ch_{ch.get('id')}_{m_email}"
                            session_exists = any(s.get('id') == session_id for s in db.get('sessions', []))
                            
                            m['rewarded'] = True
                            db_updated = True
                            
                            if not session_exists:
                                # Create study session object for competitor
                                m_session = {
                                    "id": session_id,
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
                expires = parse_ist_datetime(expires_str)
                
                joining_window_closed = expires and now_ist > expires
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
                comp_at = parse_ist_datetime(ch.get('completed_at', ''))
                if comp_at and now_ist > comp_at + timedelta(minutes=10):
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
    except (ValueError, TypeError):
        duration = 0
        
    if duration <= 0:
        return jsonify({"status": "error", "message": "Challenge duration must be at least 1 minute"}), 400
        
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
        
    expires = parse_ist_datetime(challenge.get('expires_at'))
    if expires and get_ist_now() > expires:
        return jsonify({"status": "error", "message": "Challenge joining window has expired"}), 400
        
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

# ═══════════════════════════════════════════════════════════
# MAVX ECHOES — MILESTONE CARD GALLERY
# ═══════════════════════════════════════════════════════════

ECHO_TEMPLATES = {
    'naruto':     'assets/echo_templates/naruto.png',
    'dbz':        'assets/echo_templates/dbz.png',
    'deathnote':  'assets/echo_templates/deathnote.png',
    'onepiece':   'assets/echo_templates/onepiece.png',
    'jjk':        'assets/echo_templates/jjk.png',
    'aot':        'assets/echo_templates/aot.png',
    'demonslayer':'assets/echo_templates/demonslayer.png',
}

AVATAR_MAP = {
    'itachi':  'assets/avatars/itachi.jpg',
    'kakashi': 'assets/avatars/kakashi.jpg',
    'naruto':  'assets/avatars/naruto.jpg',
    'sasuke':  'assets/avatars/sasuke.jpg',
}

MILESTONE_META = {
    'initiation':   {'label': 'Initiation Echo',        'icon': '🔥', 'phrase': 'Joined the MavX Mndset'},
    'streak_7':     {'label': '7-Day Streak',            'icon': '⚡', 'phrase': '7-Day Consistency Streak'},
    'streak_30':    {'label': '30-Day Streak',           'icon': '💎', 'phrase': '30-Day Warrior Streak'},
    'leaderboard_1':{'label': 'Leaderboard #1',          'icon': '👑', 'phrase': 'Ranked #1 on Leaderboard'},
    'pomodoro_5':   {'label': '5-Session Day',           'icon': '🎯', 'phrase': '5 Focus Sessions in One Day'},
    'journal_7':    {'label': '7-Day Journal Streak',    'icon': '📜', 'phrase': '7-Day Journal Streak'},
}


def generate_echo_card(echo_id, template_id, username, avatar_id, achievement_phrase, has_synergy):
    """Composite an Echo card PNG using PIL: template BG + dark overlay + text + avatar circle."""
    try:
        os.makedirs('assets/echoes', exist_ok=True)
        out_path = f'assets/echoes/{echo_id}.png'

        # --- Canvas: 720x1280 (9:16) ---
        W, H = 720, 1280

        # Load background template
        tmpl_path = ECHO_TEMPLATES.get(template_id, ECHO_TEMPLATES['naruto'])
        if os.path.exists(tmpl_path):
            bg = Image.open(tmpl_path).convert('RGBA').resize((W, H), Image.LANCZOS)
        else:
            bg = Image.new('RGBA', (W, H), (7, 1, 20, 255))

        canvas = bg.copy()
        draw = ImageDraw.Draw(canvas)

        # --- Dark gradient overlay at bottom 45% ---
        overlay = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        ov_draw = ImageDraw.Draw(overlay)
        grad_start = int(H * 0.42)
        for y in range(grad_start, H):
            alpha = int(220 * ((y - grad_start) / (H - grad_start)) ** 0.6)
            ov_draw.line([(0, y), (W, y)], fill=(0, 0, 0, alpha))
        canvas = Image.alpha_composite(canvas, overlay)
        draw = ImageDraw.Draw(canvas)

        # --- Synergy badge (top-left) ---
        if has_synergy:
            badge_x, badge_y = 30, 30
            draw.rounded_rectangle([badge_x, badge_y, badge_x+110, badge_y+36], radius=10,
                                   fill=(40, 0, 80, 180), outline=(157, 0, 255, 255), width=1)
            try:
                font_badge = ImageFont.truetype('arial.ttf', 18)
            except Exception:
                font_badge = ImageFont.load_default()
            draw.text((badge_x + 12, badge_y + 8), '⚡∞ SYNERGY', fill=(200, 150, 255, 255), font=font_badge)

        # --- Avatar circle (top-right) ---
        av_size = 96
        av_x, av_y = W - av_size - 30, 30
        av_path = AVATAR_MAP.get(avatar_id, 'assets/avatars/itachi.jpg')
        if os.path.exists(av_path):
            try:
                av_img = Image.open(av_path).convert('RGBA').resize((av_size, av_size), Image.LANCZOS)
                mask = Image.new('L', (av_size, av_size), 0)
                ImageDraw.Draw(mask).ellipse([(0, 0), (av_size, av_size)], fill=255)
                av_img.putalpha(mask)
                canvas.paste(av_img, (av_x, av_y), av_img)
                # Neon cyan ring
                draw.ellipse([av_x - 3, av_y - 3, av_x + av_size + 3, av_y + av_size + 3],
                             outline=(0, 243, 255, 200), width=3)
            except Exception:
                pass

        # --- Achievement phrase (center of bottom zone) ---
        try:
            font_phrase = ImageFont.truetype('arialbd.ttf', 44)
        except Exception:
            try:
                font_phrase = ImageFont.truetype('arial.ttf', 44)
            except Exception:
                font_phrase = ImageFont.load_default()

        phrase_y = int(H * 0.68)
        # Word-wrap to max 18 chars per line
        words = achievement_phrase.split()
        lines, line = [], ''
        for w in words:
            if len(line + ' ' + w) <= 18:
                line = (line + ' ' + w).strip()
            else:
                if line:
                    lines.append(line)
                line = w
        if line:
            lines.append(line)
        for i, ln in enumerate(lines):
            bbox = draw.textbbox((0, 0), ln, font=font_phrase)
            tw = bbox[2] - bbox[0]
            draw.text(((W - tw) // 2, phrase_y + i * 52), ln, fill=(255, 255, 255, 255), font=font_phrase)

        # --- Username (below phrase) ---
        try:
            font_user = ImageFont.truetype('arial.ttf', 28)
        except Exception:
            font_user = ImageFont.load_default()
        user_text = f'@{username}'
        bbox_u = draw.textbbox((0, 0), user_text, font=font_user)
        tw_u = bbox_u[2] - bbox_u[0]
        user_y = phrase_y + len(lines) * 52 + 20
        draw.text(((W - tw_u) // 2, user_y), user_text, fill=(0, 243, 255, 220), font=font_user)

        # --- MavX Echoes watermark (bottom-center) ---
        try:
            font_wm = ImageFont.truetype('arial.ttf', 20)
        except Exception:
            font_wm = ImageFont.load_default()
        wm = 'MavX Echoes'
        bbox_wm = draw.textbbox((0, 0), wm, font=font_wm)
        tw_wm = bbox_wm[2] - bbox_wm[0]
        draw.text(((W - tw_wm) // 2, H - 50), wm, fill=(255, 255, 255, 80), font=font_wm)

        # --- Chibi character sticker (bottom-right corner) ---
        sticker_map = {
            'naruto':      'assets/echo_stickers/naruto.png',
            'dbz':         'assets/echo_stickers/goku.png',
            'deathnote':   'assets/echo_stickers/ryuk.png',
            'onepiece':    'assets/echo_stickers/luffy.png',
            'jjk':         'assets/echo_stickers/gojo.png',
            'aot':         'assets/echo_stickers/eren.png',
            'demonslayer': 'assets/echo_stickers/tanjirou.png'
        }
        st_path = sticker_map.get(template_id, 'assets/echo_stickers/naruto.png')
        if os.path.exists(st_path):
            try:
                st_img = Image.open(st_path).convert('RGBA')
                # Resize sticker: width 200px, maintaining aspect ratio
                st_w = 200
                st_h = int(st_img.height * (st_w / st_img.width))
                st_img = st_img.resize((st_w, st_h), Image.LANCZOS)
                
                # Paste in bottom-right corner
                st_x = W - st_w - 10
                st_y = H - st_h - 120 # above watermark
                canvas.paste(st_img, (st_x, st_y), st_img)
            except Exception as e:
                print(f"[STICKER ERROR] {e}")

        # Save as RGB PNG
        final = canvas.convert('RGB')
        final.save(out_path, 'PNG', quality=95)
        return out_path
    except Exception as e:
        print(f'[ECHO CARD ERROR] {e}')
        return None


def check_echo_eligibility(user, uid, db):
    """Returns dict of milestone_type -> {eligible: bool, reason: str}."""
    eligibility = {}
    streak = user.get('streak', 0)
    creation_str = user.get('creation_date', get_ist_iso())
    created = parse_ist_datetime(creation_str) or get_ist_now()
    age_days = max(1, (get_ist_now().date() - created.date()).days + 1)

    # Collect already shared milestone types
    shared_types = set()
    for echo in db.get('echoes', {}).values():
        if isinstance(echo, dict) and echo.get('user_id') == uid:
            shared_types.add(echo.get('milestone_type'))

    # Initiation — once only, day 1+
    if 'initiation' not in shared_types:
        eligibility['initiation'] = {'eligible': True, 'reason': ''}
    else:
        eligibility['initiation'] = {'eligible': False, 'reason': 'Already shared'}

    # Streak milestones — eligible each time a new one is hit
    for stype, needed in [('streak_7', 7), ('streak_30', 30)]:
        if streak >= needed:
            # Find the last time they shared this type
            last_share = None
            for echo in db.get('echoes', {}).values():
                if isinstance(echo, dict) and echo.get('user_id') == uid and echo.get('milestone_type') == stype:
                    t = parse_ist_datetime(echo.get('created_at', ''))
                    if t and (last_share is None or t > last_share):
                        last_share = t
            # Eligible if streak was at different value (new milestone) — allow re-share
            eligibility[stype] = {'eligible': True, 'reason': ''}
        else:
            eligibility[stype] = {'eligible': False, 'reason': f'Reach {needed}-day streak first'}

    # Leaderboard #1 — check current ranking
    all_profiles = db.get('user_profiles', {})
    sorted_users = sorted(all_profiles.items(), key=lambda x: x[1].get('balls', 0), reverse=True)
    is_rank1 = len(sorted_users) > 0 and sorted_users[0][0] == uid
    if is_rank1 and 'leaderboard_1' not in shared_types:
        eligibility['leaderboard_1'] = {'eligible': True, 'reason': ''}
    elif is_rank1:
        eligibility['leaderboard_1'] = {'eligible': True, 'reason': 'New milestone = new eligibility'}
    else:
        eligibility['leaderboard_1'] = {'eligible': False, 'reason': 'Reach #1 on Leaderboard first'}

    # 5 sessions in one day
    today = get_ist_now().date()
    today_sessions = [s for s in db.get('sessions', []) if s.get('user_id') == uid
                      and s.get('status') in ('completed', 'early_exit')
                      and parse_ist_datetime(s.get('start_time', '')) is not None
                      and parse_ist_datetime(s.get('start_time', '')).date() == today]
    if len(today_sessions) >= 5:
        eligibility['pomodoro_5'] = {'eligible': True, 'reason': ''}
    else:
        eligibility['pomodoro_5'] = {'eligible': False, 'reason': f'Complete 5 sessions today ({len(today_sessions)}/5 done)'}

    # 7 journal days
    journal_dates = set()
    for j in db.get('journal', []):
        if j.get('user_id') == uid:
            t = parse_ist_datetime(j.get('timestamp', ''))
            if t:
                journal_dates.add(t.date())
    if len(journal_dates) >= 7:
        eligibility['journal_7'] = {'eligible': True, 'reason': ''}
    else:
        eligibility['journal_7'] = {'eligible': False, 'reason': f'Write journal on 7 days ({len(journal_dates)}/7 done)'}

    return eligibility


@app.route('/api/echoes', methods=['GET'])
def get_echoes():
    db = load_db()
    user, uid = get_current_user(db)
    if not user:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401

    tab = request.args.get('tab', 'all')  # 'all' or 'mine'
    page = int(request.args.get('page', 0))
    per_page = 20

    all_echoes = list(db.get('echoes', {}).values())
    if isinstance(all_echoes, list) and len(all_echoes) > 0 and isinstance(all_echoes[0], dict):
        pass
    else:
        all_echoes = [v for v in db.get('echoes', {}).values() if isinstance(v, dict)]

    if tab == 'mine':
        all_echoes = [e for e in all_echoes if e.get('user_id') == uid]

    all_echoes.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    paginated = all_echoes[page * per_page:(page + 1) * per_page]

    # Annotate liked_by_me
    result = []
    for e in paginated:
        ec = dict(e)
        ec['liked_by_me'] = uid in (ec.get('likes') or [])
        ec['likes_count'] = len(ec.get('likes') or [])
        result.append(ec)

    return jsonify(result)


@app.route('/api/echoes/eligible', methods=['GET'])
def get_eligible_echoes():
    db = load_db()
    user, uid = get_current_user(db)
    if not user:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401

    elig = check_echo_eligibility(user, uid, db)
    result = []
    for mtype, meta in MILESTONE_META.items():
        e = elig.get(mtype, {'eligible': False, 'reason': 'Not available'})
        result.append({
            'type': mtype,
            'label': meta['label'],
            'icon': meta['icon'],
            'phrase': meta['phrase'],
            'eligible': e['eligible'],
            'reason': e['reason'],
        })
    return jsonify(result)


@app.route('/api/echoes/share', methods=['POST'])
def share_echo():
    db = load_db()
    user, uid = get_current_user(db)
    if not user:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401

    data = request.json or {}
    milestone_type = data.get('milestone_type', '').strip()
    template_id = data.get('template_id', 'naruto').strip()

    if milestone_type not in MILESTONE_META:
        return jsonify({'status': 'error', 'message': 'Invalid milestone type'}), 400
    if template_id not in ECHO_TEMPLATES:
        template_id = 'naruto'

    # Verify eligibility
    elig = check_echo_eligibility(user, uid, db)
    if not elig.get(milestone_type, {}).get('eligible'):
        reason = elig.get(milestone_type, {}).get('reason', 'Not eligible')
        return jsonify({'status': 'error', 'message': f'Not eligible: {reason}'}), 403

    # Determine Synergy status
    partner_id = user.get('partner_id')
    has_synergy = bool(partner_id)
    partner_name = None
    if has_synergy and partner_id in db.get('user_profiles', {}):
        pf = db['user_profiles'][partner_id]
        partner_name = pf.get('leaderboard_name') or pf.get('name', 'Partner')

    echo_id = f"echo_{int(get_ist_now().timestamp())}_{random.randint(1000, 9999)}"
    username_display = user.get('leaderboard_name') or user.get('name', 'Warrior')
    achievement_phrase = MILESTONE_META[milestone_type]['phrase']
    avatar_id = user.get('avatar', 'itachi')

    # Generate the card image
    card_path = generate_echo_card(echo_id, template_id, username_display, avatar_id, achievement_phrase, has_synergy)

    echo_obj = {
        'id': echo_id,
        'user_id': uid,
        'template_id': template_id,
        'milestone_type': milestone_type,
        'achievement_phrase': achievement_phrase,
        'username_display': username_display,
        'avatar_id': avatar_id,
        'has_synergy': has_synergy,
        'partner_name': partner_name,
        'synergy_symbol': user.get('synergy_symbol'),
        'likes': [],
        'card_path': card_path,
        'created_at': get_ist_iso(),
    }

    if 'echoes' not in db:
        db['echoes'] = {}
    db['echoes'][echo_id] = echo_obj
    save_db(db)

    return jsonify({'status': 'success', 'echo_id': echo_id, 'card_path': card_path})


@app.route('/api/echoes/<echo_id>/like', methods=['POST'])
def like_echo(echo_id):
    db = load_db()
    user, uid = get_current_user(db)
    if not user:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401

    echo = db.get('echoes', {}).get(echo_id)
    if not echo:
        return jsonify({'status': 'error', 'message': 'Echo not found'}), 404

    likes = echo.get('likes', [])
    if uid in likes:
        likes.remove(uid)
        liked = False
    else:
        likes.append(uid)
        liked = True
    echo['likes'] = likes
    db['echoes'][echo_id] = echo
    save_db(db)
    return jsonify({'status': 'success', 'likes_count': len(likes), 'liked': liked})


@app.route('/api/echoes/card-image/<echo_id>', methods=['GET'])
def serve_echo_card(echo_id):
    db = load_db()
    echo = db.get('echoes', {}).get(echo_id)
    if not echo:
        return jsonify({'status': 'error', 'message': 'Echo not found'}), 404
    card_path = echo.get('card_path', '')
    if not card_path or not os.path.exists(card_path):
        return jsonify({'status': 'error', 'message': 'Card image not found'}), 404
    return send_file(card_path, mimetype='image/png')


# ═══════════════════════════════════════════════════════════
# MAVX SYNERGY — ACCOUNTABILITY DUO SYSTEM
# ═══════════════════════════════════════════════════════════

def generate_synergy_code(db):
    import string
    chars = string.ascii_uppercase + string.digits
    while True:
        code = 'MAVX-' + ''.join(random.choice(chars) for _ in range(4))
        existing = [p.get('synergy_code') for p in db.get('synergy_pairs', {}).values()]
        if code not in existing:
            return code


def get_active_pair_for_user(uid, db):
    """Returns (duo_id, pair_data) if user has an active synergy, else (None, None)."""
    for duo_id, pair in db.get('synergy_pairs', {}).items():
        if isinstance(pair, dict) and pair.get('is_active'):
            if pair.get('partner_a_id') == uid or pair.get('partner_b_id') == uid:
                return duo_id, pair
    return None, None


@app.route('/api/synergy/create', methods=['POST'])
def synergy_create():
    db = load_db()
    user, uid = get_current_user(db)
    if not user:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401

    if user.get('partner_id'):
        return jsonify({'status': 'error', 'message': 'Already in an active Synergy'}), 400

    # Check for existing pending invite from this user
    for duo_id, pair in db.get('synergy_pairs', {}).items():
        if pair.get('partner_a_id') == uid and not pair.get('partner_b_id') and pair.get('is_active') is False:
            return jsonify({'status': 'success', 'synergy_code': pair['synergy_code'], 'duo_id': duo_id})

    if 'synergy_pairs' not in db:
        db['synergy_pairs'] = {}

    code = generate_synergy_code(db)
    duo_id = f"syn_{int(get_ist_now().timestamp())}_{random.randint(100, 999)}"
    pair = {
        'duo_id': duo_id,
        'partner_a_id': uid,
        'partner_b_id': None,
        'synergy_code': code,
        'is_active': False,
        'aura_a': 0,
        'aura_b': 0,
        'created_at': get_ist_iso(),
        'last_activity': get_ist_iso(),
        'recent_sessions': [],
    }
    db['synergy_pairs'][duo_id] = pair
    save_db(db)
    return jsonify({'status': 'success', 'synergy_code': code, 'duo_id': duo_id})


@app.route('/api/synergy/join', methods=['POST'])
def synergy_join():
    db = load_db()
    user, uid = get_current_user(db)
    if not user:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401

    if user.get('partner_id'):
        return jsonify({'status': 'error', 'message': 'Already in an active Synergy'}), 400

    data = request.json or {}
    code = (data.get('synergy_code') or '').strip().upper()
    if not code:
        return jsonify({'status': 'error', 'message': 'Synergy code required'}), 400

    # Find the pending pair
    target_duo_id = None
    target_pair = None
    for duo_id, pair in db.get('synergy_pairs', {}).items():
        if pair.get('synergy_code') == code and not pair.get('partner_b_id') and not pair.get('is_active'):
            target_duo_id = duo_id
            target_pair = pair
            break

    if not target_pair:
        return jsonify({'status': 'error', 'message': 'Invalid or expired Synergy Code'}), 404

    a_id = target_pair['partner_a_id']
    if a_id == uid:
        return jsonify({'status': 'error', 'message': 'Cannot link with yourself'}), 400

    symbol = '⚡∞'
    target_pair['partner_b_id'] = uid
    target_pair['is_active'] = True
    target_pair['linked_at'] = get_ist_iso()
    target_pair['last_activity'] = get_ist_iso()
    db['synergy_pairs'][target_duo_id] = target_pair

    # Update both user profiles
    db['user_profiles'][a_id]['partner_id'] = uid
    db['user_profiles'][a_id]['synergy_symbol'] = symbol
    db['user_profiles'][uid]['partner_id'] = a_id
    db['user_profiles'][uid]['synergy_symbol'] = symbol

    save_db(db)
    return jsonify({'status': 'success', 'message': 'Synergy link established!', 'synergy_symbol': symbol})


@app.route('/api/synergy/status', methods=['GET'])
def synergy_status():
    db = load_db()
    user, uid = get_current_user(db)
    if not user:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401

    partner_id = user.get('partner_id')
    if not partner_id:
        # Check for pending invite this user created
        pending_code = None
        for pair in db.get('synergy_pairs', {}).values():
            if pair.get('partner_a_id') == uid and not pair.get('is_active'):
                pending_code = pair.get('synergy_code')
                break
        return jsonify({
            'has_partner': False,
            'pending_code': pending_code,
            'aura_self': user.get('aura_balance', 0),
        })

    duo_id, pair = get_active_pair_for_user(uid, db)
    if not pair:
        # Stale partner_id, clean up
        db['user_profiles'][uid]['partner_id'] = None
        db['user_profiles'][uid]['synergy_symbol'] = None
        save_db(db)
        return jsonify({'has_partner': False})

    is_a = pair.get('partner_a_id') == uid
    aura_self = pair.get('aura_a') if is_a else pair.get('aura_b')
    aura_partner = pair.get('aura_b') if is_a else pair.get('aura_a')

    partner_profile = db.get('user_profiles', {}).get(partner_id, {})
    partner_info = {
        'name': partner_profile.get('leaderboard_name') or partner_profile.get('name', 'Partner'),
        'avatar': partner_profile.get('avatar', 'itachi'),
        'aura': aura_partner,
    }

    return jsonify({
        'has_partner': True,
        'duo_id': duo_id,
        'synergy_code': pair.get('synergy_code'),
        'synergy_symbol': user.get('synergy_symbol', '⚡∞'),
        'partner': partner_info,
        'aura_self': aura_self,
        'aura_partner': aura_partner,
        'created_at': pair.get('linked_at') or pair.get('created_at'),
        'recent_sessions': pair.get('recent_sessions', [])[-10:],
    })


@app.route('/api/synergy/task/start', methods=['POST'])
def synergy_task_start():
    db = load_db()
    user, uid = get_current_user(db)
    if not user:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401

    data = request.json or {}
    title = (data.get('title') or '').strip()
    if not title:
        return jsonify({'status': 'error', 'message': 'Task title is required'}), 400
    words = [w for w in title.split() if w]
    if len(words) < 2:
        return jsonify({'status': 'error', 'message': 'Title must be at least 2 words'}), 400

    mark_user_active_today(user)

    # Record as a normal session with the Synergy task title as subject
    session_id = f"syn_sess_{int(get_ist_now().timestamp())}_{random.randint(1000, 9999)}"
    session = {
        'id': session_id,
        'user_id': uid,
        'subject': f'[Synergy] {title}',
        'mode': 'Synergy Duo Task',
        'start_time': get_ist_iso(),
        'status': 'running',
        'is_synergy': True,
    }
    db['sessions'].append(session)
    save_db(db)
    return jsonify({'status': 'success', 'session_id': session_id})


@app.route('/api/synergy/task/end', methods=['POST'])
def synergy_task_end():
    db = load_db()
    user, uid = get_current_user(db)
    if not user:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401

    data = request.json or {}
    session_id = data.get('session_id', '')
    duration_minutes = max(0.0, float(data.get('duration_minutes', 0)))

    # Complete the normal session record
    for s in db['sessions']:
        if s['id'] == session_id and s.get('user_id') == uid:
            if s.get('status') == 'running':
                s['status'] = 'completed'
                s['end_time'] = get_ist_iso()
                s['duration_minutes'] = duration_minutes
                # Standard ball reward for focus
                earned_balls = max(1, int(round(duration_minutes)))
                db['user_profiles'][uid]['balls'] = db['user_profiles'][uid].get('balls', 0) + earned_balls
            break

    # Calculate Aura: 2 pts per minute
    aura_earned = int(duration_minutes * 2)
    duo_id, pair = get_active_pair_for_user(uid, db)

    if pair:
        is_a = pair.get('partner_a_id') == uid
        partner_id = pair.get('partner_b_id') if is_a else pair.get('partner_a_id')

        if is_a:
            pair['aura_a'] = pair.get('aura_a', 0) + aura_earned
        else:
            pair['aura_b'] = pair.get('aura_b', 0) + aura_earned

        # Also credit partner
        if partner_id and partner_id in db.get('user_profiles', {}):
            if is_a:
                pair['aura_b'] = pair.get('aura_b', 0) + aura_earned
                db['user_profiles'][partner_id]['aura_balance'] = db['user_profiles'][partner_id].get('aura_balance', 0) + aura_earned
            else:
                pair['aura_a'] = pair.get('aura_a', 0) + aura_earned
                db['user_profiles'][partner_id]['aura_balance'] = db['user_profiles'][partner_id].get('aura_balance', 0) + aura_earned

        db['user_profiles'][uid]['aura_balance'] = db['user_profiles'][uid].get('aura_balance', 0) + aura_earned
        pair['last_activity'] = get_ist_iso()

        # Log in recent sessions
        recent = pair.get('recent_sessions', [])
        task_title = ''
        for s in db['sessions']:
            if s.get('id') == session_id:
                task_title = s.get('subject', 'Duo Task').replace('[Synergy] ', '')
                break
        recent.append({
            'session_id': session_id,
            'title': task_title,
            'duration_minutes': duration_minutes,
            'aura_earned': aura_earned,
            'completed_by': uid,
            'completed_at': get_ist_iso(),
        })
        pair['recent_sessions'] = recent[-50:]  # Keep last 50
        db['synergy_pairs'][duo_id] = pair

    save_db(db)
    total_aura = db['user_profiles'][uid].get('aura_balance', 0)
    return jsonify({'status': 'success', 'aura_earned': aura_earned, 'total_aura': total_aura})


@app.route('/api/synergy/dismantle', methods=['POST'])
def synergy_dismantle():
    db = load_db()
    user, uid = get_current_user(db)
    if not user:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401

    partner_id = user.get('partner_id')
    if not partner_id:
        return jsonify({'status': 'error', 'message': 'No active Synergy to dismantle'}), 400

    duo_id, pair = get_active_pair_for_user(uid, db)

    # Apply penalties
    db['user_profiles'][uid]['balls'] = db['user_profiles'][uid].get('balls', 0) - 50
    db['user_profiles'][uid]['partner_id'] = None
    db['user_profiles'][uid]['synergy_symbol'] = None

    if partner_id in db.get('user_profiles', {}):
        db['user_profiles'][partner_id]['balls'] = db['user_profiles'][partner_id].get('balls', 0) - 50
        db['user_profiles'][partner_id]['partner_id'] = None
        db['user_profiles'][partner_id]['synergy_symbol'] = None

    if pair:
        pair['is_active'] = False
        pair['dismantled_at'] = get_ist_iso()
        pair['dismantled_by'] = uid
        db['synergy_pairs'][duo_id] = pair

    save_db(db)
    return jsonify({'status': 'success', 'message': 'Synergy dismantled. -50 Dragon Balls applied.'})


@app.route('/api/synergy/leaderboard', methods=['GET'])
def synergy_leaderboard():
    db = load_db()
    user, uid = get_current_user(db)
    if not user:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401

    if not user.get('partner_id'):
        return jsonify({'status': 'error', 'message': 'Aura Ranking only visible to partnered warriors'}), 403

    # Build list of all partnered users with their aura
    result = []
    for user_id, profile in db.get('user_profiles', {}).items():
        if profile.get('partner_id'):
            result.append({
                'name': profile.get('leaderboard_name') or profile.get('name', 'Warrior'),
                'email': user_id,
                'avatar': profile.get('avatar', 'itachi'),
                'aura': profile.get('aura_balance', 0),
                'synergy_symbol': profile.get('synergy_symbol', '⚡∞'),
            })
    result.sort(key=lambda x: x['aura'], reverse=True)
    return jsonify(result)


if __name__ == '__main__':
    print("MavX Mndset Local Server Starting...")
    app.run(debug=True, host='0.0.0.0', port=5000)
