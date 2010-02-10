
from collections import namedtuple

from math import log, floor, ceil, isnan

from mech.fusion.bitstream.interfaces import IFormat

from zope.interface import implements
from zope.component import provideAdapter

# Fast lookup for write/read_string.
# This seems really stupid, but I need it for SPEEEEED.

def lookup():
    b1 = {}
    b2 = {}
    b3 = {}
    b4 = {}
    for i in xrange(256):
        tup = tuple(bool(i & (1 << j)) for j in reversed(xrange(8)))
        b1[i] = tup
        b2[tup] = i
        b3[i-128] = tup
        b4[tup] = i-128
    return b1, b2, b3, b4

BYTE_TO_BITS, BITS_TO_BYTE, SIGNED_BYTE_TO_BITS, BITS_TO_SIGNED_BYTE = lookup()
del lookup

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

# New API for the BitStream, suggested by Jon Morton.

def requires_length(can_be=None, cant_be=None):
    def requires_length(fn):
        def requires_length(self, *args, **kwargs):
            if can_be is not None and self.length not in can_be:
                raise ValueError("Format %r requires a length in the set of "
                                 "%s" % (type(self).__name__, can_be,))
            if cant_be is not None and self.length in cant_be:
                raise ValueError("Format %r cannot have a length in the set "
                                 "of %s" % (type(self).__name__, cant_be,))
            return fn(self, *args, **kwargs)
        return requires_length
    return requires_length

def no_endianness(fn):
    def no_endianness(self, *args, **kwargs):
        if self.endianness is not None:
            raise ValueError("Format %r does cannot"
                             " have endianness." % (type(self).__name__,))
        return fn(self, *args, **kwargs)
    return fn

FormatData = namedtuple("FormatData", "length endianness repr")

class _FormatMeta(type):
    """
    The metaclass used to implement formats.
    """
    def __getitem__(self, item):
        if item is None:
            return self.specialize(FormatData(None, None, None))
        elif isinstance(item, slice):
            # assert isinstance(item.start, (int, long)) or item.start is None
            # assert isinstance(item.stop , basestring)
            return self.specialize(FormatData(item.start, item.stop, item.step))
        elif isinstance(item, (int, long)):
            return self.specialize(FormatData(item, None, None))
        elif item in "<>":
            return self.specialize(FormatData(None, item, None))
        raise ValueError("Format argument must either be an int (length), "
                         "or < or > (endianness), or a slice of "
                         "length:endianness.")
    
    def __str__(self):
        return self.__name__

class _FormatMetaAdaptor(object):
    
    implements(IFormat)
    adapts(_FormatMeta)
    
    def __init__(self, format):
        self.format = format
    
    def _read(self, bs, cursor):
        return self.format(FormatData(
            None, None, None))._read(bs, cursor)
    
    def _write(self, bs, cursor, argument):
        return self.format(FormatData(
            None, None, None))._write(bs, cursor, argument)

provideAdapter(_FormatMetaAdaptor)

class _Format(object):
    """
    A single "field" in a BitStream.
    """
    __metaclass__ = _FormatMeta
    implements(IFormat)

    @classmethod
    def specialize(cls, data):
        return cls(data)
    
    def __init__(self, data=None):
        if data:
            self.length     = data.length
            self.endianness = data.endianness
            self.repr       = data.repr
    
    def __getitem__(self, item):
        assert isinstance(item, (int, long))
        return _FormatArray(self, item)

    def __str__(self):
        if self.repr:
            return self.repr
        return "%s[%d]" % (type(self).__name__, self.length)

    def _read(self, bitstream, cursor):
        raise NotImplementedError

    def _write(self, bitstream, cursor, argument):
        raise NotImplementedError

    def _pre_read(self, struct):
        if hasattr(self.length, "_pre_read"):
            self.length._pre_read(struct, self)

    def _pre_write(self, struct):
        if hasattr(self.length, "_pre_write"):
            self.length._pre_write(struct, self)

    def _evaluate_read(self, struct):
        length = None
        if hasattr(self.length, "_evaluate"):
            length = self.length._evaluate(struct, self)
        elif hasattr(self.length, "_evaluate_read"):
            length = self.length._evaluate_read(struct, self)
        if length is None:
            return self
        else:
            return type(self)(length=length, endianness=self.endianness)

    def _evaluate_write(self, struct):
        length = None
        if hasattr(self.length, "_evaluate"):
            length = self.length._evaluate(struct, self)
        elif hasattr(self.length, "_evaluate_write"):
            length = self.length._evaluate_write(struct, self)
        if length is None:
            return self
        else:
            return type(self)(length=length, endianness=self.endianness)

