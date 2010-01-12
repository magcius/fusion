
from collections import namedtuple

DataType = namedtuple("DataType", "id name size")

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

def lltype_to_avm1(value):
    return None
    #return _lltype_to_avm1[value]

class AVM1TypeSystem(object):
    def __init__(self, db):
        self.db = db

    def escape_name(self, name):
        return name
    
    def lltype_to_cts(self, TYPE):
        return lltype_to_avm1(TYPE)
    
    def llvar_to_cts(self, var):
        return self.lltype_to_cts(var.concretetype), var.name
