
from mech.fusion.bitstream.flash_formats import UI8, UI24, U32
from mech.fusion.avm2.util import serialize_u32 as u32, Avm2Label
from mech.fusion.avm2.constants import METHODFLAG_Activation, \
    METHODFLAG_SetsDxns, has_RTName, has_RTNS

INSTRUCTIONS = {}

def parse_instruction(bitstream, abc, constants, asm):
    cls = INSTRUCTIONS[bitstream.read(UI8)]
    return cls.parse_inner(bitstream, abc, constants, asm)

class _Avm2ShortInstruction(object):
    flags = 0
    stack = 0
    scope = 0
    opcode = None
    name = None
    
    def __repr__(self):
        if self.opcode is None:
            return self.name
        return "%s (%#X%s)" % (self.name, self.opcode, self.__repr_inner__())

    def __repr_inner__(self):
        return ""
      
    def set_assembler_props(self, asm):
        asm.flags |= self.flags
        asm.stack_depth += self.stack
        asm.scope_depth += self.scope

    def set_assembler_props_late(self, asm, address):
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
        return " arg=%d" % (self.argument,)
    
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
        return " arg=" + ' '.join("%#X" % (a,) for a in self.arguments)
    
    @classmethod
    def parse_inner(cls, bitstream, abc, constants, asm):
        return cls(*(bitstream.read(U32) for i in xrange(cls.arg_count)))
    
    def serialize(self):
        if self.arg_count != len(self.arguments):
            raise ValueError("This opcode takes %d argument(s). "
                             "This instance has %d argument(s)." % \
                             (self.arg_count, len(self.arguments)))
        return chr(self.opcode) + ''.join(u32(i) for i in self.arguments)
    
    def __init__(self, argument, *arguments):
        self.arguments = (argument, ) + arguments
        self.argument = argument

class _Avm2MultinameInstruction(_Avm2U30Instruction):
    no_rt = False
    def set_assembler_props(self, asm):
        super(_Avm2MultinameInstruction, self).set_assembler_props(asm)
        has_rtname = has_RTName(self.multiname)
        has_rtns   = has_RTNS  (self.multiname)
        if self.no_rt:
            if has_rtname and has_rtns:
                raise ValueError("%s used with runtime-qualified name: %s" % \
                                 (self.name, self.multiname))
        
        self.arguments = [asm.constants.multiname_pool.index_for(self.multiname)]
        asm.stack_depth -= int(has_rtns) + int(has_rtname)

    @classmethod
    def parse_inner(cls, bitstream, abc, constants, asm):
        return cls(abc.multinames.value_at(bitstream.read(U32)))
    
    def __init__(self, multiname):
        self.multiname = multiname.multiname()

class _Avm2OffsetInstruction(_Avm2ShortInstruction):
    def __repr_inner__(self):
        return" lbl=%r" % self.lbl
    
    def set_assembler_props(self, asm):
        super(_Avm2OffsetInstruction, self).set_assembler_props(asm)
        if self.lblname in asm.labels:
            asm.labels[self.lblname].backref = True
        else:
            lbl = asm.labels[self.lblname] = Avm2Label(asm)
        self.asm = asm
        self.lbl = asm.labels[self.lblname]

    def set_assembler_props_late(self, asm, address):
        asm.offsets.append(self)
        self.address = address
    
    @classmethod
    def parse_inner(cls, bitstream, abc, constants, asm):
        relative_offset = bitstream.read(UI24)
        offset = len(asm)+4+relative_offset
        inst = cls("_lbl_%d" % (offset,))
        if relative_offset not in asm.labels: # Forward reference.
            asm.labels[offset] = self
    
    def serialize(self):
        return chr(self.opcode) + "\0\0\0"
    
    def __init__(self, name):
        self.lblname = name

class _Avm2LookupSwitchInstruction(_Avm2ShortInstruction):
    def set_assembler_props(self, asm):
        super(_Avm2LookupSwitchInstruction, self).set_assembler_props(asm)
        self.asm = asm
        if self.default_label is None:
            self.default_label = Avm2Label(asm)
        if isinstance(self.case_labels, int):
            self.case_labels = [Avm2Label(asm) for i in xrange(self.case_labels)]
    
    def serialize(self):
        code = chr(self.opcode)
        base = len(self.asm)
        code += self.default_label.write_relative_offset(base, base+1)
        code += u32(len(self.case_labels) - 1)
        
        for lbl in self.case_labels:
            location = base + len(code)
            code += lbl.write_relative_offset(base, location)
        return code
        
    def __init__(self, default_label=None, case_labels=None):
        self.default_label = default_label, self.case_labels = case_labels

class _Avm2LabelInstruction(_Avm2ShortInstruction):
    def set_assembler_props(self, asm):
        super(_Avm2LabelInstruction, self).set_assembler_props(asm)
        if self.lblname in asm.labels:
            lbl = asm.labels[self.lblname]
            assert lbl.address == -1
            asm.stack_depth = lbl.stack_depth
            asm.scope_depth = lbl.scope_depth
        else:
            lbl = asm.labels[self.lblname] = Avm2Label(asm)
        self.lbl = lbl

    def set_assembler_props_late(self, asm, address):
        self.lbl.address = address
    
    def serialize(self):
        if self.lbl.backref:
            return label_internal.serialize()
        return ""
    
    def __init__(self, name):
        self.lblname = name

class _Avm2Call(_Avm2U30Instruction):
    def set_assembler_props(self, asm):
        asm.stack_depth += 1 - (self.argument + 2) # push function/receiver/args; push result

