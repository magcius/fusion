
"""
This module implements serializers for the DoAction tags,
otherwise known as "AVM1 Actions"

.. seealso:

   `SWF Specification v10 <http://www.adobe.com/devnet/swf/>`_
      Adobe's specifications for the SWF file format.
"""

# AVM1 = ActionScript Virtual Machine 1
# Used for ActionScript 1 and 2

import os
import struct

from mech.fusion.avm1 import types_ as types
from mech.fusion.util import BitStream, camel_case_convert

preload = dict(this="preload_this",
               arguments="preload_args",
               super="preload_super",
               _root="preload_root",
               _parent="preload_parent",
               _global="preload_global")

class ActionMeta(type):
    def __init__(cls, name, bases, dct):
        if name != 'Action' and 'ACTION_ID' in dct:
            Action.REVERSE_INDEX[dct['ACTION_ID']] = cls

class Action(object):
    
    """
    The base Action class.
    """

    __metaclass__ = ActionMeta
    
    ACTION_NAME = "NotImplemented"
    ACTION_ID = 0x00

    REVERSE_INDEX = {}
    
    offset = 0
    label_name = ""
    
    def serialize(self):
        inner_data = self.gen_data()
        outer_data = self.gen_outer_data()
        header = struct.pack("<BH", self.ACTION_ID, len(inner_data))
        return header + inner_data + outer_data

    @classmethod
    def parse(cls, bits):
        header = bits.read_bits(24)
        actnid = header.read_int_value(8)
        actcls = cls.REVERSE_INDEX[actnid]
        if actnid < 0x70:
            # Ignore this, it doesn't matter.
            length = header.read_int_value(16, endianness="<")
            action = actcls.parse_data(bits, length)
        return action, length

    @classmethod
    def parse_data(cls, bits, length):
        pass
    
    def __len__(self):
        return 6 + len(self.gen_data()) + len(self.gen_outer_data())
    
    def gen_data(self):
        """
        Overridden in Action subclasses.

        Return data counted by the tag length.
        
        :rtype: bytestring
        """
        return ""

    def gen_outer_data(self):
        """
        Overridden in Action subclasses.

        Return data not counted by the tag length.

        :rtype: bytestring
        """
        return ""
    
    def get_block_props_early(self, block):
        pass

    def get_block_props_late(self, block):
        pass

class RegisterError(IndexError):
    pass

class SealedBlockError(Exception):
    pass

class ActionConstantPool(Action):
    ACTION_NAME = "ActionConstantPool"
    ACTION_ID = 0x88

    def __init__(self, *constants):
        self.pool = []
        for string in constants:
            if not string in self.pool:
                self.pool.append(string)

    def add_constant(self, string):
        if not string in self.pool:
            self.pool.append(string)
            return len(self.pool)-1
        return self.pool.index(string)

    def serialize(self):
        if len(self.pool) == 0:
            return ""
        else:
            return super(ActionConstantPool, self).serialize()

    @classmethod
    def parse(cls, bits, length):
        pool = []
        while bits.bits_available() > 0:
            pool.append(bits.read_cstring())
        return cls(*pool)
    
    def gen_data(self):
        return struct.pack("H", len(self.pool)) + "\0".join(self.pool) + "\0"

