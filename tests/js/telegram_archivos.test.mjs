// resolverRuta (telegram-bot-or/archivos.js): lo que se pide por /ls, /fotos y
// /archivo queda SIEMPRE dentro de la carpeta del usuario. Antes «../..» salía a
// C:\ y /ls listaba todo el disco.
import { test } from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath, pathToFileURL } from "node:url";
import { dirname, join, sep } from "node:path";

const RAIZ = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const { resolverRuta, HOME } = await import(pathToFileURL(join(RAIZ, "telegram-bot-or", "archivos.js")).href);

const B = "\\";
const dentro = (r) => r === HOME || r.startsWith(HOME + sep);

test("«..», absolutas, unidad y red vuelven a la carpeta del usuario", () => {
  const fuera = ["..", "../..", "../../Windows/System32/drivers/etc", "Desktop/../..",
    "C:" + B + "Windows", B + B + "servidor" + B + "c$", "//servidor/c", B + "Windows", "/Windows",
    HOME + B + ".." + B + ".."];
  for (const c of fuera) assert.equal(resolverRuta(c), HOME, `«${c}» debería quedarse en HOME`);
});

test("lo que está dentro se resuelve dentro", () => {
  for (const c of ["Desktop", "~/Desktop", "~" + B + "Desktop", "Desktop/../Documents", HOME + B + "Desktop"]) {
    const r = resolverRuta(c);
    assert.ok(dentro(r) && r !== HOME, `«${c}» → ${r}`);
  }
  assert.equal(resolverRuta(""), HOME);
  assert.equal(resolverRuta("~"), HOME);
  assert.equal(resolverRuta(undefined), HOME);
});
