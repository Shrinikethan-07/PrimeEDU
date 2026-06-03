with open(r'c:\Users\HI\Desktop\PrimeEDU\app.py', 'r', encoding='utf-8') as f:
    text = f.read()

# Replace auth fields
text = text.replace('phone = data.get(\'phone\')', 'email = data.get(\'email\')')
text = text.replace('if not phone or not password:', 'if not email or not password:')
text = text.replace('if phone in db[\'user_profiles\']:', 'if email in db[\'user_profiles\']:')
text = text.replace('return jsonify({"status": "error", "message": "Phone and password required"}), 400', 'return jsonify({"status": "error", "message": "Email and password required"}), 400')
text = text.replace('return jsonify({"status": "error", "message": "Phone already registered"}), 400', 'return jsonify({"status": "error", "message": "Email already registered"}), 400')
text = text.replace('db[\'user_profiles\'][phone] = {', 'db[\'user_profiles\'][email] = {')
text = text.replace('"phone": phone,', '"email": email,')
text = text.replace('user = db[\'user_profiles\'].get(phone)', 'user = db[\'user_profiles\'].get(email)')
text = text.replace('phone = request.json.get(\'phone\')', 'email = request.json.get(\'email\')')
text = text.replace('if phone not in db[\'user_profiles\']:', 'if email not in db[\'user_profiles\']:')
text = text.replace('return jsonify({"status": "error", "message": "Phone not found"}), 404', 'return jsonify({"status": "error", "message": "Email not found"}), 404')
text = text.replace('db[\'user_profiles\'][phone][\'reset_otp\'] = otp', 'db[\'user_profiles\'][email][\'reset_otp\'] = otp')
text = text.replace('print(f"\\n{\'=\'*40}\\n[SMS SIMULATOR] OTP for {phone}: {otp}\\n{\'=\'*40}\\n")', 'print(f"\\n{\'=\'*40}\\n[EMAIL OTP SIMULATOR] OTP for {email}: {otp}\\n{\'=\'*40}\\n")')
text = text.replace('return jsonify({"status": "success", "message": "OTP sent to phone"})', 'return jsonify({"status": "success", "message": "OTP sent to email"})')

# Ensure we replace all phone variables in verify_otp and login
text = text.replace('phone = data.get(\'phone\')', 'email = data.get(\'email\')')

# Add Leaderboard & Admin endpoints
endpoints = '''
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
    user, uid = get_current_user(db)
    if not user or user.get('name', '').lower() != 'admin':
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

if __name__ == '__main__':'''

text = text.replace("if __name__ == '__main__':", endpoints)

with open(r'c:\Users\HI\Desktop\PrimeEDU\app.py', 'w', encoding='utf-8') as f:
    f.write(text)

print('Successfully modified app.py')
