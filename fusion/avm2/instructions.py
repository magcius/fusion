
from fusion.bitstream.flash_formats import UI8, SI8, SI24, U32
from fusion.avm2.util import serialize_u32 as u32
from fusion.avm2.interfaces import IMultiname, IConstantPoolWriter
from fusion.avm2.constants import MethodFlag

from zope.interface import implements

## Parsing

def _make_offset_label_name(offset):
    return "lbl" + str(offset)

def _make_offset_label(offset, asm):
    name = _make_offset_label_name(offset)
    label = asm.make_label(name)
    label.address = offset
    return label

class BaseInstruction(object):
    implements(IConstantPoolWriter)

    flags = 0
    stack = 0
    scope = 0
    magic  = None
    opcode = None
    name   = None
    label  = None
    jumplike = False

    def __repr__(self):
        if self.opcode is None:
            return self.name
        return "%s (0x%02X%s)" % (self.name, self.opcode, self.additional_repr())

    def __len__(self):
        return 1

    def additional_repr(self):
        return ""

    def write_constants(self, pool):
        pass

    @classmethod
    def parse_inner(cls, bitstream, abc, constants, asm):
        return cls()

    def serialize(self):
        return chr(self.opcode) + self.serialize_arguments()

    def serialize_arguments(self):
        return ""

    # Hooks for the assembler.
    def assembler_added(self, asm):
        """
        Called when the assembler adds this instruction.
        """

    def assembler_pass1(self, asm):
        """
        Called on the assembler's first pass.
        """
        asm.flags |= self.flags
        asm.stack_depth += self.stack() if callable(self.stack) else self.stack
        asm.scope_depth += self.scope() if callable(self.scope) else self.scope

    def assembler_pass2(self, asm, address):
        """
        Called on the assembler's second pass.
        """

class Debug(BaseInstruction):
    def __init__(self, debug_type, index, reg, extra):
        self.debug_type = debug_type
        self.index = index
        self.reg = reg
        self.extra = extra

    def serialize_arguments(self):
        buf = ""
        buf += chr(self.debug_type)
        buf += u32(self.index)
        buf += chr(self.reg)
        buf += u32(self.extra)
        return buf

    @classmethod
    def parse_inner(cls, bitstream, abc, constants, asm):
        debug_type = bitstream.read(UI8)
        index      = bitstream.read(U32)
        reg        = bitstream.read(UI8)
        extra      = bitstream.read(U32)
        return cls(debug_type, index, reg, extra)

    def __len__(self):
        return len(self.serialize())

class GetScope(BaseInstruction):
    def __init__(self, argument):
        self.argument = argument

    @classmethod
    def parse_inner(cls, bitstream, abc, constants, asm):
        return cls(bitstream.read(UI8))

    def serialize_arguments(self):
        return chr(self.argument)

    def additional_repr(self):
        return ", arg=%d" % (self.argument,)

    def __len__(self):
        return 2

class PushByte(BaseInstruction):
    def __init__(self, argument):
        self.argument = argument

    @classmethod
    def parse_inner(cls, bitstream, abc, constants, asm):
        return cls(bitstream.read(SI8))

    def serialize_arguments(self):
        return chr(self.argument & 0xFF)

    def additional_repr(self):
        return ", arg=%d" % (self.argument,)

class U30Base(BaseInstruction):
    arg_count = 1

    def __init__(self, *args):
        if self.arg_count != len(args):
            raise ValueError("%s takes %d argument(s). "
                             "This instance has %d argument(s)." % \
                             (self.name, self.arg_count, len(args)))

        self.arguments = args
        if self.arg_count == 1:
            self.argument = args[0]

    @classmethod
    def parse_inner(cls, bitstream, abc, constants, asm):
        return cls(*[bitstream.read(U32) for i in xrange(cls.arg_count)])

    def serialize_arguments(self):
        return ''.join(u32(i) for i in self.arguments)

    def additional_repr(self):
        return " arg="+' '.join("0x%02X" % (a,) for a in self.arguments)

    def __len__(self):
        return 2

