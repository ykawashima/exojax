from exojax.utils.constants import opfac, bar_cgs, Gcr
from scipy.constants import m_u
import pytest


def test_opfac():
    kg2g = 1.0e3
    val = bar_cgs / (m_u * kg2g)

    assert opfac == pytest.approx(val)


def test_Gcr():
    from astropy.constants import G as G_astropy
    from astropy.constants import M_sun
    from astropy import units as u

    day = 24 * 3600 * u.s
    Gu = (G_astropy * M_sun / day).value
    Gcr_val = Gu ** (1.0 / 3.0) * 1.0e-3  # km/s

    assert Gcr == pytest.approx(Gcr_val)