class Block(object):

    AUTO_LABEL_TEMPLATE = "label%d"
    MAX_REGISTERS = 4
    FUNCTION_TYPE = 0
    
    def __init__(self, toplevel=None, insert_end=False):
        if toplevel:
            self.constants = toplevel.constants
            self.registers = toplevel.registers
        else:
            self.constants = ActionConstantPool()
            self.registers = []
        
        self.code = ""
        self._sealed = False
        self.insert_end = insert_end
        
        self.labels = {}
        self.branch_blocks = []
        self.actions = []
        
        self.current_offset = 0
        self.label_count = 0
    
    def get_free_register(self):
        if None in self.registers:
            return self.registers.index(None)
        elif len(self.registers) < self.MAX_REGISTERS:
            self.registers.append(None)
            return len(self.registers)-1
        else:
            raise RegisterError("maximum number of registers in use")

    def store_register(self, value, index=-1):
        if value in self.registers:
            index = self.registers.index(value)
            return index
        if index < 1:
            index = self.get_free_register()
        self.registers[index] = value
        return index
    
    def find_register(self, value):
        if value in self.registers:
            return self.registers.index(value)
        return -1
    
    def free_register(self, index):
        self.registers[index] = None
    
    def __len__(self):
        return self.current_offset + (2 if self.insert_end else 0)

    def seal(self):
        self._sealed = True
        return len(self)

    @property
    def sealed(self):
        return self._sealed
    
    def add_action(self, action):
        if self._sealed:
            raise SealedBlockError("Block is sealed. Cannot add new actions")

        assert isinstance(action, Action)
        
        self.code = "" # Dirty the code.
        action.offset = self.current_offset
        action.get_block_props_early(self)
        
        # Do some early optimizations. Combine two pushes into one.
        if len(self.actions) > 0 and action.ACTION_NAME == "ActionPush" and self.actions[-1].ACTION_NAME == "ActionPush":
            old_action = self.actions[-1]
            old_len = len(old_action)
            self.actions[-1].values.extend(action.values)
            self.current_offset += len(old_action) - old_len
            return old_action

        # Two nots negate. Take them out.
        if len(self.actions) > 0 and action.ACTION_NAME == "ActionNot" and self.actions[-1].ACTION_NAME == "ActionNot":
            self.actions.pop()
            self.current_offset -= 1 # len(ShortAction) is 1
            return None
            
        if not isinstance(action, Block): # Don't add block length until we've finalized.
            self.current_offset += len(action)
        
        self.actions.append(action)
        return action
    
    def serialize(self):
        if not self._sealed:
            raise SealedBlockError("Block must be sealed before it can be serialized")
        
        if len(self.code) > 0:
            return self.code
        
        bytes = []
        block_offset = 0
        for action in self.actions:
            if isinstance(action, Block):
                block_offset += len(action)
            action.offset += block_offset
            action.get_block_props_late(self)
            bytes += action.serialize()
        if self.insert_end:
            bytes += "\0"
        self.code = "".join(bytes)
        return self.code
    
    def new_label(self):
        self.label_count += 1
        name = Block.AUTO_LABEL_TEMPLATE % self.label_count
        self.labels[name] = -1
        return name
        
    def set_label_here(self, name):
        self.labels[name] = self.current_offset

    def new_label_here(self):
        name = self.new_label()
        self.labels[name] = self.current_offset
        return name

class ActionCall(Action):
    ACTION_NAME = "ActionCall"
    ACTION_ID = 0x9e

class ActionDefineFunction(Action, Block):
    ACTION_NAME = "ActionDefineFunction"
    ACTION_ID = 0x9b
    FUNCTION_TYPE = 1

    def __init__(self, toplevel=None, name="", parameters=None):
        Block.__init__(self, toplevel, False)
        self.function_name = name
        self.params = parameters or []

    def gen_data(self):
        self.block_data = Block.serialize(self)
        bytes = [self.function_name, "\0", struct.pack("<H", len(self.params))]
        bytes += [p + "\0" for p in self.params]
        bytes += struct.pack("<H", len(self.block_data))
        return "".join(bytes)

    def gen_outer_data(self):
        return self.block_data

    @classmethod
    def parse(cls, bits, length):
        actn = cls()
        actn.function_name = bits.read_cstring()
        paramlen = bits.read_bit_value(16, endianness="<")
        for i in xrange(paramlen):
            actn.params.append(bits.read_cstring())
        blocklen = bits.read_bit_value(16, endianness="<")
        while blocklen > 0:
            action, length = Action.parse(bits)
            actn.actions.append(action)
            blocklen -= length
            
        return actn

