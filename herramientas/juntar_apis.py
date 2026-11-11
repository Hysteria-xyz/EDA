r"""juntar_apis -- juntar lo que midió cada método y quedarse con lo que se sostiene.

Hay tres fuentes, y ninguna sola alcanza:

  1. `_trabajo/apis_cruzadas.json`  — EMULANDO la VM, y sólo lo que dio IGUAL en dos volcados de
     dos corridas distintas de ASProtect (`emular_stub.py cruzar`). La más confiable.
  2. `_trabajo/apis_por_bytes.json` — LEYENDO el stub: los que saltan dentro de la API unos bytes
     después del comienzo, y los que se copiaron el cuerpo entero de la función
     (`emular_stub.py bytes`). Resuelve sitios que la emulación no toca.
  3. `NUNCA_SE_IMPORTAN` de `desempacar.py` — lo que ningún compilador pondría en una tabla de
     imports (las tripas de otra API). Eso se descarta siempre.

Reglas, en este orden:
  - si las dos fuentes contestan y dicen LO MISMO  ⇒ entra (doblemente confirmada);
  - si contestan y dicen cosas DISTINTAS           ⇒ ⛔ NO entra. No se elige una a dedo;
  - si contesta una sola                           ⇒ entra, anotando por qué camino salió.

Deja `_trabajo/apis_finales.json`, que es lo que lee `desempacar.py construir`.

    py herramientas\juntar_apis.py
"""
import json
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                            # noqa: BLE001
    pass

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "herramientas"))
from desempacar import NUNCA_SE_IMPORTAN                    # noqa: E402

TRABAJO = os.path.join(RAIZ, "_trabajo")
FUENTES = [("emulada y cruzada", "apis_cruzadas.json"),
           ("leída del stub", "apis_por_bytes.json"),
           # ⚠ la más débil: la emulación la resolvió en UNA corrida y en la otra no pudo. Eso no
           #   es una contradicción (nadie dijo lo contrario), pero no está confirmada: entra sólo
           #   si ninguna de las otras dos contesta ese sitio, y se anota como tal.
           ("una sola corrida", "apis_una_corrida.json")]
SALIDA = os.path.join(TRABAJO, "apis_finales.json")


A_MANO = os.path.join(RAIZ, "documentacion", "APIS_A_MANO.md")

# ★★ LAS ENVOLTURAS (11-nov). La emulación termina muchas veces DENTRO de la implementación y no
#    en la función exportada que el juego importó: `MoveFileExA` llama por dentro a
#    `MoveFileWithProgressA`, `CreateMutexA` a `CreateMutexExA`, `LoadLibraryA` a `LoadLibraryExA`,
#    `FileTimeToSystemTime` a `RtlpTimeToTimeFields`. Si entra la interna, la API limpia de la pila
#    la cantidad de argumentos de LA INTERNA y el exe se muere lejos: así moría en `0x7D4FF8`
#    (`MoveFileWithProgressA` saca 20 bytes donde `MoveFileExA` saca 12 ⇒ 8 bytes de pila
#    destruidos en cada vuelta del bucle).
#    La clave para no inventar: la **cantidad de argumentos medida** (`validar_apis.py`). Se
#    cambia la interna por la envoltura sólo si la medición coincide con la envoltura; y para las
#    internas que ningún programa importa (`*Worker`, `Basep*`) se cambia siempre.
ENVOLTURAS = {
    # (función interna, bytes de argumento medidos): la envoltura que el juego importó
    ("MoveFileWithProgressA", 12): "KERNEL32.dll!MoveFileExA",
    ("CreateMutexExA", 12): "KERNEL32.dll!CreateMutexA",
    ("LoadLibraryExA", 4): "KERNEL32.dll!LoadLibraryA",
    ("RtlpTimeToTimeFields", 8): "KERNEL32.dll!FileTimeToSystemTime",
    ("CreateEventExA", 16): "KERNEL32.dll!CreateEventA",
    ("CreateSemaphoreExA", 16): "KERNEL32.dll!CreateSemaphoreA",
}
# y éstas se cambian aunque no haya medición: son internas que no son export de nada que un
# programa importe, o cuyo nombre lo dice (`Worker`)
SIEMPRE = {"MoveFileWithProgressA": "KERNEL32.dll!MoveFileExA",
           "CreateMutexExA": "KERNEL32.dll!CreateMutexA",
           "GetTimeFormatAWorker": "KERNEL32.dll!GetTimeFormatA",
           "GetDateFormatAWorker": "KERNEL32.dll!GetDateFormatA"}


