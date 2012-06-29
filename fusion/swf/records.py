
from fusion.bitstream.bitstream import BitStream
from fusion.bitstream.interfaces import IStruct, IFormat, IStructEvaluateable
from fusion.bitstream.formats import UB, SB, FB, Bit, Zero, One
from fusion.bitstream.flash_formats import SI32, UI8, UI16, UI24, UI32, FIXED8
from fusion.bitstream.structs import Struct, NBits, Field, Local, Fields, Enum, byte_aligned
from fusion.util import nbits, nbits_signed, clamp

from math import sqrt

from zope.interface import implements, classProvides

def serialize_style_list(lst):
    bits = BitStream()
    if len(lst) < 0xFF:
        bits.write(len(lst), UI8)
    else:
        bits.write(0xFF, UI8)
        bits.write(len(lst), UI16)

    for style in lst:
        bits += style

    return bits

def parse_fill_style_list(bits):
    length = bits.read(UI8)
    if length == 0xFF:
        length = bits.read(UI16)

    for i in xrange(length):
        yield FillStyle.from_bitstream(bits)

class RecordHeader(object):
    """
    RECORDHEADER struct, the header that signifies SWF tags.
    """
    implements(IStruct)
    def __init__(self, id, length):
        from fusion.swf.tags import tag_map
        self.id = id
        self.type = tag_map[id]
        self.length = length
        self.bit_length = length*8

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
        bits.write((self.id << 6) | min(self.length, 0x3F), UI16)
        if self.length >= 0x3F:
            bits.write(self.length, SI32)
        return bits

    @classmethod
    def from_bitstream(cls, bitstream):
        bits = bitstream.read(UI16)
        id, length = (bits >> 6), (bits & 0x3F)
        if length == 0x3F:
            length = bitstream.read(UI32)
        return cls(id, length)

class _EndShapeRecord(Struct):
    classProvides(IFormat, IStructEvaluateable)
    """
    Don't worry about me ;)
    """
    def create_fields(self):
        yield Zero[6]

EndShapeRecord = _EndShapeRecord()

class Rect(Struct):
    classProvides(IFormat, IStructEvaluateable)
    """
    Rect usually stores bounds or size in the SWF format.
    """
    def __init__(self, XMin=0, YMin=0, XMax=0, YMax=0):
        if XMin > XMax:
            XMin, XMax = XMax, XMin
        if YMin > YMax:
            YMin, YMax = YMax, YMin
        super(Rect, self).__init__(dict(XMin=XMin, YMin=YMin, XMax=XMax, YMax=YMax))

    @byte_aligned
    def create_fields(self):
        yield NBits[5]
        yield Fields("XMin XMax YMin YMax", SB[NBits]) * 20

    def union(self, rect):
        self.XMin = min(self.XMin, rect.XMin)
        self.YMin = min(self.YMin, rect.YMin)
        self.XMax = max(self.XMax, rect.XMax)
        self.YMax = max(self.YMax, rect.YMax)

    def include_point(self, x, y):
        self.XMin = min(x, self.XMin)
        self.YMin = min(y, self.YMin)
        self.XMax = max(x, self.XMax)
        self.YMax = max(y, self.YMax)

class XY(Struct):
    classProvides(IFormat, IStructEvaluateable)
    """
    XY usually stores a position or point in the SWF format.
    """
    def __init__(self, X=0, Y=0):
        super(XY, self).__init__(locals())

    def create_fields(self):
        yield NBits[5]
        yield Fields("X Y", SB[NBits])

class RGB(Struct):
    classProvides(IFormat, IStructEvaluateable)
    """
    RGB stores a color in the SWF format.
    """
    has_alpha = False
    def __init__(self, color):
        super(RGB, self).__init__(dict(color=color & 0xFFFFFF))

    def create_fields(self):
        yield Field("color", UI24)
        if self.has_alpha:
            yield Field("alpha", UI8) * 255

    def __eq__(self, other):
        equals = self.color == other.color and self.has_alpha == other.has_alpha
        if equals and self.has_alpha:
            return self.alpha == other.alpha
        return equals

class RGBA(RGB):
    classProvides(IFormat, IStructEvaluateable)
    """
    RGBA is an RGB object plus alpha.
    """
    has_alpha = True
    def __init__(self, color, alpha=1.0):
        """
        Constructor.

        :param color: something like 0xFFFFFF or 0xADCAFE
        :param alpha: the alpha. a value between 0.0 and 1.0
        """
        super(RGBA, self).__init__(color)
        self.alpha = alpha

