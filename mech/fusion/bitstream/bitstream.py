
import os
import zlib

ALIGN_LEFT = "left"
ALIGN_RIGHT = "right"


from mech.fusion.bitstream import formats as F, flash_formats as FF
from mech.fusion.bitstream.interfaces import IBitStream, IFormat, IFormatData

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
        leftover = self.cursor & 7
        if leftover & 7:
            self.write(F.Zero[8 - (leftover)])
    
    def skip_flush(self):
        """
        Align the cursor so that it is flush with the next
        byte, as in the cursor is a multiple of 8.

        If there are not enough bits left, do nothing.
        """
        leftover = self.cursor & 7
        if leftover and self.bits_available > 8-leftover:
            self.cursor += 8-leftover

    def __iter__(self):
        return iter(self.bits)

    def __eq__(self, other):
        return self.bits == list(other)

    def __ne__(self, other):
        return self.bits != list(other)
    
    def __str__(self):
        return "".join("1" if b else "0" for b in self.bits)

    def __repr__(self):
        return "<BitStream '%s' cursor=%d>" % (str(self), self.cursor)

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
            self.cursor = offset + self.cursor
        elif whence == os.SEEK_END:
            self.cursor = len(self) - offset

    def rewind(self):
        """
        Seek to the beginning of the stream.
        """
        self.cursor = 0

    def skip_to_end(self):
        """
        Seek to the end of the stream.
        """
        self.cursor = len(self)

    @property
    def bits_available(self):
        """
        The number of bits available to be read, or the
        distance from the cursor to the end of the stream.
        """
        return len(self) - self.cursor

    @bits_available.setter
    def bits_available(self, value):
        self.cursor = len(self) - value

    def __add__(self, bits):
        b = BitStream()
        b += self
        b += bits
        return b

    def __iadd__(self, bits):
        self.skip_to_end()
        self.write(bits)
        return self

    def decompress(self):
        """
        Decompress and replace the contents of
        this BitStream from cursor on outward.
        """
        cursor = self.cursor
        bytes = zlib.decompress(self.read(F.ByteString))
        new_cursor = IFormat(F.ByteString)._write(self, cursor, bytes) + cursor
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

    byte_aligned = False
    
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
        retval, cursor = IFormat(part)._read(self, self.cursor)
        self.cursor += cursor
        return retval

    def write(self, argument, part=None):
        if part is None:
            part = argument
        cursor = IFormat(part)._write(self, self.cursor, argument)
        if cursor is not None:
            self.cursor += cursor

    def modify(self, modifier, *args, **kwargs):
        data, self.cursor = modifier(self, self.cursor, *args, **kwargs)
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
        bits.write(bits, F.Byte)
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
        L = bs.bits_available
        advance = BitStreamDataFormat(type(self), L)._write(inst, 0, bs)
        inst.rewind()
        return inst, advance

    # bs.write(bs2, BitStream)
    # bs.write(bs2)
    def _write(self, bs, cursor, argument):
        argument = IBitStream(argument)
        argcursor = argument.cursor
        argument.rewind()
        L = argument.bits_available
        advance = BitStreamDataFormat(type(self), L)._write(bs, cursor, argument)
        argument.cursor = argcursor
        return advance

# bs.read(BitStream)
# bs.write(bs2, BitStream)
provideAdapter(BitStreamFormatAdaptor, [BitStreamMeta], IFormat)

# bs.write(bs2)
provideAdapter(BitStreamFormatAdaptor, [IBitStream], IFormat)

class BitStreamDataFormat(object):
    implements(IFormat)

    def __init__(self, cls, data):
        self.cls = cls
        data = IFormatData(data)
        self.length = data.length
        self.endianness = data.endianness

    # bs.read(BitStream[8])
    def _read(self, bs, cursor):
        inst = self.cls()
        length = self.length
        if bs.bits_available < length:
            raise IndexError("BitStream read beyond boundaries")
        if self.endianness == "<":
            if length & 7: # we don't support non-byte-aligned endianness
                raise ValueError("You must have a length of a multiple of 8"
                                 " in order to read with endianness")
            inst.write(bs.read(F.ByteString[length//8]), F.ByteString["<"])
            length = 0
        else:
            inst[:] = bs[cursor:cursor+length]
        inst.rewind()
        return inst, length

    # bs.write(bs2, BitStream[8])
    def _write(self, bs, cursor, argument):
        argument = IBitStream(argument)
        length = len(argument) if self.length is None else self.length
        try:
            if self.endianness == "<":
                if length & 7:
                    raise ValueError("You must have a length of a multiple of 8"
                                     " in order to write with endianness")
                bs.write(argument.read(F.ByteString[length//8]), F.ByteString["<"])
            else:
                bs[cursor:cursor+length] = argument.read(F.BitsList[length])
            return length
        finally:
            if argument.byte_aligned:
                bs.flush()

class BitStreamParseMixin(object):
    @classmethod
    def from_bitstream(cls, bitstream):
        raise NotImplementedError

    @classmethod
    def from_bytestring(cls, bytes, *a, **kw):
        bits = BitStream()
        bits.write(bytes, F.ByteString)
        bits.rewind()
        return cls.from_bitstream(bits, *a, **kw)

    @classmethod
    def from_file(cls, file, *a, **kw):
        return cls.from_bytestring(file.read(), *a, **kw)

    @classmethod
    def from_filename(cls, filename, *a, **kw):
        return cls.from_file(open(filename, "rb"), *a, **kw)
