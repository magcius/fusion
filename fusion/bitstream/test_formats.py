
import py.test
import os

from fusion.bitstream.bitstream import BitStream

from fusion.bitstream.formats import Bit, Byte, ByteList,  \
     ByteString, SignedByte, CString, UTF8, CUTF8, Zero, One, UB, SB, FB, \
     FloatFormat, FixedFormat

def test_Bit_read():
    bits = BitStream("1001")
    assert bits.read(Bit) == 1
    assert bits.read(Bit) == 0
    assert bits.read(Bit) == 0
    assert bits.read(Bit) == 1
    assert bits.bits_available == 0
    py.test.raises(IndexError, bits.read, Bit)

def test_Bit_write():
    bits = BitStream()

    # Testing IFormat adapting.
    bits.write(True)
    bits.write(False)

    # Testing Bit format.
    bits.write(1, Bit)
    bits.write(0, Bit)

    # Testing Bit format adaption by Bool.
    bits.write(bits, Bit) # Should be True.
    bits.write([], Bit)   # Should be False.

    # Testing boolean formats.
    bits.write(One)
    bits.write(Zero)
    assert str(bits) == "10101010"
    assert bits.bits_available == 0

def test_FormatArray_read():
    bits = BitStream("010101")

    result = bits.read(Bit[:][6])
    assert result == [False, True]*3

def test_FormatArray_write():
    bits = BitStream()

    bits.write([True, False]*3, Bit[:][6])
    assert str(bits) == "101010"

def test_sequence_to_IFormat():
    bits = BitStream()

    bits.write([True, False, True])
    assert str(bits) == "101"

def test_Byte_read():
    # Testing basics.
    bits = BitStream("10101010 11001100")
    result = bits.read(Byte[1])
    assert result == 0b10101010
    assert bits.bits_available == 8

    result = bits.read(Byte[1])
    assert result == 0b11001100
    assert bits.bits_available == 0

    # Testing out-of-bounds checking.
    py.test.raises(ValueError, bits.read, Byte)

    # Testing length.
    bits.seek(0)
    result = bits.read(Byte[2])
    assert result == 0b1010101011001100
    assert bits.bits_available == 0

    # Testing endianness.
    bits.seek(0)
    result = bits.read(Byte[2:"<"])
    assert result == 0b1100110010101010
    assert bits.bits_available == 0

    # Testing length behavior.
    bits.seek(0)
    result = bits.read(Byte) # This should read one byte.
    assert result == 0b10101010
    assert bits.bits_available == 8

    # Make length not divisible by 8.
    bits.seek(0, os.SEEK_END)
    bits.write(Zero)

    bits.seek(0)
    result = bits.read(Byte) # But this should still work.
    assert result == 0b10101010
    assert bits.bits_available == 9

def test_Byte_write():
    # Testing basics.
    bits = BitStream()
    bits.write(42, Byte)
    assert str(bits) == "00101010"

    # Testing signed numbers.
    bits = BitStream()
    bits.write(-42, SignedByte)
    assert str(bits) == "11010110"

    # Testing multiple-byte values.
    bits = BitStream()
    bits.write(1033, Byte)
    assert str(bits) == "0000010000001001"

    # Testing explicit length.
    bits = BitStream()
    bits.write(1033, Byte[3])
    assert str(bits) == "000000000000010000001001"

    # Testing explicit length with 0.
    bits = BitStream()
    bits.write(0, Byte[3])
    assert str(bits) == "000000000000000000000000"

    # Testing leftover < 0.
    bits = BitStream()
    py.test.raises(ValueError, bits.write, 1033, Byte[1])

    # Testing endianness.
    bits = BitStream()
    bits.write(1033, Byte["<"])
    assert str(bits) == "0000100100000100"

    # Testing endianness and explicit length.
    bits = BitStream()
    bits.write(1033, Byte[3:"<"])
    assert str(bits) == "000010010000010000000000"

    # Testing endianness and explicit length with 0.
    bits = BitStream()
    bits.write(0, Byte[3:"<"])
    assert str(bits) == "000000000000000000000000"


