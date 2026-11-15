/* eda_opciones.c — ★ LAS OPTIONS DE EDA, ADENTRO DE LA DLL (15-nov). Se compila con eda_d3d9.c (#include).
 *
 *  Es paneles/EDA-Opciones.py (con el «look» de paneles/eda_ui.py) pasado a la dll, para que el botón Options
 *  ande IGUAL en local y en multijugador sin Python: la ventana la abre la dll en la PC del jugador.
 *  Lo mismo que el panel de Python:
 *   · marco de acero con bisel y remaches, placa «O P T I O N S» con la luz roja, la ✕ de metal;
 *   · el MENÚ de metal a la izquierda (VIDEO · SONIDO · MOUSE · GRÁFICOS · CONTROLES; el elegido granate)
 *     con GUARDAR (teal) y CERRAR (granate) abajo, y la línea de estado en verde;
 *   · a la derecha el panel negro: títulos en cian con la línea roja, selectores (Ventana / Pantalla
 *     completa, Monitor), deslizadores de acero con relleno rojo y el valor en cian, casillas con LED rojo;
 *   · las mismas opciones, los mismos valores por defecto y la misma forma de escribirlas en autoexec.cfg.
 *  Lo que cambia es DÓNDE se guardan y CÓMO se aplican (no hay Python ni Frida en la PC de un jugador):
 *   · GUARDAR → [opciones] de eda_d3d9.ini (del jugador: el launcher no lo pisa) y, si existe al lado del
 *     repo (la PC de desarrollo), también EDA-opciones.json, así el panel de Python sigue viendo lo mismo;
 *   · al instante, por la CONSOLA del juego en su hilo ([0x92CF50]+0x200 = RunConsoleString, la que usaba
 *     TECLAS_JS de herramientas/eda_original.py): sonido, mouse y gráficos;
 *   · al abrir el juego (DllMain, antes de que el juego lea autoexec.cfg): todo lo de [opciones] al
 *     autoexec.cfg, como `EDA-Opciones.py --aplicar` (el juego lo reescribe al salir con lo que tiene en
 *     memoria); pantalla completa y monitor valen desde ahí («al reabrir EDA», como en el panel de Python);
 *   · el monitor: con la ventana del juego ya creada, se la centra en el monitor elegido (`--ubicar`).
 *  GDI se pide en tiempo de ejecución (LoadLibrary): la receta de compilación no cambia (sin -lgdi32). */

static char g_ini[MAX_PATH];                     /* eda_d3d9.ini (lo llena leer_ajustes) */

/* ── la cola de comandos de consola (se corre en el hilo del juego, desde PeekMessageA) ── */
#define OPC_LINEAS 32
static CRITICAL_SECTION g_opc_cs;
static int g_opc_cs_lista;
static char g_opc_cola[OPC_LINEAS][96];
static int g_opc_n;

static void opc_encolar(const char *linea)
{
    if (!g_opc_cs_lista) return;
    EnterCriticalSection(&g_opc_cs);
    if (g_opc_n < OPC_LINEAS) lstrcpynA(g_opc_cola[g_opc_n++], linea, 96);
    LeaveCriticalSection(&g_opc_cs);
}

typedef void (__cdecl *J_CONSOLA)(char *);
static J_CONSOLA consola_del_juego(void)
{
    BYTE *o = leer_ptr((void *)0x92CF50);
    BYTE *f = o ? leer_ptr(o + 0x200) : NULL;
    return f && legible(f, 1) ? (J_CONSOLA)f : NULL;
}

/* ★ (15-nov) EL VOLUMEN EN VIVO: la consola sólo cambia la variable; el juego la lleva al sonido UNA vez, al
 *   arrancar (0x40377E: GetConsoleVar «MusicVolume» → su valor → 0x5C2050() el sonido → 0x5C0080(v) música /
 *   0x5C0020(v) efectos). Se llaman esas mismas dos funciones, en el hilo del juego. */
typedef void *(__cdecl *J_SONIDO)(void);
typedef void (__attribute__((thiscall)) *J_VOLUMEN)(void *, float);
static volatile LONG g_vol_musica = -1, g_vol_efectos = -1;   /* 0..100 pendientes; -1 = nada */
static int volumen_ok(void)
{
    static int ok = -1;
    if (ok < 0)
        ok = firma(0x5C2050, "64 a1 00 00 00 00 8a 0d b8 6d 93 00") && firma(0x5C0080, "d9 44 24 04 57 8b f9")
             && firma(0x5C0020, "d9 44 24 04 56 8b f1");
    return ok;
}
static void opc_volumen(void)
{
    LONG m = InterlockedExchange(&g_vol_musica, -1), e = InterlockedExchange(&g_vol_efectos, -1);
    if ((m < 0 && e < 0) || !volumen_ok()) return;
    void *snd = JUEGO(J_SONIDO, 0x5C2050)();
    if (!snd) return;
    if (m >= 0) JUEGO(J_VOLUMEN, 0x5C0080)(snd, m / 100.0f);
    if (e >= 0) JUEGO(J_VOLUMEN, 0x5C0020)(snd, e / 100.0f);
    apuntar("  [mazino] opciones: volumen al sonido del juego (música %ld · efectos %ld)", m, e);
}

/* ★ los valores QUE USA EL JUEGO (para que el panel muestre lo real): GetConsoleVar = [0x92CF50]+0xFC (cdecl,
 *   el nombre) y su valor = la función 0x5C de la vtable (thiscall), como en 0x403784. Sólo en el hilo del juego. */
typedef void *(__cdecl *J_VARIABLE)(const char *);
typedef float (__attribute__((thiscall)) *J_VALOR)(void *, void *);
static int variable_del_juego(const char *nombre, float *valor)
{
    BYTE *o = leer_ptr((void *)0x92CF50);
    BYTE *f = o ? leer_ptr(o + 0xFC) : NULL, *vt = o ? leer_ptr(o) : NULL;
    BYTE *g = vt ? leer_ptr(vt + 0x5C) : NULL;
    if (!f || !g || !legible(f, 1) || !legible(g, 1)) return 0;
    void *h = ((J_VARIABLE)f)(nombre);
    if (!h) return 0;
    *valor = ((J_VALOR)g)(o, h);
    return 1;
}

static void opc_correr_cola(void);
static void opc_correr_cola_desde_dibujo(void)
{
    if (g_opc_cs_lista && (g_opc_n || g_vol_musica >= 0 || g_vol_efectos >= 0)) opc_correr_cola();
}
static void opc_correr_cola(void)
{
    char lista[OPC_LINEAS][96];
    int n;
    EnterCriticalSection(&g_opc_cs);
    n = g_opc_n;
    memcpy(lista, g_opc_cola, sizeof(lista));
    g_opc_n = 0;
    LeaveCriticalSection(&g_opc_cs);
    if (n <= 0) { opc_volumen(); return; }
    J_CONSOLA run = consola_del_juego();
    if (!run) { apuntar("  [mazino] opciones: ⚠ no encontré la consola del juego (0x92CF50): quedan para el reinicio"); return; }
    for (int i = 0; i < n; i++) run(lista[i]);
    apuntar("  [mazino] opciones: %d en vivo (%s%s)", n, lista[0], n > 1 ? " …" : "");
    opc_volumen();
}

/* ── las opciones (las de EDA-Opciones.py, POR_DEFECTO) ── */
typedef struct {
    int completa, monitor, musica, efectos, sens, sombras, detalle, reflejos, niebla, brillo, gamma;
} OPC;
#define OPC_N 11
static const OPC OPC_DEFECTO = {0, 1, 100, 50, 6, 0, 0, 0, 1, 0, 100};
static const char *const OPC_CLAVES[OPC_N] = {"pantalla_completa", "monitor", "musica", "efectos", "sensibilidad",
                                              "sombras", "texturas_detalle", "reflejos", "niebla", "brillo",
                                              "brillo_pantalla"};
static int *opc_campo(OPC *o, int i)
{
    int *c[OPC_N] = {&o->completa, &o->monitor, &o->musica, &o->efectos, &o->sens, &o->sombras, &o->detalle,
                     &o->reflejos, &o->niebla, &o->brillo, &o->gamma};
    return c[i];
}
static void opc_limitar(OPC *o)
{
    if (o->musica < 0) o->musica = 0;
    if (o->musica > 100) o->musica = 100;
    if (o->efectos < 0) o->efectos = 0;
    if (o->efectos > 100) o->efectos = 100;
    if (o->sens < 1) o->sens = 1;
    if (o->sens > 30) o->sens = 30;
    if (o->monitor < 1) o->monitor = 1;
    if (o->gamma < 50) o->gamma = 50;
    if (o->gamma > 150) o->gamma = 150;
}

/* rutas al lado del exe (la carpeta del juego) y EDA-opciones.json (sólo en la PC de desarrollo:
 *   repo\_trabajo\juego\ → tres carpetas arriba) */
static int ruta_juego(WCHAR *r, const WCHAR *nombre)
{
    DWORD n = GetModuleFileNameW(NULL, r, MAX_PATH);
    while (n && r[n - 1] != L'\\') n--;
    if (!n || n + lstrlenW(nombre) + 1 >= MAX_PATH) return 0;
    lstrcpyW(r + n, nombre);
    return 1;
}
static int ruta_json(WCHAR *r)
{
    WCHAR t[MAX_PATH];
    if (!ruta_juego(t, L"..\\..\\..\\EDA-opciones.json")) return 0;
    if (!GetFullPathNameW(t, MAX_PATH, r, NULL)) return 0;
    return GetFileAttributesW(r) != INVALID_FILE_ATTRIBUTES;
}

