/* eda_medir5.c — ★ (Punto 5, Etapa 0, 18-nov) MEDICIÓN DE RESOLUCIÓN: SÓLO LEER. Se compila con eda_d3d9.c (#include).
 *
 *  Sólo se prende con la variable EDA_RES_PRUEBA («1280x720», «1920x1080», «800x600»), que pone únicamente
 *  EDA-Medir-Resolucion-*.bat (entorno de prueba). Sin ella, la dll hace exactamente lo de siempre.
 *  Con ella:
 *   · el autoexec.cfg que la dll escribe al cargar lleva esa resolución en vez de 800×600 (opc_lineas);
 *   · desde el Present que ya estaba enganchado (sin ganchos nuevos), una vez por segundo se LEE y se anota
 *     sólo lo que cambió: backbuffer (GetBackBuffer → GetDesc), viewport (GetViewport), la proyección vigente
 *     (GetTransform PROJECTION → FovX/FovY si es perspectiva), ventana / área cliente / monitor / escritorio,
 *     DPI, cuánto estira Windows el Present, el cursor de Windows y el del juego (0x94952C), y la escena;
 *   · 3 s después de cada escena nueva se guarda el BACKBUFFER (lo que dibuja el juego, antes de que Windows
 *     lo estire) en _trabajo\juego\medir5\*.png con D3DXSaveSurfaceToFileA de la d3dx9_29.dll que ya carga el
 *     juego. Nada se escribe en el juego ni en el dispositivo. */

static int g_medir5;                         /* EDA_RES_PRUEBA presente */
static int g_res_w = 800, g_res_h = 600;     /* lo que va al autoexec.cfg (800×600 si no hay prueba) */

static void medir5_leer_env(void)
{
    char v[32];
    int w = 0, h = 0;
    if (!GetEnvironmentVariableA("EDA_RES_PRUEBA", v, sizeof(v))) return;
    if (sscanf(v, "%dx%d", &w, &h) == 2 && w >= 640 && h >= 480 && w <= 7680 && h <= 4320) {
        g_res_w = w;
        g_res_h = h;
        g_medir5 = 1;
        apuntar("  (medir5) ★ PRUEBA DE RESOLUCIÓN: autoexec.cfg con %d×%d · sólo lectura · capturas del backbuffer", w, h);
    } else apuntar("  (medir5) EDA_RES_PRUEBA=«%s» no válida: se queda en 800×600", v);
}

typedef long (WINAPI *M5_GETBB)(void *, UINT, UINT, UINT, void **);
typedef long (WINAPI *M5_GETVP)(void *, DWORD *);
typedef long (WINAPI *M5_GETTR)(void *, DWORD, float *);
typedef long (WINAPI *M5_DESC)(void *, DWORD *);
typedef ULONG (WINAPI *M5_REL)(void *);
typedef long (WINAPI *M5_GUARDAR)(const char *, DWORD, void *, const void *, const RECT *);
typedef UINT (WINAPI *M5_DPI)(HWND);

static float m5_atan(float x) { return (float)atan((double)x); }

static void medir5_guardar(void *dev, DWORD escena)
{
    static M5_GUARDAR guardar;
    static int buscado;
    if (!buscado) {
        buscado = 1;
        HMODULE m = GetModuleHandleA("d3dx9_29.dll");
        if (m) guardar = (M5_GUARDAR)GetProcAddress(m, "D3DXSaveSurfaceToFileA");
        if (!guardar) apuntar("  (medir5) ⚠ no encontré D3DXSaveSurfaceToFileA: sin capturas del backbuffer");
    }
    if (!guardar) return;
    char carpeta[MAX_PATH], ruta[MAX_PATH], *b;
    lstrcpynA(carpeta, g_log, MAX_PATH);
    b = strrchr(carpeta, '\\');
    if (!b) return;
    lstrcpyA(b + 1, "medir5");
    CreateDirectoryA(carpeta, NULL);
    SYSTEMTIME t;
    GetLocalTime(&t);
    void *sup = NULL;
    if (((M5_GETBB)VT(dev)[18])(dev, 0, 0, 0, &sup) != 0 || !sup) return;
    DWORD d[8] = {0};
    ((M5_DESC)VT(sup)[12])(sup, d);
    wsprintfA(ruta, "%s\\%02d%02d%02d-escena_%06lX-%lux%lu.png", carpeta, t.wHour, t.wMinute, t.wSecond,
              (unsigned long)escena & 0xFFFFFF, d[6], d[7]);
    long hr = guardar(ruta, 3 /* D3DXIFF_PNG */, sup, NULL, NULL);
    ((M5_REL)VT(sup)[2])(sup);
    apuntar("  (medir5) captura del backbuffer %lu×%lu → %s (0x%08lx)", d[6], d[7], strrchr(ruta, '\\') + 1, (unsigned long)hr);
}

