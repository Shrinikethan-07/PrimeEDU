import os
import glob

directories = [
    r'c:\Users\HI\Documents\PrimeEDU',
    r'c:\Users\HI\Desktop\PrimeEDU\public'
]

old_js = '''const _me = (localStorage.getItem('primeedu_leaderboard_name') || localStorage.getItem('primeedu_name') || '').trim().toLowerCase();
    const _email = (localStorage.getItem('primeedu_email') || '').trim().toLowerCase();
    if(_me === 'shrinikethan m s' && _email === 'buvanavel.m01@gmail.com') {'''

new_js = '''const _me = (localStorage.getItem('primeedu_leaderboard_name') || localStorage.getItem('primeedu_name') || '').trim().toLowerCase();
    const _email = (localStorage.getItem('primeedu_email') || '').trim().toLowerCase();
    if(_email === 'buvanavel.m01@gmail.com') {'''

for d in directories:
    for filepath in glob.glob(os.path.join(d, '*.html')):
        with open(filepath, 'r', encoding='utf-8') as f:
            text = f.read()
        
        if old_js in text:
            text = text.replace(old_js, new_js)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(text)

print("Simplified frontend admin visibility check to only require email!")
