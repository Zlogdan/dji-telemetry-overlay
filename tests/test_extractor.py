# -*- coding: utf-8 -*-
"""Тесты для модуля core/extractor.py."""

import pytest
from core.extractor import _get_video_info, _run_ffprobe, extract_telemetry
from core.parser import TelemetryPoint


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


class TestRunFfprobe:
    class _FakeCompletedProcess:
        def __init__(self, returncode=0, stdout="", stderr=""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def test_returns_none_when_stdout_is_none(self, monkeypatch):
        def fake_run(*args, **kwargs):
            return self._FakeCompletedProcess(returncode=0, stdout=None, stderr="")

        monkeypatch.setattr("core.extractor.subprocess.run", fake_run)

        result = _run_ffprobe("dummy.mp4")
        assert result is None

    def test_returns_none_when_stdout_is_empty(self, monkeypatch):
        def fake_run(*args, **kwargs):
            return self._FakeCompletedProcess(returncode=0, stdout="", stderr="")

        monkeypatch.setattr("core.extractor.subprocess.run", fake_run)

        result = _run_ffprobe("dummy.mp4")
        assert result is None


class TestExtractTelemetry:
    def test_returns_empty_when_file_missing(self, monkeypatch):
        monkeypatch.setattr("core.extractor.os.path.exists", lambda _p: False)

        result = extract_telemetry("missing.mp4")

        assert result["points"] == []
        assert result["source"] == "missing"

    def test_returns_empty_when_probe_unavailable(self, monkeypatch):
        monkeypatch.setattr("core.extractor.os.path.exists", lambda _p: True)
        monkeypatch.setattr("core.extractor._run_ffprobe", lambda *_a, **_k: None)

        result = extract_telemetry("video.mp4")

        assert result["points"] == []
        assert result["source"] == "unavailable"

    def test_prefers_pyosmogps_points(self, monkeypatch):
        monkeypatch.setattr("core.extractor.os.path.exists", lambda _p: True)
        monkeypatch.setattr(
            "core.extractor._run_ffprobe",
            lambda *_a, **_k: {
                "format": {"duration": "2.0"},
                "streams": [{"codec_type": "video", "r_frame_rate": "30/1"}],
            },
        )

        pyosmo_points = [
            TelemetryPoint(t=0.0, lat=55.0, lon=37.0, speed=10.0, alt=100.0, heading=90.0),
            TelemetryPoint(t=1.0, lat=55.1, lon=37.1, speed=11.0, alt=101.0, heading=91.0),
        ]

        monkeypatch.setattr("core.extractor._try_extract_with_pyosmogps", lambda *_a, **_k: pyosmo_points)

        # ffmpeg путь не должен быть вызван, если pyosmogps уже дал точки
        def _fail_if_called(*_a, **_k):
            raise AssertionError("ffmpeg fallback should not run when pyosmogps succeeds")

        monkeypatch.setattr("core.extractor._extract_data_stream", _fail_if_called)

        result = extract_telemetry("video.mp4")
        assert result["source"] == "video"
        assert len(result["points"]) == 2
        assert result["points"][0]["lat"] == pytest.approx(55.0)

    def test_fallbacks_to_ffmpeg_when_pyosmogps_empty(self, monkeypatch):
        monkeypatch.setattr("core.extractor.os.path.exists", lambda _p: True)
        monkeypatch.setattr(
            "core.extractor._run_ffprobe",
            lambda *_a, **_k: {
                "format": {"duration": "1.0"},
                "streams": [{"codec_type": "video", "r_frame_rate": "25/1"}],
            },
        )
        monkeypatch.setattr("core.extractor._try_extract_with_pyosmogps", lambda *_a, **_k: [])
        monkeypatch.setattr("core.extractor._extract_data_stream", lambda *_a, **_k: b"raw")

        nmea_points = [TelemetryPoint(t=0.0, lat=50.0, lon=30.0)]
        monkeypatch.setattr("core.extractor._parse_nmea_from_bytes", lambda *_a, **_k: nmea_points)

        result = extract_telemetry("video.mp4")
        assert result["source"] == "video"
        assert len(result["points"]) == 1
        assert result["points"][0]["lat"] == pytest.approx(50.0)
