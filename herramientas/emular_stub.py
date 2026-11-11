r"""emular_stub -- qué API de Windows emula cada llamada que ASProtect desvió. SIN correr el juego.

El problema (ver `documentacion/MEDICIONES.md`, corridas 4 y 5): ASProtect reemplazó 329
`call dword ptr [IAT]` del juego por llamadas a stubs suyos. Unos 70 se resuelven leyendo
(`desempacar.py api_de_stub`), pero **259 pasan por un despachador común** que es una máquina
virtual ofuscada. Con un depurador por fuera no se llega (corrida 5).

La idea de acá: **no hace falta entenderla, alcanza con hacerla correr**. Tenemos un volcado de
TODA la memoria del juego (`_trabajo/volcado/eda_2_total/`), así que se emula el despachador con
Unicorn sobre esa memoria, poniéndole en la pila la dirección de retorno del sitio que queremos
averiguar — que es justo el dato con el que la VM decide. Se mira dónde termina.

⚠ ESTADO AL 08-nov-2026: A MEDIO CAMINO. La emulación FUNCIONA (la VM de ASProtect corre dentro
  de Unicorn y llega hasta las APIs de Windows de verdad: para el sitio del cartel se la ve pasar
  por `MessageBoxA`). Lo que falta es **elegir cuál de las APIs tocadas es la que pidió el juego**:
  la VM llama primero a varias por su cuenta (`GetCurrentProcessId`, `GetActiveWindow`…), y el
  filtro actual se queda con la primera, que es ruido.
  ⛔ Se probó quedarse con el prefijo común y tomar la primera que se sale de él (`ruido_comun`):
     NO SIRVE. Tres sitios distintos dan **las mismas 26 APIs seguidas**, sin separarse nunca
     (medido el 08-nov). O sea que la VM, arrancada desde cero sobre la memoria volcada, **no toma
     el camino del sitio**: se queda en una rutina suya (carga una DLL, arma cadenas…).
     ⇒ Con la dirección de retorno NO alcanza: le falta algo del estado real (los registros del
     juego al entrar, o algún contexto que ASProtect deja armado en la corrida). Averiguar qué es
     ya es meterse a entender la VM, que es justo lo que este atajo quería evitar.

    py herramientas\emular_stub.py control            # ★ casos de respuesta conocida
    py herramientas\emular_stub.py sitio 0x402cb2     # uno solo
    py herramientas\emular_stub.py todos              # los 329, a _trabajo/apis_emuladas.json

⚠ El que manda es el filtro de la **dirección de retorno**: la VM llama por su cuenta a APIs para
  su propio trabajo (`GetCurrentProcessId` y parecidas). La API de verdad es aquella en la que se
  entra con el retorno AL JUEGO en el tope de la pila. Sin ese filtro, todos los sitios dan lo
  mismo y parece que anduvo.
"""
import bisect
import json
import os
import re
import struct
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                            # noqa: BLE001
    pass

from capstone import CS_ARCH_X86, CS_MODE_32, Cs
from unicorn import (UC_ARCH_X86, UC_HOOK_BLOCK, UC_HOOK_MEM_UNMAPPED,
                     UC_HOOK_MEM_WRITE, UC_MODE_32, Uc, UcError)
from unicorn.x86_const import (UC_X86_REG_CS, UC_X86_REG_DS, UC_X86_REG_EAX, UC_X86_REG_EBP,
                               UC_X86_REG_EIP,
                               UC_X86_REG_ES, UC_X86_REG_ESP, UC_X86_REG_FS, UC_X86_REG_GDTR,
                               UC_X86_REG_SS)

GDT = 0x2F000000           # dónde le ponemos la tabla de segmentos al emulador


def _entrada_gdt(base, limite, acceso, banderas):
    """Una entrada de la tabla de segmentos (formato del 386, 8 bytes)."""
    if limite > 0xFFFFF:
        limite >>= 12
        banderas |= 0x8
    return struct.pack(
        "<HHBBBB", limite & 0xFFFF, base & 0xFFFF, (base >> 16) & 0xFF, acceso,
        ((limite >> 16) & 0xF) | ((banderas & 0xF) << 4), (base >> 24) & 0xFF)


def _poner_segmentos(uc, teb):
    """⚠ La VM de ASProtect lee el TEB por `fs:[...]`. Sin esto lee ceros, se va por un camino
    equivocado y termina saltando a cualquier lado (medido: moría siempre en el mismo eip)."""
    uc.mem_map(GDT, 0x1000)
    # ⚠ todo en anillo 0 (acceso 0x9A/0x92, selectores sin RPL): con descriptores de anillo 3
    #   Unicorn rechaza escribir SS, porque el nivel no coincide con el de CS.
    uc.mem_write(GDT + 1 * 8, _entrada_gdt(0, 0xFFFFFFFF, 0x9A, 0xC))      # código
    uc.mem_write(GDT + 2 * 8, _entrada_gdt(0, 0xFFFFFFFF, 0x92, 0xC))      # datos
    uc.mem_write(GDT + 3 * 8, _entrada_gdt(teb, 0xFFF, 0x92, 0x4))         # fs -> TEB
    uc.reg_write(UC_X86_REG_GDTR, (0, GDT, 0x1000 - 1, 0))
    for r in (UC_X86_REG_DS, UC_X86_REG_ES, UC_X86_REG_SS):
        uc.reg_write(r, 2 << 3)
    uc.reg_write(UC_X86_REG_CS, 1 << 3)
    uc.reg_write(UC_X86_REG_FS, 3 << 3)

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VOLCADO = os.path.join(RAIZ, "_trabajo", "volcado", "eda_2_total")
SALIDA = os.path.join(RAIZ, "_trabajo", "apis_emuladas.json")
BASE_IMG = 0x400000
EXE = (0x401000, 0x90C000)
ARRANQUE = 0x7E3A11        # el OEP (`__tmainCRTStartup`), medido en MEDICIONES.md, corrida 4
PILA = 0x30000000
MEM_IMAGE = 0x1000000
TOPE_PASOS = 12000000      # la VM es lenta: con menos, muchos sitios quedan sin resolver
# ⚠ SIN ESTO LA CORRIDA NO TERMINA NUNCA: medido el 09-nov, un sitio se quedó 26 h sin pasar de
#   los primeros 25. El bucle de abajo le regala 1000 pasos más cada vez que la VM hace un syscall
#   o pide una DLL, y un sitio que gira en falso los pide para siempre. Hay que cortarlo por reloj.
SEGUNDOS_POR_SITIO = int(os.environ.get("EDA_SEGUNDOS", "25"))   # se puede subir sin tocar el código
TOPE_RONDAS = 20000        # cuántas veces se le puede reanudar la emulación a un mismo sitio
CERCA = 160            # el stub devuelve el control unos bytes después del comienzo de la API


