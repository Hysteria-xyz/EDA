/* eda_d3d9.c — el d3d9.dll PROPIO de EDA: tope de cuadros + contador de cuadros en pantalla.
 *
 * Va AL LADO de EDA_limpio.exe / EDA.exe. Windows la carga antes que el d3d9 del sistema (el juego
 * la pide por nombre), así que se mete en el medio sin tocar un byte del juego. Reenvía todo al
 * d3d9 de verdad y engancha dos métodos del dispositivo:
 *
 *   · Present (17): ★ el TOPE DE CUADROS. EDA pide PresentationInterval IMMEDIATE y no tiene tope:
 *     dibuja ~900 cuadros/s en la lista de servidores y pone cualquier placa a máxima potencia;
 *     con dos juegos abiertos se pelean la placa y el que pierde cae a ~25 cuadros/s, y como el
 *     juego lee la red UNA vez por cuadro, el ping de la sala sube a ~75 ms (MEDICIONES §40–41).
 *     Con un tope de 120: placa en 48–84 W y ping de sala 8 ms (medido con DXVK). Acá el tope es
 *     NUESTRO (sin Vulkan: anda en cualquier PC con D3D9).
 *     Y, si se pide, dibuja arriba a la izquierda «FPS 120» con rectángulos (como un reloj digital:
 *     sin fuentes ni texturas).
 *   · Reset (16): suelta el «state block» del contador antes de que el juego resetee (si no, Reset
 *     falla), y lo vuelve a crear después.
 *
 * Ajustes: eda_d3d9.ini al lado de la dll —
 *     [video]
 *     tope_fps=120      ; 0 = sin tope
 *     mostrar_fps=1     ; 1 = el contador arriba a la izquierda
 * (las variables EDA_TOPE_FPS / EDA_MOSTRAR_FPS, si están, mandan: sirven para medir).
 * Registro: eda_d3d9.log al lado de la dll.
 *
 * Se compila con `py herramientas\dll_d3d9\compilar.py` (Zig, la misma receta que la de R2Beat).
 */
#include <winsock2.h>
#include <windows.h>
#include <stdio.h>

#define VT(o) (*(void ***)(o))             /* la vtable de un objeto COM */
static void apuntar(const char *fmt, ...);

/* ── el d3d9 de verdad ─────────────────────────────────────────────────── */
typedef void *(WINAPI *CREAR9)(UINT);
static HMODULE g_real;
static CREAR9 g_crear;

/* ── ajustes ───────────────────────────────────────────────────────────── */
static int g_tope = 120;
static int g_mostrar = 1;
/* ★ backbuffer_rapido=1: en el CreateDevice/Reset del juego, sacar LOCKABLE_BACKBUFFER (Flags bit 1) y
 *   pasar SwapEffect COPY (3) → DISCARD (1). Lo mismo que hizo la dll de R2Beat («COPY prohíbe el
 *   camino rápido»). A medir en la SALA, que es donde el juego cae a ~15 cuadros/s. */
static int g_rapido = 0;
/* ★★★ buferes_rapidos=1 (MEDICIONES §42): EL CULPABLE DEL «LAG». En cada dibujo el juego bloquea su
 *   búfer de vértices ENTERO (96.000 B, POOL_DEFAULT, WRITEONLY, FVF 0x142) con Lock(0, 0, …, flags 0):
 *   ~290 veces por cuadro en la sala, y cada una hace esperar al procesador hasta que la placa termine
 *   de usar ese búfer. Con dos juegos las esperas se suman y los dos caen a ~14 cuadros/s.
 *   La salida: crear esos búferes DYNAMIC y convertir cada Lock(0, 0, 0) en Lock(…, DISCARD) — «dame
 *   uno nuevo, lo escribo entero» —: la placa sigue con el anterior sin parar. El juego siempre escribe
 *   desde el principio lo que va a dibujar, así que el dibujo es el mismo. */
static int g_buferes = 1;
static long g_convertidos;

typedef long (WINAPI *M_CVB)(void *, UINT, DWORD, DWORD, DWORD, void **, void *);
typedef long (WINAPI *M_LOCK)(void *, UINT, UINT, void **, DWORD);
typedef long (WINAPI *M_DESC)(void *, void *);
static M_CVB g_cvb_real;
static M_LOCK g_lock_real;
typedef long (WINAPI *M_UNLOCK)(void *);
static M_UNLOCK g_unlock_real;

/* ★★ LA COPIA (11-nov): con DISCARD a secas se rompía la puerta del primer mapa — el juego bloquea el
 *   búfer ENTERO pero reescribe sólo una parte y cuenta con que el resto SIGA ahí; DISCARD lo borra.
 *   Ahora cada búfer «caliente» tiene una COPIA en memoria del procesador: el Lock del juego recibe la
 *   copia (con todo lo que había) y, en el Unlock, la dll pide un búfer nuevo a la placa (DISCARD:
 *   sin esperar) y le vuelca la copia ENTERA. Mismo resultado que el juego espera, sin frenar la placa. */
/* ★★★ EL ANILLO (11-nov, la versión buena). Medido con EDA_MEDIR_ESCRITURA: cada Lock del juego escribe
 *   DESDE EL PRINCIPIO del búfer ~100 B (un cuadradito), y a veces 38 KB de una (el escenario), que después
 *   se dibujan en varias veces entre medio de los cuadraditos. Con DISCARD a secas se perdía lo de 38 KB
 *   (la puerta rota); volcando la copia ENTERA en cada Unlock la placa volvía a 153 W.
 *   Ahora: el juego escribe en la COPIA (memoria del procesador) y la dll sube a la placa SÓLO lo que
 *   cada dibujo usa (el dibujo dice qué vértices), en el próximo lugar libre del búfer (NOOVERWRITE: sin
 *   esperar); cuando se llena, DISCARD y de nuevo desde el principio. Al dibujo se le corre el «vértice
 *   base» para que lea de ahí. Así se sube ~100 B por dibujo, la placa nunca espera y no se pierde nada. */
typedef struct { void *vb; UINT tam; BYTE *copia; int abierto, cargada; UINT anillo; } SOMBRA;

