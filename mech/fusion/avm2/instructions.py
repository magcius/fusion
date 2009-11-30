
from mech.fusion.avm2.util import serialize_u32 as u32, Avm2Label
from mech.fusion.avm2.constants import METHODFLAG_Activation, METHODFLAG_SetsDxns, has_RTName, has_RTNS

INSTRUCTIONS = {}

class _Avm2ShortInstruction(object):
    flags = 0
    stack = 0
    scope = 0
    opcode = None
    name = None
    def __repr__(self):
        if self.opcode is None:
            return self.name
        return "%s (%#X)" % (self.name, self.opcode)
      
    def set_assembler_props(self, asm):
        asm.flags |= self.flags
        asm.stack_depth += self.stack
        asm.scope_depth += self.scope

    def serialize(self):
        return chr(self.opcode)

class _Avm2DebugInstruction(_Avm2ShortInstruction):    
    def serialize(self):
        return chr(self.opcode) + \
            chr(self.debug_type & 0xFF) + \
            u32(self.index) + \
            chr(self.reg & 0xFF) + \
            u32(self.extra)
    
    def __init__(self, debug_type, index, reg, extra):
        self.debug_type = debug_type, self.index = index, self.reg=reg, self.extra=extra
    
class _Avm2U8Instruction(_Avm2ShortInstruction):
    def serialize(self):
        return chr(self.opcode) + chr(self.argument)
    
    def __init__(self, argument):
        self.argument = argument
    
class _Avm2U30Instruction(_Avm2ShortInstruction):
    def serialize(self):
        return chr(self.opcode) + ''.join(u32(i) for i in self.arguments)

    def __init__(self, argument, *arguments):
        self.arguments = (argument, ) + arguments
        self.argument = argument

class _Avm2MultinameInstruction(_Avm2U30Instruction):
    no_rt = False
    def set_assembler_props(self, asm):
        super(_Avm2MultinameInstruction, self).set_assembler_props(asm)
        has_rtname, has_rtns = has_RTName(self.multiname), has_RTNS(self.multiname)
        if self.no_rt:
            if has_rtname and has_rtns:
                raise ValueError("%s used with runtime-qualified name: %s" % (self.name, self.multiname))
        self.arguments = [asm.constants.multiname_pool.index_for(self.multiname)]
        
        asm.stack_depth -= int(has_rtns) + int(has_rtname)
        
    def __init__(self, multiname):
        self.multiname = multiname

class _Avm2OffsetInstruction(_Avm2ShortInstruction):
    def __repr__(self):
        return repr(super(_Avm2OffsetInstruction, self))[:-2] + " lbl=%r)>" % self.lbl
    
    def set_assembler_props(self, asm):
        super(_Avm2OffsetInstruction, self).set_assembler_props(asm)
        if self.lblname not in asm.labels:
            asm.labels[self.lblname] = Avm2Label(asm)
            # print "created label", self.lblname, asm.labels[self.lblname].address
        self.asm = asm
        self.lbl = asm.labels[self.lblname]
    
    def serialize(self):
        code = chr(self.opcode)
        code += self.lbl.write_relative_offset(len(self.asm) + 4, len(self.asm) + 1)
        return code
    
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
    define = False
    def set_assembler_props(self, asm):
        super(_Avm2LabelInstruction, self).set_assembler_props(asm)
        if self.lblname in asm.labels:
            lbl = asm.labels[self.lblname]
            assert lbl.address == -1
            asm.stack_depth = lbl.stack_depth
            asm.scope_depth = lbl.scope_depth
        else:
            self.define = True
            lbl = asm.labels[self.lblname] = Avm2Label(asm)
        lbl.address = len(asm)
    
    def serialize(self):
        if self.define:
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
        self.multiname, self.num_args = multiname, num_args

class _Avm2CallMN(_Avm2CallIDX):
    is_void = False
    def set_assembler_props(self, asm):
        super(_Avm2CallMN, self).set_assembler_props(asm)
        has_rtns   = has_RTNS(self.multiname)
        has_rtname = has_RTName(self.multiname)
        asm.stack_depth += int(self.is_void) - (1 + int(has_rtns) + int(has_rtname) + self.num_args)

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