class _FormatArray(object):
    def __init__(self, format, repeat):
        self.format = format
        self.repeat = repeat

    def _read(self, bs, cursor):
        for i in xrange(self.repeat):
            yield bs.read(self.format)

    def _write(self, bs, cursor, argument):
        if len(argument) != self.repeat:
            raise ValueError("This %s array is of length %d, you tried to wri"
                             "te an %s" % (self.format, self.repeat, argument))
        for i in argument:
            bs.write(i, self.format)

    def __str__(self):
        return "%s[%d]" % (self.format, self.repeat)
    
class Bit(_Format):
    """
    One bit, either True or False.
    """
    @requires_length(can_be=(1, None))
    @no_endianness
    def _read(self, bs, cursor):
        """
        Reads a bit from the bit stream and returns it as either True or False.
        
        :rtype: bool
        :raises IndexError: when reading past the end of the stream.
        """
        return bs[cursor], 1
    
    @requires_length(can_be=(1, None))
    @no_endianness
    def _write(self, bs, cursor, bit):
        bs[cursor] = bool(bit)
        return 1

class BitsList(_Format):
    @no_endianness
    def _read(self, bs, cursor):
        length = self.length
        if length is None:
             length = len(bs)
        data = bs[cursor:cursor+length]
        return data, length
    
    @no_endianness
    def _write(self, bs, cursor, argument):
        lenL = len(argument)
        assert lenL == self.length or self.length is None
        bs[cursor:cursor+lenL] = argument
        return lenL

class _BoolFormat(_Format):
    VALUE = None
    @no_endianness
    def _read(self, bs, cursor):
        length = self.length or 1
        return None, length
    
    @no_endianness
    def _write(self, bs, cursor, argument):
        length = self.length or 1
        bs[cursor:cursor+length] = [self.VALUE]*length
        return length

class Zero(_BoolFormat):
    VALUE = False

class One(_BoolFormat):
    VALUE = True

class Byte(_Format):
    """
    A byte/bytestring.
    """
    string = False
    signed = False
    def _read(self, bs, cursor):
        lookup = BITS_TO_BYTE
        if self.signed:
            lookup = BITS_TO_SIGNED_BYTE
        
        length = self.length
        if (length in (None, 1) and not self.string) or length == 1:
            if bs.bits_available < 8:
                raise ValueError("%s read beyond boundaries" % (bs,))
            byte = lookup[tuple(bs.read(BitsList[8]))]
            if self.string:
                return chr(byte)
            if length == 1:
                return [byte]
            return byte
        elif length is None:
            if bs.bits_available() & 7:
                raise ValueError("You cannot read the rest of the BitStream "
                                 "as a ByteString. The length of the "
                                 "available bits is not divisible by 8.")
            length = bs.bits_available() // 8
        
        R = (lookup[tuple(bs.read(BitsList[8]))] for i in xrange(length))

        try:
            if self.string:
                bytes = ''.join(chr(a) for a in R)
            else:
                bytes = list(R)
        except KeyError:
            raise ValueError("%s read beyond boundaries" % (bs,))
        
        if self.endianness == "<":
            return bytes[::-1]
        
        return bytes

    def _write(self, bs, cursor, bytes):
        lookup = BYTE_TO_BITS
        if self.signed:
            lookup = SIGNED_BYTE_TO_BITS
        
        if isinstance(bytes, (int, long)):
            if bytes < 256 and self.length in (1, None):
                bs[cursor:cursor+8] = lookup[bytes]
                return 8
            Len = int(ceil(nbits(bytes) / 8.))
            L = Len - self.length
            if L > 0:
                bs.write(Zero[8*L])
            elif L < 0:
                raise ValueError("%r does not fit in %d bytes"
                                 ""% (bytes, self.length))
            
            R = xrange(0, Len*8, 8)
            if self.endianness == "<":
                R = reversed(R)
            for i in R:
                bs.write(lookup[(bytes & (0xFF << i)) >> i])
        elif isinstance(bytes, str):
            if self.length is not None:
                L = len(bytes) - self.length
                if L > 0:
                    bs.write(Zero[8*L])
                elif L < 0:
                    raise ValueError("%r does not fit in %d bytes"
                                     "" % (bytes, self.length))
            
            if self.endianness == "<":
                bytes = reversed(bytes)
            for i in bytes:
                if isinstance(i, str):
                    i = ord(i)
                bs.write(BYTE_TO_BITS[i], BitsList)
        else:
            raise TypeError("Invalid type for Byte/ByteString")

class ByteString(Byte):
    string = True

class SignedByte(Byte):
    signed = True

