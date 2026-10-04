"""Build the Sonic Unleashed Traditional Chinese mod from your own game files.

    python build_mod.py --game "D:/Games/UnleashedRecompiled"

--game is the Unleashed Recompiled install folder (the one containing game/,
update/, dlc/ and UnleashedRecomp.exe). The mod is written to dist/UnleashedTC.
No game data is stored in this repository; everything is generated locally.
"""
import argparse
import collections
import glob
import json
import os
import shutil
import sys
import tempfile
import time

from tclib import config, images
from tclib.archive import decompress, read_ar, write_ar, ar_extras, read_arl, write_arl
from tclib.converse import build_archive
from tclib.fco import read_fco, write_fco

HERE = os.path.dirname(os.path.abspath(__file__))

# WorldMap text exists in the base game and (extended) in each DLC; the mod ships one
# merged WorldMap. Order matters: earlier sources provide the base layout.
DLC_PRIORITY = ['Apotos', 'Empire', 'Holoska', 'Spagonia', 'Mazuri', 'Chun']
# Shared (non-language) archives holding the Japanese speaker name plates.
SHARED_ARCHIVES = ['Town_Common', 'SystemCommonCore']


def log(msg):
    print(msg, flush=True)


def merge_worldmap(sources, dst):
    """Union of the cells of several WorldMap archives; the first source is the base."""
    base = read_ar(sources[0])
    others = [dict(read_ar(p)) for p in sources[1:]]
    out = []
    for name, data in base:
        if name.endswith('.fco'):
            fhdr, groups = read_fco(data)
            by_name = {g: cells for g, cells in groups}
            for other in others:
                if name not in other:
                    continue
                for gname, cells in read_fco(other[name])[1]:
                    if gname not in by_name:
                        by_name[gname] = []
                        groups.append((gname, by_name[gname]))
                    have = collections.Counter(c['name'] for c in by_name[gname])
                    count = collections.Counter()
                    for c in cells:
                        count[c['name']] += 1
                        if count[c['name']] > have[c['name']]:
                            c = dict(c, msg=[], hl=[], subs=[])
                            c['colors'] = [[0, -1, x[2], x[3]] for x in c['colors']]
                            c['end'] = [0, -1, c['end'][2]]
                            by_name[gname].append(c)
                            have[c['name']] += 1
            data = write_fco(fhdr, groups)
        out.append((name, data))
    extra, align = ar_extras(sources[0])
    open(dst, 'wb').write(write_ar(out, align, extra))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--game', required=True, help='Unleashed Recompiled folder (contains game/ and dlc/)')
    ap.add_argument('--out', default=os.path.join(HERE, 'dist', 'UnleashedTC'), help='output mod folder')
    ap.add_argument('--font', default=config.ZH_FONT, help='Noto Sans TC font file (variable font recommended)')
    ap.add_argument('--fallback-font', default=config.FALLBACK_FONT, help='Japanese font for leftover kana')
    ap.add_argument('--zip', action='store_true', help='also create a zip next to the mod folder')
    args = ap.parse_args()

    game = os.path.join(args.game, 'game')
    if not os.path.isdir(os.path.join(game, 'Languages', 'Japanese')):
        sys.exit(f'找不到 {game}/Languages/Japanese，請確認 --game 指向 Unleashed Recompiled 的安裝資料夾。')
    for f in (args.font, args.fallback_font):
        if not os.path.exists(f):
            sys.exit(f'找不到字型 {f}（可用 --font / --fallback-font 指定）。')
    config.setup(args.font, args.fallback_font)

    texts = json.load(open(os.path.join(HERE, 'data', 'zh_text.json'), encoding='utf-8'))
    out = args.out
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(out)
    stats = collections.Counter()
    t0 = time.time()

    with tempfile.TemporaryDirectory(prefix='unleashed_tc_') as work:
        jobs = []  # (decompressed archive, text key, archive name, out .ar path, out .arl path)

        # language archives
        lang_dir = os.path.join(game, 'Languages', 'Japanese')
        for src in sorted(glob.glob(os.path.join(lang_dir, '*.ar.00'))):
            name = os.path.basename(src)[:-6]
            dst = os.path.join(work, 'lang', name + '.ar')
            decompress(src, dst)
            jobs.append([dst, 'Languages/' + name, name,
                         os.path.join(out, 'Languages', 'Japanese', name + '.ar.00'),
                         os.path.join(out, 'Languages', 'Japanese', name + '.arl')])

        # WorldMap: merge DLC versions (when installed) with the base game
        wm_sources = []
        dlcs = sorted(glob.glob(os.path.join(args.game, 'dlc', '*', 'Languages', 'Japanese', 'WorldMap.ar.00')))
        for key in DLC_PRIORITY:
            for p in dlcs:
                if key.lower() in p.lower() and p not in wm_sources:
                    wm_sources.append(p)
        wm_sources.append(os.path.join(lang_dir, 'WorldMap.ar.00'))
        if len(wm_sources) > 1:
            dec = []
            for i, p in enumerate(wm_sources):
                d = os.path.join(work, 'wm', f'{i}.ar')
                decompress(p, d)
                dec.append(d)
            merged = os.path.join(work, 'wm', 'WorldMap.ar')
            # identical DLC copies add nothing; the zh_text layout was built from Apotos + Chun-nan + base
            merge_worldmap(dec, merged)
            for j in jobs:
                if j[2] == 'WorldMap':
                    j[0] = merged
            log(f'WorldMap：合併 {len(wm_sources) - 1} 個 DLC 版本')

        # cutscene subtitles
        sub_dir = os.path.join(game, 'Inspire', 'subtitle', 'Japanese')
        for src in sorted(glob.glob(os.path.join(sub_dir, '*.ar'))):
            name = os.path.basename(src)[:-3]
            dst = os.path.join(work, 'sub', name + '.ar')
            decompress(src, dst)
            jobs.append([dst, 'Subtitle/' + name, name,
                         os.path.join(out, 'Inspire', 'subtitle', 'Japanese', name + '.ar'),
                         os.path.join(out, 'Inspire', 'subtitle', 'Japanese', name + '.arl')])

        for arc, key, name, out_ar, out_arl in jobs:
            r = build_archive(arc, name, texts.get(key, {}), stats)
            if r is None:
                continue
            os.makedirs(os.path.dirname(out_ar), exist_ok=True)
            open(out_ar, 'wb').write(r[0])
            open(out_arl, 'wb').write(r[1])
            log(f'  {key}')

        # shared archives: only the name plate texture changes
        specs = images.specs()
        for name in SHARED_ARCHIVES:
            arl_tmp = os.path.join(work, 'shared', name + '.arl')
            decompress(os.path.join(game, name + '.arl'), arl_tmp)
            sizes, names_blob = read_arl(arl_tmp)
            for i in range(len(sizes)):
                src = os.path.join(work, 'shared', f'{name}.ar.{i:02d}')
                decompress(os.path.join(game, f'{name}.ar.{i:02d}'), src)
                changed = False
                entries = []
                for n, d in read_ar(src):
                    sp = specs.get('ROOT/' + n[:-4]) if n.endswith('.dds') else None
                    if sp:
                        d = images.apply(d, sp)[0]
                        changed = True
                        stats['images'] += 1
                    entries.append((n, d))
                if changed:
                    extra, align = ar_extras(src)
                    data = write_ar(entries, align, extra)
                    sizes[i] = len(data)
                    open(os.path.join(out, f'{name}.ar.{i:02d}'), 'wb').write(data)
            open(os.path.join(out, name + '.arl'), 'wb').write(write_arl([], sizes) + names_blob)
            log(f'  {name}（名牌）')

    for f in os.listdir(os.path.join(HERE, 'mod_template')):
        shutil.copy(os.path.join(HERE, 'mod_template', f), out)

    log(f'完成：{stats["translated"]} 個文字格、{stats["images"]} 張圖片、{stats["pages"]} 張字型貼圖'
        f'（{time.time() - t0:.0f} 秒）→ {out}')
    if stats['missing_cell']:
        log(f'注意：{stats["missing_cell"]} 個文字格沒有對應譯文（可能是遊戲版本或 DLC 不同），已留白。')
    if args.zip:
        z = shutil.make_archive(out, 'zip', os.path.dirname(out), os.path.basename(out))
        log(f'壓縮檔：{z}')


if __name__ == '__main__':
    main()