def _make_avm2(class_, opcode, name, stack=0, scope=0, flags=0, no_rt=False):
    o, n, st, sc, f, nr = opcode, name, stack, scope, flags, no_rt
    class inner(class_):
        opcode = o
        name = n
        stack = st
        scope = sc
        flags = f
        no_rt = nr
    inner.__name__ = name
    INSTRUCTIONS[name] = inner
    return inner
    
        
#{ Instructions that push one value to the stack and take no arguments.
dup = _make_avm2(_Avm2ShortInstruction, 0x2A, "dup", 1)
getglobalscope = _make_avm2(_Avm2ShortInstruction, 0x64, "getglobalscope", 1)
getlocal_0 = _make_avm2(_Avm2ShortInstruction, 0xD0, "getlocal_0", 1)
getlocal_1 = _make_avm2(_Avm2ShortInstruction, 0xD1, 'getlocal_1', 1)
getlocal_2 = _make_avm2(_Avm2ShortInstruction, 0xD2, 'getlocal_2', 1)
getlocal_3 = _make_avm2(_Avm2ShortInstruction, 0xD3, 'getlocal_3', 1)
newactivation = _make_avm2(_Avm2ShortInstruction, 0x57, 'newactivation', 1, flags=METHODFLAG_Activation)
pushfalse = _make_avm2(_Avm2ShortInstruction, 0x27, 'pushfalse', 1)
pushnan = _make_avm2(_Avm2ShortInstruction, 0x28, 'pushnan', 1)
pushnull = _make_avm2(_Avm2ShortInstruction, 0x20, 'pushnull', 1)
pushtrue = _make_avm2(_Avm2ShortInstruction, 0x26, 'pushtrue', 1)
pushundefined = _make_avm2(_Avm2ShortInstruction, 0x21, 'pushundefined', 1)
#}

#{ Instructions that pop one value from the stack and take no arguments.
add = _make_avm2(_Avm2ShortInstruction, 0xA0, 'add', -1)
add_i = _make_avm2(_Avm2ShortInstruction, 0xC5, 'add_i', -1)
astypelate = _make_avm2(_Avm2ShortInstruction, 0x87, 'astypelate', -1)
bitand = _make_avm2(_Avm2ShortInstruction, 0xA8, 'bitand', -1)
bitor = _make_avm2(_Avm2ShortInstruction, 0xA9, 'bitor', -1)
bitxor = _make_avm2(_Avm2ShortInstruction, 0xAA, 'bitxor', -1)
divide = _make_avm2(_Avm2ShortInstruction, 0xA3, 'divide', -1)
dxnslate = _make_avm2(_Avm2ShortInstruction, 0x07, 'dxnslate', -1, flags=METHODFLAG_SetsDxns)
equals = _make_avm2(_Avm2ShortInstruction, 0xAB, 'equals', -1)
greaterequals = _make_avm2(_Avm2ShortInstruction, 0xB0, 'greaterequals', -1)
greaterthan = _make_avm2(_Avm2ShortInstruction, 0xAF, 'greaterthan', -1)
hasnext = _make_avm2(_Avm2ShortInstruction, 0x1F, 'hasnext', -1)
if_ = _make_avm2(_Avm2ShortInstruction, 0xB4, 'in', -1)
instanceof = _make_avm2(_Avm2ShortInstruction, 0xB1, 'instanceof', -1)
istypelate = _make_avm2(_Avm2ShortInstruction, 0xB3, 'istypelate', -1)
lessequals = _make_avm2(_Avm2ShortInstruction, 0xAE, 'lessequals', -1)
lessthan = _make_avm2(_Avm2ShortInstruction, 0xAD, 'lessthan', -1)
lshift = _make_avm2(_Avm2ShortInstruction, 0xA5, 'lshift', -1)
modulo = _make_avm2(_Avm2ShortInstruction, 0xA4, 'modulo', -1)
multiply = _make_avm2(_Avm2ShortInstruction, 0xA2, 'multiply', -1)
multiply_i = _make_avm2(_Avm2ShortInstruction, 0xC7, 'multiply_i', -1)
nextname = _make_avm2(_Avm2ShortInstruction, 0x1E, 'nextname', -1)
nextvalue = _make_avm2(_Avm2ShortInstruction, 0x23, 'nextvalue', -1)
pop = _make_avm2(_Avm2ShortInstruction, 0x29, 'pop', -1)
pushscope = _make_avm2(_Avm2ShortInstruction, 0x30, 'pushscope', -1, 1) # Changes scope depth.
pushwith = _make_avm2(_Avm2ShortInstruction, 0x1C, 'pushwith', -1, 1) # Changes scope depth.
returnvalue = _make_avm2(_Avm2ShortInstruction, 0x48, 'returnvalue', -1)
rshift = _make_avm2(_Avm2ShortInstruction, 0xA6, 'rshift', -1)
setlocal_0 = _make_avm2(_Avm2ShortInstruction, 0xD4, 'setlocal_0', -1)
setlocal_1 = _make_avm2(_Avm2ShortInstruction, 0xD5, 'setlocal_1', -1)
setlocal_2 = _make_avm2(_Avm2ShortInstruction, 0xD6, 'setlocal_2', -1)
setlocal_3 = _make_avm2(_Avm2ShortInstruction, 0xD7, 'setlocal_3', -1)
strictequals = _make_avm2(_Avm2ShortInstruction, 0xAC, 'strictequals', -1)
subtract = _make_avm2(_Avm2ShortInstruction, 0xA1, 'subtract', -1)
subtract_i = _make_avm2(_Avm2ShortInstruction, 0xC6, 'subtract_i', -1)
throw = _make_avm2(_Avm2ShortInstruction, 0x03, 'throw', -1)
urshift = _make_avm2(_Avm2ShortInstruction, 0xA7, 'urshift', -1)
#}

