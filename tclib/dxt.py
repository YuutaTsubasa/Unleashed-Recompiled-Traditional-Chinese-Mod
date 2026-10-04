import numpy as np, struct

def encode_dxt5_gray(img):
    """img: HxW uint8 grayscale (rgb=gray, alpha=255). Returns DXT5 block data."""
    H, W = img.shape
    b = img.reshape(H // 4, 4, W // 4, 4).transpose(0, 2, 1, 3).reshape(-1, 16).astype(np.int32)
    mx = b.max(1); mn = b.min(1)
    # 565 endpoints for gray: quantize to 5 bits (R,B) / 6 bits (G) -> use 5-bit levels for all
    def q(v):
        r = (v * 31 + 127) // 255; g = (v * 63 + 127) // 255
        return (r << 11) | (g << 5) | r, (r * 255 + 15) // 31
    c0, v0 = q(mx); c1, v1 = q(mn)
    # ensure c0 > c1 for 4-color mode
    same = c0 <= c1
    c0 = np.where(same, np.where(c1 < 0xFFFF, c1 + 1, c0), c0)  # rare: flat blocks
    flat = mx == mn
    # palette: v0, v1, (2v0+v1)/3, (v0+2v1)/3
    pal = np.stack([v0, v1, (2 * v0 + v1) // 3, (v0 + 2 * v1) // 3], 1)
    d = np.abs(b[:, :, None] - pal[:, None, :])
    idx = d.argmin(2)
    idx = np.where(flat[:, None], 0, idx)
    # where flat & c0 adjusted, color index 0 means c0 which may be +1 off; use c1 instead (exact)
    idx = np.where((flat & same)[:, None], 1, idx)
    bits = np.zeros(len(b), np.uint64)
    for i in range(16):
        bits |= (idx[:, i].astype(np.uint64) << np.uint64(2 * i))
    out = bytearray()
    alpha = bytes([255, 255, 0, 0, 0, 0, 0, 0])
    c0 = c0.astype(np.uint16); c1 = c1.astype(np.uint16)
    blocks = np.zeros((len(b), 16), np.uint8)
    blocks[:, 0:8] = np.frombuffer(alpha, np.uint8)
    blocks[:, 8:10] = c0.view(np.uint8).reshape(-1, 2)
    blocks[:, 10:12] = c1.view(np.uint8).reshape(-1, 2)
    blocks[:, 12:16] = bits.astype(np.uint32).view(np.uint8).reshape(-1, 4)
    return blocks.tobytes()

def dds_dxt5(img, header_template=None):
    H, W = img.shape
    data = encode_dxt5_gray(img)
    hdr = bytearray(128)
    struct.pack_into('<4sIIIIIII', hdr, 0, b'DDS ', 124, 0x81007, H, W, len(data), 0, 0)
    struct.pack_into('<II4s', hdr, 76, 32, 4, b'DXT5')
    struct.pack_into('<I', hdr, 108, 0x1000)
    return bytes(hdr) + data

def encode_dxt5_rgba(img):
    """img: HxWx4 uint8 RGBA -> DXT5 blocks (PCA endpoints, 4-color + 8-alpha)."""
    H, W, _ = img.shape
    b = img.reshape(H // 4, 4, W // 4, 4, 4).transpose(0, 2, 1, 3, 4).reshape(-1, 16, 4).astype(np.float32)
    n = len(b)
    rgb = b[:, :, :3]; al = b[:, :, 3]
    # color: principal axis
    mean = rgb.mean(1, keepdims=True); c = rgb - mean
    cov = np.einsum('nki,nkj->nij', c, c)
    v = np.ones((n, 3), np.float32)
    for _ in range(8):
        v = np.einsum('nij,nj->ni', cov, v); v /= (np.linalg.norm(v, axis=1, keepdims=True) + 1e-6)
    t = np.einsum('nki,ni->nk', c, v)
    e0 = mean[:, 0] + v * t.max(1, keepdims=True); e1 = mean[:, 0] + v * t.min(1, keepdims=True)
    def to565(e):
        e = np.clip(e, 0, 255)
        r = np.round(e[:, 0] * 31 / 255).astype(np.int32); g = np.round(e[:, 1] * 63 / 255).astype(np.int32); bb = np.round(e[:, 2] * 31 / 255).astype(np.int32)
        return (r << 11) | (g << 5) | bb, np.stack([(r * 255 + 15) // 31, (g * 255 + 31) // 63, (bb * 255 + 15) // 31], 1).astype(np.float32)
    c0, v0 = to565(e0); c1, v1 = to565(e1)
    swap = c0 < c1
    c0, c1 = np.where(swap, c1, c0), np.where(swap, c0, c1)
    v0, v1 = np.where(swap[:, None], v1, v0), np.where(swap[:, None], v0, v1)
    eq = c0 == c1
    pal = np.stack([v0, v1, (2 * v0 + v1) / 3, (v0 + 2 * v1) / 3], 1)
    d = ((rgb[:, :, None, :] - pal[:, None, :, :]) ** 2).sum(-1)
    idx = d.argmin(2); idx = np.where(eq[:, None], 0, idx)
    cbits = np.zeros(n, np.uint64)
    for i in range(16): cbits |= idx[:, i].astype(np.uint64) << np.uint64(2 * i)
    # alpha
    a0 = al.max(1); a1 = al.min(1)
    apal = np.stack([a0, a1] + [((6 - k) * a0 + (k + 1) * a1) / 7 for k in range(6)], 1)
    aidx = np.abs(al[:, :, None] - apal[:, None, :]).argmin(2)
    aidx = np.where((a0 == a1)[:, None], 0, aidx)
    abits = np.zeros(n, np.uint64)
    for i in range(16): abits |= aidx[:, i].astype(np.uint64) << np.uint64(3 * i)
    blocks = np.zeros((n, 16), np.uint8)
    blocks[:, 0] = a0.astype(np.uint8); blocks[:, 1] = a1.astype(np.uint8)
    blocks[:, 2:8] = abits.view(np.uint8).reshape(-1, 8)[:, :6]
    blocks[:, 8:10] = c0.astype(np.uint16).view(np.uint8).reshape(-1, 2)
    blocks[:, 10:12] = c1.astype(np.uint16).view(np.uint8).reshape(-1, 2)
    blocks[:, 12:16] = cbits.astype(np.uint32).view(np.uint8).reshape(-1, 4)
    return blocks.tobytes()

def dds_dxt5_rgba(img):
    H, W, _ = img.shape
    data = encode_dxt5_rgba(img)
    hdr = bytearray(128)
    struct.pack_into('<4sIIIIIII', hdr, 0, b'DDS ', 124, 0x81007, H, W, len(data), 0, 0)
    struct.pack_into('<II4s', hdr, 76, 32, 4, b'DXT5')
    struct.pack_into('<I', hdr, 108, 0x1000)
    return bytes(hdr) + data
