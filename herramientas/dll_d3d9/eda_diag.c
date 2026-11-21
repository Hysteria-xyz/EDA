/* eda_diag.c — ★ (21-nov) EL DIAGNÓSTICO AUTOMÁTICO: la dll anota eventos chicos de la partida y los manda sola, en
 * segundo plano, al server de PRUEBA (POST /eda/diag, servidor/diag.py). El jugador no hace nada: ni BAT ni logs.
 *
 * CUÁNDO: sólo si el entorno es TEST (el server del launcher/ini) Y hay dirección ([diag] url / EDA_DIAG_URL) Y el
 * juego se lanzó con usuario y ticket. En prod, local o sin dirección: no hace NADA (ni el hilo).
 *
 * QUÉ MANDA (y nada más): inicio (versión, build, resolución del ini no: sólo versión), escena (la vtable de la escena,
 * un número del exe), congelado (≥ 2 s sin cuadros: cuánto y en qué escena), atrapado (≥ 15 s y sigue), fps (cada
 * ~30 s), foco (el juego al frente o no), server_conecta (cuántas veces; SIN la dirección), caida (código, sitio en el
 * exe o el NOMBRE del módulo, sin ruta), fin (cierre normal). Sin MAC, sin IP, sin nombre de la PC, sin rutas, sin
 * chat, sin el ticket. La sesión es un número al azar de cada arranque (no identifica la PC).
 *
 * CÓMO, SIN TOCAR LOS FPS: los ganchos sólo ponen una línea en una cola sin candados (eda_diag_nucleo.c) y siguen; si
 * se llena, se descarta. Un hilo de prioridad mínima la vacía cada 10 s y manda un lote por HTTPS (WinHTTP, cargada
 * con LoadLibrary desde ese hilo: si no está, no hay diagnóstico). Si no hay red, guarda hasta 256 KB en memoria y
 * reintenta cada vez más espaciado. Lo que no llegó (y la caída, que se escribe en el momento) queda en
 * diag\pendiente.jsonl (≤ 2 MB, ≤ 48 h) y sale en el próximo arranque.
 *
 * LA AUTENTICACIÓN (la misma de servidor/diag.py): K = HMAC-SHA256(ticket, "eda-diag-v1"); la dll calcula K en
 * preparar_linea y NO guarda el ticket. Cada lote: cuenta, sesión, lote (1, 2, 3…; un reintento usa el mismo número:
 * si ya había llegado, el server contesta 409 y se da por entregado), hora y firma. */
#include "eda_diag_nucleo.c"

static int g_dg_activo;                              /* ★ todo lo de acá mira esto primero */
static char g_dg_url[256];
static char g_dg_cuenta[24];
static unsigned char g_dg_k[32];
static int g_dg_k_lista;
static char g_dg_sesion[33];
static char g_dg_dir[MAX_PATH];                      /* <carpeta de la dll>\diag\ */
static DG_COLA g_dg_cola;
static ULONGLONG g_dg_t0;
static volatile LONG g_dg_ocupado;                   /* el hilo está tocando el búfer (para el cierre) */
static char *g_dg_buf;                               /* lo que todavía no llegó (líneas enteras) */
static size_t g_dg_n;
#define DG_BUF (256 * 1024)
#define DG_SPOOL_MAX (2 * 1024 * 1024)
#define DG_SPOOL_HORAS 48

static unsigned long long dg_ahora_utc(void)
{
    FILETIME f;
    GetSystemTimeAsFileTime(&f);
    unsigned long long t = ((unsigned long long)f.dwHighDateTime << 32) | f.dwLowDateTime;
    return t / 10000ULL - 11644473600000ULL;
}

/* ★ el gancho: una línea a la cola (nunca espera, nunca escribe a disco) */
static void dg_anotar(const char *e, const char *extra)
{
    if (!g_dg_activo) return;
    char l[DG_LARGO];
    if (dg_evento(l, sizeof(l), dg_ahora_utc(), GetTickCount64() - g_dg_t0, e, extra)) dg_cola_poner(&g_dg_cola, l);
}

static void dg_spool_ruta(char *out)
{
    lstrcpyA(out, g_dg_dir);
    lstrcatA(out, "pendiente.jsonl");
}

