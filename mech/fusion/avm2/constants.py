
import struct

from mech.fusion.bitstream.bitstream import BitStreamParseMixin
from mech.fusion.bitstream.flash_formats import UI8, U32, S32, DOUBLE
from mech.fusion.bitstream.formats import UTF8
from mech.fusion.avm2.interfaces import ILoadable
from mech.fusion.avm2.util import (serialize_u32 as s_u32,
                                   ValuePool, U32_MAX, S32_MAX)

from zope.interface import implements

# ======================================
# Constants
# ======================================

# ======================================
# Method Flags
# ======================================

"""
Suggest to the run-time that an arguments object (as specified by
the ActionScript 3.0 Language Reference) be created. Must not be used
together with METHODFLAG_NeedRest
"""
METHODFLAG_Arguments     = 0x01

"""
Must be set if this method uses the newactivation opcode
"""
METHODFLAG_Activation    = 0x02

"""
This flag creates an ActionScript 3.0 ...rest arguments array.
Must not by used with METHODFLAG_Arguments
"""
METHODFLAG_NeedRest      = 0x04

"""
Must be set if this method has optional parameters and the options
field is present in this method_info structure.
"""
METHODFLAG_HasOptional   = 0x08

"""
Undocumented as of now.
"""
METHODFLAG_IgnoreRest    = 0x10

"""
Undocumented as of now. Assuming this flag is to implement the
"native" keyword in AS3.
"""
METHODFLAG_Native        = 0x20

"""
Must be set if this method uses the dxns or dxnslate opcodes.
"""
METHODFLAG_SetsDxns      = 0x40

"""
Must be set when the param_names field is presetn in this method_info
structure.
"""
METHODFLAG_HasParamNames = 0x80

# ======================================
# Types
# ======================================

# String types
TYPE_STRING_Utf8                  = 0x01

# Number types
TYPE_NUMBER_Int                   = 0x03
TYPE_NUMBER_UInt                  = 0x04
TYPE_NUMBER_Double                = 0x06

# Boolean types
TYPE_BOOLEAN_False                = 0x0A
TYPE_BOOLEAN_True                 = 0x0B

# Object types
TYPE_OBJECT_Undefined             = 0x00
TYPE_OBJECT_Null                  = 0x0C

# Namespace types
TYPE_NAMESPACE_PrivateNamespace   = 0x05
TYPE_NAMESPACE_Namespace          = 0x08
TYPE_NAMESPACE_PackageNamespace   = 0x16
TYPE_NAMESPACE_PackageInternalNs  = 0x17
TYPE_NAMESPACE_ProtectedNamespace = 0x18
TYPE_NAMESPACE_ExplicitNamespace  = 0x19
TYPE_NAMESPACE_StaticProtectedNs  = 0x1A

TYPE_NAMESPACE_KINDS              = 0x05, 0x08, 0x16, 0x17, 0x18, 0x19, 0x1A

# Namespace Set types
TYPE_NAMESPACE_SET_NamespaceSet   = 0x15

# Multiname types
TYPE_MULTINAME_QName              = 0x07 # o.ns::name   - fully resolved at compile-time
TYPE_MULTINAME_QNameA             = 0x0D # o.@ns::name
TYPE_MULTINAME_Multiname          = 0x09 # o.name       - uses an nsset to resolve at runtime
TYPE_MULTINAME_MultinameA         = 0x0E # o.@name
TYPE_MULTINAME_RtqName            = 0x0F # o.ns::name   - namespace on stack
TYPE_MULTINAME_RtqNameA           = 0x10 # o.@ns::name
TYPE_MULTINAME_RtqNameL           = 0x11 # o.ns::[name] - namespace and name on stack
TYPE_MULTINAME_RtqNameLA          = 0x12 # o.@ns::name
# NameL and NameLA no longer exist.
# TYPE_MULTINAME_NameL              = 0x13 # o.[name]     - implied public namespace, name on stack
# TYPE_MULTINAME_NameLA             = 0x14 # o.@[name]
TYPE_MULTINAME_MultinameL         = 0x1B # o.[name]     -
TYPE_MULTINAME_MultinameLA        = 0x1C # o.@[name]
TYPE_MULTINAME_TypeName           = 0x1D # o.ns::name.<generic> - used to implement Vector

def has_RTNS(multiname):
    m = multiname.multiname()
    return m.KIND in (TYPE_MULTINAME_RtqName,
                      TYPE_MULTINAME_RtqNameA,
                      TYPE_MULTINAME_RtqNameL,
                      TYPE_MULTINAME_RtqNameLA)

