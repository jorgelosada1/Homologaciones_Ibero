/* Homologaciones SENA · Ibero — utilidades globales */
(function () {
    'use strict';
    const root = document.documentElement;
    const body = document.body;
    const CSRF = document.querySelector('meta[name="csrf-token"]')?.content || '';

    const store = {
        get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch { return d; } },
        set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* sin almacenamiento */ } },
        del(k) { try { localStorage.removeItem(k); } catch { /* */ } },
    };

    // ---------- Helpers ----------
    const escapeHtml = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const money = (n) => '$' + Math.round(Number(n) || 0).toLocaleString('es-CO');
    const normalize = (s) => String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
    const debounce = (fn, ms = 250) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };
    const waFormat = (text) => escapeHtml(text)
        .replace(/\*([^*\n]+)\*/g, '<strong>$1</strong>')
        .replace(/(^|\s)_([^_\n]+)_(?=\s|$|[.,!?])/g, '$1<em>$2</em>')
        .replace(/~([^~\n]+)~/g, '<s>$1</s>');
    const highlight = (text, q) => {
        const t = escapeHtml(text);
        if (!q) return t;
        const nt = normalize(text); const nq = normalize(q).trim();
        const i = nt.indexOf(nq);
        if (i < 0 || !nq) return t;
        return escapeHtml(text.slice(0, i)) + '<mark>' + escapeHtml(text.slice(i, i + nq.length)) + '</mark>' + escapeHtml(text.slice(i + nq.length));
    };

    // ---------- Fetch con CSRF ----------
    const _fetch = window.fetch.bind(window);
    window.fetch = (input, init = {}) => {
        const method = (init.method || 'GET').toUpperCase();
        const url = typeof input === 'string' ? input : input.url;
        const same = !/^https?:\/\//i.test(url) || url.startsWith(location.origin);
        if (same && method !== 'GET' && method !== 'HEAD') {
            init.headers = new Headers(init.headers || {});
            if (!init.headers.has('X-CSRF-Token')) init.headers.set('X-CSRF-Token', CSRF);
        }
        return _fetch(input, init);
    };
    const api = async (url, opts = {}) => {
        const init = { ...opts };
        if (opts.json !== undefined) {
            init.method = init.method || 'POST';
            init.headers = { 'Content-Type': 'application/json', ...(init.headers || {}) };
            init.body = JSON.stringify(opts.json);
            delete init.json;
        }
        const res = await fetch(url, init);
        let data = null;
        try { data = await res.json(); } catch { data = { ok: false, error: 'Respuesta inválida del servidor' }; }
        if (res.status === 401) { location.href = '/login?next=' + encodeURIComponent(location.pathname + location.search); }
        if (!res.ok && data && data.ok === undefined) data.ok = false;
        return data;
    };

    function injectCsrf(form) {
        if ((form.method || '').toLowerCase() !== 'post') return;
        if (form.querySelector('input[name="csrf_token"]')) return;
        const i = document.createElement('input');
        i.type = 'hidden'; i.name = 'csrf_token'; i.value = CSRF;
        form.appendChild(i);
    }
    document.querySelectorAll('form').forEach(injectCsrf);
    document.addEventListener('submit', (e) => injectCsrf(e.target), true);
    new MutationObserver((muts) => muts.forEach((m) => m.addedNodes.forEach((n) => {
        if (n.nodeType !== 1) return;
        if (n.tagName === 'FORM') injectCsrf(n);
        n.querySelectorAll?.('form').forEach(injectCsrf);
    }))).observe(document.body, { childList: true, subtree: true });

    // ---------- Toasts ----------
    function toast(message, type = 'success', ms = 2600) {
        const stack = document.getElementById('toastStack');
        if (!stack) return;
        const icons = { success: 'fa-circle-check', error: 'fa-circle-xmark', info: 'fa-circle-info' };
        const el = document.createElement('div');
        el.className = `toast ${type}`;
        el.setAttribute('role', 'status');
        el.innerHTML = `<i class="fa-solid ${icons[type] || icons.success}"></i><span>${escapeHtml(message)}</span>`;
        stack.appendChild(el);
        setTimeout(() => { el.classList.add('hiding'); setTimeout(() => el.remove(), 260); }, ms);
    }

    // ---------- Portapapeles ----------
    async function copyText(text, label = 'Copiado al portapapeles', trackQuery) {
        try {
            await navigator.clipboard.writeText(text);
        } catch {
            const ta = document.createElement('textarea');
            ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
            document.body.appendChild(ta); ta.select();
            try { document.execCommand('copy'); } catch { toast('No se pudo copiar', 'error'); ta.remove(); return false; }
            ta.remove();
        }
        toast(label);
        if (trackQuery !== undefined) track('copia', trackQuery);
        return true;
    }
    function track(tipo, query) {
        fetch('/api/track', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ tipo, query }) }).catch(() => {});
    }

    // ---------- WhatsApp ----------
    const PREFIX = (document.querySelector('meta[name="phone-prefix"]')?.content || '57').replace(/\D/g, '');
    function normalizePhone(raw) {
        let d = String(raw || '').replace(/\D/g, '');
        if (!d) return '';
        if (d.startsWith('00')) d = d.slice(2);
        if (d.length === 10 && PREFIX && !d.startsWith(PREFIX)) d = PREFIX + d;
        return d;
    }
    function waLink(phone, text) {
        const p = normalizePhone(phone);
        const q = text ? '?text=' + encodeURIComponent(text) : '';
        return p ? `https://wa.me/${p}${q}` : `https://wa.me/${q}`;
    }
    function openWhatsApp(phone, text, trackQuery) {
        window.open(waLink(phone, text), '_blank', 'noopener');
        track('whatsapp', trackQuery || '');
    }

    // ---------- Tema ----------
    function applyTheme(t) {
        root.setAttribute('data-theme', t);
        document.querySelectorAll('[data-theme-icon]').forEach((i) => { i.className = t === 'dark' ? 'fa-solid fa-sun' : 'fa-solid fa-moon'; });
        const meta = document.querySelector('meta[name="theme-color"]');
        if (meta) meta.content = t === 'dark' ? '#0b0e14' : '#f4f5f7';
        window.dispatchEvent(new CustomEvent('themechange', { detail: t }));
    }
    function toggleTheme() {
        const t = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
        store.set('theme', t); applyTheme(t);
    }
    applyTheme(root.getAttribute('data-theme') || 'light');

    // ---------- Sidebar ----------
    function toggleSidebar(force) {
        if (window.innerWidth <= 1024) {
            body.classList.toggle('sidebar-open', force);
        } else {
            const c = body.classList.toggle('sidebar-collapsed', force);
            store.set('sidebar-collapsed', c);
        }
    }
    document.querySelectorAll('[data-action="toggle-sidebar"]').forEach((b) => b.addEventListener('click', () => toggleSidebar()));
    document.getElementById('sideOverlay')?.addEventListener('click', () => toggleSidebar(false));
    document.querySelectorAll('.side-link').forEach((a) => a.addEventListener('click', () => { if (window.innerWidth <= 1024) toggleSidebar(false); }));
    document.querySelectorAll('[data-action="toggle-theme"]').forEach((b) => b.addEventListener('click', toggleTheme));

    // ---------- Dropdowns ----------
    document.querySelectorAll('[data-dropdown]').forEach((btn) => {
        const menu = document.getElementById(btn.dataset.dropdown);
        btn.addEventListener('click', (e) => { e.stopPropagation(); menu.classList.toggle('open'); btn.setAttribute('aria-expanded', menu.classList.contains('open')); });
    });
    document.addEventListener('click', () => document.querySelectorAll('.dropdown.open').forEach((d) => d.classList.remove('open')));

    // ---------- Reloj ----------
    const clock = document.getElementById('clock');
    if (clock) {
        const tick = () => { clock.textContent = new Date().toLocaleTimeString('es-CO', { hour: '2-digit', minute: '2-digit' }); };
        tick(); setInterval(tick, 15000);
    }

    // ---------- Modales ----------
    function openModal(id) { const m = document.getElementById(id); if (!m) return; m.classList.add('open'); m.setAttribute('aria-hidden', 'false'); setTimeout(() => m.querySelector('[autofocus], input, textarea, button')?.focus(), 60); }
    function closeModal(id) { const m = typeof id === 'string' ? document.getElementById(id) : id; if (!m) return; m.classList.remove('open'); m.setAttribute('aria-hidden', 'true'); }
    document.addEventListener('click', (e) => {
        const closer = e.target.closest('[data-close-modal]');
        if (closer) { closeModal(closer.closest('.modal')); return; }
        if (e.target.classList?.contains('modal')) closeModal(e.target);
        const opener = e.target.closest('[data-open-modal]');
        if (opener) openModal(opener.dataset.openModal);
    });

    // ---------- Confirmaciones ----------
    document.addEventListener('submit', (e) => {
        const msg = e.target.dataset.confirm;
        if (msg && !confirm(msg)) { e.preventDefault(); e.stopImmediatePropagation(); }
    }, true);

    // ---------- Paleta de comandos ----------
    const palette = document.getElementById('palette');
    const pInput = document.getElementById('paletteInput');
    const pList = document.getElementById('paletteList');
    let pItems = []; let pSel = 0; let titulos = null; let titulosPres = null;
    const pages = JSON.parse(document.getElementById('navData')?.textContent || '[]');
    const actions = [
        { label: 'Cambiar tema claro / oscuro', icon: 'fa-circle-half-stroke', run: toggleTheme, hint: 'Tema' },
        { label: 'Panel de administración', icon: 'fa-shield-halved', href: '/admin', hint: 'Admin' },
        { label: 'Cerrar sesión', icon: 'fa-right-from-bracket', href: '/logout', hint: 'Sesión' },
    ];

    async function loadTitulos() {
        if (titulos) return;
        const d = await api('/api/titulos');
        titulos = d?.items || [];
    }
    function renderPalette() {
        const q = normalize(pInput.value.trim());
        const groups = [];
        const pg = pages.filter((p) => !q || normalize(p.label).includes(q)).slice(0, q ? 6 : 8)
            .map((p) => ({ ...p, hint: 'Ir a' }));
        if (pg.length) groups.push(['Páginas', pg]);
        if (q && titulos) {
            const t = titulos.filter((x) => normalize(x).includes(q)).slice(0, 8)
                .map((x) => ({ label: x, icon: 'fa-graduation-cap', href: '/?q=' + encodeURIComponent(x), hint: 'Homologar' }));
            if (t.length) groups.push(['Títulos SENA', t]);
            if (!t.length && q.length > 2) groups.push(['Buscar', [{ label: `Buscar “${pInput.value.trim()}” en homologaciones`, icon: 'fa-magnifying-glass', href: '/?q=' + encodeURIComponent(pInput.value.trim()), hint: 'Búsqueda inteligente' }]]);
        }
        const ac = actions.filter((a) => !q || normalize(a.label).includes(q));
        if (ac.length) groups.push(['Acciones', ac]);
        pItems = groups.flatMap((g) => g[1]);
        pSel = Math.min(pSel, Math.max(pItems.length - 1, 0));
        let i = 0;
        pList.innerHTML = groups.map(([name, items]) => `<div class="palette-group">${name}</div>` + items.map((it) => {
            const idx = i++;
            return `<div class="palette-item${idx === pSel ? ' sel' : ''}" data-i="${idx}"><span class="pi-icon"><i class="fa-solid ${it.icon}"></i></span><span class="pi-text">${highlight(it.label, pInput.value.trim())}</span><span class="pi-hint">${it.hint || ''}</span></div>`;
        }).join('')).join('') || '<div class="empty" style="padding:28px"><p>Sin resultados</p></div>';
    }
    function runItem(it, alt) {
        if (!it) return;
        closePalette();
        if (it.run) it.run();
        else location.href = alt && it.alt ? it.alt : it.href;
    }
    function openPalette() {
        if (!palette) return;
        palette.classList.add('open'); pInput.value = ''; pSel = 0; renderPalette();
        pInput.focus();
        loadTitulos().then(renderPalette);
    }
    function closePalette() { palette?.classList.remove('open'); }
    if (palette) {
        pInput.addEventListener('input', () => { pSel = 0; renderPalette(); });
        pInput.addEventListener('keydown', (e) => {
            if (e.key === 'ArrowDown') { e.preventDefault(); pSel = Math.min(pSel + 1, pItems.length - 1); renderPalette(); pList.querySelector('.sel')?.scrollIntoView({ block: 'nearest' }); }
            else if (e.key === 'ArrowUp') { e.preventDefault(); pSel = Math.max(pSel - 1, 0); renderPalette(); pList.querySelector('.sel')?.scrollIntoView({ block: 'nearest' }); }
            else if (e.key === 'Enter') { e.preventDefault(); runItem(pItems[pSel], e.shiftKey); }
            else if (e.key === 'Escape') closePalette();
        });
        pList.addEventListener('click', (e) => { const el = e.target.closest('.palette-item'); if (el) runItem(pItems[+el.dataset.i], e.shiftKey); });
        palette.addEventListener('click', (e) => { if (e.target === palette) closePalette(); });
        document.querySelectorAll('[data-action="palette"]').forEach((b) => b.addEventListener('click', openPalette));
    }

    // ---------- Atajos ----------
    let gPressed = 0;
    document.addEventListener('keydown', (e) => {
        const tag = (e.target.tagName || '').toLowerCase();
        const typing = tag === 'input' || tag === 'textarea' || tag === 'select' || e.target.isContentEditable;
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); palette?.classList.contains('open') ? closePalette() : openPalette(); return; }
        if (e.key === 'Escape') { closePalette(); document.querySelectorAll('.modal.open').forEach(closeModal); document.querySelectorAll('.dropdown.open').forEach((d) => d.classList.remove('open')); }
        if (typing || e.ctrlKey || e.metaKey || e.altKey) return;
        if (e.key === '/') { const s = document.querySelector('[data-page-search]'); if (s) { e.preventDefault(); s.focus(); s.select?.(); } }
        if (e.key === 'g') { gPressed = Date.now(); return; }
        if (Date.now() - gPressed < 900) {
            const map = { h: '/', p: '/programas', m: '/mensajes', d: '/dashboard', r: '/precios', b: '/brochures' };
            const enabled = new Set(pages.map((x) => x.href));
            if (map[e.key]) { location.href = map[e.key]; }
            gPressed = 0;
        }
        if (e.key === '?') { e.preventDefault(); openModal('shortcutsModal'); }
    });

    // ---------- Inputs con botón limpiar ----------
    document.querySelectorAll('.input-icon').forEach((w) => {
        const input = w.querySelector('input'); const clr = w.querySelector('.input-clear');
        if (!input || !clr) return;
        const sync = () => w.classList.toggle('has-value', !!input.value);
        input.addEventListener('input', sync); sync();
        clr.addEventListener('click', () => { input.value = ''; sync(); input.dispatchEvent(new Event('input', { bubbles: true })); input.focus(); });
    });

    // ---------- Contadores animados ----------
    const counters = document.querySelectorAll('[data-count]');
    if (counters.length && 'IntersectionObserver' in window) {
        const io = new IntersectionObserver((entries) => entries.forEach((en) => {
            if (!en.isIntersecting) return;
            io.unobserve(en.target);
            const el = en.target; const target = Number(el.dataset.count) || 0; const fmt = el.dataset.format;
            const t0 = performance.now(); const dur = 900;
            const step = (t) => {
                const p = Math.min((t - t0) / dur, 1); const v = target * (1 - Math.pow(1 - p, 3));
                el.textContent = fmt === 'money' ? money(v) : Math.round(v).toLocaleString('es-CO');
                if (p < 1) requestAnimationFrame(step);
            };
            requestAnimationFrame(step);
        }), { threshold: 0.3 });
        counters.forEach((c) => io.observe(c));
    }

    // ---------- API pública ----------
    window.App = { toast, copyText, track, waLink, openWhatsApp, normalizePhone, escapeHtml, money, normalize, debounce, waFormat, highlight, api, store, openModal, closeModal, toggleTheme, openPalette };
    // Compatibilidad con plantillas anteriores
    window.showToast = toast;
    window.escapeHtml = escapeHtml;
    window.copiarTexto = (id, label) => { const el = document.getElementById(id); if (el) copyText(el.innerText, label || 'Mensaje copiado al portapapeles'); };
    window.toggleSidebar = () => toggleSidebar();
})();
