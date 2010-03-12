\
from collections import namedtuple

from math import log, floor, ceil, isnan

from mech.fusion.bitstream.interfaces import IBitStream
from mech.fusion.bitstream.interfaces import IFormat
from mech.fusion.bitstream.interfaces import IFormatData, IFormatLength
from mech.fusion.bitstream.interfaces import IStructEvaluateable

from types import NoneType

from zope.interface import implements, classImplements
from zope.component import provideAdapter, adapter

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

def nbits_fixed(num, *args):
    """
    Returns the number of bits in the max of all the arguments,
    assuming FBits.
    """
    if all(a == 0 for a in (num,)+args):
        return 0
    return nbits_signed(*(int(a*float(0x10000)) for a in (num,) + args))

def nbits_signed(num, *args):
    """
    Returns nbits + 1, for the sign bit. Please use this
    instead of adding one manually.
    """
    if all(a == 0 for a in (num,)+args):
        return 0
    return nbits(num, *args) + 1

def nbits(num, *args):
    """
    Returns the number of bits in the max of all the arguments.
    """
    # according to StackOverflow, using the string
    # length is faster than everything else
    if all(a == 0 for a in (num,)+args):
        return 0
    return max(len(bin(abs(a))) for a in (num,) + args)  - 2

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

classImplements(FormatData, IFormatData)

classImplements(int,  IFormatLength)
classImplements(long, IFormatLength)

class FormatMeta(type):
    """
    The metaclass used to implement formats.
    """
    def __getitem__(self, item):
        return self.specialize(IFormatData(item))
    
    def __str__(self):
        return self.__name__

def none_as_formatdata(none):
    return FormatData(None, None, None)

def slice_as_formatdata(slice):
    return FormatData(slice.start, slice.stop, slice.step)

def length_as_formatdata(length):
    return FormatData(IFormatLength(length), None, None)

def string_as_formatdata(string):
    if string in "<>":
        return FormatData(None, string, None)
    raise TypeError("cannot adapt string %r to IFormatData" % (string,))

provideAdapter(none_as_formatdata,   [NoneType],      IFormatData)
provideAdapter(slice_as_formatdata,  [slice],         IFormatData)
provideAdapter(length_as_formatdata, [IFormatLength], IFormatData)
provideAdapter(string_as_formatdata, [str],           IFormatData)

@adapter(FormatMeta)
class FormatMetaAdaptor(object):
    
    implements(IFormat, IStructEvaluateable)
    
    def __init__(self, format):
        self.format = format
    
    def _read(self, bs, cursor):
        return self.format(None)._read(bs, cursor)
    
    def _write(self, bs, cursor, argument):
        return self.format(None)._write(bs, cursor, argument)

    def _pre_read(self, struct):
        pass

    def _pre_write(self, struct, field):
        pass

    def _evaluate(self, struct):
        return self

provideAdapter(FormatMetaAdaptor, None, IFormat)

class Format(object):
    """
    A single "field" in a BitStream.
    """
    __metaclass__ = FormatMeta
    implements(IFormat, IStructEvaluateable)

    @classmethod
    def specialize(cls, data):
        return cls(data)
    
    def __init__(self, data=None):
        data = IFormatData(data)
        self.length     = data.length
        self.endianness = data.endianness
        self.repr       = data.repr
    
    def __getitem__(self, item):
        assert isinstance(item, (int, long))
        return FormatArray(self, item)

    def __str__(self):
        if self.repr:
            return self.repr
        return "%s[%s]" % (type(self).__name__, self.length)

    def _read(self, bitstream, cursor):
        raise NotImplementedError

    def _write(self, bitstream, cursor, argument):
        raise NotImplementedError

    def _pre_write(self, struct, field):
        if getattr(self.length, "_pre_write_inner", None):
            self.length._pre_write_inner(struct, self, field)

    def _evaluate(self, struct):
        return type(self).specialize(FormatData(
            IStructEvaluateable(self.length)._evaluate(struct),
            IStructEvaluateable(self.endianness)._evaluate(struct),
            self.repr))

