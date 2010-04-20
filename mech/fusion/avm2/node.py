
import inspect

from mech.fusion.avm2 import traits
from mech.fusion.avm2.codegen import Argument
from mech.fusion.avm2.constants import QName, packagedQName, undefined
from mech.fusion.avm2.library import ClassDesc, NativePackage, get_type
from mech.fusion.avm2.interfaces import INode

from zope.interface import implements, implementer
from zope.component import adapter, provideAdapter

from copy import copy
from types import FunctionType

class Slot(object):
    KIND = traits.AbcSlotTrait
    def __init__(self, type, id=None, static=False):
        self.type = QName(type)
        self.slot_id = id
        self.static = static

    def create_trait(self, name):
        return self.KIND(name, self.type, self.slot_id), self.static

class CompiledABCNode(object):
    """
    A node which renders a compiled ABC file to the generator.
    """
    implements(INode)
    def __init__(self, abcfile):
        self.abc = abcfile

    def dependencies(self):
        pass

    def render(self, generator):
        generator.abc.merge(self.abc)

class ClassNodeMeta(type):
    implements(INode)
    def __new__(cls, name, bases, dct):
        straits = dct['__straits__'] = []
        itraits = dct['__itraits__'] = []
        functs  = dct['__functs__']  = []
        if getattr(name, "multiname", None) is None:
            package = dct.pop('package', '')
            name = packagedQName(package, name)

        if dct.get('__init__'):
            raise ValueError("ClassNodes aren't allowed to have __init__ "
                             "methods. Please use __iinit__ or __cinit__.")

        basetype = bases[0]
        if len(bases) > 1:
            raise ValueError("Tamarin cannot do multiple inheritance.")
        elif not bases or bases[0] == object:
            bases = (object,)
            basetype = QName("Object")

        for attr, val in dct.iteritems():
            if isinstance(val, Slot):
                trait, static = val.create_trait(attr)
                [itraits, straits][static].append(trait)
                dct[attr] = trait
            elif isinstance(val, FunctionType):
                if getattr(val, "exported", None):
                    argtypes, rettype = val.exported
                    val = FunctionNode(val, argtypes, rettype)
                    dct[attr] = val
                    functs.append(val)

        dct.setdefault('name', name)
        dct['__basetype__'] = basetype
        dct.setdefault('__iinit__', None)
        dct.setdefault('__cinit__', None)
        name = str(dct['name'])

        if dct['__iinit__']:
            iinit = dct['__iinit__'] = export_method(dct['__iinit__'])
        if dct['__cinit__']:
            cinit = dct['__cinit__'] = export_method(dct['__cinit__'])

        return super(ClassNodeMeta, cls).__new__(cls, name, bases, dct)

    def multiname(self):
        return self.name

    def dependencies(self):
        if INode.providedBy(self.__basetype__):
            return [self.__basetype__]
        return []

    def render(self, generator):
        cls = generator.begin_class(self.name, self.__basetype__)
        cls.static_traits   = self.__straits__
        cls.instance_traits = self.__itraits__
        for func in self.__functs__:
            func.owner = self
            func.render(generator)
        if self.__iinit__:
            self.__iinit__.owner = self
            self.__iinit__.render(generator)
            cls.iinit = self.__iinit__.ctx.method
            cls.instance_traits.remove(self.__iinit__.ctx.trait)
        if self.__cinit__:
            self.__cinit__.owner = self
            self.__cinit__.render(generator)
            cls.cinit = self.__cinit__.ctx.method
            cls.instance_traits.remove(self.__cinit__.ctx.trait)
        generator.end_class()

class ClassNode(object):
    """
    A base class for class nodes.
    """
    __metaclass__ = ClassNodeMeta