/* (medición, EDA_MEDIR_ESCRITURA=1): qué pedazo del búfer cambia en cada Lock/Unlock */
static int g_medir_escritura;
static BYTE *g_antes;
static UINT g_antes_tam;
static long g_med_n, g_med_desde0, g_med_bytes, g_med_max;
static UINT g_med_ultimo_fin;
static long g_med_siguiente;     /* cuántas veces el pedazo empieza donde terminó el anterior */
static SOMBRA g_sombras[32];

static SOMBRA *sombra_de(void *vb, UINT tam, int crear)
{
    SOMBRA *libre = NULL;
    for (int i = 0; i < 32; i++) {
        if (g_sombras[i].vb == vb) {
            if (g_sombras[i].tam == tam) return &g_sombras[i];
            HeapFree(GetProcessHeap(), 0, g_sombras[i].copia);   /* otro búfer en la misma dirección */
            g_sombras[i].vb = NULL;
        }
        if (!g_sombras[i].vb && !libre) libre = &g_sombras[i];
    }
    if (!crear || !libre) return NULL;
    libre->copia = (BYTE *)HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, tam);
    if (!libre->copia) return NULL;
    libre->vb = vb;
    libre->tam = tam;
    libre->abierto = 0;
    libre->cargada = 0;
    return libre;
}

static long WINAPI mi_lock(void *vb, UINT desde, UINT cuanto, void **datos, DWORD flags)
{
    if (g_buferes) {
        DWORD d[6] = {0};                                        /* D3DVERTEXBUFFER_DESC */
        if (((M_DESC)VT(vb)[13])(vb, d) == 0 && (d[2] & 0x200 /* DYNAMIC */)) {
            if (flags == 0 && desde == 0 && cuanto == 0) {
                SOMBRA *s = sombra_de(vb, d[4], 1);
                if (s && datos) {
                    if (!s->cargada) {
                        /* la 1ª vez, la copia arranca con lo que tiene el búfer */
                        void *p;
                        if (g_lock_real(vb, 0, 0, &p, 0x10 /* READONLY */) == 0) {
                            CopyMemory(s->copia, p, s->tam);
                            g_unlock_real(vb);
                        }
                        s->cargada = 1;
                    }
                    s->abierto = 1;
                    if (g_medir_escritura) {                     /* (foto de la copia antes de escribir) */
                        if (g_antes_tam != s->tam) {
                            g_antes = (BYTE *)HeapAlloc(GetProcessHeap(), 0, s->tam);
                            g_antes_tam = g_antes ? s->tam : 0;
                        }
                        if (g_antes) CopyMemory(g_antes, s->copia, s->tam);
                    }
                    *datos = s->copia;
                    g_convertidos++;
                    return 0;                                    /* D3D_OK: el juego escribe la copia */
                }
            } else {
                /* un Lock parcial sobre un búfer con copia: la placa no tiene la copia entera (sólo lo
                 *   que se fue dibujando): se vuelca toda una vez y se deja de usar la copia */
                SOMBRA *s = sombra_de(vb, d[4], 0);
                if (s && !s->abierto) {
                    void *p;
                    if (g_lock_real(vb, 0, 0, &p, 0x2000 /* DISCARD */) == 0) {
                        CopyMemory(p, s->copia, s->tam);
                        g_unlock_real(vb);
                    }
                    HeapFree(GetProcessHeap(), 0, s->copia);
                    s->vb = NULL;
                }
            }
        }
    }
    return g_lock_real(vb, desde, cuanto, datos, flags);
}

static long WINAPI mi_unlock(void *vb)
{
    for (int i = 0; i < 32; i++) {
        SOMBRA *s = &g_sombras[i];
        if (s->vb == vb && s->abierto) {
            s->abierto = 0;
            if (g_medir_escritura && g_antes && g_antes_tam == s->tam) {
                UINT a = 0, b = s->tam;
                while (a < s->tam && g_antes[a] == s->copia[a]) a++;
                while (b > a && g_antes[b - 1] == s->copia[b - 1]) b--;
                if (b > a) {
                    g_med_n++;
                    g_med_bytes += b - a;
                    if ((long)(b - a) > g_med_max) g_med_max = b - a;
                    if (a < 64) g_med_desde0++;
                    if (a >= g_med_ultimo_fin && a <= g_med_ultimo_fin + 64) g_med_siguiente++;
                    g_med_ultimo_fin = b;
                }
                if (g_med_n && g_med_n % 20000 == 0)
                    apuntar("  escritura: %ld bloqueos · promedio %ld B · máx %ld · empiezan en 0: %ld · siguen al anterior: %ld",
                            g_med_n, g_med_bytes / g_med_n, g_med_max, g_med_desde0, g_med_siguiente);
            }
            return 0;                       /* ★ nada se sube acá: se sube lo que use cada dibujo */
        }
    }
    return g_unlock_real(vb);
}

/* ── los dibujos: subir del anillo lo que usan ─────────────────────────── */
typedef long (WINAPI *M_SSS)(void *, UINT, void *, UINT, UINT);          /* SetStreamSource */
typedef long (WINAPI *M_DP)(void *, DWORD, UINT, UINT);                   /* DrawPrimitive */
typedef long (WINAPI *M_DIP)(void *, DWORD, INT, UINT, UINT, UINT, UINT); /* DrawIndexedPrimitive */
static M_SSS g_sss_real;
static M_DP g_dp_real;
static M_DIP g_dip_real;
static void *g_st_vb;                 /* lo puesto en el stream 0 */
static UINT g_st_desde, g_st_paso;
static long g_subidos, g_subidos_bytes;

static long WINAPI mi_sss(void *dev, UINT n, void *vb, UINT desde, UINT paso)
{
    if (n == 0) {
        g_st_vb = vb;
        g_st_desde = desde;
        g_st_paso = paso;
    }
    return g_sss_real(dev, n, vb, desde, paso);
}

/* sube [lo, lo+largo) de la copia al próximo lugar del anillo; devuelve cuántos VÉRTICES hay que correr
 *   el dibujo, o un número enorme si no se pudo (y entonces se sube TODO como antes) */
