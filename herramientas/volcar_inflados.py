r"""volcar_inflados -- guardar TODO lo que el juego descomprime de Data.dat, mientras juega.

`Data.dat` es el «Softnyx File System» (zlib 1.2.3 adentro) y su formato no se conoce todavía.
En vez de reversearlo, se le pide al juego: se engancha **`inflate` de zlib (`0x788260`)** — se
la reconoce porque es la que pone «incorrect header check» / «invalid stored block lengths» en
`strm->msg` (`0x788454`, `0x788B41`) y revisa `strm->state` (+0x1C) y `strm->next_out` (+0x0C) —
y cada salida que termina en Z_STREAM_END se guarda en `_trabajo/inflados/NNNNN.<ext>`.

Abre el juego BAJO Frida (desde el arranque: así pasan también `Data\main.xml` y compañía) y,
en la misma apertura, captura la tabla de entrada de `control_partida.py` (ver ahí). Queda
corriendo hasta que el juego se cierra; el índice va a `_trabajo/inflados/indice.tsv`.

    py herramientas\volcar_inflados.py                 # abre el juego y vuelca (dejarlo en 2º plano)
    py herramientas\volcar_inflados.py buscar OnTrigger_01   # en qué archivos volcados está un texto
    py herramientas\volcar_inflados.py --atajo fin --sin-guardar   # la stage termina sola (prueba)

★ El control: `zlib.compress` de un texto conocido descomprimido POR EL JUEGO (llamando a su
  `inflate` desde Frida) tiene que volver idéntico, y un texto cambiado no — `control`.
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
import control_partida as CP                                  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SALIDA = os.path.join(RAIZ, "_trabajo", "inflados")
INFLATE = 0x788260
MAXIMO = 4 << 20            # lo más grande que se guarda entero (más grande: sólo se anota)

JS = r"""
'use strict';
const inflate = ptr(%d);
const parciales = {};
const CAMBIOS = %s;          // [[patrón hexa de Memory.scan, [bytes nuevos]], ...]
let n = 0;
Interceptor.attach(inflate, {
    onEnter(a) { this.s = a[0]; this.o = a[0].add(0xC).readPointer(); this.ra = this.returnAddress; },
    onLeave(rv) {
        const k = this.s.toString();
        const fin = this.s.add(0xC).readPointer();
        const largo = fin.sub(this.o).toInt32();
        if (!parciales[k]) parciales[k] = {trozos: [], total: 0, ra: this.ra.toString()};
        const p = parciales[k];
        if (largo > 0 && CAMBIOS.length) {
            // ★ reescribir en memoria lo que el juego acaba de descomprimir (mismo largo)
            for (const [de, a] of CAMBIOS) {
                for (const h of Memory.scanSync(this.o, largo, de)) {
                    h.address.writeByteArray(a); send({t: 'cambio', en: h.address.toString()});
                }
            }
        }
        if (largo > 0) {
            p.total += largo;
            if (p.total <= %d) p.trozos.push(this.o.readByteArray(largo));
        }
        const r = rv.toInt32();
        if (r === 1 || r < 0) {
            n++;
            let datos = null;
            if (p.total <= %d && p.trozos.length) {
                const u = new Uint8Array(p.total); let i = 0;
                p.trozos.forEach(t => { u.set(new Uint8Array(t), i); i += t.byteLength; });
                datos = u.buffer;
            }
            send({t: 'inflado', n: n, total: p.total, ret: r, ra: p.ra}, datos);
            delete parciales[k];
        }
    }
});
send({t: 'listo_inflate'});
"""

# ★ ATAJOS de prueba (sólo en memoria, sólo en esta corrida; Data.dat no se toca): reescriben el
#   guion al descomprimirse, con el MISMO largo. `fin`: la stage 1011 termina sola al segundo de
#   OnStart (en vez de crear el primer grupo de NPC llama a OnEnd → SendEvent → 0x1064).
ATAJOS = {
    "fin": [('InsertFunction("OnTrigger_01", 1000)', 'InsertFunction("OnEnd",        1000)')],
}


def js(atajo=None, guardar=True):
    cambios = []
    for de, a in ATAJOS.get(atajo, []):
        assert len(de) == len(a), (de, a)
        cambios.append([" ".join("%02x" % b for b in de.encode()), list(a.encode())])
    return JS % (INFLATE, json.dumps(cambios), MAXIMO if guardar else -1, MAXIMO if guardar else -1)


def extension(d):
    c = d[:64].lstrip(b"\xef\xbb\xbf \r\n\t")
    if c.startswith(b"<"):
        return "xml"
    if d[:4] == b"\x1bLua":
        return "luac"
    if d[:2] == b"\xff\xfe" or d[:2] == b"\xfe\xff":
        return "txt16"
    if c[:2] in (b"--", b"fu", b"lo") or b"function" in d[:400]:
        return "lua"
    if d[:4] == b"DDS ":
        return "dds"
    if d[:3] == b"\x89PN":
        return "png"
    return "bin"


def lanzar(atajo=None, guardar=True):
    os.makedirs(SALIDA, exist_ok=True)
    import subprocess
    subprocess.run(["taskkill", "/F", "/IM", "EDA_limpio.exe"], capture_output=True)
    time.sleep(0.5)
    pid = frida.spawn([os.path.join(CP.JUEGO, "EDA_limpio.exe")], cwd=CP.JUEGO, stdio="pipe")
    ses = frida.attach(pid)
    indice = open(os.path.join(SALIDA, "indice.tsv"), "a", encoding="utf-8")
    indice.write("# %s pid %d\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), pid))
    listo = []

    def al_mensaje(m, datos):
        if m["type"] != "send":
            print("  [js error]", m.get("description"))
            return
        p = m["payload"]
        if p.get("t") == "listo_inflate":
            listo.append(1)
        elif p.get("t") == "cambio":
            print("  ★ atajo «%s» aplicado en %s" % (atajo, p["en"]), flush=True)
        elif p.get("t") == "inflado":
            nombre = ""
            if datos:
                nombre = "%05d.%s" % (p["n"], extension(datos))
                open(os.path.join(SALIDA, nombre), "wb").write(datos)
            indice.write("%d\t%s\t%d\t%d\t%s\t%s\n" % (p["n"], time.strftime("%H:%M:%S"), p["total"],
                                                     p["ret"], p["ra"], nombre))
            indice.flush()
    sc = ses.create_script(js(atajo, guardar))
    sc.on("message", al_mensaje)
    sc.load()
    # ★ y la tabla de entrada de control_partida (su SetDataFormat pasa una sola vez, al arrancar)
    sc2 = ses.create_script(CP.JS)
    sc2.on("message", lambda m, d: m["type"] == "send" and m["payload"].get("t") == "formato"
           and CP.FORMATOS.append(m["payload"]))
    sc2.load()
    frida.resume(pid)
    print("★ EDA_limpio.exe pid %d — volcando en %s" % (pid, SALIDA), flush=True)
    guardada = False
    while True:
        time.sleep(1)
        if not guardada and len({f["tipoDev"] for f in CP.FORMATOS}) >= 2:
            time.sleep(3)                                     # que termine de armar los dos
            mapa = {}
            for f in CP.FORMATOS:
                mapa.setdefault(str(f["tipoDev"]), {}).update({o["nombre"]: o["ofs"] for o in f["objs"]})
            json.dump({"mapa": mapa, "crudo": CP.FORMATOS}, open(CP.FORMATO, "w"), indent=1)
            print("  tabla de entrada → %s" % CP.FORMATO, flush=True)
            guardada = True
        try:
            os.kill(pid, 0)
        except OSError:
            break
    print("  el juego se cerró")


def buscar(texto):
    aguja = texto.encode()
    aguja16 = texto.encode("utf-16-le")
    for f in sorted(os.listdir(SALIDA)):
        d = open(os.path.join(SALIDA, f), "rb").read()
        if aguja in d or aguja16 in d:
            print("  %s  (%d B)" % (f, len(d)))


def main():
    a = sys.argv[1:]
    if a and a[0] == "buscar":
        buscar(a[1])
    else:
        atajo = a[a.index("--atajo") + 1] if "--atajo" in a else None
        lanzar(atajo, guardar="--sin-guardar" not in a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