#{ Instructions that do not change the stack height and take no arguments.
bitnot = _make_avm2(_Avm2ShortInstruction, 0x97, 'bitnot')
checkfilter = _make_avm2(_Avm2ShortInstruction, 0x78, 'checkfilter')
coerce_a = _make_avm2(_Avm2ShortInstruction, 0x82, 'coerce_a')
coerce_s = _make_avm2(_Avm2ShortInstruction, 0x85, 'coerce_s')
convert_b = _make_avm2(_Avm2ShortInstruction, 0x76, 'convert_b')
convert_d = _make_avm2(_Avm2ShortInstruction, 0x75, 'convert_d')
convert_i = _make_avm2(_Avm2ShortInstruction, 0x73, 'convert_i')
convert_o = _make_avm2(_Avm2ShortInstruction, 0x77, 'convert_o')
convert_s = _make_avm2(_Avm2ShortInstruction, 0x70, 'convert_s')
convert_u = _make_avm2(_Avm2ShortInstruction, 0x74, 'convert_u')
decrement = _make_avm2(_Avm2ShortInstruction, 0x93, 'decrement')
decrement_i = _make_avm2(_Avm2ShortInstruction, 0xC1, 'decrement_i')
esc_xattr = _make_avm2(_Avm2ShortInstruction, 0x72, 'esc_xattr')
esc_xelem = _make_avm2(_Avm2ShortInstruction, 0x71, 'esc_xelem')
increment = _make_avm2(_Avm2ShortInstruction, 0x91, 'increment')
increment_i = _make_avm2(_Avm2ShortInstruction, 0xC0, 'increment_i')
# kill moved down to Special.
negate = _make_avm2(_Avm2ShortInstruction, 0x90, 'negate')
negate_i = _make_avm2(_Avm2ShortInstruction, 0xC4, 'negate_i')
nop = _make_avm2(_Avm2ShortInstruction, 0x02, 'nop')
not_ = _make_avm2(_Avm2ShortInstruction, 0x96, 'not')
popscope = _make_avm2(_Avm2ShortInstruction, 0x1D, 'popscope', 0, -1) # Changes scope depth.
returnvoid = _make_avm2(_Avm2ShortInstruction, 0x47, 'returnvoid')
swap = _make_avm2(_Avm2ShortInstruction, 0x2B, 'swap')
typeof = _make_avm2(_Avm2ShortInstruction, 0x95, 'typeof')
#}

