
from mech.fusion.avm2.constants import packagedQName, TypeName

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

    def __str__(self):
        return "<ClassDesc for %s>" % (self.multiname(),)

    def multiname(self):
        if self.Specialized:
            return self.SpecializedFast.get(self.Specialized, TypeName(self.FullName, *self.Specialized))
        else:
            return self.FullName

    def __getitem__(self, item):
        if not isinstance(item, tuple):
            item = item,
        return self.specialize(item)

    def specialize(self, types):
        if self.Specializable:
            specialized = self.clone()
            specialized.Specialized = types
            return specialized
        raise TypeError("%s is not a specializable type.")
