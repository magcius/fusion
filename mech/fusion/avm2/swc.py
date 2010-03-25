
import zipfile

from mech.fusion.avm2.abc_ import AbcFile
from mech.fusion.swf.swfdata import SwfData

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

    def get_swf(self, name="library"):
        if not name.endswith(".swf"):
            name += ".swf"
        return SwfData.from_file(self.zip.open(name, "r"))

    def get_all_swfs(self):
        return [self.get_swf(name) for name in self.zip.namelist() if name.endswith(".swf")]

    def get_all_abcs(self):
        swfs = self.get_all_swfs()
        abc = AbcFile()
        for swf in swfs:
            abc.merge(*swf.collect_type(AbcFile))
        return abc

    def get_abc(self, name="library"):
        library = self.get_swf(name)
        abc = AbcFile()
        abc.merge(*library.collect_type(AbcFile))
        return abc
