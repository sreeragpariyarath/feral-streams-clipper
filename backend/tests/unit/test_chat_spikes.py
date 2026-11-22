import random

from src.detect.chat_spikes import detect_spikes
from src.twitch_chat import chat_signal_lines, parse_chat_json, twitch_vod_id


def synthetic_chat(seconds=900, spike_at=500):
    """Quiet chat (about 1 message a second) with a loud burst of reactions at ``spike_at``."""
    rng = random.Random(7)
    messages = []
    for second in range(seconds):
        for _ in range(rng.choice([0, 1, 1, 2])):
            messages.append((second + rng.random(), f"viewer{rng.randint(1, 40)}", rng.choice(["nice", "ok", "gg", "yeah", "true"])))
        if spike_at <= second < spike_at + 20:
            for i in range(14):
                messages.append((second + rng.random(), f"fan{i}{second}", rng.choice(["LMAO", "KEKW", "no way", "WTF", "omg", "PogChamp"])))
    return sorted(messages)


def test_a_burst_of_reactions_is_found_near_where_it_happened():
    spikes = detect_spikes(synthetic_chat())
    assert spikes, "expected a spike"
    best = spikes[0]
    assert 490 <= best["peak_t"] <= 540
    assert 0 < best["h_score"] <= 1


def test_quiet_chat_has_no_spikes():
    assert detect_spikes(synthetic_chat(spike_at=10_000)) == []


def test_an_empty_replay_is_fine():
    assert detect_spikes([]) == []


def test_signal_lines_use_the_prompt_format():
    line = chat_signal_lines(detect_spikes(synthetic_chat()))
    assert line.startswith("- [")
    assert "live chat reacted here" in line


def test_vod_id_from_urls():
    assert twitch_vod_id("https://www.twitch.tv/videos/2345678901") == "2345678901"
    assert twitch_vod_id("https://twitch.tv/somechannel/video/42") == "42"
    assert twitch_vod_id("https://www.youtube.com/watch?v=abc") is None


def test_parse_chat_json_reads_text_user_and_offset_in_order():
    payload = {"comments": [
        {"content_offset_seconds": 13, "commenter": {"display_name": "Bo"}, "message": {"body": "late"}},
        {"content_offset_seconds": 12.5, "commenter": {"display_name": "Ann"}, "message": {"body": "LMAO wow"}},
        {"content_offset_seconds": 14, "commenter": None, "message": {"body": "  "}},
    ]}
    assert parse_chat_json(payload) == [(12.5, "ann", "LMAO wow"), (13.0, "bo", "late")]
    assert parse_chat_json({}) == []
    assert parse_chat_json(None) == []
