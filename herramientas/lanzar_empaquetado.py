r"""lanzar_empaquetado -- abrir el EDA.exe ORIGINAL (con ASProtect) y pasar GameGuard EN MEMORIA.

Para qué: el exe desempacado (`EDA_limpio.exe`) todavía tiene ~184 llamadas desviadas sin
resolver (la TRAMPA de `desempacar.py`). El original las tiene todas. Correr el original es la
forma de saber si algo que no anda (las habilidades jugando, p. ej.) es culpa del desempacado o
del server.

Cómo: el archivo NO se toca (sus bytes están cifrados por ASProtect). Se lo abre bajo Frida y,
desde adentro, se miran cada pocos ms las direcciones de la receta `limpio` de `sin_gameguard.py`;
apenas ASProtect las desempaca (tienen los bytes ORIGINALES que espera la receta) se les ponen
los mismos parches que lleva `EDA_limpio.exe`. ★ El control: si una dirección no tiene los bytes
esperados, NO se toca (y se avisa).

    py herramientas\lanzar_empaquetado.py            # usa _trabajo/juego/EDA.exe (copia del original)

⚠ Se corre desde `_trabajo/juego/` (nunca desde `cliente/`). El Broker usa la clave = MD5 del exe
  que habla: `paquete_broker.py` ya calcula la del original (está en `_trabajo/juego/EDA.exe`).
"""
import json
import os
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                            # noqa: BLE001
    pass

import frida

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sin_gameguard as SG                                    # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JUEGO = os.path.join(RAIZ, "_trabajo", "juego")

JS = r"""
const parches = %s;
const hechos = {};
function hex(p, n) { return Array.from(new Uint8Array(p.readByteArray(n)))
                         .map(b => ('0' + b.toString(16)).slice(-2)).join(''); }
const t0 = Date.now();
const vuelta = setInterval(function () {
    let faltan = 0;
    for (const [va, viejo, nuevo] of parches) {
        if (hechos[va]) continue;
        const p = ptr(va);
        let actual;
        try { actual = hex(p, viejo.length / 2); } catch (e) { faltan++; continue; }
        if (actual === viejo) {
            const b = []; for (let i = 0; i < nuevo.length; i += 2) b.push(parseInt(nuevo.substr(i, 2), 16));
            Memory.patchCode(p, b.length, function (c) { c.writeByteArray(b); });
            hechos[va] = true;
            send({t: 'parche', va: va, ms: Date.now() - t0, ahora: hex(p, b.length)});
        } else if (actual === nuevo) {
            hechos[va] = true;
            send({t: 'ya', va: va});
        } else {
            faltan++;
        }
    }
    if (faltan === 0) { clearInterval(vuelta); send({t: 'listo', ms: Date.now() - t0}); }
    if (Date.now() - t0 > 60000) { clearInterval(vuelta); send({t: 'tiempo', hechos: hechos}); }
}, 2);
"""


def main():
    exe = os.path.join(JUEGO, "EDA.exe")
    parches = [[va, viejo, nuevo] for va, viejo, nuevo, _ in SG.RECETAS["limpio"]]
    pid = frida.spawn([exe], cwd=JUEGO, stdio="pipe")
    ses = frida.attach(pid)
    sc = ses.create_script(JS % json.dumps(parches))
    estado = {"listo": False}

    def msg(m, d):
        p = m.get("payload", m)
        print("  ", p, flush=True)
        if isinstance(p, dict) and p.get("t") in ("listo", "tiempo"):
            estado["listo"] = True
    sc.on("message", msg)
    sc.load()
    frida.resume(pid)
    print("★ EDA.exe (original, empaquetado) pid %d" % pid, flush=True)
    open(os.path.join(RAIZ, "_trabajo", "multi_pids.txt"), "w").write(str(pid))
    t = time.time()
    while not estado["listo"] and time.time() - t < 70:
        time.sleep(0.2)
    # queda abierto: la sesión de Frida se suelta (los parches ya están en la memoria)
    ses.detach()
    return 0


if __name__ == "__main__":
    sys.exit(main())