def has_RTName(multiname):
    m = multiname.multiname()
    return m.KIND in (TYPE_MULTINAME_MultinameL,
                      TYPE_MULTINAME_MultinameLA,
                      TYPE_MULTINAME_RtqNameL,
                      TYPE_MULTINAME_RtqNameLA)

class _undefined(object):
    implements(ILoadable)
    def load(self, generator):
        generator.push_undefined()

    def __eq__(self, other):
        return type(self) == type(other)

    def __repr__(self):
        return "undefined"

undefined = _undefined()

class _null(object):
    implements(ILoadable)
    def load(self, generator):
        generator.push_null()

    def __eq__(self, other):
        return type(self) == type(other)

    def __repr__(self):
        return "null"

null = _null()

def py_to_abc(value, pool):
    if value is True:
        return TYPE_BOOLEAN_True, 0
    if value is False:
        return TYPE_BOOLEAN_False, 0
    if value is None or value is null:
        return TYPE_OBJECT_Null, 0
    if value is undefined:
        return TYPE_OBJECT_Undefined, 0
    if isinstance(value, basestring):
        return TYPE_STRING_Utf8, pool.utf8_pool.index_for(value)
    if isinstance(value, (long, int)):
        if value > U32_MAX or value < -S32_MAX:
            return TYPE_NUMBER_Double, pool.double_pool.index_for(value)
        elif value < 0:
            return TYPE_NUMBER_Int, pool.int_pool.index_for(value)
        else:
            return TYPE_NUMBER_UInt, pool.uint_pool.index_for(value)
    if isinstance(value, float):
        return TYPE_NUMBER_Double, pool.double_pool.index_for(value)
    if isinstance(value, Namespace):
        return value.kind, pool.namespace_pool.index_for(value)
    if isinstance(value, NamespaceSet):
        return TYPE_NAMESPACE_SET_NamespaceSet, pool.nsset_pool.index_for(value)
    if hasattr(value, "multiname"):
        return value.multiname().KIND, pool.multiname_pool.index_for(value.multiname())
    raise ValueError("This is not an ABC-compatible type.")

def abc_to_py(tup, pool):
    index, TYPE = tup
    if TYPE == TYPE_BOOLEAN_True:
        return True
    if TYPE == TYPE_BOOLEAN_False:
        return False
    if TYPE == TYPE_OBJECT_Null:
        return null
    if TYPE == TYPE_OBJECT_Undefined:
        return undefined
    if TYPE == TYPE_STRING_Utf8:
        return pool.utf8_pool.value_at(index)
    if TYPE == TYPE_NUMBER_Double:
        return pool.double_pool.value_at(index)
    if TYPE == TYPE_NUMBER_UInt:
        return pool.uint_pool.value_at(index)
    if TYPE == TYPE_NUMBER_Int:
        return pool.int_pool.value_at(index)
    if TYPE in TYPE_NAMESPACE_KINDS:
        return pool.namespace_pool.value_at(index)
    if TYPE == TYPE_NAMESPACE_SET_NamespaceSet:
        return pool.nsset_pool.value_at(index)
    if TYPE in MULTINAME_KINDS:
        return pool.multiname_pool.value_at(index)
    raise ValueError("Unknown ABC type value %d." % (TYPE,))

def mn_utf8(bitstream, constants):
    namei = bitstream.read(U32)
    if namei == 0:
        return "*"
    return constants.utf8_pool.value_at(namei)

# ======================================
# Namespaces
# ======================================

class Namespace(object):
    def __init__(self, kind, name):
        self.kind = kind
        self.name = name
        self._name_index = None

    def __hash__(self):
        return hash((self.name, self.kind))

    def __eq__(self, other):
        return isinstance(other, type(self)) and self.name == other.name and self.kind == other.kind

    def __ne__(self, other):
        return not self == other

    def write_to_pool(self, pool):
        self._name_index = pool.utf8_pool.index_for(self.name)

    def serialize(self):
        assert self._name_index is not None, "Please call write_to_pool before serializing"
        return chr(self.kind) + s_u32(self._name_index)

    @classmethod
    def parse(cls, bitstream, constants):
        return cls(bitstream.read(UI8), constants.utf8_pool.value_at(bitstream.read(U32)))

    def __repr__(self):
        kind = {0x16: "package", 0x08: "normal", 0x05: "private"}
        return "Namespace(name=%r, kind=%r)" % (self.name, kind.get(self.kind, self.kind))

