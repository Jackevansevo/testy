from calc.stats import mean


def test_mean(numbers):
    assert mean(numbers) == 2.5


def test_mean_single():
    assert mean([7]) == 7
