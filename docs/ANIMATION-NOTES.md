# Animation notes (2026-10-13) - the rules the rig and every move follow

Written before touching `art/`. The author's verdict on the V4 output was "stiff and cheap": flat poses, capsule limbs,
even timing, no squash/stretch or smears, an afterimage that was a stack of tinted copies. These notes are the
research that drove the V5 rework, with the sources, and what each reference pack taught in practice.

## 1. The twelve principles, as they apply at 64 px

The principles come from Thomas & Johnston's *The Illusion of Life*; the game-specific reading is the
[Game Developer article](https://www.gamedeveloper.com/production/the-12-principles-of-animation-in-video-games) and the
pixel-art weighting from [sprite-ai's guide](https://www.sprite-ai.art/guides/animation-principles). At sprite scale three
of them carry nearly all the weight: **timing, anticipation, squash & stretch**. Concretely:

- **Timing is per-frame milliseconds, never a fixed fps.** Even timing reads mechanical. Fast parts get 30-60 ms,
  holds get 120-300 ms. Ease-in = hold the first frames longer; ease-out = hold the last frames longer.
- **Anticipation is contrast.** Mariel Cartwright (Lab Zero, Skullgirls) on a six-frame punch budget: "even a frame of
  anticipation will make your move much better in terms of readability"
  ([GDC Vault](https://gdcvault.com/play/1020575/Animation-Bootcamp-Fluid-and-Powerful),
  [Siliconera](https://www.siliconera.com/fluid-powerful-animations-skullgirls-achieved/),
  [80.lv summary](https://80.lv/articles/tips-on-making-fluid-and-powerful-animations)). Anticipation frames usually
  *outnumber* the motion frames, and the body moves the opposite way first.
- **Squash & stretch keeps volume.** At 16-64 px it is 1-3 px: shorter + wider on the crouch and the landing, taller +
  narrower on the launch and the peak of a fast rise. Stretch the limb, not the whole sprite, on a strike.
- **Follow-through and overlapping action.** Head and torso lead a punch, the arm snaps after; cloth, hair and the scarf
  lag a frame behind and settle after the body stops. Overshoot past the rest pose, then settle back.
- **Arcs.** Hands and feet travel on curves, never straight lines between keys; a deliberately broken arc (a head snapping
  on a hit) reads as impact.
- **Secondary action, exaggeration, appeal.** Faces change on contact; push keys further than real; the silhouette of
  every key pose must read as a flat black shape.

## 2. Fighting-game timing rules (what we adopted)

- **Hitstop / impact freeze.** Both fighters freeze for about 9 / 11 / 13 frames at 60 fps for light / medium / heavy in
  modern Street Fighter, 14 in SF2 ([Sonic Hurricane](https://sonichurricane.com/?p=1043); definition on
  [Dustloop](https://dustloop.com/w/GGST/Esoterica)). That is 150 / 180 / 220 ms. Our moves carry it as `hitstop_ms`
  on the contact frame: 150 for power 1, 180 for power 2, 220 for power 3, 260-320 for an ultimate's landing frame.
- **The six-frame punch.** Anticipation (1-2 frames, 60-100 ms) -> smear (1 frame, 30-50 ms) -> contact hold (the
  `hit_frame`, 120-220 ms incl. hitstop) -> follow-through overshoot (1 frame, 60-80 ms) -> settle (1-2 frames, 80-120 ms).
- **Smear frame.** One frame between two extremes where the limb is drawn as the whole arc it swept, thick at the
  shoulder end and tapering to a point, with the limb's own colour and a lighter inner band; torso and head stay clean so
  the body still reads ([CGWire](https://blog.cg-wire.com/smear-frames/),
  [RebusFarm](https://static.rebusfarm.net/blog/smear-frames-in-animation-how-animators-create-fast-and-dynamic-motion),
  [Tiny Warrior on sub-pixel/smears](https://tinywarriorgames.com/2019/01/04/game-development-pixel-art-sub-pixel-animation/)).
- **Walk cycle = contact / down / passing / up.** Head lowest on *down* (the landed leg bends), highest on *passing/up*;
  arms counter the legs ([CSE 459 walk notes](https://courses.cs.washington.edu/courses/cse459/19au/assignments/assignment_5/index.html)).
  Six frames: contact, down, passing, contact, down, passing, with the head bobbing 1 px either way of rest.
- **Afterimage trail.** Spawn copies back along the path and fade them; in pixel art never use alpha, use solid
  palette-shifted copies with stepped dither density
  ([Defold thread](https://forum.defold.com/t/how-do-you-make-an-afterimage-effect/65628),
  [Easy Image Trail](https://syntheticpixel.itch.io/easy-image-trail-after-image-effect)). Ours: 3-4 copies, each
  further back on the motion arc, each smaller (scaled toward the ground anchor), each dimmer (checker -> 1-in-3 ->
  1-in-4 density, hi -> base -> sh tone).

## 3. What the reference packs taught (study only; every frame of ours is original)

**LuizMelo - Martial Hero** (CC0, 200 px cells; idle 8 / run 8 / jump 4 / fall 4 / attack 6+6 / hit 4 / death 6).
- Attack 1 = four nearly identical anticipation frames (1-2 px shifts: the pose is *held under tension*), then two
  frames of a crescent smear bigger than the character, with the body rotated and the hair whipping the other way.
  Anticipation : action = 4 : 2. The smear is pure white, no outline, drawn as a single cluster.
- The scarf/hair is one third of the silhouette and never still: it lags on every idle frame and streams flat on run.
- Take Hit: frame 0 is the full white silhouette, then the head and hair whip back further than the torso.
- Death: a fall through an arc, not a pivot: hips drop, shoulders lead, then the body settles over two frames.

**Mattz Art / xzany - Samurai** (free tier: idle 10 / run 16 / attack 7 / hurt 4, 96 px canvas, 18-19 colours).
- Attack 1: frames 0-3 hold the wind-up with sub-pixel shifts, frame 4 is the smear (a white slash wider than the body
  plus the body thrust forward), 5 fades the smear, 6 is the follow-through. The timing is "hold, hold, hold, hold, SNAP,
  fade, settle" and it is the single most useful pattern we copied structurally.
- Idle (10 frames): 1 px breathing on the chest, the hair tail sways with a one-frame delay. Nothing larger than 1 px moves.
- Run (16 frames): 25-30 degree lean, the back leg fully extended behind, hair streams horizontally; the head bobs 2 px.
- Hurt: white silhouette flash, then a 2-frame recoil, then settle.

**GandalfHardcore - Archer** (free tier; 64 px, 11-frame Fire, ~8 tones per colourway; licence: use + modify, no
redistribution, no AI training).
- Fire (11 frames) is the model for our ultimates' charge: draw the bow progressively over 7 frames (each frame a small,
  readable increment), release on one frame, then 3 frames of recovery with the bowstring vibrating (secondary action
  on the *tool*, not the body).
- Hit: frame 1 is a flat white silhouette with a burst, frame 2 a smaller burst, then 2 frames of settle.
- Eight tones per character at 64 px, two-tone clusters, one-pixel outlines only where a form meets the background.

**Visual inspiration only (not asset sources, nothing downloaded):**
[Game Academie](https://game-academie.itch.io/) store previews (64 px fighters: heavy single-colour clusters, no
interior lines) and [DullMesh's Cyber White Samurai](https://dullmesh.itch.io/free-rigged-stylized-cyber-white-samurai)
(white armour plates with neon edge light) - adopted as LM Studio's costume direction: white plates, teal/magenta
edge-light trim, and holographic (dithered neon) afterimages on its flash-steps.

## 4. The rules the V5 rig and moves follow

1. Every strike: 1-2 anticipation keys (opposite direction, 60-100 ms) -> 1 smear (30-50 ms) -> contact hold with
   `hitstop_ms` -> 1 overshoot (60-80 ms) -> settle (80-120 ms). No two consecutive frames share a duration.
2. Squash on every landing and every crouch (torso -10..-15 %, head wider), stretch on every launch (+10 %).
3. Cloth lags one frame behind the head in the direction opposite the motion, and settles after the body.
4. The head leads a hit reaction; the arms follow one frame later.
5. Idle moves nothing by more than 1 px; the chest expands, the head bobs, the scarf sways.
6. An afterimage is 3-4 copies back along the arc, each smaller and sparser, never a solid stack.
7. Limbs taper (shoulder/hip thick, wrist/ankle thin); hands have knuckles or fingers; shoes have a heel and a toe.

## 5. Where to look

- `qa/fluid/<character>-<category>.gif`: 4x reels at the real frame durations (locomotion, strikes, signature,
  defense, reactions, emotes, states, ultimate) for all seven characters; `qa/fluid/before-after.png` is five
  moves from the V4 snapshot above the V5 build; `qa/fluid/*-keyframes.png` are labelled strips (smear / HIT /
  hitstop / shake per frame).  Regenerate with `python art/qa_fluid.py reels <character> qa/fluid`.
- `tests/test_art.py`: `test_v5_timing_rules_on_every_strike` and `test_afterimages_trail_behind_the_motion_and_thin_out`
  assert rules 1 and 6 on the real sheets; `test_rows_match_the_v5_visual_regression_fixture` pins every row
  (`python tests/test_art.py --regen-hashes` after a change that was judged by eye).
- `anim.json` adds `hitstop_ms`, `shake`, `smear_frames` and `credits`; the top-level `schema_notes` describe them.
- `fx.json` (V5.1) adds two keys to every effect, described in its own `schema_notes`: `grow: {from_w, to_w, ms}` (the
  engine draws the effect stretched from `from_w` to `to_w` px over its first `ms` after spawn with the anchored end
  fixed, so a beam extends from the hands instead of appearing whole; `null` = draw the frames as authored) and
  `flash: true` (frame 0 is a one-frame white-hot release flash; the engine whitens the owner sprite on the taskbar
  and the whole overlay in the arena for that frame; never true on a looping effect). `art/fx.py` holds
  `FX_SCHEMA_NOTES`; `minis_core/fx.py` / `effects.py` read them, and an engine that does not know the keys ignores
  them. `python art/qa_v5.py beams` renders every beam, wave and burst at 4x with real timings to `qa/v5/beams.gif`.

## 6. Lessons from two fight-animation videos (2026-10-14)

Sources, studied only (nothing copied): "STRENGTH VS SPEED" by StickNodes (21 s stick-figure fight; frame-stepped at 6 fps) and
"I Animated a FULL FIGHT SCENE in Just 7 Days" by RJ Animations Too (transcript read in full, 14 min).

What the stick-figure clip does that ours does not (SEEN in the frames):
1. **Long anticipation, short action.** Fighters crouch, coil or hold a pose for many frames, then the strike lands in one or two
   frames. Our strikes spend their frames evenly, so nothing "pops".
2. **Held keyframes with sparse inbetweens.** Big gaps between poses, with a smear or blur between them, read faster than smooth
   tweening. Silhouette first: every key pose reads as a black shape.
3. **The ground is a stage.** Characters are thrown across it, skid, roll, spring up. Movement covers distance; ours stay in place.
4. **Smears are streaks, not shapes.** A thin curved trail from the limb's path (red arc on a kick, blue speed lines when a character
   dashes) plus a ghosted copy of the previous pose. Speed lines fill the whole frame on a rush.
5. **Camera and framing change.** Cuts between wide and close, and the world scrolls when someone dashes.
6. **Variety of rhythm.** Not every hit is the same length: a counter, a juggle in the air, a dash-through, a grapple, a finisher.

What the 7-day video teaches (SEEN in transcript):
1. **Key poses first, inbetweens last.** 35 keys for a whole fight; draw rough and loose ("scribbly") so gesture stays dynamic, stiffness
   comes from drawing too carefully.
2. **Retime the reference.** Copying real or 3D motion looks floaty; change the timing, widen the shot to show the silhouette, hold a
   key for several frames (they used a 6-frame hold), then speed up.
3. **Impact frames are the 2D trick.** On the biggest hit: a pose in silhouette with radial lines inside it (white background), then the
   inverse (black with white lines, lines longer and more chaotic), then short outline lines on white, then a blank white or black frame.
   Slow-motion plus an impact frame replaces a plain slow-mo.
4. **Simplify anatomy.** Generic characters with a simple face; inbetweens can be drawn as silhouettes only to save time.
5. **Use a colour per character** while roughing, so overlap stays readable.

How this turns into work for minis (the order is by payoff):
- **Impact frames.** A 2-4 frame sequence on heavy hits and ultimates: whole-sprite silhouette on white, inverse on black, radial lines
  clipped to the silhouette, then one blank frame. At 64 px that is a 100-160 ms flash; it must not read as a glitch, so it plays on
  contact only and never on every hit.
- **Anticipation and holds in `art/moves.py`.** Longer wind-ups (4-6 frames at the slow end), a one-frame contact, a smear frame, a 3-6
  frame hold after the big hits; shorter hits stay snappy. Vary durations per move instead of one flat 100 ms.
- **Travel.** Dash-through, slide, lunge and knockback that cover real distance on the strip, with dust and speed-line streaks.
- **Streak smears** drawn from the limb path (thin, tapered, one colour), plus one ghosted previous pose, instead of blobs.
- **Silhouette test.** Each key pose has to read as a black shape on `#202020` at 1x; if two poses look the same, redraw one.
- **No long trailing cloth** (owner: the cape/scarf "doesn't look good"). Short hanging parts that lag one frame only.
