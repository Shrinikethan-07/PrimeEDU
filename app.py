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
    "clans": "clan_id"
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

scheduler = BackgroundScheduler(timezone=timezone(timedelta(hours=5, minutes=30)))
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
                new_completed_rewards += 1
            else:
                # Keep it marked as rewarded
                t['rewarded'] = True
        else:
            t['rewarded'] = False # If they uncheck it, reset
            
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
    width, height = 400, 250
    img = Image.new('RGBA', (width, height), color=(13, 4, 26, 255))
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
    width, height = 400, 250
    img = Image.new('RGBA', (width, height), color=(13, 4, 26, 255))
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
    visuals = visual_agent.get_recap_visuals(sessions, tasks)
    return jsonify(visuals)

@app.route('/api/recap/graph/<graph_type>')
def get_recap_graph(graph_type):
    db = load_db()
    user, uid = get_current_user(db)
    if not user:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
        
    sessions = [s for s in db.get('sessions', []) if s.get('user_id') == uid]
    
    if graph_type == 'weekly_grit':
        hours, labels = get_study_hours_by_day(sessions, 7)
        buf = generate_line_graph(hours, labels)
    elif graph_type == 'consistency_monthly':
        hours, labels = get_study_hours_by_day(sessions, 30)
        buf = generate_line_graph(hours, labels)
    elif graph_type == 'knowledge_monthly':
        categories, values = get_study_hours_by_subject(sessions, 30)
        buf = generate_bar_graph(categories, values)
    elif graph_type == 'legacy_yearly':
        hours, labels = get_study_hours_by_month(sessions)
        buf = generate_line_graph(hours, labels)
    elif graph_type == 'growth_yearly':
        categories, values = get_study_hours_by_subject(sessions, 365)
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

if __name__ == '__main__':
    print("MavX Mndset Local Server Starting...")
    app.run(debug=True, host='0.0.0.0', port=5000)