/* agrega líneas al archivo pendiente (sin pasar de 2 MB). Lo usan la caída y el cierre: el proceso puede no seguir */
static void dg_spool_agregar(const char *t, size_t n)
{
    if (!n) return;
    char ruta[MAX_PATH];
    dg_spool_ruta(ruta);
    CreateDirectoryA(g_dg_dir, NULL);
    HANDLE h = CreateFileA(ruta, FILE_APPEND_DATA, FILE_SHARE_READ, NULL, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (h == INVALID_HANDLE_VALUE) return;
    LARGE_INTEGER tam;
    DWORD e;
    if (GetFileSizeEx(h, &tam) && tam.QuadPart + (LONGLONG)n <= DG_SPOOL_MAX) WriteFile(h, t, (DWORD)n, &e, NULL);
    CloseHandle(h);
}

/* ★ la caída: además de la cola, al disco YA (el hilo puede no llegar a mandarla) */
static void dg_caida(DWORD cod, DWORD eip, const char *modulo)
{
    if (!g_dg_activo) return;
    static volatile LONG n;
    if (InterlockedIncrement(&n) > 3) return;
    char m[40] = "", ex[160], l[DG_LARGO];
    int j = 0;                                       /* sólo el nombre del módulo, sin la ruta y sin rarezas */
    for (const char *p = modulo ? modulo : ""; *p && j < 39; p++) {
        char c = *p;
        if (c == '\\' || c == '/' || c == ':') { j = 0; continue; }
        if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '.' || c == '_' || c == '-')
            m[j++] = c;
    }
    m[j] = 0;
    wsprintfA(ex, ",\"codigo\":\"0x%08lX\",\"sitio\":\"0x%08lX\",\"modulo\":\"%s\"", (unsigned long)cod, (unsigned long)eip, m);
    int k = dg_evento(l, sizeof(l) - 1, dg_ahora_utc(), GetTickCount64() - g_dg_t0, "caida", ex);
    if (!k) return;
    dg_cola_poner(&g_dg_cola, l);                    /* si el juego sigue (era de 1ª oportunidad), sale por la red */
    l[k++] = '\n';
    dg_spool_agregar(l, (size_t)k);                  /* y si no sigue, en el próximo arranque (diag_partida no la repite) */
}

/* ★ (vigía, cada 250 ms) congelamientos y foco, sin depender de [general] diagnostico */
static void dg_vigia(LONG presents, DWORD vt)
{
    if (!g_dg_activo) return;
    static LONG antes;
    static DWORD quieto, vuelta;
    static int atrapado_dicho, foco = -1;
    char ex[96];
    DWORD ahora = GetTickCount();
    if (presents != antes) {
        if (quieto && ahora - quieto >= 2000) {
            wsprintfA(ex, ",\"ms\":%lu,\"vt\":\"0x%08lX\"", ahora - quieto, (unsigned long)vt);
            dg_anotar("congelado", ex);
        }
        quieto = 0;
        atrapado_dicho = 0;
        antes = presents;
    } else if (presents && !quieto) quieto = ahora;
    if (quieto && !atrapado_dicho && ahora - quieto >= 15000) {
        wsprintfA(ex, ",\"vt\":\"0x%08lX\"", (unsigned long)vt);
        dg_anotar("atrapado", ex);
        atrapado_dicho = 1;
    }
    if (++vuelta % 4 == 0) {                         /* (cada 1 s) ¿el juego al frente? */
        DWORD pid = 0;
        HWND f = GetForegroundWindow();
        if (f) GetWindowThreadProcessId(f, &pid);
        int ahora_foco = pid == GetCurrentProcessId();
        if (ahora_foco != foco) {
            wsprintfA(ex, ",\"activo\":%d", ahora_foco);
            if (foco >= 0) dg_anotar("foco", ex);
            foco = ahora_foco;
        }
    }
}

static void dg_escena(DWORD vt)
{
    char ex[40];
    wsprintfA(ex, ",\"vt\":\"0x%08lX\"", (unsigned long)vt);
    dg_anotar("escena", ex);
}

static void dg_fps(int fps)
{
    char ex[24];
    wsprintfA(ex, ",\"fps\":%d", fps);
    dg_anotar("fps", ex);
}

