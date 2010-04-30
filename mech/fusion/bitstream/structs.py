
import sys
import operator

from types import NoneType

from mech.fusion.bitstream.bitstream import BitStream, BitStreamParseMixin
from mech.fusion.bitstream.formats import UB, FormatArray

from mech.fusion.bitstream.interfaces import IBitStream, IFormat, IFormatLength
from mech.fusion.bitstream.interfaces import IStruct, IAutoStruct, IStructClass
from mech.fusion.bitstream.interfaces import IStructEvaluateable, IStructStatement

from zope.interface import implements, classProvides
from zope.component import adapter, provideAdapter

class IterableStructStatementAdapter(object):
    implements(IStructStatement)

    def __init__(self, statements):
        self.statements = statements

    def _struct_read(self, struct, bitstream):
        for stat in self.statements:
            stat._struct_read(struct, bitstream)

    def _struct_write(self, struct, bitstream):
        for stat in self.statements:
            stat._struct_write(struct, bitstream)

provideAdapter(IterableStructStatementAdapter, [list], IStructStatement)
provideAdapter(IterableStructStatementAdapter, [tuple], IStructStatement)

class FormatStructStatementAdapter(object):
    def __init__(self, format):
        self.format = format

    def _pre_write(self, struct):
        self.format._pre_write(struct, self)
    
    def _struct_read(self, struct, bitstream):
        bitstream.read(format)

    def _struct_write(self, struct, bitstream):
        bitstream.write(format)

provideAdapter(FormatStructStatementAdapter, [IFormat], IStructStatement)

class Atom(object):
    implements(IStructEvaluateable)
    
    def __init__(self, function):
        self.function = function
    
    def _evaluate(self, struct):
        return self.function(struct)
    
    def and_(self, other):
        def atom_and(struct):
            return IStructEvaluateable(self) ._evaluate(struct) \
               and IStructEvaluateable(other)._evaluate(struct)
        return Atom(atom_and)

    def or_(self, other):
        def atom_or(struct):
            return IStructEvaluateable(self) ._evaluate(struct) \
                or IStructEvaluateable(other)._evaluate(struct)
        return Atom(atom_or)

    def not_(self):
        def atom_not(struct):
            return not IStructEvaluateable(self)._evaluate(struct)
        return Atom(atom_not)
    
    __and__ = and_
    __or__  = or_

and_ = Atom.and_
or_ = Atom.or_

def binary_atomizer(name):
    def atom(self, other):
        def atom(struct):
            self_  = IStructEvaluateable(self)._evaluate(struct)
            other_ = IStructEvaluateable(other)._evaluate(struct)
            return getattr(operator, name)(self_, other_)
        atom.__name__ = "atom_%s_%s_%s" % (name, self, other)
        return Atom(atom)
    atom.__name__ = "__%s__" % (name,)
    return atom

def unary_atomizer(name):
    def atom(self):
        def atom(struct):
            return getattr(IStructEvaluateable(self)._evaluate(struct),
                           "__%s__" % (name,))()
        atom.__name__ = "atom_%s_%s" % (name, self)
        return Atom(atom)
    atom.__name__ = "__%s__" % (name,)
    return atom

SOPMAP = dict(add="sub", sub="add", mul="div", div="mul")

def simple_op_filter(name):
    name_write = "__%s__" % (name,)
    name_read  = "__%s__" % (SOPMAP[name],)
    def op(self, other):
        def op_filter_read(struct, value):
            return getattr(value, name_read) \
                   (IStructEvaluateable(other)._evaluate(struct))
        def op_filter_write(struct, value):
            return getattr(value, name_write) \
                   (IStructEvaluateable(other)._evaluate(struct))
        self.filter_read .append(op_filter_read)
        self.filter_write.append(op_filter_write)
        return self
    op.__name__ = "__%s__" % (name,)
    return op

