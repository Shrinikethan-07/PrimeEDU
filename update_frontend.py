import os

file_path = r'c:\Users\HI\Documents\PrimeEDU\index.html'

with open(file_path, 'r', encoding='utf-8') as f:
    text = f.read()

# Replace HTML labels and icons
text = text.replace('<label>Mobile Number</label>', '<label>Google Email ID</label>')
text = text.replace('<label>Registered Mobile Number</label>', '<label>Registered Google Email</label>')
text = text.replace('type="tel"', 'type="email"')
text = text.replace('placeholder="Enter mobile number"', 'placeholder="example@gmail.com"')
text = text.replace('placeholder="Enter your mobile number"', 'placeholder="example@gmail.com"')
text = text.replace('class="fas fa-phone input-icon"', 'class="fas fa-envelope input-icon"')

# Replace IDs
text = text.replace('id="login-phone"', 'id="login-email"')
text = text.replace('id="reg-phone"', 'id="reg-email"')
text = text.replace('id="reset-phone"', 'id="reset-email"')

# Replace JS variables
text = text.replace("const phone = document.getElementById('login-phone').value;", "const email = document.getElementById('login-email').value;")
text = text.replace("body: JSON.stringify({ phone, password: pass })", "body: JSON.stringify({ email, password: pass })")
text = text.replace("const phone = document.getElementById('reg-phone').value;", "const email = document.getElementById('reg-email').value;")
text = text.replace("body: JSON.stringify({ name, phone, password: pass })", "body: JSON.stringify({ name, email, password: pass })")
text = text.replace("document.getElementById('login-phone').value = phone;", "document.getElementById('login-email').value = email;")
text = text.replace("const phone = document.getElementById('reset-phone').value;", "const email = document.getElementById('reset-email').value;")
text = text.replace("body: JSON.stringify({ phone })", "body: JSON.stringify({ email })")
text = text.replace("body: JSON.stringify({ phone, otp, new_password: new_pass })", "body: JSON.stringify({ email, otp, new_password: new_pass })")

# In case my previous replacements didn't catch the exact string (like auto-login)
text = text.replace("JSON.stringify({ phone, password: pass })", "JSON.stringify({ email, password: pass })")
text = text.replace("login-phone", "login-email")
text = text.replace("reg-phone", "reg-email")
text = text.replace("reset-phone", "reset-email")

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(text)

print("Updated index.html frontend")
