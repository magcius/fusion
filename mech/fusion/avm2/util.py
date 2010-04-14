import struct
import re
from collections import namedtuple

U32_MAX = 2**32 - 1
S32_MAX = 2**31 - 1

def serialize_u32(value):
    encoded, unsigned = "", value & 0xFFFFFFFF
    for i in xrange(5):
        bits = unsigned & 0b01111111
        unsigned >>= 7
        if not unsigned:
            encoded += chr(bits)
            break
        encoded += chr(0b10000000 | bits)
    else:
        raise ValueError("value %d does not fit in a u32" % (value,))
    return encoded

def serialize_s24(value):
    """
    Serialize a 3-byte signed S24.
    """
    m = struct.pack("<l", value)
    if (value < 0 and m[3] != "\xff") or (value >= 0 and m[3] != "\x00"):
        raise ValueError, "value does not fit in a s24"
    return m[:3]

class Avm2Label(object):
    backref = False
    seenlabel = False
    def __init__(self, asm, address=None):
        self.asm = asm
        self._address = address
        self.stack_depth = asm._stack_depth_max
        self.scope_depth = asm._scope_depth_max
        self.temporaries = asm.temporaries.clone()

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

class empty(object):
    def __repr__(self):
        return "(empty)"

empty = empty()

class ValuePool(object):
    def __init__(self, default=None, parent=None, debug=False):
        self.parent = parent
        self.index_map = {}
        self.pool      = []
        self.free      = []
        self.default   = default
        self.debug     = debug
        self.has_default = default is not None

    def __contains__(self, value):
        return value in self.index_map

    def __iter__(self):
        return iter(self.pool)

    def __str__(self):
        return "ValuePool(%r)" % (self.pool,)

    def __len__(self):
        return len(self.pool) + int(self.has_default)

    def merge(self, pool):
        for value in pool:
            self.index_for(value)

    def clone(self):
        m = ValuePool()
        m.copy(self)
        return m

    def copy(self, pool):
        self.parent = pool.parent
        self.index_map = pool.index_map.copy()
        self.pool = pool.pool[:]
        self.free = pool.free[:]
        self.default = pool.default
        self.debug = pool.debug
        self.has_default = pool.has_default

    def index_for(self, value, add=True, allow_conflicts=False):
        if self.has_default and (value == self.default or value is None) and not allow_conflicts:
            return 0

        if self.parent and getattr(self.parent, "write_to", None):
            self.parent.write(value)

        if self.debug and not isinstance(value, basestring):
            baaah

        if value in self.index_map and not allow_conflicts:
            return self.index_map[value]

        if not add:
            raise ValueError("value not in ValuePool\n\nHave: %r, requested %r" % (self.pool, value))

        index, reuse = self.next_free()

        if reuse:
            self.pool[index] = value
        else:
            self.pool.append(value)

        if value not in self.index_map or value == self.default:
            self.index_map[value] = index

        return index

    def value_at(self, index):
        if self.has_default and index == 0:
            return self.default

        if self.has_default:
            index -= 1

        value = self.pool[index]

        if value is empty:
            raise ValueError("value is empty")

        return value

    def next_free(self):
        if self.free:
            index = self.free.pop(0)
            reuse = True
        else:
            index = len(self.pool)
            reuse = False

            if self.has_default:
                index += 1

        return index, reuse

    def kill(self, value):
        if not value in self.index_map:
            raise ValueError("value not in ValuePool\n\nHave: %r, requested %r" % (self.pool, value))

        index = self.index_map[value]
        del self.index_map[value]
        self.pool[index] = empty
        self.free.append(index)
        return index