#define NO_SE_PUDO 0x7FFFFFFF
static int subir(SOMBRA *s, UINT lo, UINT largo, UINT paso)
{
    if (!paso || lo + largo > s->tam || largo == 0) return NO_SE_PUDO;
    UINT base = ((s->anillo + paso - 1) / paso) * paso;
    UINT p = base + (lo % paso);
    DWORD flags = 0x1000;                                        /* NOOVERWRITE: sin esperar */
    if (p + largo > s->tam) {
        p = lo % paso;                                           /* lleno: de nuevo desde el principio */
        flags = 0x2000;                                          /* DISCARD */
    }
    void *dst;
    if (g_lock_real(s->vb, p, largo, &dst, flags) != 0) return NO_SE_PUDO;
    CopyMemory(dst, s->copia + lo, largo);
    g_unlock_real(s->vb);
    s->anillo = p + largo;
    g_subidos++;
    g_subidos_bytes += largo;
    return (int)((INT)(p - lo) / (INT)paso);
}

static SOMBRA *sombra_puesta(void)
{
    if (!g_st_vb) return NULL;
    for (int i = 0; i < 32; i++)
        if (g_sombras[i].vb == g_st_vb && g_sombras[i].copia) return &g_sombras[i];
    return NULL;
}

static UINT vertices_de(DWORD tipo, UINT prims)
{
    switch (tipo) {
    case 1: return prims;            /* POINTLIST */
    case 2: return prims * 2;        /* LINELIST */
    case 3: return prims + 1;        /* LINESTRIP */
    case 4: return prims * 3;        /* TRIANGLELIST */
    case 5: case 6: return prims + 2;/* TRIANGLESTRIP / FAN */
    default: return 0;
    }
}

static void subir_todo(SOMBRA *s)
{
    void *p;
    if (g_lock_real(s->vb, 0, 0, &p, 0x2000) == 0) {
        CopyMemory(p, s->copia, s->tam);
        g_unlock_real(s->vb);
    }
    s->anillo = s->tam;              /* lo próximo, con DISCARD */
}

static long WINAPI mi_dp(void *dev, DWORD tipo, UINT inicio, UINT prims)
{
    SOMBRA *s = sombra_puesta();
    if (s) {
        UINT n = vertices_de(tipo, prims);
        int corre = subir(s, g_st_desde + inicio * g_st_paso, n * g_st_paso, g_st_paso);
        if (corre != NO_SE_PUDO && (INT)inicio + corre >= 0)
            return g_dp_real(dev, tipo, (UINT)((INT)inicio + corre), prims);
        subir_todo(s);
    }
    return g_dp_real(dev, tipo, inicio, prims);
}

static long WINAPI mi_dip(void *dev, DWORD tipo, INT base, UINT minimo, UINT n, UINT desde_idx, UINT prims)
{
    SOMBRA *s = sombra_puesta();
    if (s) {
        INT primero = base + (INT)minimo;
        if (primero >= 0) {
            int corre = subir(s, g_st_desde + (UINT)primero * g_st_paso, n * g_st_paso, g_st_paso);
            if (corre != NO_SE_PUDO)
                return g_dip_real(dev, tipo, base + corre, minimo, n, desde_idx, prims);
        }
        subir_todo(s);
    }
    return g_dip_real(dev, tipo, base, minimo, n, desde_idx, prims);
}

static void poner(void **vt, int i, void *nuevo, void **viejo);

static long WINAPI mi_crear_vb(void *dev, UINT largo, DWORD uso, DWORD fvf, DWORD pool, void **vb, void *comp)
{
    if (g_buferes && pool == 0 /* DEFAULT */ && !(uso & 0x200)) uso |= 0x200;   /* + DYNAMIC */
    long hr = g_cvb_real(dev, largo, uso, fvf, pool, vb, comp);
    if (hr == 0 && vb && *vb)                                  /* un búfer nuevo no hereda una copia vieja */
        for (int i = 0; i < 32; i++)
            if (g_sombras[i].vb == *vb && !g_sombras[i].abierto) {
                HeapFree(GetProcessHeap(), 0, g_sombras[i].copia);
                g_sombras[i].vb = NULL;
                g_sombras[i].copia = NULL;
            }
    if (hr == 0 && vb && *vb && !g_lock_real) {
        poner(VT(*vb), 12, (void *)mi_unlock, (void **)&g_unlock_real);
        poner(VT(*vb), 11, (void *)mi_lock, (void **)&g_lock_real);
        apuntar("  enganchados VertexBuffer::Lock/Unlock (búferes rápidos: copia + DISCARD)");
    }
    return hr;
}

static void ajustar_pp(void *pp)
{
    if (!g_rapido || !pp) return;
    DWORD *p = (DWORD *)pp;
    p[11] &= ~1u;                       /* +0x2C Flags: sin D3DPRESENTFLAG_LOCKABLE_BACKBUFFER */
    if (p[6] == 3) p[6] = 1;            /* +0x18 SwapEffect: COPY → DISCARD */
}
static char g_log[MAX_PATH];

static void apuntar(const char *fmt, ...)
{
    if (!g_log[0]) return;
    FILE *f = fopen(g_log, "a");
    if (!f) return;
    SYSTEMTIME t;
    GetLocalTime(&t);
    fprintf(f, "%02d:%02d:%02d.%03d  ", t.wHour, t.wMinute, t.wSecond, t.wMilliseconds);
    va_list a;
    va_start(a, fmt);
    vfprintf(f, fmt, a);
    va_end(a);
    fputc('\n', f);
    fclose(f);
}

/* ── los métodos del dispositivo que usamos (índices de IDirect3DDevice9) ── */
typedef long (WINAPI *M_PRESENT)(void *, const RECT *, const RECT *, HWND, const void *);
typedef long (WINAPI *M_RESET)(void *, void *);
typedef long (WINAPI *M_SIN)(void *);                                  /* BeginScene / EndScene */
typedef long (WINAPI *M_RS)(void *, DWORD, DWORD);                     /* SetRenderState, SetFVF… */
typedef long (WINAPI *M_TSS)(void *, DWORD, DWORD, DWORD);             /* SetTextureStageState */
typedef long (WINAPI *M_PTR)(void *, DWORD, void *);                   /* SetTexture */
typedef long (WINAPI *M_UNO)(void *, void *);                          /* SetVertex/PixelShader */
typedef long (WINAPI *M_DPUP)(void *, DWORD, UINT, const void *, UINT);
typedef long (WINAPI *M_CSB)(void *, DWORD, void **);                  /* CreateStateBlock */
typedef long (WINAPI *M_SB)(void *);                                   /* Capture / Apply / Release */
typedef long (WINAPI *M_CREARDEV)(void *, UINT, DWORD, HWND, DWORD, void *, void **);

