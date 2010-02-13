
from types import NoneType

from mech.fusion.bitstream.bitstream import BitStream
from mech.fusion.bitstream.formats import UB

from mech.fusion.bitstream.interfaces import IBitStream, IFormat, IFormatLength
from mech.fusion.bitstream.interfaces import IStruct, IStructClass, IStructEvaluateable

from zope.interface import implements, classProvides
from zope.component import adapter, provideAdapter

class Atom(object):
    implements(IStructEvaluateable)
    
    def __init__(self, function):
        self.function = function
    
    def _evaluate(self, struct, field):
        return self.function(struct, field)
    
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
        def atom(struct, field):
            return getattr(IStructEvaluateable(self) ._evaluate(struct, field),
                           "__%s__" % (name,)) \
                          (IStructEvaluateable(other)._evaluate(struct, field))
        atom.__name__ = "atom_%s_%s_%s" % (name, self, other)
        return Atom(atom)
    atom.__name__ = "__%s__" % (name,)
    return atom

SOPMAP = dict(add="sub", sub="add", mul="div", div="mul")

def simple_op_filter(name):
    name_write = "__%s__" % (name,)
    name_read  = "__%s__" % (SOPMAP[name],)
    def op(self, other):
        def op_filter_read(struct, value, field):
            return getattr(value, name_read) \
                   (IStructEvaluateable(other)._evaluate(struct, field))
        def op_filter_write(struct, value, field):
            return getattr(value, name_write) \
                   (IStructEvaluateable(other)._evaluate(struct, field))
        self.filter_read .append(op_filter_read)
        self.filter_write.append(op_filter_write)
        return self
    op.__name__ = "__%s__" % (name,)
    return op

class FieldTemp(object):
    
    def __init__(self, name, format=None):
        self.name = name
        self.format = format
        self.filter_read  = []
        self.filter_write = []
        self.context = None

    def _pre_read(self, struct):
        pass

    def _pre_write(self, struct):
        self.format._pre_write(struct, self)

    def _struct_get(self, struct):
        raise NotImplementedError
    
    def _struct_set(self, struct):
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
        format = IStructEvaluateable(self.format)._evaluate(struct, self)
        value  = self._filter_read(struct, bitstream.read(format))
        self._struct_set(struct, value)
        return value
    
    def _struct_write(self, struct, bitstream):
        format = IStructEvaluateable(self.format)._evaluate(struct, self)
        bitstream.write(self._filter_write(struct, self._struct_get(struct)),
                        format)
    
    __eq__  = binary_atomizer("eq")
    __ne__  = binary_atomizer("ne")
    __ge__  = binary_atomizer("ge")
    __le__  = binary_atomizer("le")
    __lt__  = binary_atomizer("lt")
    __gt__  = binary_atomizer("gt")

    __add__ = simple_op_filter("add")
    __sub__ = simple_op_filter("sub")
    __mul__ = simple_op_filter("mul")
    __div__ = simple_op_filter("div")

class Field(FieldTemp):
    def _struct_set(self, struct, value):
        struct._FIELDS[self.name] = value

    def _struct_get(self, struct):
        return struct._FIELDS[self.name]

    def __str__(self):
        return "Field(%r)" % (self.name,)
    
class Local(FieldTemp):
    def _struct_set(self, struct, value):
        self.context._TEMP_FIELDS[self.name] = value

    def _struct_get(self, struct):
        return self.context._TEMP_FIELDS[self.name]

    def __str__(self):
        return "Local(%r)" % (self.name,)

class Fields(Field):
    def __init__(self, fields, format):
        self.fields = fields.split()
        super(Fields, self).__init__(None, format[len(self.fields)])

    def _struct_set(self, struct, value):
        for k, v in zip(self.fields, value):
            struct._FIELDS[k] = v

    def _struct_get(self, struct):
        return [struct._FIELDS[k] for k in self.fields]

    def _filter_read(self, struct, value):
        for filter in self.filter_read:
            value = [filter(struct, a, self) for a in value]
        return value

    def _filter_write(self, struct, value):
        for filter in self.filter_write:
            value = [filter(struct, a, self) for a in value]
        return value

class NBitsMeta(type):
    
    implements(IStructEvaluateable, IFormatLength)
    
    def __getitem__(self, item):
        return self(length=item)
    
    def __str__(self):
        return "NBits"

    @staticmethod
    def _evaluate(struct, field):
        return field.context._TEMP_FIELDS["NBits%d" % \
                   (field.context._TEMP_FIELDS["NBitsCount"],)]

    @staticmethod
    def _pre_write_inner(struct, format, field):
        value = field._filter_write(struct, field._struct_get(struct))
        if isinstance(value, (int, float, long)):
            value = [value]
        nbits = format._nbits(*value)
        name = "NBits%d" % (field.context._TEMP_FIELDS["NBitsCount"],)
        if nbits > field.context._TEMP_FIELDS[name]:
            field.context._TEMP_FIELDS[name] = nbits

