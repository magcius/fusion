
from mech.fusion.bitstream.bitstream import BitStream
from mech.fusion.bitstream.formats import UB
from mech.fusion.bitstream.interfaces import (IBitStream, IStruct,
                                              IStructClass, IFormat)

from zope.interface import implements, classProvides
from zope.component import provideAdapter

def identity(v):
    return v

class Atom(object):
    def __init__(self, function):
        self.function = function

    def _evaluate(self, struct):
        return self.function(struct)
    
    def and_(self, other):
        def atom_and(struct):
            return self._evaluate(struct) and other._evaluate(struct)
        return Atom(atom_and)

    def or_(self, other):
        def atom_or(struct):
            return self._evaluate(struct) or other._evaluate(struct)
        return Atom(atom_or)

    def not_(self):
        def atom_not(struct):
            return not self._evaluate(struct)
        return Atom(atom_not)
    
    __and__ = and_
    __or__  = or_

and_ = Atom.and_
or_ = Atom.or_

def make_atomizer(name):
    def atom(self, other):
        def atom(struct):
            other_ = other
            if hasattr(other_, "_evaluate"):
                other_ = other_._evaluate(struct)
            return getattr(self._evaluate(struct), "__%s__" % (name,))(other)
        atom.__name__ = "atom_%s_%s_%s" % (name, self, other)
        return Atom(atom)
    atom.__name__ = "__%s__" % (name,)
    return atom

class _FieldTemp(object):
    def __init__(self, name, format=None):
        self.name = name
        self.format = format
        self.format.field = self
        self.filter = identity
        self.context = None

    def _pre_read(self, struct):
        self.format._pre_read(struct)

    def _pre_write(self, struct):
        self.format._pre_write(struct)
    
    def _struct_get(self, struct):
        raise NotImplementedError
    
    def _struct_set(self, struct):
        raise NotImplementedError
    
    def _struct_read(self, struct, bitstream):
        format = self.format._evaluate_read(struct)
        self._struct_set(struct, self.filter(bitstream.read(format)))
    
    def _struct_write(self, struct, bitstream):
        format = self.format._evaluate_write(struct)
        bitstream.write(self.filter(self._struct_get(struct)), format)
    
    __eq__ = make_atomizer("eq")
    __ne__ = make_atomizer("ne")
    __ge__ = make_atomizer("ge")
    __le__ = make_atomizer("le")
    __lt__ = make_atomizer("lt")
    __gt__ = make_atomizer("gt")
    __nonzero__ = make_atomizer("nonzero")

class Field(_FieldTemp):
    def _struct_set(self, struct, value):
        setattr(struct, self.name, value)

    def _struct_get(self, struct):
        return getattr(struct, self.name)

    def __str__(self):
        return "Field(%r)" % (self.name,)
    
class Local(_FieldTemp):
    def _struct_set(self, struct, value):
        self.context._TEMP[self.name] = value

    def _struct_get(self, struct):
        return self.context._TEMP[self.name]

    def __str__(self):
        return "Local(%r)" % (self.name,)

class _NBitsMeta(type):
    def __getitem__(self, item):
        return self(length=item)

    def _evaluate(self, struct, format):
        return format.field.context._TEMP["NBits"]
    
    def _pre_write(self, struct, format):
        value = format.field._struct_get(struct)
        nbits = format._nbits(value)
        if nbits > format.field.context._TEMP["NBits"]:
            format.field.context._TEMP["NBits"] = nbits
    
    def __str__(self):
        return "NBits"
        
class NBits(Local):
    __metaclass__ = _NBitsMeta
    def __init__(self, length):
        self.name = "NBits"
        self.format = UB[length]
        self.length = length
    
    def __str__(self):
        return "NBits[%d]" % (self.length,)

def Map(map, field):
    if isinstance(map, dict):
        for k, v in map:
            map[v] = k
        f = field.filter
        def map_filter_dict(key):
            return map[f(key)]
        field.filter = map_filter_dict
    else:
        f = field.filter
        def map_filter_func(key):
            return map(f(key))
        field.filter = map_filter_func
    return field

class If(object):
    def __init__(self, read, write, *statements):
        self.read  = read
        self.write = write
        self.statements  = statements

    def _struct_write(self, struct, bitstream):
        if getattr(self.write, "_evaluate",
                   getattr(self.write, "_evaluate_write"))._evaluate(struct):
            for stat in self.statements:
                stat._struct_write(struct)

    def _struct_read(self, struct, bitstream):
        if getattr(self.write, "_evaluate",
                   getattr(self.write, "_evaluate_read"))._evaluate(struct):
            for stat in self.statements:
                stat._struct_read(struct)

class Group(object):
    def __init__(self, *statements):
        self.statements = statements
        for stat in xrange(statements):
            stat.context = self

    def _struct_write(self, struct, bitstream):
        self._TEMP = {}
        stat_new = []
        for stat in self.statements:
            if hasattr(stat, "_pre_write"):
                stat._pre_write(struct)
        for stat in self.statements:
            if hasattr(stat, "_evaluate"):
                stat_new.append(stat._evaluate(struct))
            elif hasattr(stat, "_evaluate_write"):
                stat_new.append(stat._evaluate_write(struct))
            else:
                stat_new.append(stat)
        for stat in stat_new:
            stat._struct_write(struct, bitstream)
        del self._TEMP

    def _struct_read(self, struct, bitstream):
        self._TEMP = {}
        stat_new = []
        for stat in self.statements:
            if hasattr(stat, "_pre_read"):
                stat._pre_read(struct)
        for stat in self.statements:
            if hasattr(stat, "_evaluate"):
                stat_new.append(stat._evaluate(struct))
            elif hasattr(stat, "_evaluate_read"):
                stat_new.append(stat._evaluate_read(struct))
            else:
                stat_new.append(stat)
        for stat in stat_new:
            stat._struct_read(struct, bitstream)
        del self._TEMP

class StructMixin(object):
    def as_format(self):
        return IFormat(self.as_bitstream())

class Struct(StructMixin):
    """
    A struct of bit fields.
    """
    
    implements(IStruct)
    classProvides(IFormat)
    classProvides(IStructClass)
    
    FORMAT = None
    POSITIONAL = [] # for backwards compatibility

    def __init__(self, *args, **kwargs):
        for k, v in zip(self.POSITIONAL, args):
            setattr(self, k, v)
        for k, v in kwargs.iteritems():
            setattr(self, k, v)
    
    @classmethod
    def _read(cls, bs, cursor):
        return cls.from_bitstream(bs)
    
    @classmethod
    def _write(cls, bs, cursor, argument):
        if isinstance(argument, dict):
            argument = cls(**argument)
        assert isinstance(argument, cls)
        bs += argument.as_bits()
    
    def as_bitstream(self):
        bitstream = BitStream()
        for statement in self.FORMAT:
            statement._struct_write(self, bitstream)
        return bitstream

    @classmethod
    def from_bitstream(cls, bitstream):
        instance = cls()
        for statement in cls.FORMAT:
            statement._struct_read(instance, bitstream)
        return instance

provideAdapter(Struct.as_bitstream, [IStruct], IBitStream)
provideAdapter(Struct.as_format,    [IStruct], IFormat)