class Memoria:
    """La memoria del juego, tal como estaba: 91 MB, 769 regiones."""

    def __init__(self, carpeta=VOLCADO):
        ind = os.path.join(carpeta, "indice.txt")
        if not os.path.exists(ind):
            sys.exit("[!] falta %s — hay que volcar la memoria del juego primero" % ind)
        self.idx = []
        for l in open(ind):
            a, b, c, t = l.split()
            self.idx.append((int(a, 16), int(b, 16), int(c, 16), int(t)))
        self.idx.sort()
        self.bases = [r[0] for r in self.idx]
        self.blob = open(os.path.join(carpeta, "todo.bin"), "rb").read()
        self.md = Cs(CS_ARCH_X86, CS_MODE_32)
        self.mods = self._modulos()

    def region(self, va):
        i = bisect.bisect_right(self.bases, va) - 1
        if i < 0:
            return None
        rb, n, o, t = self.idx[i]
        return self.idx[i] if rb <= va < rb + n else None

    def leer(self, va, n):
        r = self.region(va)
        if not r:
            return None
        rb, sz, o, t = r
        return self.blob[o + (va - rb):o + (va - rb) + n]

    def u32(self, va):
        b = self.leer(va, 4)
        return struct.unpack("<I", b)[0] if b and len(b) == 4 else None

    def _modulos(self):
        """Las DLL cargadas, leídas del propio volcado (no del disco): nombre y exports.
        ⚠ Así se evita el error de la corrida 4 —leer la DLL de 64 bits en vez de la de 32—:
        acá los exports salen de la memoria que el juego tenía de verdad."""
        mods = []
        for rb, sz, o, t in self.idx:
            if t != MEM_IMAGE or self.blob[o:o + 2] != b"MZ":
                continue
            try:
                pe = struct.unpack_from("<I", self.blob, o + 0x3C)[0]
                if self.blob[o + pe:o + pe + 4] != b"PE\0\0":
                    continue
                if struct.unpack_from("<H", self.blob, o + pe + 24)[0] != 0x10B:
                    continue                                   # sólo las de 32 bits
                tam = struct.unpack_from("<I", self.blob, o + pe + 24 + 56)[0]
                erva = struct.unpack_from("<I", self.blob, o + pe + 24 + 96)[0]
                nombre, exp = "?", {}
                if erva:
                    ed = self.leer(rb + erva, 44)
                    (nrva, _base, nfun, nnom, afun, anom,
                     aord) = struct.unpack_from("<IIIIIII", ed, 12)
                    nb = self.leer(rb + nrva, 64)
                    if nb:
                        nombre = nb.split(b"\0")[0].decode("latin1") or "?"
                    nomb = self.leer(rb + anom, 4 * nnom) or b""
                    ords = self.leer(rb + aord, 2 * nnom) or b""
                    funs = self.leer(rb + afun, 4 * nfun) or b""
                    for i in range(nnom):
                        if 4 * i + 4 > len(nomb) or 2 * i + 2 > len(ords):
                            break
                        p = struct.unpack_from("<I", nomb, 4 * i)[0]
                        oi = struct.unpack_from("<H", ords, 2 * i)[0]
                        if 4 * oi + 4 > len(funs):
                            continue
                        fr = struct.unpack_from("<I", funs, 4 * oi)[0]
                        nm = (self.leer(rb + p, 96) or b"").split(b"\0")[0].decode("latin1")
                        if nm:
                            exp[fr] = nm
                if exp:
                    mods.append({"base": rb, "tam": tam, "nombre": nombre,
                                 "exp": exp, "rvas": sorted(exp)})
            except Exception:                                  # noqa: BLE001
                continue
        return mods

    def teb(self):
        """El TEB de 32 bits del hilo principal, con su pila.

        Se lo identifica sin lugar a dudas: se apunta a sí mismo en +0x18, su +0x30 lleva al PEB,
        y **el PEB dice que la imagen del proceso es 0x400000**, que es el juego. ⚠ Con sólo el
        puntero a sí mismo caía en una página cualquiera cuyos límites de pila eran `FFEEFFEE`
        (memoria sin estrenar), y la emulación arrancaba con una pila inválida."""
        if getattr(self, "_teb", None) is None:
            self._teb = (0, 0, 0)
            for rb, sz, o, t in self.idx:
                if t == MEM_IMAGE:
                    continue
                for p in range(rb, rb + sz, 0x1000):
                    if self.u32(p + 0x18) != p:
                        continue
                    peb = self.u32(p + 0x30)
                    if not peb or self.u32(peb + 8) != 0x400000:
                        continue
                    base, limite = self.u32(p + 4) or 0, self.u32(p + 8) or 0
                    if limite and base > limite:
                        self._teb = (p, base, limite)
                        return self._teb
        return self._teb

    def es_de_asprotect(self, va):
        """Memoria que ASProtect pidió al arrancar: ni el exe, ni una DLL. Si una API fue llamada
        y su retorno apunta ahí, la llamó la VM ⇒ es la que el juego pidió. Si el retorno cae en
        una DLL, es una API llamando a otra: ruido de la implementación de Windows."""
        if EXE[0] <= va < EXE[1]:
            return False
        r = self.region(va)
        return bool(r) and r[3] != MEM_IMAGE and va < PILA

    def api_en(self, va):
        for m in self.mods:
            if m["base"] <= va < m["base"] + m["tam"]:
                i = bisect.bisect_right(m["rvas"], va - m["base"]) - 1
                if i < 0:
                    return None
                r = m["rvas"][i]
                if (va - m["base"]) - r <= CERCA:
                    return "%s!%s" % (m["nombre"], m["exp"][r])
                return None
        return None

    def api_que_contiene(self, va):
        """★ La API que CONTIENE esa dirección (el export de mayor dirección que no la pasa),
        sin límite de cercanía. `api_en` sólo reconoce el comienzo de un export (y hace bien: ahí
        no inventa). Esto es para otra pregunta: «¿de qué función es este `ret`?»."""
        for m in self.mods:
            if m["base"] <= va < m["base"] + m["tam"]:
                i = bisect.bisect_right(m["rvas"], va - m["base"]) - 1
                if i < 0:
                    return None, None
                r = m["rvas"][i]
                return "%s!%s" % (m["nombre"], m["exp"][r]), (va - m["base"]) - r
        return None, None

    def es_de_dll(self, va):
        """¿La dirección cae dentro de una DLL cargada (no en el exe del juego)?"""
        if EXE[0] <= va < EXE[1]:
            return False
        r = self.region(va)
        return bool(r) and r[3] == MEM_IMAGE

    # ---------- los sitios desviados ----------
    def sitios(self):
        """★ Cada `call rel32` del juego que ASProtect desvió. Se VERIFICA cada candidato en vez
        de confiar en a dónde se puede llegar.

        ⛔ Antes esto era un barrido RECURSIVO desde los destinos de llamada, y dejaba agujeros:
           daba 312 sitios cuando hay 694. Las funciones a las que no se llega desde otra (el
           punto de entrada, las que se llaman por puntero desde una tabla) quedaban sin recorrer,
           y el exe reconstruido se moría en sitios que estaban a la vista: `0x7E3B16`
           (GetCommandLineA) y `0x7E0B1A` (GetSystemTimeAsFileTime), ninguno en la lista.
        ✅ Ahora: todo `call rel32` que apunte fuera de la imagen, a memoria propia de ASProtect,
           y que además (a) vaya al DESPACHADOR —que se descubre solo: es el destino más llamado,
           637 de 694— o (b) caiga al comienzo de una página (+0 o +4), que es donde ASProtect
           pone los stubs individuales.
        ✅ Por qué la regla no inventa: que 637 candidatos caigan en UNA misma dirección no puede
           ser azar (un `0xE8` desalineado lee 4 bytes cualquiera: la probabilidad de acertar una
           dirección concreta es ~1 en 4.000 millones). Y el control: esta lista CONTIENE los 312
           del barrido recursivo, sin dejar ninguno afuera.
        """
        ini, fin = EXE
        datos = self.leer(ini, fin - ini)
        cand = {}
        i = 0           # ⚠ con un bucle byte a byte esto tardaba >15 min: 5 millones de vueltas
        while (i := datos.find(bytes([0xE8]), i, len(datos) - 5)) >= 0:
            s = ini + i
            t = (s + 5 + struct.unpack_from("<i", datos, i + 1)[0]) & 0xFFFFFFFF
            if not (BASE_IMG <= t < BASE_IMG + 0x600000):
                r = self.region(t)
                if r and r[3] != MEM_IMAGE:
                    cand[s] = t
            i += 1
        if not cand:
            return {}
        from collections import Counter
        desp = Counter(cand.values()).most_common(1)[0][0]
        self.despachador = desp
        return {s: t for s, t in cand.items() if t == desp or (t & 0xFFF) in (0, 4)}


