// tests/js/mc_falsos.mjs — dobles para los tests del bot de Minecraft (minecraft-bot/src).
// Sin mineflayer ni red: un bot de mentira (EventEmitter), vectores, habilidades que
// apuntan lo que se les pide, minecraft-data mínimo y un reloj que se avanza a mano.
import { EventEmitter } from 'node:events';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const aqui = path.dirname(fileURLToPath(import.meta.url));
export const SRC = path.resolve(aqui, '../../minecraft-bot/src');
/** require() de CommonJS con la ruta de minecraft-bot/src. */
export const requerirBot = createRequire(path.join(SRC, 'bot.js'));

export class Vec {
  constructor(x = 0, y = 0, z = 0) { this.x = x; this.y = y; this.z = z; }
  distanceTo(o) { return Math.hypot(this.x - o.x, this.y - o.y, this.z - o.z); }
  offset(dx, dy, dz) { return new Vec(this.x + dx, this.y + dy, this.z + dz); }
  plus(o) { return new Vec(this.x + o.x, this.y + o.y, this.z + o.z); }
  minus(o) { return new Vec(this.x - o.x, this.y - o.y, this.z - o.z); }
  floored() { return new Vec(Math.floor(this.x), Math.floor(this.y), Math.floor(this.z)); }
  equals(o) { return this.x === o.x && this.y === o.y && this.z === o.z; }
}

export function reloj(t0 = 1_000_000) {
  let t = t0;
  return { ahora: () => t, avanzar: (ms) => { t += ms; }, poner: (v) => { t = v; } };
}

/** minecraft-data de mentira: lo justo para commands.js. */
export function mcDataFalso() {
  const bloques = ['iron_ore', 'oak_log', 'birch_log', 'stone', 'diamond_ore', 'coal_ore', 'crafting_table'];
  const entidades = ['zombie', 'skeleton', 'creeper', 'player', 'villager', 'cow', 'armor_stand', 'wolf'];
  const porNombre = (lista) => Object.fromEntries(lista.map((n, i) => [n, { id: i + 1, name: n }]));
  return () => ({ blocksByName: porNombre(bloques), entitiesByName: porNombre(entidades), itemsByName: {}, items: {} });
}

/** Habilidades que apuntan las llamadas (skills.js de mentira). */
export function skillsFalsas({ entidades = {} } = {}) {
  const llamadas = [];
  const apunta = (nombre, valor) => (...args) => { llamadas.push([nombre, ...args.slice(1)]); return valor; };
  return {
    llamadas,
    nombres: () => llamadas.map((l) => l[0]),
    stopAll: apunta('stopAll'),
    follow: apunta('follow', true),
    comeToPlayer: apunta('comeToPlayer', Promise.resolve(true)),
    goToCoords: apunta('goToCoords', Promise.resolve()),
    mineNearest: apunta('mineNearest', Promise.resolve(1)),
    chopTree: apunta('chopTree', Promise.resolve(3)),
    attackNearest: apunta('attackNearest', Promise.resolve(true)),
    collectNearbyItems: apunta('collectNearbyItems', Promise.resolve(2)),
    dropItem: apunta('dropItem', Promise.resolve(true)),
    eatFood: apunta('eatFood', Promise.resolve(true)),
    explore: apunta('explore', Promise.resolve()),
    equipArmor: apunta('equipArmor', Promise.resolve()),
    fleeFrom: apunta('fleeFrom', Promise.resolve()),
    nearestHostile: (bot, d) => { llamadas.push(['nearestHostile', d]); return entidades.hostil || null; },
    nearestEntityByName: () => null,
    nearestPlayer: () => null,
    playerEntity: (bot, n) => { llamadas.push(['playerEntity', n]); return entidades[n] || null; },
    isDarkHere: () => false,
    placeTorchNearby: async () => false,
    approach: apunta('approach'),
    sleep: async () => {},
  };
}

/** Un bot de mineflayer de mentira. */
export class BotFalso extends EventEmitter {
  constructor({ username = 'Lune', pos = new Vec(0, 64, 0) } = {}) {
    super();
    this.username = username;
    this.version = '1.21.1';
    this.entity = { position: pos, yaw: 0 };
    this.players = {};
    this.entities = {};
    this.health = 20;
    this.food = 20;
    this.time = { timeOfDay: 1000 };
    this.isRaining = false;
    this.experience = { level: 0 };
    this.dichos = [];
    this.controles = [];
    this.plugins = [];
    this.salio = null;
    this.inventory = { items: () => [], count: () => 0 };
    this.lune = { busy: false, panic: false, reflexBusy: false, thinking: false };
  }
  chat(t) { this.dichos.push(t); }
  quit(motivo) { this.salio = motivo ?? true; }
  loadPlugin(p) { this.plugins.push(p); }
  setControlState(c, v) { this.controles.push([c, v]); }
  clearControlStates() {}
  lookAt() { return Promise.resolve(); }
  look() { return Promise.resolve(); }
  blockAt() { return null; }
  jugador(nombre, pos) {
    const e = { position: pos, name: 'player', username: nombre };
    this.players[nombre] = { username: nombre, entity: e };
    return e;
  }
  mob(id, nombre, pos) {
    const e = { id, name: nombre, position: pos, type: 'hostile' };
    this.entities[id] = e;
    return e;
  }
}

export const esperar = (n = 3) => new Promise((r) => {
  let i = 0;
  const paso = () => (++i >= n ? r() : setImmediate(paso));
  setImmediate(paso);
});
