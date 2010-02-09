
from zope.interface import Interface

class IBitStream(Interface):
    def read(format):
        """
        Read a format or struct.
        """
    
    def write(argument, format=None):
        """
        Write argument as format.
        """

class IFormat(Interface):
    def _read(bitstream, cursor):
        """
        Read and return this format from the IBitStream bitstream.
        
        If you need to advance the bitstream's cursor, return a tuple
        with the first element the return value, and the second value
        an increment to be added to the current cursor.
        """

    def _write(bitstream, cursor, argument):
        """
        Write argument to as format to the IBitStream bitstream.

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
        Read and return this struct from an IBitStream.
        """
