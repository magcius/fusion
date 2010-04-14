
from zope.interface import implements, Interface

class ILoadable(Interface):
    """
    An ILoadable is something that is loadable on the stack.
    """
    def load(generator):
        """
        Add the instructions needed to load this object on
        the stack to "generator".
        """

class LoadableAdapter(object):
    implements(ILoadable)
    def __init__(self, value):
        self.value = value
