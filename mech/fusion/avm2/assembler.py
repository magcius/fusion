
from mech.fusion.bitstream.flash_formats import U32
from mech.fusion.compat import set, StringIO
from mech.fusion.avm2.util import ValuePool, serialize_s24
from mech.fusion.avm2 import instructions as I

BRANCH_OPTIMIZE = {
    ("not",            "iftrue"):  I.iffalse,
    ("not",            "iffalse"): I.iftrue,
    ("equals",         "iftrue"):  I.ifeq,
    ("equals",         "iffalse"): I.ifne,
    ("lessthan",       "iftrue"):  I.iflt,
    ("lessthan",       "iffalse"): I.ifnlt,
    ("lessequals",     "iftrue"):  I.ifle,
    ("lessequals",     "iffalse"): I.ifnle,
    ("greaterthan",    "iftrue"):  I.ifgt,
    ("greaterthan",    "iffalse"): I.ifngt,
    ("greaterequals",  "iftrue"):  I.ifge,
    ("greaterequals",  "iffalse"): I.ifnge,
    ("strictequals",   "iftrue"):  I.ifstricteq,
    ("strictequals",   "iffalse"): I.ifstrictne,
}

GET_LOCALS = set(("getlocal", "getlocal0", "getlocal1", "getlocal2", "getlocal3"))
SET_LOCALS = set(("setlocal", "setlocal0", "setlocal1", "setlocal2", "setlocal3"))

class Avm2Label(object):
    def __init__(self, name):
        self.name = name
        self.address = None
        self.stack_depth, self.scope_depth = 0, 0

    def relative_offset(self, base):
        return serialize_s24(self.address - base)

    def __repr__(self):
        return "<Avm2Label (name=%s, stack_depth=%d, scope_depth=%d)>" \
            % (self.name, self.stack_depth, self.scope_depth)