#  ★ los valores marcados del modo `marcas` (ver `robados.py`): se ponen en los registros antes de
#    emular, y cuando la ejecución vuelve al juego se los reconoce para saber qué hizo el código
#    que ASProtect se robó («escribió en ebx+0x2B7C el valor de eax»).
MARCAS = (("eax", "UC_X86_REG_EAX", 0xAAAA0000), ("ebx", "UC_X86_REG_EBX", 0xBBBB0000),
          ("ecx", "UC_X86_REG_ECX", 0xCCCC0000), ("edx", "UC_X86_REG_EDX", 0xDDDD0000),
          ("esi", "UC_X86_REG_ESI", 0x51510000), ("edi", "UC_X86_REG_EDI", 0xD1D10000))


def nombrar_marca(v):
    """Traduce un valor a «registro ± desplazamiento» si cae cerca de una marca."""
    if v is None:
        return None
    for nom, _, m in MARCAS:
        if -0x10000 <= (v - m) <= 0x10000:
            return nom if v == m else "%s%+#x" % (nom, v - m)
    return "%#010x" % v


def secuencia_de(mem, sitio, pasos=TOPE_PASOS, tope=6, marcas=False, anotar=False):
    """(lista de APIs, detalle). Emula el stub de ESE sitio y anota, EN ORDEN, cada API que la VM
    llama por sí misma (o a la que entra con el retorno al juego). La primera no es la que el juego
    pidió: antes la VM llama a un par por su cuenta, siempre las mismas. De eso se ocupa
    `ruido_comun`."""
    b = mem.leer(sitio, 5)
    if not b or b[0] != 0xE8:
        return {"directa": None, "pedido": None, "dll": None, "apis": [], "args": [],
                "detalle": "no hay un call ahí"}
    stub = (sitio + 5 + struct.unpack("<i", b[1:5])[0]) & 0xFFFFFFFF
    if not mem.region(stub):
        return {"directa": None, "pedido": None, "dll": None, "apis": [], "args": [],
                "detalle": "el stub %08x no está en el volcado" % stub}
    uc = Uc(UC_ARCH_X86, UC_MODE_32)
    mapeadas = set()

    def mapear(p):
        p &= ~0xFFF
        if p in mapeadas:
            return
        try:
            uc.mem_map(p, 0x1000)
        except UcError:
            mapeadas.add(p)
            return
        d = mem.leer(p, 0x1000)
        if d:
            uc.mem_write(p, d.ljust(0x1000, b"\0"))
        mapeadas.add(p)

    def falta(uc_, tipo, dir_, tam, val, ud):
        for p in range(dir_ & ~0xFFF, (dir_ + max(tam, 1) + 0xFFF) & ~0xFFF, 0x1000):
            mapear(p)
        return True

    uc.hook_add(UC_HOOK_MEM_UNMAPPED, falta)
    teb, pila_base, pila_limite = mem.teb()
    if teb:
        _poner_segmentos(uc, teb)
        mapear(teb)
        # ★ la pila DE VERDAD del hilo, la que dice el TEB. Con una pila inventada la VM se da
        #   cuenta de que el entorno no es el suyo y se va por el camino de error: todos los
        #   sitios daban la misma secuencia (GetCurrentProcessId, GetActiveWindow, MessageBoxA).
        for p in range(pila_limite, pila_base, 0x1000):
            mapear(p)
        esp = (pila_base - 0x2000) & ~0xF
        # ⚠ la pila volcada trae las llamadas VIEJAS de esa corrida: si no se borran, el filtro
        #   de "quién llamó" se engancha con un retorno que quedó ahí y da una API equivocada.
        try:
            uc.mem_write(pila_limite, bytes(esp - pila_limite))
        except UcError:
            pass
    else:
        uc.mem_map(PILA, 0x200000)
        mapeadas.add(PILA)
        esp = PILA + 0x100000
    # ⚠ el stub hace `inc dword ptr [esp]` para saltear el byte sobrante del `call` original
    #   (medía 6, quedó en 5), así que el retorno al juego puede ser +5 o +6.
    retorno = sitio + 5
    retornos = (sitio + 5, sitio + 6)
    uc.mem_write(esp, struct.pack("<I", retorno))
    uc.reg_write(UC_X86_REG_ESP, esp)
    uc.reg_write(UC_X86_REG_EBP, esp + 0x800)
    hallado, tocadas, salto64, pedido, dll, reanudar = [], [], [], [], [], []
    directas, args_vistos, vuelto = [], [], []
    vuelta, escrituras, regs_vuelta, ultimo_dll = [], [], {}, []
    if marcas:
        import unicorn.x86_const as _c
        for _nom, _reg, _val in MARCAS:
            uc.reg_write(getattr(_c, _reg), _val)

        def _escribio(uc_, tipo, dir_, tam, val, ud):
            if vuelta:
                return
            n = nombrar_marca(dir_)
            # sólo las escrituras que tocan algo apuntado por un registro marcado, o un dato de
            # la imagen del juego: el resto es la VM trabajando en su propia memoria.
            if not n.startswith("0x"):
                escrituras.append((n, tam, nombrar_marca(val)))
            elif EXE[1] <= dir_ < 0x9D7000:
                escrituras.append(("%#010x" % dir_, tam, nombrar_marca(val)))

        if anotar:
            # ⚠ CARO: un enganche por ESCRITURA pasa por Python millones de veces y la
            #   corrida se vuelve lentisima. Solo se pide en la 2a pasada, cuando ya se sabe
            #   que el sitio tiene codigo robado y hace falta ver que hacia.
            uc.hook_add(UC_HOOK_MEM_WRITE, _escribio)
    arena = [ARENA]                   # de dónde sale la próxima memoria que pida la VM

    def paso(uc_, dir_, tam, ud):
        # ★ modo marcas (`robados.py`): el PRIMER bloque del código del juego al que vuelve la VM.
        #   +6 = una llamada normal; más que eso = ASProtect se robó (vuelve_a - 6) bytes de
        #   código de ahí. No se corta la emulación: sólo se anota el punto y los registros de
        #   ese momento, que es lo que dice qué hacían los bytes robados.
        if marcas and not vuelta and mem.es_de_dll(dir_):
            # ★★ el ÚLTIMO bloque que se ejecutó dentro de una DLL antes de devolverle el control
            #    al juego: ahí está el `ret N` de la API que el juego pidió. La función que lo
            #    contiene ES la respuesta. (`api_en` no la ve porque el stub entra a la API unos
            #    bytes después del comienzo, y `api_en` sólo reconoce comienzos.)
            ultimo_dll[:] = [dir_]
        if marcas and not vuelta and EXE[0] <= dir_ < EXE[1] and dir_ != sitio:
            import unicorn.x86_const as _c2
            vuelta.append(dir_)
            regs_vuelta.update({n: nombrar_marca(uc_.reg_read(getattr(_c2, r)))
                                for n, r, _ in MARCAS})
            # ★★ Y LOS BYTES DE ARGUMENTO, que es el dato más duro que da esto: las API de
            #    Windows son `stdcall`, las limpia la propia API. Cuando el control vuelve al
            #    juego, ESP quedó en (el de entrada) + 4 del retorno + los argumentos. O sea que
            #    esta resta DICE cuántos argumentos tenía la API de verdad, medido, sin contar
            #    `push` del juego (que se entrelazan entre llamadas y no sirven de juez).
            vuelta.append(uc_.reg_read(UC_X86_REG_ESP) - esp - 4)
        try:
            if uc_.mem_read(dir_, 1)[0] == 0xEA:      # jmp far: la puerta a 64 bits
                salto64.append(dir_)
                uc_.emu_stop()
                return
        except UcError:
            pass
        if dir_ in retornos:                  # volvió al juego: la llamada terminó
            uc_.emu_stop()
            return
        a = mem.api_en(dir_)
        if not a:
            return
        try:
            ret = struct.unpack("<I", uc_.mem_read(uc_.reg_read(UC_X86_REG_ESP), 4))[0]
        except Exception:                                      # noqa: BLE001
            return
        fn = a.split("!")[1]
        # ★★ El stub no «emula» la API: la BUSCA POR NOMBRE, como haría cualquiera.
        #    Carga la DLL y después pide la función. Ese nombre es la respuesta que buscamos.
        if fn in PIDE_NOMBRE:
            p = _arg(uc_, 2)
            nombre = _cadena(uc_, p)
            if nombre:
                pedido.append(nombre)
            elif p and p < 0x10000:
                pedido.append("#%d" % p)                        # pedida por número, no por nombre
            uc_.emu_stop()
            return
        if fn in ARGS:
            # Se le contesta con el módulo que el juego ya tenía cargado, y listo: emular
            # LoadLibrary de verdad es carísimo y encima acá no hay disco del cual cargar.
            p1 = _arg(uc_, 1)
            nd = _cadena(uc_, p1) or _cadena(uc_, p1, ancho=2) or ""
            dll.append(nd)
            # ★★ Y SE ANOTA (09-nov). Éstas las contestamos nosotros, así que nunca llegaban a
            #    la lista de APIs vistas — y resulta que una de ellas PUEDE SER la que el juego
            #    pidió. 72 de los 117 sitios sin resolver eran exactamente esto: la traza completa
            #    de 0x40A6A8 muestra a la VM llamando a GetModuleHandleA y volviendo al juego,
            #    mientras nosotros informábamos «sólo hizo su rutina».
            args_vistos.append((a, p1 or 0, nd, ret))
            base = 0
            for mo in mem.mods:
                if mo["nombre"].lower() == nd.lower().strip():
                    base = mo["base"]
                    break
            _retornar(uc_, base, ARGS[fn])
            reanudar.append(1)
            uc_.emu_stop()     # en Unicorn, cambiar EIP dentro del hook exige parar y seguir
            return
        # ★★ la memoria que la VM pide para trabajar: se la damos nosotros (ver ASIGNAN arriba)
        if fn in ASIGNAN:
            n = max(min(_arg(uc_, TAM_EN.get(fn, 2)) or 0x1000, 0x200000), 0x1000)
            p = arena[0]
            for q in range(p, (p + n + 0xFFF) & ~0xFFF, 0x1000):
                mapear(q)                       # fuera del volcado ⇒ páginas en cero, como recién pedidas
            arena[0] = (p + n + 0xFFF) & ~0xFFF
            _retornar(uc_, p, ASIGNAN[fn])
            reanudar.append(1)
            uc_.emu_stop()
            return
        tocadas.append(a)
        # ★★ LA SEÑAL FUERTE (09-nov): entrar en una API con el retorno AL JUEGO en el tope de la
        #    pila. Tiene que ser así, porque el stub arma la llamada para que la API le devuelva el
        #    control al juego directamente — por eso hace `inc dword ptr [esp]`. Ninguna llamada
        #    que la VM haga para su propio trabajo puede tener eso en la pila.
        #    ⚠ Sin esto, la regla era "la primera API útil" y se equivocaba: en 0x40AF2F daba
        #      MessageBoxA donde el juego empuja UN argumento (es FreeLibrary), y en 0x7FAE04 daba
        #      VirtualAlloc (4 argumentos) donde el juego empuja un puntero (es DeleteFileA).
        if ret in retornos:
            directas.append(a)
            # ★ y SE ANOTA A CUÁL de los dos vuelve (10-nov): +6 quiere decir que el stub hizo
            #   `inc dword ptr [esp]`, o sea que el `call` original medía 6 bytes
            #   (`call dword ptr [casillero]`) y restaurarlo en su lugar es correcto. +5 querría
            #   decir que el original ya medía 5 y escribir 6 le come un byte de código real.
            vuelto.append(ret - sitio)
            uc_.emu_stop()
            return
        # ★ si no, sólo cuentan las llamadas que hace la VM misma: un retorno que cae dentro de una
        #   DLL es una API de Windows llamando a otra = ruido de la implementación.
        if mem.es_de_asprotect(ret):
            if not hallado or hallado[-1] != a:
                hallado.append(a)
                if len(hallado) >= tope:
                    uc_.emu_stop()

    # ⚠ por BLOQUE, no por instrucción: el enganche de Unicorn pasa por Python y con uno por
    #   instrucción esto tardaba ~100 s por sitio (9 horas para los 329). Todo lo que miramos
    #   —entrar en una API, volver al juego, el salto a 64 bits— empieza un bloque, así que se ve igual.
    uc.hook_add(UC_HOOK_BLOCK, paso)
    for p in range(stub & ~0xFFF, (stub & ~0xFFF) + 0x8000, 0x1000):
        mapear(p)
    # ⚠ Windows de 64 bits atiende los syscalls de un programa de 32 saltando a modo 64
    #   (`jmp far 0033:...`, la «puerta del cielo»). El emulador es de 32 y ahí se muere.
    #   Como lo único que nos importa es adónde va la VM, se simula que el syscall salió bien:
    #   se vuelve a quien lo llamó con 0 en EAX.
    inicio, restantes = stub, pasos
    t0, rondas = time.time(), 0
    def fin(detalle):
        return {"directa": directas[0] if directas else None,
                "pedido": pedido[0] if pedido else None,
                "dll": next((d for d in reversed(dll) if d and d.lower().endswith(".dll")), None),
                "apis": hallado, "args": args_vistos, "detalle": detalle,
                "vuelve_a": vuelto[0] if vuelto else None,
                "vuelve_al_juego": (vuelta[0] - sitio) if vuelta else None,
                "bytes_de_argumento": vuelta[1] if len(vuelta) > 1 else None,
                "ultimo_en_dll": ultimo_dll[0] if ultimo_dll else None,
                "regs": dict(regs_vuelta) if regs_vuelta else None,
                "escrituras": escrituras}

    while True:
        resto = SEGUNDOS_POR_SITIO - (time.time() - t0)
        rondas += 1
        if resto <= 0 or rondas > TOPE_RONDAS:
            if not (vuelta or directas or hallado or pedido):
                return fin("se pasó del tiempo (%d rondas, %.0f s)" % (rondas, time.time() - t0))
            break
        try:
            # el 3er argumento es el tope de MICROsegundos: el corte duro, por si el sitio gira
            # en falso dentro de un solo bloque y el contador de pasos no llega a frenarlo.
            uc.emu_start(inicio, 0, int(resto * 1000000), restantes)
        except UcError as e:
            if not (vuelta or directas or hallado or pedido):
                return fin("%s en eip %08x" % (e, uc.reg_read(UC_X86_REG_EIP)))
            break
        if (marcas and vuelta) or directas or pedido or len(hallado) >= tope:
            break
        if salto64:                       # un syscall: se contesta que salió bien y se sigue
            esp = uc.reg_read(UC_X86_REG_ESP)
            try:
                inicio = struct.unpack("<I", uc.mem_read(esp, 4))[0]
            except UcError:
                break
            uc.reg_write(UC_X86_REG_ESP, esp + 4)
            uc.reg_write(UC_X86_REG_EAX, 0)
            salto64.clear()
        elif reanudar:                    # le contestamos a un LoadLibrary: seguir donde quedó
            inicio = uc.reg_read(UC_X86_REG_EIP)
            reanudar.clear()
        else:
            break
        # ⚠ no se le descuenta nada: ahora que se le contesta la memoria que pide, la VM da muchas
        #   más vueltas y cada una es legítima. El que corta es el reloj de arriba.
        restantes = pasos
    if vuelta or directas or pedido or hallado or args_vistos:
        return fin("ok")
    return fin("no llamó a ninguna API (pasó por: %s)" % (
        ", ".join(dict.fromkeys(tocadas[:5])) or "ninguna"))


