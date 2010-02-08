
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

    # New API.
    def read(self, part):
        retval, cursor = part._read(self, self.cursor), 
        if isinstance(retval, tuple):
            retval, cursor = retval
        self.cursor += cursor
    
    def write(self, argument, part=None):
        if part is None:
            return argument.write(self, self.cursor)
        self.cursor += part._write(self, self.cursor, argument) or 0
    
    def read_bit(self):
        """
        Reads a bit from the bit stream and returns it as either True or False.

        .. seealso

           :meth:`write_bit`
              The writing equivalent of this method.
        
        :rtype: bool
        :raises IndexError: when reading past the end of the stream.
        """
        if self.bits_available() < 1:
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

    def read_bits(self, length, as_list=False, endianness=">"):
        """
        Reads length bits and return them in their own bit stream.

        .. seealso

           :meth:`write_bi.serializets`
              The writing equivalent of this method.
        
        :rtype: BitStream
        :param length: the length of the BitStream that should be returned
        :type length:  an integer
        :param as_list: fast switch, ignores endianness
        :raises IndexError: when reading past the end of the stream.
        :param endianness: if "<", string is reversed.
        :type endianness:  anything, either equal to "<" or not
        """
        if length > self.bits_available():
            raise IndexError("Attempted to read off the end of the BitStream")

        if as_list:
            bits = self.bits[self.cursor:self.cursor+length]
            self.cursor += length
            return bits
        
        bits = BitStream()
        bits.write_int_value(self.read_int_value(length),
                             length, endianness=endianness)
        bits.cursor = 0
        return bits

    def write_bits(self, bits, offset=0, length=None, endianness=">"):
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
        :param endianness: if "<", string is reversed.
        :type endianness:  anything, either equal to "<" or not
        """
        if hasattr(bits, "as_bits"):
            bits = bits.as_bits()

        if not length:
            length = len(bits) - offset

        value = BitStream(bits[offset:offset+length]).read_int_value(length)
        self.write_int_value(value, length, endianness=endianness)

    def read_string(self, length=None):
        """
        Read and return a string of *length* **bytes** (not bits).

        If endianness is "<", then the string is reversed
        before it is returned.

        .. seealso
        
           :meth:`write_string`
              The writing equivalent of this method.

        :rtype: a bytestring
        :param length: how many bytes to read, or None to read the rest of the BitStream
        :type length:  an integer
        :raises ValueError: when length is None and the rest
        of the BitStream is not divisible by 8
        """
        if length is None:
            if self.bits_available() & 7:
                raise ValueError("You cannot read the rest of the BitStream "
                                 "as a string. The length of the available "
                                 "bits is not divisible by 8.")
            length = self.bits_available() // 8
        return ''.join(BITS_TO_BYTE[tuple(self.read_bits(8, as_list=True))]
                       for i in xrange(length))

    def write_string(self, string):
        """
        Writes *string* to the BitStream as if with bytes.
        
        .. seealso

           :meth:`read_string`
              The reading equivalent of this method.

        :param string: the string to write
        :type string:  an iterable of characters
        """
        for c in string:
            self.bits += BYTE_TO_BITS[c]
        self.cursor += len(string) * 8

    def read_cstring(self):
        """
        Reads a C string (a string ended by a NUL or "\0").

        .. seealso

           :meth:`write_cstring`
              The writing equivalent of this method.
        
        :rtype: a string
        :raises ValueError: if no NUL character was found while reading
        """
        cursor = self.cursor
        buffer = ""
        s = ""
        while s != "\0":
            buffer += s
            try:
                s = self.read_string(1)
            except IndexError:
                self.cursor = cursor
                raise ValueError("Exhausted BitStream while trying to find NUL.")
        
        return buffer

    def write_cstring(self, string):
        """
        Writes a C string (a string ended by a NUL or "\0").

        .. seealso

           :meth:`read_cstring`
              The reading equivalent of this method.
        
        :param string: the string to write
        :type string:  an iterable of characters
        """
        self.write_string(string)
        self.zero_fill(8)
        
    def read_int_value(self, length, signed=False, endianness=">"):
        """
        Read *length* bits and return a number in twos-complement form,
        with the last bit read being the least significant bit.

        Example with endianness:
        
        >>> bits = BitStream()
        >>> bits.write_string("\xDD\xEE\xFF", endianness="<")
        >>> bits.rewind()
        >>> bits.read_int_value(24, endianness=">") == 0xFFEEDD
        True
        
        .. seealso

           :meth:`write_int_value`
              The writing equivalent of this method.

           `Wikipedia: Two's complement
           <http://en.wikipedia.org/wiki/Two%27s_complement>`_
              Has information on the two's complement number system.
        
        :rtype: an integer
        :param length: the amount of bits to be read
        :type length:  an integer
        :param signed: whether the first bit should be read as a sign bit
        :type signed:  True or False
        :param endianness: the byte-endianness to read
        :type endianness:  anything, either equal to "<" or not
        :raises IndexError: when reading past the end of the stream.
        """
        if length > self.bits_available():
            raise IndexError("Attempted to read off the end of the BitStream")
        
        n = 0
        s = False
        
        if signed and self.read_bit():
            s = True
            length -= 1
        
        for i in reversed(xrange(length)):
            if endianness == "<":
                i = (length // 8 - i // 8 - 1)*8 + i%8
            n |= self.read_bit() << i

        if s:
            return -n
        return n
    
    def write_int_value(self, value, length=None, endianness=">"):
        """
        Writes *value* to the specified number of bits in the stream,
        the most significant bit first. If *length* is omitted or 0,
        the log base 2 of value is taken.
        
        >>> bits = BitStream()
        >>> bits.write_int_value(7, length=10)
        >>> str(bits)
        "00000111"
        >>> bits.rewind()
        >>> bits.write_int_value(0xDDEEFF, endianness="<")
        >>> bits.rewind()
        >>> bits.read_string(3, endianness=">") == "\xFF\xEE\xDD"
        True
        
        .. seealso

           :meth:`read_int_value`
              The reading equivalent of this method.

           `Wikipedia: Two's complement
           <http://en.wikipedia.org/wiki/Two%27s_complement>`_
              Has information on the two's complement number system.
        
        :param value: the value to be written to this stream
        :type value:  an integer
        :param length: the amount of bits
        :type length:  an integer
        :param endianness: the byte-endianness to write
        :type endianness:  anything, either equal to "<" or not
        :raises ValueError: when length is not enough to serialize value
        """

        log2 = nbits(value)
        
        if not length:
            length = log2
        elif length < log2:
            # Length is not large enough
            raise ValueError(("length of %d is not large"
                             " enough to store %d") % (length, value))
        
        for i in reversed(xrange(length)):
            if endianness == "<":
                i = (length/8 - i/8 - 1)*8 + i%8
            self.write_bit(value & (1 << i))
    
    def read_fixed_value(self, length, endianness=">"):
        """
        Reads a fixed point number, either 8.8 or 16.16.
        
        If length is 16, an 8.8 format is used.
        If length is 32, a 16.16 format is used.

        .. seealso

           :meth:`write_fixed_value`
              The writing equivalent of this method.

           `SWF specification v10 <http://www.adobe.com/devnet/swf/>`_
              Has information on fixed-point values.
        
        :rtype: a float
        :param length: either 8 or 16
        :param endianness: the byte-endianness to write
        :type endianness:  anything, either equal to "<" or not
        """
        if length not in (16, 32):
            raise ValueError("Fixed values must be of length 16 (8.8) or length 32 (16.16)")
        return self.read_int_value(length, endianness=endianness) / \
            float({8: 0x100, 16: 0x10000}[length])

    def write_fixed_value(self, value, length, endianness=">"):
        """
        Writes a fixed point number, decimal part first.

        If length is 16, an 8.8 format is used.
        If length is 32, a 16.16 format is used.

        .. seealso:

           :meth:`read_fixed_value`
              The reading equivalent of this method.

           `SWF specification v10 <http://www.adobe.com/devnet/swf/>`_
              Has information on fixed-point values.

        :param value: the number to be written
        :type value:  a float
        :param length: either 8 or 16
        :param endianness: the byte-endianness to write
        :type endianness:  anything, either equal to "<" or not
        """
        if length not in (16, 32):
            raise ValueError("Fixed values must be of length 16 (8.8) or length 32 (16.16)")
        self.write_int_value(value * float({8: 0x100, 16: 0x10000}[length]),
                             length, endianness=endianness)

    # Precalculated, see the Wikipedia links below.
    _EXPN_BIAS = {16: 16, 32: 127, 64: 1023}
    _N_EXPN_BITS = {16: 5, 32: 8, 64: 11}
    _N_FRAC_BITS = {16: 10, 32: 23, 64: 52}
    _FLOAT_NAME = {16: "float16", 32: "float", 64: "double"}

    def read_float_value(self, length, endianness=">"):
        """
        Reads a floating point number of *length*, which must
        be 16 (float16), 32 (float) or 64 (double).

        .. seealso:

           :meth:`write_float_value`
              The writing equivalent of this method.

           `Wikipedia: IEEE floating-point standard
           <http://en.wikipedia.org/wiki/IEEE_floating-point_standard>`_
              A good overview article of the IEEE floating-point standard, from Wikipedia.
        
        .. warning: Flash's float16 exponent bias is 16, not 15.

        :param length: either 16, 32, or 64
        :type length:  an integer
        """

        if length not in self._FLOAT_NAME:
            raise ValueError("length is not 16, 32 or 64.")

        bits = self.read_bits(length, endianness=endianness)
        
        sign = bits.read_bit()
        
        expn_len = self._N_EXPN_BITS[length]
        frac_len = self._N_FRAC_BITS[length]
        
        expn = bits.read_int_value(expn_len)
        frac = bits.read_int_value(frac_len)

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

           `Wikipedia: IEEE floating-point standard
           <http://en.wikipedia.org/wiki/IEEE_floating-point_standard>`_
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

        bits = BitStream()
            
        if isnan(value):
            self.one_fill(length)
            return
        elif value == float("-inf"): # negative infinity
            bits.one_fill(BitStream._N_EXPN_BITS[length] + 1) # sign merged
            bits.zero_fill(BitStream._N_FRAC_BITS[length])
        elif value == float("inf"): # positive infinity
            bits.write_bit(False)
            bits.one_fill(BitStream._N_EXPN_BITS[length])
            bits.zero_fill(BitStream._N_FRAC_BITS[length])
        else:
            if value < 0:
                bits.write_bit(True)
                value = ~value + 1
            else:
                bits.write_bit(False)
                
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
                raise ValueError("Exponent out of range in %s [%d]." %
                                 (BitStream._FLOAT_NAME[length], length))

            frac_total = 1 << BitStream._N_FRAC_BITS[length]
            bits.write_int_value(exp, BitStream._N_EXPN_BITS[length])
            bits.write_int_value(int((value-1)*frac_total) & (frac_total - 1),
                                 BitStream._N_FRAC_BITS[length])
    
    def read_u32(self):
        """
        Read a U32, as defined in the ABC file format document.
        
        :raises ValueError: after 5 bytes read all with the high bit set
        """
        n = 0
        i = 0
        cont = True
        while cont:
            cont = self.read_bit()
            if i == 5:
                raise ValueError("u32 parsed beyond bounds")
            n |= self.read_int_value(7) << 7*i
            i += 1
        print
        return n

    def _fill(self, amount, value):
        n = self.bits_available()
        if amount > n:
            self.bits[self.cursor:] = [value] * n
            self.bits += [value] * (amount - n)
        else:
            self.bits[self.cursor:self.cursor+amount] = [value] * amount
        self.cursor += amount
        
    def one_fill(self, amount):
        """
        Fills amount bits with one. The equivalent of calling
        self.write_bit(True) amount times, but more efficient.
        """
        self._fill(amount, True)
        
    def zero_fill(self, amount):
        """
        Fills amount bits with zero. The equivalent of calling
        self.write_bit(False) amount times, but more efficient.
        """
        self._fill(amount, False)
    
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
        self.cursor = 0
        
    def skip_to_end(self):
        """
        Seek to the end of the stream.
        """
        self.cursor = len(self.bits)

    @property
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
        if len(self.bits) % 8:
            self.zero_fill(8 - (len(self.bits) % 8))

    def skip_flush(self):
        if self.cursor % 8:
            self.cursor += 8 - self.cursor % 8

    def __iter__(self):
        return iter(self.bits)

    def __eq__(self, other):
        return self.bits == list(other)

    def __ne__(self, other):
        return self.bits != list(other)
    
    def __len__(self):
        return len(self.bits)

    def __getitem__(self, i):
        return self.bits[i]

    def __setitem__(self, i, v):
        while len(bits) < i:
            self.bits.append(False)
        self.bits[i] = bool(v)
    
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

    def decompress(self):
        """
        Decompress and replace the contents of
        this BitStream from cursor on outward.
        """
        cursor = self.cursor
        bytes = zlib.decompress(self.read_string())
        self.cursor = cursor
        self.write_string(bytes)
        self.cursor = cursor
    
    def serialize(self, align=ALIGN_LEFT):
        """
        Serialize bit array into a byte string, aligning either
        on the right (ALIGN_RIGHT) or left (ALIGN_LEFT).
        """
        lst = self.bits[:]
        numbytes, leftover = divmod(len(lst), 8)
        if leftover > 0:
            if align == ALIGN_RIGHT:
                # Insert some False values to pad the list
                # so it is aligned to the right.
                lst[:0] = [False] * (8-leftover)
            else:
                lst += [False] * (8-leftover)
            numbytes += 1
        return BitStream(lst).read_string(numbytes)

class BitStreamParseMixin(object):
    @classmethod
    def parse_bitstream(cls, bitstream):
        raise NotImplementedError
    
    @classmethod
    def parse_bytestring(cls, bytes):
        bits = BitStream()
        bits.write_string(bytes)
        bits.rewind()
        return cls.parse_bitstream(bits)

    @classmethod
    def parse_file(cls, file):
        return cls.parse_bytestring(file.read())

    @classmethod
    def parse_filename(cls, filename):
        return cls.parse_file(open(filename))
