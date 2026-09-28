// tests/js/sentarse.test.mjs — módulo 'sentarse' del VRM (ui_web/vrm/lune_sentarse.js,
// corte 7): poses puras de las 4 variantes y la barra, la mezcla (≈88 % en 0.35 s), la
// sustitución de piernas y brazos, encuadre de cuerpo entero, inhibe/ocupado, est.sentada,
// los pies (trasPose), la medida del asiento con la pose completa y, con el motor de
// verdad y matrices (VRM 1.0 y 0.x), brazos SIEMPRE abajo y muslos hacia delante.
// Al final, la página (companion_vrm.html): lo pedido antes de cargar se repite.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';

import {
  montar, correr, quietaSinIdles, vaciarCola, brazoMundo, matEuler, lienzoFalso, scriptsEnLinea,
  reescribirImports, aDataURL, DATA_MOTOR, UI, frames, cargas, crearVRMFalso,
} from './motor_vrm_falso.mjs';
import { crearElemento, crearDocumento } from './dom_falso.mjs';
import {
  instalar, poseSentada, aplicarSentada, medirAsiento, modoValido, varianteValida,
  NOMBRE, ORDEN, MODOS, VARIANTES_VENTANA, PIERNAS, BRAZOS, PARAMS_SENTARSE,
} from '../../ui_web/vrm/lune_sentarse.js';

const DT = 1 / 60;
const cerca = (a, b, tol, msg) => assert.ok(Math.abs(a - b) <= tol, `${msg ?? ''} ${a} ≉ ${b} (±${tol})`);
const TODAS = [...Array.from({ length: VARIANTES_VENTANA }, (_, v) => ['ventana', v]), ['barra', 0]];

function mul(A, B) { return A.map((f) => [0, 1, 2].map((j) => f[0] * B[0][j] + f[1] * B[1][j] + f[2] * B[2][j])); }
const aplicar = (A, v) => A.map((f) => f[0] * v[0] + f[1] * v[1] + f[2] * v[2]);
/** Dirección del muslo en el MUNDO (con las caderas), VRM 1.0 y 0.x (rig girado 180°). */
function musloMundo(vrm, lado, version) {
  const d = aplicar(mul(matEuler(vrm.huesos.hips.rotation), matEuler(vrm.huesos[lado + 'UpperLeg'].rotation)), [0, -1, 0]);
  return version === '0' ? [-d[0], d[1], -d[2]] : d;
}

// ── Lógica pura ────────────────────────────────────────────────────────────────

test('4 variantes de ventana y la barra: poses finitas, con todas las claves y brazos abajo en la pose', () => {
  assert.equal(NOMBRE, 'sentarse');
  assert.equal(ORDEN, 85);
  assert.deepEqual([...MODOS], ['ventana', 'barra']);
  for (const [modo, v] of TODAS) {
    for (const t of [null, 0, 0.37, 1.1, 2.9]) {
      const p = poseSentada(modo, v, t);
      for (const h of [...PIERNAS, ...BRAZOS, 'hips', 'spine', 'leftFoot', 'rightFoot']) {
        assert.ok(Array.isArray(p[h]) && p[h].length === 3, `${modo} ${v}: falta ${h}`);
        for (const x of p[h]) assert.ok(Number.isFinite(x) && Math.abs(x) <= 1.8, `${modo} ${v} ${h} = ${x}`);
      }
      // muslos adelante (x < −1.2) y rodillas dobladas (x > +1.1)
      assert.ok(p.leftUpperLeg[0] < -1.2 && p.rightUpperLeg[0] < -1.2, `${modo} ${v}: muslos adelante`);
      assert.ok(p.leftLowerLeg[0] > 1.1 && p.rightLowerLeg[0] > 1.1, `${modo} ${v}: rodillas dobladas`);
      // el brazo baja (z del izquierdo muy negativo, del derecho muy positivo)
      assert.ok(p.leftUpperArm[2] < -1.2 && p.rightUpperArm[2] > 1.2, `${modo} ${v}: brazos caídos`);
    }
  }
  assert.equal(modoValido(' Barra '), 'barra');
  assert.equal(modoValido('constructor'), null);
  assert.equal(varianteValida('ventana', 9), 3);
  assert.equal(varianteValida('ventana', -2), 0);
  assert.equal(varianteValida('ventana', 'x'), 0);
  assert.equal(varianteValida('barra', 3), 0);
  assert.deepEqual(poseSentada('no', 7), poseSentada('ventana', 3), 'desconocido → ventana (variante acotada)');
});

