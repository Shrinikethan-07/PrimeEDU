from flask import Flask, render_template, request, jsonify, send_from_directory
import os
import json
import asyncio
from datetime import datetime, timedelta
from backend.agents.core import FocusForgeAgent, DisciplineAgent, JournalEntry

app = Flask(__name__, 
            static_folder='.', 
            template_folder='.')

# Mock database
DB_PATH = 'data/db.json'
if not os.path.exists('data'):
    os.makedirs('data')

def init_db():
    if not os.path.exists(DB_PATH):
        initial_data = {
            "user_profiles": {
                "seetharam_01": {
                    "name": "Seetharam",
                    "leaderboard_name": "Seetharam",
                    "balls": 750,
                    "streak": 12,
                    "massive_goal": None
                }
            },
            "sessions": [],
            "syllabus_progress": {},
            "topic_notes": {},
            "journal": [],
            "tasks": [],
            "custom_syllabus": {}
        }
        with open(DB_PATH, 'w') as f:
            json.dump(initial_data, f, indent=4)

init_db()

DEFAULT_USER = {
    "name": "Seetharam",
    "leaderboard_name": "Seetharam",
    "balls": 750,
    "streak": 12,
    "massive_goal": None
}

def ensure_db_structure(db):
    """Merge legacy db.json shapes into the schema the app expects."""
    if "user_profiles" not in db:
        db["user_profiles"] = {"seetharam_01": dict(DEFAULT_USER)}
    elif "seetharam_01" not in db["user_profiles"]:
        db["user_profiles"]["seetharam_01"] = dict(DEFAULT_USER)
    else:
        for key, val in DEFAULT_USER.items():
            db["user_profiles"]["seetharam_01"].setdefault(key, val)

    for key, default in [
        ("sessions", []),
        ("syllabus_progress", {}),
        ("topic_notes", {}),
        ("journal", []),
        ("tasks", []),
        ("custom_syllabus", {}),
    ]:
        db.setdefault(key, default if not isinstance(default, dict) else dict(default))
    return db

def load_db():
    with open(DB_PATH, 'r') as f:
        db = json.load(f)
    before = json.dumps(db, sort_keys=True)
    db = ensure_db_structure(db)
    if json.dumps(db, sort_keys=True) != before:
        save_db(db)
    return db

def save_db(data):
    with open(DB_PATH, 'w') as f:
        json.dump(data, f, indent=4)

# Initialize Agents
journal_agent = FocusForgeAgent(api_key="LOCAL_DEV")
discipline_agent = DisciplineAgent()

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/api/user/profile', methods=['GET', 'POST'])
def handle_profile():
    db = load_db()
    user_id = "seetharam_01"
    if request.method == 'POST':
        data = request.json
        if 'leaderboard_name' in data:
            db['user_profiles'][user_id]['leaderboard_name'] = data['leaderboard_name']
        if 'massive_goal' in data:
            # Check if existing goal is locked
            current_goal = db['user_profiles'][user_id].get('massive_goal')
            if current_goal:
                deadline = datetime.fromisoformat(current_goal['deadline'])
                if datetime.now() < deadline:
                    return jsonify({"status": "error", "message": "Goal is locked until the deadline."}), 403
            db['user_profiles'][user_id]['massive_goal'] = data['massive_goal']
        save_db(db)
        return jsonify({"status": "success"})
    return jsonify(db['user_profiles'].get(user_id, {}))

@app.route('/api/journal', methods=['POST'])
def submit_journal():
    data = request.json or {}
    content = data.get('content', '')
    title = data.get('title', f"Entry_{datetime.now().strftime('%Y%m%d_%H%M%S')}")

    entry = JournalEntry(
        user_id="seetharam_01",
        content=content,
        timestamp=datetime.now(),
        mood_score=7
    )

    db = load_db()
    db['journal'].append({
        "title": title,
        "content": content,
        "timestamp": datetime.now().isoformat()
    })
    save_db(db)

    asyncio.run(journal_agent.analyze_journal(entry))
    recap = asyncio.run(journal_agent.generate_recap_card([entry], period="Daily"))

    return jsonify({
        "status": "success",
        "recap": {
            "title": recap.title,
            "content": recap.content,
            "sentiment": recap.sentiment
        }
    })

@app.route('/api/tasks', methods=['GET', 'POST'])
def handle_tasks():
    db = load_db()
    if request.method == 'POST':
        task = request.json
        task['id'] = len(db['tasks']) + 1
        db['tasks'].append(task)
        save_db(db)
        return jsonify({"status": "success", "task": task})
    return jsonify(db['tasks'])

@app.route('/api/tasks/sync', methods=['POST'])
def sync_tasks():
    db = load_db()
    data = request.json
    db['tasks'] = data.get('tasks', [])
    save_db(db)
    return jsonify({"status": "success"})

@app.route('/api/syllabus/custom', methods=['POST'])
def sync_custom_syllabus():
    db = load_db()
    data = request.json or {}
    db['custom_syllabus'] = data.get('chapters', {})
    save_db(db)
    return jsonify({"status": "success"})


