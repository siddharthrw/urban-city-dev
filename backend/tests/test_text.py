import pytest

from core.text import compare_names, is_distinctive, name_similarity, normalize_name


@pytest.mark.parametrize("raw, expected", [
    ("North Usman Rd.", "north usman road"),
    ("Perumal Koil St Extn", "perumal koil street extension"),
    ("Ulaganathapuram VIIth Cross Street", "ulaganathapuram 7th cross street"),
    ("Nolambur Phase Ii 4th  Cross Street", "nolambur phase 2nd 4th cross street"),
    ("4 th Main Rd", "4th main road"),
    ("3 Cross St", "3rd cross street"),
    ("First Avenue Road", "1st avenue road"),
    ("N.S.K.Salai", "nsk salai"),
    ("V. O. C. Street", "voc street"),
    ("A Block Main Road", "a block main road"),
    ("Café & Bakery Street", "cafe and bakery street"),
    ("", ""),
    (None, ""),
])
def test_normalize(raw, expected):
    assert normalize_name(raw) == expected


def test_ordinals_are_correct():
    assert normalize_name("11 Cross St") == "11th cross street"
    assert normalize_name("22 Main Rd") == "22nd main road"
    assert normalize_name("XII Street") == "12th street"


def test_distinctive():
    assert is_distinctive("anna street")
    assert not is_distinctive("1st street")
    assert not is_distinctive("main road")
    assert not is_distinctive("4th cross street")


@pytest.mark.parametrize("a, b, expected", [
    ("Karuneegar Street", "KARNEEGAR STREET", "similar"),
    ("North Usman Road", "North Usman Rd.", "same"),
    ("Anna Street", "Anna Street Padi", "similar"),        # official name adds the locality
    ("1st Street", "Sadasiva Nagar 1st Link Street", "different"),  # too generic to call similar
    ("Mannar Street", "South Usman Road", "different"),
    ("Anna Salai", None, "only_a"),
    (None, "Anna Salai", "only_b"),
    (float("nan"), "Anna Salai", "only_b"),                # pandas missing values
    ("", None, "none"),
])
def test_compare(a, b, expected):
    assert compare_names(a, b) == expected


def test_similarity_bounds():
    assert name_similarity("x", "x") == 100
    assert name_similarity(None, "x") == 0
    assert 0 <= name_similarity("abc road", "xyz street") < 85
