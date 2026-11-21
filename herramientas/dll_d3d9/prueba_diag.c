/* prueba_diag.c — ★ (21-nov) las pruebas de lo portable del diagnóstico automático (eda_diag_nucleo.c), con gcc:
 *   gcc -std=gnu11 -O1 -pthread -o /tmp/prueba_diag prueba_diag.c && /tmp/prueba_diag
 *   /tmp/prueba_diag firma <ticket> <cuenta> <hora> <sesion> <lote> < cuerpo   (para prueba_diag.py: lo compara con
 *                                                                               servidor/diag.py)
 *   /tmp/prueba_diag eventos                                                   (eventos de muestra, uno por línea) */
#include "eda_diag_nucleo.c"
#include <pthread.h>
#include <stdlib.h>

static int fallas, pruebas;
#define OK(c, ...) do { pruebas++; if (!(c)) { fallas++; printf("  ⛔ "); printf(__VA_ARGS__); printf("\n"); } } while (0)

static void hex_de(const void *d, size_t n, char *out) { dg_hex((const unsigned char *)d, (int)n, out); }

static void prueba_sha(void)
{
    unsigned char h[32];
    char x[65];
    dg_sha256("abc", 3, h); hex_de(h, 32, x);
    OK(!strcmp(x, "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"), "sha256(abc) = %s", x);
    dg_sha256("", 0, h); hex_de(h, 32, x);
    OK(!strcmp(x, "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"), "sha256('') = %s", x);
    const char *dos = "abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq";   /* 56 bytes: 2 bloques */
    dg_sha256(dos, strlen(dos), h); hex_de(h, 32, x);
    OK(!strcmp(x, "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1"), "sha256(56 B) = %s", x);
    static char millon[1000000];
    memset(millon, 'a', sizeof(millon));
    dg_sha256(millon, sizeof(millon), h); hex_de(h, 32, x);
    OK(!strcmp(x, "cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0"), "sha256(1e6 a) = %s", x);
    /* de a pedazos = de una vez */
    DG_SHA s;
    unsigned char h2[32];
    dg_sha_ini(&s);
    for (size_t i = 0; i < sizeof(millon); i += 997) dg_sha_mas(&s, millon + i, i + 997 > sizeof(millon) ? sizeof(millon) - i : 997);
    dg_sha_fin(&s, h2);
    OK(!memcmp(h, h2, 32), "sha256 de a pedazos");
}

static void prueba_hmac(void)
{
    unsigned char k[20], h[32], kl[131];
    char x[65];
    memset(k, 0x0b, 20);
    dg_hmac(k, 20, "Hi There", 8, h); hex_de(h, 32, x);                                     /* RFC 4231, caso 1 */
    OK(!strcmp(x, "b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7"), "hmac caso 1 = %s", x);
    dg_hmac((const unsigned char *)"Jefe", 4, "what do ya want for nothing?", 28, h); hex_de(h, 32, x);   /* caso 2 */
    OK(!strcmp(x, "5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843"), "hmac caso 2 = %s", x);
    memset(kl, 0xaa, sizeof(kl));                                                             /* caso 6: clave > 64 */
    const char *m6 = "Test Using Larger Than Block-Size Key - Hash Key First";
    dg_hmac(kl, sizeof(kl), m6, strlen(m6), h); hex_de(h, 32, x);
    OK(!strcmp(x, "60e431591ee0b67f0d8a26aacbf5b77f8e0bc6213728c5140546040f0ee37f54"), "hmac caso 6 = %s", x);
}

static void prueba_firma(void)
{
    /* los mismos valores que servidor/diag.py (calculados ahí: prueba_diag.py los vuelve a comparar al azar) */
    unsigned char k[32];
    char x[65], f[65];
    dg_clave("TICKETabc", 9, k); hex_de(k, 32, x);
    OK(!strcmp(x, "33b28159c7c13b41f7af02a54ebdec1f70808561bc7cc1d0f5b1f6c2bd55d357"), "clave = %s", x);
    const char *c = "{\"e\":\"x\"}\n";
    dg_firmar(k, "en_7", 1763740000000ULL, "0123456789abcdef0123456789abcdef", 3, c, strlen(c), f);
    OK(!strcmp(f, "c9a63cb98b95eb73da226d9456eb3ad1e4b9c266369c1a29a9a4406414b46bd2"), "firma = %s", f);
    char f2[65];                                                       /* cambia cualquier cosa → cambia la firma */
    dg_firmar(k, "en_8", 1763740000000ULL, "0123456789abcdef0123456789abcdef", 3, c, strlen(c), f2);
    OK(strcmp(f, f2), "la cuenta entra en la firma");
    dg_firmar(k, "en_7", 1763740000000ULL, "0123456789abcdef0123456789abcdef", 4, c, strlen(c), f2);
    OK(strcmp(f, f2), "el lote entra en la firma");
    dg_firmar(k, "en_7", 1763740000000ULL, "0123456789abcdef0123456789abcdef", 3, c, strlen(c) - 1, f2);
    OK(strcmp(f, f2), "el cuerpo entra en la firma");
}

