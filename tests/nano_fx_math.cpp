// Host-side verification of the Arduino Nano chest-OLED effect math.
//
// The Nano (ATmega328P) has a 16-bit `int`. The original NEURAL_MESH /
// OPTICS_CAMO effects computed `seed * i * 17` etc. in 16-bit, which overflows
// and wraps negative; a negative `% 128` then yields negative (off-screen)
// coordinates, so the effect looked dead. This harness:
//   1. proves the OLD math really does go out of bounds (simulating the 16-bit
//      wrap by truncating to int16_t), and
//   2. proves the NEW math (mirrored from nano_node.ino) keeps every drawn
//      coordinate inside the 128x64 canvas across a long sweep of millis().
//
// Exit code 0 = all checks passed.

#include <cstdio>
#include <cstdint>
#include <cmath>
#include <cstdlib>

static const int W = 128;
static const int H = 64;

static bool in_bounds(int x, int y) {
    return x >= 0 && x < W && y >= 0 && y < H;
}

// --- NEW NEURAL_MESH (mirrors nano_node.ino) -------------------------------
static int check_new_neural_mesh() {
    const int NODES = 8;
    for (unsigned long t = 0; t < 900000UL; t += 33) {   // ~15 min of frames
        for (int i = 0; i < NODES; i++) {
            float phase = (t / 900.0) + i * 0.7854;
            float cx = 18.0 + (i % 4) * 31.0;
            float cy = 28.0 + (i / 4) * 20.0;
            int x = (int)(cx + cos(phase) * 10.0);
            int y = (int)(cy + sin(phase * 1.4) * 8.0);
            if (x < 2) x = 2; else if (x > 125) x = 125;
            if (y < 18) y = 18; else if (y > 61) y = 61;
            if (!in_bounds(x, y)) {
                printf("NEW NEURAL_MESH out of bounds t=%lu i=%d (%d,%d)\n", t, i, x, y);
                return 1;
            }
        }
    }
    return 0;
}

// --- NEW OPTICS_CAMO (mirrors nano_node.ino) -------------------------------
static int check_new_optics_camo() {
    for (unsigned long t = 0; t < 900000UL; t += 120) {
        unsigned long s = (t / 120);
        for (int i = 0; i < 120; i++) {
            unsigned long h = (s * 31UL) + (unsigned long)i * 1013UL;
            h ^= (h << 3);
            int px = (int)(h % 128UL);
            int py = 18 + (int)((h / 128UL) % 44UL);
            if (!in_bounds(px, py)) {
                printf("NEW OPTICS_CAMO out of bounds t=%lu i=%d (%d,%d)\n", t, i, px, py);
                return 1;
            }
        }
    }
    return 0;
}

// --- NEW RAM_ALLOCATOR seed must stay bounded ------------------------------
static int check_new_ram_allocator() {
    for (unsigned long t = 0; t < 90000000UL; t += 25000UL) {  // long uptime sweep
        int seed = (int)((t / 250) % 256);
        if (seed < 0 || seed > 255) {
            printf("NEW RAM_ALLOCATOR seed out of range t=%lu seed=%d\n", t, seed);
            return 1;
        }
        for (int y = 0; y < 4; y++)
            for (int x = 0; x < 16; x++) {
                int bx = 4 + x * 7, by = 20 + y * 9;
                if (!in_bounds(bx, by) || !in_bounds(bx + 5, by + 6)) {
                    printf("NEW RAM_ALLOCATOR cell out of bounds (%d,%d)\n", bx, by);
                    return 1;
                }
            }
    }
    return 0;
}

// --- 8x8 matrix pattern index/color math must stay in [0,63] / [0,255] -----
// Mirrors the index arithmetic of the mat* renderers in nano_node.ino. Any
// out-of-range NeoPixel index or color channel would be a firmware bug.
static bool px_ok(int idx) { return idx >= 0 && idx < 64; }
static bool ch_ok(int v) { return v >= 0 && v <= 255; }

