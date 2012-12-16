
import struct
from math import isnan

from fusion.bitstream.bitstream import BitStreamParseMixin
from fusion.bitstream.flash_formats import UI8, U32, S32, DOUBLE
from fusion.bitstream.formats import UTF8
from fusion.avm2.interfaces import ILoadable, IMultiname, IConstantPoolWriter
from fusion.avm2.util import serialize_u32 as u32, ValuePool

from zope.interface import implements, implementer
from zope.component import adapter, provideAdapter

from types import NoneType

# ======================================
# Constants
# ======================================

# ======================================
# Method Flags
# ======================================

class MethodFlag(object):
    # Suggest to the run-time that an arguments object (as specified by
    # the ActionScript 3.0 Language Reference) be created. Must not be used
    # together with MethodFlag.NeedRest
    Arguments     = 0x01

    # Must be set if this method uses the newactivation opcode
    Activation    = 0x02

    # This flag creates an ActionScript 3.0 ...rest arguments array.
    # Must not be used with MethodFlag.Arguments
    NeedRest      = 0x04

    # Must be set if this method has optional parameters and the options
    # field is present in this method_info structure.
    HasOptional   = 0x08

    # Undocumented as of now.
    IgnoreRest    = 0x10

    # Undocumented as of now. Assuming this flag is to implement the
    # "native" keyword in AS3.
    Native        = 0x20

    # Must be set if this method uses the dxns or dxnslate opcodes.
    SetsDxns      = 0x40

    # Must be set when the param_names field is present in this method_info
    # structure.
    HasParamNames = 0x80

# ======================================
# Types
# ======================================

class TypeIdentifier(object):
    UTF8        = 0x01

    # Number types
    Int         = 0x03
    UInt        = 0x04
    Double      = 0x06

    # Boolean types
    False       = 0x0A
    True        = 0x0B

    # Object types
    Undefined   = 0x00
    Null        = 0x0C

    # Namespace types
    PrivateNamespace   = 0x05
    Namespace          = 0x08
    PackageNamespace   = 0x16
    PackageInternalNs  = 0x17
    ProtectedNamespace = 0x18
    ExplicitNamespace  = 0x19
    StaticProtectedNs  = 0x1A

    # Namespace Set types
    NamespaceSet       = 0x15

    # Multiname types
    QName              = 0x07 # o.ns::name   - fully resolved at compile-time
    QNameA             = 0x0D # o.@ns::name
    Multiname          = 0x09 # o.name       - uses an nsset to resolve at runtime
    MultinameA         = 0x0E # o.@name
    RtqName            = 0x0F # o.ns::name   - namespace on stack
    RtqNameA           = 0x10 # o.@ns::name
    RtqNameL           = 0x11 # o.ns::[name] - namespace and name on stack
    RtqNameLA          = 0x12 # o.@ns::name
    MultinameL         = 0x1B # o.[name]     - name on stack
    MultinameLA        = 0x1C # o.@[name]
    TypeName           = 0x1D # o.ns::name.<types> - used to implement Vector

class _undefined(object):
    """
    The "undefined" object.
    """
    implements(ILoadable)
    def load(self, generator):
        generator.emit('pushundefined')

    def __eq__(self, other):
        return type(self) == type(other)

    def __repr__(self):
        return "undefined"

undefined = _undefined()

class _null(object):
    """
    The "null" object.
    """
    implements(ILoadable)
    def load(self, generator):
        generator.emit('pushnull')

    def __eq__(self, other):
        return type(self) == type(other)

    def __repr__(self):
        return "null"

null = _null()

# ======================================
# Namespace
# ======================================

class Namespace(object):
    implements(IConstantPoolWriter)
    def __init__(self, kind, name):
        self.kind = kind
        self.name = name
        self._name_index = None

    def __hash__(self):
        return hash((self.name, self.kind))

    def __eq__(self, other):
        return self.name == other.name and self.kind == other.kind

    def __ne__(self, other):
        return not self == other

    def write_constants(self, pool):
        self._name_index = pool.utf8.index_for(self.name)

    def serialize(self):
        return chr(self.kind) + u32(self._name_index)

    @classmethod
    def parse(cls, bitstream, pool):
        return cls(bitstream.read(UI8), pool.utf8.value_at(bitstream.read(U32)))

    def __repr__(self):
        kind = {0x16: "package", 0x08: "normal", 0x05: "private"}
        return "Namespace(name=%r, kind=%r)" % (self.name, kind.get(self.kind, self.kind))

