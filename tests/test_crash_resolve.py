"""Forge crash-report / latest.log dependency parser."""

from __future__ import annotations

from cultagent.content.crash_resolve import parse_dep_failures


LOG = """
[17Aug2026 09:08:52.729] [main/ERROR] [net.minecraftforge.fml.loading.ModSorter/LOADING]: Missing or unsupported mandatory dependencies:
	Mod ID: 'curios', Requested by: 'irons_spellbooks', Expected range: '[5.14.1+1.20.1,)', Actual version: '[MISSING]'
	Mod ID: 'geckolib', Requested by: 'saintsdragons', Expected range: '[4.8.1,)', Actual version: '4.4.4'
	Mod ID: 'forge', Requested by: 'subtle_effects', Expected range: '[47.4.14,)', Actual version: '47.4.10'
	Mod ID: 'moonlight', Requested by: 'supplementaries', Expected range: '[1.20-2.16.26,]', Actual version: '[MISSING]'
"""

CRASH = """
-- MOD fog --
Details:
	Mod File: /C:/Users/arcad/mods/Fog-forge-1.5.3-1.20.1.jar
	Failure message: Mod fog requires mru any
		Currently, mru is not installed
	Mod Version: 1.5.3-1.20.1

-- MOD saintsdragons --
Details:
	Mod File: /C:/Users/arcad/mods/saintsdragons-0.9.3_forge-1.20.1.jar
	Failure message: Mod saintsdragons requires geckolib 4.8.1 or above
		Currently, geckolib is 4.4.4
"""


def test_parse_latest_log_mod_sorter_lines() -> None:
    issues = parse_dep_failures(LOG)
    by_req = {i.required: i for i in issues}
    assert by_req["curios"].missing
    assert by_req["curios"].requester == "irons_spellbooks"
    assert by_req["geckolib"].actual == "4.4.4"
    assert not by_req["geckolib"].missing
    assert by_req["forge"].platform
    assert by_req["moonlight"].version_range.startswith("[1.20")


def test_parse_fml_crash_blocks() -> None:
    issues = parse_dep_failures(CRASH)
    fog = next(i for i in issues if i.required == "mru")
    assert fog.requester == "fog"
    assert fog.missing
    assert fog.jar == "Fog-forge-1.5.3-1.20.1.jar"
    gecko = next(i for i in issues if i.required == "geckolib")
    assert gecko.actual == "4.4.4"
    assert gecko.jar and gecko.jar.startswith("saintsdragons")


def test_parse_client_dist_crash_disables_fog() -> None:
    text = """
-- MOD fog --
Details:
	Mod File: /C:/x/mods/Fog-forge-1.5.3-1.20.1.jar
	Failure message: Fog (fog) has failed to load correctly
		java.lang.RuntimeException: Attempted to load class net/minecraft/client/KeyMapping for invalid dist DEDICATED_SERVER
	Mod Version: 1.5.3-1.20.1
"""
    issues = parse_dep_failures(text)
    assert len(issues) == 1
    assert issues[0].client_dist
    assert issues[0].requester == "fog"
    assert issues[0].jar == "Fog-forge-1.5.3-1.20.1.jar"


def test_slug_candidates_cristellib() -> None:
    from cultagent.content.crash_resolve import _slug_candidates

    cands = _slug_candidates("cristellib")
    assert "cristel-lib" in cands


def test_slug_candidates_iceandfire() -> None:
    from cultagent.content.crash_resolve import _slug_candidates

    cands = _slug_candidates("iceandfire")
    assert "ice-and-fire-dragons" in cands


def test_parse_merges_log_and_crash() -> None:
    issues = parse_dep_failures(LOG + "\n" + CRASH)
    keys = {(i.required, i.requester) for i in issues}
    assert ("curios", "irons_spellbooks") in keys
    assert ("mru", "fog") in keys
    mru = next(i for i in issues if i.required == "mru")
    assert mru.jar