class CXForm(Struct):
    classProvides(IFormat, IStructEvaluateable)
    """
    CXForm = ColorTransform
    """
    has_alpha = False
    def __init__(self, rmul=1, gmul=1, bmul=1, radd=0, gadd=0, badd=0):
        super(CXForm, self).__init__(dict(amul=1, aadd=0, **locals()))

    @byte_aligned
    def create_fields(self):
        if self.writing:
            has_add_terms = (Field("radd") != 0) | (Field("gadd") != 0) | (Field("badd") != 0) | (Field("aadd") != 0)
            self.set_local("HasAddTerms", has_add_terms)

            has_mul_terms = (Field("rmul") != 1) | (Field("gmul") != 1) | (Field("bmul") != 1) | (Field("amul") != 1)
            self.set_local("HasMulTerms", has_mul_terms)

        yield Local("HasAddTerms", Bit)
        yield Local("HasMulTerms", Bit)
        yield NBits[4]

        if self.get_local("HasMulTerms", True):
            yield Fields("rmul gmul bmul", UB[NBits]) * 256
            if self.has_alpha:
                yield Field("amul", UB[NBits]) * 256

        if self.get_local("HasAddTerms", True):
            yield Fields("radd gadd badd", SB[NBits])
            if self.has_alpha:
                yield Field("aadd", SB[NBits])

class CXFormWithAlpha(CXForm):
    has_alpha = True
    def __init__(self, rmul=1, gmul=1, bmul=1, amul=1, radd=0, gadd=0, badd=0, aadd=0):
        super(CXFormWithAlpha, self).__init__(rmul, gmul, bmul, radd, gadd, badd)
        self.amul = amul
        self.aadd = aadd

class Matrix(Struct):
    classProvides(IFormat, IStructEvaluateable)
    def __init__(self, a=1, b=0, c=0, d=1, tx=0, ty=0):
        super(Matrix, self).__init__(locals())

    @byte_aligned
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

class Shape(object):
    implements(IStruct)
    def __init__(self):
        self.records = []

        # Edge bounds have no stroke.
        # Shape bounds are visible bounds.
        self.edge_bounds = Rect()
        self.shape_bounds = Rect()

        self.has_scaling = False
        self.has_non_scaling = False

        self.bounds_calculated = False

    def add_shape_record(self, shape):
        self.records.append(shape)
        shape.parent = self
        shape.record_added()

    def as_bitstream(self):
        """
        Serializes this record, according to the following format.

        ================= ============
        Format            Parameter
        ================= ============

        SHAPERECORD[...]  the shape records
        UB[24]            always 0
        ================= ============
        """

        if EndShapeRecord not in self.records:
            self.records.append(EndShapeRecord)

        bits = BitStream()
        bits += self.serialize_style()
        recn = len(self.records)
        for i, record in enumerate(self.records):
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

        self.style = None
        self.last_x, self.last_y = 0, 0
        for record in self.records:
            record.calculate_bounds(self)

        del self.last_x
        del self.last_y
        del self.style
        self.bounds_calculated = True

    def update_bounds(self, delta_x, delta_y):
        self.last_x += delta_x
        self.last_y += delta_y
        self.shape_bounds.include_point(self.last_x, self.last_y)
        self.edge_bounds.include_point(self.last_x, self.last_y)

class ShapeWithStyle(Shape):
    def __init__(self, fills=None, strokes=None):
        super(ShapeWithStyle, self).__init__()
        self.fills = fills or []
        self.fillbits = 0
        self.strokes = strokes or []
        self.linebits = 0

    def add_fill_style(self, style):
        if style and style not in self.fills:
            style.parent = self.fills
            self.fills.append(style)

    def add_line_style(self, style):
        if style and style not in self.strokes:
            style.parent = self.strokes
            self.strokes.append(style)

    def add_shape(self, shape):
        super(ShapeWithStyle, self).add_shape(self, shape)
        try:
            self.fills += shape.fills
            self.strokes += shape.strokes
        except AttributeError:
            pass

    def serialize_style(self):
        bits = BitStream()
        bits += serialize_style_list(self.fills)
        bits += serialize_style_list(self.strokes)
        self.fillbits = nbits(len(self.fills))
        self.linebits = nbits(len(self.strokes))
        bits.write(self.fillbits, UB[4])
        bits.write(self.linebits, UB[4])
        return bits

