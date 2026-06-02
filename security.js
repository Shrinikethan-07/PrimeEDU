/**
 * PrimeEDU client-side security helpers (XSS prevention, safe storage).
 */
(function (global) {
    'use strict';

    const HTML_ESCAPE_MAP = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;',
    };

    function escapeHtml(str) {
        if (str == null) return '';
        return String(str).replace(/[&<>"']/g, (ch) => HTML_ESCAPE_MAP[ch] || ch);
    }

    function clampString(str, maxLen) {
        if (str == null) return '';
        const s = String(str);
        return s.length > maxLen ? s.slice(0, maxLen) : s;
    }

    function safeJsonParse(raw, fallback) {
        if (raw == null || raw === '') return fallback;
        try {
            const parsed = JSON.parse(raw);
            if (parsed === null || typeof parsed !== 'object') return fallback;
            return parsed;
        } catch (_) {
            return fallback;
        }
    }

    function sanitizeId(id, maxLen) {
        if (id == null) return '';
        return String(id).replace(/[^\w.-]/g, '').slice(0, maxLen || 120);
    }

    function pickFromAllowlist(value, allowlist, fallback) {
        return allowlist.includes(value) ? value : fallback;
    }

    global.PrimeEDUSecurity = {
        escapeHtml,
        clampString,
        safeJsonParse,
        sanitizeId,
        pickFromAllowlist,
        LIMITS: {
            TASK_TEXT: 500,
            CHAPTER_TITLE: 200,
            NOTE_CONTENT: 10000,
            JOURNAL_TITLE: 200,
            JOURNAL_CONTENT: 50000,
            TOPIC_ID: 120,
        },
    };
})(typeof window !== 'undefined' ? window : global);
