import os
import glob

# 1. Update Frontend JS
directories = [
    r'c:\Users\HI\Documents\PrimeEDU',
    r'c:\Users\HI\Desktop\PrimeEDU\public'
]

old_js = '''const _me = localStorage.getItem('primeedu_leaderboard_name') || localStorage.getItem('primeedu_name') || '';
    const _email = localStorage.getItem('primeedu_email') || '';
    if(_me === 'Shrinikethan M S' && _email === 'buvanavel.m01@gmail.com') {'''

new_js = '''const _me = (localStorage.getItem('primeedu_leaderboard_name') || localStorage.getItem('primeedu_name') || '').trim().toLowerCase();
    const _email = (localStorage.getItem('primeedu_email') || '').trim().toLowerCase();
    if(_me === 'shrinikethan m s' && _email === 'buvanavel.m01@gmail.com') {'''

for d in directories:
    for filepath in glob.glob(os.path.join(d, '*.html')):
        with open(filepath, 'r', encoding='utf-8') as f:
            text = f.read()
        
        if old_js in text:
            text = text.replace(old_js, new_js)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(text)

# 2. Update Backend Python
app_path = r'c:\Users\HI\Desktop\PrimeEDU\app.py'
with open(app_path, 'r', encoding='utf-8') as f:
    app_text = f.read()

old_admin_logic = '''if not user or user.get('name') != 'Shrinikethan M S' or email != 'buvanavel.m01@gmail.com':'''
new_admin_logic = '''if not user or user.get('name', '').strip().lower() != 'shrinikethan m s' or email.strip().lower() != 'buvanavel.m01@gmail.com':'''

app_text = app_text.replace(old_admin_logic, new_admin_logic)
with open(app_path, 'w', encoding='utf-8') as f:
    f.write(app_text)

print("Updated lenient admin auth logic!")
