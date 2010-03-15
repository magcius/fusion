
from zope.interface import implements, classProvides

from mech.fusion.bitstream.interfaces import IStruct, IStructClass
from mech.fusion.bitstream.formats import CString, Bit, Zero
from mech.fusion.bitstream.flash_formats import SI16, UI16, UI32
from mech.fusion.swf.records import (RecordHeader, ShapeWithStyle,
                                     Matrix, CXForm, RGB, Rect)
from mech.fusion.avm1.actions import Block
from mech.fusion.util import BitStream
from mech.fusion.avm2.abc_ import AbcFile

from collections import defaultdict

class complexdefaultdict(defaultdict):
    def __missing__(self, key):
        self[key] = self.default_factory(key)

class UnknownSwfTag(object):
    """
    Used for both SWF tags not yet implemented by Fusion
    and unknown SWF tags.
    """
    TAG_MIN_VERSION = -1
    TAG_TYPE = -1
    TAG_REFERENCE = [
        "End",                  # 00
        "ShowFrame",            # 01
        "DefineShape",          # 02
        "FreeCharacter",        # 03
        "PlaceObject",          # 04
        "RemoveObject",         # 05
        "DefineBits",           # 06
        "DefineButton",         # 07
        "JPEGTables",           # 08
        "SetBackgroundColor",   # 09
        "DefineFont",           # 10
        "DefineText",           # 11
        "DoAction",             # 12
        "DefineFontInfo",       # 13
        "DefineSound",          # 14
        "StartSound",           # 15
        "StopSound",            # 16
        "DefineButtonSound",    # 17
        "SoundStreamHead",      # 18
        "SoundStreamBlock",     # 19
        "DefineBitsLossless",   # 20
        "DefineBitsJPEG2",      # 21
        "DefineShape2",         # 22
        "DefineButtonCxform",   # 23
        "Protect",              # 24
        "PathsArePostScript",   # 25
        "PlaceObject2",         # 26
        "27 (invalid)",         # 27
        "RemoveObject2",        # 28
        "SyncFrame",            # 29
        "30 (invalid)",         # 30
        "FreeAll",              # 31
        "DefineShape3",         # 32
        "DefineText2",          # 33
        "DefineButton2",        # 34
        "DefineBitsJPEG3",      # 35
        "DefineBitsLossless2",  # 36
        "DefineEditText",       # 37
        "DefineVideo",          # 38
        "DefineSprite",         # 39
        "NameCharacter",        # 40
        "ProductInfo",          # 41
        "DefineTextFormat",     # 42
        "FrameLabel",           # 43
        "DefineBehavior",       # 44
        "SoundStreamHead2",     # 45
        "DefineMorphShape",     # 46
        "FrameTag",             # 47
        "DefineFont2",          # 48
        "GenCommand",           # 49
        "DefineCommandObj",     # 50
        "CharacterSet",         # 51
        "FontRef",              # 52
        "DefineFunction",       # 53
        "PlaceFunction",        # 54
        "GenTagObject",         # 55
        "ExportAssets",         # 56
        "ImportAssets",         # 57
        "EnableDebugger",       # 58
        "DoInitAction",         # 59
        "DefineVideoStream",    # 60
        "VideoFrame",           # 61
        "DefineFontInfo2",      # 62
        "DebugID",              # 63
        "EnableDebugger2",      # 64
        "ScriptLimits",         # 65
        "SetTabIndex",          # 66
        "DefineShape4",         # 67
        "DefineMorphShape2",    # 68
        "FileAttributes",       # 69
        "PlaceObject3",         # 70
        "ImportAssets2",        # 71
        "DoABCDefine",          # 72
        "73 (invalid)",         # 73
        "74 (invalid)",         # 74
        "75 (invalid)",         # 75
        "SymbolClass",          # 76
        "77 (invalid)",         # 77
        "78 (invalid)",         # 78
        "79 (invalid)",         # 79
        "80 (invalid)",         # 80
        "81 (invalid)",         # 81
        "DoABC",                # 82
        "83 (invalid)"          # 83
    ]
    def __init__(self, tag):
        self.tag = tag
        self.name = self.TAG_REFERENCE[tag]

    def __repr__(self):
        return "<%s (%#X) (Unknown Tag)>" % (self.name, self.tag)
    
    def parse_inner(self, bitstream):
        self.data = bitstream.read_string()
        return self
    