enum { I_RESET = 16, I_PRESENT = 17, I_BEGINSCENE = 41, I_ENDSCENE = 42, I_SETRS = 57,
       I_CREATESB = 59, I_SETTEXTURE = 65, I_SETTSS = 67, I_DPUP = 83, I_SETFVF = 89,
       I_SETVS = 92, I_SETPS = 107 };

static M_PRESENT g_present_real;
static M_RESET g_reset_real;
static M_CREARDEV g_creardev_real;
static void *g_bloque;          /* el state block del contador (D3DSBT_ALL) */
static void *g_bloque_dev;      /* …y el dispositivo al que pertenece */

/* ── el reloj ──────────────────────────────────────────────────────────── */
static LARGE_INTEGER g_frec, g_proximo, g_ventana;
static int g_cuadros, g_fps;

static double ms_entre(LARGE_INTEGER a, LARGE_INTEGER b)
{
    return (double)(b.QuadPart - a.QuadPart) * 1000.0 / (double)g_frec.QuadPart;
}

/* ★★ LA RED NO ESPERA AL CUADRO (MEDICIONES §42). El juego lee su UDP una vez por vuelta del bucle,
 *   o sea una vez por cuadro: con el tope de 120 cada mensaje esperaba hasta 8 ms (ping de sala 8);
 *   a 480, 2. Eso está mal hecho de fábrica: la latencia no tiene que depender de los cuadros.
 *   El juego registra cada socket con WSAEventSelect(socket, EVENTO, FD_READ…): Windows levanta ese
 *   evento cuando llega algo. La dll se queda con los eventos de los sockets UDP y, en vez de dormir a
 *   ciegas entre cuadro y cuadro, ESPERA ESOS EVENTOS: si llega un mensaje, suelta al juego en el acto
 *   (un cuadro antes de hora) y lo lee enseguida. El tope sigue (la placa descansa) y la red, al toque. */
static int g_red = 1;                       /* [video] red_inmediata */
static int g_estricto = 1;                  /* [video] tope_estricto: los cuadros, FIJOS en el tope */
static HANDLE g_eventos[16];
static int g_neventos;
static long g_despertadas, g_bombeos;
typedef int (WSAAPI *M_WSAES)(SOCKET, WSAEVENT, long);
static M_WSAES g_wsaes_real;

/* ★★ EL BOMBEO DE RED DEL JUEGO (medido 11-nov, MEDICIONES §42): `0x74D530` es el método «actualizar»
 *   del socket UDP (thiscall, this = el objeto del socket, que es GLOBAL: 0x948F90): mira SIN esperar si
 *   el evento del socket (+0xAC) está levantado, y si lo está llama a `0x750110` (WSAEnumNetworkEvents
 *   → leer); después manda lo que tenga en cola. El juego lo llama UNA vez por cuadro, desde el hilo
 *   principal — el mismo del Present. Llamándolo NOSOTROS mientras esperamos el turno del cuadro, el
 *   juego atiende la red al instante SIN dibujar un cuadro de más: el tope queda fijo.
 *   ⚠ Antes de usarlo se verifican sus bytes y que el objeto tenga el socket (+0x88) y el evento
 *   (+0xAC) que el juego registró: con otro exe, no se llama a nada. */
typedef int (__attribute__((thiscall)) *M_BOMBEO)(void *);
static M_BOMBEO g_bombeo;
static void *g_socket_obj;
static HANDLE g_ev_bombeo;
/* ⛔ APAGADO por defecto ([video] bombeo_red=1 para experimentar): medido el 11-nov, apenas el juego
 *   lo usó en la sala (1, después 12 bombeos) LOS DOS JUEGOS SE CONGELARON. Llamar a 0x74D530 desde
 *   adentro del Present traba algo del juego (🟡 ¿un candado que tiene tomado mientras dibuja?). */
static int g_usar_bombeo = 0;
static const BYTE FIRMA_BOMBEO[12] = {0x53, 0x55, 0x8B, 0x2D, 0x74, 0xA1, 0x88, 0x00, 0x56, 0x8B, 0xF1, 0x57};
static const BYTE FIRMA_EVENTO[8] = {0x83, 0xEC, 0x2C, 0x56, 0x8B, 0xF1, 0x8B, 0x8E};

static int legible(const void *p, SIZE_T n)
{
    MEMORY_BASIC_INFORMATION m;
    if (!VirtualQuery(p, &m, sizeof(m)) || m.State != MEM_COMMIT || (m.Protect & (PAGE_NOACCESS | PAGE_GUARD)))
        return 0;
    return (const BYTE *)p + n <= (const BYTE *)m.BaseAddress + m.RegionSize;
}

static void buscar_bombeo(SOCKET s, WSAEVENT ev)
{
    BYTE *bombeo = (BYTE *)0x74D530, *evento = (BYTE *)0x750110, *obj = (BYTE *)0x948F90;
    if (!legible(bombeo, 12) || memcmp(bombeo, FIRMA_BOMBEO, 12) || !legible(evento, 8)
            || memcmp(evento, FIRMA_EVENTO, 8)) {
        apuntar("  ⚠ el bombeo de red no está donde lo esperaba (¿otro exe?): no se usa");
        return;
    }
    if (!legible(obj + 0x88, 0x28) || *(SOCKET *)(obj + 0x88) != s || *(HANDLE *)(obj + 0xAC) != ev) {
        apuntar("  (el socket %u no es el del objeto 0x948F90: no se bombea)", (unsigned)s);
        return;
    }
    g_bombeo = (M_BOMBEO)bombeo;
    g_socket_obj = obj;
    g_ev_bombeo = ev;
    apuntar("  ★ bombeo de red: 0x74D530 con el objeto 0x948F90 (socket %u, evento %p)", (unsigned)s, ev);
}

static int WSAAPI mi_wsa_event_select(SOCKET s, WSAEVENT ev, long que)
{
    int r = g_wsaes_real(s, ev, que);              /* ⚠ primero el real: el objeto ya tiene sus campos */
    int tipo = 0, largo = sizeof(tipo);
    if (ev && (que & FD_READ) && getsockopt(s, SOL_SOCKET, SO_TYPE, (char *)&tipo, &largo) == 0
            && tipo == SOCK_DGRAM) {
        int ya = 0;
        for (int i = 0; i < g_neventos; i++) ya |= g_eventos[i] == ev;
        if (!ya && g_neventos < 16) {
            g_eventos[g_neventos++] = ev;
            apuntar("  red inmediata: el socket UDP %u avisa con el evento %p", (unsigned)s, ev);
            if (!g_bombeo) buscar_bombeo(s, ev);
        }
    }
    return r;
}

