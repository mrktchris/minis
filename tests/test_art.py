"""Art gates, asserted on the real sheets (assets/<character>/) and the real pose data, for every roster character.

The sheets are read directly here (not through minis_core.atlas) so these gates test the art alone."""
import json, math, os, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'art'))
from PIL import Image, ImageDraw, ImageFilter  # noqa: E402
import rig  # noqa: E402
import moves as M  # noqa: E402
import roster  # noqa: E402
import build_fighters as BF  # noqa: E402

CHARS = roster.NAMES
CAP = 32          # Pixel Joint fighting-character challenge: 32 colours counting transparency
SKINLIKE = {rig.PID[n] for n in ('head', 'ear', 'hand_f', 'hand_b', 'eye', 'brow', 'mouth',
                                  'arm_f_up', 'arm_f_fo', 'arm_b_up', 'arm_b_fo', 'cuff_f', 'cuff_b')}
SKIN = {rig.PID[n] for n in ('head', 'ear', 'hand_f', 'hand_b')}    # colours that can never equal a sigil colour
FX_IDS = {rig.PID[n] for n in ('fx_a', 'fx_b', 'fx_w', 'fx_c')}


class Sheet:
    """<root>/<character>/ as built: metadata, right- and left-facing sheets, projectile strip and effects sheet."""
    _cache = {}

    def __new__(cls, ch, root='assets'):
        key = (ch, root)
        if key not in cls._cache:
            o = super().__new__(cls)
            d = ROOT / root / ch
            o.root = root
            o.meta = json.loads((d / 'anim.json').read_text(encoding='utf-8'))
            o.anim = o.meta['anims']
            o.cell = int(o.meta['cell'][0])
            o.res = int(o.meta.get('res', 1))
            o.sheets = {k: Image.open(d / v).convert('RGBA') for k, v in o.meta['sheets'].items()}
            o.proj = Image.open(d / o.meta['projectile']['file']).convert('RGBA')
            o.fx = json.loads((d / 'fx.json').read_text(encoding='utf-8')) if (d / 'fx.json').exists() else None
            o.fxs = Image.open(d / o.fx.get('sheet', 'fx.png')).convert('RGBA') if o.fx else None
            cls._cache[key] = o
        return cls._cache[key]

    def frame(self, name, i, facing=1):
        r = self.anim[name]['row']
        c = self.cell
        return self.sheets['R' if facing >= 0 else 'L'].crop((i * c, r * c, (i + 1) * c, (r + 1) * c))

    def frames(self, name, facing=1):
        return [self.frame(name, i, facing) for i in range(len(self.anim[name]['frames']))]


def bbox(im):
    return im.getchannel('A').getbbox()


def parts(ch, name, i, scarf=True):
    """(right-facing part buffer, meta, pose) exactly as the builder renders it."""
    c = roster.get(ch)
    mv = M.build_moves(c)[name]
    pose = mv['frames'][i][0]
    pts = None
    if scarf and c.body.has_tail:
        pts = tracks(ch)[name][i]
    buf, meta = rig.render_parts(c.body, pose, pts)
    return buf, meta, pose


_tracks = {}


def tracks(ch):
    """Scarf / ponytail points per move, computed the way build() computes them."""
    if ch not in _tracks:
        c = roster.get(ch)
        idle_pts = BF.idle_scarf(c)
        out = {}
        for name, mv in M.build_moves(c).items():
            poses = [f[0] for f in mv['frames']]
            start = None if name == 'idle' else idle_pts
            out[name] = BF.scarf_track(c.body, poses, mv['loop'], mv.get('loop_range'), start=start)
        _tracks[ch] = out
    return _tracks[ch]


def glyph_cells(sym):
    return {(x, y) for y, row in enumerate(rig.GLYPH[sym]) for x, ch in enumerate(row) if ch == '#'}


class Roster(unittest.TestCase):
    def test_every_roster_character_is_built_with_its_identity(self):
        self.assertEqual(set(CHARS), {'claude', 'codex', 'gemini', 'cursor', 'ollama', 'lmstudio', 'generic'})
        for ch in CHARS:
            c, s = roster.get(ch), Sheet(ch)
            for k in ('character', 'display', 'tag', 'accent', 'signature'):
                self.assertIn(k, s.meta, f'{ch}: anim.json lacks {k}')
            self.assertEqual(s.meta['character'], ch)
            self.assertEqual(s.meta['tag'], c.tag)
            self.assertRegex(s.meta['accent'], r'^#[0-9A-F]{6}$')
            self.assertEqual(set(s.meta['signature']), {'strike', 'special', 'super', 'ultimate'})
        self.assertEqual(Sheet('claude').meta['tag'], '/reverse')
        self.assertEqual(Sheet('codex').meta['tag'], '$reverse')

    def test_identities_are_distinct(self):
        for key in ('tag', 'accent'):
            vals = [Sheet(ch).meta[key] for ch in CHARS]
            self.assertEqual(len(vals), len(set(vals)), f'two characters share a {key}: {vals}')
        sig = [roster.get(ch).body.sigil for ch in CHARS]
        self.assertEqual(len(sig), len(set(sig)), f'two characters share a cap sigil: {sig}')


class Palette(unittest.TestCase):
    def test_at_most_32_colours_including_transparency_and_one_shared_palette(self):
        for ch in CHARS:
            s = Sheet(ch)
            meta_pal = set(s.meta['palette'])
            seen = set()
            for k, sheet in s.sheets.items():
                a = sheet.getchannel('A')
                self.assertTrue(set(a.getcolors()) and {v for _, v in a.getcolors()} <= {0, 255}, f'{ch}/{k}: partial alpha pixel')
                for _, p in sheet.getcolors(1 << 16):
                    if p[3]:
                        seen.add('#%02X%02X%02X' % p[:3])
            self.assertLessEqual(len(seen) + 1, CAP, f'{ch}: {len(seen)} colours + transparency')
            self.assertTrue(seen <= meta_pal, f'{ch}: a frame uses a colour outside the shared palette: {seen - meta_pal}')
            self.assertEqual(s.meta['colors'], len(seen))


