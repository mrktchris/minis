import json, os, sys, time, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import ROOT, CFG, Isolated, Clock  # noqa: E402
from minis_core import config as cfgmod  # noqa: E402
from minis_core import telemetry as T  # noqa: E402

FX = ROOT / 'tests' / 'fixtures'


def objs(rel):
    return [json.loads(l) for l in (FX / rel).read_text(encoding='utf-8').splitlines() if l.strip()]


def iso(t):
    return time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(t)) + '.%03dZ' % int(round((t % 1) * 1000))


# synthetic, content-free lines in the real key shapes
def c_asst(t, stop='tool_use', cache_read=500000, inp=1):
    return {'type': 'assistant', 'timestamp': iso(t), 'message': {'stop_reason': stop, 'usage': {'input_tokens': inp, 'cache_read_input_tokens': cache_read}}}


def c_user_tool_result(t):
    return {'type': 'user', 'timestamp': iso(t), 'message': {'role': 'user', 'content': [{'type': 'tool_result', 'content': 'redacted'}]}}


def x_evt(t, kind):
    return {'timestamp': iso(t), 'type': 'event_msg', 'payload': {'type': kind}}


def x_tokens(t, used=50000, win=258400, limit_id='codex', pct=40.0, resets=None, window=10080):
    primary = None if resets is None else {'used_percent': pct, 'window_minutes': window, 'resets_at': resets}
    return {'timestamp': iso(t), 'type': 'event_msg', 'payload': {'type': 'token_count', 'info': {'last_token_usage': {'input_tokens': used}, 'model_context_window': win},
                                                                    'rate_limits': {'limit_id': limit_id, 'primary': primary}}}


class ClaudeParser(unittest.TestCase):
    def now(self, rel, plus):
        ts = [o for o in objs(rel) if o.get('timestamp')][-1]['timestamp']
        return T.parse_iso(ts) + plus

    def test_working_mid_turn(self):
        s = T.parse_claude(objs('claude/working.jsonl'), self.now('claude/working.jsonl', 5), CFG)
        self.assertEqual(s.state, 'working')
        self.assertAlmostEqual(s.ctx_pct, (2 + 685 + 219120) / 1e6 * 100, places=1)

    def test_done_turn_is_idle(self):
        s = T.parse_claude(objs('claude/done.jsonl'), self.now('claude/done.jsonl', 5), CFG)
        self.assertEqual(s.state, 'idle')
        self.assertAlmostEqual(s.ctx_pct, (3 + 900 + 250000) / 1e6 * 100, places=1)   # newest assistant line wins

    def test_housekeeping_lines_are_not_activity(self):
        s = T.parse_claude(objs('claude/housekeeping-only.jsonl'), 1e10, CFG)
        self.assertEqual(s.state, 'idle')
        self.assertIsNone(s.ctx_pct)

    def test_unanswered_tool_use_becomes_waiting_after_45s(self):
        o = objs('claude/working.jsonl')
        self.assertEqual(T.parse_claude(o, self.now('claude/working.jsonl', 44), CFG).state, 'working')
        self.assertEqual(T.parse_claude(o, self.now('claude/working.jsonl', 46), CFG).state, 'waiting')

    def test_ten_quiet_minutes_is_idle_not_working(self):
        o = objs('claude/working.jsonl')
        self.assertEqual(T.parse_claude(o, self.now('claude/working.jsonl', 601), CFG).state, 'idle')

    def test_no_content_leaves_the_parser(self):
        s = T.parse_claude(objs('claude/working.jsonl'), self.now('claude/working.jsonl', 5), CFG)
        self.assertNotIn('redacted', json.dumps(s.__dict__))

    def test_tool_result_user_line_means_working(self):
        s = T.parse_claude([c_asst(100.0), c_user_tool_result(101.0)], 103.0, CFG)
        self.assertEqual(s.state, 'working')
        self.assertNotIn('redacted', json.dumps(s.__dict__))

    def test_zero_token_assistant_line_does_not_drop_context_to_zero(self):
        s = T.parse_claude([c_asst(100.0, cache_read=400000), c_asst(101.0, 'end_turn', cache_read=0, inp=0)], 102.0, CFG)
        self.assertAlmostEqual(s.ctx_pct, 40.0, places=1)
        self.assertEqual(s.state, 'idle')