static char *leer_archivo(const WCHAR *ruta, DWORD *largo)
{
    HANDLE f = CreateFileW(ruta, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE, NULL, OPEN_EXISTING, 0, NULL);
    if (f == INVALID_HANDLE_VALUE) return NULL;
    DWORD t = GetFileSize(f, NULL), leidos = 0;
    char *b = (t != INVALID_FILE_SIZE && t < (4u << 20)) ? (char *)HeapAlloc(GetProcessHeap(), 0, t + 1) : NULL;
    if (b && !ReadFile(f, b, t, &leidos, NULL)) leidos = 0;
    CloseHandle(f);
    if (!b) return NULL;
    b[leidos] = 0;
    if (largo) *largo = leidos;
    return b;
}
static int escribir_archivo(const WCHAR *ruta, const char *b, DWORD largo)
{
    WCHAR tmp[MAX_PATH];
    if (lstrlenW(ruta) + 5 >= MAX_PATH) return 0;
    lstrcpyW(tmp, ruta);
    lstrcatW(tmp, L".tmp");
    HANDLE f = CreateFileW(tmp, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, 0, NULL);
    if (f == INVALID_HANDLE_VALUE) return 0;
    DWORD hechos = 0;
    BOOL ok = WriteFile(f, b, largo, &hechos, NULL) && hechos == largo;
    CloseHandle(f);
    if (!ok) { DeleteFileW(tmp); return 0; }
    return MoveFileExW(tmp, ruta, MOVEFILE_REPLACE_EXISTING) != 0;
}

/* "clave": valor de un json chico (true / false / número) */
static int json_valor(const char *j, const char *clave, int *v)
{
    char busca[48];
    wsprintfA(busca, "\"%s\"", clave);
    const char *p = strstr(j, busca);
    if (!p) return 0;
    p += lstrlenA(busca);
    while (*p == ' ' || *p == ':' || *p == '\t') p++;
    if (!strncmp(p, "true", 4)) *v = 1;
    else if (!strncmp(p, "false", 5)) *v = 0;
    else if ((*p >= '0' && *p <= '9') || *p == '-') *v = (int)(atof(p) + (atof(p) < 0 ? -0.5 : 0.5));
    else return 0;
    return 1;
}

/* un número del autoexec.cfg: la línea que empieza con `prefijo` */
static double cfg_num(const char *cfg, const char *prefijo, double defecto)
{
    int largo = lstrlenA(prefijo);
    for (const char *p = cfg; p && *p; ) {
        if (!strncmp(p, prefijo, largo)) {
            p += largo;
            while (*p == ' ' || *p == '"') p++;
            return atof(p);
        }
        while (*p && *p != '\n') p++;
        if (*p) p++;
    }
    return defecto;
}

/* lo guardado: [opciones] del ini; si no hay, EDA-opciones.json (PC de desarrollo); si no, lo que dice
 *   el autoexec.cfg del juego; y lo que falte, POR_DEFECTO. Devuelve de dónde salió (para el registro). */
static int mas_nuevo(const WCHAR *a, const char *b)       /* ¿el archivo a es más nuevo que b? */
{
    WIN32_FILE_ATTRIBUTE_DATA x, y;
    if (!GetFileAttributesExW(a, GetFileExInfoStandard, &x)) return 0;
    if (!GetFileAttributesExA(b, GetFileExInfoStandard, &y)) return 1;
    return CompareFileTime(&x.ftLastWriteTime, &y.ftLastWriteTime) > 0;
}
static const char *opc_leer(OPC *o)
{
    WCHAR rj[MAX_PATH];
    *o = OPC_DEFECTO;
    /* (en la PC de desarrollo el panel de Python guarda EDA-opciones.json: si es más nuevo, manda ése) */
    int json = ruta_json(rj), json_nuevo = json && g_ini[0] && mas_nuevo(rj, g_ini);
    if (g_ini[0] && GetPrivateProfileIntA("opciones", "guardado", 0, g_ini) && !json_nuevo) {
        for (int i = 0; i < OPC_N; i++) *opc_campo(o, i) = GetPrivateProfileIntA("opciones", OPC_CLAVES[i], *opc_campo(o, i), g_ini);
        opc_limitar(o);
        return "eda_d3d9.ini";
    }
    WCHAR r[MAX_PATH];
    if (ruta_json(r)) {
        char *j = leer_archivo(r, NULL);
        if (j) {
            for (int i = 0; i < OPC_N; i++) json_valor(j, OPC_CLAVES[i], opc_campo(o, i));
            HeapFree(GetProcessHeap(), 0, j);
            opc_limitar(o);
            return "EDA-opciones.json";
        }
    }
    if (ruta_juego(r, L"autoexec.cfg")) {
        char *c = leer_archivo(r, NULL);
        if (c) {
            o->completa = cfg_num(c, "\"windowed\"", 1) < 0.5;
            o->musica = (int)(cfg_num(c, "\"MusicVolume\"", 1.0) * 100 + 0.5);
            o->efectos = (int)(cfg_num(c, "\"SoundVolume\"", 0.5) * 100 + 0.5);
            o->sens = (int)(cfg_num(c, "scale \"##mouse\" \"##x-axis\"", 0.006) * 1000 + 0.5);
            o->sombras = cfg_num(c, "\"ModelShadow_Proj_Enable\"", 0) > 0.5;
            o->detalle = cfg_num(c, "\"DetailTextures\"", 0) > 0.5;
            o->reflejos = cfg_num(c, "\"EnvMapEnable\"", 0) > 0.5;
            o->niebla = cfg_num(c, "\"FogEnable\"", 1) > 0.5;
            o->brillo = cfg_num(c, "\"ScreenGlowEnable\"", 0) > 0.5;
            o->gamma = (int)(cfg_num(c, "\"GammaR\"", 1.0) * 100 + 0.5);
            HeapFree(GetProcessHeap(), 0, c);
            opc_limitar(o);
            return "autoexec.cfg";
        }
    }
    return "por defecto";
}

/* las líneas del autoexec.cfg (EDA-Opciones.py aplicar(): las mismas claves y el mismo formato) */
static int opc_lineas(const OPC *o, char l[][64], int en_vivo)
{
    int n = 0;
    if (!en_vivo) {
        lstrcpyA(l[n++], "\"windowed\" \"1\"");           /* ★ siempre: la pantalla completa es sin bordes (la dll) */
        lstrcpyA(l[n++], "\"screenwidth\" \"800\"");
        lstrcpyA(l[n++], "\"screenheight\" \"600\"");
    }
    wsprintfA(l[n++], "\"MusicVolume\" \"%d.%02d\"", o->musica / 100, o->musica % 100);
    wsprintfA(l[n++], "\"SoundVolume\" \"%d.%02d\"", o->efectos / 100, o->efectos % 100);
    wsprintfA(l[n++], "\"ModelShadow_Proj_Enable\" \"%d\"", o->sombras ? 1 : 0);
    wsprintfA(l[n++], "\"DetailTextures\" \"%d\"", o->detalle ? 1 : 0);
    wsprintfA(l[n++], "\"EnvMapEnable\" \"%d\"", o->reflejos ? 1 : 0);
    wsprintfA(l[n++], "\"FogEnable\" \"%d\"", o->niebla ? 1 : 0);
    wsprintfA(l[n++], "\"ScreenGlowEnable\" \"%d\"", o->brillo ? 1 : 0);
    lstrcpyA(l[n++], "\"ScreenGlowGaussAmp0\" \"0.045\"");
    lstrcpyA(l[n++], "\"ScreenGlowGaussAmp1\" \"0.035\"");
    for (int k = 0; k < 3; k++)                              /* el brillo de la pantalla: la gamma del render */
        wsprintfA(l[n++], "\"Gamma%c\" \"%d.%02d\"", "RGB"[k], o->gamma / 100, o->gamma % 100);
    if (!en_vivo) lstrcpyA(l[n++], "\"alwaysfocused\" \"0\"");
    return n;
}
static void opc_escala(const OPC *o, char *t, const char *eje)
{
    wsprintfA(t, "scale \"##mouse\" \"##%s\" 0.%06d", eje, o->sens * 1000);
}

/* ★ al autoexec.cfg: cada "clave" se reemplaza en su línea (o se agrega arriba) y la escala del mouse en
 *   sus dos líneas (o se agrega abajo); se conservan los finales de línea del archivo */
