
from mech.fusion.bitstream.bitstream import BitStream
from mech.fusion.bitstream.interfaces import IStruct
from mech.fusion.bitstream.formats import UB, SB
from mech.fusion.bitstream.flash_formats import SI32, UI16, UI32
from mech.fusion.bitstream.structs import Struct, NBits, Field, Local, Fields
from mech.fusion.util import nbits, nbits_signed, clamp

from math import sqrt

from zope.interface import implements

def serialize_style_list(lst):
    bits = BitStream()

    if len(lst) <= 0xFF:
        bits.write_int_value(len(lst), 8)
    else:
        bits.write_int_value(0xFF, 8)
        bits.write_int_value(len(lst), 16, endianness="<")

    for style in lst:
        bits += style

    return bits

def parse_style_list(bits):
    bits = BitStream()
    lst_len = bits.read_int_value(8)
    if lst_len == 0xFF:
        lst_len = bits.read_int_value(16, endianness="<")

    L = []
    for i in xrange(lst_len):
        TYPE = bits.read_int_value(8)
        L.append(FillStyle.REVERSE_INDEX[TYPE].parse(bits))
    return L

class RecordHeader(object):
    """
    RECORDHEADER struct, the header that signifies SWF tags.
    """

    implements(IStruct)
    
    def __init__(self, type, length):
        self.type = type
        self.length = length

    def as_bitstream(self):
        """
        Serializes this record, according to the following format.

        ====== =========
        Format Parameter
        ====== =========
        U[10]  type
        U[6]   length
        ====== =========
        """
        bits = BitStream()
        bits.write((self.type << 6) | min(self.length, 0x3F), UI16)
        if self.length >= 0x3F:
            bits.write(self.length, SI32)
        return bits

    @classmethod
    def from_bitstream(cls, bitstream):
        bits = bitstream.read(UI16)
        type, length = (bits >> 6), (bits & 0x3F)
        if length == 0x3F:
            length = bitstream.read(UI32)
        return cls(type, length)

class _EndShapeRecord(Struct):
    """
    Don't worry about me ;)
    """
    def as_bitstream(self):
        """
        Serializes this record, according to the following format.

        ====== =========
        Format Parameter
        ====== =========
        U[6]   always 0
        ====== =========
        """
        bitstream = BitStream()
        bitstream.zero_fill(6)
        return bitstream

    @classmethod
    def from_bitstream(cls, bits):
        bits.cursor += 6

EndShapeRecord = _EndShapeRecord()

class Rect(Struct):
    """
    Rect usually stores bounds or size in the SWF format.
    """
    def __init__(self, XMin=0, YMin=0, XMax=0, YMax=0):
        super(Rect, self).__init__(locals())
    
    def create_fields(self):
        yield NBits[5]
        yield Fields("XMin XMax YMin YMax", SB[NBits]) * 20

## class Rect(Struct):
##     """
##     Rect usually stores bounds or size in the SWF format.
##     """
##     def __init__(self, XMin=0, XMax=0, YMin=0, YMax=0):
##         """
##         Constructor.

##         :param XMin: the minimum X of the bounds.
##         :param XMax: the maximum X of the bounds. should be equal to XMin + width
##         :param YMin: the minimum Y of the bounds.
##         :param YMax: the maximum Y of the bounds. should be equal to YMin + height
##         """
##         self.XMin = XMin
##         self.XMax = XMax
##         self.YMin = YMin
##         self.YMax = YMax
        
##     def union(self, rect, *rects):
##         r = Rect(min(self.XMin, rect.XMin),
##                  max(self.XMax, rect.XMax),
##                  min(self.YMin, rect.YMin),
##                  max(self.YMax, rect.YMax))
##         if len(rects) > 0:
##             return r.union(*rects)
##         return r
    
##     def as_bitstream(self):
##         """
##         Serializes this record, according to the following format.

##         ======== =========
##         Format   Parameter
##         ======== =========
##         U[5]     NBits
##         S[NBits] XMin
##         S[NBits] XMax
##         S[NBits] YMin
##         S[NBits] YMax
##         ======== =========
##         """
##         if self.XMin > self.XMax or self.YMin > self.YMax:
##             raise ValueError, "Maximum values in a RECT must be larger than the minimum values."

##         # Find our values in twips.
##         twpXMin = self.XMin * 20
##         twpXMax = self.XMax * 20
##         twpYMin = self.YMin * 20
##         twpYMax = self.YMax * 20
        
