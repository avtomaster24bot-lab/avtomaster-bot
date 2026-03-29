import pytest
from utils.helpers import stars_from_rating, haversine

def test_stars_from_rating():
    assert stars_from_rating(None) == "☆☆☆☆☆"
    assert stars_from_rating(0) == "☆☆☆☆☆"
    assert stars_from_rating(1) == "⭐☆☆☆☆"
    assert stars_from_rating(1.2) == "⭐☆☆☆☆"
    assert stars_from_rating(1.5) == "⭐⯨☆☆☆"
    assert stars_from_rating(1.8) == "⭐⭐☆☆☆"
    assert stars_from_rating(2) == "⭐⭐☆☆☆"
    assert stars_from_rating(2.5) == "⭐⭐⯨☆☆"
    assert stars_from_rating(3) == "⭐⭐⭐☆☆"
    assert stars_from_rating(4.9) == "⭐⭐⭐⭐⭐"
    assert stars_from_rating(5) == "⭐⭐⭐⭐⭐"

def test_haversine():
    mos = (55.7558, 37.6173)
    spb = (59.9343, 30.3351)
    dist = haversine(mos[0], mos[1], spb[0], spb[1])
    assert 630 < dist < 640