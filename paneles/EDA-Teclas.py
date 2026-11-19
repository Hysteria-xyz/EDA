r"""EDA-Teclas -- CONTROLES: cambiar las teclas del juego (habilidades, ítems, moverse, mouse, arma…).

★ Medido en el juego (13-nov): EDA es LithTech y sus teclas son las líneas `rangebind` del
  autoexec.cfg (`rangebind "##keyboard" "##59" 0.000000 0.000000 "Skill1"`). Las acciones las
  declara `AddAction` (Skill1..8, GameItem1..6, Revival1..7, MoveForward…, ChangeWeapon, Guard,
  Jump, Skill_Next/Prev, MouseButtonL/R/M, Tab, Enter). Un mismo botón puede llevar varias
  acciones en la misma línea (el «1» = GameItem1 y Revival1). Una tecla se escribe por su código
  DirectInput (`##<n>`), un botón del mouse `"##mouse" "##Button <n>"`.

★ 14-nov: con EDA abierto se aplican AL INSTANTE (el lanzador las manda al juego: «Bind» de su
consola, ver herramientas/eda_original.py TECLAS_JS). El juego reescribe el autoexec.cfg AL SALIR con lo que tenía en memoria, así que lo que vale es
EDA-teclas.json: (18-nov) ya NO se vuelve a poner antes de cada partida: las teclas las maneja Options →
CONTROLES de la d3d9.dll; esto queda para usarlo a mano (`--aplicar`).

    pythonw EDA-Teclas.py            la ventana
    python  EDA-Teclas.py --aplicar  sólo escribir el autoexec.cfg
    python  EDA-Teclas.py --prueba   las pruebas
"""
import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
CFG = RAIZ / "repo" / "_trabajo" / "juego" / "autoexec.cfg"
TECLAS = RAIZ / "EDA-teclas.json"
PID = RAIZ / "repo" / "_trabajo" / "servidor" / "teclas_panel.pid"

# código DirectInput → nombre que se ve
DIK = {1: "Esc", 2: "1", 3: "2", 4: "3", 5: "4", 6: "5", 7: "6", 8: "7", 9: "8", 10: "9", 11: "0",
       12: "-", 13: "=", 14: "Retroceso", 15: "Tab", 16: "Q", 17: "W", 18: "E", 19: "R", 20: "T", 21: "Y",
       22: "U", 23: "I", 24: "O", 25: "P", 26: "[", 27: "]", 28: "Enter", 29: "Ctrl", 30: "A", 31: "S",
       32: "D", 33: "F", 34: "G", 35: "H", 36: "J", 37: "K", 38: "L", 39: "Ñ", 40: "'", 41: "º",
       42: "Shift", 43: "\\", 44: "Z", 45: "X", 46: "C", 47: "V", 48: "B", 49: "N", 50: "M", 51: ",",
       52: ".", 53: "/", 54: "Shift der.", 55: "Num *", 56: "Alt", 57: "Espacio", 58: "Bloq Mayús",
       59: "F1", 60: "F2", 61: "F3", 62: "F4", 63: "F5", 64: "F6", 65: "F7", 66: "F8", 67: "F9",
       68: "F10", 71: "Num 7", 72: "Num 8", 73: "Num 9", 74: "Num -", 75: "Num 4", 76: "Num 5",
       77: "Num 6", 78: "Num +", 79: "Num 1", 80: "Num 2", 81: "Num 3", 82: "Num 0", 83: "Num .",
       86: "<", 87: "F11", 88: "F12", 156: "Num Enter", 157: "Ctrl der.", 181: "Num /", 184: "Alt Gr",
       199: "Inicio", 200: "↑", 201: "RePág", 203: "←", 205: "→", 207: "Fin", 208: "↓", 209: "AvPág",
       210: "Insert", 211: "Supr"}
MOUSE = {0: "Clic izq.", 1: "Clic der.", 2: "Clic medio", 3: "Botón lat. 1", 4: "Botón lat. 2"}