##         # Find the number of bits required to store the longest value.
##         NBits = nbits_signed(twpXMin, twpXMax, twpYMin, twpYMax)

##         if NBits > 31:
##             raise ValueError, "Number of bits per value field cannot exceede 31."

##         # And write out our bits.
##         bits = BitStream()
##         bits.write_int_value(NBits, 5)
##         bits.write_int_value(twpXMin, NBits)
##         bits.write_int_value(twpXMax, NBits)
##         bits.write_int_value(twpYMin, NBits)
##         bits.write_int_value(twpYMax, NBits)

##         return bits

##     @classmethod
##     def parse(cls, bitstream):
##         NBits = bitstream.read_int_value(5)
##         XMin = bitstream.read_int_value(NBits) / 20
##         XMax = bitstream.read_int_value(NBits) / 20
##         YMin = bitstream.read_int_value(NBits) / 20
##         YMax = bitstream.read_int_value(NBits) / 20
##         return cls(XMin, XMax, YMin, YMax)

class XY(Struct):
    def __init__(self, X, Y):
        super(XY, self).__init__(locals())

    def create_fields(self):
        yield NBits[5]
        yield Fields("X Y", SB[NBits])

## class XY(object):
##     """
##     XY usually stores a position in the SWF format.
##     """
##     def __init__(self, X, Y):
##         """
##         Constructor.

##         :param X: the x translation
##         :param Y: the y translation
##         """
##         self.X = X
##         self.Y = Y

##     def as_bitstream(self):
##         """
##         Serializes this record, according to the following format.

##         ======== =========
##         Format   Parameter
##         ======== =========
##         U[5]     NBits
##         S[NBits] X
##         S[NBits] Y
##         ======== =========
##         """
##         # Convert to twips plz.
##         twpX = self.X * 20
##         twpY = self.Y * 20

##         # Find the number of bits required to store the longest value.
##         NBits = nbits_signed(twpX, twpY)

##         bits = BitStream()
##         bits.write_int_value(NBits, 5)
##         bits.write_int_value(twpX, NBits)
##         bits.write_int_value(twpY, NBits)

##         return bits

##     @classmethod
##     def parse(cls, bitstream):
##         NBits = bitstream.read_int_value(5)
##         X = bitstream.read_int_value(NBits) / 20
##         Y = bitstream.read_int_value(NBits) / 20
##         return cls(X, Y)

class RGB(object):
    implements(IStruct)
    """
    RGB stores a color in the SWF format.
    """
    def __init__(self, color):
        """
        Constructor.

        :param color: something like 0xFFFFFF or 0xADCAFE
        """
        self.color = color & 0xFFFFFF

    def as_bitstream(self):
        """
        Serializes this record, according to the following format.

        ====== ===========
        Format Parameter
        ====== ===========
        U[8]   red value
        U[8]   green value
        U[8]   blue value
        ====== ===========
        """
        bits = BitStream()
        bits.write_int_value(self.color, 24)
        return bits

    @classmethod
    def from_bitstream(cls, bitstream):
        return cls(bitstream.read_int_value(24))

class RGBA(RGB):
    """
    RGBA is an RGB object plus alpha.
    """
    def __init__(self, color, alpha=1.0):
        """
        Constructor.

        :param color: something like 0xFFFFFF or 0xADCAFE
        :param alpha: the alpha. a value between 0.0 and 1.0
        """
        super(RGBA, self).__init__(color)
        self.alpha = alpha

    def as_bitstream(self):
        """
        ====== ===========
        Format Parameter
        ====== ===========
        U[8]   red value
        U[8]   green value
        U[8]   blue value
        U[8]   alpha value
        ====== ===========
        """
        bits = RGB.as_bitstream(self)
        
        from mech.fusion.swf.tags import DefineShape
        
        # If we are in a DefineShape and the version does not support
        # alpha (DefineShape1 or DefineShape2), don't use alpha!
        if DefineShape._current_variant not in (1, 2):
            bits.write_int_value(int(self.alpha * 0xFF), 8)
        
        return bits

    @classmethod
    def from_bitstream(cls, bitstream):
        from mech.fusion.swf.tags import DefineShape
        rgb = RGB.from_bitstream(bitstream)
        color = rgb.color
        alpha = 1.0
        if DefineShape._current_variant not in (1, 2):
            alpha = bitstream.read_int_value(8) / 255.
        return RGBA(color, alpha)

