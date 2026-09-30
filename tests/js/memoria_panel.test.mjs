/*
 * Panel MEMORIA de la interfaz completa (ui_kits/lune-desktop/panels.jsx) en el sandbox de jsx_falso.mjs:
 * enseña lo que contaste en las tres preguntas de bienvenida (versión 11: «Cómo eres» y «Cómo quieres que sea
 * contigo»), que también va al system prompt; sin eso, igual que antes. «Olvidar todo» sale también cuando solo
 * hay perfil (sin recuerdos).
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import { crearSandbox, KIT, boton, todoTexto, porId } from './jsx_falso.mjs';

const PANELS = path.join(KIT, 'panels.jsx');

function montar(info) {
  const llamadas = [];
  const lune = {
    memoria_info: (cb) => { llamadas.push('memoria_info'); cb(JSON.stringify(info)); },
    memoria_olvidar: (id, cb) => { llamadas.push(['olvidar', id]); cb && cb(); },
    memoria_olvidar_todo: (cb) => { llamadas.push('olvidar_todo'); cb && cb(); },
  };
  const S = crearSandbox({ archivos: [PANELS], lune, globales: { confirm: () => true } });
  const el = S.h(S.sb.MemoriaPanel);
  S.render(el);                                   // el efecto pide memoria_info…
  return { S, arbol: S.render(el), llamadas };    // …y el segundo render ya la pinta
}

test('el panel enseña cómo eres y cómo quieres que sea contigo', () => {
  const { arbol, llamadas } = montar({
    nombre: 'Ana', personalidad: 'curiosa y bromista', trato: 'con humor',
    stats: { total_mensajes: 12 }, recuerdos: [],
  });
  assert.ok(llamadas.includes('memoria_info'));
  const t = todoTexto(arbol);
  assert.match(t, /Usuario · Ana/);
  assert.equal(porId(arbol, 'mem-personalidad') !== undefined, true);
  assert.match(t, /Cómo eres: curiosa y bromista/);
  assert.match(t, /Cómo quieres que sea contigo: con humor/);
  assert.match(t, /\/conocernos/);
  assert.ok(boton(arbol, 'Olvidar todo'), 'con perfil (aunque sin recuerdos) se puede olvidar todo');
});

test('sin perfil (o con un puente viejo que no lo manda) queda como antes', () => {
  const { arbol } = montar({ nombre: null, stats: {}, recuerdos: [] });
  const t = todoTexto(arbol);
  assert.doesNotMatch(t, /Cómo eres/);
  assert.doesNotMatch(t, /Cómo quieres que sea contigo/);
  assert.equal(boton(arbol, 'Olvidar todo'), undefined);
  assert.match(t, /Aún no hay recuerdos/);
});

test('un valor raro en personalidad o trato no se pinta', () => {
  const { arbol } = montar({ nombre: 'Ana', personalidad: { x: 1 }, trato: 5, stats: {}, recuerdos: [] });
  const t = todoTexto(arbol);
  assert.doesNotMatch(t, /Cómo eres/);
  assert.doesNotMatch(t, /\[object Object\]/);
});
