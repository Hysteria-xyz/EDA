/* eda_apis.c — ★ (21-nov) LAS LLAMADAS A WINDOWS QUE EL EXE TODAVÍA TIENE «SIN RESOLVER», reparadas en memoria.
 *
 * Qué pasa: `EDA_limpio.exe` es el EDA.exe de 2009 sin ASProtect. ASProtect había cambiado cada `call [IAT]` (6 bytes:
 * FF 15 + la dirección de la entrada de la tabla) por un `call` de 5 bytes a su propio código + 1 byte de relleno. Al
 * desempacar, los sitios cuya API no se pudo medir quedaron como TRAMPA: `E8` con destino 0xD0000000 + sitio − 0x400000
 * (herramientas/desempacar.py, BASE_TRAMPA). Si el juego llega a uno, salta a una dirección que no existe y se cae.
 *
 * Medido (21-nov, server de prueba, partida de dos, 14:20:27): EDA_limpio.rpt con EIP = 0xD03F4626 = la trampa del
 * sitio 0x7F4626, y la caja negra «llamada de Windows SIN RESOLVER: sitio 0x7F4626». Ese sitio es `IsValidLocale`
 * (documentacion/APIS_A_MANO.md, gemela 18/18 en msvcr71.dll): `setlocale` (0x7E545B) → 0x7E4E97 → 0x7F4508
 * (__get_qualified_locale) → 0x7F4610 `IsValidCodePage` (resuelta) → 0x7F4626 `IsValidLocale(lcid, 1)` (trampa). Al
 * juego se llega por un `std::locale("korean")` (0x5CB8E2 / 0x5CBC92 → 0x7905D0) que arma un cargador en plena stage.
 *
 * Qué hace esto: al cargar la dll (DllMain: el exe todavía no corrió nada suyo), para cada sitio de la lista,
 *   1. comprueba que el exe sea el EDA_limpio.exe conocido (base 0x400000, sello y tamaño del PE);
 *   2. comprueba que en el sitio esté EXACTAMENTE la trampa (E8 + el desplazamiento a 0xD0000000 + sitio − 0x400000);
 *   3. pone la instrucción original de 6 bytes, `call dword ptr [p]`, donde `p` es un puntero de ESTA dll a la función
 *      de verdad de Windows (GetProcAddress). La API se comporta como siempre: no se fuerza ningún resultado.
 * Si algo no coincide (otro exe, el EDA.exe con ASProtect, un sitio ya reparado), ese sitio no se toca y se anota.
 *
 * La lista: SÓLO sitios de la CRT de VC 7.1 que ya están en APIS_A_MANO.md con su prueba de «gemela» en msvcr71.dll
 * (17 o 18 de 18 instrucciones iguales), todos de KERNEL32 (siempre cargada), y en los que lo que sigue al lugar de 6
 * bytes usa el resultado (test eax,eax / mov …,eax): medido con herramientas/dll_d3d9/prueba_apis.py. Los otros ~95
 * sitios ya medidos (juego, red, protección, registro) quedan para cuando cada uno tenga su prueba en el juego.
 *
 * [apis] reparar=0 en eda_d3d9.ini lo apaga (EDA_REPARAR_APIS=0 también). [apis] probar_locale=1 (o
 * EDA_PROBAR_LOCALE=1): en el primer cuadro, la dll llama ella misma al `setlocale` del juego con «korean» y lo vuelve
 * a dejar como estaba (lo mismo que hace `std::locale`): reproduce el camino de la caída sin jugar una stage. */

#ifndef EDA_APIS_SOLO_DATOS
#define EDA_APIS_SOLO_DATOS 0
#endif

