"""
Regression tests for scientific corrections. Each test pins a value or behaviour
that was wrong in an earlier version, with the reference derivation in the docstring.
"""
import math

import numpy as np
import pytest

from helios.core.science import SpaceWeatherPhysics


def test_akasofu_epsilon_includes_4pi_over_mu0():
    """
    Perreault & Akasofu (1978): epsilon = v B^2 sin^4(theta/2) l0^2 in Gaussian units.
    In SI this is (4 pi / mu_0) v B^2 sin^4(theta/2) l0^2 with 4 pi / mu_0 = 1e7.
    v = 400 km/s, B = 10 nT purely southward, l0 = 7 R_E:
    1e7 * 4e5 * 1e-16 * (7 * 6.371e6)^2 = 7.955e11 W = 795.5 GW.
    """
    eps = SpaceWeatherPhysics.akasofu_epsilon(400.0, 10.0, 0.0, -10.0)
    expected = 1e7 * 4e5 * 1e-16 * (7.0 * 6.371e6) ** 2 / 1e9
    assert eps == pytest.approx(expected, rel=1e-6)
    assert 700.0 < eps < 900.0
