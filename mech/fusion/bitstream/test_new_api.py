
from mech.fusion.bitstream.bitstream import BitStream
from mech.fusion.bitstream import formats as F

class CursorFormat(F.Format):
    def _read(self, bs, cursor):
        return cursor
    
    def _write(self, bs, cursor, argument):
        return argument

def test_read():
    bs = BitStream()
    bs.write(BitStream("11010"))
    assert bs.read(CursorFormat) == 5
    assert bs.cursor == 5
    bs.rewind()
    
    assert bs.read(CursorFormat) == 0
    assert bs.cursor == 0
    
