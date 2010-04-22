"""
extractabc [filename]

extract abc files from a .swf or .swc
"""

import sys
import os.path

from mech.fusion.swf.swfdata import SwfData
from mech.fusion.avm2.swc    import SwcData
from mech.fusion.avm2.abc_   import AbcFile

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
        abc = AbcFile()
        for tag in SwfData.from_filename(filename, False, AbcFile).tags:
            abc.merge(tag)
        data = abc.serialize()
    elif ext == ".swc":
        data = SwcData.from_filename(filename).get_all_abcs().serialize()
    else:
        error('cannot parse a %s file' % (ext,))

    out = open(nex+".abc", "w")
    out.write(data)
    out.close()
    print "wrote %s.abc, %s" % (nex, sizeof_fmt(len(data)))

if __name__ == '__main__':
    main()
