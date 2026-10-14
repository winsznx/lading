from evaluation.stats import describe


def test_describe_counts_wins_in_the_right_direction():
    spoiled = describe([-10.0, -5.0, 0.0, 4.0], "spoiled_kg")
    assert spoiled["wins"] == 2 and spoiled["losses"] == 1 and spoiled["n"] == 4
    assert spoiled["median"] == -2.5
    net = describe([100.0, -50.0, 25.0], "net_inr")
    assert net["wins"] == 2 and net["median"] == 25.0
    assert net["q1"] == -12.5 and net["q3"] == 62.5
