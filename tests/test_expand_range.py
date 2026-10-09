import pytest

from app.refs import expand_range


@pytest.mark.parametrize("value, expected", [
    ("43.2-6", ["43.2", "43.3", "43.4", "43.5", "43.6"]),
    ("43.2-43.4", ["43.2", "43.3", "43.4"]),
    ("1-3", ["1", "2", "3"]),
    ("5–6", ["5", "6"]),
    ("а-в", ["а", "б", "в"]),
    ("и-л", ["и", "к", "л"]),          # «й» пропускается
    ("12", ["12"]),
    ("4.6", ["4.6"]),
    ("1-2024", ["1-2024"]),            # не диапазон, а мусор
    ("6-2", ["6-2"]),
])
def test_expand_range(value, expected):
    assert expand_range(value) == expected