@app.route('/api/syllabus/progress', methods=['GET', 'POST'])
def syllabus_progress():
    db = load_db()
    user_id = "seetharam_01"

    if request.method == 'GET':
        return jsonify(db.get('syllabus_progress', {}))

    data = request.json or {}
    topic_id = data.get('topic_id')
    if topic_id is None:
        return jsonify({"status": "error", "message": "topic_id required"}), 400

    completed = bool(data.get('completed'))
    db['syllabus_progress'][topic_id] = completed

    if completed:
        profile = db['user_profiles'][user_id]
        profile['balls'] = profile.get('balls', 750) + 5

    save_db(db)
    return jsonify({
        "status": "success",
        "balls": db['user_profiles'][user_id].get('balls', 750)
    })


@app.route('/api/syllabus/notes', methods=['POST'])
def syllabus_notes():
    db = load_db()
    data = request.json or {}
    topic_id = data.get('topic_id')
    if not topic_id:
        return jsonify({"status": "error", "message": "topic_id required"}), 400
    db['topic_notes'][topic_id] = data.get('content', '')
    save_db(db)
    return jsonify({"status": "success"})

@app.route('/api/journal/save', methods=['POST'])
def save_journal_entry():
    db = load_db()
    data = request.json
    entry = {
        "id": int(datetime.now().timestamp()),
        "title": data.get('title', 'The Wish'),
        "content": data.get('content'),
        "timestamp": datetime.now().isoformat()
    }
    db['journal'].append(entry)
    save_db(db)
    return jsonify({"status": "success"})


@app.route('/api/sessions/start', methods=['POST'])
def start_session():
    db = load_db()
    data = request.json or {}
    session = {
        "id": int(datetime.now().timestamp() * 1000),
        "subject": data.get('subject', 'General'),
        "start_time": datetime.now().isoformat(),
        "end_time": None,
        "status": "active"
    }
    db['sessions'].append(session)
    save_db(db)
    return jsonify({"status": "success", "session": session})


@app.route('/api/sessions/end', methods=['POST'])
def end_session():
    db = load_db()
    data = request.json or {}
    session_id = data.get('session_id')
    user_id = "seetharam_01"
    balls_earned = 0

    for session in db['sessions']:
        if session.get('id') == session_id and session.get('status') == 'active':
            session['end_time'] = datetime.now().isoformat()
            session['status'] = 'abandoned' if data.get('early_exit') else 'completed'
            if session['status'] == 'completed':
                start = datetime.fromisoformat(session['start_time'])
                end = datetime.fromisoformat(session['end_time'])
                minutes = max(1, int((end - start).total_seconds() / 60))
                balls_earned = min(50, minutes)
                profile = db['user_profiles'][user_id]
                profile['balls'] = profile.get('balls', 750) + balls_earned
            save_db(db)
            return jsonify({"status": "success", "balls_earned": balls_earned})

    return jsonify({"status": "error", "message": "Session not found"}), 404


@app.route('/api/identity', methods=['GET'])
def get_identity():
    db = load_db()
    sessions = db['sessions']
    user = db['user_profiles']["seetharam_01"]
    
    if not sessions:
        return jsonify({"identity": "THE BEGINNER", "description": "Just starting your journey."})

    # Logic for identities
    night_minutes = 0
    morning_minutes = 0
    total_minutes = 0
    max_session_len = 0
    subject_times = {}

    for s in sessions:
        if s['status'] != 'completed': continue
        start = datetime.fromisoformat(s['start_time'])
        end = datetime.fromisoformat(s['end_time'])
        duration = (end - start).total_seconds() / 60
        total_minutes += duration
        max_session_len = max(max_session_len, duration)
        
        # Time of day
        hour = start.hour
        if 22 <= hour or hour <= 4:
            night_minutes += duration
        if 4 <= hour <= 8:
            morning_minutes += duration
            
        # Subject distribution
        subj = s.get('subject', 'General')
        subject_times[subj] = subject_times.get(subj, 0) + duration

    if user['streak'] >= 15:
        return jsonify({"identity": "THE STREAK MASTER", "description": "Maintained study streak of 15+ days straight."})
    if night_minutes > (total_minutes * 0.5):
        return jsonify({"identity": "THE NIGHT OWL", "description": "Thrives when the rest of the world is asleep."})
    if morning_minutes > (total_minutes * 0.6):
        return jsonify({"identity": "THE EARLY RISER", "description": "Owns the morning before the day even begins."})
    if max_session_len >= 90:
        return jsonify({"identity": "THE DEEP DIVER", "description": "Prefers long uninterrupted focus sessions."})
        
    # Alchemist check (simplified: 3+ subjects with similar time)
    if len(subject_times) >= 3:
        vals = list(subject_times.values())
        if max(vals) - min(vals) < total_minutes * 0.2:
            return jsonify({"identity": "THE ALCHEMIST", "description": "Excels at balancing completely different fields of study."})

    return jsonify({"identity": "THE MIND MAKER", "description": "A dedicated practitioner of discipline."})


@app.route('/<path:path>')
def static_files(path):
    return send_from_directory('.', path)

if __name__ == '__main__':
    print("PrimeEDU Local Server Starting...")
    app.run(debug=True, host='0.0.0.0', port=5000)