def test_ByteString_read():
    # Testing basics.
    bits = BitStream("00101010 00101111")
    result = bits.read(ByteString[1])
    assert result == chr(0b00101010)
    assert bits.bits_available == 8

    # Testing length.
    bits.seek(0)
    result = bits.read(ByteString[2])
    assert result == chr(0b00101010) + chr(0b00101111)
    assert bits.bits_available == 0

    # Testing endianness.
    bits.seek(0)
    result = bits.read(ByteString[2:"<"])
    assert result == chr(0b00101111) + chr(0b00101010)
    assert bits.bits_available == 0

    # Testing with no length provided.
    bits.seek(0)
    result = bits.read(ByteString)
    assert result == chr(0b00101010) + chr(0b00101111)


    # Testing non-flush length.

    # Make length not divisible by 8.
    bits.seek(0, os.SEEK_END)
    bits.write(Zero)

    bits.seek(0)
    result = bits.read(ByteString[2]) # This should still work.
    assert result == chr(0b00101010) + chr(0b00101111)
    assert bits.bits_available == 1

    bits.seek(0)
    py.test.raises(ValueError, bits.read, ByteString) # But this should fail.

def test_ByteString_write():
    # Testing basics.
    bits = BitStream()
    bits.write("SWF", ByteString)
    assert bits.bits_available == 0
    assert len(bits) == 24

    bits.seek(0)
    for i, char in enumerate("SWF"):
        result = bits.read(Byte)
        assert result == ord(char)
        assert bits.bits_available + i*8 == 16

    # Testing explicit length.
    bits = BitStream()
    bits.write("SWF", ByteString[3])
    assert bits.bits_available == 0
    assert len(bits) == 24

    bits.seek(0)
    for i, char in enumerate("SWF"):
        result = bits.read(Byte)
        assert result == ord(char)
        assert bits.bits_available + i*8 == 16

    # Testing leftover > 0.
    bits = BitStream()
    bits.write("SWF", ByteString[4])
    assert bits.bits_available == 0
    assert len(bits) == 32

    bits.seek(0)
    for i, char in enumerate("\0SWF"):
        result = bits.read(Byte)
        assert result == ord(char)
        assert bits.bits_available + i*8 == 24

    # Testing leftover < 0.
    bits = BitStream()
    py.test.raises(ValueError, bits.write, "SWF", ByteString[1])

    # Testing endianness.
    bits = BitStream()
    bits.write("SWF", ByteString["<"])
    assert bits.bits_available == 0
    assert len(bits) == 24

    bits.seek(0)
    for i, char in enumerate("FWS"):
        result = bits.read(Byte)
        assert result == ord(char)
        assert bits.bits_available + i*8 == 16

    # Testing leftover > 0 and endianness.
    bits = BitStream()
    bits.write("SWF", ByteString[5:"<"])
    assert bits.bits_available == 0
    assert len(bits) == 40

    bits.seek(0)
    for i, char in enumerate("FWS\0\0"):
        result = bits.read(Byte)
        assert result == ord(char)
        assert bits.bits_available + i*8 == 32

def test_CString_read():
    # Testing basics.
    bits = BitStream()
    test_data = "test 123\x01\xFF"
    bits.write(test_data, ByteString)
    bits.write(Zero[8])
    bits.seek(0)
    result = bits.read(CString)
    assert result == test_data

    # Testing error-handling.
    bits = BitStream()
    bits.write("adsfasfdgjklhrgokrjygaosaf", ByteString)
    bits.seek(0)
    py.test.raises(ValueError, bits.read, CString)

def test_CString_write():
    # Testing basics.
    bits = BitStream()
    bits.write("FWS", CString)
    assert bits.bits_available == 0
    assert len(bits) == 32
    bits.seek(0)
    result = bits.read(Byte)
    assert result == ord("F")
    assert bits.bits_available == 24
    result = bits.read(Byte)
    assert result == ord("W")
    assert bits.bits_available == 16
    result = bits.read(Byte)
    assert result == ord("S")
    assert bits.bits_available == 8
    result = bits.read(Byte)
    assert result == 0
    assert bits.bits_available == 0

