
from itertools import izip, izip_longest
from math import ceil, isnan

from fusion.bitstream.interfaces import IFormat, IBitStream
from fusion.bitstream.interfaces import IFormatData, IFormatLength
from fusion.bitstream.interfaces import IStructEvaluateable
from fusion.util import nbits, nbits_signed, nbits_fixed

from types import NoneType

from zope.interface import implements, classImplements, implementer
from zope.component import provideAdapter, adapter

FAST = True

if FAST:
    def requires_length(can_be=0, cant_be=0):
        def i(fn):
            return fn
        return i

    def no_endianness(fn):
        return fn
else:
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

class FormatData(object):
    implements(IFormatData)
    def __init__(self, length, endianness, repr):
        self.length = length
        self.endianness = endianness
        self.repr = repr

classImplements(int,  IFormatLength)
classImplements(long, IFormatLength)

class FormatMeta(type):
    """
    The metaclass used to implement formats.
    """
    def __init__(self, name, bases, dct):
        self._cache = {}

    def __getitem__(self, item):
        return self.specialize(IFormatData(item))

    def __str__(self):
        return "<FormatMeta '%s'>" % (self.__name__,)

@adapter(NoneType)
@implementer(IFormatData)
def none_as_formatdata(none):
    return FormatData(None, None, None)

provideAdapter(none_as_formatdata)

@adapter(slice)
@implementer(IFormatData)
def slice_as_formatdata(slice):
    return FormatData(slice.start, slice.stop, slice.step)

provideAdapter(slice_as_formatdata)

@adapter(IFormatLength)
@implementer(IFormatData)
def length_as_formatdata(length):
    return FormatData(length, None, None)

provideAdapter(length_as_formatdata)

@adapter(str)
@implementer(IFormatData)
def string_as_formatdata(string):
    if string in "<>":
        return FormatData(None, string, None)
    raise TypeError("cannot adapt string %r to IFormatData" % (string,))

provideAdapter(string_as_formatdata)

class FormatMetaAdaptor(object):

    implements(IFormat, IStructEvaluateable)

    def __init__(self, format):
        self.format = format

    def _read(self, bs, cursor):
        return self.format(FormatData(None, None, None))._read(bs, cursor)

    def _write(self, bs, cursor, argument):
        return self.format(FormatData(None, None, None))._write(bs, cursor, argument)

    def _pre_read(self, struct):
        pass

    def _pre_write(self, struct, field):
        pass

    def _evaluate(self, struct):
        return self

provideAdapter(FormatMetaAdaptor, [FormatMeta], IFormat)

class Format(object):
    """
    A single "field" in a BitStream.
    """
    __metaclass__ = FormatMeta
    implements(IFormat, IStructEvaluateable)

    cached = False

    @classmethod
    def specialize(cls, data):
        ## D = cls._cache
        ## if data in D:
        ##     return D[data]
        obj = cls(data)
        ## D[data] = obj
        return obj

    def __init__(self, data=None):
        data = IFormatData(data)
        self.length     = data.length
        self.endianness = data.endianness
        self.repr       = data.repr

    def __getitem__(self, item):
        assert isinstance(item, (int, long))
        return FormatArray(self, item)

    def __repr__(self):
        if self.repr:
            return self.repr
        return "%s[%s]" % (type(self).__name__, self.length)

    def _read(self, bitstream, cursor):
        raise NotImplementedError

    def _write(self, bitstream, cursor, argument):
        raise NotImplementedError

    def _pre_write(self, struct, field):
        m = getattr(self.length, "_pre_write_inner", None)
        if m:
            m(struct, self, field)

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
        results = []
        for i in xrange(self.repeat):
            results.append(bs.read(self.format))
        return results

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
        return bs.read_bit()

    @requires_length(can_be=(1, None))
    @no_endianness
    def _write(self, bs, cursor, bit):
        bs.write_bit(bit)

