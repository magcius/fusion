
# Fast lookup for write/read_string.
# This seems really stupid, but I need it for SPEEEEED.

from math import log, floor, ceil

def lookup():
    b1 = {}
    b2 = {}
    b3 = {}
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
                raise ValueError("Part %r requires a length in the set of "
                                 "%s" % (type(self).__name__, can_be,))
            if cant_be is not None and self.length in cant_be:
                raise ValueError("Part %r cannot be in the set of "
                                 "%s" % (type(self).__name__, cant_be,))
            return fn(*args, **kwargs)
        return requires_length
    return requires_length

def no_endianness(fn):
    def no_endianness(self, *args, **kwargs):
        if self.endianness is not None:
            raise ValueError("Part %r does cannot"
                             " have endianness." % (type(self).__name__,))
        return fn(*args, **kwargs)
    return fn

class _PartMeta(object):
    """
    The metaclass used to implement parts.
    """
    TYPE = "Part"
    def __getitem__(self, item):
        if isinstance(item, slice):
            assert isinstance(item.start, (int, long))
            assert isinstance(item.stop , basestring)
            return self(item.start, item.stop, item.step)
        elif isinstance(item, (int, long)):
            return self(length=item)
        elif item in "<>":
            return self(endianness=item)
        raise ValueError("Part argument must either be an int (length), "
                         "or < or > (endianness), or a slice of "
                         "length:endianness.")

    def _read(self, bitstream):
        return self()._read(bitstream)

    def _write(self, bitstream, argument):
        return self()._write(bitstream, argument)
    
class _Part(object):
    """
    A single field in a BitStream.
    """
    TYPE = "Part"
    __metaclass__ = _PartMeta
    def __init__(self, length=None, endianness=None, repr=None):
        self.length = length
        self.endianness = endianness
        self.repr = repr

    def __getitem__(self, item):
        assert isinstance(item, (int, long))
        return _PartArray(self, item)

    def __str__(self):
        if self.repr:
            return self.repr
        return "%s[%d]" % (type(self).__name__, self.length)
    
    def _read(self, bitstream, cursor):
        raise NotImplementedError

    def _write(self, bitstream, cursor, argument):
        raise NotImplementedError

    def _pre_read(self, struct):
        self.length_old = self.length
        if hasattr(self.length, "_pre_write"):
            self.length._pre_write(struct, self)
        if hasattr(self.length, "_evaluate"):
            self.length = self.length._evaluate_write(struct, self)
        if hasattr(self.length, "_evaluate_read"):
            self.length = self.length._evaluate_read(struct, self)

    def _post_read(self, struct):
        self.length = self.length_old
    
    def _pre_write(self, struct):
        self.length_old = self.length
        if hasattr(self.length, "_pre_write"):
            self.length._pre_write(struct, self)
        if hasattr(self.length, "_evaluate"):
            self.length = self.length._evaluate_write(struct, self)
        elif hasattr(self.length, "_evaluate_write"):
            self.length = self.length._evaluate_write(struct, self)

    def _post_write(self, struct):
        self.length = self.length_old
    
class _PartArray(object):
    def __init__(self, part, repeat):
        self.part = part
        self.repeat = repeat

    def _read(self, bs, cursor):
        for i in xrange(self.repeat):
            yield s.read(self.part)

    def _write(self, bs, cursor, argument):
        if len(argument) != self.repeat:
            raise ValueError("This %s array is of length %d, you tried to wr"
                             "ite an %s" % (self.part, self.repeat, argument))
        for i in argument:
            bs.write(i, self.part)

    def __str__(self):
        return "%s[%d]" % (self.part, self.repeat)
    