# NamespaceSets
class NamespaceSet(object):
    """
    A "NamespaceSet" provides a list of namespaces, usually with
    a Multiname/MultinameL to search the scope stack.
    """
    implements(IConstantPoolWriter)
    def __init__(self, *namespaces):
        self.ns = namespaces
        self._ns_indices = None

    def __len__(self):
        return len(self.ns)

    def __hash__(self):
        return hash(tuple(self.ns))

    def __eq__(self, other):
        return self.ns == other.ns

    def __ne__(self, other):
        return not self == other

    def __repr__(self):
        return 'NamespaceSet(%r)' % (list(self.ns,))

    def write_constants(self, pool):
        self._ns_indices = [pool.namespace.index_for(v) for v in self.ns]

    @classmethod
    def parse(cls, bitstream, pool):
        ns = []
        for i in xrange(bitstream.read(U32)):
            ns.append(pool.namespace.value_at(bitstream.read(U32)))
        return cls(*ns)

    def serialize(self):
        return u32(len(self.ns)) + ''.join(u32(index) for index in self._ns_indices)

PACKAGE_NAMESPACE = Namespace(TypeIdentifier.PackageNamespace, "")
ANY_NAMESPACE     = Namespace(TypeIdentifier.Namespace, "*")

# This is the "AS3" namespace, which is used to get the internal builtin methods
# in case somebody overrides the prototype, or if AS3 changes ES5 semantics.
AS3_NAMESPACE     = Namespace(TypeIdentifier.Namespace, "http://adobe.com/AS3/2006/builtin")

NO_NAMESPACE_SET  = NamespaceSet()
PACKAGE_NSSET     = NamespaceSet(PACKAGE_NAMESPACE)

# ======================================
# Multinames
# ======================================

@adapter(_undefined)
@implementer(IMultiname)
def undef_to_IMultiname(mult):
    return QName("*")

provideAdapter(undef_to_IMultiname)

@adapter(NoneType)
@implementer(IMultiname)
def none_to_IMultiname(none):
    return QName("*")

provideAdapter(none_to_IMultiname)

@adapter(basestring)
@implementer(IMultiname)
def str_to_IMultiname(string):
    return QName(string)

provideAdapter(str_to_IMultiname)

# This is used in something like:
#   a = new Array();
#   print(a[0]);
# The index, 0, is converted to the string "0" and used as the name component as a QName.
# It's an awful hack, but it's how ECMAScript was designed.
@adapter(int)
@implementer(IMultiname)
def int_to_IMultiname(num):
    return QName(str(num))

provideAdapter(int_to_IMultiname)

def parse_multiname(bitstream, pool):
    kind = bitstream.read(U32)
    cls = MultinameKinds[kind]
    return cls.parse(bitstream, pool)

class MultinameL(object):
    implements(IMultiname, ILoadable, IConstantPoolWriter)

    kind = TypeIdentifier.MultinameL

    runtime = False
    runtime_namespace = True

    def __init__(self, ns_set=None):
        self.ns_set = ns_set or PACKAGE_NSSET
        self._ns_set_index = None

    def __eq__(self, other):
        return self.kind == other.kind and self.ns_set == other.ns_set

    def load(self, gen):
        gen.emit('getlex', self)

    def write_constants(self, pool):
        self._ns_set_index = pool.nsset.index_for(self.ns_set)

    @classmethod
    def parse(cls, bitstream, constants):
        return cls(constants.nsset.value_at(bitstream.read(U32)))

    def serialize(self):
        return chr(self.kind) + u32(self._ns_set_index)

class MultinameLA(MultinameL):
    kind = TypeIdentifier.MultinameLA

class Multiname(object):
    implements(IMultiname, ILoadable, IConstantPoolWriter)

    kind = TypeIdentifier.Multiname

    runtime = False
    runtime_namespace = False

    def __init__(self, name, ns_set=None):
        self.ns_set = ns_set or PACKAGE_NSSET
        self._ns_set_index = None
        self.name = name
        self._name_index = None

    def __eq__(self, other):
        return self.kind == other.kind and self.ns_set == other.ns_set and self.name == other.name

    def load(self, gen):
        gen.emit('getlex', self)

    def write_constants(self, pool):
        self._ns_set_index = pool.nsset.index_for(self.ns_set)
        self._name_index = pool.utf8.index_for(self.name)

    @classmethod
    def parse(cls, bitstream, constants):
        name = constants.utf8.value_at(bitstream.read(U32))
        nsset = constants.nsset.value_at(bitstream.read(U32))
        return cls(name, nsset)

    def serialize(self):
        return chr(self.kind) + u32(self._name_index) + u32(self._ns_set_index)

    def __str__(self):
        return '%s::%s' % (self.ns_set, self.name)