class CXForm(object):
    """
    CXForm = ColorTransform
    """
    implements(IStruct)
    has_alpha = False
    def __init__(self, rmul=1, gmul=1, bmul=1, radd=0, gadd=0, badd=0):
        """
        Constructor.

        The multiplies are between 0.0 and 1.0

        :param rmul: Red Multiply.
        :param gmul: Green Multiply.
        :param bmul: Blue Multiply.

        The offsets are between -255 and 255.
        
        :param radd: Red Offset.
        :param gadd: Green Offset.
        :param badd: Blue Offset.
        """
        self.rmul = rmul
        self.gmul = gmul
        self.bmul = bmul
        self.amul = 1
        self.radd = radd
        self.gadd = gadd
        self.badd = badd
        self.aadd = 0

    def as_bitstream(self):
        """
        Serializes this record, according to the following format.
        
        ========================= =============
        Format                    Parameter
        ========================= =============
        U[1]                      HasAddTerms
        U[1]                      HasMulTerms
        U[4]                      NBits
        if HasMulTerms, U[NBits]  RedMultiply
        if HasMulTerms, U[NBits]  GreenMultiply
        if HasMulTerms, U[NBits]  BlueMultiply
        if HasAddTerms, U[NBits]  RedOffset
        if HasAddTerms, U[NBits]  GreenOffset
        if HasAddTerms, U[NBits]  BlueOffset
        ========================= =============
        """
        has_add_terms = self.radd != 0 or self.gadd != 0 or self.badd != 0 or self.aadd != 0
        has_mul_terms = self.rmul != 1 or self.gmul != 1 or self.bmul != 1 or self.amul != 1
        
        rm = abs(self.rmul * 256)
        gm = abs(self.gmul * 256)
        bm = abs(self.bmul * 256)
        am = abs(self.amul * 256)
        
        ro = clamp(self.radd, -255, 255)
        go = clamp(self.gadd, -255, 255)
        bo = clamp(self.badd, -255, 255)
        ao = clamp(self.aadd, -225, 255)
        
        NBits = 0
        if has_mul_terms: NBits = nbits(rm, gm, bm, am)
        if has_add_terms: NBits = max(NBits, nbits_signed(ro, go, bo, ao))
        
        bits = BitStream()
        bits.write_bit(has_add_terms)
        bits.write_bit(has_mul_terms)
        bits.write_int_value(NBits, 4)

        if has_mul_terms:
            bits.write_int_value(rm, NBits)
            bits.write_int_value(gm, NBits)
            bits.write_int_value(bm, NBits)
            if self.has_alpha: bits.write_int_value(am, NBits)

        if has_add_terms:
            bits.write_int_value(ro, NBits)
            bits.write_int_value(go, NBits)
            bits.write_int_value(bo, NBits)
            if self.has_alpha: bits.write_int_value(ao, NBits)

        return bits

    @classmethod
    def from_bitstream(cls, bits):
        has_add_terms = bits.read_bit()
        has_mul_terms = bits.read_bit()
        NBits = bits.read_int_value(4)

        if has_mul_terms:
            rmul = bits.read_int_value(NBits) / 256.
            gmul = bits.read_int_value(NBits) / 256.
            bmul = bits.read_int_value(NBits) / 256.
            if cls is CXFormWithAlpha: amul = bits.read_int_value(NBits) / 256.

        if has_add_terms:
            radd = bits.read_int_value(NBits)
            gadd = bits.read_int_value(NBits)
            badd = bits.read_int_value(NBits)
            if cls is CXFormWithAlpha: aadd = bits.read_int_value(NBits)

        if cls is CXFormWithAlpha:
            return cls(rmul, gmul, bmul, amul, radd, gadd, badd, aadd)
        return cls(rmul, gmul, bmul, radd, gadd, badd, aadd)
        
