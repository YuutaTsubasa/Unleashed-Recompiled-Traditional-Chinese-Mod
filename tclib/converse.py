"""Rebuild FCO (text) / FTE (font table) / font pages of one archive with Chinese text.

FCO messages are lists of character codes:
  code < 100        control code ({cN}, 0 = line break)
  100 <= code < 200 button icon N ({iN})
  code >= 200       glyph index (code - 200) into the archive's FTE table
Each archive gets its own FTE containing exactly the glyphs its text needs.
"""
import collections
import re
import unicodedata
import numpy as np
from PIL import Image, ImageDraw
from . import config, images
from .archive import read_ar, write_ar, ar_extras, write_arl
from .dxt import dds_dxt5
from .fco import read_fco, write_fco, read_fte, write_fte

TOKEN = re.compile(r'\{([ci?])(\d+)\}')  # {?N} = raw code N


def tokenize(s):
    out = []
    pos = 0
    for m in TOKEN.finditer(s):
        out += list(s[pos:m.start()])
        out.append((m.group(1), int(m.group(2))))
        pos = m.end()
    out += list(s[pos:])
    return out


# ---------------------------------------------------------------- glyph rendering
_calib = {}


def calib(h):
    """font size + y offset so an ideograph's ink spans ~0.17h..0.87h, like the original font."""
    if h not in _calib:
        for s in range(6, 200):
            l, t, r, b = config.zh_font(s).getbbox('國')
            if b - t >= 0.70 * h:
                _calib[h] = (s, round(0.17 * h) - t)
                break
    return _calib[h]


def render_glyph(ch, h):
    """returns (image array or None for blank, advance width)"""
    fw = round(0.8 * h)
    if ch == ' ':
        return None, round(0.4 * h)
    if ch == '　':
        return None, fw
    size, yoff = calib(h)
    f = config.font_for(ch, size)
    if unicodedata.east_asian_width(ch) in 'WF':
        w = fw
        im = Image.new('L', (w, h))
        l, t, r, b = f.getbbox(ch)
        ImageDraw.Draw(im).text(((w - (r - l)) / 2 - l, yoff), ch, font=f, fill=255)
    else:
        l, t, r, b = f.getbbox(ch)
        w = max(int(np.ceil(max(f.getlength(ch), r))) + 2, 4)
        im = Image.new('L', (w, h))
        ImageDraw.Draw(im).text((1, yoff), ch, font=f, fill=255)
    return np.array(im), w