class ActionDefineFunction2(Action, Block):
    ACTION_NAME = "ActionDefineFunction2"
    ACTION_ID = 0x8e
    MAX_REGISTERS = 256
    FUNCTION_TYPE = 2

    def __init__(self, toplevel=None, name="", parameters=None):
        Block.__init__(self, toplevel, False)
        self.function_name = name
        self.params = parameters or []
        self.preload_register_count = 1 # Start at 1.
        
        # Flags
        self.registers        = [None]
        self.preload_parent   = False
        self.preload_root     = False
        self.suppress_super   = True
        self.preload_super    = False
        self.suppress_args    = True
        self.preload_args     = False
        self.suppress_this    = True
        self.preload_this     = False
        self.preload_global   = False
        self.eval_flags()

        for name in parameters:
            self.registers.append(name)
        
    def eval_flags(self):
        
        # According to the docs, this is the order of register allocation.
        i = 0
        if self.preload_this and "this" not in self.registers:
            self.suppress_this = False
            self.registers.insert(i, "this")
            i += 1
            
        if self.preload_args and "arguments" not in self.registers:
            self.suppress_args = False
            self.registers.insert(i, "arguments")
            i += 1
            
        if self.preload_super and "super" not in self.registers:
            self.suppress_super = False
            self.registers.insert(i, "super")
            i += 1
            
        if self.preload_root and "_root" not in self.registers:
            self.registers.insert(i, "_root")
            i += 1
            
        if self.preload_parent and "_parent" not in self.registers:
            self.registers.insert(i, "_parent")
            i += 1
        
        if self.preload_global and "_global" not in self.registers:
            self.registers.insert(i, "_global")
            i += 1
        
    def gen_data(self):
        bits = BitStream()
        bits.write_bit(self.preload_parent)
        bits.write_bit(self.preload_root)
        bits.write_bit(self.suppress_super)
        bits.write_bit(self.preload_super)
        bits.write_bit(self.suppress_args)
        bits.write_bit(self.preload_args)
        bits.write_bit(self.suppress_this)
        bits.write_bit(self.preload_this)
        bits.zero_fill(7) # skip over 7 Reserved bits
        bits.write_bit(self.preload_global)
        
        self.block_data = Block.serialize(self)
        bits.write_cstring(self.function_name)
        bits.write_int_value(len(self.params), 16, endianness="<")
        bits.write_int_value(len(self.registers), 8)
        
        for name in self.params:
            bits.write_int_value(chr(self.registers.index(name)), 8)
            bits.write_cstring(name)
        
        bits.write_int_value(len(self.block_data), 16, endianness="<")
        return bits.serialize()

    def gen_outer_data(self):
        return self.block_data

    @classmethod
    def parse_data(cls, bits, length):
        actn = cls()
        actn.preload_parent = bits.read_bit()
        actn.preload_root   = bits.read_bit()
        actn.suppress_super = bits.read_bit()
        actn.preload_super  = bits.read_bit()
        actn.suppress_args  = bits.read_bit()
        actn.preload_args   = bits.read_bit()
        actn.suppress_this  = bits.read_bit()
        bits.seek(os.SEEK_CUR)
        actn.preload_global = bits.read_bit()
        actn.eval_flags()
        
        actn.function_name = bits.read_cstring()
        paramlen = bits.read_int_value(16, endianness="<")
        registerlen = bits.read_int_value(8)
        
        for i in xrange(paramlen):
            register_num = bits.read_int_value(8)
            actn.params.append(bits.read_cstring())
        
        blocklen = bits.read_bit_value(16, endianness="<")
        while blocklen > 0:
            action, length = Action.parse(bits)
            actn.actions.append(action)
            blocklen -= length

        return actn

