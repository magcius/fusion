
import struct

from mech.fusion.swf.records import RecordHeader, ShapeWithStyle, Matrix, CXForm, RGB
from mech.fusion.avm1.actions import Block
from mech.fusion.util import BitStream
from mech.fusion.avm2.abc_ import AbcFile

class SwfTag(object):

    TAG_TYPE = -1
    TAG_MIN_VERSION = -1
    REVERSE_INDEX = {}
    
    def __init__(self):
        SwfTag.REVERSE_INDEX[self.TAG_TYPE] = self
    
    def serialize_data(self):
        return ""
    
    def serialize(self):
        data = self.serialize_data()
        return RecordHeader(self.TAG_TYPE, len(data)).serialize().serialize() + data

    def parse_data(self, bitstream):
        pass

    def parse(self, bitstream):
        recordheader = RecordHeader()
        

class SetBackgroundColor(SwfTag):
    
    TAG_TYPE = 9
    TAG_MIN_VERSION = 1

    def __init__(self, color):
        self.color = RGB(color)

    def serialize_data(self):
        return self.color.serialize().serialize()

class DoAction(SwfTag, Block):

    TAG_TYPE = 12
    TAG_MIN_VERSION = 3

    def __init__(self):
        Block.__init__(self, None, True)

    def serialize_data(self):
        return Block.serialize(self)

class DoABC(SwfTag, AbcFile):

    TAG_TYPE = 82
    TAG_MIN_VERSION = 9

    def __init__(self, name="Mecheye Fusion", flags=0):
        AbcFile.__init__(self)
        self.name  = name
        self.flags = flags
    
    def serialize_data(self):
        bits = BitStream()
        bits.write_int_value(self.flags, 32)
        bits.write_cstring(self.name)
        return bits.serialize() + AbcFile.serialize(self)

class DoABCDefine(SwfTag, AbcFile):

    TAG_TYPE = 72
    TAG_MIN_VERSION = 9

    def __init__(self):
        AbcFile.__init__(self)
    
    def serialize_data(self):
        return AbcFile.serialize(self)
    
class SymbolClass(SwfTag):

    TAG_TYPE = 76
    TAG_MIN_VERSION = 9

    def __init__(self, symbols):
        self.symbols = symbols

    def serialize_data(self):
        bits = BitStream()
        bits.write_int_value(len(self.symbols), 16, endianness="<")
        for char_id, classname in self.symbols.iteritems():
            bits.write_int_value(char_id, 16, endianness="<")
            bits.write_cstring(classname)
        return bits.serialize()

class DefineShape(SwfTag):

    TAG_TYPE = 2
    TAG_MIN_VERSION = 1
    TAG_VARIANT = 1
    
    _current_variant = None
    
    def __init__(self, shapes=None, characterid=None):
        self.shapes = ShapeWithStyle() if shapes is None else shapes
        self.characterid = characterid

    def serialize_data(self):
        self.shapes.calculate_bounds()
        DefineShape._current_variant = self.TAG_VARIANT
        
        bits = BitStream()
        bits.write_int_value(self.characterid, 16, endianness="<")
        
        bits += self.shapes.shape_bounds.serialize()
        bits += self.shapes.serialize()
        
        DefineShape._current_variant = None
        return bits

class DefineShape2(DefineShape):
    TAG_TYPE = 22
    TAG_MIN_VERSION = 2
    TAG_VARIANT = 2

class DefineShape3(DefineShape):
    TAG_TYPE = 32
    TAG_MIN_VERSION = 32
    TAG_VARIANT = 3

class DefineShape4(DefineShape):
    
    TAG_TYPE = 83
    TAG_MIN_VERSION = 8
    TAG_VARIANT = 4

    def serialize_data(self):
        self.shapes.calculate_bounds()
        DefineShape._current_variant = self.TAG_VARIANT
        
        bits = BitStream()
        bits.write_int_value(self.characterid, 16, endianness="<") # Shape ID
        
        bits += self.shapes.shape_bounds.serialize() # ShapeBounds Rect
        bits += self.shapes.edge_bounds.serialize()  # EdgeBounds Rect
        
        bits.zero_fill(6) # Reserved

        bits.write_bit(self.shapes.has_scaling)     # UsesNonScalingStrokes
        bits.write_bit(self.shapes.has_non_scaling) # UsesScalingStrokes
        
        bits += self.shapes.serialize() # ShapeWithStyle
        
        DefineShape._current_variant = None

        return bits.serialize()

class ShowFrame(SwfTag):
    TAG_TYPE = 1
    TAG_MIN_VERSION = 1

