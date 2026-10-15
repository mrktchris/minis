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

## 7. V6 fight feel in the engine (2026-10-14)

Found in a live taskbar recording and a 300-match audit; fixed in `minis_core/{choreo,rounds,brain,effects,fx,sim}.py`. Numbers
are from the same 300-match audit before / after (seeded, all roster pairs, played through the real `Brain` playback at 30 fps).

**Timing that is actually drawn.** The taskbar redrew at 10 fps during fights, so 40 ms smears, the halved hitstop (75 ms) and the
60 ms ultimate flash mostly fell between two redraws. Now: a fight script redraws at `fps_fight` (30); `Brain.held_ms` lengthens any
smear / hit frame shorter than 50 ms by taking the time from the frame before it (contact time and total unchanged, so the shared
timeline still lines up); hitstop has a 100 ms floor (`choreo.HITSTOP_FLOOR_MS`, blocks 70 ms); flashes last 100-120 ms; a knockback
slide runs on the animation clock, so it waits out the hitstop instead of sliding through the freeze.

**Knockdowns.** A knockdown that is not a KO no longer returns to idle before the get-up (the "stand, then fall again" bug); the
get-up starts the instant the fall ends, and nobody is hit while still on the floor.

**The finisher beat (match-deciding KO), inside 3.4 s:** a 280 ms freeze with impact frames, the fall in slow motion (0.55 s at
0.35x), dust on landing, the winner's victory pose under a name banner centred over where it really stands, the loser stays down
~1 s and slumps up (a get-up at 0.6x). V5 left the KO'd fighter lying ~6 s with nothing happening.

**Impact frames** (`@impact`, ANIMATION-NOTES section 6) play only on heavy hits (power 3), supers, ultimates and KOs, for 130 ms:
the fx `impact` on the struck fighter when the sheet has it, else a strong white flash. control.json `flashes` off removes every
flash and impact frame.

**Rarity.** The ultimate is a desperation move: only an attacker below 30 HP, one roll (35 %) per match, one per match between both
(1.72 -> 0.30 per match). Supers need a 250 hit meter (2.99 -> ~1.0 per match) and are never an idle flourish.

**Spacing and travel.** Bouts start 32 px apart; a strike stands its fighter at the move's own `reach` + 9 px from the defender; no
two hips come closer than 22 px (body-overlap frames 6.5 % -> 0.3 %). Knockback is 6 / 18 / 42 px (hit / heavy / knockdown) with a
dust skid; a far strike may be a lunge that slides the whole gap with dust.

**Story and rhythm.** Hit-vs-defence odds tilt up to 25 % toward the fighter behind on HP or rounds (2-0 rate 53 % -> ~28 %); the
loser of a round gets one comeback exchange; a KO lands with the signature strike; a launcher can be followed by a jump-up juggle
kick; ranged duels end with a landed hit or a parry and one taunt. The sweep opener goes through the picker; shadowboxing uses a
no-repeat picker every 8-14 s. A round called on time shows TIME and the loser slumps (no unprovoked fall). A defender braces
(guard, or a low guard below 30 HP) through a long wind-up. Fighters turn and walk home facing their way (no moonwalk), then turn
back. An agent that finishes a task opens the next bout (within 20 s) with its signature super (`plan['boost']`); near the context
limit, or below 25 HP in a match, a fighter pulses white once a second.

**Arena (same rules, `minis_core/arena.py`).** The arena plays the same V6 rules: tilt / comeback / boost / one desperation
ultimate per match, signature-strike KOs, a guard on long wind-ups, TIME + slump, the finisher (freeze, slow fall, name banner,
slowed get-up, KO -> exit about 3.4 s). Impact frames there are flat silhouettes of the two sprites (struck = white, striker =
dark) plus the fx `impact`, never a full-screen frame, and the arena reads control.json `flashes` itself. Pacing: V5 arena rounds
mostly ran out the clock (48 % TIME, mean 21.5 s) because a far special bounced between "approach" and "beat" until the exchange
deadline, fighters walked at 180 px/s, the defender flew to a ledge half the time and an exchange could start while someone was
on the floor. Fixed, plus walk 240 px/s, ledge 30 %, shorter cooldowns and arena hits x1.25 (the ultimate stays 40): 15 % TIME,
mean round 16 s over 40 seeded matches. Afterimages are now one per two frames and the sprite cache no longer thrashes, so a
frame costs less than before (1.06 vs 1.16 ms headless).

