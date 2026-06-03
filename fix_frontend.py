import os
import glob
import re

directories = [
    r'c:\Users\HI\Documents\PrimeEDU',
    r'c:\Users\HI\Desktop\PrimeEDU\public'
]

api_injection = '''<script>
    window.API_BASE_URL = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1' ? '' : 'https://primeedu.onrender.com';
</script>'''

admin_link = '''<li class="nav-item admin-only-link" style="display: none;">
                    <a href="admin.html" class="nav-link" style="color: #ff3366;">
                        <i class="fas fa-user-shield"></i><span>Admin</span>
                    </a>
                </li>
            </ul>'''

admin_visibility_js = '''<script>
    // Reveal admin link if user is admin
    const _me = localStorage.getItem('primeedu_leaderboard_name') || localStorage.getItem('primeedu_name') || '';
    if(_me.toLowerCase() === 'admin') {
        const adminLinks = document.querySelectorAll('.admin-only-link');
        adminLinks.forEach(link => link.style.display = 'flex');
    }
</script>'''

for d in directories:
    for filepath in glob.glob(os.path.join(d, '*.html')):
        with open(filepath, 'r', encoding='utf-8') as f:
            text = f.read()
        
        changed = False
        
        # Inject API base URL if missing
        if 'window.API_BASE_URL =' not in text:
            text = text.replace('</head>', api_injection + '\n</head>')
            changed = True
            
        # Inject Admin link if missing
        if 'admin.html' not in text and '<ul class="nav-links">' in text:
            text = text.replace('</ul>', admin_link)
            text = text.replace('</body>', admin_visibility_js + '\n</body>')
            changed = True
            
        if changed:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(text)
            print(f'Updated {filepath}')
