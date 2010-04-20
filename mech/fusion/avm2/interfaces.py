
from zope.interface import implements, Interface, Attribute

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

class IStorable(Interface):
    """
    An IStorable is something that can be stored into.
    """
    def store(generator):
        """
        Add the instructions needed to store the object on
        the top of the stack into this object.
        """

class INode(ILoadable):
    name = Attribute("The name of this node.")
    generator = Attribute("Set by the code generator when added")

    def dependencies():
        """
        Return a list of dependency nodes this
        node needs before it is rendered.
        """

    def render(generator):
        """
        Render this node. The generator is expected to be in
        ScriptContext or ClassContext.
        """

class ITraitable(Interface):
    """
    Something that can be converted to a trait.
    """
    def create_trait(name):
        pass