## 7. V6: the new roster, the weapon rig and real HD (2026-10-14)

The audit of V5.1: one stiff 3.3-head chibi recoloured seven times, 13 px heads with 1 px eyes, boxers with no weapons,
small kicks with tiny smears, and an HD build that was the 64 px frame doubled. What V6 changed (all in `art/`):

- **Proportions.** ~4.5 heads: 11 px head, 15 px torso, 20-23 px legs, 50-54 px tall in the 64 px cell (the engine
  bottom-aligns the cell on the taskbar, so the top ~11 px of a standing fighter now sit just above the 48 px taskbar).
  Pose data is still authored for the old body; `rig.skeleton()` scales hand targets by `ka`, foot lifts and hip drops
  by `kl`, foot spread by `stance` (walks pin `fk=1` so the planted foot never slides) and rises by `KJ` so a jump
  stays in the cell. A planted foot that cannot reach the floor sinks the hips instead of floating.
- **A held weapon is a rig part** (`rig.Weapon`: kind, length, grip, rest angle on the forearm, width, `slide` for
  poles, `grip2` for a two-handed grip). `Pose.wa` / `wb` aim it per key; a weapon that would leave the cell slides
  through the hand (spear, staff) or turns toward the side it already leans. Kinds: katana, short sword, energy blade,
  greatsword, dagger, kunai, spear, staff, kanabo, axe, tonfa, tessen fan, chakram, bow. Impact sparks of a weapon
  strike sit on the blade, and `reach` is measured from the weapon pixels.
- **Every swing draws its crescent.** On a smear frame the rig draws, behind the body, the white band between the path
  of the weapon's striking point and a path inside it (hairline at the start, widest just before the end, going round
  the front of the shoulder); a thrust gets a tapered band and two speed lines; a kick gets the same crescent off the
  hip. The frame after a smear draws a thin tapered streak along the path, and the smear frame keeps one checker
  ghost of the striking limb and weapon from the previous frame (section 6: streak smears plus one ghosted pose).
- **Timing (section 6).** Strikes are a two-key held wind-up (110-150 ms, then a 70-110 ms tension hold), one 40 ms
  smear with a lunge (`dx` 4-5), the contact hold with hitstop, then a held follow-through (220-280 ms) on medium and
  heavy hits; kicks turn the hips (`turn` 0.55-0.8). Dash and backdash cover 38 / 31 px with dust and speed lines.
- **Short hanging bits only** (`rig.Bit`: 2-3 segments, at most ~7 px): topknot tail, mask knots, tassels, sash ends,
  a plume, a turban tail, a chain. They hang by gravity and swing opposite to how far their anchor moved since the
  previous frame, so they lag one frame without any state. No long tails or capes.
- **Real HD.** RES 2 renders the same pose data into a 128 px cell with a one-pixel outline, five tones per material
  (rim, highlight, base, shadow, deep shadow), tinted inner lines where one material crosses another, one light
  direction (top-left, also for left-facing frames, which are shaded after the mirror) and HD-only detail drawn at
  pixel level: 2x2 eyes with a white, kasa straw seams, armour and plate seams, blade highlights, helmet breaths.
  Palettes are hue-shifted ramps (`rig.ramp`): highlights lean warm, shadows cool, outlines are a dark tint of the
  material, never black. Colour caps: <= 31 + transparency at RES 1, <= 63 at RES 2.
- **Impact frames.** Every character's `fx.json` has an `impact` effect (4 opaque cells, 40/40/40/30 ms): its ultimate
  contact pose as a silhouette on white with radial lines inside, the inverse on black with longer chaotic lines,
  broken outline strokes, one blank frame. The engine plays it on heavy (power 3) and ultimate contacts only.