# ---------- ★ lo que el stub hace de verdad: resolver la API POR NOMBRE ----------
ARGS = {"LoadLibraryA": 4, "LoadLibraryW": 4, "LoadLibraryExA": 12, "LoadLibraryExW": 12,
        "GetModuleHandleA": 4, "GetModuleHandleW": 4, "GetModuleHandleExA": 12,
        "GetModuleHandleExW": 12}
PIDE_NOMBRE = ("GetProcAddress", "LdrGetProcedureAddress", "LdrGetProcedureAddressForCaller")

# ★★ LO QUE DESTAPÓ TODO (medido el 09-nov). La VM pide memoria para trabajar. Si se la deja
#    ejecutar de verdad, VirtualAlloc termina en un syscall —que un emulador de 32 bits no puede
#    hacer— y se le contestaba 0: la reserva FALLABA y la VM se iba por su camino de error ANTES
#    de pedir la API por su nombre. Resultado: de 274 sitios resueltos, 272 salían por heurística
#    y 161 "daban" VirtualAlloc, que no era del juego sino de la propia VM.
#    ⇒ Hay que contestarle con memoria DE VERDAD del emulador, igual que con LoadLibrary.
ARENA = 0x60000000         # de acá le damos la memoria que pida
ASIGNAN = {"VirtualAlloc": 16, "VirtualAllocEx": 20, "HeapAlloc": 12, "RtlAllocateHeap": 12,
           "LocalAlloc": 8, "GlobalAlloc": 8}