class FormatArray(object):
    
    implements(IFormat, IStructEvaluateable)
    
    def __init__(self, format, repeat):
        self.format = IFormat(format)
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

    def _pre_write(self, struct, field):
        self.format._pre_write(struct, field)

    def _evaluate(self, struct):
        return type(self)(self.format._evaluate(struct), self.repeat)
    
    def __str__(self):
        return "%s[%s]" % (self.format, self.repeat)
    
class Bit(Format):
    
    """
    One bit, either True or False.
    """
    @requires_length(can_be=(1, None))
    @no_endianness
    def _read(self, bs, cursor):
        return bs[cursor], 1
    
    @requires_length(can_be=(1, None))
    @no_endianness
    def _write(self, bs, cursor, bit):
        bs[cursor] = bool(bit)
        return 1

class BitsList(Format):
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

class BoolFormat(Format):
    VALUE = None
    @no_endianness
    def _read(self, bs, cursor):
        length = 1 if self.length is None else self.length
        return None, length
    
    @no_endianness
    def _write(self, bs, cursor, argument):
        length = 1 if self.length is None else self.length
        bs[cursor:cursor+length] = [self.VALUE]*length
        return length

class Zero(BoolFormat):
    VALUE = False

class One(BoolFormat):
    VALUE = True

class Ignore(Format):
    @no_endianness
    def _read(self, bs, cursor):
        return None, self.length

    def _write(self, bs, cursor, argument):
        return self.length

class Byte(Format):
    """
    A byte/bytestring.
    """
    string = False
    list   = False
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
            if self.list:
                return [byte]
            return byte
        elif length is None:
            if bs.bits_available & 7:
                raise ValueError("You cannot read the rest of the BitStream "
                                 "as a ByteString. The length of the "
                                 "available bits is not divisible by 8.")
            length = bs.bits_available // 8

        R = [tuple(bs.read(BitsList[8])) for i in xrange(length)]
        
        try:
            if self.string:
                bytes = ''.join(chr(lookup[a]) for a in R)
            else:
                bytes = [lookup[a] for a in R]
        except KeyError:
            raise ValueError("%s read beyond boundaries" % (bs,))
        
        if self.endianness == "<":
            bytes = bytes[::-1]

        if self.string or self.list:
            return bytes
        else:
            n = 0
            for i, b in zip(reversed(xrange(0, len(bytes)*8, 8)), bytes):
                n |= b << i
            return n

    def _write(self, bs, cursor, bytes):
        if isinstance(bytes, (int, long)):
            if bytes < 256 and self.length in (1, None):
                bs[cursor:cursor+8] = BYTE_TO_BITS[bytes]
                return 8
            Len = int(ceil(nbits(bytes)/8.)) * 8
            L = self.length*8 - Len
            if L > 0 and self.endianness != "<":
                if self.signed and bytes < 0:
                    bs.write(One[L])
                else:
                    bs.write(Zero[L])
            elif L < 0:
                raise ValueError("%r does not fit in %d bytes"
                                 ""% (bytes, self.length))
            
            R = xrange(0, Len, 8)
            if self.endianness != "<":
                R = reversed(R)
            for i in R:
                bs.write(BYTE_TO_BITS[(bytes & (0xFF << i)) >> i])
            if self.endianness == "<":
                if self.signed and bytes < 0:
                    bs.write(One[L])
                else:
                    bs.write(Zero[L])
        elif isinstance(bytes, str):
            if self.length is not None:
                L = len(bytes) - self.length
                if L > 0 and self.endianness != "<":
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
            if self.endianness == "<":
                bs.write(Zero[8*L])
        else:
            raise TypeError("Invalid type for Byte/ByteString")

class ByteString(Byte):
    string = True

class ByteList(Byte):
    list = True

class SignedByte(Byte):
    signed = True

class SignedByteList(ByteList, SignedByte):
    pass

class CString(Format):
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
        bs.write(Zero[8])

class UTF8(Format):
    """
    A UTF8 string.
    """
    @requires_length(cant_be=(None,))
    def _read(self, bs, cursor):
        return bs.read(ByteString[self.length]).decode("utf8")

    @requires_length(cant_be=(None,))
    def _write(self, bs, cursor, argument):
        bs.write(argument.encode("utf8"), ByteString[self.length])