- **Roster.** Thirteen characters: the seven program ids keep their names, moves and signatures (new bodies), and six
  selectable extras reuse the signature and ultimate templates under their own move names (`fx.character_effects`
  aliases the template's main effect to the move name).

Checks: `python art/qa_v6.py sheet <char|all> [--res 2]` (contact sheets with per-frame timing / HIT / smear labels),
`python art/qa_v6.py silhouettes` (every idle as flat black on #202020, 1x and 4x) and `python art/qa_v6.py lineup`.
`tests/test_art.py` asserts the proportions, a weapon and a swing crescent on every strike, distinct idle silhouettes
(IoU < 0.8 for every pair), short bits only, and the impact-frame sequence.

## 8. V7: every fighter fights like its weapon (2026-10-15)

Owner: "expand on the move list" - every fighter held a weapon after V6 but still fought with one shared, mostly unarmed
move set.  V7 adds weapon move families, new move *types* the choreographer understands, a contact system, a 128 px detail
pass and hand-authored set pieces.  All of it is generated by the rig from pose data (no copied frames), and every V3-V6
row of the 64 px build is byte-identical (checked against the old fixture before it was regenerated).

**Families** (`art/moves.py` `FAMILY_MOVES`, picked from the weapon: `FAMILY`): blade (Claude, LM Studio: iai draw-slash,
cross-cut, lunging riposte), dual (Gemini, Monk: three-cut flurry, scissor cut, spinning blade dance, rear-hand riposte),
polearm (Cursor: long thrust, low sweep, vault kick, overhead pole spin, choked-up jab), staff (Ollama: overhead slam with a
ground crack, sweep, pole vault), chain (Codex: chain pull, kunai toss, reverse-grip riposte; its dash-through is
`shadow_step`), bow (Agent: point-blank shot with the string drawn back to the cheek, three-arrow volley, leaping back-shot,
dagger riposte, a bow-limb guard break), fans / chakram (Kunoichi: fan gust, fan cut, fan flurry; Nomad: a chakram
boomerang that is caught again, ring slash, ring flurry), heavy (Knight, Barbarian, Oni: an armoured cleave, a ground slam
whose shock wave lands, a pommel riposte).  Shared types for everyone: air slash, spike, throw (+ `thrown`), dash-through,
guard break, a taunt variant, and the reactions `launched`, `air_hit`, `spiked`, `thrown`, `pulled`, `guard_crush`,
`hit_high`, `hit_low`, `hit_back`, `clash`.  8-10 new attack moves per character.

**Keying rules that came out of the per-frame QA** (every new move was rendered at 1x on a taskbar mock and at 4x, frame by
frame, plus a black-silhouette strip, and redrawn until it read):
1. *A weapon is never turned by the solver.*  `place_weapon` rotates a weapon whose ends would leave the cell; that made a
   level iai cut point at the sky and the riposte flip 96 degrees between two frames.  `fit_weapons` now pulls the hands in
   toward the shoulder (4 % steps) until the weapon fits at the angle the key asks for; keys that fit are untouched.
2. *Rises stay under the cell top.*  A jump with the arms overhead clipped the kasa; air moves rise 6-8 (not 12) and keep
   the hands at shoulder height on the apex.
3. *A pommel / shoulder drive is not a swing.*  A smear on the front weapon whose blade points backward drew a full
   crescent in front of the body; the guard break smears the driving arm (`smear_b`) with speed lines instead.
4. *A bow draw must show the string.*  `Pose.nock` bends the string to the rear hand with the arrow nocked; without it the
   draw read as a raised fist.
5. *The afterimage of a dash-through stays thin* (2 copies, then 1): three dense copies of a dark costume read as a blob.
6. *Heavy weapons are heavier* (`heavier`): the shared moves of the heavy family hold every wind-up frame x1.25 and the
   follow-through x1.15; the cleave winds up for ~590 ms and stays in the ground for 330 ms.
7. *A thrown weapon leaves the hand* (`Pose.nowf`) until its catch frame.
8. *In-cell missiles* (`arrow`, `kunai`, `chain`, `gust` in `rig.fx_draw`): the 64 px cell reaches past the opponent's front
   edge at bout distance, so short-range shots fly inside the attacker's own sprite and `reach` is measured from them.

**Contact** (part C).  Every landing move carries `hit` (slash / blunt / pierce) and `height` (high / mid / low / back).
The defender gets the spark for the kind (`hit_slash`: a thin bright arc that breaks into embers; `hit_blunt`: a white core,
a widening shock ring, dust; `hit_pierce`: a streak driven through and a spray behind; `block_deflect`: a clang flash and
sparks thrown back at the attacker; `clash_sparks`), a light hit plays a directional reaction (`hit_high` chin up,
`hit_low` doubled over, `hit_back` pitched forward), every landed hit shakes by power, and a freeze longer than 250 ms holds
the hit pose, not the one-frame white flash.  About a third of blocked or parried weapon strikes become a weapon lock: both
fighters play `clash` on the same instant, strain, and skid apart.

**128 px detail** (part B, RES 2 only - the 64 px build is unchanged): faces with an eye white, an iris and an upper lid, a
brow and a mouth per expression (determined lids, a shout with teeth, gritted teeth when hurt, a grin), knuckles across a
fist that grips a weapon, and a fold line inside every bent elbow and knee (`crease`: drawn last, coloured with the deep
shadow of the material it crosses).

**In the engine** (`minis_core/choreo.py`, `rounds.py`, `brain.py`): moves are picked by `type`, never by name.  A throw
starts the defender's row on the attacker's grab frame (both rows share `THROW_MS`), hoists it in and slams it out
(`path`: a second slide leg); a launcher pops the defender up and it hangs (`hold`) through the air slash until the spike;
a chain pull yanks it in on `pull_frame` (`slide_at`); a dash-through slides only during its burst, keeps its back turned,
swaps sides and vaults back; a boomerang projectile flies out and back to the catch frame; strings cancel on
`cancel_frame`; a heavy cleave shrugs off a poke (`@armor`).  The V6 rules stay: one desperation ultimate per match below
30 HP, supers behind the 250 meter, the finisher beat, the flashes switch.

**Set pieces** (part D, `minis_core/setpieces.py`): eight hand-authored joint exchanges written against weapon-family
slots - blade lock, pull and launch, cross-cut freeze, vault overhead, parry-riposte, guard crush, reversal, aerial finish -
played one to three per match at the dramatic moments (a round's second exchange, the comeback, match point), through the
same beat machinery so both slot processes derive them from the shared seed.  `python tools/setpiece_preview.py <piece>
--a <char> --b <char>` renders one frame by frame at taskbar size.

**Numbers** (`python -m minis_core.sim 300`: 300 seeded matches over every ordered roster pair, pure timelines):

| | before (V6) | after (V7) |
| --- | ---: | ---: |
| distinct attack moves per character | 9 | 17-19 |
| 10-minute sessions with 12+ distinct moves | 0 % | 100 % (fewest in one session: 16) |
| most-used move's share (worst character) | 17.4% | 13.5% |
| ultimates / supers per match | 0.29 / 0.88 | 0.24 / 0.53 |
| juggles / throws / dash-throughs / clashes per match | 0.97 / 0 / 0 / 0 | 2.36 / 0.6 / 0.95 / 0.56 |
| strings / guard breaks / ripostes per match | 0 / 0 / 0 | 1.5 / 0.44 / 0.97 |
| rounds called on time | 8.9% | 4.1% |
| 2-0 matches | 29% | 38% |
| mean round | 15.8 s | 13.7 s |

The 2-0 rate rose because set pieces and juggles land more damage per exchange; it stays under the V6 ceiling (45 %).

Checks: `tests/test_art.py` (`WeaponMovesV7`, `HD128`: 8+ weapon moves per character, the wind-up / smear / hold
contract on every new strike, throw and thrown on one clock, strings with cancel frames, the boomerang really leaving the
hand, missile reach, the drawn bow string, HD faces / knuckles / folds and nothing of them at 64 px),
`tests/test_rounds.py` (`WeaponFightsV7`: the 300-match audit, throw sync to 0.01 s, launch -> air hit -> spike with the
defender hanging, the boomerang's return on the catch frame, the dash-through swap and vault, both fighters locking on a
clash, string cancel timing, set pieces deterministic and 1-3 per match).  `qa/v7/<character>-moves-4x.png` and
`qa/v7/reactions-4x.png` are the 4x review sheets (1x taskbar strip, silhouettes, every frame with its timing).