class ActionGetURL(Action):
    ACTION_NAME = "ActionGetURL"
    ACTION_ID = 0x83

    def __init__(self, url="", target=""):
        self.url = url
        self.target = target

    def gen_data(self):
        return "%s\0%s\0" % (self.url, self.target)

    @classmethod
    def parse_data(cls, bits, length):
        url = bits.read_cstring()
        target = bits.read_cstring()
        return cls(url, target)

class ActionGetURL2(Action):
    ACTION_NAME = "ActionGetURL2"
    ACTION_ID = 0x9a

    METHODS = {"": 0, "GET": 1, "POST": 2}
    METHODR = {0: "", 1: "GET", 2: "POST"}

    def __init__(self, method="", load_target=False, load_variables=False):
        self.method = method
        self.load_target = load_target
        self.load_variables = load_variables

    def gen_data(self):
        # The SWF 10 spec document is incorrect.
        # method goes at the low end
        # and the flags at the high end
        bits = BitStream()
        bits.write_bit(self.load_variables)
        bits.write_bit(self.load_target)
        bits.zero_fill(4)
        bits.write_int_value(self.METHODS[self.method.upper()], 2)
        return bits.serialize()

    @classmethod
    def parse_data(cls, bits, length):
        actn = cls("")
        actn.load_variables = bits.read_bit()
        actn.load_target    = bits.read_bit()
        bits.seek(4, os.SEEK_CUR)
        actn.method = cls.METHODR[bits.read_int_value(2)]
        return actn

class ActionGotoFrame(Action):
    ACTION_NAME = "ActionGotoFrame"
    ACTION_ID = 0x81

    def __init__(self, index):
        self.index = index

    def gen_data(self):
        return struct.pack("<H", self.index)

    @classmethod
    def parse_data(cls, bits, length):
        return cls(bits.read_int_value(16, endianness="<"))

class ActionGotoFrame2(Action):
    ACTION_NAME = "ActionGotoFrame2"
    ACTION_ID = 0x9f

    def __init__(self, play=False, scene_bias=0):
        self.play = play
        self.scene_bias = scene_bias

    def gen_data(self):
        bits = BitStream()
        bits.zero_fill(6)
        bits.write_bit(self.scene_bias > 0)
        bits.write_bit(self.play)

        if self.scene_bias > 0:
            return bits.serialize() + struct.pack("<H", self.scene_bias)

        return bits.serialize()

    @classmethod
    def parse_data(cls, bits, length):
        bits.seek(6, os.SEEK_CUR)
        has_scene_bias = bits.read_bit()
        play = bits.read_bit()

        if has_scene_bias:
            scene_bias = bits.read_int_value(16, endianness="<")
        return cls(play, scene_bias)

class ActionGotoLabel(Action):
    ACTION_NAME = "ActionGotoLabel"
    ACTION_ID = 0x81

    def __init__(self, label_name):
        self.label_name = label_name

    def serialize(self):
        return self.label_name + "\0"

    @classmethod
    def parse_data(cls, bits, length):
        return cls(bits.read_cstring())

class BranchingActionBase(Action):

    def __init__(self, branch=None):
        if isinstance(branch, str):
            self.branch_label = branch
            self.branch_offset = 0
        else:
            self.branch_label = None
            self.branch_offset = branch

    def get_block_props_late(self, block):
        if self.branch_label is not None:
            # print "BRANCH:", self.branch_label, block.labels[self.branch_label], self.offset
            self.branch_offset = block.labels[self.branch_label] - self.offset - len(self)

    def gen_data(self):
        return struct.pack("<h", self.branch_offset)

    @classmethod
    def parse_data(cls, bits, lengthj):
        return cls(bits.read_int_value(16, signed=True, endianness="<"))

class ActionJump(BranchingActionBase):
    ACTION_NAME = "ActionJump"
    ACTION_ID = 0x99

class ActionIf(BranchingActionBase):
    ACTION_NAME = "ActionIf"
    ACTION_ID = 0x9d

