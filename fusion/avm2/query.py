
from copy import copy
from fusion.avm2.interfaces import IMultiname
from fusion.avm2.constants import TypeName

from zope.interface import implementer
from zope.component import adapter, provideAdapter

class ClassDesc(object):
    """
    A class description is used when using the native exports API
    to determine the methods, fields, and properties of a type.
    """

    # default values
    FullName         = None
    BaseType         = None
    Methods          = []
    Fields           = []
    Properties       = []
    StaticFields     = []
    StaticMethods    = []
    StaticProperties = []
    Specializable    = False
    Specialized      = None
    SpecializedFast  = {}

    @property
    def ShortName(self):
        return self.FullName.name

    @property
    def Package(self):
        return self.FullName.ns.name

    def __eq__(self, other):
        return self.__dict__ == other.__dict__

    def __hash__(self):
        return hash(self.FullName)

    def __repr__(self):
        return "<ClassDesc for %s>" % (IMultiname(self),)

    def __copy__(self):
        cd = ClassDesc()
        cd.__dict__.update(self.__dict__)
        return cd

    def __getstate__(self):
        state = self.__dict__.copy()
        state.pop('Library', None)
        return state

    def __getitem__(self, item):
        if not isinstance(item, tuple):
            item = item,
        return self.specialize(item)

    def specialize(self, types):
        if self.Specializable:
            specialized = copy(self)
            specialized.Specialized = types
            return specialized
        raise TypeError("%s is not a specializable type.")

@adapter(ClassDesc)
@implementer(IMultiname)
def classdesc_to_multiname(self):
    if self.Specialized:
        return self.SpecializedFast.get(self.Specialized, TypeName(self.FullName, *self.Specialized))
    else:
        return self.FullName

provideAdapter(classdesc_to_multiname)