class CodexParser(unittest.TestCase):
    NOW = 1791834000 + 100          # just after the fixtures' task_started

    def test_working_ctx_and_weekly_plan(self):
        s = T.parse_codex(objs('codex/working.jsonl'), self.NOW, CFG)
        self.assertAlmostEqual(s.ctx_pct, 60028 / 258400 * 100, places=1)
        self.assertEqual((s.plan_pct, s.plan_label), (40.0, 'wk'))
        self.assertTrue(s.resets_in.endswith('h') and 'd' in s.resets_in)

    def test_task_complete_means_idle(self):
        self.assertEqual(T.parse_codex(objs('codex/done.jsonl'), self.NOW, CFG).state, 'idle')

    def test_started_without_complete_is_working(self):
        s = T.parse_codex(objs('codex/working.jsonl'), T.parse_iso('2026-10-12T19:40:20.000Z'), CFG)
        self.assertEqual(s.state, 'working')

    def test_premium_null_limit_is_ignored_never_zero(self):
        s = T.parse_codex(objs('codex/premium-null.jsonl'), self.NOW, CFG)
        self.assertIsNone(s.plan_pct)
        self.assertAlmostEqual(s.ctx_pct, 23.2, places=1)

    def test_expired_window_is_stale_not_shown(self):
        self.assertIsNone(T.parse_codex(objs('codex/stale-window.jsonl'), self.NOW, CFG).plan_pct)

    def test_quiet_working_session_becomes_waiting(self):
        o = objs('codex/working.jsonl')
        last = T.parse_iso(o[-1]['timestamp'])
        self.assertEqual(T.parse_codex(o, last + 30, CFG).state, 'working')
        self.assertEqual(T.parse_codex(o, last + 60, CFG).state, 'waiting')
        self.assertEqual(T.parse_codex(o, last + 700, CFG).state, 'idle')

    def test_other_limit_id_with_a_real_primary_is_ignored(self):
        s = T.parse_codex([x_evt(100.0, 'task_started'), x_tokens(101.0, limit_id='premium', pct=77.0, resets=10 ** 10)], 102.0, CFG)
        self.assertIsNone(s.plan_pct)
        s = T.parse_codex([x_evt(100.0, 'task_started'), x_tokens(101.0, pct=12.0, resets=10 ** 10)], 102.0, CFG)
        self.assertEqual(s.plan_pct, 12.0)

    def test_turn_aborted_means_idle(self):
        s = T.parse_codex([x_evt(100.0, 'task_started'), x_tokens(101.0), x_evt(102.0, 'turn_aborted')], 103.0, CFG)
        self.assertEqual(s.state, 'idle')


# ====================================================================== the real Tracker on temp files and a fake clock
class TrackerBase(Isolated):
    who = 'claude'

    def setUp(self):
        super().setUp()
        self.root = self.data / 'sessions'
        self.proj = self.root / 'proj'
        self.proj.mkdir(parents=True)
        self.cfg = dict(CFG, claude_dirs=[str(self.root)], codex_dirs=[str(self.root)])
        self.base = 1_800_000_000.0
        self.clock = Clock(self.base)
        self.tr = T.Tracker(self.who, self.cfg, clock=self.clock)

    def write(self, name, lines, mtime=None, mode='w', newline=True):
        p = self.proj / name
        with open(p, mode, encoding='utf-8', newline='') as f:
            for o in lines:
                f.write((o if isinstance(o, str) else json.dumps(o)) + ('\n' if newline else ''))
        m = self.clock.t if mtime is None else mtime
        os.utime(p, (m, m))
        return p

    def poll(self, at=None):
        if at is not None:
            self.clock.t = self.base + at
        return self.tr.poll()


