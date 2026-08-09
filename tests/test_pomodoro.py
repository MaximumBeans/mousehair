"""Tests for the Mousehair Pomodoro complication."""

import unittest

from mousehair_app.complications import (
    PHASE_FOCUS,
    PHASE_LONG_BREAK,
    PHASE_SHORT_BREAK,
    STATE_IDLE,
    STATE_PAUSED,
    STATE_RUNNING,
    PomodoroComplication,
)


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += float(seconds)


class PomodoroHost:
    pomodoro_focus_minutes = 25
    pomodoro_short_break_minutes = 5
    pomodoro_long_break_minutes = 15
    pomodoro_focuses_before_long_break = 4

    pomodoro_auto_start_break = False
    pomodoro_auto_start_focus = False


class ShortPomodoroHost(PomodoroHost):
    pomodoro_focus_minutes = 1
    pomodoro_short_break_minutes = 1
    pomodoro_long_break_minutes = 2


class AutoStartBreakHost(ShortPomodoroHost):
    pomodoro_auto_start_break = True


class AutoStartFocusHost(ShortPomodoroHost):
    pomodoro_auto_start_focus = True


class ThreeFocusCycleHost(ShortPomodoroHost):
    pomodoro_focuses_before_long_break = 3


class PomodoroTests(unittest.TestCase):

    def make_timer(self, host=None):
        clock = FakeClock()

        timer = PomodoroComplication(
            host or PomodoroHost(),
            clock=clock,
        )

        return timer, clock

    def finish_phase(
        self,
        timer,
        clock,
    ):
        timer.start()

        clock.advance(
            timer.phase_duration_seconds()
        )

        self.assertTrue(
            timer.update()
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

    def test_pause_and_resume_preserve_progress(self):
        timer, clock = self.make_timer()

        timer.start()
        clock.advance(30)
        timer.pause()

        paused = timer.remaining_seconds()

        clock.advance(500)

        self.assertEqual(
            timer.state,
            STATE_PAUSED,
        )

        self.assertEqual(
            timer.remaining_seconds(),
            paused,
        )

        timer.start()
        clock.advance(20)

        self.assertEqual(
            timer.remaining_seconds(),
            25 * 60 - 50,
        )

    def test_first_focus_leads_to_short_break(self):
        timer, clock = self.make_timer(
            ShortPomodoroHost()
        )

        self.finish_phase(
            timer,
            clock,
        )

        self.assertEqual(
            timer.phase,
            PHASE_SHORT_BREAK,
        )

        self.assertEqual(
            timer.completed_focus_sessions,
            1,
        )

    def test_fourth_focus_leads_to_long_break(self):
        timer, clock = self.make_timer(
            ShortPomodoroHost()
        )

        for _index in range(3):
            self.finish_phase(
                timer,
                clock,
            )

            self.finish_phase(
                timer,
                clock,
            )

        self.finish_phase(
            timer,
            clock,
        )

        self.assertEqual(
            timer.completed_focus_sessions,
            4,
        )

        self.assertEqual(
            timer.phase,
            PHASE_LONG_BREAK,
        )

    def test_configurable_three_focus_cycle(self):
        timer, clock = self.make_timer(
            ThreeFocusCycleHost()
        )

        for _index in range(2):
            self.finish_phase(
                timer,
                clock,
            )

            self.finish_phase(
                timer,
                clock,
            )

        self.finish_phase(
            timer,
            clock,
        )

        self.assertEqual(
            timer.completed_focus_sessions,
            3,
        )

        self.assertEqual(
            timer.phase,
            PHASE_LONG_BREAK,
        )

    def test_short_break_returns_to_focus(self):
        timer, clock = self.make_timer(
            ShortPomodoroHost()
        )

        timer.skip()

        self.assertEqual(
            timer.phase,
            PHASE_SHORT_BREAK,
        )

        self.finish_phase(
            timer,
            clock,
        )

        self.assertEqual(
            timer.phase,
            PHASE_FOCUS,
        )

    def test_auto_start_break_is_independent(self):
        timer, clock = self.make_timer(
            AutoStartBreakHost()
        )

        self.finish_phase(
            timer,
            clock,
        )

        self.assertEqual(
            timer.phase,
            PHASE_SHORT_BREAK,
        )

        self.assertEqual(
            timer.state,
            STATE_RUNNING,
        )

    def test_auto_start_focus_is_independent(self):
        timer, clock = self.make_timer(
            AutoStartFocusHost()
        )

        timer.skip()

        self.assertEqual(
            timer.phase,
            PHASE_SHORT_BREAK,
        )

        self.finish_phase(
            timer,
            clock,
        )

        self.assertEqual(
            timer.phase,
            PHASE_FOCUS,
        )

        self.assertEqual(
            timer.state,
            STATE_RUNNING,
        )

    def test_pause_after_full_cycle_overrides_focus_auto_start(self):
        class Host(AutoStartFocusHost):
            pomodoro_pause_after_cycle = True

        timer, clock = self.make_timer(
            Host()
        )

        timer.completed_focus_sessions = (
            timer.focuses_before_long_break()
        )

        timer._enter_phase(
            PHASE_LONG_BREAK
        )

        self.finish_phase(
            timer,
            clock,
        )

        self.assertEqual(
            timer.phase,
            PHASE_FOCUS,
        )

        self.assertEqual(
            timer.state,
            STATE_IDLE,
        )

    def test_cycle_can_continue_when_pause_after_cycle_disabled(self):
        class Host(AutoStartFocusHost):
            pomodoro_pause_after_cycle = False

        timer, clock = self.make_timer(
            Host()
        )

        timer.completed_focus_sessions = (
            timer.focuses_before_long_break()
        )

        timer._enter_phase(
            PHASE_LONG_BREAK
        )

        self.finish_phase(
            timer,
            clock,
        )

        self.assertEqual(
            timer.phase,
            PHASE_FOCUS,
        )

        self.assertEqual(
            timer.state,
            STATE_RUNNING,
        )

    def test_long_break_uses_long_duration(self):
        timer, _clock = self.make_timer(
            ShortPomodoroHost()
        )

        timer.completed_focus_sessions = 4
        timer._enter_phase(
            PHASE_LONG_BREAK
        )

        self.assertEqual(
            timer.remaining_seconds(),
            120.0,
        )

    def test_focuses_until_long_break(self):
        timer, _clock = self.make_timer()

        self.assertEqual(
            timer.focuses_until_long_break(),
            4,
        )

        timer.completed_focus_sessions = 1

        self.assertEqual(
            timer.focuses_until_long_break(),
            3,
        )

        timer.completed_focus_sessions = 3

        self.assertEqual(
            timer.focuses_until_long_break(),
            1,
        )

    def test_reset_resets_cycle(self):
        timer, _clock = self.make_timer()

        timer.completed_focus_sessions = 3

        timer.reset()

        self.assertEqual(
            timer.phase,
            PHASE_FOCUS,
        )

        self.assertEqual(
            timer.completed_focus_sessions,
            0,
        )

        self.assertEqual(
            timer.focuses_until_long_break(),
            4,
        )

    def test_snapshot_contains_cycle_state(self):
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

        self.assertAlmostEqual(
            snapshot.remaining_seconds,
            45.0,
        )

        self.assertAlmostEqual(
            snapshot.progress,
            0.25,
        )

        self.assertEqual(
            snapshot.focuses_until_long_break,
            4,
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
