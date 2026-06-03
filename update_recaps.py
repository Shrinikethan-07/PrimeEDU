import os, glob

src = r'c:\Users\HI\Documents\PrimeEDU'

for f in glob.glob(os.path.join(src, 'recaps.html')):
    with open(f, 'r', encoding='utf-8') as file:
        text = file.read()
        
    old_init = '''        // ═══ INIT RECAPS ═══
        async function initRecaps() {
            let accountAgeDays = 0;
            try {
                const pRes = await fetch(window.API_BASE_URL + '/api/user/profile');
                const profile = await pRes.json();
                accountAgeDays = profile.account_age_days || 0;
            } catch(e) {}

            function applyLockOverlay(gridId, requiredDays) {
                const grid = document.getElementById(gridId);
                grid.style.position = 'relative';
                // Frosted glass overlay
                const overlay = document.createElement('div');
                overlay.style.cssText = `
                    position: absolute; top: 0; left: 0; right: 0; bottom: 0;
                    background: rgba(13, 4, 26, 0.65);
                    backdrop-filter: blur(8px);
                    -webkit-backdrop-filter: blur(8px);
                    z-index: 100;
                    display: flex; flex-direction: column; align-items: center; justify-content: center;
                    border-radius: 20px; text-align: center;
                `;
                overlay.innerHTML = `
                    <i class="fas fa-lock" style="font-size: 3rem; color: rgba(255,255,255,0.8); margin-bottom: 1rem; text-shadow: 0 0 15px rgba(255,255,255,0.4);"></i>
                    <h3 style="color: white; font-family: var(--font-heading); font-size: 1.2rem; letter-spacing: 2px;">LOCKED UNTIL DAY ${requiredDays}</h3>
                    <p style="color: var(--neon-cyan); font-size: 0.85rem; margin-top: 0.5rem; font-weight: 600;">You are on Day ${accountAgeDays}. Keep grinding.</p>
                `;
                grid.appendChild(overlay);
                
                // Disable pointer events on the cards underneath
                Array.from(grid.children).forEach(child => {
                    if (child !== overlay) {
                        child.style.pointerEvents = 'none';
                        child.style.userSelect = 'none';
                    }
                });
            }

            try {
                const response = await fetch(window.API_BASE_URL + '/api/recap/dynamic');
                const dynamicData = await response.json();

                // Weekly Data
                const weeklyData = [
                    { title: "Weekly Grit", content: dynamicData.reason || 'No data', type: 'chart', image: dynamicData.image || 'consistency_v2.png' },
                    { title: "Dragon Balls", statValue: dynamicData.highlight_stat || '0', statLabel: dynamicData.label || 'EARNED', type: 'stat' }
                ];
                const weeklyGrid = document.getElementById('weekly-grid');
                weeklyData.forEach((d, i) => weeklyGrid.appendChild(createPoster(d, i)));
                if(accountAgeDays < 7) applyLockOverlay('weekly-grid', 7);

                // Monthly Data
                const monthlyData = [
                    { title: "Identity", html: `<div style="font-size:0.85rem;color:var(--neon-purple);font-family:var(--font-heading);border:1px solid var(--neon-purple);padding:0.4rem 0.8rem;border-radius:8px;margin-bottom:0.75rem;">THE ALCHEMIST</div><p style="font-size:0.8rem;">Surgical Precision.</p><div style="background-image:url('https://i.pinimg.com/736x/97/4a/5b/974a5b6a4e8b3c2d1f0e9a8b7c6d5e4f.jpg');height:90px;background-size:cover;background-position:center;border-radius:12px;width:100%;"></div>` },
                    { title: "Consistency", content: "28 Day Streak. Unstoppable.", type: 'chart', image: 'consistency_v2.png' },
                    { title: "Knowledge", content: "3 Chapters Decoded.", type: 'chart', image: 'focus_bars.png' },
                    { title: "Focus Master", statValue: "154", statLabel: "HOURS", type: 'stat' }
                ];
                const monthlyGrid = document.getElementById('monthly-grid');
                monthlyData.forEach((d, i) => monthlyGrid.appendChild(createPoster(d, i)));
                if(accountAgeDays < 30) applyLockOverlay('monthly-grid', 30);

                // Yearly Data
                const yearlyData = [
                    { title: "Legacy", content: "Master of Deep Work.", type: 'chart', image: 'consistency_graph.png' },
                    { title: "Chronos", statValue: "8,400", statLabel: "MINUTES", type: 'stat' },
                    { title: "Growth Mindset", content: "Peak Form.", type: 'chart', image: 'focus_bars.png' },
                    { title: "The Scroll", statValue: "154", statLabel: "ENTRIES", type: 'stat' },
                    { title: "Final Form", html: `<div style="color:#ff00ea;font-family:var(--font-heading);border:1px solid #ff00ea;padding:0.4rem 0.8rem;border-radius:8px;font-size:0.8rem;margin-bottom:0.75rem;">ASCENDED WARRIOR</div><div style="background-image:url('https://i.pinimg.com/736x/4e/40/87/4e4087e01177d1c3ea5e7143e7284f9e.jpg');height:90px;background-size:cover;background-position:center;border-radius:12px;width:100%;"></div>` },
                    { title: "Prime Rating", statValue: "9.8", statLabel: "TIER S+", type: 'stat' }
                ];
                const yearlyGrid = document.getElementById('yearly-grid');
                yearlyData.forEach((d, i) => yearlyGrid.appendChild(createPoster(d, i)));
                if(accountAgeDays < 365) applyLockOverlay('yearly-grid', 365);

            } catch (e) {
                console.error("Failed to load recaps", e);
            }
        }'''
        
    new_init = '''        // ═══ INIT RECAPS ═══
        async function initRecaps() {
            let accountAgeDays = 1;
            try {
                // We add token to headers just in case it's needed by the backend
                const token = localStorage.getItem('primeedu_token');
                const pRes = await fetch(window.API_BASE_URL + '/api/user/profile', {
                    headers: { 'Authorization': 'Bearer ' + token }
                });
                const profile = await pRes.json();
                accountAgeDays = profile.account_age_days || 1;
            } catch(e) {}

            function applyLockOverlay(gridId, requiredDays, periodName) {
                const grid = document.getElementById(gridId);
                grid.style.position = 'relative';
                
                // If the user hasn't reached the required days, we completely hide the cards and show a premium lock card
                grid.innerHTML = ''; // Clear empty space or fake cards
                grid.style.gridTemplateColumns = '1fr'; // Make it take full width
                
                const daysLeft = requiredDays - accountAgeDays;
                const lockCard = document.createElement('div');
                lockCard.style.cssText = `
                    background: linear-gradient(135deg, #121212 0%, #1f1f1f 100%);
                    border: 1px solid #333;
                    border-radius: 20px;
                    padding: 3rem 2rem;
                    text-align: center;
                    box-shadow: inset 0 0 40px rgba(0,0,0,0.5), 0 10px 30px rgba(0,0,0,0.6);
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                    justify-content: center;
                    position: relative;
                    overflow: hidden;
                `;
                
                lockCard.innerHTML = `
                    <div style="position: absolute; top: 0; left: 0; right: 0; height: 3px; background: linear-gradient(90deg, transparent, #555, transparent);"></div>
                    <i class="fas fa-lock" style="font-size: 3.5rem; color: #666; margin-bottom: 1.5rem; text-shadow: 0 4px 10px rgba(0,0,0,0.5);"></i>
                    <h3 style="color: #eee; font-family: var(--font-heading); font-size: 1.4rem; letter-spacing: 2px; text-transform: uppercase;">${periodName} Locked</h3>
                    <p style="color: #999; font-size: 0.95rem; margin-top: 0.5rem;">You are currently on <strong>Day ${accountAgeDays}</strong>.</p>
                    <div style="margin-top: 1.5rem; background: rgba(0,0,0,0.4); border: 1px solid #222; padding: 0.8rem 1.5rem; border-radius: 12px;">
                        <span style="color: #ccc; font-size: 0.9rem;">Wait <strong style="color: white; font-size: 1.1rem;">${daysLeft}</strong> more days to unlock.</span>
                    </div>
                `;
                
                grid.appendChild(lockCard);
            }

            let dynamicData = {};
            try {
                const response = await fetch(window.API_BASE_URL + '/api/recap/dynamic');
                if (response.ok) {
                    dynamicData = await response.json();
                }
            } catch (e) {
                console.error("Failed to load dynamic data, using fallbacks", e);
            }

            // Weekly Data
            const weeklyGrid = document.getElementById('weekly-grid');
            if(accountAgeDays < 7) {
                applyLockOverlay('weekly-grid', 7, 'Weekly Insights');
            } else {
                const weeklyData = [
                    { title: "Weekly Grit", content: dynamicData.reason || 'You stayed disciplined and forged your mind daily.', type: 'chart', image: dynamicData.image || 'consistency_v2.png' },
                    { title: "Dragon Balls", statValue: dynamicData.highlight_stat || '150', statLabel: dynamicData.label || 'EARNED', type: 'stat' }
                ];
                weeklyData.forEach((d, i) => weeklyGrid.appendChild(createPoster(d, i)));
            }

            // Monthly Data
            const monthlyGrid = document.getElementById('monthly-grid');
            if(accountAgeDays < 30) {
                applyLockOverlay('monthly-grid', 30, 'Monthly Mastery');
            } else {
                const monthlyData = [
                    { title: "Identity", html: `<div style="font-size:0.85rem;color:var(--neon-purple);font-family:var(--font-heading);border:1px solid var(--neon-purple);padding:0.4rem 0.8rem;border-radius:8px;margin-bottom:0.75rem;">THE ALCHEMIST</div><p style="font-size:0.8rem;">Surgical Precision.</p><div style="background-image:url('https://i.pinimg.com/736x/97/4a/5b/974a5b6a4e8b3c2d1f0e9a8b7c6d5e4f.jpg');height:90px;background-size:cover;background-position:center;border-radius:12px;width:100%;"></div>` },
                    { title: "Consistency", content: "28 Day Streak. Unstoppable.", type: 'chart', image: 'consistency_v2.png' },
                    { title: "Knowledge", content: "3 Chapters Decoded.", type: 'chart', image: 'focus_bars.png' },
                    { title: "Focus Master", statValue: "154", statLabel: "HOURS", type: 'stat' }
                ];
                monthlyData.forEach((d, i) => monthlyGrid.appendChild(createPoster(d, i)));
            }

            // Yearly Data
            const yearlyGrid = document.getElementById('yearly-grid');
            if(accountAgeDays < 365) {
                applyLockOverlay('yearly-grid', 365, 'Yearly Legacy');
            } else {
                const yearlyData = [
                    { title: "Legacy", content: "Master of Deep Work.", type: 'chart', image: 'consistency_graph.png' },
                    { title: "Chronos", statValue: "8,400", statLabel: "MINUTES", type: 'stat' },
                    { title: "Growth Mindset", content: "Peak Form.", type: 'chart', image: 'focus_bars.png' },
                    { title: "The Scroll", statValue: "154", statLabel: "ENTRIES", type: 'stat' },
                    { title: "Final Form", html: `<div style="color:#ff00ea;font-family:var(--font-heading);border:1px solid #ff00ea;padding:0.4rem 0.8rem;border-radius:8px;font-size:0.8rem;margin-bottom:0.75rem;">ASCENDED WARRIOR</div><div style="background-image:url('https://i.pinimg.com/736x/4e/40/87/4e4087e01177d1c3ea5e7143e7284f9e.jpg');height:90px;background-size:cover;background-position:center;border-radius:12px;width:100%;"></div>` },
                    { title: "Prime Rating", statValue: "9.8", statLabel: "TIER S+", type: 'stat' }
                ];
                yearlyData.forEach((d, i) => yearlyGrid.appendChild(createPoster(d, i)));
            }
        }'''
        
    text = text.replace(old_init, new_init)
    
    with open(f, 'w', encoding='utf-8') as file:
        file.write(text)
    print('Updated recaps UI')

import shutil
dest_public = r'c:\Users\HI\Desktop\PrimeEDU\public'
shutil.copy2(os.path.join(src, 'recaps.html'), dest_public)
print('Mirrored recaps to public')