class LineStyle(Struct):
    classProvides(IFormat, IStructEvaluateable)
    def __init__(self, width=1, color=0, alpha=1.0):
        super(LineStyle, self).__init__(
              dict(width=width, color=RGBA(color, alpha),
                   has_h_scale=False, has_v_scale=False))

    @property
    def index(self):
        try:
            return self.parent.index(self) + 1
        except ValueError:
            return 0

    def create_fields(self):
        yield Field("width", UI16) * 20
        yield Field("color", RGBA)

    def cap_style_logic(self, context, delta):
        dx, dy = delta
        XMin = context.last_x - self.width / 2.0
        YMin = context.last_y - self.width / 2.0
        XMax = XMin + dx + self.width
        YMax = YMin + dy + self.width
        return Rect(XMin, YMin, XMax, YMax)

class LineStyle2(LineStyle):
    classProvides(IFormat, IStructEvaluateable)
    CAPS   = dict(round=0, none=1, square=2)
    JOINTS = dict(round=0, bevel=1, miter=2)
    def __init__(self, width=1, fillstyle=None, pixel_hinting=False, scale_mode=None, caps="round", joints="round", miter_limit=3):
        super(LineStyle2, self).__init__(width, 0, 1.0)
        # This is begging to be rewritten with zope.interface.
        self.color, self.alpha, self.fillstyle = 0, 1, None
        if isinstance(fillstyle, RGBA):
            self.color = fillstyle.color
            self.alpha = fillstyle.alpha
        elif isinstance(fillstyle, RGB):
            self.color = fillstyle.color
        elif isinstance(fillstyle, int):
            if fillstyle > 0xFFFFFF:
                self.color = fillstyle & 0xFFFFFF
                self.alpha = fillstyle >> 6 & 0xFF
            else:
                self.color = fillstyle
        elif isinstance(fillstyle, FillStyleSolidFill):
            self.color = fillstyle.color.color
            self.alpha = fillstyle.color.alpha
        elif isinstance(fillstyle, FillStyle):
            self.fillstyle = fillstyle

        self.pixel_hinting = pixel_hinting
        self.scale_mode = scale_mode

        self.has_h_scale = self.scale_mode in ("normal", "horizontal")
        self.has_v_scale = self.scale_mode in ("normal", "vertical")

        self.caps = caps
        self.joints = joints

        self.miter_limit = miter_limit

    @property
    def index(self):
        try:
            return self.parent.index(self) + 1
        except ValueError:
            return 0

    def create_fields(self):
        yield Field("width", UI16) * 20
        yield Enum(Field("caps",   UB[2]), self.CAPS,   default=0)
        yield Enum(Field("joints", UB[2]), self.JOINTS, default=0)

        if self.writing:
            self.set_local("HasFillStyle", self.fillstyle is not None)
            self.set_local("NoHScale", not self.has_h_scale)
            self.set_local("NoVScale", not self.has_v_scale)

        yield Local("HasFillStyle" , Bit)
        yield Local("NoHScale",      Bit)
        yield Local("NoVScale",      Bit)
        yield Field("pixel_hinting", Bit)
        yield Zero[5] # Reserved
        yield One     # TODO: NoClose
        yield Enum(Field("caps",   UB[2]), self.CAPS,   default=0) # TODO: EndCapStyle

        if self.get_local("HasFillStyle", True):
            yield Field("fillstyle", FillStyle)

        if self.joints == "miter":
            yield Field("miter_limit", UI16)

        if not self.get_local("HasFillStyle", False):
            yield Field("color", UI24)
            yield Field("alpha", UI8) * 255

    def cap_style_logic(self, context, delta):
        # Half thickness (radius of round cap; diameter is thickness)
        off = self.width / 2.0
        dx, dy = delta
        lx, ly = context.last_x, context.last_y

        if self.caps == "round":
            return super(LineStyle2, self).cap_style_logic(context, delta)

        if self.caps == "square":
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

