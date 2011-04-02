
import struct

U32_MAX = 2**32 - 1
S32_MAX = 2**31 - 1

def serialize_u32(value):
    if value >= 2**35 or value <= -2**34:
        raise ValueError("value %d does not fit in a u32" % (value,))
    encoded, value = "", value & 0xFFFFFFFF
    for i in xrange(5):
        bits = value & 0b01111111
        value >>= 7
        if not value:
            encoded += chr(bits)
            break
        encoded += chr(0b10000000 | bits)
    return encoded

def serialize_s24(value):
    """
    Serialize a 3-byte signed S24.
    """
    m = struct.pack("<l", value)
    if (value < 0 and m[3] != "\xff") or (value >= 0 and m[3] != "\x00"):
        raise ValueError, "value does not fit in a s24"
    return m[:3]

class empty(object):
    def __repr__(self):
        return "(empty)"

empty = empty()

class ValuePool(object):
    def __init__(self, parent, default=None, is_default=None):
        self.parent = parent
        self.index_map  = {}
        self.pool       = []
        self.free       = []
        self.default    = default
        self.is_default = is_default or self.default_compare

    def default_compare(self, value):
        return value == self.default

    def __contains__(self, value):
        return value in self.index_map

    def __iter__(self):
        return iter(self.pool)

    def __str__(self):
        return "ValuePool(%r)" % (self.pool,)

    def __len__(self):
        if self.default is not None:
            return len(self.pool) + 1
        return len(self.pool)

    def merge(self, pool):
        for value in pool:
            self.index_for(value)

    def get_index(self, value):
        return self.index_map[value]

    def add_value(self, value):
        index, reuse = self.next_free()

        if reuse:
            self.pool[index] = value
        else:
            self.pool.append(value)

        self.index_map.setdefault(value, index)

        return index

    def index_for(self, value):
        if self.parent:
            self.parent.write(value)

        if value in self.index_map:
            return self.index_map[value]

        if self.is_default(value):
            return 0

        return self.add_value(value)

    def value_at(self, index):
        if self.default is not None:
            if index == 0:
                return self.default
            index -= 1

        try:
            value = self.pool[index]
        except IndexError:
            raise ValueError("No value at %d." % (index,))

        if value is empty:
            raise ValueError("No value at %d." % (index,))

        return value

    def next_free(self):
        if self.free:
            index = self.free.pop(0)
            reuse = True
        else:
            index = len(self.pool)
            reuse = False

            if self.default is not None:
                index += 1

        return index, reuse

    def kill(self, value):
        index = self.index_map[value]
        del self.index_map[value]
        self.pool[index] = empty
        self.free.append(index)
        return index