/* cambiar UNA entrada de la tabla de importaciones del exe (el juego llama a la nuestra) */
static void *parchear_iat(const char *dll, const char *funcion, void *nueva)
{
    BYTE *base = (BYTE *)GetModuleHandleA(NULL);
    IMAGE_NT_HEADERS *nt = (IMAGE_NT_HEADERS *)(base + ((IMAGE_DOS_HEADER *)base)->e_lfanew);
    IMAGE_DATA_DIRECTORY dir = nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT];
    if (!dir.VirtualAddress) return NULL;
    for (IMAGE_IMPORT_DESCRIPTOR *d = (IMAGE_IMPORT_DESCRIPTOR *)(base + dir.VirtualAddress); d->Name; d++) {
        if (lstrcmpiA((char *)(base + d->Name), dll)) continue;
        IMAGE_THUNK_DATA *nombres = (IMAGE_THUNK_DATA *)(base + (d->OriginalFirstThunk ? d->OriginalFirstThunk : d->FirstThunk));
        IMAGE_THUNK_DATA *real = (IMAGE_THUNK_DATA *)(base + d->FirstThunk);
        for (; nombres->u1.AddressOfData; nombres++, real++) {
            if (IMAGE_SNAP_BY_ORDINAL(nombres->u1.Ordinal)) continue;
            IMAGE_IMPORT_BY_NAME *n = (IMAGE_IMPORT_BY_NAME *)(base + nombres->u1.AddressOfData);
            if (lstrcmpA((char *)n->Name, funcion)) continue;
            DWORD prot;
            if (!VirtualProtect(&real->u1.Function, sizeof(void *), PAGE_READWRITE, &prot)) return NULL;
            void *viejo = (void *)real->u1.Function;
            real->u1.Function = (ULONG_PTR)nueva;
            VirtualProtect(&real->u1.Function, sizeof(void *), prot, &prot);
            return viejo;
        }
    }
    return NULL;
}

/* ── ★ EL SERVER, SIN PYTHON (12-nov) ──────────────────────────────────────
 * El cliente se conecta al Broker de 2009 (218.145.66.187:25000, de un XML de Data.dat), y el server
 * de juego que le da la lista apunta al MISMO lugar (herramientas/reglas_broker.py). Hasta acá eso lo
 * desviaba Frida (redirigir_cliente.py / eda_original.py). Ahora lo hace la DLL: el exe pide
 * `connect` por NOMBRE (EDA_limpio.exe, 2º descriptor de WS2_32), así que alcanza con su entrada de
 * la tabla de importaciones. Adónde: [red] server=host[:puerto] del ini (o EDA_SERVER, que manda);
 * vacío = no se desvía nada (el juego como antes). Sólo ESE destino: cualquier otro pasa igual. */
typedef int (WSAAPI *M_CONNECT)(SOCKET, const struct sockaddr *, int);
static M_CONNECT g_connect_real;
static char g_server[256];
static struct sockaddr_in g_destino;
static int g_destino_listo;
static long g_desviados;
static const BYTE BROKER_IP[4] = {218, 145, 66, 187};
#define BROKER_PUERTO 25000

static int resolver_server(void)
{
    if (g_destino_listo) return 1;
    char host[256];
    lstrcpynA(host, g_server, sizeof(host));
    int puerto = 25900;
    char *dp = strrchr(host, ':');
    if (dp) { *dp = 0; puerto = atoi(dp + 1); }
    unsigned long ip = inet_addr(host);
    if (ip == INADDR_NONE) {                         /* un nombre (un dominio): se resuelve acá */
        struct hostent *h = gethostbyname(host);
        if (h && h->h_addrtype == AF_INET && h->h_addr_list[0]) memcpy(&ip, h->h_addr_list[0], 4);
    }
    if (ip == INADDR_NONE || puerto <= 0 || puerto > 65535) {
        apuntar("  ⛔ server: no pude resolver «%s» (el juego va a 218.145.66.187, que no existe)", g_server);
        return 0;                                    /* sin guardar: el próximo connect reintenta */
    }
    memset(&g_destino, 0, sizeof(g_destino));
    g_destino.sin_family = AF_INET;
    g_destino.sin_port = htons((u_short)puerto);
    g_destino.sin_addr.s_addr = ip;
    g_destino_listo = 1;
    return 1;
}

/* ¿es el connect al Broker de 2009? (sólo IPv4, IP y puerto exactos) */
static int es_broker(const struct sockaddr *sa, int largo)
{
    const struct sockaddr_in *in = (const struct sockaddr_in *)sa;
    return sa && largo >= (int)sizeof(*in) && in->sin_family == AF_INET
        && ntohs(in->sin_port) == BROKER_PUERTO && !memcmp(&in->sin_addr, BROKER_IP, 4);
}

static int WSAAPI mi_connect(SOCKET s, const struct sockaddr *sa, int largo)
{
    if (es_broker(sa, largo) && resolver_server()) {
        struct sockaddr_in nuevo = *(const struct sockaddr_in *)sa;   /* ⚠ una copia: el del juego no se toca */
        nuevo.sin_port = g_destino.sin_port;
        nuevo.sin_addr = g_destino.sin_addr;
        g_desviados++;
        apuntar("  server: connect a 218.145.66.187:25000 → %s:%u (%ld)", inet_ntoa(nuevo.sin_addr),
                (unsigned)ntohs(nuevo.sin_port), g_desviados);
        return g_connect_real(s, (const struct sockaddr *)&nuevo, sizeof(nuevo));
    }
    return g_connect_real(s, sa, largo);
}

/* ★ las TRAMPAS del desempacado (sin Frida): una llamada que no se pudo resolver salta a
 *   0xD0000000 + sitio − 0x400000 y el juego se cae. Queda anotado QUÉ sitio en eda_d3d9.log, para
 *   que un jugador lo pueda mandar (documentacion/APIS_A_MANO.md). No cambia nada: sigue la caída. */