# tkinter (keysym) → código DirectInput
KEYSYM = {"Escape": 1, "minus": 12, "equal": 13, "BackSpace": 14, "Tab": 15, "bracketleft": 26,
          "bracketright": 27, "Return": 28, "Control_L": 29, "semicolon": 39, "ntilde": 39, "Ntilde": 39,
          "apostrophe": 40, "grave": 41, "masculine": 41, "Shift_L": 42, "backslash": 43, "comma": 51,
          "period": 52, "slash": 53, "Shift_R": 54, "KP_Multiply": 55, "Alt_L": 56, "space": 57,
          "Caps_Lock": 58, "KP_Subtract": 74, "KP_Add": 78, "KP_Decimal": 83, "KP_Delete": 83, "less": 86,
          "KP_Enter": 156, "Control_R": 157, "KP_Divide": 181, "Alt_R": 184, "ISO_Level3_Shift": 184,
          "Home": 199, "Up": 200, "Prior": 201, "Left": 203, "Right": 205, "End": 207, "Down": 208,
          "Next": 209, "Insert": 210, "Delete": 211,
          "KP_7": 71, "KP_Home": 71, "KP_8": 72, "KP_Up": 72, "KP_9": 73, "KP_Prior": 73, "KP_4": 75,
          "KP_Left": 75, "KP_5": 76, "KP_Begin": 76, "KP_6": 77, "KP_Right": 77, "KP_1": 79, "KP_End": 79,
          "KP_2": 80, "KP_Down": 80, "KP_3": 81, "KP_Next": 81, "KP_0": 82, "KP_Insert": 82}
for _i, _l in enumerate("QWERTYUIOP"):
    KEYSYM[_l] = 16 + _i
for _i, _l in enumerate("ASDFGHJKL"):
    KEYSYM[_l] = 30 + _i
for _i, _l in enumerate("ZXCVBNM"):
    KEYSYM[_l] = 44 + _i
for _i in range(1, 10):
    KEYSYM[str(_i)] = 1 + _i
KEYSYM["0"] = 11
for _i in range(1, 11):
    KEYSYM["F%d" % _i] = 58 + _i
KEYSYM["F11"], KEYSYM["F12"] = 87, 88

# (acción del juego, lo que se ve, grupo, por defecto [principal, alterna], acciones que van JUNTO)
ACCIONES = [
    ("MoveForward", "Avanzar", "Movimiento", ["K17", "K200"], []),
    ("MoveBackward", "Retroceder", "Movimiento", ["K31", "K208"], []),
    ("MoveLeft", "Izquierda", "Movimiento", ["K30", "K203"], []),
    ("MoveRight", "Derecha", "Movimiento", ["K32", "K205"], []),
    ("Jump", "Saltar", "Movimiento", ["K57", ""], []),
    ("Guard", "Defender / guardia", "Movimiento", ["K42", ""], []),
    ("MouseButtonL", "Atacar", "Combate", ["M0", ""], []),
    ("MouseButtonR", "Lanzar la habilidad elegida", "Combate", ["M1", ""], []),
    ("MouseButtonM", "Botón medio del mouse", "Combate", ["M2", ""], []),
    ("ChangeWeapon", "Cambiar de arma", "Combate", ["K33", ""], []),
    ("Skill_Next", "Habilidad siguiente", "Combate", ["K18", ""], []),
    ("Skill_Prev", "Habilidad anterior", "Combate", ["K16", ""], []),
] + [("Skill%d" % i, "Habilidad %d" % i, "Habilidades", ["K%d" % (58 + i), ""], []) for i in range(1, 9)] + [
    ("GameItem%d" % i, "Ítem %d (HP, MP…)" % i if i <= 2 else "Ítem %d" % i, "Ítems", ["K%d" % (1 + i), ""],
     ["Revival%d" % i]) for i in range(1, 7)] + [
    ("Revival7", "Revivir: opción 7", "Ítems", ["K8", ""], []),
    ("Tab", "Tabla de puntos (Tab)", "Interfaz", ["K15", ""], []),
    ("Enter", "Chat (Enter)", "Interfaz", ["K28", ""], []),
]
FIJAS = [("F9", "Listo / empezar (en la sala, del juego)"), ("F10", "Options"), ("F11", "Messenger"),
         ("F12", "Clan (reservado)")]
