"""PR #12 port: value_parse, vst_params, vst_intents, calibration, filter.

All pure helpers -- no FL, no bridge.
"""
from __future__ import annotations

from fl_studio_mcp.music import calibration as cal
from fl_studio_mcp.music import value_parse as vp
from fl_studio_mcp.music import vst_intents as vin
from fl_studio_mcp.music import vst_params as vpm
from fl_studio_mcp.tools.plugin import filter_params_by_name

# -- value_parse ------------------------------------------------------------

def test_parse_db():
    r = vp.parse_value_string("-16.00 dB")
    assert r["value"] == -16.0 and r["unit"] == "dB"


def test_parse_khz_folds_to_hz():
    r = vp.parse_value_string("1.2 kHz")
    assert abs(r["value"] - 1200.0) < 1e-9 and r["unit"] == "Hz"


def test_parse_ratio():
    r = vp.parse_value_string("3.50:1")
    assert r["value"] == 3.5 and r["unit"] == "ratio"


def test_parse_compound_percent_wins():
    r = vp.parse_value_string("50% [-9.0 dB]")
    assert r["value"] == 50.0 and r["unit"] == "%"


def test_parse_ms_beats_s():
    assert vp.parse_value_string("0.725 ms")["unit"] == "ms"
    assert vp.to_canonical(1.5, "s") == (1500.0, "ms")


def test_parse_empty_and_plain():
    assert vp.parse_value_string("")["value"] is None
    assert vp.parse_value_string(None)["value"] is None
    r = vp.parse_value_string("0.42")
    assert r["value"] == 0.42 and r["unit"] is None


# -- vst_params -------------------------------------------------------------

def test_group_params_by_role():
    params = [{"i": 0, "name": "Cutoff"},
              {"i": 1, "name": "LFO Rate"},
              {"i": 2, "name": "Attack"},
              {"i": 3, "name": "Mystery"}]
    groups = vpm.group_params_by_role(params)
    assert "filter" in groups and groups["filter"][0]["i"] == 0
    assert "lfo" in groups
    assert "envelope" in groups
    assert "other" in groups


def test_classify_exposure_tiers():
    named = [{"name": "Cutoff", "s": "2 kHz"}] * 10
    assert vpm.classify_param_exposure(named)["tier"] == "full"
    names_only = [{"name": "Cutoff", "s": ""}] * 10
    assert vpm.classify_param_exposure(names_only)["tier"] == "partial"
    generic = [{"name": "Param %d" % i, "s": ""} for i in range(10)]
    assert vpm.classify_param_exposure(generic)["tier"] == "opaque"
    assert vpm.classify_param_exposure([])["tier"] == "empty"


def test_is_generic_name():
    assert vpm.is_generic_name("Param 12")
    assert vpm.is_generic_name("P3")
    assert vpm.is_generic_name("")
    assert not vpm.is_generic_name("Cutoff")


# -- calibration ------------------------------------------------------------

def test_build_curve_monotonic():
    c = cal.build_curve([(0.0, 0.0), (0.5, 5.0), (1.0, 10.0)])
    assert c["monotonic"] is True and c["n"] == 3


def test_build_curve_drops_non_monotonic():
    c = cal.build_curve([(0.0, 5.0), (0.5, 2.0), (1.0, 10.0)])
    assert c["monotonic"] is False


def test_interp_both_directions():
    c = cal.build_curve([(0.0, 0.0), (1.0, 100.0)])
    assert cal.norm_to_value(c, 0.5) == 50.0
    assert cal.value_to_norm(c, 25.0) == 0.25
    # clamps outside range
    assert cal.norm_to_value(c, 2.0) == 100.0
    assert cal.value_to_norm(c, -5.0) == 0.0


def test_signature_changes_with_layout():
    a = cal.signature("Serum", 541, ["Cutoff", "Reso"])
    b = cal.signature("Serum", 541, ["Cutoff", "Reso"])
    c = cal.signature("Serum", 540, ["Cutoff", "Reso"])
    assert a == b and a != c


# -- vst_intents ------------------------------------------------------------

def test_resolve_and_list():
    assert vin.resolve_intent("brighter")["direction"] == +1
    assert vin.resolve_intent("DARKER")["direction"] == -1
    assert vin.resolve_intent("nonsense") is None
    assert "wider" in vin.list_intents()


def test_pick_param_prefers_specific():
    params = [{"i": 0, "name": "Filter Cutoff Env Amount"},
              {"i": 1, "name": "Cutoff"},
              {"i": 2, "name": "Volume"}]
    picked = vin.pick_param(params, ("cutoff",))
    assert picked["i"] == 1  # shorter name wins


def test_relative_target_mul_and_frac():
    spec = vin.resolve_intent("brighter")   # mul, +1
    t = vin.relative_target(1000.0, spec, 0.5, (20.0, 20000.0))
    assert t == 2000.0                        # 1000 * (1 + 2*0.5)
    spec = vin.resolve_intent("wider")       # frac, +1
    t = vin.relative_target(0.5, spec, 0.5, (0.0, 1.0))
    assert abs(t - 1.0) < 1e-9                # 0.5 + 0.5*(1-0)*0.5... span*amount
    # clamped
    t = vin.relative_target(0.9, spec, 1.0, (0.0, 1.0))
    assert t == 1.0


# -- filter_params_by_name --------------------------------------------------

def test_filter_all_tokens_must_match():
    params = [{"i": 0, "name": "Filter Cutoff"},
              {"i": 1, "name": "Cutoff"},
              {"i": 2, "name": "Filter Resonance"}]
    hits = filter_params_by_name(params, "filter cutoff")
    assert [p["i"] for p in hits] == [0]


def test_filter_case_insensitive_and_limit():
    params = [{"i": i, "name": "Cutoff %d" % i} for i in range(100)]
    hits = filter_params_by_name(params, "cutoff", limit=5)
    assert len(hits) == 5


def test_filter_empty_query():
    assert filter_params_by_name([{"name": "X"}], "") == []
