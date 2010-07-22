"""
swfdump [filename]

dump a .swf or .abc file
"""

import sys
import os.path

from mech.fusion.compat import set
from mech.fusion.avm2 import constants, traits as TRAITS, abc_ as abc
from mech.fusion.swf import SwfData, tags

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
    print "  bounds:", swfdata.width, swfdata.height
    abcs = []
    for tag in swfdata.read_tags():
        if isinstance(tag, tags.DoABC):
            abcs.append(tag)
        print "    %04x %s" % (tag.offset, tag,)

    p, s, m, b = [0]*4

    for abc in abcs:
        print "  %s:" % (abc.name,)
        dumper = AbcDumper(abc)
        dumper.dump_abc(indent="  ")
        p, s, m, b = (a+b for a,b in zip((p,s,m,b), dumper.stats()))

    print "// overall stats:"
    print "//   %d methods, %d bodies" % (m, b)
    print "//   %d properties" % (p,)
    print "//   %d slots" % (s,)

class AbcDumper(object):
    def __init__(self, abc):
        self.abc = getattr(abc, "abc", abc)
        self.meth_count = 0
        self.body_count = 0
        self.prop_count = 0
        self.slot_count = 0

    def stats(self):
        return self.prop_count, self.slot_count, self.meth_count, self.body_count

    def dump_pool(self, name, pool, indent="", default=None):
        print indent + "    %s:" % (name,)
        print indent + "      %s[0] = %r" % (name, pool.default if default is None else default)
        for i, obj in enumerate(pool):
            print indent + "      %s[%d] = %r" % (name, i+1, obj)

    def dump_traits(self, obj, indent, attrib=""):
        seen = set()
        for trait in obj.traits:
            if isinstance(trait, TRAITS.AbcSlotTrait):
                print indent+attrib+("const" if type(trait) is TRAITS.AbcConstTrait else "var"),
                print "%s:%s" % (trait.name, trait.type_name),
                print "// slot id=%d" % (trait.slot_id,),
                print
                self.slot_count += 1
            if isinstance(trait, TRAITS.AbcClassTrait):
                self.dump_class(trait.cls, indent)
            elif isinstance(trait, TRAITS.AbcMethodTrait):
                if trait.KIND in (TRAITS.TRAIT_Getter, TRAITS.TRAIT_Setter):
                    D = {TRAITS.TRAIT_Getter:"g", TRAITS.TRAIT_Setter:"s"}
                    attrib = D.get(trait.KIND) + "et "
                    if trait.name not in seen:
                        self.prop_count += 1
                        seen.add(trait.name)
                else:
                    self.meth_count += 1
                    attrib = ""
                self.dump_method(trait.method, indent, attrib)

    def dump_class(self, cls, indent):
        inst = cls.instance
        print indent + "%s %s" % (["class", "interface"][inst.is_interface], cls.name),
        if inst.super_name:
            print "extends %s" % (cls.instance.super_name,),
        if inst.interfaces:
            print "implements", ', '.join(inst.interfaces)
        print "{"
        cls.cinit.name = "%s$cinit" % (cls.name.name,)
        cls.cinit.return_type = constants.QName("void")
        cls.instance.iinit.name = "%s$iinit" % (cls.name.name,)
        self.dump_method(cls.cinit,   indent+"    ", "static ")
        self.dump_method(inst.iinit,  indent+"    ")
        self.dump_traits(cls,         indent+"    ", "static ")
        self.dump_traits(inst,        indent+"    ")
        print indent+"}"
        print

    def dump_method(self, meth, indent, attrib=""):
        print indent + "function %s%s(%s):%s" % (attrib, meth.name,
            ', '.join("%s:%s" % t for t in zip(meth.param_names, meth.param_types)), meth.return_type),
        if meth.flags & constants.METHODFLAG_Native or getattr(meth.owner, "is_interface", None):
            print ";"
        else:
            self.body_count += 1
            print "{"
            print meth.body.code.dump_instructions(indent=indent+"  ", exceptions=meth.body.exceptions)
            print indent + "}"
        print

    def dump_abc(self, indent=""):
        print indent + "  constants:"
        abc = self.abc
        self.dump_pool("ints", abc.constants.int_pool, indent)
        self.dump_pool("uints", abc.constants.uint_pool, indent)
        self.dump_pool("doubles", abc.constants.double_pool, indent)
        self.dump_pool("utf8", abc.constants.utf8_pool, indent, default="")
        self.dump_pool("namespaces", abc.constants.namespace_pool, indent)
        self.dump_pool("nssets", abc.constants.nsset_pool, indent)
        self.dump_pool("multinames", abc.constants.multiname_pool, indent, default="*")

        print
        for i, script in enumerate(abc.scripts):
            print indent + "script%d {" % (i,)
            script.init.name = constants.QName("script%d$init" % (i,))
            script.init.return_type = constants.QName("*")
            self.dump_method(script.init, indent+"    ")
            self.dump_traits(script,      indent+"    ")
            print indent + "}"

        print indent + "// stats:"
        print indent + "//   %d methods, %d bodies" % (self.meth_count, self.body_count)
        print indent + "//   %d properties" % (self.prop_count,)
        print indent + "//   %d slots" % (self.slot_count,)

def main():
    if len(sys.argv) == 2:
        filename = sys.argv[1]
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
        AbcDumper(abc.AbcFile.from_filename(filename, lazy=False)).dump_abc()
    else:
        error('cannot parse a %s file' % (ext,))

if __name__ == "__main__":
    main()
