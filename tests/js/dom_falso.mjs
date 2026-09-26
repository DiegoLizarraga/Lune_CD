// tests/js/dom_falso.mjs — DOM y temporizador de mentira para los tests de la mascota
// animada (anim_video.test.mjs, anim_fisica.test.mjs). No es un test: node --test solo
// ejecuta los *.test.mjs y test_js_modulos.py lanza solo esos.

/** Elemento falso con lo que usan lune_anim_video.js y lune_anim_fisica.js. */
export function crearElemento(tag = 'div', id = '') {
  const attrs = new Map();
  const clases = new Set();
  const oyentes = {};
  const el = {
    tagName: String(tag).toUpperCase(), id, children: [], parentNode: null, textContent: '',
    style: { props: {}, setProperty(k, v) { this.props[k] = v; } },
    classList: {
      add: (c) => clases.add(c),
      remove: (c) => clases.delete(c),
      contains: (c) => clases.has(c),
    },
    get className() { return [...clases].join(' '); },
    set className(v) { clases.clear(); String(v).split(/\s+/).filter(Boolean).forEach((c) => clases.add(c)); },
    getAttribute: (k) => (attrs.has(k) ? attrs.get(k) : null),
    setAttribute: (k, v) => { attrs.set(k, String(v)); },
    removeAttribute: (k) => { attrs.delete(k); },
    hasAttribute: (k) => attrs.has(k),
    addEventListener(t, f) { (oyentes[t] || (oyentes[t] = new Set())).add(f); },
    removeEventListener(t, f) { if (oyentes[t]) oyentes[t].delete(f); },
    /** Dispara un evento ('canplay', 'error'…) a los oyentes registrados. */
    disparar(t) { for (const f of [...(oyentes[t] || [])]) f({ type: t, target: el }); },
    oyentes: (t) => (oyentes[t] ? oyentes[t].size : 0),
    // <video>
    cargas: 0, reproducciones: 0, pausas: 0, playbackRate: 1, defaultPlaybackRate: 1, onerror: null,
    load() { el.cargas += 1; },
    play() { el.reproducciones += 1; return Promise.resolve(); },
    pause() { el.pausas += 1; },
    // árbol
    appendChild(c) { c.parentNode = el; el.children.push(c); return c; },
    replaceChildren(...nodos) {
      for (const c of el.children) c.parentNode = null;
      el.children = [];
      for (const n of nodos) el.appendChild(n);
    },
    /** innerHTML no se interpreta: se apunta en htmlCrudo (los tests comprueban que nadie lo use con datos). */
    get innerHTML() { return el.htmlCrudo === undefined ? '' : el.htmlCrudo; },
    set innerHTML(v) { el.htmlCrudo = String(v); },
    insertBefore(c, ref) {
      c.parentNode = el;
      const i = ref ? el.children.indexOf(ref) : -1;
      if (i < 0) el.children.push(c); else el.children.splice(i, 0, c);
      return c;
    },
    /** Solo '.clase' y 'etiqueta', en profundidad. */
    querySelector(sel) {
      const cumple = (n) => (sel.startsWith('.') ? n.classList.contains(sel.slice(1)) : n.tagName === sel.toUpperCase());
      const buscar = (n) => {
        for (const h of n.children) {
          if (cumple(h)) return h;
          const r = buscar(h);
          if (r) return r;
        }
        return null;
      };
      return buscar(el);
    },
  };
  return el;
}

/** document falso: createElement y getElementById sobre `raiz`. */
export function crearDocumento(raiz = null) {
  const doc = {
    creados: [],
    createElement(tag) { const e = crearElemento(tag); e.ownerDocument = doc; doc.creados.push(e); return e; },
    getElementById(id) {
      const buscar = (n) => {
        if (!n) return null;
        if (n.id === id) return n;
        for (const h of n.children) { const r = buscar(h); if (r) return r; }
        return null;
      };
      return buscar(raiz);
    },
  };
  return doc;
}

/** Temporizador virtual: setTimeout/clearTimeout que solo avanzan con avanzar(ms). */
export function crearTemporizador() {
  let ahora = 0;
  let sig = 1;
  const tareas = new Map();
  return {
    setTimeout(f, ms) { const id = sig++; tareas.set(id, { f, t: ahora + Math.max(0, Number(ms) || 0) }); return id; },
    clearTimeout(id) { tareas.delete(id); },
    avanzar(ms) {
      const fin = ahora + ms;
      for (;;) {
        let prox = null;
        for (const [id, x] of tareas) if (x.t <= fin && (!prox || x.t < prox[1].t)) prox = [id, x];
        if (!prox) break;
        tareas.delete(prox[0]);
        ahora = prox[1].t;
        prox[1].f();
      }
      ahora = fin;
    },
    get ahora() { return ahora; },
    pendientes: () => tareas.size,
  };
}
