
from zope.interface import Interface, Attribute

class ISwfPart(Interface):
    """
    A SWF tag.
    """
    def add_to(data):
        """
        Add the tag to the SwfData.
        """
