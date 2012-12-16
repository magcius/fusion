
import os

from zope.interface import implements, classProvides
from zope.component import provideAdapter

from fusion.bitstream.bitstream import BitStream
from fusion.bitstream.interfaces import IStruct, IStructClass
from fusion.bitstream.formats import CString, Bit, Zero
from fusion.bitstream.flash_formats import UI16, UI32

from fusion.swf.interfaces import ISwfPart, IPlaceable
from fusion.swf.records import (RecordHeader, ShapeWithStyle,
                                     Matrix, CXFormWithAlpha, RGB, Rect)

from fusion.avm2.abc_ import AbcFile

class SwfTagTooNew(Exception): pass
class SwfTagNotAllowed(Exception): pass

class SwfTag(object):
    """
    The base class for defining SWF tags.

    You should never instantiate this class directly,
    instead use one of its subclasses.
    """

    implements(IStruct, ISwfPart)
    classProvides(IStructClass)

    id = -1
    min_version = -1

    def add_to(self, data):
        if data.version < self.min_version:
            raise SwfTagTooNew("%r requires a minimum version of %d. Your SWF v"
                "ersion is %d" % (self, self.min_version, data.version))
        data.add_raw_tag(self)

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
        return "<%s (%#X)%s>" % (type(self).__name__, self.id, repr_inner)

    def __repr_inner__(self):
        return ""

    def serialize(self):
        """
        Return a bytestring containing the appropriate structures of the tag.
        """
        data = self.serialize_data()
        rh = RecordHeader(self.id, len(data)).as_bitstream()
        return rh.serialize() + data

    @classmethod
    def from_bitstream(cls, bitstream):
        offset = bitstream.tell() // 8
        recordheader = RecordHeader.from_bitstream(bitstream)
        bits = bitstream.read(BitStream[recordheader.length*8])
        inst = cls.parse_inner(bits)
        inst.length = recordheader.length
        inst.offset = offset
        return inst

class SetBackgroundColor(SwfTag):
    id = 9
    min_version = 1

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

class EnableDebugger2(SwfTag):
    id = 64
    min_version = 1

    def __init__(self, password=""):
        """
        Constructor.

        :param password: MD5-encrypted password
        """
        self.password = password

    def serialize_data(self):
        """
        Serailizes this tag, according to the following format.

        ========  =========
        Format    Parameter
        ========  =========
        Reserved  UI16 - 0
        Password  MD5
        ========  =========
        """
        bits = BitStream()
        bits.write(0, UI16)
        bits.write(self.password, CString)
        return bits.serialize()

    @classmethod
    def parse_inner(cls, bits):
        bits.read(Zero[6])
        return cls(bits.read(CString))

class DoABC(SwfTag):
    id = 82
    min_version = 9

    def __init__(self, name="Mecheye Fusion", abc=None, flags=0):
        """
        Constructor.

        :param name: the name for the ABC Block
        :type name:  a string
        :param flags: the flags for the ABC Block
                      currently, that can be 1, which
                      lazily inits the ABC Block
        """
        self.abc   = abc or AbcFile()
        self.name  = name
        self.flags = flags

    @classmethod
    def parse_inner(cls, bitstream):
        flags = bitstream.read(UI32)
        name  = bitstream.read(CString)
        abc   = AbcFile.from_bitstream(bitstream)
        instance = cls(name, abc, flags)
        return instance

    def create_generator(self):
        return self.abc.create_generator()

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
        return bits.serialize() + self.abc.serialize()

    def __repr_inner__(self):
        return "name=%s, flags=%s" % (self.name, bin(self.flags)[2:])

class DoABCDefine(SwfTag):
    id = 72
    min_version = 9

    def __init__(self, abc):
        self.abc = abc

    def serialize_data(self):
        """
        Serializes this tag, according to the following format.

        =======  ==========
        Format   Parameter
        =======  ==========
        ABC      abc file
        =======  ==========
        """
        return self.abc.serialize(self)

class SymbolClass(SwfTag):
    id = 76
    min_version = 9

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
        bits.write(len(self.symbols), UI16)
        for char_id, classname in self.symbols.iteritems():
            bits.write(char_id, UI16)
            bits.write(classname, CString)
        return bits.serialize()

    @classmethod
    def parse_inner(cls, bits):
        length = bits.read(UI16)
        symbols = {}
        for i in xrange(length):
            char_id = bits.read(UI16)
            symbols[char_id] = bits.read(CString)
        return cls(symbols)

    def __repr_inner__(self):
        return self.symbols

class DefineShape(SwfTag):
    id = 2
    min_version = 1
    variant = 1

    _current_variant = None

    implements(IPlaceable)

    def __init__(self, shape=None, characterid=None):
        """
        Constructor.

        :param shapes:
        """
        self.shape = ShapeWithStyle() if shape is None else shape
        self.characterid = characterid

    def add_to(self, data):
        super(DefineShape, self).add_to(data)
        self.characterid = self.shape.characterid = data.next_character_id
        data.next_character_id += 1

    def serialize_data(self):
        DefineShape._current_variant = self.variant

        self.shape.calculate_bounds()

        bits = BitStream()
        bits.write(self.characterid, UI16)

        bits += self.shape.shape_bounds
        bits += self.shape

        DefineShape._current_variant = None
        return bits.serialize()