REVERSE_INDEX = complexdefaultdict(UnknownSwfTag)

class SwfTagMeta(type):
    def __init__(cls, name, bases, dct):
        if name != 'SwfTag' and 'TAG_TYPE' in dct:
            REVERSE_INDEX[dct['TAG_TYPE']] = cls
            REVERSE_INDEX[name] = cls

class SwfTag(object):
    """
    The base class for defining SWF tags.

    You should never instantiate this class directly,
    instead use one of its subclasses.
    """

    implements(IStruct)
    classProvides(IStructClass)

    __metaclass__ = SwfTagMeta

    TAG_TYPE = -1
    TAG_MIN_VERSION = -1

    def serialize_data(self):
        """
        Return the internal data of a tag.

        This should not include a RecordHeader.
        """
        return ""

    def __repr__(self):
        repr_inner = self.__repr_inner__()
        if repr_inner:
            repr_inner = " (%s)" % (repr_inner)
        return "<%s (%#X)%s>" % (type(self).__name__, self.TAG_TYPE, repr_inner)

    def __repr_inner__(self):
        return ""
    
    def as_bitstream(self):
        """
        Return a bytestring containing the appropriate structures of the tag.
        """
        data = self.serialize_data()
        return RecordHeader(self.TAG_TYPE, len(data)).as_bitstream().serialize() + data

    @classmethod
    def from_bitstream(cls, bitstream):
        offset = bitstream.cursor//8
        recordheader = RecordHeader.from_bitstream(bitstream)
        cls = REVERSE_INDEX[recordheader.type]
        if not hasattr(cls, "parse_inner"):
            cls = UnknownSwfTag(recordheader.type)
        inst = cls.parse_inner(bitstream.read(BitStream[recordheader.length*8]))
        inst.length = recordheader.length
        inst.offset = offset
        return inst

class SetBackgroundColor(SwfTag):
    TAG_TYPE = 9
    TAG_MIN_VERSION = 1

    def __init__(self, color):
        """
        Constructor.

        :param color: the color to set the background to
        :type color:  an integer, like 0xCCCCCC
        """
        self.color = RGB(color)

    def serialize_data(self):
        """
        Serailizes this tag, according to the following format.
        
        =======  =========
        Format   Parameter
        =======  =========
        RGB      color
        =======  =========
        """
        return self.color.as_bitstream().serialize()

    def __repr_inner__(self):
        return "color=%s" % (self.color,)

    @classmethod
    def parse_inner(cls, bits):
        return cls(RGB.from_bitstream(bits).color)

class DoAction(SwfTag, Block):
    TAG_TYPE = 12
    TAG_MIN_VERSION = 3

    def __init__(self):
        """
        Constructor.
        """
        Block.__init__(self, None, True)

    def serialize_data(self):
        """
        Serailizes this tag, according to the following format.
        
        ============  ===========
        Format        Parameter
        ============  ===========
        ACTION[...]   the actions
        ============  ===========
        """
        return Block.serialize(self)

    

