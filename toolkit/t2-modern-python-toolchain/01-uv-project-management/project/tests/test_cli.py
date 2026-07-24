"""Given, not edited. Requires pytest from the dev dependency group to run
at all — that's part of what this task grades."""

from pricetool.cli import main
from pricetool.data import PRICES


def test_prices_fixture_shape() -> None:
    assert len(PRICES) == 5
    assert all(isinstance(p, float) for p in PRICES)


def test_main_prints_summary(capsys) -> None:
    main()
    out = capsys.readouterr().out
    assert "count=5" in out
    assert "currency=USD" in out
