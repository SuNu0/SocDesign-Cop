#ifndef FFN_DRIVER_H
#define FFN_DRIVER_H

#include <stdint.h>
#include <stddef.h>

enum {
    FFN_ROWS = 99, FFN_INNER = 64, FFN_COLS = 256,
    FFN_X_WORDS = 6336, FFN_W_WORDS = 16384,
    FFN_B_WORDS = 256, FFN_Y_WORDS = 25344
};

/* MMIO base is chosen by the E203 platform address decoder, not by this driver.
 * x/w/b/y contain signed Q8.8 integer encodings, NOT float bit patterns.
 * Return: 0=success, -1=already busy, -2=timeout, -3=bad argument.
 * Bus errors require platform-specific trap handling and are not hidden here.
 */
int ffn_run(uintptr_t base, const int16_t *x, const int16_t *w,
            const int16_t *b, int16_t *y, unsigned layer,
            uint32_t max_polls, uint32_t *core_cycles,
            uint32_t *saturation_count);

#endif
