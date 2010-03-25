import sys
try:
    import cPickle as pickle
except ImportError:
    import pickle
import os.path
import subprocess
from mech.fusion import avm2

def load_playerglobal():
    playerglobal = os.path.join(os.path.dirname(avm2.__file__), "playerglobal.pickle")
    if os.path.exists(playerglobal):
        return load_library(picklepath)
    else:
        print >> sys.stderr, """
Please install a correct version of Mecheye Fusion.

mech/fusion/avm2/playerglobal.pickle is missing.
"""
        sys.exit(1)

def load_library(picklepath):
    f = open(picklepath, "rb")
    types, Packages = pickle.load(f)
    Types.update(types)
    f.close()
    return Packages

Types = {}

def get_type(TYPE):
    return TYPE

class RuntimePackage(type(sys)):
    def __init__(self, name):
        self._name = name
        self._types = {}

    def __getattr__(self, attr):
        if attr in self._types:
            setattr(self, attr, get_type(self._types[attr]))

def install_library(Packages, modulename_prefixes):
    toplevel = RuntimePackage("")
    for prefix in modulename_prefixes:
        if prefix and prefix not in sys.modules:
            sys.modules[prefix] = toplevel
    import __builtin__
    modules = [sys.modules.get(prefix, __builtin__) for prefix in modulename_prefixes]
    def recursive_package(fullname, packagedict, package):
        for name, value in packagedict.iteritems():
            fullname = "%s.%s" % (fullname, name)
            if isinstance(value, dict):
                thispackage = RuntimePackage(fullname)
                for prefix in modulename_prefixes:
                    if prefix:
                        sys.modules[prefix + fullname] = thispackage
                    else:
                        sys.modules[fullname[1:]] = thispackage
                recursive_package(fullname, value, thispackage)
                setattr(package, name, thispackage)
            else:
                if package:
                    package._types[name] = Types[name]
                else:
                    setattr(__builtin__, name, get_type(Types[fullname]))
    recursive_package
    return ns

def install_playerglobal(modulename_prefixes):
    install_library(load_playerglobal(), modulename_prefixes)

def install_playerglobal_toplevel():
    install_playerglobal([""])

def install_playerglobal_here():
    install_playerglobal([__name__])
