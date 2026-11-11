r"""miembro_sala -- leer de un cliente ANDANDO el registro de un miembro de su sala (0x32C = 812 B).

Para el multijugador el server tiene que mandar a cada cliente los miembros de la sala (`0x1020`,
`0x1057`): N × 812 bytes por miembro, un formato grande y desconocido. En vez de inventarlo, se lo
copia de un cliente real: el anfitrión ya tiene SU miembro armado en memoria. Se lo busca con el
buscador del propio juego, `0x61C110(índice)` sobre la lista de miembros de la cuenta
(`0x623E60()` + 0x240; la cuenta está en `0x937390`: su +0x2B0 = `0x937640`, medido en
`0x6209F0`). Sólo lee: llama a una búsqueda y copia bytes.

    py herramientas\miembro_sala.py <pid> [índice]     # → _trabajo/servidor/miembro_<pid>_<i>.bin
"""
import os
import sys

import frida

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

JS = r"""
const cuenta = new NativeFunction(ptr(0x623E60), 'pointer', []);
const buscar = new NativeFunction(ptr(0x61C110), 'pointer', ['pointer', 'uint32'], 'thiscall');
rpc.exports = {
    leer(i) {
        // ★ la lista es un VECTOR de objetos de 0x36F B (`0x61C110`: [+0x64] comienzo, [+0x68]
        //   fin; busca por el byte +5 = número de jugador). Se lee el i-ésimo directo.
        const c = cuenta(), lista = c.add(0x240);
        const ini = lista.add(0x64).readPointer(), fin = lista.add(0x68).readPointer();
        const n = fin.sub(ini).toInt32() / 0x36F;
        if (i >= n) return {cuenta: c.toString(), miembro: null, cantidad: n};
        const m = ini.add(0x36F * i);
        return {cuenta: c.toString(), miembro: m.toString(), cantidad: n,
                bytes: Array.from(new Uint8Array(m.readByteArray(0x36F)))};
    }
};
"""


def main():
    pid = int(sys.argv[1])
    i = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    ses = frida.attach(pid)
    sc = ses.create_script(JS)
    sc.load()
    r = sc.exports_sync.leer(i)
    ses.detach()
    print("cuenta %s · miembro %d de %s en %s" % (r["cuenta"], i, r.get("cantidad"), r["miembro"]))
    if r.get("bytes"):
        b = bytes(r["bytes"])
        ruta = os.path.join(RAIZ, "_trabajo", "servidor", "miembro_%d_%d.bin" % (pid, i))
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        open(ruta, "wb").write(b)
        print("→ %s" % ruta)
        for o in range(0, len(b), 16):
            print("  %03x  %s" % (o, b[o:o + 16].hex(" ")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
