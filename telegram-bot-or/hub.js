/**
 * hub.js — Cliente del hub de Lune para el bot (un terminal mas).
 *
 * Mismo contrato que lune_core/protocolo.py: sobres JSON planos, `auth` →
 * `announce` → listo, ping cada 20 s, respuestas correlacionadas por
 * meta.parent_id. Reconecta con backoff exponencial; si el token es invalido
 * (error terminal / cierre 4001) se rinde.
 *
 * Node >= 22 trae `WebSocket` global; en Node mas viejo se intenta `ws`.
 */
import { randomUUID } from "crypto";

const WS = globalThis.WebSocket ?? (await import("ws").then(m => m.default).catch(() => null));

export class HubCliente {
  constructor({ url, token, nombre, kind = "bot", eventos = [] }) {
    this.url = url.replace(/\/+$/, "").endsWith("/ws") ? url : url.replace(/\/+$/, "") + "/ws";
    this.token = token ?? "";
    this.fuente = { id: nombre, kind };
    this.eventos = eventos;
    this.estado = "idle";
    this.peerId = null;
    this.ws = null;
    this.pendientes = new Map();     // id -> {resolve, reject, timer}
    this.chats = new Map();          // id -> {resolve, reject, timer, onDelta} (streaming de chat)
    this.oyentes = new Map();        // type -> [handlers]
    this._cerrar = false;
    this._intento = 0;
    this._ping = null;
  }

  get listo() { return this.estado === "ready"; }

  on(type, handler) {
    if (!this.oyentes.has(type)) this.oyentes.set(type, []);
    this.oyentes.get(type).push(handler);
  }

  // ── Conexion ────────────────────────────────────────────────────────────────

  async conectar() {
    if (!WS) throw new Error("No hay WebSocket disponible (Node >= 22 o `npm i ws`).");
    while (!this._cerrar) {
      this.estado = this._intento === 0 ? "connecting" : "reconnecting";
      const ok = await this._intentar().catch(e => {
        if (e?.terminal) { this.estado = "failed"; return null; }
        return false;
      });
      if (ok === null) return false;      // token invalido: no insistir
      if (ok) return true;
      this._intento++;
      const espera = Math.min(1000 * 2 ** (this._intento - 1), 30000) * (0.5 + Math.random() * 0.5);
      await new Promise(r => setTimeout(r, espera));
    }
    return false;
  }

  _intentar() {
    return new Promise((resolve, reject) => {
      let ws;
      try { ws = new WS(this.url); } catch (e) { return resolve(false); }
      let fase = "auth";
      let idAuth = null, idAnn = null;

      const timeoutHandshake = setTimeout(() => { try { ws.close(); } catch {} resolve(false); }, 10000);

      ws.onopen = () => {
        idAuth = this._enviarCrudo(ws, "auth", { token: this.token });
        this.estado = "authenticating";
      };
      ws.onmessage = (m) => {
        let ev;
        try { ev = JSON.parse(typeof m.data === "string" ? m.data : m.data.toString()); } catch { return; }
        if (fase === "auth" && ev.meta?.parent_id === idAuth) {
          if (ev.type === "error") {
            clearTimeout(timeoutHandshake);
            const err = new Error(ev.data?.message ?? "error de autenticacion");
            err.terminal = !!ev.data?.terminal;
            try { ws.close(); } catch {}
            return reject(err);
          }
          this.peerId = ev.data?.peer_id ?? null;
          fase = "announce";
          this.estado = "announcing";
          idAnn = this._enviarCrudo(ws, "announce", { name: this.fuente.id, kind: this.fuente.kind, events: this.eventos });
          return;
        }
        if (fase === "announce" && ev.meta?.parent_id === idAnn) {
          clearTimeout(timeoutHandshake);
          fase = "ready";
          this.ws = ws;
          this.estado = "ready";
          this._intento = 0;
          this._arrancarPing();
          ws.onmessage = (mm) => this._onMensaje(mm);
          ws.onclose = (c) => this._onCierre(c);
          return resolve(true);
        }
      };
      ws.onerror = () => {};
      ws.onclose = (c) => {
        clearTimeout(timeoutHandshake);
        if (fase !== "ready") {
          if (c?.code === 4001) { const e = new Error("token invalido"); e.terminal = true; return reject(e); }
          resolve(false);
        }
      };
    });
  }