typedef struct { unsigned long sitio; const char *fn; } API_SITIO;
/* (todas de KERNEL32; el comentario dice dónde está en la CRT de VC 7.1) */
static const API_SITIO API_SITIOS[] = {
    {0x7F4626, "IsValidLocale"},           /* __get_qualified_locale (setlocale): ★ LA CAÍDA del 21-nov */
    {0x7E1B32, "GetCPInfo"},               /* __init_ctype (setlocale LC_CTYPE) */
    {0x7F20B5, "GetStringTypeA"},          /* __crtGetStringTypeA (__init_ctype) */
    {0x7E48E6, "LCMapStringA"},            /* __crtLCMapStringA (locale) */
    {0x7F46E5, "IsBadWritePtr"},           /* _ValidateWrite (excepciones de C++: un std::locale que falla tira una) */
    {0x7E9D94, "IsBadWritePtr"},           /* manejo de excepciones de la CRT */
    {0x7E9DCE, "IsBadWritePtr"},
    {0x7E9E2E, "IsBadWritePtr"},
    {0x7E83A0, "GetCurrentProcess"},
    {0x7E8DCC, "GetCurrentThreadId"},
    {0x7E3811, "GetFullPathNameA"},        /* _fullpath */
    {0x7EBFB5, "GetFileType"},             /* _ioinit / fopen */
    {0x7F68F7, "GetFileType"},
    {0x7EE4A9, "FlushFileBuffers"},        /* _commit (fflush de un archivo) */
    {0x7F29EA, "GetModuleFileNameA"},      /* _NMSG_WRITE (el cartel de error de la CRT) */
    {0x7F5923, "CreatePipe"},              /* _pipe */
    {0x7F7BD1, "SetEnvironmentVariableA"}, /* _putenv */
};
#define API_N (int)(sizeof(API_SITIOS) / sizeof(API_SITIOS[0]))
/* el EDA_limpio.exe conocido (md5 0799387e…): su PE */
#define API_EXE_BASE 0x00400000u
#define API_EXE_SELLO 0x4A858317u
#define API_EXE_TAMANO 0x005DB000u

/* ¿en `p` (los bytes del sitio) está la trampa de ESE sitio? E8 + rel32 hacia 0xD0000000 + sitio − 0x400000 */
static int api_es_trampa(const unsigned char *p, unsigned long sitio)
{
    unsigned long dest = 0xD0000000ul + sitio - 0x400000ul;
    unsigned long rel = (dest - (sitio + 5)) & 0xFFFFFFFFul;
    return p[0] == 0xE8 && p[1] == (rel & 0xFF) && p[2] == ((rel >> 8) & 0xFF) && p[3] == ((rel >> 16) & 0xFF)
           && p[4] == ((rel >> 24) & 0xFF);
}

/* los 6 bytes originales: `call dword ptr [puntero]` = FF 15 + la dirección (32 bits) del puntero */
static void api_instruccion(unsigned char out[6], unsigned long puntero)
{
    out[0] = 0xFF;
    out[1] = 0x15;
    out[2] = puntero & 0xFF;
    out[3] = (puntero >> 8) & 0xFF;
    out[4] = (puntero >> 16) & 0xFF;
    out[5] = (puntero >> 24) & 0xFF;
}

#if !EDA_APIS_SOLO_DATOS
static int g_apis = 1, g_apis_probar, g_apis_reparadas;
static void *g_api_ptr[API_N];                       /* el puntero de cada sitio: lo lee el `call [ptr]` del juego */
static volatile LONG g_apis_probado;

static int api_exe_conocido(void)
{
    BYTE *b = (BYTE *)GetModuleHandleA(NULL);
    if ((ULONG_PTR)b != API_EXE_BASE || !legible(b, 0x40)) return 0;
    IMAGE_NT_HEADERS32 *nt = (IMAGE_NT_HEADERS32 *)(b + ((IMAGE_DOS_HEADER *)b)->e_lfanew);
    if (!legible(nt, sizeof(*nt))) return 0;
    return nt->FileHeader.TimeDateStamp == API_EXE_SELLO && nt->OptionalHeader.SizeOfImage == API_EXE_TAMANO;
}

