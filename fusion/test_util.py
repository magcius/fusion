
import py.test

from fusion.util import nbits, nbits_signed

def test_nbits():
    assert nbits(0) == 0
    assert nbits(1) == 1
    assert nbits(2) == 2
    assert nbits(4) == 3

    assert nbits(-1) == 1
    assert nbits(-2) == 2
    assert nbits(-4) == 3

    assert nbits(0, 1, 4, 2) == 3
    assert nbits(0, 1, -4, 2) == 3

def test_nbits_signed():
    assert nbits_signed(0) == 0
    assert nbits_signed(1) == 2
    assert nbits_signed(2) == 3
    assert nbits_signed(3) == 3
    assert nbits_signed(4) == 4
    assert nbits_signed(63) == 7
    assert nbits_signed(64) == 8
    assert nbits_signed(65) == 8

    assert nbits_signed(-1) == 2
    assert nbits_signed(-2) == 2
    assert nbits_signed(-3) == 3
    assert nbits_signed(-4) == 3
    assert nbits_signed(-63) == 7
    assert nbits_signed(-64) == 7
    assert nbits_signed(-65) == 8

    assert nbits_signed(0, 1, 4, 2) == 4
    assert nbits_signed(0, 1, -4, 2) == 3
