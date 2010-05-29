
import inspect

from mech.fusion.avm2 import traits
from mech.fusion.avm2.codegen import Argument
from mech.fusion.avm2.constants import QName, packagedQName, undefined
from mech.fusion.avm2.library import ClassDesc, NativePackage, get_type
from mech.fusion.avm2.interfaces import INode, ILoadable

from zope.interface import implements, implementer
from zope.component import adapter, provideAdapter

from copy import copy
from types import FunctionType
from itertools import chain

class Slot(object):
    """
    A slot trait. It handles AbcSlotTrait as well as getters and setters.
    """
    implements(ILoadable)
    def __init__(self, type, id=None, static=False, owner=None):
        self.type, self.slot_id, self.static = QName(type), id, static
        self.owner, self.name = None, None

    def create_trait(self):
        return traits.AbcSlotTrait(self.name, self.type, slot_id=self.slot_id)

    def load(self, gen):
        """
        Load this slot of the owner on the stack.
        """
        # First, load the owner.
        gen.load(self.owner)
        if self.slot_id > 0:
            gen.emit('getslot', self.slot_id)
        else:
            gen.get_field(self.name)

    def __getattr__(self, attr):
        # Do some magic here to make sure our load method gets called.
        # Get the attribute, calling the descriptor if it exists.
        attribute = getattr(INode(get_type(self.type)), attr)
        # And finally, call the descriptor on us.
        if getattr(attribute, "get_bound", None):
            attribute = attribute.get_bound(self, False)
        return attribute

class CompiledAbcFileNode(object):
    """
    A node which renders a compiled ABC file to the generator.
    """
    implements(INode)
    def __init__(self, abcfile):
        """
        The AbcFile instance to add to the generator.
        """
        self.abc = abcfile

    def dependencies(self):
        pass

    def render(self, generator):
        generator.abc.merge(self.abc)

class ClassNodeMeta(type):
    """
    Metaclass used to support the Node API.
    """
    implements(INode, ILoadable)
    currently_rendering = None
    def __new__(cls, name, bases, dct):
        # We need __new__ because we modify the dct.
        straits = dct['__straits__'] = []
        itraits = dct['__itraits__'] = []
        functs  = dct['__functs__']  = []
        slots   = dct['__tslots__']  = []

        # exported name - name can be a multinamable
        # when using the ClassNodeMeta() constructor.
        if getattr(name, "multiname", None) is None:
            package = dct.pop('package', '')
            name = packagedQName(package, name)

        # set our name if it doesn't exist in the class.
        dct.setdefault('__multiname__', name)
        name = str(dct['__multiname__'])

        # XXX: should we allow __init__?
        if dct.get('__init__'):
            raise ValueError("ClassNodes aren't allowed to have __init__ "
                             "methods. Please use __iinit__ or __cinit__.")

        basetype = dct.get('__basetype__') or bases[0]
        if len(bases) > 1:
            raise ValueError("Tamarin cannot do multiple inheritance.")
        elif not bases or basetype == object:
            bases = (object,)
            basetype = QName("Object")

        slot_ids = set()

        # Go through and set our attributes.
        for attr, val in dct.iteritems():
            if isinstance(val, Slot):
                if val.slot_id:
                    slot_ids.add(val.slot_id)
                val.name = attr
                slots.append(val)
                [itraits, straits][val.static].append(val)
            elif isinstance(val, FunctionType):
                if getattr(val, "exported", None):
                    argtypes, rettype = val.exported
                    val = FunctionNode(val, argtypes, rettype)
                    dct[attr] = val
                    functs.append(val)

        # Allocate slot ids.
        for slot in slots:
            if not slot.slot_id:
                proposed = len(slot_ids)
                while proposed in slot_ids:
                    proposed += 1
                slot.slot_id = proposed
                slot_ids.add(proposed)

        dct['__basetype__'] = basetype
        dct.setdefault('__iinit__', None)
        dct.setdefault('__cinit__', None)

        if dct['__iinit__']:
            iinit = dct['__iinit__'] = export_method(dct['__iinit__'])
        if dct['__cinit__']:
            cinit = dct['__cinit__'] = export_method(dct['__cinit__'])

        return super(ClassNodeMeta, cls).__new__(cls, name, bases, dct)

    def __init__(self, name, bases, dct):
        for slot in self.__tslots__:
            if not slot.owner:
                slot.owner = self

    def dependencies(self):
        """
        All the dependencies this node needs, which is the basetype.
        """
        if INode.providedBy(self.__basetype__):
            return [self.__basetype__]
        return []

    def __getattribute__(self, attr):
        """
        Emulate descriptor nonsense.
        """
        obj = super(ClassNodeMeta, self).__getattribute__(attr)
        if getattr(obj, "get_bind", None):
            if self.currently_rendering:
                return obj.get_bind(self, True)
            return obj.get_bind(self, False)
        return obj

    def render(self, generator):
        """
        Render this class.
        """
        cls = generator.begin_class(self.__multiname__, self.__basetype__)

        # blah blah blah traits
        cls.static_traits   = [t.create_trait() for t in self.__straits__ if t.owner == self]
        cls.instance_traits = [t.create_trait() for t in self.__itraits__ if t.owner == self]

        # render our function nodes
        for func in self.__functs__:
            func.owner = self
            self.currently_rendering = func
            func.render(generator)

        self.currently_rendering = None

        # special methods
        for name in ("iinit", "cinit"):
            meth = self.__dict__.get("__%s__" % name)
            if meth:
                meth.owner = self
                meth.render(generator)
                setattr(cls, name, meth.ctx.method)
                cls.instance_traits.remove(meth.ctx.trait)

        generator.end_class()

    def multiname(self):
        return self.__multiname__

    def bases(self):
        bases, context = [], self
        while context and QName(context) != QName("Object"):
            bases.append(context)
            context = INode(get_type(QName(context.__basetype__)))
        return bases

    def load(self, gen):
        """
        Load this node on the stack.
        """
        if gen.current_node == self or self in gen.current_node.bases():
            gen.push_this()
        else:
            # XXX: what should we do here?
            # Before we ever get here I think we'll
            # need some sort of __call__ on class
            # nodes that constructS them.
            assert False