class FieldTemp(object):

    implements(IStructStatement)
    default = True

    def __init__(self, name, format=None):
        self.name = name
        self.format = format
        self.filter_read  = []
        self.filter_write = []

    def _pre_read(self, struct):
        self._struct_set(struct, self.default)

    def _pre_write(self, struct):
        IFormat(self.format)._pre_write(struct, self)

    def _struct_get(self, struct):
        raise NotImplementedError

    def _struct_set(self, struct, value):
        raise NotImplementedError

    def _filter_read(self, struct, argument):
        for filter in self.filter_read:
            argument = filter(struct, argument)
        return argument

    def _filter_write(self, struct, argument):
        for filter in self.filter_write:
            argument = filter(struct, argument)
        return argument

    def _struct_read(self, struct, bitstream):
        format = IFormat(self.format)
        format = IStructEvaluateable(format)._evaluate(struct)
        value  = self._filter_read(struct, bitstream.read(format))
        self._struct_set(struct, value)
        return value

    def _struct_write(self, struct, bitstream):
        format = IFormat(self.format)
        format = IStructEvaluateable(format)._evaluate(struct)
        bitstream.write(self._filter_write(struct, self._struct_get(struct)),
                        format)

    __eq__  = binary_atomizer("eq")
    __ne__  = binary_atomizer("ne")
    __ge__  = binary_atomizer("ge")
    __le__  = binary_atomizer("le")
    __lt__  = binary_atomizer("lt")
    __gt__  = binary_atomizer("gt")

    __and__ = binary_atomizer("and") # bitwise and
    __or__  = binary_atomizer("or")  # bitwise or
    __xor__ = binary_atomizer("xor") # bitwise xor

    __nonzero__ = unary_atomizer("nonzero")

    __add__ = simple_op_filter("add")
    __sub__ = simple_op_filter("sub")
    __mul__ = simple_op_filter("mul")
    __div__ = simple_op_filter("div")

@adapter(FieldTemp)
class FieldStructEvaluateableAdapter(object):
    implements(IStructEvaluateable)
    def __init__(self, field):
        self.field = field

    def _evaluate(self, struct):
        return self.field._struct_get(struct)

provideAdapter(FieldStructEvaluateableAdapter)

class Field(FieldTemp):
    def _struct_set(self, struct, value):
        return setattr(struct, self.name, value)

    def _struct_get(self, struct):
        return getattr(struct, self.name)

    def __str__(self):
        return "Field(%r, %r)" % (self.name, self.format)
    
class Local(FieldTemp):
    def _struct_set(self, struct, value):
        struct.set_local(self.name, value)

    def _struct_get(self, struct):
        return struct.get_local(self.name)

    def __str__(self):
        return "Local(%r, %r)" % (self.name, self.format)

class FieldTempArray(Field):
    var_name = None
    default = []
    def __init__(self, fields, format):
        if isinstance(fields, basestring):
            self.fields = fields.split()
        else:
            self.fields = fields
        repeat = len(self.fields)
        super(FieldTempArray, self).__init__(None, FormatArray(format, repeat))

    def _struct_set(self, struct, value):
        for k, v in zip(self.fields, value):
            getattr(struct, self.var_name)[k] = v

    def _struct_get(self, struct):
        return [getattr(struct, self.var_name)[k] for k in self.fields]

    def _filter_read(self, struct, value):
        for filter in self.filter_read:
            value = [filter(struct, a) for a in value]
        return value

    def _filter_write(self, struct, value):
        for filter in self.filter_write:
            value = [filter(struct, a) for a in value]
        return value

    def __str__(self):
        return "Fields(%r)" % (' '.join(self.fields),)
    
class Fields(FieldTempArray):
    var_name = "_FIELDS"

class Locals(FieldTempArray):
    var_name = "_TEMP_FIELDS"

class NBitsMeta(type):
    
    implements(IStructEvaluateable, IFormatLength)
    
    def __getitem__(self, item):
        return self(length=item)
    
    def __str__(self):
        return "NBits"

    @staticmethod
    def _evaluate(struct):
        return struct.get_local("NBits%d" % \
                   (struct.get_local("NBitsCount"),))

    @staticmethod
    def _pre_write_inner(struct, format, field):
        value = field._filter_write(struct, field._struct_get(struct))
        if isinstance(value, (int, float, long)):
            value = [value]
        nbits = format._nbits(*value)
        name = "NBits%d" % (struct.get_local("NBitsCount"),)
        if nbits > struct.get_local(name, -1):
            struct.set_local(name, nbits)

class NBits(object):
    
    __metaclass__ = NBitsMeta

    implements(IStructStatement)
    
    def __init__(self, length):
        self.length = length
        # XXX: find a better way to do this
        frame = sys._getframe(2)
        self.hash = (frame.f_lineno, frame.f_code.co_filename)
    
    def _prequel(self, struct):
        self.count = struct.get_local("NBitsCount", 0) + 1
        struct.set_local("NBitsCount", self.count)
        self.name = "NBits%d" % (self.count,)
        
    def _pre_read(self, struct):
        self._prequel(struct)

    def _pre_write(self, struct):
        self._prequel(struct)

    def _realquel(self, struct):
        struct.set_local("NBitsCount", self.count)

    def _struct_read(self, struct, bitstream):
        self._realquel(struct)
        struct.set_local(self.name,
                   bitstream.read(UB[self.length]))

    def _struct_write(self, struct, bitstream):
        self._realquel(struct)
        bitstream.write(struct.get_local(self.name),
                        UB[self.length])

    def __hash__(self):
        return hash(self.hash)

    def __eq__(self, other):
        return isinstance(other, type(self)) and self.hash == other.hash
    
    def __str__(self):
        return "NBits[%d]" % (self.length,)

