r"""sin_gameguard -- pasar el muro de GameGuard en una COPIA del exe desempacado.

★ Qué se encontró (10-nov, midiendo sobre el volcado con `leer_exe.py`):

    0x4035f0   el método de arranque del juego (virtual, lo llama el shell de LithTech)
      0x403601   call 0x4026d0   subclasa la ventana: SetWindowLongA(hwnd, GWL_WNDPROC=-4, 0x4026c0)
                                 para recibir los avisos de GameGuard (mensajes 0x3E9..0x3F9,
                                 el switch está en 0x402100)
      0x403606   call 0x402bb0   ★ EL MURO: devuelve AL=1 si GameGuard está bien, 0 si no
      0x40360d   test al,al
      0x40360f   je 0x403764     → `mov eax,1; ret 8`: se corta el arranque
      0x403613   push 0x181 ...  → sigue el juego

    0x402bb0   el juez:
      0x402bc2   call 0x7ce840   el código de error de GameGuard
      0x402bc7   cmp eax, 0x755  ★ 0x755 (1877) es el ÚNICO valor que vale: va a 0x402cce,
                                 que le pasa el HWND a la librería, lee la config «id» y
                                 termina en `mov al, 1`
      el resto   un switch de tres tablas que elige el texto del error y lo muestra con
                 MessageBox, y termina en `xor al, al` (0x402cb8, después del call desviado)
                 ⇒ el 361 que vemos (0x169) cae en la tercera tabla. Y ojo: **el 0 también
                   es error** para este juez; no alcanza con «no hubo error».

    0x7ce840   mov ecx,[0x949e30]; test ecx,ecx; jne → jmp 0x7cefb0
               `0x949e30` es el objeto de NPGameLib (lo crea `0x7ce890`, un `new` de 0x2b98
               bytes). `0x7cefb0` loguea «InitNPGameMon: %lu» y devuelve `[este+0x10]`,
               que es el resultado guardado del init. O sea: 0x7ce840 = «dame el error».

★ GameGuard está ESTÁTICO dentro del exe (la cadena «--- NPGameLib.lib version %d : %hs ---»
  está en los datos). No es una DLL que se pueda no cargar: hay que tocar el código.

Las dos maneras, y las dos se prueban:

    emular   0x7ce840 → `mov eax, 0x755; ret`     ⇒ el juego cree que GameGuard dijo OK y
                                                    recorre su camino de éxito DE VERDAD
                                                    (le pasa el HWND a la librería, lee «id»)
    nop      0x403606 → `mov al, 1; nop; nop; nop` ⇒ el juez no se llama nunca; el camino de
                                                    éxito de la librería tampoco corre

    py herramientas\sin_gameguard.py control
    py herramientas\sin_gameguard.py emular
    py herramientas\sin_gameguard.py nop

⛔ Nunca escribe en `cliente/`: lee `_trabajo/EDA_libre/EDA_libre.exe` y deja la copia parchada
   en `_trabajo/juego/`.
"""
import os
import shutil
import struct
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                            # noqa: BLE001
    pass

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRABAJO = os.path.join(RAIZ, "_trabajo")
ENTRADA = (os.path.join(TRABAJO, "EDA_libre", "EDA_libre.exe")
           if os.path.exists(os.path.join(TRABAJO, "EDA_libre", "EDA_libre.exe"))
           else os.path.join(TRABAJO, "juego", "EDA_limpio.exe"))
JUEGO = os.path.join(TRABAJO, "juego")