class NamespaceSet(object):
    def __init__(self, *namespaces):
        self.namespaces = namespaces
        self._namespace_indices = None

    def __len__(self):
        return len(self.namespaces)

    def __hash__(self):
        return hash(tuple(self.namespaces))

    def __eq__(self, other):
        return  isinstance(other, type(self)) and self.namespaces == other.namespaces

    def __ne__(self, other):
        return not self == other

    def write_to_pool(self, pool):
        self._namespace_indices = [pool.namespace_pool.index_for(ns) for ns in self.namespaces]

    def __repr__(self):
        return 'NamespaceSet(%r)' % (list(self.namespaces,))

    @classmethod
    def parse(cls, bitstream, constants):
        return cls(*(constants.namespace_pool.value_at(bitstream.read(U32)) for i in xrange(bitstream.read(U32))))

    def serialize(self):
        assert self._namespace_indices is not None, "Please call write_to_pool before serializing"
        return s_u32(len(self.namespaces)) + ''.join(s_u32(index) for index in self._namespace_indices)


NO_NAMESPACE  = Namespace(TYPE_NAMESPACE_Namespace, "")
ANY_NAMESPACE = Namespace(TYPE_NAMESPACE_Namespace, "*")

PACKAGE_NAMESPACE   = Namespace(TYPE_NAMESPACE_PackageNamespace, "")
PACKAGE_I_NAMESPACE = Namespace(TYPE_NAMESPACE_PackageInternalNs, "")
PRIVATE_NAMESPACE   = Namespace(TYPE_NAMESPACE_PrivateNamespace, "")
AS3_NAMESPACE       = Namespace(TYPE_NAMESPACE_Namespace, "http://adobe.com/AS3/2006/builtin")

NO_NAMESPACE_SET = NamespaceSet()
PACKAGE_NSSET    = NamespaceSet(PACKAGE_NAMESPACE)
PROP_NAMESPACE_SET = NamespaceSet(PRIVATE_NAMESPACE, PACKAGE_NAMESPACE, PACKAGE_I_NAMESPACE, AS3_NAMESPACE)

def packagedQName(ns, name):
    return QName(name, Namespace(TYPE_NAMESPACE_PackageNamespace, ns))

# ======================================
# Multinames
# ======================================

class MultinameL(object):
    KIND = TYPE_MULTINAME_MultinameL

    def __init__(self, ns_set):
        self.ns_set = ns_set
        self._ns_set_index = None

    def __eq__(self, other):
        return isinstance(other, type(self)) and self.KIND == other.KIND and self.ns_set == other.ns_set

    def __ne__(self, other):
        return not self == other

    def __hash__(self):
        return hash((self.KIND, self.ns_set))

    def __repr__(self):
        return "MultinameL(%r)" % (self.ns_set)

    def write_to_pool(self, pool):
        self._ns_set_index = pool.nsset_pool.index_for(self.ns_set)

    @classmethod
    def parse_inner(cls, bitstream, constants):
        return cls(constants.nsset_pool.value_at(bitstream.read_u32()))

    def serialize(self):
        assert self._ns_set_index is not None, "Please call write_to_pool before serializing"
        return chr(self.KIND) + s_u32(self._ns_set_index)

    def multiname(self):
        return self

class MultinameLA(MultinameL):
    KIND = TYPE_MULTINAME_MultinameLA

class Multiname(MultinameL):
    KIND = TYPE_MULTINAME_Multiname

    def __init__(self, name, ns_set):
        super(Multiname, self).__init__(ns_set)
        self.name = name
        self._name_index = None

    def __eq__(self, other):
        return isinstance(other, self.__class__) and self.KIND == other.KIND and self.name == other.name

    def __ne__(self, other):
        return not self == other

    def __hash__(self):
        return hash((self.KIND, self.name))

    def __repr__(self):
        return "%s::%s" % (self.ns_set, self.name)

    def write_to_pool(self, pool):
        super(Multiname, self).write_to_pool(pool)
        assert self.name != ""
        if self.name == "*":
            self._name_index = 0
        else:
            self._name_index = pool.utf8_pool.index_for(self.name)

    @classmethod
    def parse_inner(cls, bitstream, constants):
        return cls(mn_utf8(bitstream, constants), constants.nsset_pool.value_at(bitstream.read(U32)))

    @classmethod
    def parse(cls, bitstream, constants):
        kind = bitstream.read(UI8)
        cls = MULTINAME_KINDS[kind]
        return cls.parse_inner(bitstream, constants)

    def serialize(self):
        assert self._name_index is not None, "Please call write_to_pool before serializing"
        assert self._ns_set_index is not None, "Please call write_to_pool before serializing"
        return chr(self.KIND) + s_u32(self._name_index) + s_u32(self._ns_set_index)