static void prueba_evento(void)
{
    char l[DG_LARGO];
    int n = dg_evento(l, sizeof(l), 1763740000000ULL, 1234, "congelado", ",\"ms\":2500,\"vt\":\"0x00899670\"");
    OK(n > 0 && !strcmp(l, "{\"t\":1763740000000,\"m\":1234,\"e\":\"congelado\",\"ms\":2500,\"vt\":\"0x00899670\"}"), "evento: %s", l);
    dg_evento(l, sizeof(l), 1, 2, "ma\"l\\o\nNOMBRE", NULL);           /* el nombre se limpia: nada de comillas */
    OK(!strcmp(l, "{\"t\":1,\"m\":2,\"e\":\"malo\"}"), "nombre limpio: %s", l);
    char chico[16];
    OK(dg_evento(chico, sizeof(chico), 1, 2, "largo", NULL) == 0, "si no entra, no se arma a medias");
}

static void prueba_cola(void)
{
    static DG_COLA c;
    char l[DG_LARGO + 8], t[32];
    memset(&c, 0, sizeof(c));
    OK(!dg_cola_sacar(&c, l, sizeof(l)), "vacía");
    for (int i = 0; i < DG_LUGARES + 10; i++) { sprintf(t, "e%d", i); dg_cola_poner(&c, t); }
    OK(c.perdidos == 10, "llena: se descartan los de más (%ld)", c.perdidos);
    int i = 0, orden = 1;
    while (dg_cola_sacar(&c, l, sizeof(l))) { sprintf(t, "e%d", i++); if (strcmp(l, t)) orden = 0; }
    OK(i == DG_LUGARES && orden, "en orden y todos (%d)", i);
    char largo[600];
    memset(largo, 'x', sizeof(largo) - 1);
    largo[sizeof(largo) - 1] = 0;
    dg_cola_poner(&c, largo);
    dg_cola_sacar(&c, l, sizeof(l));
    OK(strlen(l) == DG_LARGO - 1, "una línea larga se corta (%zu)", strlen(l));
    for (int k = 0; k < 3 * DG_LUGARES; k++) {                          /* vueltas enteras del anillo */
        sprintf(t, "v%d", k); dg_cola_poner(&c, t);
        OK(dg_cola_sacar(&c, l, sizeof(l)) && !strcmp(l, t), "vuelta %d", k);
    }
}

/* varios hilos anotando a la vez y uno sacando: no se pierde nada que no se haya contado, nada se repite, nada roto */
static DG_COLA g_c;
#define HILOS 4
#define POR_HILO 20000
static volatile long g_terminados;
static void *escritor(void *p)
{
    long h = (long)p;
    char t[32];
    for (int i = 0; i < POR_HILO; i++) { sprintf(t, "h%ld-%d", h, i); dg_cola_poner(&g_c, t); }
    __sync_add_and_fetch(&g_terminados, 1);
    return NULL;
}

static void prueba_hilos(void)
{
    pthread_t th[HILOS];
    static unsigned char visto[HILOS][POR_HILO];
    int ultimo[HILOS];
    memset(visto, 0, sizeof(visto));
    for (int h = 0; h < HILOS; h++) ultimo[h] = -1;
    for (long h = 0; h < HILOS; h++) pthread_create(&th[h], NULL, escritor, (void *)h);
    long leidos = 0, rotos = 0, repetidos = 0, desorden = 0;
    char l[DG_LARGO];
    for (;;) {
        if (dg_cola_sacar(&g_c, l, sizeof(l))) {
            long h; int i;
            if (sscanf(l, "h%ld-%d", &h, &i) != 2 || h < 0 || h >= HILOS || i < 0 || i >= POR_HILO) { rotos++; continue; }
            if (visto[h][i]) repetidos++;
            visto[h][i] = 1;
            if (i <= ultimo[h]) desorden++;
            ultimo[h] = i;
            leidos++;
        } else if (__sync_fetch_and_add(&g_terminados, 0) == HILOS) {
            if (!dg_cola_sacar(&g_c, l, sizeof(l))) break;              /* (lo último que quedó) */
            long h; int i;
            if (sscanf(l, "h%ld-%d", &h, &i) == 2 && h >= 0 && h < HILOS && i >= 0 && i < POR_HILO) {
                if (visto[h][i]) repetidos++;
                visto[h][i] = 1;
                if (i <= ultimo[h]) desorden++;
                ultimo[h] = i;
                leidos++;
            } else rotos++;
        }
    }
    for (int h = 0; h < HILOS; h++) pthread_join(th[h], NULL);
    OK(!rotos && !repetidos && !desorden, "hilos: rotos %ld, repetidos %ld, fuera de orden %ld", rotos, repetidos, desorden);
    OK(leidos + g_c.perdidos == (long)HILOS * POR_HILO, "hilos: leídos %ld + perdidos %ld = %d", leidos, g_c.perdidos, HILOS * POR_HILO);
    printf("  (hilos: %ld leídos, %ld descartados con la cola llena)\n", leidos, g_c.perdidos);
}

