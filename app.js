document.addEventListener('DOMContentLoaded', () => {
    function safeParse(key, defaultVal) {
        try {
            const item = localStorage.getItem(key);
            if (!item || item === 'undefined') return defaultVal;
            return JSON.parse(item);
        } catch(e) {
            console.error('Storage parse error for', key, e);
            return defaultVal;
        }
    }

    // --- AUTH INTERCEPTOR ---
    const originalFetch = window.fetch;
    window.fetch = async (...args) => {
        let [resource, config] = args;
        config = config || {};
        config.headers = config.headers || {};
        
        const token = localStorage.getItem('primeedu_token');
        if (token) {
            config.headers['Authorization'] = `Bearer ${token}`;
        }
        
        const response = await originalFetch(resource, config);
        
        if (response.status === 401 && !window.location.pathname.endsWith('index.html')) {
            window.location.href = 'index.html';
        }
        
        return response;
    };

    // Custom Alert Modal Function
    window.customAlert = function(title, message) {
        return new Promise((resolve) => {
            const modal = document.getElementById('custom-alert-modal');
            if (!modal) {
                alert(message);
                resolve();
                return;
            }
            document.getElementById('custom-alert-title').innerText = title;
            document.getElementById('custom-alert-msg').innerText = message;
            modal.classList.add('active');
            
            const closeBtn = document.getElementById('custom-alert-close');
            const handler = () => {
                modal.classList.remove('active');
                closeBtn.removeEventListener('click', handler);
                resolve();
            };
            closeBtn.addEventListener('click', handler);
        });
    };

    // Custom Input Modal Function
    window.customPrompt = function(title, desc, placeholder = '') {
        return new Promise((resolve) => {
            const modal = document.getElementById('custom-input-modal');
            if (!modal) {
                const res = prompt(desc, placeholder);
                resolve(res);
                return;
            }
            document.getElementById('custom-input-title').innerText = title;
            document.getElementById('custom-input-desc').innerText = desc;
            const inputField = document.getElementById('custom-input-field');
            inputField.placeholder = placeholder;
            inputField.value = placeholder;
            modal.classList.add('active');
            
            const submitBtn = document.getElementById('custom-input-submit');
            const cancelBtn = document.getElementById('custom-input-cancel');
            
            const cleanUp = () => {
                modal.classList.remove('active');
                submitBtn.removeEventListener('click', submitHandler);
                cancelBtn.removeEventListener('click', cancelHandler);
            };
            
            const submitHandler = () => {
                const val = inputField.value;
                cleanUp();
                resolve(val);
            };
            
            const cancelHandler = () => {
                cleanUp();
                resolve(null);
            };
            
            submitBtn.addEventListener('click', submitHandler);
            cancelBtn.addEventListener('click', cancelHandler);
        });
    };

    // Override default alert
    window.alert = function(msg) {
        window.customAlert("System Alert", msg);
    };

    let progressData = safeParse('primeedu_progress_v3', {});


    // ═══════════════ ANIME CHARACTERS & AVATARS ═══════════════
    // Local WebP images (itachi, goku, gojo) are from assets/avatars/*.webp
    // Others use reliable CDN URLs
    const CHARACTERS = [
        { id: 'itachi', name: 'Itachi', img: 'assets/avatars/itachi.webp', fallback: 'https://i.pinimg.com/736x/4e/40/87/4e4087e01177d1c3ea5e7143e7284f9e.jpg' },
        { id: 'goku', name: 'Goku', img: 'assets/avatars/goku.webp', fallback: 'https://i.pinimg.com/736x/c4/11/c9/c411c9e40e6f4b3d6e2a1f0c5b8a7d2e.jpg' },
        { id: 'gojo', name: 'Gojo', img: 'assets/avatars/gojo.webp', fallback: 'https://i.pinimg.com/736x/97/4a/5b/974a5b6a4e8b3c2d1f0e9a8b7c6d5e4f.jpg' },
        { id: 'sasuke', name: 'Sasuke', img: 'assets/avatars/sasuke.webp', fallback: 'https://i.pinimg.com/736x/4e/40/87/4e4087e01177d1c3ea5e7143e7284f9e.jpg' },
        { id: 'naruto', name: 'Naruto', img: 'assets/avatars/naruto.webp', fallback: 'https://i.pinimg.com/736x/d0/b5/3b/d0b53bc5ddd3b25c55ea471fa30c64d0.jpg' },
        { id: 'kakashi', name: 'Kakashi', img: 'assets/avatars/kakashi.webp', fallback: 'https://i.pinimg.com/736x/2b/3c/4d/2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e.jpg' },
    ];

    const DEFAULT_AVATAR = 'assets/avatars/itachi.webp';

    function getSelectedChar() {
        const id = localStorage.getItem('primeedu_avatar') || 'itachi';
        return CHARACTERS.find(c => c.id === id) || CHARACTERS[0];
    }

    // ─── Apply avatar to every .avatar-circle on the page ───
    function applyAvatar(char) {
        const src = char.img;
        document.querySelectorAll('.avatar-circle, #header-avatar').forEach(img => {
            img.src = src;
            img.alt = char.name;
            img.onerror = () => { img.src = char.fallback || DEFAULT_AVATAR; };
        });
        // Also set a CSS variable so CSS-only elements can use it
        document.documentElement.style.setProperty('--current-avatar', `url('${src}')`);
    }

    // ─── Persist avatar to backend so all pages stay in sync ───
    async function persistAvatar(charId) {
        localStorage.setItem('primeedu_avatar', charId);
        try {
            await fetch(window.API_BASE_URL + '/api/user/avatar', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ avatar: charId })
            });
        } catch (e) { /* offline, localStorage already set */ }
    }

    // ─── On boot: prefer localStorage (instant), then confirm from backend ───
    async function initAvatar() {
        applyAvatar(getSelectedChar());
        try {
            const res = await fetch(window.API_BASE_URL + '/api/user/avatar');
            if (res.ok) {
                const { avatar } = await res.json();
                if (avatar && avatar !== localStorage.getItem('primeedu_avatar')) {
                    localStorage.setItem('primeedu_avatar', avatar);
                    applyAvatar(getSelectedChar());
                }
            }
        } catch (e) { /* offline, use localStorage */ }
    }

    // Cache frequent DOM elements
    const dom = {
        avatarCircles: document.querySelectorAll('.avatar-circle, #header-avatar, .sidebar .avatar-circle'),
        minorTasksList: document.getElementById('minor-tasks-list'),
        dreamInput: document.getElementById('dream-input'),
        ballCount: document.getElementById('ball-count'),
        taskInput: document.getElementById('task-input'),
        focusToggle: document.getElementById('focus-toggle'),
        focusOverlay: document.getElementById('focus-timer-overlay'),
        focusTimerDisplay: document.getElementById('minor-timer-display')
    };

    // ─── updateAllAvatars is now an alias for applyAvatar ───
    function updateAllAvatars() { applyAvatar(getSelectedChar()); }

    const charGrid = document.getElementById('char-grid');
    if (charGrid) {
        const fragment = document.createDocumentFragment();
        CHARACTERS.forEach(c => {
            const div = document.createElement('div');
            const isSelected = getSelectedChar().id === c.id;
            div.className = 'char-option' + (isSelected ? ' selected' : '');
            div.innerHTML = `
                <div class="char-img-wrapper">
                    <img src="${c.img}" alt="${c.name}" loading="lazy"
                         onerror="this.src='${c.fallback || DEFAULT_AVATAR}'">
                </div>
                <span>${c.name}</span>
            `;
            div.onclick = async () => {
                await persistAvatar(c.id);
                document.querySelectorAll('.char-option').forEach(el => el.classList.remove('selected'));
                div.classList.add('selected');
                applyAvatar(c);
            };
            fragment.appendChild(div);
        });
        charGrid.innerHTML = '';
        charGrid.appendChild(fragment);
    }

    window.openCharacterSelect = () => {
        const modal = document.getElementById('char-modal');
        if (modal) modal.style.display = 'flex';
    };

    // ═══════════════ QUOTE SLIDER (V4) ═══════════════
    const QUOTES = {
        consistency: [
            "Consistency is the art of showing up.",
            "Small steps every day yield massive results.",
            "The secret of your future is hidden in your daily routine."
        ],
        time: [
            "Time is the only currency you can't earn back.",
            "Lost time is never found again.",
            "Don't spend time, invest it."
        ],
        power: [
            "Thinking is the hardest work, which is why few engage in it.",
            "The mind is a powerful thing. When you fill it with positive thoughts, your life will start to change."
        ],
        curiosity: [
            "Stay hungry, stay curious.",
            "Asking 'why' is the beginning of wisdom."
        ]
    };

    let allQuotes = [];
    Object.values(QUOTES).forEach(cat => allQuotes = allQuotes.concat(cat));
    let quoteIdx = 0;

    function startQuoteSlider() {
        const quoteEl = document.getElementById('active-quote');
        if (!quoteEl) return;
        setInterval(() => {
            quoteIdx = (quoteIdx + 1) % allQuotes.length;
            quoteEl.style.opacity = '0';
            setTimeout(() => {
                quoteEl.innerText = `"${allQuotes[quoteIdx]}"`;
                quoteEl.style.opacity = '1';
            }, 500);
        }, 6000);
    }
    startQuoteSlider();

    // ═══════════════ GLOBAL CONFIRM MODAL ═══════════════
    let confirmCallback = null;
    window.showConfirm = (msg, callback) => {
        const modal = document.getElementById('confirm-modal');
        if(!modal) {
            if(confirm(msg)) callback();
            return;
        }
        document.getElementById('confirm-msg').innerText = msg;
        confirmCallback = callback;
        modal.style.display = 'flex';
    };
    
    window.closeConfirmModal = () => {
        document.getElementById('confirm-modal').style.display = 'none';
        confirmCallback = null;
    };
    
    setTimeout(() => {
        const confirmYesBtn = document.getElementById('confirm-yes-btn');
        if(confirmYesBtn) {
            confirmYesBtn.onclick = () => {
                if(confirmCallback) confirmCallback();
                closeConfirmModal();
            };
        }
    }, 500);

    // ─── Instant name load from localStorage (prevents flicker on tab switch) ───
    const storedName = localStorage.getItem('primeedu_leaderboard_name');
    const greetingEl = document.getElementById('user-greeting');
    if (greetingEl && storedName) {
        greetingEl.innerText = `Ascended Warrior ${storedName}`;
    }

    initAvatar(); // load from localStorage immediately, sync from backend in background

    // ═══════════════ FORGED DESTINY MATRIX ═══════════════
    window.saveDream = async (btn) => {
        const input = document.getElementById('dream-input');
        const deadlineInput = document.getElementById('dream-deadline');
        if (!input || !input.value.trim() || !deadlineInput.value) {
            alert("Please provide both a destiny and an absolute target time.");
            return;
        }
        
        const dream = input.value.trim();
        const deadline = new Date(deadlineInput.value).toISOString();

        // Visual feedback
        const originalText = btn.innerText;
        btn.innerText = "DESTINY FORGED";
        btn.disabled = true;
        btn.classList.add('vibrant-pulse');

        try {
            const res = await fetch(window.API_BASE_URL + '/api/user/profile', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ massive_goal: { title: dream, deadline: deadline } })
            });
            const data = await res.json();
            if (data.status === 'error') {
                alert(data.message);
                btn.innerText = originalText;
                btn.disabled = false;
            } else {
                input.value = '';
                deadlineInput.value = '';
                loadDestinies(); // reload
                setTimeout(() => { btn.innerText = originalText; btn.disabled = false; btn.classList.remove('vibrant-pulse'); }, 2000);
            }
        } catch (e) { 
            alert("Network error.");
            btn.innerText = originalText;
            btn.disabled = false;
        }
    };

    window.cancelDestiny = (index) => {
        showConfirm("Canceling a destiny early costs 5 Dragon Balls. Proceed?", async () => {
            try {
                const res = await fetch(window.API_BASE_URL + '/api/user/destiny/cancel', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ goal_index: index })
                });
                const data = await res.json();
                if (res.ok) {
                    if (data.balls !== undefined) updateDragonBalls(0); // Will reload from backend shortly anyway
                    loadDestinies();
                }
            } catch (e) { console.error(e); }
        });
    };

    let destinyInterval = null;
    async function loadDestinies() {
        const container = document.getElementById('active-destinies');
        if (!container) return;
        try {
            const res = await fetch(window.API_BASE_URL + '/api/user/profile');
            const user = await res.json();
            // Update UI elements while we have the profile
            if (user.balls !== undefined) document.getElementById('ball-count').innerText = user.balls.toLocaleString();
            if (user.streak !== undefined) document.querySelector('.user-stats .stat-card:first-child .stat-value').innerText = user.streak;
            if (user.leaderboard_name && document.getElementById('user-greeting')) {
                document.getElementById('user-greeting').innerText = `Ascended Warrior ${user.leaderboard_name}`;
            }
            
            // Hide the fullscreen loading screen
            const loadingScreen = document.getElementById('loading-screen');
            if (loadingScreen) {
                setTimeout(() => {
                    loadingScreen.style.opacity = '0';
                    loadingScreen.style.visibility = 'hidden';
                }, 1500);
            }
            
            const goals = user.massive_goals || [];
            if (goals.length === 0) {
                container.innerHTML = '<p style="color:#64748b; font-size:0.9rem; text-align:center; padding: 2rem;">No destinies forged yet.</p>';
                if (destinyInterval) { clearInterval(destinyInterval); destinyInterval = null; }
                return;
            }
            
            if (destinyInterval) { clearInterval(destinyInterval); }
            
            container.innerHTML = goals.map((g, i) => {
                const date = new Date(g.deadline);
                return `
                <div id="destiny-card-${i}" style="background: rgba(139, 92, 246, 0.1); border: 1px solid var(--synth-purple); border-radius: 12px; padding: 1rem; position: relative; transition: all 0.3s ease;">
                    <h3 style="color: white; font-size: 1.1rem; margin-bottom: 0.25rem;">${g.title}</h3>
                    <p style="color: var(--synth-pink); font-size: 0.8rem; margin-bottom: 0.25rem;"><i class="fas fa-clock"></i> Target: ${date.toLocaleString()}</p>
                    <p id="countdown-text-${i}" style="color: var(--neon-cyan); font-size: 0.85rem; font-weight: bold; margin-bottom: 0.5rem;"></p>
                    <div style="width: 100%; height: 120px; background: url('assets/vision_board.png') center/cover no-repeat; border-radius: 8px; margin-bottom: 0.5rem; border: 1px solid rgba(255,255,255,0.15); box-shadow: 0 4px 15px rgba(0,0,0,0.5);">
                    </div>
                    <button class="neon-btn" style="padding: 0.3rem 0.6rem; font-size: 0.7rem; border-color: #ff2a85; color: #ff2a85; width: 100%;" onclick="cancelDestiny(${i})">
                        <i class="fas fa-times"></i> CANCEL (COSTS 5 BALLS)
                    </button>
                </div>
                `;
            }).join('');
            
            const updateCountdowns = () => {
                goals.forEach((g, i) => {
                    const el = document.getElementById(`countdown-text-${i}`);
                    const card = document.getElementById(`destiny-card-${i}`);
                    if (!el || !card) return;
                    
                    const targetTime = new Date(g.deadline).getTime();
                    const now = Date.now();
                    const diff = targetTime - now;
                    
                    if (diff <= 0) {
                        el.innerHTML = `<span style="color: #ff0055; font-weight: 800; letter-spacing: 1px;">EXPIRED</span>`;
                        card.style.borderColor = '#ff0055';
                        card.style.boxShadow = '0 0 15px rgba(255, 0, 85, 0.2)';
                        
                        if (!card.dataset.expired) {
                            card.dataset.expired = 'true';
                            setTimeout(async () => {
                                try {
                                    const cancelRes = await fetch(window.API_BASE_URL + '/api/user/destiny/cancel', {
                                        method: 'POST',
                                        headers: { 'Content-Type': 'application/json' },
                                        body: JSON.stringify({ goal_index: i })
                                    });
                                    if (cancelRes.ok) {
                                        loadDestinies();
                                    }
                                } catch (err) {
                                    console.error(err);
                                }
                            }, 3000);
                        }
                    } else {
                        const days = Math.floor(diff / (1000 * 60 * 60 * 24));
                        const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
                        const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
                        const seconds = Math.floor((diff % (1000 * 60)) / 1000);
                        
                        if (days > 0) {
                            el.innerText = `Time Left: ${days}d ${hours}h ${minutes}m`;
                        } else {
                            el.innerText = `Time Left: ${hours}h ${minutes}m ${seconds}s`;
                        }
                    }
                });
            };
            
            updateCountdowns();
            destinyInterval = setInterval(updateCountdowns, 1000);
            
        } catch(e) {
            const loadingScreen = document.getElementById('loading-screen');
            if (loadingScreen) {
                loadingScreen.style.opacity = '0';
                loadingScreen.style.visibility = 'hidden';
            }
        }
    }
    loadDestinies();

    // ═══════════════ MANUAL MISSIONS (TASKS) ═══════════════
    let manualTasks = safeParse('primeedu_manual_tasks', []);

    window.addManualTask = () => {
        const text = dom.taskInput.value.trim();
        if (!text) return;
        const task = { id: Date.now(), text, completed: false };
        manualTasks.push(task);
        dom.taskInput.value = '';
        renderTasks();
        saveTasks();
    };

    window.toggleTask = (id) => {
        const task = manualTasks.find(t => t.id === id);
        if (task) {
            task.completed = !task.completed;
            if (task.completed) {
                playSlashAnimation(); // Restore Sasuke Slash
                if(typeof playTaskSound === 'function') playTaskSound();
                updateDragonBalls(10);
            }
            renderTasks();
            saveTasks();
        }
    };

    function renderTasks() {
        if (!dom.minorTasksList) return;
        dom.minorTasksList.innerHTML = manualTasks.map(t => `
            <div class="task-item ${t.completed ? 'completed' : ''}" onclick="toggleTask(${t.id})">
                <div class="custom-checkbox"></div>
                <span>${t.text}</span>
            </div>
        `).join('');
    }

    async function saveTasks() {
        localStorage.setItem('primeedu_manual_tasks', JSON.stringify(manualTasks));
        try {
            await fetch(window.API_BASE_URL + '/api/tasks/sync', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ tasks: manualTasks })
            });
        } catch (e) { }
    }
    renderTasks();

    // ═══════════════ FULL JEE SYLLABUS ACCORDION ═══════════════
    const JEE_SYLLABUS = [
        {
            subject: 'PHYSICS', color: '#00F3FF', icon: 'fa-atom',
            units: [
                { name: '1. Foundations & Kinematics (Cl.11)', topics: ['Physical World', 'Units & Measurements', 'Motion in Straight Line', 'Motion in Plane'] },
                { name: '2. Dynamics & Energy (Cl.11)', topics: ['Laws of Motion', 'Work, Energy & Power'] },
                { name: '3. Rotational & Gravitation (Cl.11)', topics: ['System of Particles & Rotational Motion', 'Gravitation'] },
                { name: '4. Properties of Matter (Cl.11)', topics: ['Mechanical Properties of Solids', 'Mechanical Properties of Fluids'] },
                { name: '5. Thermal Physics (Cl.11)', topics: ['Thermal Properties of Matter', 'Thermodynamics', 'Kinetic Theory'] },
                { name: '6. Oscillations & Waves (Cl.11)', topics: ['Oscillations', 'Waves'] },
                { name: '7. Electrostatics (Cl.12)', topics: ['Electric Charges & Fields', 'Electrostatic Potential & Capacitance'] },
                { name: '8. Current & Magnetism (Cl.12)', topics: ['Current Electricity', 'Moving Charges & Magnetism', 'Magnetism & Matter'] },
                { name: '9. EM Induction & AC (Cl.12)', topics: ['Electromagnetic Induction', 'Alternating Current'] },
                { name: '10. EM Waves (Cl.12)', topics: ['Electromagnetic Waves'] },
                { name: '11. Optics (Cl.12)', topics: ['Ray Optics & Optical Instruments', 'Wave Optics'] },
                { name: '12. Modern Physics (Cl.12)', topics: ['Dual Nature of Radiation & Matter', 'Atoms', 'Nuclei', 'Semiconductor Electronics', 'Communication Systems'] }
            ]
        },
        {
            subject: 'CHEMISTRY', color: '#9D00FF', icon: 'fa-flask',
            units: [
                { name: '1. Basic Concepts & Structure (Cl.11)', topics: ['Some Basic Concepts of Chemistry', 'Structure of Atom'] },
                { name: '2. Periodicity & Bonding (Cl.11)', topics: ['Classification of Elements & Periodicity', 'Chemical Bonding & Molecular Structure'] },
                { name: '3. States & Thermodynamics (Cl.11)', topics: ['States of Matter', 'Thermodynamics'] },
                { name: '4. Equilibrium & Redox (Cl.11)', topics: ['Equilibrium', 'Redox Reactions'] },
                { name: '5. Hydrogen & s-Block (Cl.11)', topics: ['Hydrogen', 's-Block Elements'] },
                { name: '6. p-Block & Organic Basics (Cl.11)', topics: ['p-Block Elements (Group 13)', 'Organic Chemistry: Basic Principles & Techniques'] },
                { name: '7. Hydrocarbons & Environment (Cl.11)', topics: ['Hydrocarbons', 'Environmental Chemistry'] },
                { name: '8. Solutions & Electrochemistry (Cl.12)', topics: ['Solutions', 'Electrochemistry'] },
                { name: '9. Kinetics & Surface Chemistry (Cl.12)', topics: ['Chemical Kinetics', 'Surface Chemistry'] },
                { name: '10. p-Block Elements (Cl.12)', topics: ['p-Block Elements (Groups 15–18)'] },
                { name: '11. d-f Block + Coordination (Cl.12)', topics: ['d- and f-Block Elements', 'Coordination Compounds'] },
                { name: '12. Haloalkanes & Alcohols (Cl.12)', topics: ['Haloalkanes & Haloarenes', 'Alcohols, Phenols & Ethers'] },
                { name: '13. Carbonyls & Amines (Cl.12)', topics: ['Aldehydes, Ketones & Carboxylic Acids', 'Amines'] },
                { name: '14. Biomolecules & Polymers (Cl.12)', topics: ['Biomolecules', 'Polymers', 'Chemistry in Everyday Life'] }
            ]
        },
        {
            subject: 'MATHEMATICS', color: '#FFCC00', icon: 'fa-square-root-variable',
            units: [
                { name: '1. Sets & Functions (Cl.11)', topics: ['Sets', 'Relations & Functions', 'Trigonometric Functions'] },
                { name: '2. Algebra Basics (Cl.11)', topics: ['Principle of Mathematical Induction', 'Complex Numbers & Quadratic Equations', 'Linear Inequalities'] },
                { name: '3. Permutation & Series (Cl.11)', topics: ['Permutations & Combinations', 'Binomial Theorem', 'Sequences & Series'] },
                { name: '4. Coordinate Geometry (Cl.11)', topics: ['Straight Lines', 'Conic Sections', 'Introduction to 3D Geometry'] },
                { name: '5. Calculus Intro (Cl.11)', topics: ['Limits & Derivatives'] },
                { name: '6. Stats & Probability (Cl.11)', topics: ['Mathematical Reasoning', 'Statistics', 'Probability'] },
                { name: '7. Relations & Functions (Cl.12)', topics: ['Relations & Functions', 'Inverse Trigonometric Functions'] },
                { name: '8. Algebra (Cl.12)', topics: ['Matrices', 'Determinants'] },
                { name: '9. Calculus I (Cl.12)', topics: ['Continuity & Differentiability', 'Application of Derivatives'] },
                { name: '10. Calculus II (Cl.12)', topics: ['Integrals', 'Application of Integrals'] },
                { name: '11. Differential Equations (Cl.12)', topics: ['Differential Equations'] },
                { name: '12. Vectors & 3D (Cl.12)', topics: ['Vector Algebra', 'Three-Dimensional Geometry'] },
                { name: '13. Probability & LP (Cl.12)', topics: ['Probability', 'Linear Programming'] }
            ]
        },
        {
            subject: 'BIOLOGY', color: '#00FFCC', icon: 'fa-dna',
            units: [
                { name: '1. Diversity in Living Organisms (Cl.11)', topics: ['Biological Classification', 'Plant Kingdom', 'Animal Kingdom'] },
                { name: '2. Structural Organization (Cl.11)', topics: ['Morphology of Flowering Plants', 'Structural Organization in Animals'] },
                { name: '3. Cell Biology (Cl.11)', topics: ['Cell: The Unit of Life', 'Biomolecules'] },
                { name: '4. Plant Physiology (Cl.11)', topics: ['Photosynthesis in Higher Plants', 'Respiration in Plants', 'Plant Growth & Development'] },
                { name: '5. Human Physiology (Cl.11)', topics: ['Digestion & Absorption', 'Breathing & Exchange of Gases', 'Body Fluids & Circulation', 'Excretory Products & Elimination', 'Locomotion & Movement', 'Neural Control & Coordination', 'Chemical Coordination & Integration'] },
                { name: '6. Reproduction (Cl.12)', topics: ['Reproduction in Organisms', 'Sexual Reproduction in Flowering Plants', 'Human Reproduction', 'Reproductive Health'] },
                { name: '7. Genetics & Evolution (Cl.12)', topics: ['Principles of Inheritance & Variation', 'Molecular Basis of Inheritance', 'Evolution'] },
                { name: '8. Ecology (Cl.12)', topics: ['Organisms & Populations', 'Ecosystem', 'Biodiversity & Conservation', 'Environmental Issues'] },
                { name: '9. Biotechnology (Cl.12)', topics: ['Biotechnology: Principles & Processes', 'Biotechnology & Its Applications'] }
            ]
        }
    ];

    function renderJeeSyllabus() {
        const container = document.getElementById('jee-syllabus-accordion');
        if (!container) return;

        const storedDone = safeParse('primeedu_jee_done', {});

        container.innerHTML = JEE_SYLLABUS.map((subj, si) => `
            <div class="jee-subject-group" id="jee-subj-${si}">
                <div class="jee-subject-header" onclick="toggleJeeSubject(${si})">
                    <span class="jee-subject-label" style="color:${subj.color};">
                        <i class="fas ${subj.icon}"></i> ${subj.subject}
                    </span>
                    <i class="fas fa-chevron-down jee-subject-toggle"></i>
                </div>
                <div class="jee-unit-list">
                    ${subj.units.map((unit, ui) => `
                        <div class="jee-unit" id="jee-unit-${si}-${ui}">
                            <div class="jee-unit-header" onclick="toggleJeeUnit(${si},${ui})">
                                <span>${unit.name}</span>
                                <i class="fas fa-chevron-right" style="font-size:0.55rem;transition:transform 0.2s;"></i>
                            </div>
                            <div class="jee-topic-list">
                                ${unit.topics.map((topic, ti) => {
                                    const key = `jee-${si}-${ui}-${ti}`;
                                    const done = storedDone[key] || false;
                                    return `<div class="jee-topic ${done ? 'done' : ''}" onclick="toggleJeeTopic(${si},${ui},${ti},this)">
                                        <div class="jee-topic-check"></div>
                                        <span>${topic}</span>
                                    </div>`;
                                }).join('')}
                            </div>
                        </div>
                    `).join('')}
                </div>
            </div>
        `).join('');
    }

    window.toggleJeeSubject = (si) => {
        const el = document.getElementById(`jee-subj-${si}`);
        if (el) el.classList.toggle('open');
    };

    window.toggleJeeUnit = (si, ui) => {
        const el = document.getElementById(`jee-unit-${si}-${ui}`);
        if (!el) return;
        el.classList.toggle('open');
        const chevron = el.querySelector('.jee-unit-header .fa-chevron-right');
        if (chevron) chevron.style.transform = el.classList.contains('open') ? 'rotate(90deg)' : '';
    };

    window.toggleJeeTopic = (si, ui, ti, el) => {
        const key = `jee-${si}-${ui}-${ti}`;
        const storedDone = safeParse('primeedu_jee_done', {});
        const newState = !storedDone[key];
        storedDone[key] = newState;
        localStorage.setItem('primeedu_jee_done', JSON.stringify(storedDone));
        el.classList.toggle('done', newState);
        if (newState) {
            playSlashAnimation();
            updateDragonBalls(5);
        }
    };

    renderJeeSyllabus();


    // ═══════════════ DRAGON BALL ECONOMY ═══════════════
    function updateDragonBalls(amt) {
        const el = document.getElementById('ball-count');
        if (!el) return;
        let count = parseInt(el.innerText.replace(/,/g, '')) || 0;
        count = Math.max(0, count + amt);
        el.innerText = count.toLocaleString();
        localStorage.setItem('primeedu_balls', count);
        
        // Trigger neon pulse flash animations
        if (amt > 0) {
            el.classList.remove('db-flash-positive', 'db-flash-negative');
            void el.offsetWidth;
            el.classList.add('db-flash-positive');
            if (window.playSwordSound) window.playSwordSound();
            setTimeout(() => el.classList.remove('db-flash-positive'), 600);
        } else if (amt < 0) {
            el.classList.remove('db-flash-positive', 'db-flash-negative');
            void el.offsetWidth;
            el.classList.add('db-flash-negative');
            if (window.playSwordSound) window.playSwordSound();
            setTimeout(() => el.classList.remove('db-flash-negative'), 600);
        }

        // Sync to backend DB
        if (amt !== 0) {
            fetch(window.API_BASE_URL + '/api/balls/update', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': 'Bearer ' + localStorage.getItem('primeedu_token')
                },
                body: JSON.stringify({ delta: amt })
            })
            .then(res => res.json())
            .then(data => {
                if (data.status === 'success' && data.balls !== undefined) {
                    el.innerText = data.balls.toLocaleString();
                    localStorage.setItem('primeedu_balls', data.balls);
                }
            })
            .catch(err => console.error("Error syncing balls:", err));
        }
        
        // Track daily balls
        if (amt > 0) {
            const today = new Date().toLocaleDateString();
            const dailyStr = localStorage.getItem('primeedu_daily_balls');
            let dailyObj = dailyStr ? JSON.parse(dailyStr) : { date: today, amount: 0 };
            if (dailyObj.date !== today) dailyObj = { date: today, amount: 0 };
            dailyObj.amount += amt;
            localStorage.setItem('primeedu_daily_balls', JSON.stringify(dailyObj));
        }
    }

    // Initialize ball count from storage
    const savedBalls = localStorage.getItem('primeedu_balls');
    if (savedBalls && document.getElementById('ball-count')) {
        document.getElementById('ball-count').innerText = parseInt(savedBalls).toLocaleString();
    }

    // ═══════════════ NEURAL FOCUS TIMER (V4 - PERSISTENT) ═══════════════
    let focusInterval = null;

    window.startFocusClick = async () => {
        const circle = document.getElementById('focus-toggle');
        
        if (focusInterval) {
            showConfirm("Stopping now costs 50 Dragon Balls. Proceed?", () => {
                updateDragonBalls(-50);
                stopFocus();
                localStorage.removeItem('primeedu_focus_end');
            });
            return;
        }

        const mins = await customPrompt("Neural Focus Timer", "Minutes of pure focus?", "25");
        if (!mins || isNaN(mins)) return;

        const focusSeconds = parseInt(mins) * 60;
        const endTime = Date.now() + focusSeconds * 1000;
        localStorage.setItem('primeedu_focus_end', endTime);
        
        startTimerLoop();
    };

    function startTimerLoop() {
        const circle = document.getElementById('focus-toggle');
        const overlay = document.getElementById('focus-timer-overlay');
        const display = document.getElementById('minor-timer-display');
        
        if (!circle) return;

        circle.classList.add('active');
        overlay.style.display = 'block';

        focusInterval = setInterval(() => {
            const end = parseInt(localStorage.getItem('primeedu_focus_end')) || 0;
            const remaining = Math.round((end - Date.now()) / 1000);

            if (remaining <= 0) {
                stopFocus();
                localStorage.removeItem('primeedu_focus_end');
                if(typeof playTimerSound === 'function') playTimerSound();
                showConfirm("FOCUS COMPLETE. Click PROCEED to save your session and earn 20 Dragon Balls.", () => {
                    updateDragonBalls(20);
                });
            } else {
                const m = Math.floor(remaining / 60);
                const s = remaining % 60;
                display.innerText = `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
            }
        }, 1000);
    }

    function stopFocus() {
        if(focusInterval) clearInterval(focusInterval);
        focusInterval = null;
        const circle = document.getElementById('focus-toggle');
        if(circle) circle.classList.remove('active');
        const overlay = document.getElementById('focus-timer-overlay');
        if(overlay) overlay.style.display = 'none';
    }

    if (localStorage.getItem('primeedu_focus_end')) {
        startTimerLoop();
    }

    // ═══════════════ GRAPHS ENGINE (RECAPS) ═══════════════
    window.renderRecapGraphs = (canvasId, type) => {
        const canvas = document.getElementById(canvasId);
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        const W = canvas.width;
        const H = canvas.height;
        const padding = 50;

        ctx.clearRect(0, 0, W, H);

        // Draw Axes with high visibility
        ctx.strokeStyle = 'rgba(0, 243, 255, 0.8)';
        ctx.lineWidth = 2;
        ctx.beginPath();
        // Y Axis
        ctx.moveTo(padding, 20);
        ctx.lineTo(padding, H - padding);
        // X Axis
        ctx.lineTo(W - 20, H - padding);
        ctx.stroke();

        // Axis Labels (Small indicators)
        ctx.fillStyle = 'rgba(255, 255, 255, 0.5)';
        ctx.font = '10px Inter';
        ctx.fillText('Consistency', padding - 45, 30);
        ctx.fillText('Time', W - 40, H - padding + 20);

        if (type === 'line') {
            ctx.strokeStyle = '#00f3ff';
            ctx.shadowBlur = 10;
            ctx.shadowColor = '#00f3ff';
            ctx.lineWidth = 4;
            ctx.beginPath();
            ctx.moveTo(padding, H - padding);

            for (let i = 1; i <= 6; i++) {
                const x = padding + (i * (W - 2 * padding) / 6);
                const y = (H - padding) - (Math.random() * (H - 2 * padding) * 0.8) - 10;
                ctx.lineTo(x, y);
                // Draw nodes
                ctx.save();
                ctx.fillStyle = '#fff';
                ctx.beginPath();
                ctx.arc(x, y, 4, 0, Math.PI * 2);
                ctx.fill();
                ctx.restore();
            }
            ctx.stroke();
            ctx.shadowBlur = 0;
        } else {
            // Precision Bars
            ctx.fillStyle = '#9d00ff';
            ctx.shadowBlur = 15;
            ctx.shadowColor = '#9d00ff';
            for (let i = 1; i <= 5; i++) {
                const x = padding + (i * (W - 2 * padding) / 6);
                const barH = Math.random() * (H - 2 * padding) * 0.7 + 20;
                // Smoothed bar tops using rect with radius
                const barWidth = 30;
                ctx.beginPath();
                ctx.roundRect(x - barWidth / 2, (H - padding) - barH, barWidth, barH, [10, 10, 0, 0]);
                ctx.fill();
            }
            ctx.shadowBlur = 0;
        }
    };

    // ═══════════════ ANIME SLASH ANIMATION ═══════════════
    function playSlashAnimation() {
        const overlay = document.getElementById('slash-overlay');
        const charImg = document.getElementById('slash-char-img');
        if (!overlay || !charImg) return;

        const char = getSelectedChar();
        charImg.style.backgroundImage = `url('${char.img}')`;

        overlay.style.display = 'flex';
        overlay.classList.remove('slash-active');

        // Trigger reflow
        void overlay.offsetWidth;

        overlay.classList.add('slash-active');
        if (window.playSwordSound) window.playSwordSound();

        setTimeout(() => {
            overlay.style.display = 'none';
            overlay.classList.remove('slash-active');
        }, 1200);
    }

    // ═══════════════ SETTINGS MODAL LOGIC ═══════════════
    window.handleSettingsRename = async () => {
        const input = document.getElementById('settings-rename-input');
        if(!input) return;
        const newName = input.value.trim();
        if(!newName) return;
        try {
            const res = await fetch(window.API_BASE_URL + '/api/user/profile', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ leaderboard_name: newName })
            });
            if(res.ok) {
                alert("Warrior handle updated successfully!");
                document.getElementById('settings-modal').style.display = 'none';
                localStorage.setItem('primeedu_leaderboard_name', newName);
                if(document.getElementById('user-greeting')) document.getElementById('user-greeting').innerText = `Ascended Warrior ${newName}`;
            }
        } catch(e) { console.error(e); }
    };

    window.handleSettingsChangePassword = async () => {
        const currPassEl = document.getElementById('settings-curr-pass');
        const newPassEl = document.getElementById('settings-new-pass');
        const current_password = currPassEl ? currPassEl.value : '';
        const new_password = newPassEl ? newPassEl.value : '';
        
        if(!current_password || !new_password) {
            alert("Both current and new passwords are required.");
            return;
        }
        
        try {
            const res = await fetch(window.API_BASE_URL + '/api/user/change_password', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ current_password, new_password })
            });
            const data = await res.json();
            if(res.ok) {
                alert("Password updated successfully!");
                currPassEl.value = '';
                newPassEl.value = '';
                document.getElementById('settings-modal').style.display = 'none';
            } else {
                alert(data.message || "Failed to update password.");
            }
        } catch(e) {
            console.error(e);
            alert("Error connecting to server.");
        }
    };

    window.handleLogout = () => {
        showConfirm("Are you sure you want to log out from this device?", () => {
            localStorage.removeItem('primeedu_token');
            window.location.href = 'index.html';
        });
    };

    window.handleLogoutAll = () => {
        showConfirm("This will log out all other devices. Proceed?", async () => {
            try {
                const res = await fetch(window.API_BASE_URL + '/api/auth/logout_all', { method: 'POST' });
                if(res.ok) alert("All other devices have been securely logged out.");
            } catch(e) { console.error(e); }
        });
    };

    // ═══════════════ AUDIO SYNTHESIS ═══════════════
    const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    
    window.playTaskSound = () => {
        if(audioCtx.state === 'suspended') audioCtx.resume();
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        osc.connect(gain);
        gain.connect(audioCtx.destination);
        
        osc.type = 'sine';
        osc.frequency.setValueAtTime(523.25, audioCtx.currentTime); // C5
        osc.frequency.exponentialRampToValueAtTime(1046.50, audioCtx.currentTime + 0.1); // C6
        
        gain.gain.setValueAtTime(0, audioCtx.currentTime);
        gain.gain.linearRampToValueAtTime(0.3, audioCtx.currentTime + 0.05);
        gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.5);
        
        osc.start(audioCtx.currentTime);
        osc.stop(audioCtx.currentTime + 0.5);
    };

    window.playTimerSound = () => {
        if(audioCtx.state === 'suspended') audioCtx.resume();
        const osc1 = audioCtx.createOscillator();
        const osc2 = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        
        osc1.connect(gain);
        osc2.connect(gain);
        gain.connect(audioCtx.destination);
        
        osc1.type = 'triangle';
        osc2.type = 'sine';
        osc1.frequency.setValueAtTime(440, audioCtx.currentTime); // A4
        osc2.frequency.setValueAtTime(880, audioCtx.currentTime); // A5
        
        gain.gain.setValueAtTime(0, audioCtx.currentTime);
        gain.gain.linearRampToValueAtTime(0.4, audioCtx.currentTime + 0.1);
        gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 1.5);
        
        osc1.start(audioCtx.currentTime);
        osc2.start(audioCtx.currentTime);
        osc1.stop(audioCtx.currentTime + 1.5);
        osc2.stop(audioCtx.currentTime + 1.5);
    };
    
    window.playSwordSound = () => {
        if(audioCtx.state === 'suspended') audioCtx.resume();
        const noise = audioCtx.createBufferSource();
        const buffer = audioCtx.createBuffer(1, audioCtx.sampleRate * 0.5, audioCtx.sampleRate);
        const data = buffer.getChannelData(0);
        for(let i=0; i<buffer.length; i++) {
            data[i] = Math.random() * 2 - 1;
        }
        noise.buffer = buffer;
        
        const filter = audioCtx.createBiquadFilter();
        filter.type = 'highpass';
        filter.frequency.value = 1000;
        
        const gain = audioCtx.createGain();
        gain.gain.setValueAtTime(0.5, audioCtx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.3);
        
        noise.connect(filter);
        filter.connect(gain);
        gain.connect(audioCtx.destination);
        noise.start(audioCtx.currentTime);
    };

    console.log('PrimeEDU v4 Refinement Complete');
});


// ==========================================
// DAILY RECAP SYSTEM
// ==========================================

window.saveRecapTime = function() {
    const timeVal = document.getElementById('daily-recap-time').value;
    if(timeVal) {
        localStorage.setItem('primeedu_recap_time', timeVal);
        const btn = event.target;
        btn.innerHTML = '<i class="fas fa-check"></i> SAVED';
        setTimeout(() => btn.innerHTML = 'SAVE', 2000);
    }
};

function getTodayStr() {
    return new Date().toLocaleDateString();
}

function calculateDailyFocus() {
    try {
        const sessionsStr = localStorage.getItem('primeedu_sessions');
        if(!sessionsStr) return 0;
        const sessions = JSON.parse(sessionsStr);
        const todayStr = getTodayStr();
        return sessions.filter(s => s.date === todayStr).reduce((acc, curr) => acc + (parseInt(curr.duration) || 0), 0);
    } catch(e) { return 0; }
}

function calculateDailyJournals() {
    try {
        const journalsStr = localStorage.getItem('primeedu_journal_entries');
        if(!journalsStr) return 0;
        const journals = JSON.parse(journalsStr);
        const todayStr = getTodayStr();
        return journals.filter(j => new Date(j.timestamp).toLocaleDateString() === todayStr).length;
    } catch(e) { return 0; }
}

function calculateDailyTasks() {
    try {
        const tasksStr = localStorage.getItem('primeedu_tasks');
        if(!tasksStr) return 0;
        const tasks = JSON.parse(tasksStr);
        const todayStr = getTodayStr();
        // Since tasks don't have completion dates saved, we just approximate by looking at completed tasks
        return tasks.filter(t => t.completed).length;
    } catch(e) { return 0; }
}

function checkDailyRecap() {
    const recapTime = localStorage.getItem('primeedu_recap_time') || '22:00';
    const lastRecapDate = localStorage.getItem('primeedu_last_recap_date');
    const todayStr = getTodayStr();
    
    // Check if we already showed it today
    if (lastRecapDate === todayStr) return;
    
    const now = new Date();
    const [recapHour, recapMin] = recapTime.split(':').map(Number);
    const recapDate = new Date();
    recapDate.setHours(recapHour, recapMin, 0, 0);
    
    // If current time is past recap time
    if (now >= recapDate) {
        // Trigger recap
        const modal = document.getElementById('daily-recap-modal');
        if(modal) {
            document.getElementById('daily-recap-date').innerText = new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' });
            
            // Get Balls
            const dailyBallsStr = localStorage.getItem('primeedu_daily_balls');
            let balls = 0;
            if(dailyBallsStr) {
                const bObj = JSON.parse(dailyBallsStr);
                if(bObj.date === todayStr) balls = bObj.amount;
            }
            document.getElementById('recap-balls').innerText = balls;
            
            // Get Focus
            const focusMins = calculateDailyFocus();
            document.getElementById('recap-focus').innerText = focusMins + 'm';
            
            // Get Tasks
            const tasks = calculateDailyTasks();
            document.getElementById('recap-tasks').innerText = tasks;
            
            // Get Journals
            const journals = calculateDailyJournals();
            document.getElementById('recap-journal').innerText = journals;
            
            modal.style.display = 'flex';
            localStorage.setItem('primeedu_last_recap_date', todayStr);
        }
    }
}

// Initialize Daily Recap
document.addEventListener('DOMContentLoaded', () => {
    const recapInput = document.getElementById('daily-recap-time');
    if(recapInput) {
        recapInput.value = localStorage.getItem('primeedu_recap_time') || '22:00';
    }
    
    // Check every minute
    setInterval(checkDailyRecap, 60000);
    // Check immediately on load
    setTimeout(checkDailyRecap, 2000);
});
