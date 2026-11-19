/* eda_version.c — ★ QUÉ DLL ES ÉSTA Y A QUÉ SERVER VA (19-nov). Sin Windows: se prueba con prueba_version.c.
 *
 * La identidad la escribe version.py en eda_version.h al compilar (versión, commit, sucio, fecha, build):
 * nadie la edita a mano. Sin eda_version.h (una compilación a mano, sin compilar.py) la dll dice
 * «sin-version» y LOCAL: nunca se hace pasar por una publicada.
 *
 * El ENTORNO no sale de la rama de git sino del server que el juego VA A USAR (el mismo g_server al que
 * mi_connect desvía la conexión: [red] server del ini, EDA_SERVER o el 3er argumento del launcher):
 *   · host de esta PC o de la red de la casa (127.x, 10.x, 172.16–31.x, 192.168.x, 169.254.x, localhost) → LOCAL
 *   · puerto 35900 → TEST (server de prueba, rama develop) · puerto 25900 → PROD (rama main) — ENTORNOS §1, fila D
 *   · otro puerto → OTRO · sin server → SIN SERVER (el juego de 2009, sin desviar)
 * Una dll compilada de develop conectada al 25900 dice PROD: dice adónde va, no de dónde salió. */

#if defined(__has_include)
#if __has_include("eda_version.h")
#include "eda_version.h"
#endif
#endif
#ifndef EDA_VERSION
#define EDA_VERSION "0.0.0"
#define EDA_COMMIT "sin-version"
#define EDA_SUCIO 1
#define EDA_FECHA "?"
#define EDA_BUILD "b-sin-version"
#endif
#define EDA_TXT_(x) #x
#define EDA_TXT(x) EDA_TXT_(x)

/* la marca que lee identificar.py en el archivo (y el diagnóstico): texto fijo, sin el hash del archivo */
static const char g_eda_id[] = "EDA-ID|v=" EDA_VERSION "|c=" EDA_COMMIT "|s=" EDA_TXT(EDA_SUCIO) "|f=" EDA_FECHA
                               "|b=" EDA_BUILD "|";

enum { ENT_SIN = 0, ENT_LOCAL, ENT_TEST, ENT_PROD, ENT_OTRO };
#define PUERTO_PROD 25900
#define PUERTO_TEST 35900

static const char *ent_nombre(int e)
{
    return e == ENT_LOCAL ? "LOCAL" : e == ENT_TEST ? "TEST" : e == ENT_PROD ? "PROD" : e == ENT_OTRO ? "OTRO" : "SIN SERVER";
}
static const char *ent_sufijo(int e)
{
    return e == ENT_LOCAL ? "local" : e == ENT_TEST ? "test" : e == ENT_PROD ? "prod" : e == ENT_OTRO ? "otro" : "sin-server";
}

/* "a.b.c.d" → 1 y los 4 números; cualquier otra cosa (un nombre) → 0 */
static int ver_ipv4(const char *h, int n[4])
{
    for (int i = 0; i < 4; i++) {
        if (*h < '0' || *h > '9') return 0;
        int v = 0, dig = 0;
        while (*h >= '0' && *h <= '9') { v = v * 10 + (*h++ - '0'); if (++dig > 3) return 0; }
        if (v > 255) return 0;
        n[i] = v;
        if (i < 3 && *h++ != '.') return 0;
    }
    return *h == 0;
}

/* el entorno de un server «host[:puerto]» (puerto por defecto 25900, como resolver_server) */
static int ver_entorno(const char *server, int *puerto_out)
{
    char host[256];
    int puerto = PUERTO_PROD, n = 0;
    if (puerto_out) *puerto_out = 0;
    while (server && *server == ' ') server++;
    if (!server || !*server) return ENT_SIN;
    while (server[n] && n < (int)sizeof(host) - 1) { host[n] = server[n]; n++; }
    host[n] = 0;
    char *dp = strrchr(host, ':');
    if (dp) {
        *dp = 0;
        puerto = 0;
        for (const char *p = dp + 1; *p; p++) {
            if (*p < '0' || *p > '9' || puerto > 65535) { puerto = -1; break; }
            puerto = puerto * 10 + (*p - '0');
        }
    }
    if (puerto_out) *puerto_out = puerto;
    for (char *p = host; *p; p++) if (*p >= 'A' && *p <= 'Z') *p += 32;
    int ip[4];
    if (!strcmp(host, "localhost")) return ENT_LOCAL;
    if (ver_ipv4(host, ip)) {
        if (ip[0] == 127 || ip[0] == 10 || ip[0] == 0 || (ip[0] == 172 && ip[1] >= 16 && ip[1] <= 31)
            || (ip[0] == 192 && ip[1] == 168) || (ip[0] == 169 && ip[1] == 254)) return ENT_LOCAL;
    }
    if (puerto == PUERTO_TEST) return ENT_TEST;
    if (puerto == PUERTO_PROD) return ENT_PROD;
    return ENT_OTRO;
}

/* las líneas del aviso de arranque (UTF-8). estado = NULL → «DLL cargada correctamente». Devuelve el entorno. */
#define VER_LINEAS 5
#define VER_LARGO 128
static int ver_lineas(const char *server, const char *estado, char lin[VER_LINEAS][VER_LARGO])
{
    int puerto, e = ver_entorno(server, &puerto);
    snprintf(lin[0], VER_LARGO, "EDA — Cliente iniciado");
    snprintf(lin[1], VER_LARGO, "Versión: %s-%s", EDA_VERSION, ent_sufijo(e));
    if (EDA_SUCIO) snprintf(lin[2], VER_LARGO, "Compilación: %s-dirty · %s (LOCAL, no publicada)", EDA_COMMIT, EDA_BUILD);
    else snprintf(lin[2], VER_LARGO, "Compilación: %s · %s", EDA_COMMIT, EDA_BUILD);
    if (e == ENT_SIN) snprintf(lin[3], VER_LARGO, "Entorno: SIN SERVER (el juego no se desvía)");
    else snprintf(lin[3], VER_LARGO, "Entorno: %s (puerto %d)", ent_nombre(e), puerto);
    snprintf(lin[4], VER_LARGO, "Estado: %s", estado && *estado ? estado : "DLL cargada correctamente");
    return e;
}

/* una sola línea (Options, el registro): «EDA 0.5.0-test · a1b2c3d · b0123456789» */
static void ver_corta(const char *server, char *t, int cap)
{
    int e = ver_entorno(server, NULL);
    snprintf(t, cap, "EDA %s-%s · %s%s · %s", EDA_VERSION, ent_sufijo(e), EDA_COMMIT, EDA_SUCIO ? "-dirty" : "", EDA_BUILD);
}