static LONG WINAPI mi_excepcion(EXCEPTION_POINTERS *e)
{
    DWORD eip = (DWORD)(ULONG_PTR)e->ExceptionRecord->ExceptionAddress;
    if (eip >= 0xD0000000u && eip < 0xD0600000u)
        apuntar("⛔ el juego llegó a una llamada de Windows SIN RESOLVER: sitio 0x%lX (abrí un issue con "
                "este número)", (unsigned long)(eip - 0xD0000000u + 0x400000u));
    return EXCEPTION_CONTINUE_SEARCH;
}

/* ★ esperar hasta el próximo cuadro. Sin eventos de red: Sleep mientras falte más de ~2 ms (con
 *   timeBeginPeriod(1), Sleep(1) ≈ 1 ms) y girar el último tramo. CON eventos: esperarlos con el tiempo
 *   que falta como plazo; si llega un mensaje, soltar YA (sin correr la grilla de los cuadros). */
static LARGE_INTEGER g_ultimo;
static void esperar_tope(void)
{
    if (g_tope <= 0) return;
    LARGE_INTEGER ahora;
    QueryPerformanceCounter(&ahora);
    LONGLONG paso = g_frec.QuadPart / g_tope;
    if (g_proximo.QuadPart == 0 || ahora.QuadPart - g_proximo.QuadPart > paso) {
        g_proximo.QuadPart = ahora.QuadPart + paso;      /* atrasados (o el 1er cuadro): no recuperar */
        g_ultimo = ahora;
        return;
    }
    for (;;) {
        QueryPerformanceCounter(&ahora);
        double falta = ms_entre(ahora, g_proximo);
        if (falta <= 0) break;
        /* ★★ con el bombeo: esperar el evento de red con el tiempo que falta; si llega algo, el JUEGO lo
         *   atiende (0x74D530) y seguimos esperando el turno: los cuadros quedan fijos en el tope */
        if (g_red && g_bombeo && g_usar_bombeo && falta > 0.3) {
            DWORD plazo = falta > 1.5 ? (DWORD)(falta - 1.0) : 0;
            if (WaitForSingleObject(g_ev_bombeo, plazo) == WAIT_OBJECT_0) {
                g_bombeo(g_socket_obj);
                g_bombeos++;
            } else if (plazo == 0) {
                YieldProcessor();
            }
            continue;
        }
        if (g_red && g_neventos && falta > 0.5) {
            /* ⚠ un piso de 1 ms entre cuadros: si un evento quedara levantado (el juego no lo leyó),
             *   no se dispara a miles de cuadros por segundo */
            if (ms_entre(g_ultimo, ahora) >= 1.0
                    && WaitForMultipleObjects(g_neventos, g_eventos, FALSE, falta > 2.0 ? (DWORD)(falta - 1.0) : 0)
                       < WAIT_OBJECT_0 + (DWORD)g_neventos) {
                g_despertadas++;
                QueryPerformanceCounter(&g_ultimo);
                /* ★ con tope ESTRICTO el cuadro adelantado «gasta» el turno: el próximo va un paso
                 *   más allá, así el promedio queda EXACTO en el tope (nunca hay cuadros de más) */
                if (g_estricto) g_proximo.QuadPart += paso;
                return;                                   /* ★ llegó algo: el juego lo lee ya */
            }
            if (falta > 2.0 && ms_entre(g_ultimo, ahora) < 1.0) Sleep(1);
            else if (falta <= 2.0) YieldProcessor();
            continue;
        }
        if (falta > 2.0) Sleep(1);
        else YieldProcessor();
    }
    g_proximo.QuadPart += paso;
    QueryPerformanceCounter(&g_ultimo);
}

/* ── el contador: «FPS 120» con segmentos ─────────────────────────────── */
typedef struct { float x, y, z, rhw; DWORD color; } VERTICE;
static VERTICE g_v[600];
static int g_nv;

static void rect(float x, float y, float w, float h, DWORD c)
{
    if (g_nv + 6 > (int)(sizeof(g_v) / sizeof(g_v[0]))) return;
    VERTICE q[4] = {{x, y, 0, 1, c}, {x + w, y, 0, 1, c}, {x, y + h, 0, 1, c}, {x + w, y + h, 0, 1, c}};
    int orden[6] = {0, 1, 2, 2, 1, 3};
    for (int i = 0; i < 6; i++) g_v[g_nv++] = q[orden[i]];
}

/* segmentos a..g: bit 0 = a (arriba) … bit 6 = g (medio) */
static const unsigned char SEG_DIGITO[10] = {0x3F, 0x06, 0x5B, 0x4F, 0x66, 0x6D, 0x7D, 0x07, 0x7F, 0x6F};
enum { SEG_F = 0x71, SEG_P = 0x73, SEG_S = 0x6D };

static void segmentos(float x, float y, unsigned char m, DWORD c)
{
    const float w = 9, h = 16, t = 2;
    if (m & 0x01) rect(x, y, w, t, c);                        /* a */
    if (m & 0x02) rect(x + w - t, y, t, h / 2, c);            /* b */
    if (m & 0x04) rect(x + w - t, y + h / 2, t, h / 2, c);    /* c */
    if (m & 0x08) rect(x, y + h - t, w, t, c);                /* d */
    if (m & 0x10) rect(x, y + h / 2, t, h / 2, c);            /* e */
    if (m & 0x20) rect(x, y, t, h / 2, c);                    /* f */
    if (m & 0x40) rect(x, y + h / 2 - t / 2, w, t, c);        /* g */
}

