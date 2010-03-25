
import py.test
import os

from mech.fusion.bitstream.bitstream import BitStream
from mech.fusion.bitstream.formats import One

def test_constructor():
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
    assert bits.cursor == 0
    bits.seek(1, os.SEEK_END)
    assert bits.bits_available == 1
    assert bits.read_bit() == 1
    py.test.raises(IndexError, bits.read_bit)

    bits.seek(0)
    assert bits.bits_available == 8

    result = bits.read_bit()
    assert result == 0
    
    result = bits.read_bits(2)
    assert result == [True, False]
    
    bits.seek(1, os.SEEK_CUR)
    assert bits.bits_available == 4
    assert bits.read_bits(2) == [True, True]

    bits.skip_to_end()
    assert bits.cursor == len(bits)

    bits.cursor = 0
    result = bits.read_bits(8)
    print str(result)
    print str(bits)
    assert str(result) == str(bits)

def test_BitStream_specialized_format_read():
    bits = BitStream("1011001")
    result = bits.read(BitStream[4])
    assert result == [True, False, True, True]
    assert bits.bits_available == 3
    py.test.raises(IndexError, bits.read, BitStream[4])

    bits = BitStream()
    bits.write("SWF", ByteString)

    bits.rewind()
    result = bits.read(BitStream[24:"<"])
    result = result.read(ByteString[3])
    assert result == "FWS"
    assert bits.bits_available == 0

def test_BitStream_specialized_format_write():
    L = [1, 0, True, False]
    
    bits = BitStream()
    bits.write(L)
    assert str(bits) == "1010"
    
    bits = BitStream("11")
    bits.write(L)
    assert str(bits) == "1010"

    bits = BitStream()
    bits.write(L[3:], BitStream[1])
    bits.write(L[2:], BitStream[1])
    assert str(bits) == "01"

    test = BitStream()
    test.write("SWF", ByteString)
    test.rewind()
    print str(test)

    bits = BitStream()
    bits.write(test, BitStream["<"])
    bits.rewind()
    print str(bits)

    result = bits.read(ByteString[3])
    assert result == "FWS"
    assert bits.bits_available == 0

def test_flush():
    # Test when bits has no data.
    bits = BitStream("")
    bits.flush()
    assert str(bits) == ""
    assert bits.bits_available == 0

    # Test when cursor == 0
    bits = BitStream("1111")
    bits.rewind()
    bits.flush()
    assert str(bits) == "11111100"
    assert bits.bits_available == 0

    # Test when cursor != 0.
    bits = BitStream("11100")
    bits.skip_to_end()
    bits.flush()
    assert str(bits) == "11100000"
    assert bits.bits_available == 0

    # Test when already flush.
    bits = BitStream("11111111")
    bits.rewind()
    bits.flush()
    assert str(bits) == "11111111"
    assert bits.bits_available == 0

    bits = BitStream("11111111 11111")
    bits.skip_to_end()
    bits.flush()
    assert str(bits) == "1111111111111000"
    assert bits.bits_available == 0

def test_skip_flush():
    bits = BitStream("111")
    bits.rewind()
    bits.skip_flush()
    assert str(bits) == "111"
    assert bits.bits_available == 3

    bits = BitStream("111")
    bits.skip_to_end()
    bits.skip_flush()
    assert str(bits) == "111"
    assert bits.bits_available == 3
