import { readFileSync, existsSync, statSync } from "fs";
import { execSync } from "child_process";
import { homedir } from "os";
import os from "os";

export function estadoSistema() {
  const lineas = [];

  // CPU
  const cpus = os.cpus();
  const modelo = cpus[0]?.model?.trim() ?? "Desconocido";
  const nucleos = cpus.length;
  lineas.push(`*CPU:* ${modelo} (${nucleos} nucleos)`);

  // Carga del sistema
  const [load1, load5] = os.loadavg();
  lineas.push(`*Carga:* ${load1.toFixed(2)} (1min) / ${load5.toFixed(2)} (5min)`);

  // RAM
  const totalRam  = os.totalmem();
  const libreRam  = os.freemem();
  const usadaRam  = totalRam - libreRam;
  const pctRam    = ((usadaRam / totalRam) * 100).toFixed(1);
  lineas.push(`*RAM:* ${fmt(usadaRam)} usados / ${fmt(totalRam)} total (${pctRam}%)`);

  // Uptime
  const up = os.uptime();
  const horas   = Math.floor(up / 3600);
  const minutos = Math.floor((up % 3600) / 60);
  lineas.push(`*Uptime:* ${horas}h ${minutos}m`);

  // Hostname y plataforma
  lineas.push(`*Host:* ${os.hostname()} (${os.platform()} ${os.release()})`);

  // Disco (df del home)
  try {
    const df = execSync(`df -h ${homedir()} | tail -1`, { encoding: "utf8" }).trim();
    const partes = df.split(/\s+/);
    if (partes.length >= 5) {
      lineas.push(`*Disco:* ${partes[2]} usados / ${partes[1]} total (${partes[4]} lleno)`);
    }
  } catch {
    lineas.push(`*Disco:* no disponible`);
  }

  // Procesos corriendo
  try {
    const procs = execSync("ps aux --no-headers | wc -l", { encoding: "utf8" }).trim();
    lineas.push(`*Procesos:* ${procs}`);
  } catch {}

  return lineas.join("\n");
}

function fmt(bytes) {
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(0)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
}
