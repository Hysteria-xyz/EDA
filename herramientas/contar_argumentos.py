r"""contar_argumentos -- ★ EL CONTROL de `emular_stub.py`: ¿la API que dice cada sitio puede ser?

Por qué hace falta: la emulación contesta un nombre para cada `call` que ASProtect desvió, pero
nada garantiza que sea el bueno — podría estar quedándose con una llamada que la VM hace para su
propio trabajo. Mirar tres sitios a dedo no alcanza (y me hizo sacar una conclusión equivocada el
09-nov, por desensamblar desalineado). Así que se controlan LOS 310, con dos cuentas
independientes que tienen que dar lo mismo:

  A) **lo que el juego empuja**: los `push` que hay justo antes del `call`.
  B) **lo que la API saca**: su `ret N`. En stdcall la limpia el llamado, así que N/4 = cuántos
     argumentos pide. ⚠ No se escribe a mano: se LEE del código de la DLL en el volcado, que es
     el generador del dato (regla de LEEME.md).

Si A ≠ B, ese sitio está mal resuelto. Si no se puede determinar alguna de las dos, se dice.

    py herramientas\contar_argumentos.py            # controla _trabajo/apis_emuladas.json
    py herramientas\contar_argumentos.py --control  # ★ el control AL REVÉS del propio control

El control al revés: se le da a propósito una respuesta falsa para todos los sitios (que todos son
`GetCurrentProcess`, que no lleva argumentos). Si el método sirve, eso tiene que dar un choque
masivo. Si diera "todo bien", la cuenta no estaría midiendo nada.
"""
import argparse
import json
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                            # noqa: BLE001
    pass

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "herramientas"))

from capstone import CS_ARCH_X86, CS_MODE_32, Cs             # noqa: E402
import emular_stub as E                                      # noqa: E402

SALIDA = os.path.join(RAIZ, "_trabajo", "apis_emuladas.json")
md = Cs(CS_ARCH_X86, CS_MODE_32)

# Pasan de largo cuando se camina para atrás buscando los `push`: no tocan la pila.
INOCUAS = ("lea", "mov", "movzx", "movsx", "xor", "test", "cmp", "and", "or", "inc", "dec",
           "nop", "sete", "setne", "neg", "not", "shl", "shr", "sar", "cdq", "sbb", "adc",
           "imul", "mul", "div", "idiv", "fld", "fstp", "fild", "cvttsd2si")


def instrucciones(mem, va, atras=0x60):
    """Las instrucciones que terminan EXACTAMENTE en `va`.
    ⚠ El desensamblado lineal se desincroniza: hay que probar varios arranques y quedarse con el
      que cae justo en el sitio. Sin esto se leen instrucciones que no existen (medido el 09-nov:
      me hizo creer que 0x40AF2F empujaba 1 argumento cuando empuja 4)."""
    mejor = None
    for d in range(0x10, atras):
        datos = mem.leer(va - d, d + 8)
        if not datos:
            continue
        ins = [i for i in md.disasm(datos, va - d)]
        if any(i.address == va for i in ins) and (mejor is None or len(ins) > len(mejor)):
            mejor = ins
    return [i for i in (mejor or []) if i.address < va]


def empuja(mem, sitio):
    """Cuántos argumentos empuja el juego antes del `call`, o None si no se puede decir."""
    ins = instrucciones(mem, sitio)
    if not ins:
        return None
    n = 0
    for i in reversed(ins):
        m = i.mnemonic
        if m == "push":
            n += 1
        elif m in INOCUAS or m.startswith("j"):
            # los `j` se dejan pasar: lo empujado antes de un salto condicional también llega
            # al `call` (medido en 0x40AF2F, donde hay un `jne` en el medio de los 4 push)
            continue
        else:
            break                       # call, add esp, ret, pop, leave… ahí termina la tanda
    return n