static void dibujar_contador(void *dev)
{
    void **vt = VT(dev);
    char num[12];
    int n = sprintf(num, "%d", g_fps);
    g_nv = 0;
    float x0 = 6, y0 = 6, paso = 13;
    rect(x0 - 4, y0 - 4, paso * (4 + n) + 6, 24, 0xFF000000);  /* el fondo negro */
    DWORD verde = g_tope > 0 && g_fps > g_tope + 5 ? 0xFFFF6040 : 0xFF40FF60;
    segmentos(x0, y0, SEG_F, verde);
    segmentos(x0 + paso, y0, SEG_P, verde);
    segmentos(x0 + 2 * paso, y0, SEG_S, verde);
    for (int i = 0; i < n; i++) segmentos(x0 + (4 + i) * paso, y0, SEG_DIGITO[num[i] - '0'], 0xFFFFFFFF);

    /* ⚠ el state block es DEL DISPOSITIVO que lo creó: el juego crea OTRO al entrar a la partida, y
     *   aplicarle el del viejo le ponía estados ajenos (glitches) y el contador desaparecía (11-nov).
     *   El del dispositivo viejo se abandona sin tocarlo (ese dispositivo ya puede no existir). */
    if (g_bloque && g_bloque_dev != dev) g_bloque = NULL;
    if (!g_bloque && ((M_CSB)vt[I_CREATESB])(dev, 1 /* D3DSBT_ALL */, &g_bloque) != 0) g_bloque = NULL;
    g_bloque_dev = dev;
    if (g_bloque) ((M_SB)VT(g_bloque)[4])(g_bloque);            /* Capture */
    ((M_SIN)vt[I_BEGINSCENE])(dev);
    ((M_UNO)vt[I_SETVS])(dev, NULL);
    ((M_UNO)vt[I_SETPS])(dev, NULL);
    ((M_PTR)vt[I_SETTEXTURE])(dev, 0, NULL);
    ((M_RS)vt[I_SETFVF])(dev, 0x044, 0);                         /* XYZRHW | DIFFUSE */
    static const DWORD estados[][2] = {{7, 0} /* ZENABLE */, {14, 0} /* ZWRITE */, {15, 0} /* ALPHATEST */,
        {27, 0} /* ALPHABLEND */, {22, 1} /* CULL NONE */, {137, 0} /* LIGHTING */, {28, 0} /* FOG */,
        {52, 0} /* STENCIL */, {174, 0} /* SCISSOR */, {168, 0xF} /* COLORWRITE */, {8, 3} /* SOLID */};
    for (unsigned i = 0; i < sizeof(estados) / sizeof(estados[0]); i++)
        ((M_RS)vt[I_SETRS])(dev, estados[i][0], estados[i][1]);
    ((M_TSS)vt[I_SETTSS])(dev, 0, 1, 2);        /* COLOROP = SELECTARG1 */
    ((M_TSS)vt[I_SETTSS])(dev, 0, 2, 0);        /* COLORARG1 = DIFFUSE */
    ((M_TSS)vt[I_SETTSS])(dev, 0, 4, 2);        /* ALPHAOP = SELECTARG1 */
    ((M_TSS)vt[I_SETTSS])(dev, 0, 5, 0);        /* ALPHAARG1 = DIFFUSE */
    ((M_TSS)vt[I_SETTSS])(dev, 1, 1, 1);        /* etapa 1: DISABLE */
    ((M_DPUP)vt[I_DPUP])(dev, 4 /* TRIANGLELIST */, g_nv / 3, g_v, sizeof(VERTICE));
    ((M_SIN)vt[I_ENDSCENE])(dev);
    if (g_bloque) ((M_SB)VT(g_bloque)[5])(g_bloque);            /* Apply: todo como estaba */
}

/* ── los ganchos ───────────────────────────────────────────────────────── */
static long WINAPI mi_present(void *dev, const RECT *a, const RECT *b, HWND w, const void *r)
{
    LARGE_INTEGER ahora;
    QueryPerformanceCounter(&ahora);
    g_cuadros++;
    if (g_ventana.QuadPart == 0) g_ventana = ahora;
    double ms = ms_entre(g_ventana, ahora);
    if (ms >= 500) {
        static int ventanas;
        g_fps = (int)(g_cuadros * 1000.0 / ms + 0.5);
        g_cuadros = 0;
        g_ventana = ahora;
        if (++ventanas % 60 == 0)                                   /* cada ~30 s */
        {
            apuntar("  %d cuadros/s · despertadas %ld · bloqueos a la copia %ld · subidas al anillo %ld (%ld B en promedio)",
                    g_fps, g_despertadas, g_convertidos, g_subidos, g_subidos ? g_subidos_bytes / g_subidos : 0);
            if (g_medir_escritura)
                apuntar("  escritura: %ld de %ld bloqueos CAMBIAN algo · promedio %ld B · máx %ld · empiezan en 0: %ld · siguen al anterior: %ld",
                        g_med_n, g_convertidos, g_med_n ? g_med_bytes / g_med_n : 0, g_med_max, g_med_desde0, g_med_siguiente);
        }
    }
    if (g_mostrar) dibujar_contador(dev);
    long hr = g_present_real(dev, a, b, w, r);
    esperar_tope();
    return hr;
}

static long WINAPI mi_reset(void *dev, void *pp)
{
    if (g_bloque) {
        if (g_bloque_dev == dev)
            ((M_SB)VT(g_bloque)[2])(g_bloque);                     /* Release (si no, Reset falla) */
        g_bloque = NULL;                                          /* (el de otro dispositivo: ni tocarlo) */
    }
    ajustar_pp(pp);
    long hr = g_reset_real(dev, pp);
    apuntar("Reset -> 0x%08lx", (unsigned long)hr);
    return hr;
}

static void poner(void **vt, int i, void *nuevo, void **viejo)
{
    if (vt[i] == nuevo) return;
    DWORD prot;
    if (!VirtualProtect(&vt[i], sizeof(void *), PAGE_EXECUTE_READWRITE, &prot)) return;
    *viejo = vt[i];
    vt[i] = nuevo;
    VirtualProtect(&vt[i], sizeof(void *), prot, &prot);
}

static long WINAPI mi_crear_dispositivo(void *d3d, UINT adaptador, DWORD tipo, HWND foco, DWORD flags,
                                        void *pp, void **dev)
{
    ajustar_pp(pp);
    long hr = g_creardev_real(d3d, adaptador, tipo, foco, flags, pp, dev);
    apuntar("CreateDevice(adaptador %u, flags 0x%lx, swap %lu, pflags 0x%lx, intervalo 0x%lx) -> 0x%08lx",
            adaptador, (unsigned long)flags, (unsigned long)((DWORD *)pp)[6], (unsigned long)((DWORD *)pp)[11],
            (unsigned long)((DWORD *)pp)[13], (unsigned long)hr);
    if (hr == 0 && dev && *dev) {
        void **vt = VT(*dev);
        poner(vt, I_PRESENT, (void *)mi_present, (void **)&g_present_real);
        poner(vt, I_RESET, (void *)mi_reset, (void **)&g_reset_real);
        if (g_buferes) {
            poner(vt, 26 /* CreateVertexBuffer */, (void *)mi_crear_vb, (void **)&g_cvb_real);
            poner(vt, 100 /* SetStreamSource */, (void *)mi_sss, (void **)&g_sss_real);
            poner(vt, 81 /* DrawPrimitive */, (void *)mi_dp, (void **)&g_dp_real);
            poner(vt, 82 /* DrawIndexedPrimitive */, (void *)mi_dip, (void **)&g_dip_real);
        }
        apuntar("  enganchados Present y Reset · tope %d cuadros/s · contador %s · búferes rápidos %s",
                g_tope, g_mostrar ? "sí" : "no", g_buferes ? "sí" : "no");
    }
    return hr;
}