class Placement(unittest.TestCase):
    def test_every_frame_fits_the_cell_with_a_margin(self):
        for ch in CHARS:
            s = Sheet(ch)
            for name in s.anim:
                for facing in (1, -1):
                    for i, im in enumerate(s.frames(name, facing)):
                        bb = bbox(im)
                        self.assertIsNotNone(bb, f'{ch}/{name}/{i} is empty')
                        self.assertGreaterEqual(bb[1], 1, f'{ch}/{name}/{i} touches the top edge')
                        self.assertGreaterEqual(bb[0], 0)
                        self.assertLessEqual(bb[2], 64)

    def test_planted_soles_sit_on_the_same_baseline(self):
        soles = {rig.PID['sole_f'], rig.PID['sole_b']}
        for ch in CHARS:
            body = roster.get(ch).body
            checked = 0
            for name, m in M.build_moves(ch).items():
                for i, (pose, _) in enumerate(m['frames']):
                    grounded = (pose.ff[1] == 0 or pose.fb[1] == 0) and pose.lean > -45 and 0 <= pose.dy < 12 and not pose.flash
                    if not grounded or name in ('knockdown', 'ko', 'getup', 'sleep', 'wake'):
                        continue
                    buf, _ = rig.render_parts(body, pose, None)
                    px = buf.load()
                    low = max(y for y in range(64) for x in range(64) if px[x, y] in soles)
                    self.assertEqual(low, 57, f'{ch}/{name}/{i}: lowest sole row {low}, expected 57')
                    checked += 1
            self.assertGreater(checked, 150, ch)

    def test_nothing_dips_more_than_a_pixel_below_the_outline_row(self):
        for ch in CHARS:
            s = Sheet(ch)
            for name in s.anim:
                for i, im in enumerate(s.frames(name)):
                    self.assertLessEqual(bbox(im)[3], 60, f'{ch}/{name}/{i} reaches row {bbox(im)[3] - 1}')


class Motion(unittest.TestCase):
    def test_walk_planted_foot_does_not_slide(self):
        for ch in CHARS:
            for name in ('walk', 'walk_back'):
                fr = M.build_moves(ch)[name]['frames']
                for slot in ('ff', 'fb'):
                    world, track = 0.0, []
                    for pose, _ in fr + fr:                      # two cycles to cover the wrap
                        world += pose.dx
                        track.append((world + getattr(pose, slot)[0], getattr(pose, slot)[1] == 0))
                    cur = []
                    for wx, planted in track + [(0, False)]:
                        if planted:
                            cur.append(wx)
                        else:
                            if len(cur) >= 2:
                                self.assertLessEqual(max(cur) - min(cur), 1.0, f'{ch}/{name}/{slot} slides {max(cur) - min(cur)} px')
                            cur = []

    def test_walk_speed_matches_the_planners_speed(self):
        for ch in CHARS:
            m = M.build_moves(ch)['walk']
            stride = sum(abs(p.dx) for p, _ in m['frames'])
            cycle = sum(ms for _, ms in m['frames']) / 1000.0
            self.assertAlmostEqual(stride / cycle, 40.0, delta=1.0)

    def test_looping_moves_close_without_a_pop(self):
        """Every looping move, over its loop_range when it has one: the wrap is no bigger than a normal step."""
        def diff(a, b):
            pa, pb = a.load(), b.load()
            return sum(1 for y in range(64) for x in range(64) if pa[x, y] != pb[x, y])
        for ch in CHARS:
            s = Sheet(ch)
            for name, a in s.anim.items():
                if not a['loop']:
                    continue
                lo, hi = a.get('loop_range') or (0, len(a['frames']) - 1)
                if hi == lo:
                    continue
                fr = s.frames(name)[lo:hi + 1]
                step = max(diff(fr[i], fr[i + 1]) for i in range(len(fr) - 1))
                self.assertLessEqual(diff(fr[-1], fr[0]), step * 1.5 + 40, f'{ch}/{name} pops at the loop point')

    def test_jump_actually_leaves_the_ground(self):
        for ch in CHARS:
            tops = [bbox(im)[1] for im in Sheet(ch).frames('jump')]
            self.assertLess(min(tops), tops[0] - 5, ch)


class Scarf(unittest.TestCase):
    TAILS = [ch for ch in CHARS if roster.get(ch).body.has_tail]

    def test_some_characters_have_a_tail(self):
        self.assertIn('claude', self.TAILS)
        self.assertIn('gemini', self.TAILS)          # ponytail

    def test_segment_lengths_stay_bounded_in_every_frame(self):
        """The pole bug: a fall moved the neck 10+ px and the first segment stretched into a stick (knockdown/1)."""
        for ch in self.TAILS:
            n_seg, seg = roster.get(ch).body.tail_seg
            for name, tr in tracks(ch).items():
                for i, pts in enumerate(tr):
                    self.assertEqual(len(pts), n_seg + 1)
                    for k in range(n_seg):
                        L = math.dist(pts[k], pts[k + 1])
                        self.assertGreaterEqual(L, seg * 0.69, f'{ch}/{name}/{i} segment {k} is {L:.1f} px')
                        self.assertLessEqual(L, seg * 1.51, f'{ch}/{name}/{i} segment {k} is {L:.1f} px')

    def test_scarf_never_sinks_into_the_taskbar(self):
        for ch in self.TAILS:
            for name, tr in tracks(ch).items():
                for i, pts in enumerate(tr):
                    self.assertLessEqual(max(p[1] for p in pts[1:]), BF.FLOOR + 1e-6, f'{ch}/{name}/{i}')   # [0] is the neck

    def test_scarf_loops_close_over_the_loop_range(self):
        for ch in self.TAILS:
            body = roster.get(ch).body
            for name, mv in M.build_moves(ch).items():
                if not mv['loop']:
                    continue
                lo, hi = mv.get('loop_range') or (0, len(mv['frames']) - 1)
                tr = tracks(ch)[name]
                nxt = BF.scarf_step(body, tr[hi], mv['frames'][lo][0])
                err = max(math.dist(a, b) for a, b in zip(nxt, tr[lo]))
                self.assertLess(err, 0.5, f'{ch}/{name}: scarf jumps {err:.2f} px at the loop point')

    def test_non_looping_moves_start_from_the_idle_scarf(self):
        """A move that starts in the idle stance starts with the idle scarf shape, not its own end state."""
        for ch in self.TAILS:
            body = roster.get(ch).body
            idle_end = BF.idle_scarf(ch)
            for name, mv in M.build_moves(ch).items():
                if mv['loop']:
                    continue
                pose0 = mv['frames'][0][0]
                a0 = BF.head_attach(body, pose0)
                shifted = [(x + a0[0] - idle_end[0][0], y + a0[1] - idle_end[0][1]) for x, y in idle_end]
                want = BF.scarf_step(body, shifted, pose0)
                err = max(math.dist(a, b) for a, b in zip(want, tracks(ch)[name][0]))
                self.assertLess(err, 1e-6, f'{ch}/{name}: frame 0 scarf does not continue from idle')


