"""Replace Japanese text baked into UI textures with Traditional Chinese.

Each spec entry names a box on the texture (the original word's location, in
pixels): the Japanese is erased and the Chinese is drawn into the same box in a
style imitating the original (silver italic, white outlined, gold, ...).
"""
import io
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from . import config
from .dxt import dds_dxt5_rgba

# font weights (Noto Sans TC variable font)
BLACK = 900
BOLD = 700
REG = 500

def load_font(weight, size):
    return config.zh_font(size, weight)
SS = 4  # supersampling

def text_mask(text, weight, px_h):
    """render text (possibly multi-line with \n) as float mask; ink height of a line ~= px_h"""
    size = px_h * SS
    f = load_font(weight, size)
    l, t, r, b = f.getbbox('國')
    scale = size / (b - t)
    f = load_font(weight, int(size * scale))
    lines = text.split('\n')
    boxes = [f.getbbox(s) for s in lines]
    lh = int(px_h * SS * 1.15)
    W = max(bb[2] - bb[0] for bb in boxes) + 8 * SS
    H = lh * len(lines) + 8 * SS
    im = Image.new('L', (W, H)); d = ImageDraw.Draw(im)
    for i, (s, bb) in enumerate(zip(lines, boxes)):
        d.text((4 * SS - bb[0], 4 * SS + i * lh - f.getbbox('國')[1]), s, font=f, fill=255)
    a = np.array(im, np.float32) / 255
    ys, xs = np.where(a > 0.02)
    return a[ys.min():ys.max() + 1, xs.min():xs.max() + 1]

def shear(a, k):
    """forward italic: top of the glyph leans right by |k| * height, nothing is cropped"""
    if not k: return a
    k = abs(k)
    H, W = a.shape
    pad = int(np.ceil(k * H)) + 2
    # output (x', y) samples input x = x' - k * (H - y)
    im = Image.fromarray((a * 255).astype(np.uint8)).transform((W + pad, H), Image.AFFINE, (1, k, -k * H, 0, 1, 0), Image.BICUBIC)
    return np.array(im, np.float32) / 255