class FillStyle(Struct):
    classProvides(IFormat, IStructEvaluateable)
    @property
    def index(self):
        return self.parent.find(self) + 1

    @classmethod
    def from_bitstream(self, bits):
        cls = {0: FillStyleSolidFill,
               16: FillStyleLinearGradient}.get(bits.read(UI8))
        return Struct.from_bitstream(cls, bits)

    def as_bitstream(self):
        bits = BitStream()
        bits.write(self.TYPE, UI16)
        bits.write(Struct.as_bitstream(self))

class FillStyleSolidFill(FillStyle):
    TYPE = 0
    def __init__(self, color=0, alpha=1.0):
        super(FillStyleSolidFill, self).__init__(dict(color=RGBA(color, alpha)))

    def create_fields(self):
        yield Field("color", RGBA)

class GradRecord(Struct):
    def __init__(self, ratio=0, color=0, alpha=1.0):
        super(GradRecord, self).__init__(dict(ratio=raio, color=RGBA(color, alpha)))

    def create_fields(self):
        yield Field("ratio", UI8)
        yield Field("color", RGBA)

    def __cmp__(self, other):
        return cmp(self.ratio, other.ratio)

    def __eq__(self, other):
        return self.ratio == other.ratio and self.color == other.color

    def __ne__(self, other):
        return not self == other

    def __lt__(self, other):
        return self.ratio < other.ratio

    def __le__(self, other):
        return self.ratio <= other.ratio

    def __gt__(self, other):
        return self.ratio > other.ratio

    def __ge__(self, other):
        return self.ratio >= other.ratio

class Gradient(Struct):
    has_focal = False

    SPREAD = dict(pad=0, reflect=1, repeat=2)
    INTERPOLATION = dict(rgb=0, linear=1)

    def __init__(self, grads, spread="pad", interpolation="rgb"):
        super(Gradient, self).__init__(dict(grads=sorted(grads or []),
            spread=spread, interpolation=interpolation, focalpoint=0))

    def create_fields(self):
        yield Enum(Field("spread", UB[2]), self.SPREAD, default=0)
        yield Enum(Field("interpolation", UB[2]), self.INTERPOLATION, default=0)

        if self.writing:
            self.set_local("NumGrads", len(self.grads))

        yield Local("NumGrads", UB[4])
        yield Field("grads", GradRecord[self.get_local("NumGrads", 1)])

        if self.has_focal:
            yield Field("focalpoint", FIXED8)

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
        super(FillStyleLinearGradientFill).__init__(locals())
        self.matrix = matrix
        self.gradient = gradient

    def create_fields(self):
        yield Field("TYPE", UI8)
        yield Field("matrix", Matrix)
        yield Field("gradient", Gradient)

class StraightEdgeRecord(Struct):
    classProvides(IFormat, IStructEvaluateable)
    def __init__(self, delta_x, delta_y):
        super(StraightEdgeRecord, self).__init__(locals())
        self.bounds_calculated = False

    def record_added(self):
        pass

    def create_fields(self):
        if self.writing:
            GeneralLineFlag = not (self.delta_x == 0 or self.delta_y == 0)
            self.set_local("GeneralLineFlag", GeneralLineFlag)
            self.set_local("VerticalLineFlag", self.delta_x == 0)

        yield One # TypeFlag
        yield One # StraightFlag

        yield NBits[4] - 2
        yield Local("GeneralLineFlag", Bit)

        if self.get_local("GeneralLineFlag", True):
            yield Fields("delta_x delta_y", SB[NBits]) * 20

        if not self.get_local("GeneralLineFlag", False):
            yield Local("VerticalLineFlag", Bit)

            if self.get_local("VerticalLineFlag", True):
                yield Field("delta_y", SB[NBits]) * 20

            if not self.get_local("VerticalLineFlag", False):
                yield Field("delta_x", SB[NBits]) * 20

    def calculate_bounds(self, context):
        if context.style:
            context.shape_bounds.union(context.style.cap_style_logic(context, (self.delta_x, self.delta_y)))

        context.update_bounds(self.delta_x, self.delta_y)

