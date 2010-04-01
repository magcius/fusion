
import sys

import zipfile

from mech.fusion.avm2.abc_ import AbcFile

class SwcData(object):
    def __init__(self, file):
        self.zip = zipfile.ZipFile(file)

    @classmethod
    def from_file(cls, file):
        return cls(file)

    @classmethod
    def from_filename(cls, filename):
        return cls(open(filename, "rb"))

    def get_catalog(self):
        return self.zip.open("catalog.xml", "r")

    def get_swf(self, name="library", tags_as_list=True, only_parse_type=None):
        from mech.fusion.swf.swfdata import SwfData
        if not name.endswith(".swf"):
            name += ".swf"
        return SwfData.from_file(self.zip.open(name, "r"),
                                 tags_as_list, only_parse_type)

    def get_all_swfs(self, tags_as_list=True, only_parse_type=None):
        return [self.get_swf(name, tags_as_list, only_parse_type) \
                for name in self.zip.namelist() if name.endswith(".swf")]

    def get_all_abcs(self):
        swfs = self.get_all_swfs(False, AbcFile)
        abc = AbcFile()
        for swf in swfs:
            for tag in swf.tags:
                if tag:
                    abc.merge(tag)
        return abc

    def get_abc(self, name="library"):
        library = self.get_swf(name, False, AbcFile)
        abc = AbcFile()
        for tag in library.tags:
            sys.stdout.write(".")
            sys.stdout.flush()
            if tag:
                abc.merge(tag)
        return abc
