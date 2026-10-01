/*
 * packaging/compilar_web.mjs — Deja la piel web lista para el instalador (SOLO en la copia que se empaqueta).
 *
 * Desde el código, ui_kits/lune-desktop/index.html trae Babel y traduce los .jsx en el navegador en
 * CADA arranque: cómodo para tocar la interfaz (guardas y recargas), pero cuesta. Para el instalador:
 *   · los .jsx se traducen UNA vez aquí, con el mismo Babel vendorizado y las mismas opciones que
 *     <script type="text/babel"> (las de tests/js/jsx_falso.mjs), a un .js al lado de cada uno;
 *   · cada <script type="text/babel"> pasa a <script defer src="….js">: los defer se ejecutan en el
 *     orden del documento cuando el HTML ya está leído, como hacía Babel (el módulo vrm_barra.js, que
 *     va antes en el documento, sigue ejecutándose antes);
 *   · el bloque en línea (el que monta <LuneApp/>) va a arranque.js, también con defer;
 *   · no se carga babel.min.js (3 MB que el navegador leía y compilaba en cada arranque) ni sus
 *     respaldos del CDN, y React/ReactDOM usan sus builds de producción (ui_web/vendor/*.production.min.js).
 *
 * Uso:   node packaging/compilar_web.mjs <carpeta ui_web de la COPIA a empaquetar>
 * Nunca se ejecuta sobre el repo: packaging/construir.py le pasa la copia en build/.
 * Sale con código 1 si algo no se pudo traducir (el build se para).
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const AQUI = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(AQUI, '..');

export const OPCIONES = {
  presets: ['react', 'env'],
  plugins: ['transform-class-properties', 'transform-object-rest-spread', 'transform-flow-strip-types'],
};

export function cargarBabel(rutaBabel) {
  const src = fs.readFileSync(rutaBabel, 'utf8');
  const m = { exports: {} };
  new Function('module', 'exports', 'self', 'window', src)(m, m.exports, {}, {});
  if (!m.exports || typeof m.exports.transform !== 'function') throw new Error('no pude cargar Babel standalone');
  return m.exports;
}

const RE_BABEL_SRC = /<script\s+type="text\/babel"\s+src="([^"]+\.jsx)"\s*><\/script>/g;
const RE_BABEL_INLINE = /<script\s+type="text\/babel"\s*>([\s\S]*?)<\/script>/g;
const RE_VENDOR = /<script\s+src="([^"]*vendor\/)(react|react-dom)\.development\.js"\s*><\/script>/g;
const RE_BABEL_TAG = /[ \t]*<script\s+src="[^"]*vendor\/babel\.min\.js"\s*><\/script>[ \t]*\r?\n?/g;
// Los respaldos del CDN (document.write de unpkg si falta vendor/): instalado, vendor/ siempre está.
const RE_RESPALDO = /[ \t]*<script>\s*window\.(React|ReactDOM|Babel)\s*\|\|\s*document\.write\([\s\S]*?\);\s*<\/script>[ \t]*\r?\n?/g;

/** Traduce el HTML `rutaHtml` (y sus .jsx) en su sitio. Devuelve {html, jsx: [rutas traducidas]}. */
export function compilarHtml(rutaHtml, babel) {
  const dir = path.dirname(rutaHtml);
  let html = fs.readFileSync(rutaHtml, 'utf8');
  const hechos = [];
  const traducir = (codigo, nombre) => babel.transform(codigo, { ...OPCIONES, filename: nombre, sourceType: 'script' }).code;

  html = html.replace(RE_BABEL_SRC, (_, src) => {
    const origen = path.join(dir, src);
    const destino = origen.replace(/\.jsx$/, '.js');
    fs.writeFileSync(destino, traducir(fs.readFileSync(origen, 'utf8'), src), 'utf8');
    hechos.push(path.relative(dir, origen));
    return `<script defer src="${src.replace(/\.jsx$/, '.js')}"></script>`;
  });
  let n = 0;
  html = html.replace(RE_BABEL_INLINE, (_, codigo) => {
    const nombre = n === 0 ? 'arranque.js' : `arranque_${n}.js`;
    n += 1;
    fs.writeFileSync(path.join(dir, nombre), traducir(codigo, nombre), 'utf8');
    hechos.push(`(en línea) → ${nombre}`);
    return `<script defer src="${nombre}"></script>`;
  });
  html = html.replace(RE_RESPALDO, '');
  html = html.replace(RE_BABEL_TAG, '');
  html = html.replace(RE_VENDOR, (_, base, lib) => `<script src="${base}${lib}.production.min.js"></script>`);
  if (/<script[^>]*type="text\/babel"/.test(html)) throw new Error(`${rutaHtml}: queda un <script type="text/babel"> sin traducir`);
  if (/<script[^>]*src="[^"]*vendor\/babel\.min\.js"/.test(html)) throw new Error(`${rutaHtml}: sigue cargando babel.min.js`);
  if (/<script[^>]*src="[^"]*\.development\.js"/.test(html)) throw new Error(`${rutaHtml}: sigue cargando React de desarrollo`);
  fs.writeFileSync(rutaHtml, html, 'utf8');
  return { html, jsx: hechos };
}

function main() {
  const uiWeb = path.resolve(process.argv[2] || '');
  if (!process.argv[2] || !fs.existsSync(path.join(uiWeb, 'ui_kits'))) {
    console.error('Uso: node packaging/compilar_web.mjs <carpeta ui_web de la copia>');
    process.exit(2);
  }
  if (path.resolve(uiWeb) === path.join(REPO, 'ui_web')) {
    console.error('No: esto reescribe los HTML. Pásale la COPIA de ui_web (build/…), nunca la del repo.');
    process.exit(2);
  }
  const babel = cargarBabel(path.join(uiWeb, 'vendor', 'babel.min.js'));
  const paginas = [path.join(uiWeb, 'ui_kits', 'lune-desktop', 'index.html')];
  let total = 0;
  for (const p of paginas) {
    const { jsx } = compilarHtml(p, babel);
    total += jsx.length;
    console.log(`${path.relative(uiWeb, p)}: ${jsx.length} bloques traducidos`);
  }
  for (const f of ['babel.min.js', 'react.development.js', 'react-dom.development.js']) {
    fs.rmSync(path.join(uiWeb, 'vendor', f), { force: true });
  }
  console.log(`listo: ${total} bloques; vendor sin Babel ni React de desarrollo`);
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    main();
  } catch (e) {
    console.error(String(e && e.stack || e));
    process.exit(1);
  }
}