class CXFormWithAlpha(CXForm):
    has_alpha = True
    implements(IStruct)
    def __init__(self, rmul=1, gmul=1, bmul=1, amul=1, radd=0, gadd=0, badd=0, aadd=0):
        super(CXFormWithAlpha, self).__init__(rmul, gmul, bmul, radd, gadd, badd)
        self.amul = amul
        self.aadd = aadd

    def as_bitstream(self):
        """
        Serializes this record, according to the following format.
        
        ========================= =============
        Format                    Parameter
        ========================= =============
        U[1]                      HasAddTerms
        U[1]                      HasMulTerms
        U[4]                      NBits
        if HasMulTerms, U[NBits]  RedMultiply
        if HasMulTerms, U[NBits]  GreenMultiply
        if HasMulTerms, U[NBits]  BlueMultiply
        if HasMulTerms, U[NBits]  AlphaMultiply
        if HasAddTerms, U[NBits]  RedOffset
        if HasAddTerms, U[NBits]  GreenOffset
        if HasAddTerms, U[NBits]  BlueOffset
        if HasADdTerms, U[NBits]  AlphaOffset
        ========================= =============
        """
        return super(CXFormWithAlpha, self).as_bitstream()

class Matrix(object):
    
    def __init__(self, a=1, b=0, c=0, d=1, tx=0, ty=0):
        self.a, self.b, self.c, self.d, self.tx, self.ty = a, b, c, d, tx, ty

    def as_bitstream(self):
        """
        Serializes this record, according to the following format.
        
        =================================== =============
        Format                              Parameter
        =================================== =============
        U[1]                                HasScale
        U[5]                                NScaleBits
        if HasScale, U[NScaleBits]          ScaleX
        if HasScale, U[NScaleBits]          ScaleY
        U[1]                                HasRotate
        U[5]                                NRotateBits
        if HasScale, U[NRotateBits]         RotateSkew0
        if HasScale, U[NRotateBits]         RotateSkew1
        U[5]                                NTransxlateBits
        if HasScale, U[NTranslateBits]      TranslateX
        if HasScale, U[NTranslateBits]      TranslateY
        =================================== =============
        """
        def write_prefixed_values(a, b):
            NBits = nbits(a, b)
            bits.write_int_value(NBits, 5)
            bits.write_int_value(a, NBits)
            bits.write_int_value(b, NBits)
        
        bits = BitStream()
        if self.a != 1 or self.d != 1: # HasScale
            bits.write_bit(True)
            write_prefixed_values(self.a, self.d)
        else:
            bits.write_bit(False)

        if self.b != 0 or self.c != 0: # HasRotate
            bits.write_bit(True)
            write_prefixed_values(self.b, self.c)
        else:
            bits.write_bit(False)

        write_prefixed_values(self.tx * 20, self.ty * 20)
        return bits

    @classmethod
    def from_bitstream(cls, bits):
        def read_prefixed_values():
            NBits = bits.read_int_value(5)
            return bits.read_int_value(NBits), bits.read_int_value(NBits)

        a, b, c, d = 1, 0, 0, 1
        
        if bits.read_bit(): # HasScale
            a, d = read_prefixed_values()

        if bits.read_bit(): # HasRotate
            b, c = read_prefixed_values()

        tx, ty = read_prefixed_values()
        return cls(a, b, c, d, tx, ty)

class Shape(object):

    def __init__(self):
        self.shapes = []
        
        self.edge_bounds = Rect()
        self.shape_bounds = Rect()
        
        self.has_scaling = False
        self.has_non_scaling = False
        
        self.bounds_calculated = False

    def add_shape_record(self, shape):
        self.shapes.append(shape)
        self.bounds_calculated = False
    
    def add_shape(self, shape):
        self.shapes += shape.shapes
        self.bounds_calculated = False

    def as_bitstream(self):
        """
        Serializes this record, according to the following format.

        ================= ============
        Format            Parameter
        ================= ============
        
        SHAPERECORD[...]  the shape records
        U[24]             always 0
        ================= ============
        """
        if not self.bounds_calculated:
            self.calculate_bounds()
        
        if EndShapeRecord not in self.shapes:
            self.shapes.append(EndShapeRecord)

        bits = BitStream()
        
        bits += self.serialize_style()
        for record in self.shapes:
            bits += record

        return bits

    def serialize_style(self):
        """
        Serializes the style portion of this record.
        """
        bits = BitStream()
        bits.zero_fill(8) # NumFillBits and NumLineBits
        return bits
    
    def calculate_bounds(self):
        if self.bounds_calculated:
            return

        last = 0, 0
        style = None
        for record in self.shapes:
            last, (self.shape_bounds, self.edge_bounds), (has_scale, has_non_scale, style) = \
                  record.calculate_bounds(last, self.shape_bounds, self.edge_bounds, style)
            if has_scale:
                self.has_scaling = True
            if has_non_scale:
                self.has_non_scaling = True

        self.bounds_calculated = True

