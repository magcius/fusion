
import sys
import urllib
import zipfile

try:
    import cPickle as pickle
except ImportError:
    import pickle

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

from mech.fusion.swf.swfdata import SwfData
from mech.fusion.avm2.swc import SwcData
from mech.fusion.avm2.abc_ import AbcFile

from mech.fusion.avm2.query import ClassDesc

def get_playerglobal_swc():
    URL = "http://download.macromedia.com/pub/labs/flashplayer10/flashplayer10_globalswc.zip"
    zipf = zipfile.ZipFile(StringIO(urllib.urlopen(URL).read()))
    filename = next(f for f in zipf.namelist() if \
                    f.endswith("playerglobal.swc") and not \
                    f.startswith("__MACOSX"))
    return SwcData.from_file(StringIO(zipf.open(filename, "r").read()))

def playerglobal():
    pickle_library(gen_library_abc(\
        get_playerglobal_swc().get_abc("library.swf")), "playerglobal.pickle")

def gen_library_swcdata(swcdata):
    return gen_library_abc(swcdata.get_all_abcs())

def gen_library_swfdata(swfdata):
    return gen_library_swf(swfdata.collect_type(AbcFile))

def gen_library_abc(abc):
    Types    = {}
    Packages = {}
    PackagesFlat = {}

    def properties(inst):
        return [(str(name), str(type),
                 int(getter) + int(setter)*2) for (name, type, getter,
                 setter) in inst.properties.itervalues()]

    def fields(inst):
        return [(str(field.name),
                 str(field.type_name)) for field in inst.fields.itervalues()]

    def methods(inst):
        return [(str(meth.name), [str(T) for T in meth.param_types],
                 str(meth.return_type)) for meth in inst.methods.itervalues()]

    for inst in abc.instances:
        desc = ClassDesc()
        desc.ShortName     = inst.name.name
        desc.Package       = inst.name.ns.name
        desc.FullName      = str(inst.name)
        desc.BaseType      = str(inst.super_name)
        desc.Fields        = fields(inst)
        desc.StaticFields  = fields(inst.cls)
        desc.Methods       = methods(inst)
        desc.StaticMethods = methods(inst.cls)
        desc.Properties    = properties(inst)
        desc.StaticProperties = properties(inst.cls)
        package = PackagesFlat.setdefault(desc.Package, {})
        Types[str(inst.name)] = package[desc.ShortName] = desc
    for package, D in PackagesFlat.iteritems():
        parts = package.split(".")
        context = Packages
        for part in parts[:-1]:
            context = context.setdefault(part, {})
        context[parts[-1]] = D
    return Types, Packages

def pickle_library(T, filename):
    f = open(filename, "wb")
    pickle.dump(T, f)
    f.close()