class Look(unittest.TestCase):
    @staticmethod
    def _iou(a, b):
        pa, pb = Sheet(a).frame('idle', 0).getchannel('A').load(), Sheet(b).frame('idle', 0).getchannel('A').load()
        inter = union = 0
        for y in range(64):
            for x in range(64):
                p, q = pa[x, y] > 0, pb[x, y] > 0
                inter += p and q
                union += p or q
        return inter / union

    def test_the_claude_and_codex_silhouettes_differ(self):
        self.assertLess(self._iou('claude', 'codex'), 0.8)

    def test_every_character_looks_different_from_every_other(self):
        for i, a in enumerate(CHARS):
            for b in CHARS[i + 1:]:
                pa = {c for _, c in Sheet(a).frame('idle', 0).getcolors(4096) if c[3]}
                pb = {c for _, c in Sheet(b).frame('idle', 0).getcolors(4096) if c[3]}
                self.assertLess(len(pa & pb) / len(pa | pb), 0.5, f'{a} and {b} share most idle colours')

    def test_no_orphan_pixels_except_intended_effects(self):
        kern = ImageFilter.Kernel((3, 3), [1, 1, 1, 1, 0, 1, 1, 1, 1], scale=1)
        for ch in CHARS:
            s = Sheet(ch)
            for name, m in M.build_moves(ch).items():
                for i, (pose, _) in enumerate(m['frames']):
                    if pose.fx or pose.ghost or pose.aura:
                        continue
                    mask = s.frame(name, i).getchannel('A').point(lambda a: 1 if a else 0)
                    nb = mask.filter(kern).load()
                    mp = mask.load()
                    for y in range(1, 63):
                        for x in range(1, 63):
                            if mp[x, y] and not nb[x, y]:
                                self.fail(f'{ch}/{name}/{i}: orphan pixel at {(x, y)}')

    def test_stamp_corners_are_really_softened(self):
        for t, want in ((3, 9), (4, 12), (5, 21)):
            im = Image.new('L', (16, 16), 0)
            rig.stamp(ImageDraw.Draw(im), 8, 8, t, 1)
            px = im.load()
            n = sum(1 for y in range(16) for x in range(16) if px[x, y])
            self.assertEqual(n, want, f'stamp {t}')
            bb = im.getbbox()
            corner = px[bb[0], bb[1]]
            self.assertEqual(bool(corner), t < 4, f'stamp {t}: corner pixel')

    def test_zzz_reads_as_a_z_not_an_i(self):
        for extra in (0, 1):
            im = Image.new('L', (64, 64), 0)
            rig.fx_draw(ImageDraw.Draw(im), 'zzz', 20, 20, extra)
            px = im.load()
            rows = {}
            for y in range(64):
                xs = [x for x in range(64) if px[x, y]]
                if xs:
                    rows[y] = xs
            ys = sorted(rows)
            widths = [max(v) - min(v) + 1 for v in rows.values()]
            mid = [sum(rows[y]) / len(rows[y]) for y in ys if max(rows[y]) - min(rows[y]) + 1 < max(widths)]
            mid = [m for j, m in enumerate(mid) if j == 0 or m != mid[j - 1]]     # 2x scale repeats each row
            self.assertGreaterEqual(len(mid), 2, 'no diagonal')
            self.assertTrue(all(a > b for a, b in zip(mid, mid[1:])), f'diagonal must run top-right to bottom-left: {mid}')


