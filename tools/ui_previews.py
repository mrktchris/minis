"""Offscreen previews of the V6 UI (select screen + scoreboard) as PNGs: never a screen capture.

    python tools/ui_previews.py [out_dir]      (default: %TEMP%\\minis-v6-ui)
"""
import os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from PIL import Image  # noqa: E402
from minis_core import lineup, scoreboard as SB, select  # noqa: E402
from minis_core.atlas import Library  # noqa: E402


def big(im, k):
    return im.resize((im.width * k, im.height * k), Image.NEAREST)


def on_taskbar(im, k=2):
    bg = Image.new('RGBA', (im.width + 16, 48), (32, 32, 40, 255))
    bg.alpha_composite(im, (8, (48 - im.height) // 2))
    return big(bg, k)


def main(out=None):
    out = Path(out or Path(os.environ.get('TEMP', '.')) / 'minis-v6-ui')
    out.mkdir(parents=True, exist_ok=True)
    rows = [dict(source='claude', program='Claude Code', label='Claude', character='claude', state='working'),
            dict(source='codex', program='Codex', label='Codex', character='codex', state='asleep'),
            dict(source='grok', program='Grok', label='Grok', character='generic', state='idle'),
            dict(source='ollama', program='Ollama', label='Ollama', character='ollama', state='idle'),
            dict(source='sparring', program='Sparring bot', label='Bot', character='generic', state='bot')]
    lu = {'a': 'auto', 'b': 'codex', 'skins': {'grok': 'gemini'}}
    chars = lineup.characters()
    por = select.Portraits(Library())
    paths = []
    m = select.Model(('a', 'b'), select.offer(rows, lu), lu, chars, por, now=0.0)
    m.cur['a'] = 1
    im = m.render(0.1)
    paths.append(out / 'select-who.png')
    big(im, 2).save(paths[-1])
    m.key(select.VK['enter'], 0.2)                    # P1 confirms Claude -> look stage
    m.key(select.VK['right'], 0.3)
    paths.append(out / 'select-look.png')
    big(m.render(0.4), 2).save(paths[-1])
    m.key(select.VK['enter'], 0.5)                    # P1 done; P2 on its pick
    paths.append(out / 'select-p2.png')
    big(m.render(0.6), 2).save(paths[-1])
    m.key(select.VK['enter'], 0.7)
    m.key(select.VK['enter'], 0.8)
    paths.append(out / 'select-vs.png')
    big(m.render(0.9), 2).save(paths[-1])
    many = chars * 2                                  # what a 13+ roster looks like (ids repeated for the preview only)
    m2 = select.Model(('b',), select.offer(rows, lu), lu, many[:14], por, now=0.0)
    m2.key(select.VK['right'], 0.1)
    m2.key(select.VK['enter'], 0.1)
    paths.append(out / 'select-14-looks.png')
    big(m2.render(0.3), 2).save(paths[-1])
    base = dict(names={'a': 'Claude', 'b': 'Codex'}, records={'a': (12, 7), 'b': (7, 12)}, mode='taskbar', arena=False, paused=False,
                hp=None, wins={}, spark=[20, 35, 60, 72, 91, 40, None])
    for name, st in (('plain', base), ('bout', dict(base, hp={'a': 64, 'b': 22}, wins={'a': 1, 'b': 0})),
                     ('result', dict(base, result='CLAUDE WINS 2-1')), ('hidden', dict(base, hidden={'b': 3120.0})),
                     ('paused', dict(base, mode='paused', paused=True)), ('long', dict(base, names={'a': 'LM Studio', 'b': 'Perplexity'}))):
        paths.append(out / f'scoreboard-{name}.png')
        on_taskbar(SB.render(st), 3).save(paths[-1])
    for p in paths:
        print(p)


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else None)