class DoABC(SwfTag, AbcFile):
    TAG_TYPE = 82
    TAG_MIN_VERSION = 9

    def __init__(self, name="Mecheye Fusion", flags=0):
        """
        Constructor.

        :param name: the name for the ABC Block
        :type name:  a string
        :param flags: the flags for the ABC Block
                      currently, that can be 1, which
                      lazily inits the ABC Block
        """
        AbcFile.__init__(self)
        self.name  = name
        self.flags = flags

    @classmethod
    def parse_inner(cls, bitstream):
        flags = bitstream.read(UI32)
        name  = bitstream.read(CString)
        abc   = AbcFile.from_bitstream(bitstream)
        # XXX
        instance = cls(name, flags)
        for name in dir(abc):
            if not name.startswith("__"):
                setattr(instance, name, getattr(abc, name))
        return instance
    
    def serialize_data(self):
        """
        Serializes this tag, according to the following format.

        =======  =========
        Format   Parameter
        =======  =========
        U[32]    flags
        CSTRING  name
        ABC      abc file
        =======  =========
        """
        bits = BitStream()
        bits.write(self.flags, UI32)
        bits.write(self.name, CString)
        return bits.serialize() + AbcFile.serialize(self)

    def __repr_inner__(self):
        return "name=%s, flags=%s" % (self.name, bin(self.flags)[2:])

class DoABCDefine(SwfTag, AbcFile):
    TAG_TYPE = 72
    TAG_MIN_VERSION = 9

    name = "DoABCDefine"
    
    def __init__(self):
        """
        Constructor.
        """
        AbcFile.__init__(self)
    
    def serialize_data(self):
        """
        Serializes this tag, according to the following format.

        =======  ==========
        Format   Parameter
        =======  ==========
        ABC      abc file
        =======  ==========
        """
        return AbcFile.serialize(self)

class SymbolClass(SwfTag):
    TAG_TYPE = 76
    TAG_MIN_VERSION = 9

    def __init__(self, symbols):
        """
        Constructor.

        :param symbols: a dict mapping of character ids to class names
        :type symbols: a dict
        """
        self.symbols = symbols

    def serialize_data(self):
        """
        Serializes this tag, according to the following format.
        
        =======  =============
        Format   Parameter
        =======  =============
        U[16]    character id
        CSTRING  classsname
        =======  =============
        """
        bits = BitStream()
        bits.write_int_value(len(self.symbols), 16, endianness="<")
        for char_id, classname in self.symbols.iteritems():
            bits.write_int_value(char_id, 16, endianness="<")
            bits.write_cstring(classname)
        return bits.serialize()

    @classmethod
    def parse_inner(cls, bits):
        length = bits.read_int_value(16, endianness="<")
        symbols = {}
        for i in xrange(length):
            char_id = bits.read_int_value(16)
            symbols[char_id] = bits.read_cstring()
        return cls(symbols)

class DefineShape(SwfTag):
    TAG_TYPE = 2
    TAG_MIN_VERSION = 1
    TAG_VARIANT = 1
    
    _current_variant = None
    
    def __init__(self, shapes=None, characterid=None):
        """
        Constructor.

        :param shapes:
        """
        self.shapes = ShapeWithStyle() if shapes is None else shapes
        self.characterid = characterid

    def serialize_data(self):
        self.shapes.calculate_bounds()
        DefineShape._current_variant = self.TAG_VARIANT
        
        bits = BitStream()
        bits.write_int_value(self.characterid, 16, endianness="<")
        
        bits += self.shapes.shape_bounds
        bits += self.shapes
        
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
        
        bits += self.shapes.shape_bounds # ShapeBounds Rect
        bits += self.shapes.edge_bounds  # EdgeBounds Rect
        
        bits.zero_fill(6) # Reserved

        bits.write_bit(self.shapes.has_scaling)     # UsesNonScalingStrokes
        bits.write_bit(self.shapes.has_non_scaling) # UsesScalingStrokes
        
        bits += self.shapes # ShapeWithStyle
        
        DefineShape._current_variant = None

        return bits.serialize()