class NBits(Local):
    
    __metaclass__ = NBitsMeta
    
    def __init__(self, length):
        super(NBits, self).__init__(None, UB[length])
        self.length = length

    def _prequel(self, struct):
        if "NBitsCount" in self.context._TEMP_FIELDS:
            self.context._TEMP_FIELDS["NBitsCount"] += 1
        self.context._TEMP_FIELDS["NBitsCount"] = 1
        self.name = "NBits%d" % (self.context._TEMP_FIELDS["NBitsCount"],)

    def _pre_read(self, struct):
        self._prequel(struct)

    def _pre_write(self, struct):
        self._prequel(struct)
        self.context._TEMP_FIELDS[self.name] = 0
        
    def __str__(self):
        return "NBits[%d]" % (self.length,)

def DictionaryMap(map, field):
    reverse_map = {}
    for k, v in map.iteritems():
        reverse_map[v] = k
    def map_filter_read(key):
        return map[key]
    def map_filter_write(key):
        return reverse_map[key]
    field.filter_read .append(map_filter_read)
    field.filter_write.append(map_filter_write)

class If(object):
    def __init__(self, read, write, *statements):
        self.read  = read
        self.write = write
        self.statements  = statements

    def _struct_write(self, struct, bitstream):
        if self.write._evaluate(struct):
            for stat in self.statements:
                stat._struct_write(struct, bitstream)

    def _struct_read(self, struct, bitstream):
        if self.read._evaluate(struct):
            for stat in self.statements:
                stat._struct_read(struct, bitstream)

    @property
    def context(self):
        return self._context

    @context.setter
    def context(self, value):
        self._context = value
        for stat in self.statements:
            stat.context = value

## class Group(object):
##     def __init__(self, *statements):
##         self.statements = statements
##         for stat in xrange(statements):
##             stat.context = self

##     def _struct_write(self, struct, bitstream):
##         stat_new = []
##         for stat in self.statements:
##             if hasattr(stat, "_pre_write"):
##                 stat._pre_write(struct)
##         for stat in self.statements:
##             if hasattr(stat, "_evaluate"):
##                 stat_new.append(stat._evaluate(struct))
##             elif hasattr(stat, "_evaluate_write"):
##                 stat_new.append(stat._evaluate_write(struct))
##             else:
##                 stat_new.append(stat)
##         for stat in stat_new:
##             stat._struct_write(struct, bitstream)
##         del self._TEMP

##     def _struct_read(self, struct, bitstream):
##         self._TEMP = {}
##         stat_new = []
##         for stat in self.statements:
##             if hasattr(stat, "_pre_read"):
##                 stat._pre_read(struct)
##         for stat in self.statements:
##             if hasattr(stat, "_evaluate"):
##                 stat_new.append(stat._evaluate(struct))
##             elif hasattr(stat, "_evaluate_read"):
##                 stat_new.append(stat._evaluate_read(struct))
##             else:
##                 stat_new.append(stat)
##         for stat in stat_new:
##             stat._struct_read(struct, bitstream)
##         del self._TEMP

class StructMixin(object):
    @adapter(IFormat)
    def as_format(self):
        return IFormat(self.as_bitstream())

class IdentityStructEvaluateableAdaptor(object):
    def __init__(self, value):
        self.value = value

    def _evaluate(self, struct, field):
        return self.value

provideAdapter(IdentityStructEvaluateableAdaptor, [int], IStructEvaluateable)
provideAdapter(IdentityStructEvaluateableAdaptor, [long], IStructEvaluateable)
provideAdapter(IdentityStructEvaluateableAdaptor, [str], IStructEvaluateable)
provideAdapter(IdentityStructEvaluateableAdaptor, [NoneType], IStructEvaluateable)


class Struct(StructMixin):
    """
    A struct of bit fields.
    """
    
    implements(IStruct)
    classProvides(IFormat, IStructClass)
    
    def __init__(self, kwargs=None):
        if "self" in kwargs:
            del kwargs["self"]
        self._FIELDS = kwargs or {}
        self.__setattr__ = self._setattr

    def createFields(self):
        pass

    def __str__(self):
        return "<Struct(%r): %s>" % (type(self).__name__, ', '.join("%r=%s" % (k, v) for k, v in self._FIELDS.iteritems()))

    def __getattr__(self, name):
        return self._FIELDS[name]

    def _setattr(self, name, value):
        self._FIELDS[name] = value

    @classmethod
    def _read(cls, bs, cursor):
        return cls.from_bitstream(bs)

    @classmethod
    def _write(cls, bs, cursor, argument):
        if isinstance(argument, dict):
            argument = cls(**argument)
        assert isinstance(argument, cls)
        bs += argument.as_bitstream()

    @adapter(IBitStream)
    def as_bitstream(self):
        bitstream = BitStream()
        self._TEMP_FIELDS = {}
        fields = list(self.createFields())
        for statement in fields:
            statement.context = self
            statement._pre_write(self)
        for statement in fields:
            statement._struct_write(self, bitstream)
        del self._TEMP_FIELDS
        return bitstream

    @classmethod
    def from_bitstream(cls, bitstream):
        instance = cls()
        instance._TEMP_FIELDS = {}
        fields = list(instance.createFields())
        for statement in fields:
            statement.context = instance
            statement._pre_read(instance)
        for statement in fields:
            statement._struct_read(instance, bitstream)
        del instance._TEMP_FIELDS
        return instance