class ShapeWithStyle(Shape):

    def __init__(self, fills=None, strokes=None):
        super(ShapeWithStyle, self).__init__()
        self.fills = fills or []
        self.strokes = strokes or []

    def add_fill_style(self, style):
        style.parent = self.fills
        self.fills.append(style)

    def add_line_style(self, style):
        style.parent = self.strokes
        self.strokes.append(style)
        
    def add_shape(self, shape):
        Shape.add_shape(self, shape)
        try:
            self.fills += shape.fills
            self.strokes += shape.strokes
        except AttributeError:
            pass
    
    def serialize_style(self):
        bits = BitStream()
        bits += serialize_style_list(self.fills)
        bits += serialize_style_list(self.strokes)
        bits.write_int_value(nbits(len(self.fills)), 4)
        bits.write_int_value(nbits(len(self.strokes)), 4)
        return bits
    
class LineStyle(object):

    caps = "round"
    
    def __init__(self, width=1, color=0, alpha=1.0):
        self.width = width
        self.color = RGBA(color, alpha)

    @property
    def index(self):
        return self.parent.find(self)
    
    def as_bitstream(self):
        bits = BitStream()
        bits.write_int_value(self.width * 20, 16, endianness="<")
        bits += self.color
        return bits

    def from_bitstream(self, bits):
        self.width = bits.read_int_value(16, endianness="<")
        self.color = RGBA.from_bitstream(bits)

class LineStyle2(LineStyle):

    def __init__(self, width=1, fillstyle=None, pixel_hinting=False, scale_mode=None, caps="round", joints="round", miter_limit=3):

        color, alpha, self.fillstyle = 0, 1.0, None
        
        if isinstance(fillstyle, RGBA):
            color = fillstyle.color
            alpha = fillstyle.alpha
        elif isinstance(fillstyle, RGB):
            color = fillstyle.color
        elif isinstance(fillstyle, int):
            if fillstyle > 0xFFFFFF:
                color = fillstyle & 0xFFFFFF
                alpha = fillstyle >> 6 & 0xFF
            else:
                color = fillstyle
        elif isinstance(fillstyle, FillStyleSolidFill):
            color = fillstyle.color.color
            alpha = fillstyle.color.alpha
        elif isinstance(fillstyle, FillStyle):
            self.fillstyle = fillstyle
        
        super(LineStyle2, self).__init__(self, width, color, alpha)
        self.pixel_hinting = pixel_hinting
        self.scale_mode = scale_mode

        self.caps = caps
        self.joints = joints

        self.miter_limit = miter_limit

    def as_bitstream(self):

        h_scale = (self.scale_mode == "normal" or self.scale_mode == "horizontal")
        v_scale = (self.scale_mode == "normal" or self.scale_mode == "vertical")
        
        bits = BitStream()
        bits.write_int_value(self.width * 20, 16, endianness="<")

        caps = dict(round=0, none=1, square=2).get(self.caps, 0)
        joints = dict(round=0, bevel=1, miter=2).get(self.joints, 0)
        
        bits.write_int_value(caps, 2)
        bits.write_int_value(joints, 2)
        bits.write_bit(self.fillstyle is not None)
        bits.write_bit(h_scale)
        bits.write_bit(v_scale)
        bits.write_bit(self.pixel_hinting)

        if joints == 2:
            bits.write_fixed_value(self.miter_limit, 16, endianness="<")

        if self.fillstyle:
            bits += self.fillstyle
        else:
            bits += self.color

        return bits

    ## def from_bitstream(self, bits):
    ##     self.width = bits.read_int_value(16, endianness="<")

    def cap_style_logic(self, style, last, delta):
        # Half thickness (radius of round cap; diameter is thickness)
        off = style.width / 2.0
        dx, dy = delta
        lx, ly = last
        
        if style.caps == "round":
            r = Rect()
            r.XMin = cmp(dx, 0) * off
            r.YMin = cmp(dy, 0) * off
            r.XMax = r.XMin + dx
            r.YMax = r.XMax + dy
            return r
        
        if style.caps == "square":
            
            # Account for the length of the caps.
            dellen = sqrt(dx*dx + dy*dy)  # Delta length
            norm = (dellen+off*2)/dellen  # Extra length
            dx *= norm                    # Add the extra length
            dy *= norm
            sqx, sqy = delta              # Square cap offset
            norm = off/dellen             # Offset amount
            sqx *= norm                   # Position offsets.
            sqy *= norm
            
            # And offset the position.
            lx -= sqx
            ly -= sqy

        # Right-hand normal to vector delta relative to (0, 0).
        p1x, p1y = (-dy, dx)
        norm = sqrt(p1x*p1x + p1y*p1y)
        p1x /= norm
        p1y /= norm

        # Left-hand normal to vector delta relative to (0, 0)
        p2x, p2y = (-p1x, -p1y)
        
        # Right-hand normal to vector delta relative to delta.
        p3x, p3y = (p1x + dx, p1y + dy)

        # Left-hand normal to vector delta relative to delta.
        p4x, p4y = (p2x + dx, p2y + dy)

        return Rect(
            min(p1x, p2x, p3x, p4x) + lx,
            max(p1x, p2x, p3x, p4x) + lx,
            min(p1y, p2y, p3y, p4y) + ly,
            max(p1y, p2y, p3y, p4y) + ly)

