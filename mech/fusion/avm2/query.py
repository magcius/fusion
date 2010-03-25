
from mech.fusion.avm2.constants import packagedQName

class ClassDesc(object):

    # default values
    FullName      = ""
    ShortName     = ""
    BaseType      = ""
    Package       = ""
    Methods       = []
    Fields        = []
    Properties    = []
    StaticFields  = []
    StaticMethods = []
    StaticProperties = []

    _nativeclass = None

    def __eq__(self, other):
        return self.__dict__ == other.__dict__

    def __hash__(self):
        raise TypeError

    def multiname(self):
        return packagedQName(self.Package, self.ShortName)