class BoolFormat(Format):
    VALUE = None
    @no_endianness
    def _read(self, bs, cursor):
        length = 1 if self.length is None else self.length
        value = bs.read_bits(length)
        assert all(bit == self.VALUE for bit in value)
        return value

    @no_endianness
    def _write(self, bs, cursor, argument):
        length = 1 if self.length is None else self.length
        bs.write_bits([self.VALUE] * length)

class Zero(BoolFormat):
    VALUE = False

class One(BoolFormat):
    VALUE = True

class Byte(Format):
    """
    A byte/bytestring.
    """
    string = False
    list   = False
    signed = False
    def _read(self, bs, cursor):
        length = self.length
        if (length == None and not self.string) or length == 1:
            byte = bs.read_byte()
            if self.string:
                return chr(byte)
            if self.list:
                return [byte]
            if self.signed and byte > 127:
                return byte-256
            return byte

        elif length is None:
            if bs.bits_available & 7:
                raise ValueError("You cannot read the rest of the BitStream "
                                 "as a ByteString. The length of the "
                                 "available bits is not divisible by 8.")
            length = bs.bits_available // 8
            bs.read_all()

        if self.string:
            bytes = ''.join(chr(bs.read_byte()) for _ in xrange(length))
        else:
            bytes = [bs.read_byte() for _ in xrange(length)]

        if self.endianness == "<":
            bytes = bytes[::-1]

        if self.string or self.list:
            return bytes
        else:
            n = 0
            for i, b in izip(reversed(xrange(0, len(bytes)*8, 8)), bytes):
                n |= b << i
            if self.signed:
                if n > 2**(length*8-1):
                    n -= 2**(length*8)
            return n

    def _write(self, bs, cursor, bytes):
        if isinstance(bytes, float):
            bytes = int(bytes)

        if isinstance(bytes, (int, long)):
            if bytes in xrange(-128, 256) and self.length in (1, None):
                return bs.write_byte(bytes)
            Len = int(ceil(nbits(bytes)/8.))

            if self.length:
                leftover = (self.length - Len) * 8
                if leftover > 0 and self.endianness != "<":
                    if self.signed and bytes < 0:
                        bs.write(One[leftover])
                    else:
                        bs.write(Zero[leftover])
                elif leftover < 0:
                    raise ValueError("%r does not fit in %d bytes"
                                     ""% (bytes, self.length))
            else:
                leftover = 0

            R = xrange(0, Len*8, 8)
            if self.endianness != "<":
                R = reversed(R)

            for i in R:
                bs.write_byte((bytes & (0xFF << i)) >> i)

            if self.endianness == "<":
                if self.signed and bytes < 0:
                    bs.write(One[leftover])
                else:
                    bs.write(Zero[leftover])

        elif isinstance(bytes, str):
            length = self.length
            if length is not None:
                leftover = length - len(bytes)
                if leftover > 0:
                    bytes = "\0" * leftover + bytes
                elif leftover < 0:
                    raise ValueError("%r does not fit in %d bytes"
                                     "" % (bytes, self.length))
            else:
                leftover, length = 0, len(bytes)*8

            if self.endianness == "<":
                bytes = reversed(bytes)

            bs.write_bytes(ord(B) for B in bytes)
        else:
            raise TypeError("Invalid type for Byte/ByteString")

class ByteString(Byte):
    string = True

class ByteList(Byte):
    list = True

