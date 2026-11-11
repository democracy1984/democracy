import services.promo as promo


def test_promo_text_contains_context():
    text = promo.build_promo_text("замутили", "Тестовый чат")
    assert "замутили" in text
    assert "Тестовый чат" in text
    assert "ВЫБОРЫ ЕСТЬ" in text


def test_promo_text_exact_first_variant():
    text = promo.build_promo_text(
        "забанили", "Чат", chooser=lambda variants: variants[0]
    )
    assert text == (
        "Тебя совершенно несправедливо забанили в чате Чат, это ВОЗМУТИТЕЛЬНО!!!\n"
        "ДОВОЛЬНО ЭТО ТЕРПЕТЬ!!! Вставай на путь демократии и свободы выбора!!!\n"
        "Присоединяйся к нашему походу за справедливость, распространяй стикер, ВЫБОРЫ ЕСТЬ!!!"
    )


def test_promo_text_all_variants_format():
    for opening in promo.OPENINGS:
        for middle in promo.MIDDLES:
            for ending in promo.ENDINGS:
                assert "{" not in opening.format(action_word="x", chat_title="y")
                assert "{" not in middle
                assert "{" not in ending


def test_promo_text_randomizes():
    texts = {promo.build_promo_text("замутили", "Чат") for _ in range(30)}
    assert len(texts) > 1


def test_victory_text_is_random_and_known():
    assert promo.build_victory_text(chooser=lambda variants: variants[0]) == promo.VICTORY_PHRASES[0]
    texts = {promo.build_victory_text() for _ in range(30)}
    assert len(texts) > 1
    assert texts <= set(promo.VICTORY_PHRASES)
