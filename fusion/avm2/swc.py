
import zipfile
import itertools

from fusion.swf.tags  import DoABC, DoABCDefine

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
        from fusion.swf.swfdata import SwfData
        if not name.endswith(".swf"):
            name += ".swf"
        info = self.zip.getinfo(name)
        return SwfData.from_file(self.zip.open(info, "r"), info.file_size)

    def get_all_swfs(self):
        return (self.get_swf(name) for name in
                self.zip.namelist() if name.endswith(".swf"))

    def get_abcs(self, name="library"):
        return self.get_swf(name).read_tags((DoABC, DoABCDefine))

    def get_all_abcs(self):
        return itertools.chain(s.read_tags((DoABC, DoABCDefine))
                               for s in self.get_all_swfs())
