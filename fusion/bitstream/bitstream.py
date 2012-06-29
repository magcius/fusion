
from array import array
import os
import zlib

ALIGN_LEFT = "left"
ALIGN_RIGHT = "right"

from fusion.bitstream import formats as F, flash_formats as FF
from fusion.bitstream.interfaces import IBitStream, IFormat, IFormatData

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

    def flush(self):
        """
        Zero-fill until we are aligned with byte boundaries,
        i.e until our length is a multiple of 8.
        This sets the cursor to the end of the stream.
        """
        self.seek(0, os.SEEK_END)
        leftover = self.tell() & 7
        if leftover & 7:
            self.write(F.Zero[8 - leftover])

    def skip_flush(self):
        """
        Align the cursor so that it is flush with the next
        byte, as in the cursor is a multiple of 8.

        If there are not enough bits left, do nothing.
        """
        leftover = self.tell() & 7
        if leftover and self.bits_available > 8-leftover:
            self.seek(8-leftover, os.SEEK_CUR)

    def seek(self, offset, whence=os.SEEK_SET):
        """
        Standard file protocol *seek* method.

        .. seealso:

           `Built-in Types: File Objects
           <http://docs.python.org/library/stdtypes.html#file-objects>`_
              Standard Python library documentation.
        """
        def inner(stream, cursor, offset, add=False):
            if add:
                return None, cursor+offset
            return None, offset
        if whence == os.SEEK_SET:
            self.modify(inner, offset)
        elif whence == os.SEEK_CUR:
            self.modify(inner, offset, True)
        elif whence == os.SEEK_END:
            self.modify(inner, len(self) - offset)

    def tell(self):
        """
        Gets the current cursor position.
        """
        def inner(a, b):
            return b, b
        return self.modify(inner)

    def rewind(self):
        """
        Seek to the beginning of the stream.
        """
        self.seek(0)

    def skip_to_end(self):
        """
        Seek to the end of the stream.
        """
        self.seek(len(self))

    @property
    def bits_ready(self):
        """
        The number of bits left in the stream, going past
        laziness.
        """
        return len(self) - self.tell()

    @property
    def bits_available(self):
        """
        The number of bits available in the stream to be
        read.
        """
        return self.real_len() - self.tell()

    def read_all(self):
        pass

    def decompress(self):
        """
        Decompress and replace the contents of
        this BitStream from cursor on outward.
        """
        cursor = self.tell()
        bytes = self.read(F.ByteString)
        decomp = zlib.decompress(bytes)
        self.seek(cursor)
        self.write(decomp, F.ByteString)
        self.seek(cursor)

    def serialize(self, align=ALIGN_LEFT):
        """
        Serialize bit array into a byte string, aligning either
        on the right (ALIGN_RIGHT) or left (ALIGN_LEFT).
        """
        copy = type(self)(list(self))
        numbytes, leftover = divmod(len(copy), 8)
        if leftover > 0:
            if align == ALIGN_RIGHT:
                # Insert some False values to pad the list
                # so it is aligned to the right.
                copy[:0] = [False] * (8-leftover)
            else:
                copy += [False] * (8-leftover)
            numbytes += 1
        copy.seek(0)
        return copy.read(F.ByteString[numbytes])

    def real_len(self):
        return len(self)

    def make_reader(self, format):
        return lambda: self.read(format)

    def __str__(self):
        return "".join("1" if b else "0" for b in self)

    def __repr__(self):
        return "<BitStream '%s' pos=%d>" % (str(self)[:len(self)], self.tell())

    def __iadd__(self, rhs):
        self.write(rhs)
        return self