  _onMensaje(m) {
    let ev;
    try { ev = JSON.parse(typeof m.data === "string" ? m.data : m.data.toString()); } catch { return; }
    const pid = ev.meta?.parent_id;
    // Streaming de chat: varios eventos con el mismo parent_id hasta el done.
    if (pid && this.chats.has(pid)) {
      const c = this.chats.get(pid);
      if (ev.type === "output:chat:delta") { c.onDelta?.(ev.data?.text ?? ""); return; }
      if (ev.type === "output:chat:act") return;                 // emociones: el bot no las usa
      if (ev.type === "output:chat:done") {
        clearTimeout(c.timer); this.chats.delete(pid); c.resolve(ev); return;
      }
      return;
    }
    if (pid && this.pendientes.has(pid)) {
      const p = this.pendientes.get(pid);
      clearTimeout(p.timer);
      this.pendientes.delete(pid);
      p.resolve(ev);
      return;
    }
    if (ev.type === "pong") return;
    for (const h of this.oyentes.get(ev.type) ?? []) {
      try { h(ev); } catch (e) { console.error("[hub] oyente fallo:", e.message); }
    }
  }

  _onCierre(c) {
    this._pararPing();
    this.ws = null;
    for (const [, p] of this.pendientes) { clearTimeout(p.timer); p.reject(new Error("conexion perdida")); }
    this.pendientes.clear();
    for (const [, c] of this.chats) { clearTimeout(c.timer); c.reject(new Error("conexion perdida")); }
    this.chats.clear();
    if (this._cerrar) { this.estado = "idle"; return; }
    if (c?.code === 4001) { this.estado = "failed"; return; }
    this.estado = "reconnecting";
    this.conectar().catch(() => {});
  }

  _arrancarPing() {
    this._pararPing();
    this._ping = setInterval(() => { if (this.ws) this._enviarCrudo(this.ws, "ping", {}); }, 20000);
  }
  _pararPing() { if (this._ping) { clearInterval(this._ping); this._ping = null; } }

  // ── Envio ───────────────────────────────────────────────────────────────────

  _sobre(type, data, parentId = null, to = null) {
    const ev = { type, data: data ?? {}, meta: { source: this.fuente, id: randomUUID().replace(/-/g, ""), parent_id: parentId, ts: new Date().toISOString().slice(0, 19) } };
    if (to?.length) ev.route = { to };
    return ev;
  }

  _enviarCrudo(ws, type, data, parentId = null, to = null) {
    const ev = this._sobre(type, data, parentId, to);
    ws.send(JSON.stringify(ev));
    return ev.meta.id;
  }

  enviar(type, data, to = null) {
    if (!this.listo) throw new Error("el cliente del hub no esta listo");
    return this._enviarCrudo(this.ws, type, data, null, to);
  }

  /** Envia y espera el evento cuyo parent_id sea el nuestro. */
  pedir(type, data, timeoutMs = 10000) {
    if (!this.listo) return Promise.reject(new Error("el cliente del hub no esta listo"));
    const ev = this._sobre(type, data);
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { this.pendientes.delete(ev.meta.id); reject(new Error(`sin respuesta del host a ${type}`)); }, timeoutMs);
      this.pendientes.set(ev.meta.id, { resolve, reject, timer });
      this.ws.send(JSON.stringify(ev));
    });
  }

  /**
   * Envia input:text y espera el output:chat:done del host (agente). Los
   * output:chat:delta llegan a onDelta si se pasa. Devuelve el texto final.
   */
  pedirChat(text, { onDelta = null, imagenes = [], provider = null, timeoutMs = 180000 } = {}) {
    if (!this.listo) return Promise.reject(new Error("el cliente del hub no esta listo"));
    const ev = this._sobre("input:text", { text, images: imagenes, provider });
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { this.chats.delete(ev.meta.id); reject(new Error("sin respuesta del host (chat)")); }, timeoutMs);
      this.chats.set(ev.meta.id, { resolve, reject, timer, onDelta });
      this.ws.send(JSON.stringify(ev));
    }).then(ev => ev.data?.text ?? "");
  }

  cerrar() {
    this._cerrar = true;
    this._pararPing();
    try { this.ws?.close(); } catch {}
    this.ws = null;
    this.estado = "idle";
  }
}
