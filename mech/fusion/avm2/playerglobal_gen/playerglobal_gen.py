
import urllib
import zipfile
import sys
import os

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

path = os.getcwd()

while True:
    try:
        import mech.fusion
        break
    except ImportError:
        path = os.path.dirname(path)
        sys.path.append(path)

from mech.fusion.swf.swfdata import SwfData

URL = "http://download.macromedia.com/pub/labs/flashplayer10/flashplayer10_globalswc.zip"

if __name__ == '__main__':
    print "Fetching the zip file from Adobe."
    zipf = zipfile.ZipFile(StringIO(urllib.urlopen(URL).read()))
    files = [filename for filename in zipf.namelist() if \
             (filename.endswith("playerglobal.swc") and \
              not filename.startswith("__MACOSX"))]
    print "Fetching the SWC file from the zip file."
    swcf = zipfile.ZipFile(StringIO(zipf.open(files[0], 'r').read()))
    library_swf = swcf.open("library.swf", 'r')
    print "Parsing library.swf"
    swf = SwfData.from_file(library_swf)