#{ Call Instructions
call = _make_avm2(_Avm2Call, 0x41, 'call')
construct = _make_avm2(_Avm2Construct, 0x42, 'construct')
constructsuper = _make_avm2(_Avm2ConstructSuper, 0x49, 'constructsuper')

callmethod = _make_avm2(_Avm2CallIDX, 0x43, 'callmethod')
callstatic = _make_avm2(_Avm2CallIDX, 0x43, 'callstatic')

callsuper = _make_avm2(_Avm2CallMN, 0x45, 'callsuper')
callproperty = _make_avm2(_Avm2CallMN, 0x46, 'callproperty')
constructprop = _make_avm2(_Avm2CallMN, 0x4A, 'constructprop')
callproplex = _make_avm2(_Avm2CallMN, 0x4C, 'callproplex')
callsupervoid = _make_avm2(_Avm2CallMNVoid, 0x4E, 'callsupervoid')
callpropvoid = _make_avm2(_Avm2CallMNVoid, 0x4F, 'callpropvoid')
#}

#{ Instructions that do not chage the stack height stack and take one U30 argument.
astype = _make_avm2(_Avm2U30Instruction, 0x86, 'astype')
# coerce moved to special.
debugfile = _make_avm2(_Avm2U30Instruction, 0xF1, 'debugfile')
debugline = _make_avm2(_Avm2U30Instruction, 0xF0, 'debugline')
declocal = _make_avm2(_Avm2U30Instruction, 0x94, 'declocal')
declocal_i = _make_avm2(_Avm2U30Instruction, 0xC3, 'declocal_i')
dxns = _make_avm2(_Avm2U30Instruction, 0x06, 'dxns', flags=METHODFLAG_SetsDxns)
getslot = _make_avm2(_Avm2U30Instruction, 0x6C, 'getslot')
inclocal = _make_avm2(_Avm2U30Instruction, 0x92, 'inclocal')
inclocal_i = _make_avm2(_Avm2U30Instruction, 0xC2, 'inclocal_i')
istype = _make_avm2(_Avm2U30Instruction, 0xB2, 'istype')
kill = _make_avm2(_Avm2U30Instruction, 0x08, 'kill')
newclass = _make_avm2(_Avm2U30Instruction, 0x58, 'newclass')
#}

#{ Instructions that push to the stack and take one U30 argument.
getglobalslot = _make_avm2(_Avm2U30Instruction, 0x6E, 'getglobalslot', 1)
getscopeobject = _make_avm2(_Avm2U30Instruction, 0x65, 'getscopeobject', 1)
getouterscope = _make_avm2(_Avm2U30Instruction, 0x67, 'getouterscope', 1)
# getproperty moved down to special.
newcatch = _make_avm2(_Avm2U30Instruction, 0x5A, 'newcatch', 1)
newfunction = _make_avm2(_Avm2U30Instruction, 0x40, 'newfunction', 1)
pushdouble = _make_avm2(_Avm2U30Instruction, 0x2F, 'pushdouble', 1)
pushint = _make_avm2(_Avm2U30Instruction, 0x2D, 'pushint', 1)
pushnamespace = _make_avm2(_Avm2U30Instruction, 0x31, 'pushnamespace', 1)
pushshort = _make_avm2(_Avm2U30Instruction, 0x25, 'pushshort', 1)
pushstring = _make_avm2(_Avm2U30Instruction, 0x2C, 'pushstring', 1)
pushuint = _make_avm2(_Avm2U30Instruction, 0x2E, 'pushuint', 1)

_getlocal = _make_avm2(_Avm2U30Instruction, 0x62, 'getlocal')
#}

#{ Instructions that pop from the stack and take one U30 argument.
_setlocal = _make_avm2(_Avm2U30Instruction, 0x63, 'setlocal')
setslot = _make_avm2(_Avm2U30Instruction, 0x6D, 'setslot', -1)
#}

