# Fighter move list

Generated from `assets/*/anim.json` by `tools/gen_movelist.py`; every number below is read from the real sheets. "Used" is decided from the planner: a move says *yes* only if `minis_core/brain.py` triggers it or it is a signature move (the planner reads each character's signature strike / special / super from its atlas).

## At a glance

- **13 characters**: Claude, Codex, Gemini, Cursor, Ollama, LM Studio, Agent, Barbarian, Knight, Kunoichi, Monk, Nomad, Oni. Each has the same **45 shared moves** plus **three signature moves** (49 moves, 263 frames for Claude).
- 43 of 45 shared moves are triggered by the planner today, and every signature move is; 2 shared moves are built and waiting for a trigger (listed at the end).
- Which character appears is decided by the **director** from what is running (at most two at a time, slot `a` left and slot `b` right).

## The roster

| character | plate tag | accent | strike | special (projectile) | super | ultimate (40 dmg) | shown for |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Claude | `/reverse` | #F0A184 | `spin_kick` | `slash_wave` | `reverse` | `kamehameha` | Claude Code transcripts |
| Codex | `$reverse` | #A99DFF | `ground_pound` | `deploy` | `sudo` | `rasengan` | Codex transcripts (CLI, Emdash, desktop app) |
| Gemini | `*gemini` | #7FA8F2 | `spin_kick` | `star_shot` | `twin_flash` | `getsuga` | Gemini |
| Cursor | `>cursor` | #5FD3F3 | `ground_pound` | `tab_bolt` | `autocomplete` | `odm_strike` | Cursor |
| Ollama | `ollama` | #E9E2D2 | `ground_pound` | `pull_shot` | `serve` | `wind_scar` | Ollama |
| LM Studio | `lmstudio` | #7CF8EA | `spin_kick` | `load_wave` | `hot_swap` | `bankai` | LM Studio |
| Agent | `agent` | #E0C46C | `spin_kick` | `energy_bolt` | `overclock` | `spirit_bomb` | Windsurf, aider, opencode, Copilot CLI, Qwen Code, Perplexity, Grok (and any character whose art is missing) |
| Barbarian | `barbarian` | #FF8A4A | `axe_spin` | `axe_toss` | `berserk` | `earthsplitter` | - |
| Knight | `knight` | #7FA8FF | `crusher` | `sword_wave` | `valor` | `holy_crescent` | - |
| Kunoichi | `kunoichi` | #FF5A7A | `fan_whirl` | `petal_shot` | `vanish` | `petal_dance` | - |
| Monk | `monk` | #F2C14E | `palm_crash` | `chi_bolt` | `meditate` | `chi_sphere` | - |
| Nomad | `nomad` | #2A9D8F | `ring_spin` | `chakram_throw` | `mirage` | `ring_storm` | - |
| Oni | `oni` | #E04A3A | `club_slam` | `oni_fire` | `rampage` | `oni_roar` | - |

### Signature moves

| character | move | role | frames | length | what it is |
| --- | --- | --- | ---: | ---: | --- |
| Claude | `spin_kick` | strike | 8 | 920 ms | Claude's signature spinning kick. · reach 26 px, contact at frame 4 |
| Claude | `slash_wave` | special | 7 | 900 ms | Throws a "/" slash wave across the taskbar. Costs nothing; looks cool. |
| Claude | `reverse` | super | 7 | 760 ms | "/reverse": rewinds to where it stood a second ago, dodging everything. Afterimage trail. |
| Claude | `kamehameha` | ultimate | 8 | 2060 ms | Cups both hands at the hip, charges for a full second, then fires a horizontal beam the width of the taskbar. · reach 30 px, contact at frame 6 · 40 damage · effects: `kamehameha_charge`, `kamehameha` |
| Codex | `ground_pound` | strike | 8 | 1110 ms | Codex's heavy leaping slam with a ground shockwave. · reach 19 px, contact at frame 4 |
| Codex | `deploy` | special | 8 | 1010 ms | Types a command and hits ENTER: fires a ">_" bolt across the taskbar. |
| Codex | `sudo` | super | 7 | 890 ms | "$reverse": raises a giant $ and powers up with elevated permissions. |
| Codex | `rasengan` | ultimate | 8 | 1280 ms | Spins a sphere of energy in one hand, dashes in with afterimages and drives it home in a spiral burst. · reach 27 px, contact at frame 6 · 40 damage · effects: `rasengan_orb`, `rasengan_burst` |
| Gemini | `spin_kick` | strike | 8 | 920 ms | Gemini's spinning kick, both blades whipping round. · reach 26 px, contact at frame 4 |
| Gemini | `star_shot` | special | 7 | 900 ms | Two-handed push that fires a "*" sparkle along the taskbar. |
| Gemini | `twin_flash` | super | 7 | 760 ms | Flash-steps back a second in time, leaving a sparkle and an afterimage trail. |
| Gemini | `getsuga` | ultimate | 8 | 1440 ms | Raises an arm, gathers energy and swings down a giant crescent slash wave. · reach 30 px, contact at frame 5 · 40 damage · effects: `getsuga_charge`, `getsuga` |
| Cursor | `ground_pound` | strike | 8 | 1110 ms | Cursor's leaping slam with a ground shockwave. · reach 19 px, contact at frame 4 |
| Cursor | `tab_bolt` | special | 8 | 1010 ms | Accepts a suggestion and hits TAB: fires a ">|" caret bolt across the taskbar. |
| Cursor | `autocomplete` | super | 7 | 890 ms | Raises a giant ">" and powers up: the whole line completes itself. |
| Cursor | `odm_strike` | ultimate | 8 | 1010 ms | Fires two grapple lines, zips across them and finishes with a spinning cross slash. · reach 28 px, contact at frame 6 · 40 damage · effects: `odm_lines`, `odm_slash` |
| Ollama | `ground_pound` | strike | 8 | 1110 ms | Ollama's llama stomp with a ground shockwave. · reach 19 px, contact at frame 4 |
| Ollama | `pull_shot` | special | 8 | 1010 ms | "ollama pull": hurls a wool-white orb across the taskbar. |
| Ollama | `serve` | super | 7 | 890 ms | "ollama serve": raises a giant "o" and powers up, local and unstoppable. |
| Ollama | `wind_scar` | ultimate | 8 | 1540 ms | Raises both arms, then slams down and rips three claws of energy along the ground. · reach 26 px, contact at frame 5 · 40 damage · effects: `wind_scar_charge`, `wind_scar` |
| LM Studio | `spin_kick` | strike | 8 | 920 ms | LM Studio's spinning kick, the energy blade trailing. · reach 26 px, contact at frame 4 |
| LM Studio | `load_wave` | special | 7 | 900 ms | Loads a model and throws it as a teal-and-magenta wave across the taskbar. |
| LM Studio | `hot_swap` | super | 7 | 760 ms | Hot-swaps back to where it stood a second ago, afterimage trail and a giant "L". |
| LM Studio | `bankai` | ultimate | 8 | 1270 ms | Releases a pillar of aura, then lands three flash-step strikes faster than the eye. · reach 30 px, contact at frame 4 · 40 damage · effects: `bankai_aura`, `bankai_slash` |
| Agent | `spin_kick` | strike | 8 | 920 ms | A spinning kick: every agent learns this one. · reach 26 px, contact at frame 4 |
| Agent | `energy_bolt` | special | 8 | 1010 ms | Types a command and fires an energy orb across the taskbar. |
| Agent | `overclock` | super | 7 | 890 ms | Raises a giant "+" and powers up: everything runs faster. |
| Agent | `spirit_bomb` | ultimate | 8 | 1760 ms | Raises both hands, gathers a huge slow ball of energy overhead and hurls it. · reach 24 px, contact at frame 5 · 40 damage · effects: `spirit_bomb_orb`, `spirit_bomb` |
| Barbarian | `axe_spin` | strike | 8 | 920 ms | A wild spinning kick, axe swinging round with it. · reach 27 px, contact at frame 4 |
| Barbarian | `axe_toss` | special | 8 | 1010 ms | Hurls a spinning hand-axe across the taskbar. |
| Barbarian | `berserk` | super | 7 | 890 ms | Roars under a giant "V" and goes berserk. |
| Barbarian | `earthsplitter` | ultimate | 8 | 1540 ms | Raises the axe, then splits the ground with three tearing shock claws. · reach 26 px, contact at frame 5 · 40 damage · effects: `wind_scar_charge`, `wind_scar` |
| Knight | `crusher` | strike | 8 | 1110 ms | Leaps and brings the greatsword down with a ground-shaking crash. · reach 19 px, contact at frame 4 |
| Knight | `sword_wave` | special | 7 | 900 ms | A two-handed sweep that sends a steel wave across the taskbar. |
| Knight | `valor` | super | 7 | 890 ms | Raises the greatsword under a giant "T" and steels itself. |
| Knight | `holy_crescent` | ultimate | 8 | 1440 ms | Raises the greatsword, gathers light and cleaves a giant crescent down the taskbar. · reach 31 px, contact at frame 5 · 40 damage · effects: `getsuga_charge`, `getsuga` |
| Kunoichi | `fan_whirl` | strike | 8 | 920 ms | A spinning kick with both fans snapping open. · reach 26 px, contact at frame 4 |
| Kunoichi | `petal_shot` | special | 7 | 900 ms | Sweeps a fan and sends a spinning blade-petal across the taskbar. |
| Kunoichi | `vanish` | super | 7 | 760 ms | Vanishes back a second in a swirl of petals, a giant "x" where she stood. |
| Kunoichi | `petal_dance` | ultimate | 8 | 1270 ms | A burst of crimson aura, then three flash-step fan cuts faster than the eye. · reach 29 px, contact at frame 4 · 40 damage · effects: `bankai_aura`, `bankai_slash` |
| Monk | `palm_crash` | strike | 8 | 1110 ms | Leaps and drives both tonfa into the ground. · reach 19 px, contact at frame 4 |
| Monk | `chi_bolt` | special | 8 | 1010 ms | Thrusts a tonfa and fires a ball of chi across the taskbar. |
| Monk | `meditate` | super | 7 | 890 ms | Centres itself under a giant "O"; the aura flares. |
| Monk | `chi_sphere` | ultimate | 8 | 1760 ms | Raises both tonfa, gathers a huge sphere of chi overhead and hurls it. · reach 28 px, contact at frame 5 · 40 damage · effects: `spirit_bomb_orb`, `spirit_bomb` |
| Nomad | `ring_spin` | strike | 8 | 920 ms | A spinning kick, both chakrams whirling. · reach 26 px, contact at frame 4 |
| Nomad | `chakram_throw` | special | 7 | 900 ms | Whips a chakram across the taskbar. |
| Nomad | `mirage` | super | 7 | 760 ms | Slips back a second like a heat mirage, a giant "Y" left behind. |
| Nomad | `ring_storm` | ultimate | 8 | 1010 ms | Throws two chakrams on lines, zips after them and finishes with a spinning cross cut. · reach 22 px, contact at frame 6 · 40 damage · effects: `odm_lines`, `odm_slash` |
| Oni | `club_slam` | strike | 8 | 1110 ms | Leaps and smashes the kanabo into the ground. · reach 19 px, contact at frame 4 |
| Oni | `oni_fire` | special | 8 | 1010 ms | Spits a ball of oni-fire across the taskbar. |
| Oni | `rampage` | super | 7 | 890 ms | Swells under a giant "H", eyes blazing. |
| Oni | `oni_roar` | ultimate | 8 | 2060 ms | Plants the kanabo, draws a breath for a full second and roars a beam of fire across the taskbar. · reach 32 px, contact at frame 6 · 40 damage · effects: `kamehameha_charge`, `kamehameha` |

## What makes them move

| the agent is... | the fighter does |
| --- | --- |
| working (context under 70%) | `work` and `type`, alternating every 8-14 s |
| working, context 70%+ | `powerup` (aura charging) |
| idle | `idle`, with an `idle_flourish` every 6-10 s (1 in 4 is its signature super) |
| idle, context 85%+ | `rage` (aura on) |
| quiet for 45 s mid-turn | `wait` (foot tap), with a `shrug` every 10-16 s |
| no session for 30 min | `sleep` (dimmed), then `wake` when it comes back |
| finished a task (15 s+ of work) | `victory` |
| at its limit (90%+) | `ko` for 6 s, then `getup`, then `dizzy` while it stays there |
| paused (`minis.py pause` or the right-click menu) | one static `idle` frame; the plate keeps updating; no walking, no bouts |

Program sources without numbers (Cursor, Ollama, LM Studio, Gemini, aider, opencode, Windsurf) are *working* while their process tree uses more than 15% of one CPU core (averaged over 6 s), otherwise *idle*; their plate shows `ctx -`.

## Matches, HP and winners (V4)

A **match** is best-of-3 rounds: both fighters start a round at 100 HP; a landed move does power x 12 (12 / 24 / 36), a super 24, the ultimate 40; a round ends at 0 HP or after 25 s (higher HP wins).  `ROUND n` / `FIGHT!` / `K.O.` / `WINNER` texts and every hit, block and KO effect come from the effects sheet.  Winners are drawn from the seed: **decided** (default) weights each exchange by the health score = (100 - ctx%) + 20 if not at the limit + 10 if working; **random** is even.  `python minis.py winners random|decided` or the right-click menu switches it.  W/L per character live in `%LOCALAPPDATA%\minis\record.json` and show on the scoreboard widget.  A match starts every 3-6 minutes while both are awake, from `minis.py demo match`, the menu, or the scoreboard's *Bout now*; the same fighters fight the same way in **arena mode** (`minis.py arena --monitor N`).

## What makes them *interact* (separate processes; only tiny bus events pass between them)

| trigger | what happens |
| --- | --- |
| both agents working | **Clash** every 20-40 s: two quick exchanges and a fist-bump, no bows |
| both idle | **Spar** or **ranged duel** every 60-120 s: slot `a` invites, slot `b` accepts, both derive the same timeline |
| one finishes a task | **Handoff**: the finished fighter gives, the other walks over, takes the diff, reviews it for 6 s, gives a thumbs-up, they fist-bump |
| one hits its limit | **Console**: the other walks over (only if the knocked-out one is at home) and pats it on the shoulder, waves, goes home |
| one asleep or paused | no bouts |
| a mouse drag, a pause, a reassignment, or one hitting its limit mid-bout | the bout is cancelled on both sides; each walks home |

**Spar**: bow, four exchanges (attacker move, defender block / hit), then fist-bump or high-five, bow. The strike pool is the five shared strikes plus the attacker's signature strike. A strike's contact frame and the defender's reaction start on the same instant (tested to 0.01 s).  **Ranged duel**: each fighter casts its signature special, the projectile crosses the gap, the other blocks, then a taunt.  **Handoff**: the giver releases the diff on the exact frame the taker grabs it.

## Shared moves by category

### Locomotion

| move | frames | length | used | what it is |
| --- | ---: | ---: | :---: | --- |
| `idle` | 8 | 1190 ms↻ | yes | Default guard stance (idle, done). |
| `idle_flourish` | 6 | 620 ms | yes | Every 6-10 s while idle: shoulder roll and a hop (1 in 4 is the super instead). |
| `walk` | 6 | 600 ms↻ | yes | Walking to a bout, wandering, or visiting. Stride-locked: 40 px/s, feet do not slide. |
| `walk_back` | 6 | 660 ms↻ | yes | Backing away while still facing the other fighter. |
| `dash` | 5 | 360 ms | yes | Hop-step forward to close distance. |
| `turn` | 2 | 120 ms | not yet | Pivot to face the other way. |
| `crouch` | 3 | 300 ms↻ | not yet | Low stance. |
| `jump` | 7 | 600 ms | yes | Neutral jump with squash on landing. |

### Strikes

| move | frames | length | used | what it is |
| --- | ---: | ---: | :---: | --- |
| `jab` | 7 | 640 ms | yes | Spar / clash: fast lead-hand strike, light hit. · reach 29 px, contact at frame 3 |
| `cross` | 7 | 830 ms | yes | Spar / clash: rear-hand power punch. · reach 30 px, contact at frame 3 |
| `uppercut` | 7 | 800 ms | yes | Spar / clash: rising launcher. · reach 14 px, contact at frame 3 |
| `low_kick` | 7 | 730 ms | yes | Spar / clash: ground sweep. · reach 26 px, contact at frame 3 |
| `roundhouse` | 8 | 1010 ms | yes | Spar / clash: high kick, heavy hit, longest hit-stop. · reach 27 px, contact at frame 3 |

### Defense

| move | frames | length | used | what it is |
| --- | ---: | ---: | :---: | --- |
| `backdash` | 5 | 350 ms | yes | Evasive hop back with afterimages. |
| `block` | 4 | 370 ms↻ | yes | Spar / duel: the defender raises guard just before a strike lands. |
| `block_hit` | 3 | 230 ms | yes | Spar / duel: the guard absorbs the hit with a flash. |
| `crouch_block` | 2 | 200 ms↻ | yes | Low guard. |
| `parry` | 4 | 420 ms | yes | Swat a strike aside. Counter window. · reach 32 px, contact at frame 1 |

### Reactions

| move | frames | length | used | what it is |
| --- | ---: | ---: | :---: | --- |
| `hit` | 5 | 360 ms | yes | Spar: head snap when a strike lands. |
| `hit_heavy` | 6 | 490 ms | yes | Spar: slides back and wobbles after a heavy strike. |
| `knockdown` | 7 | 610 ms | yes | Falls flat. (Spar is friendly, so it is reserved for a finisher.) |
| `getup` | 6 | 590 ms | yes | After a KO: kip up. |
| `dizzy` | 4 | 520 ms↻ | yes | Stagger with stars: shown while a fighter stays at its limit. |
| `ko` | 7 | 890 ms↻ | yes | Context or plan limit reached (90%+): knocked out, stars orbit. |

### Emotes

| move | frames | length | used | what it is |
| --- | ---: | ---: | :---: | --- |
| `victory` | 7 | 1270 ms | yes | A task finished (15 s+ of work, not a timeout): fist pump with a hop. |
| `victory2` | 4 | 560 ms | yes | Flex. The bigger-win version. |
| `taunt` | 6 | 720 ms | yes | End of a ranged duel: come-on beckon. |
| `wave` | 4 | 480 ms | yes | After consoling a KO. |
| `thumbs_up` | 4 | 600 ms | yes | The reviewer approves the diff. |
| `facepalm` | 4 | 560 ms | yes | Something broke. |
| `shrug` | 4 | 540 ms | yes | Waiting state: every 10-16 s, unsure. |

### State animations (what an agent is doing)

| move | frames | length | used | what it is |
| --- | ---: | ---: | :---: | --- |
| `work` | 6 | 540 ms↻ | yes | Working state: shadowboxing. |
| `type` | 6 | 540 ms↻ | yes | Working state: typing on an air keyboard. |
| `review` | 6 | 720 ms↻ | yes | Handoff: the receiving fighter strokes its chin and reads the diff. |
| `wait` | 4 | 600 ms↻ | yes | Waiting? state: foot tap, hands on hips (no new activity for 45 s). |
| `sleep` | 4 | 2400 ms↻ | yes | Sleeping state: no session in 30 minutes (dimmed). |
| `wake` | 4 | 700 ms | yes | Stretch and yawn when a sleeping fighter gets a session. |
| `powerup` | 5 | 400 ms↻ | yes | Working while context is past 70%: visibly charging. |
| `rage` | 4 | 320 ms↻ | yes | Idle while context is past 85%: aura on. |

### Paired moves

| move | frames | length | used | what it is |
| --- | ---: | ---: | :---: | --- |
| `bow` | 4 | 750 ms | yes | Respect bow before and after a spar (a clash skips the bows). |
| `fistbump` | 4 | 420 ms | yes | Ends every spar, clash and handoff, on the same frame for both. · reach 25 px, contact at frame 2 |
| `highfive` | 5 | 500 ms | yes | Alternative spar ending: jump high-five. · reach 18 px, contact at frame 2 |
| `handoff_give` | 6 | 840 ms | yes | Handoff: the fighter that just finished holds out the diff. |
| `handoff_take` | 6 | 780 ms | yes | Handoff: the other fighter takes the diff to review it. |
| `console` | 4 | 640 ms | yes | The other fighter hit its limit: pats it on the shoulder. |

↻ = loops. Frame counts and lengths are Claude's; reach differs slightly per body.

## HUD plate

A dark pill behind each fighter (it flips to the front side only when the back side would leave the zone). Line 1: the character's tag + the state word. Line 2: a 10-segment bar for **context fill of the active session** (`ctx 69%`), then the plan figure when one can be trusted (`wk 1%` for Codex under the trust rules, `5h 35%` for Claude only from the optional feed). The bar colour follows **context only**: accent under 70%, amber 70-89%, blinking red 90%+. Numbers and a state word only: never titles, prompts, file names or client names.

## Built but not triggered yet

`turn`, `crouch`. These have art, timing and tests; they need a trigger in `minis_core/brain.py`.

## Ideas to expand

**More fighting**

- **Throws and grapples** (needs a paired pose set): a shoulder toss the other fighter tumbles through.
- **Combo counter and hit-streak** text above a fighter ("3 HIT") when exchanges chain.
- **Super meter** that fills from something real, e.g. the cache-hit ratio, and spends on the signature super.
- **Parry into counter**: wire `parry`, `crouch_block`, `dash`, `backdash` into longer, less predictable bouts.

**Real signals instead of flair**

- **CI pass or fail** becomes win or lose; a failing test is a `facepalm`.
- A **click** opens that agent's window; hover shows exact numbers and "resets in 2d 4h".

**Polish**

- Hand-polish key frames: drop a 64x64 PNG with the character's palette at `art/hand/<character>/<move>_<frame>.png` (or point `MINIS_HAND_DIR` elsewhere) and rebuild with `python art/build_fighters.py`.
- Second monitor support; per-monitor DPI scaling above 100%.
