
from mech.fusion.bitstream.bitstream import BitStream

from mech.fusion.bitstream.formats import SB
from mech.fusion.bitstream.structs import Struct, Fields, NBits

class Rect(Struct):
    def __init__(self, XMin=0, YMin=0, XMax=0, YMax=0):
        super(Rect, self).__init__(locals())
    
    def createFields(self):
        yield NBits[5]
        yield Fields("XMin XMax YMin YMax", SB[NBits]) * 20

def test_rect_write():
    rect = Rect(0, 0, 600, 800)
    assert str(rect.as_bitstream()) == "01111000000000000000010111011100000000000000000000011111010000000"

def test_rect_read():
    bits = BitStream("01111000000000000000010111011100000000000000000000011111010000000")
    rect = Rect.from_bitstream(bits)
    assert rect.XMin == 0
    assert rect.XMax == 600
    assert rect.YMin == 0
    assert rect.YMax == 800
