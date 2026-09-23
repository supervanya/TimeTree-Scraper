from timetree_sync.title_rules import format_event_title, should_include_event


def test_maps_assignee_name_and_adds_volleyball_emoji() -> None:
    assert format_event_title("Volleyball Game", ("Jessica Danley",)) == "Jess: Volleyball Game 🏐"


def test_tournament_matching_is_case_insensitive() -> None:
    assert format_event_title("Fall Tournament") == "Fall Tournament 🏐"


def test_pom_adds_bow_emoji() -> None:
    assert format_event_title("Pom Practice", ("Hazel",)) == "Hazel: Pom Practice 🎀"


def test_combines_rules_without_duplicate_emoji() -> None:
    assert format_event_title("Pom Volleyball 🏐") == "Pom Volleyball 🏐 🎀"


def test_excludes_brittani_case_insensitively() -> None:
    assert should_include_event(("Brittani",)) is False
    assert should_include_event(("Hazel", "BRITTANI")) is False
    assert should_include_event(("Hazel",)) is True
