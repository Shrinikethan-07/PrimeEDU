import os
import glob

directories = [
    r'c:\Users\HI\Documents\PrimeEDU',
    r'c:\Users\HI\Desktop\PrimeEDU\public'
]

# 1. Update index.html to store email in localStorage
for d in directories:
    index_path = os.path.join(d, 'index.html')
    if os.path.exists(index_path):
        with open(index_path, 'r', encoding='utf-8') as f:
            text = f.read()
        
        # In handleLogin
        if "localStorage.setItem('primeedu_leaderboard_name', loginData.name);" in text:
            text = text.replace("localStorage.setItem('primeedu_leaderboard_name', loginData.name);",
                                "localStorage.setItem('primeedu_leaderboard_name', loginData.name);\n                localStorage.setItem('primeedu_email', document.getElementById('login-email').value);")
        
        # In handleRegister
        if "localStorage.setItem('primeedu_leaderboard_name', data.name);" in text:
            text = text.replace("localStorage.setItem('primeedu_leaderboard_name', data.name);",
                                "localStorage.setItem('primeedu_leaderboard_name', data.name);\n                localStorage.setItem('primeedu_email', document.getElementById('reg-email').value);")
        
        with open(index_path, 'w', encoding='utf-8') as f:
            f.write(text)

# 2. Update Admin Visibility JS in all HTML files
old_js = '''const _me = localStorage.getItem('primeedu_leaderboard_name') || localStorage.getItem('primeedu_name') || '';
    if(_me.toLowerCase() === 'admin') {'''

new_js = '''const _me = localStorage.getItem('primeedu_leaderboard_name') || localStorage.getItem('primeedu_name') || '';
    const _email = localStorage.getItem('primeedu_email') || '';
    if(_me === 'Shrinikethan M S' && _email === 'buvanavel.m01@gmail.com') {'''

for d in directories:
    for filepath in glob.glob(os.path.join(d, '*.html')):
        with open(filepath, 'r', encoding='utf-8') as f:
            text = f.read()
        
        if old_js in text:
            text = text.replace(old_js, new_js)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(text)

# 3. Update admin.html unauthorized message
for d in directories:
    admin_path = os.path.join(d, 'admin.html')
    if os.path.exists(admin_path):
        with open(admin_path, 'r', encoding='utf-8') as f:
            text = f.read()
        text = text.replace('Only the user named "admin" can access the Admin Dashboard.',
                            'Only the user named "Shrinikethan M S" with email "buvanavel.m01@gmail.com" can access the Admin Dashboard.')
        with open(admin_path, 'w', encoding='utf-8') as f:
            f.write(text)

# 4. Update app.py backend logic
app_path = r'c:\Users\HI\Desktop\PrimeEDU\app.py'
with open(app_path, 'r', encoding='utf-8') as f:
    app_text = f.read()

old_admin_logic = '''def admin_users():
    db = load_db()
    user, uid = get_current_user(db)
    if not user or user.get('name', '').lower() != 'admin':'''

new_admin_logic = '''def admin_users():
    db = load_db()
    user, email = get_current_user(db)
    if not user or user.get('name') != 'Shrinikethan M S' or email != 'buvanavel.m01@gmail.com':'''

app_text = app_text.replace(old_admin_logic, new_admin_logic)
with open(app_path, 'w', encoding='utf-8') as f:
    f.write(app_text)

print("Updated strict admin rules successfully!")
