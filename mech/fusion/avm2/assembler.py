
from collections import namedtuple

from mech.fusion.avm2.util import Avm2Label, serialize_s24 as s24, ValuePool

from mech.fusion.avm2.instructions import parse_instruction

class BackpatchNotSealed(Exception):
    def __init__(self, b):
        self.backpatch = b
    
    def __str__(self):
        return "Backpatch not sealed: %s" % (self.backpatch,)
        

class Avm2CodeAssembler(object):
    
    def __init__(self, constants, local_names):
        self.temporaries = ValuePool()
        for i in local_names:
            self.temporaries.index_for(i)

        self.instructions = []
        
        self._stack_depth = 0
        self._scope_depth = 0

        self._stack_depth_max = 0
        self._scope_depth_max = 0
        
        self.offsets = []
        self.labels  = {}

        self.flags = 0
        self.constants = constants

    @classmethod
    def parse(cls, bitstream, abc, constants, local_count):
        asm = cls(constants, ("_loc%d" % (i,) for i in xrange(local_count)))
        codelen = bitstream.read_u32()
        finish  = bitstream.cursor*8 + codelen
        while bitstream.cursor*8 < finish:
            asm.add_instruction(parse_instruction(bitstream, abc, constants, asm))

    def add_instruction(self, instruction):
        instruction.set_assembler_props(self)
        self.instructions.append(instruction)

    def add_instructions(self, instructions):
        for i in instructions:
            self.add_instruction(i)

    @property
    def stack_depth(self):
        return self._stack_depth

    @stack_depth.setter
    def stack_depth(self, value):
        self._stack_depth = value
        self._stack_depth_max = max(value, self._stack_depth_max)

    @property
    def scope_depth(self):
        return self._scope_depth

    @scope_depth.setter
    def scope_depth(self, value):
        self._scope_depth = value
        self._scope_depth_max = max(value, self._scope_depth_max)
        
    @property
    def next_free_local(self):
        return self.temporaries.next_free()

    def set_local(self, name):
        return self.temporaries.index_for(name, True)

    def get_local(self, name):
        return self.temporaries.index_for(name, False)
    
    def kill_local(self, name):
        return self.temporaries.kill(name)

    def has_local(self, name):
        return name in self.temporaries

    @property
    def local_count(self):
        return len(self.temporaries)
    
    ## def add_backpatch(self, bkptch):
    ##     self.backpatches.append(bkptch)

    ## def seal_backpatches(self):
    ##     for b in self.offsets:
    ##         if b.lbl.address == None:
    ##             raise BackpatchNotSealed(b)
    ##         v = b.lbl.address - b.base
    ##         l = b.location
    ##         self.code = self.code[:l] + s24(v) + self.code[l+3:]
        
    ##     self.backpatches = []

    def serialize(self):
        code = ""
        for inst in self.instructions:
            inst.set_assembler_props_late(self, len(code))
            code += inst.serialize()
            print len(code), inst
        for inst in self.offsets:
            print inst.address, inst
            code = code[:inst.address+1] + inst.lbl.relative_offset(inst.address+4) + code[inst.address+4:]
        return code