test('las variantes 3 y barra balancean las piernas (alternas); las demás están quietas', () => {
  const amp = (modo, v) => {
    let min = Infinity, max = -Infinity, suma = Infinity;
    for (let t = 0; t < 4; t += 0.02) {
      const p = poseSentada(modo, v, t);
      min = Math.min(min, p.leftLowerLeg[0]); max = Math.max(max, p.leftLowerLeg[0]);
      suma = Math.min(suma, Math.abs(p.leftLowerLeg[0] + p.rightLowerLeg[0] - 2 * poseSentada(modo, v, null).leftLowerLeg[0]));
    }
    return { amp: (max - min) / 2, alternas: suma < 1e-9 };
  };
  const v3 = amp('ventana', 3), barra = amp('barra', 0);
  cerca(v3.amp, PARAMS_SENTARSE.balanceoRad, 0.01, 'variante 3 ±0.18');
  cerca(barra.amp, PARAMS_SENTARSE.barraRad, 0.01, 'barra ±0.12');
  assert.ok(v3.alternas && barra.alternas, 'una pierna adelante y la otra atrás');
  for (const v of [0, 1, 2]) assert.equal(amp('ventana', v).amp, 0, `variante ${v} quieta`);
  // frecuencias: 0.5 Hz y 0.35 Hz (medio periodo = cambio de signo)
  cerca(poseSentada('ventana', 3, 0.5).leftLowerLeg[0] - poseSentada('ventana', 3, null).leftLowerLeg[0], PARAMS_SENTARSE.balanceoRad, 1e-9);
  cerca(poseSentada('barra', 0, 1 / (4 * 0.35)).leftLowerLeg[0] - poseSentada('barra', 0, null).leftLowerLeg[0], PARAMS_SENTARSE.barraRad, 1e-9);
});

test('aplicarSentada: piernas y brazos se SUSTITUYEN (un idle que sube los brazos no sube nada); caderas y columna se suman', () => {
  const idle = {
    leftUpperArm: [0.4, 0.2, 1.6], rightUpperArm: [0.4, -0.2, -1.6], leftLowerArm: [0, 0, 1.2], rightLowerArm: [0, 0, -1.2],
    leftUpperLeg: [0.3, 0, 0.2], hips: [0.05, 0.1, 0], spine: [0.02, 0, 0],
  };
  const pose = poseSentada('ventana', 0);
  const out = aplicarSentada(structuredClone(idle), pose, 1);
  for (const h of [...PIERNAS, ...BRAZOS]) assert.deepEqual(out[h], pose[h], `${h} sustituido`);
  cerca(out.hips[0], 0.05 + pose.hips[0], 1e-12, 'caderas sumadas');
  cerca(out.hips[1], 0.1, 1e-12);
  cerca(out.spine[0], 0.02 + pose.spine[0], 1e-12, 'columna sumada');
  // a medias
  const mitad = aplicarSentada(structuredClone(idle), pose, 0.5);
  cerca(mitad.leftUpperArm[2], (1.6 + pose.leftUpperArm[2]) / 2, 1e-12);
  // brazos con otro peso (un gesto que usa los brazos)
  const gesto = aplicarSentada(structuredClone(idle), pose, 1, 0);
  assert.deepEqual(gesto.leftUpperArm, idle.leftUpperArm, 'wBrazos 0: el gesto manda en los brazos');
  assert.deepEqual(gesto.leftUpperLeg, pose.leftUpperLeg, '…pero las piernas siguen sentadas');
  assert.deepEqual(aplicarSentada({ a: 1 }, pose, 0), { a: 1 }, 'w = 0 no toca nada');
});

// ── Módulo con un ctx falso ────────────────────────────────────────────────────

