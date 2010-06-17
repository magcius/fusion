
from zope.interface import Interface, Attribute

class ISwfPart(Interface):
    """
    A SWF tag.
    """
    def add_to(data):
        """
        Add the tag to the SwfData.
        """

class IPlaceable(Interface):
    """
    An object that has a characterid that
    can be placed upon the stage.
    """
    characterid = Attribute("The character ID for this object")