class FunctionNode(object):
    implements(INode)
    owner = None
    def __init__(self, fn, argtypes, rettype):
        self.fn = fn
        fn.node = self
        argspec = inspect.getargspec(fn)
        self.defaults = dict(zip(argspec.args[-len(argspec.defaults or []):],
                                 argspec.defaults or []))

        self.varargs = None
        if argspec.varargs:
            self.varargs = argspec.varargs
        if argspec.keywords:
            raise ValueError("Functions with keyword arguments"
                             "cannot translate (maybe yet).")

        self.name = fn.func_name
        self.trait_type = getattr(fn, "trait_type", "method")
        self.static = getattr(fn, "static", None)
        self.argspec = zip(argtypes, argspec.args[2:])
        self.rettype = QName(rettype)

    def dependencies(self):
        pass

    def render(self, asm):
        self.ctx = asm.begin_method(self.name, self.argspec,
                   self.rettype, varargs=self.varargs,
                   defaults=self.defaults, static=self.static)
        if self.owner:
            self.fn(self.owner, asm, *[Argument(name) for t, name in self.argspec])
        else:
            self.fn(asm, *[Argument(name) for t, name in self.argspec])
        if self.rettype != QName("void"):
            asm.return_value()
        asm.end_method()

    def __call__(self, asm, *args):
        if self.owner:
            # assuming we're calling from the same class
            # hack for now
            if self.static:
                asm.load(QName(self.owner.name))
            else:
                asm.push_this()
        else:
            asm.emit('findpropstrict', self.name)
        asm.load(*args)
        opcode = 'callproperty'
        if self.rettype == QName("void"):
            opcode = 'callpropvoid'
        asm.emit(opcode, self.name, len(args))

class ClassDescNodeMeta(ClassNodeMeta):
    def __new__(cls, name, bases, dct):
        if not dct.pop('keep_desc', None):
            base = bases[0]
            newdct = {}
            for k in dir(base):
                newdct[k] = getattr(base, k)
            newdct.update(dct)
            return ClassNodeMeta(name, (object,), dct)
        return super(ClassDescNodeMeta, cls).__new__(cls, name, bases, dct)

    def render(self, asm):
        pass

class ClassDescFunctionNode(FunctionNode):
    def __init__(self, name, static=False):
        self.name, self.static, self.owner = name, static, None

    def render(self, asm):
        pass

@implementer(INode)
@adapter(ClassDesc)
def ClassDescNodeAdapter(classdesc, _cache={}):
    if classdesc in _cache:
        return _cache[classdesc]
    dct = dict(keep_desc=True)
    for n, t in classdesc.Fields:
        dct[n.name] = Slot(t)
    for n, t in classdesc.StaticFields:
        dct[n.name] = Slot(t, static=True)
    for n, p, r in classdesc.Methods:
        dct[n.name] = ClassDescFunctionNode(n.name)
    for n, p, r in classdesc.StaticMethods:
        dct[n.name] = ClassDescFunctionNode(n.name, static=True)
    base = classdesc.BaseType
    if type(base) == object or base is None: # interfaces and root objects
        base = object
    else:
        base = ClassDescNodeAdapter(get_type(base))
    meta = ClassDescNodeMeta(str(classdesc.FullName), (base,), dct)
    _cache[classdesc] = meta
    return meta

provideAdapter(ClassDescNodeAdapter)

def convert_package(package):
    package = copy(package)
    for name, TYPE in package._types.iteritems():
        package._types[name] = INode(TYPE)
    for name, PKG in package._packages.iteritems():
        package._packages[name] = convert_package(PKG)
    return package

def export_as(name):
    """
    Export this node as the given name. Can be a QName.
    """
    def inner(node):
        node.func_name = name
        node.name = name
        return node
    return inner

def getter(fn):
    """
    Decorator to mark a method as a "getter".
    """
    if getattr(fn, "node", None):
        fn.node.trait_type = "getter"
    fn.trait_type = "getter"
    return fn

def setter(fn):
    """
    Decorator to mark a method as a "setter".
    """
    if getattr(fn, "node", None):
        fn.node.trait_type = "setter"
    fn.trait_type = "setter"
    return fn

def static(fn):
    """
    Decorator to mark a method as "static".
    """
    if getattr(fn, "node", None):
        fn.node.static = True
    fn.static = True
    return fn

def export_node(generator):
    """
    Add a node to the generator with a decorator.
    """
    def inner(node):
        generator.add_node(node)
        return node
    return inner

def export_method(argtypes, rettype=None):
    """
    Mark a method as exported, with the given argument types
    and the return type of the function.
    """
    if isinstance(argtypes, FunctionType) and rettype is None:
        return FunctionNode(argtypes, [], undefined)
    def inner(fn):
        fn.exported = argtypes, rettype or "void"
        return fn
    return inner

def export_function(argtypes, rettype=None):
    """
    Mark a function as exported, with the given argument types
    and the return type of the function.
    """
    if isinstance(argtypes, FunctionType) and rettype is None:
        return FunctionNode(argtypes, [], undefined)
    def inner(fn):
        return FunctionNode(fn, argtypes, rettype)
    return inner

## class PackageNode(object):
##     provides(INode)

##     @staticmethod
##     def dependencies():
##         return []

##     @staticmethod
##     def render(generator):
##         pass