class CurvedEdgeRecord(Struct):
    classProvides(IFormat, IStructEvaluateable)
    def __init__(self, controlx, controly, anchorx, anchory):
        super(CurvedEdgeRecord, self).__init__(locals())

    def record_added(self):
        pass

    def create_fields(self):
        yield One # TypeFlag
        yield Zero # StraightFlag

        yield NBits[4] + 2
        yield Fields("controlx controly anchorx anchory", SB[NBits]) * 20

    def _get_x(self, t):
        return self.controlx*2*(1-t)*t + self.anchorx*t*t

    def _get_y(self, t):
        return self.controly*2*(1-t)*t + self.anchory*t*t

    def _get_p(self, t):
        return (self._get_x(t), self._get_y(t))

    def calculate_bounds(self, context):
        """
        CurvedEdgeRecord Bounds
        Formulas somewhat based on
        http://code.google.com/p/bezier/source/browse/trunk/bezier/src/flash/geom/Bezier.as
        Maths here may be incorrect

        extremumX = last.x - 2 * control.x + anchor.x
        extremumX = last.x - 2 * (controlDeltaX + last.x) + anchorDeltaX - last.x
        extremumX = (last.x - last.x) - 2 * (controlDeltaX + last.x) + anchorDeltaX
        extremumX = -2*(controlDeltaX + last.x) + anchorDeltaX

        For the case of last.[xy] = 0, we can use the formula below.
        """

        x = -2 * self.controlx + self.anchorx
        t = -self.controlx / x
        p = self._get_x(t)

        union = Rect(0, 0, 0, 0)

        if t <= 0 or t >= 1:
            union.XMin = context.last_x + min(self.anchorx, 0)
            union.XMax = union.XMin + max(self.anchorx, 0)
        else:
            union.XMin = min(p, 0, self.anchorx + context.last_x)
            union.XMax = union.XMin + max(p - context.last_y, 0, self.anchorx)

        y = -2 * self.controly + self.anchory
        t = -self.controly / y
        p = self._get_y(t)

        if t <= 0 or t >= 1:
            union.YMin = context.last_y + min(self.anchory, 0)
            union.YMax = union.YMin + max(self.anchory, 0)
        else:
            union.YMin = min(p, 0, self.anchory + context.last_y)
            union.YMax = union.YMin + max(p - context.last_x, 0, self.anchory)

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
        end_cap_rect   = style.cap_style_logic(context.last, slope2)
        start_cap_rect = style.cap_style_logic(context.last, slope1)

        context.shape_bounds.union(union, start_cap_rect, end_cap_rect)
        context.edge_bounds.union(union)

        context.last_x += self.anchorx
        context.last_y += self.anchory