def saca(mem, api, limite=400):
    """Cuántos argumentos saca la API de la pila (su `ret N` / 4), o None si no se puede leer.
    Se sigue un `jmp dword ptr [..]` porque medio KERNEL32 reenvía a KERNELBASE."""
    dll, fn = api.split("!", 1)

    def donde(dll, fn):
        for m in mem.mods:
            if m["nombre"].lower() == dll.lower():
                for rva, nombre in m["exp"].items():
                    if nombre == fn:
                        return m["base"] + rva
        return None
    va = donde(dll, fn)
    if va is None:
        return None
    for salto in range(4):
        # ⚠ un export REENVIADO no apunta a código sino al texto "OTRADLL.OtraFuncion"
        cab = mem.leer(va, 80) or b""
        txt = cab.split(b"\0")[0]
        if b"." in txt and 4 < len(txt) < 72 and all(32 <= c < 127 for c in txt):
            d2, _, f2 = txt.decode("latin1").partition(".")
            va = donde(d2 + ".dll", f2) or donde(d2, f2)
            if va is None:
                return None
            continue
        datos = mem.leer(va, limite)
        if not datos:
            return None
        for i in md.disasm(datos, va):
            if i.mnemonic == "ret":
                return (int(i.op_str, 0) // 4) if i.op_str else 0
            if i.mnemonic == "jmp":
                if i.op_str.startswith("dword ptr ["):
                    try:
                        p = int(i.op_str[11:-1], 16)
                    except ValueError:
                        return None
                    va = mem.u32(p) or 0
                elif i.op_str.startswith("0x"):
                    va = int(i.op_str, 16)
                else:
                    return None
                break
        else:
            return None
        if not va:
            return None
    return None


def controlar(mem, respuestas):
    bien, mal, sin_a, sin_b = [], [], [], []
    for s, api in sorted(respuestas.items()):
        a, b = empuja(mem, s), saca(mem, api)
        if a is None:
            sin_a.append((s, api))
        elif b is None:
            sin_b.append((s, api))
        elif a == b:
            bien.append((s, api, a))
        else:
            mal.append((s, api, a, b))
    return bien, mal, sin_a, sin_b


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--control", action="store_true",
                    help="el control al revés: dar una respuesta falsa a propósito")
    ap.add_argument("--json", default=SALIDA)
    a = ap.parse_args()
    mem = E.Memoria()
    res = {int(k, 16): v for k, v in json.load(open(a.json, encoding="utf-8")).items()}
    print("sitios resueltos a controlar: %d" % len(res))

    bien, mal, sin_a, sin_b = controlar(mem, res)
    decididos = len(bien) + len(mal)
    print("\n★ cuántos argumentos empuja el juego vs. cuántos saca la API:")
    print("   se pudo comparar: %d de %d" % (decididos, len(res)))
    if decididos:
        print("   ✅ coinciden: %d  (%.0f %%)" % (len(bien), 100.0 * len(bien) / decididos))
        print("   ⛔ CHOCAN:    %d  (%.0f %%)" % (len(mal), 100.0 * len(mal) / decididos))
    print("   no se pudo contar lo que empuja: %d · no se pudo leer el `ret N`: %d"
          % (len(sin_a), len(sin_b)))
    if mal:
        print("\nlos que chocan (sitio · lo que dice la emulación · empuja → saca):")
        for s, api, x, y in mal[:30]:
            print("   %08x  %-44s %d → %d" % (s, api, x, y))
    if a.control:
        falso = {s: "KERNEL32.dll!GetCurrentProcess" for s in res}
        b2, m2, _, _ = controlar(mem, falso)
        d2 = len(b2) + len(m2)
        print("\n★ control al revés (decir que TODOS son GetCurrentProcess, que lleva 0):")
        print("   coinciden %d de %d → %s" % (
            len(b2), d2,
            "✅ BIEN: la respuesta falsa choca" if d2 and len(b2) < d2 * 0.25
            else "⛔ MAL: la cuenta no está midiendo nada"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
