
import os
import zlib
import struct

from fusion.bitstream.bitstream import BitStream, BitStreamParseMixin
from fusion.bitstream.formats import ByteString
from fusion.bitstream.flash_formats import UI8, UI16, UI32, FIXED8
from fusion.swf.records import Rect, RecordHeader
from fusion.swf.interfaces import ISwfPart
from fusion.swf.tags import SwfTag
from fusion.swf.core import SwfMovieClip

class SwfData(BitStreamParseMixin, SwfMovieClip):
    def __init__(self, width=600, height=400, fps=24, compress=False, version=10):
        BitStreamParseMixin.__init__(self)
        SwfMovieClip.__init__(self, self)
        self.width = width
        self.height = height
        self.fps = fps
        self.compress = compress
        self.version = version
        self._next_tag_header = None
        self._next_character_id = 1

    def __getitem__(self, i):
        return self.tags[i]

    def __iadd__(self, part):
        self.add_part(part)

    def add_part(self, part):
        """
        Add a SwfPart, which may consist of
        one or more tags.
        """
        ISwfPart(part).add_to(self)

    def serialize(self):
        """
        Serialize to bytes.
        """
        data = self.get_data_stub()
        data += super(SwfData, self).serialize()
        filesize = len(data) + 8

        if self.compress:
            data = zlib.compress(data)

        return "".join([self.get_magic(), chr(self.version),
                        struct.pack("<L", filesize), data])

    def get_magic(self):
        return "CWS" if self.compress else "FWS"

    def get_data_stub(self):
        bits = BitStream()
        bits += Rect(XMax=self.width, YMax=self.height)
        bits.flush()
        bits.write(self.fps, FIXED8)
        bits.write(self.num_frames, UI16)
        return bits.serialize()

    @classmethod
    def from_bitstream(cls, bitstream):
        header = bitstream.read(ByteString[3])
        if header not in ("CWS", "FWS"):
            raise ValueError("Unrecognizable header. Are you sure this is a SWF file?")
        compressed = header[0] == "C"

        version = bitstream.read(UI8)
        length  = bitstream.read(UI32)
        if compressed:
            bitstream.decompress()

        rect = Rect.from_bitstream(bitstream)
        bitstream.skip_flush()
        fps = bitstream.read(FIXED8)
        frame_count = bitstream.read(UI16)
        inst = cls(rect.XMax, rect.YMax, fps, compressed, version)
        inst.frame_count = frame_count
        inst.bitstream = bitstream
        return inst

    @property
    def next_tag_header(self):
        if not self._next_tag_header:
            self._next_tag_header = RecordHeader.from_bitstream(self.bitstream)
        return self._next_tag_header

    def skip_tag(self):
        self.bitstream.seek(self._next_tag_header.bit_length, os.SEEK_CUR)
        self._next_tag_header = None

    def read_tag(self):
        header = self.next_tag_header
        bits = self.bitstream.read(BitStream[header.bit_length])
        tag = header.type.parse_inner(bits)
        tag.offset = self.bitstream.tell() // 8 - header.length - 2
        self._next_tag_header = None
        return tag

    def read_tags(self, only_parse_type=None):
        if isinstance(only_parse_type, SwfTag):
            only_parse_type = (only_parse_type,)
        while self.bitstream.bits_available > 0:
            if only_parse_type:
                if self.next_tag_header.type in only_parse_type:
                    yield self.read_tag()
                else:
                    self.skip_tag()
            else:
                yield self.read_tag()