def medidos(nombre="robados_resueltos.json"):
    """{sitio: bytes de argumento} de lo que midió `robados.py`."""
    r = os.path.join(TRABAJO, nombre)
    if not os.path.exists(r):
        return {}
    return {int(k, 16): v["bytes_de_argumento"]
            for k, v in json.load(open(r, encoding="utf-8")).items()
            if v.get("bytes_de_argumento") is not None}


def nombres_que_pide():
    """Los nombres de import que ASProtect guarda DESCIFRADOS en su memoria (192), cacheados en
    `_trabajo/nombres_pedidos.txt` por `emular_stub.nombres_pedidos`. Es una señal positiva: que
    un nombre esté ahí quiere decir que el juego lo importa."""
    r = os.path.join(TRABAJO, "nombres_pedidos.txt")
    return set(open(r, encoding="utf-8").read().split()) if os.path.exists(r) else set()


PIDE = nombres_que_pide()
EX = __import__("re").compile(r"^(\w+?)Ex([AW]?)$")


def envolver(sitio, api, arg):
    """Cambia la función interna por la que el juego importó de verdad, si corresponde."""
    dll, _, fn = api.partition("!")
    if (fn, arg) in ENVOLTURAS:
        return ENVOLTURAS[(fn, arg)]
    if fn in SIEMPRE:
        return SIEMPRE[fn]
    # ★ la regla que sale de los datos: si la que dijimos es la variante `…Ex` y **no** está en la
    #   lista de nombres que ASProtect guarda, pero la variante SIN `Ex` **sí** está, el juego
    #   importó la de sin `Ex`. No es una corazonada: la lista es la tabla de nombres del propio
    #   juego descifrada.
    #   ⚠ Y no se aplica cuando las dos están en la lista (`LoadLibraryA` y `LoadLibraryExA` lo
    #     están las dos): ahí no se sabe cuál es y decide la cantidad de argumentos.
    #   El caso que lo pidió: 9 sitios decían `GetFileSizeEx`, que no está en la lista, y
    #   `GetFileSize` sí. Las dos llevan 2 argumentos, así que el juez de los argumentos no las
    #   distingue — pero `GetFileSizeEx` **explota** si el 2º argumento es NULL, y el juego le
    #   pasa `push 0` (`0x7D7697`). Con `GetFileSizeEx` el exe se moría dentro de KERNELBASE.
    m = EX.match(fn)
    if m and fn not in PIDE:
        base = m.group(1) + m.group(2)
        if base in PIDE:
            return "%s!%s" % (dll, base)
    return api
FILA = __import__("re").compile(
    r"^\|\s*0x([0-9A-Fa-f]{6,8})\s*\|\s*([A-Za-z0-9_.\-]+![A-Za-z0-9_@]+)\s*\|\s*(\S.*?)\s*\|\s*$")


def a_mano():
    """Las resueltas a mano, de `documentacion/APIS_A_MANO.md`. Pisan a todo lo demás porque
    traen la prueba escrita al lado; una fila sin prueba o mal escrita se avisa y NO entra."""
    if not os.path.exists(A_MANO):
        return {}
    d, malas = {}, 0
    for l in open(A_MANO, encoding="utf-8"):
        if not l.startswith("|") or l.startswith("|---") or l.startswith("| sitio"):
            continue
        m = FILA.match(l.rstrip("\n"))
        if not m or len(m.group(3)) < 40:          # sin prueba de verdad no vale
            malas += 1
            continue
        d[int(m.group(1), 16)] = m.group(2)
    if malas:
        print("  ⚠ %d filas de APIS_A_MANO.md no se entienden o no traen prueba" % malas)
    return d


def cargar(nombre):
    r = os.path.join(TRABAJO, nombre)
    if not os.path.exists(r):
        print("  ⚠ falta %s" % nombre)
        return {}
    return {int(k, 16): v for k, v in json.load(open(r, encoding="utf-8")).items()}


def imposible(api):
    fn = api.split("!", 1)[-1]
    return fn in NUNCA_SE_IMPORTAN or fn.startswith("Basep")


