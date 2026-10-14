"""Sources: everything that can put a fighter on the taskbar.  Each detector yields Activity records.

  claude, codex      transcript-based (telemetry.Tracker): real state, context %, plan %.
  process detectors  a table of known AI programs, matched by executable name or command line (ctypes only, no file
                     reading).  State comes from the CPU use of the program's process tree over the last few seconds;
                     context and plan are unknown (None -> the plate shows '-').  Anything not in the table never shows.

A program is never counted twice: rules that point at `claude` or `codex` only *claim* processes for those transcript
sources (the Codex desktop app is ChatGPT.exe under an OpenAI.Codex_* package folder: it is Codex, not ChatGPT), and a
claimed process - with its children - is left out of every other program's CPU tree.
"""
from __future__ import annotations
import os, time
from collections import deque
from dataclasses import dataclass, field

from .telemetry import Snapshot, Tracker, Transitions

TRANSCRIPT_SOURCES = ('claude', 'codex')
LAUNCHERS = {'npx', 'npx-cli', 'npm-cli', 'npm', 'bunx', 'uvx', 'pipx', 'pnpm', 'dlx'}
INTERPRETERS = {'node.exe', 'bun.exe', 'deno.exe', 'python.exe', 'pythonw.exe', 'python3.exe', 'py.exe', 'uv.exe', 'uvx.exe'}

# First match wins, so claims come first.  exe: lower-case image names.  path_has: required substring of the image path.
# cmd: names matched against the first few argv tokens of an interpreter (basename without .js/.cmd/.exe/.mjs/.py),
# or a package path fragment.
RULES = [
    dict(source='codex', exe=('chatgpt.exe',), path_has='openai.codex_'),
    dict(source='codex', exe=('codex.exe',)),
    dict(source='codex', cmd=('codex', '@openai/codex')),
    dict(source='claude', exe=('claude.exe',)),
    dict(source='claude', cmd=('claude', '@anthropic-ai/claude-code')),
    dict(source='cursor', program='Cursor', character='cursor', exe=('cursor.exe',)),
    dict(source='windsurf', program='Windsurf', character='generic', exe=('windsurf.exe',)),
    dict(source='ollama', program='Ollama', character='ollama', exe=('ollama.exe', 'ollama app.exe')),
    dict(source='lmstudio', program='LM Studio', character='lmstudio', exe=('lm studio.exe',)),
    dict(source='gemini', program='Gemini', character='gemini', exe=('gemini.exe',), cmd=('gemini', '@google/gemini-cli')),
    dict(source='aider', program='aider', character='generic', exe=('aider.exe',), cmd=('aider',)),
    dict(source='opencode', program='opencode', character='generic', exe=('opencode.exe',), cmd=('opencode', 'opencode-ai')),
]
PROGRAM = {'claude': 'Claude Code', 'codex': 'Codex'}
for _r in RULES:
    PROGRAM.setdefault(_r['source'], _r.get('program', _r['source']))
CHARACTER = {r['source']: r.get('character', r['source']) for r in RULES}


@dataclass
class Activity:
    source_id: str
    program: str
    character: str
    state: str = 'idle'
    ctx_pct: float | None = None
    plan_pct: float | None = None
    plan_label: str = ''
    resets_in: str = ''
    last_active: float = 0.0
    events: list = field(default_factory=list)

    def snapshot(self) -> Snapshot:
        return Snapshot(self.character, self.state, self.ctx_pct, self.plan_pct, self.plan_label, self.resets_in, events=list(self.events))


def _stem(tok):
    b = tok.replace('\\', '/').rstrip('/').rsplit('/', 1)[-1].lower()
    for ext in ('.js', '.mjs', '.cjs', '.cmd', '.exe', '.py', '.ps1'):
        if b.endswith(ext):
            return b[:-len(ext)]
    return b


def cmd_matches(argv, names):
    """True if one of the first few non-option arguments after the interpreter is one of `names` (or contains a package
    path like @google/gemini-cli).  Only names and package paths are compared; nothing is kept."""
    argv = argv or []
    if any(a in ('-c', '-e', '--eval', '-p', '--print') for a in argv[1:2]):
        return False                                              # inline code: its text is not a program name
    rest = [t for t in argv[1:] if t and not t.startswith('-')]
    if len(argv) > 2 and argv[1] == '-m':                         # python -m aider
        rest = [argv[2]] + rest
    toks = rest[:1]                                               # the script or module, never a later argument
    if rest and _stem(rest[0]) in LAUNCHERS:                      # npx @google/gemini-cli, uvx aider-chat, ...
        toks = rest[:2]
    toks = [t for t in toks if not any(c.isspace() for c in t)]
    for t in toks:
        low = t.replace('\\', '/').lower()
        for n in names:
            if '/' in n or n.startswith('@'):
                if n in low or n.split('/')[-1] in low.split('/'):
                    return True
            elif _stem(t) == n:
                return True
    return False


# ------------------------------------------------------------------ transcript sources
class TranscriptSource:
    def __init__(self, who, cfg, clock=time.time, feed_path=None):
        self.source_id = who
        self.tracker = Tracker(who, cfg, clock=clock, feed_path=feed_path)
        self.cfg = cfg

    def poll(self, now):
        snap = self.tracker.poll(now)
        m = self.tracker.mtime
        if not self.tracker.path or m is None or now - m > self.cfg['stale_session_hours'] * 3600:
            return []                                              # no session at all: this program is not around
        return [Activity(self.source_id, PROGRAM[self.source_id], self.source_id, snap.state, snap.ctx_pct, snap.plan_pct,
                         snap.plan_label, snap.resets_in, last_active=m, events=list(snap.events))]


