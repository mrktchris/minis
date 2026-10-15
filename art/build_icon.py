"""Build the minis app icon: two crossed katanas on a terracotta disc (the V6 Claude ronin palette).

    python art/build_icon.py [--preview PNG]

Writes assets/icon/minis.ico (16, 20, 24, 32, 40, 48, 64, 256) and assets/icon/minis-256.png.  Deterministic: no
randomness, no timestamps, the .ico is written by hand (32-bit BMP entries below 256, PNG at 256) so every size holds
exactly the pixels drawn here - Windows never resamples one size into another.

Every size is drawn natively on its own grid (45-degree blades are crisp at any size); the small sizes (16, 20, 24) get
their own tuning in SIZES, and `FIX` holds hand-placed pixels.  40/48/64/256 are drawn at 20/24/32/64 and scaled by an
integer (nearest neighbour), which keeps the chunky pixel look instead of a blurred downscale.
`--preview` renders every size zoomed, on the dark (#202020) and light (#F3F3F3) taskbar colours, for a look.
"""
from __future__ import annotations
import argparse, io, struct, sys
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'assets' / 'icon'

DARK = (0x2A, 0x22, 0x30, 255)        # outline, hilts
TERRA = (0xD9, 0x77, 0x57, 255)       # the ronin's kimono
TERRA_SH = (0xBF, 0x5A, 0x3C, 255)    # disc shade (lower right)
TERRA_HI = (0xE8, 0x96, 0x78, 255)    # disc highlight (upper left)
CREAM = (0xF2, 0xE6, 0xD8, 255)       # blades
STEEL_SH = (0xC9, 0xB9, 0xA8, 255)    # blade shade side
GOLD = (0xFF, 0xB8, 0x6B, 255)        # tsuba (hand guard)
CLEAR = (0, 0, 0, 0)

ICO_SIZES = (16, 20, 24, 32, 40, 48, 64, 256)
# native grid for each icon size: (drawn at, integer scale)
NATIVE = {16: (16, 1), 20: (20, 1), 24: (24, 1), 32: (32, 1), 40: (20, 2), 48: (24, 2), 64: (32, 2), 256: (64, 4)}

# per-grid design: blade width (px), blade margin from the corner, hilt length, shading on/off, blade outline
SIZES = {
    # under: a dark line under each 1 px blade (the X stays bold at 16/20); guard: the gold tsuba (noise below 24 px)
    16: dict(blade=1, margin=2, hilt=3, shade=False, edge=False, under=True, guard=False),
    20: dict(blade=1, margin=2, hilt=4, shade=True, edge=False, under=True, guard=False),
    24: dict(blade=2, margin=3, hilt=4, shade=True, edge=True, under=False, guard=True),
    32: dict(blade=2, margin=4, hilt=6, shade=True, edge=True, under=False, guard=True),
    64: dict(blade=4, margin=8, hilt=12, shade=True, edge=True, under=False, guard=True),
}
FIX = {}                                  # grid -> {(x, y): colour}: hand-placed pixels applied last


def disc_mask(n):
    """Filled circle on an n x n grid, symmetric in both axes (pixel centres within radius n/2)."""
    c = (n - 1) / 2.0
    r2 = (n / 2.0) ** 2 - 0.25 * (n <= 20)          # small grids: shave the 4 flat edge runs so it reads as round
    return {(x, y) for y in range(n) for x in range(n) if (x - c) ** 2 + (y - c) ** 2 <= r2}


def outline_of(mask):
    return {(x, y) for (x, y) in mask if any((x + dx, y + dy) not in mask for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))}


def blade_cells(n, p, flip):
    """The cells of one katana on an n-grid: a 45-degree band from the top corner (tip) to the bottom corner (pommel).
    flip=False runs top-left -> bottom-right.  -> (blade cells, hilt cells, guard cells), each a list in drawing order."""
    m, w, hl = p['margin'], p['blade'], p['hilt']
    blade, hilt, guard = [], [], []
    ext = p.get('pommel', 1)                            # the hilt runs this far past the disc: a pommel nub outside the rim
    length = n - 2 * m + ext
    for i in range(length):
        for k in range(w):
            x, y = m + i + k, m + i                     # a w-wide band along the diagonal
            if x >= n - m + ext or y >= n:
                continue
            cell = (n - 1 - x, y) if flip else (x, y)
            if i >= length - ext - hl:
                hilt.append(cell)
            else:
                blade.append(cell)
    # the tsuba: a short bar across the blade just above the hilt
    g = length - ext - hl - 1
    for d in range(-1, w + 1):
        x, y = m + g + d + 1, m + g - d + 0
        if 0 <= x < n and 0 <= y < n:
            guard.append((n - 1 - x, y) if flip else (x, y))
    return blade, hilt, guard