class BoolArrayBitStream(BitStreamMixin):
    implements(IBitStream)

    byte_aligned = False


    # Fast lookup for write/read_string.
    # This seems really stupid, but I need it for SPEEEEED.

    BYTE_TO_BITS, BITS_TO_BYTE = {}, {}
    for i in xrange(256):
        bits = ''.join(chr(a == "1") for a in bin(i)[2:])
        bits = "\0"*(8-len(bits)) + bits
        BYTE_TO_BITS[i] = array('c', bits)
        BITS_TO_BYTE[bits] = i
    del bits, i


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
        if isinstance(bits, str):
            bits = bits.strip()
        self.bits = array('c', ''.join("\1" if bit or bit == "1" else "\0" for bit in bits))
        self.bytes = {}
        self.cursor = 0

    # New API.

    def read(self, part):
        return IFormat(part)._read(self, self.cursor)

    def write(self, argument, part=None):
        if part is None:
            part = argument
        IFormat(part)._write(self, self.cursor, argument)

    def modify(self, modifier, *args, **kwargs):
        data, self.cursor = modifier(self, self.cursor, *args, **kwargs)
        return data

    def read_bit(self):
        self.cursor += 1
        try:
            return self.bits[self.cursor - 1] == "\1"
        except IndexError:
            raise IndexError("BitStream read beyond boundaries")

    def write_bit(self, bit):
        self.bits[self.cursor:self.cursor+1] = array('c', chr(bool(bit)))
        self.cursor += 1

    def _read_bits(self, length, raw=False):
        if self.bits_available < length:
            raise IndexError("BitStream read beyond boundaries")
        self.cursor += length
        arr = self.bits[self.cursor-length:self.cursor]
        if raw: return arr
        return [a == "\1" for a in arr]

    read_bits = _read_bits

    def write_bits(self, bits, raw=False):
        if not raw: bits = array('c', (chr(bool(bit)) for bit in bits))
        self.bits[self.cursor:self.cursor+len(bits)] = bits
        self.cursor += len(bits)

    def read_byte(self):
        if self.cursor in self.bytes:
            self.cursor += 8
            return self.bytes[self.cursor-8]
        return self.BITS_TO_BYTE[self._read_bits(8, raw=True).tostring()]

    def write_byte(self, byte):
        self.bytes[self.cursor] = byte
        self.write_bits(self.BYTE_TO_BITS[byte], raw=True)

    def write_bytes(self, bytes):
        bits = array('c')
        for i, B in enumerate(bytes):
            self.bytes[self.cursor+i*8] = B
            bits += self.BYTE_TO_BITS[B]
        self.write_bits(bits, raw=True)

    def tell(self):
        return self.cursor

    def __len__(self):
        return len(self.bits)

    def __iter__(self):
        return iter(a == "\1" for a in self.bits)

class ByteArrayBitStream(BitStreamMixin):
    implements(IBitStream)

    byte_aligned = False

    # Fast lookup for write/read_string.
    # This seems really stupid, but I need it for SPEEEEED.

    BYTE_TO_BITS, BITS_TO_BYTE = {}, {}
    for i in xrange(256):
        bits = [a == "1" for a in bin(i)[2:]]
        bits = tuple([False]*(8-len(bits)) + bits)
        BYTE_TO_BITS[i] = bits
        BITS_TO_BYTE[bits] = i
    del bits, i, a

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
        self.bytes = array('B', [0])
        self.byte, self.bit = 0, 7
        self.len = 0
        for bit in bits:
            if bit == " ": continue
            self.write_bit(bit or bit == "1")

    def read(self, part):
        return IFormat(part)._read(self, self.tell())

    def write(self, argument, part=None):
        if part is None:
            part = argument
        IFormat(part)._write(self, self.tell(), argument)

    def modify(self, modifier, *args, **kwargs):
        data, cursor = modifier(self, self.tell(), *args, **kwargs)
        self.byte, bit = divmod(cursor, 8)
        self.bit = 7-bit
        return data

    def read_bit(self):
        value = bool(self.bytes[self.byte] & (1 << self.bit))
        if self.bit == 0:
            self.bit = 7
            self.byte += 1
        else:
            self.bit -= 1
        return value

    def write_bit(self, v):
        if v:
            self.bytes[self.byte] |= 1 << self.bit
        else:
            self.bytes[self.byte] &= ~(1 << self.bit)

        if self.bit == 0:
            self.bit = 7
            self.byte += 1
            if self.byte*8 > self.len:
                self.bytes.append(0)
        else:
            self.bit -= 1
        L = self.tell()
        if L > self.len: self.len = L

    def read_bits(self, length):
        return tuple(self.read_bit() for _ in xrange(length))

    def write_bits(self, bits):
        for b in bits:
            self.write_bit(b)

    def read_byte(self):
        if self.bit == 7:
            self.byte += 1
            return self.bytes[self.byte-1]
        return self.BITS_TO_BYTE[self.read_bits(8)]

    def write_byte(self, byte):
        if byte < 0: byte += 256
        if self.bit == 7:
            self.bytes[self.byte] = byte
            self.byte += 1
            if self.byte*8 > self.len:
                self.len += 8
                self.bytes.append(0)
        else:
            self.write_bits(self.BYTE_TO_BITS[byte])

    def write_bytes(self, bytes):
        bytes = list(bytes)
        Len = len(bytes)
        if self.bit == 7:
            self.bytes[self.byte:self.byte+Len] = array('B', bytes)
            self.byte += Len
            if self.byte*8 > self.len:
                self.len = self.byte*8
                self.bytes.append(0)
        else:
            for byte in bytes:
                self.write_byte(byte)

    def tell(self):
        return self.byte*8 + 7-self.bit

    def __len__(self):
        return self.len

    def __iter__(self):
        bytes = self.bytes
        if self.len & 7 == 0:
            bytes = bytes[:-1] # chop off the last 0
        for B in bytes:
            for i in reversed(xrange(8)):
                yield bool(B & 1 << i)