# (VA, los bytes que TIENEN que estar, los bytes nuevos, qué es)
RECETAS = {
    "emular": [
        (0x7CE840, "8b0d309e9400", "b855070000c3",
         "mov eax, 0x755 / ret -- el codigo que el juez de 0x402bc7 acepta"),
    ],
    "nop": [
        (0x403606, "e8a5f5ffff", "b0019090 90".replace(" ", ""),
         "mov al, 1 / nop x3 -- el juez de 0x402bb0 no se llama"),
    ],
    # ★ la tercera, y la que de verdad lo saca del medio (10-nov, tarde). Las dos de arriba dejan
    #   que GameGuard ARRANQUE y sólo le tapan la boca al juez: la librería igual sale a buscar su
    #   server de actualización, igual tarda ~22 s y, cuando falla, igual abre la web de ayuda de
    #   nProtect (`gameguardfaq.nprotect.com/con_02.html`) — lo vio el tester.
    #   `0x7CE890` es el init de NPGameLib (lo llama sólo `0x402B38`): hace el `new` de 0x2B98
    #   bytes del objeto y lo guarda en `0x949E30`. Si devuelve 0 sin crear nada, el objeto nunca
    #   existe, y TODAS las demás entradas de la librería (`0x7CE840`, `0x7CE860`, `0x7CEB30`,
    #   `0x7CEB80`) empiezan con `test` sobre `0x949E30` y se van sin hacer nada. O sea: GameGuard
    #   no arranca, no actualiza, no falla y no abre nada.
    #   ⚠ Y el juez SIGUE haciendo falta taparlo: sin objeto, `0x7CE840` devolvería 0, y el 0
    #     también es error para `0x402BC7`.
    # ★★ LA BUENA (medida el 10-nov con `ventanas.py`, que ahora anota los procesos nuevos):
    #   quién abría `gameguardfaq.nprotect.com` era **`GameGuard.des` corriendo como PROCESO
    #   aparte**, que el juego lanza a los 0,4 s con una línea de comando cifrada; a los 23 s,
    #   cuando no encuentra su server, abre el navegador. Con el init cortado no se lanza.
    #   Y el juez se saltea con el `nop` en vez de con el 0x755, porque el camino de éxito de
    #   `0x402CCE` lee `[0x92CEAC]` sin comprobarlo y con GameGuard apagado eso se muere.
    "limpio": [
        (0x7CE890, "a1309e9400", "33c0c39090",
         "xor eax,eax / ret -- NPGameLib no se crea: no se lanza GameGuard.des ni se abre la web"),
        (0x403606, "e8a5f5ffff", "b0019090 90".replace(" ", ""),
         "mov al, 1 / nop x3 -- el juez no se llama, y su camino de exito tampoco"),
        # ★★ el TERCERO (10-nov, corrida 16): el chequeo PERIÓDICO. `0x402E80` corre en cada
        #   cuadro; cada 10 s (`cmp eax, 0x2710`) le pide a NPGameLib su estado (`0x7CEAD0`, el
        #   único que la llama) y si no es 0x755 llama a `ILTClient::Shutdown()` ([+0x94]).
        #   Sin NPGameLib devuelve 0 ⇒ el juego se cerraba solo a los 10 s, SIEMPRE (medido con
        #   un breakpoint en `0x40FC40`: lo llama `0x402ECC`). `je` -> `jmp`: el chequeo sigue
        #   corriendo pero su respuesta no cierra nada. El otro chequeo de esa función
        #   («d3ddevice» == «d3d9.dll») no se toca.
        (0x402EC4, "740c", "eb0c",
         "je -> jmp -- el chequeo de cada 10 s de GameGuard no cierra el juego"),
        # ★★ el CUARTO (12-nov): la otra mitad de ese chequeo: si la variable de consola
        #   «d3ddevice» no es «d3d9.dll» (`0x7D4B10`) también llama a Shutdown ([+0x94]). Bajo
        #   Frida a veces no coincide y el juego se cerraba SOLO a los 10,0 s, sin reporte de caída
        #   (medido 3 veces con jugar.py desde una copia limpia del repo público). `je` -> `jmp`.
        (0x402EFB, "740c", "eb0c",
         "je -> jmp -- el chequeo de «d3ddevice» de cada 10 s no cierra el juego"),
    ],
    "fuera": [
        (0x7CE890, "a1309e9400", "33c0c39090",
         "xor eax,eax / ret -- NPGameLib no se crea nunca (devuelve 0, que es lo que ya "
         "devolvia cuando el objeto ya existia)"),
        (0x7CE840, "8b0d309e9400", "b855070000c3",
         "mov eax, 0x755 / ret -- el codigo que el juez de 0x402bc7 acepta"),
    ],
}


class Exe:
    """El exe en memoria, con el mapa de secciones leído del propio archivo (sin pefile)."""

    def __init__(self, ruta):
        self.ruta = ruta
        self.d = bytearray(open(ruta, "rb").read())
        pe = struct.unpack_from("<I", self.d, 0x3C)[0]
        assert self.d[pe:pe + 4] == b"PE\0\0", "no es un PE"
        nsec = struct.unpack_from("<H", self.d, pe + 6)[0]
        tam_opt = struct.unpack_from("<H", self.d, pe + 20)[0]
        self.base = struct.unpack_from("<I", self.d, pe + 24 + 28)[0]
        self.sec = []
        o = pe + 24 + tam_opt
        for i in range(nsec):
            s = o + i * 40
            nombre = bytes(self.d[s:s + 8]).rstrip(b"\0").decode("latin1", "replace")
            vsz, va, rsz, raw = struct.unpack_from("<IIII", self.d, s + 8)
            self.sec.append((nombre, self.base + va, max(vsz, rsz), raw))

    def off(self, va):
        for nombre, ini, tam, raw in self.sec:
            if ini <= va < ini + tam:
                return raw + (va - ini), nombre
        return None, None


