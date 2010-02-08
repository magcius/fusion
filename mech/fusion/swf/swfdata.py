
import struct

from mech.fusion.util import BitStream, BitStreamParseMixin
from mech.fusion.swf.records import Rect
from mech.fusion.swf.tags import REVERSE_INDEX

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
                     actual type itself, or a number indicating the tag type.
        :returns: an iterable of Tag objects, all the same type.
        """
        
        if TYPE in REVERSE_INDEX:
            TYPE = REVERSE_INDEX[TYPE]
        
        for tag in self.tags:
            if type(tag) == TYPE:
                yield tag

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
            if tag.TAG_NAME == "ShowFrame":
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
        data += ''.join(tag.serialize() for tag in self.tags)
        
        header[2] = struct.pack("<L", 8 + len(data)) # FileSize
        if self.compress:
            import zlib
            data = zlib.compress(data)
            
        return "".join(header + [data])

    @classmethod
    def parse_bitstream(cls, bitstream):
        header = bitstream.read_string(3)
        compressed = False
        if header == "CWS": # compressed
            compressed = True
        elif header != "FWS":
            raise ValueError("Unrecognizable header. Are you sure this is a SWF file?")
        version = bitstream.read_int_value(8)
        length = bitstream.read_int_value(32, endianness="<")
        if compressed:
            bitstream.decompress()
        rect = Rect.parse(bitstream)
        bitstream.skip_flush()
        fps = bitstream.read_fixed_value(16, endianness="<")
        frame_count = bitstream.read_fixed_value(16, endianness="<")
        inst = cls(rect.XMax, rect.YMax, fps, compressed, version)
        inst.frame_count = frame_count

    def _gen_header(self):
        return ["CWS" if self.compress else "FWS", struct.pack("<B", self.version), "\0\0\0\0"]

    def _gen_data_stub(self):
        data = Rect(XMax=self.width, YMax=self.height).serialize().serialize()
        return data + struct.pack("<BBH", int((self.fps - int(self.fps)) * 0x100),
                                  self.fps, self.frame_count)
