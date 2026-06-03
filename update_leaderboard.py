import os
import re

file_path = r'c:\Users\HI\Documents\PrimeEDU\leaderboard.html'

with open(file_path, 'r', encoding='utf-8') as f:
    text = f.read()

# Replace podium
podium_pattern = r'<div class="lb-podium">.*?</div>\s*<!-- WARRIOR LIST ranks 4-10 -->'
new_podium = '''<div class="lb-podium" id="dynamic-podium">
                    <!-- Dynamic Podium -->
                </div>

                <!-- WARRIOR LIST ranks 4-10 -->'''
text = re.sub(podium_pattern, new_podium, text, flags=re.DOTALL)

# Replace list
list_pattern = r'<div class="warrior-list">.*?</div>\s*</div>\s*</main>'
new_list = '''<div class="warrior-list" id="dynamic-list">
                    <!-- Dynamic List -->
                </div>
            </div>
        </main>'''
text = re.sub(list_pattern, new_list, text, flags=re.DOTALL)

# Add share button to header
header_pattern = r'<div class="header-left">.*?</div>\s*</header>'
new_header = '''<div class="header-left">
                    <h1><i class="fas fa-trophy" style="color:#ffd700;"></i> Royal Leaderboard</h1>
                    <p class="text-secondary">Champions of Consistency — forged through daily discipline</p>
                </div>
                <div class="header-right">
                    <button class="neon-btn" onclick="shareLeaderboard()" style="padding: 0.6rem 1.2rem; font-size: 0.85rem;">
                        <i class="fas fa-share-alt"></i> Share Rank
                    </button>
                </div>
            </header>'''
text = re.sub(header_pattern, new_header, text, flags=re.DOTALL)

# Inject JS for leaderboard
js_injection = '''
        async function loadLeaderboard() {
            try {
                const res = await fetch(window.API_BASE_URL + '/api/leaderboard');
                const users = await res.json();
                
                const podiumDiv = document.getElementById('dynamic-podium');
                const listDiv = document.getElementById('dynamic-list');
                
                const myName = localStorage.getItem('primeedu_leaderboard_name') || '';
                
                // Podium HTML Builder
                function getPodiumCard(u, rank) {
                    if (!u) return '';
                    let char = CHARACTERS.find(c => c.id === u.avatar) || CHARACTERS[0];
                    let crown = rank === 1 ? '<div class="crown-icon"><i class="fas fa-crown"></i></div>' : '';
                    return `
                    <div class="podium-card rank-${rank}">
                        ${crown}
                        <div class="podium-rank-badge">${rank}</div>
                        <img src="${char.img}" alt="${char.name}" class="podium-avatar" onerror="this.src='${char.fallback}'">
                        <div class="podium-name">${u.name}</div>
                        <div class="podium-score">${(u.balls || 0).toLocaleString()}</div>
                        <div class="podium-sub">Dragon Balls</div>
                    </div>`;
                }

                // Render Podium (Order: 2, 1, 3)
                let podiumHtml = '';
                if (users[1]) podiumHtml += getPodiumCard(users[1], 2);
                if (users[0]) podiumHtml += getPodiumCard(users[0], 1);
                if (users[2]) podiumHtml += getPodiumCard(users[2], 3);
                podiumDiv.innerHTML = podiumHtml;

                // Render List
                let listHtml = '';
                for (let i = 3; i < users.length; i++) {
                    let u = users[i];
                    let char = CHARACTERS.find(c => c.id === u.avatar) || CHARACTERS[0];
                    let isMe = (u.name === myName) ? 'is-user' : '';
                    let nameDisplay = isMe ? `<span id="user-lb-name">${u.name}</span> <i class="fas fa-edit" style="cursor:pointer; font-size: 0.8rem; opacity:0.7;" onclick="editHandle()" title="Edit Handle"></i>` : u.name;
                    
                    listHtml += `
                    <div class="warrior-row ${isMe}">
                        <div class="warrior-rank-num" style="color:${isMe ? 'var(--neon-cyan)' : '#a090c0'};">${i + 1}</div>
                        <img src="${char.img}" alt="${char.name}" class="warrior-avatar" style="${isMe ? 'border-color:var(--neon-cyan);' : ''}" onerror="this.src='${char.fallback}'">
                        <div class="warrior-info">
                            <div class="warrior-name" style="${isMe ? 'color:var(--neon-cyan); display:flex; align-items:center; gap:0.5rem;' : ''}">
                                ${nameDisplay}
                            </div>
                            <div class="warrior-discipline">Streak: ${u.streak} Days</div>
                        </div>
                        <div class="warrior-balls" style="${isMe ? 'color:var(--neon-cyan);' : ''}">${(u.balls || 0).toLocaleString()}<small>Dragon Balls</small></div>
                    </div>`;
                }
                listDiv.innerHTML = listHtml;
                
            } catch (e) {
                console.error("Leaderboard load failed", e);
            }
        }
        loadLeaderboard();

        function shareLeaderboard() {
            const text = "Check out my rank on the PrimeEDU Leaderboard! Only the most consistent warriors make it to the top. Can you beat me?";
            if (navigator.share) {
                navigator.share({
                    title: 'PrimeEDU Leaderboard',
                    text: text,
                    url: window.location.href
                });
            } else {
                navigator.clipboard.writeText(`${text} \\n${window.location.href}`);
                alert("Leaderboard link copied to clipboard! Share it with your friends.");
            }
        }
'''

text = text.replace('loadProfile();', 'loadProfile();\n' + js_injection)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(text)

print("Updated leaderboard.html")
