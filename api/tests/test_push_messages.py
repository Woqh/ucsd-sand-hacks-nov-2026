from api.push.dispatch import MESSAGES_BY_TONE, _message


def test_every_tone_has_all_three_levels_and_they_differ():
    assert set(MESSAGES_BY_TONE) == {"gentle", "neutral", "direct"}
    for tone, table in MESSAGES_BY_TONE.items():
        assert set(table) == {1, 2, 3}, tone
        assert len({table[1], table[2], table[3]}) == 3                      # escalation is audible
    assert len({MESSAGES_BY_TONE[t][1] for t in MESSAGES_BY_TONE}) == 3      # and the tones really differ


def test_message_picks_the_tone_clamps_the_level_and_falls_back():
    assert _message(1, "direct") == ("Sit up.", "Slouching. Back straight, shoulders down.")
    assert _message(9, "neutral") == MESSAGES_BY_TONE["neutral"][3]           # beyond level 3: the last one
    assert _message(1, "no-such-tone") == MESSAGES_BY_TONE["gentle"][1]
    assert _message(2) == MESSAGES_BY_TONE["gentle"][2]