class Bit(_Part):
    """
    One bit.
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
    
class BitsList(_Part):
    @requires_length(cant_be=(None,))
    @no_endianness
    def _read(self, bs, cursor):
        return bs[cursor:cursor+self.length], self.length

    @requires_length(can_be=(None,))
    @no_endianness
    def _write(self, bs, cursor, argument):
        lenL = len(argument)
        bs[cursor:cursor+lenL] = argument
        return lenL

class _BoolPart(_Part):
    VALUE = None
    @requires_length(cant_be=(None,))
    @no_endianness
    def _read(self, bs, cursor):
        assert bs.read(BitsList[self.length]) == [self.VALUE]*self.length
        return None

    @requires_length(cant_be=(None,))
    @no_endianness
    def _write(self, bs, cursor):
        bs.write([self.VALUE]*self.length, BitsList[self.length])

class Zero(_BoolPart):
    VALUE = False

class One(_BoolPart):
    VALUE = True

class Ignore(_Part):
    @no_endianness
    def _read(self, bs, cursor):
        return None, 1 if self.length is None else self.length

class Byte(_Part):
    signed=False
    def _read(self, bs, cursor):
        lookup = BITS_TO_BYTE
        if self.signed:
            lookup = BITS_TO_SIGNED_BYTE
        
        if self.length in (None, 1):
            byte = lookup[bs.read(BitsList[8])]
            if self.length == 1:
                return chr(byte)
            return byte
        
        bytes = ''.join(chr(lookup[bs.read(BitsList[8])]) \
                        for i in xrange(self.length))
        
        if self.endianness == "<":
            return bytes[::-1]
        
        return bytes
    
    def _write(self, bs, cursor, bytes):
        lookup = BYTE_TO_BITS
        if self.signed:
            lookup = SIGNED_BYTE_TO_BITS
        
        if isinstance(bytes, (int, long)):
            if bytes < 256:
                return bs.write(lookup[bytes], BitsList[8])
            Len = int(ceil(nbits(bytes) / 8.))
            L = Len - self.length
            if L > 0:
                bs.write(Zero[8*L])
            elif L < 0:
                raise ValueError("%r does not fit in %d bytes"
                                 ""% (bytes, self.length))
            
            R = xrange(Len)
            if self.endianness == "<":
                R = reversed(R)
            for i in R:
                bs.write(lookup[bytes & (0xFF << 8*i)])
        else:
            L = len(bytes) - self.length
            if L > 0:
                bs.write(Zero[8*L])
            elif L < 0:
                raise ValueError("%r does not fit in %d bytes"
                                 "" % (bytes, self.length))
            
            if self.endianness == "<":
                bytes = reversed(bytes)
            for i in bytes:
                if isinstance(bytes, str):
                    i = ord(i)
                bs.write(BYTE_TO_BITS[i], BitsList[8])

ByteString = Byte

class SignedByte(Byte):
    signed=True

class CString(_Part):
    @no_endianness
    @requires_length(can_be=(None,))
    def _read(self, bs, cursor):
        bytes = [0xDEADBEEF]
        while bytes[-1] != 0:
            bytes.append(bs.read(Byte))
        return ''.join(chr(i) for i in bytes[1:])
    
    @requires_length(can_be=(None,))
    def _write(self, bs, cursor, argument):
        bs.write(argument, ByteString)
        bs.write(0, Byte)

class UTF8(_Part):
    @requires_length(cant_be=(None,))
    def _read(self, bs, cursor):
        return bs.read(ByteString[self.length]).decode("utf8")
    
    def _write(self, bs, cursor, argument):
        bs.write(argument.encode("utf8"), ByteString[self.length])

class CUTF8(_Part):
    @requires_length(can_be=(None,))
    def _read(self, bs, cursor):
        return bs.read(CString).decode("utf8")

    @requires_length(can_be=(None,))
    def _write(self, bs, cursor, argument):
        bs.write(argument.encode("utf8"), CString)
    
class UB(_Part):
    def _read(self, bs, cursor):
        length = 1 if self.length is None else self.length
        if length == 1:
            return bs[cursor], 1
        elif length & 7:
            return bs.read(Byte[length//8])
        
        n = 0
        
        R = reversed(xrange(length))
        if self.endianness == "<":
            R = ((length // 8 - i // 8 - 1)*8 + i%8 for i in R)
        
        for i, j in enumerate(R):
            n |= bs[cursor+j] << i
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
        elif length & 7:
            return bs.write(argument, Byte[length//8])
        
        R = reversed(xrange(length))
        if self.endianness == "<":
            R = ((length // 8 - i // 8 - 1)*8 + i%8 for i in R)
        
        for i, j in enumerate(R):
            bs[cursor+j] = argument & i
        return n, length

    def _nbits(self, argument):
        return nbits(argument)

Bit = UB

class SB(_Part):
    def _read(self, bs, cursor):
        if self.length in (1, None):
            return bs[cursor], 1
        signed = bs.read(Bit)
        n = bs.read(UB[self.length-1])
        if signed:
            return -n
        return n

    def _write(self, bs, cursor, argument):
        length = self.length
        if self.length == 1:
            bs[cursor] = bool(argument)
            return 1
        if length is not None:
            length -= 1
        bs.write(argument < 0, Bit)
        bs.write(abs(argument), UB[length])

    def _nbits(self, argument):
        return nbits_signed(argument)

SI8  = SignedByte[1:"<":"SI8"]
SI16 = SignedByte[2:"<":"SI16"]
SI32 = SignedByte[4:"<":"SI32"]

UI8  = Byte[1:"<":"UI8"]
UI16 = Byte[2:"<":"UI16"]
UI24 = Byte[3:"<":"UI24"]
UI32 = Byte[4:"<":"UI32"]
UI64 = Byte[8:"<":"UI64"]

class U32(_Part):
    @requires_length(can_be=(None,))
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
    def _write(self, bs, cursor, n):
        while n > 0:
            bs.write((n >> 7) > 0,     Bit)
            bs.write((n & 0b01111111), UB[7])
            

class _FixedPart(_Part):
    @requires_length(can_be=(16, 32))
    def _read(self, bs, cursor):
        return bs.read(Byte[self.length:self.endianness]) / \
            float({8: 0x100, 16: 0x10000}[self.length])

    @requires_length(can_be=(16, 32))
    def _write(self, bs, cursor, value):
         bs.write(value * float({8: 0x100, 16: 0x10000}[self.length]),
                  Byte[self.length:self.endianness])

class _FloatPart(_Part):
    _EXPN_BIAS = {16: 16, 32: 127, 64: 1023}
    _N_EXPN_BITS = {16: 5, 32: 8, 64: 11}
    _N_FRAC_BITS = {16: 10, 32: 23, 64: 52}
    _FLOAT_NAME = {16: "float16", 32: "float", 64: "double"}

    @requires_length(can_be=(16, 32, 64))
    def _read(self, bs, cursor):
        if self.length not in self._FLOAT_NAME:
            raise ValueError("length is not 16, 32 or 64.")

        bits = bs.read_bits(BitsList[self.length])
        
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