static void prueba_lote(void)
{
    const char *t = "a\nbb\nccc\nmedia";
    OK(dg_cortar_lote(t, strlen(t)) == 9, "lote: sólo líneas enteras (%zu)", dg_cortar_lote(t, strlen(t)));
    OK(dg_cortar_lote("sin fin", 7) == 0, "lote: una línea a medias no sale");
    static char g[200000];
    size_t n = 0;
    for (int i = 0; i < 2000; i++) n += sprintf(g + n, "{\"t\":%d,\"e\":\"x\"}\n", i);
    size_t c = dg_cortar_lote(g, n);
    int lineas = 0;
    for (size_t i = 0; i < c; i++) lineas += g[i] == '\n';
    OK(lineas == DG_LOTE_LINEAS && c <= DG_LOTE_BYTES, "lote: ≤ 500 líneas (%d, %zu B)", lineas, c);
    n = 0;
    for (int i = 0; i < 400; i++) { memset(g + n, 'y', 199); n += 199; g[n++] = '\n'; }
    c = dg_cortar_lote(g, n);
    OK(c <= DG_LOTE_BYTES && c > DG_LOTE_BYTES - 200 && g[c - 1] == '\n', "lote: ≤ 60 KB (%zu)", c);
}

static void prueba_url(void)
{
    int s, p;
    char h[128], r[128];
    OK(dg_url("https://ensayo.example.link/eda/diag", &s, h, 128, &p, r, 128) && s && p == 443
       && !strcmp(h, "ensayo.example.link") && !strcmp(r, "/eda/diag"), "url https");
    OK(dg_url("https://x.y:8443/eda/diag", &s, h, 128, &p, r, 128) && p == 8443, "url con puerto");
    OK(dg_url("http://127.0.0.1:25901/eda/diag", &s, h, 128, &p, r, 128) && !s && p == 25901, "http a 127.0.0.1");
    OK(!dg_url("http://ensayo.example.link/eda/diag", &s, h, 128, &p, r, 128), "http afuera: NO");
    OK(!dg_url("http://192.168.0.5/eda/diag", &s, h, 128, &p, r, 128), "http a la LAN: NO");
    OK(!dg_url("ftp://x/y", &s, h, 128, &p, r, 128), "otro esquema: NO");
    OK(!dg_url("https://x.y", &s, h, 128, &p, r, 128), "sin ruta: NO");
    OK(!dg_url("https://us er@x/y", &s, h, 128, &p, r, 128), "host raro: NO");
    OK(!dg_url("https://x:99999/y", &s, h, 128, &p, r, 128), "puerto malo: NO");
}

int main(int argc, char **argv)
{
    if (argc == 7 && !strcmp(argv[1], "firma")) {
        static char cuerpo[70000];
        size_t n = fread(cuerpo, 1, sizeof(cuerpo), stdin);
        unsigned char k[32];
        char f[65], x[65];
        dg_clave(argv[2], strlen(argv[2]), k);
        dg_hex(k, 32, x);
        dg_firmar(k, argv[3], strtoull(argv[4], NULL, 10), argv[5], strtoul(argv[6], NULL, 10), cuerpo, n, f);
        printf("%s %s\n", x, f);
        return 0;
    }
    if (argc == 2 && !strcmp(argv[1], "eventos")) {                    /* las formas que arma eda_diag.c */
        static const char *ej[][2] = {
            {"inicio", ",\"version\":\"0.5.1\",\"build\":\"b73d820cc5d\""}, {"escena", ",\"vt\":\"0x00899670\""},
            {"congelado", ",\"ms\":2500,\"vt\":\"0x00899670\""}, {"atrapado", ",\"vt\":\"0x00899670\""},
            {"fps", ",\"fps\":60"}, {"foco", ",\"activo\":0"}, {"server_conecta", ",\"n\":1"},
            {"caida", ",\"codigo\":\"0xC0000005\",\"sitio\":\"0x007F4626\",\"modulo\":\"sin_resolver\""},
            {"caida", ",\"codigo\":\"0xC0000005\",\"sitio\":\"0x1000ABCD\",\"modulo\":\"d3d9.dll\""},
            {"perdidos", ",\"n\":3"}, {"fin", ""}};
        char l[DG_LARGO];
        for (size_t i = 0; i < sizeof(ej) / sizeof(ej[0]); i++) {
            dg_evento(l, sizeof(l), 1763740000000ULL + i, 1000 + i, ej[i][0], ej[i][1]);
            printf("%s\n", l);
        }
        return 0;
    }
    printf("prueba_diag: lo portable del diagnóstico automático\n");
    prueba_sha();
    prueba_hmac();
    prueba_firma();
    prueba_evento();
    prueba_cola();
    prueba_hilos();
    prueba_lote();
    prueba_url();
    printf("%s %d pruebas, %d fallas\n", fallas ? "⛔" : "✅", pruebas, fallas);
    return fallas != 0;
}