class _Avm2Construct(_Avm2U30Instruction):
    def set_assembler_props(self, asm):
        asm.stack_depth += 1 - (self.argument + 1) # push object/args; push result

class _Avm2ConstructSuper(_Avm2U30Instruction):
    def set_assembler_props(self, asm):
        asm.stack_depth += self.argument + 1 # pop receiver/args

class _Avm2CallIDX(_Avm2U30Instruction):
    def set_assembler_props(self, asm):
        self.index = asm.constants.multiname_pool.index_for(self.multiname)
        self.arguments = [self.index, self.num_args]
        asm.stack_depth += 1 - (self.num_args + 1) # push object/args; push result
        
    def __init__(self, multiname, num_args):
        self.multiname, self.num_args = multiname.multiname(), num_args

class _Avm2CallMN(_Avm2CallIDX):
    is_void = False
    def set_assembler_props(self, asm):
        super(_Avm2CallMN, self).set_assembler_props(asm)
        has_rtns   = has_RTNS(self.multiname)
        has_rtname = has_RTName(self.multiname)
        asm.stack_depth += int(self.is_void) - \
            (1 + int(has_rtns) + int(has_rtname) + self.num_args)

class _Avm2CallMNVoid(_Avm2CallMN):
    is_void = True

class _Avm2ApplyType(_Avm2U30Instruction):
    def set_assembler_props(self, asm):
        asm.stack_depth += 1 - self.argument

class _Avm2NewArray(_Avm2U30Instruction):
    def set_assembler_props(self, asm):
        asm.stack_depth += 1 - self.argument

class _Avm2NewObject(_Avm2U30Instruction):
    def set_assembler_props(self, asm):
        asm.stack_depth += 1 - (2 * self.argument)

def _make_avm2(class_, opcode, name, stack=0, scope=0, flags=0, no_rt=False, num_args=1):
    o, n, st, sc, f, nr, na = opcode, name, stack, scope, flags, no_rt, num_args
    class inner(class_):
        opcode = o
        name = n
        stack = st
        scope = sc
        flags = f
        no_rt = nr
        arg_count = na
    inner.__name__ = name
    INSTRUCTIONS[name] = inner
    return inner

m = _make_avm2
del _make_avm2
        
# Instructions that push one value to the stack and take no arguments.
dup = m(_Avm2ShortInstruction, 0x2A, "dup", 1)
getglobalscope = m(_Avm2ShortInstruction, 0x64, "getglobalscope", 1)
getlocal_0 = m(_Avm2ShortInstruction, 0xD0, "getlocal_0", 1)
getlocal_1 = m(_Avm2ShortInstruction, 0xD1, 'getlocal_1', 1)
getlocal_2 = m(_Avm2ShortInstruction, 0xD2, 'getlocal_2', 1)
getlocal_3 = m(_Avm2ShortInstruction, 0xD3, 'getlocal_3', 1)
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
setlocal_0 = m(_Avm2ShortInstruction, 0xD4, 'setlocal_0', -1)
setlocal_1 = m(_Avm2ShortInstruction, 0xD5, 'setlocal_1', -1)
setlocal_2 = m(_Avm2ShortInstruction, 0xD6, 'setlocal_2', -1)
setlocal_3 = m(_Avm2ShortInstruction, 0xD7, 'setlocal_3', -1)
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
callmethod = m(_Avm2CallIDX, 0x43, 'callmethod', num_args=2)
callstatic = m(_Avm2CallIDX, 0x43, 'callstatic', num_args=2)
callsuper = m(_Avm2CallMN, 0x45, 'callsuper', num_args=2)
callproperty = m(_Avm2CallMN, 0x46, 'callproperty', num_args=2)
constructprop = m(_Avm2CallMN, 0x4A, 'constructprop', num_args=2)
callproplex = m(_Avm2CallMN, 0x4C, 'callproplex', num_args=2)
callsupervoid = m(_Avm2CallMNVoid, 0x4E, 'callsupervoid', num_args=2)
callpropvoid = m(_Avm2CallMNVoid, 0x4F, 'callpropvoid', num_args=2)

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
pushdouble = m(_Avm2U30Instruction, 0x2F, 'pushdouble', 1)
pushint = m(_Avm2U30Instruction, 0x2D, 'pushint', 1)
pushnamespace = m(_Avm2U30Instruction, 0x31, 'pushnamespace', 1)
pushshort = m(_Avm2U30Instruction, 0x25, 'pushshort', 1)
pushstring = m(_Avm2U30Instruction, 0x2C, 'pushstring', 1)
pushuint = m(_Avm2U30Instruction, 0x2E, 'pushuint', 1)
_getlocal = m(_Avm2U30Instruction, 0x62, 'getlocal')

# Instructions that pop from the stack and take one U30 argument.
_setlocal = m(_Avm2U30Instruction, 0x63, 'setlocal')
setslot = m(_Avm2U30Instruction, 0x6D, 'setslot', -1)

# Instructions that push one value to the stack and take two U30 arguments.
hasnext2 = m(_Avm2U30Instruction, 0x32, 'hasnext2', 1, num_args=2)

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
label_internal = m(_Avm2ShortInstruction, 0x09, 'label_interal')()
label = m(_Avm2LabelInstruction, None, 'label')
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

def setlocal(index):
    _speed = {0: setlocal_0, 1: setlocal_1, 2: setlocal_2, 3: setlocal_3}
    if index in _speed:
        return _speed[index]()
    return _setlocal(index)

def getlocal(index):
    _speed = {0: getlocal_0, 1: getlocal_1, 2: getlocal_2, 3: getlocal_3}
    if index in _speed:
        return _speed[index]()
    return _getlocal(index)
    
del m