TAM_EN = {"HeapAlloc": 3, "RtlAllocateHeap": 3}        # cuál argumento dice el tamaño (si no, el 2º)
# ⚠ Y SÓLO esas. Probé simulando también VirtualProtect/VirtualFree/GetCurrentProcess y fue peor:
#    cualquiera de ellas puede ser LA API que el juego pidió, así que contestarlas por él borra la
#    respuesta (medido: 0x40B0AE, que es GetCurrentProcess, dejó de resolverse). Las que no tienen
#    un dato de salida crítico pueden ejecutarse de verdad: su syscall devuelve 0 = NT_SUCCESS.


def _arg(uc, n):
    """El n-ésimo argumento de una llamada stdcall recién entrada (1 = el primero)."""
    try:
        return struct.unpack("<I", uc.mem_read(uc.reg_read(UC_X86_REG_ESP) + 4 * n, 4))[0]
    except Exception:                                          # noqa: BLE001
        return 0


def _cadena(uc, p, ancho=1, largo=120):
    if not p:
        return None
    try:
        d = bytes(uc.mem_read(p, largo))
    except Exception:                                          # noqa: BLE001
        return None
    s = (d.split(b"\0\0")[0].decode("utf-16le", "replace") if ancho == 2
         else d.split(b"\0")[0].decode("latin1", "replace"))
    return s if s and s.isprintable() and len(s) > 1 else None


def _retornar(uc, eax, limpiar):
    """Contestarle a una API sin ejecutarla: devolver `eax` y volver a quien la llamó."""
    esp = uc.reg_read(UC_X86_REG_ESP)
    try:
        ret = struct.unpack("<I", uc.mem_read(esp, 4))[0]
    except Exception:                                          # noqa: BLE001
        return
    uc.reg_write(UC_X86_REG_EAX, eax)
    uc.reg_write(UC_X86_REG_ESP, esp + 4 + limpiar)
    uc.reg_write(UC_X86_REG_EIP, ret)


def ruido_comun(mem, muestra=(0x402CB2, 0x7E39BD, 0x4077D2, 0x409813, 0x40A0D7)):
    """Lo que la VM llama SIEMPRE, antes de la que pidió el juego: el prefijo común a varios
    sitios. ★ Se deriva midiendo, no se escribe a mano: si mañana cambia, cambia solo."""
    listas = [secuencia_de(mem, s)[0] for s in muestra]
    listas = [l for l in listas if l]
    if len(listas) < 2:
        return []
    pref = []
    for i in range(min(len(l) for l in listas)):
        if len({l[i] for l in listas}) == 1:
            pref.append(listas[0][i])
        else:
            break
    return pref


RUTINA = ("GetCurrentProcessId", "RtlSetLastWin32Error")   # lo que el stub hace siempre, primero