class ActionPush(Action):
    ACTION_NAME = "ActionPush"
    ACTION_ID = 0x96

    USE_CONSTANTS = False
    
    def __init__(self, *args):
        self.values = []
        self.add_elements(args)

    def add_elements(self, iterable):
        for t in iterable:
            self.add_element(t)
    
    def add_element(self, element):
        if element in (types.NULL, types.UNDEFINED):
            element = (None, element)
        assert isinstance(element, tuple)
        self.values.append(element)
        
    def get_block_props_early(self, block):
        if not ActionPush.USE_CONSTANTS: return
        for index, (value, type) in enumerate(self.values):
            if type == types.STRING:
                constant_index = block.constants.add_constant(value)
                self.values[index] = (constant_index, types.CONSTANT8 if constant_index < 256 else types.CONSTANT16)
    
    def gen_data(self):
        bytes = []
        for value, type in self.values:
            bytes += chr(type.id)
            if type.size == "Z":
                bytes += [value, "\0"]
            elif type.size != "!":
                bytes += struct.pack("<"+type.size, value)
        return "".join(bytes)

    @classmethod
    def parse_data(cls, bits, length):
        bytesread = 0
        values = []
        while bytesread < length:
            Type = types.DataType.REVERSE_INDEX[bits.read_int_value(8)]
            bytesread += 1
            value = None
            if type.size == "Z":
                value = bits.read_cstring()
                bytesread += len(value)
            elif type.size != "!":
                value = struct.unpack("<"+type.size, bits.read_string(struct.calcsize(type.size)))
            values.append((type, value))
        return cls(*values)

class ActionSetTarget(Action):
    ACTION_NAME = "ActionSetTarget"
    ACTION_ID = 0x8b

    def __init__(self, target):
        self.target = target

    def gen_data(self):
        return self.target + "\0"

    @classmethod
    def parse_data(cls, bits, length):
        return cls(bits.read_cstring())

class ActionStoreRegister(Action):
    ACTION_NAME = "ActionStoreRegister"
    ACTION_ID = 0x87

    def __init__(self, index):
        self.index = index

    def gen_data(self):
        return chr(self.index)

    @classmethod
    def parse_data(cls, bits, length):
        return cls(bits.read_int_value(8))

class ActionTry(Action):
    ACTION_NAME = "ActionTry"
    ACTION_ID = 0x8f

    def __init__(self, catch_object, try_block=None, catch_block=None, finally_block=None):

        self.catch_object = catch_object
        
        self.try_block = try_block or Block()
        self.catch_block = catch_block or Block()
        self.finally_block = finally_block or Block()

    def gen_data(self):
        has_catch_block = len(self.catch_block.actions) > 0
        bits = BitStream()
        bits.zero_fill(5)
        bits.write_bit(isinstance(self.catch_object, int))
        bits.write_bit(len(self.finally_block.actions) > 0)
        bits.write_bit(has_catch_block)
        bytes = [bits.serialize()]
        bytes += [struct.pack("3H",
                              len(self.try_block) + 5 if has_catch_block else 0,
                              len(self.catch_block),
                              len(self.finally_block))]
        bytes += [self.catch_object, "" if isinstance(self.catch_object, int) else "\0"]
        return bytes

    def gen_outer_data(self):
        bytes = [self.try_block.serialize()]
        if len(self.catch_block.actions) > 0:
            bytes += ActionJump(len(self.catch_block)).serialize()
            bytes += self.catch_block.serialize()
        bytes += self.finally_block.serialize()

class ActionWaitForFrame(Action):
    ACTION_NAME = "ActionWaitForFrame"
    ACTION_ID = 0x8a

    def __init__(self, index, skip_count=0):
        self.index = index
        self.skip_count = skip_count

    def gen_data(self):
        return struct.pack("<HB", self.index, self.skip_count)

    @classmethod
    def parse_data(cls, bits, length):
        return cls(bits.read_int_value(16, endianness="<"), bits.read_int_value(8))
    
