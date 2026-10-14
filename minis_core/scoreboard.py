"""The right-side taskbar widget (scoreboard): pure layout + rendering + hit-testing.  The director process hosts it
in a third layered window (minis.py Scoreboard) just left of the centred icon cluster.

Shows "A W-L  vs  B W-L", the mode (taskbar / arena / paused), round HP bars during a bout, and three buttons:
Pause/Resume, Arena, Bout now.  Only the buttons are solid to the mouse (hit()); everything else is click-through.
Numbers, names of programs and enums only: never window titles or content.
"""
from __future__ import annotations
from PIL import Image, ImageDraw

from . import config as cfgmod
from .render import font, text, TRACK, AMBER, RED

W, H = 190, 40
BTN_Y0, BTN_Y1 = 26, 38
BUTTONS = (('pause', (3, BTN_Y0, 63, BTN_Y1)), ('arena', (66, BTN_Y0, 124, BTN_Y1)), ('bout', (127, BTN_Y0, 187, BTN_Y1)))
BG, EDGE, INK, DIM = (18, 18, 22, 205), (90, 90, 104, 190), (230, 230, 240), (160, 160, 175)
BTN_BG, BTN_EDGE, BTN_ON = (40, 40, 48, 255), (120, 120, 136, 255), (70, 70, 84, 255)
MODE_COLOR = {'taskbar': (150, 220, 150), 'arena': (255, 196, 80), 'paused': (255, 120, 110)}


def left_x(cfg) -> int:
    """Screen x of the widget: cfg['scoreboard_x'], else just left of the icon cluster (zone end + 36, i.e. x 936 here)."""
    v = cfg.get('scoreboard_x')
    if v is None:
        v = int(cfg['zone'][1]) + 36 - W
    return int(v)


def enabled(cfg) -> bool:
    return bool(cfg.get('scoreboard', True))


def hit(x, y):
    """-> button name under client point (x, y) in logical px, or None (click-through)."""
    for name, (x0, y0, x1, y1) in BUTTONS:
        if x0 <= x <= x1 and y0 <= y <= y1:
            return name
    return None


def labels(state):
    paused = state.get('mode') == 'paused' or state.get('paused')
    return {'pause': 'Resume' if paused else 'Pause', 'arena': 'Exit arena' if state.get('arena') else 'Arena', 'bout': 'Bout now'}


def _fit(d, s, maxw, size, bold=True):
    f = font(size, bold)
    if d.textlength(s, font=f) <= maxw:
        return s
    while len(s) > 1 and d.textlength(s + '.', font=f) > maxw:
        s = s[:-1]
    return s + '.'


_cache = {}


def signature(state):
    hp = state.get('hp') or {}
    return (tuple(state.get('names', {}).get(s) for s in 'ab'), tuple(tuple(state.get('records', {}).get(s, (0, 0))) for s in 'ab'),
            state.get('mode'), bool(state.get('arena')), bool(state.get('paused')), hp.get('a'), hp.get('b'),
            tuple(sorted((state.get('wins') or {}).items())), state.get('winners'), state.get('pressed'),
            tuple(None if v is None else int(v) for v in (state.get('spark') or ())))


def render(state) -> Image.Image:
    """state: names {a,b}, records {a: (w, l), b: (w, l)}, mode, arena, paused, hp {a, b} | None, wins {a, b}, winners, pressed."""
    key = signature(state)
    im = _cache.get(key)
    if im is None:
        if len(_cache) > 64:
            _cache.clear()
        im = _cache[key] = _render(state)
    return im


