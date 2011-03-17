"""
extractabc [filename]

extract abc files from a .swf or .swc
"""

import sys
import os.path

from fusion.swf.swfdata import SwfData
from fusion.swf.tags    import DoABC, DoABCDefine
from fusion.avm2.swc    import SwcData

def sizeof_fmt(num):
    for x in [' bytes','KiB','MiB','GiB','TiB']:
        if num < 1024.0:
            return "%3.1f%s" % (num, x)
        num /= 1024.0

def error(message):
    if message:
        print >> sys.stderr, "error:", message
    print >> sys.stderr, __doc__
    sys.exit(2)

def main():
    if len(sys.argv) == 2:
        filename = sys.argv[1]
    else:
        error('no filename passed')

    filename = os.path.abspath(filename)
    nex, ext = os.path.splitext(filename)

    if not os.path.exists(filename):
        error('cannot find file %s' % (filename,))

    if ext == ".swf":
        abcs = SwfData.from_filename(filename).read_tags((DoABC, DoABCDefine))
    else:
        error('cannot parse a %s file' % (ext,))

    for i, abc in enumerate(abcs):
        name = getattr(abc, "name", None) or "%s_%d" % (nex, i)
        abc  = getattr(abc, "abc", abc)
        data = abc.serialize(optimize=False)
        f = open(name+".abc", "w")
        f.write(data)
        f.close()
        print "wrote %s.abc, %s" % (name, sizeof_fmt(len(data)))

if __name__ == '__main__':
    main()
