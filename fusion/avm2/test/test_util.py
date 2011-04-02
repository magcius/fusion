
import py.test

from fusion.avm2.util import serialize_u32, ValuePool

def test_serialize_u32():
    for i in xrange(2**7):
        assert serialize_u32(i) == chr(i)

    for i in xrange(2**7, 2**14):
        assert serialize_u32(i) == chr(0x80 | i & 0x7F) + chr(i >> 7)

    for i in xrange(2**14, 2**16):
        assert serialize_u32(i) == chr(0x80 | i & 0x7F) + chr(0x80 | (i >> 7) & 0x7F) + chr(i >> 14)

    for i in range(2**35, 2**35+5):
        py.test.raises(ValueError, serialize_u32, i)

def test_serialize_u32_signed():
    for i in xrange(-1, -2**16, -1):
        j = i & 0xFFFFFFFF
        assert serialize_u32(i) == ''.join(chr(b) for b in [ (j     &0x7F)|0x80,
                                                            ((j>>7 )&0x7f)|0x80,
                                                            ((j>>14)&0x7f)|0x80,
                                                            ((j>>21)&0x7f)|0x80,
                                                            ((j>>28)&0x7f)])

    for i in range(-2**35, -2**35-5):
        py.test.raises(ValueError, serialize_u32, i)

def test_value_pool_default():
    test = object()
    pool = ValuePool(None, default=test)

    assert pool.value_at(0) == test
    assert pool.index_for(test) == 0

    assert pool.index_for(1) == 1
    assert pool.index_for(1) == 1

    assert pool.value_at(0) == test
    assert pool.value_at(1) == 1

def test_value_pool_no_default():
    test1, test2 = object(), object()
    pool = ValuePool(None)

    assert pool.index_for(test1) == 0
    assert pool.value_at(0) == test1

    assert pool.index_for(test2) == 1
    assert pool.value_at(1) == test2