function modulo() {
  const encuadres = [], eventos = [];
  const camera = { position: { x: 0, y: 1, z: 2 } };
  const est = { gesto: 'normal', gestoPeso: 0, baile: false, grande: false, sentada: false };
  const pies = { leftFoot: { rotation: { x: 0, y: 0, z: 0, set(a, b, c) { this.x = a; this.y = b; this.z = c; } } },
    rightFoot: { rotation: { x: 0, y: 0, z: 0, set(a, b, c) { this.x = a; this.y = b; this.z = c; } } } };
  let sXZ = 1;
  const ctx = {
    camera, emitir: (t, d) => eventos.push([t, d]), estado: () => est,
    encuadrar: (modo, temporal) => {
      encuadres.push([modo, temporal]);
      camera.position.y = modo === 'cuerpo' ? 0.8 : 1;           // cambia la cámara como el motor
      return modo;
    },
    vrm: () => ({ humanoid: { getNormalizedBoneNode: (h) => pies[h] || null } }),
    get sXZ() { return sXZ; },
  };
  const mod = instalar(ctx);
  let t = 0;
  const pasos = (seg, extra = null) => {
    let out = {};
    for (let i = 0, n = Math.round(seg / DT); i < n; i++) {
      t += DT;
      out = { leftUpperArm: [0, 0, -1.15], rightUpperArm: [0, 0, 1.15] };
      if (extra) extra(out);
      mod.pose(out, DT, t, est);
      mod.trasPose(DT, t, est);
    }
    return out;
  };
  return { mod, ctx, est, camera, encuadres, eventos, pies, pasos, setSXZ: (s) => { sXZ = s; } };
}

test('mezcla ≈88 % en 0.35 s, inhibe/ocupado, est.sentada y encuadre de cuerpo entero (temporal) hasta que w vuelve a 0', () => {
  const { mod, est, encuadres, eventos, pasos } = modulo();
  assert.equal(mod.ocupado(est), false);
  assert.deepEqual(mod.inhibe(est), { idle: 1 });
  assert.equal(mod.api.sentar('ventana', 2), null, 'sin modelo no hay medida');
  assert.deepEqual(encuadres, [['cuerpo', true]], 'encuadre en la misma llamada');
  assert.equal(est.sentada, 'ventana');
  assert.deepEqual(eventos, [['sentada', { modo: 'ventana', variante: 2 }]]);
  pasos(0.35);
  const w = mod.api.estado().peso;
  cerca(w, 1 - Math.exp(-6 * 0.35), 0.01, 'mezcla a 0.35 s');
  assert.ok(w > 0.86 && w < 0.9);
  assert.equal(mod.ocupado(est), true, 'mientras 0 < w < 1');
  cerca(mod.inhibe(est).idle, 1 - 0.65 * w, 1e-9);
  pasos(2);
  assert.equal(mod.api.estado().peso, 1);
  assert.equal(mod.ocupado(est), false);
  cerca(mod.inhibe(est).idle, 0.35, 1e-9);
  assert.equal(mod.api.levantar(), true);
  assert.equal(mod.api.levantar(), false, 'ya de pie');
  assert.equal(est.sentada, 'ventana', 'le queda peso: sigue marcada mientras se funde');
  pasos(0.2);
  assert.equal(encuadres.length, 1, 'el encuadre sigue mientras se funde');
  pasos(2);
  assert.equal(mod.api.estado().peso, 0);
  assert.equal(est.sentada, false);
  assert.deepEqual(encuadres, [['cuerpo', true], [null, undefined]], 'al acabar, el encuadre del usuario');
  assert.deepEqual(mod.inhibe(est), { idle: 1 });
});

test('encuadre: si otro lo cambia estando sentada se vuelve a poner; con el baile en marcha no se suelta; en grande no pelea', () => {
  const { mod, est, camera, encuadres, pasos } = modulo();
  mod.api.sentar('barra');
  pasos(1);
  assert.equal(encuadres.length, 1);
  camera.position.y = 1.3;                         // el baile que se funde llamó encuadrar(null)
  pasos(DT);
  assert.deepEqual(encuadres.at(-1), ['cuerpo', true], 'vuelve a cuerpo entero');
  const n = encuadres.length;
  est.grande = true; camera.position.z = 5;        // pantalla grande mueve la cámara cada frame
  pasos(0.5);
  assert.equal(encuadres.length, n, 'en grande no se toca la cámara');
  est.grande = false;
  // se levanta con el baile ya en marcha: el encuadre de cuerpo entero es del baile
  est.baile = true;
  mod.api.levantar();
  pasos(3);
  assert.equal(mod.api.estado().peso, 0);
  assert.ok(!encuadres.slice(n).some(([m]) => m === null), 'no suelta el encuadre del baile');
  assert.equal(mod.api.estado().encuadrado, false);
});