class ShowFrame(SwfTag):
    TAG_TYPE = 1
    TAG_MIN_VERSION = 1

    @classmethod
    def parse_inner(cls, bitstream):
        return cls()

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

    def __repr_inner__(self):
        return "hasMetadata=%s, useAS3=%s, useNetwork=%s" % (self.hasMetadata, self.useAS3, self.useNetwork)
    
    def serialize_data(self):
        bits = BitStream()
        bits.write(Zero[3])
        bits.write(self.hasMetadata)
        bits.write(self.useAS3)
        bits.write(Zero[2])
        bits.write(self.useNetwork)
        bits.write(Zero[24])
        
        return bits.serialize()

    @classmethod
    def parse_inner(cls, bits):
        fa = cls()
        bits.cursor += 3
        fa.hasMetadata = bits.read(Bit)
        fa.useAS3      = bits.read(Bit)
        bits.cursor += 2
        fa.useNetwork  = bits.read(Bit)
        bits.cursor += 24
        return fa
    
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
        
        bits += self.transform
        bits += self.colortransform
        
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
            bits += self.transform
        if self.colortransform is not None:
            bits += self.colortransform
        
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

    @classmethod
    def parse_inner(cls, bits):
        CharacterID = bits.read(UI16)
        Bounds      = Rect.from_bitstream(bits)
        
        HasText       = bits.read(Bit)
        WordWrap      = bits.read(Bit)
        Multiline     = bits.read(Bit)
        Password      = bits.read(Bit)
        ReadOnly      = bits.read(Bit)
        HasColor      = bits.read(Bit)
        HasMaxLength  = bits.read(Bit)
        HasFont       = bits.read(Bit)

        HasFontClass  = bits.read(Bit)
        AutoSize      = bits.read(Bit)
        HasLayout     = bits.read(Bit)
        NotSelectable = bits.read(Bit)
        HasBorder     = bits.read(Bit)
        WasStatic     = bits.read(Bit)
        IsHTML        = bits.read(Bit)
        HasOutlines   = bits.read(Bit)

        FontID    = None
        FontClass = None
        FontSize  = None
        
        Color     = None
        MaxLength = None
        Layout    = None
        Text      = None
        
        if HasFont:      FontID    = bits.read(UI16)
        if HasFontClass: FontClass = bits.read(CString)
        if HasFont:      FontSize  = bits.read(UI16)

        if HasColor:     Color     = RGB.from_bitstream(bits)
        if HasMaxLength: MaxLength = bits.read(UI16)
        if HasLayout:    Layout    = NonExistant.parse(bits)

        Variable         = bits.read(CString)
        if HasText: Text = Text.read(CString)

        inst = cls(Bounds, Variable, Text, ReadOnly, IsHTML, WordWrap,
                   Multiline, Password, AutoSize, not NotSelectable,
                   HasBorder, Color, MaxLength, Layout, FontID, FontSize,
                   FontClass, CharacterID)
        inst.wasstatic = WasStatic
        inst.outlines  = HasOutlines
        return inst

    def serialize_data(self):
        bits = BitStream()
        bits.write(self.characterid, SI16)
        
        bits += self.rect
        bits.flush()
        
        flags = BitStream()
        flags.write(self.text != "")
        flags.write(self.wordwrap)
        flags.write(self.multiline)
        flags.write(self.password)
        flags.write(self.readonly)
        flags.write(self.color is not None)
        flags.write(self.maxlength is not None)
        flags.write(self.font is not None)
        
        flags.write(self.fontclass is not None)
        flags.write(self.autosize)
        flags.write(self.layout is not None)
        flags.write(not self.selectable)
        flags.write(self.border)
        flags.write(self.wasstatic)
        flags.write(self.isHTML)
        flags.write(self.outlines)

        bits += flags
        
        if self.font is not None:
            bits.write(self.font.id, UI16) # Doesn't exist yet.
        if self.fontclass is not None:
            bits.write(self.fontclass, CString)
        if self.font is not None:
            bits.write(self.size, UI16)
        
        if self.color is not None:
            bits += self.color
        if self.maxlength is not None:
            bits.write(self.maxlength, UI16)
        if self.layout is not None:
            bits += self.layout # Doesn't exist yet.

        bits.write_cstring(self.variable)
        
        if self.text != "":
            bits.write_cstring(self.text)
        return bits.serialize()
        
class End(SwfTag):

    TAG_TYPE = 0
    TAG_MIN_VERSION = 0
    
    def serialize(self):
        return "\0\0"

    @classmethod
    def parse_inner(cls, bits):
        bits.cursor += 16
        return cls()
