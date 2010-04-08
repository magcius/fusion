import struct
import re
from collections import namedtuple

U32_MAX = 2**32 - 1
S32_MAX = 2**31 - 1

def serialize_u32(value):
    s, i, v, b = "", 0, value & 0x07FFFFFFFF, value < 0
    while True:
        if i == 5:
            raise ValueError("value does not fit in a u32: %r" % (value,))
        bits = v & 0b01111111 # low 7 bits
        v >>= 7
        if (not b and not v) or (b and v & 0x7F == 0x7F):
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
    backref = False
    def __init__(self, asm, address=None):
        self.asm = asm
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

    def index_for(self, value, add=True, allow_conflicts=False):
        if self.has_default and (value == self.default or value is None) and not allow_conflicts:
            return 0

        if self.parent and getattr(self.parent, "write_to", None):
            self.parent.write(value)

        if value in self.index_map and not allow_conflicts:
            return self.index_map[value]

        if self.debug and not isinstance(value, basestring):
            aaa

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
            raise ValueError

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
        index = self.index_map[value]
        del self.index_map[value]
        self.pool[index] = empty
        self.free.append(index)
        return index