class DefineShape2(DefineShape):
    id = 22
    min_version = 2
    variant = 2

class DefineShape3(DefineShape):
    id = 32
    min_version = 32
    variant = 3

class DefineShape4(DefineShape):
    id = 83
    min_version = 8
    variant = 4

    def serialize_data(self):
        DefineShape._current_variant = self.variant

        self.shape.calculate_bounds()

        bits = BitStream()
        bits.write(self.characterid, UI16) # Shape ID

        bits += self.shape.shape_bounds # ShapeBounds Rect
        bits += self.shape.edge_bounds  # EdgeBounds Rect

        bits.write(Zero[6]) # Reserved

        bits.write(self.shape.has_scaling)     # UsesNonScalingStrokes
        bits.write(self.shape.has_non_scaling) # UsesScalingStrokes

        bits += self.shape # ShapeWithStyle

        DefineShape._current_variant = None
        return bits.serialize()

    @classmethod
    def parse_inner(cls, bits):
        DefineShape._current_variant = cls.variant
        inst = cls()
        inst.characterid = bits.read(UI16)
        shape_bounds, edge_bounds = (bits.read(Rect) for i in xrange(2))
        bits.read(Zero[6])
        has_scaling, has_nonscaling = bits.read_bits(2)
        DefineShape._current_variant = None
        return inst

class DefineSprite(SwfTag):
    id = 39
    min_version = 3

    implements(IPlaceable)

    def __init__(self, movieclip):
        self.mc = movieclip

    def add_to(self, data):
        super(DefineSprite, self).add_to(data)
        self.characterid = self.mc.shapes.characterid = data.next_character_id
        data.next_character_id += 1

    def serialize_data(self):
        bits = BitStream()
        bits.write(self.characterid, UI16)
        bits.write(self.mc.num_frames, UI16)

        return bits.serialize + self.mc.serialize()

class ShowFrame(SwfTag):
    id = 1
    min_version = 1

    def add_to(self, data):
        super(ShowFrame, self).add_to(data)
        data.num_frames += 1

    @classmethod
    def parse_inner(cls, bitstream):
        return cls()

class FileAttributes(SwfTag):
    id = 69
    min_version = 1

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
        bits.seek(3, os.SEEK_CUR)
        fa.hasMetadata = bits.read(Bit)
        fa.useAS3      = bits.read(Bit)
        bits.seek(2, os.SEEK_CUR)
        fa.useNetwork  = bits.read(Bit)
        bits.seek(24, os.SEEK_CUR)
        return fa

class RemoveObject(SwfTag):
    id = 5
    min_version = 1

    def __init__(self, charid, depth):
        self.characterid, self.depth = charid, depth

    def serialize_data(self):
        bits = BitStream()
        bits.write(self.characterid, UI16)
        bits.write(self.depth, UI16)
        return bits.serialize()

    @classmethod
    def parse_inner(cls, bits):
        return cls(bits.read(UI16), bits.read(UI16))

class RemoveObject2(SwfTag):
    id = 28
    min_version = 3

    def __init__(self, depth):
        self.depth = depth

    def serialize_data(self):
        bits = BitStream()
        bits.write(self.depth, UI16)
        return bits.serialize()

    @classmethod
    def parse_inner(cls, bits):
        return cls(bits.read(UI16))

class PlaceObject(SwfTag):
    id = 4
    min_version = 1

    def __init__(self, depth, charid=None, transform=None, colortransform=None):
        self.shapeid = charid
        self.depth = depth
        self.transform = transform or Matrix()
        # XXX: swf version
        self.colortransform = colortransform or CXFormWithAlpha()

    def serialize_data(self):
        bits = BitStream()
        bits.write(self.shapeid, UI16)
        bits.write(self.depth, UI16)

        bits += self.transform
        bits += self.colortransform

        return bits.serialize()

class PlaceObject2(PlaceObject):
    id = 26
    min_version = 3

    def __init__(self, depth, charid=None, update=False,
                 name=None, transform=None, colortransform=None):
        self.depth = depth
        self.charid = charid
        self.update = update
        self.name = name
        self.transform = transform
        # XXX: swf version
        self.colortransform = colortransform

    def serialize_data(self):
        HasCharacterId = (self.charid is not None) and (not self.update)

        bits = BitStream()
        bits.write(False) # HasClipActions
        bits.write(False) # HasClipDepth
        bits.write(self.name is not None) # HasName
        bits.write(False) # HasRatio
        bits.write(self.colortransform is not None)
        bits.write(self.transform is not None)
        bits.write(HasCharacterId)  # HasCharacterId
        bits.write(self.update) # FlagMove

        bits.write(self.depth, UI16)

        if HasCharacterId:
            bits.write(self.charid, UI16)

        if self.name is not None:
            bits.write(self.name, CString)

        if self.transform is not None:
            bits += self.transform
        if self.colortransform is not None:
            bits += self.colortransform

        return bits.serialize()