#{ Instructions that push one value to the stack and take two U30 arguments.
hasnext2 = _make_avm2(_Avm2U30Instruction, 0x32, 'hasnext2', 1)
#}

#{ Instructions that push/pop values to the stack (depends on arg) and take one U30 argument.
newarray = _make_avm2(_Avm2NewArray, 0x56, 'newarray')
newobject = _make_avm2(_Avm2NewObject, 0x55, 'newobject')
applytype = _make_avm2(_Avm2ApplyType, 0x53, 'applytype')
#}

#{ Instructions that take one U8 argument.
pushbyte = _make_avm2(_Avm2U8Instruction, 0x24, 'pushbyte', 1)
#}

#{ Offset instructions
ifeq = _make_avm2(_Avm2OffsetInstruction, 0x13, 'ifeq', -2)
ifge = _make_avm2(_Avm2OffsetInstruction, 0x18, 'ifge', -2)
ifgt = _make_avm2(_Avm2OffsetInstruction, 0x17, 'ifgt', -2)
ifle = _make_avm2(_Avm2OffsetInstruction, 0x16, 'ifle', -2)
iflt = _make_avm2(_Avm2OffsetInstruction, 0x15, 'iflt', -2)
ifne = _make_avm2(_Avm2OffsetInstruction, 0x14, 'ifne', -2)
ifnge = _make_avm2(_Avm2OffsetInstruction, 0x0F, 'ifnge', -2)
ifngt = _make_avm2(_Avm2OffsetInstruction, 0x0E, 'ifngt', -2)
ifnle = _make_avm2(_Avm2OffsetInstruction, 0x0D, 'ifnle', -2)
ifnlt = _make_avm2(_Avm2OffsetInstruction, 0x0C, 'ifnlt', -2)

ifstricteq = _make_avm2(_Avm2OffsetInstruction, 0x19, 'ifstricteq', -2)
ifstrictne = _make_avm2(_Avm2OffsetInstruction, 0x1A, 'ifstrictne', -2)

iffalse = _make_avm2(_Avm2OffsetInstruction, 0x12, 'iffalse', -1)
iftrue = _make_avm2(_Avm2OffsetInstruction, 0x11, 'iftrue', -1)

jump = _make_avm2(_Avm2OffsetInstruction, 0x10, 'jump')
#}

#{ Special Instructions
debug = _make_avm2(_Avm2DebugInstruction, 0xEF, 'debug')

label_internal = _make_avm2(_Avm2ShortInstruction, 0x09, 'label_interal')
label = _make_avm2(_Avm2LabelInstruction, None, 'label')

lookupswitch = _make_avm2(_Avm2LookupSwitchInstruction, 0x1B, 'lookupswitch')

coerce = _make_avm2(_Avm2MultinameInstruction, 0x80, 'coerce', 0, no_rt=True)
getlex = _make_avm2(_Avm2MultinameInstruction, 0x60, 'getlex', 1, no_rt=True)
deleteproperty = _make_avm2(_Avm2MultinameInstruction, 0x6A, 'deleteproperty', 0)
getdescendants = _make_avm2(_Avm2MultinameInstruction, 0x59, 'getdescendants', 0)
getproperty = _make_avm2(_Avm2MultinameInstruction, 0x66, 'getproperty', 0)
getsuper = _make_avm2(_Avm2MultinameInstruction, 0x04, 'getsuper', 0)
findproperty = _make_avm2(_Avm2MultinameInstruction, 0x5E, 'findproperty', 1)
findpropstrict = _make_avm2(_Avm2MultinameInstruction, 0x5D, 'findpropstrict', 1)
initproperty = _make_avm2(_Avm2MultinameInstruction, 0x68, 'initproperty', -2)
setproperty = _make_avm2(_Avm2MultinameInstruction, 0x61, 'setproperty', -2)
setsuper = _make_avm2(_Avm2MultinameInstruction, 0x05, 'setsuper', -2)
#}

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
    