def draw(n):
    p = SIZES[n]
    im = Image.new('RGBA', (n, n), CLEAR)
    px = im.load()
    disc = disc_mask(n)
    c = (n - 1) / 2.0
    for (x, y) in disc:
        col = TERRA
        if p['shade']:
            d = (x - c) + (y - c)                       # light from the upper left
            if d > n * 0.42:
                col = TERRA_SH
            elif d < -n * 0.5:
                col = TERRA_HI
        px[x, y] = col
    for (x, y) in outline_of(disc):
        px[x, y] = DARK
    blades = [blade_cells(n, p, flip) for flip in (True, False)]
    if p['under']:                                      # all dark lines first, so no blade's line cuts the other blade
        for blade, hilt, _ in blades:
            for (x, y) in blade:
                if y + 1 < n and px[x, y + 1][3]:
                    px[x, y + 1] = DARK
    for blade, hilt, guard in blades:                   # the second blade is drawn over the first at the crossing
        if not p['guard']:
            guard = []
        if p['edge']:                                   # a dark rim so the blade reads on the cream-ish highlight too
            for (x, y) in blade + hilt:
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    q = (x + dx, y + dy)
                    if 0 <= q[0] < n and 0 <= q[1] < n and q not in blade and q not in hilt and q not in guard:
                        if px[q][3] and px[q] != CREAM and px[q] != STEEL_SH:
                            px[q] = DARK
        for j, (x, y) in enumerate(blade):
            lower = p['blade'] > 1 and (j % p['blade']) == 0
            px[x, y] = STEEL_SH if lower and p['shade'] else CREAM
        for (x, y) in hilt:
            px[x, y] = DARK
            if p['under'] and y + 1 < n:              # 1 px blades: a 2 px grip, so the hilt reads as a hilt
                px[x, y + 1] = DARK
        for (x, y) in guard:
            px[x, y] = GOLD
    for (x, y), col in FIX.get(n, {}).items():
        px[x, y] = col
    return im


def icon_images():
    out = {}
    for size in ICO_SIZES:
        grid, k = NATIVE[size]
        im = draw(grid)
        out[size] = im if k == 1 else im.resize((size, size), Image.NEAREST)
    return out


def _png_bytes(im):
    buf = io.BytesIO()
    im.save(buf, format='PNG', optimize=False)
    return buf.getvalue()


def _bmp_entry(im):
    """A 32-bit BGRA DIB for an .ico entry: BITMAPINFOHEADER (height doubled for the AND mask), bottom-up rows, then a
    1-bit AND mask (all transparent where alpha is 0)."""
    w, h = im.size
    hdr = struct.pack('<IiiHHIIiiII', 40, w, h * 2, 1, 32, 0, 0, 0, 0, 0, 0)
    rows = []
    data = im.tobytes('raw', 'BGRA')
    for y in range(h - 1, -1, -1):
        rows.append(data[y * w * 4:(y + 1) * w * 4])
    mask_stride = ((w + 31) // 32) * 4
    a = im.getchannel('A').load()
    mask = bytearray()
    for y in range(h - 1, -1, -1):
        row = bytearray(mask_stride)
        for x in range(w):
            if a[x, y] == 0:
                row[x // 8] |= 0x80 >> (x % 8)
        mask += row
    return hdr + b''.join(rows) + bytes(mask)


def ico_bytes(images):
    """images: {size: RGBA image} -> .ico file bytes (ICONDIR + entries; PNG for 256, BMP below)."""
    sizes = sorted(images)
    blobs = [_png_bytes(images[s]) if s >= 256 else _bmp_entry(images[s]) for s in sizes]
    out = struct.pack('<HHH', 0, 1, len(sizes))
    off = 6 + 16 * len(sizes)
    for s, b in zip(sizes, blobs):
        out += struct.pack('<BBBBHHII', s % 256, s % 256, 0, 0, 1, 32, len(b), off)
        off += len(b)
    return out + b''.join(blobs)


def preview(images, zoom_to=128):
    """Every size zoomed (nearest) to about `zoom_to` px, on a dark and a light band, plus a 1:1 row at the true size."""
    pad = 16
    cols = [images[s] for s in ICO_SIZES]
    cells = [im.resize((zoom_to * im.width // 256,) * 2, Image.NEAREST) if im.width > zoom_to
             else im.resize((im.width * max(1, zoom_to // im.width),) * 2, Image.NEAREST) for im in cols]
    cells[-1] = cols[-1].resize((zoom_to, zoom_to), Image.NEAREST)      # 256 = 64 x 4: an exact halving
    cw = max(c.width for c in cells) + pad
    W = cw * len(cells) + pad
    H = (zoom_to + pad) * 2 + (64 + pad) * 2 + pad
    sheet = Image.new('RGBA', (W, H), (128, 128, 128, 255))
    y = pad
    for bg in ((0x20, 0x20, 0x20, 255), (0xF3, 0xF3, 0xF3, 255)):
        band = Image.new('RGBA', (W, zoom_to + pad), bg)
        sheet.paste(band, (0, y - pad // 2))
        for i, c in enumerate(cells):
            sheet.alpha_composite(c, (pad + i * cw, y + (zoom_to - c.height) // 2))
        y += zoom_to + pad
    for bg in ((0x20, 0x20, 0x20, 255), (0xF3, 0xF3, 0xF3, 255)):        # true size, as the taskbar and tray show it
        band = Image.new('RGBA', (W, 64 + pad), bg)
        sheet.paste(band, (0, y - pad // 2))
        x = pad
        for s in ICO_SIZES[:-1]:
            sheet.alpha_composite(images[s], (x, y + (64 - s) // 2))
            x += s + pad
        y += 64 + pad
    return sheet


def build(out_dir=OUT, preview_path=None):
    images = icon_images()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / 'minis.ico').write_bytes(ico_bytes(images))
    (out_dir / 'minis-256.png').write_bytes(_png_bytes(images[256]))
    if preview_path:
        Path(preview_path).parent.mkdir(parents=True, exist_ok=True)
        preview(images).save(preview_path)
    return images


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--preview', default=None, help='also write a zoomed preview sheet here')
    a = ap.parse_args(argv)
    build(preview_path=a.preview)
    print(f'wrote {OUT / "minis.ico"} ({", ".join(map(str, ICO_SIZES))}) and {OUT / "minis-256.png"}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
