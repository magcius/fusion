
from mech.fusion.bitstream.flash_formats import U32

from mech.fusion.avm2.util import ValuePool
from mech.fusion.avm2.instructions import parse_instruction, INSTRUCTIONS, getlocal, setlocal

BRANCH_OPTIMIZE = {
    ("equals", "not",  "iftrue"):  "ifne",
    ("equals", "not",  "iffalse"): "ifeq",
    ("equals",         "iftrue"):  "ifeq",
    ("equals",         "iffalse"): "ifne",
    ("lessthan",       "iftrue"):  "iflt",
    ("lessthan",       "iffalse"): "ifnlt",
    ("lessequals",     "iftrue"):  "ifle",
    ("lessequals",     "iffalse"): "ifnle",
    ("greaterthan",    "iftrue"):  "ifgt",
    ("greaterthan",    "iffalse"): "ifngt",
    ("greaterequals",  "iftrue"):  "ifge",
    ("greaterequals",  "iffalse"): "ifnge",
    ("strictequals",   "iftrue"):  "ifstricteq",
    ("strictequals",   "iffalse"): "ifstrict",
}

NO_OP = set((
    ("setlocal0", "getlocal0"),
    ("setlocal1", "getlocal1"),
    ("setlocal2", "getlocal2"),
    ("setlocal3", "getlocal3"),
    
    ("getlocal0", "setlocal0"),
    ("getlocal1", "setlocal1"),
    ("getlocal2", "setlocal2"),
    ("getlocal3", "setlocal3"),
))

NO_OP_GLSL = "getlocal", "setlocal"

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

        self.registers_used = dict((i, i) for i, a in enumerate(local_names))

    def add_instruction(self, instruction):
        """
        Add an instruction to this block.
        """
        if self.instructions:
            prev = self.instructions[-1]
            instruction = self.optimize(prev, instruction)
            prev = self.instructions[-1] # may have popped instruction
            if instruction:
                prev.next = instruction
        if instruction:
            instruction.set_assembler_props(self)
            self.instructions.append(instruction)

    def optimize(self, prev, instruction):
        """
        Optimize when adding an instruction.
        """
        test = prev.name, instruction.name
        print test
        if instruction.name.startswith("setlocal"):
            self.registers_used.setdefault(instruction.argument, len(self.registers_used))
            instruction = setlocal(self.registers_used[instruction.argument])
        elif instruction.name.startswith("getlocal"):
            instruction = getlocal(self.registers_used[instruction.argument])
        if test in BRANCH_OPTIMIZE:
            self.instructions.pop()
            instruction = INSTRUCTIONS[BRANCH_OPTIMIZE[test]](instruction.lblname)
        elif test in NO_OP or (test == NO_OP_GLSL and prev.argument == instruction.argument):
            self.instructions.pop()
            return
        return instruction

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

    def dump_instructions(self, indent="\t"):
        dump, offset = "", 0
        for inst in self.instructions:
            if inst.label:
                dump += "\n%s%s:\n" % (indent, inst.label.name,)
            dump += "%s%d%s%s\n" % (indent*2, offset, indent, inst)
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
            code += inst.serialize()
        for inst in self.offsets:
            code = code[:inst.address+1] + inst.lbl.relative_offset(inst.address+4) + code[inst.address+4:]
        return code

    @classmethod
    def parse(cls, bitstream, abc, constants, local_count):
        asm = cls(constants, ("_loc%d" % (i,) for i in xrange(local_count)))
        codelen = bitstream.read(U32)
        finish  = bitstream.cursor + codelen*8
        while bitstream.cursor < finish:
            asm.add_instruction(parse_instruction(bitstream, abc, constants, asm))
        return asm