static void medir5_present(void *dev)
{
    static DWORD ultimo, escena_antes, escena_desde, capturada;
    static char antes[512];
    DWORD ahora = GetTickCount();
    BYTE *esc = leer_ptr((void *)0x934554);
    DWORD escena = esc ? (DWORD)(ULONG_PTR)leer_ptr(esc) : 0;
    if (escena != escena_antes) { escena_antes = escena; escena_desde = ahora; capturada = 0; }
    if (!capturada && escena && ahora - escena_desde >= 3000) { capturada = 1; medir5_guardar(dev, escena); }
    if (ahora - ultimo < 1000) return;
    ultimo = ahora;

    /* backbuffer */
    DWORD bb[8] = {0};
    void *sup = NULL;
    if (((M5_GETBB)VT(dev)[18])(dev, 0, 0, 0, &sup) == 0 && sup) {
        ((M5_DESC)VT(sup)[12])(sup, bb);
        ((M5_REL)VT(sup)[2])(sup);
    }
    /* viewport y proyección vigentes (los últimos que puso el juego en este cuadro) */
    DWORD vp[6] = {0};
    ((M5_GETVP)VT(dev)[48])(dev, vp);
    float p[16] = {0};
    long hr_p = ((M5_GETTR)VT(dev)[45])(dev, 3 /* D3DTS_PROJECTION */, p);
    char proy[96];
    if (hr_p != 0) lstrcpyA(proy, "proyección: no se pudo leer");
    else if (p[11] > 0.99f && p[11] < 1.01f && p[15] > -0.01f && p[15] < 0.01f && p[0] > 0 && p[5] > 0) {
        float fx = 2 * m5_atan(1 / p[0]) * 57.29578f, fy = 2 * m5_atan(1 / p[5]) * 57.29578f;
        sprintf(proy, "perspectiva FovX %.1f° FovY %.1f° (m11 %.3f m22 %.3f → aspecto %.3f)", fx, fy, p[0], p[5], p[5] / p[0]);
    } else sprintf(proy, "no perspectiva (2D/orto: m11 %.4f m22 %.4f m41 %.2f m42 %.2f)", p[0], p[5], p[12], p[13]);
    /* ventana, área cliente, monitor, escritorio, DPI */
    RECT wr = {0}, cr = {0};
    HWND v = g_ventana_juego;
    if (v) { GetWindowRect(v, &wr); GetClientRect(v, &cr); }
    MONITORINFO mi = {sizeof(mi)};
    if (v) GetMonitorInfoW(MonitorFromWindow(v, MONITOR_DEFAULTTONEAREST), &mi);
    static M5_DPI dpi_de;
    static int dpi_buscado;
    if (!dpi_buscado) { dpi_buscado = 1; dpi_de = (M5_DPI)GetProcAddress(GetModuleHandleA("user32.dll"), "GetDpiForWindow"); }
    UINT dpi = v && dpi_de ? dpi_de(v) : 0;
    /* cursor de Windows (en el área cliente) y el que dibuja el juego (su objeto 0x94952C, en SU pantalla) */
    POINT c = {0};
    GetCursorPos(&c);
    if (v) ScreenToClient(v, &c);
    char cur[96] = "cursor del juego: ?";
    BYTE *o = leer_ptr((void *)0x94952C);
    if (o && legible(o + 0x27DC, 8) && legible(o + 0x330, 8))
        sprintf(cur, "cursor del juego (%.0f, %.0f) en su pantalla %d×%d", *(float *)(o + 0x27DC), *(float *)(o + 0x27E0),
                *(int *)(o + 0x330), *(int *)(o + 0x334));
    int cw = cr.right - cr.left, ch = cr.bottom - cr.top;
    char linea[512];
    sprintf(linea, "backbuffer %lu×%lu · viewport %lu,%lu %lu×%lu · %s · ventana %ld×%ld · cliente %d×%d (Windows estira ×%.2f / ×%.2f) · "
                   "monitor %ld×%ld · escritorio %d×%d · DPI %u · escena 0x%08lX",
            bb[6], bb[7], vp[0], vp[1], vp[2], vp[3], proy, wr.right - wr.left, wr.bottom - wr.top, cw, ch,
            bb[6] ? (double)cw / bb[6] : 0.0, bb[7] ? (double)ch / bb[7] : 0.0,
            mi.rcMonitor.right - mi.rcMonitor.left, mi.rcMonitor.bottom - mi.rcMonitor.top,
            GetSystemMetrics(78 /* SM_CXVIRTUALSCREEN */), GetSystemMetrics(79), dpi, (unsigned long)escena);
    if (strcmp(linea, antes)) { lstrcpynA(antes, linea, sizeof(antes)); apuntar("  (medir5) %s", linea); }
    static DWORD ultimo_cursor;
    if (ahora - ultimo_cursor >= 5000) {                 /* (el mouse, cada 5 s: Windows vs el del juego) */
        ultimo_cursor = ahora;
        apuntar("  (medir5) mouse: Windows (%ld, %ld) del cliente %d×%d · %s · %d cuadros/s", c.x, c.y, cw, ch, cur, g_fps);
    }
}
