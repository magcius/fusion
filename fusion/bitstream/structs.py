
import sys
import operator

from types import NoneType

from fusion.bitstream.bitstream import BitStream, BitStreamParseMixin
from fusion.bitstream.formats import UB, FormatArray, FormatMeta

from fusion.bitstream.interfaces import IBitStream, IFormat, IFormatLength
from fusion.bitstream.interfaces import IStruct, IAutoStruct, IStructClass
from fusion.bitstream.interfaces import IStructEvaluateable, IStructStatement

from zope.interface import implements, classProvides
from zope.component import adapter, provideAdapter

try:
    from numbers import Integral
except ImportError:
    Integral = (int, long)

def byte_aligned(func):
    func.byte_aligned = True
    return func

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
    implements(IStructStatement)

    def __init__(self, format):
        self.format = format

    def _pre_read(self, struct):
        pass

    def _pre_write(self, struct):
        self.format._pre_write(struct, self)

    def _struct_read(self, struct, bitstream):
        bitstream.read(self.format)

    def _struct_write(self, struct, bitstream):
        bitstream.write(self.format)

def formatmeta_as_statement(meta):
    return FormatStructStatementAdapter(meta(None))

provideAdapter(FormatStructStatementAdapter, [IFormat], IStructStatement)
provideAdapter(formatmeta_as_statement, [FormatMeta], IStructStatement)

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

def simple_op_filter(name, read=None):
    name_write = "__%s__" % (name,)
    name_read  = "__%s__" % (read or name,)
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

class FilterStatement(object):
    def __init__(self):
        self.filter_read = []
        self.filter_write = []

    def _filter_read(self, struct, argument):
        for filter in self.filter_read:
            argument = filter(struct, argument)
        return argument

    def _filter_write(self, struct, argument):
        for filter in self.filter_write:
            argument = filter(struct, argument)
        return argument

    __add__ = simple_op_filter("add", "sub")
    __sub__ = simple_op_filter("sub", "add")
    __mul__ = simple_op_filter("mul", "div")
    __div__ = simple_op_filter("div", "mul")

    __and__ = simple_op_filter("and") # bitwise and
    __or__  = simple_op_filter("or")  # bitwise or
    __xor__ = simple_op_filter("xor") # bitwise xor


class FieldTemp(FilterStatement):

    implements(IStructStatement)
    default = True

    def __init__(self, name, format=None):
        super(FieldTemp, self).__init__()
        self.name = name
        self.format = format

    def _pre_read(self, struct):
        self._struct_set(struct, self.default)

    def _pre_write(self, struct):
        IFormat(self.format)._pre_write(struct, self)

    def _struct_get(self, struct):
        raise NotImplementedError

    def _struct_set(self, struct, value):
        raise NotImplementedError

    def _struct_read(self, struct, bitstream):
        format = IFormat(self.format)
        format = IStructEvaluateable(format)._evaluate(struct)
        value  = bitstream.read(format)
        value  = self._filter_read(struct, value)
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

    __nonzero__ = unary_atomizer("nonzero")

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

class FieldTempArray(FieldTemp):
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
    var_name = "__dict__"

class Locals(FieldTempArray):
    var_name = "TEMP_FIELDS"

class NBitsMeta(type):

    implements(IStructEvaluateable, IFormatLength)

    def __getitem__(self, item):
        return self(length=item)

    def __str__(self):
        return "NBits"

    @staticmethod
    def _evaluate(struct):
        name = "NBits%d" % (struct.get_local("NBitsCount"),)
        return struct.get_local(name) - struct.get_local(name+"Offset")

    @staticmethod
    def _pre_write_inner(struct, format, field):
        name = "NBits%d" % (struct.get_local("NBitsCount"),)
        value = field._filter_write(struct, field._struct_get(struct))
        if isinstance(value, Integral):
            value = [value]
        nbits = max(format._nbits(*value) + struct.get_local(name+"Offset"), 0)
        if nbits > struct.get_local(name, -1):
            struct.set_local(name, nbits)

