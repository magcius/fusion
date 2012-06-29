
class AtomTypes(object):
    NumberType        = 0
    BooleanType       = 1
    StringType        = 2
    ObjectType        = 3
    MovieClipType     = 4
    NullType          = 5
    UndefinedType     = 6
    ReferenceType     = 7
    ArrayType         = 8
    ObjectEndType     = 9
    StrictArrayType   = 10
    DateType          = 11
    LongStringType    = 12
    UnsupportedType   = 13
    RecordSetType     = 14
    XMLType           = 15
    TypedObjectType   = 16
    AvmPlusObjectType = 17
    NamespaceType     = 18

    # This one is special: When passed to the debugger, it indicates
    # that the "variable" is not a variable at all, but rather is a
    # class name.  For example, if class Y extends class X, then
    # we will send a kDTypeTraits for class Y; then we'll send all the
    # members of class Y; then we'll send a kDTypeTraits for class X;
    # and then we'll send all the members of class X.  This is only
    # used by the AVM+ debugger.
    TraitsType        = 19

class VariableTypes(object):
    Number    = 0
    Boolean   = 1
    String    = 2
    Object    = 3
    Function  = 4
    MovieClip = 5
    Null      = 6
    Undefined = 7
    Unknown   = 8

    _name_mapping = {
        Number: "Number",
        Boolean: "Boolean",
        String: "String",
        Null: "null",
        Undefined: "undefined",
    }

    @classmethod
    def get_name(cls, vartype):
        return cls._name_mapping[vartype]

    _atom_mapping = {
        AtomTypes.NumberType: Number,
        AtomTypes.BooleanType: Boolean,
        AtomTypes.StringType: String,
        AtomTypes.MovieClipType: MovieClip,
        AtomTypes.NullType: Null,
        AtomTypes.UndefinedType: Undefined
    }

    @classmethod
    def from_atom(cls, atomtype, isfunc):
        if atomtype == AtomTypes.ObjectType:
            return cls.Function if isfunc else cls.Object
        return cls._atom_mapping[atomtype]

class AVM1ClassTypes(object):
    Normal          = 0
    XMLSocket       = 1
    TextField       = 2
    Button          = 3
    Number          = 4
    Boolean         = 5
    String          = 6
    Array           = 7
    Date            = 8
    Sound           = 9
    XML             = 10
    XMLNode         = 11
    Camera          = 12
    Microphone      = 13
    Communication   = 14
    NetConnection   = 15
    NetStream       = 16
    Video           = 17
    TextFormat      = 18
    Shared          = 19
    SharedData      = 20
    PrintJob        = 21
    MovieClipLoader = 22
    StyleSheet      = 23
    FapPacketDummy  = 24
    LoadVars        = 25
    TextSnapshot    = 26

    _name_mapping = ['Normal', 'XMLSocket', 'TextField', 'Button', 'Number',
     'Boolean', 'String', 'Array', 'Date', 'Sound', 'XML',
     'XMLNode', 'Camera', 'Microphone', 'Communication', 'NetConnection',
     'NetStream', 'Video', 'TextFormat', 'Shared', 'SharedData', 'PrintJob',
     'MovieClipLoader', 'StyleSheet', 'FapPacketDummy', 'LoadVars',
     'TextSnapshot']

    @classmethod
    def get_classname(cls, classtype, ismc):
        if classtype == cls.Normal:
            return "MovieClip" if ismc else "Object"
        return cls._name_mapping[classtype]


class PointerValue(object):
    def __init__(self, addr):
        self.addr = addr

class DebugValue(object):

    UnknownID = -1 # primitive types
    GlobalID  = -2 # _global
    ThisID    = -3 # this
    RootID    = -4 # _root

    # Magic ID for the top frame of the stack.
    # Locals and arguments are members of this psuedo-variable.
    # This is the base Stack ID, subsequent stack frames have
    # BaseID-1, BaseID-2, etc.
    BaseID    = -100

    LevelID   = -300 # Remember _level0?

    def __init__(self, vartype, typename, classname, attr, value):
        self.vartype = vartype
        self.typename = typename
        self.classname = classname
        self.attr = attr
        self.value = value

        self.members = None

    def fetch_members(self, context):
        if self.members is not None:
            return

        oid = self.id
        if oid == self.UnknownID:
            return

        context.obtain_members(oid)

    @classmethod
    def for_pointer(cls, addr):
        return cls(VariableTypes.Unknown, None, None, 0, PointerValue(addr))

    @property
    def id(self):
        try:
            return self.value.addr
        except AttributeError:
            return self.UnknownID

    @property
    def is_traits(self):
        return self.id == self.UnknownID and self.typename == "traits"

class DebugVariable(object):
    def __init__(self, name, value):
        self.raw_name = name

        if "::" in name:
            ns, name = name.split("::", 1)
        else:
            ns, name = "", name

        ns = ns.partition("@", 1)[0]

        self.ns, self.name = ns, name
        self.value = value

        self.level, self.definingclass = None, None

    @property
    def fqname(self):
        """
        Fully qualified name.
        """
        if self.ns:
            return "%s::%s" % (self.ns, self.name)
        return self.name

    @property
    def is_traits(self):
        return self.value.is_traits

    def get_value(self, context):
        pass