def cadena_del_stub(mem, sitio, saltos=8):
    """TODOS los escalones por los que pasa el stub, siguiendo `jmp X` y `push X; ret`.

    ⚠ No alcanza con el último: ASProtect copia el comienzo de la API a su memoria y desde ahí
      salta, y a veces la cadena termina en una rutina INTERNA compartida de la DLL (el prólogo de
      excepciones `__SEH_prolog4`, en `0x76BB2F3C`), que no es ningún export. Los bytes que sirven
      son los del escalón ANTERIOR, el que está en memoria de ASProtect. Medido el 09-nov en
      `0x7F2DFD` y en 7 sitios más que caían todos en la misma rutina interna."""
    b = mem.leer(sitio, 5)
    if not b or b[0] != 0xE8:
        return []
    d = (sitio + 5 + struct.unpack("<i", b[1:5])[0]) & 0xFFFFFFFF
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    cadena = []
    for _ in range(saltos):
        datos = mem.leer(d, 0x40)
        if not datos:
            return cadena
        cadena.append(d)
        empuje, sig = None, None
        for i in md.disasm(datos, d):
            if i.mnemonic == "push" and i.op_str.startswith("0x"):
                empuje = int(i.op_str, 16)
            elif i.mnemonic == "jmp" and i.op_str.startswith("0x"):
                sig = int(i.op_str, 16)
                break
            elif i.mnemonic == "ret":
                sig = empuje
                break
            elif i.mnemonic in ("call", "jmp"):
                break
        if sig is None or not mem.region(sig):
            return cadena
        d = sig
    return cadena


def final_del_stub(mem, sitio, saltos=8):
    c = cadena_del_stub(mem, sitio, saltos)
    return c[-1] if c else None


_NOMBRES_PEDIDOS = set()


def nombres_pedidos(mem):
    """★ Los nombres de API que están escritos en la memoria PROPIA de ASProtect.

    Hallazgo del 09-nov: en esa memoria está la **tabla de nombres de imports original del juego**,
    descifrada (en `0x05378000` se lee la lista clásica del CRT de Visual C++: GetCurrentThreadId,
    GetCommandLineA, GetVersionExA, ExitProcess, GetProcAddress, SetHandleCount, GetStdHandle…).
    Tiene sentido: ASProtect tuvo que resolver cada una por nombre al arrancar.

    Sirve para dos cosas:
      - desempatar cuando varias APIs tienen los MISMOS bytes (medido: el stub de 0x7EC09C copia
        un cuerpo que sólo devuelve su argumento, igual en `SetHandleCount`, `GdiGetLocalFont`,
        `WTHelperProvDataFromStateData` e `InternalCStdIdentityGetIProxyManager`; de las cuatro,
        sólo `SetHandleCount` está acá);
      - desconfiar de cualquier respuesta cuyo nombre NO esté en la lista.
    ⚠ Es sobre-inclusiva: también están las que usa el propio ASProtect. Vale como filtro, no
      como respuesta.
    Control al revés (medido): `GetCurrentThreadId`, que sabemos por otro camino, SÍ está;
    `CreateWaitableTimerExW` (plausible pero no usada) y un nombre inventado, NO."""
    if _NOMBRES_PEDIDOS:
        return _NOMBRES_PEDIDOS
    conocidos = {}
    for m in mem.mods:
        for nombre in m["exp"].values():
            conocidos.setdefault(len(nombre), set()).add(nombre.encode())
    for rb, sz, o, t in mem.idx:
        if t == MEM_IMAGE:                 # sólo la memoria propia, no el código de las DLL
            continue
        # ⚠ no sirve cortar por bytes cero: en la tabla de imports cada nombre viene precedido por
        #   2 bytes de «pista» que no siempre traen un cero, así que el pedazo sale pegado a ellos
        #   y no coincide con ningún export (me pasó el 09-nov: no encontraba `SetHandleCount`).
        for m2 in re.finditer(rb"[A-Za-z_][A-Za-z0-9_@]{4,62}", mem.blob[o:o + sz]):
            pedazo = m2.group()
            if pedazo in conocidos.get(len(pedazo), ()):
                _NOMBRES_PEDIDOS.add(pedazo.decode())
    return _NOMBRES_PEDIDOS


_INDICE_BYTES = {}


def _indice_de_cuerpos(mem, largo=24):
    """{primeros 8 bytes: [(dll, función, los `largo` bytes)]} de CADA export de CADA DLL del
    volcado. Se arma una sola vez. Es el generador del dato: los bytes salen de las DLL mismas."""
    if _INDICE_BYTES:
        return _INDICE_BYTES
    for m in mem.mods:
        for rva, nombre in m["exp"].items():
            b = mem.leer(m["base"] + rva, largo)
            if b and len(b) == largo:
                _INDICE_BYTES.setdefault(b[:8], []).append((m["nombre"], nombre, b))
    return _INDICE_BYTES


def api_por_bytes(mem, sitio, largo=24):
    """★ Qué API es un sitio cuyo stub se COPIÓ EL CUERPO de la función.

    Descubierto el 09-nov con `0x7E9045`: el stub hace `inc dword ptr [esp]` y
    `push 0x3BC0000; ret`, y en 0x3BC0000 hay `mov eax, fs:[0x24]; ret` — que es
    `GetCurrentThreadId` ENTERA. Para funciones cortas, ASProtect no salta a la DLL: se trae el
    código. Por eso esos sitios no tocan ninguna API y la emulación no ve nada.
    ⇒ Se comparan los bytes copiados contra el comienzo de cada export del volcado.

    Devuelve (dll!función, detalle) o (None, por qué). Sólo contesta si todas las coincidencias
    son la MISMA función (varias DLL pueden exportar la misma), porque medio Windows comparte el
    mismo prólogo y una coincidencia ambigua no dice nada."""
    cadena = cadena_del_stub(mem, sitio)
    if not cadena:
        return None, "no se pudo seguir el stub"
    # ★ Se prueba escalón por escalón, del último al primero: lo que vale puede estar en el medio
    #   (ver cadena_del_stub). El último escalón primero porque es el que más se parece a la API.
    porque = "no se pudo seguir el stub"
    for d in reversed(cadena):
        a, porque = _api_de_un_escalon(mem, d, largo)
        if a:
            return a, porque
    return None, porque