def Enum(field, enum, **kwargs):
    enum  = enum.copy()
    renum = {}
    for k, v in enum.iteritems():
        renum[v] = k
    if "default" in kwargs:
        def map_filter_r(key, struct):
            return renum.get(key, kwargs["default"])
        def map_filter_w(key, struct):
            return enum.get(key, kwargs["default"])
    else:
        def map_filter_r(key, struct):
            return renum[key]
        def map_filter_w(key, struct):
            return enum[key]
    field.filter_read .append(map_filter_r)
    field.filter_write.append(map_filter_w)
    return field

def Map(field, read, write):
    field.filter_read .append(read)
    field.filter_write.append(write)
    return field

class StructMixin(BitStreamParseMixin):
    @adapter(IFormat)
    def as_format(self):
        return IFormat(self.as_bitstream())

class IdentityStructEvaluateableAdaptor(object):
    def __init__(self, value):
        self.value = value

    def _evaluate(self, struct):
        return self.value

provideAdapter(IdentityStructEvaluateableAdaptor, [int], IStructEvaluateable)
provideAdapter(IdentityStructEvaluateableAdaptor, [long], IStructEvaluateable)
provideAdapter(IdentityStructEvaluateableAdaptor, [str], IStructEvaluateable)
provideAdapter(IdentityStructEvaluateableAdaptor, [NoneType], IStructEvaluateable)

class Struct(StructMixin):
    """
    A struct of bit fields.
    """
    
    implements(IAutoStruct)
    classProvides(IFormat, IStructClass)
    
    def __init__(self, kwargs=None):
        self.reading, self.writing = False, False
        self._FIELDS = kwargs or {}
        if "self" in self._FIELDS:
            del self._FIELDS["self"]
        self.__setattr__ = self._setattr

    def create_fields(self):
        pass

    def __str__(self):
        return "<%s: %s>" % (type(self).__name__,
            ', '.join("%r=%s" % (k, v) for k, v in self._FIELDS.iteritems()))

    def __getattr__(self, name):
        try:
            return self._FIELDS[name]
        except KeyError, e:
            raise AttributeError(str(e))

    def _setattr(self, name, value):
        self._FIELDS[name] = value

    def set(self, field, value):
        field._struct_set(self, IStructEvaluateable(value)._evaluate(self))

    def get(self, field, default=None):
        if default is not None:
            try:
                return field._struct_get(self)
            except KeyError:
                return default
        return field._struct_get(self)

    def get_local(self, name, default=None):
        if default is not None:
            return self._TEMP_FIELDS.get(name, default)
        return self._TEMP_FIELDS[name]

    def set_local(self, name, value):
        self._TEMP_FIELDS[name] = IStructEvaluateable(value)._evaluate(self)

    @classmethod
    def _read(cls, bs, cursor):
        return cls.from_bitstream(bs)

    @classmethod
    def _write(cls, bs, cursor, argument):
        if isinstance(argument, dict):
            argument = cls(**argument)
        assert isinstance(argument, cls)
        bs += argument.as_bitstream()
    
    def as_bitstream(self):
        bitstream = BitStream()
        self._TEMP_FIELDS = {}
        statements = {}
        for statement in self.create_fields():
            statement = IStructStatement(statement)
            statement._pre_write(self)
            statements[statement] = statement
        self.writing = True
        for statement in self.create_fields():
            statement = statements.get(statement, statement)
            statement._struct_write(self, bitstream)
        del self._TEMP_FIELDS
        self.writing = False
        bitstream.rewind()
        return bitstream

    @classmethod
    def from_bitstream(cls, bitstream):
        instance = cls.__new__(cls)
        instance._TEMP_FIELDS = {}
        statements = {}
        for statement in instance.create_fields():
            statement = IStructStatement(statement)
            statement._pre_read(instance)
            statements[statement] = statement
        instance.reading = True
        for statement in instance.create_fields():
            statement = statements.get(statement, statement)
            statement._struct_read(instance, bitstream)
        del instance._TEMP_FIELDS
        instance.reading = False
        return instance

def istruct_as_iformat(struct):
    return IFormat(IBitStream(struct))

provideAdapter(istruct_as_iformat, [IStruct], IFormat)