class CString(_Format):
    """
    A string ended with a NUL, like a c-string.
    """
    @no_endianness
    @requires_length(can_be=(None,))
    def _read(self, bs, cursor):
        bytes = [0xDEADBEEF]
        while bytes[-1] != 0:
            bytes.append(bs.read(Byte))
        return ''.join(chr(i) for i in bytes[1:-1])
    
    @requires_length(can_be=(None,))
    def _write(self, bs, cursor, argument):
        bs.write(argument, ByteString)
        bs.write(0, Byte)

class UTF8(_Format):
    """
    A UTF8 string.
    """
    @requires_length(cant_be=(None,))
    def _read(self, bs, cursor):
        return bs.read(ByteString[self.length]).decode("utf8")

    @requires_length(cant_be=(None,))
    def _write(self, bs, cursor, argument):
        bs.write(argument.encode("utf8"), ByteString[self.length])

class CUTF8(_Format):
    """
    A UTF8 string ended with a NUL, like a CString.
    """
    @requires_length(can_be=(None,))
    def _read(self, bs, cursor):
        return bs.read(CString).decode("utf8")

    @requires_length(can_be=(None,))
    def _write(self, bs, cursor, argument):
        bs.write(argument.encode("utf8"), CString)
    
class UB(_Format):
    """
    Unsigned Bits, most significant bit first.

    .. seealso:
    
    When writing, if length is None, the log base 2 of the value is
    taken.
    
    >>> bits = BitStream()
    >>> bits.write_int_value(7, length=10)
    >>> str(bits)
    "00000111"
    >>> bits.rewind()
    >>> bits.write(0xDDEEFF, Byte[3:"<"])
    >>> bits.rewind()
    >>> bits.read(ByteString[3:">"]) == "\xFF\xEE\xDD"
    True
    
    .. seealso

        `Wikipedia: Two's complement
         <http://en.wikipedia.org/wiki/Two%27s_complement>`_
            Has information on the two's complement number system.
    
        `SWF specification v10 <http://www.adobe.com/devnet/swf/>`_
           Has information on UB, page 16
    
    """
    @requires_length(cant_be=(None,))
    def _read(self, bs, cursor):
        length = self.length
        if length == 1:
            return bs[cursor], 1
        elif length & 7 == 0:
            bytes, n = bs.read(Byte[length//8]), 0
            R = xrange(len(bytes))
            if self.endianness != "<":
                R = reversed(R)
            for i, b in zip(R, bytes):
                n |= b << 8*i
            return n
        
        n = 0
        
        R = reversed(xrange(length))
        if self.endianness == "<":
            R = ((length // 8 - i // 8 - 1)*8 + i%8 for i in R)
        
        for i, j in enumerate(R):
            n |= bs[cursor+i] << j
        return n, length
    
    def _write(self, bs, cursor, argument):
        length = self.length
        nb = nbits(argument)
        if length is None:
            length = nbits(argument)
        elif length < nb:
            raise ValueError(("length of %d is not large "
                              "enough to store %d") % (length, argument))
        elif length == 1:
            bs[cursor] = bool(argument)
            return 1
        elif length & 7 == 0:
            return bs.write(argument, Byte[length//8])
        
        R = reversed(xrange(length))
        if self.endianness == "<":
            R = ((length // 8 - i // 8 - 1)*8 + i%8 for i in R)
        
        for i, j in enumerate(R):
            bs[cursor+i] = bool(argument & (1 << j))
        return length
    
    def _nbits(self, argument):
        return nbits(argument)

class SB(_Format):
    """
    Signed Bits.

    When writing, if length is None, the log base 2
    of the value is taken.

    .. seealso:
    
        `SWF specification v10 <http://www.adobe.com/devnet/swf/>`_
           Has information on SB, page 16
    
    """
    @requires_length(cant_be=(None,))
    def _read(self, bs, cursor):
        signed = bs.read(Bit)
        n = bs.read(UB[self.length-1])
        if signed:
            return -n
        return n
    
    def _write(self, bs, cursor, argument):
        length = self.length
        if length is not None:
            length -= 1
        bs.write(argument < 0,  Bit)
        bs.write(abs(argument), UB[length])

    def _nbits(self, argument):
        return nbits_signed(argument)

class FB(_Format):
    """
    Fixed Bits.

    When writing, if length is None, the log base 2
    of the value is taken.
    
    .. seealso:
    
        `SWF specification v10 <http://www.adobe.com/devnet/swf/>`_
           Has information on FB, page 16.
    """
    @requires_length(cant_be=(None,))
    def _read(self, bs, cursor):
        return bs.read(SB) / float(0x10000)
    
    def _write(self, bs, cursor, value):
        bs.write(value / float(0x10000), SB)
    
class U32(_Format):
    """
    A U32/EncodedU32, as defined in the ABC file format specification.
    
    .. seealso:
    
       `ABC file format specification
       <http://www.adobe.com/devnet/actionscript/articles/avm2overview.pdf>`_
          Has information on U32.
    """
    @requires_length(can_be=(None,))
    @no_endianness
    def _read(self, bs, cursor):
        n = 0
        i = 0
        cont = True
        while cont:
            cont = bs.read(Bit)
            if i == 5:
                raise ValueError("U32 parsed beyond bounds")
            n |= bs.read(UB[7]) << 7*i
            i += 1
        return n

    @requires_length(can_be=(None,))
    @no_endianness
    def _write(self, bs, cursor, n):
        while n > 0:
            bs.write((n >> 7) > 0,     Bit)
            bs.write((n & 0b01111111), UB[7])
            n >>= 7

class FixedFormat(_Format):
    """
    A fixed point number.
    
    If length is 16, an 8.8 format is used.
    If length is 32, a 16.16 format is used.
    
    .. seealso:
    
        `SWF specification v10 <http://www.adobe.com/devnet/swf/>`_
           Has information on fixed-point values.
    """
    @requires_length(can_be=(16, 32))
    def _read(self, bs, cursor):
        return bs.read(Byte[self.length:self.endianness]) / \
            float({8: 0x100, 16: 0x10000}[self.length])

    @requires_length(can_be=(16, 32))
    def _write(self, bs, cursor, value):
         bs.write(value * float({8: 0x100, 16: 0x10000}[self.length]),
                  Byte[self.length:self.endianness])

class FloatFormat(_Format):
    """
    A IEEE floating-point number.

    .. seealso:

        `Wikipedia: IEEE floating-point standard
        <http://en.wikipedia.org/wiki/IEEE_floating-point_standard>`_
           A good overview article of the IEEE floating-point standard, from Wikipedia.

    .. warning: Flash's FLOAT16 exponent bias is 16, not 15.
    """
    # Precalculated, see the Wikipedia links below.
    _EXPN_BIAS = {16: 16, 32: 127, 64: 1023}
    _N_EXPN_BITS = {16: 5, 32: 8, 64: 11}
    _N_FRAC_BITS = {16: 10, 32: 23, 64: 52}
    
    @requires_length(can_be=(16, 32, 64))
    def _read(self, bs, cursor):
        sign = bs.read(Bit)
        
        expn_len = self._N_EXPN_BITS[self.length]
        frac_len = self._N_FRAC_BITS[self.length]
        
        expn = bs.read(UB[expn_len])
        frac = bs.read(UB[frac_len])
        
        bias = expn - self._EXPN_BIAS[self.length]
        
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

    @requires_length(can_be=(16, 32, 64))
    def _write(self, bs, cursor, value):
        if value in (0, 0.0): # value is zero
            bs.write(Zero[self.length])
        elif value == -0.0:
            bs.write(One)
            bs.write(Zero[self.length-1])
        
        if isnan(value):
            bs.write(One [self.length])
        elif value == float("-inf"): # negative infinity
            bs.write(One [self._N_EXPN_BITS[self.length] + 1]) # sign merged
            bs.write(Zero[self._N_FRAC_BITS[self.length]])
        elif value == float("inf"): # positive infinity
            bs.write(Zero)
            bs.write(One [self._N_EXPN_BITS[self.length]])
            bs.write(Zero[self._N_FRAC_BITS[self.length]])
        else:
            if value < 0:
                bs.write(One)
                value = ~value + 1
            else:
                bs.write(Zero)
            
            exp = self._EXPN_BIAS[self.length]
            if value < 1:
                while int(value) != 1:
                    value *= 2
                    exp -= 1
            else:
                while int(value) != 1:
                    value /= 2
                    exp += 1
            
            if exp < 0 or exp > (1 << self._N_EXPN_BITS[self.length]):
                raise ValueError("Exponent out of range in %s." % (self,))
            
            frac_total = 1 << self._N_FRAC_BITS[self.length]
            bs.write(exp, UB[self._N_EXPN_BITS[self.length]])
            bs.write(int((value-1)*frac_total) & (frac_total - 1),
                     UB[self._N_FRAC_BITS[self.length]])

def bool_adaptor(bit):
    if bit:
        return One
    return Zero

def list_adaptor(bits):
    from mech.fusion.bitstream.bitstream import BitStream
    return IFormat(BitStream(bits))

provideAdapter(bool_adaptor, [bool], IFormat)
provideAdapter(list_adaptor, [list], IFormat)
provideAdapter(list_adaptor, [tuple], IFormat)
