
from zope.interface import implements, Interface, Attribute

class IMultiname(Interface):
    kind = Attribute("What is the kind of this multiname?")
    runtime = Attribute("Is this multiname runtime-qualified?")
    runtime_namespace = Attribute("Is this multiname runtime-ns-qualified?")

class ILoadable(Interface):
    """
    An ILoadable is something that is loadable on the stack.
    """
    def load(generator):
        """
        Add the instructions needed to load this object on
        the stack to "generator".
        """

class IConstantPoolWriter(Interface):
    """
    Something that writes itself to a constant pool.
    """
    def write_constants(pool):
        """
        Write to the constant pool.
        """
class IAbcContainer(Interface):
    def add_abc_elements(abcfile):
        " "

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
