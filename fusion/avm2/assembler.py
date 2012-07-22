
try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

from fusion.bitstream.flash_formats import U32
from fusion.avm2.instructions import get_instruction, parse_instruction
from fusion.avm2.util import ValuePool, serialize_s24
from fusion.avm2.interfaces import IConstantPoolWriter

from zope.interface import implements

class Label(object):
    def __init__(self, name):
        self.name = name
        self.address = None
        self.stack_depth, self.scope_depth = 0, 0

    def relative_offset(self, base):
        return serialize_s24(self.address - base)

    def __repr__(self):
        return "<Label (name=%s, stack_depth=%d, scope_depth=%d)>" \
            % (self.name, self.stack_depth, self.scope_depth)

class CodeAssembler(object):
    implements(IConstantPoolWriter)
    def __init__(self, local_names):
        self.local_names = local_names
        self.locals = ValuePool(None)
        for i in local_names:
            self.locals.index_for(i)

        self.instructions = []

        self._stack_depth = 0
        self._scope_depth = 0

        self.max_local_count = len(local_names)
        self.max_stack_depth = 0
        self.max_scope_depth = 0

        # jump-like instructions
        self.jumps = []

        # name -> Label
        self.labels  = {}

        self.flags = 0

    def make_label(self, name):
        label = Label(name)
        label.stack_depth, label.scope_depth = self.stack_depth, self.scope_depth
        return self.labels.setdefault(name, label)

    def emit(self, name, *a, **kw):
        """
        Emit an instruction, with given arguments.
        """
        return self.add_instruction(get_instruction(name)(*a, **kw))

    def add_instruction(self, instruction):
        """
        Add an instruction to this block.
        """
        self.instructions.append(instruction)
        instruction.assembler_added(self)
        return instruction

    def add_instructions(self, instructions):
        """
        Iterate over the given argument and add these instructions,
        one by one, to this assembler.
        """
        for i in instructions:
            self.add_instruction(i)

    def optimize(self):
        """
        Do some not so simple optimizations.
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
                     curr.name in SET_LOCALS:
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
                        new = get_instruction(BRANCH_OPTIMIZE[test])(curr.labelname)
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
                instructions[-1] = get_instruction('setlocal')(index)

            elif curr.name in GET_LOCALS:
                inst[-1] = get_instruction('getlocal')(used_registers.get(curr.argument, curr.argument))

            elif curr.name == "kill":
                inst[-1] = get_instruction('kill')(used_registers.get(curr.argument, curr.argument))

        self.numlocals = len(used_registers)
        self.instructions = instructions

    # ========================================
    # STACK DEPTH and SCOPE DEPTH tracking

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

    # ========================================
    # LOCAL tracking

    @property
    def next_free_local(self):
        """
        Return the index of the next empty local.
        """
        return self.locals.next_free()

    def set_local(self, name):
        """
        Mark the register named "name" as set and return
        the index.
        """
        index = self.locals.index_for(name)
        if self.local_count > self.max_local_count:
            self.max_local_count = self.local_count
        return index

    def get_local(self, name):
        """
        Return the index for the local named "name".
        """
        return self.locals.get_index(name)

    def kill_local(self, name):
        """
        Mark the register named "name" as free and return
        the index.
        """
        index = self.locals.kill(name)
        if self.local_count > self.max_local_count:
            self.max_local_count = self.local_count
        return index

    def has_local(self, name):
        """
        Returns True if we have a register named "name" in the current
        assembler context.
        """
        return name in self.locals

    @property
    def local_count(self):
        """
        The current local count.
        """
        return len(self.locals)



    def dump_instructions(self, exceptions=[], use_label_names=False):
        """
        Dump this assembler's instructions to a string, with the given
        "indent" prepended to each line. If "use_label_names" is True,
        then the label names will be used when dumping, otherwise
        label names will be generated. Label names are not kept in
        compiled code, so it makes to set this to False when dumping
        parsed code.
        """

        # label name => remapped label name
        lblmap = {}

        # address => [exception, ...]
        exc_from = {}
        exc_to   = {}
        for exc in exceptions:
            exc_from.setdefault(exc.from_, []).append(exc)
            exc_to  .setdefault(exc.to_  , []).append(exc)

        for inst in self.instructions:
            inst.assembler_pass1(self)
            if inst.label and not use_label_names:
                lblmap[inst.label.name] = "L%d" % (len(lblmap)+1)

        dump, offset = [], 0
        for inst in self.instructions:

            if inst.label:
                lblname = inst.label.name
                lblname = lblmap.get(lblname, lblname)
                if inst.jumplike:
                    # we're jumping to the label -- get us a mapped label
                    inst.labelname = lblname
                else:
                    # we're defining a label
                    dump.append("\n%s:" % (lblname,))

            for exc in exc_from.get(offset, []):
                dump.append("<%s %d" % (exc.exc_type, exc.target))
            for exc in exc_to.get(offset, []):
                dump.append(">%s %d" % (exc.exc_type, exc.target))

            dump.append("%d\t%s" % (offset, inst))
            offset += len(inst)

        return '\n'.join(dump)

    def pass1(self):
        """
        Do assembler pass 1.
        """
        # Pass 1.
        for inst in self.instructions:
            inst.assembler_pass1(self)

    def write_constants(self, pool):
        for inst in self.instructions:
            pool.write(inst)

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
        asm = cls(["_loc%d" % (i,) for i in xrange(local_count)])
        codelen = bitstream.read(U32)
        finish  = bitstream.tell() + codelen*8
        while bitstream.tell() < finish:
            asm.add_instruction(parse_instruction(bitstream, abc, constants, asm))
        return asm