static void reparar_apis(void)
{
    if (!g_apis) { apuntar("  [apis] reparar=0: las llamadas sin resolver del exe quedan como están"); return; }
    if (!api_exe_conocido()) {
        apuntar("  [apis] no es el EDA_limpio.exe conocido (sello/tamaño del PE distintos): no se toca nada");
        return;
    }
    HMODULE k32 = GetModuleHandleA("kernel32.dll");
    int hechas = 0, ya = 0, otras = 0;
    char cuales[512];
    cuales[0] = 0;
    for (int i = 0; i < API_N; i++) {
        BYTE *p = (BYTE *)(ULONG_PTR)API_SITIOS[i].sitio;
        void *f = k32 ? (void *)GetProcAddress(k32, API_SITIOS[i].fn) : NULL;
        if (!legible(p, 6) || !f) { otras++; continue; }
        if (p[0] == 0xFF && p[1] == 0x15) { ya++; continue; }          /* (ya tiene su llamada: no se toca) */
        if (!api_es_trampa(p, API_SITIOS[i].sitio)) {
            otras++;
            apuntar("  [apis] ⚠ 0x%lX (%s): no está la trampa esperada: no se toca", API_SITIOS[i].sitio, API_SITIOS[i].fn);
            continue;
        }
        g_api_ptr[i] = f;
        BYTE nuevo[6];
        DWORD prot;
        api_instruccion(nuevo, (unsigned long)(ULONG_PTR)&g_api_ptr[i]);
        if (!VirtualProtect(p, 6, PAGE_EXECUTE_READWRITE, &prot)) { otras++; continue; }
        memcpy(p, nuevo, 6);
        VirtualProtect(p, 6, prot, &prot);
        FlushInstructionCache(GetCurrentProcess(), p, 6);
        hechas++;
        if (lstrlenA(cuales) < 440) wsprintfA(cuales + lstrlenA(cuales), "%s0x%lX %s", hechas > 1 ? " · " : "",
                                               API_SITIOS[i].sitio, API_SITIOS[i].fn);
    }
    g_apis_reparadas = hechas;
    apuntar("  [apis] %d llamadas sin resolver del exe reparadas (%s)%s%s", hechas, cuales[0] ? cuales : "ninguna",
            ya ? " · ya estaban bien: " : "", ya ? "sí" : "");
    if (otras) apuntar("  [apis] ⚠ %d sitio(s) de la lista no se tocaron (ver arriba)", otras);
}

/* ★ la prueba de la caída SIN jugar: el `setlocale` del juego (CRT de VC 7.1, 0x7E545B, cdecl) con «korean», y de vuelta
 *   a como estaba. Es lo que hace std::locale("korean") (_Locinfo guarda el viejo, pone el nuevo y lo restituye). Corre
 *   UNA vez, en el hilo del juego (desde el Present), sólo con [apis] probar_locale=1. Sin la reparación, el juego se
 *   cae acá mismo (la caja negra lo dice): eso es lo que se quiere ver. */
typedef char *(__cdecl *M_SETLOCALE)(int, const char *);
static void apis_probar_locale(void)
{
    if (!g_apis_probar || InterlockedExchange(&g_apis_probado, 1)) return;
    M_SETLOCALE sl = (M_SETLOCALE)(ULONG_PTR)0x7E545B;
    if (!api_exe_conocido() || !firma(0x7E545B, "6a 14 68 28 b3 8b 00")) {
        apuntar("  [apis] prueba de locale: no es el exe conocido: no se prueba");
        return;
    }
    char antes[256];
    const char *v = sl(0, NULL);                     /* LC_ALL = 0: cuál está */
    lstrcpynA(antes, v ? v : "C", sizeof(antes));
    apuntar("  [apis] prueba de locale: antes «%s» · llamando setlocale(LC_ALL, \"korean\") (camino de la caída del 21-nov)…", antes);
    const char *r = sl(0, "korean");
    char nuevo[256];
    lstrcpynA(nuevo, r ? r : "(NULL: Windows dice que no es válido)", sizeof(nuevo));
    const char *vuelta = sl(0, antes);
    apuntar("  [apis] prueba de locale: ✅ volvió sin caerse · «korean» → «%s» · restituido «%s»", nuevo,
            vuelta ? vuelta : "(NULL)");
}
#endif
