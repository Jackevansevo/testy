import pytest
from calc.arith import add, mul


@pytest.mark.parametrize(
    ("op", "a", "b", "expected"),
    [(add, 1, 2, 3), (mul, 2, 3, 6)],
)
def test_ops(op, a, b, expected):
    assert op(a, b) == expected