test('los brazos siguen el gesto solo si el gesto usa los brazos (wave sí, happy no)', () => {
  const { mod, est, pasos } = modulo();
  mod.api.sentar('ventana', 0);
  pasos(3);
  const pose = poseSentada('ventana', 0);
  const alzado = (o) => { o.rightUpperArm = [0, 0, -2.2]; };
  est.gesto = 'happy'; est.gestoPeso = 1;
  assert.deepEqual(pasos(DT, alzado).rightUpperArm, pose.rightUpperArm, 'happy: brazos sentados');
  est.gesto = 'wave';
  assert.deepEqual(pasos(DT, alzado).rightUpperArm, [0, 0, -2.2], 'wave: se ve el saludo');
  est.gestoPeso = 0.5;
  cerca(pasos(DT, alzado).rightUpperArm[2], (-2.2 + pose.rightUpperArm[2]) / 2, 1e-9);
});

test('pies: trasPose los pone × w con el signo del rig y vuelven a identidad al acabar y en alDescargar', () => {
  const { mod, pies, pasos, setSXZ } = modulo();
  setSXZ(-1);
  mod.api.sentar('ventana', 1);
  pasos(3);
  const p = poseSentada('ventana', 1).leftFoot;
  cerca(pies.leftFoot.rotation.x, -p[0], 1e-9, 'x × sXZ');
  mod.api.levantar();
  pasos(3);
  assert.deepEqual([pies.leftFoot.rotation.x, pies.leftFoot.rotation.y, pies.leftFoot.rotation.z], [0, 0, 0]);
  mod.api.sentar('barra');
  pasos(1);
  assert.notEqual(pies.rightFoot.rotation.x, 0);
  mod.alDescargar();
  assert.deepEqual([pies.rightFoot.rotation.x, pies.rightFoot.rotation.y, pies.rightFoot.rotation.z], [0, 0, 0]);
});

test('cambiar de variante sentada funde de una a otra (sin saltos)', () => {
  const { mod, pasos } = modulo();
  mod.api.sentar('ventana', 0);
  pasos(3);
  const a = poseSentada('ventana', 0).leftUpperArm[1], b = poseSentada('ventana', 1).leftUpperArm[1];
  mod.api.sentar('ventana', 1);
  assert.equal(mod.api.estado().variante, 1);
  const y1 = pasos(DT).leftUpperArm[1];
  assert.ok(Math.abs(y1 - a) < Math.abs(b - a) * 0.2, 'el primer frame sigue casi en la anterior');
  assert.equal(mod.ocupado(), true, 'fundiendo');
  const y2 = pasos(2).leftUpperArm[1];
  cerca(y2, b, 1e-9);
  assert.equal(mod.ocupado(), false);
});

// ── Con el motor de verdad ─────────────────────────────────────────────────────

/** Módulo falso de idle que sube los brazos por encima de la cabeza (lo que la sustitución anula). */
const idleBrazosArriba = () => ({
  nombre: 'idleArriba', orden: 20,
  pose(out) {
    out.leftUpperArm = [0, 0, 1.6]; out.rightUpperArm = [0, 0, -1.6];
    out.leftLowerArm = [0, 0, 1.0]; out.rightLowerArm = [0, 0, -1.0];
  },
});