def test_UB_read():
    bits = BitStream("101010")
    assert bits.read(UB[6]) == 42
    assert bits.bits_available == 0

    bits = BitStream("010 0111011001 101010 10001 10111")
    assert bits.read(UB[3]) == 2
    assert bits.bits_available == 26
    assert bits.read(UB[10]) == 0b0111011001
    assert bits.bits_available == 16
    assert bits.read(UB[6]) == 0b101010
    assert bits.bits_available == 10
    assert bits.read(UB[5]) == 0b10001
    assert bits.bits_available == 5
    assert bits.read(UB[5]) == 0b10111
    assert bits.bits_available == 0

    bits = BitStream()
    bits.write("\xDD\xEE\xFF", ByteString)

    bits.seek(0)
    result = bits.read(UB[24])
    assert result == 0xDDEEFF
    assert bits.bits_available == 0

    bits.seek(0)
    result = bits.read(UB[24:"<"])
    assert result == 0xFFEEDD
    assert bits.bits_available == 0

def test_UB_write():
    bits = BitStream()
    bits.write(0b1111, UB[4])
    assert len(bits) == 4 and str(bits) == "1111"

    bits = BitStream()
    bits.write(0b1111, UB[8])
    assert len(bits) == 8 and str(bits) == "00001111"

    bits = BitStream()
    bits.write(0xDDEEFF, UB)
    bits.seek(0)
    result = bits.read(ByteString[3])
    assert result == "\xDD\xEE\xFF"
    assert bits.bits_available == 0

    bits = BitStream()
    bits.write(0xDDEEFF, UB["<"])
    bits.seek(0)
    result = bits.read(ByteString[3])
    assert result == "\xFF\xEE\xDD"
    assert bits.bits_available == 0

def test_FixedValue_read():
    # TODO
    pass

def test_FixedValue_write():
    # TODO
    pass

def test_FloatValue_read():
    # Testing 16-bit float values.
    # Note that these are Flash's FLOAT16, with a different exponent
    # bias than the extended IEEE 754 spec.
    bits = BitStream("0100000000000000")
    result = bits.read(FloatFormat[16])
    assert result == 1
    assert bits.bits_available == 0

    bits = BitStream("0111110000000000")
    result = bits.read(FloatFormat[16])
    assert result == float("inf")
    assert bits.bits_available == 0

    bits = BitStream("1111110000000000")
    result = bits.read(FloatFormat[16])
    assert result == float("-inf")
    assert bits.bits_available == 0

    # Testing 32-bit float values.
    bits = BitStream("0 01111100 01000000000000000000000")
    result = bits.read(FloatFormat[32])
    assert result == 0.15625
    assert bits.bits_available == 0

    bits = BitStream("0 10000011 10010000000000000000000")
    result = bits.read(FloatFormat[32])
    assert result == 25
    assert bits.bits_available == 0

    bits = BitStream("0 11111111 00000000000000000000000")
    result = bits.read(FloatFormat[32])
    assert result == float("inf")
    assert bits.bits_available == 0

    bits = BitStream("1 11111111 00000000000000000000000")
    result = bits.read(FloatFormat[32])
    assert result == float("-inf")
    assert bits.bits_available == 0

    # Testing 32-bit float values.
    bits = BitStream("0011111111110000000000000000000000000000000000000000000000000000")
    result = bits.read(FloatFormat[64])
    assert result == 1
    assert bits.bits_available == 0

    bits = BitStream("0111111111110000000000000000000000000000000000000000000000000000")
    result = bits.read(FloatFormat[64])
    assert result == float("inf")
    assert bits.bits_available == 0

    bits = BitStream("1111111111110000000000000000000000000000000000000000000000000000")
    result = bits.read(FloatFormat[64])
    assert result == float("-inf")
    assert bits.bits_available == 0
