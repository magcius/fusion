
import py.test

def test_nbits():
    assert nbits(0) == 1
    assert nbits(1) == 1
    assert nbits(2) == 2
    assert nbits(4) == 3

    assert nbits(-1) == 1
    assert nbits(-2) == 2
    assert nbits(-4) == 3

    assert nbits(0, 1, 4, 2) == 3
    assert nbits(0, 1, -4, 2) == 3