def aplicar(receta, destino, verboso=True):
    """Hace la copia parchada. Devuelve la lista de bytes cambiados [(off, viejo, nuevo)].

    ★ Si los bytes que esperábamos no están, NO parcha: una dirección vieja o un exe
      distinto tiene que dar error, no un parche escrito en el lugar equivocado."""
    e = Exe(ENTRADA)
    cambios = []
    for va, viejo_hex, nuevo_hex, por_que in RECETAS[receta]:
        viejo, nuevo = bytes.fromhex(viejo_hex), bytes.fromhex(nuevo_hex)
        if len(viejo) != len(nuevo):
            raise SystemExit("⛔ %08x: el parche mide %d y el hueco %d" % (va, len(nuevo), len(viejo)))
        o, sec = e.off(va)
        if o is None:
            raise SystemExit("⛔ %08x no cae en ninguna sección" % va)
        hay = bytes(e.d[o:o + len(viejo)])
        if hay != viejo:
            raise SystemExit("⛔ %08x: esperaba %s y hay %s -- NO parcheo"
                             % (va, viejo.hex(), hay.hex()))
        for i in range(len(nuevo)):
            if e.d[o + i] != nuevo[i]:
                cambios.append((o + i, e.d[o + i], nuevo[i]))
        e.d[o:o + len(nuevo)] = nuevo
        if verboso:
            print("  %08x [%s] %s -> %s   %s" % (va, sec, viejo.hex(), nuevo.hex(), por_que))
    os.makedirs(os.path.dirname(destino) or ".", exist_ok=True)
    open(destino, "wb").write(bytes(e.d))
    return cambios


def control():
    """★ El control y su revés."""
    ok = []

    def chequear(nombre, cond, detalle=""):
        print("  %s %s %s" % ("✅" if cond else "⛔", nombre, detalle))
        ok.append(bool(cond))

    e = Exe(ENTRADA)
    chequear("lee las secciones del exe desempacado", len(e.sec) >= 8, "(%d)" % len(e.sec))
    o, sec = e.off(0x403606)
    chequear("ubica 0x403606 en el código", o is not None and sec is not None, "off %s" % (hex(o) if o else "-"))

    # el caso que TIENE que fallar: los bytes esperados mentidos
    guardado = RECETAS["nop"][0]
    RECETAS["nop"][0] = (guardado[0], "9090909090", guardado[2], guardado[3])
    tmp = os.path.join(TRABAJO, "control_sin_gg.exe")
    try:
        aplicar("nop", tmp, verboso=False)
        chequear("RECHAZA parchar si los bytes no son los esperados", False, "(parcheó igual)")
    except SystemExit as ex:
        chequear("RECHAZA parchar si los bytes no son los esperados", "NO parcheo" in str(ex))
    finally:
        RECETAS["nop"][0] = guardado

    # y el caso bueno: parcha, y cambia EXACTAMENTE los bytes declarados y ninguno más
    for receta in sorted(RECETAS):
        cambios = aplicar(receta, tmp, verboso=False)
        a = open(ENTRADA, "rb").read()
        b = open(tmp, "rb").read()
        distintos = [i for i in range(len(a)) if a[i] != b[i]]
        esperados = sorted(c[0] for c in cambios)
        chequear("«%s» cambia sólo lo declarado" % receta, distintos == esperados,
                 "%d bytes: %s" % (len(distintos), " ".join("%x" % i for i in distintos[:8])))
        chequear("«%s» no cambia el tamaño" % receta, len(a) == len(b))
    if os.path.exists(tmp):
        os.remove(tmp)
    # y que el original siga intacto
    chequear("no tocó el exe de entrada", os.path.getsize(ENTRADA) == len(open(ENTRADA, "rb").read()))
    print("\n%s" % ("→ TODO BIEN" if all(ok) else "→ ⛔ ALGO FALLA"))
    return 0 if all(ok) else 1


def main():
    arg = sys.argv[1:]
    if not arg or arg[0] == "control":
        return control()
    receta = arg[0]
    if receta not in RECETAS:
        raise SystemExit("recetas: %s" % ", ".join(sorted(RECETAS)) + ", control")
    destino = arg[1] if len(arg) > 1 else os.path.join(JUEGO, "EDA_%s.exe" % receta)
    print("receta «%s»  %s" % (receta, os.path.basename(destino)))
    cambios = aplicar(receta, destino)
    print("\n★ %d bytes cambiados -> %s" % (len(cambios), destino))
    return 0


if __name__ == "__main__":
    sys.exit(main())