class ConstantPoolBase(BaseInstruction):
    pool = None

    def __init__(self, argument):
        self.argument = argument
        self._arg_index = None

    @classmethod
    def parse_inner(cls, bitstream, abc, constants, asm):
        return cls(getattr(constants, cls.pool).value_at(bitstream.read(U32)))

    def serialize_arguments(self):
        return u32(self._arg_index)

    def write_constants(self, pool):
        self._arg_index = getattr(pool, self.pool).index_for(self.argument)

    def additional_repr(self):
        return " arg=%s (%r)" % (self._arg_index, self.argument)

    def __len__(self):
        return len(self.serialize())

class MultinameBase(BaseInstruction):
    no_rt = False

    def __init__(self, multiname):
        self.multiname = IMultiname(multiname)
        self._multiname_index = None

    @classmethod
    def parse_inner(cls, bitstream, abc, constants, asm):
        return cls(constants.multiname.value_at(bitstream.read(U32)))

    def assembler_pass1(self, asm):
        super(MultinameBase, self).assembler_pass1(asm)
        if self.multiname.runtime:
            asm.stack_depth -= 1

        if self.multiname.runtime_namespace:
            asm.stack_depth -= 1

    def write_constants(self, pool):
        if self.no_rt:
            if self.multiname.runtime or self.multiname.runtime_namespace:
                raise ValueError("%s used with runtime-qualified name: %s" % \
                                 (self.name, self.multiname))

        self._multiname_index = pool.multiname.index_for(self.multiname)

    def serialize_arguments(self):
        return u32(self._multiname_index)

    def additional_repr(self):
        return ", multiname=%s" % (self.multiname,)

    def __len__(self):
        return len(self.serialize())

class JumpBase(BaseInstruction):
    jumplike = True
    def __init__(self, name):
        self.labelname = name
        self.address = None

    def assembler_pass1(self, asm):
        super(JumpBase, self).assembler_pass1(asm)
        self.label = asm.make_label(self.labelname)
        asm.jumps.append(self)

    def assembler_pass2(self, asm, address):
        self.address = address

    @classmethod
    def parse_inner(cls, bitstream, abc, constants, asm):
        offset  = bitstream.read(SI24)
        offset += bitstream.tell()//8
        label = _make_offset_label(offset, asm)
        return cls(label.name)

    def serialize_arguments(self):
        return "\0\0\0"

    def additional_repr(self):
        return" lbl=%r" % (self.labelname,)

    def __len__(self):
        return 4

class LookupSwitch(BaseInstruction):
    def __init__(self, default, cases):
        self.default_name, self.case_names = default, cases
        self.default_label, self.case_labels = None, None

    @classmethod
    def parse_inner(cls, bitstream, abc, constants, asm):
        # default label
        offset  = bitstream.read(SI24)
        offset += bitstream.tell()//8
        lbl = _make_offset_label(offset, asm)

        # case label count
        cases, count = [], bitstream.read(U32) + 1

        for i in xrange(count):
            offset  = bitstream.tell()//8 - 1
            offset += bitstream.read(SI24)
            lbl = _make_offset_label(offset, asm)
            cases.append(lbl.name)

        return cls(lbl.name, cases)

    def assembler_pass1(self, asm):
        super(LookupSwitch, self).assembler_pass1(asm)
        self.default_label =  asm.make_label(self.default_name)
        self.case_labels   = [asm.make_label(name) for name in self.case_names]

    def assembler_pass2(self, asm, address):
        asm.jumps.append(self.default_label)
        asm.jumps.extend(self.case_labels)

    def serialize_arguments(self):
        cases = "\0\0\0"*len(self.case_labels)
        return "\0\0\0%s%s" % (u32(len(self.case_labels) - 1), cases)

    def __len__(self):
        return len(self.serialize())

