"""
swfdump [filename]

dump a .swf or .abc file
"""

import sys
import os.path

from fusion.avm2 import constants, abc_ as abc
from fusion.avm2.traits import TraitKinds
from fusion.swf import swfdata, tags

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
    print "  bounds:", swfdata.width, swfdata.height
    print "  tags:"
    abcs = []
    for tag in swfdata.read_tags():
        if isinstance(tag, tags.DoABC):
            abcs.append(tag)
        print "    %04x %s" % (tag.offset, tag,)

    meth_count, body_count = 0, 0
    prop_count, slot_count = 0, 0

    for abcfile in abcs:
        print "  %s:" % (abcfile.name,)
        dumper = AbcDumper(abcfile)
        dumper.indent()
        dumper.dump_abc()
        dumper.outdent()

        meth_count += dumper.meth_count
        body_count += dumper.body_count
        prop_count += dumper.prop_count
        slot_count += dumper.slot_count

    print "// overall stats:"
    print "//   %d methods, %d bodies" % (meth_count, body_count)
    print "//   %d properties" % (prop_count,)
    print "//   %d slots"      % (slot_count,)

class AbcDumper(object):
    def __init__(self, abcfile):
        self.abc = getattr(abcfile, "abc", abcfile)
        self.meth_count = 0
        self.body_count = 0
        self.prop_count = 0
        self.slot_count = 0

        self._indent = 0

        self.methods_seen = set()

    def indent(self):
        self._indent += 1

    def outdent(self):
        self._indent -= 1

    def output(self, lines=""):
        if lines == "":
            print

        for line in lines.splitlines():
            print "\t" * self._indent + line

    def dump_pool(self, name, pool):
        self.output("%s:" % (name,))

        self.indent()
        self.output("%s[0] = %r" % (name, pool.default))
        for i, obj in enumerate(pool):
            self.output("%s[%d] = %r" % (name, i+1, obj))
        self.outdent()

    def dump_traits(self, obj, attrib):
        seen = set()
        for trait in obj.traits:
            if trait.kind in (TraitKinds.Slot, TraitKinds.Const):
                decl = "var" if trait.kind == TraitKinds.Slot else "const"
                self.output("%s %s : %s  (slot id=%d)" % (decl, trait.name, trait.type_name, trait.slot_id))
                self.slot_count += 1

            elif trait.kind == TraitKinds.Class:
                self.dump_class(trait.cls)

            elif trait.kind == TraitKinds.Method:
                self.meth_count += 1
                self.dump_method(trait.method, attrib)

            elif trait.kind in (TraitKinds.Getter, TraitKinds.Setter):
                if trait.kind == TraitKinds.Getter:
                    attrib.append("get")
                else:
                    attrib.append("set")

                if trait.name not in seen:
                    self.prop_count += 1
                    seen.add(trait.name)

                self.dump_method(trait.method, attrib)

    def dump_class(self, cls):
        inst = cls.instance

        line = []

        line.append("interface " if inst.is_interface else "class ")
        line.append(str(cls.name))

        if inst.super_name:
            line.append(" extends %s" % (cls.instance.super_name,))
        if inst.interfaces:
            if inst.is_interface:
                line.append(" extends ")
            else:
                line.append(" implements ")

            line.append(', '.join(interface.name for interface in inst.interfaces))

        self.output(''.join(line))
        self.output("{")
        self.indent()

        cls.cinit.name = "%s$cinit" % (cls.name.name,)
        cls.cinit.return_type = constants.QName("void")
        cls.instance.iinit.name = "%s$iinit" % (cls.name.name,)
        self.dump_method(cls.cinit, ["static"])
        self.dump_method(inst.iinit, [])
        self.dump_traits(cls, ["static"])
        self.dump_traits(inst, [])

        self.outdent()
        self.output("}")
        self.output()

    def dump_method(self, meth, attrib):
        self.methods_seen.add(meth)

        # Fill in remaining parameter names.
        have = len(meth.param_names)
        needed = len(meth.param_types)
        for i in xrange(have, needed):
            meth.param_names.append("param%d" % (i,))

        owner = getattr(meth, "owner", None)
        trait = getattr(meth, "trait", None)

        native = bool(meth.flags & constants.MethodFlag.Native)
        is_interface = getattr(owner, "is_interface", False)

        if native:
            attrib.append("native")
        if getattr(trait, "override", False):
            attrib.append("override")
        if getattr(trait, "final", False):
            attrib.append("final")

        functionspec = ' '.join(attrib)
        if functionspec:
            functionspec += ' '

        name = getattr(meth, "name", "anonymous_%d" % (len(self.methods_seen)),)

        param_names, param_types = meth.param_names[:], meth.param_types[:]            
        params = ', '.join("%s:%s" % (n, t) for n, t in zip(meth.param_names, meth.param_types))
        if meth.varargs:
            params += ", ..."

        functionspec += "function %s(%s) : %s" % (name, params, meth.return_type,)

        if native or is_interface: # has no body
            self.output(functionspec + ";")
        else:
            self.body_count += 1
            self.output(functionspec)
            self.output("{")
            self.indent()
            self.output(meth.body.code.dump_instructions(exceptions=meth.body.exceptions))
            self.outdent()
            self.output("}")
        self.output()

    def dump_abc(self):
        self.output("constants:")
        pool = self.abc.constants
        self.indent()
        self.dump_pool("ints", pool.int)
        self.dump_pool("uints", pool.uint)
        self.dump_pool("doubles", pool.double)
        self.dump_pool("utf8", pool.utf8)
        self.dump_pool("namespaces", pool.namespace)
        self.dump_pool("nssets", pool.nsset)
        self.dump_pool("multinames", pool.multiname)
        self.outdent()

        self.output()

        for i, script in enumerate(self.abc.scripts):
            self.output("script" + str(i))
            self.output("{")
            self.indent()

            script.init.name = constants.QName("script%d$init" % (i,))
            script.init.return_type = constants.QName("*")
            self.dump_method(script.init, [])
            self.dump_traits(script, [])
            self.outdent()
            self.output("}")
            self.output()
 
        # Leftover methods like closures.
        for method in set(self.abc.methods) - self.methods_seen:
            self.dump_method(method, [])
            
        self.output("// stats:")
        self.output("//   %d methods, %d bodies" % (self.meth_count, self.body_count))
        self.output("//   %d properties" % (self.prop_count,))
        self.output("//   %d slots" % (self.slot_count,))

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
        dump_swf(swfdata.SwfData.from_filename(filename))
    elif ext == ".abc":
        header(filename)
        AbcDumper(abc.AbcFile.from_filename(filename, lazy=False)).dump_abc()
    else:
        error('cannot parse a %s file' % (ext,))

if __name__ == "__main__":
    main()