static int opc_al_cfg(const OPC *o)
{
    WCHAR r[MAX_PATH];
    DWORD largo = 0;
    if (!ruta_juego(r, L"autoexec.cfg")) return 0;
    char *viejo = leer_archivo(r, &largo);
    if (!viejo) return 0;
    const char *nl = strstr(viejo, "\r\n") ? "\r\n" : "\n";
    DWORD cap = largo + 4096;
    char *t = (char *)HeapAlloc(GetProcessHeap(), 0, cap), *aux = (char *)HeapAlloc(GetProcessHeap(), 0, cap);
    if (!t || !aux) { HeapFree(GetProcessHeap(), 0, viejo); return 0; }
    lstrcpynA(t, viejo, cap);
    char l[20][64], escalas[2][64];
    int n = opc_lineas(o, l, 0);
    opc_escala(o, escalas[0], "x-axis");
    opc_escala(o, escalas[1], "y-axis");
    for (int k = 0; k < n + 2; k++) {
        const char *linea = k < n ? l[k] : escalas[k - n];
        char prefijo[64];
        if (k < n) {                                /* "clave" " */
            const char *fin = strchr(linea + 1, '"');
            lstrcpynA(prefijo, linea, (int)(fin - linea) + 4);      /* "clave" " (con la comilla del valor) */
        } else {
            lstrcpyA(prefijo, k == n ? "scale \"##mouse\" \"##x-axis\" " : "scale \"##mouse\" \"##y-axis\" ");
        }
        int lp = lstrlenA(prefijo);
        char *p = t, *hallado = NULL;
        while (*p) {
            if (!strncmp(p, prefijo, lp)) { hallado = p; break; }
            while (*p && *p != '\n') p++;
            if (*p) p++;
        }
        if (hallado) {
            char *fin = hallado;
            while (*fin && *fin != '\r' && *fin != '\n') fin++;
            lstrcpynA(aux, fin, cap);
            *hallado = 0;
            if ((DWORD)(lstrlenA(t) + lstrlenA(linea) + lstrlenA(aux) + 1) >= cap) break;
            lstrcatA(t, linea);
            lstrcatA(t, aux);
        } else if (k < n) {                         /* arriba, como el panel de Python */
            if ((DWORD)(lstrlenA(t) + lstrlenA(linea) + 3) >= cap) break;
            lstrcpynA(aux, t, cap);
            lstrcpyA(t, linea);
            lstrcatA(t, nl);
            lstrcatA(t, aux);
        } else {                                    /* abajo */
            if ((DWORD)(lstrlenA(t) + lstrlenA(linea) + 3) >= cap) break;
            int lt = lstrlenA(t);
            if (lt && t[lt - 1] != '\n') lstrcatA(t, nl);
            lstrcatA(t, linea);
            lstrcatA(t, nl);
        }
    }
    int ok = 1;
    if (lstrcmpA(t, viejo)) ok = escribir_archivo(r, t, (DWORD)lstrlenA(t));
    HeapFree(GetProcessHeap(), 0, viejo);
    HeapFree(GetProcessHeap(), 0, t);
    HeapFree(GetProcessHeap(), 0, aux);
    return ok;
}

/* ★ EN VIVO (sin guardar): sonido (con las funciones del juego), mouse, gráficos y brillo, por la consola */
static int g_sens_aplicada;              /* (la escala del mouse no es una variable del juego: la última puesta) */
static void opc_aplicar_vivo(const OPC *o)
{
    char l[20][64], e[64];
    InterlockedExchange(&g_vol_musica, o->musica);
    InterlockedExchange(&g_vol_efectos, o->efectos);
    int n = opc_lineas(o, l, 1);
    for (int i = 0; i < n; i++) opc_encolar(l[i]);
    opc_escala(o, e, "x-axis");
    opc_encolar(e);
    opc_escala(o, e, "y-axis");
    opc_encolar(e);
    g_sens_aplicada = o->sens;
}

/* ★ (15-nov) PANTALLA COMPLETA = SIN BORDES. Medido: con «windowed 0» (y RestartRender) el juego pasa a la
 *   pantalla completa EXCLUSIVA de Direct3D: ahí ninguna ventana (Options, Messenger) puede quedar encima (salía
 *   una «mini pantalla» en otro lado y nada respondía) y al volver el juego se cerró (21:58). Ahora el juego queda
 *   SIEMPRE en modo ventana (800×600) y la dll hace que su ventana tape el monitor entero, sin bordes: Present
 *   estira la imagen solo. Cambiar de modo es mover la ventana: al instante, sin Reset, y con todo lo demás encima. */
static volatile LONG g_pantalla_pedida = -1;    /* 1 sin bordes · 0 ventana · -1 nada */
static int g_pantalla_monitor = 1, g_sin_bordes;
static LONG g_estilo_viejo;
static RECT g_rect_viejo;
static int opc_monitores(RECT *salida);
static void opc_poner_sin_bordes(int si)
{
    HWND v = g_ventana_juego;
    if (!v) return;
    LONG estilo = GetWindowLongA(v, GWL_STYLE);
    if (si) {
        RECT mon[8], r;
        int n = opc_monitores(mon), k = g_pantalla_monitor >= 1 && g_pantalla_monitor <= n ? g_pantalla_monitor : 1;
        MONITORINFO mi = {sizeof(mi)};
        if (k == 1 || !GetMonitorInfoW(MonitorFromRect(&mon[k - 1], MONITOR_DEFAULTTONEAREST), &mi))
            GetMonitorInfoW(MonitorFromWindow(v, MONITOR_DEFAULTTOPRIMARY), &mi);
        if (k > 1) GetMonitorInfoW(MonitorFromRect(&mon[k - 1], MONITOR_DEFAULTTONEAREST), &mi);
        r = mi.rcMonitor;                                         /* (el monitor entero, con la barra de tareas) */
        if (!g_sin_bordes) { g_estilo_viejo = estilo; GetWindowRect(v, &g_rect_viejo); }
        SetWindowLongA(v, GWL_STYLE, (estilo & ~(WS_CAPTION | WS_THICKFRAME | WS_SYSMENU | WS_MINIMIZEBOX | WS_MAXIMIZEBOX))
                                     | WS_POPUP | WS_VISIBLE);
        SetWindowPos(v, HWND_TOP, r.left, r.top, r.right - r.left, r.bottom - r.top, SWP_FRAMECHANGED | SWP_SHOWWINDOW);
        if (!g_sin_bordes) apuntar("  [mazino] opciones: pantalla completa SIN BORDES (%ld×%ld, monitor %d)",
                                   r.right - r.left, r.bottom - r.top, k);
        g_sin_bordes = 1;
    } else if (g_sin_bordes) {
        g_sin_bordes = 0;
        SetWindowLongA(v, GWL_STYLE, g_estilo_viejo);
        SetWindowPos(v, NULL, g_rect_viejo.left, g_rect_viejo.top, g_rect_viejo.right - g_rect_viejo.left,
                     g_rect_viejo.bottom - g_rect_viejo.top, SWP_FRAMECHANGED | SWP_NOZORDER | SWP_SHOWWINDOW);
        apuntar("  [mazino] opciones: de vuelta a modo ventana");
    }
}
/* (en el hilo del juego) lo pedido; y si el juego le devolvió los bordes a su ventana, se los saca otra vez */
static void opc_pantalla_tick(void)
{
    if (!g_ventana_juego) return;
    LONG p = InterlockedExchange(&g_pantalla_pedida, -1);
    if (p >= 0) opc_poner_sin_bordes((int)p);
    else if (g_sin_bordes && (GetWindowLongA(g_ventana_juego, GWL_STYLE) & WS_CAPTION)) {
        g_sin_bordes = 0;
        opc_poner_sin_bordes(1);
    }
}
static void opc_cambiar_modo(const OPC *o)
{
    g_pantalla_monitor = o->monitor;
    InterlockedExchange(&g_pantalla_pedida, o->completa ? 1 : 0);
}

/* GUARDAR: el ini, el json (si está) y la consola */
static int opc_guardar(const OPC *o)
{
    char v[16];
    int ok = g_ini[0] != 0;
    if (ok) {
        for (int i = 0; i < OPC_N; i++) {
            wsprintfA(v, "%d", *opc_campo((OPC *)o, i));
            ok &= WritePrivateProfileStringA("opciones", OPC_CLAVES[i], v, g_ini) != 0;
        }
        ok &= WritePrivateProfileStringA("opciones", "guardado", "1", g_ini) != 0;
    }
    WCHAR r[MAX_PATH];
    if (ruta_json(r)) {                             /* el mismo formato que json.dumps(indent=1) */
        char j[600];
        wsprintfA(j, "{\n \"pantalla_completa\": %s,\n \"musica\": %d,\n \"efectos\": %d,\n \"sensibilidad\": %d,\n"
                     " \"sombras\": %s,\n \"texturas_detalle\": %s,\n \"reflejos\": %s,\n \"niebla\": %s,\n"
                     " \"monitor\": %d,\n \"brillo\": %s,\n \"brillo_pantalla\": %d\n}",
                  o->completa ? "true" : "false", o->musica, o->efectos, o->sens, o->sombras ? "true" : "false",
                  o->detalle ? "true" : "false", o->reflejos ? "true" : "false", o->niebla ? "true" : "false",
                  o->monitor, o->brillo ? "true" : "false", o->gamma);
        escribir_archivo(r, j, (DWORD)lstrlenA(j));
    }
    opc_aplicar_vivo(o);
    apuntar("  [mazino] opciones: guardadas (%s) · música %d · efectos %d · mouse %d · %s · monitor %d", ok ? "ini" : "⚠ ini",
            o->musica, o->efectos, o->sens, o->completa ? "pantalla completa" : "ventana", o->monitor);
    return ok;
}