class MultinameA(Multiname):
    kind = TypeIdentifier.MultinameA

class QName(object):
    implements(IMultiname, ILoadable, IConstantPoolWriter)

    kind = TypeIdentifier.QName

    runtime = False
    runtime_namespace = False

    def __init__(self, name, ns=None):
        self.name = name
        self.ns = ns or PACKAGE_NAMESPACE

        self._name_index = None
        self._ns_index = None

    def __eq__(self, other):
        return self.kind == other.kind and self.ns == other.ns and self.name == other.name

    def __ne__(self, other):
        return not (self == other)

    def __hash__(self):
        return hash((self.ns, self.name))

    def __repr__(self):
        if self.ns.name:
            return "%s::%s" % (self.ns.name, self.name)
        return "%s" % (self.name,)

    def load(self, gen):
        if self.name == "*":
            gen.load(undefined)
        else:
            gen.emit('getlex', self)

    def write_constants(self, pool):
        if self.name == "*":
            self._name_index = 0
        else:
            self._name_index = pool.utf8.index_for(self.name)
        self._ns_index = pool.namespace.index_for(self.ns)

    @classmethod
    def parse(cls, bitstream, constants):
        ns = constants.namespace.value_at(bitstream.read(U32))
        nameidx = bitstream.read(U32)
        if nameidx == 0:
            name = "*"
        else:
            name = constants.utf8.value_at(nameidx)
        return cls(name, ns)

    def serialize(self):
        return chr(self.kind) + u32(self._ns_index) + u32(self._name_index)

class QNameA(QName):
    kind = TypeIdentifier.QNameA

# A convenient factory to get packaged QNames.
def packagedQName(ns, name):
    return QName(name, Namespace(TypeIdentifier.PackageNamespace, ns))

class RtqName(object):
    implements(IMultiname, ILoadable, IConstantPoolWriter)

    kind = TypeIdentifier.RtqName

    runtime = False
    runtime_namespace = True

    def __init__(self, name):
        self.name  = IMultiname(name)
        self._name_index = None

    def __eq__(self, other):
        return self.kind == other.kind and self.name == other.name

    def __hash__(self):
        return hash((self.name,))

    def __repr__(self):
        return "RT::%s" % (self.name,)

    def load(self, gen):
        gen.emit('getlex', self)

    def write_constants(self, pool):
        self._name_index = pool.multiname.index_for(self.name)

    @classmethod
    def parse(cls, bitstream, constants):
        name = constants.utf8.value_at(bitstream.read(U32))
        return cls(name)

    def serialize(self):
        return chr(self.kind) + u32(self._name_index)

class RtqNameA(RtqName):
    kind = TypeIdentifier.RtqNameA

class RtqNameL(object):
    implements(IMultiname, ILoadable, IConstantPoolWriter)

    kind = TypeIdentifier.RtqNameL

    runtime = True
    runtime_namespace = True

    def __eq__(self, other):
        return self.kind == other.kind

    def __hash__(self):
        return hash("RTQNAMEL") # XXX

    def __repr__(self):
        return "RT::RT"

    def load(self, gen):
        gen.emit('getlex', self)

    @classmethod
    def parse(cls, bitstream, constants):
        return cls()

    def serialize(self):
        return chr(self.kind)

class RtqNameLA(object):
    kind = TypeIdentifier.RtqNameLA