class FillStyle(object):

    TYPE = -1
    REVERSE_INDEX = {}

    def __init__(self):
        FillStyle.REVERSE_INDEX[self.TYPE] = self
    
    @property
    def index(self):
        return self.parent.find(self)
    
    def as_bitstream(self):
        bits = BitStream()
        bits.write_int_value(self.TYPE, 8)
        bits += self.as_bitstream_inner()
        return bits

    def as_bitstream_inner(self):
        pass
    
class FillStyleSolidFill(FillStyle):
    
    TYPE = 0
    
    def __init_(self, color, alpha=1.0):
        self.color = RGBA(color, alpha)

    def as_bitstream_inner(self):
        return self.color.as_bitstream()

class GradRecord(object):

    def __init__(self, ratio=0, color=0, alpha=1.0):
        self.ratio = ratio
        self.color = RGBA(color, alpha)

    def as_bitstream(self):
        bits = BitStream()
        bits.write_int_value(self.ratio, 8)
        bits += self.color
        return bits

    @classmethod
    def from_bitstream(cls, bits):
        ratio = bits.read_int_value(8)
        color = RGBA.from_bitstream(bits)
        color, alpha = color.color, color.alpha
        return cls(ratio, color, alpha)

class Gradient(object):
    has_focal = False
    def __init__(self, grads=[], spread="pad", interpolation="rgb"):
        import operator
        grads.sort(key=operator.attrgetter("ratio"))
        self.grads = grads
        self.spread = spread
        self.interpolation = interpolation
        self.focalpoint = 0

    def as_bitstream(self):
        spread = dict(pad=0, reflect=1, repeat=2).get(self.spread, 0)
        interpolation = dict(rgb=0, linear=1).get(self.interpolation, 0)

        bits = BitStream()
        bits.write_int_value(spread, 2)
        bits.write_int_value(interpolation, 2)

        bits.write_int_value(len(self.grads), 4)
        for grad in self.grads:
            bits += grad

        if self.has_focal:
            bits.write_fixed_value(self.focalpoint, 16, endianness="<")

        return bits

    @classmethod
    def from_bitstream(cls, bits):
        spread = ["pad", "reflect", "repeat"][bits.read_int_value(2)]
        interpolation = ["rgb", "linear"][bits.read_int_value(2)]
        
        grads = []
        
        lst_len = bits.read_int_value(4)
        for i in xrange(lst_len):
            grad = GradRecord.from_bitstream(bits)
            grads.append(grad)

        if cls.has_focal:
            focalpoint = bits.read_fixed_value(16, endianness="<")
            return cls(grads, spread, interpolation, focalpoint)

        return cls(grads, spread, interpolation)
        
    @classmethod
    def from_begin_gradient_fill(cls, colors, alphas, ratios, spread, interpolation, focalpoint):
        grads = [GradRecord(*t) for t in zip(ratios, colors, alphas)]
        return cls(grads, spread, interpolation, focalpoint)

class FocalGradient(Gradient):
    has_focal = True
    def __init__(self, grads, spread="pad", interpolation="rgb", focalpoint=0):
        super(FocalGradient, self).__init__(grads, spread, interpolation)
        self.focalpoint = focalpoint

