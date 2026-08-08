"""Tests for the Mousehair Pomodoro complication."""

import unittest

from mousehair_app.complications import (
    PHASE_BREAK,
    PHASE_FOCUS,
    STATE_IDLE,
    STATE_PAUSED,
    STATE_RUNNING,
    PomodoroComplication,
)


class FakeClock:
    """Controllable monotonic clock for timer tests."""

    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += float(seconds)


class PomodoroHost:
    """Minimal host supplying Pomodoro settings."""

    pomodoro_focus_minutes = 25
    pomodoro_break_minutes = 5
    pomodoro_auto_start = False


class ShortPomodoroHost:
    """Tiny durations keep transition tests readable."""

    pomodoro_focus_minutes = 1
    pomodoro_break_minutes = 1
    pomodoro_auto_start = False


class AutoStartHost(ShortPomodoroHost):
    pomodoro_auto_start = True


class PomodoroTests(unittest.TestCase):

    def make_timer(
        self,
        host=None,
    ):
        clock = FakeClock()

        timer = PomodoroComplication(
            host or PomodoroHost(),
            clock=clock,
        )

        return (
            timer,
            clock,
        )

    def test_defaults_to_idle_focus(self):
        timer, _clock = self.make_timer()

        self.assertEqual(
            timer.phase,
            PHASE_FOCUS,
        )

        self.assertEqual(
            timer.state,
            STATE_IDLE,
        )

        self.assertEqual(
            timer.remaining_seconds(),
            25 * 60,
        )

    def test_start_begins_countdown(self):
        timer, clock = self.make_timer()

        timer.start()

        self.assertEqual(
            timer.state,
            STATE_RUNNING,
        )

        clock.advance(30)

        self.assertEqual(
            timer.remaining_seconds(),
            25 * 60 - 30,
        )

    def test_pause_freezes_remaining_time(self):
        timer, clock = self.make_timer()

        timer.start()
        clock.advance(30)

        timer.pause()

        paused_remaining = (
            timer.remaining_seconds()
        )

        clock.advance(120)

        self.assertEqual(
            timer.state,
            STATE_PAUSED,
        )

        self.assertEqual(
            timer.remaining_seconds(),
            paused_remaining,
        )

    def test_resume_continues_from_pause(self):
        timer, clock = self.make_timer()

        timer.start()
        clock.advance(30)

        timer.pause()
        clock.advance(500)

        timer.start()
        clock.advance(20)

        self.assertEqual(
            timer.remaining_seconds(),
            25 * 60 - 50,
        )

    def test_progress_increases(self):
        timer, clock = self.make_timer(
            ShortPomodoroHost()
        )

        timer.start()

        self.assertEqual(
            timer.progress(),
            0.0,
        )

        clock.advance(30)

        self.assertAlmostEqual(
            timer.progress(),
            0.5,
        )

    def test_focus_completion_switches_to_break(self):
        timer, clock = self.make_timer(
            ShortPomodoroHost()
        )

        timer.start()
        clock.advance(60)

        changed = timer.update()

        self.assertTrue(changed)

        self.assertEqual(
            timer.phase,
            PHASE_BREAK,
        )

        self.assertEqual(
            timer.state,
            STATE_IDLE,
        )

        self.assertEqual(
            timer.completed_focus_sessions,
            1,
        )

    def test_break_completion_returns_to_focus(self):
        timer, clock = self.make_timer(
            ShortPomodoroHost()
        )

        timer.skip()

        self.assertEqual(
            timer.phase,
            PHASE_BREAK,
        )

        timer.start()
        clock.advance(60)
        timer.update()

        self.assertEqual(
            timer.phase,
            PHASE_FOCUS,
        )

    def test_auto_start_starts_next_phase(self):
        timer, clock = self.make_timer(
            AutoStartHost()
        )

        timer.start()
        clock.advance(60)

        timer.update()

        self.assertEqual(
            timer.phase,
            PHASE_BREAK,
        )

        self.assertEqual(
            timer.state,
            STATE_RUNNING,
        )

    def test_reset_returns_to_fresh_focus(self):
        timer, clock = self.make_timer()

        timer.start()
        clock.advance(100)

        timer.reset()

        self.assertEqual(
            timer.phase,
            PHASE_FOCUS,
        )

        self.assertEqual(
            timer.state,
            STATE_IDLE,
        )

        self.assertEqual(
            timer.remaining_seconds(),
            25 * 60,
        )

    def test_snapshot_contains_render_state(self):
        timer, clock = self.make_timer(
            ShortPomodoroHost()
        )

        timer.start()
        clock.advance(15)

        snapshot = timer.snapshot()

        self.assertEqual(
            snapshot.phase,
            PHASE_FOCUS,
        )

        self.assertEqual(
            snapshot.state,
            STATE_RUNNING,
        )

        self.assertAlmostEqual(
            snapshot.remaining_seconds,
            45.0,
        )

        self.assertAlmostEqual(
            snapshot.progress,
            0.25,
        )

    def test_default_placement_is_full_inner_ring(self):
        timer, _clock = self.make_timer()

        self.assertEqual(
            timer.placement.radial_zone,
            "inside",
        )

        self.assertTrue(
            timer.placement.is_full_ring
        )


if __name__ == "__main__":
    unittest.main()