/* ── el envío (sólo el hilo) ─────────────────────────────────────────────────────────────────────────── */
typedef void *HINET;
typedef HINET (WINAPI *W_OPEN)(LPCWSTR, DWORD, LPCWSTR, LPCWSTR, DWORD);
typedef HINET (WINAPI *W_CONNECT)(HINET, LPCWSTR, WORD, DWORD);
typedef HINET (WINAPI *W_REQ)(HINET, LPCWSTR, LPCWSTR, LPCWSTR, LPCWSTR, LPCWSTR *, DWORD);
typedef BOOL (WINAPI *W_SEND)(HINET, LPCWSTR, DWORD, LPVOID, DWORD, DWORD, DWORD_PTR);
typedef BOOL (WINAPI *W_RECV)(HINET, LPVOID);
typedef BOOL (WINAPI *W_QUERY)(HINET, DWORD, LPCWSTR, LPVOID, LPDWORD, LPDWORD);
typedef BOOL (WINAPI *W_CLOSE)(HINET);
typedef BOOL (WINAPI *W_TIMEOUTS)(HINET, int, int, int, int);
static struct { W_OPEN open; W_CONNECT connect; W_REQ req; W_SEND send; W_RECV recv; W_QUERY query; W_CLOSE close;
                W_TIMEOUTS timeouts; HINET ses; } W;
#define DG_W_ACCESO_PROXY 0                          /* WINHTTP_ACCESS_TYPE_DEFAULT_PROXY */
#define DG_W_SEGURO 0x00800000                       /* WINHTTP_FLAG_SECURE */
#define DG_W_ESTADO 19                               /* WINHTTP_QUERY_STATUS_CODE */
#define DG_W_NUMERO 0x20000000                       /* WINHTTP_QUERY_FLAG_NUMBER */

static int dg_winhttp(void)
{
    HMODULE m = LoadLibraryA("winhttp.dll");
    if (!m) return 0;
    W.open = (W_OPEN)GetProcAddress(m, "WinHttpOpen");
    W.connect = (W_CONNECT)GetProcAddress(m, "WinHttpConnect");
    W.req = (W_REQ)GetProcAddress(m, "WinHttpOpenRequest");
    W.send = (W_SEND)GetProcAddress(m, "WinHttpSendRequest");
    W.recv = (W_RECV)GetProcAddress(m, "WinHttpReceiveResponse");
    W.query = (W_QUERY)GetProcAddress(m, "WinHttpQueryHeaders");
    W.close = (W_CLOSE)GetProcAddress(m, "WinHttpCloseHandle");
    W.timeouts = (W_TIMEOUTS)GetProcAddress(m, "WinHttpSetTimeouts");
    if (!W.open || !W.connect || !W.req || !W.send || !W.recv || !W.query || !W.close || !W.timeouts) return 0;
    W.ses = W.open(L"EDA-diag/1", DG_W_ACCESO_PROXY, NULL, NULL, 0);
    if (!W.ses) return 0;
    W.timeouts(W.ses, 5000, 5000, 10000, 10000);
    return 1;
}

/* un lote: devuelve el código HTTP (0 = no hubo respuesta) */
static int dg_post(const char *cuerpo, size_t n, unsigned long lote)
{
    int https, puerto;
    char host[128], ruta[128], firma[65], cab[512];
    if (!dg_url(g_dg_url, &https, host, sizeof(host), &puerto, ruta, sizeof(ruta))) return 0;
    unsigned long long hora = dg_ahora_utc();
    dg_firmar(g_dg_k, g_dg_cuenta, hora, g_dg_sesion, lote, cuerpo, n, firma);
    WCHAR whost[128], wruta[128], wcab[512];
    MultiByteToWideChar(CP_ACP, 0, host, -1, whost, 128);
    MultiByteToWideChar(CP_ACP, 0, ruta, -1, wruta, 128);
    snprintf(cab, sizeof(cab), "Content-Type: application/x-ndjson\r\nX-EDA-Cuenta: %s\r\nX-EDA-Sesion: %s\r\n"
             "X-EDA-Lote: %lu\r\nX-EDA-Hora: %llu\r\nX-EDA-Firma: %s\r\n", g_dg_cuenta, g_dg_sesion, lote, hora, firma);
    MultiByteToWideChar(CP_ACP, 0, cab, -1, wcab, 512);
    int estado = 0;
    HINET c = W.connect(W.ses, whost, (WORD)puerto, 0);
    HINET r = c ? W.req(c, L"POST", wruta, NULL, NULL, NULL, https ? DG_W_SEGURO : 0) : NULL;
    if (r && W.send(r, wcab, (DWORD)-1, (LPVOID)cuerpo, (DWORD)n, (DWORD)n, 0) && W.recv(r, NULL)) {
        DWORD v = 0, t = sizeof(v);
        if (W.query(r, DG_W_ESTADO | DG_W_NUMERO, NULL, &v, &t, NULL)) estado = (int)v;
    }
    if (r) W.close(r);
    if (c) W.close(c);
    return estado;
}

