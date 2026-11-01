from calc.arith import add


def mean(xs):
    total = 0
    for x in xs:
        total = add(total, x)
    return total / len(xs)
