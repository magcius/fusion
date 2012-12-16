
from zope.interface import implements
from zope.component import adapter, provideAdapter

from math import isnan
from fusion.avm2.util import S32_MAX, U32_MAX
from fusion.avm2.interfaces import ILoadable

class NotAnArgumentError(Exception):
    def __init__(self, name):
        self.name = name

    def __str__(self):
        return ("The local variable %r is not an argument"
                "in the current method.") % (self.name,)

class Local(object):
    implements(ILoadable)
    """
    A loadable object that pushes a local onto the stack.
    """
    def __init__(self, name):
        self.name = name

    def load(self, generator):
        generator.emit('getlocal', generator.current_assembler.get_local(self.name))

    def __repr__(self):
        return "Local(%r)" % (self.name,)

class _This(object):
    implements(ILoadable)
    """
    A loadable object that pushes the "this" object onto the stack.
    """
    def load(self, generator):
        generator.emit('getlocal', 0)

    def __repr__(self):
        return "This"

This = _This()

class Field(object):
    implements(ILoadable)
    """
    A loadable object that pushes a field onto the stack.
    """
    def __init__(self, name):
        self.name = name

    def load(self, generator):
        generator.emit('getproperty', self.name)

    def __repr__(self):
        return "Field(%r)" % (self.name,)

class Slot(object):
    implements(ILoadable)
    """
    A loadable object that pushes a slot onto the stack.
    """
    def __init__(self, index):
        self.index = index

    def load(self, generator):
        generator.emit('getslot', self.index)

    def __repr__(self):
        return "Slot(%r)" % (self.index,)

class Argument(object):
    implements(ILoadable)
    """
    A loadable object that pushes a method argument onto the stack.
    """
    def __init__(self, name):
        self.name = name

    def load(self, generator):
        if self.name not in generator.current_rib.method.param_names:
            raise NotAnArgumentError(self.name)
        generator.emit('getlocal', generator.current_assembler.get_local(self.name))

    def get_index(self, generator):
        return generator.current_assembler.get_local(self.name)

    def __repr__(self):
        return "Argument(%r)" % (self.name,)

class _NothingType(object):
    implements(ILoadable)
    """
    A loadable object that does nothing. May be useful for specifying
    things that pop off the stack.
    """
    def load(self, generator):
        pass

    def __repr__(self):
        return "Nothing"

_Nothing = _NothingType()

def Nothing(count):
    return [_Nothing] * count

Stack = Nothing

class Chain(object):
    implements(ILoadable)
    def __init__(self, *loadables):
        self.loadables = loadables

    def load(self, generator):
        for loadable in self.loadables:
            ILoadable(loadable).load(generator)

# Adapters

class LoadableAdapter(object):
    implements(ILoadable)
    def __init__(self, value):
        self.value = value

@adapter(list)
class ListLoadable(LoadableAdapter):
    def load(self, generator):
        generator.init_array(self.value)

provideAdapter(ListLoadable)

@adapter(dict)
class DictLoadable(LoadableAdapter):
    def load(self, generator):
        generator.init_object(self.value)

provideAdapter(DictLoadable)

@adapter(bool)
class BoolLoadable(LoadableAdapter):
    def load(self, generator):
        if self.value:
            generator.emit('pushtrue')
        else:
            generator.emit('pushfalse')

provideAdapter(BoolLoadable)

class IntLoadable(LoadableAdapter):
    def load(self, generator):
        if self.value > U32_MAX or self.value < -S32_MAX:
            generator.emit('pushdouble', self.value)
        elif self.value >= 0:
            generator.emit('pushuint', self.value)
        else:
            generator.emit('pushint', self.value)

provideAdapter(IntLoadable, [int], ILoadable)
provideAdapter(IntLoadable, [long], ILoadable)

@adapter(float)
class FloatLoadable(LoadableAdapter):
    def load(self, generator):
        if isnan(self.value):
            generator.emit('pushnan', self.value)
        else:
            generator.emit('pushdouble', self.value)

provideAdapter(FloatLoadable)

@adapter(basestring)
class BaseStringLoadable(LoadableAdapter):
    def load(self, generator):
        generator.emit('pushstring', self.value)

provideAdapter(BaseStringLoadable)
