
import os
import zlib

ALIGN_LEFT = "left"
ALIGN_RIGHT = "right"


from mech.fusion.bitstream import formats as F, flash_formats as FF
from mech.fusion.bitstream.interfaces import IBitStream, IFormat

from zope.interface import implements
from zope.component import provideAdapter, adapter

class BitStreamMeta(F.FormatMeta):
    pass

class BitStreamMixin(object):
    """
    A class that implements various extra BitStream methods
    for those that implement the core methods defined in IBitStream.
    """

    __metaclass__ = BitStreamMeta

    @classmethod
    def specialize(cls, data):
        return BitStreamDataFormat(cls, data)
    
    # Old API.
    def read_bit(self):
        return self.read(F.Bit)
    
    def write_bit(self, value):
        self.write(value, F.Bit)

    def read_bits(self, length, as_list=False, endianness=">"):
        if as_list:
            return self.read(F.BitsList[length])
        return self.read(type(self)[length:endianness])

    def write_bits(self, bits, offset=0, length=None, endianness=">"):
        self.write(bits[offset:], BitStream[length:endianness])
    
    def read_string(self, length=None, endianness=">"):
        return self.read(F.ByteString[length:endianness])
    
    def write_string(self, string):
        self.write(string, F.ByteString)
        
    def read_cstring(self):
        return self.read(F.CString)

    def write_cstring(self, string):
        self.write(string, F.CString)
        
    def read_int_value(self, length, signed=False, endianness=">"):
        if signed:
            return self.read(F.SB[length:endianness])
        return self.read(F.UB[length:endianness])
        
    def write_int_value(self, value, length=None, signed=False, endianness=">"):
        if signed:
            return self.write(value, F.SB[length:endianness])
        self.write(value, F.UB[length:endianness])
    
    def read_fixed_value(self, length, endianness=">"):
        return self.read(F.FixedFormat[length:endianness])

    def write_fixed_value(self, value, length, endianness=">"):
        self.write(value, F.FixedFormat[length:endianness])
    
    def read_float_value(self, length, endianness=">"):
        return self.read(F.FloatFormat[length])

    def write_float_value(self, value, length):
        self.write(value, F.FloatFormat[length])

    def write_u32(self, value):
        self.write(value, F.U32)
    
    def read_u32(self):
        return self.read(F.U32)
    
    def one_fill(self, amount):
        """
        Fills amount bits with one. The equivalent of calling
        self.write_bit(True) amount times, but more efficient.
        """
        self.write(F.One[amount])
        
    def zero_fill(self, amount):
        """
        Fills amount bits with zero. The equivalent of calling
        self.write_bit(False) amount times, but more efficient.
        """
        self.write(F.Zero[amount])
    
    def flush(self):
        """
        Zero-fill until we are aligned with byte boundaries,
        i.e until our length is a multiple of 8.
        This sets the cursor to the end of the stream.
        """
        self.skip_to_end()
        lself = len(self)
        if lself & 7:
            self.write(F.Zero[8 - (lself & 7)])
    
    def skip_flush(self):
        """
        Align the cursor so that it is flush with the next
        byte, as in the cursor is a multiple of 8.
        """
        if self.cursor & 7:
            self.cursor += 8 - self.cursor & 7

    def __iter__(self):
        return iter(self.bits)

    def __eq__(self, other):
        return self.bits == list(other)

    def __ne__(self, other):
        return self.bits != list(other)
    
    def __str__(self):
        return "".join("1" if b else "0" for b in self.bits)

    __repr__ = __str__

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
            self.bits_available = offset

    def rewind(self):
        """
        Seek to the beginning of the stream.
        """
        def rewind(bs, cursor):
            return None, 0
        self.modify(rewind)
        
    def skip_to_end(self):
        """
        Seek to the end of the stream.
        """
        def skip_to_end(bs, cursor):
            return None, len(bs)
        self.modify(skip_to_end)

    @property
    def bits_available(self):
        """
        The number of bits available to be read, or the
        distance from the cursor to the end of the stream.
        """
        def bits_available(bs, cursor):
            return len(bs) - cursor, cursor
        return self.modify(bits_available)
    
    @bits_available.setter
    def bits_available(self, value):
        def bits_available(bs, cursor):
            return None, len(bs) - value
        self.modify(bits_available)
    
    def __add__(self, bits):
        b = BitStream()
        b += self
        b += bits
        return b

    def __iadd__(self, bits):
        self.skip_to_end()
        self.write(IBitStream(bits))
        return self

    @property
    def cursor(self):
        def get_cursor(bs, cursor):
            return cursor, cursor
        return self.modify(get_cursor)

    @cursor.setter
    def cursor(self, value):
        def set_cursor(bs, cursor):
            return None, value
        self.modify(set_cursor)
    
    def decompress(self):
        """
        Decompress and replace the contents of
        this BitStream from cursor on outward.
        """
        cursor = self.cursor
        bytes = zlib.decompress(self.read(F.ByteString))
        new_cursor = F.ByteString._write(bytes, cursor)
        self[new_cursor:] = []
        self.cursor = cursor
    
    def serialize(self, align=ALIGN_LEFT):
        """
        Serialize bit array into a byte string, aligning either
        on the right (ALIGN_RIGHT) or left (ALIGN_LEFT).
        """
        copy = type(self)(self[:])
        numbytes, leftover = divmod(len(copy), 8)
        if leftover > 0:
            if align == ALIGN_RIGHT:
                # Insert some False values to pad the list
                # so it is aligned to the right.
                copy[:0] = [False] * (8-leftover)
            else:
                copy += [False] * (8-leftover)
            numbytes += 1
        copy.rewind()
        return copy.read(F.ByteString[numbytes])