# ---------------------------------------------------------------- one FTE group
def build_fte_group(fdict, fte_name, fco_names, texts, stats, page_size):
    hdr, texs, chars = read_fte(fdict[fte_name])
    nic = next(i for i, c in enumerate(chars) if c[0] >= 2)   # leading entries are button icons
    icon_entries = chars[:nic]
    base_tex = texs[2][0].rsplit('_', 1)[0]
    orig_pages = [t[0] for t in texs[2:]]

    def cell_height(msg):
        """glyph cell height the original text used (keeps big/small fonts as they were)"""
        hs = collections.Counter()
        for c in msg:
            if c >= 200:
                ti, l, t, r, b = chars[c - 200]
                hh = round((b - t) * texs[ti][2])
                if hh:
                    hs[hh] += 1
        return hs.most_common(1)[0][0] if hs else None

    parsed = {n: read_fco(fdict[n]) for n in fco_names}
    default_h = collections.Counter()
    for fhdr, groups in parsed.values():
        for gname, cells in groups:
            for c in cells:
                hh = cell_height(c['msg'])
                if hh:
                    default_h[hh] += len(c['msg'])
    dh = default_h.most_common(1)[0][0] if default_h else 35

    # pass 1: tokenize the Chinese text of every cell
    glyph_keys = collections.OrderedDict()
    for n, (fhdr, groups) in parsed.items():
        ftexts = texts.get(n, {})
        for gname, cells in groups:
            seen = {}
            for c in cells:
                ck = gname + '/' + c['name']
                occ = seen.get(ck, 0)
                seen[ck] = occ + 1
                zh = ftexts.get('%s#%d' % (ck, occ))
                if zh is None:
                    stats['missing_cell'] += 1
                    zh = ''
                else:
                    stats['translated'] += 1
                hh = cell_height(c['msg']) or dh
                c['_toks'] = tokenize(zh)
                c['_h'] = hh
                for t in c['_toks']:
                    if isinstance(t, str):
                        glyph_keys.setdefault((t, hh), None)

    # pass 2: render + pack glyphs into font pages
    P = page_size
    pages = []
    state = {'x': 0, 'y': 0, 'rowh': 0}
    new_chars = list(icon_entries)
    index = {}

    def new_page():
        pages.append(np.zeros((P, P), np.uint8))
        state.update(x=0, y=0, rowh=0)

    new_page()
    for (ch, hh) in glyph_keys:
        img, w = render_glyph(ch, hh)
        if state['x'] + w > P:
            state['x'] = 0
            state['y'] += state['rowh'] + 1
            state['rowh'] = 0
        if state['y'] + hh > P:
            new_page()
        x, y, cur = state['x'], state['y'], pages[-1]
        if img is not None:
            cur[y:y + hh, x:x + w] = np.maximum(cur[y:y + hh, x:x + w], img)
            rect = (x / P, y / P, (x + w) / P, (y + hh) / P)
        else:
            rect = (x / P, y / P, (x + w) / P, y / P)
        index[(ch, hh)] = len(new_chars)
        new_chars.append((2 + len(pages) - 1,) + rect)
        state['x'] += w + 1
        state['rowh'] = max(state['rowh'], hh)

    page_names = [orig_pages[i] if i < len(orig_pages) else f'{base_tex}_{i:03d}' for i in range(len(pages))]
    new_texs = texs[:2] + [(pn, P, P) for pn in page_names]

    # pass 3: encode the FCOs
    out_files = {}
    for n, (fhdr, groups) in parsed.items():
        for gname, cells in groups:
            for c in cells:
                msg = []
                for t in c.pop('_toks'):
                    if isinstance(t, tuple):
                        msg.append(t[1] if t[0] in 'c?' else 100 + t[1])
                    else:
                        msg.append(200 + index[(t, c['_h'])])
                c.pop('_h')
                L = len(msg)
                c['msg'] = msg
                c['colors'] = [[0, L - 1, col[2], col[3]] for col in c['colors']]
                c['end'] = [0, L - 1, c['end'][2]]
                c['hl'] = []    # highlight ranges refer to Japanese character positions
                c['subs'] = []  # furigana
        out_files[n] = write_fco(fhdr, groups)
    out_files[fte_name] = write_fte(hdr, new_texs, new_chars)
    for pn, pg in zip(page_names, pages):
        out_files[pn + '.dds'] = dds_dxt5(pg)
    stats['glyphs'] += len(glyph_keys)
    stats['pages'] += len(pages)
    return out_files, page_names, orig_pages, pages


# ---------------------------------------------------------------- whole archive
def build_archive(arc_path, arc_name, texts, stats, unsplit=False):
    """returns (ar bytes, arl bytes) or None when nothing in the archive needs changing.

    unsplit: the archive is a single .ar file (split count 0 in its .arl, e.g. cutscene subtitles)
    rather than .ar.00 splits; the .arl must say so or the game looks for a missing .ar.00.
    """
    files = read_ar(arc_path)
    fdict = dict(files)
    ftes = [n for n, _ in files if n.endswith('.fte')]
    specs = images.specs()
    out_files = {}
    for n, d in files:
        if n.endswith('.dds'):
            sp = images.lookup(specs, arc_name, n[:-4])
            if sp:
                out_files[n] = images.apply(d, sp)[0]
                stats['images'] += 1
    if not ftes and not out_files:
        return None

    groups_by_fte = collections.OrderedDict((f, []) for f in ftes)
    conv = [f for f in ftes if 'ConverseMain' in f]
    for n, _ in files:
        if n.endswith('.fco'):
            own = n[:-4] + '.fte'
            groups_by_fte[own if own in fdict else (conv[0] if conv else ftes[0])].append(n)

    page_info = {}
    for fte_name, fco_names in groups_by_fte.items():
        if not fco_names:
            continue
        # 512px pages like the original; switch to 1024px if that would need more textures than before
        local = collections.Counter()
        of, page_names, orig_pages, pages = build_fte_group(fdict, fte_name, fco_names, texts, local, 512)
        if len(pages) > max(1, len(orig_pages)):
            local = collections.Counter()
            of, page_names, orig_pages, pages = build_fte_group(fdict, fte_name, fco_names, texts, local, 1024)
        stats.update(local)
        out_files.update(of)
        page_info[fte_name] = (page_names, orig_pages)

    names = [n for n, _ in files]
    for fte_name, (page_names, orig_pages) in page_info.items():
        names = [n for n in names if not (n.endswith('.dds') and n[:-4] in orig_pages and n[:-4] not in page_names)]
        for i, pn in enumerate(page_names):
            if pn + '.dds' not in names:
                names.insert(names.index(fte_name) + 1 + i, pn + '.dds')
    entries = [(n, out_files.get(n, fdict.get(n))) for n in names]
    extra, align = ar_extras(arc_path)
    ar = write_ar(entries, align, extra)
    return ar, write_arl(names, [] if unsplit else [len(ar)])