def dilate(a, r):
    if r <= 0: return a
    im = Image.fromarray((a * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(2 * r + 1))
    return np.array(im, np.float32) / 255

STYLES = {
    # font, italic shear, fill top/bottom, outline color, outline px(at 1x), shadow
    'silver': (BLACK, -0.22, (255, 255, 255), (150, 150, 160), (20, 20, 25), 2.0, True),
    'silver_up': (BLACK, 0.0, (255, 255, 255), (165, 165, 175), (25, 25, 30), 1.5, True),
    'italic_white': (BOLD, -0.18, (255, 255, 255), (235, 235, 235), (15, 15, 15), 1.5, False),
    'white': (BOLD, 0.0, (255, 255, 255), (235, 235, 235), (20, 20, 30), 1.2, False),
    'plain': (REG, 0.0, (255, 255, 255), (255, 255, 255), None, 0, False),
    'gold': (BLACK, 0.0, (255, 250, 215), (205, 150, 50), (60, 35, 10), 2.0, True),
}

def render(text, box_w, box_h, style, lines=1):
    font, k, top, bot, oc, ow, shadow = STYLES[style]
    oh = ow * SS
    line_h = box_h / lines
    ink_h = max(4, int(line_h - 2 * ow))
    m = text_mask(text, font, ink_h)
    m = shear(m, k)
    pad = int(oh) + 2 * SS
    m = np.pad(m, pad)
    H, W = m.shape
    fill = np.zeros((H, W, 3), np.float32)
    ys = np.linspace(0, 1, H)[:, None]
    for c in range(3): fill[:, :, c] = top[c] * (1 - ys) + bot[c] * ys
    out = np.zeros((H, W, 4), np.float32)
    if oc is not None and ow > 0:
        o = dilate(m, int(round(oh)))
        if shadow:
            sh = np.zeros_like(o); s = int(SS * 1.5); sh[s:, s:] = o[:-s, :-s]; o = np.maximum(o, sh * 0.8)
        out[..., :3] = np.array(oc, np.float32); out[..., 3] = o
    # composite fill over outline
    a = m
    out[..., :3] = out[..., :3] * (1 - a[..., None]) + fill * a[..., None]
    out[..., 3] = np.maximum(out[..., 3], a)
    im = Image.fromarray(np.clip(out * [1, 1, 1, 255], 0, 255).astype(np.uint8), 'RGBA')
    # downsample
    w1, h1 = max(1, round(W / SS)), max(1, round(H / SS))
    im = im.resize((w1, h1), Image.LANCZOS)
    im = im.crop(im.getchannel('A').point(lambda v: 255 if v > 24 else 0).getbbox())
    w1, h1 = im.size
    # fit into box: scale height to box, compress width if needed
    th = box_h
    tw = round(w1 * th / h1)
    if tw > box_w: tw = box_w
    return im.resize((tw, th), Image.LANCZOS)

def apply(dds_bytes, spec):
    arr = np.array(Image.open(io.BytesIO(dds_bytes)).convert('RGBA'))
    for e in spec:
        box = e['box']
        x0, y0, x1, y1 = e.get('clearbox', box)
        mode = e.get('mode', 'clear')
        if mode == 'clear':
            m = e.get('margin', 2)
            ya, yb, xa, xb = max(0, y0 - m), min(arr.shape[0], y1 + m), max(0, x0 - m), min(arr.shape[1], x1 + m)
            ring = np.concatenate([arr[max(0, ya - 2):ya, xa:xb].reshape(-1, 4), arr[yb:yb + 2, xa:xb].reshape(-1, 4),
                                   arr[ya:yb, max(0, xa - 2):xa].reshape(-1, 4), arr[ya:yb, xb:xb + 2].reshape(-1, 4)])
            ring = ring[ring[:, 3] < 40] if len(ring) else ring
            arr[ya:yb, xa:xb] = np.median(ring, axis=0).astype(np.uint8) if len(ring) else 0
        elif mode == 'inpaint':
            # rebuild flat bar background: per-row median over the whole bar width, painted over the text zone
            fx0, fy0, fx1, fy1 = e['fill']; bx0, bx1 = e['bar']
            for y in range(fy0, fy1):
                ref = np.concatenate([arr[y, bx0:bx0 + 10], arr[y, bx1 - 10:bx1]]).astype(np.float32)
                med = np.median(ref, axis=0)
                arr[y, fx0:fx1] = med.astype(np.uint8)
        if not e.get('zh'): continue
        x0, y0, x1, y1 = box
        bw, bh = x1 - x0, y1 - y0
        g = render(e['zh'], bw, bh, e['style'], e.get('lines', 1))
        align = e.get('align', 'left')
        if align == 'left': gx = x0
        elif align == 'right': gx = x1 - g.size[0]
        else: gx = x0 + (bw - g.size[0]) // 2
        base = Image.fromarray(arr, 'RGBA')
        base.alpha_composite(g, (max(0, gx), y0))
        arr = np.array(base)
    return dds_dxt5_rgba(arr), arr

def split(b, n, axis='y'):
    x0, y0, x1, y1 = b
    if axis == 'y':
        h = (y1 - y0) / n
        return [[x0, round(y0 + i * h), x1, round(y0 + (i + 1) * h)] for i in range(n)]
    w = (x1 - x0) / n
    return [[round(x0 + i * w), y0, round(x0 + (i + 1) * w), y1] for i in range(n)]

STAGES_DAY = ['風車島', '屋頂疾奔', '龍之道', '草原要塞', '酷寒邊境', '炎熱沙漠', '叢林兜風', '摩天樓奔馳', '蛋頭樂園']
STAGES_NIGHT = ['白色島嶼', '橘色屋頂', '龍之道', '黏土城堡', '酷寒邊境', '炎熱沙漠', '叢林兜風', '摩天樓奔馳', '蛋頭樂園']

def stage_spec(boxes, style):
    spec = []
    for i in range(9):
        spec.append({'box': boxes[2 * i], 'zh': STAGES_DAY[i], 'style': style})
        spec.append({'box': boxes[2 * i + 1], 'zh': STAGES_NIGHT[i], 'style': style})
    return spec

def specs():
    S = {}
    g = [[1, 1, 209, 30], [257, 2, 462, 30], [0, 33, 188, 62], [256, 33, 440, 62], [1, 65, 160, 94], [258, 65, 417, 94], [2, 97, 198, 126], [257, 98, 442, 127], [0, 129, 139, 158], [257, 129, 396, 158], [0, 161, 158, 190], [257, 161, 415, 190], [1, 193, 236, 223], [258, 193, 493, 223], [0, 225, 256, 254], [256, 225, 512, 254], [0, 257, 179, 286], [257, 257, 436, 286]]
    S['mat_gate_en_001'] = stage_spec(g, 'silver')
    w2 = [[2, 0, 221, 28], [259, 0, 484, 28], [1, 31, 191, 60], [258, 32, 458, 60], [2, 63, 172, 92], [259, 63, 429, 92], [1, 96, 206, 124], [258, 96, 459, 125], [1, 128, 150, 156], [258, 128, 407, 156], [2, 160, 172, 188], [259, 160, 429, 188], [2, 191, 242, 221], [259, 191, 499, 221], [1, 224, 239, 253], [258, 224, 496, 253], [1, 254, 239, 282], [258, 254, 496, 282]]
    w2 = [[b[0], 32 * (i // 2) + 1, b[2], 32 * (i // 2) + 29] for i, b in enumerate(w2)]
    S['mat_worldmap_en_002'] = stage_spec(w2, 'silver')
    w1 = [[157, 0, 254, 28], [125, 30, 253, 59], [131, 64, 253, 92], [162, 95, 253, 123], [150, 127, 253, 155], [140, 159, 254, 188], [154, 191, 254, 219], [65, 223, 254, 251], [59, 254, 254, 283]]
    S['mat_worldmap_en_001'] = [{'box': [max(0, b[0] - 60), 32 * i + 2, b[2] - 6, 32 * i + 28], 'clearbox': b, 'margin': 2, 'zh': z, 'style': 'silver', 'align': 'right'} for i, (b, z) in enumerate(zip(w1, ['阿波托斯', '斯帕戈尼亞', '春南', '馬祖里', '霍斯加', '沙瑪爾', '阿達巴塔', '帝國城', '蛋頭樂園']))]
    pb = [[4, 1, 97, 29], [4, 33, 79, 60]]
    pause = [{'box': pb[0], 'zh': '招式列表', 'style': 'italic_white'}, {'box': pb[1], 'zh': '持有物品', 'style': 'italic_white'}]
    bars = [[128, 100, 256, 126], [128, 130, 256, 156], [128, 160, 256, 186], [128, 190, 256, 216], [128, 220, 256, 246]]
    bz = ['空中', '防禦中', '衝刺中', '蓄力', '長蓄力']
    bar = lambda b, z: {'box': [b[0] + 34, b[1] + 6, b[2] - 34, b[3] - 5], 'fill': [b[0] + 6, b[1] + 3, b[2] - 6, b[3] - 3], 'bar': (b[0] + 4, b[2] - 4), 'zh': z, 'style': 'plain', 'align': 'center', 'mode': 'inpaint'}
    S['SystemCommonCore/mat_pause_en_001'] = pause + [bar(b, z) for b, z in zip(bars, bz)]
    S['Town_Common/mat_pause_en_001'] = pause + [bar(b, z) for b, z in zip(bars[:2], bz[:2])]
    c1 = [[3, 5, 49, 30], [3, 36, 67, 60], [2, 65, 48, 90], [3, 95, 50, 120], [2, 124, 79, 150], [25, 156, 102, 180], [4, 186, 101, 209], [3, 216, 41, 239], [3, 246, 55, 269], [1, 276, 84, 300], [4, 306, 70, 330], [2, 336, 93, 359], [3, 366, 102, 390]]
    cz = ['確定', '返回', '太陽', '下一步', '重播', '切換', '詳細', None, None, '開始', '對話', '拍照', '取消']
    S['mat_comon_en_001'] = [{'box': b, 'zh': z, 'style': 'white', 'align': 'left' if i != 5 else 'center'} for i, (b, z) in enumerate(zip(c1, cz)) if z]
    c2 = [[2, 5, 130, 30], [2, 36, 93, 59], [4, 65, 133, 90]]
    S['mat_comon_en_002'] = [{'box': b, 'zh': z, 'style': 'white'} for b, z in zip(c2, ['移動太陽', '拍照', '對話 / 使用'])]
    t1 = [[47, 28, 82, 46], [174, 28, 207, 46], [27, 53, 103, 72], [170, 56, 217, 71], [103, 79, 154, 99], [39, 106, 91, 125], [153, 105, 233, 124], [41, 131, 87, 150], [175, 131, 212, 151], [48, 157, 84, 177], [177, 158, 209, 177], [33, 184, 98, 203], [139, 185, 246, 202], [85, 209, 169, 229], [19, 236, 112, 254], [163, 237, 226, 254], [108, 262, 145, 281], [48, 287, 84, 307], [159, 287, 229, 307], [35, 313, 94, 333], [163, 314, 225, 332], [59, 339, 200, 358], [81, 365, 177, 385], [81, 391, 176, 411], [88, 417, 165, 436]]
    tz = ['開', '關', '儲存裝置', '新', '音效', '亮度', '選項', None, '字幕', '語音', '按鍵', '聲音', '繼續遊戲', '鏡頭操作', '安裝DLC', '一般', '左右', '上下', '語言設定', '反轉', '開始', None, '讀取遊戲', '新遊戲', '儲存裝置']
    def grow(b, half):
        cy = (b[1] + b[3]) // 2
        cx = (b[0] + b[2]) // 2
        return [max(0, min(b[0], cx - half)), cy - 11, min(256, max(b[2], cx + half)), cy + 11]
    S['mat_title_en_001'] = [{'box': grow(b, 40), 'zh': z, 'style': 'silver_up', 'align': 'center', 'margin': 1} for b, z in zip(t1, tz) if z]
    t2 = [[44, 4, 84, 23], [37, 30, 93, 49], [22, 56, 107, 75], [31, 82, 101, 101], [21, 108, 107, 127], [19, 134, 110, 153]]
    S['mat_title_en_002'] = [{'box': b, 'zh': z, 'style': 'white', 'align': 'center'} for b, z in zip(t2, ['英語', '中文', '法語', '德語', '義大利語', '西班牙語'])]
    ls = [[2, 1, 127, 22], [1, 28, 105, 48], [2, 55, 139, 75], [3, 78, 62, 98], [4, 106, 65, 126], [2, 133, 94, 153], [4, 159, 67, 180], [2, 186, 51, 205], [2, 211, 36, 252], [2, 265, 37, 286]]
    lz = ['快速側移', '光速衝刺', '追蹤攻擊', '加速衝刺', '蹲下', '踩踏', '跳躍', '鏡頭', '走路\n奔跑', '移動']
    S['mat_loadinfo_text_sonic_e'] = [{'box': b, 'zh': z, 'style': 'white', 'lines': z.count('\n') + 1} for b, z in zip(ls, lz)]
    le = [[2, 3, 65, 23], [17, 29, 66, 49], [2, 56, 97, 75], [1, 81, 35, 102], [2, 107, 51, 148], [2, 159, 52, 179], [3, 185, 98, 226], [61, 236, 95, 277]]
    lez = ['衝刺', '防禦', '解放', '攻擊', '攻擊\n投擲', '抓取', '跳躍\n二段跳', '走路\n奔跑']
    S['mat_loadinfo_text_evil_e'] = [{'box': b, 'zh': z, 'style': 'white', 'lines': z.count('\n') + 1} for b, z in zip(le, lez)]
    su = split([20, 0, 250, 96], 3)
    S['mat_su_en_001'] = [{'box': [b[0] + 70, b[1] + 6, b[2] - 70, b[3] - 7], 'fill': [b[0] + 40, b[1] + 2, b[2] - 40, b[3] - 3], 'bar': (b[0] + 12, b[2] - 12), 'zh': z, 'style': 'plain', 'align': 'center', 'mode': 'inpaint'} for b, z in zip(su, ['加速', '防禦', '攻擊'])]
    sh = [[2, 27, 53, 54], [2, 57, 54, 84]]
    S['mat_shop_en_001'] = [{'box': b, 'zh': z, 'style': 'white'} for b, z in zip(sh, ['購買', '販賣'])]
    mz = ['圖鑑', '設定資料', '居民介紹', '敵人圖鑑', '伴手禮', '劇情影片', None, 'BGM欣賞', '蛋頭的機械', '黑暗蓋亞的僕從']
    m1 = [[2, 1, 82, 40], [2, 47, 159, 88], [3, 93, 160, 133], [2, 140, 228, 180], [2, 186, 154, 225], [3, 231, 334, 272], [2, 278, 309, 320], [3, 323, 194, 364], [2, 368, 334, 410], [2, 415, 371, 456]]
    m2 = [[216, 1, 297, 40], [178, 47, 334, 88], [178, 93, 334, 133], [144, 140, 369, 180], [179, 186, 332, 225], [92, 231, 422, 272], [103, 278, 409, 320], [161, 323, 351, 364], [90, 368, 422, 410], [72, 415, 441, 456]]
    S['mat_media_en_001'] = [{'box': b, 'zh': z, 'style': 'gold'} for b, z in zip(m1, mz) if z]
    S['mat_media_en_002'] = [{'box': b, 'zh': z, 'style': 'gold', 'align': 'center'} for b, z in zip(m2, mz) if z]
    nm = [[100, 1, 197, 30], [100, 33, 199, 62], [100, 65, 199, 94]]
    S['ROOT/mat_talk_comon_002'] = [{'box': b, 'zh': z, 'style': 'white', 'margin': 1} for b, z in zip(nm, ['索尼克', '塔爾斯', '奇普'])]
    S['mat_status_en_001'] = [{'box': [12, 488, 64, 509], 'zh': '結束', 'style': 'italic_white'}]
    return S

def lookup(S, archive, name):
    return S.get(archive + '/' + name) or S.get(name)