/* ── el monitor (`EDA-Opciones.py --ubicar`) ── */
typedef struct { RECT r[8]; int prim[8], n; } MONITORES;
static BOOL CALLBACK opc_un_monitor(HMONITOR h, HDC d, LPRECT r, LPARAM dato)
{
    (void)d; (void)r;
    MONITORES *m = (MONITORES *)dato;
    MONITORINFO i = {sizeof(i)};
    if (m->n < 8 && GetMonitorInfoW(h, &i)) {
        m->r[m->n] = i.rcWork;
        m->prim[m->n] = (i.dwFlags & MONITORINFOF_PRIMARY) != 0;
        m->n++;
    }
    return TRUE;
}
/* el principal primero y los demás de izquierda a derecha */
static int opc_monitores(RECT *salida)
{
    MONITORES m;
    m.n = 0;
    EnumDisplayMonitors(NULL, NULL, opc_un_monitor, (LPARAM)&m);
    for (int i = 1; i < m.n; i++)
        for (int k = i; k > 0; k--) {
            int a = !m.prim[k - 1], b = !m.prim[k];
            if (a > b || (a == b && m.r[k - 1].left > m.r[k].left)) {
                RECT tr = m.r[k]; m.r[k] = m.r[k - 1]; m.r[k - 1] = tr;
                int tp = m.prim[k]; m.prim[k] = m.prim[k - 1]; m.prim[k - 1] = tp;
            }
        }
    for (int i = 0; i < m.n && salida; i++) salida[i] = m.r[i];
    return m.n ? m.n : 1;
}
static int g_ubicar, g_ubicadas;
static DWORD g_ubicar_desde;
static void opc_ubicar_tick(void)
{
    RECT mon[8], w;
    if (!g_ventana_juego || !g_ubicar) return;
    if (!g_ubicar_desde) g_ubicar_desde = GetTickCount();
    if (GetTickCount() - g_ubicar_desde > 90000 || g_ubicadas >= 6) { g_ubicar = 0; return; }
    int n = opc_monitores(mon);
    if (g_ubicar > n || !GetWindowRect(g_ventana_juego, &w)) { g_ubicar = 0; return; }
    RECT a = mon[g_ubicar - 1];
    int an = w.right - w.left, al = w.bottom - w.top;
    int x = a.left + (a.right - a.left - an > 0 ? (a.right - a.left - an) / 2 : 0);
    int y = a.top + (a.bottom - a.top - al > 0 ? (a.bottom - a.top - al) / 2 : 0);
    if (w.left != x || w.top != y) SetWindowPos(g_ventana_juego, NULL, x, y, 0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE);
    if (++g_ubicadas == 1) apuntar("  [mazino] opciones: la ventana del juego al monitor %d", g_ubicar);
}

static void opc_mover_monitor(int monitor)
{
    g_ubicadas = 0;
    g_ubicar_desde = 0;
    g_ubicar = monitor;
    apuntar("  [mazino] opciones: monitor %d (en vivo)", monitor);
}

/* ★ al abrir el juego (DllMain): lo guardado en el ini, al autoexec.cfg */
static void opc_al_arrancar(void)
{
    WCHAR rj[MAX_PATH];
    if (!(g_ini[0] && GetPrivateProfileIntA("opciones", "guardado", 0, g_ini)) && !ruta_json(rj)) {
        apuntar("  [mazino] opciones: nada guardado en eda_d3d9.ini todavía (se usa el autoexec.cfg tal cual)");
        return;
    }
    OPC o;
    const char *origen = opc_leer(&o);
    int ok = opc_al_cfg(&o);                 /* (también con EDA-opciones.json: así «windowed» queda en 1) */
    apuntar("  [mazino] opciones: %s → autoexec.cfg %s (%s, monitor %d)", origen, ok ? "puesto" : "⚠ no se pudo escribir",
            o.completa ? "pantalla completa sin bordes" : "ventana", o.monitor);
    if (o.completa) { g_pantalla_monitor = o.monitor; g_pantalla_pedida = 1; }
    else if (o.monitor > 1) g_ubicar = o.monitor;
}

/* ════════════════════════════════ LA VENTANA (el look de eda_ui.py) ════════════════════════════════ */
typedef struct {
    HBRUSH (WINAPI *solido)(COLORREF);
    HPEN (WINAPI *lapiz)(int, int, COLORREF);
    HGDIOBJ (WINAPI *usar)(HDC, HGDIOBJ);
    BOOL (WINAPI *borrar)(HGDIOBJ);
    BOOL (WINAPI *elipse)(HDC, int, int, int, int);
    BOOL (WINAPI *poligono)(HDC, const POINT *, int);
    BOOL (WINAPI *ir)(HDC, int, int, LPPOINT);
    BOOL (WINAPI *trazar)(HDC, int, int);
    COLORREF (WINAPI *color_texto)(HDC, COLORREF);
    int (WINAPI *fondo)(HDC, int);
    HFONT (WINAPI *fuente)(int, int, int, int, int, DWORD, DWORD, DWORD, DWORD, DWORD, DWORD, DWORD, DWORD, LPCWSTR);
    HDC (WINAPI *dc)(HDC);
    HBITMAP (WINAPI *mapa)(HDC, int, int);
    BOOL (WINAPI *copiar)(HDC, int, int, int, int, HDC, int, int, DWORD);
    BOOL (WINAPI *borrar_dc)(HDC);
    HGDIOBJ (WINAPI *stock)(int);
    BOOL (WINAPI *medir)(HDC, LPCWSTR, int, LPSIZE);
} GDI;
static GDI G;
static int gdi_listo(void)
{
    static int hecho = -1;
    if (hecho >= 0) return hecho;
    HMODULE m = LoadLibraryW(L"gdi32.dll");
    hecho = 0;
    if (!m) return 0;
#define CARGA(campo, nombre) if (!(*(FARPROC *)&G.campo = GetProcAddress(m, nombre))) return 0
    CARGA(solido, "CreateSolidBrush"); CARGA(lapiz, "CreatePen"); CARGA(usar, "SelectObject");
    CARGA(borrar, "DeleteObject"); CARGA(elipse, "Ellipse"); CARGA(poligono, "Polygon");
    CARGA(ir, "MoveToEx"); CARGA(trazar, "LineTo"); CARGA(color_texto, "SetTextColor"); CARGA(fondo, "SetBkMode");
    CARGA(fuente, "CreateFontW"); CARGA(dc, "CreateCompatibleDC"); CARGA(mapa, "CreateCompatibleBitmap");
    CARGA(copiar, "BitBlt"); CARGA(borrar_dc, "DeleteDC"); CARGA(stock, "GetStockObject");
    CARGA(medir, "GetTextExtentPoint32W");
#undef CARGA
    hecho = 1;
    return 1;
}

/* los colores de eda_ui.py (0xRRGGBB) */
enum {
    NEGRO = 0x050607, FONDO = 0x0d0e10, PANEL = 0x08090b, ACERO_CLARO = 0xc9ccd1, ACERO = 0x7d828a,
    ACERO_OSCURO = 0x34373c, TEXTO = 0xe6e6e6, GRIS = 0x8a8f96, CIAN = 0x7fd6ff, CIAN_BRILLO = 0xd9f3ff,
    ROJO = 0x8e1b1b, ROJO_LUZ = 0xff3b3b, VERDE = 0x3ddc84, ORO = 0xe0b84f, MENU_FONDO = 0x0a0b0d
};
static const DWORD ESTILO_ARRIBA[4] = {0x454a86, 0x3c706c, 0x7a2a2a, 0x5b6068};   /* morado teal granate acero */
static const DWORD ESTILO_ABAJO[4] = {0x15172e, 0x102423, 0x240a0a, 0x16181b};
enum { MORADO, TEAL, GRANATE, ACERO_E };
#define CR(x) RGB(((x) >> 16) & 255, ((x) >> 8) & 255, (x) & 255)
static DWORD mezcla(DWORD a, DWORD b, int t256)
{
    DWORD r = 0;
    for (int s = 0; s <= 16; s += 8) {
        int x = (a >> s) & 255, y = (b >> s) & 255;
        r |= (DWORD)(x + (y - x) * t256 / 256) << s;
    }
    return r;
}

static HFONT F_NORMAL, F_BOLD, F_CHICA, F_SECCION, F_TITULO;
static void caja(HDC d, int x0, int y0, int x1, int y1, DWORD c)      /* [x0,x1) × [y0,y1) */
{
    RECT r = {x0, y0, x1, y1};
    HBRUSH b = G.solido(CR(c));
    FillRect(d, &r, b);
    G.borrar(b);
}
static void borde(HDC d, int x0, int y0, int x1, int y1, DWORD c)     /* como create_rectangle(outline) */
{
    RECT r = {x0, y0, x1 + 1, y1 + 1};
    HBRUSH b = G.solido(CR(c));
    FrameRect(d, &r, b);
    G.borrar(b);
}
static void degrade(HDC d, int x0, int y0, int x1, int y1, DWORD arriba, DWORD abajo)
{
    int h = y1 - y0 > 0 ? y1 - y0 : 1;
    for (int i = 0; i < y1 - y0; i++) caja(d, x0, y0 + i, x1, y0 + i + 1, mezcla(arriba, abajo, i * 256 / h));
}
static void linea(HDC d, int x0, int y0, int x1, int y1, DWORD c, int ancho)
{
    HPEN p = G.lapiz(PS_SOLID, ancho, CR(c));
    HGDIOBJ v = G.usar(d, p);
    G.ir(d, x0, y0, NULL);
    G.trazar(d, x1, y1);
    G.usar(d, v);
    G.borrar(p);
}
static void ovalo(HDC d, int x0, int y0, int x1, int y1, long relleno, long contorno)   /* -1 = sin */
{
    HBRUSH b = relleno >= 0 ? G.solido(CR((DWORD)relleno)) : (HBRUSH)G.stock(NULL_BRUSH);
    HPEN p = contorno >= 0 ? G.lapiz(PS_SOLID, 1, CR((DWORD)contorno)) : (HPEN)G.stock(NULL_PEN);
    HGDIOBJ vb = G.usar(d, b), vp = G.usar(d, p);
    G.elipse(d, x0, y0, x1 + 1, y1 + 1);
    G.usar(d, vb);
    G.usar(d, vp);
    if (relleno >= 0) G.borrar(b);
    if (contorno >= 0) G.borrar(p);
}
static void poligono(HDC d, const POINT *pt, int n, long relleno, DWORD contorno, int ancho)
{
    HBRUSH b = relleno >= 0 ? G.solido(CR((DWORD)relleno)) : (HBRUSH)G.stock(NULL_BRUSH);
    HPEN p = G.lapiz(PS_SOLID, ancho, CR(contorno));
    HGDIOBJ vb = G.usar(d, b), vp = G.usar(d, p);
    G.poligono(d, pt, n);
    G.usar(d, vb);
    G.usar(d, vp);
    if (relleno >= 0) G.borrar(b);
    G.borrar(p);
}
/* texto: modo 0 = arriba-izquierda en (x,y); 1 = centrado en (x,y); devuelve el ancho */
static int texto(HDC d, int x, int y, const WCHAR *t, DWORD c, HFONT f, int modo)
{
    SIZE s = {0, 0};
    HGDIOBJ v = G.usar(d, f);
    G.medir(d, t, lstrlenW(t), &s);
    G.color_texto(d, CR(c));
    RECT r;
    if (modo == 1) { r.left = x - s.cx / 2 - 1; r.top = y - s.cy / 2; }
    else { r.left = x; r.top = y; }
    r.right = r.left + s.cx + 2;
    r.bottom = r.top + s.cy;
    DrawTextW(d, t, -1, &r, DT_LEFT | DT_TOP | DT_SINGLELINE | DT_NOPREFIX | DT_NOCLIP);
    G.usar(d, v);
    return s.cx;
}
/* un párrafo (wraplength): devuelve el alto */
static int parrafo(HDC d, int x, int y, int ancho, const WCHAR *t, DWORD c, HFONT f)
{
    RECT r = {x, y, x + ancho, y + 400};
    HGDIOBJ v = G.usar(d, f);
    G.color_texto(d, CR(c));
    DrawTextW(d, t, -1, &r, DT_LEFT | DT_WORDBREAK | DT_NOPREFIX | DT_CALCRECT);
    DrawTextW(d, t, -1, &r, DT_LEFT | DT_WORDBREAK | DT_NOPREFIX);
    G.usar(d, v);
    return r.bottom - r.top;
}

