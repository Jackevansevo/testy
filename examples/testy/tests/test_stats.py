from calc.stats import mean
from tests.fixtures.numbers import numbers


def test_mean():
    with numbers() as xs:
        assert mean(xs) == 2.5


def test_mean_single():
    assert mean([7]) == 7
