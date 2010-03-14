
from collections import namedtuple

from mech.fusion.avm2.util import ValuePool

from mech.fusion.avm2.instructions import parse_instruction

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

    def add_instruction(self, instruction):
        """
        Add an instruction to this block.
        """
        instruction.set_assembler_props(self)
        self.instructions.append(instruction)
        self.instructions[-1].next = instruction

    def add_instructions(self, instructions):
        """
        Add these instructions to this block.
        """
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
        if isinstance(name, int):
            return name
        return self.temporaries.index_for(name, True)

    def get_local(self, name):
        if isinstance(name, int):
            return name
        return self.temporaries.index_for(name, False)
    
    def kill_local(self, name):
        if isinstance(name, int):
            return name
        return self.temporaries.kill(name)

    def has_local(self, name):
        if isinstance(name, int):
            try:
                self.temporaries.value_at(name)
                return True
            except IndexError:
                return False
        return name in self.temporaries

    @property
    def local_count(self):
        return len(self.temporaries)

    def dump_instructions(self):
        dump, offset = "", 0
        for inst in self.instructions:
            if inst.label:
                dump += "\n%s:\n" % (inst.label.name,)
            dump += "\t%d\t%s\n" % (offset, inst)
            offset += len(inst.serialize())
        return dump
    
    def serialize(self):
        """
        Serialize this code to a string, and also
        resolve any jump offsets.
        """
        code = ""
        for inst in self.instructions:
            inst.set_assembler_props_late(self, len(code))
            print len(code), inst
            code += inst.serialize()
        for inst in self.offsets:
            print inst.address, inst
            code = code[:inst.address+1] + inst.lbl.relative_offset(inst.address+4) + code[inst.address+4:]
        return code

    @classmethod
    def parse(cls, bitstream, abc, constants, local_count):
        asm = cls(constants, ("_loc%d" % (i,) for i in xrange(local_count)))
        codelen = bitstream.read_u32()
        finish  = bitstream.cursor*8 + codelen
        while bitstream.cursor*8 < finish:
            asm.add_instruction(parse_instruction(bitstream, abc, constants, asm))
