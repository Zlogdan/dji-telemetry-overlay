# -*- coding: utf-8 -*-
"""Тесты для модуля core/interpolator.py."""

import math
import pytest
from core.parser import TelemetryPoint
from core.interpolator import (
    lerp,
    lerp_angle,
    interpolate_point,
    interpolate_to_fps,
    smooth_points,
)


class TestLerp:
    def test_t_zero_returns_a(self):
        assert lerp(0.0, 10.0, 0.0) == 0.0

    def test_t_one_returns_b(self):
        assert lerp(0.0, 10.0, 1.0) == 10.0

    def test_midpoint(self):
        assert lerp(0.0, 10.0, 0.5) == 5.0

    def test_negative_values(self):
        assert lerp(-10.0, 10.0, 0.5) == 0.0

    def test_same_values(self):
        assert lerp(5.0, 5.0, 0.7) == 5.0


class TestLerpAngle:
    def test_simple_interpolation(self):
        result = lerp_angle(0.0, 90.0, 0.5)
        assert abs(result - 45.0) < 1e-6

    def test_wraparound_359_to_1(self):
        # Кратчайший путь: 359 → 1 (через 0, diff=2)
        result = lerp_angle(359.0, 1.0, 0.5)
        assert abs(result - 0.0) < 1e-6

    def test_wraparound_270_to_90(self):
        # Кратчайший путь: 270 → 90 (через 360/0, diff=-180 → в одну сторону)
        result = lerp_angle(270.0, 90.0, 0.5)
        # Разница: 90-270 = -180 → нормализуется до -180, result=270+(-180*0.5)=180
        assert abs(result - 180.0) < 1e-6

    def test_full_circle_same_start_end(self):
        result = lerp_angle(45.0, 45.0, 0.5)
        assert abs(result - 45.0) < 1e-6

    def test_result_in_0_360(self):
        for a in range(0, 360, 30):
            for b in range(0, 360, 30):
                result = lerp_angle(float(a), float(b), 0.5)
                assert 0.0 <= result < 360.0


class TestInterpolatePoint:
    def _make_point(self, t, lat, lon, speed, alt, heading):
        return TelemetryPoint(t=t, lat=lat, lon=lon, speed=speed, alt=alt, heading=heading)

    def test_midpoint_interpolation(self):
        p1 = self._make_point(0.0, 55.0, 37.0, 10.0, 100.0, 0.0)
        p2 = self._make_point(2.0, 56.0, 38.0, 20.0, 200.0, 90.0)
        result = interpolate_point(p1, p2, 0.5)
        assert abs(result.t - 1.0) < 1e-9
        assert abs(result.lat - 55.5) < 1e-9
        assert abs(result.lon - 37.5) < 1e-9
        assert abs(result.speed - 15.0) < 1e-9
        assert abs(result.alt - 150.0) < 1e-9
        assert abs(result.heading - 45.0) < 1e-6

    def test_t_zero_returns_p1(self):
        p1 = self._make_point(0.0, 55.0, 37.0, 10.0, 100.0, 0.0)
        p2 = self._make_point(1.0, 56.0, 38.0, 20.0, 200.0, 90.0)
        result = interpolate_point(p1, p2, 0.0)
        assert result.lat == p1.lat
        assert result.lon == p1.lon

    def test_t_one_returns_p2(self):
        p1 = self._make_point(0.0, 55.0, 37.0, 10.0, 100.0, 0.0)
        p2 = self._make_point(1.0, 56.0, 38.0, 20.0, 200.0, 90.0)
        result = interpolate_point(p1, p2, 1.0)
        assert result.lat == p2.lat
        assert result.lon == p2.lon


class TestInterpolateToFps:
    def _make_point(self, t, lat=55.0, lon=37.0):
        return TelemetryPoint(t=t, lat=lat, lon=lon)

    def test_empty_points_returns_empty_frames(self):
        result = interpolate_to_fps([], fps=10.0, duration=1.0)
        assert len(result) == 10
        for p in result:
            assert p.lat == 0.0

    def test_single_point_duplicated(self):
        pts = [self._make_point(0.0, lat=55.5)]
        result = interpolate_to_fps(pts, fps=5.0, duration=1.0)
        assert len(result) == 5
        for p in result:
            assert p.lat == 55.5

    def test_correct_frame_count(self):
        pts = [self._make_point(0.0), self._make_point(1.0)]
        result = interpolate_to_fps(pts, fps=30.0, duration=1.0)
        assert len(result) == 30

    def test_interpolated_values_between_points(self):
        pts = [
            self._make_point(0.0, lat=55.0),
            self._make_point(1.0, lat=56.0),
        ]
        result = interpolate_to_fps(pts, fps=2.0, duration=1.0)
        # frame 0 at t=0.0 → lat=55.0, frame 1 at t=0.5 → lat~55.5
        assert len(result) == 2
        assert abs(result[0].lat - 55.0) < 1e-6
        assert abs(result[1].lat - 55.5) < 1e-6

    def test_frames_before_first_point_use_first_point(self):
        pts = [self._make_point(0.5, lat=55.5), self._make_point(1.0, lat=56.0)]
        result = interpolate_to_fps(pts, fps=4.0, duration=1.0)
        # frame 0 at t=0.0 is before first point (t=0.5)
        assert result[0].lat == 55.5

    def test_frames_after_last_point_use_last_point(self):
        pts = [self._make_point(0.0, lat=55.0), self._make_point(0.5, lat=55.5)]
        result = interpolate_to_fps(pts, fps=4.0, duration=1.0)
        # Last frame (t=0.75) is after last point (t=0.5)
        assert result[-1].lat == 55.5


class TestSmoothPoints:
    def _make_pts(self, values):
        return [TelemetryPoint(t=float(i), lat=v, lon=v, speed=v, alt=v) for i, v in enumerate(values)]

    def test_empty_or_single_unchanged(self):
        assert smooth_points([]) == []
        single = [TelemetryPoint(t=0.0, lat=55.0)]
        assert smooth_points(single) == single

    def test_constant_values_unchanged(self):
        pts = self._make_pts([5.0, 5.0, 5.0, 5.0, 5.0])
        result = smooth_points(pts, window=3)
        for p in result:
            assert abs(p.lat - 5.0) < 1e-9

    def test_smoothing_reduces_spike(self):
        # Middle value is a spike
        pts = self._make_pts([1.0, 1.0, 100.0, 1.0, 1.0])
        result = smooth_points(pts, window=5)
        # Smoothed middle should be much less than 100
        assert result[2].lat < 100.0
        assert result[2].lat > 1.0

    def test_preserves_timestamps(self):
        pts = self._make_pts([1.0, 2.0, 3.0])
        result = smooth_points(pts, window=3)
        for orig, sm in zip(pts, result):
            assert orig.t == sm.t

    def test_heading_smoothing_wraparound(self):
        # Headings around 0/360 boundary
        pts = [
            TelemetryPoint(t=0.0, lat=55.0, lon=37.0, heading=350.0),
            TelemetryPoint(t=1.0, lat=55.0, lon=37.0, heading=5.0),
            TelemetryPoint(t=2.0, lat=55.0, lon=37.0, heading=10.0),
        ]
        result = smooth_points(pts, window=3)
        # Result should not be around 180° (wrong wraparound)
        for p in result:
            assert not (80.0 < p.heading < 280.0), (
                f"Heading {p.heading} looks like a wrong wraparound average"
            )
