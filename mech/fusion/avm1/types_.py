
class DataType(object):
    REVERSE_INDEX = {}
    def __init__(self, id, name, size):
        self.id = id
        self.name = name
        self.size = size
        DataType.REVERSE_INDEX[self.id] = self


STRING      = DataType(0, "string", "Z")
FLOAT       = DataType(1, "float", "f")
NULL        = DataType(2, "null", "!")
UNDEFINED   = DataType(3, "undefined", "!")
REGISTER    = DataType(4, "register", "B")
BOOLEAN     = DataType(5, "boolean", "B")
DOUBLE      = DataType(6, "double", "d")
INTEGER     = DataType(7, "integer", "l")
CONSTANT8   = DataType(8, "constant 8", "B")
CONSTANT16  = DataType(9, "constant 16", "H")

_pytype_to_avm1 = {
    str:         STRING,
    unicode:     STRING,
    int:         INTEGER,
    long:        INTEGER,
    bool:        BOOLEAN,
    float:       DOUBLE,
}

def pytype_to_avm1(value):
    return (value, _pytype_to_avm1[type(value)])