class Sigil(unittest.TestCase):
    """Left-facing frames are the mirrored part buffer with the cap sigil redrawn un-mirrored."""

    def _box_colours(self, im, x0, y0):
        px = im.load()
        return {(x, y) for y in range(5) for x in range(3) if px[x0 + x, y0 + y][:3]}

    def test_sigil_reads_correctly_on_the_real_sheets_in_both_facings(self):
        for ch in CHARS:
            c, s = roster.get(ch), Sheet(ch)
            sig = c.body.palette['trim']['hi']
            want = glyph_cells(c.body.sigil)
            checked = 0
            for name, mv in M.build_moves(ch).items():
                for i, (pose, _) in enumerate(mv['frames']):
                    if pose.flash or pose.ghost:
                        continue
                    buf, meta, _ = parts(ch, name, i)
                    gx0, gy0 = meta['sigil']
                    bp = buf.load()
                    box = [(gx0 + x, gy0 + y) for y in range(5) for x in range(3)]
                    if not all(0 <= x < 64 and 0 <= y < 64 and bp[x, y] in (rig.PID['cap'], rig.PID['sigil']) for x, y in box):
                        continue                                   # cap partly occluded or off the crown this frame
                    for facing, x0 in ((1, gx0), (-1, rig.sigil_box_l(meta, c.body)[0])):
                        px = s.frame(name, i, facing).load()
                        got = {(x, y) for y in range(5) for x in range(3) if px[x0 + x, gy0 + y][:3] == sig}
                        self.assertEqual(got, want, f'{ch}/{name}/{i} facing {facing}: sigil {sorted(got)}')
                    checked += 1
            self.assertGreater(checked, 120, f'{ch}: too few unoccluded frames checked')

    def test_left_facing_redraw_never_paints_over_skin_or_hands(self):
        for ch in CHARS:
            c, s = roster.get(ch), Sheet(ch)
            sig = c.body.palette['trim']['hi']
            for name, mv in M.build_moves(ch).items():
                for i in range(len(mv['frames'])):
                    buf, meta, pose = parts(ch, name, i)
                    flipped = meta.get('pre_text', buf).transpose(Image.FLIP_LEFT_RIGHT).load()
                    left = rig.mirror_parts(buf, meta, c.body).load()
                    real = s.frame(name, i, -1).load()
                    for y in range(64):
                        for x in range(64):
                            if flipped[x, y] in SKINLIKE:
                                self.assertIn(left[x, y], {flipped[x, y]} | FX_IDS,
                                              f'{ch}/{name}/{i}: ({x},{y}) was {rig.NAME[flipped[x, y]]}, now {rig.NAME.get(left[x, y])}')
                                if left[x, y] == flipped[x, y] and left[x, y] in SKIN and not pose.flash:
                                    self.assertNotEqual(real[x, y][:3], sig, f'{ch}/{name}/{i}: sigil colour on skin at ({x},{y})')

    def test_letters_in_effects_are_not_mirrored_on_left_facing_frames(self):
        """'$', '>', 'L', '?', 'z' read the same way in both facings."""
        checked = 0
        for ch in CHARS:
            body = roster.get(ch).body
            for name, mv in M.build_moves(ch).items():
                for i, (pose, _) in enumerate(mv['frames']):
                    if not any(f[0] in rig.TEXT_FX for f in pose.fx):
                        continue
                    buf, meta, _ = parts(ch, name, i)
                    left = rig.mirror_parts(buf, meta, body)
                    for kind, x, y, extra in meta['text_fx']:
                        bb = rig.text_fx_bbox(kind, x, y, extra, body.sigil)
                        ref = Image.new('L', (64, 64), 0)
                        rig.fx_draw(ImageDraw.Draw(ref), kind, x + (63 - bb[2]) - bb[0], y, extra, body.sigil)
                        rp, lp = ref.load(), left.load()
                        for yy in range(64):
                            for xx in range(64):
                                if rp[xx, yy]:
                                    self.assertEqual(lp[xx, yy], rp[xx, yy], f'{ch}/{name}/{i}: {kind} mirrored at ({xx},{yy})')
                        checked += 1
        self.assertGreater(checked, 20)

    def test_hand_polished_frames_get_the_sigil_redrawn_for_left_facing(self):
        ch = 'codex'
        c = roster.get(ch)
        mv = M.build_moves(c)['idle']
        gen = BF.render_move(c, 'idle', mv)
        hand = gen[0]['r'].copy()
        hand.putpixel((2, 40), (255, 0, 255, 255))               # a marker only an artist's frame would have
        old = os.environ.get('MINIS_HAND_DIR')
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, ch))
            hand.save(os.path.join(tmp, ch, 'idle_0.png'))
            os.environ['MINIS_HAND_DIR'] = tmp
            try:
                out = BF.render_move(c, 'idle', mv)
            finally:
                if old is None:
                    os.environ.pop('MINIS_HAND_DIR', None)
                else:
                    os.environ['MINIS_HAND_DIR'] = old
        self.assertEqual(out[0]['r'].tobytes(), hand.tobytes(), 'the hand frame replaces the generated right frame')
        self.assertEqual(out[0]['l'].getpixel((61, 40)), (255, 0, 255, 255), 'the left frame is the mirror of the hand frame')
        x0, y0 = rig.sigil_box_l(gen[0]['meta'], c.body)
        sig = c.body.palette['trim']['hi']
        px = out[0]['l'].load()
        got = {(x, y) for y in range(5) for x in range(3) if px[x0 + x, y0 + y][:3] == sig}
        self.assertEqual(got, glyph_cells(c.body.sigil))
        self.assertEqual(out[1]['l'].tobytes(), gen[1]['l'].tobytes(), 'frames without a hand file are untouched')


class Reach(unittest.TestCase):
    def test_reach_is_measured_from_the_striking_pixels_on_the_real_sheet(self):
        for ch in CHARS:
            s = Sheet(ch)
            for name, a in s.anim.items():
                if 'hit_frame' not in a:
                    continue
                self.assertIn('reach', a, f'{ch}/{name}')
                i = a['hit_frame']
                buf, _, pose = parts(ch, name, i)
                anc = next((f[1] for f in pose.fx if f[0] in BF.IMPACT_FX and f[1] in BF.STRIKE_PARTS), None)
                if anc is None:
                    self.assertTrue(8 <= a['reach'] <= 30, f'{ch}/{name}: reach {a["reach"]}')
                    continue
                twin = {'hf': 'hb', 'hb': 'hf', 'ff': 'fb', 'fb': 'ff'}[anc]
                bp, sp = buf.load(), s.frame(name, i).load()
                for limbs in (BF.STRIKE_PARTS[anc], BF.STRIKE_PARTS[anc] + BF.STRIKE_PARTS[twin]):
                    ids = {rig.PID[n] for n in limbs}
                    xs = [x for y in range(64) for x in range(64) if bp[x, y] in ids and sp[x, y][3]]
                    if xs:
                        break
                # the striking limb's outer outline pixel is opaque on the real sheet, one past the limb
                edge = max(xs) + 1
                rows = [y for y in range(64) if bp[max(xs), y] in ids]
                self.assertTrue(any(sp[edge, y][3] for y in rows), f'{ch}/{name}: no outline beyond the striking limb')
                self.assertEqual(a['reach'], edge + 1 - rig.HIP_X, f'{ch}/{name}')

    def test_a_jab_reaches_further_than_an_uppercut(self):
        for ch in CHARS:
            an = Sheet(ch).anim
            self.assertGreater(an['jab']['reach'], an['uppercut']['reach'], ch)