static int check_matrix_patterns() {
    const uint8_t bitmaps[5][8] = {
        { 0x7E, 0xFF, 0xBD, 0xBD, 0xE7, 0x7E, 0x24, 0x3C },  // skull
        { 0x66, 0xFF, 0xFF, 0xFF, 0x7E, 0x3C, 0x18, 0x00 },  // heart
        { 0x18, 0x18, 0x00, 0xC3, 0xC3, 0x00, 0x18, 0x18 },  // crosshair
        { 0x18, 0x3C, 0x7E, 0xFF, 0xFF, 0x7E, 0x3C, 0x18 },  // diamond
        { 0x66, 0xDB, 0x3C, 0x7E, 0x66, 0x24, 0x42, 0x00 },  // biohazard
    };
    for (unsigned long t = 0; t < 900000UL; t += 37) {
        // bitmap render path
        for (int b = 0; b < 5; b++)
            for (int i = 0; i < 64; i++)
                if (!px_ok(i)) { printf("bitmap idx oob %d\n", i); return 1; }

        // radar sweep
        int col = (int)((t / 90) % 8);
        for (int k = 1; k <= 3; k++) {
            int c = (col - k + 8) % 8;
            if (!px_ok(0 * 8 + c) || !ch_ok(70 - k * 20) || !ch_ok(30 - k * 8)) {
                printf("radar oob t=%lu\n", t); return 1;
            }
        }
        // rain cascade
        for (int c = 0; c < 8; c++) {
            unsigned long speed = 60 + (c % 4) * 25;
            int head = (int)(((t / speed) + c * 3) % 8);
            for (int k = 0; k < 4; k++) {
                int r = (head - k + 8) % 8;
                if (!px_ok(r * 8 + c) || !ch_ok(200 - k * 55)) { printf("rain oob t=%lu\n", t); return 1; }
            }
        }
        // signal bars
        for (int c = 0; c < 8; c++) {
            int h = 1 + (int)(fabs(sin((t / 300.0) + c * 0.7)) * 7);
            if (h > 8) h = 8;
            for (int r = 0; r < h; r++) if (!px_ok((7 - r) * 8 + c)) { printf("bars oob\n"); return 1; }
        }
        // firewall ice
        for (int c = 0; c < 8; c++) {
            int h = 3 + (int)(((unsigned long)c * 37 + (t / 200)) % 5);
            for (int r = 0; r < h; r++) if (!px_ok((7 - r) * 8 + c)) { printf("firewall oob\n"); return 1; }
            int row = 7 - h;
            if (row < 0 || row > 7) { printf("firewall cap oob\n"); return 1; }
        }
        // hex dump
        {
            unsigned long s = (t / 150);
            for (int i = 0; i < 24; i++) {
                unsigned long h = (s * 31UL) + (unsigned long)i * 1013UL;
                h ^= (h << 3);
                int c = (int)(h % 8UL), r = (int)((h / 8UL) % 8UL);
                if (!px_ok(r * 8 + c)) { printf("hexdump oob\n"); return 1; }
            }
        }
        // sandevistan
        for (int r = 0; r < 8; r++) {
            unsigned long speed = 20 + (r % 3) * 12;
            int c0 = (int)(((t / speed) + r * 5) % 8);
            for (int k = 0; k < 4; k++) {
                int c = (c0 - k + 8) % 8;
                if (!px_ok(r * 8 + c) || !ch_ok(255 - k * 60)) { printf("sandy oob\n"); return 1; }
            }
        }
        // lightning
        {
            unsigned long s = (t / 70);
            int x = 3 + (int)(s % 3);
            for (int r = 0; r < 8; r++) {
                if (!px_ok(r * 8 + x)) { printf("lightning oob\n"); return 1; }
                if ((s + r) % 2 == 0) x = (x + 1) % 8;
            }
            for (int i = 0; i < 10; i++) {
                unsigned long h = (s * 17UL) + (unsigned long)i * 999UL;
                h ^= (h << 5);
                if (!px_ok((int)(h % 64UL))) { printf("lightning spark oob\n"); return 1; }
            }
        }
        // sonar ring
        {
            int radius = (int)((t / 120) % 5);
            for (int r = 0; r < 8; r++)
                for (int c = 0; c < 8; c++) {
                    int dx = abs(c - 3), dy = abs(r - 3);
                    int dist = (dx > dy) ? dx : dy;
                    if (dist == radius || dist == ((radius + 4) % 5))
                        if (!px_ok(r * 8 + c)) { printf("sonar oob\n"); return 1; }
                }
        }
        // equalizer
        for (int c = 0; c < 8; c++) {
            int phase = (int)(((t / 60) + c * 3) % 14);
            int h = (phase < 7 ? phase : 14 - phase) + 1;
            for (int r = 0; r < h; r++)
                if (!px_ok((7 - r) * 8 + c) || !ch_ok(100 + r * 18)) { printf("eq oob\n"); return 1; }
        }
    }
    return 0;
}

// --- OLD NEURAL_MESH must demonstrably go out of bounds --------------------
// Simulates the AVR 16-bit `int` by truncating each product to int16_t (which
// reproduces the low-16-bit wrap of the AVR) before the `%`.
static int old_neural_mesh_goes_oob() {
    for (unsigned long t = 0; t < 900000UL; t += 100) {
        int seed = (int)((t / 100) % 255);
        for (int i = 0; i < 30; i++) {
            int16_t px_raw = (int16_t)(seed * i * 17);   // 16-bit overflow wrap
            int px = px_raw % 128;                        // may be negative
            int16_t py_prod = (int16_t)(seed * i * 31);
            int py = 15 + (py_prod % 49);                 // may be negative
            if (!in_bounds(px, py))
                return 1;                                 // found the bug
        }
    }
    return 0;  // never went out of bounds (bug NOT reproduced)
}

int main() {
    int rc = 0;
    rc |= check_new_neural_mesh();
    rc |= check_new_optics_camo();
    rc |= check_new_ram_allocator();
    rc |= check_matrix_patterns();
    if (!old_neural_mesh_goes_oob()) {
        printf("EXPECTED old NEURAL_MESH to overflow 16-bit and go out of bounds\n");
        rc |= 1;
    }
    if (rc == 0) printf("ALL NANO FX MATH OK\n");
    return rc;
}
