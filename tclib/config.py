"""Font configuration shared by the text and image builders."""
from PIL import ImageFont
from fontTools.ttLib import TTCollection, TTFont

ZH_FONT = 'C:/Windows/Fonts/NotoSansTC-VF.ttf'   # Noto Sans TC (variable)
FALLBACK_FONT = 'C:/Windows/Fonts/YuGothM.ttc'   # for the few kana left in debug strings
TEXT_WEIGHT = 500                                # Medium

_cmap = None
_cache = {}


def setup(zh_font=None, fallback_font=None):
    global ZH_FONT, FALLBACK_FONT, _cmap
    if zh_font:
        ZH_FONT = zh_font
    if fallback_font:
        FALLBACK_FONT = fallback_font
    _cmap = None
    _cache.clear()


def zh_cmap():
    global _cmap
    if _cmap is None:
        fonts = TTCollection(ZH_FONT).fonts if ZH_FONT.lower().endswith('.ttc') else [TTFont(ZH_FONT)]
        _cmap = set(fonts[0].getBestCmap().keys())
    return _cmap


def zh_font(size, weight=TEXT_WEIGHT):
    key = (ZH_FONT, size, weight)
    if key not in _cache:
        f = ImageFont.truetype(ZH_FONT, size)
        try:
            f.set_variation_by_axes([weight])
        except Exception:
            pass  # static (non-variable) font
        _cache[key] = f
    return _cache[key]


def font_for(ch, size):
    """Chinese font if it has the glyph, otherwise the fallback font."""
    if ord(ch) in zh_cmap():
        return zh_font(size)
    key = (FALLBACK_FONT, size)
    if key not in _cache:
        _cache[key] = ImageFont.truetype(FALLBACK_FONT, size)
    return _cache[key]