class CUTF8(Format):
    """
    A UTF8 string ended with a NUL, like a CString.
    """
    @requires_length(can_be=(None,))
    def _read(self, bs, cursor):
        return bs.read(CString).decode("utf8")

    @requires_length(can_be=(None,))
    def _write(self, bs, cursor, argument):
        bs.write(argument.encode("utf8"), CString)
    
class UB(Format):
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
        if length == 0:
            return 0
        elif length == 1:
            return bs[cursor], 1
        elif length & 7 == 0:
            bytes, n = bs.read(ByteList[length//8]), 0
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
        elif length == 0:
            return 0
        elif length < nb:
            raise ValueError(("length of %d is not large "
                              "enough to store %d") % (length, argument))
        elif length == 1:
            bs[cursor] = bool(argument)
            return 1
        elif length & 7 == 0:
            return bs.write(argument, Byte[length//8:self.endianness])
        
        R = reversed(xrange(length))
        if self.endianness == "<":
            R = ((length // 8 - i // 8 - 1)*8 + i%8 for i in R)
        
        for i, j in enumerate(R):
            bs[cursor+i] = bool(argument & (1 << j))
        return length

    @staticmethod
    def _nbits(*args):
        return nbits(*args)

class SB(Format):
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
        if self.length == 0:
            return 0
        signed = bs.read(Bit)
        n = bs.read(UB[self.length-1])
        if signed:
            return -n
        return n
    
    def _write(self, bs, cursor, argument):
        length = self.length
        if length == 0:
            return 0
        elif length is not None:
            length -= 1
        bs.write(argument < 0,  Bit)
        bs.write(abs(argument), UB[length])

    @staticmethod
    def _nbits(*args):
        return nbits_signed(*args)

class FB(Format):
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
        return bs.read(SB[self.length]) / float(0x10000)
    
    def _write(self, bs, cursor, value):
        if self.length == 0:
            return 0
        bs.write(int(value * float(0x10000)), SB[self.length])

    def _nbits(self, *args):
        return nbits_fixed(*args)
    
class U32(Format):
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

class FixedFormat(Format):
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
        return bs.read(Byte[self.length//8:self.endianness]) / \
            float({16: 0x100, 32: 0x10000}[self.length])
    
    @requires_length(can_be=(16, 32))
    def _write(self, bs, cursor, value):
         bs.write(value * float({16: 0x100, 32: 0x10000}[self.length]),
                  SB[self.length:self.endianness])

class FloatFormat(Format):
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
        from mech.fusion.bitstream.bitstream import BitStream
        bits = bs.read(BitStream[self.length:self.endianness])
        sign = bits.read(Bit)
        
        expn_len = self._N_EXPN_BITS[self.length]
        frac_len = self._N_FRAC_BITS[self.length]
        
        expn = bits.read(UB[expn_len])
        frac = bits.read(UB[frac_len])
        
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
        from mech.fusion.bitstream.bitstream import BitStream
        bits = BitStream()
        if value in (0, 0.0): # value is zero
            bits.write(Zero[self.length])
        elif value == -0.0:
            bits.write(One)
            bits.write(Zero[self.length-1])
        elif isnan(value):
            bits.write(One [self.length])
        elif value == float("-inf"): # negative infinity
            bits.write(One [self._N_EXPN_BITS[self.length] + 1]) # sign merged
            bits.write(Zero[self._N_FRAC_BITS[self.length]])
        elif value == float("inf"): # positive infinity
            bits.write(Zero)
            bits.write(One [self._N_EXPN_BITS[self.length]])
            bits.write(Zero[self._N_FRAC_BITS[self.length]])
        else:
            if value < 0:
                bits.write(One)
                value = ~value + 1
            else:
                bits.write(Zero)
            
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
            bits.write(exp, UB[self._N_EXPN_BITS[self.length]])
            bits.write(int((value-1)*frac_total) & (frac_total - 1),
                     UB[self._N_FRAC_BITS[self.length]])
        bs.write(bits, BitStream[self.endianness])

def bool_to_iformat(bit):
    if bit:
        return IFormat(One)
    return IFormat(Zero)

def generic_to_iformat(obj):
    return IFormat(IBitStream(obj))

provideAdapter(bool_to_iformat,    [bool],  IFormat)
provideAdapter(generic_to_iformat, [list],  IFormat)
provideAdapter(generic_to_iformat, [tuple], IFormat)