class ActionWaitForFrame2(Action):
    ACTION_NAME = "ActionWaitForFrame2"
    ACTION_ID = 0x8d

    def __init__(self, skip_count):
        self.skip_count = skip_count

    def gen_data(self):
        return chr(self.skip_count)

    @classmethod
    def parse_data(cls, bits, length):
        return cls(bits.read_int_value(8))

class ActionWith(Action):
    ACTION_NAME = "ActionWith"
    ACTION_ID = 0x94
    
    def __init__(self, with_block):
        self.block = with_block or Block()
    
    def gen_data(self):
        return struct.pack("<H", len(self.block))

    def gen_outer_data(self):
        return self.block.serialize()

SHORT_ACTIONS = {}

def make_short_action(value, name, push=0):
    
    def len_(self):
        return 1 # 1 (Action ID)
    
    def serialize_(self):
        return chr(self.ACTION_ID)

    class inner(Action):
        ACTION_ID   = value
        ACTION_NAME = name
        push_count  = push
        __len__   = len_
        serialize = serialize_
    
    inner.__name__ = name
    
    SHORT_ACTIONS[name[6:].lower()] = inner
    SHORT_ACTIONS[camel_case_convert(name[6:])] = inner

    return inner

ActionNextFrame           = make_short_action(0x04, "ActionNextFrame")
ActionPreviousFrame       = make_short_action(0x05, "ActionPreviousFrame")
ActionPlay                = make_short_action(0x06, "ActionPlay")
ActionStop                = make_short_action(0x07, "ActionStop")
ActionToggleQuality       = make_short_action(0x08, "ActionToggleQuality")
ActionStopSounds          = make_short_action(0x09, "ActionStopSounds")
ActionAdd                 = make_short_action(0x0a, "ActionAdd", -1)
ActionSubtract            = make_short_action(0x0b, "ActionSubtract", -1)
ActionMultiply            = make_short_action(0x0c, "ActionMultiply", -1)
ActionDivide              = make_short_action(0x0d, "ActionDivide", -1)
ActionEquals              = make_short_action(0x0e, "ActionEquals", -1)
ActionLess                = make_short_action(0x0f, "ActionLess", -1)
ActionAnd                 = make_short_action(0x10, "ActionAnd", -1)
ActionOr                  = make_short_action(0x11, "ActionOr", -1)
ActionNot                 = make_short_action(0x12, "ActionNot")
ActionStringEquals        = make_short_action(0x13, "ActionStringEquals", -1)
ActionStringLength        = make_short_action(0x14, "ActionStringLength")
ActionStringExtract       = make_short_action(0x15, "ActionStringExtract")
ActionPop                 = make_short_action(0x17, "ActionPop", -1)
ActionToInteger           = make_short_action(0x18, "ActionToInteger")
ActionGetVariable         = make_short_action(0x1c, "ActionGetVariable")
ActionSetVariable         = make_short_action(0x1d, "ActionSetVariable", -2)
ActionSetTarget2          = make_short_action(0x20, "ActionSetTarget2")
ActionStringAdd           = make_short_action(0x21, "ActionStringAdd", -1)
ActionGetProperty         = make_short_action(0x22, "ActionGetProperty", -1)
ActionSetProperty         = make_short_action(0x23, "ActionSetProperty", -3)
ActionCloneSprite         = make_short_action(0x24, "ActionCloneSprite")
ActionRemoveSprite        = make_short_action(0x25, "ActionRemoveSprite")
ActionTrace               = make_short_action(0x26, "ActionTrace", -1)
ActionStartDrag           = make_short_action(0x27, "ActionStartDrag")
ActionEndDrag             = make_short_action(0x28, "ActionEndDrag")
ActionStringLess          = make_short_action(0x29, "ActionStringLess")
ActionThrow               = make_short_action(0x2a, "ActionThrow")
ActionCastOp              = make_short_action(0x2b, "ActionCastOp")
ActionImplementsOp        = make_short_action(0x2c, "ActionImplementsOp")
ActionRandomNumber        = make_short_action(0x30, "ActionRandomNumber")
ActionMBStringLength      = make_short_action(0x31, "ActionMBStringLength")
ActionCharToAscii         = make_short_action(0x32, "ActionCharToAscii")
ActionAsciiToChar         = make_short_action(0x33, "ActionAsciiToChar")
ActionGetTime             = make_short_action(0x34, "ActionGetTime")
ActionMBStringExtract     = make_short_action(0x35, "ActionMBStringExtract")
ActionMBCharToAscii       = make_short_action(0x36, "ActionMBCharToAscii")
ActionMBAsciiToChar       = make_short_action(0x37, "ActionMBAsciiToChar")
ActionDelVar              = make_short_action(0x3a, "ActionDelVar")
ActionDelThreadVars       = make_short_action(0x3b, "ActionDelThreadVars")
ActionDefineLocalVal      = make_short_action(0x3c, "ActionDefineLocalVal")
ActionCallFunction        = make_short_action(0x3d, "ActionCallFunction")
ActionReturn              = make_short_action(0x3e, "ActionReturn")
ActionModulo              = make_short_action(0x3f, "ActionModulo", -1)
ActionNewObject           = make_short_action(0x40, "ActionNewObject")
ActionDefineLocal         = make_short_action(0x41, "ActionDefineLocal")
ActionInitArray           = make_short_action(0x42, "ActionInitArray")
ActionInitObject          = make_short_action(0x43, "ActionInitObject")
ActionTypeof              = make_short_action(0x44, "ActionTypeof")
ActionGetTargetPath       = make_short_action(0x45, "ActionGetTargetPath")
ActionEnumerate           = make_short_action(0x46, "ActionEnumerate")
ActionTypedAdd            = make_short_action(0x47, "ActionTypedAdd", -1)
ActionTypedLess           = make_short_action(0x48, "ActionTypedLess", -1)
ActionTypedEquals         = make_short_action(0x49, "ActionTypedEquals", -1)
ActionConvertToNumber     = make_short_action(0x4a, "ActionConvertToNumber")
ActionConvertToString     = make_short_action(0x4b, "ActionConvertToString")
ActionDuplicate           = make_short_action(0x4c, "ActionDuplicate", 1)
ActionSwap                = make_short_action(0x4d, "ActionSwap")
ActionGetMember           = make_short_action(0x4e, "ActionGetMember", -1)
ActionSetMember           = make_short_action(0x4f, "ActionSetMember", -3)
ActionIncrement           = make_short_action(0x50, "ActionIncrement")
ActionDecrement           = make_short_action(0x51, "ActionDecrement")
ActionCallMethod          = make_short_action(0x52, "ActionCallMethod")
ActionCallNewMethod       = make_short_action(0x53, "ActionCallNewMethod")
ActionBitAnd              = make_short_action(0x60, "ActionBitAnd", -1)
ActionBitOr               = make_short_action(0x61, "ActionBitOr", -1)
ActionBitXor              = make_short_action(0x62, "ActionBitXor", -1)
ActionShiftLeft           = make_short_action(0x63, "ActionShiftLeft", -1)
ActionShiftRight          = make_short_action(0x64, "ActionShiftRight", -1)
ActionShiftUnsigned       = make_short_action(0x65, "ActionShiftUnsigned", -1)
ActionStrictEquals        = make_short_action(0x66, "ActionStrictEquals", -1)
ActionGreater             = make_short_action(0x67, "ActionGreater", -1)
ActionStringGreater       = make_short_action(0x68, "ActionStringGreater", -1)
ActionExtends             = make_short_action(0x69, "ActionExtends")