class ClassNode(object):
    """
    A base class for class nodes, if they do not
    want to inherit from a playerglobal class.
    """
    __metaclass__ = ClassNodeMeta

def call_node(asm, node, args):
    if args:
        asm.load(*args)
    opcode = 'callproperty'
    if node.rettype == QName("void"):
        opcode = 'callpropvoid'
    asm.emit(opcode, node.name, len(args))

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
        asm.emit('findpropstrict', self.name)
        call_node(asm, self, args)

    def __repr__(self):
        return "<FunctionNode around %r>" % (self.name)

    def get_bound(self, obj, static):
        """
        Function/method descriptor emulation.
        """
        if static and not self.static:
            return UnboundMethodNode(self)
        elif static:
            return StaticMethodNode(self, obj)
        return BoundMethodNode(self, obj)

class StaticMethodNode(object):
    """
    Static method node, used for static methods in Tamarin
    that do not need an instance, but instead an "owner".
    """
    def __init__(self, function, owner):
        self.function, self.owner = function, owner
        if isinstance(owner, Slot):
            self.cls = owner.owner
        else:
            self.cls = owner

    def __call__(self, asm, *args):
        asm.load(self.cls)
        call_node(asm, self.function, args)

    def __repr__(self):
        return "<StaticMethodNode around %r>" % (self.function,)

class UnboundMethodNode(object):
    """
    Unbound method node, used for instance methods
    that need a first "instance" parameter.
    """
    def __init__(self, function):
        self.function = function

    def __call__(self, inst, asm, *args):
        asm.load(inst)
        call_node(asm, self.function, args)

    def __repr__(self):
        return "<UnboundMethodNode around %r>" % (self.function,)

class BoundMethodNode(object):
    """
    Bound method node, used for instance methods
    that were already bound through emulated description.
    """
    def __init__(self, function, owner):
        self.function, self.owner = function, owner

    def __call__(self, asm, *args):
        asm.load(self.owner)
        call_node(asm, self.function, args)

    def __repr__(self):
        return "<BoundMethodNode around %r>" % (self.function,)

class ClassDescNodeMeta(ClassNodeMeta):
    """
    Node metaclass for ClassDesc.

    The __new__ function will return a ClassNodeMeta with dct copied
    and bases == (object,) if there is no "keep_desc" attribute that
    evaluates to true.
    """
    def __new__(cls, name, bases, dct):
        if not dct.pop('keep_desc', None):
            base = bases[0]
            newdct = {'__basetype__': base}
            for k in dir(base):
                if not k.startswith('__'):
                    newdct[k] = getattr(base, k)
            newdct.update(dct)
            newdct.pop('__init__', None)
            return ClassNodeMeta(name, (object,), newdct)
        return super(ClassDescNodeMeta, cls).__new__(cls, name, bases, dct)

    def render(self, asm):
        pass

class ClassDescFunctionNode(FunctionNode):
    def __init__(self, name, rettype, static=False):
        self.name, self.static, self.rettype, self.owner = name, static, rettype, None

    def render(self, asm):
        pass

@implementer(INode)
@adapter(ClassDesc)
def ClassDescNodeAdapter(classdesc, _cache={}):
    """
    Adapter to convert a ClassDesc into an INode.
    """
    if classdesc in _cache:
        return _cache[classdesc]
    dct = dict(keep_desc=True, __multiname__=classdesc.FullName)
    for n, t in classdesc.Fields:
        dct[n.name] = Slot(t)
    for n, t in classdesc.StaticFields:
        dct[n.name] = Slot(t, static=True)
    for n, t, g, s in classdesc.Properties:
        dct[n.name] = Slot(t)
    for n, t, g, s in classdesc.StaticProperties:
        dct[n.name] = Slot(t, static=True)
    for n, p, r in classdesc.Methods:
        dct[n.name] = ClassDescFunctionNode(n.name, r)
    for n, p, r in classdesc.StaticMethods:
        dct[n.name] = ClassDescFunctionNode(n.name, r, static=True)
    base = classdesc.BaseType
    if type(base) == object or base is None or base == undefined: # interfaces and root objects
        base = object
    else:
        base = ClassDescNodeAdapter(get_type(base))
    meta = ClassDescNodeMeta(str(classdesc.FullName), (base,), dct)
    _cache[classdesc] = meta
    return meta

provideAdapter(ClassDescNodeAdapter)

def convert_package(package):
    """
    Convert all of a package's classes to the INode API.
    """
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
    def inner(type):
        if getattr(fn, "node", None):
            fn.node.trait_type = "getter"
            fn.node.exported = [], type
        fn.trait_type = "getter"
        fn.exported = [], type
        return fn
    return inner

def setter(fn):
    """
    Decorator to mark a method as a "setter".
    """
    def inner(type):
        if getattr(fn, "node", None):
            fn.node.trait_type = "setter"
            fn.node.exported = [type], QName("void")
        fn.trait_type = "setter"
        fn.exported = [type], QName("void")
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
        return FunctionNode(argtypes, [], "void")
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
        return FunctionNode(argtypes, [], "void")
    def inner(fn):
        return FunctionNode(fn, argtypes, rettype)
    return inner