def main():
    datos = []
    for etiqueta, nombre in FUENTES:
        d = cargar(nombre)
        print("  %-20s %d sitios" % (etiqueta, len(d)))
        datos.append((etiqueta, d))
    (e1, d1), (e2, d2), (e3, d3) = datos

    mano = a_mano()
    arg_medido = medidos()
    print("  %-20s %d sitios (con la prueba al lado)" % ("a mano", len(mano)))
    # ★ y lo que el juez de los argumentos reprobó (`validar_apis.py`): sale. Una respuesta cuya
    #   cantidad de argumentos no coincide con el `ret N` de la API deja la pila corrida y el exe
    #   se muere en cualquier parte. Mejor sin respuesta: ahí la trampa dice qué sitio falta.
    reprobados = {}
    rr = os.path.join(TRABAJO, "apis_mal.json")
    if os.path.exists(rr):
        reprobados = {int(k, 16): v for k, v in json.load(open(rr, encoding="utf-8")).items()}
        print("  %-20s %d sitios ⇒ se descartan" % ("reprobados", len(reprobados)))

    final, como = {}, {}
    choques, tirados = [], []
    for s in sorted(set(d1) | set(d2) | set(d3) | set(mano)):
        if s in mano:                 # ★ pisa a todo: es la única fuente que trae su prueba
            final[s], como[s] = mano[s], "a mano"
            continue
        if s in reprobados:
            # ★ el juez de los argumentos la reprobó. Pero antes de tirarla: si era una función
            #   INTERNA y la medición dice qué envoltura es (ver ENVOLTURAS), eso no es una
            #   respuesta mala sino una respuesta a medio camino, y se corrige.
            r = envolver(s, reprobados[s]["api"], arg_medido.get(s))
            if r != reprobados[s]["api"]:
                final[s], como[s] = r, "la reprobada, corregida por la envoltura"
            continue
        a, b = d1.get(s), d2.get(s)
        if not (a or b):
            api = d3[s]
            if imposible(api):
                tirados.append((s, api))
                continue
            final[s], como[s] = api, e3
            continue
        if a and b and a != b:
            choques.append((s, a, b))
            continue
        api = a or b
        if imposible(api):
            tirados.append((s, api))
            continue
        final[s] = api
        como[s] = "las dos" if (a and b) else (e1 if a else e2)

    # ★ y el último paso: cambiar la función INTERNA por la envoltura que el juego importó
    #   de verdad (ver ENVOLTURAS y la regla de los nombres descifrados, arriba).
    cambiadas = 0
    for s in list(final):
        nuevo = envolver(s, final[s], arg_medido.get(s))
        if nuevo != final[s]:
            final[s], como[s] = nuevo, como[s] + " + envoltura"
            cambiadas += 1
    if cambiadas:
        print("  %-20s %d sitios (la interna por la exportada)" % ("envolturas", cambiadas))

    print("\n★ resultado")
    print("   a mano (con prueba escrita): %d" % sum(1 for s in como if como[s] == "a mano"))
    print("   confirmadas por los dos métodos: %d" % sum(1 for s in como if como[s] == "las dos"))
    print("   sólo %-18s %d" % (e1 + ":", sum(1 for s in como if como[s] == e1)))
    print("   sólo %-18s %d" % (e2 + ":", sum(1 for s in como if como[s] == e2)))
    print("   ⚠ sólo %-16s %d" % (e3 + ":", sum(1 for s in como if como[s] == e3)))
    print("   ⛔ descartadas por chocar entre métodos: %d" % len(choques))
    for s, a, b in choques:
        print("        %08x  %-40s  vs  %s" % (s, a, b))
    print("   ⛔ descartadas por imposibles: %d" % len(tirados))
    for s, a in tirados[:6]:
        print("        %08x  %s" % (s, a))
    print("   ⇒ TOTAL que entra al exe: %d" % len(final))

    # ★ el control: las dos fuentes, donde las dos contestan, tienen que coincidir casi siempre.
    #   Si chocaran en la mitad, alguna está midiendo mal y no habría que usar ninguna.
    comunes = len([s for s in set(d1) & set(d2)])
    if comunes:
        ok = comunes - len(choques)
        print("\n   control: %d sitios los contestan las dos · coinciden %d (%.0f %%) → %s"
              % (comunes, ok, 100.0 * ok / comunes,
                 "✅ bien" if ok >= comunes * 0.75 else "⛔ demasiados choques"))
    json.dump({"%08x" % k: final[k] for k in sorted(final)},
              open(SALIDA, "w", encoding="utf-8"), indent=1)
    json.dump({"%08x" % k: {"api": final[k], "fuente": como[k]} for k in sorted(final)},
              open(SALIDA.replace(".json", "_detalle.json"), "w", encoding="utf-8"), indent=1)
    print("\n   -> %s" % SALIDA)
    return 0


if __name__ == "__main__":
    sys.exit(main())