class SignedByte(Byte):
    signed = True

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
        try:
            argument = unicode(argument, "latin-1")
        except TypeError:
            pass
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

    When writing, if length is None, the log base 2 of the value is
    taken.

    >>> bits = BitStream()
    >>> bits.write(7, UB[10])
    >>> str(bits)
    "00000111"
    >>> bits.seek(0)
    >>> bits.write(0xDDEEFF, UB[24:"<"])
    >>> bits.seek(0)
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
            return bs.read_bit()
        elif length & 7 == 0:
            bytes, n = [bs.read_byte() for _ in xrange(length // 8)], 0
            R = xrange(len(bytes))
            if self.endianness != "<":
                R = reversed(R)
            for i, b in zip(R, bytes):
                n |= b << 8*i
            return n

        n = 0

        R = reversed(xrange(length))
        if self.endianness == "<":
            R = (b for a in izip_longest(*[iter(R)]*8) for b in reversed(a) if b is not None)

        for i, B in zip(R, bs.read_bits(length)):
            n |= B << i
        return n

    def _write(self, bs, cursor, argument):
        length = self.length
        argument = int(argument)
        nb = nbits(argument)
        if length is None:
            length = nbits(argument)
        elif length == 0:
            return
        elif length < nb:
            raise ValueError(("length of %d is not large "
                              "enough to store %d") % (length, argument))
        elif length == 1:
            return bs.write_bit(argument)
        elif length & 7 == 0:
            return bs.write(argument, Byte[length//8:self.endianness])

        R = reversed(xrange(length))
        if self.endianness == "<":
            R = (b for a in izip_longest(*[iter(R)]*8) for b in reversed(a) if b is not None)

        bs.write_bits(argument & (1 << b) for b in R)

    @staticmethod
    def _nbits(*args):
        return nbits(*(int(a) for a in args))

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
        signed = bs.read_bit()
        n = bs.read(UB[self.length-1:self.endianness])
        if signed:
            return n - 1 << self.length
        return n

    def _write(self, bs, cursor, argument):
        length = self.length
        if length == 0:
            return

        if argument > 0:
            if length is not None:
                length -= 1
            bs.write_bit(0)

        bs.write(argument, UB[length:self.endianness])

    @staticmethod
    def _nbits(*args):
        return nbits_signed(*(int(a) for a in args))

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
    signed = False
    @requires_length(can_be=(None,))
    @no_endianness
    def _read(self, bs, cursor):
        n = 0
        for i in xrange(5):
            byte = bs.read_byte()
            n |= (byte & 0x7F) << 7*i
            if not (byte & 0x80):
                break
        else:
            raise ValueError("Invalid U32")
        if self.signed and n > 0x7FFFFFFF:
            n -= 0x100000000
        return int(n) # no pesky 'L's

    @requires_length(can_be=(None,))
    @no_endianness
    def _write(self, bs, cursor, n):
        n &= 0xFFFFFFFF
        for i in xrange(5):
            cont = bool(n >> 7)
            bs.write_byte((cont << 7) | (n & 0x7F))
            n >>= 7
            if not cont:
                break
        else:
            raise ValueError("Value does not fit in a U32")

class S32(U32):
    signed = True

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
        return bs.read(SignedByte[self.length//8:self.endianness]) / \
            float({16: 0x100, 32: 0x10000}[self.length])

    @requires_length(can_be=(16, 32))
    def _write(self, bs, cursor, value):
         bs.write(value * float({16: 0x100, 32: 0x10000}[self.length]),
                  SignedByte[self.length//8:self.endianness])

class FloatFormat(Format):
    """
    A IEEE floating-point number.

    .. seealso:

        `Wikipedia: IEEE floating-point standard
        <http://en.wikipedia.org/wiki/IEEE_floating-point_standard>`_
           A good overview article of the IEEE floating-point standard, from
           Wikipedia.

    .. warning: Flash's FLOAT16 exponent bias is 16, not 15.
    """
    # Precalculated, see the Wikipedia links below.
    _EXPN_BIAS = {16: 16, 32: 127, 64: 1023}
    _N_EXPN_BITS = {16: 5, 32: 8, 64: 11}
    _N_FRAC_BITS = {16: 10, 32: 23, 64: 52}

    @requires_length(can_be=(16, 32, 64))
    def _read(self, bs, cursor):
        from fusion.bitstream.bitstream import BitStream
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
        from fusion.bitstream.bitstream import BitStream
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
        return One()
    return Zero()

def sequence_to_iformat(obj):
    return IFormat(IBitStream(obj))

provideAdapter(bool_to_iformat,    [bool],  IFormat)
provideAdapter(sequence_to_iformat, [list],  IFormat)
provideAdapter(sequence_to_iformat, [tuple], IFormat)
