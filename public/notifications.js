// PrimeEDU Global Notification Manager
(function() {
    // 1. Ensure toast container exists
    function ensureToastContainer() {
        let container = document.getElementById('toast-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'toast-container';
            document.body.appendChild(container);
        }
        return container;
    }

    // 2. Request notification permission on first interaction
    function initBrowserNotifications() {
        if ("Notification" in window && Notification.permission === "default") {
            const askPerm = () => {
                Notification.requestPermission().then(permission => {
                    console.log("Notification permission:", permission);
                });
                document.removeEventListener('click', askPerm);
            };
            document.addEventListener('click', askPerm);
        }
    }

    // 3. Show premium toast notification
    window.showPremiumNotification = function(title, message, type = 'cyan') {
        const container = ensureToastContainer();
        const toast = document.createElement('div');
        toast.className = `premium-toast ${type}`;
        
        let iconClass = 'fa-info-circle';
        if (type === 'pink') iconClass = 'fa-skull-crossbones';
        if (type === 'green') iconClass = 'fa-trophy';
        
        toast.innerHTML = `
            <i class="fas ${iconClass} premium-toast-icon"></i>
            <div class="premium-toast-content">
                <div class="premium-toast-title">${title}</div>
                <div class="premium-toast-msg">${message}</div>
            </div>
        `;
        
        container.appendChild(toast);
        
        // Trigger reflow to animate
        toast.offsetHeight;
        toast.classList.add('active');
        
        // Play notification sound
        playNotificationSound(type);

        // Native push notification if page is hidden
        if (document.hidden && "Notification" in window && Notification.permission === "granted") {
            try {
                new Notification(title, {
                    body: message,
                    icon: 'assets/avatars/itachi.webp'
                });
            } catch (e) {
                console.error("Failed to send native notification", e);
            }
        }
        
        // Auto remove after 5s
        setTimeout(() => {
            toast.classList.remove('active');
            setTimeout(() => toast.remove(), 400);
        }, 5000);
    };

    // Synthesized sound effects using Web Audio API
    let audioCtx = null;
    function playNotificationSound(type) {
        try {
            if (!audioCtx) {
                audioCtx = new (window.AudioContext || window.webkitAudioContext)();
            }
            if (audioCtx.state === 'suspended') {
                audioCtx.resume();
            }
            
            const osc = audioCtx.createOscillator();
            const gainNode = audioCtx.createGain();
            osc.connect(gainNode);
            gainNode.connect(audioCtx.destination);
            
            const now = audioCtx.currentTime;
            
            if (type === 'green') {
                // Victory fan-fare chime
                osc.type = 'triangle';
                osc.frequency.setValueAtTime(523.25, now); // C5
                osc.frequency.exponentialRampToValueAtTime(783.99, now + 0.15); // G5
                osc.frequency.exponentialRampToValueAtTime(1046.50, now + 0.3); // C6
                gainNode.gain.setValueAtTime(0.15, now);
                gainNode.gain.exponentialRampToValueAtTime(0.01, now + 0.4);
                osc.start(now);
                osc.stop(now + 0.4);
            } else if (type === 'pink') {
                // Warning chime
                osc.type = 'sawtooth';
                osc.frequency.setValueAtTime(440, now); // A4
                osc.frequency.setValueAtTime(392, now + 0.1); // G4
                gainNode.gain.setValueAtTime(0.12, now);
                gainNode.gain.exponentialRampToValueAtTime(0.01, now + 0.3);
                osc.start(now);
                osc.stop(now + 0.3);
            } else {
                // Info chime
                osc.type = 'sine';
                osc.frequency.setValueAtTime(587.33, now); // D5
                osc.frequency.exponentialRampToValueAtTime(880, now + 0.15); // A5
                gainNode.gain.setValueAtTime(0.15, now);
                gainNode.gain.exponentialRampToValueAtTime(0.01, now + 0.25);
                osc.start(now);
                osc.stop(now + 0.25);
            }
        } catch (e) {
            console.error("Audio failed", e);
        }
    }

    // 4. Background polling for challenges
    let knownChallenges = null; // Seed on first successful fetch
    
    async function pollChallenges() {
        const token = localStorage.getItem('primeedu_token');
        if (!token) return; // Not logged in
        
        try {
            const apiBase = window.API_BASE_URL || '';
            const res = await fetch(apiBase + '/api/clan/info');
            if (!res.ok) return;
            
            const data = await res.json();
            if (data.status !== 'success' || !data.challenges) return;
            
            const challenges = data.challenges;
            const myEmail = (localStorage.getItem('primeedu_email') || '').trim().toLowerCase();
            
            if (knownChallenges === null) {
                // First poll: seed
                knownChallenges = {};
                challenges.forEach(ch => {
                    knownChallenges[ch.id] = ch.status;
                });
                return;
            }
            
            // Check for updates
            challenges.forEach(ch => {
                const prevStatus = knownChallenges[ch.id];
                
                if (prevStatus === undefined) {
                    // New challenge!
                    knownChallenges[ch.id] = ch.status;
                    
                    // Don't notify if we created it
                    if (ch.creator_email.toLowerCase() !== myEmail) {
                        window.showPremiumNotification(
                            "New Arena Duel",
                            `${ch.creator_name} issued: "${ch.title}" (${ch.duration_minutes}m)`,
                            "pink"
                        );
                    }
                } else if (prevStatus !== ch.status) {
                    // Status changed!
                    knownChallenges[ch.id] = ch.status;
                    
                    const isCreator = ch.creator_email.toLowerCase() === myEmail;
                    const isAcceptor = ch.accepted_members && ch.accepted_members.some(m => m.email.toLowerCase() === myEmail);
                    const isParticipant = isCreator || isAcceptor;
                    
                    if (isParticipant) {
                        if (ch.status === 'active') {
                            window.showPremiumNotification(
                                "Duel Started!",
                                `Your focus duel "${ch.title}" is active. Go to the Clan Arena!`,
                                "cyan"
                            );
                        } else if (ch.status === 'completed') {
                            window.showPremiumNotification(
                                "Duel Completed!",
                                `Focus duel "${ch.title}" finished. 50 Dragon Balls awarded!`,
                                "green"
                            );
                        }
                    }
                }
            });
            
            // Clean up deleted challenges from local cache
            const currentIds = new Set(challenges.map(ch => ch.id));
            Object.keys(knownChallenges).forEach(id => {
                if (!currentIds.has(id)) {
                    delete knownChallenges[id];
                }
            });
            
        } catch (e) {
            console.error("Poll challenges error:", e);
        }
    }

    // 5. Background focus timer monitoring
    let timerFinishedNotified = {}; // track notified session IDs to avoid duplicate alerts

    function checkBackgroundTimer() {
        const saved = localStorage.getItem('primeedu_timer_state');
        if (!saved) return;
        try {
            const state = JSON.parse(saved);
            // Only handle countdown timers (Pomodoro or Custom), stopwatch has no targetEndTime
            if (state.isRunning && state.mode !== 'stopwatch' && state.targetEndTime && state.currentSessionId) {
                const remaining = Math.round((state.targetEndTime - Date.now()) / 1000);
                if (remaining <= 0 && !timerFinishedNotified[state.currentSessionId]) {
                    timerFinishedNotified[state.currentSessionId] = true;
                    
                    // Show premium notification (both browser native notification and glassmorphic toast)
                    window.showPremiumNotification(
                        "Session Completed!", 
                        `Excellent work! You finished your study focus on ${state.currentSubject || 'your subject'}.`, 
                        "green"
                    );
                    
                    // Update the state so that returning to timer.html opens the save modal
                    state.isRunning = false;
                    state.isSaveModalOpen = true;
                    state.seconds = 0;
                    localStorage.setItem('primeedu_timer_state', JSON.stringify(state));
                }
            }
        } catch (e) {
            console.error("Error monitoring background timer:", e);
        }
    }

    // 6. Active time tracking heartbeat
    let lastHeartbeat = 0;
    async function sendActivityHeartbeat() {
        const token = localStorage.getItem('primeedu_token');
        if (!token) return; // Not logged in
        
        // Skip if page is hidden
        if (document.hidden) return;
        
        const now = Date.now();
        if (now - lastHeartbeat >= 55000) {
            lastHeartbeat = now;
            try {
                const apiBase = window.API_BASE_URL || '';
                await fetch(apiBase + '/api/user/active_time_heartbeat', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': 'Bearer ' + token
                    },
                    body: JSON.stringify({
                        timestamp: new Date().toISOString(),
                        page: window.location.pathname
                    })
                });
            } catch (e) {
                console.error("Heartbeat failed", e);
            }
        }
    }

    // Initialize
    document.addEventListener('DOMContentLoaded', () => {
        ensureToastContainer();
        initBrowserNotifications();
        
        // Start polling if we are logged in, run every 15 seconds
        setInterval(pollChallenges, 15000);
        // Initial delay to avoid duplicate on-load fetch collisions
        setTimeout(pollChallenges, 3000);
        
        // Monitor timer state every second in the background of all tabs
        setInterval(checkBackgroundTimer, 1000);

        // Heartbeat active time tracking
        setInterval(sendActivityHeartbeat, 60000);
        setTimeout(sendActivityHeartbeat, 2000);
    });
})();
