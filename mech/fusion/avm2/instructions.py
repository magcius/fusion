from types import FunctionType

from mech.fusion.bitstream.flash_formats import UI8, SI24, U32
from mech.fusion.avm2.util import serialize_u32 as u32, Avm2Label
from mech.fusion.avm2.constants import METHODFLAG_Activation, \
    METHODFLAG_SetsDxns, has_RTName, has_RTNS, QName

INSTRUCTIONS = {}

def parse_instruction(bitstream, abc, constants, asm):
    label_name = make_offset_label_name(bitstream.cursor//8)
    cls = INSTRUCTIONS[bitstream.read(UI8)]
    inst = cls.parse_inner(bitstream, abc, constants, asm)
    if label_name in asm.labels:
        inst.label = asm.labels[label_name]
    return inst

def make_offset_label_name(offset):
    return "lbl%d" % (offset,)

def make_offset_label(offset, asm):
    name = make_offset_label_name(offset)
    if name in asm.labels:
        return asm.labels[name]
    else:
        lbl = Avm2Label(asm, offset)
        lbl.name = name
        asm.labels[name] = lbl
        return lbl

def fake_offset(lbl, offset):
    lbl.lbl = lbl
    lbl.address = offset

def get_label(name, asm):
    if name in asm.labels:
        lbl = asm.labels[name]
        if lbl.seenlabel:
            lbl.backref = True
    else:
        lbl = asm.labels[name] = Avm2Label(asm)
        lbl.name = name
    return lbl

class _Avm2ShortInstruction(object):
    offset = False
    flags = 0
    stack = 0
    scope = 0
    opcode = None
    name  = None
    label = None
    next  = None

    def __repr__(self):
        if self.opcode is None:
            return self.name
        return "%s (0x%02X%s)" % (self.name, self.opcode, self.__repr_inner__())

    def __repr_inner__(self):
        return ""

    def assembler_added(self, asm):
        pass

    def assembler_pass1(self, asm):
        asm.flags |= self.flags
        asm.stack_depth += self.stack
        asm.scope_depth += self.scope

    def assembler_pass2(self, asm, address):
        pass

    def write_to_pool(self, pool):
        pass

    @classmethod
    def parse_inner(cls, bitstream, abc, constants, asm):
        return cls()

    def serialize(self):
        return chr(self.opcode)

class _Avm2DebugInstruction(_Avm2ShortInstruction):
    def serialize(self):
        return chr(self.opcode) + \
            chr(self.debug_type & 0xFF) + \
            u32(self.index) + \
            chr(self.reg & 0xFF) + \
            u32(self.extra)

    @classmethod
    def parse_inner(cls, bitstream, abc, constants, asm):
        debug_type = bitstream.read(UI8)
        index      = bitstream.read(U32)
        reg        = bitstream.read(UI8)
        extra      = bitstream.read(U32)
        return cls(debug_type, index, reg, extra)

    def __init__(self, debug_type, index, reg, extra):
        self.debug_type = debug_type
        self.index = index
        self.reg = reg
        self.extra = extra

class _Avm2U8Instruction(_Avm2ShortInstruction):
    def __repr_inner__(self):
        return ", arg=%d" % (self.argument,)

    @classmethod
    def parse_inner(cls, bitstream, abc, constants, asm):
        return cls(bitstream.read(UI8))

    def serialize(self):
        return chr(self.opcode) + chr(self.argument)

    def __init__(self, argument):
        self.argument = argument

class _Avm2U30Instruction(_Avm2ShortInstruction):
    arg_count = 1
    def __repr_inner__(self):
        return " arg="+' '.join("0x%02X" % (a,) for a in self.arguments)

    @classmethod
    def parse_inner(cls, bitstream, abc, constants, asm):
        return cls(*[bitstream.read(U32) for i in xrange(cls.arg_count)])

    def serialize(self):
        if self.arg_count != len(self.arguments):
            raise ValueError("%s takes %d argument(s). "
                             "This instance has %d argument(s)." % \
                             (self.name, self.arg_count, len(self.arguments)))
        return chr(self.opcode) + ''.join(u32(i) for i in self.arguments)

    def __init__(self, argument, *arguments):
        self.arguments = (argument, ) + arguments
        self.argument = argument

class _Avm2PushPoolInstruction(_Avm2ShortInstruction):
    pool = None
    def __repr_inner__(self):
        return " arg=%s (%r)" % (self._arg_index, self.argument)

    @classmethod
    def parse_inner(cls, bitstream, abc, constants, asm):
        return cls(getattr(constants, cls.pool).value_at(bitstream.read(U32)))

    def serialize(self):
        return chr(self.opcode) + u32(self._arg_index)

    def write_to_pool(self, pool):
        self._arg_index = getattr(pool, self.pool).index_for(self.argument)

    def __init__(self, argument):
        self.argument = argument
        self._arg_index = None

class _Avm2MultinameInstruction(_Avm2ShortInstruction):
    no_rt = False
    def assembler_pass1(self, asm):
        super(_Avm2MultinameInstruction, self).assembler_pass1(asm)
        asm.stack_depth -= int(self._has_rtns) + int(self._has_rtname)

    def write_to_pool(self, pool):
        self._has_rtname = has_RTName(self.multiname)
        self._has_rtns   = has_RTNS  (self.multiname)
        if self.no_rt:
            if self._has_rtname or self._has_rtns:
                raise ValueError("%s used with runtime-qualified name: %s" % \
                                 (self.name, self.multiname))

        self._multiname_index = pool.multiname_pool.index_for(self.multiname)

    def serialize(self):
        return chr(self.opcode) + u32(self._multiname_index)

    @classmethod
    def parse_inner(cls, bitstream, abc, constants, asm):
        return cls(constants.multiname_pool.value_at(bitstream.read(U32)))

    def __repr_inner__(self):
        return ", multiname=%s" % (self.multiname,)

    def __init__(self, multiname):
        self._multiname_index = 0
        self.multiname = QName(multiname)

class _Avm2OffsetInstruction(_Avm2ShortInstruction):
    offset=True
    def __repr_inner__(self):
        return" lbl=%r" % (self.lblname,)

    def assembler_pass1(self, asm):
        super(_Avm2OffsetInstruction, self).assembler_pass1(asm)
        self.lbl = get_label(self.lblname, asm)
        asm.offsets.setdefault(self.lblname, [])
        asm.offsets[self.lblname].append(self)

    def assembler_pass2(self, asm, address):
        self.address = address

    @classmethod
    def parse_inner(cls, bitstream, abc, constants, asm):
        offset  = bitstream.read(SI24)
        offset += bitstream.cursor//8
        lbl = make_offset_label(offset, asm)
        return cls(lbl.name)

    def serialize(self):
        return chr(self.opcode) + "\0\0\0"

    def __init__(self, name):
        self.lblname = name

class _Avm2LookupSwitchInstruction(_Avm2ShortInstruction):
    def assembler_pass1(self, asm):
        super(_Avm2LookupSwitchInstruction, self).assembler_pass1(asm)
        self.default_label =  get_label(self.default_label_name, asm)
        self.case_labels   = [get_label(name, asm) for name in self.case_label_names]

    def assembler_pass2(self, asm, address):
        address += 1 # opcode
        fake_offset(self.default_label, address)
        asm.offsets.setdefault(self.default_label_name, [])
        asm.offsets[self.default_label].append(self.default_label)
        address += len(u32(len(self.case_labels) - 1))
        for lbl in self.case_labels:
            fake_offset(lbl, address)
            asm.offsets.setdefault(lbl.name, [])
            asm.offsets[lbl.name].append(lbl)
            address += 3 # s24

    def serialize(self):
        return chr(self.opcode) + "\0\0\0" + u32(len(self.case_labels) - 1) + "\0\0\0"*len(self.case_labels)

    @classmethod
    def parse_inner(cls, bitstream, abc, constants, asm):
        # default label
        offset  = bitstream.read(SI24)
        offset += bitstream.cursor/8
        lbl = make_offset_label(offset, asm)

        # case label count
        cases, count = [], bitstream.read(U32) + 1

        for i in xrange(count):
            offset  = bitstream.cursor//8 - 1
            offset += bitstream.read(SI24)
            lbl = make_offset_label(offset, asm)
            cases.append(lbl.name)

        return cls(lbl.name, *cases)

    def __init__(self, default_label_name=None, *case_label_names):
        self.default_label_name, self.case_label_names = default_label_name, case_label_names

class _Avm2LabelInstruction(_Avm2ShortInstruction):
    def __repr_inner__(self):
        return " lbl=%r" % (self.lblname,)

    def assembler_pass1(self, asm):
        if self.lblname in asm.labels:
            lbl = asm.labels[self.lblname]
            asm.stack_depth = lbl.stack_depth
            asm.scope_depth = lbl.scope_depth
        else:
            lbl = asm.labels[self.lblname] = Avm2Label(asm)
            lbl.name = self.lblname

        lbl.seenlabel = True
        self.lbl = lbl

    def assembler_pass2(self, asm, address):
        self.lbl.address = address
        if self.lbl.backref:
            self.label = self.lbl
        else:
            self.next.label = self.lbl

    def serialize(self):
        if self.lbl.backref:
            return label_internal.serialize()
        return ""

    @classmethod
    def parse_inner(cls, bitstream, abc, constants, asm):
        lbl = make_offset_label(bitstream.cursor//8-1, asm)
        lbl.backref = True
        inst = cls(lbl.name)
        inst.label = lbl
        return inst

    def __init__(self, name):
        self.lblname = name

class _Avm2Call(_Avm2U30Instruction):
    def assembler_pass1(self, asm):
        asm.stack_depth += 1 - (self.argument + 2) # push function/receiver/args; push result

class _Avm2Construct(_Avm2U30Instruction):
    def assembler_pass1(self, asm):
        asm.stack_depth += 1 - (self.argument + 1) # push object/args; push result

class _Avm2ConstructSuper(_Avm2U30Instruction):
    def assembler_pass1(self, asm):
        asm.stack_depth += self.argument + 1 # pop receiver/args

class _Avm2CallIDX(_Avm2ShortInstruction):
    def assembler_pass1(self, asm):
        asm.stack_depth += 1 - (self.num_args + 1) # push object/args; push result

    def write_to_pool(self, pool):
        self._multiname_index = pool.multiname_pool.index_for(self.multiname)

    def __init__(self, multiname, num_args):
        self.multiname, self.num_args = QName(multiname), num_args

    def serialize(self):
        return chr(self.opcode) + u32(self._multiname_index) + u32(self.num_args)

    @classmethod
    def parse_inner(cls, bitstream, abc, constants, asm):
        return cls(constants.multiname_pool.value_at(bitstream.read(U32)), bitstream.read(U32))

    def __repr_inner__(self):
        return ", multiname=%s, num_args=%d" % (self.multiname, self.num_args)

class _Avm2CallMN(_Avm2CallIDX):
    is_void = False
    def assembler_pass1(self, asm):
        super(_Avm2CallMN, self).assembler_pass1(asm)
        has_rtns   = has_RTNS(self.multiname)
        has_rtname = has_RTName(self.multiname)
        asm.stack_depth += int(self.is_void) - \
            (1 + int(has_rtns) + int(has_rtname) + self.num_args)

class _Avm2CallMNVoid(_Avm2CallMN):
    is_void = True

class _Avm2ApplyType(_Avm2U30Instruction):
    def assembler_pass1(self, asm):
        asm.stack_depth += 1 - self.argument

class _Avm2NewArray(_Avm2U30Instruction):
    def assembler_pass1(self, asm):
        asm.stack_depth += 1 - self.argument

class _Avm2NewObject(_Avm2U30Instruction):
    def assembler_pass1(self, asm):
        asm.stack_depth += 1 - (2 * self.argument)

def _make_avm2(class_, opcode, name, stack=0, scope=0, **kwargs):
    o, n, st, sc = opcode, name, stack, scope
    class inner(class_):
        opcode = o
        name = n
        stack = st
        scope = sc
    for k, v in kwargs.iteritems():
        if isinstance(v, FunctionType):
            v = staticmethod(v)
        setattr(inner, k, v)
    inner.__name__ = name
    INSTRUCTIONS[name]   = inner
    INSTRUCTIONS[opcode] = inner
    return inner

m = _make_avm2
del _make_avm2

class _Avm2BogusInstruction(_Avm2ShortInstruction):
    opcode = -1
    def serialize(self):
        return ""

class _Avm2TryInstruction(_Avm2BogusInstruction):
    def assembler_pass2(self, asm, address):
        setattr(self.context, self.attrname, address)

    def __init__(self, context):
        self.context = context

class begintry(_Avm2TryInstruction): attrname = "try_begin"
class endtry  (_Avm2TryInstruction): attrname = "try_end"

class addexcinfo(_Avm2BogusInstruction):
    scope = 1
    def assembler_pass2(self, asm, address):
        self.exc.from_  = self.context.try_begin
        self.exc.to_    = self.context.try_end
        self.exc.target = address

    def __init__(self, context, exc):
        self.context = context
        self.exc = exc

class begincatch(_Avm2BogusInstruction): scope = 1

# Instructions that push one value to the stack and take no arguments.
dup = m(_Avm2ShortInstruction, 0x2A, "dup", 1)
getglobalscope = m(_Avm2ShortInstruction, 0x64, "getglobalscope", 1)
getlocal0 = m(_Avm2ShortInstruction, 0xD0, "getlocal0", 1, argument=0)
getlocal1 = m(_Avm2ShortInstruction, 0xD1, 'getlocal1', 1, argument=1)
getlocal2 = m(_Avm2ShortInstruction, 0xD2, 'getlocal2', 1, argument=2)
getlocal3 = m(_Avm2ShortInstruction, 0xD3, 'getlocal3', 1, argument=3)
newactivation = m(_Avm2ShortInstruction, 0x57, 'newactivation', 1,\
                      flags=METHODFLAG_Activation)
pushfalse = m(_Avm2ShortInstruction, 0x27, 'pushfalse', 1)
pushnan = m(_Avm2ShortInstruction, 0x28, 'pushnan', 1)
pushnull = m(_Avm2ShortInstruction, 0x20, 'pushnull', 1)
pushtrue = m(_Avm2ShortInstruction, 0x26, 'pushtrue', 1)
pushundefined = m(_Avm2ShortInstruction, 0x21, 'pushundefined', 1)
# Instructions that pop one value from the stack and take no arguments.
add = m(_Avm2ShortInstruction, 0xA0, 'add', -1)
add_i = m(_Avm2ShortInstruction, 0xC5, 'add_i', -1)
astypelate = m(_Avm2ShortInstruction, 0x87, 'astypelate', -1)
bitand = m(_Avm2ShortInstruction, 0xA8, 'bitand', -1)
bitor = m(_Avm2ShortInstruction, 0xA9, 'bitor', -1)
bitxor = m(_Avm2ShortInstruction, 0xAA, 'bitxor', -1)
divide = m(_Avm2ShortInstruction, 0xA3, 'divide', -1)
dxnslate = m(_Avm2ShortInstruction, 0x07, 'dxnslate', -1, flags=METHODFLAG_SetsDxns)
equals = m(_Avm2ShortInstruction, 0xAB, 'equals', -1)
greaterequals = m(_Avm2ShortInstruction, 0xB0, 'greaterequals', -1)
greaterthan = m(_Avm2ShortInstruction, 0xAF, 'greaterthan', -1)
hasnext = m(_Avm2ShortInstruction, 0x1F, 'hasnext', -1)
if_ = m(_Avm2ShortInstruction, 0xB4, 'in', -1)
instanceof = m(_Avm2ShortInstruction, 0xB1, 'instanceof', -1)
istypelate = m(_Avm2ShortInstruction, 0xB3, 'istypelate', -1)
lessequals = m(_Avm2ShortInstruction, 0xAE, 'lessequals', -1)
lessthan = m(_Avm2ShortInstruction, 0xAD, 'lessthan', -1)
lshift = m(_Avm2ShortInstruction, 0xA5, 'lshift', -1)
modulo = m(_Avm2ShortInstruction, 0xA4, 'modulo', -1)
multiply = m(_Avm2ShortInstruction, 0xA2, 'multiply', -1)
multiply_i = m(_Avm2ShortInstruction, 0xC7, 'multiply_i', -1)
nextname = m(_Avm2ShortInstruction, 0x1E, 'nextname', -1)
nextvalue = m(_Avm2ShortInstruction, 0x23, 'nextvalue', -1)
pop = m(_Avm2ShortInstruction, 0x29, 'pop', -1)
pushscope = m(_Avm2ShortInstruction, 0x30, 'pushscope', -1, 1) # Changes scope depth.
pushwith = m(_Avm2ShortInstruction, 0x1C, 'pushwith', -1, 1) # Changes scope depth.
returnvalue = m(_Avm2ShortInstruction, 0x48, 'returnvalue', -1)
rshift = m(_Avm2ShortInstruction, 0xA6, 'rshift', -1)
setlocal0 = m(_Avm2ShortInstruction, 0xD4, 'setlocal0', -1, argument=0)
setlocal1 = m(_Avm2ShortInstruction, 0xD5, 'setlocal1', -1, argument=1)
setlocal2 = m(_Avm2ShortInstruction, 0xD6, 'setlocal2', -1, argument=2)
setlocal3 = m(_Avm2ShortInstruction, 0xD7, 'setlocal3', -1, argument=3)
strictequals = m(_Avm2ShortInstruction, 0xAC, 'strictequals', -1)
subtract = m(_Avm2ShortInstruction, 0xA1, 'subtract', -1)
subtract_i = m(_Avm2ShortInstruction, 0xC6, 'subtract_i', -1)
throw = m(_Avm2ShortInstruction, 0x03, 'throw', -1)
urshift = m(_Avm2ShortInstruction, 0xA7, 'urshift', -1)

# Instructions that do not change the stack height and take no arguments.
bitnot = m(_Avm2ShortInstruction, 0x97, 'bitnot')
checkfilter = m(_Avm2ShortInstruction, 0x78, 'checkfilter')
coerce_a = m(_Avm2ShortInstruction, 0x82, 'coerce_a')
coerce_s = m(_Avm2ShortInstruction, 0x85, 'coerce_s')
convert_b = m(_Avm2ShortInstruction, 0x76, 'convert_b')
convert_d = m(_Avm2ShortInstruction, 0x75, 'convert_d')
convert_i = m(_Avm2ShortInstruction, 0x73, 'convert_i')
convert_o = m(_Avm2ShortInstruction, 0x77, 'convert_o')
convert_s = m(_Avm2ShortInstruction, 0x70, 'convert_s')
convert_u = m(_Avm2ShortInstruction, 0x74, 'convert_u')
decrement = m(_Avm2ShortInstruction, 0x93, 'decrement')
decrement_i = m(_Avm2ShortInstruction, 0xC1, 'decrement_i')
esc_xattr = m(_Avm2ShortInstruction, 0x72, 'esc_xattr')
esc_xelem = m(_Avm2ShortInstruction, 0x71, 'esc_xelem')
increment = m(_Avm2ShortInstruction, 0x91, 'increment')
increment_i = m(_Avm2ShortInstruction, 0xC0, 'increment_i')
# kill moved down to Special.
negate = m(_Avm2ShortInstruction, 0x90, 'negate')
negate_i = m(_Avm2ShortInstruction, 0xC4, 'negate_i')
nop = m(_Avm2ShortInstruction, 0x02, 'nop')
not_ = m(_Avm2ShortInstruction, 0x96, 'not')
popscope = m(_Avm2ShortInstruction, 0x1D, 'popscope', 0, -1) # Changes scope depth.
returnvoid = m(_Avm2ShortInstruction, 0x47, 'returnvoid')
swap = m(_Avm2ShortInstruction, 0x2B, 'swap')
typeof = m(_Avm2ShortInstruction, 0x95, 'typeof')

# Call Instructions
call = m(_Avm2Call, 0x41, 'call')
construct = m(_Avm2Construct, 0x42, 'construct')
constructsuper = m(_Avm2ConstructSuper, 0x49, 'constructsuper')
callmethod = m(_Avm2CallIDX, 0x43, 'callmethod', arg_count=2)
callstatic = m(_Avm2CallIDX, 0x43, 'callstatic', arg_count=2)
callsuper = m(_Avm2CallMN, 0x45, 'callsuper', arg_count=2)
callproperty = m(_Avm2CallMN, 0x46, 'callproperty', arg_count=2)
constructprop = m(_Avm2CallMN, 0x4A, 'constructprop', arg_count=2)
callproplex = m(_Avm2CallMN, 0x4C, 'callproplex', arg_count=2)
callsupervoid = m(_Avm2CallMNVoid, 0x4E, 'callsupervoid', arg_count=2)
callpropvoid = m(_Avm2CallMNVoid, 0x4F, 'callpropvoid', arg_count=2)

# Instructions that do not chage the stack height stack and take one U30 argument.
astype = m(_Avm2U30Instruction, 0x86, 'astype')
# coerce moved to special.
debugfile = m(_Avm2U30Instruction, 0xF1, 'debugfile')
debugline = m(_Avm2U30Instruction, 0xF0, 'debugline')
declocal = m(_Avm2U30Instruction, 0x94, 'declocal')
declocal_i = m(_Avm2U30Instruction, 0xC3, 'declocal_i')
dxns = m(_Avm2U30Instruction, 0x06, 'dxns', flags=METHODFLAG_SetsDxns)
getslot = m(_Avm2U30Instruction, 0x6C, 'getslot')
inclocal = m(_Avm2U30Instruction, 0x92, 'inclocal')
inclocal_i = m(_Avm2U30Instruction, 0xC2, 'inclocal_i')
istype = m(_Avm2U30Instruction, 0xB2, 'istype')
kill = m(_Avm2U30Instruction, 0x08, 'kill')
newclass = m(_Avm2U30Instruction, 0x58, 'newclass')

# Instructions that push to the stack and take one U30 argument.
getglobalslot = m(_Avm2U30Instruction, 0x6E, 'getglobalslot', 1)
getscopeobject = m(_Avm2U30Instruction, 0x65, 'getscopeobject', 1)
getouterscope = m(_Avm2U30Instruction, 0x67, 'getouterscope', 1)
# getproperty moved down to special.
newcatch = m(_Avm2U30Instruction, 0x5A, 'newcatch', 1)
newfunction = m(_Avm2U30Instruction, 0x40, 'newfunction', 1)
pushdouble = m(_Avm2PushPoolInstruction, 0x2F, 'pushdouble', 1, pool="double_pool")
pushint = m(_Avm2PushPoolInstruction, 0x2D, 'pushint', 1, pool="int_pool")
pushnamespace = m(_Avm2PushPoolInstruction, 0x31, 'pushnamespace', 1, pool="namespace_pool")
pushshort = m(_Avm2U30Instruction, 0x25, 'pushshort', 1)
pushstring = m(_Avm2PushPoolInstruction, 0x2C, 'pushstring', 1, pool="utf8_pool")
pushuint = m(_Avm2PushPoolInstruction, 0x2E, 'pushuint', 1, pool="uint_pool")
_getlocal = m(_Avm2U30Instruction, 0x62, 'getlocal')

# Instructions that pop from the stack and take one U30 argument.
_setlocal = m(_Avm2U30Instruction, 0x63, 'setlocal', -1)
setslot = m(_Avm2U30Instruction, 0x6D, 'setslot', -1)

# Instructions that push one value to the stack and take two U30 arguments.
hasnext2 = m(_Avm2U30Instruction, 0x32, 'hasnext2', 1, arg_count=2)

# Instructions that push/pop values to the stack (depends on arg) and take one U30 argument.
newarray = m(_Avm2NewArray, 0x56, 'newarray')
newobject = m(_Avm2NewObject, 0x55, 'newobject')
applytype = m(_Avm2ApplyType, 0x53, 'applytype')

# Instructions that take one U8 argument.
pushbyte = m(_Avm2U8Instruction, 0x24, 'pushbyte', 1)

# Offset instructions
ifeq = m(_Avm2OffsetInstruction, 0x13, 'ifeq', -2)
ifge = m(_Avm2OffsetInstruction, 0x18, 'ifge', -2)
ifgt = m(_Avm2OffsetInstruction, 0x17, 'ifgt', -2)
ifle = m(_Avm2OffsetInstruction, 0x16, 'ifle', -2)
iflt = m(_Avm2OffsetInstruction, 0x15, 'iflt', -2)
ifne = m(_Avm2OffsetInstruction, 0x14, 'ifne', -2)
ifnge = m(_Avm2OffsetInstruction, 0x0F, 'ifnge', -2)
ifngt = m(_Avm2OffsetInstruction, 0x0E, 'ifngt', -2)
ifnle = m(_Avm2OffsetInstruction, 0x0D, 'ifnle', -2)
ifnlt = m(_Avm2OffsetInstruction, 0x0C, 'ifnlt', -2)
ifstricteq = m(_Avm2OffsetInstruction, 0x19, 'ifstricteq', -2)
ifstrictne = m(_Avm2OffsetInstruction, 0x1A, 'ifstrictne', -2)
iffalse = m(_Avm2OffsetInstruction, 0x12, 'iffalse', -1)
iftrue = m(_Avm2OffsetInstruction, 0x11, 'iftrue', -1)
jump = m(_Avm2OffsetInstruction, 0x10, 'jump')

# Special Instructions
debug = m(_Avm2DebugInstruction, 0xEF, 'debug')
label_internal = m(_Avm2ShortInstruction, 0x09, 'label')()
label = m(_Avm2LabelInstruction, 0x09, 'label') # Override this for parsing.
lookupswitch = m(_Avm2LookupSwitchInstruction, 0x1B, 'lookupswitch')
coerce = m(_Avm2MultinameInstruction, 0x80, 'coerce', 0, no_rt=True)
getlex = m(_Avm2MultinameInstruction, 0x60, 'getlex', 1, no_rt=True)
deleteproperty = m(_Avm2MultinameInstruction, 0x6A, 'deleteproperty', 0)
getdescendants = m(_Avm2MultinameInstruction, 0x59, 'getdescendants', 0)
getproperty = m(_Avm2MultinameInstruction, 0x66, 'getproperty', 0)
getsuper = m(_Avm2MultinameInstruction, 0x04, 'getsuper', 0)
findproperty = m(_Avm2MultinameInstruction, 0x5E, 'findproperty', 1)
findpropstrict = m(_Avm2MultinameInstruction, 0x5D, 'findpropstrict', 1)
initproperty = m(_Avm2MultinameInstruction, 0x68, 'initproperty', -2)
setproperty = m(_Avm2MultinameInstruction, 0x61, 'setproperty', -2)
setsuper = m(_Avm2MultinameInstruction, 0x05, 'setsuper', -2)

_s_speed = {0: setlocal0, 1: setlocal1, 2: setlocal2, 3: setlocal3}
def setlocal(index):
    if index in _s_speed:
        return _s_speed[index]()
    return _setlocal(index)

_g_speed = {0: getlocal0, 1: getlocal1, 2: getlocal2, 3: getlocal3}
def getlocal(index):
    if index in _g_speed:
        return _g_speed[index]()
    return _getlocal(index)

del m
