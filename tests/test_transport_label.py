from app.models.day import transport_label, TRANSPORT_MODES, TRANSPORT_MODE_EMOJI


def test_label_prepends_emoji():
    assert transport_label("飞机") == "✈️ 飞机"


def test_every_mode_has_emoji():
    for m in TRANSPORT_MODES:
        assert m in TRANSPORT_MODE_EMOJI
        assert transport_label(m).startswith(TRANSPORT_MODE_EMOJI[m])


def test_label_handles_empty_and_unknown():
    assert transport_label(None) == ""
    assert transport_label("") == ""
    assert transport_label("火箭") == "火箭"  # 未知方式无 emoji，原样返回
