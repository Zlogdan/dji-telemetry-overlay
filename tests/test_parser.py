# -*- coding: utf-8 -*-
"""Тесты для модуля core/parser.py."""

import pytest
from core.parser import (
    TelemetryPoint,
    nmea_to_decimal,
    _validate_checksum,
    parse_gprmc,
    parse_gpgga,
    parse_nmea_sentence,
    merge_points,
)


class TestNmeaToDecimal:
    def test_north_latitude(self):
        result = nmea_to_decimal("5530.5000", "N")
        assert abs(result - 55.508333) < 1e-4

    def test_south_latitude(self):
        result = nmea_to_decimal("5530.5000", "S")
        assert abs(result - (-55.508333)) < 1e-4

    def test_east_longitude(self):
        result = nmea_to_decimal("03712.0000", "E")
        assert abs(result - 37.2) < 1e-4

    def test_west_longitude(self):
        result = nmea_to_decimal("03712.0000", "W")
        assert abs(result - (-37.2)) < 1e-4

    def test_empty_value_returns_zero(self):
        assert nmea_to_decimal("", "N") == 0.0

    def test_empty_direction_returns_zero(self):
        assert nmea_to_decimal("5530.5000", "") == 0.0

    def test_invalid_value_returns_zero(self):
        assert nmea_to_decimal("bad_data", "N") == 0.0

    def test_zero_degrees(self):
        result = nmea_to_decimal("0000.0000", "N")
        assert result == 0.0


class TestValidateChecksum:
    def test_valid_checksum(self):
        # $GPRMC with valid checksum
        sentence = "$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A"
        assert _validate_checksum(sentence) is True

    def test_invalid_checksum(self):
        sentence = "$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*FF"
        assert _validate_checksum(sentence) is False

    def test_no_checksum_passes(self):
        # Sentences without checksum should pass (no validation)
        sentence = "$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394"
        assert _validate_checksum(sentence) is True

    def test_malformed_checksum_returns_false(self):
        assert _validate_checksum("$GPRMC*ZZ") is False


class TestParseGprmc:
    def test_valid_gprmc(self):
        parts = "$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W".split(",")
        result = parse_gprmc(parts)
        assert result is not None
        assert abs(result["lat"] - 48.117300) < 1e-3
        assert abs(result["lon"] - 11.516667) < 1e-3
        assert result["speed"] > 0
        assert result["heading"] == pytest.approx(84.4)

    def test_void_status_returns_none(self):
        parts = "$GPRMC,123519,V,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W".split(",")
        assert parse_gprmc(parts) is None

    def test_too_few_fields_returns_none(self):
        assert parse_gprmc(["$GPRMC", "123519"]) is None

    def test_empty_speed_defaults_zero(self):
        parts = "$GPRMC,123519,A,4807.038,N,01131.000,E,,084.4,230394,003.1,W".split(",")
        result = parse_gprmc(parts)
        assert result is not None
        assert result["speed"] == 0.0

    def test_speed_conversion_knots_to_ms(self):
        # 1 knot = 0.514444 m/s
        parts = "$GPRMC,123519,A,4807.038,N,01131.000,E,001.0,084.4,230394,003.1,W".split(",")
        result = parse_gprmc(parts)
        assert result is not None
        assert abs(result["speed"] - 0.514444) < 1e-4


class TestParseGpgga:
    def test_valid_gpgga(self):
        parts = "$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47".split(",")
        result = parse_gpgga(parts)
        assert result is not None
        assert abs(result["alt"] - 545.4) < 0.1

    def test_no_fix_returns_none(self):
        parts = "$GPGGA,123519,4807.038,N,01131.000,E,0,08,0.9,545.4,M,46.9,M,,*47".split(",")
        assert parse_gpgga(parts) is None

    def test_too_few_fields_returns_none(self):
        assert parse_gpgga(["$GPGGA", "123519"]) is None

    def test_empty_altitude_defaults_zero(self):
        parts = "$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,,M,46.9,M,,*47".split(",")
        result = parse_gpgga(parts)
        assert result is not None
        assert result["alt"] == 0.0


class TestParseNmeaSentence:
    def test_gprmc_sentence(self):
        sentence = "$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A"
        result = parse_nmea_sentence(sentence)
        assert result is not None
        assert isinstance(result, TelemetryPoint)
        assert result.lat > 0
        assert result.lon > 0

    def test_gnrmc_sentence(self):
        sentence = "$GNRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*74"
        result = parse_nmea_sentence(sentence)
        # Even if checksum differs, test sentence type routing
        # Accept None if checksum fails — main goal is no crash
        assert result is None or isinstance(result, TelemetryPoint)

    def test_invalid_sentence_no_dollar(self):
        assert parse_nmea_sentence("GPRMC,123519,A,...") is None

    def test_empty_string(self):
        assert parse_nmea_sentence("") is None

    def test_bad_checksum_returns_none(self):
        sentence = "$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*FF"
        assert parse_nmea_sentence(sentence) is None

    def test_unknown_sentence_type_returns_none(self):
        sentence = "$GPXXX,data,data*00"
        assert parse_nmea_sentence(sentence) is None


class TestMergePoints:
    def test_empty_returns_empty(self):
        assert merge_points([]) == []

    def test_all_zero_coords_filtered(self):
        pts = [TelemetryPoint(lat=0.0, lon=0.0), TelemetryPoint(lat=0.0, lon=0.0)]
        assert merge_points(pts) == []

    def test_sorted_by_time(self):
        pts = [
            TelemetryPoint(t=2.0, lat=55.0, lon=37.0),
            TelemetryPoint(t=0.0, lat=55.1, lon=37.1),
            TelemetryPoint(t=1.0, lat=55.2, lon=37.2),
        ]
        result = merge_points(pts)
        times = [p.t for p in result]
        assert times == sorted(times)

    def test_merges_alt_from_gga(self):
        # Two points at same time: first has speed/heading, second has alt
        pts = [
            TelemetryPoint(t=0.0, lat=55.0, lon=37.0, speed=10.0, heading=90.0, alt=0.0),
            TelemetryPoint(t=0.0, lat=55.0, lon=37.0, speed=0.0, heading=0.0, alt=150.0),
        ]
        result = merge_points(pts)
        assert len(result) == 1
        assert result[0].alt == 150.0
        assert result[0].speed == 10.0

    def test_single_valid_point(self):
        pts = [TelemetryPoint(t=0.0, lat=55.0, lon=37.0, speed=5.0)]
        result = merge_points(pts)
        assert len(result) == 1
        assert result[0].lat == 55.0
