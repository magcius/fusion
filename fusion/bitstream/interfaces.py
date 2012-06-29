
from zope.interface import Interface, Attribute
from zope.component import provideAdapter

class IBitStream(Interface):
    byte_aligned = Attribute("Whether this BitStream should be"
                             " read/written on a byte boundary")

    bits_available = Attribute("The number of bits left in the BitStream")

    def read(format):
        """
        Read a format or struct and return it.
        """

    def write(argument, format=None):
        """
        Write argument as format, which is an IFormat.

        If format is None, argument should be treated as an IFormat
        that doesn't require an argument.
        """

    def modify(modifier, *args, **kwargs):
        """
        Execute the modifier on this IBitStream.

        The modifier should which is a function that takes the bitstream
        and the cursor, args and kwargs returns a tuple containing user data
        to be returned in the first field and a new cursor in the second.
        """

    def read_bit():
        """
        Read a bit.
        """

    def write_bit():
        """
        Write a bit.
        """

    def read_bits(length):
        """
        Read length bits.
        """

    def write_bits(length):
        """
        Write length bits.
        """

    def read_byte():
        """
        Read a byte.
        """

    def write_byte(byte):
        """
        Write a byte.
        """

    def __len__():
        """
        Return how many bits are in this stream.
        """

    def __iter__():
        """
        Iterate over the bits in the stream.
        """

    def seek(a, b):
        pass

    def tell():
        pass

class IFormat(Interface):
    def _read(bitstream, cursor):
        """
        Read and return this format from the IBitStream bitstream.

        This should be called by an IBitStream instance.

        If you need to advance the bitstream's cursor, return a tuple
        with the first element the return value, and the second value
        an increment to be added to the current cursor.
        """

    def _write(bitstream, cursor, argument):
        """
        Write argument to as format to the IBitStream bitstream.

        This should be called by an IBitStream instance.

        If you need to advance the bitstream's cursor, return an
        increment to be added to the current cursor.
        """

class IFormatData(Interface):
    """
    TODO: document
    """
    length     = Attribute("length")
    endianness = Attribute("endianness")
    repr       = Attribute("repr")


class IFormatLength(Interface):
    """
    TODO: document
    """

class IStruct(Interface):
    def as_bitstream():
        """
        Return this struct represented as an instance of an IBitStream.
        """

def istruct_as_ibitstream(struct):
    return struct.as_bitstream()

provideAdapter(istruct_as_ibitstream, [IStruct], IBitStream)

class IStructClass(Interface):
    def from_bitstream(bitstream):
        """
        Read and return an instance of this struct from an IBitStream.
        """

class IAutoStruct(IStruct):
    def create_fields():
        """
        This should be a generator that yields IStructStatements that make
        up this struct.
        """

    def set_local(name, value):
        """
        Set the local (temporary) variable name to value.
        """

    def get_local(name):
        """
        Get the local (temporary) variable name.
        """

class IStructEvaluateable(Interface):
    """
    TODO: document
    """
    def _evaluate(struct):
        """
        TODO: document
        """

class IStructPrereadable(Interface):
    """
    TODO: document
    """
    def _pre_read(struct, field):
        """
        TODO: document
        """

    def _pre_write(struct, field):
        """
        TODO: document
        """

class IStructStatement(IStructPrereadable):
    def _struct_read(struct, bitstream):
        """
        Read this statement from bitstream and store it in struct.
        """

    def _struct_write(struct, bitstream):
        """
        Write this statement to the bitstream using struct.
        """