DE_EDA = {"EDA_Inventario"}            # no van al autoexec.cfg
GRUPOS = ["Movimiento", "Combate", "Habilidades", "Ítems", "Interfaz", "Atajos"]   # (Atajos: sólo las fijas)


def nombre(cod):
    """'K59' → 'F1', 'M1' → 'Clic der.', 'C23' → 'Ctrl + I', '' → '—'."""
    if not cod:
        return "—"
    n = int(cod[1:])
    if cod[0] == "M":
        return MOUSE.get(n, "Botón %d" % n)
    texto = DIK.get(n, "Tecla %d" % n)
    return "Ctrl + " + texto if cod[0] == "C" else texto


def por_defecto():
    return {a: list(d) for a, _, _, d, _ in ACCIONES}


def leer_teclas():
    t = por_defecto()
    try:
        guardado = json.loads(TECLAS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        guardado = {}
    for a, v in guardado.items():
        if a in t and isinstance(v, list) and len(v) == 2:
            t[a] = [str(x) for x in v]
    return t


def guardar_teclas(t):
    TECLAS.write_text(json.dumps(t, ensure_ascii=False, indent=1), encoding="utf-8")


def quien_usa(t, cod, salvo=None):
    """Las (acción, lugar) que ya usan `cod`."""
    return [(a, i) for a, v in t.items() for i, x in enumerate(v) if x == cod and cod and (a, i) != salvo]


def asignar(t, accion, lugar, cod):
    """Pone `cod` en (accion, lugar) y lo saca de donde estaba. Devuelve las acciones que lo perdieron."""
    quitadas = []
    for a, i in quien_usa(t, cod, (accion, lugar)):
        t[a][i] = ""
        quitadas.append(a)
    t[accion][lugar] = cod
    return quitadas


def aplicar(texto, t):
    """El autoexec.cfg (texto) con las teclas `t` en sus `rangebind` (lo demás, igual)."""
    nl = "\r\n" if "\r\n" in texto else "\n"
    juntas = {a: [a] + extra for a, _, _, _, extra in ACCIONES}
    teclado, mouse = {}, {}
    for a, _, _, _, _ in ACCIONES:
        if a in DE_EDA:
            continue
        for cod in t.get(a, []):
            if not cod:
                continue
            destino = mouse if cod[0] == "M" else teclado
            destino.setdefault(int(cod[1:]), []).extend(juntas[a])
    lineas = [l for l in texto.split(nl)
              if not re.match(r'rangebind "##keyboard"', l) and not re.match(r'rangebind "##mouse" "##Button', l)]

    def renglon(dispositivo, objeto, acciones):
        return 'rangebind "%s" "%s" %s ' % (dispositivo, objeto, " ".join(
            '0.000000 0.000000 "%s"' % x for x in acciones))
    nuevas_t = [renglon("##keyboard", "##%d" % k, v) for k, v in sorted(teclado.items())]
    nuevas_m = [renglon("##mouse", "##Button %d" % k, v) for k, v in sorted(mouse.items())]
    i_t = next((i for i, l in enumerate(lineas) if l.strip() == 'enabledevice "##keyboard"'), None)
    if i_t is None:
        lineas.append('enabledevice "##keyboard"')
        i_t = len(lineas) - 1
    lineas[i_t + 1:i_t + 1] = nuevas_t
    i_m = max((i for i, l in enumerate(lineas) if l.strip() == 'enabledevice "##mouse"'), default=None)
    if i_m is None:
        lineas.append('enabledevice "##mouse"')
        i_m = len(lineas) - 1
    lineas[i_m + 1:i_m + 1] = nuevas_m
    return nl.join(lineas)


def aplicar_al_juego(t=None):
    if not CFG.is_file():
        return False
    texto = CFG.read_bytes().decode("latin-1")
    nuevo = aplicar(texto, t or leer_teclas())
    if nuevo != texto:
        temporal = CFG.with_suffix(".cfg.tmp")
        temporal.write_bytes(nuevo.encode("latin-1"))
        temporal.replace(CFG)
    return True


# ── la ventana ─────────────────────────────────────────────────────────────────────────────────
def ventana():
    import tkinter as tk
    import eda_ui as ui

    v = ui.Ventana("Controles", 600, 560)
    ui.una_instancia(str(PID))
    e = v.e
    t = leer_teclas()
    estado = {"grupo": "Movimiento", "esperando": None}

    barra = tk.Frame(v.cuerpo, bg=ui.FONDO)
    barra.pack(fill="x", padx=e(8), pady=(e(6), 0))
    pestanas = {}

    def elegir(g):
        estado["grupo"] = g
        estado["esperando"] = None
        for nom, p in pestanas.items():
            p.elegir(nom == g)
        dibujar()
    for g in GRUPOS:
        pestanas[g] = ui.Pestana(barra, g, lambda g=g: elegir(g), ancho=93, escala=v.escala)
        pestanas[g].pack(side="left", padx=(0, 1))

    marco, lista = ui.panel(v.cuerpo)
    marco.pack(fill="both", expand=True, padx=e(8))
    ui.cabecera(lista, [("Acción", 3), ("Principal", 2), ("Alterna", 2)]).pack(fill="x")
    filas = tk.Frame(lista, bg=ui.PANEL)
    filas.pack(fill="both", expand=True, padx=e(4), pady=e(4))

    linea = tk.Label(v.cuerpo, text="", bg=ui.FONDO, fg=ui.GRIS, font=ui.CHICA, anchor="w")
    nota = tk.Label(v.cuerpo, text="Clic en una tecla y pulsa la nueva (o un botón del mouse). "
                    "Clic derecho = borrar. Esc = cancelar.", bg=ui.FONDO, fg=ui.GRIS, font=ui.CHICA,
                    anchor="w")

    def aviso(texto, color=ui.GRIS):
        linea.configure(text=" " + texto, fg=color)

    def boton_tecla(padre, accion, lugar):
        cod = t[accion][lugar]
        espera = estado["esperando"] == (accion, lugar)
        w, h = e(118), e(24)
        cv = tk.Canvas(padre, width=w, height=h, bg=ui.PANEL, highlightthickness=0, cursor="hand2")
        ui.degrade(cv, 1, 1, w - 1, h - 1, "#3a0d0d" if espera else "#1e2024", "#060708")
        cv.create_rectangle(0, 0, w - 1, h - 1, outline=ui.ROJO_LUZ if espera else ui.ACERO_CLARO)
        cv.create_text(w // 2, h // 2, text="Pulsa…" if espera else nombre(cod),
                       fill=ui.ROJO_LUZ if espera else (ui.CIAN_BRILLO if cod else ui.GRIS), font=ui.FUENTE_B)
        cv.bind("<Button-1>", lambda ev: esperar(accion, lugar) if not espera else tomar_mouse(0))
        cv.bind("<Button-3>", lambda ev: borrar(accion, lugar) if not espera else tomar_mouse(1))
        cv.bind("<Button-2>", lambda ev: espera and tomar_mouse(2))
        return cv

    def dibujar():
        for w in filas.winfo_children():
            w.destroy()
        g = estado["grupo"]
        for accion, etiqueta, grupo, _, _ in ACCIONES:
            if grupo != g:
                continue
            f = tk.Frame(filas, bg="#101215", highlightthickness=1, highlightbackground="#5c6168")
            f.pack(fill="x", pady=e(2))
            tk.Label(f, text=etiqueta, bg="#101215", fg=ui.TEXTO, font=ui.FUENTE, anchor="w").pack(
                side="left", fill="x", expand=True, padx=e(8), pady=e(3))
            boton_tecla(f, accion, 1).pack(side="right", padx=(e(4), e(6)), pady=e(3))
            boton_tecla(f, accion, 0).pack(side="right", padx=e(4), pady=e(3))
        if g == "Atajos":
            tk.Label(filas, text="FIJAS", bg=ui.PANEL, fg=ui.CIAN, font=ui.CHICA, anchor="w").pack(
                fill="x", pady=(e(8), e(2)))
            for tecla, que in FIJAS:
                f = tk.Frame(filas, bg="#0b0c0e", highlightthickness=1, highlightbackground="#2c2f34")
                f.pack(fill="x", pady=e(1))
                tk.Label(f, text=que, bg="#0b0c0e", fg=ui.GRIS, font=ui.FUENTE, anchor="w").pack(
                    side="left", fill="x", expand=True, padx=e(8), pady=e(3))
                tk.Label(f, text=tecla, bg="#0b0c0e", fg=ui.ORO, font=ui.FUENTE_B, width=10).pack(
                    side="right", padx=e(6))
        if g == "Ítems":
            tk.Label(filas, text="El número de cada ítem también elige la opción al revivir.",
                     bg=ui.PANEL, fg=ui.GRIS, font=ui.CHICA, anchor="w").pack(fill="x", pady=(e(6), 0))

    def esperar(accion, lugar):
        estado["esperando"] = (accion, lugar)
        v.tk.focus_force()
        aviso("Pulsa la tecla nueva para «%s»…" % dict((a, x) for a, x, *_ in ACCIONES)[accion], ui.ROJO_LUZ)
        dibujar()

    def poner(cod):
        accion, lugar = estado["esperando"]
        estado["esperando"] = None
        if accion in DE_EDA and cod[0] == "M":
            aviso("Ese atajo va con teclado.", ui.ORO)
            dibujar()
            return
        if cod in ("K67", "K68", "K87", "K88") and accion not in DE_EDA:
            aviso("F9–F12 están reservadas (listo, Options, Messenger, Clan).", ui.ORO)
            dibujar()
            return
        quitadas = asignar(t, accion, lugar, cod)
        etiquetas = dict((a, x) for a, x, *_ in ACCIONES)
        aviso("%s → %s%s" % (etiquetas[accion], nombre(cod), (" (se quitó de: %s)" % ", ".join(
            etiquetas[q] for q in quitadas)) if quitadas else ""), ui.VERDE)
        dibujar()

    def tomar_mouse(n):
        if estado["esperando"]:
            poner("M%d" % n)

    def tecla(ev):
        if not estado["esperando"]:
            return
        if ev.keysym == "Escape":
            estado["esperando"] = None
            aviso("Cancelado.")
            dibujar()
            return
        cod = KEYSYM.get(ev.keysym) or KEYSYM.get(ev.keysym.upper())
        if cod is None:
            aviso("Esa tecla no se puede usar (%s)." % ev.keysym, ui.ORO)
            return
        accion = estado["esperando"][0]
        ctrl = bool(ev.state & 0x4) and cod not in (29, 157)
        poner(("C%d" if accion in DE_EDA and ctrl else "K%d") % cod)
    v.tk.bind("<KeyPress>", tecla)

    def borrar(accion, lugar):
        t[accion][lugar] = ""
        aviso("Borrada.")
        dibujar()

    def defecto():
        t.clear()
        t.update(por_defecto())
        aviso("Teclas de fábrica (falta GUARDAR).", ui.ORO)
        dibujar()

    def guardar():
        guardar_teclas(t)
        ok = aplicar_al_juego(t)
        aviso("Guardado: el juego ya usa las teclas nuevas (al instante).%s" % (
            "" if ok else " (no se encontró el autoexec.cfg del juego)"), ui.VERDE)

    abajo = tk.Frame(v.cuerpo, bg=ui.FONDO)
    abajo.pack(side="bottom", fill="x", padx=e(8), pady=e(8))
    ui.Boton(abajo, "CERRAR", v.cerrar, "granate", 100, 26, v.escala).pack(side="right")
    ui.Boton(abajo, "GUARDAR", guardar, "teal", 110, 26, v.escala).pack(side="right", padx=e(6))
    ui.Boton(abajo, "POR DEFECTO", defecto, "morado", 120, 26, v.escala).pack(side="left")
    linea.pack(side="bottom", fill="x", padx=e(8))
    nota.pack(side="bottom", fill="x", padx=e(8))
    elegir("Movimiento")
    v.centrar_en_juego()
    v.tk.focus_force()
    v.tk.mainloop()


def prueba():
    ok = []

    def chequear(n, c, d=""):
        ok.append(bool(c))
        print(("  ✅ " if c else "  ⛔ ") + n + ("" if c else "  " + str(d)))
    base = ('enabledevice "##keyboard"\r\nrangebind "##keyboard" "D" 0.000000 0.000000 "MoveRight" \r\n'
            'rangebind "##keyboard" "F1" 0.000000 0.000000 "Skill1" \r\nenabledevice "##mouse"\r\n'
            'rangebind "##mouse" "##Button 0" 0.000000 0.000000 "MouseButtonL" \r\n'
            'rangebind "##mouse" "##x-axis" 0.000000 0.000000 "Axis1" \r\nscale "##mouse" "##x-axis" 0.006\r\n')
    t = por_defecto()
    s = aplicar(base, t)
    chequear("de fábrica: F1 (##59) = Skill1", 'rangebind "##keyboard" "##59" 0.000000 0.000000 "Skill1" ' in s)
    chequear("el 1 lleva el ítem y el revivir en la misma línea",
             '"##2" 0.000000 0.000000 "GameItem1" 0.000000 0.000000 "Revival1"' in s)
    chequear("las flechas siguen siendo la alterna", '"##200" 0.000000 0.000000 "MoveForward"' in s)
    chequear("los ejes del mouse quedan", '"##x-axis"' in s and 'scale "##mouse" "##x-axis" 0.006' in s)
    chequear("las viejas por nombre («D», «F1») se van", '"D" 0.0' not in s and '"F1" 0.0' not in s)
    chequear("CRLF se conserva", "\r\n" in s and "\n" not in s.replace("\r\n", ""))
    quitadas = asignar(t, "Skill1", 0, "K44")
    s = aplicar(base, t)
    chequear("Habilidad 1 → Z (##44)", '"##44" 0.000000 0.000000 "Skill1"' in s and '"##59"' not in s)
    quitadas = asignar(t, "Jump", 0, "K44")
    chequear("★ el revés: Z a Saltar se la saca a Habilidad 1", quitadas == ["Skill1"] and t["Skill1"][0] == "")
    asignar(t, "Guard", 0, "M1")
    asignar(t, "MouseButtonR", 0, "M3")
    s = aplicar(base, t)
    chequear("Defender con el clic derecho, la habilidad con el botón lateral",
             '"##Button 1" 0.000000 0.000000 "Guard"' in s and '"##Button 3" 0.000000 0.000000 "MouseButtonR"' in s)
    chequear("aplicar dos veces da lo mismo", aplicar(s, t) == s)
    chequear("nombres", nombre("K59") == "F1" and nombre("M1") == "Clic der." and nombre("C23") == "Ctrl + I"
             and nombre("") == "—")
    print("\n→ TODO BIEN" if all(ok) else "\n→ ⛔ ALGO FALLA")
    return 0 if all(ok) else 1


if __name__ == "__main__":
    if "--prueba" in sys.argv:
        sys.exit(prueba())
    if "--aplicar" in sys.argv:
        sys.exit(0 if aplicar_al_juego() else 1)
    sys.path.insert(0, str(RAIZ))
    try:
        ventana()
    except Exception:                                         # noqa: BLE001  (pythonw no muestra errores)
        import traceback
        (RAIZ / "repo" / "_trabajo" / "servidor" / "teclas_panel.log").write_text(traceback.format_exc(),
                                                                                   encoding="utf-8")
        raise