class FillStyleLinearGradientFill(FillStyle):
    TYPE = 0x10
    def __init__(self, matrix, gradient):
        self.matrix = matrix
        self.gradient = gradient

    def as_bitstream_inner(self):
        return self.matrix.serialize() + self.gradient.serialize()

class StraightEdgeRecord(object):

    def __init__(self, delta_x, delta_y):
        self.delta_x = delta_x
        self.delta_y = delta_y
        self.bounds_calculated = False

    def as_bitstream(self):
            
        bits = BitStream()
        
        if self.delta_x == 0 and self.delta_y == 0:
            return bits

        bits.write_bit(True) # TypeFlag
        bits.write_bit(True) # StraightFlag

        X = self.delta_x * 20
        Y = self.delta_y * 20

        NBits = nbits(X, Y)

        if NBits > 15:
            raise ValueError("Number of bits per value field cannot exceed 15")
        
        bits.write_int_value(NBits, 4)
        NBits += 2
        if X == 0:
            # Vertical Line
            bits.write_bit(False) # GeneralLineFlag
            bits.write_bit(True)  # VerticalLineFlag
            bits.write_int_value(Y, NBits)
        elif Y == 0:
            # Horizontal Line
            bits.write_bit(False) # GeneralLineFlag
            bits.write_bit(True)  # HorizontalLineFlag
            bits.write_int_value(X, NBits)
        else:
            # General Line
            bits.write_bit(True) # GeneralLineFlag
            bits.write_int_value(X, NBits)
            bits.write_int_value(Y, NBits)

        return bits

    def calculate_bounds(self, last, shape_bounds, edge_bounds, style):
        rect = Rect(last[0], last[1], self.delta_x, self.delta_y)
        return ((self.delta_x, self.delta_y),
                (shape_bounds.union(rect),
                 edge_bounds.union(LineStyle2.cap_style_logic(style,
                              last, (self.delta_x, self.delta_y)))),
                (False, False, style))


class CurvedEdgeRecord(object):

    def __init__(self, controlx, controly, anchorx, anchory):
        self.controlx = controlx
        self.controly = controly
        self.anchorx = anchorx
        self.anchory = anchory

    def as_bitstream(self):
            
        bits = BitStream()

        bits.write_bit(True)  # TypeFlag
        bits.write_bit(False) # StraightFlag

        cX = self.controlx * 20
        cY = self.controly * 20
        aX = self.anchorx  * 20
        aY = self.anchory  * 20
        
        NBits = nbits(cX, cY, aX, aY)

        if NBits > 15:
            raise ValueError("Number of bits per value field cannot exceed 15")

        bits.write_int_value(NBits, 4)
        NBits += 2
        bits.write_int_value(cX, NBits)
        bits.write_int_value(cY, NBits)
        bits.write_int_value(aX, NBits)
        bits.write_int_value(aY, NBits)
        return bits
    
    def _get_x(self, t):
        return self.controlx * 2 * (1-t) * t + self.anchorx * t * t

    def _get_y(self, t):
        return self.controly * 2 * (1-t) * t + self.anchory * t * t

    def _get_p(self, t):
        return (self._get_x(t), self._get_y(t))
    
    def calculate_bounds(self, last, shape_bounds, edge_bounds, style):
        union = Rect(0, 0, 0, 0)

        """
        CurvedEdgeRecord Bounds
        Formulas somewhat based on
        http://code.google.com/p/bezier/source/browse/trunk/bezier/src/flash/geom/Bezier.as
        Maths here may be incorrect
        
        extremumX = last.x - 2 * control.x + anchor.x
        extremumX = last.x - 2 * ( controlDeltaX - last.x ) + anchorDeltaX - last.x
        extremumX = (last.x - last.x) - 2 * ( controlDeltaX - last.x ) + anchorDeltaX
        extremumX = -2 * ( controlDeltaX - last.x ) + anchorDeltaX
        
        For the case of last.[xy] = 0, we can use the formula below.
        """

        x = -2 * self.controlx + self.anchorx
        t = -self.controlx / x
        p = self._get_x(t)

        if t <= 0 or t >= 1:
            union.XMin = last[0] + min(self.anchorx, 0)
            union.XMax = union.XMin + max(self.anchorx, 0)
        else:
            union.XMin = min(p, 0, self.anchorx + last[0])
            union.XMax = union.XMin + max(p - last[0], 0, self.anchorx)
            
        y = -2 * self.controly + self.anchory
        t = -self.controly / y
        p = self._get_y(t)

        if t <= 0 or t >= 1:
            union.YMin = last[1] + min(self.anchory, 0)
            union.YMax = union.YMin + max(self.anchory, 0)
        else:
            union.YMin = min(p, 0, self.anchory + last[1])
            union.YMax = union.YMin + max(p - last[0], 0, self.anchory)

        """
        CapStyle logic:

        Assume that p0 is last (start anchor),
        p1 is control, and p2 is (end) anchor.

        Get some small increments in the segment to
        find somewhat of a slope derivative type thing.

        We should be able to pass these two line deltas
        into LineStyle2.cap_style_logic and union the
        results.

        This will break at some point.
        """
        
        slope1 = self._get_p(0.01)
        slope2 = (self.anchorx - self._get_x(0.99), self.anchory - self._get_y(0.99))
        end_cap_rect   = LineStyle2.cap_style_logic(style, last, slope2)
        start_cap_rect = LineStyle2.cap_style_logic(style, last, slope1)

        return ((self.anchorx, self.anchory),
                (shape_bounds.union(union),
                 edge_bounds.union(union, start_cap_rect, end_cap_rect)),
                (False, False, style))

