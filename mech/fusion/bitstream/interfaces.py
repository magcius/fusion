
from zope.interface import Interface

class IBitStream(Interface):
    
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
    
    def __getitem__(index):
        """
        Get and return the bit at value.
        """
    
    def __setitem__(index, value):
        """
        Set the bit at index to value.

        Index may be a slice.
        """

    def __len__():
        """
        Return how many bits are in this stream.
        """

    def __iter__():
        """
        Iterate over the bits in the stream.
        """
    
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

class IStruct(Interface):
    def as_bits():
        """
        Return this struct represented as an instance of an IBitStream.
        """

class IStructClass(Interface):
    def from_bits(bitstream):
        """
        Read and return an instance of this struct from an IBitStream.
        """
