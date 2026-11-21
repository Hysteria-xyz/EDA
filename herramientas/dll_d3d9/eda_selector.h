/* Sólo el selector medido de EDA_limpio.exe; no imágenes de otros paneles. */
#ifndef EDA_SELECTOR_H
#define EDA_SELECTOR_H
static int selector_es_flecha(unsigned long escena, unsigned long vt, unsigned long id)
{
    return escena == 0x899670UL && vt == 0x8AD900UL && id >= 14000 && id < 14150;
}
#endif
