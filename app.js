document.addEventListener('DOMContentLoaded', () => {

    const SEC = window.PrimeEDUSecurity || {
        escapeHtml: (s) => String(s ?? ''),
        clampString: (s, n) => String(s ?? '').slice(0, n),
        safeJsonParse: (r, fb) => { try { return JSON.parse(r); } catch { return fb; } },
        sanitizeId: (id) => String(id ?? '').replace(/[^\w.-]/g, '').slice(0, 120),
        pickFromAllowlist: (v, list, fb) => (list.includes(v) ? v : fb),
        LIMITS: { TASK_TEXT: 500, CHAPTER_TITLE: 200, NOTE_CONTENT: 10000, TOPIC_ID: 120 },
    };

    // ═══════════════ ANIME CHARACTERS & AVATARS ═══════════════
    const AV = window.PrimeEDUAvatars || {
        CHARACTERS: [],
        DEFAULT_AVATAR: '',
        AVATAR_IDS: [],
        getSelectedCharacter: () => ({ id: 'sasuke', name: 'Sasuke', img: '' }),
        updateAvatarImages: () => {},
    };
    const CHARACTERS = AV.CHARACTERS;
    const DEFAULT_AVATAR = AV.DEFAULT_AVATAR;
    const AVATAR_IDS = AV.AVATAR_IDS;

    function getSelectedChar() {
        return AV.getSelectedCharacter();
    }

    function updateAllAvatars() {
        AV.updateAvatarImages();
    }

    const charGrid = document.getElementById('char-grid');
    if (charGrid) {
        // Use a document fragment for faster rendering and zero lag
        const fragment = document.createDocumentFragment();
        CHARACTERS.forEach(c => {
            const div = document.createElement('div');
            div.className = 'char-option' + (getSelectedChar().id === c.id ? ' selected' : '');
            div.innerHTML = `
                <div class="char-img-wrapper">
                    <img src="${c.img}" alt="${c.name}" loading="lazy">
                </div>
                <span>${c.name}</span>
            `;
            div.addEventListener('click', () => {
                localStorage.setItem('primeedu_avatar', SEC.pickFromAllowlist(c.id, AVATAR_IDS, 'sasuke'));
                document.querySelectorAll('.char-option').forEach(el => el.classList.remove('selected'));
                div.classList.add('selected');
                updateAllAvatars();
            });
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

    updateAllAvatars();

    // ═══════════════ SYLLABUS STATE & DOM ═══════════════
    const SYLLABUS_TREE = document.getElementById('syllabus-tree');
    const EXAM_NAME_EL = document.getElementById('exam-name');
    const EXAM_PROGRESS_FILL = document.getElementById('exam-progress-fill');
    const EXAM_PROGRESS_TEXT = document.getElementById('exam-progress-text');
    const EXAM_SELECTOR = document.getElementById('exam-selector');

    const examKeys = typeof EXAM_DATA !== 'undefined' ? Object.keys(EXAM_DATA) : [];
    let currentExamId = SEC.pickFromAllowlist(
        localStorage.getItem('primeedu_active_exam') || 'neet-ug',
        examKeys,
        examKeys[0] || 'neet-ug'
    );
    let progressData = SEC.safeJsonParse(localStorage.getItem('primeedu_progress_v3'), {});
    if (typeof progressData !== 'object' || Array.isArray(progressData)) progressData = {};

    // ═══════════════ DRAGON BALL ECONOMY ═══════════════
    function updateDragonBalls(amt, absolute) {
        const el = document.getElementById('ball-count');
        if (!el) return;
        const count = absolute != null
            ? absolute
            : (parseInt(el.innerText.replace(/,/g, ''), 10) || 0) + (amt || 0);
        el.innerText = count.toLocaleString();
        localStorage.setItem('primeedu_balls', count);
    }

    const savedBalls = localStorage.getItem('primeedu_balls');
    if (savedBalls && document.getElementById('ball-count')) {
        document.getElementById('ball-count').innerText = parseInt(savedBalls, 10).toLocaleString();
    }

    async function loadUserProfile() {
        try {
            const res = await fetch('/api/user/profile');
            if (!res.ok) return;
            const profile = await res.json();
            if (profile.balls != null) updateDragonBalls(0, profile.balls);
            const greeting = document.getElementById('user-greeting');
            if (greeting && profile.name) {
                greeting.textContent = `Welcome back, ${SEC.clampString(profile.name, 80)}`;
            }
        } catch (e) { /* offline / file:// */ }
    }
    loadUserProfile();

    // ═══════════════ DREAM DECONSTRUCTION HUB ═══════════════
    window.saveDream = async (ev) => {
        const input = document.getElementById('dream-input');
        if (!input || !input.value.trim()) return;
        const dream = SEC.clampString(input.value.trim(), 500);
        localStorage.setItem('primeedu_massive_dream', dream);

        const btn = ev?.currentTarget || ev?.target;
        if (!btn) return;
        const originalText = btn.innerText;
        btn.innerText = "Goal saved";
        btn.classList.add('vibrant-pulse');

        try {
            await fetch('/api/user/profile', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ massive_goal: { title: dream, deadline: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString() } })
            });
        } catch (e) { }

        setTimeout(() => { btn.innerText = originalText; btn.classList.remove('vibrant-pulse'); }, 2000);
    };

    // Load dream
    const savedDream = localStorage.getItem('primeedu_massive_dream');
    if (savedDream && document.getElementById('dream-input')) {
        document.getElementById('dream-input').value = savedDream;
    }

    // ═══════════════ MANUAL MISSIONS (TASKS) ═══════════════
    let manualTasks = SEC.safeJsonParse(localStorage.getItem('primeedu_manual_tasks'), []);
    if (!Array.isArray(manualTasks)) manualTasks = [];

    window.addManualTask = () => {
        const input = document.getElementById('task-input');
        if (!input || !input.value.trim()) return;
        const task = {
            id: Date.now(),
            text: SEC.clampString(input.value.trim(), SEC.LIMITS.TASK_TEXT),
            completed: false,
        };
        manualTasks.push(task);
        input.value = '';
        renderTasks();
        saveTasks();
    };

    window.toggleTask = (id) => {
        const task = manualTasks.find(t => t.id === id);
        if (task) {
            task.completed = !task.completed;
            if (task.completed) {
                showCompleteToast('Task completed');
                updateDragonBalls(10);
            }
            renderTasks();
            saveTasks();
        }
    };

    function renderTasks() {
        const list = document.getElementById('manual-tasks-list');
        if (!list) return;
        list.innerHTML = '';
        manualTasks.forEach(t => {
            const div = document.createElement('div');
            div.className = 'task-item' + (t.completed ? ' completed' : '');
            div.dataset.taskId = String(t.id);
            const span = document.createElement('span');
            span.textContent = t.text || '';
            const icon = document.createElement('i');
            icon.className = 'fas ' + (t.completed ? 'fa-check-circle' : 'fa-circle');
            icon.style.color = t.completed ? 'var(--sage)' : 'var(--text-muted)';
            div.appendChild(span);
            div.appendChild(icon);
            div.addEventListener('click', () => toggleTask(t.id));
            list.appendChild(div);
        });
    }

    async function saveTasks() {
        localStorage.setItem('primeedu_manual_tasks', JSON.stringify(manualTasks));
        try {
            await fetch('/api/tasks/sync', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ tasks: manualTasks })
            });
        } catch (e) { }
    }
    renderTasks();

    // ═══════════════ SYLLABUS FORGER (CHAPTERS) ═══════════════
    let activeSubj = 'physics';
    let userChapters = SEC.safeJsonParse(
        localStorage.getItem('primeedu_chapters'),
        { physics: [], chemistry: [], biology: [], mathematics: [] }
    );

    window.switchSubj = (subj) => {
        if (subj === 'alt') {
            // Check if current exam is NEET or JEE
            const isJee = localStorage.getItem('primeedu_exam_type') === 'jee';
            subj = isJee ? 'mathematics' : 'biology';
        }
        activeSubj = subj;
        document.querySelectorAll('.subj-tab').forEach(t => t.classList.remove('active'));
        const tabId = (subj === 'biology' || subj === 'mathematics') ? 'bio-math-tab' : '';
        if (tabId) {
            const tab = document.getElementById(tabId);
            tab.innerText = subj.toUpperCase();
            tab.classList.add('active');
        } else {
            document.querySelector(`.subj-tab[onclick*="${subj}"]`)?.classList.add('active');
        }
        renderChapters();
    };

    window.addChapter = () => {
        const input = document.getElementById('chapter-input');
        if (!input || !input.value.trim()) return;
        userChapters[activeSubj].push({
            title: SEC.clampString(input.value.trim(), SEC.LIMITS.CHAPTER_TITLE),
            completed: false,
        });
        input.value = '';
        renderChapters();
        saveChapters();
    };

    function renderChapters() {
        const grid = document.getElementById('chapters-grid');
        if (!grid) return;
        grid.innerHTML = '';
        (userChapters[activeSubj] || []).forEach(c => {
            const div = document.createElement('div');
            div.className = 'chapter-tag';
            const span = document.createElement('span');
            span.textContent = c.title || '';
            const icon = document.createElement('i');
            icon.className = 'fas fa-bookmark';
            icon.style.cssText = 'font-size:0.7rem; color:var(--sage)';
            div.appendChild(span);
            div.appendChild(icon);
            grid.appendChild(div);
        });
    }

    async function saveChapters() {
        localStorage.setItem('primeedu_chapters', JSON.stringify(userChapters));
        try {
            await fetch('/api/syllabus/custom', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ chapters: userChapters })
            });
        } catch (e) { }
    }
    renderChapters();
    async function syncProgressWithBackend() {
        try {
            const res = await fetch('/api/syllabus/progress');
            const backendProgress = await res.json();
            progressData = { ...progressData, ...backendProgress };
            renderSyllabus();
        } catch (e) {
            console.warn('Backend sync failed, using local data.');
        }
    }

    async function saveProgress(topicId, state) {
        localStorage.setItem('primeedu_progress_v3', JSON.stringify(progressData));
        calculateAggregateProgress();

        try {
            const res = await fetch('/api/syllabus/progress', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ topic_id: topicId, completed: state })
            });
            const data = await res.json();
            if (data.balls) updateDragonBalls(0, data.balls);
        } catch (e) {
            console.error('Failed to sync progress to backend');
        }
    }

    async function saveNoteToBackend(topicId, val) {
        const safeId = SEC.sanitizeId(topicId);
        const safeVal = SEC.clampString(val, SEC.LIMITS.NOTE_CONTENT);
        localStorage.setItem(`note-${safeId}`, safeVal);
        try {
            await fetch('/api/syllabus/notes', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ topic_id: safeId, content: safeVal })
            });
        } catch (e) {
            console.error('Failed to sync note to backend');
        }
    }

    function renderSyllabus() {
        if (!SYLLABUS_TREE) return;
        const exam = EXAM_DATA[currentExamId];
        if (!exam) return;

        if (EXAM_NAME_EL) EXAM_NAME_EL.innerText = exam.name;
        SYLLABUS_TREE.innerHTML = '';

        exam.units.forEach(unit => {
            const unitDiv = document.createElement('div');
            unitDiv.className = 'unit-item';

            const unitHeader = document.createElement('div');
            unitHeader.className = 'unit-header';
            unitHeader.innerHTML = `
                <div class="unit-title"><i class="fas fa-folder"></i> ${unit.name}</div>
                <span class="unit-progress" id="progress-${unit.id}">0%</span>
            `;
            unitHeader.addEventListener('click', () => {
                unitDiv.classList.toggle('open');
            });

            const chaptersList = document.createElement('div');
            chaptersList.className = 'chapters-list';

            unit.chapters.forEach(chapter => {
                const chapterDiv = document.createElement('div');
                chapterDiv.className = 'chapter-item';
                chapterDiv.innerHTML = `<span class="chapter-title">${chapter.name}</span>`;

                const topicsList = document.createElement('div');
                topicsList.className = 'topics-list';

                chapter.topics.forEach(topicName => {
                    const topicId = SEC.sanitizeId(
                        `${unit.id}-${chapter.id}-${topicName}`.replace(/\s+/g, '-')
                    );
                    const isDone = progressData[topicId] || false;

                    const topicDiv = document.createElement('div');
                    topicDiv.className = 'topic-item' + (isDone ? ' completed' : '');
                    topicDiv.dataset.topicId = topicId;

                    const savedNote = localStorage.getItem(`note-${topicId}`) || '';

                    const titleSpan = document.createElement('span');
                    titleSpan.textContent = topicName;

                    const actions = document.createElement('div');
                    actions.className = 'topic-actions';

                    const noteBtn = document.createElement('i');
                    noteBtn.className = 'fas fa-edit action-btn' + (savedNote ? ' has-content' : '');
                    noteBtn.title = 'Notes';
                    noteBtn.addEventListener('click', (e) => {
                        e.stopPropagation();
                        toggleNote(topicId);
                    });

                    const flashBtn = document.createElement('i');
                    flashBtn.className = 'fas fa-bolt action-btn';
                    flashBtn.title = 'Flashcard';
                    flashBtn.addEventListener('click', (e) => {
                        e.stopPropagation();
                        openFlashcard(topicName, topicId);
                    });

                    const checkWrap = document.createElement('div');
                    checkWrap.className = 'topic-checkbox';
                    const checkIcon = document.createElement('i');
                    checkIcon.className = 'fas fa-check';
                    if (!isDone) checkIcon.style.display = 'none';
                    checkWrap.appendChild(checkIcon);
                    checkWrap.addEventListener('click', (e) => {
                        e.stopPropagation();
                        toggleTopic(topicId, topicDiv);
                    });

                    actions.append(noteBtn, flashBtn, checkWrap);
                    topicDiv.append(titleSpan, actions);

                    const noteDrawer = document.createElement('div');
                    noteDrawer.className = 'note-drawer';
                    noteDrawer.id = `drawer-${topicId}`;
                    const textarea = document.createElement('textarea');
                    textarea.className = 'note-editor';
                    textarea.placeholder = 'Add revision notes, formulas...';
                    textarea.value = savedNote;
                    textarea.addEventListener('input', () => saveNote(topicId, textarea.value));
                    noteDrawer.appendChild(textarea);

                    const wrapper = document.createElement('div');
                    wrapper.appendChild(topicDiv);
                    wrapper.appendChild(noteDrawer);
                    topicsList.appendChild(wrapper);
                });

                chapterDiv.appendChild(topicsList);
                chaptersList.appendChild(chapterDiv);
            });

            unitDiv.appendChild(unitHeader);
            unitDiv.appendChild(chaptersList);
            SYLLABUS_TREE.appendChild(unitDiv);
            updateUnitProgressSummary(unit);
        });

        calculateAggregateProgress();
    }

    window.toggleTopic = (topicId, el) => {
        const newState = !progressData[topicId];
        progressData[topicId] = newState;
        el.classList.toggle('completed');
        el.querySelector('.fa-check').style.display = newState ? 'block' : 'none';
        if (newState) {
            showCompleteToast('Topic marked complete');
            updateDragonBalls(5);
        }
        saveProgress(topicId, newState);
        const exam = typeof EXAM_DATA !== 'undefined' ? EXAM_DATA[currentExamId] : null;
        if (exam) exam.units.forEach(u => updateUnitProgressSummary(u));
    };

    window.toggleNote = (topicId) => {
        const drawer = document.getElementById(`drawer-${topicId}`);
        if (drawer) {
            const isVisible = drawer.style.display === 'block';
            drawer.style.display = isVisible ? 'none' : 'block';
        }
    };

    window.saveNote = (topicId, val) => {
        saveNoteToBackend(topicId, val);
        const safeId = SEC.sanitizeId(topicId);
        const row = document.querySelector(`.topic-item[data-topic-id="${CSS.escape(safeId)}"]`);
        const icon = row?.querySelector('.fa-edit');
        if (icon) icon.classList.toggle('has-content', String(val).length > 0);
    };

    window.openFlashcard = (title, id) => {
        const modal = document.getElementById('flashcard-modal');
        if (!modal) return;
        const examName = (typeof EXAM_DATA !== 'undefined' && EXAM_DATA[currentExamId])
            ? EXAM_DATA[currentExamId].name : 'your exam';
        document.getElementById('fc-topic-title').textContent = title;
        document.getElementById('fc-question').textContent = `What is the core concept of ${title}?`;
        document.getElementById('fc-answer').textContent = `Essential high-yield facts about ${title} for the ${examName}.`;
        document.getElementById('flashcard-obj').classList.remove('flipped');
        modal.style.display = 'flex';
    };

    window.handleLeitner = (level) => {
        alert(`Spaced Repetition: Scheduled for ${level === 'easy' ? '4 days' : level === 'med' ? '2 days' : 'tomorrow'}.`);
        document.getElementById('flashcard-modal').style.display = 'none';
        updateDragonBalls(2);
    };

    function updateUnitProgressSummary(unit) {
        const unitEl = document.getElementById(`progress-${unit.id}`);
        if (!unitEl) return;

        let total = 0, completed = 0;
        unit.chapters.forEach(c => {
            c.topics.forEach(t => {
                total++;
                const tid = `${unit.id}-${c.id}-${t}`.replace(/\s+/g, '-');
                if (progressData[tid]) completed++;
            });
        });

        const pct = total > 0 ? Math.round((completed / total) * 100) : 0;
        unitEl.innerText = `${pct}%`;
        unitEl.style.color = pct === 100 ? 'var(--sage)' : 'var(--text-secondary)';
    }

    function calculateAggregateProgress() {
        const exam = typeof EXAM_DATA !== 'undefined' ? EXAM_DATA[currentExamId] : null;
        if (!exam) return;
        let total = 0, completed = 0;
        exam.units.forEach(u => {
            u.chapters.forEach(c => {
                c.topics.forEach(t => {
                    total++;
                    const tid = `${u.id}-${c.id}-${t}`.replace(/\s+/g, '-');
                    if (progressData[tid]) completed++;
                });
            });
        });

        const pct = total > 0 ? Math.round((completed / total) * 100) : 0;
        if (EXAM_PROGRESS_FILL) EXAM_PROGRESS_FILL.style.width = `${pct}%`;
        if (EXAM_PROGRESS_TEXT) EXAM_PROGRESS_TEXT.innerText = `${pct}%`;
    }

    if (SYLLABUS_TREE && typeof EXAM_DATA !== 'undefined') {
        if (EXAM_SELECTOR) {
            EXAM_SELECTOR.value = currentExamId;
            EXAM_SELECTOR.addEventListener('change', (e) => {
                currentExamId = SEC.pickFromAllowlist(e.target.value, examKeys, currentExamId);
                localStorage.setItem('primeedu_active_exam', currentExamId);
                renderSyllabus();
            });
        }
        syncProgressWithBackend();
    }

    // ═══════════════ COMPLETION FEEDBACK ═══════════════
    window.showCompleteToast = (message = 'Done') => {
        const root = document.getElementById('complete-toast-root');
        if (!root) return;
        const toast = document.createElement('div');
        toast.className = 'complete-toast';
        const icon = document.createElement('i');
        icon.className = 'fas fa-check-circle';
        const span = document.createElement('span');
        span.textContent = SEC.clampString(message, 200);
        toast.append(icon, span);
        root.appendChild(toast);
        setTimeout(() => toast.remove(), 1800);
    };

    window.playSlashAnimation = () => showCompleteToast('Progress saved');

    // ═══════════════ GRAPHS ENGINE (RECAPS) ═══════════════
    window.renderRecapGraphs = (canvasId, type) => {
        const canvas = document.getElementById(canvasId);
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        const W = canvas.width;
        const H = canvas.height;
        const padding = 40;

        // Draw Axes
        ctx.strokeStyle = 'rgba(255,255,255,0.4)';
        ctx.lineWidth = 2;
        ctx.beginPath();
        // Y Axis
        ctx.moveTo(padding, 10);
        ctx.lineTo(padding, H - padding);
        // X Axis
        ctx.lineTo(W - 10, H - padding);
        ctx.stroke();

        if (type === 'line') {
            ctx.strokeStyle = '#5c8a6e';
            ctx.lineWidth = 3;
            ctx.beginPath();
            ctx.moveTo(padding, H - padding); // Origin

            for (let i = 1; i <= 6; i++) {
                const x = padding + (i * (W - 2 * padding) / 6);
                const y = (H - padding) - (Math.random() * (H - 2 * padding) * 0.8);
                ctx.lineTo(x, y);
            }
            ctx.stroke();
        } else {
            ctx.fillStyle = '#4a7c9e';
            for (let i = 1; i <= 6; i++) {
                const x = padding + (i * (W - 2 * padding) / 7);
                const barH = Math.random() * (H - 2 * padding) * 0.7;
                ctx.fillRect(x, (H - padding) - barH, 20, barH);
            }
        }
    };

    console.log('PrimeEDU — Focused Mind theme loaded');
});