class Schema(unittest.TestCase):
    REQUIRED = ['idle', 'walk', 'walk_back', 'dash', 'backdash', 'jump', 'crouch', 'jab', 'cross', 'uppercut', 'low_kick', 'roundhouse',
                'block', 'block_hit', 'parry', 'hit', 'hit_heavy', 'knockdown', 'getup', 'dizzy', 'ko', 'victory', 'taunt', 'bow',
                'fistbump', 'highfive', 'wave', 'work', 'type', 'review', 'wait', 'sleep', 'wake', 'powerup', 'rage', 'handoff_give', 'handoff_take', 'console']

    def test_every_character_has_the_full_shared_move_set(self):
        shared = None
        for ch in CHARS:
            s = Sheet(ch)
            for n in self.REQUIRED:
                self.assertIn(n, s.anim, f'{ch} is missing {n}')
            own = set(s.anim) - set(s.meta['signature'].values())
            own -= {a['support'] for a in s.anim.values() if a.get('support')}     # an ultimate's helper row
            shared = own if shared is None else shared
            self.assertEqual(own, shared, f'{ch}: shared move set differs')

    def test_signature_moves_exist_and_have_the_right_shape(self):
        legacy = {'claude': ('spin_kick', 'slash_wave', 'reverse', 'kamehameha'), 'codex': ('ground_pound', 'deploy', 'sudo', 'rasengan')}
        for ch, (st, sp, su, ul) in legacy.items():
            self.assertEqual(Sheet(ch).meta['signature'], {'strike': st, 'special': sp, 'super': su, 'ultimate': ul})
        for ch in CHARS:
            s = Sheet(ch)
            sig = s.meta['signature']
            for role in ('strike', 'special', 'super', 'ultimate'):
                self.assertIn(sig[role], s.anim, f'{ch}: signature {role} {sig[role]} is not in its move set')
            st, sp, su = (s.anim[sig[k]] for k in ('strike', 'special', 'super'))
            self.assertEqual(st['cat'], 'strike')
            self.assertIn('hit_frame', st)
            self.assertIn('reach', st)
            self.assertEqual(sp['cat'], 'special')
            self.assertIn('proj_frame', sp)
            self.assertEqual(len(sp['proj_from']), 2)
            self.assertEqual(su['cat'], 'super')

    def test_anim_json_schema_and_projectile(self):
        for ch in CHARS:
            s = Sheet(ch)
            d = s.meta
            self.assertEqual(d['cell'], [64, 64])
            self.assertEqual(d['ground_y'], 57)
            self.assertEqual(d['anchor'], {'R': 30, 'L': 33})
            self.assertEqual(d.get('res'), 1)
            for name, m in d['anims'].items():
                self.assertIn('row', m)
                self.assertTrue(all({'i', 'ms', 'dx'} <= set(f) for f in m['frames']), name)
                self.assertTrue(all(f['ms'] > 0 for f in m['frames']), name)
                if 'loop_range' in m:
                    lo, hi = m['loop_range']
                    self.assertTrue(0 <= lo <= hi < len(m['frames']), name)
            p = d['projectile']
            self.assertEqual(p['move'], d['signature']['special'])
            self.assertEqual(s.proj.size, (p['w'] * p['frames'], p['h']))
            for k in range(p['frames']):
                self.assertIsNotNone(s.proj.crop((k * p['w'], 0, (k + 1) * p['w'], p['h'])).getbbox(), f'{ch}: empty projectile frame {k}')


# ====================================================================== V4: resolution, effects, ultimates
ROOTS = {'assets': 1, 'assets_hd': 2}
CAPS = {1: 32, 2: 64}
GENERIC_FX = ('hit_light', 'hit_heavy', 'block_spark', 'dust', 'ko_stars', 'crack_small', 'crack_big', 'shatter', 'explosion',
              'letters', 'ko_text', 'round_text')
BANNER_FX = ('round_1', 'round_2', 'round_3', 'fight', 'winner', 'ko')
ULTIMATES = {'claude': 'kamehameha', 'codex': 'rasengan', 'gemini': 'getsuga', 'cursor': 'odm_strike',
             'ollama': 'wind_scar', 'lmstudio': 'bankai', 'generic': 'spirit_bomb'}
FX_KEYS = {'frames', 'anchor', 'offset', 'loop', 'layer', 'hit_frame', 'travel', 'shake', 'grow', 'flash'}


def sheet_colours(im):
    a = im.getchannel('A')
    assert {v for _, v in a.getcolors()} <= {0, 255}, 'partial alpha'
    return {p[:3] for _, p in im.getcolors(1 << 20) if p[3]}