class NBits(object):

    __metaclass__ = NBitsMeta

    implements(IStructStatement)

    def __init__(self, length):
        super(NBits, self).__init__()
        self.length = length
        self.offset = 0
        # XXX: find a better way to do this
        frame = sys._getframe(2)
        self.hash = (frame.f_lineno, frame.f_code.co_filename)

    def _prequel(self, struct):
        self.count = struct.get_local("NBitsCount", 0) + 1
        struct.set_local("NBitsCount", self.count)
        self.name = "NBits%d" % (self.count,)
        struct.set_local(self.name+"Offset", self.offset)

    def _pre_read(self, struct):
        self._prequel(struct)

    def _pre_write(self, struct):
        self._prequel(struct)

    def _realquel(self, struct):
        struct.set_local("NBitsCount", self.count)

    def _struct_read(self, struct, bitstream):
        self._realquel(struct)
        struct.set_local(self.name, bitstream.read(UB[self.length]))

    def _struct_write(self, struct, bitstream):
        self._realquel(struct)
        bitstream.write(struct.get_local(self.name), UB[self.length])

    def __hash__(self):
        return hash(self.hash)

    def __eq__(self, other):
        return isinstance(other, type(self)) and self.hash == other.hash

    def __str__(self):
        return "NBits[%d]" % (self.length,)

    def __add__(self, other):
        self.offset += other
        return self

    def __sub__(self, other):
        self.offset -= other
        return self

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
    classProvides(IFormat, IStructClass, IStructEvaluateable)

    def __init__(self, kwargs=None):
        self.reading, self.writing = False, False
        kwargs = kwargs or {}
        kwargs.pop('self', None)
        for k, v in kwargs.iteritems():
            setattr(self, k, v)

    def create_fields(self):
        pass

    def __repr__(self):
        return "<%s: %s>" % (type(self).__name__, repr(self.__dict__))

    @classmethod
    def _pre_write(cls, struct, field):
        pass

    def set(self, field, value):
        field._struct_set(self, IStructEvaluateable(value)._evaluate(self))

    def get_local(self, name, default=None):
        if default is not None:
            return self.TEMP_FIELDS.get(name, default)
        return self.TEMP_FIELDS[name]

    def set_local(self, name, value):
        self.TEMP_FIELDS[name] = IStructEvaluateable(value)._evaluate(self)

    @classmethod
    def _read(cls, bs, cursor):
        if getattr(cls.create_fields, "byte_aligned", None):
            bs.skip_flush()
        return cls.from_bitstream(bs)

    @classmethod
    def _write(cls, bs, cursor, argument):
        if isinstance(argument, dict):
            argument = cls(**argument)
        assert isinstance(argument, cls)
        if getattr(cls.create_fields, "byte_aligned", None):
            bs.flush()
        bs += argument.as_bitstream()

    def as_bitstream(self):
        bitstream = BitStream()
        bitstream.byte_aligned = getattr(self.create_fields, "byte_aligned", False)
        self.TEMP_FIELDS = {}
        statements = {}
        for statement in self.create_fields():
            statement = IStructStatement(statement)
            statement._pre_write(self)
            statements[statement] = statement
        self.writing = True
        for statement in self.create_fields():
            statement = IStructStatement(statements.get(statement, statement))
            statement._struct_write(self, bitstream)
        del self.TEMP_FIELDS
        self.writing = False
        bitstream.seek(0)
        return bitstream

    @classmethod
    def from_bitstream(cls, bitstream):
        instance = cls.__new__(cls)
        Struct.__init__(instance)
        instance.TEMP_FIELDS = {}
        statements = {}
        for statement in instance.create_fields():
            statement = IStructStatement(statement)
            statement._pre_read(instance)
            statements[statement] = statement
        instance.reading = True
        for statement in instance.create_fields():
            statement = IStructStatement(statements.get(statement, statement))
            statement._struct_read(instance, bitstream)
        del instance.TEMP_FIELDS
        instance.reading = False
        return instance

    @classmethod
    def _evaluate(cls, struct):
        return cls

@adapter(IStruct)
class IStructFormatAdapter(object):
    implements(IFormat)
    def __init__(self, struct):
        self.struct = struct

    def _read(self, bs, cursor):
        return self.struct.from_bitstream(bs)

    def _write(self, bs, cursor, argument):
        bs += self.struct.as_bitstream()

provideAdapter(IStructFormatAdapter)