test('en el motor (VRM 1.0 y 0.x): en todas las variantes la mano queda bajo el hombro y el pecho y los muslos van hacia delante', () => {
  for (const version of ['1', '0']) {
    const { m, vrm, est } = montar({ version });
    quietaSinIdles(m);
    m.registrar(idleBrazosArriba);
    correr(0.2);
    const sube = brazoMundo(vrm, 'left', version);
    assert.ok(sube.mano[1] > 0.5, `el idle falso sube el brazo (VRM ${version})`);
    const mod = m.registrar(instalar);
    assert.equal(mod.nombre, 'sentarse');
    for (const [modo, v] of TODAS) {
      m.mod('sentarse', 'sentar', modo, v);
      correr(2);
      assert.equal(m.mod('sentarse', 'estado').peso, 1, `${modo} ${v}: sentada del todo`);
      assert.equal(est.sentada, modo);
      cerca(est.inh.idle, 0.35, 1e-6, 'los idles bajan');
      correr(2.5, null, () => {
        for (const lado of ['left', 'right']) {
          const b = brazoMundo(vrm, lado, version);
          assert.ok(b.codo[1] < -0.8, `${modo} ${v} (VRM ${version}): codo ${lado} alto (${b.codo[1].toFixed(2)})`);
          assert.ok(b.mano[1] < -1.2, `${modo} ${v} (VRM ${version}): mano ${lado} sobre el pecho (${b.mano[1].toFixed(2)})`);
          // hacia el centro solo por delante del cuerpo (nada de atravesarlo)
          const haciaDentro = lado === 'left' ? -b.mano[0] : b.mano[0];
          if (haciaDentro > 0) assert.ok(b.mano[2] > 0.5, `${modo} ${v}: mano ${lado} por detrás`);
          const muslo = musloMundo(vrm, lado, version);
          assert.ok(muslo[2] > 0.9, `${modo} ${v} (VRM ${version}): muslo ${lado} hacia delante (${muslo.map((x) => x.toFixed(2))})`);
        }
      });
    }
    // se levanta: vuelve el idle falso (brazos arriba) y los muslos abajo
    m.mod('sentarse', 'sentar', null);
    m.mod('sentarse', 'levantar');
    correr(2);
    assert.equal(est.sentada, false);
    assert.ok(brazoMundo(vrm, 'left', version).mano[1] > 0.5, 'de pie manda otra vez el idle');
    assert.ok(musloMundo(vrm, 'left', version)[1] < -0.9, 'de pie, piernas abajo');
    m.destruir();
  }
});

test('en el motor: sentar() mide con la pose sentada completa y deja las rotaciones como estaban; wave se sigue viendo', () => {
  for (const version of ['1', '0']) {
    const { m, vrm } = montar({ version });
    quietaSinIdles(m);
    const s = version === '0' ? -1 : 1;
    const antes = Object.fromEntries(Object.entries(vrm.huesos).map(([h, n]) => [h, [n.rotation.x, n.rotation.y, n.rotation.z]]));
    const vistas = [];
    const orig = vrm.huesos.hips.getWorldPosition.bind(vrm.huesos.hips);
    vrm.huesos.hips.getWorldPosition = (v) => {
      vistas.push([vrm.huesos.leftUpperLeg.rotation.x, vrm.huesos.rightLowerLeg.rotation.x, vrm.huesos.hips.rotation.x]);
      return orig(v);
    };
    m.registrar(instalar);
    const p = m.mod('sentarse', 'sentar', 'ventana', 0);
    assert.ok(p && Number.isFinite(p.asiento.x) && Number.isFinite(p.asiento.y) && Number.isFinite(p.sonda.y), JSON.stringify(p));
    const pose = poseSentada('ventana', 0);
    assert.ok(vistas.length >= 1, 'midió');
    const [ul, ll, hi] = vistas.at(-1);
    cerca(ul, pose.leftUpperLeg[0] * s, 1e-12, 'muslo al 100 % al medir');
    cerca(ll, pose.rightLowerLeg[0] * s, 1e-12, 'espinilla al 100 %');
    cerca(hi, pose.hips[0] * s, 1e-12, 'caderas al 100 %');
    for (const [h, r0] of Object.entries(antes)) {
      const n = vrm.huesos[h].rotation;
      assert.deepEqual([n.x, n.y, n.z], r0, `${h} restaurado`);
    }
    // luneSeatPx sentada: la pose quieta (misma medida)
    assert.deepEqual(m.mod('sentarse', 'puntos'), p);
    vrm.huesos.hips.getWorldPosition = orig;
    // un saludo sentada se ve (el brazo sube)
    correr(1.5);
    m.setEstado('wave');
    let max = -Infinity;
    correr(1.5, null, () => { max = Math.max(max, brazoMundo(vrm, 'right', version).mano[1]); });
    assert.ok(max > 0, `el saludo sube la mano derecha (VRM ${version}): ${max}`);
    correr(3);
    assert.ok(brazoMundo(vrm, 'right', version).mano[1] < -1.2, 'acabado el saludo, abajo otra vez');
    m.destruir();
  }
});