class TypeName(object):
    implements(IMultiname, ILoadable, IConstantPoolWriter)

    kind = TypeIdentifier.TypeName

    runtime = False
    runtime_namespace = False

    def __init__(self, name, types):
        self.name  = IMultiname(name)
        self.types = tuple(IMultiname(T) for T in types)

        self._name_index = None
        self._types_indices = None

    def __eq__(self, other):
        return self.kind == other.kind and self.name == other.name and self.types == other.types

    def __hash__(self):
        return hash((self.name, tuple(self.types)))

    def __repr__(self):
        return "%s.<%s>" % (self.name, ', '.join(str(a) for a in self.types))

    def load(self, gen):
        gen.load(self.name)
        gen.load_many(self.types)
        gen.emit('applytype', len(self.types))

    def write_constants(self, pool):
        self._name_index = pool.multiname.index_for(self.name)
        self._types_indices = [pool.multiname.index_for(t) for t in self.types]

    @classmethod
    def parse(cls, bitstream, constants):
        # XXX: forward references
        name = constants.multiname.value_at(bitstream.read(U32))
        types_count = bitstream.read(U32)
        types = [constants.multiname.value_at(bitstream.read(U32)) for i in xrange(types_count)]
        return cls(name, types)

    def serialize(self):
        code = [chr(self.kind)]
        code.append(u32(self._name_index))
        code.append(u32(len(self._types_indices)))
        code.extend(u32(a) for a in self._types_indices)
        return ''.join(code)

MultinameKinds = {
    TypeIdentifier.QName: QName,
    TypeIdentifier.QNameA: QNameA,
    TypeIdentifier.MultinameL: MultinameL,
    TypeIdentifier.MultinameLA: MultinameLA,
    TypeIdentifier.Multiname: Multiname,
    TypeIdentifier.MultinameA: MultinameA,
    TypeIdentifier.RtqName: RtqName,
    TypeIdentifier.RtqNameA: RtqNameA,
    TypeIdentifier.RtqNameL: RtqNameL,
    TypeIdentifier.RtqNameLA: RtqNameLA,
    TypeIdentifier.TypeName: TypeName,
}

# ======================================
# Constant Pool
# ======================================

class ConstantPool(BitStreamParseMixin):
    def __init__(self):
        self.int       = ValuePool(self, 0)

        # don't match -- pushuint is dumb
        self.uint      = ValuePool(self, 0, lambda v: False)
        self.double    = ValuePool(self, float('nan'), isnan)

        # don't match due to https://bugzilla.mozilla.org/show_bug.cgi?id=628031
        self.utf8      = ValuePool(self, "", lambda v: False)
        self.namespace = ValuePool(self, ANY_NAMESPACE)
        self.nsset     = ValuePool(self, "non-existant", lambda v: False)
        self.multiname = ValuePool(self, QName("*"))

    def write(self, value):
        try:
            IConstantPoolWriter(value).write_constants(self)
        except TypeError:
            pass

    def serialize(self):

        def double(double):
            return struct.pack("<d", double)

        def utf8(string):
            try:
                string = unicode(string, "latin-1")
            except TypeError:
                pass
            string = string.encode("utf8")
            return u32(len(string)) + string

        def serializable(item):
            return item.serialize()

        def write_pool(pool, fn):
            return u32(len(pool)) + ''.join(fn(i) for i in pool)

        bytes = ""
        bytes += write_pool(self.int, u32)
        bytes += write_pool(self.uint, u32)
        bytes += write_pool(self.double, double)
        bytes += write_pool(self.utf8, utf8)
        bytes += write_pool(self.namespace, serializable)
        bytes += write_pool(self.nsset, serializable)
        bytes += write_pool(self.multiname, serializable)

        return bytes

    @classmethod
    def from_bitstream(cls, bitstream):
        pool = cls()

        int_count = bitstream.read(U32)
        for i in xrange(1, int_count):
            pool.int.add_value(bitstream.read(S32))

        uint_count = bitstream.read(U32)
        for i in xrange(1, uint_count):
            pool.uint.add_value(bitstream.read(U32))

        double_count = bitstream.read(U32)
        for i in xrange(1, double_count):
            pool.double.add_value(bitstream.read(DOUBLE))

        utf8_count = bitstream.read(U32)
        for i in xrange(1, utf8_count):
            length = bitstream.read(U32)
            pool.utf8.add_value(bitstream.read(UTF8[length]))

        ns_count = bitstream.read(U32)
        for i in xrange(1, ns_count):
            pool.namespace.add_value(Namespace.parse(bitstream, pool))

        nsset_count = bitstream.read(U32)
        for i in xrange(1, nsset_count):
            pool.nsset.add_value(NamespaceSet.parse(bitstream, pool))

        mname_count = bitstream.read(U32)
        for i in xrange(1, mname_count):
            pool.multiname.add_value(parse_multiname(bitstream, pool))

        return pool