class StyleChangeRecord(Struct):
    classProvides(IFormat, IStructEvaluateable)
    def __init__(self, delta_x, delta_y, linestyle=None,
                 fillstyle0=None, fillstyle1=None,
                 fillstyles=None, linestyles=None):
        super(StyleChangeRecord, self).__init__(locals())

    def record_added(self):
        self.parent.add_line_style(self.linestyle)
        self.parent.add_fill_style(self.fillstyle0)
        self.parent.add_fill_style(self.fillstyle1)

    def create_fields(self):
        if self.writing:
            from fusion.swf.tags import DefineShape
            new_styles = (DefineShape._current_variant > 1) and bool(self.linestyles or self.fillstyles)

            self.set_local("HasNewStyles", new_styles)
            self.fillstyles = self.fillstyles or []
            self.linestlyes = self.linestyles or []

            self.set_local("FillStyleCount", len(self.fillstyles or []))
            self.set_local("FillStyleBits", nbits(len(self.fillstyles or [])))
            self.set_local("LineStyleCount", len(self.linestyles or []))
            self.set_local("LineStyleBits", nbits(len(self.linestyles or [])))

            self.set_local("HasLineStyle", bool(self.linestyle))
            self.set_local("LineStyleIndex", self.linestyle.index if self.linestyle else 0)

            self.set_local("HasFillStyle1", bool(self.fillstyle1))
            self.set_local("FillStyle1Index", self.fillstyle1.index if self.fillstyle1 else 0)

            self.set_local("HasFillStyle0", bool(self.fillstyle0))
            self.set_local("FillStyle0Index", self.fillstyle0.index if self.fillstyle0 else 0)
            self.set_local("HasMoveTo", bool(self.delta_x or self.delta_y))

        yield Zero # TypeFlag
        yield Local("HasNewStyles", Bit)
        yield Local("HasLineStyle", Bit)
        yield Local("HasFillStyle1", Bit)
        yield Local("HasFillStyle0", Bit)
        yield Local("HasMoveTo", Bit)

        if self.get_local("HasMoveTo", True):
            yield NBits[5]
            yield Fields("delta_x delta_y", SB[NBits]) * 20

        if self.get_local("HasFillStyle0", True):
            yield Local("FillStyle0Index", UB[self.parent.fillbits])
            if self.reading:
                self.fillstyle0 = self.parent.fills[self.get_local("FillStyle0Index")]

        if self.get_local("HasFillStyle1", True):
            yield Local("FillStyle1Index", UB[self.parent.fillbits])
            if self.reading:
                self.fillstyle1 = self.parent.fills[self.get_local("FillStyle1Index")]

        if self.get_local("HasLineStyle", True):
            yield Local("LineStyleIndex", UB[self.parent.linebits])
            if self.reading:
                self.linestyle = self.parent.fills[self.get_local("LineStyleIndex")]

        if self.get_local("HasNewStyles", True):
            yield Local("FillStyleCount", UI8) & 0xFF
            if self.get_local("FillStyleCount", 0xFF) & 0xFF == 0xFF:
                yield Local("FillStyleCount", UI16)
            yield Field("fillstyles", FillStyle)

            yield Local("LineStyleCount", UI8) & 0xFF
            if self.get_local("LineStyleCount", 0xFF) & 0xFF == 0xFF:
                yield Local("LineStyleCount", UI16)
            # TODO: SWF version
            yield Field("linestyles", LineStyle2)

            yield Local("FillStyleBits", UB[4])
            yield Local("LineStyleBits", UB[4])

            if self.writing:
                self.parent.fills   = self.fillstyles or []
                self.parent.strokes = self.linestyles or []

    def calculate_bounds(self, context):
        if self.linestyle:
            context.style = self.linestyle
            # XXX
            # context.has_h_scale |= self.linestyle.has_h_scale
            # context.has_v_scale |= self.linestyle.has_v_scale

        context.shape_bounds.union(context.style.cap_style_logic(context, (self.delta_x, self.delta_y)))
        context.update_bounds(self.delta_x, self.delta_y)

    ## def as_bitstream(self):
    ##     bits = BitStream()
    ##     if self.fillstyle0 is not None and self.fillstyle1 is not None and \
    ##            self.fillstyle0.parent != self.fillstyle1.parent:
    ##         raise ValueError("fillstyle0 and fillstyle1 do not have the same parent!")

    ##     fsi0 = 0 if self.fillstyle0 is None else self.fillstyle0.index
    ##     fsi1 = 0 if self.fillstyle1 is None else self.fillstyle1.index
    ##     lsi  = 0 if self.linestyle  is None else self.linestyle.index

    ##     fbit = 0 if self.fillstyle0 is None else nbits(len(self.fillstyle0.parent))
    ##     lbit = 0 if self.linestyle  is None else nbits(len(self.linestyle.parent))

    ##     from fusion.swf.tags import DefineShape

    ##     new_styles = ((DefineShape._current_variant > 1) and
    ##                  ((self.linestyles != None and len(self.linestyles) > 0) or
    ##                   (self.fillstyles != None and len(self.fillstyles) > 0)))

    ##     bits.write_bit(False)       # TypeFlag
    ##     bits.write_bit(new_styles)  # StateNewStyles
    ##     bits.write_bit(lsi  > 0)    # StateLineStyle
    ##     bits.write_bit(fsi0 > 0)    # StateFillStyle0
    ##     bits.write_bit(fsi1 > 0)    # StateFillStyle1

    ##     move_flag = self.delta_x != 0 or self.delta_y != 0

    ##     if move_flag:
    ##         bits += XY(self.delta_x, self.delta_y)

    ##     if fsi0 > 0:  bits.write_int_value(fsi0, fbit) # FillStyle0
    ##     if fsi1 > 0:  bits.write_int_value(fsi1, fbit) # FillStyle1
    ##     if lsi  > 0:  bits.write_int_value(lsi,  lbit) # LineStyle

    ##     if new_styles:
    ##         bits += serialize_style_list(self.fillstyles) # FillStyles
    ##         bits += serialize_style_list(self.linestyles) # LineStyles

    ##         bits.write_int_value(nbits(len(self.fillstyles)), 4) # FillBits
    ##         bits.write_int_value(nbits(len(self.linestyles)), 4) # LineBits

    ##     return bits

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


