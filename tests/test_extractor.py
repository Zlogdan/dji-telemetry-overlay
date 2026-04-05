# -*- coding: utf-8 -*-
"""Тесты для модуля core/extractor.py."""

import pytest
from core.extractor import generate_demo_telemetry, _get_video_info


class TestGenerateDemoTelemetry:
    def test_returns_dict_with_required_keys(self):
        result = generate_demo_telemetry()
        assert "fps" in result
        assert "duration" in result
        assert "points" in result
        assert "source" in result

    def test_source_is_demo(self):
        result = generate_demo_telemetry()
        assert result["source"] == "demo"

    def test_fps_preserved(self):
        result = generate_demo_telemetry(duration=10.0, fps=25.0)
        assert result["fps"] == 25.0

    def test_duration_preserved(self):
        result = generate_demo_telemetry(duration=30.0)
        assert result["duration"] == 30.0

    def test_points_count_matches_duration(self):
        result = generate_demo_telemetry(duration=60.0)
        # One point per second
        assert len(result["points"]) == 60

    def test_points_have_required_fields(self):
        result = generate_demo_telemetry(duration=5.0)
        for p in result["points"]:
            assert "t" in p
            assert "lat" in p
            assert "lon" in p
            assert "speed" in p
            assert "alt" in p
            assert "heading" in p

    def test_speed_is_positive(self):
        result = generate_demo_telemetry(duration=10.0)
        for p in result["points"]:
            assert p["speed"] >= 0.0

    def test_heading_in_range(self):
        result = generate_demo_telemetry(duration=10.0)
        for p in result["points"]:
            assert 0.0 <= p["heading"] < 360.0

    def test_lat_lon_near_moscow(self):
        result = generate_demo_telemetry(duration=10.0)
        for p in result["points"]:
            # Demo route is centered around Moscow
            assert 55.0 < p["lat"] < 56.5
            assert 36.5 < p["lon"] < 38.5


class TestGetVideoInfo:
    def test_defaults_when_no_streams(self):
        probe_data = {"format": {}, "streams": []}
        fps, duration = _get_video_info(probe_data)
        assert fps == 30.0
        assert duration == 0.0

    def test_duration_from_format(self):
        probe_data = {"format": {"duration": "120.5"}, "streams": []}
        fps, duration = _get_video_info(probe_data)
        assert duration == pytest.approx(120.5)

    def test_fps_from_video_stream(self):
        probe_data = {
            "format": {"duration": "10.0"},
            "streams": [
                {"codec_type": "video", "r_frame_rate": "60/1"}
            ]
        }
        fps, duration = _get_video_info(probe_data)
        assert fps == pytest.approx(60.0)

    def test_fps_fractional(self):
        probe_data = {
            "format": {"duration": "10.0"},
            "streams": [
                {"codec_type": "video", "r_frame_rate": "30000/1001"}
            ]
        }
        fps, duration = _get_video_info(probe_data)
        assert abs(fps - 29.97) < 0.01

    def test_fps_bad_value_keeps_default(self):
        probe_data = {
            "format": {},
            "streams": [
                {"codec_type": "video", "r_frame_rate": "bad/value"}
            ]
        }
        fps, _ = _get_video_info(probe_data)
        assert fps == 30.0

    def test_duration_from_stream_when_format_missing(self):
        probe_data = {
            "format": {},
            "streams": [
                {"codec_type": "video", "r_frame_rate": "30/1", "duration": "45.0"}
            ]
        }
        fps, duration = _get_video_info(probe_data)
        assert duration == pytest.approx(45.0)

    def test_skips_non_video_streams(self):
        probe_data = {
            "format": {"duration": "10.0"},
            "streams": [
                {"codec_type": "audio", "r_frame_rate": "0/0"},
                {"codec_type": "video", "r_frame_rate": "24/1"},
            ]
        }
        fps, _ = _get_video_info(probe_data)
        assert fps == pytest.approx(24.0)

    def test_invalid_duration_in_format_defaults_zero(self):
        probe_data = {"format": {"duration": "not_a_number"}, "streams": []}
        fps, duration = _get_video_info(probe_data)
        assert duration == 0.0