/* saca de la cola al búfer (si no entra, lo más viejo se pierde: se cuenta) */
static void dg_juntar(void)
{
    char l[DG_LARGO + 1];
    InterlockedExchange(&g_dg_ocupado, 1);
    while (dg_cola_sacar(&g_dg_cola, l, DG_LARGO)) {
        size_t k = strlen(l);
        if (g_dg_n + k + 1 > DG_BUF) {               /* sin red hace rato: se tira la mitad más vieja */
            size_t corte = dg_cortar_lote(g_dg_buf, g_dg_n / 2 + 1);
            if (!corte) corte = g_dg_n;
            memmove(g_dg_buf, g_dg_buf + corte, g_dg_n - corte);
            g_dg_n -= corte;
            DG_ATOMICO_MAS(&g_dg_cola.perdidos);
        }
        memcpy(g_dg_buf + g_dg_n, l, k);
        g_dg_buf[g_dg_n + k] = '\n';
        g_dg_n += k + 1;
    }
    InterlockedExchange(&g_dg_ocupado, 0);
}

/* lo que quedó de la vez anterior (si no es muy viejo) pasa adelante del búfer, y el archivo se borra */
static void dg_spool_levantar(void)
{
    char ruta[MAX_PATH];
    dg_spool_ruta(ruta);
    WIN32_FILE_ATTRIBUTE_DATA fa;
    if (!GetFileAttributesExA(ruta, GetFileExInfoStandard, &fa)) return;
    ULARGE_INTEGER mt;
    mt.LowPart = fa.ftLastWriteTime.dwLowDateTime;
    mt.HighPart = fa.ftLastWriteTime.dwHighDateTime;
    unsigned long long ms = mt.QuadPart / 10000ULL - 11644473600000ULL;
    size_t tam = fa.nFileSizeLow;
    if (!fa.nFileSizeHigh && tam <= DG_BUF / 2 && dg_ahora_utc() - ms < DG_SPOOL_HORAS * 3600000ULL) {
        HANDLE h = CreateFileA(ruta, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, 0, NULL);
        DWORD leidos = 0;
        if (h != INVALID_HANDLE_VALUE) {
            if (ReadFile(h, g_dg_buf, (DWORD)tam, &leidos, NULL)) g_dg_n = leidos;
            CloseHandle(h);
            while (g_dg_n && g_dg_buf[g_dg_n - 1] != '\n') g_dg_n--;   /* (sólo líneas enteras) */
        }
    }
    DeleteFileA(ruta);                               /* (viejo, grande o ya levantado) */
}

static DWORD WINAPI dg_hilo(LPVOID nada)
{
    (void)nada;
    SetThreadPriority(GetCurrentThread(), THREAD_PRIORITY_LOWEST);
    g_dg_buf = (char *)HeapAlloc(GetProcessHeap(), 0, DG_BUF);
    if (!g_dg_buf || !dg_winhttp()) {
        apuntar("  [diag] ⚠ sin WinHTTP: el diagnóstico automático queda apagado");
        g_dg_activo = 0;
        return 0;
    }
    dg_spool_levantar();
    unsigned long lote = 0;
    DWORD espera = 10000, rechazos = 0;
    int pendiente = 0;                               /* el lote `lote` se mandó y no se sabe si llegó */
    long perdidos_dichos = 0;
    for (;;) {
        Sleep(espera);
        dg_juntar();
        long p = g_dg_cola.perdidos;
        if (p != perdidos_dichos) {                  /* (se avisa al servidor cuántos se perdieron) */
            char ex[32];
            wsprintfA(ex, ",\"n\":%ld", p - perdidos_dichos);
            dg_anotar("perdidos", ex);
            perdidos_dichos = p;
        }
        if (!g_dg_n) { espera = 10000; continue; }
        size_t n = dg_cortar_lote(g_dg_buf, g_dg_n);
        if (!n) { g_dg_n = 0; continue; }            /* (no pasa: las líneas son cortas) */
        if (!pendiente) { lote++; pendiente = 1; }
        int r = dg_post(g_dg_buf, n, lote);
        if (r == 200 || r == 409 || r == 413 || r == 400) {   /* llegó (o el server ya lo tenía / no lo quiere): fuera */
            InterlockedExchange(&g_dg_ocupado, 1);
            memmove(g_dg_buf, g_dg_buf + n, g_dg_n - n);
            g_dg_n -= n;
            InterlockedExchange(&g_dg_ocupado, 0);
            pendiente = 0;
            rechazos = 0;
            espera = g_dg_n ? 6000 : 10000;          /* (≤ 12 por minuto, como pide el server) */
        } else if (r == 401 || r == 404) {           /* ticket vencido, reloj, o el server sin EDA_DIAG */
            if (++rechazos >= 5) {
                apuntar("  [diag] el server rechazó 5 veces (%d): el diagnóstico automático se apaga en esta sesión", r);
                g_dg_activo = 0;
                return 0;
            }
            espera = 60000;
        } else {                                     /* sin red, 429, 5xx: cada vez más espaciado (≤ 5 min) */
            espera = espera < 10000 ? 10000 : espera * 2;
            if (espera > 300000) espera = 300000;
        }
    }
}