class FileAttributes(SwfTag):
    
    TAG_TYPE = 69
    TAG_MIN_VERSION = 1
    
    def __init__(self, hasMetadata=False, useAS3=True, useNetwork=False):
        """
        Constructor.
        :param hasMetadata:	True if the SWF contains a metadata tag.
        :param useAS3:		True if the SWF uses ActionScript 3.0.
        :param useNetwork:	If true the SWF is given network access when
                                loaded locally.  If false the SWF is given local access.
        """
        self.hasMetadata = hasMetadata
        self.useAS3      = useAS3
        self.useNetwork  = useNetwork

    def serialize_data(self):
        bits = BitStream()
        bits.zero_fill(3)
        bits.write_bit(self.hasMetadata)
        bits.write_bit(self.useAS3)
        bits.zero_fill(2)
        bits.write_bit(self.useNetwork)
        bits.zero_fill(24)
        
        return bits.serialize()
    
class PlaceObject(SwfTag):
    
    TAG_TYPE = 4
    TAG_MIN_VERSION = 1

    def __init__(self, shapeid, depth, transform=None, colortransform=None):
        self.shapeid = shapeid
        self.depth = depth
        self.transform = transform or Matrix()
        self.colortransform = colortransform or CXForm()

    def serialize_data(self):
        bits = BitStream()
        bits.write_int_value(self.shapeid, 16, endianness="<")
        bits.write_int_value(self.depth, 16, endianness="<")
        
        bits += self.transform.serialize()
        bits += self.colortransform.serialize()
        
        return bits.serialize()

class PlaceObject2(PlaceObject):

    TAG_TYPE = 26
    TAG_MIN_VERSION = 3

    def __init__(self, shapeid, depth, name=None, transform=None, colortransform=None):
        self.shapeid = shapeid
        self.depth = depth
        self.name = name
        self.transform = transform
        self.colortransform = colortransform
    
    def serialize_data(self):
        bits = BitStream()
        bits.write_bit(False) # HasClipActions
        bits.write_bit(False) # HasClipDepth
        bits.write_bit(self.name is not None) # HasName
        bits.write_bit(False) # HasRatio
        bits.write_bit(self.colortransform is not None)
        bits.write_bit(self.transform is not None)
        bits.write_bit(True)  # HasCharacter
        bits.write_bit(False) # FlagMove
        
        bits.write_int_value(self.depth, 16, endianness="<")
        bits.write_int_value(self.shapeid, 16, endianness="<")
        
        if self.name is not None:
            bits.write_cstring(self.name)
        
        if self.transform is not None:
            bits += self.transform.serialize()
        if self.colortransform is not None:
            bits += self.colortransform.serialize()
        
        return bits.serialize()

class DefineEditText(SwfTag):

    TAG_TYPE = 37
    TAG_MIN_VERSION = 4
    
    def __init__(self, rect, variable, text="", readonly=True, isHTML=False,
                 wordwrap=False, multiline=True, password=False, autosize=True,
                 selectable=True, border=False, color=None, maxlength=None,
                 layout=None, font=None, size=12, fontclass=None, characterid=None):
        
        self.rect        = rect
        self.variable    = variable
        self.text        = text
        self.readonly    = readonly
        self.isHTML      = isHTML
        self.wordwrap    = wordwrap
        self.multiline   = multiline
        self.password    = password
        self.autosize    = autosize
        self.selectable  = selectable
        self.border      = border
        self.color       = color
        self.maxlength   = maxlength
        self.layout      = layout
        self.font        = font
        self.size        = size
        self.fontclass   = fontclass
        self.characterid = characterid

        self.outlines    = False
        self.wasstatic   = False

    def serialize_data(self):
        bits = BitStream()
        bits.write_int_value(self.characterid, 16, endianness="<")

        print bits
        bits += self.rect.serialize()
        print bits
        bits.flush()
        print bits
        
        flags = BitStream()
        flags.write_bit(self.text != "")
        flags.write_bit(self.wordwrap)
        flags.write_bit(self.multiline)
        flags.write_bit(self.password)
        flags.write_bit(self.readonly)
        flags.write_bit(self.color is not None)
        flags.write_bit(self.maxlength is not None)
        flags.write_bit(self.font is not None)
        
        flags.write_bit(self.fontclass is not None)
        flags.write_bit(self.autosize)
        flags.write_bit(self.layout is not None)
        flags.write_bit(not self.selectable)
        flags.write_bit(self.border)
        flags.write_bit(self.wasstatic)
        flags.write_bit(self.isHTML)
        flags.write_bit(self.outlines)
        
        bits += flags
        print flags
        print bits
        
        if self.font is not None:
            bits.write_int_value(self.font.id, 16, endianness="<") # Doesn't exist yet.
        if self.fontclass is not None:
            bits.write_cstring(self.fontclass)
        if self.font is not None:
            bits.write_int_value(self.size, 16, endianness="<")
            
        if self.color is not None:
            bits += self.color.serialize()
        if self.maxlength is not None:
            bits.write_int_value(self.maxlength, 16, endianness="<")
        if self.layout is not None:
            bits += self.layout.serialize() # Doesn't exist yet.
            
        bits.write_cstring(self.variable)

        if self.text != "":
            bits.write_cstring(self.text)
        
        return bits.serialize()
        
class End(SwfTag):

    TAG_TYPE = 0
    TAG_MIN_VERSION = 0
    
    def serialize(self):
        return "\0\0"