def _api_de_un_escalon(mem, d, largo=24):
    # ★ Caso 1: el stub salta DENTRO de la API, unos bytes después del comienzo (copió el prólogo
    #   y sigue ahí). El export que empieza justo antes es la respuesta.
    a = mem.api_en(d)
    if a:
        return a, "ok (el stub salta dentro de la API)"
    # ⛔ Lo que NO se hace: aceptar un destino que cae en una DLL pero LEJOS del comienzo de un
    #    export. Probado el 09-nov: daba 9 sitios más, con destinos a 11.032 y 18.700 bytes del
    #    export más cercano — a esa distancia ya es otra función, y uno de ellos contradecía a la
    #    emulación (decía CryptReleaseContext donde la emulación decía CryptAcquireContextA).
    #    `api_en` ya acepta hasta CERCA=160 bytes, que es lo que ASProtect copia de verdad.
    for m in mem.mods:
        if m["base"] <= d < m["base"] + m["tam"]:
            return None, "cae en %s lejos de todo export" % m["nombre"]
    cuerpo = mem.leer(d, largo)
    if not cuerpo or len(cuerpo) < largo:
        return None, "no se pudo leer el destino %08x" % d
    # ★★ Cuando la API empieza con `push <tam>; call __SEH_prolog4`, ASProtect copia ese comienzo
    #    y arma la llamada a mano. Entre los números que empuja está **la dirección de retorno,
    #    que es un punto DENTRO de la API real**. Medido el 09-nov en `0x7F2DFD`:
    #        push 0x20 · push 0x76C31810 · push 0x76B2F8BC · push 0x76BB2F3C · ret
    #    el 3º es la API (el 4º es el prólogo compartido, que no es export de nada).
    #    ⇒ Cualquier inmediato del cuerpo copiado que caiga justo después de un export, sirve.
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    for ins in md.disasm(cuerpo, d):
        if ins.mnemonic != "push" or not ins.op_str.startswith("0x"):
            continue
        a2 = mem.api_en(int(ins.op_str, 16))
        if a2:
            return a2, "ok (el stub empuja una dirección dentro de la API)"
        if ins.mnemonic == "ret":
            break
    cand = _indice_de_cuerpos(mem, largo).get(cuerpo[:8], [])
    exactos = [c for c in cand if c[2] == cuerpo]
    if not exactos:
        # ⚠ el cuerpo copiado puede terminar antes de los `largo` bytes (`ret` y basura después):
        #    se compara sólo hasta el primer `ret` / `jmp` del cuerpo.
        corte = next((k for k in range(1, largo) if cuerpo[k - 1] in (0xC3, 0xC2, 0xE9)), largo)
        exactos = [c for c in cand if c[2][:corte] == cuerpo[:corte]]
        if not exactos:
            return None, "los bytes de %08x no son el comienzo de ningún export" % d
    nombres = {c[1] for c in exactos}
    if len(nombres) != 1:
        # ★ Desempate: de los candidatos con los mismos bytes, el que ASProtect tiene escrito por
        #   nombre en su memoria (ver `nombres_pedidos`). Sólo vale en POSITIVO: la lista está
        #   incompleta —medido: cubre el bloque del CRT pero no toda la tabla, y faltan APIs
        #   clarísimas del juego como DeleteFileA— así que que un nombre NO esté no dice nada.
        pedidos = nombres_pedidos(mem)
        cortos = [c for c in exactos if c[1] in pedidos]
        if len({c[1] for c in cortos}) != 1:
            return None, "ambiguo: %s" % ", ".join(sorted(nombres)[:4])
        exactos = cortos
        return ("%s!%s" % (exactos[0][0], exactos[0][1]),
                "ok (cuerpo copiado; desempatado por el nombre que ASProtect guarda)")
    return "%s!%s" % (exactos[0][0], exactos[0][1]), "ok (el stub copió el cuerpo de la función)"


def resolver(mem, sitio, pasos=TOPE_PASOS):
    """(api, detalle): qué API de Windows esconde ese `call`.

    El stub **carga la DLL y busca la función ahí dentro**. Así que la respuesta es la primera API
    que ejecuta que (a) no sea de su rutina de siempre y (b) sea de la DLL que acaba de cargar.
    ⚠ Sin simular el `LoadLibrary` esto no se ve: la carga de verdad mete decenas de llamadas de
    Windows por el medio y tapan la buena."""
    r = secuencia_de(mem, sitio, pasos=pasos, tope=14)
    if r["directa"]:                      # ★★ entró en la API con el retorno al juego: es ÉSA
        return r["directa"], "ok (entró con el retorno al juego)"
    if r["pedido"]:                       # lo pidió por nombre con GetProcAddress
        return "%s!%s" % (r["dll"] or "?", r["pedido"]), "ok (pedida por nombre)"
    utiles = [a for a in r["apis"] if a.split("!")[1] not in RUTINA]
    if r["dll"]:
        dela = [a for a in utiles if a.split("!")[0].lower() == r["dll"].lower()]
        if dela:
            return dela[0], "ok (de la DLL que cargó)"
    if utiles:
        return utiles[0], "ok (sin confirmar con la DLL)"
    # ★★ Las que simulamos (LoadLibrary/GetModuleHandle) también pueden SER la que el juego pidió.
    #    Se distinguen por el argumento: la que la VM hace para su propio trabajo apunta a un texto
    #    de SU memoria («KERNEL32.dll»), la del juego apunta a datos del exe. Si no se puede
    #    distinguir, vale la ÚLTIMA: la VM hace su trabajo primero y la llamada del juego al final.
    #    La VM carga su DLL SIEMPRE, con el nombre guardado en SU memoria: ésas se descartan
    #    («LoadLibraryA("KERNEL32.dll")» con el texto en 0x038412b4). Lo que queda, si queda, es
    #    del juego. ⚠ No vale quedarse con «la última» sin este filtro: en 0x64FE4E la única que
    #    hay es la de la VM y daba `LoadLibraryA` por un sitio que empuja un puntero de una
    #    estructura; y en 0x40A6A8, descartada ésa, queda GetModuleHandleA — que es la correcta,
    #    porque el texto que el juego empuja ahí dice «NTDLL.DLL».
    av = [x for x in (r.get("args") or [])
          if not (x[2] and x[2].lower().endswith(".dll") and not EXE[0] <= x[1] < EXE[1])]
    if av:
        del_juego = [x for x in av if EXE[0] <= x[1] < EXE[1]]
        if del_juego:
            return del_juego[-1][0], "ok (la simulamos; el argumento es del juego)"
        return av[-1][0], "ok (la simulamos; descartada la carga de la VM)"
    # ★ último recurso: los stubs que se copiaron el CUERPO de la función (ver api_por_bytes)
    a, d = api_por_bytes(mem, sitio)
    if a:
        return a, d
    return None, r["detalle"] if r["detalle"] != "ok" else (
        "sólo hizo su rutina%s" % (" (cargó %s)" % r["dll"] if r["dll"] else ""))


