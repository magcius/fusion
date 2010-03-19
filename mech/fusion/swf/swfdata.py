
import itertools
import struct

from mech.fusion.bitstream.formats import ByteString
from mech.fusion.bitstream.flash_formats import UI8, UI16, UI32, FIXED8
from mech.fusion.bitstream.bitstream import BitStreamParseMixin
from mech.fusion.swf.records import Rect
from mech.fusion.swf.tags import REVERSE_INDEX, ShowFrame, SwfTag

class SwfData(BitStreamParseMixin):
    def __init__(self, width=600, height=400, fps=24, compress=False, version=10):
        self.width = width
        self.height = height
        self.fps = fps
        self.compress = compress
        self.version = version
        self.frame_count = 0
        self.next_character_id = 1

        self.tags = []

    def collect_type(self, TYPE):
        """
        Return all tags of *TYPE*.

        :param TYPE: a string indicating the tag name or the
                     actual type itself, or a number indicating the tag type,
                     or tuples containing one or the other.
        :returns: an iterable of Tag objects, all the same type.
        """

        if isinstance(TYPE, tuple):
            return itertools.chain(*(self.collect_type(t) for t in TYPE))
        
        if TYPE in REVERSE_INDEX:
            TYPE = REVERSE_INDEX[TYPE]

        return (tag for tag in self.tags if isinstance(tag, TYPE))

    def __getitem__(self, i):
        return self.tags[i]

    def __iadd__(self, other):
        if hasattr(other, "TAG_TYPE"):
            self.add_tag(other)
        else:
            self.add_tags(other)
        return self

    def add_tag(self, tag):
        """
        Add a tag.
        """
        if self.version >= tag.TAG_MIN_VERSION:
            if hasattr(tag, "characterid") and tag.characterid == None:
                tag.characterid = self.next_character_id
                self.next_character_id += 1
            if tag.TAG_TYPE == ShowFrame.TAG_TYPE:
                self.frame_count += 1
            self.tags.append(tag)

    def add_tags(self, tag_container):
        """
        Add tags to this SWF.
        """
        if hasattr(tag_container, "tags"):
            tag_container = tag_container.tags

        for tag in tag_container:
            self.add_tag(tag)

    def serialize(self):
        """
        Serialize to bytes.
        """
        header = self._gen_header()
        data = self._gen_data_stub()
        data += ''.join(tag.as_bitstream() for tag in self.tags)
        
        header[2] = struct.pack("<L", 8 + len(data)) # FileSize
        if self.compress:
            import zlib
            data = zlib.compress(data)
            
        return "".join(header + [data])

    @classmethod
    def from_bitstream(cls, bitstream):
        header = bitstream.read(ByteString[3])
        compressed = False
        if header == "CWS": # compressed
            compressed = True
        elif header != "FWS":
            raise ValueError("Unrecognizable header. Are you sure this is a SWF file?")
        version = bitstream.read(UI8)
        length = bitstream.read(UI32)
        if compressed:
            bitstream.decompress()
        rect = Rect.from_bitstream(bitstream)
        bitstream.skip_flush()
        fps = bitstream.read(FIXED8)
        frame_count = bitstream.read(UI16)
        inst = cls(rect.XMax, rect.YMax, fps, compressed, version)
        inst.frame_count = frame_count
        while bitstream.bits_available:
            inst.add_tag(SwfTag.from_bitstream(bitstream))
        return inst

    def _gen_header(self):
        return ["CWS" if self.compress else "FWS", struct.pack("<B", self.version), "\0\0\0\0"]

    def _gen_data_stub(self):
        rect = Rect(XMax=self.width, YMax=self.height).as_bitstream()
        rect = rect.serialize()
        return rect + struct.pack("<BBH", int((self.fps - int(self.fps)) * 0x100),
                                  self.fps, self.frame_count)
