
from mech.fusion.bitstream import BitStream
from mech.fusion.bitstream.parts import UB

def identity(v):
    return v

class Atom(object):
    def __init__(self, function):
        self.function = function

    def _evaluate_read(self, struct):
        return self.function(struct)

    def _evaluate_write(self, struct):
        return self.function(struct)

    def and_(self, other):
        def conditional_and(struct):
            return self._evaluate(self, struct) and self._evaluate(other, struct)
        return Conditional(conditional_and)

    def or_(self, other):
        def conditional_or(struct):
            return self._evaluate(self, struct) or self._evaluate(other, struct)
        return Conditional(conditional_or)

    def not_(self):
        def conditional_not(struct):
            return not self._evaluate(self, struct)
    
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
        return Conditional(atom)
    atom.__name__ = "__%s__" % (name,)
    return atom

class _FieldTemp(object):
    def __init__(self, name, format=None):
        self.name = name
        self.format = format
        self.format.field = self
        self.filter = identity
        self.context = None

    def _evaluate(self, struct):
        return self._struct_get(struct)
    
    def _struct_read(self, struct, bitstream):
        self.format._pre_read(struct)
        self._struct_set(struct, self.filter(bitstream.read(self.format)))
    
    def _struct_write(self, struct, bitstream):
        self.format.pre_write(struct)
        bitstream.write(self.filter(self._struct_get(struct)), self.format)

    def __str__(self):
        return "Field(%r)" % (self.name,)
    
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
    
class Local(_FieldTemp):
    def _struct_set(self, struct, value):
        self.context._TEMP[self.name] = value

    def _struct_get(self, struct):
        return self.context._TEMP[self.name]

class _NBitsMeta(object):
    def __getitem__(self, item):
        return self(length=item)

    def _pre_read(self, struct, format):
        return format.field.context._TEMP["NBits"]

    def _pre_write(self, struct, format):
        nbits = format._nbits(value)
        value = format.field._struct_get(struct)
        if nbits > format.field.context._TEMP["NBits"]:
            format.field.context._TEMP["NBits"] = nbits
        
class _NBits(Local):
    __metaclass__ = _NBitsMeta
    def __init__(self, length):
        self.name = "NBits"
        self.format = UB[length]
    
    def _evaluate(self, struct):
        return self._struct_get(struct, "NBits")
    
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
    def __init__(self, read_conditional, write_conditional, *statements):
        self.conditional = conditional
        self.statements  = statements

class Group(object):
    def __init__(self, *statements):
        self._TEMP = {}
        self.statements = statements
        for stat in xrange(statements):
            stat.context = self

    def _pre_read(self):
        pass
    
class Struct(object):
    """
    A struct of bit fields.
    """
    FORMAT = None
    POSTIIONAL = [] # for backwards compatibility
    
    def __init__(self, *args, **kwargs):
        for k, v in zip(POSITIONAL, args):
            setattr(self, k, v)
        for k, v in kwargs.iteritems():
            setattr(self, k, v)
    
    def as_bits(self):
        bitstream = BitStream()
        for statement in self.FORMAT:
            statement._struct_write(self, bitstream)
        return bitstream

    @classmethod
    def from_bits(cls, bitstream):
        instance = cls()
        for statement in self.FORMAT:
            statement._struct_read(instance, bitstream)
        return instance