class Resolution(unittest.TestCase):
    """RES 1 = the V3 sheets byte for byte; RES 2 = the same moves in 128 px cells under a 64-colour cap."""

    def test_rows_match_the_v5_visual_regression_fixture(self):
        """Every row of every character, both facings and both resolutions, hashes to the fixture regenerated when
        the V5 fluid pass was signed off by eye (python tests/test_art.py --regen-hashes).  A hash mismatch means the
        art changed: look at it (art/qa_fluid.py strip ...), and regenerate only when the change is wanted."""
        fix = json.loads((ROOT / 'tests' / 'fixtures' / 'v5_frame_hashes.json').read_text())
        got = frame_hashes()
        self.assertEqual(set(got), set(fix), 'character / root set changed')
        for key, e in fix.items():
            g = got[key]
            self.assertEqual(g['proj'], e['proj'], f'{key}: proj.png changed')
            self.assertEqual(g['palette'], e['palette'], f'{key}: palette changed')
            self.assertEqual(list(g['moves']), list(e['moves']), f'{key}: move order changed')
            for name, m in e['moves'].items():
                for facing in ('R', 'L'):
                    self.assertEqual(g['moves'][name][facing], m[facing], f'{key}/{name} facing {facing} changed')
                self.assertEqual(g['moves'][name]['frames'], m['frames'], f'{key}/{name} timing')
                self.assertEqual(g['moves'][name]['meta'], m['meta'], f'{key}/{name} metadata')

    def test_v5_timing_rules_on_every_strike(self):
        """The fluid-pass contract: a strike has a smear before its contact, the contact carries hitstop, no two
        consecutive frames share a duration, and every smear frame is short."""
        for ch in CHARS:
            s = Sheet(ch)
            for name, a in s.anim.items():
                if a['cat'] not in ('strike', 'ultimate'):
                    continue
                ms = [f['ms'] for f in a['frames']]
                self.assertTrue(all(x != y for x, y in zip(ms, ms[1:])), f'{ch}/{name}: even timing {ms}')
                self.assertIn('hitstop_ms', a, f'{ch}/{name}')
                self.assertGreaterEqual(a['hitstop_ms'], 150)
                sm = a.get('smear_frames') or []
                self.assertTrue(sm, f'{ch}/{name}: no smear frame')
                self.assertTrue(all(ms[i] <= 110 for i in sm), f'{ch}/{name}: a smear frame is held {[ms[i] for i in sm]}')
                self.assertTrue(any(i <= a['hit_frame'] for i in sm), f'{ch}/{name}: the smear comes after the contact')
            self.assertIn('credits', s.meta)
            self.assertIn('hitstop_ms', s.meta['schema_notes'])

    def test_afterimages_trail_behind_the_motion_and_thin_out(self):
        """A dash's ghosts sit on the side the fighter came from; copies further back are sparser."""
        for ch in CHARS:
            s = Sheet(ch)
            for name, a in s.anim.items():
                for i, (pose, _) in enumerate(M.build_moves(ch)[name]['frames']):
                    if not pose.ghost or pose.flash:
                        continue
                    buf, meta, _ = parts(ch, name, i)
                    body_px = buf.load()
                    body_cols = [x for y in range(64) for x in range(64) if body_px[x, y] and rig.NAME[body_px[x, y]] not in rig.NOLINE]
                    real = s.frame(name, i).load()
                    ghost_cols = [x for y in range(64) for x in range(64) if real[x, y][3] and not body_px[x, y]
                                  and x not in range(min(body_cols) - 1, max(body_cols) + 2)]
                    if not ghost_cols:
                        continue
                    behind = sum(1 for x in ghost_cols if (x < min(body_cols)) == (pose.dx >= 0))
                    self.assertGreater(behind / len(ghost_cols), 0.9, f'{ch}/{name}/{i}: afterimage on the wrong side')

    def test_ultimate_rows_come_after_every_v3_row(self):
        for ch in CHARS:
            s = Sheet(ch)
            v3 = max(a['row'] for n, a in s.anim.items() if n not in (s.meta['signature']['ultimate'], s.anim[s.meta['signature']['ultimate']].get('support')))
            self.assertGreater(s.anim[s.meta['signature']['ultimate']]['row'], v3, ch)

    def test_rig_res_factor_scales_the_cell_and_is_restored(self):
        self.assertEqual(rig.RES, 1)
        try:
            rig.set_res(2)
            self.assertEqual((rig.cell_px(), rig.ground_px(), rig.hip_x_px()), (128, 114, 60))
            buf, meta = rig.render_parts(rig.CLAUDE, rig.Pose(), None)
            self.assertEqual(buf.size, (128, 128))
            im = rig.finish(buf, rig.CLAUDE, rig.Pose(), meta['hip'][1])
            self.assertEqual(im.size, (128, 128))
            self.assertIn(rig.rim_tone(rig.CLAUDE.palette['cloth']), {p[:3] for _, p in im.getcolors(4096) if p[3]}, 'HD adds the rim tone')
        finally:
            rig.set_res(1)
        buf, _ = rig.render_parts(rig.CLAUDE, rig.Pose(), None)
        self.assertEqual(buf.size, (64, 64))

    def test_hd_atlas_schema_matches_res1_with_scaled_geometry(self):
        for ch in CHARS:
            lo, hd = Sheet(ch), Sheet(ch, 'assets_hd')
            self.assertEqual(hd.meta['res'], 2)
            self.assertEqual(hd.meta['cell'], [128, 128])
            self.assertEqual(hd.meta['ground_y'], 114)
            self.assertEqual(hd.meta['anchor'], {'R': 60, 'L': 67})
            self.assertEqual(hd.meta['signature'], lo.meta['signature'])
            self.assertEqual(list(hd.anim), list(lo.anim), f'{ch}: HD move order differs')
            for name, a in lo.anim.items():
                b = hd.anim[name]
                self.assertEqual(b['row'], a['row'], f'{ch}/{name}')
                self.assertEqual([f['ms'] for f in b['frames']], [f['ms'] for f in a['frames']], f'{ch}/{name}')
                self.assertEqual([f['dx'] for f in b['frames']], [f['dx'] * 2 for f in a['frames']], f'{ch}/{name}: dx scales')
                for k in ('loop', 'cat', 'hit_frame', 'proj_frame', 'loop_range', 'power', 'fx', 'support'):
                    self.assertEqual(b.get(k), a.get(k), f'{ch}/{name}/{k}')
                if 'stride' in a:
                    self.assertEqual(b['stride'], a['stride'] * 2)
                if 'reach' in a:
                    self.assertTrue(1.6 * a['reach'] <= b['reach'] <= 2.4 * a['reach'] + 2, f'{ch}/{name}: reach {a["reach"]} -> {b["reach"]}')
            p = hd.meta['projectile']
            self.assertEqual((p['w'], p['h'], p['speed']), (48, 40, 260))
            self.assertEqual(hd.proj.size, (p['w'] * p['frames'], p['h']))
            for k, sheet in hd.sheets.items():
                self.assertEqual(sheet.size, (8 * 128, len(hd.anim) * 128), f'{ch}/{k}')

    def test_palette_caps_per_resolution_for_sheets_and_effects(self):
        for root, res in ROOTS.items():
            cap = CAPS[res]
            for ch in CHARS:
                s = Sheet(ch, root)
                seen = set()
                for k, sheet in s.sheets.items():
                    seen |= sheet_colours(sheet)
                self.assertLessEqual(len(seen) + 1, cap, f'{root}/{ch}: {len(seen)} colours + transparency')
                self.assertEqual(s.meta['colors'], len(seen), f'{root}/{ch}')
                self.assertTrue({('#%02X%02X%02X' % c) for c in seen} <= set(s.meta['palette']), f'{root}/{ch}: colour outside the shared palette')
                self.assertIsNotNone(s.fxs, f'{root}/{ch}: no fx.png')
                fxc = sheet_colours(s.fxs)
                self.assertLessEqual(len(fxc) + 1, cap, f'{root}/{ch}: fx.png {len(fxc)} colours + transparency')
            shared = ROOT / root / 'fx' / 'fx.png'
            self.assertTrue(shared.exists(), f'{root}/fx/fx.png missing')
            self.assertLessEqual(len(sheet_colours(Image.open(shared).convert('RGBA'))) + 1, cap)

    def test_hd_frames_fit_the_cell_and_planted_soles_sit_on_row_114(self):
        soles = {rig.PID['sole_f'], rig.PID['sole_b']}
        for ch in CHARS:
            s = Sheet(ch, 'assets_hd')
            for name in s.anim:
                for facing in (1, -1):
                    for i, im in enumerate(s.frames(name, facing)):
                        bb = bbox(im)
                        self.assertIsNotNone(bb, f'{ch}/{name}/{i} is empty')
                        self.assertGreaterEqual(bb[1], 1, f'{ch}/{name}/{i} touches the top edge')
                        self.assertLessEqual(bb[3], 120, f'{ch}/{name}/{i} reaches row {bb[3] - 1}')
        try:
            rig.set_res(2)
            for ch in CHARS:
                body = roster.get(ch).body
                exact = total = 0
                for name, m in M.build_moves(ch).items():
                    if name in ('knockdown', 'ko', 'getup', 'sleep', 'wake'):
                        continue
                    for i, (pose, _) in enumerate(m['frames']):
                        grounded = (pose.ff[1] == 0 or pose.fb[1] == 0) and pose.lean > -45 and 0 <= pose.dy < 12 and not pose.flash
                        if not grounded or i % 3:                        # every third grounded pose: enough to catch a shifted floor
                            continue
                        buf, _ = rig.render_parts(body, pose, None)
                        px = buf.load()
                        low = max(y for y in range(128) for x in range(128) if px[x, y] in soles)
                        self.assertTrue(113 <= low <= 114, f'{ch}/{name}/{i}: lowest sole row {low}')
                        exact += low == 114
                        total += 1
                self.assertGreater(total, 40, ch)
                self.assertGreaterEqual(exact / total, 0.97, f'{ch}: planted soles off row 114 in {total - exact}/{total} poses')
        finally:
            rig.set_res(1)

    def test_hd_left_facing_frames_never_put_the_sigil_colour_on_skin(self):
        """The HD mirror redraws a 6x10 sigil box; it may only touch cap cloth / sigil pixels, never skin or hands."""
        try:
            rig.set_res(2)
            checked = 0
            for ch in CHARS:
                c, s = roster.get(ch), Sheet(ch, 'assets_hd')
                sig = c.body.palette['trim']['hi']
                for name, mv in M.build_moves(c).items():
                    for i, (pose, _) in enumerate(mv['frames']):
                        if i not in (0, mv.get('hit_frame'), mv.get('proj_frame')) or pose.flash:
                            continue
                        pts = tracks(ch)[name][i] if c.body.has_tail else None
                        buf, meta = rig.render_parts(c.body, pose, pts)
                        flipped = meta.get('pre_text', buf).transpose(Image.FLIP_LEFT_RIGHT).load()
                        left = rig.mirror_parts(buf, meta, c.body).load()
                        real = s.frame(name, i, -1).load()
                        x0, y0 = rig.sigil_box_l(meta, c.body)
                        for y in range(max(0, y0 - 2), min(128, y0 + 12)):
                            for x in range(max(0, x0 - 2), min(128, x0 + 8)):
                                if flipped[x, y] in SKINLIKE:
                                    self.assertEqual(left[x, y], flipped[x, y], f'{ch}/{name}/{i}: ({x},{y}) repainted')
                                    if flipped[x, y] in SKIN:
                                        self.assertNotEqual(real[x, y][:3], sig, f'{ch}/{name}/{i}: sigil colour on skin at ({x},{y})')
                        checked += 1
            self.assertGreater(checked, 300)
        finally:
            rig.set_res(1)