/* ── los controles que se dibujan (y se buscan al hacer clic) ── */
enum { C_CERRAR_X = 1, C_MENU, C_GUARDAR, C_CERRAR, C_SELECTOR, C_DESLIZADOR, C_CASILLA, C_TECLAS };
typedef struct { RECT r; int tipo, id, valor; } CTL;
static CTL g_ctl[48];
static int g_nctl, g_encima = -1, g_arrastre = -1;
static int registrar(int x0, int y0, int x1, int y1, int tipo, int id, int valor)
{
    if (g_nctl >= 48) return -1;
    CTL *c = &g_ctl[g_nctl];
    SetRect(&c->r, x0, y0, x1, y1);
    c->tipo = tipo; c->id = id; c->valor = valor;
    return g_nctl++;
}
static int encima_de(int k) { return k >= 0 && k == g_encima; }

static HWND g_opc_ventana;
static volatile LONG g_opc_abriendo;
static OPC g_op, g_abierto;              /* (g_abierto: cómo estaba al abrir, para saber qué pide reinicio) */
static float g_valor_real[9];                  /* lo que usa el juego, leído al apretar Options (hilo del juego) */
static int g_valor_hay[9];
static const char *const REAL_NOMBRES[9] = {"MusicVolume", "SoundVolume", "ModelShadow_Proj_Enable", "DetailTextures",
                                           "EnvMapEnable", "FogEnable", "ScreenGlowEnable", "windowed", "GammaR"};
static void opc_leer_real(void)
{
    for (int i = 0; i < 9; i++) g_valor_hay[i] = variable_del_juego(REAL_NOMBRES[i], &g_valor_real[i]);
}
static void opc_poner_real(OPC *o)
{
    int *campos[7] = {&o->musica, &o->efectos, &o->sombras, &o->detalle, &o->reflejos, &o->niebla, &o->brillo};
    int n = 0;
    for (int i = 0; i < 7; i++)
        if (g_valor_hay[i]) { *campos[i] = i < 2 ? (int)(g_valor_real[i] * 100 + 0.5f) : g_valor_real[i] > 0.5f; n++; }
    o->completa = g_sin_bordes;                                           /* (la pantalla completa es la nuestra) */
    if (g_valor_hay[8]) o->gamma = (int)(g_valor_real[8] * 100 + 0.5f);
    if (g_sens_aplicada) o->sens = g_sens_aplicada;
    opc_limitar(o);
    if (n) apuntar("  [mazino] opciones: %d valores leídos del juego (música %d · efectos %d)", n, o->musica, o->efectos);
}
static int g_seccion, g_nmon = 1;
static WCHAR g_estado[160];
static DWORD g_estado_color = VERDE;
#define OPC_ANCHO 660
#define OPC_ALTO 450

/* Boton de eda_ui.py */
static void boton(HDC d, int x, int y, int w, int h, const WCHAR *t, int estilo, int tipo, int id)
{
    int k = registrar(x, y, x + w, y + h, tipo, id, 0), sobre = encima_de(k);
    DWORD arriba = ESTILO_ARRIBA[estilo], abajo = ESTILO_ABAJO[estilo];
    caja(d, x, y, x + w, y + h, 0x0a0a0a);
    degrade(d, x + 2, y + 2, x + w - 2, y + h - 2, sobre ? mezcla(arriba, 0xffffff, 31) : arriba, abajo);
    linea(d, x + 2, y + 2, x + w - 2, y + 2, mezcla(arriba, 0xffffff, 115), 1);
    borde(d, x + 1, y + 1, x + w - 2, y + h - 2, sobre ? ROJO_LUZ : ACERO_CLARO);
    texto(d, x + w / 2 + 1, y + h / 2 + 1, t, 0x000000, F_BOLD, 1);
    texto(d, x + w / 2, y + h / 2, t, TEXTO, F_BOLD, 1);
}
/* Selector: opciones en fila, una elegida */
static void selector(HDC d, int x, int y, int w, int grupo, const int *valores, const WCHAR *const *textos, int n, int elegido)
{
    for (int i = 0; i < n; i++) {
        int x0 = x + i * (w + 4), si = valores[i] == elegido;
        registrar(x0, y, x0 + w, y + 26, C_SELECTOR, grupo, valores[i]);
        degrade(d, x0 + 1, y + 1, x0 + w - 1, y + 25, si ? 0x3c706c : 0x1e2024, si ? 0x0b1312 : 0x060708);
        borde(d, x0, y, x0 + w - 1, y + 25, si ? CIAN : ACERO);
        texto(d, x0 + w / 2, y + 13, textos[i], si ? CIAN_BRILLO : GRIS, si ? F_BOLD : F_NORMAL, 1);
    }
}
/* Deslizador: barra de metal, relleno rojo, perilla de acero y el valor en cian */
static void deslizador(HDC d, int x, int y, int id, int valor, int desde, int hasta)
{
    const int w = 260, h = 22;
    int x0 = x + 8, x1 = x + w - 8, yc = y + h / 2;
    int xp = x0 + (x1 - x0) * (valor - desde) / (hasta - desde > 0 ? hasta - desde : 1);
    registrar(x, y, x + w, y + h, C_DESLIZADOR, id, 0);
    caja(d, x0 - 1, yc - 4, x1 + 2, yc + 5, 0x000000);
    borde(d, x0 - 1, yc - 4, x1 + 1, yc + 4, ACERO);
    if (xp > x0) degrade(d, x0, yc - 3, xp, yc + 3, ROJO_LUZ, 0x5a0b0b);
    ovalo(d, xp - 7, yc - 7, xp + 7, yc + 7, 0x9aa0a8, 0x1a1c1f);
    ovalo(d, xp - 3, yc - 3, xp + 3, yc + 3, 0xe8eaee, -1);
    WCHAR v[12];
    wsprintfW(v, L"%d", valor);
    texto(d, x + w + 22, yc, v, CIAN_BRILLO, F_BOLD, 1);
}
/* Casilla: interruptor con LED */
static int casilla(HDC d, int x, int y, int id, const WCHAR *t, int si)
{
    int ancho = texto(d, x + 24, y, t, si ? TEXTO : GRIS, F_NORMAL, 0);
    registrar(x, y, x + 24 + ancho, y + 16, C_CASILLA, id, 0);
    caja(d, x, y, x + 16, y + 16, 0x000000);
    borde(d, x, y, x + 15, y + 15, ACERO_CLARO);
    if (si) { caja(d, x + 3, y + 3, x + 13, y + 13, ROJO_LUZ); borde(d, x + 3, y + 3, x + 12, y + 12, 0xff9a9a); }
    else { caja(d, x + 3, y + 3, x + 13, y + 13, 0x1b1d20); borde(d, x + 3, y + 3, x + 12, y + 12, 0x2a2d31); }
    return 16;
}
/* título de sección: en mayúsculas, cian, con la línea roja */
static int titulo(HDC d, int x, int y, int derecha, const WCHAR *t)
{
    y += 10;
    int a = texto(d, x, y, t, CIAN, F_SECCION, 0);
    caja(d, x + a + 8, y + 8, derecha, y + 10, ROJO);
    return y + 17 + 6;
}
static int fila_etiqueta(HDC d, int x, int y, const WCHAR *t, DWORD c, HFONT f)
{
    texto(d, x, y, t, c, f, 0);
    return x + 104;
}

