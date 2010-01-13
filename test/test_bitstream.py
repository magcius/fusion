
import py.test
import os

from mech.fusion.util import BitStream, nbits

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

def test_string():
    bits = BitStream("10")
    assert bits.bits == [True, False]
    
    bits = BitStream("10101100")
    assert bits.bits == [True, False, True, False, True, True, False, False]
    
    bits = BitStream("  1  ")
    assert len(bits) == 1

    bits = BitStream([True, False, True, False])
    assert str(bits) == "1010"

def test_cursor():
    bits = BitStream("01001101")
    bits.seek(1, os.SEEK_END)
    assert bits.bits_available() == 1
    assert bits.read_bit() == 1
    py.test.raises(IndexError, bits.read_bit)

    bits.seek(0)
    assert bits.bits_available() == 8
    assert bits.read_bit() == 0
    assert bits.read_bits(2) == [True, False]

    bits.seek(1, os.SEEK_CUR)
    assert bits.bits_available() == 4
    assert bits.read_bits(2) == [True, True]

def test_flush():
    bits = BitStream("010010")
    bits.flush()
    assert bits == BitStream("01001000")

def test_read_bit():
    bits = BitStream("1001")
    assert bits.read_bit() == 1
    assert bits.read_bit() == 0
    assert bits.read_bit() == 0
    assert bits.read_bit() == 1

def test_read_bits():
    bits = BitStream("1011001")
    result = bits.read_bits(4)
    assert result == [True, False, True, True]
    py.test.raises(IndexError, bits.read_bits, 4)

def test_read_int_value():
    bits = BitStream("101010")
    assert bits.read_int_value(6) == 42

    bits = BitStream("01011111111111")
    assert bits.read_int_value(3) == 2
    assert bits.read_int_value(11) == 2047

def test_read_fixed_value():
    # TODO
    pass

def test_read_float_value_16():
    bits = BitStream("0100000000000000")
    result = bits.read_float_value(16)
    assert result == 1
    
    bits = BitStream("0111110000000000")
    result = bits.read_float_value(16)
    assert result == float("inf")
    
    bits = BitStream("1111110000000000")
    result = bits.read_float_value(16)
    assert result == float("-inf")

def test_read_float_value_32():
    bits = BitStream("0 01111100 01000000000000000000000")
    assert bits.read_float_value(32) == 0.15625

    bits = BitStream("0 10000011 10010000000000000000000")
    assert bits.read_float_value(32) == 25

    bits = BitStream("0 11111111 00000000000000000000000")
    assert bits.read_float_value(32) == float("inf")
    
    bits = BitStream("1 11111111 00000000000000000000000")
    assert bits.read_float_value(32) == float("-inf")
    
def test_read_float_value_64():
    bits = BitStream("0011111111110000000000000000000000000000000000000000000000000000")
    result = bits.read_float_value(64)
    assert result == 1
    
    bits = BitStream("0111111111110000000000000000000000000000000000000000000000000000")
    result = bits.read_float_value(64)
    assert result == float("inf")

    bits = BitStream("1111111111110000000000000000000000000000000000000000000000000000")
    result = bits.read_float_value(64)
    assert result == float("-inf")

def test_flush():
    bits = BitStream("11000000")
    bits.flush()
    assert str(bits) == "11000000"
