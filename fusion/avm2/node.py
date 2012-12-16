
import functools
import inspect

from fusion.avm2 import traits
from fusion.avm2.loadable import Argument, This, Field, Slot as SlotLoad
from fusion.avm2.constants import QName, packagedQName
from fusion.avm2.library import ClassDesc, make_package, get_type
from fusion.avm2.interfaces import INode, ILoadable, IMultiname

from zope.interface import implements, implementer
from zope.component import adapter, provideAdapter

from types import FunctionType

class Slot(object):
    """
    A slot trait. It handles AbcSlotTrait as well as getters and setters.
    """
    implements(ILoadable)
    def __init__(self, type, slot_id=None, static=False):
        self.type = IMultiname(type)
        self.slot_id, self.static = slot_id or 0, static
        self.owner, self.name = None, None

    def create_trait(self):
        return traits.SlotTrait(self.name, self.type, slot_id=self.slot_id)

    def load(self, gen):
        """
        Load this slot of the owner on the stack.
        """
        # First, load the owner.
        gen.load(self.owner)
        if self.slot_id:
            gen.load(SlotLoad(self.name))
        else:
            gen.load(Field(self.name))

    def __getattr__(self, attr):
        # Do some dirty magic here to make sure the Slot is
        # the object the function is being bound to.

        # Get the attribute, calling the descriptor if it exists.
        attribute = getattr(INode(get_type(self.type)), attr)

        # Get the actual function.
        attribute = getattr(attribute, "function", attribute)
        attribute = getattr(attribute, "im_func", attribute)

        # And finally, call the descriptor on us.
        if getattr(attribute, "get_bound", None):
            attribute = attribute.get_bound(self, False)
        return attribute

    def __repr__(self):
        return "Slot(%s)" % (self.name,)

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
        return []

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
        if not IMultiname.providedBy(name):
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

        for name in ('iinit', 'cinit'):
            key = '__%s__' % (name,)
            if key in dct:
                meth = dct[key] = export_method(dct[key])
                meth.special = name
                functs.append(meth)

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

        dct['__basetype__'] = basetype

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
        if getattr(obj, "get_bound", None):
            if self.currently_rendering:
                return obj.get_bound(self, True)
            return obj.get_bound(self, False)
        return obj

    def render(self, generator):
        """
        Render this class.
        """
        generator.begin_script()
        cls = generator.begin_class(self.__multiname__, self.__basetype__)

        # blah blah blah traits
        cls.static_traits   = [t.create_trait() for t in self.__straits__ if t.owner == self]
        cls.instance_traits = [t.create_trait() for t in self.__itraits__ if t.owner == self]

        # render our function nodes
        for func in self.__functs__:
            func.owner = self
            self.currently_rendering = func
            func.render(generator)

            if func.special:
                setattr(cls, func.special, func.rib.method)
                if func.special == 'cinit':
                    traits = cls.static_traits
                else:
                    traits = cls.instance_traits
                traits.remove(func.rib.method.trait)

        self.currently_rendering = None

        generator.exit_current_rib() # Class
        generator.exit_current_rib() # Script

    def bases(self):
        bases, context = [], self
        while context and IMultiname(context) != IMultiname("Object"):
            bases.append(context)
            context = INode(get_type(IMultiname(context.__basetype__)))
        return bases

    def load(self, gen):
        """
        Load this node on the stack.
        """
        if gen.current_node == self or self in gen.current_node.bases():
            gen.load(This)
        else:
            # XXX: what should we do here?
            # Before we ever get here I think we'll
            # need some sort of __call__ on class
            # nodes that constructs them.
            assert False

class ClassNode(object):
    """
    A base class for class nodes, if they do not
    want to inherit from a playerglobal class.
    """
    __metaclass__ = ClassNodeMeta

def call_node(asm, node, args):
    if args:
        asm.load_many(args)
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

        if argspec.keywords:
            raise ValueError("Functions with keyword arguments"
                             "cannot translate (maybe yet).")

        self.is_method = getattr(fn, "method", False)
        self.name = fn.func_name
        self.trait_type = getattr(fn, "trait_type", "method")
        self.static = getattr(fn, "static", None)
        if self.is_method:
            args = argspec.args[2:] # self, gen
        else:
            args = argspec.args[1:] # gen
        self.argspec = zip(argtypes, args)
        self.rettype = IMultiname(rettype)

    def dependencies(self):
        return []

    def render(self, asm):
        if not self.is_method:
            asm.begin_script()

        self.rib = asm.begin_method(self.name, self.argspec,
                                    self.rettype, static=self.static)
        if self.owner:
            ret = self.fn(self.owner, asm, *[Argument(name) for t, name in self.argspec])
        else:
            ret = self.fn(asm, *[Argument(name) for t, name in self.argspec])
        if self.rettype != QName("void"):
            self.load(ret)
            asm.return_value()
        asm.exit_current_rib() # method

        if not self.is_method:
            asm.exit_current_rib() # script

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
    dct = dict(keep_desc=True, __multiname__=classdesc.FullName, __library__=classdesc.Library)
    for n, t, s in classdesc.Fields:
        dct[n.name] = Slot(t, s)
    for n, t, s in classdesc.StaticFields:
        dct[n.name] = Slot(t, s, static=True)
    for n, t, g, s in classdesc.Properties:
        dct[n.name] = Slot(t)
    for n, t, g, s in classdesc.StaticProperties:
        dct[n.name] = Slot(t, static=True)
    for n, p, r in classdesc.Methods:
        dct[n.name] = ClassDescFunctionNode(n.name, r)
    for n, p, r in classdesc.StaticMethods:
        dct[n.name] = ClassDescFunctionNode(n.name, r, static=True)
    base = classdesc.BaseType
    if type(base) == object or base is None or base == QName("*"): # interfaces and root objects
        base = object
    else:
        base = INode(get_type(base))
    meta = ClassDescNodeMeta(classdesc.FullName, (base,), dct)
    _cache[classdesc] = meta
    return meta

provideAdapter(ClassDescNodeAdapter)

@adapter(ClassNodeMeta)
@implementer(IMultiname)
def nodemeta_to_IMultiname(self):
    return self.__multiname__

provideAdapter(nodemeta_to_IMultiname)

convert_package = functools.partial(make_package, Interface=INode)

def export_as(name):
    """
    Export this node as the given name. Can be a QName.
    """
    def inner(node):
        node.func_name = name
        node.name = name
        return node
    return inner

def getter(type):
    """
    Decorator to mark a method as a "getter".
    """
    def inner(fn):
        if getattr(fn, "node", None):
            fn.node.trait_type = "getter"
            fn.node.exported = [], type
        fn.trait_type = "getter"
        fn.exported = [], type
        return fn
    return inner

def setter(type):
    """
    Decorator to mark a method as a "setter".
    """
    def inner(fn):
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
        fn = argtypes
        fn.method = True
        return FunctionNode(fn, [], "void")
    def inner(fn):
        fn.method = True
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
