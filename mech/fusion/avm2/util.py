
import struct
import re
from collections import namedtuple

# 5 bytes with the 7 low bits contributing to the number
U32_MAX = 2**(7*5) - 1
S32_MAX = 2**((7*5) - 2)

def serialize_u32(value):
    s = ""
    i = 0
    while True:
        if i == 5:
            raise ValueError("value does not fit in a u32: %r" % s)
        bits = value & 0b01111111 # low 7 bits
        value >>= 7
        if not value:
            s += chr(bits)
            break
        s += chr(0b10000000 | bits)
        i += 1
    return s

def serialize_s24(value):
    """
    Serialize a 3-byte signed S24.
    """
    m = struct.pack("<l", value)
    if (value < 0 and m[3] != "\xff") or (value >= 0 and m[3] != "\x00"):
        raise ValueError, "value does not fit in a s24"
    return m[:3]

class Avm2Label(object):
    _next_label = 1000
    
    backref = False
    
    def __init__(self, asm, address=-1):
        self.asm = asm
        self.name = Avm2Label._next_label
        Avm2Label._next_label += 1
        self._address = address
        self.stack_depth = asm._stack_depth_max
        self.scope_depth = asm._scope_depth_max

    @property
    def address(self):
        return self._address

    @address.setter
    def address(self, value):
        self._address = value
        
    def relative_offset(self, base):
        return serialize_s24(self.address - base)

    def __repr__(self):
        return "<Avm2Label (name=%d, address=%d, stack_depth=%d, scope_depth=%d)>" \
            % (self.name, self.address, self.stack_depth, self.scope_depth)

empty = object()
    
class ValuePool(object):
    
    def __init__(self, default=None, parent=None, debug=False):
        self.parent = parent
        self.index_map = {}
        self.pool      = []
        self.debug     = debug
        self.default   = default
        self.has_default = default is not None

    def __contains__(self, value):
        return value in self.index_map

    def __iter__(self):
        return iter(self.pool)

    def __str__(self):
        return "ValuePool(%r)" % (self.pool,)

    def __len__(self):
        return len(self.pool) + int(self.has_default)

    def index_for(self, value, add=True):
        if self.debug and isinstance(value, str):
            pass
        
        if self.has_default and (value == self.default or value is None):
            return 0
        
        if value in self.index_map:
            return self.index_map[value]
        
        if not add:
            raise ValueError("value not in ValuePool\n\nHave: %r, requested %r" % (self.pool, value))
        
        if hasattr(self.parent, "write_to"):
            self.parent.write(value)
        
        index, reuse = self.next_free()

        if reuse:
            self.pool[index] = value
        else:
            self.pool.append(value)
        self.index_map[value] = index
        
        return index

    def value_at(self, index):
        if self.has_default and index == 0:
            return self.default
        
        if index <= len(self.pool):
            return self.pool[index-1]
        
        return None

    def next_free(self):
        if empty in self.pool:
            index = self.pool.index(empty)
            reuse = True
        else:
            index = len(self.pool)
            reuse = False
        
        if self.has_default:
            index += 1
        
        return index, reuse

    def kill(self, value):
        index = self.index_map[value]
        del self.index_map[value]
        self.pool[index] = empty
        return index