class BitStream(BitStreamMixin):
    implements(IBitStream)
    
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
        self._cursor = 0

    # New API.
    
    def read(self, part):
        retval, cursor = IFormat(part)._read(self, self._cursor), 0
        if isinstance(retval, tuple):
            retval, cursor = retval
        self._cursor += cursor
        return retval
    
    def write(self, argument, part=None):
        if part is None:
            part = argument
        cursor = IFormat(part)._write(self, self._cursor, argument)
        if cursor:
            self._cursor += cursor
        
    def modify(self, modifier, *args, **kwargs):
        data, self._cursor = modifier(self, self._cursor, *args, **kwargs)
        return data

    def __getitem__(self, i):
        return self.bits[i]

    def __setitem__(self, i, v):
        if isinstance(i, slice):
            self.bits[i] = v
        elif len(self.bits) == i:
            self.bits.append(v)
        else:
            self.bits[i] = bool(v)
    
    def __len__(self):
        return len(self.bits)

    def __iter__(self):
        return iter(self.bits)

def list_to_bitstream(bits):
    bits = list(bits)
    if all(bit in (0, 1, True, False) for bit in bits):
        return BitStream(bits)
    if all(bit in xrange(256) for bit in bits):
        bits = BitStream()
        bits.write(bits, Byte)
        return bits
    raise ValueError("Uncertain how to adapt this list into an"
                     "IFormat. Please check your input.")

provideAdapter(list_to_bitstream, [list],  IBitStream)
provideAdapter(list_to_bitstream, [tuple], IBitStream)

class BitStreamFormatAdaptor(object):
    implements(IFormat)
    
    def __init__(self, bitstream):
        self.bitstream = bitstream
    
    # bs.read(BitStream)
    def _read(self, bs, cursor):
        inst = self.bitstream()
        L = len(bs)
        inst.write(bs.read(F.UB[L]), F.UB[L])
        inst.rewind()
        return inst
    
    # bs.write(bs2, BitStream)
    # bs.write(bs2)
    def _write(self, bs, cursor, argument):
        argument = IBitStream(argument)
        cursor = argument.cursor
        argument.rewind()
        L = len(argument)
        bs.write(argument.read(F.UB[L]), F.UB[L])
        argument.cursor = cursor

# bs.read(BitStream)
# bs.write(bs2, BitStream)
provideAdapter(BitStreamFormatAdaptor, [BitStreamMeta], IFormat)

# bs.write(bs2)
provideAdapter(BitStreamFormatAdaptor, [IBitStream], IFormat)

class BitStreamDataFormat(object):
    implements(IFormat)

    def __init__(self, cls, data):
        self.cls = cls
        self.length = data.length
        self.endianness = data.endianness
    
    # bs.read(BitStream[8])
    def _read(self, bs, cursor):
        inst = self.cls()
        inst.write(bs.read(F.UB[self.length]),
                   F.UB[self.length:self.endianness])
        inst.rewind()
        return inst

    # bs.write(bs2, BitStream[8])
    def _write(self, bs, cursor, argument):
        argument = IBitStream(argument)
        length = self.length
        if length is None:
            length = argument.bits_available
        bs.write(argument.read(F.UB[length]),
                 F.UB[length:self.endianness])

class BitStreamParseMixin(object):
    @classmethod
    def from_bitstream(cls, bitstream):
        raise NotImplementedError
    
    @classmethod
    def from_bytestring(cls, bytes):
        bits = BitStream()
        bits.write(bytes, F.ByteString)
        bits.rewind()
        return cls.from_bitstream(bits)

    @classmethod
    def from_file(cls, file):
        return cls.from_bytestring(file.read())

    @classmethod
    def from_filename(cls, filename):
        return cls.from_file(open(filename))
