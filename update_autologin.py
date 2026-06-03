import os
import glob

src = r'c:\Users\HI\Documents\PrimeEDU'

for ext in ['*.html']:
    for f in glob.glob(os.path.join(src, ext)):
        if os.path.basename(f) == 'index.html':
            with open(f, 'r', encoding='utf-8') as file:
                text = file.read()
            
            old_register = '''                if(res.ok) {
                    showAlert("Registration successful. Please log in.");
                    switchView('view-login');
                    document.getElementById('login-phone').value = phone;
                    hideLoad();
                } else {'''
            
            new_register = '''                if(res.ok) {
                    // Auto-login upon successful registration
                    try {
                        const loginRes = await fetch(window.API_BASE_URL + '/api/auth/login', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({ phone, password: pass })
                        });
                        const loginData = await loginRes.json();
                        if(loginRes.ok) {
                            localStorage.setItem('primeedu_token', loginData.token);
                            localStorage.setItem('primeedu_leaderboard_name', loginData.name);
                            window.location.href = 'dashboard.html';
                        } else {
                            switchView('view-login');
                            document.getElementById('login-phone').value = phone;
                            hideLoad();
                        }
                    } catch(e) {
                        switchView('view-login');
                        document.getElementById('login-phone').value = phone;
                        hideLoad();
                    }
                } else {'''
                
            text = text.replace(old_register, new_register)
            with open(f, 'w', encoding='utf-8') as file:
                file.write(text)
            print('Modified handleRegister in index.html')

import shutil
dest_public = r'c:\Users\HI\Desktop\PrimeEDU\public'
for ext in ['*.html']:
    for f in glob.glob(os.path.join(src, ext)):
        shutil.copy2(f, dest_public)
print('Mirrored to public')