# ------------------------------------------------------------------ process sources
class ProcessScanner:
    """One pass over the process list classifies every process by RULES, builds each program's tree (children included,
    claimed and other programs' processes excluded) and measures its CPU over a sliding window."""

    def __init__(self, cfg, info=None, rules=None):
        if info is None:
            from minis_win import procs
            info = procs.Info
        self.cfg, self.info, self.rules = cfg, info, rules or RULES
        self._cls = {}           # (pid, create) -> source or None   (command lines are read once per process)
        self._cpu = {}           # (pid, create) -> last cpu seconds
        self.groups = {}         # source -> dict(samples=deque[(t, cum)], cum, last_active, first_seen, tr)
        self.claimed = {}        # source -> pid count (diagnostics)

    def _classify(self, pid, name, create):
        key = (pid, create)
        if key in self._cls:
            return self._cls[key]
        src = None
        argv = None
        for r in self.rules:
            if name in r.get('exe', ()):
                ph = r.get('path_has')
                if ph:
                    p = self.info.path(pid)
                    if not p or ph not in p.lower():
                        continue
                src = r['source']
                break
            if r.get('cmd') and name in INTERPRETERS:
                if argv is None:
                    argv = self.info.argv(pid) or []
                if cmd_matches(argv, r['cmd']):
                    src = r['source']
                    break
        self._cls[key] = src
        return src

    def scan(self, now):
        """-> {source: (state, last_active, events)} for every program from the table that is running."""
        plist = self.info.list()
        kids, times = {}, {}
        for pid, ppid, name in plist:
            kids.setdefault(ppid, []).append(pid)
        names = {pid: name for pid, _, name in plist}
        owner = {}
        for pid, ppid, name in plist:
            if name not in INTERPRETERS and not any(name in r.get('exe', ()) for r in self.rules):
                continue
            t = self.info.times(pid)
            if not t:
                continue
            times[pid] = t
            src = self._classify(pid, name, t[0])
            if src:
                owner[pid] = src
        roots = {}
        for pid, src in owner.items():
            roots.setdefault(src, []).append(pid)
        self.claimed = {s: len(v) for s, v in roots.items() if s in TRANSCRIPT_SOURCES}
        seen_keys = set()
        out = {}
        for src, rs in roots.items():
            if src in TRANSCRIPT_SOURCES:
                continue
            tree, stack = set(), list(rs)
            while stack:                                           # children, but never another program's or a claimed one
                p = stack.pop()
                if p in tree or (p in owner and owner[p] != src):
                    continue
                tree.add(p)
                stack.extend(kids.get(p, []))
            delta = 0.0
            for p in tree:
                t = times.get(p) or self.info.times(p)
                if not t:
                    continue
                key = (p, t[0])
                seen_keys.add(key)
                if key in self._cpu:
                    delta += max(0.0, t[1] - self._cpu[key])        # a process first seen now counts from now on
                self._cpu[key] = t[1]
            g = self.groups.get(src)
            if g is None:
                g = self.groups[src] = dict(samples=deque(), cum=0.0, last_active=0.0, tr=Transitions(self.cfg))   # never active yet
            g['cum'] += delta
            g['samples'].append((now, g['cum']))
            win = self.cfg['proc_window_s']
            while len(g['samples']) > 2 and g['samples'][1][0] <= now - win:
                g['samples'].popleft()
            t0, c0 = g['samples'][0]
            rate = (g['cum'] - c0) / (now - t0) * 100.0 if now - t0 >= 1.0 else 0.0
            g['rate'] = rate
            state = 'working' if rate >= self.cfg['proc_working_cpu_pct'] else 'idle'
            if state == 'working':
                g['last_active'] = now
            snap = g['tr'].apply(Snapshot(src, state), now)
            out[src] = (snap.state, g['last_active'], snap.events)
        for k in list(self._cpu):
            if k not in seen_keys:
                del self._cpu[k]
        live = {(pid, times[pid][0]) for pid in times}
        for k in list(self._cls):
            if k not in live:
                del self._cls[k]
        for src in list(self.groups):
            if src not in out:
                del self.groups[src]                               # program closed: start fresh if it comes back
        return out


class ProcessSource:
    """All process programs (or just `only`), as Activities."""

    def __init__(self, cfg, scanner=None, only=None):
        self.scanner = scanner or ProcessScanner(cfg)
        self.only = only

    def poll(self, now):
        acts = []
        for src, (state, last, events) in sorted(self.scanner.scan(now).items()):
            if self.only and src != self.only:
                continue
            acts.append(Activity(src, PROGRAM.get(src, src), CHARACTER.get(src, 'generic'), state, last_active=last, events=list(events)))
        return acts


# ------------------------------------------------------------------ registry
class Sources:
    """Every detector.  poll(now) -> [Activity] for whatever is around right now."""

    def __init__(self, cfg, detectors=None, clock=time.time):
        self.cfg = cfg
        self.detectors = detectors if detectors is not None else [
            TranscriptSource('claude', cfg, clock), TranscriptSource('codex', cfg, clock), ProcessSource(cfg)]

    def poll(self, now):
        out, ids = [], set()
        for d in self.detectors:
            try:
                acts = d.poll(now)
            except Exception:                                      # one broken detector must not hide the others
                acts = []
            for a in acts:
                if a.source_id not in ids:
                    ids.add(a.source_id)
                    out.append(a)
        return out


def detector_for(source_id, cfg, clock=time.time):
    """The single detector a fighter slot runs for its assigned source."""
    if source_id in TRANSCRIPT_SOURCES:
        return TranscriptSource(source_id, cfg, clock)
    return ProcessSource(cfg, only=source_id)