def control(mem):
    """★ Casos de respuesta CONOCIDA y VARIADA (si todos dieran lo mismo, el método no serviría):
       - 0x402CB2 es el que muestra el cartel de GameGuard ⇒ MessageBox (se ve en pantalla);
       - 0x4077D2 y 0x409813 tienen que dar APIs DISTINTAS entre sí y de la anterior;
       - y el control al revés: donde no hay un `call` desviado, no puede salir nada."""
    ok = True

    def chequear(n, c, d=""):
        nonlocal ok
        print("  %s %s %s" % ("✅" if c else "⛔", n, d))
        ok = ok and c

    print("control sobre %s (%d DLL con exports)" % (VOLCADO, len(mem.mods)))
    a1, d1 = resolver(mem, 0x402CB2)
    chequear("0x402CB2 es el cartel (MessageBox)", bool(a1) and "MessageBox" in a1, a1 or d1)
    a2, d2 = resolver(mem, 0x4077D2)
    a3, d3 = resolver(mem, 0x409813)
    chequear("otros dos sitios resuelven", bool(a2) and bool(a3), "%s / %s" % (a2 or d2, a3 or d3))
    chequear("y dan APIs DISTINTAS entre sí", len({a1, a2, a3} - {None}) == 3,
             str(sorted({a1, a2, a3} - {None})))
    a4, d4 = resolver(mem, 0x402000, pasos=2000)
    chequear("NO inventa nada donde no hay call desviado", a4 is None, a4 or d4)
    print("  →", "TODO BIEN" if ok else "ALGO FALLA")
    return ok


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "control"
    mem = Memoria()
    if cmd == "control":
        return 0 if control(mem) else 1
    if cmd == "sitio":
        s = int(sys.argv[2], 0)
        a, d = resolver(mem, s)
        print("%08x -> %s   [%s]" % (s, a or "sin resolver", d))
        return 0
    if cmd == "bytes":
        a, d = api_por_bytes(mem, int(sys.argv[2], 0))
        print("%s -> %s   [%s]" % (sys.argv[2], a or "sin resolver", d))
        return 0
    if cmd == "sitios":
        # la lista cruda, para que otras herramientas no tengan que repetir el barrido
        # ⚠ y sobre todo para que NO lo hagan lineal: el lineal se desincroniza y da miles de
        #   sitios fantasma (medido el 09-nov: 14.295 contra los 310 de verdad).
        ss = sorted(mem.sitios())
        ruta = os.path.join(RAIZ, "_trabajo", "sitios_desviados.txt")
        open(ruta, "w").write("".join("%08x\n" % s for s in ss))
        print("%d sitios -> %s" % (len(ss), ruta))
        return 0
    if cmd == "cruzar":
        # ★★ EL CONTROL INDEPENDIENTE (09-nov). ASProtect pone su VM en una dirección distinta en
        #    cada corrida, así que dos volcados de dos corridas son dos mediciones separadas del
        #    mismo dato. Si las dos dan la misma API para un sitio, la respuesta no depende de la
        #    corrida. ⚠ Contar los `push` del juego NO sirve de juez: los argumentos se entrelazan
        #    entre llamadas (medido: en 0x40B0AE el `push 0x80` es de la llamada siguiente).
        otra = sys.argv[2] if len(sys.argv) > 2 else os.path.join(
            RAIZ, "_trabajo", "volcado", "eda_3")
        cuantos = int(sys.argv[3]) if len(sys.argv) > 3 else 0
        mem2 = Memoria(otra)
        a1, a2 = sorted(mem.sitios()), sorted(mem2.sitios())
        comunes = sorted(set(a1) & set(a2))
        print("sitios: %d en el 1º, %d en el 2º, %d en los dos" % (len(a1), len(a2), len(comunes)))
        # ★ modo incremental: saltear los que ya están validados en apis_cruzadas.json, para no
        #   volver a pagar 1,5 h cuando se agregan sitios nuevos o se mejora el resolvedor.
        if "--faltantes" in sys.argv:
            ya = os.path.join(RAIZ, "_trabajo", "apis_cruzadas.json")
            tengo = set()
            if os.path.exists(ya):
                tengo = {int(k, 16) for k in json.load(open(ya, encoding="utf-8"))}
            comunes = [s for s in comunes if s not in tengo]
            print("sólo los que faltan: %d (ya validados %d)" % (len(comunes), len(tengo)))
        if cuantos and cuantos < len(comunes):      # una muestra repartida, no los primeros
            paso_ = len(comunes) / float(cuantos)
            comunes = [comunes[int(i * paso_)] for i in range(cuantos)]
            print("se controla una muestra repartida de %d" % len(comunes))
        igual, distinto, incompleto = [], [], []
        for i, s in enumerate(comunes, 1):
            x, _ = resolver(mem, s)
            y, _ = resolver(mem2, s)
            if x and y:
                (igual if x == y else distinto).append((s, x, y))
            else:
                incompleto.append((s, x, y))
            print("  %3d/%d %08x  %-40s %s %s" % (
                i, len(comunes), s, x or "-", "==" if x and x == y else "!=", y or "-"),
                flush=True)
        d = len(igual) + len(distinto)
        print("\n★ los dos volcados contestan para %d sitios:" % d)
        if d:
            print("   ✅ coinciden: %d (%.0f %%)" % (len(igual), 100.0 * len(igual) / d))
            print("   ⛔ difieren:  %d (%.0f %%)" % (len(distinto), 100.0 * len(distinto) / d))
        print("   uno de los dos no resolvió: %d" % len(incompleto))
        # ★ y se guarda lo que SOBREVIVIÓ al control: es esto, no la corrida suelta, lo que
        #   tiene que alimentar a `desempacar.py`. Una respuesta que no se repite en otra corrida
        #   no entra al exe.
        ruta = os.path.join(RAIZ, "_trabajo", "apis_cruzadas.json")
        previas = {}
        if "--faltantes" in sys.argv and os.path.exists(ruta):
            previas = json.load(open(ruta, encoding="utf-8"))
        previas.update({"%08x" % s: x for s, x, _ in igual})
        json.dump(dict(sorted(previas.items())), open(ruta, "w", encoding="utf-8"), indent=1)
        print("   -> %s (%d nuevas, %d en total)" % (ruta, len(igual), len(previas)))
        for s, x, y in distinto[:25]:
            print("   %08x  %-40s  vs  %s" % (s, x, y))
        return 0
    if cmd == "todos":
        sitios = mem.sitios()
        print("sitios desviados: %d" % len(sitios))
        res, fallos, comos = {}, {}, {}

        def guardar():
            json.dump({"%08x" % k: v for k, v in sorted(res.items())},
                      open(SALIDA, "w", encoding="utf-8"), indent=1)
            # ★ y aparte CÓMO salió cada uno: "pedida por nombre" es la vía confiable (el stub
            #   pide la función por su nombre y lo leemos), el resto es heurística y hay que
            #   mirarla con desconfianza. Sin esta separación, un número alto no dice nada.
            json.dump({"%08x" % k: {"api": res[k], "como": comos[k]} for k in sorted(res)},
                      open(SALIDA.replace(".json", "_detalle.json"), "w", encoding="utf-8"),
                      indent=1)
        t_ini = time.time()
        for i, s in enumerate(sorted(sitios), 1):
            t = time.time()
            a, d = resolver(mem, s)
            if a:
                res[s] = a
                comos[s] = d
            else:
                fallos[s] = d
            # ⚠ una línea por sitio, a propósito: así se ve CUÁL tarda. Sin esto, la corrida del
            #   08-nov quedó 26 h colgada sin que se pudiera saber en qué sitio.
            print("  %3d/%d %08x -> %-44s %5.1fs · %s" % (
                i, len(sitios), s, a or "(sin resolver)", time.time() - t, d[:60]), flush=True)
            if i % 25 == 0:
                guardar()
                print("  ── %d/%d · %d resueltos · %.0f s" % (
                    i, len(sitios), len(res), time.time() - t_ini), flush=True)
        guardar()
        print("\n%d resueltos, %d sin resolver → %s" % (len(res), len(fallos), SALIDA))
        from collections import Counter
        print("\ncómo salió cada uno (★ 'pedida por nombre' = confiable, el resto heurística):")
        for c, n in Counter(comos.values()).most_common():
            print("   %-46s x%d" % (c, n))
        print("\nAPIs distintas: %d" % len(set(res.values())))
        for api, n in Counter(res.values()).most_common(15):
            print("   %-46s x%d" % (api, n))
        if fallos:
            print("motivos de los que no salieron:")
            for m, n in Counter(fallos.values()).most_common(5):
                print("   %-70s x%d" % (m[:70], n))
        return 0
    sys.exit(__doc__)


if __name__ == "__main__":
    sys.exit(main())