static void dibujar_seccion(HDC d, int x, int y, int derecha)
{
    static const int MODOS[2] = {0, 1};
    static const WCHAR *const MODOS_T[2] = {L"Ventana", L"Pantalla completa"};
    switch (g_seccion) {
    case 0: {                                                           /* VIDEO */
        y = titulo(d, x, y, derecha, L"PANTALLA");
        y += 5;
        selector(d, fila_etiqueta(d, x, y + 5, L"Modo", TEXTO, F_NORMAL), y, 150, 0, MODOS, MODOS_T, 2, g_op.completa);
        y += 26 + 5;
        if (g_nmon > 1) {
            int vals[8];
            WCHAR txt[8][24];
            const WCHAR *ptr[8];
            int n = g_nmon > 8 ? 8 : g_nmon;
            for (int i = 0; i < n; i++) {
                vals[i] = i + 1;
                wsprintfW(txt[i], i == 0 ? L"%d · principal" : L"%d", i + 1);
                ptr[i] = txt[i];
            }
            y += 5;
            selector(d, fila_etiqueta(d, x, y + 5, L"Monitor", TEXTO, F_NORMAL), y, 110, 1, vals, ptr, n, g_op.monitor);
            y += 26 + 5;
        }
        y += 4;
        y += 5;
        deslizador(d, fila_etiqueta(d, x, y + 4, L"Brillo", TEXTO, F_NORMAL), y, 3, g_op.gamma, 50, 150);
        y += 22 + 5 + 4;
        y += parrafo(d, x, y, 400, L"Modo y monitor: al GUARDAR, sin cerrar EDA. Pantalla completa = sin bordes "
                                   L"(Options y Messenger quedan encima). Brillo, sonido, mouse y gráficos: al moverlos.",
                     ORO, F_CHICA) + 4;
        parrafo(d, x, y, 400, L"La interfaz de 2009 sólo funciona en 800×600 (en pantalla completa se estira): "
                              L"por eso no hay otras resoluciones. El monitor vale en modo ventana.", GRIS, F_CHICA);
        break;
    }
    case 1:                                                             /* SONIDO */
        y = titulo(d, x, y, derecha, L"SONIDO");
        y += 5;
        deslizador(d, fila_etiqueta(d, x, y + 4, L"Música", TEXTO, F_NORMAL), y, 0, g_op.musica, 0, 100);
        y += 22 + 10;
        deslizador(d, fila_etiqueta(d, x, y + 4, L"Efectos", TEXTO, F_NORMAL), y, 1, g_op.efectos, 0, 100);
        break;
    case 2:                                                             /* MOUSE */
        y = titulo(d, x, y, derecha, L"MOUSE");
        y += 5;
        deslizador(d, fila_etiqueta(d, x, y + 4, L"Sensibilidad", TEXTO, F_NORMAL), y, 2, g_op.sens, 1, 30);
        y += 22 + 5 + 4;
        parrafo(d, x, y, 400, L"6 = la del juego.", GRIS, F_CHICA);
        break;
    case 3: {                                                           /* GRÁFICOS */
        static const WCHAR *const T[5] = {L"Brillo de la ropa con piedras", L"Sombras de los personajes",
                                          L"Texturas de detalle", L"Reflejos", L"Niebla"};
        int v[5] = {g_op.brillo, g_op.sombras, g_op.detalle, g_op.reflejos, g_op.niebla};
        y = titulo(d, x, y, derecha, L"CALIDAD GRÁFICA");
        for (int i = 0; i < 5; i++) { y += 5; y += casilla(d, x, y, i, T[i], v[i]) + 5; }
        break;
    }
    default: {                                                          /* CONTROLES */
        static const WCHAR *const AT[4][2] = {{L"F9", L"Listo / empezar (en la sala)"}, {L"F10", L"Options"},
                                              {L"F11", L"Messenger"}, {L"F12", L"Clan (reservado)"}};
        y = titulo(d, x, y, derecha, L"CONTROLES");
        y += 4;
        y += parrafo(d, x, y, 400, L"Habilidades F1–F8, ítems de HP/MP, moverse (WASD), mouse, cambiar de arma, "
                                   L"defender…: cada acción con la tecla que quieras.", GRIS, F_CHICA);
        y += 12;
        boton(d, x, y, 170, 30, L"CAMBIAR TECLAS", MORADO, C_TECLAS, 0);
        y += 30 + 12;
        y = titulo(d, x, y, derecha, L"ATAJOS");
        for (int i = 0; i < 4; i++) {
            y += 5;
            texto(d, x, y, AT[i][0], ORO, F_BOLD, 0);
            texto(d, x + 48, y, AT[i][1], TEXTO, F_NORMAL, 0);
            y += 15 + 5;
        }
    }
    }
}

static void opc_pintar(HDC d)
{
    const int w = OPC_ANCHO, h = OPC_ALTO;
    static const WCHAR *const MENU[5] = {L"VIDEO", L"SONIDO", L"MOUSE", L"GRÁFICOS", L"CONTROLES"};
    static const DWORD BANDAS[7] = {0x1b1d20, 0x5c6168, 0xb9bdc3, 0x8d939b, 0x4a4e54, 0x24272b, 0x0d0e10};
    g_nctl = 0;
    G.fondo(d, TRANSPARENT);
    caja(d, 0, 0, w, h, NEGRO);
    for (int i = 0; i < 7; i++) borde(d, i, i, w - 1 - i, h - 1 - i, BANDAS[i]);
    caja(d, 9, 52, w - 9, h - 9, FONDO);
    /* remaches */
    const int RX[4] = {12, w - 12, 12, w - 12}, RY[4] = {12, 12, h - 12, h - 12};
    for (int i = 0; i < 4; i++) {
        ovalo(d, RX[i] - 3, RY[i] - 3, RX[i] + 3, RY[i] + 3, 0x9aa0a8, 0x2a2d31);
        ovalo(d, RX[i] - 1, RY[i] - 1, RX[i] + 1, RY[i] + 1, 0xe8eaee, -1);
    }
    /* la placa del título */
    int pw = 170, px0 = (w - pw) / 2, py0 = 8, px1 = (w + pw) / 2, py1 = 40, c = 10;
    POINT forma[8] = {{px0 + c, py0}, {px1 - c, py0}, {px1, py0 + c}, {px1, py1 - c}, {px1 - c, py1}, {px0 + c, py1},
                      {px0, py1 - c}, {px0, py0 + c}};
    poligono(d, forma, 8, 0x0a0b0d, ACERO_CLARO, 2);
    POINT dentro[8] = {{px0 + c + 3, py0 + 4}, {px1 - c - 3, py0 + 4}, {px1 - 4, py0 + c + 1}, {px1 - 4, py1 - c - 1},
                       {px1 - c - 3, py1 - 4}, {px0 + c + 3, py1 - 4}, {px0 + 4, py1 - c - 1}, {px0 + 4, py0 + c + 1}};
    poligono(d, dentro, 8, -1, 0x3a3e44, 1);
    static const DWORD LUZ[5] = {0x3a0606, 0x7a0d0d, ROJO_LUZ, 0x7a0d0d, 0x3a0606};
    for (int i = 0; i < 5; i++) caja(d, px0 + c + 10, py1 + 3 + i, px1 - c - 10, py1 + 4 + i, LUZ[i]);
    texto(d, (px0 + px1) / 2 + 1, (py0 + py1) / 2 + 1, L"O P T I O N S", 0x1f6f8f, F_TITULO, 1);
    texto(d, (px0 + px1) / 2, (py0 + py1) / 2, L"O P T I O N S", CIAN_BRILLO, F_TITULO, 1);
    /* la ✕ de metal */
    int xx = w - 24, yy = 22, k = registrar(xx - 9, yy - 9, xx + 10, yy + 10, C_CERRAR_X, 0, 0);
    ovalo(d, xx - 9, yy - 9, xx + 9, yy + 9, 0x1a1c1f, ACERO);
    DWORD cx = encima_de(k) ? ROJO_LUZ : GRIS;
    linea(d, xx - 4, yy - 4, xx + 5, yy + 5, cx, 2);
    linea(d, xx + 4, yy - 4, xx - 5, yy + 5, cx, 2);
    /* el menú de metal (izquierda) */
    int L0 = 17, L1 = L0 + 148, T0 = 60, T1 = h - 9 - 8;
    caja(d, L0, T0, L1, T1, MENU_FONDO);
    borde(d, L0, T0, L1 - 1, T1 - 1, ACERO_OSCURO);
    int y = T0 + 1 + 8;
    texto(d, (L0 + L1) / 2, y + 6, L"MENU", CIAN, F_CHICA, 1);
    y += 13 + 4;
    for (int i = 0; i < 5; i++) {
        y += 3;
        boton(d, L0 + 1 + 8, y, 130, 32, MENU[i], i == g_seccion ? GRANATE : ACERO_E, C_MENU, i);
        y += 32 + 3;
    }
    int cerrar_y = T1 - 1 - 8 - 28, guardar_y = cerrar_y - 8 - 28;
    boton(d, L0 + 1 + 8, cerrar_y, 130, 28, L"CERRAR", GRANATE, C_CERRAR, 0);
    boton(d, L0 + 1 + 8, guardar_y, 130, 28, L"GUARDAR", TEAL, C_GUARDAR, 0);
    if (g_estado[0]) {
        RECT r = {L0 + 6, 0, L1 - 6, 0};
        HGDIOBJ v = G.usar(d, F_CHICA);
        DrawTextW(d, g_estado, -1, &r, DT_LEFT | DT_WORDBREAK | DT_NOPREFIX | DT_CALCRECT);
        int alto = r.bottom - r.top;
        r.left = L0 + 6; r.right = L1 - 6; r.bottom = guardar_y - 6; r.top = r.bottom - alto;
        G.color_texto(d, CR(g_estado_color));
        DrawTextW(d, g_estado, -1, &r, DT_LEFT | DT_WORDBREAK | DT_NOPREFIX);
        G.usar(d, v);
    }
    /* el panel negro (derecha) */
    int R0 = L1 + 8, R1 = w - 9 - 8;
    caja(d, R0, T0, R1, T1, ACERO);
    caja(d, R0 + 1, T0 + 1, R1 - 1, T1 - 1, PANEL);
    borde(d, R0 + 1, T0 + 1, R1 - 2, T1 - 2, 0x1f2226);
    dibujar_seccion(d, R0 + 2 + 16, T0 + 2 + 6, R1 - 2 - 16);
}

