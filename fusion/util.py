
import re

def nbits(*args):
    """
    Returns the number of bits in the max of all the arguments.
    """
    # according to StackOverflow, using the string
    # length is faster than everything else
    if all(a == 0 for a in args):
        return 0
    return max(len(bin(abs(a))) for a in args) - 2

def nbits_signed(*args):
    """
    Returns the number of bits in the max of all the arguments, if interpreted
    as a signed number. This is significantly more difficult than the absolute
    value case.
    """
    nbits = set()
    for num in args:
        if num == 0:
            nbits.add(0)
        elif num == -1:
            nbits.add(2)
        elif num > 0:
            nbits.add(len(bin(num)) - 1)
        elif num < 0:
            nbits.add(len(bin(num+1)) - 2)
    return max(nbits)

def nbits_fixed(num, *args):
    """
    Returns the number of bits in the max of all the arguments, assuming FBits.
    """
    if all(a == 0 for a in (num,)+args):
        return 0
    return nbits_signed(*(int(a*float(0x10000)) for a in (num,) + args))

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