class Effects(unittest.TestCase):
    """fx.json follows the work-order schema exactly and every frame is a real crop of fx.png."""

    def _check(self, s, label):
        self.assertIsNotNone(s.fx, f'{label}: no fx.json')
        self.assertEqual(s.fx.get('res'), s.res, label)
        eff = s.fx['effects']
        self.assertIsInstance(eff, dict)
        W_, H_ = s.fxs.size
        for name, e in eff.items():
            self.assertEqual(set(e), FX_KEYS, f'{label}/{name}: keys {sorted(e)}')
            self.assertTrue(e['frames'], f'{label}/{name}: no frames')
            for f in e['frames']:
                self.assertEqual(set(f), {'x', 'y', 'w', 'h', 'ms'}, f'{label}/{name}')
                self.assertTrue(f['w'] > 0 and f['h'] > 0 and f['ms'] > 0, f'{label}/{name}: {f}')
                self.assertTrue(0 <= f['x'] and 0 <= f['y'] and f['x'] + f['w'] <= W_ and f['y'] + f['h'] <= H_, f'{label}/{name}: frame outside fx.png {f}')
                self.assertIsNotNone(s.fxs.crop((f['x'], f['y'], f['x'] + f['w'], f['y'] + f['h'])).getbbox(), f'{label}/{name}: empty frame {f}')
            self.assertIn(e['anchor'], ('hand', 'ground', 'center'), f'{label}/{name}')
            self.assertIn(e['layer'], ('front', 'back'), f'{label}/{name}')
            self.assertTrue(isinstance(e['offset'], list) and len(e['offset']) == 2 and all(isinstance(v, int) for v in e['offset']), f'{label}/{name}')
            self.assertIsInstance(e['loop'], bool, f'{label}/{name}')
            self.assertTrue(e['hit_frame'] is None or 0 <= e['hit_frame'] < len(e['frames']), f'{label}/{name}: hit_frame')
            self.assertTrue(e['travel'] is None or (set(e['travel']) == {'speed'} and e['travel']['speed'] > 0), f'{label}/{name}: travel')
            self.assertTrue(e['shake'] is None or (set(e['shake']) == {'frames', 'amp'} and e['shake']['frames'] > 0 and e['shake']['amp'] > 0), f'{label}/{name}: shake')
        return eff

    def test_schema_and_frame_bounds_in_every_sheet(self):
        for root in ROOTS:
            for ch in CHARS:
                self._check(Sheet(ch, root), f'{root}/{ch}')
            shared = ROOT / root / 'fx'
            meta = json.loads((shared / 'fx.json').read_text(encoding='utf-8'))
            self.assertTrue(set(GENERIC_FX) <= set(meta['effects']), f'{root}/fx: generic set incomplete')

    def test_every_character_has_the_generic_set_banners_and_its_ultimate(self):
        for root, res in ROOTS.items():
            for ch in CHARS:
                s = Sheet(ch, root)
                eff = s.fx['effects']
                for n in GENERIC_FX + BANNER_FX:
                    self.assertIn(n, eff, f'{root}/{ch}: missing {n}')
                self.assertEqual(len(eff['letters']['frames']), 52, f'{root}/{ch}: letters = 26 glyphs x 2 sizes')
                small, big = eff['letters']['frames'][:26], eff['letters']['frames'][26:]
                self.assertGreater(min(f['h'] for f in big), max(f['h'] for f in small))
                self.assertEqual(len(eff['round_text']['frames']), 5)
                self.assertGreaterEqual(len(eff['shatter']['frames']), 6)
                self.assertEqual(eff['ko_stars']['loop'], True)
                self.assertIsNotNone(eff['explosion']['shake'])
                sig = s.meta['signature']
                ult = sig['ultimate']
                self.assertEqual(ult, ULTIMATES[ch])
                a = s.anim[ult]
                self.assertEqual(a['cat'], 'ultimate')
                for k in ('proj_frame', 'hit_frame', 'hand', 'fx', 'reach'):
                    self.assertIn(k, a, f'{root}/{ch}/{ult}: no {k}')
                self.assertTrue(len(a['hand']) == 2 and a['hand'][1] < 0, f'{root}/{ch}: hand anchor should be above the ground row')
                self.assertIn(ult, eff, f'{root}/{ch}: no effect named after the ultimate (engine get(<ultimate>) would go procedural)')
                self.assertTrue(a['fx'], f'{ch}/{ult}: no fx list')
                for spec in a['fx']:
                    self.assertIn(spec['name'], eff, f'{root}/{ch}: {ult} references effect {spec["name"]} not in fx.json')
                    if 'at' in spec:
                        self.assertTrue(0 <= spec['at'] < len(a['frames']))
                    else:
                        self.assertTrue(0 <= spec['from'] <= spec['to'] < len(a['frames']))
                windup = max(a['proj_frame'], a['hit_frame'])
                self.assertGreaterEqual(sum(f['ms'] for f in a['frames'][:windup]), 500, f'{ch}: an ultimate winds up before it lands')
                main = eff[ult]
                self.assertTrue(main['shake'] or main['travel'] or main['hit_frame'] is not None, f'{ch}: {ult} has no impact metadata')
                self.assertIn(f'{sig["special"]}_proj', eff)
                self.assertIn(f'{sig["special"]}_impact', eff)
                self.assertIn(f'{sig["super"]}_burst', eff)
                if ch == 'codex':
                    self.assertEqual(a.get('support'), 'shadow_clones')
                    self.assertEqual(s.anim['shadow_clones']['cat'], 'support')
                    self.assertIn('shadow_clones', eff)
                    self.assertIsNotNone(eff['shadow_clones']['travel'])
                    self.assertEqual(len(eff['shadow_clones']['frames']), 3)
                if res == 2:
                    lo = Sheet(ch).fx['effects']
                    self.assertEqual(set(lo), set(eff), f'{ch}: HD and RES 1 effect sets differ')
                    for n in ('kamehameha', 'getsuga', 'wind_scar', 'explosion'):
                        if n in eff:
                            self.assertEqual(eff[n]['frames'][1]['w'], lo[n]['frames'][1]['w'] * 2, f'{ch}/{n}: HD frames are 2x')

    def test_generic_effects_are_identical_across_characters(self):
        """The engine merges per-character sheets by name, so the generic art must not differ per character."""
        for root in ROOTS:
            ref = Sheet(CHARS[0], root)
            for ch in CHARS[1:]:
                s = Sheet(ch, root)
                for n in GENERIC_FX:
                    a, b = ref.fx['effects'][n], s.fx['effects'][n]
                    self.assertEqual({k: v for k, v in a.items() if k != 'frames'}, {k: v for k, v in b.items() if k != 'frames'}, f'{root}/{ch}/{n}')
                    for fa, fb in zip(a['frames'], b['frames']):
                        ia = ref.fxs.crop((fa['x'], fa['y'], fa['x'] + fa['w'], fa['y'] + fa['h']))
                        ib = s.fxs.crop((fb['x'], fb['y'], fb['x'] + fb['w'], fb['y'] + fb['h']))
                        self.assertEqual(ia.tobytes(), ib.tobytes(), f'{root}/{ch}/{n}: generic art differs')

    def test_beams_and_waves_are_wide_and_energy_has_a_white_core(self):
        s = Sheet('claude', 'assets_hd')
        beam = s.fx['effects']['kamehameha']
        self.assertGreaterEqual(beam['frames'][2]['w'], 256)
        f = beam['frames'][3]
        im = s.fxs.crop((f['x'], f['y'], f['x'] + f['w'], f['y'] + f['h']))
        self.assertIn((255, 255, 255), {p[:3] for _, p in im.getcolors(1 << 16) if p[3]})
        self.assertEqual(beam['anchor'], 'hand')
        self.assertIsNotNone(beam['shake'])
        for ch, n in (('gemini', 'getsuga'), ('ollama', 'wind_scar'), ('generic', 'spirit_bomb')):
            e = Sheet(ch, 'assets_hd').fx['effects'][n]
            self.assertIsNotNone(e['travel'], f'{n} travels')
            self.assertGreaterEqual(e['frames'][0]['w'], 80, f'{n} is big')