static int ctl_en(int x, int y)
{
    POINT p = {x, y};
    for (int i = g_nctl - 1; i >= 0; i--)
        if (PtInRect(&g_ctl[i].r, p)) return i;
    return -1;
}

static void deslizar(int k, int x)
{
    static const int DESDE[4] = {0, 0, 1, 50}, HASTA[4] = {100, 100, 30, 150};
    CTL *c = &g_ctl[k];
    int id = c->id, x0 = c->r.left + 8, x1 = c->r.left + 260 - 8;
    int v = DESDE[id] + ((HASTA[id] - DESDE[id]) * (x - x0) * 2 + (x1 - x0)) / (2 * (x1 - x0 > 0 ? x1 - x0 : 1));
    if (v < DESDE[id]) v = DESDE[id];
    if (v > HASTA[id]) v = HASTA[id];
    int *campos[4] = {&g_op.musica, &g_op.efectos, &g_op.sens, &g_op.gamma};
    *campos[id] = v;
}

/* abrir un archivo con su programa (como doble clic): cmd /c start, sin enlazar shell32 */
static int abrir_con_windows(const WCHAR *ruta)
{
    WCHAR cmd[MAX_PATH + 40];
    STARTUPINFOW si = {sizeof(si)};
    PROCESS_INFORMATION pi;
    wsprintfW(cmd, L"cmd.exe /c start \"\" \"%s\"", ruta);
    if (!CreateProcessW(NULL, cmd, NULL, NULL, FALSE, CREATE_NO_WINDOW, NULL, NULL, &si, &pi)) return 0;
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    return 1;
}

static void abrir_teclas(void)
{
    /* el panel de teclas pasa a la dll en la próxima etapa; hasta entonces, en la PC de desarrollo se abre el
     *   de Python (EDA-Teclas.py, al lado del repo) si está */
    WCHAR t[MAX_PATH], r[MAX_PATH];
    if (ruta_juego(t, L"..\\..\\..\\EDA-Teclas.py") && GetFullPathNameW(t, MAX_PATH, r, NULL)
        && GetFileAttributesW(r) != INVALID_FILE_ATTRIBUTES
        && abrir_con_windows(r)) {
        lstrcpyW(g_estado, L"Panel de teclas abierto.");
        g_estado_color = VERDE;
        return;
    }
    lstrcpyW(g_estado, L"El panel de teclas pasa a la dll en la próxima etapa.");
    g_estado_color = ORO;
}

/* ★ (16-nov) EL CURSOR SOBRE OPTIONS. Medido en el exe: el juego (LithTech) esconde el cursor de Windows con
 *   «while (ShowCursor(FALSE) >= 0)» (0x4D2461 / 0x4D256E, también al activarse) y en su WM_SETCURSOR pone
 *   SetCursor(NULL) (0x776862): dibuja el suyo con Direct3D. Desde que Options es ventana DEL juego (su dueño es
 *   EDA, de otro hilo), Windows une la entrada de los dos hilos y el contador del cursor pasa a ser UNO solo:
 *   el juego, al recibir la activación, lo vuelve a bajar y sobre Options el cursor no se ve.
 *   Arreglo por eventos, sin bucles ni hilos: cada vez que Windows le pregunta a Options qué cursor poner
 *   (WM_SETCURSOR, al moverse el mouse sobre ella) se sube el contador sólo lo justo para que se vea, y se anota
 *   cuánto; al cerrarla se devuelve exactamente eso, y el juego queda como lo tenía. */
static int g_cursor_subidas;
static void opc_cursor_visible(void)
{
    int n = ShowCursor(TRUE);
    if (n > 0) { ShowCursor(FALSE); return; }               /* (ya se veía: no se toca nada) */
    g_cursor_subidas++;
    while (n < 0 && g_cursor_subidas < 64) { n = ShowCursor(TRUE); g_cursor_subidas++; }
}
static void opc_cursor_devolver(void)
{
    if (g_diagnostico) apuntar("  (diag) Options: cursor de Windows devuelto al juego (%d)", g_cursor_subidas);
    while (g_cursor_subidas > 0) { ShowCursor(FALSE); g_cursor_subidas--; }
}

static LRESULT CALLBACK opc_proc(HWND v, UINT m, WPARAM w, LPARAM l)
{
    switch (m) {
    case WM_SETCURSOR:
        if (LOWORD(l) == HTCLIENT || LOWORD(l) == HTCAPTION) {
            POINT p;
            opc_cursor_visible();
            GetCursorPos(&p);
            ScreenToClient(v, &p);
            SetCursor(LoadCursorW(NULL, (LPCWSTR)(LOWORD(l) == HTCLIENT && ctl_en(p.x, p.y) >= 0 ? IDC_HAND : IDC_ARROW)));
            return TRUE;
        }
        break;
    case WM_NCHITTEST: {
        POINT p = {(short)LOWORD(l), (short)HIWORD(l)};
        ScreenToClient(v, &p);
        if (p.y < 52 && !(p.x > OPC_ANCHO - 36 && p.y < 34)) return HTCAPTION;   /* se arrastra por arriba */
        return HTCLIENT;
    }
    case WM_ERASEBKGND: return 1;
    case WM_PAINT: {
        PAINTSTRUCT ps;
        HDC d = BeginPaint(v, &ps), b = G.dc(d);
        HBITMAP bm = G.mapa(d, OPC_ANCHO, OPC_ALTO);
        HGDIOBJ viejo = G.usar(b, bm);
        opc_pintar(b);
        G.copiar(d, 0, 0, OPC_ANCHO, OPC_ALTO, b, 0, 0, SRCCOPY);
        G.usar(b, viejo);
        G.borrar(bm);
        G.borrar_dc(b);
        EndPaint(v, &ps);
        return 0;
    }
    case WM_MOUSEMOVE: {
        int x = (short)LOWORD(l), y = (short)HIWORD(l);
        if (g_arrastre >= 0) { deslizar(g_arrastre, x); InvalidateRect(v, NULL, FALSE); return 0; }
        int k = ctl_en(x, y);
        if (k >= 0 && g_ctl[k].tipo != C_CERRAR_X && g_ctl[k].tipo != C_MENU && g_ctl[k].tipo != C_GUARDAR
            && g_ctl[k].tipo != C_CERRAR && g_ctl[k].tipo != C_TECLAS) k = -1;            /* (hover: botones) */
        if (k != g_encima) {
            g_encima = k;
            TRACKMOUSEEVENT t = {sizeof(t), TME_LEAVE, v, 0};
            TrackMouseEvent(&t);
            InvalidateRect(v, NULL, FALSE);
        }
        SetCursor(LoadCursorW(NULL, (LPCWSTR)(ctl_en(x, y) >= 0 ? IDC_HAND : IDC_ARROW)));
        return 0;
    }
    case WM_MOUSELEAVE:
        if (g_encima >= 0) { g_encima = -1; InvalidateRect(v, NULL, FALSE); }
        return 0;
    case WM_LBUTTONDOWN: {
        int x = (short)LOWORD(l), y = (short)HIWORD(l), k = ctl_en(x, y);
        apuntar("  [mazino] opciones: clic (%d, %d) → %s", x, y, k < 0 ? "nada" : "control");
        if (k < 0) return 0;
        CTL c = g_ctl[k];
        switch (c.tipo) {
        case C_CERRAR_X: case C_CERRAR: DestroyWindow(v); return 0;
        case C_MENU: g_seccion = c.id; break;
        case C_SELECTOR: if (c.id == 0) g_op.completa = c.valor; else g_op.monitor = c.valor; break;
        case C_CASILLA: {
            int *campos[5] = {&g_op.brillo, &g_op.sombras, &g_op.detalle, &g_op.reflejos, &g_op.niebla};
            *campos[c.id] = !*campos[c.id];
            opc_aplicar_vivo(&g_op);                         /* ★ al instante */
            break;
        }
        case C_DESLIZADOR: g_arrastre = k; SetCapture(v); deslizar(k, x); break;
        case C_GUARDAR:
            if (opc_guardar(&g_op)) {
                int modo = g_op.completa != g_abierto.completa, mon = g_op.monitor != g_abierto.monitor;
                if (modo) opc_cambiar_modo(&g_op);
                else if (mon && !g_op.completa) opc_mover_monitor(g_op.monitor);
                else if (mon) opc_cambiar_modo(&g_op);             /* (sin bordes, a otro monitor) */
                lstrcpyW(g_estado, L"Guardado y aplicado.");
                g_estado_color = VERDE;
                g_abierto = g_op;
            } else {
                lstrcpyW(g_estado, L"No se pudo guardar en eda_d3d9.ini.");
                g_estado_color = ROJO_LUZ;
            }
            break;
        case C_TECLAS: abrir_teclas(); break;
        }
        InvalidateRect(v, NULL, FALSE);
        return 0;
    }
    case WM_LBUTTONUP:
        if (g_arrastre >= 0) { g_arrastre = -1; ReleaseCapture(); opc_aplicar_vivo(&g_op); }   /* ★ al instante */
        return 0;
    case WM_MOUSEWHEEL: {
        POINT p = {(short)LOWORD(l), (short)HIWORD(l)};
        ScreenToClient(v, &p);
        int k = ctl_en(p.x, p.y);
        if (k >= 0 && g_ctl[k].tipo == C_DESLIZADOR) {
            int *campos[4] = {&g_op.musica, &g_op.efectos, &g_op.sens, &g_op.gamma};
            *campos[g_ctl[k].id] += GET_WHEEL_DELTA_WPARAM(w) > 0 ? 1 : -1;
            opc_limitar(&g_op);
            opc_aplicar_vivo(&g_op);                         /* ★ al instante */
            InvalidateRect(v, NULL, FALSE);
        }
        return 0;
    }
    /* ★ (16-nov) con Options al frente el teclado del juego (DirectInput, «sólo al frente») no ve nada: F10
     *   se lee acá y pasan por el MISMO interruptor que en el juego (atajo → alternar_opciones), sin repetición
     *   (bit 30 = la tecla ya estaba apretada). F10 llega como tecla de sistema: se traga para que no abra el menú. */
    case WM_KEYDOWN: case WM_SYSKEYDOWN:
        if (w == VK_ESCAPE) { DestroyWindow(v); return 0; }
        if (w == VK_F10) {                                   /* (A es «MoveLeft» del juego: no es atajo) */
            if (!(l & (1L << 30))) atajo(0, "Options al frente");
            return 0;
        }
        if (m == WM_KEYDOWN) return 0;
        break;                                               /* (Alt+F4 y las demás de sistema, como siempre) */
    case WM_SYSKEYUP:
        if (w == VK_F10) return 0;
        break;
    case WM_CLOSE: DestroyWindow(v); return 0;
    case WM_DESTROY:
        opc_cursor_devolver();                               /* (todavía con la entrada unida a la del juego) */
        g_opc_ventana = NULL;
        g_arrastre = -1;
        g_encima = -1;
        PostQuitMessage(0);
        return 0;
    }
    return DefWindowProcW(v, m, w, l);
}

