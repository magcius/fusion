
import struct
import os

from math import log, isnan, floor, ceil

ALIGN_LEFT = "left"
ALIGN_RIGHT = "right"

def nbits_signed(num, *args):
    """
    Returns nbits + 1, for the sign bit. Please use this
    instead of adding one manually.
    """
    return nbits(num, *args) + 1

def nbits(num, *args):
    """
    Returns the number of bits in the max of all the arguments.
    """
    return int(floor(log(max(1, abs(num), *(abs(a) for a in args)), 2))) + 1

def clamp(n, minimum, maximum):
    """
    Clamp n between mniimum and maximum.
    """
    return max(minimum, min(n, maximum))

class BitStream(object):

    """
    BitStream is a class for taking care of data
    structures that are bit-packed, like SWF.
    """
    
    def __init__(self, bits=[]):
        """
        Constructor.
        
        >>> b1 = BitStream("101010")               # Strings are okay.
        >>> b2 = BitStream([1, 0, "1", "0", 1, 0]) # So are any iterable.
        >>> b3 = BitStream(0b101010)               # But not ints.
        Traceback (most recent call last):
          File "<stdin>", line 1, in <module>
        TypeError: 'int' object is not iterable
        """
        self.bits = [bool(b) and b != "0" for b in bits if \
                         (isinstance(b, str) and b.strip() != "") or not \
                         isinstance(b, str)]
        self.cursor = 0
        self.chunks = set((0,))
    
    def read_bit(self):
        """
        Reads a bit from the bit stream and returns it as either True or False.

        .. seealso

           :meth:`write_bit`
              The writing equivalent of this method.
        
        :rtype: bool
        :raises IndexError: when reading past the end of the stream.
        """
        if self.cursor + 1 > len(self):
            raise IndexError("Attempted to read off the end of the BitStream")
        
        self.cursor += 1
        return self.bits[self.cursor-1]
    
    def write_bit(self, value):
        """
        Writes the boolean value to the bit stream.

        .. seealso

           :meth:`read_bits`
              The reading equivalent of this method.
        
        :param value: either True or False; ``bool(value)`` is called
        """
        if self.cursor < len(self.bits):
            self.bits[self.cursor] = bool(value)
        else:
            self.bits.append(bool(value))
        self.cursor += 1

    def read_bits(self, length):
        """
        Reads length bits and return them in their own bit stream.
        
        .. seealso

           :meth:`write_bits`
              The writing equivalent of this method.
        
        :rtype: BitStream
        :param length: the length of the BitStream that should be returned
        :type length:  an integer
        :raises IndexError: when reading past the end of the stream.
        """
        if self.cursor + length > len(self):
            raise IndexError("Attempted to read off the end of the BitStream")
        
        self.cursor += length
        return BitStream(self.bits[self.cursor-length:self.cursor])

    def write_bits(self, bits, offset=0, length=None):
        """
        Writes *length* bits from bits to this bit stream, starting
        reading at *offset*. If *length*  is 0 or omitted, the entire
        stream is used.

        .. seealso

           :meth:`read_bits`
              The reading equivalent of this method.
        
        :param bits: the subscriptable to read bits from
        :type bits:  a subscriptable (something that implements ``__getitem__``)
        :param offset: the offset to start reading bits from *bits*
        :type offset:  an integer
        :param length: the length of bits that should be read from *bits*
        :type length:  an integer or None
        """
        if not length:
            length = len(bits)

        if length > self.bits_available():
            for i in range(length - self.bits_available()):
                self.bits.append(False)
        
        self.bits[self.cursor:self.cursor+length] = (bool(x) for x in bits[offset:offset+length])
        self.cursor += length

    def read_int_value(self, length):
        """
        Read *length* bits and return a number in twos-complement form,
        with the last bit read being the least significant bit.

        .. seealso

           :meth:`write_int_value`
              The writing equivalent of this method.

           `Wikipedia: Two's complement <http://en.wikipedia.org/wiki/Two%27s_complement>`_
              Has information on the two's complement number system.
        
        :rtype: an integer
        :raises IndexError: when reading past the end of the stream.
        :param length: the amount of bits to be read
        :type length:  an integer
        """
        if self.cursor + length > len(self):
            raise IndexError("Attempted to read off the end of the BitStream")
        
        n = 0
        for i in reversed(xrange(length)):
            n |= self.read_bit() << i
        return n
    
    def write_int_value(self, value, length=None):
        """
        Writes *value* to the specified number of bits in the stream,
        the most significant bit first. If *length* is omitted or 0,
        the log base 2 of value is taken.

        .. seealso

           :meth:`read_int_value`
              The reading equivalent of this method.

           `Wikipedia: Two's complement <http://en.wikipedia.org/wiki/Two%27s_complement>`_
              Has information on the two's complement number system.
        
        :param value: the value to be written to this stream
        :type value:  an integer
        :param length: the amount of bits
        :raises ValueError: when length is not enough to serialize value
        """

        log2 = nbits(value)
        
        if not length:
            length = log2
        elif length < log2:
            # Length is not large enough
            raise ValueError(("length of %d is not large"
                             " enough to store %d") % (length, value))
        self.chunk()
        for i in reversed(xrange(length)):
            self.write_bit(value & (1 << i))
    
    def read_fixed_value(self, eight_bit):
        """
        Reads a fixed point number, either 8.8 or 16.16.
        If eight_bit is True, an 8.8 format is used instead of a
        16.16 format.

        .. seealso

           :meth:`write_fixed_value`
              The writing equivalent of this method.

           `SWF specification v10 <http://www.adobe.com/devnet/swf/>`_
              Has information on fixed-point values.
        
        :rype: a float
        :param eight_bit: should 8.8 fixed format be used?
        :type eight_bit:  a boolean
        """
        return self.read_int_value(8 if eight_bit else 16) / \
            float(0x100 if eight_bit else 0x10000)

    def write_fixed_value(self, value, eight_bit):
        """
        Writes a fixed point number, decimal part first.
        If eight_bit is True, an 8.8 format is used instead of a
        16.16 format.

        .. seealso:

           :meth:`read_fixed_value`
              The reading equivalent of this method.

           `SWF specification v10 <http://www.adobe.com/devnet/swf/>`_
              Has information on fixed-point values.

        :param value: the number to be written
        :type value:  a float
        :param eight_bit: should 8.8 fixed format be used?
        :type eight_bit:  a boolean
        """
        self.write_int_value(value * float(0x100 if eight_bit else 0x10000),
                             8 if eight_bit else 16)

    # Precalculated, see the Wikipedia links below.
    _EXPN_BIAS = {16: 16, 32: 127, 64: 1023}
    _N_EXPN_BITS = {16: 5, 32: 8, 64: 11}
    _N_FRAC_BITS = {16: 10, 32: 23, 64: 52}
    _FLOAT_NAME = {16: "float16", 32: "float", 64: "double"}

    def read_float_value(self, length):
        """
        Reads a floating point number of *length*, which must
        be 16 (float16), 32 (float) or 64 (double).

        .. seealso:

           :meth:`write_float_value`
              The writing equivalent of this method.

           `Wikipedia article on floating-point <http://en.wikipedia.org/wiki/IEEE_floating-point_standard>`_
              A good overview article of the IEEE floating-point standard, from Wikipedia.
        
        .. warning: Flash's float16 exponent bias is 16, not 15.

        :param length: either 16, 32, or 64
        :type length:  an integer
        """

        if length not in self._FLOAT_NAME:
            raise ValueError, "length is not 16, 32 or 64."
        
        sign = self.read_bit()
        
        expn_len = self._N_EXPN_BITS[length]
        frac_len = self._N_FRAC_BITS[length]
        
        expn = self.read_int_value(expn_len)
        frac = self.read_int_value(frac_len)

        bias = expn - self._EXPN_BIAS[length]
        
        frac_total = float(1 << frac_len)
        expn_total = float(1 << expn_len)
        
        if expn == 0:
            if frac == 0:
                return 0
            else:
                return ~frac + 1 if sign else frac
        elif expn == expn_total - 1:
            if frac == 0:
                return float("-inf") if sign else float("inf")
            else:
                return float("nan")

        return (-1 if sign else 1) * 2**bias * (1 + frac / frac_total)

    def write_float_value(self, value, length):
        """
        Writes a floating point number of *length*, which must be
        16 (float16), 32 (float), or 64 (double).

        .. seealso:

           :meth:`read_float_value`
              The reading equivalent of this method.

           `Wikipedia article on floating-point <http://en.wikipedia.org/wiki/IEEE_floating-point_standard>`_
              A good overview article of the IEEE floating-point standard, from Wikipedia.
        
        .. warning: Flash's float16 exponent bias is 16, not 15.

        :raises ValueError: when the number is too big for this type of float.

        :param value: the value to be written
        :type value:  a float
        :param length: either 16, 32, or 64
        :type length:  an integer
        """
        
        if length not in BitStream._FLOAT_NAME:
            raise ValueError, "length is not 16, 32 or 64."
        
        if value == 0: # value is zero, so we don't care about length
            self.write_int_value(0, length)
        
        if isnan(value):
            self.one_fill(length)
            return
        elif value == float("-inf"): # negative infinity
            self.one_fill(BitStream._N_EXPN_BITS[length] + 1) # sign merged
            self.zero_fill(BitStream._N_FRAC_BITS[length])
            return
        elif value == float("inf"): # positive infinity
            self.write_bit(False)
            self.one_fill(BitStream._N_EXPN_BITS[length])
            self.zero_fill(BitStream._N_FRAC_BITS[length])
            return

        if value < 0:
            self.write_bit(True)
            value = ~value + 1
        else:
            self.write_bit(False)
        
        exp = BitStream._EXPN_BIAS[length]
        if value < 1:
            while int(value) != 1:
                value *= 2
                exp -= 1
        else:
            while int(value) != 1:
                value /= 2
                exp += 1

        if exp < 0 or exp > ( 1 << BitStream._N_EXPN_BITS[length] ):
            raise ValueError, "Exponent out of range in %s [%d]." % (BitStream._FLOAT_NAME[length], length)

        frac_total = 1 << BitStream._N_FRAC_BITS[length]
        self.write_int_value(exp, BitStream._N_EXPN_BITS[length])
        self.write_int_value(int((value-1)*frac_total) & (frac_total - 1), BitStream._N_FRAC_BITS[length])

    
    def one_fill(self, amount):
        """
        Fills amount bits with one. The equivalent of calling
        self.write_boolean(True) amount times, but more efficient.
        """

        if amount > self.bits_available():
            self.bits += [True] * (amount - self.bits_available())
        
        self.bits[self.cursor:self.cursor+amount] = [True] * amount
        self.cursor += amount
        
    def zero_fill(self, amount):
        """
        Fills amount bits with zero. The equivalent of calling
        self.write_boolean(False) amount times, but more efficient.
        """
        
        if amount > self.bits_available():
            self.bits += [False] * (amount - self.bits_available())
        
        self.bits[self.cursor:self.cursor+amount] = [False] * amount
        self.cursor += amount
        
    def seek(self, offset, whence=os.SEEK_SET):
        """
        Standard file protocol *seek* method.

        .. seealso:
          
           `Built-in Types: File Objects
           <http://docs.python.org/library/stdtypes.html#file-objects>`_
              Standard Python library documentation.
        """
        if whence == os.SEEK_SET:
            self.cursor = offset
        elif whence == os.SEEK_CUR:
            self.cursor += offset
        elif whence == os.SEEK_END:
            self.cursor = len(self.bits) - abs(offset)

    def rewind(self):
        """
        Seek to the beginning of the stream.
        """
        self.seek(0, os.SEEK_SET)
        
    def skip_to_end(self):
        """
        Seek to the end of the stream.
        """
        self.seek(0, os.SEEK_END)

    def bits_available(self):
        """
        Return the number of bits available to be read, or the
        distance from the cursor to the end of the stream.
        """
        return len(self.bits) - self.cursor

    def flush(self):
        """
        Zero-fill until we are aligned with byte boundaries,
        i.e until our length is a multiple of 8.
        This sets the cursor to the end of the stream.
        """
        self.skip_to_end()
        if len(self) % 8:
            self.zero_fill(8 - (len(self) % 8))

    def chunk(self):
        """
        Internal method to handle endianness.

        This will probably be replaced soon.
        """
        self.chunks.add(int(ceil(self.cursor / 8.)))

    def __iter__(self):
        return iter(self.bits)

    def __eq__(self, other):
        return list(self) == list(other)

    def __ne__(self, other):
        return list(self) != list(other)
    
    def __len__(self):
        return len(self.bits)

    def __getitem__(self, i):
        return self.bits[i]

    def __setitem__(self, i, v):
        self.bits[i] = v
    
    def __str__(self):
        return "".join("1" if b else "0" for b in self.bits)

    def __add__(self, bits):
        b = BitStream()
        b.write_bits(self)
        b.write_bits(bits)
        return b

    def __iadd__(self, bits):
        self.write_bits(bits)
        return self
    
    def serialize(self, align=ALIGN_LEFT, endianness=None):
        """
        Serialize bit array into a byte string, aligning either
        on the right (ALIGN_RIGHT) or left (ALIGN_LEFT). Endianness
        can also be "<" for little-endian modes.
        """
        lst = self.bits[:]
        leftover = len(lst) % 8
        if leftover > 0:
            if align == ALIGN_RIGHT:
                # Insert some False values to pad the list
                # so it is aligned to the right.
                lst[:0] = [False] * (8-leftover)
            else:
                lst += [False] * (8-leftover)
        
        lst = BitStream(lst)
        tmp = [lst.read_int_value(8) for i in xrange(int(ceil(len(lst)/8.)))]
        
        bytes = [None] * len(tmp)
        if endianness == "<":
            m = sorted(self.chunks) + [len(tmp)]
            for start, end in zip(m, m[1:]):
                bytes[start:end] = tmp[end-1:None if start == 0 else start-1:-1]
        else:
            bytes = tmp
        return ''.join(chr(b) for b in bytes)

    def parse(self, string):
        """Parse a bit array from a byte string into this BitStream."""
        for char in string:
            self.write_int_value(ord(char), 8)
    