class MultinameA(Multiname):
    KIND = TYPE_MULTINAME_MultinameA

class QName(object):
    KIND = TYPE_MULTINAME_QName

    def __new__(typ, name, ns=None):
        if ns is None:
            m = getattr(name, "multiname", None)
            if name is undefined:
                return undefined
            if m:
                s = m()
                return s
        return object.__new__(typ)

    def __init__(self, name, ns=None):
        if getattr(self, "name", None): return

        self.name = name
        self.ns = ns or PACKAGE_NAMESPACE

        self._name_index = None
        self._ns_index = None

        self._init = True

    def __eq__(self, other):
        return isinstance(other, type(self)) and self.KIND == other.KIND and self.name == other.name and self.ns == other.ns

    def __ne__(self, other):
        return not self == other

    def __hash__(self):
        return hash((self.KIND, self.name, self.ns))

    def write_to_pool(self, pool):
        assert self.name != ""
        if self.name == "*":
            self._name_index = 0
        else:
            self._name_index = pool.utf8_pool.index_for(self.name)
        self._ns_index = pool.namespace_pool.index_for(self.ns)

    @classmethod
    def parse_inner(cls, bitstream, constants):
        return cls(ns=constants.namespace_pool.value_at(bitstream.read(U32)),
                   name=mn_utf8(bitstream, constants))

    def serialize(self):
        assert self._name_index is not None, "Please call write_to_pool before serializing"
        assert self._ns_index is not None, "Please call write_to_pool before serializing"
        return chr(self.KIND) + s_u32(self._ns_index) + s_u32(self._name_index)

    def multiname(self):
        return self

    def __repr__(self):
        if self.ns.name:
            return "%s::%s" % (self.ns.name, self.name)
        return "%s" % (self.name,)

class QNameA(QName):
    KIND = TYPE_MULTINAME_QNameA

class RtqNameL(object):
    KIND = TYPE_MULTINAME_RtqNameL

    def __eq__(self, other):
        return isinstance(other, self.__class__) and self.KIND == other.KIND

    def __ne__(self, other):
        return not self == other

    def __hash__(self):
        return hash((self.KIND))

    def multiname(self):
        return self

    @classmethod
    def parse_inner(cls, bitstream, constants):
        return cls()

    def serialize(self):
        return chr(self.KIND)

class RtqNameLA(RtqNameL):
    KIND = TYPE_MULTINAME_RtqNameLA

class RtqName(object):
    KIND = TYPE_MULTINAME_RtqName

    def __init__(self, name):
        self.name = name
        self._name_index = None

    def __eq__(self, other):
        return isinstance(other, self.__class__) and self.KIND == other.KIND and self.name == other.name

    def __ne__(self, other):
        return not self == other

    def __hash__(self):
        return hash((self.KIND, self.name))

    def write_to_pool(self, pool):
        assert self.name != ""
        # if self.name == "*":
        #     self._name_index = 0
        # else:
        self._name_index = pool.utf8_pool.index_for(self.name)

    @classmethod
    def parse_inner(cls, bitstream, constants):
        return cls(constants.utf8_pool.value_at(bitstream.read_u32()))

    def serialize(self):
        assert self._name_index is not None, "Please call write_to_pool before serializing"
        return chr(self.KIND) + s_u32(self._name_index)

    def multiname(self):
        return self

class RtqNameA(RtqName):
    KIND = TYPE_MULTINAME_RtqNameA