class DefineEditText(SwfTag):

    id = 37
    min_version = 4

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
        bits.skip_flush()

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
        # if HasLayout:    Layout    = NonExistant.parse(bits)

        Variable         = bits.read(CString)
        if HasText: Text = bits.read(CString)

        inst = cls(Bounds, Variable, Text, ReadOnly, IsHTML, WordWrap,
                   Multiline, Password, AutoSize, not NotSelectable,
                   HasBorder, Color, MaxLength, Layout, FontID, FontSize,
                   FontClass, CharacterID)
        inst.wasstatic = WasStatic
        inst.outlines  = HasOutlines
        return inst

    def add_to(self, data):
        super(DefineEditText, self).add_to(data)
        self.characterid = data.next_character_id
        data.next_character_id += 1

    def serialize_data(self):
        bits = BitStream()
        bits.write(self.characterid, UI16)

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
            bits.write(self.size, UI16)
        if self.fontclass is not None:
            bits.write(self.fontclass, CString)

        if self.color is not None:
            bits += self.color
        if self.maxlength is not None:
            bits.write(self.maxlength, UI16)
        if self.layout is not None:
            bits += self.layout # Doesn't exist yet.

        bits.write(self.variable, CString)

        if self.text != "":
            bits.write(self.text, CString)
        return bits.serialize()

    def __repr_inner__(self):
        return "bounds=%s, variable=%r, initial_text=%r" % (self.rect, self.variable, self.text)

class End(SwfTag):
    id = 0
    min_version = 0

    def serialize(self):
        return "\0\0"

    @classmethod
    def parse_inner(cls, bits):
        bits.seek(16, os.SEEK_CUR)
        return cls()


class UnknownSwfTag(object):
    """
    Used for both SWF tags not yet implemented by Fusion
    and unknown SWF tags.
    """
    min_version = -1
    id = -1
    reference = {
        0: "End",
        1: "ShowFrame",
        2: "DefineShape",
        3: "FreeCharacter",
        4: "PlaceObject",
        5: "RemoveObject",
        6: "DefineBits",
        7: "DefineButton",
        8: "JPEGTables",
        9: "SetBackgroundColor",
        10: "DefineFont",
        11: "DefineText",
        12: "DoAction",
        13: "DefineFontInfo",
        14: "DefineSound",
        15: "StartSound",
        16: "StopSound",
        17: "DefineButtonSound",
        18: "SoundStreamHead",
        19: "SoundStreamBlock",
        20: "DefineBitsLossless",
        21: "DefineBitsJPEG2",
        22: "DefineShape2",
        23: "DefineButtonCxform",
        24: "Protect",
        25: "PathsArePostScript",
        26: "PlaceObject2",
        28: "RemoveObject2",
        29: "SyncFrame",
        31: "FreeAll",
        32: "DefineShape3",
        33: "DefineText2",
        34: "DefineButton2",
        35: "DefineBitsJPEG3",
        36: "DefineBitsLossless2",
        37: "DefineEditText",
        38: "DefineVideo",
        39: "DefineSprite",
        40: "NameCharacter",
        41: "ProductInfo",
        42: "DefineTextFormat",
        43: "FrameLabel",
        44: "DefineBehavior",
        45: "SoundStreamHead2",
        46: "DefineMorphShape",
        47: "FrameTag",
        48: "DefineFont2",
        49: "GenCommand",
        50: "DefineCommandObj",
        51: "CharacterSet",
        52: "FontRef",
        53: "DefineFunction",
        54: "PlaceFunction",
        55: "GenTagObject",
        56: "ExportAssets",
        57: "ImportAssets",
        58: "EnableDebugger",
        59: "DoInitAction",
        60: "DefineVideoStream",
        61: "VideoFrame",
        62: "DefineFontInfo2",
        63: "DebugID",
        64: "EnableDebugger2",
        65: "ScriptLimits",
        66: "SetTabIndex",
        69: "FileAttributes",
        70: "PlaceObject3",
        71: "ImportAssets2",
        72: "DoABCDefine",
        76: "SymbolClass",
        82: "DoABC",
        83: "DefineShape4",
        84: "DefineMorphShape2",
        87: "DefineBinaryData",
        91: "DefineFont4",
    }
    def __init__(self, id):
        self.id = id
        self.name = self.reference.get(id, "Invalid")

    def __repr__(self):
        return "<%s (%#X) (Unknown Tag)>" % (self.name, self.id)

    def parse_inner(self, bitstream):
        return self

class UnknownSwfTagMap(dict):
    def __missing__(self, key):
        self[key] = UnknownSwfTag(key)
        return self[key]

tag_map = UnknownSwfTagMap()

def add_subclasses(TYPE, tag_map=tag_map):
    for clazz in TYPE.__subclasses__():
        if getattr(clazz, "parse_inner", None):
            tag_map[clazz.__name__] = clazz
            tag_map[clazz.id] = clazz
        add_subclasses(clazz, tag_map)

add_subclasses(SwfTag)
del add_subclasses