class CodeAssembler(object):
    def __init__(self, constants, local_names):
        self.local_names = local_names
        self.temporaries = ValuePool()
        for i in local_names:
            self.temporaries.index_for(i)

        self.instructions = []

        self._stack_depth = 0
        self._scope_depth = 0

        self.max_local_count = len(local_names)
        self.max_stack_depth = 0
        self.max_scope_depth = 0

        # jump-like instructions
        self.jumps = []

        # name -> Avm2Label
        self.labels  = {}

        self.flags = 0
        self.constants = constants

    def make_label(self, name):
        label = Avm2Label(name)
        label.stack_depth, label.scope_depth = self.stack_depth, self.scope_depth
        return self.labels.setdefault(name, label)

    def add_instruction(self, instruction):
        """
        Add an instruction to this block.
        """
        if instruction is not None:
            self.instructions.append(instruction)
            instruction.assembler_added(self)

    def optimize(self):
        """
        Do some simple optimizations for stupid code generator
        clients.
        """
        for _ in xrange(2):
            jumps = {}

            # instructions to remove
            remv_inst = set()

            # register -> set([prev, curr])
            remv_regs = {}

            institer = iter(self.instructions)
            instructions = [institer.next()]

            # First pass - mark anything needed for the second pass.
            for newinst in institer:
                instructions.append(newinst)
                prev, curr = instructions[-2:]

                # Gather all jumps by their respective labels.
                if curr.jumplike:
                    jumps.setdefault(curr.labelname, []).append(curr)

                S = set((prev, curr))

                # Detect if there are any references to this register other than
                # the setlocal/getlocal sequence here.
                if prev.name in SET_LOCALS and \
                   curr.name in GET_LOCALS and \
                   prev.argument == curr.argument:
                    remv_inst.update(S)
                    remv_regs[curr.argument] = S

                # PyPy-specific optimization: some opcodes have an unnecessary
                # StoreResult at the end, so callpropvoid and some setproperty's
                # have a pushnull and an unused register afterwards. Stop that.
                elif prev.name in ("pushnull", "pushundefined") and \
                     curr.name.startswith("setlocal"):
                    remv_inst.update(S)
                    remv_regs[curr.argument] = S

                elif curr.name in GET_LOCALS:
                    if curr.argument in remv_regs:
                        remv_inst -= remv_regs[curr.argument]

                elif curr.name in SET_LOCALS:
                    # If we have any
                    remv_regs.pop(curr.argument, None)

                elif curr.name == "kill":
                    # If we're going to remove this register, mark the kill for deletion too.
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
                    prev, curr = instructions[-2:]
                    test = prev.name, curr.name

                    # Prevent errors with jumps and lone labels.
                    if curr.name == "label" and curr.labelname not in jumps:
                        instructions = instructions[:-1]

                    # Branch optimizations geared for PyPy.
                    elif test in BRANCH_OPTIMIZE:
                        instructions = instructions[:-2]
                        new = BRANCH_OPTIMIZE[test](curr.labelname)
                        jumps[curr.labelname].remove(curr)
                        jumps[curr.labelname].append(new)
                        instructions.append(new)

                    # Two opcodes in a row that do nothing should be removed.
                    elif prev.name in GET_LOCALS and curr.name in SET_LOCALS \
                             and prev.argument == curr.argument:
                        instructions = instructions[:-2]

                    # jump then label -> remove the jump.
                    elif test == ("jump", "label") and prev.labelname == curr.labelname:
                        # Don't remove the label, we may need it for a backref later on.
                        instructions.pop(-2)
                        jumps[prev.labelname].remove(prev)

                    # return after return -> remove the second return.
                    elif prev.name in ("returnvalue", "returnvoid") and \
                         curr.name in ("returnvalue", "returnvoid"):
                        instructions.pop()

                    # label then jump -> remove both and rename.
                    elif test == ("label", "jump"):
                        for jump in jumps[prev.labelname]:
                            jump.labelname = curr.labelname
                        jumps[curr.labelname].remove(curr)
                        jumps[curr.labelname].extend(jumps[prev.labelname])
                        del jumps[prev.labelname]
                        instructions = instructions[:-2]

                    elif curr in remv_inst:
                        instructions.pop()

                    else:
                        keep_going = False

            self.instructions = instructions

        # Third pass - pack in those registers.
        institer = iter(self.instructions)
        inst     = [institer.next()]
        # local_names is the arguments to the method
        used_registers = dict((i, i) for i in xrange(len(self.local_names)))

        for newinst in institer:
            curr = inst[-1]
            if curr.name in SET_LOCALS:
                index = used_registers.setdefault(curr.argument, len(used_registers))
                instructions[-1] = I.setlocal(index)

            elif curr.name in GET_LOCALS:
                inst[-1] = I.getlocal(used_registers.get(curr.argument, curr.argument))

            elif curr.name == "kill":
                inst[-1] = I.kill(used_registers.get(curr.argument, curr.argument))

        self.numlocals = len(used_registers)
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
        if value > self.max_stack_depth:
            self.max_stack_depth = value
    stack_depth = property(get_stack_depth, set_stack_depth)

    def get_scope_depth(self):
        return self._scope_depth

    def set_scope_depth(self, value):
        self._scope_depth = value
        if value > self.max_scope_depth:
            self.max_scope_depth = value
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
        if self.local_count > self.max_local_count:
            self.max_local_count = self.local_count
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
        index = self.temporaries.kill(name)
        if self.local_count > self.max_local_count:
            self.max_local_count = self.local_count
        return index

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
                          use_label_names=True):
        """
        Dump this assembler's instructions to a string, with the given
        "indent" prepended to each line. If "use_label_names" is True,
        then the label names will be used when dumping, otherwise
        label names will be generated. Label names are not kept in
        compiled code, so it makes to set this to False when dumping
        parsed code.
        """
        lblmap, exc_from, exc_to = {}, {}, {}
        for exc in exceptions:
            exc_from.setdefault(exc.from_, []).append(exc)
            exc_to  .setdefault(exc.to_  , []).append(exc)

        for inst in self.instructions:
            inst.assembler_pass1(self)
            if inst.label and not use_label_names:
                lblmap[inst.label.name] = "L%d" % (len(lblmap)+1)

        dump, offset = [], 0
        for inst in self.instructions:

            if inst.label and not inst.jumplike:
                dump.append("\n%s%s:" % (indent, lblmap.get(inst.label.name, inst.label.name)))

            for exc in exc_from.get(offset, []):
                dump.append("%s<%s %d" % (indent, exc.exc_type, exc.target))
            for exc in exc_to.get(offset, []):
                dump.append("%s>%s %d" % (indent, exc.exc_type, exc.target))

            dump.append("%s%d%s%s" % (indent*2, offset, indent, inst))
            if inst.jumplike:
                dump.append("")
            offset += len(inst)

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
        code = StringIO()
        # Pass 2. Generate code.
        for inst in self.instructions:
            inst.assembler_pass2(self, code.tell())
            code.write(inst.serialize())

        # Patch up jumps.
        for inst in self.jumps:
            assert inst in self.instructions
            code.seek(inst.address+1)
            code.write(inst.label.relative_offset(inst.address+4))
        return code.getvalue()

    @classmethod
    def parse(cls, bitstream, abc, constants, local_count):
        asm = cls(constants, ["_loc%d" % (i,) for i in xrange(local_count)])
        codelen = bitstream.read(U32)
        finish  = bitstream.tell() + codelen*8
        while bitstream.tell() < finish:
            asm.add_instruction(I.parse_instruction(bitstream, abc, constants, asm))
        return asm

Avm2CodeAssembler = CodeAssembler
