"""The fighter roster: one entry per character the director can assign to a slot.

Every character is a rig.Body variant (proportions, hood / scarf / ponytail, palette, cap sigil) plus plate identity
(`display`, `tag`, `accent`) and a `signature` naming its strike / special / super.  Every character gets the full shared
move set from moves.py; its three signature moves are built from parameterised templates in moves.py (`spin`, `pound`,
`throw`, `cast`, `rewind`, `raise`), so the planner can treat all characters the same way and never branch on a name.

claude and codex keep their original bodies (rig.CLAUDE / rig.CODEX) and their original signature moves.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import rig
from rig import Body, _g, hexrgb

PAPER = _g('F4F4F2', 'FFFFFF', 'A9A9B4', '4A4A55')
FLASH = dict(fill=hexrgb('FFFFFF'), ol=hexrgb('B8BCD0'))


@dataclass(frozen=True)
class Character:
    name: str
    display: str
    tag: str                    # plate text
    accent: str                 # plate / HUD accent, '#RRGGBB'
    body: Body
    signature: dict             # {'strike': move, 'special': move, 'super': move}
    sig_moves: dict             # move -> (template, desc, opts)
    projectile: dict = field(default_factory=dict)   # style + colours for proj.png, `kind` for anim.json


def _fx(a, b, w, c):
    return dict(a=hexrgb(a), b=hexrgb(b), w=hexrgb(w), c=hexrgb(c))


# ---------------------------------------------------------------- new bodies
GEMINI = Body('gemini', thigh=8, shin=8, torso=11, torso_w=10, upper=6, fore=6, limb=3, head_w=13, head_h=13,
              foot_len=6, sigil='*', scarf=False, hood=False, ponytail=True, tail_anchor=(-6.5, 0.5), tail_seg=(3, 2.2),
              ghost_group='cloth', palette={
    'skin': _g('9A6444', 'B98260', '73472E', '3E2418'),
    'hair': _g('1E1A2A', '3A3450', '120F1A', '08070C'),
    'cloth': _g('3F7BE0', '7FA8F2', '2A55A8', '142A5C'),
    'trim': _g('C77DD8', 'EBC0F5', '8E50A5', '4A2458'),
    'pants': _g('2A2F45', '3F4560', '1B1F30', '0E1018'),
    'shoe': PAPER,
    'sole': _g('2A55A8', '3F7BE0', '2A55A8', '142A5C'),
    'ink': _g('141420', '141420', '141420', '141420'),
    'paper': PAPER,
    'fx': _fx('E8718C', 'FFE27A', 'FFFFFF', 'EBC0F5'),
    'flash': FLASH,
})

CURSOR = Body('cursor', thigh=8, shin=7, torso=12, torso_w=11, upper=6, fore=5.5, limb=3, head_w=13, head_h=13,
              foot_len=6, sigil='>', scarf=False, hood=True, ghost_group='trim', palette={
    'skin': _g('F0CDB0', 'FBE5D2', 'CFA587', '7E5640'),
    'hair': _g('3A2A20', '5A4434', '241A13', '120D0A'),
    'cloth': _g('2B2B2F', '45454B', '1A1A1D', '0A0A0C'),
    'trim': _g('E6E6EA', 'FFFFFF', 'B4B4BC', '5E5E66'),
    'pants': _g('3C4250', '545B6B', '282C36', '14161C'),
    'shoe': _g('E6E6EA', 'FFFFFF', 'B4B4BC', '5E5E66'),
    'sole': _g('1A1A1D', '45454B', '1A1A1D', '0A0A0C'),
    'ink': _g('0C0C10', '0C0C10', '0C0C10', '0C0C10'),
    'paper': PAPER,
    'fx': _fx('5FD3F3', 'FFE27A', 'FFFFFF', 'B4B4BC'),
    'flash': FLASH,
})

OLLAMA = Body('ollama', thigh=7, shin=7, torso=11, torso_w=14, upper=5.5, fore=5.5, limb=4, head_w=14, head_h=13,
              foot_len=7, sigil='o', scarf=True, hood=False, ghost_group='cloth', palette={
    'skin': _g('E2B48C', 'F2D0B0', 'BE8A64', '6E4630'),
    'hair': _g('2E2622', '4A3E36', '1E1814', '0F0C0A'),
    'cloth': _g('E9E2D2', 'FAF6EE', 'BFB5A0', '6B6252'),
    'trim': _g('2C2C30', '4A4A52', '1C1C20', '0C0C0E'),
    'pants': _g('5A4A3C', '75634F', '413529', '221B14'),
    'shoe': _g('2C2C30', '4A4A52', '1C1C20', '0C0C0E'),
    'sole': _g('413529', '5A4A3C', '413529', '221B14'),
    'ink': _g('141414', '141414', '141414', '141414'),
    'paper': PAPER,
    'fx': _fx('FFB347', 'FFE27A', 'FFFFFF', 'FAF6EE'),
    'flash': FLASH,
})

# LM Studio: the cyber-samurai direction (white armour plates, neon teal edge light, magenta soles) - an original
# pixel costume inspired by DullMesh's "Cyber White Samurai" look (docs/CREDITS.md, visual inspiration only).
LMSTUDIO = Body('lmstudio', thigh=9, shin=8, torso=12, torso_w=9, upper=6.5, fore=6, limb=3, head_w=12, head_h=13,
                foot_len=6, sigil='L', scarf=True, hood=False, ghost_group='trim', ghost_style='holo', palette={
    'skin': _g('C68B63', 'DFAA84', 'A0694A', '5A3626'),
    'hair': _g('6B3A22', '8E5434', '4A2716', '26130A'),
    'cloth': _g('E4ECF4', 'FFFFFF', 'A9B8C8', '3E5064'),
    'trim': _g('1FD6C4', '7CF8EA', '0F8F84', '064844'),
    'pants': _g('242A3C', '384058', '161A26', '0B0D14'),
    'shoe': _g('E4ECF4', 'FFFFFF', 'A9B8C8', '3E5064'),
    'sole': _g('D9488F', 'F59AC4', 'D9488F', '501433'),
    'ink': _g('12121A', '12121A', '12121A', '12121A'),
    'paper': PAPER,
    'fx': _fx('F59AC4', 'FFE27A', 'FFFFFF', '7CF8EA'),
    'flash': FLASH,
})

GENERIC = Body('generic', thigh=8, shin=7, torso=12, torso_w=12, upper=6, fore=6, limb=4, head_w=13, head_h=13,
               foot_len=6, sigil='+', scarf=False, hood=False, ghost_group='trim', palette={
    'skin': _g('E0B090', 'F0CEB2', 'BC8C6C', '6E4A36'),
    'hair': _g('2B2420', '4A3E36', '1A1512', '100C0A'),
    'cloth': _g('5B6B4A', '8A9B72', '3E4A31', '1E2418'),
    'trim': _g('E0C46C', 'FFE9A8', 'B0963E', '5A4A1C'),
    'pants': _g('3A3A40', '50505A', '28282C', '141416'),
    'shoe': PAPER,
    'sole': _g('28282C', '50505A', '28282C', '141416'),
    'ink': _g('18181A', '18181A', '18181A', '18181A'),
    'paper': PAPER,
    'fx': _fx('FF9C2C', 'FFE27A', 'FFFFFF', 'FFE9A8'),
    'flash': FLASH,
})


def _c(name, display, tag, accent, body, strike, special, sup, projectile, ult=None, support=None):
    """ult = (move, template, desc, opts); support = (move, template, desc) for a helper row the ultimate references."""
    sig = {'strike': strike[0], 'special': special[0], 'super': sup[0]}
    moves = {strike[0]: strike[1:], special[0]: special[1:], sup[0]: sup[1:]}
    if ult:
        sig['ultimate'] = ult[0]
        opts = dict(ult[3])
        if support:
            opts['support'] = support[0]
            moves[support[0]] = (support[1], support[2], {})
        moves[ult[0]] = (ult[1], ult[2], opts)
    return Character(name, display, tag, accent, body, sig, moves, projectile)


ROSTER = {c.name: c for c in [
    _c('claude', 'Claude', '/reverse', '#F0A184', rig.CLAUDE,
       ('spin_kick', 'spin', "Claude's signature spinning kick.", {}),
       ('slash_wave', 'throw', 'Throws a "/" slash wave across the taskbar. Costs nothing; looks cool.', {}),
       ('reverse', 'rewind', '"/reverse": rewinds to where it stood a second ago, dodging everything. Afterimage trail.',
        {'glyph': 'rewind'}),
       dict(style='arc', kind='slash_wave', cols=('cloth.base', 'cloth.hi', 'trim.base'), spark='fx.b'),
       ult=('kamehameha', 'kamehameha', 'Cups both hands at the hip, charges for a full second, then fires a horizontal beam the width of the taskbar.', {})),
    _c('codex', 'Codex', '$reverse', '#A99DFF', rig.CODEX,
       ('ground_pound', 'pound', "Codex's heavy leaping slam with a ground shockwave.", {}),
       ('deploy', 'cast', 'Types a command and hits ENTER: fires a ">_" bolt across the taskbar.', {}),
       ('sudo', 'raise', '"$reverse": raises a giant $ and powers up with elevated permissions.', {'glyph': 'bigsigil'}),
       dict(style='term', kind='deploy_bolt', glyph='>_', cols=('ink.base', 'trim.base', 'trim.sh'), mark='fx.w', trail='fx.c'),
       ult=('rasengan', 'rasengan', 'Spins a sphere of energy in one hand, dashes in with afterimages and drives it home in a spiral burst.', {}),
       support=('shadow_clones', 'shadow_clones', 'Cross-finger hand sign: three dithered clones rush the opponent.')),
    _c('gemini', 'Gemini', '*gemini', '#7FA8F2', GEMINI,
       ('spin_kick', 'spin', "Gemini's spinning kick, ponytail whipping round.", {}),
       ('star_shot', 'throw', 'Two-handed push that fires a "*" sparkle along the taskbar.', {}),
       ('twin_flash', 'rewind', 'Flash-steps back a second in time, leaving a sparkle and an afterimage trail.', {'glyph': 'bigglyph'}),
       dict(style='star', kind='star_shot', cols=('trim.hi', 'cloth.hi', 'cloth.base'), spark='fx.a'),
       ult=('getsuga', 'getsuga', 'Raises an arm, gathers energy and swings down a giant crescent slash wave.', {})),
    _c('cursor', 'Cursor', '>cursor', '#5FD3F3', CURSOR,
       ('ground_pound', 'pound', "Cursor's leaping slam with a ground shockwave.", {}),
       ('tab_bolt', 'cast', 'Accepts a suggestion and hits TAB: fires a ">|" caret bolt across the taskbar.', {}),
       ('autocomplete', 'raise', 'Raises a giant ">" and powers up: the whole line completes itself.', {'glyph': 'bigglyph'}),
       dict(style='term', kind='tab_bolt', glyph='>|', cols=('ink.base', 'cloth.hi', 'cloth.base'), mark='fx.a', trail='trim.sh'),
       ult=('odm_strike', 'odm_strike', 'Fires two grapple lines, zips across them and finishes with a spinning cross slash.', {})),
    _c('ollama', 'Ollama', 'ollama', '#E9E2D2', OLLAMA,
       ('ground_pound', 'pound', "Ollama's llama stomp with a ground shockwave.", {}),
       ('pull_shot', 'cast', '"ollama pull": hurls a wool-white orb across the taskbar.', {}),
       ('serve', 'raise', '"ollama serve": raises a giant "o" and powers up, local and unstoppable.', {'glyph': 'bigglyph'}),
       dict(style='orb', kind='pull_shot', cols=('cloth.ol', 'cloth.base', 'cloth.hi'), trail='fx.a'),
       ult=('wind_scar', 'wind_scar', 'Raises both arms, then slams down and rips three claws of energy along the ground.', {})),
    _c('lmstudio', 'LM Studio', 'lmstudio', '#7CF8EA', LMSTUDIO,
       ('spin_kick', 'spin', "LM Studio's spinning kick, scarf trailing.", {}),
       ('load_wave', 'throw', 'Loads a model and throws it as a teal-and-magenta wave across the taskbar.', {}),
       ('hot_swap', 'rewind', 'Hot-swaps back to where it stood a second ago, afterimage trail and a giant "L".', {'glyph': 'bigglyph'}),
       dict(style='arc', kind='load_wave', cols=('cloth.base', 'cloth.hi', 'trim.hi'), spark='trim.base'),
       ult=('bankai', 'bankai', 'Releases a pillar of aura, then lands three flash-step strikes faster than the eye.', {})),
    _c('generic', 'Agent', 'agent', '#E0C46C', GENERIC,
       ('spin_kick', 'spin', 'A spinning kick: every agent learns this one.', {}),
       ('energy_bolt', 'cast', 'Types a command and fires an energy orb across the taskbar.', {}),
       ('overclock', 'raise', 'Raises a giant "+" and powers up: everything runs faster.', {'glyph': 'bigglyph'}),
       dict(style='orb', kind='energy_bolt', cols=('trim.ol', 'trim.base', 'trim.hi'), trail='fx.a'),
       ult=('spirit_bomb', 'spirit_bomb', 'Raises both hands, gathers a huge slow ball of energy overhead and hurls it.', {})),
]}

NAMES = tuple(ROSTER)


def get(name) -> Character:
    """Character by name (a Character passes through)."""
    return name if isinstance(name, Character) else ROSTER[name]
