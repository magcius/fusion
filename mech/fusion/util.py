
import os
import re
import zlib

from math import isnan

# Old API names
from mech.fusion.bitstream import BitStream, BitStreamParseMixin, formats, nbits_signed, nbits

try:
    import cPickle as pickle
except ImportError:
    import pickle as pickle

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

def clamp(n, minimum, maximum):
    """
    Clamp n between mniimum and maximum.
    """
    return max(minimum, min(n, maximum))

def camel_case_match(string):
    """
    Properly matches the camelCase naming style so that a name like
    writeXMLDocument gets parsed as ["write", "XML", "Document"].
    """
    return re.findall('(^[a-z]+|[A-Z][a-z]+|[A-Z]+|[0-9])(?![a-z])', string)

def camel_case_convert(string):
    """
    Properly converts the camelCase naming style to underscore style so that
    writeXMLDocument gets converted to write_xml_document.
    """
    return '_'.join(s.lower() for s in camel_case_match(string))