static DWORD WINAPI opc_hilo(LPVOID nada)
{
    (void)nada;
    HINSTANCE yo = GetModuleHandleW(NULL);
    if (!gdi_listo()) {
        apuntar("  [mazino] opciones: ⚠ no pude cargar gdi32");
        InterlockedExchange(&g_opc_abriendo, 0);
        return 0;
    }
    if (!F_NORMAL) {
        F_NORMAL = G.fuente(-12, 0, 0, 0, FW_NORMAL, 0, 0, 0, DEFAULT_CHARSET, 0, 0, CLEARTYPE_QUALITY, 0, L"Tahoma");
        F_BOLD = G.fuente(-12, 0, 0, 0, FW_BOLD, 0, 0, 0, DEFAULT_CHARSET, 0, 0, CLEARTYPE_QUALITY, 0, L"Tahoma");
        F_CHICA = G.fuente(-11, 0, 0, 0, FW_NORMAL, 0, 0, 0, DEFAULT_CHARSET, 0, 0, CLEARTYPE_QUALITY, 0, L"Tahoma");
        F_SECCION = G.fuente(-13, 0, 0, 0, FW_BOLD, 0, 0, 0, DEFAULT_CHARSET, 0, 0, CLEARTYPE_QUALITY, 0, L"Tahoma");
        F_TITULO = G.fuente(-16, 0, 0, 0, FW_BOLD, 0, 0, 0, DEFAULT_CHARSET, 0, 0, CLEARTYPE_QUALITY, 0, L"Trebuchet MS");
    }
    const char *origen = opc_leer(&g_op);
    opc_poner_real(&g_op);                                   /* ★ lo que usa el juego manda sobre lo guardado */
    g_nmon = opc_monitores(NULL);
    if (g_op.monitor > g_nmon) g_op.monitor = g_nmon;
    g_abierto = g_op;
    g_seccion = 0;
    g_estado[0] = 0;
    WNDCLASSW c = {0};
    c.lpfnWndProc = opc_proc;
    c.hInstance = yo;
    c.hCursor = LoadCursorW(NULL, (LPCWSTR)IDC_ARROW);
    c.lpszClassName = L"EDA_Opciones";
    RegisterClassW(&c);
    int x = 80, y = 80;
    RECT j;
    if (g_ventana_juego && GetWindowRect(g_ventana_juego, &j)) {      /* centrada en el juego */
        x = (j.left + j.right - OPC_ANCHO) / 2;
        y = (j.top + j.bottom - OPC_ALTO) / 2;
    }
    /* ★ (16-nov) ventana DEL juego, no «siempre encima»: su dueño es la ventana de EDA, así Windows la deja
     *   arriba de EDA (también en pantalla completa sin bordes), la baja junto con EDA cuando otra aplicación
     *   pasa al frente (Opera) y, al cerrarla, le devuelve el foco a EDA solo. Sin SetWindowPos ni temporizadores. */
    HWND v = CreateWindowExW(WS_EX_TOOLWINDOW, L"EDA_Opciones", L"Options", WS_POPUP,
                             x, y, OPC_ANCHO, OPC_ALTO, g_ventana_juego, NULL, yo, NULL);
    if (!v) { InterlockedExchange(&g_opc_abriendo, 0); apuntar("  [mazino] opciones: ⚠ no se pudo crear la ventana (%lu)", GetLastError()); return 0; }
    g_opc_ventana = v;
    InterlockedExchange(&g_opc_abriendo, 0);
    InterlockedExchange(&g_panel_abierto, 1);
    if (g_clip_real) g_clip_real(NULL);                      /* el cursor, libre */
    ShowWindow(v, SW_SHOWNORMAL);
    /* ★ al frente DE VERDAD: con el juego en pantalla completa sin bordes, SetForegroundWindow solo no alcanza
     *   (el juego tiene el foco y el mouse). Se une un momento la entrada de los dos hilos para poder pasarlo. */
    DWORD hilo_juego = g_ventana_juego ? GetWindowThreadProcessId(g_ventana_juego, NULL) : 0, yo_h = GetCurrentThreadId();
    if (hilo_juego && hilo_juego != yo_h) AttachThreadInput(yo_h, hilo_juego, TRUE);
    SetForegroundWindow(v);
    SetActiveWindow(v);
    SetFocus(v);
    if (hilo_juego && hilo_juego != yo_h) AttachThreadInput(yo_h, hilo_juego, FALSE);
    g_cursor_subidas = 0;
    opc_cursor_visible();                                    /* (el cursor ya queda sobre la ventana, abajo) */
    {   /* el cursor, sobre la ventana (en la stage el juego lo tenía centrado en otro lado o escondido) */
        RECT rv;
        if (GetWindowRect(v, &rv)) SetCursorPos((rv.left + rv.right) / 2, (rv.top + rv.bottom) / 2);
    }
    if (GetForegroundWindow() != v)                          /* (abierta pero sin el foco: se dice) */
        apuntar("  [mazino] opciones: ⚠ abierta pero SIN FOCO (al frente: 0x%08lX)", (unsigned long)(ULONG_PTR)GetForegroundWindow());
    apuntar("  [mazino] opciones: ventana abierta por %s (lo guardado salió de %s)", g_opc_por, origen);
    if (g_diagnostico) {
        POINT c;
        RECT cl;
        GetCursorPos(&c);
        GetClipCursor(&cl);
        CURSORINFO ci = {sizeof(ci)};
        GetCursorInfo(&ci);
        apuntar("  (diag) Options abierta: cursor de Windows %s (subido %d)", (ci.flags & CURSOR_SHOWING) ? "VISIBLE" : "ESCONDIDO",
                g_cursor_subidas);
        apuntar("  (diag) Options abierta: al frente %s · cursor (%ld, %ld) · cursor encerrado en (%ld,%ld)-(%ld,%ld) · %s",
                GetForegroundWindow() == v ? "OPTIONS" : GetForegroundWindow() == g_ventana_juego ? "EL JUEGO" : "otra ventana",
                c.x, c.y, cl.left, cl.top, cl.right, cl.bottom, g_sin_bordes ? "pantalla completa sin bordes" : "ventana");
    }
    g_opc_por = "?";
    MSG m;
    while (GetMessageW(&m, NULL, 0, 0) > 0) {
        TranslateMessage(&m);
        DispatchMessageW(&m);
    }
    /* (si F10 / A siguen apretadas al cerrar, el juego no las toma como una pulsación nueva: hay que soltarlas) */
    for (int i = 0; i < 3; i++) g_dik_antes[i] = 1;
    InterlockedExchange(&g_panel_abierto, 0);
    if (g_diagnostico) apuntar("  (diag) Options cerrada: al frente %s",
                               GetForegroundWindow() == g_ventana_juego ? "EL JUEGO" : "otra ventana");
    UnregisterClassW(L"EDA_Opciones", yo);
    if (g_ventana_juego) SetForegroundWindow(g_ventana_juego);
    return 0;
}

/* el botón Options (y F10 más adelante): abre la ventana, o la cierra si ya estaba */
static void alternar_opciones(void)
{
    /* ★ (16-nov) UN solo interruptor para F10, A, el botón del lobby y la barra: dos pedidos en menos de 300 ms
     *   son la misma pulsación vista por dos vías (no abre y cierra de golpe) */
    static DWORD ultimo;
    DWORD ahora = GetTickCount();
    if (ahora - ultimo < 300) { apuntar("  [mazino] opciones: pedido repetido (%s) → ignorado", g_opc_por); return; }
    ultimo = ahora;
    if (g_opc_ventana) { apuntar("  [mazino] opciones: ya estaba abierta → se cierra"); PostMessageW(g_opc_ventana, WM_CLOSE, 0, 0); return; }
    if (InterlockedExchange(&g_opc_abriendo, 1)) { apuntar("  [mazino] opciones: ya se está abriendo (pedido ignorado)"); return; }
    opc_leer_real();                                         /* (acá estamos en el hilo del juego) */
    HANDLE h = CreateThread(NULL, 0, opc_hilo, NULL, 0, NULL);
    if (h) CloseHandle(h);
    else { InterlockedExchange(&g_opc_abriendo, 0); apuntar("  [mazino] opciones: ⚠ no se pudo crear su hilo (%lu)", GetLastError()); }
}