class Label(BaseInstruction):
    def __init__(self, name):
        self.backref = False
        self.parsed = False
        self.labelname = name
        self.label = None

    @classmethod
    def parse_inner(cls, bitstream, abc, constants, asm):
        lbl = _make_offset_label(bitstream.tell()//8-1, asm)
        inst = cls(lbl.name)
        inst.label = lbl

        # Force a length and serialization.
        inst.parsed = True
        return inst

    def assembler_pass1(self, asm):
        if self.labelname in asm.labels:
            self.label = asm.labels[self.labelname]
            asm.stack_depth = self.label.stack_depth
            asm.scope_depth = self.label.scope_depth
        else:
            # If we haven't seen the label yet, we could have to jump
            # back to it later.
            self.label = asm.make_label(self.labelname)
            self.backref = True

    def assembler_pass2(self, asm, address):
        self.label.address = address

    def serialize(self):
        if self.backref or self.parsed:
            return chr(self.opcode)
        return ""

    def additional_repr(self):
        return " lbl=%r" % (self.labelname,)

    def __len__(self):
        if self.backref or self.parsed:
            return 1
        return 0

class CallIndex(BaseInstruction):
    def __init__(self, multiname, num_args):
        self.multiname = IMultiname(multiname)
        self._multiname_index = None
        self.num_args = num_args

    def stack(self):
        return 1 - (self.num_args + 1) # push object/args; push result

    def write_constants(self, pool):
        self._multiname_index = pool.multiname.index_for(self.multiname)

    def serialize_arguments(self):
        return u32(self._multiname_index) + u32(self.num_args)

    @classmethod
    def parse_inner(cls, bitstream, abc, constants, asm):
        mindex = bitstream.read(U32)
        multiname = constants.multiname.value_at(mindex)
        num_args = bitstream.read(U32)
        return cls(multiname, num_args)

    def additional_repr(self):
        return ", multiname=%s, num_args=%s" % (self.multiname, self.num_args)

    def __len__(self):
        return len(self.serialize())

class CallMultiname(CallIndex):
    void = False
    def stack(self):
        stack = -self.num_args

        if self.multiname.runtime:
            stack -= 1

        if self.multiname.runtime_namespace:
            stack -= 1

        if not self.void:
            stack += 1

        return stack

class BogusBase(BaseInstruction):
    name = "BOGUS"
    def serialize(self):
        return ""

    def __len__(self):
        return 0

class BeginTry(BogusBase):
    def __init__(self, context):
        self.context = context

    def assembler_pass2(self, asm, address):
        self.context.try_begin = address

class EndTry(BogusBase):
    def __init__(self, context):
        self.context = context

    def assembler_pass2(self, asm, address):
        self.context.try_end = address

class AddExcInfo(BogusBase):
    scope = 1

    def __init__(self, context, exc):
        self.context = context
        self.exc = exc

    def assembler_pass2(self, asm, address):
        self.exc.from_  = self.context.try_begin
        self.exc.to_    = self.context.try_end
        self.exc.target = address

class BeginCatch(BogusBase):
    stack = 1

## Instruction Table

def OP(opcode, base=BaseInstruction, **kw):
    return opcode, base, kw

OpTable = dict(
    nop             = OP(0x02),
    throw           = OP(0x03),
    getsuper        = OP(0x04, base=MultinameBase),
    setsuper        = OP(0x05, base=MultinameBase),
    dxns            = OP(0x06, flags=MethodFlag.SetsDxns, base=U30Base),
    dxnslate        = OP(0x07, flags=MethodFlag.SetsDxns),
    kill            = OP(0x08, base=U30Base),
    label           = OP(0x09, base=Label),

    pop             = OP(0x29, stack=-1),
    dup             = OP(0x2A, stack=+1),

    pushwith        = OP(0x1C, stack=-1, scope=+1),
    popscope        = OP(0x1D, scope=-1),
    pushscope       = OP(0x30, stack=-1, scope=+1),

    pushnull        = OP(0x20, stack=+1),
    pushundefined   = OP(0x21, stack=+1),
    pushtrue        = OP(0x26, stack=+1),
    pushfalse       = OP(0x27, stack=+1),
    pushnan         = OP(0x28, stack=+1),

    pushbyte        = OP(0x24, stack=+1, base=PushByte),
    pushstring      = OP(0x2C, stack=+1, base=ConstantPoolBase, pool="utf8"),
    pushint         = OP(0x2D, stack=+1, base=ConstantPoolBase, pool="int"),
    pushuint        = OP(0x2E, stack=+1, base=ConstantPoolBase, pool="uint"),
    pushdouble      = OP(0x2F, stack=+1, base=ConstantPoolBase, pool="double"),
    pushshort       = OP(0x25, stack=+1, base=U30Base),

    ifnlt           = OP(0x0C, stack=-2, base=JumpBase),
    ifnle           = OP(0x0D, stack=-2, base=JumpBase),
    ifngt           = OP(0x0E, stack=-2, base=JumpBase),
    ifnge           = OP(0x0F, stack=-2, base=JumpBase),

    jump            = OP(0x10, base=JumpBase),
    iftrue          = OP(0x11, stack=-1, base=JumpBase),
    iffalse         = OP(0x12, stack=-1, base=JumpBase),

    ifeq            = OP(0x13, stack=-2, base=JumpBase),
    ifne            = OP(0x14, stack=-2, base=JumpBase),
    iflt            = OP(0x15, stack=-2, base=JumpBase),
    ifle            = OP(0x16, stack=-2, base=JumpBase),
    ifgt            = OP(0x17, stack=-2, base=JumpBase),
    ifge            = OP(0x18, stack=-2, base=JumpBase),
    ifstricteq      = OP(0x19, stack=-2, base=JumpBase),
    ifstrictne      = OP(0x1A, stack=-2, base=JumpBase),
    lookupswitch    = OP(0x1B, base=LookupSwitch),

    nextname        = OP(0x1E, stack=-1),
    nextvalue       = OP(0x23, stack=-1),
    hasnext         = OP(0x1F, stack=-1),
    hasnext2        = OP(0x32, stack=+1, base=U30Base, arg_count=2),

    returnvoid      = OP(0x47),
    returnvalue     = OP(0x48, stack=-1),

    applytype       = OP(0x53, base=U30Base, stack=lambda self: 1-self.argument),
    newobject       = OP(0x55, base=U30Base, stack=lambda self: 1-2*self.argument),
    newarray        = OP(0x56, base=U30Base, stack=lambda self: 1-self.argument),
    newactivation   = OP(0x57, stack=+1, flags=MethodFlag.Activation),
    newfunction     = OP(0x40, stack=+1, base=U30Base),
    newclass        = OP(0x58, stack=+1, base=U30Base),
    newcatch        = OP(0x5A, stack=+1, base=U30Base),
    findproperty    = OP(0x5E, stack=+1, base=MultinameBase),
    findpropstrict  = OP(0x5D, stack=+1, base=MultinameBase),

    coerce          = OP(0x80, base=MultinameBase, no_rt=True),
    getlex          = OP(0x60, stack=+1, base=MultinameBase, no_rt=True),
    setproperty     = OP(0x61, stack=-2, base=MultinameBase),
    initproperty    = OP(0x68, stack=-2, base=MultinameBase),
    getproperty     = OP(0x66, base=MultinameBase),
    deleteproperty  = OP(0x6A, base=MultinameBase),
    getdescendants  = OP(0x59, base=MultinameBase),

    call            = OP(0x41, base=U30Base, stack=lambda self:-self.argument+1),
    construct       = OP(0x42, base=U30Base, stack=lambda self:-self.argument),
    constructsuper  = OP(0x49, base=U30Base, stack=lambda self:-self.argument-1),
    callmethod      = OP(0x43, base=CallIndex, arg_count=2),
    callstatic      = OP(0x44, base=CallIndex, arg_count=2),
    callsuper       = OP(0x45, base=CallMultiname, arg_count=2),
    callproperty    = OP(0x46, base=CallMultiname, arg_count=2),
    constructprop   = OP(0x4A, base=CallMultiname, arg_count=2),
    callproplex     = OP(0x4C, base=CallMultiname, arg_count=2),
    callsupervoid   = OP(0x4E, base=CallMultiname, arg_count=2, void=True),
    callpropvoid    = OP(0x4F, base=CallMultiname, arg_count=2, void=True),

    getlocal        = OP(0x62, base=U30Base, stack=+1),
    setlocal        = OP(0x63, base=U30Base, stack=-1),

    getglobalscope  = OP(0x64, stack=+1),
    getscopeobject  = OP(0x65, stack=+1, base=GetScope),
    getouterscope   = OP(0x67, stack=+1, base=U30Base),
    getslot         = OP(0x6C, base=U30Base),
    setslot         = OP(0x6D, stack=-1, base=U30Base),
    getglobalslot   = OP(0x6E, stack=+1, base=U30Base),

    getlocal0       = OP(0xD0, stack=+1, argument=0),
    getlocal1       = OP(0xD1, stack=+1, argument=1),
    getlocal2       = OP(0xD2, stack=+1, argument=2),
    getlocal3       = OP(0xD3, stack=+1, argument=3),

    setlocal0       = OP(0xD4, stack=-1, argument=0),
    setlocal1       = OP(0xD5, stack=-1, argument=1),
    setlocal2       = OP(0xD6, stack=-1, argument=2),
    setlocal3       = OP(0xD7, stack=-1, argument=3),

    esc_xelem       = OP(0x71),
    esc_xattr       = OP(0x72),

    coerce_a        = OP(0x82),
    coerce_s        = OP(0x85),
    convert_s       = OP(0x70),
    convert_i       = OP(0x73),
    convert_u       = OP(0x74),
    convert_d       = OP(0x75),
    convert_b       = OP(0x76),
    convert_o       = OP(0x77),
    checkfilter     = OP(0x78),

    swap            = OP(0x2B),
    negate          = OP(0x90),
    negate_i        = OP(0xC4),
    increment       = OP(0x91),
    increment_i     = OP(0xC0),
    decrement       = OP(0x93),
    decrement_i     = OP(0xC1),
    typeof          = OP(0x95),
    not_            = OP(0x96),
    bitnot          = OP(0x97),

    add             = OP(0xA0, stack=-1),
    add_i           = OP(0xC5, stack=-1),
    subtract        = OP(0xA1, stack=-1),
    subtract_i      = OP(0xC6, stack=-1),
    multiply        = OP(0xA2, stack=-1),
    multiply_i      = OP(0xC7, stack=-1),
    divide          = OP(0xA3, stack=-1),
    modulo          = OP(0xA4, stack=-1),
    lshift          = OP(0xA5, stack=-1),
    rshift          = OP(0xA6, stack=-1),
    urshift         = OP(0xA7, stack=-1),
    bitand          = OP(0xA8, stack=-1),
    bitor           = OP(0xA9, stack=-1),
    bitxor          = OP(0xAA, stack=-1),

    equals          = OP(0xAB, stack=-1),
    strictequals    = OP(0xAC, stack=-1),
    lessthan        = OP(0xAD, stack=-1),
    lessequals      = OP(0xAE, stack=-1),
    greaterthan     = OP(0xAF, stack=-1),
    greaterequals   = OP(0xB0, stack=-1),

    astype          = OP(0x86, base=MultinameBase),
    astypelate      = OP(0x87, stack=-1),
    instanceof      = OP(0xB1, stack=-1),
    istype          = OP(0xB2, base=MultinameBase),
    istypelate      = OP(0xB3, stack=-1),
    in_             = OP(0xB4, stack=-1),

    inclocal        = OP(0x92, base=U30Base),
    inclocal_i      = OP(0xC2, base=U30Base),
    declocal        = OP(0x94, base=U30Base),
    declocal_i      = OP(0xC3, base=U30Base),

    debug           = OP(0xEF, base=Debug),
    debugline       = OP(0xF0, base=U30Base),
    debugfile       = OP(0xF1, base=ConstantPoolBase, pool="utf8"),
)

_InstructionCache = {}

# Give us some bogies.
_InstructionCache["begintry"]   = BeginTry
_InstructionCache["endtry"]     = EndTry
_InstructionCache["addexcinfo"] = AddExcInfo
_InstructionCache["begincatch"] = BeginCatch

# Patch up keyword those keywords.
OpTable["in"] = OpTable.pop("in_")
OpTable["not"] = OpTable.pop("not_")

# Map opcode -> name.
def _make_name_table():
    tbl = {}
    for name, (opcode, _, _2) in OpTable.iteritems():
        tbl[opcode] = name
    return tbl

OpcodeToName = _make_name_table()

## Public API.

def get_instruction(name):
    name = name.rstrip("_")
    if name not in _InstructionCache:
        opcode, base, kw = OpTable[name]

        instruction = type(name, (base,), kw)
        instruction.opcode = opcode
        instruction.name = name

        _InstructionCache[name] = instruction

    return _InstructionCache[name]

def parse_instruction(bitstream, abc, constants, asm):
    label_name = _make_offset_label_name(bitstream.tell()//8)
    cls = get_instruction(OpcodeToName[bitstream.read(UI8)])
    inst = cls.parse_inner(bitstream, abc, constants, asm)
    if label_name in asm.labels:
        inst.label = asm.labels[label_name]
    return inst

__all__ = ["get_instruction", "parse_instruction"]