/* ★ desde preparar_linea: la cuenta y K (el ticket NO se guarda) */
static void dg_credenciales(const char *usuario, int nu, const char *ticket, int nt)
{
    if (nu <= 0 || nu >= (int)sizeof(g_dg_cuenta)) return;
    memcpy(g_dg_cuenta, usuario, nu);
    g_dg_cuenta[nu] = 0;
    dg_clave(ticket, (size_t)nt, g_dg_k);
    g_dg_k_lista = 1;
}

static void dg_leer_ini(const char *ini)
{
    GetPrivateProfileStringA("diag", "url", "", g_dg_url, sizeof(g_dg_url), ini);
    char v[256];
    DWORD n = GetEnvironmentVariableA("EDA_DIAG_URL", v, sizeof(v));
    if (n && n < sizeof(v)) lstrcpyA(g_dg_url, v);
}

/* ★ al final de DllMain: decide si se prende y arranca el hilo (la red, recién en el hilo) */
static void dg_iniciar(const char *carpeta_dll, int entorno)
{
    int https, puerto;
    char host[128], ruta[128];
    if (!g_dg_url[0]) return;
    if (entorno != ENT_TEST) { apuntar("  [diag] apagado: el entorno no es TEST"); return; }
    if (!g_dg_k_lista) { apuntar("  [diag] apagado: el juego no se lanzó con usuario y ticket"); return; }
    if (!dg_url(g_dg_url, &https, host, sizeof(host), &puerto, ruta, sizeof(ruta))) {
        apuntar("  [diag] apagado: la dirección no es https (http sólo a 127.0.0.1)");
        return;
    }
    typedef BOOLEAN (WINAPI *AZAR)(PVOID, ULONG);
    HMODULE a = LoadLibraryA("advapi32.dll");        /* (ya está cargada: no corre código nuevo en DllMain) */
    AZAR azar = a ? (AZAR)GetProcAddress(a, "SystemFunction036") : NULL;   /* RtlGenRandom */
    unsigned char s[16];
    if (!azar || !azar(s, sizeof(s))) { apuntar("  [diag] apagado: sin números al azar para la sesión"); return; }
    dg_hex(s, 16, g_dg_sesion);
    lstrcpynA(g_dg_dir, carpeta_dll, MAX_PATH - 24);
    lstrcatA(g_dg_dir, "diag\\");
    g_dg_t0 = GetTickCount64();
    g_dg_activo = 1;
    char ex[96];
    wsprintfA(ex, ",\"version\":\"%s\",\"build\":\"%s\"", EDA_VERSION, EDA_BUILD);
    dg_anotar("inicio", ex);
    HANDLE h = CreateThread(NULL, 0, dg_hilo, NULL, 0, NULL);
    if (h) CloseHandle(h); else g_dg_activo = 0;
    apuntar("  [diag] diagnóstico automático PRENDIDO → %s (cuenta %s, sesión %.8s…)", host, g_dg_cuenta, g_dg_sesion);
}

/* ★ el cierre normal (DLL_PROCESS_DETACH: los otros hilos ya no corren): «fin» y lo que no llegó, al disco */
static void dg_cerrar(void)
{
    if (!g_dg_activo) return;
    dg_anotar("fin", "");
    if (g_dg_ocupado || !g_dg_buf) {                 /* (el hilo murió a mitad: sólo la cola) */
        char l[DG_LARGO + 1];
        while (dg_cola_sacar(&g_dg_cola, l, DG_LARGO)) { size_t k = strlen(l); l[k] = '\n'; dg_spool_agregar(l, k + 1); }
        return;
    }
    dg_juntar();
    dg_spool_agregar(g_dg_buf, g_dg_n);
}
