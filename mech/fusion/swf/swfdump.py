"""
swfdump [filename]

dump a .swf or .abc file
"""

import sys
import os.path

from mech.fusion.avm2 import constants, traits as TRAITS

from mech.fusion.swf.swfdata import SwfData
from mech.fusion.avm2.abc_ import AbcFile

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

def header(filename):
    base = os.path.basename(filename)
    size = sizeof_fmt(os.path.getsize(filename))
    print "summary for %s, %s" % (base, size)

def dump_swf(swfdata):
    print
    print "  tags:"
    abcs = []
    for tag in swfdata.tags:
        print "    %04x %s" % (tag.offset, tag,)
        if isinstance(tag, AbcFile):
            abcs.append(tag)

    for abc in abcs:
        print "  %s:" % (abc.name,)
        dump_abc(abc, indent="  ")

def dump_pool(name, pool, indent="", default=None):
    print indent + "    %s:" % (name,)
    print indent + "      %s[0] = %s" % (name, pool.default if default is None else default)
    for i, num in enumerate(pool):
        print indent + "      %s[%d] = %s" % (name, i+1, num)


def dump_traits(traits, indent, attrib=""):
    for trait in traits:
        if isinstance(trait, TRAITS.AbcSlotTrait):
            print indent+attrib+("const" if type(trait) is TRAITS.AbcConstTrait else "var"),
            print "%s:%s" % (trait.name, trait.type_name),
            print "// slot id=%d" % (trait.slot_id,)
        if isinstance(trait, TRAITS.AbcClassTrait):
            dump_class(trait.cls, indent)
        elif isinstance(trait, TRAITS.AbcMethodTrait):
            dump_method(trait.method, indent, attrib+{TRAITS.AbcSetterTrait: "set ", TRAITS.AbcGetterTrait: "get "}.get(type(trait), ""))

def dump_class(cls, indent):
    print indent + "class %s" % (cls.name),
    if cls.instance.super_name and cls.instance.super_name != constants.QName("Object"):
        print "extends %s" % (cls.instance.super_name,),
    print "{"
    cls.cinit.name = "%s$cinit" % (cls.name.name,)
    cls.cinit.return_type = constants.QName("void")
    cls.instance.iinit.name = "%s$iinit" % (cls.name.name,)
    dump_method(cls.cinit, indent+"    ", "static ")
    dump_method(cls.instance.iinit, indent+"    ")
    dump_traits(cls.traits, indent+"    ", "static ")
    dump_traits(cls.instance.traits, indent+"    ")
    print indent+"}"
    print

def dump_method(meth, indent, attrib=""):
    print indent + "function %s%s(%s):%s {" % (attrib, meth.name,
        ', '.join("%s:%s" % t for t in zip(meth.param_names, meth.param_types)), meth.return_type)
    print meth.body.code.dump_instructions(indent=indent+"  ")
    print indent + "}"
    print

def dump_abc(abc, indent=""):
    print indent + "  constants:"
    dump_pool("ints", abc.constants.int_pool, indent)
    dump_pool("uints", abc.constants.uint_pool, indent)
    dump_pool("doubles", abc.constants.double_pool, indent)
    dump_pool("utf8", abc.constants.utf8_pool, indent, default="")
    dump_pool("namespaces", abc.constants.namespace_pool, indent)
    dump_pool("nssets", abc.constants.nsset_pool, indent)
    dump_pool("multinames", abc.constants.multiname_pool, indent, default="*")

    print
    for i, script in enumerate(abc.scripts):
        print indent + "script%d {" % (i,)
        script.init.name = constants.QName("script%d$init" % (i,))
        script.init.return_type = constants.QName("*")
        dump_method(script.init, indent+"    ")
        dump_traits(script.traits, indent+"    ")
        print indent + "}"

def main(argv):
    if len(argv) == 2:
        filename = argv[1]
    else:
        error('no filename passed')

    filename = os.path.abspath(filename)
    _, ext = os.path.splitext(filename)

    if not os.path.exists(filename):
        error('cannot find file %s' % (filename,))
    
    if ext == ".swf":
        header(filename)
        dump_swf(SwfData.from_filename(filename))
    elif ext == ".abc":
        header(filename)
        dump_abc(AbcFile.from_filename(filename))
    else:
        error('cannot parse a %s file' % (ext,))

if __name__ == "__main__":
    main(sys.argv)