/* Genera una imagen (PNG) de la homologación Ibero para enviar por WhatsApp. */
(function () {
    'use strict';
    const W = 1080, PAD = 64;
    const C = {
        green: '#c9a03c', green2: '#9a7620', greenSoft: '#f6efdd', ink: '#141b26', text2: '#4a5463', text3: '#8a93a1',
        line: '#e3e6eb', card: '#f6f7f9', pink: '#2e5a9c', pinkSoft: '#e6edf8', dark: '#141b26', white: '#ffffff',
    };
    const DISPLAY = 'Outfit, "Segoe UI", system-ui, sans-serif';
    const BODY = 'Inter, "Segoe UI", system-ui, sans-serif';
    const money = (n) => '$' + Math.round(Number(n) || 0).toLocaleString('es-CO');

    function font(ctx, weight, size, fam) { ctx.font = `${weight} ${size}px ${fam}`; }
    function rr(ctx, x, y, w, h, r) {
        ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r);
        ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
    }
    function wrap(ctx, text, maxW, maxLines = 3) {
        const words = String(text || '').split(/\s+/); const lines = []; let line = '';
        for (const w of words) {
            const t = line ? line + ' ' + w : w;
            if (ctx.measureText(t).width > maxW && line) { lines.push(line); line = w; } else line = t;
        }
        if (line) lines.push(line);
        if (lines.length > maxLines) { const cut = lines.slice(0, maxLines); cut[maxLines - 1] = cut[maxLines - 1].replace(/\s*\S*$/, '') + '…'; return cut; }
        return lines;
    }
    function check(ctx, cx, cy, r, bg, fg) {
        ctx.fillStyle = bg; ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.fill();
        ctx.strokeStyle = fg; ctx.lineWidth = r * 0.22; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
        ctx.beginPath(); ctx.moveTo(cx - r * 0.42, cy + r * 0.02); ctx.lineTo(cx - r * 0.1, cy + r * 0.34); ctx.lineTo(cx + r * 0.45, cy - r * 0.3); ctx.stroke();
    }
    function loadImg(src) {
        return new Promise((res) => { const i = new Image(); i.onload = () => res(i); i.onerror = () => res(null); i.src = src; });
    }

    const H = 1350; // formato 4:5 para que WhatsApp la muestre completa
    const fechaCorta = (t) => String(t || '').replace(/ de (\d{4})$/, ' $1');
    function textoPrecio(p) {
        const pr = p.precio; if (!pr) return null;
        return pr.descuento
            ? `${pr.tipo_descuento === 'SENA' ? 'Precio SENA' : 'Semestre'}: ${money(pr.valor_final)}`
            : `Semestre: ${money(pr.valor)}`;
    }

    function dibujarPrograma(ctx, p, y, R, conPrecio, inicioPropio) {
        const x = PAD, w = W - PAD * 2;
        ctx.fillStyle = C.card; rr(ctx, x, y, w, R, 28); ctx.fill();
        ctx.strokeStyle = C.line; ctx.lineWidth = 2; rr(ctx, x, y, w, R, 28); ctx.stroke();

        // Dona: % de la carrera homologada
        const r = Math.min(R * 0.34, 74), lw = Math.max(12, r * 0.27), cx = x + 34 + r + lw / 2, cy = y + R / 2;
        const pct = Math.max(0, Math.min(100, p.porcentaje || 0));
        ctx.lineCap = 'round'; ctx.lineWidth = lw; ctx.strokeStyle = C.line;
        ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.stroke();
        const g = ctx.createLinearGradient(cx - r, cy - r, cx + r, cy + r); g.addColorStop(0, '#e3c372'); g.addColorStop(1, C.green2);
        ctx.strokeStyle = g; ctx.beginPath(); ctx.arc(cx, cy, r, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * pct / 100); ctx.stroke();
        ctx.textAlign = 'center'; ctx.fillStyle = C.ink; font(ctx, 800, Math.round(r * 0.62), DISPLAY);
        ctx.fillText(`${pct}%`, cx, cy + (r > 60 ? 4 : r * 0.22));
        if (r > 60) { ctx.fillStyle = C.text2; font(ctx, 600, 16, BODY); ctx.fillText('de créditos', cx, cy + 30); }
        ctx.textAlign = 'left';

        // Contenido (bloque centrado verticalmente)
        const x0 = cx + r + lw / 2 + 34, cw = x + w - 32 - x0;
        const cl = (v, a, b) => Math.round(Math.max(a, Math.min(b, v)));
        const nameS = cl(R * 0.2, 25, 32), barH = cl(R * 0.27, 32, 44), txtS = cl(R * 0.14, 17, 21), sp = cl(R * 0.075, 9, 14);
        const B = nameS + sp + barH + sp + txtS;
        let yy = y + (R - B) / 2 + nameS * 0.8;
        ctx.fillStyle = C.ink; font(ctx, 700, nameS, DISPLAY);
        ctx.fillText(wrap(ctx, p.programa_display, cw, 1)[0], x0, yy);
        yy += nameS * 0.2 + sp;

        // Chip de precio a la derecha de la barra
        let chipW = 0; const precio = conPrecio ? textoPrecio(p) : null;
        if (precio) { font(ctx, 700, txtS - 1, BODY); chipW = ctx.measureText(precio).width + 36; }
        const n = Math.max(1, p.total || (p.homologados + p.faltantes)); const gap = 8;
        const barMax = cw - (chipW ? chipW + 20 : 0);
        const size = Math.min(48, (barMax - gap * (n - 1)) / n);
        for (let i = 0; i < n; i++) {
            const sx = x0 + i * (size + gap), done = i < p.homologados;
            ctx.fillStyle = done ? C.green : C.white; rr(ctx, sx, yy, size, barH, 11); ctx.fill();
            if (!done) { ctx.strokeStyle = '#cfd5de'; ctx.lineWidth = 2; rr(ctx, sx, yy, size, barH, 11); ctx.stroke(); }
            ctx.fillStyle = done ? C.white : C.text3; font(ctx, 700, size > 40 ? 16 : 13, BODY); ctx.textAlign = 'center';
            ctx.fillText(`S${i + 1}`, sx + size / 2, yy + barH / 2 + 6); ctx.textAlign = 'left';
        }
        if (precio) {
            const ch = barH, cxp = x + w - 32 - chipW;
            ctx.fillStyle = C.pinkSoft; rr(ctx, cxp, yy, chipW, ch, ch / 2); ctx.fill();
            ctx.fillStyle = C.pink; font(ctx, 700, txtS - 1, BODY); ctx.textBaseline = 'middle';
            ctx.fillText(precio, cxp + 18, yy + ch / 2 + 1); ctx.textBaseline = 'alphabetic';
        }
        yy += barH + sp + txtS * 0.85;

        font(ctx, 800, txtS, BODY); ctx.fillStyle = C.green2; const a = `${p.creditos_homologados} de ${p.creditos_programa} créditos`; ctx.fillText(a, x0, yy);
        let resto = `  ·  ≈${p.faltantes} semestres por cursar`;
        if (inicioPropio && p.inicio) resto += `  ·  ${p.inicio}`;
        font(ctx, 600, txtS, BODY); ctx.fillStyle = C.text2; ctx.fillText(resto, x0 + ctx.measureText(a).width + 4, yy);
    }

    async function generar({ titulo, programas, nombre, conPrecio, cfg }) {
        try { await Promise.all(['800 56px Outfit', '700 32px Outfit', '600 22px Inter', '700 22px Inter', '800 22px Inter'].map((f) => document.fonts.load(f))); } catch (e) { /* fuentes del sistema */ }
        const logo = await loadImg('/logo.jpg');
        const cv = document.createElement('canvas'); cv.width = W; cv.height = H;
        const ctx = cv.getContext('2d');
        ctx.fillStyle = C.white; ctx.fillRect(0, 0, W, H);

        const n = programas.length;
        const inicios = [...new Set(programas.map((p) => p.inicio).filter(Boolean))];
        const inicioComun = inicios.length === 1 ? inicios[0] : null;
        const ahorro = conPrecio ? Math.max(0, ...programas.map((p) => (p.precio && p.precio.ahorro_total) || 0)) : 0;

        // ---- Encabezado
        font(ctx, 800, 50, DISPLAY);
        const head = wrap(ctx, 'Tu título SENA te acerca a tu carrera profesional', W - PAD * 2, 2);
        const heroH = 168 + (nombre ? 40 : 0) + head.length * 58 + 24 + 52 + 38;
        const hg = ctx.createLinearGradient(0, 0, W, heroH); hg.addColorStop(0, '#2c3a52'); hg.addColorStop(1, '#141b26');
        ctx.fillStyle = hg; ctx.fillRect(0, 0, W, heroH);
        ctx.save(); ctx.globalAlpha = 0.12; ctx.fillStyle = C.white; ctx.beginPath(); ctx.arc(W - 70, 40, 230, 0, Math.PI * 2); ctx.fill(); ctx.restore();
        ctx.fillStyle = C.white; rr(ctx, PAD, 50, 88, 88, 22); ctx.fill();
        if (logo) ctx.drawImage(logo, PAD + 12, 62, 64, 64);
        ctx.fillStyle = C.white; font(ctx, 800, 40, DISPLAY); ctx.fillText('Ibero', PAD + 112, 92);
        ctx.globalAlpha = 0.88; font(ctx, 600, 20, BODY); ctx.fillText('Homologación para egresados SENA · 100% virtual', PAD + 112, 124); ctx.globalAlpha = 1;
        let y = 196;
        if (nombre) { font(ctx, 600, 28, BODY); ctx.fillText(`¡Hola, ${nombre}!`, PAD, y); y += 40; }
        font(ctx, 800, 50, DISPLAY); head.forEach((l) => { ctx.fillText(l, PAD, y + 44); y += 58; });
        y += 24;
        font(ctx, 600, 17, BODY); const lbl = 'TU TÍTULO'; const lw0 = ctx.measureText(lbl).width;
        font(ctx, 700, 23, BODY); const t1 = wrap(ctx, titulo, W - PAD * 2 - lw0 - 76, 1)[0];
        const pillW = Math.min(W - PAD * 2, lw0 + ctx.measureText(t1).width + 76);
        ctx.fillStyle = 'rgba(255,255,255,0.2)'; rr(ctx, PAD, y, pillW, 52, 26); ctx.fill();
        ctx.fillStyle = C.white; ctx.globalAlpha = 0.8; font(ctx, 700, 17, BODY); ctx.fillText(lbl, PAD + 26, y + 33); ctx.globalAlpha = 1;
        font(ctx, 700, 23, BODY); ctx.fillText(t1, PAD + 26 + lw0 + 20, y + 34);

        // ---- Zonas fijas de abajo hacia arriba
        const pieH = 104, pieY = H - pieH;
        const conBeneficios = n < 4; // con 4 carreras se omiten para dar espacio
        const benY = conBeneficios ? pieY - 30 - 56 : pieY;
        const banda = ahorro || inicioComun;
        const bandaY = benY - 26 - 104;
        const progEnd = (banda ? bandaY : benY) - 26;

        // ---- Programas
        y = heroH + 52;
        ctx.fillStyle = C.ink; font(ctx, 800, 32, DISPLAY);
        ctx.fillText(n > 1 ? `Puedes homologar en ${n} carreras` : 'Puedes homologar en esta carrera', PAD, y);
        y += 26;
        const gapP = n >= 4 ? 12 : 14, disp = progEnd - y;
        const R = Math.min(220, (disp - gapP * (n - 1)) / n);
        y += (disp - (R * n + gapP * (n - 1))) / 2;
        programas.forEach((p) => { dibujarPrograma(ctx, p, y, R, conPrecio, !inicioComun); y += R + gapP; });

        // ---- Banda: ahorro e inicio de clases
        if (banda) {
            const bw = W - PAD * 2;
            const ag = ctx.createLinearGradient(PAD, 0, W - PAD, 0); ag.addColorStop(0, C.pink); ag.addColorStop(1, '#4f7fc4');
            ctx.fillStyle = ag; rr(ctx, PAD, bandaY, bw, 104, 28); ctx.fill();
            ctx.fillStyle = C.white;
            const col = (bx, label, value) => {
                ctx.globalAlpha = 0.9; font(ctx, 600, 20, BODY); ctx.fillText(label, bx, bandaY + 40); ctx.globalAlpha = 1;
                font(ctx, 800, 36, DISPLAY); ctx.fillText(value, bx, bandaY + 82);
            };
            if (ahorro && inicioComun) {
                col(PAD + 34, 'Ahorro estimado', `Hasta ${money(ahorro)}`);
                ctx.globalAlpha = 0.35; ctx.fillRect(PAD + bw * 0.55, bandaY + 22, 2, 60); ctx.globalAlpha = 1;
                col(PAD + bw * 0.55 + 32, 'Cohorte', fechaCorta(inicioComun));
            } else if (ahorro) col(PAD + 34, 'Ahorro estimado frente al valor regular', `Hasta ${money(ahorro)}`);
            else col(PAD + 34, 'Cohorte', fechaCorta(inicioComun));
        }

        // ---- Beneficios
        const ben = conBeneficios ? ['100% virtual', 'Descuento SENA durante toda la carrera', 'Pronto pago en el primer periodo'] : [];
        const colW = (W - PAD * 2) / 3;
        ben.forEach((b, i) => {
            const bx = PAD + i * colW; check(ctx, bx + 20, benY + 26, 20, C.green, C.white);
            ctx.fillStyle = C.ink; font(ctx, 700, 19, BODY);
            const ls = wrap(ctx, b, colW - 64, 2);
            ls.forEach((l, j) => ctx.fillText(l, bx + 52, benY + 33 - (ls.length - 1) * 12 + j * 24));
        });

        // ---- Pie
        ctx.fillStyle = C.dark; ctx.fillRect(0, pieY, W, pieH);
        ctx.fillStyle = C.green; ctx.fillRect(0, pieY, W, 6);
        ctx.fillStyle = C.white; font(ctx, 800, 30, DISPLAY); ctx.fillText('¡Escríbeme y empieza tu carrera!', PAD, pieY + 50);
        ctx.globalAlpha = 0.7; font(ctx, 500, 19, BODY);
        const pie = [cfg && cfg.asesor ? `Tu asesor: ${cfg.asesor}` : 'Corporación Universitaria Iberoamericana', 'Valores por semestre'].join('  ·  ');
        ctx.fillText(pie, PAD, pieY + 82); ctx.globalAlpha = 1;
        return cv;
    }

    window.ImagenHomologacion = { generar };
})();