test('medirAsiento: asiento bajo los muslos (0.12·(cabeza − pie)) y sonda bajo las caderas (0.23·altura)', () => {
  // cámara «identidad» (three falso): proyectar(v) = (left + (x+1)/2·w, top + (1−y)/2·h)
  const { m, vrm } = montar();
  quietaSinIdles(m);
  vrm.huesos.leftUpperLeg.position.set(0.09, 0.85, 0); vrm.huesos.rightUpperLeg.position.set(-0.09, 0.85, 0);
  vrm.huesos.leftLowerLeg.position.set(0.09, 0.45, 0); vrm.huesos.rightLowerLeg.position.set(-0.09, 0.45, 0);
  const pie = new (vrm.scene.constructor)(); pie.position.set(0.09, 0.05, 0); vrm.scene.add(pie);
  const hum = vrm.humanoid.getNormalizedBoneNode;
  vrm.humanoid.getNormalizedBoneNode = (h) => (h === 'leftFoot' ? pie : hum(h));
  const p = medirAsiento(m.ctx);
  const alto = 320, ancho = 240;
  const h = 1.4 - 0.05, baja = 0.12 * h;
  cerca(p.asiento.y, Math.round((1 - (0.85 - baja)) / 2 * alto * 10) / 10, 0.11, 'asiento');
  cerca(p.asiento.x, Math.round((0 + 1) / 2 * ancho * 10) / 10, 0.11);
  const altura = (1.4 - 0.9) + (0.9 - 0.85) + 0.4 + 0.4;
  cerca(p.sonda.y, Math.round((1 - (0.9 - 0.23 * altura)) / 2 * alto * 10) / 10, 0.11, 'sonda');
  assert.equal(medirAsiento({}), null, 'sin ctx: null');
  m.destruir();
});

// ── La página ───────────────────────────────────────────────────────────────────

test('companion_vrm.html: luneSentar/luneSeatPx antes y después del módulo; se registra al usarse', async () => {
  const body = crearElemento('body');
  const stage = body.appendChild(crearElemento('div', 'stage'));
  stage.appendChild(Object.assign(crearElemento('canvas', 'c'), lienzoFalso()));
  const zzz = stage.appendChild(crearElemento('div', 'zzz'));
  zzz.classList.toggle = (c, on) => { if (on) zzz.classList.add(c); else zzz.classList.remove(c); };
  stage.appendChild(crearElemento('div', 'aviso'));
  const doc = crearDocumento(body);
  doc.body = body;
  globalThis.document = doc;
  globalThis.location = { search: '?src=/vrm/actual.vrm&v=1' };
  const { html, scripts } = scriptsEnLinea('companion_vrm.html');
  assert.equal(scripts.length, 2);
  assert.ok(html.includes("import('./vrm/lune_sentarse.js').catch("), 'módulo opcional');
  vm.runInThisContext(scripts[0].codigo, { filename: 'companion_vrm.html' });
  assert.equal(globalThis.luneSeatPx(), 'null', 'aún no se sabe');
  assert.equal(globalThis.luneSentar('barra', 0), 'null');
  frames.length = 0;
  await import(aDataURL(reescribirImports(scripts[1].codigo, new URL('companion_vrm.html', UI), { './vrm/lune_vrm.js': DATA_MOTOR }) + '\n// sentarse'));
  const mascota = globalThis.luneMascota;
  try {
    assert.equal(globalThis.__luneVidaPendiente, null);
    assert.ok(mascota.bus.lista().includes('sentarse'), 'registrado al repetir lo pendiente');
    assert.equal(globalThis.luneMod('sentarse', 'estado').sentada, 'barra');
    const vrm = crearVRMFalso();
    cargas.pop().alCargar({ scene: vrm.scene, userData: { vrm } });
    correr(1.5);
    const p = JSON.parse(globalThis.luneSentar('ventana', 3));
    assert.ok(Number.isFinite(p.asiento.x) && Number.isFinite(p.sonda.y), JSON.stringify(p));
    assert.deepEqual(JSON.parse(globalThis.luneSeatPx()), p, 'sentada: la pose sentada');
    assert.equal(globalThis.luneMod('sentarse', 'estado').variante, 3);
    assert.equal(globalThis.luneSentar(null), 'null');
    assert.equal(globalThis.luneMod('sentarse', 'estado').sentada, '');
    const de_pie = JSON.parse(globalThis.luneSeatPx());
    assert.ok(Number.isFinite(de_pie.asiento.y), 'de pie también mide (pose actual)');
    const ev = vaciarCola().filter((e) => e.t === 'sentada');
    assert.ok(ev.length >= 2, JSON.stringify(ev));
  } finally {
    try { mascota.destruir(); } catch (_) { /* sigue */ }
  }
});
