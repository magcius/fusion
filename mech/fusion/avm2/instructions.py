
from mech.fusion.bitstream.flash_formats import UI8, SI8, SI24, U32
from mech.fusion.avm2.util import serialize_u32 as u32
from mech.fusion.avm2.constants import METHODFLAG_Activation, \
    METHODFLAG_SetsDxns, has_RTName, has_RTNS, IMultiname

INSTRUCTIONS = {}

## Parsing

def parse_instruction(bitstream, abc, constants, asm):
    label_name = make_offset_label_name(bitstream.tell()//8)
    cls = INSTRUCTIONS[bitstream.read(UI8)]
    inst = cls.parse_inner(bitstream, abc, constants, asm)
    if label_name in asm.labels:
        inst.label = asm.labels[label_name]
    return inst

def make_offset_label_name(offset):
    return "lbl" + str(offset)

def make_offset_label(offset, asm):
    name = make_offset_label_name(offset)
    label = asm.make_label(name)
    label.address = offset
    return label

class _Avm2ShortInstruction(object):
    flags = 0
    stack = 0
    scope = 0
    opcode = None
    name   = None
    label  = None
    jumplike = False

    def __repr__(self):
        if self.opcode is None:
            return self.name
        return "%s (0x%02X%s)" % (self.name, self.opcode, self.__repr_inner__())

    def __repr_inner__(self):
        return ""

    def __len__(self):
        return 1

    def assembler_added(self, asm):
        pass

    def assembler_pass1(self, asm):
        asm.flags |= self.flags
        asm.stack_depth += self.stack(asm) if callable(self.stack) else self.stack
        asm.scope_depth += self.scope(asm) if callable(self.scope) else self.scope

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
    def __init__(self, debug_type, index, reg, extra):
        self.debug_type = debug_type
        self.index = index
        self.reg = reg
        self.extra = extra

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

    def __len__(self):
        return len(self.serialize())

class _Avm2GetScopeObject(_Avm2ShortInstruction):
    def __init__(self, argument):
        self.argument = argument

    @classmethod
    def parse_inner(cls, bitstream, abc, constants, asm):
        return cls(bitstream.read(UI8))

    def serialize(self):
        return chr(self.opcode) + chr(self.argument)

    def __repr_inner__(self):
        return ", arg=%d" % (self.argument,)

    def __len__(self):
        return 2

class _Avm2PushByte(_Avm2ShortInstruction):
    def __init__(self, argument):
        self.argument = argument

    @classmethod
    def parse_inner(cls, bitstream, abc, constants, asm):
        return cls(bitstream.read(SI8))

    def serialize(self):
        return chr(self.opcode) + chr(self.argument & 0xFF)

    def __repr_inner__(self):
        return ", arg=%d" % (self.argument,)

class _Avm2U30Instruction(_Avm2ShortInstruction):
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

    def serialize(self):
        return chr(self.opcode) + ''.join(u32(i) for i in self.arguments)

    def __repr_inner__(self):
        return " arg="+' '.join("0x%02X" % (a,) for a in self.arguments)

    def __len__(self):
        return 2

class _Avm2PushPoolInstruction(_Avm2ShortInstruction):
    pool = None

    def __init__(self, argument):
        self.argument = argument
        self._arg_index = None

    @classmethod
    def parse_inner(cls, bitstream, abc, constants, asm):
        return cls(getattr(constants, cls.pool).value_at(bitstream.read(U32)))

    def serialize(self):
        return chr(self.opcode) + u32(self._arg_index)

    def write_to_pool(self, pool):
        self._arg_index = getattr(pool, self.pool).index_for(self.argument)

    def __repr_inner__(self):
        return " arg=%s (%r)" % (self._arg_index, self.argument)

    def __len__(self):
        return len(self.serialize())

class _Avm2MultinameInstruction(_Avm2ShortInstruction):
    no_rt = False

    def __init__(self, multiname):
        self._multiname_index = 0
        self.multiname = IMultiname(multiname)

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

    def __len__(self):
        return len(self.serialize())

class _Avm2JumpInstruction(_Avm2ShortInstruction):
    jumplike = True
    def __init__(self, name):
        self.labelname = name
        self.address = None

    def assembler_pass1(self, asm):
        super(_Avm2JumpInstruction, self).assembler_pass1(asm)
        self.label = asm.make_label(self.labelname)
        asm.jumps.append(self)

    def assembler_pass2(self, asm, address):
        self.address = address

    @classmethod
    def parse_inner(cls, bitstream, abc, constants, asm):
        offset  = bitstream.read(SI24)
        offset += bitstream.tell()//8
        label = make_offset_label(offset, asm)
        return cls(label.name)

    def serialize(self):
        return chr(self.opcode) + "\0\0\0"

    def __repr_inner__(self):
        return" lbl=%r" % (self.labelname,)

    def __len__(self):
        return 4

class _Avm2LookupSwitchInstruction(_Avm2ShortInstruction):
    def assembler_pass1(self, asm):
        super(_Avm2LookupSwitchInstruction, self).assembler_pass1(asm)
        self.default_label =  asm.make_label(self.default_name)
        self.case_labels   = [asm.make_label(name) for name in self.case_names]

    def assembler_pass2(self, asm, address):
        asm.jumps.append(self.default_label)
        asm.jumps.extend(self.case_labels)

    def serialize(self):
        cases = "\0\0\0"*len(self.case_labels)
        return "%c\0\0\0%s%s" % (self.opcode, u32(len(self.case_labels) - 1), cases)

    @classmethod
    def parse_inner(cls, bitstream, abc, constants, asm):
        # default label
        offset  = bitstream.read(SI24)
        offset += bitstream.tell()//8
        lbl = make_offset_label(offset, asm)

        # case label count
        cases, count = [], bitstream.read(U32) + 1

        for i in xrange(count):
            offset  = bitstream.tell()//8 - 1
            offset += bitstream.read(SI24)
            lbl = make_offset_label(offset, asm)
            cases.append(lbl.name)

        return cls(lbl.name, *cases)

    def __init__(self, default, cases):
        self.default_name, self.case_names = default, cases
        self.default_label, self.case_labels = None, None

    def __len__(self):
        return 1 + 3*len(self.case_labels)

class _Avm2LabelInstruction(_Avm2ShortInstruction):
    def __init__(self, name):
        self.backref = False
        self.labelname = name
        self.label = None

    def assembler_pass1(self, asm):
        if self.name in asm.labels:
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
        if self.backref:
            return chr(self.opcode)
        return ""

    @classmethod
    def parse_inner(cls, bitstream, abc, constants, asm):
        lbl = make_offset_label(bitstream.tell()//8-1, asm)
        inst = cls(lbl.name)
        inst.label = lbl
        return inst

    def __repr_inner__(self):
        return " lbl=%r" % (self.labelname,)

    def __len__(self):
        return 1

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
    def __init__(self, multiname, num_args):
        self.multiname, self.num_args = IMultiname(multiname), num_args

    def assembler_pass1(self, asm):
        asm.stack_depth += 1 - (self.num_args + 1) # push object/args; push result

    def write_to_pool(self, pool):
        self._multiname_index = pool.multiname_pool.index_for(self.multiname)

    def serialize(self):
        return chr(self.opcode) + u32(self._multiname_index) + u32(self.num_args)

    @classmethod
    def parse_inner(cls, bitstream, abc, constants, asm):
        return cls(constants.multiname_pool.value_at(bitstream.read(U32)), bitstream.read(U32))

    def __repr_inner__(self):
        return ", multiname=%s, num_args=%s" % (self.multiname, self.num_args)

    def __len__(self):
        return len(self.serialize())

class _Avm2CallMN(_Avm2CallIDX):
    not_void = True
    def stack(self, asm):
        stack = -self.num_args

        if has_RTNS(self.multiname):
            stack -= 1

        if has_RTName(self.multiname):
            stack -= 1

        if self.not_void:
            stack += 1

        return stack

class _Avm2BogusInstruction(_Avm2ShortInstruction):
    opcode = -1
    name = "BOGUS"
    def serialize(self):
        return ""

    def __len__(self):
        return 0

class _Avm2TryInstruction(_Avm2BogusInstruction):
    def __init__(self, context):
        self.context = context

    def assembler_pass2(self, asm, address):
        setattr(self.context, self.attrname, address)

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

# instruction factory
def m(superclass, o, n, x=0, y=0, **kw):
    class inner(superclass):
        opcode = o
        name = n
        stack = x
        scope = y
    for k, v in kw.iteritems():
        setattr(inner, k, v)
    inner.__name__  = n
    INSTRUCTIONS[n] = inner
    INSTRUCTIONS[o] = inner
    return inner

# Instructions that push one value to the stack and take no arguments.
dup = m(_Avm2ShortInstruction, 0x2A, "dup", 1)
getglobalscope = m(_Avm2ShortInstruction, 0x64, "getglobalscope", 1)
getlocal0 = m(_Avm2ShortInstruction, 0xD0, "getlocal0", 1, argument=0)
getlocal1 = m(_Avm2ShortInstruction, 0xD1, 'getlocal1', 1, argument=1)
getlocal2 = m(_Avm2ShortInstruction, 0xD2, 'getlocal2', 1, argument=2)
getlocal3 = m(_Avm2ShortInstruction, 0xD3, 'getlocal3', 1, argument=3)
newactivation = m(_Avm2ShortInstruction, 0x57, 'newactivation', 1,
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
callstatic = m(_Avm2CallIDX, 0x44, 'callstatic', arg_count=2)
callsuper = m(_Avm2CallMN, 0x45, 'callsuper', arg_count=2)
callproperty = m(_Avm2CallMN, 0x46, 'callproperty', arg_count=2)
constructprop = m(_Avm2CallMN, 0x4A, 'constructprop', arg_count=2)
callproplex = m(_Avm2CallMN, 0x4C, 'callproplex', arg_count=2)
callsupervoid = m(_Avm2CallMN, 0x4E, 'callsupervoid', arg_count=2, not_void=False)
callpropvoid  = m(_Avm2CallMN, 0x4F, 'callpropvoid' , arg_count=2, not_void=False)

# Instructions that do not change the stack height stack and take one U30 argument.
astype = m(_Avm2U30Instruction, 0x86, 'astype')
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
getouterscope = m(_Avm2U30Instruction, 0x67, 'getouterscope', 1)
newcatch = m(_Avm2U30Instruction, 0x5A, 'newcatch', 1)
newfunction = m(_Avm2U30Instruction, 0x40, 'newfunction', 1)
pushdouble = m(_Avm2PushPoolInstruction, 0x2F, 'pushdouble', 1, pool="double_pool")
pushint = m(_Avm2PushPoolInstruction, 0x2D, 'pushint', 1, pool="int_pool")
pushnamespace = m(_Avm2PushPoolInstruction, 0x31, 'pushnamespace', 1, pool="namespace_pool")
pushshort = m(_Avm2U30Instruction, 0x25, 'pushshort', 1)
pushstring = m(_Avm2PushPoolInstruction, 0x2C, 'pushstring', 1, pool="utf8_pool")
pushuint = m(_Avm2PushPoolInstruction, 0x2E, 'pushuint', 1, pool="uint_pool")
_getlocal = m(_Avm2U30Instruction, 0x62, 'getlocal', 1)

# Instructions that pop from the stack and take one U30 argument.
_setlocal = m(_Avm2U30Instruction, 0x63, 'setlocal', -1)
setslot = m(_Avm2U30Instruction, 0x6D, 'setslot', -1)

# Instructions that push one value to the stack and take two U30 arguments.
hasnext2 = m(_Avm2U30Instruction, 0x32, 'hasnext2', 1, arg_count=2)

# Instructions that push/pop values to the stack (depends on arg) and take one U30 argument.
newarray  = m(_Avm2U30Instruction, 0x56, 'newarray' , stack=lambda self, asm: 1 - self.argument)
newobject = m(_Avm2U30Instruction, 0x55, 'newobject', stack=lambda self, asm: 1 - self.argument)
applytype = m(_Avm2U30Instruction, 0x53, 'applytype', stack=lambda self, asm: 1 - 2*self.argument)

# Instructions that take one U8 argument.
pushbyte = m(_Avm2PushByte, 0x24, 'pushbyte', 1)
getscopeobject = m(_Avm2GetScopeObject, 0x65, 'getscopeobject', 1)

# Jump instructions
ifeq = m(_Avm2JumpInstruction, 0x13, 'ifeq', -2)
ifge = m(_Avm2JumpInstruction, 0x18, 'ifge', -2)
ifgt = m(_Avm2JumpInstruction, 0x17, 'ifgt', -2)
ifle = m(_Avm2JumpInstruction, 0x16, 'ifle', -2)
iflt = m(_Avm2JumpInstruction, 0x15, 'iflt', -2)
ifne = m(_Avm2JumpInstruction, 0x14, 'ifne', -2)
ifnge = m(_Avm2JumpInstruction, 0x0F, 'ifnge', -2)
ifngt = m(_Avm2JumpInstruction, 0x0E, 'ifngt', -2)
ifnle = m(_Avm2JumpInstruction, 0x0D, 'ifnle', -2)
ifnlt = m(_Avm2JumpInstruction, 0x0C, 'ifnlt', -2)
ifstricteq = m(_Avm2JumpInstruction, 0x19, 'ifstricteq', -2)
ifstrictne = m(_Avm2JumpInstruction, 0x1A, 'ifstrictne', -2)
iffalse = m(_Avm2JumpInstruction, 0x12, 'iffalse', -1)
iftrue = m(_Avm2JumpInstruction, 0x11, 'iftrue', -1)
jump = m(_Avm2JumpInstruction, 0x10, 'jump')

# Special Instructions
debug = m(_Avm2DebugInstruction, 0xEF, 'debug')
label = m(_Avm2LabelInstruction, 0x09, 'label')
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

del m

def setlocal(index, speed=[setlocal0, setlocal1, setlocal2, setlocal3]):
    if 0 <= index < 4:
        return speed[index]()
    return _setlocal(index)

def getlocal(index, speed=[getlocal0, getlocal1, getlocal2, getlocal3]):
    if 0 <= index < 4:
        return speed[index]()
    return _getlocal(index)