class TrackerTimeRules(TrackerBase):
    def test_unchanged_file_rederives_waiting_and_idle_every_poll(self):
        self.write('s.jsonl', [c_asst(self.base)], mtime=self.base)
        self.assertEqual(self.poll(1).state, 'working')
        self.assertEqual(self.poll(46).state, 'waiting')           # the cached facts are re-judged against the new clock
        s = self.poll(700)
        self.assertEqual((s.state, s.events), ('idle', []))         # a turn that went quiet is not a finish: no victory

    def test_finished_then_done_for_8s_then_idle(self):
        p = self.write('s.jsonl', [c_asst(self.base)], mtime=self.base)
        evs, states = [], {}
        for i in range(1, 21):
            s = self.poll(i)
            evs += s.events
            states[i] = s.state
            with open(p, 'a', encoding='utf-8') as f:              # keeps working: a tool result every second
                f.write(json.dumps(c_user_tool_result(self.base + i)) + '\n')
            os.utime(p, (self.base + i, self.base + i))
        with open(p, 'a', encoding='utf-8') as f:
            f.write(json.dumps(c_asst(self.base + 21, 'end_turn')) + '\n')
        os.utime(p, (self.base + 21, self.base + 21))
        for i in range(21, 35):
            s = self.poll(i)
            evs += s.events
            states[i] = s.state
        self.assertEqual(evs, ['finished'])
        self.assertEqual(states[10], 'working')
        self.assertEqual(states[25], 'done')
        self.assertEqual(states[30], 'idle')

    def test_short_task_does_not_celebrate(self):
        p = self.write('s.jsonl', [c_asst(self.base)], mtime=self.base)
        self.poll(1)
        self.poll(5)
        with open(p, 'a', encoding='utf-8') as f:
            f.write(json.dumps(c_asst(self.base + 6, 'end_turn')) + '\n')
        os.utime(p, (self.base + 6, self.base + 6))
        self.assertEqual(self.poll(7).events, [])

    def test_limit_event_fires_once(self):
        p = self.write('s.jsonl', [c_asst(self.base, 'end_turn', cache_read=500000)], mtime=self.base)
        self.assertEqual(self.poll(1).state, 'idle')
        with open(p, 'a', encoding='utf-8') as f:
            f.write(json.dumps(c_asst(self.base + 2, 'end_turn', cache_read=930000)) + '\n')
        os.utime(p, (self.base + 2, self.base + 2))
        n, states = 0, set()
        for i in range(3, 10):
            s = self.poll(i)
            n += s.events.count('limit')
            states.add(s.state)
        self.assertEqual((n, states), (1, {'limit'}))

    def test_switching_sessions_never_fires_finished(self):
        self.write('a.jsonl', [c_asst(self.base)], mtime=self.base)
        for i in range(1, 30):
            self.poll(i)
        self.write('b.jsonl', [c_asst(self.base + 30, 'end_turn')], mtime=self.base + 30)      # a different, idle session is newest
        evs = []
        for i in range(31, 40):
            evs += self.poll(i).events
        self.assertEqual(evs, [])

    def test_plan_feed_is_read_from_the_isolated_data_dir(self):
        self.write('s.jsonl', [c_asst(self.base, 'end_turn')], mtime=self.base)
        (self.data / 'feeds').mkdir()
        (self.data / 'feeds' / 'claude-plan.json').write_text(json.dumps({'five_hour': 35, 'ts': iso(self.base)}), encoding='utf-8')
        s = self.poll(1)
        self.assertEqual((s.plan_pct, s.plan_label), (35.0, '5h'))
        self.assertIsNone(self.poll(16 * 60).plan_pct)               # older than 15 min: ignored


class CodexTracker(TrackerBase):
    who = 'codex'

    def setUp(self):
        super().setUp()
        self.proj = self.root / '2026' / '10' / '13'
        self.proj.mkdir(parents=True)

    def test_plan_window_expiry_is_rechecked_without_a_file_change(self):
        self.write('rollout-1.jsonl', [x_evt(self.base, 'task_started'), x_tokens(self.base, resets=self.base + 30)], mtime=self.base)
        self.assertEqual(self.poll(5).plan_pct, 40.0)
        self.assertIsNone(self.poll(31).plan_pct)                   # the window reset while the file sat unchanged

    def test_stray_files_in_the_date_tree_do_not_crash(self):
        (self.root / '2025').write_text('x', encoding='utf-8')     # a file named like a year
        (self.root / '2026' / '11').write_text('x', encoding='utf-8')
        (self.root / '2026' / '10' / '14').write_text('x', encoding='utf-8')
        self.write('rollout-1.jsonl', [x_evt(self.base, 'task_started')], mtime=self.base)
        files = list(T.codex_files([self.root]))
        self.assertEqual([os.path.basename(p) for p, _ in files], ['rollout-1.jsonl'])
        self.assertEqual(self.poll(2).state, 'working')

    def test_only_the_newest_days_are_scanned(self):
        for d in ('01', '02', '03', '04'):
            dd = self.root / '2026' / '09' / d
            dd.mkdir(parents=True)
            (dd / f'rollout-{d}.jsonl').write_text('{}\n', encoding='utf-8')
        names = sorted(os.path.basename(p) for p, _ in T.codex_files([self.root], days=3))
        self.assertEqual(names, ['rollout-03.jsonl', 'rollout-04.jsonl'])   # 2026/10/13 is the newest day folder (empty)

    def test_missing_root_yields_nothing(self):
        self.assertEqual(list(T.codex_files([self.root / 'nope'])), [])


