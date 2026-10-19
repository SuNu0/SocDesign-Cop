#include "ffn_driver.h"

enum {
    CONTROL=0x00, STATUS=0x04, CYCLES=0x08, LAYER_TAG=0x20,
    SATURATIONS=0x24, X_MEM=0x10000, W_MEM=0x20000,
    B_MEM=0x30000, Y_MEM=0x40000
};

static inline void io_fence(void) {
#if defined(__riscv)
    __asm__ volatile ("fence iorw, iorw" ::: "memory");
#elif defined(__GNUC__)
    __asm__ volatile ("" ::: "memory");
#endif
}

static inline void write_reg(uintptr_t base, unsigned offset, uint32_t value) {
    *(volatile uint32_t *)(base + offset) = value;
}

static inline uint32_t read_reg(uintptr_t base, unsigned offset) {
    return *(volatile uint32_t *)(base + offset);
}

int ffn_run(uintptr_t base, const int16_t *x, const int16_t *w,
            const int16_t *b, int16_t *y, unsigned layer,
            uint32_t max_polls, uint32_t *core_cycles,
            uint32_t *saturation_count) {
    uint32_t polls;
    size_t i;
    if (!x || !w || !b || !y || layer >= 12 || !max_polls)
        return -3;
    if (read_reg(base, STATUS) & 1u)
        return -1;
    write_reg(base, LAYER_TAG, layer);
    for (i=0; i<FFN_X_WORDS; ++i)
        write_reg(base, X_MEM+(unsigned)(4*i), (uint16_t)x[i]);
    for (i=0; i<FFN_W_WORDS; ++i)
        write_reg(base, W_MEM+(unsigned)(4*i), (uint16_t)w[i]);
    for (i=0; i<FFN_B_WORDS; ++i)
        write_reg(base, B_MEM+(unsigned)(4*i), (uint16_t)b[i]);
    io_fence();
    write_reg(base, CONTROL, 1); /* Clears stale DONE and starts one full task. */
    for (polls=0; polls<max_polls; ++polls) {
        if (read_reg(base, STATUS) & 2u)
            break;
    }
    if (polls == max_polls)
        return -2; /* Does not abort hardware. Wait or assert platform reset. */
    io_fence();
    if (core_cycles)
        *core_cycles = read_reg(base, CYCLES);
    if (saturation_count)
        *saturation_count = read_reg(base, SATURATIONS);
    for (i=0; i<FFN_Y_WORDS; ++i)
        y[i] = (int16_t)read_reg(base, Y_MEM+(unsigned)(4*i));
    io_fence();
    write_reg(base, CONTROL, 2); /* Acknowledge DONE/IRQ. */
    return 0;
}