class StyleChangeRecord(object):

    def __init__(self, delta_x, delta_y, linestyle=None,
                 fillstyle0=None, fillstyle1=None,
                 fillstyles=None, linestyles=None):
        
        self.delta_x = delta_x
        self.delta_y = delta_y
        self.linestyle = linestyle
        self.fillstyle0 = fillstyle0
        self.fillstyle1 = fillstyle1
        self.fillstyles = fillstyles
        self.linestyles = linestyles

    def as_bitstream(self):
        bits = BitStream()
        if self.fillstyle0 is not None and self.fillstyle1 is not None and \
               self.fillstyle0.parent != self.fillstyle1.parent:
            raise ValueError("fillstyle0 and fillstyle1 do not have the same parent!")
        
        fsi0 = 0 if self.fillstyle0 is None else self.fillstyle0.index
        fsi1 = 0 if self.fillstyle1 is None else self.fillstyle1.index
        lsi  = 0 if self.linestyle  is None else self.linestyle.index

        fbit = 0 if self.fillstyle0 is None else nbits(len(self.fillstyle0.parent))
        lbit = 0 if self.linestyle  is None else nbits(len(self.linestyle.parent))
        
        from mech.fusion.swf.tags import DefineShape
        
        new_styles = ((DefineShape._current_variant > 1) and
                     ((self.linestyles != None and len(self.linestyles) > 0) or
                      (self.fillstyles != None and len(self.fillstyles) > 0)))

        bits.write_bit(False)       # TypeFlag
        bits.write_bit(new_styles)  # StateNewStyles
        bits.write_bit(lsi  > 0)    # StateLineStyle
        bits.write_bit(fsi0 > 0)    # StateFillStyle0
        bits.write_bit(fsi1 > 0)    # StateFillStyle1

        move_flag = self.delta_x != 0 or self.delta_y != 0

        if move_flag:
            bits += XY(self.delta_x, self.delta_y)

        if fsi0 > 0:  bits.write_int_value(fsi0, fbit) # FillStyle0
        if fsi1 > 0:  bits.write_int_value(fsi1, fbit) # FillStyle1
        if lsi  > 0:  bits.write_int_value(lsi,  lbit) # LineStyle
        
        if new_styles:
            bits += serialize_style_list(self.fillstyles) # FillStyles
            bits += serialize_style_list(self.linestyles) # LineStyles

            bits.write_int_value(nbits(len(self.fillstyles)), 4) # FillBits
            bits.write_int_value(nbits(len(self.linestyles)), 4) # LineBits

        return bits

    ## def from_bitstream(self, bits):
    ##     StateNewStyles  = bits.read_bit()
    ##     StateLineStyle  = bits.read_bit()
    ##     StateFillStyle1 = bits.read_bit()
    ##     StateFillStyle0 = bits.read_bit()
    ##     StateMoveTo     = bits.read_bit()

    ##     if StateMoveTo:
    ##         xy = XY()
    ##         xy.from_bitstream(bits)
    ##         self.delta_x, self.delta_y = xy.X, xy.Y

    ##     if StateFillStyle0:
    ##         pass

    ##     if StateFillStyle1:
    ##         pass