BitStream = ByteArrayBitStream

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
        inst.write(BitStreamDataFormat(type(self), bs.bits_available))
        inst.seek(0)
        return inst

    # bs.write(bs2, BitStream)
    # bs.write(bs2)
    def _write(self, bs, cursor, argument):
        argument = IBitStream(argument)
        argcursor = argument.tell()
        argument.seek(0)
        bs.write(argument, BitStreamDataFormat(type(self), argument.bits_available))
        argument.seek(argcursor)

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
        if self.endianness and length & 7: # we don't support endianness
            raise ValueError("You must have a length of a multiple of 8"
                             " in order to read with endianness")
        inst.write_bytes(bs.read(F.ByteList[length//8:self.endianness]))
        inst.write_bits(bs.read_bits(length & 7))
        inst.seek(0)
        return inst

    # bs.write(bs2, BitStream[8])
    def _write(self, bs, cursor, argument):
        argument = IBitStream(argument)
        length = len(argument) if self.length is None else self.length
        if self.endianness == "<":
            if length & 7:
                raise ValueError("You must have a length of a multiple of 8"
                                 " in order to write with endianness")
            bs.write(argument.read(F.ByteString[length//8]), F.ByteString["<"])
        else:
            bs.write_bits(argument.read_bits(length))
        if argument.byte_aligned:
            bs.flush()

def LazyBitStream(cls):
    class LazyBitStream(cls):
        def __init__(self, source):
            super(LazyBitStream, self).__init__()
            self.source = source
            self.source.fill_stream(self, 0)
            self.install_lazy()

        def install_lazy(self):
            self.read_bit  = self.__read_bit
            self.read_bits = self.__read_bits
            self.read_byte = self.__read_byte
            self.real_len  = self.__real_len

        def uninstall_lazy(self):
            self.read_bit  = super(LazyBitStream, self).read_bit
            self.read_bits = super(LazyBitStream, self).read_bits
            self.read_byte = super(LazyBitStream, self).read_byte
            self.real_len  = super(LazyBitStream, self).real_len

        def read_all(self):
            self.source.fill_stream(self, len(self.source))
            self.uninstall_lazy()

        def __read_bit(self):
            if self.bits_ready <= 0:
                self.source.fill_stream(self, 1)
            return super(LazyBitStream, self).read_bit()

        def __read_bits(self, length):
            if self.bits_ready < length:
                self.source.fill_stream(self, length)
            return super(LazyBitStream, self).read_bits(length)

        def __read_byte(self):
            if self.bits_ready < 8:
                self.source.fill_stream(self, 8)
            return super(LazyBitStream, self).read_byte()

        def __real_len(self):
            return len(self.source)
    return LazyBitStream

class LazyBitStreamFileSource(object):
    def __init__(self, file, len, sizehint=10):
        self.file, self.len = file, len
        self.sizehint = sizehint

    def fill_stream(self, stream, length):
        cursor = stream.tell()
        length = length // 8 + self.sizehint
        stream.seek(0, os.SEEK_END)
        while True:
            data = self.file.read(length)
            stream.write_bytes(ord(B) for B in data)
            if len(data) in (0, length): break
        stream.seek(cursor)

    def __len__(self):
        return self.len*8

class LazyBitStreamByteStringSource(object):
    def __init__(self, string, sizehint=10):
        self.cursor = 0
        self.string = string
        self.sizehint = sizehint

    def fill_stream(self, stream, length):
        cursor = stream.tell()
        length = length // 8 + self.sizehint
        stream.seek(0, os.SEEK_END)
        for byte in self.string[self.cursor:self.cursor+length]:
            stream.write_byte(ord(byte))
        stream.seek(cursor)

    def __len__(self):
        return len(self.string)*8

class BitStreamParseMixin(object):
    @classmethod
    def from_bitstream(cls, bitstream):
        raise NotImplementedError

    @classmethod
    def from_bytestring(cls, bytes, *a, **kw):
        BS = kw.pop('BitStream', BitStream)
        if kw.pop('lazy', True):
            bits = LazyBitStream(BS)(LazyBitStreamByteStringSource(bytes))
        else:
            bits = BS()
            bits.write(bytes, F.ByteString)
            bits.seek(0)
        return cls.from_bitstream(bits, *a, **kw)

    @classmethod
    def from_file(cls, file, len, *a, **kw):
        BS = kw.pop('BitStream', BitStream)
        if kw.pop('lazy', True):
            bits = LazyBitStream(BS)(LazyBitStreamFileSource(file, len))
            return cls.from_bitstream(bits, *a, **kw)
        else:
            return cls.from_bytestring(file.read(), lazy=False, *a, **kw)

    @classmethod
    def from_filename(cls, filename, *a, **kw):
        return cls.from_file(open(filename, 'rb'),
                             os.path.getsize(filename),
                             *a, **kw)