class TrackerReading(TrackerBase):
    def test_only_appended_bytes_are_read(self):
        filler = [{'type': 'queue-operation', 'pad': 'x' * 500} for _ in range(300)]
        p = self.write('s.jsonl', filler + [c_asst(self.base)], mtime=self.base)
        self.poll(1)
        first = self.tr.bytes_read
        self.assertGreater(first, 100000)
        line = json.dumps(c_asst(self.base + 2, 'end_turn')) + '\n'
        with open(p, 'a', encoding='utf-8', newline='') as f:
            f.write(line)
        os.utime(p, (self.base + 2, self.base + 2))
        self.assertEqual(self.poll(3).state, 'idle')
        self.assertEqual(self.tr.bytes_read - first, len(line.encode()))
        self.poll(4)
        self.assertEqual(self.tr.bytes_read - first, len(line.encode()))     # unchanged file: nothing read

    def test_a_newest_line_bigger_than_256kb_is_still_understood(self):
        big = c_asst(self.base, 'tool_use')
        big['message']['content'] = [{'type': 'text', 'text': 'z' * 400000}]
        self.write('s.jsonl', [c_asst(self.base - 5, 'end_turn'), big], mtime=self.base)
        s = self.poll(2)
        self.assertEqual(s.state, 'working')                        # not a false idle / done from an empty tail
        self.assertAlmostEqual(s.ctx_pct, 50.0, places=1)

    def test_a_half_written_last_line_is_completed_later(self):
        p = self.write('s.jsonl', [c_asst(self.base, 'end_turn')], mtime=self.base)
        line = json.dumps(c_asst(self.base + 1, 'tool_use', cache_read=600000))
        with open(p, 'a', encoding='utf-8', newline='') as f:
            f.write(line[:40])
        os.utime(p, (self.base + 1, self.base + 1))
        s = self.poll(2)
        self.assertEqual(s.state, 'idle')
        with open(p, 'a', encoding='utf-8', newline='') as f:
            f.write(line[40:] + '\n')
        os.utime(p, (self.base + 3, self.base + 3))
        s = self.poll(4)
        self.assertEqual(s.state, 'working')
        self.assertAlmostEqual(s.ctx_pct, 60.0, places=1)

    def test_truncated_file_is_reparsed(self):
        p = self.write('s.jsonl', [c_asst(self.base, 'end_turn')] * 50, mtime=self.base)
        self.poll(1)
        self.write('s.jsonl', [c_asst(self.base + 2)], mtime=self.base + 2)
        self.assertEqual(self.poll(3).state, 'working')

    def test_vanished_file_does_not_crash(self):
        p = self.write('s.jsonl', [c_asst(self.base)], mtime=self.base)
        self.tr._newest(self.base)                                  # discovered ...
        p.unlink()                                                  # ... then deleted before it is read
        self.assertEqual(self.tr.poll(self.base + 1).state, 'sleeping')

    def test_parsed_state_is_kept_for_the_current_path_only(self):
        self.write('a.jsonl', [c_asst(self.base)], mtime=self.base)
        self.poll(1)
        self.write('b.jsonl', [c_asst(self.base + 2)], mtime=self.base + 2)
        self.poll(32)                                               # the next full scan finds it
        self.assertTrue(self.tr._file['path'].endswith('b.jsonl'))

    def test_mutating_a_returned_snapshot_does_not_poison_the_next_poll(self):
        self.write('live.jsonl', [c_asst(self.base - 2)], mtime=self.base - 2)
        first = self.poll(0)
        first.state = 'done'
        self.assertEqual(self.poll(1).state, 'working')


class TrackerDiscovery(TrackerBase):
    def test_a_fresh_file_that_appears_between_scans_is_found_within_seconds(self):
        self.write('old.jsonl', [c_asst(self.base - 7200)], mtime=self.base - 7200)
        self.assertEqual(self.poll(0).state, 'sleeping')            # only a 2-hour-old session exists
        self.write('new.jsonl', [c_asst(self.base + 4)], mtime=self.base + 4)
        s = self.poll(6)                                            # no 30 s wait: stale best -> quick rescan
        self.assertEqual(s.state, 'working')
        self.assertAlmostEqual(s.ctx_pct, 50.0, places=1)

    def test_quick_rescans_back_off_overnight(self):
        self.write('old.jsonl', [c_asst(self.base - 7200)], mtime=self.base - 7200)
        for i in range(0, 600):                                     # ten quiet minutes, polled every second
            self.poll(i)
        self.assertLessEqual(self.tr.scans, 600 // 30 + 6)          # ~ one full scan per 30 s, not one every 5 s

    def test_no_files_at_all_is_not_a_scan_every_poll(self):
        for i in range(0, 120):
            self.assertEqual(self.poll(i).state, 'sleeping')
        self.assertLessEqual(self.tr.scans, 120 // 30 + 6)

    def test_one_unreadable_entry_does_not_hide_the_rest(self):
        self.write('a.jsonl', [c_asst(self.base - 5)], mtime=self.base - 5)
        (self.proj / 'b.jsonl').mkdir()                             # a directory named like a transcript
        (self.root / 'stray.txt').write_text('x', encoding='utf-8')   # a file where project folders live
        files = list(T.claude_files([self.root]))
        self.assertEqual([os.path.basename(p) for p, _ in files], ['a.jsonl'])


class UiScale(unittest.TestCase):
    def test_integer_scale_only(self):
        self.assertEqual([cfgmod.ui_scale(b) for b in (48, 72, 88, 96, 120)], [1, 1, 2, 2, 2])


if __name__ == '__main__':
    unittest.main()
