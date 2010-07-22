import itertools

from mech.fusion.bitstream.flash_formats import U32

from mech.fusion.compat import set
from mech.fusion.avm2.util import ValuePool
from mech.fusion.avm2.instructions import (parse_instruction, INSTRUCTIONS,
                                           getlocal, setlocal, kill, get_label)

BRANCH_OPTIMIZE = {
    ("not",            "iftrue"):  "iffalse",
    ("not",            "iffalse"): "iftrue",
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

NO_OP_GLSL = set((
    ("getlocal0", "setlocal0"),
    ("getlocal1", "setlocal1"),
    ("getlocal2", "setlocal2"),
    ("getlocal3", "setlocal3"),
))

class CodeAssembler(object):
    def __init__(self, constants, local_names):
        self.local_names = local_names
        self.temporaries = ValuePool(debug=True)
        for i in local_names:
            self.temporaries.index_for(i)

        self.instructions = []

        self._stack_depth = 0
        self._scope_depth = 0

        self._numlocals_max = 0
        self._stack_depth_max = 0
        self._scope_depth_max = 0

        self.offsets = {}
        self.labels  = {}

        self.flags = 0
        self.constants = constants

    def add_instruction(self, instruction):
        """
        Add an instruction to this block.
        """
        if instruction:
            if self.instructions:
                self.instructions[-1].next = instruction
            self.instructions.append(instruction)
            instruction.assembler_added(self)

    def optimize(self):
        """
        Do some simple optimizations for stupid code generator
        clients.
        """
        for _ in xrange(2):
            jumps = {}

            remv_inst = set()
            remv_regs = {}

            prev = None

            # First pass - mark anything needed for the second pass.
            for curr in self.instructions:
                if prev is None:
                    prev = curr
                    continue

                # Label then jump. Optimize so that the people who jump to that
                # label jump to the label that label is jumping to. This will
                # require a second pass.
                if curr.offset:
                    jumps.setdefault(curr.lblname, []).append(curr)

                # Detect if there are any references to this register other than
                # the setlocal/getlocal sequence here.
                S = set((prev, curr))
                if prev.name.startswith("setlocal") and \
                   curr.name.startswith("getlocal") and \
                   prev.argument == curr.argument:
                    remv_inst |= S
                    remv_regs[curr.argument] = S

                # PyPy-specific optimization: some opcodes have an unnecessary
                # StoreResult at the end, so callpropvoid and some setproperty's
                # have a pushnull and an unused register afterwards. Stop that.
                elif prev.name in ("pushnull", "pushundefined") and \
                     curr.name.startswith("setlocal"):
                    remv_inst |= S
                    remv_regs[curr.argument] = S

                elif curr.name.startswith("getlocal"):
                    if curr.argument in remv_regs:
                        remv_inst -= remv_regs[curr.argument]

                elif curr.name.startswith("setlocal"):
                    remv_regs[curr.argument] = set()

                elif curr.name == "kill":
                    # If we're going to remove this register, then mark the kill
                    # for deletion too.
                    if curr.argument in remv_regs:
                        remv_inst.add(curr)

                prev = curr

            institer = iter(self.instructions)
            instructions = [institer.next()]
            # Second pass
            for newinst in institer:
                instructions.append(newinst)
                keep_going = True
                while keep_going:
                    curr, prev = instructions[-1], instructions[-2]
                    test = prev.name, curr.name

                    # Prevent errors with jumps and lone labels.
                    if curr.name == "label" and curr.lblname not in jumps:
                        instructions = instructions[:-1]

                    # Branch optimizations geared for PyPy.
                    elif test in BRANCH_OPTIMIZE:
                        instructions = instructions[:-2]
                        new = INSTRUCTIONS[BRANCH_OPTIMIZE[test]](curr.lblname)
                        jumps[curr.lblname].remove(curr)
                        jumps[curr.lblname].append(new)
                        instructions.append(new)

                    # Two opcodes in a row that do nothing should be removed.
                    elif test in NO_OP_GLSL or (test == ("getlocal", "setlocal") and \
                                                prev.argument == curr.argument):
                        instructions = instructions[:-2]

                    # Jump then label. Just remove the jump.
                    elif test == ("jump", "label") and  \
                         prev.lblname == curr.lblname:
                        # Don't remove the label, we may need it for a backref
                        # later on.
                        instructions.pop(-2)
                        jumps[prev.lblname].remove(prev)

                    # return after return.
                    elif prev.name in ("returnvalue", "returnvoid") and \
                         curr.name in ("returnvalue", "returnvoid"):
                        instructions.pop()

                    # Doesn't work as the label opcode does a lot of heavy lifting.
                    ## # If a label isn't jumped to at all, it's outta here.
                    ## elif curr.name == "label" and (curr.lblname not in jumps or \
                    ##                                not jumps[curr.lblname]):
                    ##     instructions.pop()

                    elif test == ("label", "jump"):
                        for jump in jumps[prev.lblname]:
                            jump.lblname = curr.lblname
                        jumps[curr.lblname].remove(curr)
                        jumps[curr.lblname].extend(jumps[prev.lblname])
                        del jumps[prev.lblname]
                        instructions = instructions[:-2]

                    elif curr in remv_inst:
                        instructions.pop()

                    else:
                        keep_going = False

            self.instructions = instructions

        # Third pass - pack in those registers.
        institer = iter(self.instructions)
        instructions = [institer.next()]
        # local_names is the arguments to the method
        used_registers = dict((i, i) for i in xrange(len(self.local_names)))
        for newinst in institer:
            curr = instructions.pop()
            if curr.name.startswith("setlocal"):
                curr = setlocal(used_registers.setdefault(curr.argument,
                                                          len(used_registers)))
            elif curr.name.startswith("getlocal"):
                curr = getlocal(used_registers.get(curr.argument,
                                                   curr.argument))
            elif curr.name == "kill":
                curr = kill(used_registers.get(curr.argument, curr.argument))
            instructions += curr, newinst

        self._numlocals_max = len(used_registers)
        self.instructions = instructions

    def add_instructions(self, instructions):
        """
        Iterate over the given argument and add these instructions,
        one by one, to this assembler.
        """
        for i in instructions:
            self.add_instruction(i)

    def get_stack_depth(self):
        return self._stack_depth

    def set_stack_depth(self, value):
        self._stack_depth = value
        self._stack_depth_max = max(value, self._stack_depth_max)
    stack_depth = property(get_stack_depth, set_stack_depth)

    def get_scope_depth(self):
        return self._scope_depth

    def set_scope_depth(self, value):
        self._scope_depth = value
        self._scope_depth_max = max(value, self._scope_depth_max)
    scope_depth = property(get_scope_depth, set_scope_depth)

    @property
    def next_free_local(self):
        """
        Return the index of the next empty local.
        """
        return self.temporaries.next_free()

    def set_local(self, name):
        """
        Mark the register named "name" as set and return
        the index.
        """
        index = self.temporaries.index_for(name, True)
        if index > self._numlocals_max:
            self._numlocals_max = index
        return index

    def get_local(self, name):
        """
        Return the index for the local named "name".
        """
        return self.temporaries.index_for(name, False)

    def kill_local(self, name):
        """
        Mark the register named "name" as free and return
        the index.
        """
        return self.temporaries.kill(name)

    def has_local(self, name):
        """
        Returns True if we have a register named "name" in the current
        assembler context.
        """
        return name in self.temporaries

    @property
    def local_count(self):
        """
        The current local count.
        """
        return len(self.temporaries)

    def dump_instructions(self, indent="\t", exceptions=[],
                          use_label_names=False):
        """
        Dump this assembler's instructions to a string, with the given
        "indent" prepended to each line. If "use_label_names" is True,
        then the label names will be used when dumping, otherwise
        label names will be generated. Label names are not kept in
        compiled code, so it makes to set this to False when dumping
        parsed code.
        """
        lblmap, from_, to_ = {}, {}, {}
        for exc in exceptions:
            from_[exc.from_] = exc
            to_[exc.to_] = exc
        for inst in self.instructions:
            inst.assembler_pass1(self)
            if inst.label and not use_label_names:
                lblmap[inst.label.name] = "L%d" % (len(lblmap)+1)
                inst.label.name = lblmap[inst.label.name]
        dump, offset = [], 0
        for inst in self.instructions:
            if inst.label:
                dump.append("\n%s%s:" % (indent, inst.label.name,))
            if offset in from_:
                exc = from_[offset]
                dump.append("%s<%s %d" % (indent, exc.exc_type, exc.target))
            if offset in to_:
                exc = to_[offset]
                dump.append("%s>%s %d" % (indent, exc.exc_type, exc.target))
            if getattr(inst, "lblname", None):
                if not use_label_names:
                    inst.lblname = lblmap.get(inst.lblname, inst.lblname)
            dump.append("%s%d%s%s" % (indent*2, offset, indent, inst))
            if inst.offset:
                dump.append("")
            offset += len(inst.serialize())
        return '\n'.join(dump)

    def pass1(self):
        """
        Do assembler pass 1.
        """
        # Pass 1.
        for inst in self.instructions:
            inst.assembler_pass1(self)

    def write_to_pool(self, pool):
        for inst in self.instructions:
            inst.write_to_pool(pool)

    def serialize(self):
        """
        Serialize this code to a string, and also
        resolve any jump offsets.
        """
        code = ""
        # Pass 2. Generate code.
        for inst in self.instructions:
            inst.assembler_pass2(self, len(code))
            code += inst.serialize()
        # Patch up offsets.
        for inst in itertools.chain(*self.offsets.itervalues()):
            code = code[:inst.address+1] + inst.lbl.relative_offset(inst.address+4) + code[inst.address+4:]
        return code

    @classmethod
    def parse(cls, bitstream, abc, constants, local_count):
        asm = cls(constants, ["_loc%d" % (i,) for i in xrange(local_count)])
        codelen = bitstream.read(U32)
        finish  = bitstream.tell() + codelen*8
        while bitstream.tell() < finish:
            asm.add_instruction(parse_instruction(bitstream, abc, constants, asm))
        return asm

Avm2CodeAssembler = CodeAssembler