def _render(state):
    im = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, W - 1, H - 1], 5, fill=BG, outline=EDGE)
    names = state.get('names') or {}
    recs = state.get('records') or {}
    hp = state.get('hp') or {}
    wins = state.get('wins') or {}
    # line 1: records
    a, b = names.get('a') or '-', names.get('b') or '-'
    ra, rb = recs.get('a', (0, 0)), recs.get('b', (0, 0))
    sa = f'{_fit(d, a, 44, 9)} {ra[0]}-{ra[1]}'
    sb = f'{_fit(d, b, 44, 9)} {rb[0]}-{rb[1]}'
    text(d, (5, 2), sa, INK, 9)
    vs = 'vs'
    text(d, (W // 2 - int(d.textlength(vs, font=font(9, False))) // 2, 2), vs, DIM, 9, False)
    text(d, (W - 5 - int(d.textlength(sb, font=font(9, True))), 2), sb, INK, 9)
    # line 2: mode, or HP bars during a bout
    mode = state.get('mode') or 'taskbar'
    if hp.get('a') is not None or hp.get('b') is not None:
        for slot, x0, flip in (('a', 5, False), ('b', W - 5 - 70, True)):
            v = hp.get(slot)
            v = 0 if v is None else max(0, min(100, int(v)))
            fill = (150, 220, 150) if v > 50 else (AMBER if v > 25 else RED)
            d.rectangle([x0, 15, x0 + 70, 21], fill=TRACK + (255,))
            w = int(70 * v / 100.0)
            if w:
                if flip:
                    d.rectangle([x0 + 70 - w, 15, x0 + 70, 21], fill=fill + (255,))
                else:
                    d.rectangle([x0, 15, x0 + w, 21], fill=fill + (255,))
        rnd = f"{wins.get('a', 0)}:{wins.get('b', 0)}"
        text(d, (W // 2 - int(d.textlength(rnd, font=font(9, True))) // 2, 13), rnd, MODE_COLOR['arena'], 9)
    else:
        word = {'taskbar': 'taskbar', 'arena': 'ARENA', 'paused': 'PAUSED'}.get(mode, mode)
        text(d, (5, 13), word, MODE_COLOR.get(mode, DIM), 9, False)
        win = 'dec' if state.get('winners') != 'random' else 'rnd'
        s = f'win: {win}'
        text(d, (W - 5 - int(d.textlength(s, font=font(9, False))), 13), s, DIM, 9, False)
        spark = list(state.get('spark') or [])
        if spark:                                              # 7-day context sparkline (history.json: numbers + dates only)
            x0 = 72
            for i, v in enumerate(spark[-7:]):
                x = x0 + i * 6
                d.rectangle([x, 14, x + 4, 23], fill=TRACK + (255,))
                if v is not None:
                    h = max(1, int(round(9 * max(0.0, min(100.0, float(v))) / 100.0)))
                    col = (150, 220, 150) if v < 70 else (AMBER if v < 90 else RED)
                    d.rectangle([x, 23 - h, x + 4, 23], fill=col + (255,))
    # buttons
    lab = labels(state)
    for name, (x0, y0, x1, y1) in BUTTONS:
        on = state.get('pressed') == name
        d.rounded_rectangle([x0, y0, x1, y1], 3, fill=BTN_ON if on else BTN_BG, outline=BTN_EDGE)
        s = _fit(d, lab[name], x1 - x0 - 6, 9)
        text(d, (x0 + (x1 - x0 - int(d.textlength(s, font=font(9, True)))) // 2, y0 + 1), s, INK, 9)
    return im


class Model:
    """Builds the render state from plain inputs: assignment, bus payloads, record.json, control flags."""

    def __init__(self, cfg):
        self.cfg = cfg

    @staticmethod
    def names_from(assign, lib=None):
        out = {}
        for s in 'ab':
            a = (assign or {}).get(s) if isinstance(assign, dict) else None
            if isinstance(a, dict):
                out[s] = str(a.get('program') or a.get('character') or '-')[:12]
            else:
                out[s] = None
        return out

    @staticmethod
    def state(assign, buses, record, paused, arena, winners, pressed=None, spark=None):
        from .rounds import record_for
        names = Model.names_from(assign)
        chars = {s: ((assign or {}).get(s) or {}).get('character') if isinstance((assign or {}).get(s), dict) else None for s in 'ab'}
        records = {s: record_for(record, chars[s]) if chars[s] else (0, 0) for s in 'ab'}
        hp = {}
        wins = {}
        for s in 'ab':
            b = (buses or {}).get(s) or {}
            if b.get('hp') is not None:
                hp[s] = b.get('hp')
            if isinstance(b.get('wins'), dict):
                wins = {k: int(v) for k, v in b['wins'].items() if k in 'ab'}
        mode = 'paused' if paused else ('arena' if arena else 'taskbar')
        return dict(names=names, records=records, mode=mode, arena=bool(arena), paused=bool(paused), hp=hp or None, wins=wins,
                    winners=winners, pressed=pressed, spark=list(spark) if spark else None)