def frame_hashes():
    """{'<root>/<char>': {proj, palette, moves: {name: {R, L, frames, meta}}}} for every built sheet."""
    import hashlib
    out = {}
    for root in ('assets', 'assets_hd'):
        for ch in CHARS:
            s = Sheet(ch, root)
            c = s.cell
            moves = {}
            for name, a in s.anim.items():
                r, n = a['row'], len(a['frames'])
                m = {}
                for key in ('R', 'L'):
                    row = s.sheets[key].crop((0, r * c, n * c, (r + 1) * c))
                    m[key] = hashlib.sha1(row.tobytes()).hexdigest()
                m['frames'] = [[f['ms'], f['dx']] for f in a['frames']]
                m['meta'] = {k: v for k, v in a.items() if k not in ('row', 'frames', 'hand')}
                moves[name] = m
            out[f'{root}/{ch}'] = dict(proj=hashlib.sha1(s.proj.tobytes()).hexdigest(), palette=s.meta['palette'], moves=moves)
    return out


if __name__ == '__main__':
    if '--regen-hashes' in sys.argv:
        (ROOT / 'tests' / 'fixtures' / 'v5_frame_hashes.json').write_text(json.dumps(frame_hashes(), indent=0), encoding='utf-8')
        print('wrote tests/fixtures/v5_frame_hashes.json')
    else:
        unittest.main()
