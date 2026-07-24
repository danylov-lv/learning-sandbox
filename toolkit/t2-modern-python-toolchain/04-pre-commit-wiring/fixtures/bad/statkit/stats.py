import os   

def mean(values):
    return sum(values) / len(values)


def variance(values: list[float]) -> float:
    avg = mean(values)
    return sum((v - avg) ** 2 for v in values) / len(values)