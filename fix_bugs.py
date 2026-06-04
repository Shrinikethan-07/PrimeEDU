import os

# 1. Fix app.py streak logic
app_path = r'c:\Users\HI\Desktop\PrimeEDU\app.py'
with open(app_path, 'r', encoding='utf-8') as f:
    app_text = f.read()

old_streak_logic = '''def check_streak_and_login(user):
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
    return user'''

new_streak_logic = '''def check_streak_and_login(user):
    last_login = user.get('last_login')
    if last_login:
        last_date = datetime.fromisoformat(last_login)
        now = datetime.now()
        
        # Calculate difference in calendar days, not 24-hour periods
        diff_days = (now.date() - last_date.date()).days
        
        # Streak logic
        if diff_days == 1:
            user['streak'] = user.get('streak', 0) + 1
            if user['streak'] == 7: user['balls'] += 20
            elif user['streak'] == 30: user['balls'] += 100
            elif user['streak'] == 365: user['balls'] += 1000
        elif diff_days > 1:
            user['streak'] = 0 # reset
            
    user['last_login'] = datetime.now().isoformat()
    return user'''

app_text = app_text.replace(old_streak_logic, new_streak_logic)
with open(app_path, 'w', encoding='utf-8') as f:
    f.write(app_text)

# 2. Fix index.html email saving bug
index_paths = [
    r'c:\Users\HI\Desktop\PrimeEDU\public\index.html',
    r'c:\Users\HI\Documents\PrimeEDU\index.html'
]

for p in index_paths:
    if os.path.exists(p):
        with open(p, 'r', encoding='utf-8') as f:
            idx_text = f.read()
        
        idx_text = idx_text.replace(
            "localStorage.setItem('primeedu_email', document.getElementById('reg-email').value);",
            "localStorage.setItem('primeedu_email', email);"
        )
        idx_text = idx_text.replace(
            "localStorage.setItem('primeedu_email', document.getElementById('login-email').value);",
            "localStorage.setItem('primeedu_email', email);"
        )
        
        with open(p, 'w', encoding='utf-8') as f:
            f.write(idx_text)

print("Fixed streak logic and index.html email bug!")
