
from fusion.bitstream.bitstream import BitStream

from fusion.swf.records import Rect

from fusion.bitstream.formats import SB, FB, Bit
from fusion.bitstream.structs import Struct, Fields, NBits
from fusion.bitstream.structs import Field, Local

from zope.interface import implementedBy

# rect_data = "01110" + "%s"*4 % tuple(("0"*(15-len(s))+s for s in (bin(s*20)[2:] for s in (20, 80, 600, 800))))
rect_data = BitStream("01111000000110010000010111011100000000011001000000011111010000000")

class TestRect(Struct):
    def __init__(self, XMin=0, YMin=0, XMax=0, YMax=0):
        super(TestRect, self).__init__(locals())

    def create_fields(self):
        yield NBits[5]
        yield Fields("XMin XMax YMin YMax", SB[NBits]) * 20

def test_rect_write():
    rect = TestRect(20, 80, 600, 800)
    assert rect.as_bitstream() == rect_data

def test_rect_read():
    rect = TestRect.from_bitstream(rect_data)
    assert rect.XMin == 20
    assert rect.YMin == 80
    assert rect.XMax == 600
    assert rect.YMax == 800

class TestMatrix(Struct):
    a, b, c, d = 1, 0, 0, 1
    def __init__(self, a, b, c, d, tx, ty):
        super(TestMatrix, self).__init__(locals())

    def create_fields(self):
        if self.writing:
            self.set_local("HasScale", (Field("a") != 1) & (Field("d") != 1))

        yield Local("HasScale", Bit)
        if self.get_local("HasScale", True):
            yield NBits[5]
            yield Fields("a d", FB[NBits])

        if self.writing:
            self.set_local("HasRotate", (Field("b") != 0) & (Field("c") != 0))

        yield Local("HasRotate", Bit)
        if self.get_local("HasRotate", True):
            yield NBits[5]
            yield Fields("b c", FB[NBits])

        yield NBits[5]
        yield Fields("tx ty", SB[NBits]) * 20

matrix_testcases = [
    ((1, 0, 0, 1, 0, 0),   "0000000"),
    ((1, 0, 0, 1, 10, 10), "0001001011001000011001000"),
    ((2, 0, 0, 2, 0, 0),   "11001101000000000000000000100000000000000000000000"),
]

def test_matrix_write():
    for tup, bits in matrix_testcases:
        matrix = TestMatrix(*tup)
        assert matrix.as_bitstream() == BitStream(bits)

def test_matrix_read():
    for tup, bits in matrix_testcases:
        matrix = TestMatrix.from_bitstream(BitStream(bits))
        assert matrix.a  == tup[0]
        assert matrix.b  == tup[1]
        assert matrix.c  == tup[2]
        assert matrix.d  == tup[3]
        assert matrix.tx == tup[4]
        assert matrix.ty == tup[5]

## test_rect_read()
## test_matrix_read()
## test_matrix_write()
