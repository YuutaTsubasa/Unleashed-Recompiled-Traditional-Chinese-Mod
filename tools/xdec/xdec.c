/*
 * xdec - decompress Xbox 360 XCompress (LZX, signature 0x0FF512EE) files.
 * Files without the signature are copied unchanged.
 *
 * Usage: xdec <input> <output>
 *
 * Uses libmspack's LZX decoder (LGPL-2.1, see libmspack/COPYING.LIB).
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include "mspack.h"
#include "lzx.h"

#define XCOMPRESS_SIGNATURE 0x0FF512EEu

static uint16_t be16(const uint8_t *p) { return (uint16_t)((p[0] << 8) | p[1]); }
static uint32_t be32(const uint8_t *p) { return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) | ((uint32_t)p[2] << 8) | p[3]; }
static uint64_t be64(const uint8_t *p) { return ((uint64_t)be32(p) << 32) | be32(p + 4); }

/* The compressed stream is a sequence of blocks, each prefixed by a big-endian
   u16 size (0xFF xx yy form carries an extra uncompressed-size byte we skip). */
struct read_stream { const uint8_t *data, *end; int remaining; };
struct write_stream { uint8_t *data; size_t remaining; };

static int ms_read(struct mspack_file *file, void *buffer, int bytes)
{
    struct read_stream *s = (struct read_stream *)file;
    if (s->remaining == 0) {
        if (s->data + 2 > s->end) return 0;
        uint16_t size = be16(s->data); s->data += 2;
        if ((size & 0xFF00) == 0xFF00) {
            s->data += 1;
            size = be16(s->data); s->data += 2;
        }
        s->remaining = size;
    }
    int n = s->remaining < bytes ? s->remaining : bytes;
    if (s->data + n > s->end) n = (int)(s->end - s->data);
    memcpy(buffer, s->data, n);
    s->data += n; s->remaining -= n;
    return n;
}

static int ms_write(struct mspack_file *file, void *buffer, int bytes)
{
    struct write_stream *s = (struct write_stream *)file;
    size_t n = s->remaining < (size_t)bytes ? s->remaining : (size_t)bytes;
    memcpy(s->data, buffer, n);
    s->data += n; s->remaining -= n;
    return (int)n;
}

static void *ms_alloc(struct mspack_system *self, size_t bytes) { (void)self; return malloc(bytes); }
static void ms_free(void *p) { free(p); }
static void ms_copy(void *src, void *dst, size_t bytes) { memcpy(dst, src, bytes); }

static struct mspack_system g_sys = { NULL, NULL, ms_read, ms_write, NULL, NULL, NULL, ms_alloc, ms_free, ms_copy, NULL };

int main(int argc, char **argv)
{
    if (argc < 3) { fprintf(stderr, "usage: xdec <input> <output>\n"); return 1; }
    FILE *f = fopen(argv[1], "rb");
    if (!f) { fprintf(stderr, "cannot open %s\n", argv[1]); return 1; }
    fseek(f, 0, SEEK_END); long size = ftell(f); fseek(f, 0, SEEK_SET);
    uint8_t *in = (uint8_t *)malloc(size > 0 ? size : 1);
    if (fread(in, 1, size, f) != (size_t)size) { fclose(f); return 1; }
    fclose(f);

    uint8_t *out = in; size_t outSize = (size_t)size;
    if (size >= 0x30 && be32(in) == XCOMPRESS_SIGNATURE) {
        uint32_t windowSize = be32(in + 0x10);
        uint32_t compressedBlockSize = be32(in + 0x14);
        uint32_t uncompressedBlockSize = be32(in + 0x28);
        outSize = (size_t)be64(in + 0x18);
        out = (uint8_t *)malloc(outSize ? outSize : 1);
        int windowBits = 0;
        while (((windowSize >> windowBits) & 1) == 0 && windowBits < 31) windowBits++;

        struct write_stream ws = { out, outSize };
        const uint8_t *src = in + 0x30, *end = in + size;
        /* The file is split into chunks of up to uncompressedBlockSize bytes, each
           prefixed by its big-endian u32 compressed size and decoded independently. */
        while (src + 4 <= end && ws.remaining > 0) {
            uint32_t chunkSize = be32(src); src += 4;
            struct read_stream rs = { src, end, 0 };
            size_t chunkOut = ws.remaining < uncompressedBlockSize ? ws.remaining : uncompressedBlockSize;
            struct lzxd_stream *lzx = lzxd_init(&g_sys, (struct mspack_file *)&rs, (struct mspack_file *)&ws,
                                                windowBits, 0, (int)compressedBlockSize, (off_t)chunkOut, 0);
            if (!lzx) { fprintf(stderr, "lzxd_init failed\n"); return 1; }
            int err = lzxd_decompress(lzx, (off_t)chunkOut);
            lzxd_free(lzx);
            if (err != MSPACK_ERR_OK) { fprintf(stderr, "decompression failed (%d)\n", err); return 1; }
            src += chunkSize;
        }
    }

    f = fopen(argv[2], "wb");
    if (!f) { fprintf(stderr, "cannot write %s\n", argv[2]); return 1; }
    fwrite(out, 1, outSize, f);
    fclose(f);
    return 0;
}
