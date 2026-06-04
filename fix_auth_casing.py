import os

app_path = r'c:\Users\HI\Desktop\PrimeEDU\app.py'
with open(app_path, 'r', encoding='utf-8') as f:
    app_text = f.read()

# Fix register
old_reg = '''def register():
    db = load_db()
    data = request.json
    email = data.get('email')'''

new_reg = '''def register():
    db = load_db()
    data = request.json
    email = data.get('email', '').strip().lower()'''

app_text = app_text.replace(old_reg, new_reg)

# Fix login
old_login = '''def login():
    db = load_db()
    data = request.json
    email = data.get('email')'''

new_login = '''def login():
    db = load_db()
    data = request.json
    email = data.get('email', '').strip().lower()'''

app_text = app_text.replace(old_login, new_login)

with open(app_path, 'w', encoding='utf-8') as f:
    f.write(app_text)

print("Fixed auth casing/spaces!")