class TypeName(object):
    KIND = TYPE_MULTINAME_TypeName

    def __init__(self, name, *types):
        self.name  = name.multiname()
        self.types = [T.multiname() for T in types]

        self._name_index = None
        self._types_indices = None

    def __repr__(self):
        return "%s.<%s>" % (self.name, ','.join(str(a) for a in self.types))

    def __eq__(self, other):
        return isinstance(other, self.__class__) and self.KIND == other.KIND and self.name == other.name and self.types == other.types

    def __ne__(self, other):
        return not self == other

    def __hash__(self):
        return hash((self.KIND, self.name, tuple(self.types)))

    def write_to_pool(self, pool):
        self._name_index = pool.multiname_pool.index_for(self.name)
        self._types_indices = [pool.multiname_pool.index_for(t) for t in self.types]

    @classmethod
    def parse_inner(cls, bitstream, constants):
        return cls(constants.multiname_pool.value_at(bitstream.read_u32()),
                 *(constants.multiname_pool.value_at(bitstream.read_u32()) for i in xrange(bitstream.read_u32())))

    def serialize(self):
        assert self._name_index is not None, "Please call write_to_pool before serializing"
        assert self._types_indices is not None, "Please call write_to_pool before serializing"
        return ''.join([chr(self.KIND), s_u32(self._name_index), s_u32(len(self._types_indices))] + [s_u32(a) for a in self._types_indices])

    def multiname(self):
        return self

MULTINAME_KINDS = {}
MULTINAME_KINDS[MultinameL.KIND]  = MultinameL
MULTINAME_KINDS[MultinameLA.KIND] = MultinameLA
MULTINAME_KINDS[Multiname.KIND]   = Multiname
MULTINAME_KINDS[MultinameA.KIND]  = MultinameA
# MULTINAME_KINDS[NameL.KIND]       = NameL
# MULTINAME_KINDS[NameLA.KIND]      = NameLA
MULTINAME_KINDS[QName.KIND]       = QName
MULTINAME_KINDS[QNameA.KIND]      = QNameA
MULTINAME_KINDS[RtqNameL.KIND]    = RtqNameL
MULTINAME_KINDS[RtqNameLA.KIND]   = RtqNameLA
MULTINAME_KINDS[RtqName.KIND]     = RtqName
MULTINAME_KINDS[RtqNameA.KIND]    = RtqNameA
MULTINAME_KINDS[TypeName.KIND]    = TypeName

# ======================================
# Constant Pool
# ======================================

class AbcConstantPool(BitStreamParseMixin):
    write_to = "pool"

    def __init__(self):
        self.int_pool       = ValuePool(0, self)
        self.uint_pool      = ValuePool(0, self)
        self.double_pool    = ValuePool(float("nan"), self)
        self.utf8_pool      = ValuePool(object(), self, True) # Don't use "" because of multinames.
        self.namespace_pool = ValuePool(ANY_NAMESPACE, self)
        self.nsset_pool     = ValuePool(NO_NAMESPACE_SET, self)
        self.multiname_pool = ValuePool(undefined, self)

    def write(self, value):
        if hasattr(value, "write_to_pool"):
            value.write_to_pool(self)

    def debug_print(self):
        print "int:   ", self.int_pool
        print "uint:  ", self.uint_pool
        print "double:", self.double_pool
        print "utf8:  ", self.utf8_pool
        print "ns:    ", self.namespace_pool
        print "nsset: ", self.nsset_pool
        print "mname: ", self.multiname_pool

    def serialize(self):

        def double(double):
            return struct.pack("<d", double)

        def utf8(string):
            return s_u32(len(string)) + string.encode("utf8")

        def serializable(item):
            return item.serialize()

        def write_pool(pool, fn):
            return s_u32(len(pool)) + ''.join(fn(i) for i in pool)

        buffer = ""
        buffer += write_pool(self.int_pool, s_u32)
        buffer += write_pool(self.uint_pool, s_u32)
        buffer += write_pool(self.double_pool, double)
        buffer += write_pool(self.utf8_pool, utf8)
        buffer += write_pool(self.namespace_pool, serializable)
        buffer += write_pool(self.nsset_pool, serializable)
        buffer += write_pool(self.multiname_pool, serializable)

        return buffer

    @classmethod
    def from_bitstream(cls, bitstream):
        pool = cls()

        def format(format):
            def inner():
                return bitstream.read(format)
            return inner

        def utf8():
            return bitstream.read(UTF8[bitstream.read(U32)])

        def serializable(item):
            def _inner():
                return item.parse(bitstream, pool)
            return _inner

        def read_pool(P, fn):
            L = bitstream.read(U32)
            for i in xrange(L-1):
                P.index_for(fn(), allow_conflicts=True)

        read_pool(pool.int_pool, format(S32))
        read_pool(pool.uint_pool, format(U32))
        read_pool(pool.double_pool, format(DOUBLE))
        read_pool(pool.utf8_pool, utf8)
        read_pool(pool.namespace_pool, serializable(Namespace))
        read_pool(pool.nsset_pool, serializable(NamespaceSet))
        read_pool(pool.multiname_pool, serializable(Multiname))

        return pool