__declspec(dllexport) void *WINAPI Direct3DCreate9(UINT version)
{
    void *fabrica = g_crear ? g_crear(version) : NULL;
    apuntar("Direct3DCreate9(%u) -> %s", version, fabrica ? "ok" : "NULO");
    if (fabrica) poner(VT(fabrica), 16, (void *)mi_crear_dispositivo, (void **)&g_creardev_real);
    return fabrica;
}

/* ── al cargar ─────────────────────────────────────────────────────────── */
static void leer_ajustes(HMODULE self)
{
    char ruta[MAX_PATH], ini[MAX_PATH], v[32];
    if (!GetModuleFileNameA(self, ruta, MAX_PATH)) return;
    char *barra = strrchr(ruta, '\\');
    if (!barra) return;
    barra[1] = 0;
    lstrcpyA(ini, ruta);
    lstrcatA(ini, "eda_d3d9.ini");
    lstrcpyA(g_log, ruta);
    lstrcatA(g_log, "eda_d3d9.log");
    g_tope = GetPrivateProfileIntA("video", "tope_fps", 120, ini);
    g_mostrar = GetPrivateProfileIntA("video", "mostrar_fps", 1, ini);
    if (GetEnvironmentVariableA("EDA_TOPE_FPS", v, sizeof(v))) g_tope = atoi(v);
    if (GetEnvironmentVariableA("EDA_MOSTRAR_FPS", v, sizeof(v))) g_mostrar = atoi(v);
    if (GetEnvironmentVariableA("EDA_MEDIR_ESCRITURA", v, sizeof(v))) g_medir_escritura = atoi(v);
    g_usar_bombeo = GetPrivateProfileIntA("video", "bombeo_red", 0, ini);
    if (GetEnvironmentVariableA("EDA_BOMBEO_RED", v, sizeof(v))) g_usar_bombeo = atoi(v);
    g_estricto = GetPrivateProfileIntA("video", "tope_estricto", 1, ini);
    if (GetEnvironmentVariableA("EDA_TOPE_ESTRICTO", v, sizeof(v))) g_estricto = atoi(v);
    g_red = GetPrivateProfileIntA("video", "red_inmediata", 1, ini);
    if (GetEnvironmentVariableA("EDA_RED_INMEDIATA", v, sizeof(v))) g_red = atoi(v);
    g_buferes = GetPrivateProfileIntA("video", "buferes_rapidos", 1, ini);
    if (GetEnvironmentVariableA("EDA_BUFERES_RAPIDOS", v, sizeof(v))) g_buferes = atoi(v);
    g_rapido = GetPrivateProfileIntA("video", "backbuffer_rapido", 0, ini);
    if (GetEnvironmentVariableA("EDA_BACKBUFFER_RAPIDO", v, sizeof(v))) g_rapido = atoi(v);
    if (g_tope < 0) g_tope = 0;
    GetPrivateProfileStringA("red", "server", "", g_server, sizeof(g_server), ini);
    char env[256];                                   /* ⚠ un dominio no entra en los 32 de `v` */
    DWORD n = GetEnvironmentVariableA("EDA_SERVER", env, sizeof(env));
    if (n && n < sizeof(env)) lstrcpyA(g_server, env);
}

BOOL WINAPI DllMain(HINSTANCE self, DWORD razon, LPVOID reservado)
{
    (void)reservado;
    if (razon != DLL_PROCESS_ATTACH) return TRUE;
    DisableThreadLibraryCalls(self);
    /* ⚠ el d3d9 DE VERDAD por ruta absoluta: con "d3d9.dll" a secas Windows encontraría ESTA misma.
     *   En 32 bits sobre Windows de 64, GetSystemDirectory ya devuelve SysWOW64 (el correcto). */
    char sys[MAX_PATH];
    UINT n = GetSystemDirectoryA(sys, MAX_PATH);
    if (!n || n > MAX_PATH - 16) return FALSE;
    lstrcatA(sys, "\\d3d9.dll");
    g_real = LoadLibraryA(sys);
    if (!g_real) return FALSE;
    g_crear = (CREAR9)GetProcAddress(g_real, "Direct3DCreate9");
    if (!g_crear) return FALSE;
    leer_ajustes((HMODULE)self);
    QueryPerformanceFrequency(&g_frec);
    timeBeginPeriod(1);                                          /* Sleep(1) ≈ 1 ms */
    apuntar("eda_d3d9 cargada · el d3d9 real: %s · tope %d · contador %d", sys, g_tope, g_mostrar);
    /* ★ la red inmediata: desde YA (el juego puede abrir su socket UDP antes de crear el D3D). Acá
     *   la tabla de importaciones del exe ya está resuelta (los DllMain corren después). */
    if (g_red && g_tope > 0) {
        g_wsaes_real = (M_WSAES)parchear_iat("WS2_32.dll", "WSAEventSelect", (void *)mi_wsa_event_select);
        apuntar("  red inmediata: %s", g_wsaes_real ? "WSAEventSelect enganchado" : "⚠ no encontré WSAEventSelect en el exe");
    }
    if (g_server[0]) {
        g_connect_real = (M_CONNECT)parchear_iat("WS2_32.dll", "connect", (void *)mi_connect);
        apuntar("  server: %s → %s", g_server, g_connect_real ? "connect enganchado"
                : "⛔ no encontré connect en el exe (¿el EDA.exe con ASProtect? ese va con jugar.py)");
    }
    AddVectoredExceptionHandler(0, mi_excepcion);
    return TRUE;
}
