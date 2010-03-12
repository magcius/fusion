
import struct

from mech.fusion.bitstream import BitStream, BitStreamParseMixin

from mech.fusion.avm2 import instructions

from mech.fusion.avm2.constants import (AbcConstantPool,
                                        METHODFLAG_HasOptional,
                                        METHODFLAG_HasParamNames,
                                        py_to_abc, abc_to_py)

from mech.fusion.avm2.util import serialize_u32 as s_u32, ValuePool

from mech.fusion.avm2.assembler import Avm2CodeAssembler

from mech.fusion.avm2.traits import AbcTrait

MAJOR_VERSION = 46
MINOR_VERSION = 16

class AbcFile(BitStreamParseMixin):

    write_to = "abc"
    
    def __init__(self, constants=None):
        self.constants = constants or AbcConstantPool()
        self.methods   = ValuePool(parent=self, debug=True)
        self.metadatas = ValuePool(parent=self)
        self.instances = ValuePool(parent=self)
        self.classes   = ValuePool(parent=self)
        self.scripts   = ValuePool(parent=self)
        self.bodies    = ValuePool(parent=self)

    def write(self, value):
        if hasattr(value, "write_to_abc"):
            value.write_to_abc(self)
        if hasattr(value, "write_to_pool"):
            value.write_to_pool(self.constants)

    @classmethod
    def from_bitstream(cls, bitstream):

        assert bitstream.read_int_value(16, endianness="<") <= MINOR_VERSION
        assert bitstream.read_int_value(16, endianness="<") <= MAJOR_VERSION
        constants = AbcConstantPool.from_bitstream(bitstream)
        constants.debug_print()
        abc = cls(constants)
        
        def read_pool(pool, info, length=None):
            if length is None:
                length = bitstream.read_u32()
            for i in xrange(length):
                pool.index_for(info.parse(bitstream, abc, constants))
            return length

        L = read_pool(abc.methods,   AbcMethodInfo)
        L = read_pool(abc.metadatas, AbcMetadataInfo)
        L = read_pool(abc.instances, AbcInstanceInfo)
        L = read_pool(abc.classes,   AbcClassInfo, L)
        L = read_pool(abc.scripts,   AbcScriptInfo)
        L = read_pool(abc.bodies,    AbcMethodBodyInfo)

    def serialize(self):
        def write_pool(pool, prefix_count=True):
            code = ""
            if prefix_count:
                code += s_u32(len(pool))
            for item in pool:
                code += item.serialize()
            return code
        
        code = ""
        code += struct.pack("<HH", MINOR_VERSION, MAJOR_VERSION)
        code += self.constants.serialize()
        
        code += write_pool(self.methods)
        code += write_pool(self.metadatas)
        code += write_pool(self.instances)
        code += write_pool(self.classes, False)
        code += write_pool(self.scripts)
        code += write_pool(self.bodies)

        return code

class AbcMethodInfo(object):
    done = False
    def __init__(self, name, param_types, return_type, flags=0, options=None, param_names=None):
        self.name = name
        self._name_index = None
        
        self.param_types = param_types or []
        self._param_types_indices = None

        self.param_names = param_names or []
        self._param_names_indices = None
        
        self.return_type = return_type
        self._return_type_index = None
        
        self.flags = flags
        
        self.options = options or []
        self._options_indices = None
    
    @classmethod
    def parse(cls, bitstream, abc, constants):
        PTL = bitstream.read_u32()
        return_type = constants.multiname_pool.value_at(bitstream.read_u32())

        param_types = [constants.multiname_pool.value_at(bitstream.read_u32()) for i in xrange(PTL)]
        name = constants.utf8_pool.value_at(bitstream.read_u32())
        
        flags = bitstream.read_int_value(8)

        options = None
        if flags & METHODFLAG_HasOptional:
            L = bitstream.read_u32()
            options = [abc_to_py((bitstream.read_u32(),
                                  bitstream.read_int_value(8)),
                                 constants) for i in xrange(L)]

        param_names = None
        if flags & METHODFLAG_HasParamNames:
            param_names = [constants.utf8_pool(bitstream.read_u32()) for i in xrange(PTL)]

        return cls(name, param_types, return_type, flags, options, param_names)
        
    def serialize(self):
        code = ""

        code += s_u32(len(self.param_types))
        code += s_u32(self._return_type_index)
        
        code += ''.join(s_u32(index) for index in self._param_types_indices)
        code += s_u32(self._name_index)

        if self.options:
            self.flags |= METHODFLAG_HasOptional
            
        if self.param_names:
            self.flags |= METHODFLAG_HasParamNames

        code += chr(self.flags & 0xFF)

        if self.options:
            code += s_u32(len(self.options))
            for ctype, index in self._options_indices:
                code += s_u32(index)
                code += chr(ctype)

        if self.param_names:
            code += ''.join(s_u32(index) for index in self._param_names_indices)

        return code

    def write_to_pool(self, pool):
        self._name_index = pool.utf8_pool.index_for(self.name)
        self._return_type_index = pool.multiname_pool.index_for(self.return_type)
        
        self._param_types_indices = [pool.multiname_pool.index_for(i) for i in self.param_types]
        self._param_names_indices = [pool.utf8_pool.index_for(i) for i in self.param_names]
        
        self._options_indices = [py_to_abc(value) for value in self.options]

    def __repr__(self):
        return "AbcMethod(%r)" % (self.name,)
        

class AbcMetadataInfo(object):

    def __init__(self, name, items):
        self.name = name
        self._name_index = None
        
        self.items = items
        self._items_indices = None

    @classmethod
    def parse(cls, bitstream, abc, constants):
        def uv():
            return constants.utf8_pool.value_at(bitstream.read_u32())
        
        name = uv()
        items = [(uv(), uv()) for i in xrange(bitstream.read_u32())]
        
        return cls(name, items)
        
    def serialize(self):
        code = ""
        code += s_u32(self._name_index)
        code += s_u32(len(self.items))

        for key_i, val_i in self._items_indices:
            code += s_u32(key_i)
            code += s_u32(val_i)
        
        return code

    def write_to_pool(self, pool):
        strindex = pool.utf8_pool.index_for
        self._name_index = strindex(self.name)
        self._items_indices = [(strindex(k), strindex(v)) for k, v in self.items.iteritems()]

class AbcInstanceInfo(object):
    def __init__(self, name, iinit, interfaces=None,
                 is_interface=False, final=False, sealed=True,
                 super_name=None, traits=None, protectedNs=None):
        
        self.name = name
        self._name_index = None

        self.super_name = super_name
        self._super_name_index = None

        self.is_interface = is_interface
        self.is_sealed = sealed
        self.is_final = final

        self.interfaces = interfaces or []
        self._interface_indices = None
        
        self.iinit = iinit
        self._iinit_index = 0

        self.traits = traits or []

        self.protectedNs = protectedNs
        self._protectedNs_index = None

    def __repr__(self):
        return "AbcInstance(%r, %r)" % (self.name, self.super_name)

    @classmethod
    def parse(cls, bitstream, abc, constants):
        name = constants.multiname_pool.value_at(bitstream.read_u32())
        super_name = constants.multiname_pool.value_at(bitstream.read_u32())

        bitstream.cursor += 4
        FlagProtectedNS = bitstream.read_bit()
        FlagIsInterface = bitstream.read_bit()
        FlagIsFinal     = bitstream.read_bit()
        FlagIsSealed    = bitstream.read_bit()

        protectedNs = None
        if FlagProtectedNS:
            protectedNs = constants.namespace_pool.value_at(bitstream.read_u32())

        interfaces = [constants.multiname_pool.index_for(bitstream.read_u32()) for i in xrange(bitstream.read_u32())]
        iinit = abc.methods.value_at(bitstream.read_u32())

        traits = [AbcTrait.parse(bitstream, abc, constants) for i in xrange(bitstream.read_u32())]
        return cls(name, iinit, interfaces, FlagIsInterface, FlagIsFinal, FlagIsSealed, super_name, traits, protectedNs)
    
    def serialize(self):
        code = ""
        code += s_u32(self._name_index)
        code += s_u32(self._super_name_index)

        # Flags
        flags = BitStream()
        flags.zero_fill(4)                        # first four bits = not defined
        flags.write_bit(self.protectedNs != None) # 1000 = 0x08 = CLASSFLAG_ClassProtectedNs
        flags.write_bit(self.is_interface)        # 0100 = 0x04 = CLASSFLAG_ClassInterface
        flags.write_bit(self.is_final)            # 0010 = 0x02 = CLASSFLAG_ClassFinal
        flags.write_bit(self.is_sealed)           # 0001 = 0x01 = CLASSFLAG_ClassSealed

        code += flags.serialize()

        if self.protectedNs:
            code += s_u32(self._protectedNs_index)

        code += s_u32(len(self.interfaces))
        for index in self._interface_indices:
            code += s_u32(index)
            
        code += s_u32(self._iinit_index)
        
        code += s_u32(len(self.traits))
        for trait in self.traits:
            code += trait.serialize()

        return code

    def write_to_pool(self, pool):
        self._name_index = pool.multiname_pool.index_for(self.name)
        self._super_name_index = pool.multiname_pool.index_for(self.super_name)
        self._interface_indices = [pool.multiname_pool.index_for(i) for i in self.interfaces]

        if self.protectedNs:
            self._protectedNs_index = pool.namespace_pool.index_for(self.protectedNs)

        for trait in self.traits:
            trait.write_to_pool(pool)

    def write_to_abc(self, abc):
        self._iinit_index = abc.methods.index_for(self.iinit)
        
        for trait in self.traits:
            trait.write_to_abc(abc)

class AbcClassInfo(object):
    def __init__(self, cinit, traits=None):
        self.traits = traits or []
        
        self.cinit = cinit
        self._cinit_index = None

    @classmethod
    def parse(cls, bitstream, abc, constants):
        cinit = abc.methods.value_at(bitstream.read_u32())
        traits = [AbcTrait.parse(bitstream, abc, constants) for i in xrange(bitstream.read_u32())]
        return cls(cinit, traits)

    def serialize(self):
        code = ""
        
        code += s_u32(self._cinit_index)
        code += s_u32(len(self.traits))
        for trait in self.traits:
            code += trait.serialize()

        return code
    
    def write_to_abc(self, abc):
        self._cinit_index = abc.methods.index_for(self.cinit)
        for trait in self.traits:
            trait.write_to_abc(abc)

    def write_to_pool(self, pool):
        for trait in self.traits:
            trait.write_to_pool(pool)

class AbcScriptInfo(object):
    def __init__(self, init, traits=None):
        self.traits = traits or []
        
        self.init = init
        self._init_index = None

    @classmethod
    def parse(cls, bitstream, abc, constants):
        init = abc.methods.value_at(bitstream.read_u32())
        traits = [AbcTrait.parse(bitstream, abc, constants) for i in xrange(bitstream.read_u32())]
        return cls(init, traits)

    def serialize(self):
        
        code = ""
        
        code += s_u32(self._init_index)
        code += s_u32(len(self.traits))
        for trait in self.traits:
            code += trait.serialize()

        return code
    
    def write_to_abc(self, abc):
        self._init_index = abc.methods.index_for(self.init)
        for trait in self.traits:
            trait.write_to_abc(abc)

    def write_to_pool(self, pool):
        for trait in self.traits:
            trait.write_to_pool(pool)

class AbcMethodBodyInfo(object):

    def __init__(self, method_info, code, traits=None, exceptions=None):
        self.method_info = method_info
        self.method_info.body = self
        self._method_info_index = None

        self.code = code
        
        self.traits = traits or []
        self.exceptions = exceptions or []

    @classmethod
    def parse(cls, bitstream, abc, constants):
        minfo = abc.methods.value_at(bitstream.read_u32())
        stack_depth_max  = bitstream.read_u32()
        local_count      = bitstream.read_u32()
        init_scope_depth = bitstream.read_u32()
        scope_depth_max  = bitstream.read_u32()
        code = Avm2CodeAssembler.parse(bitstream, abc, constants, local_count)
        code._stack_depth_max = stack_depth_max
        code._scope_depth_max = scope_depth_max

        exceptions = [AbcException.parse(bitstream, abc, constants) for i in xrange(bitstream.read_u32())]
        traits     = [AbcTrait    .parse(bitstream, abc, constants) for i in xrange(bitstream.read_u32())]
    
    def serialize(self):
        self.code.add_instruction(instructions.returnvoid())
        code = ""
        code += s_u32(self._method_info_index)
        code += s_u32(self.code._stack_depth_max+1) # just to be safe.
        code += s_u32(len(self.code.temporaries))
        code += s_u32(0) # FIXME: For now, init_scope_depth is always 0.
        code += s_u32(self.code._scope_depth_max)
        body = self.code.serialize()
        code += s_u32(len(body))
        code += body

        code += s_u32(len(self.exceptions))
        for exc in self.exceptions:
            code += exc.serialize()

        code += s_u32(len(self.traits))
        for trait in self.traits:
            code += trait.serialize()

        return code

    def write_to_abc(self, abc):
        self._method_info_index = abc.methods.index_for(self.method_info)
        for trait in self.traits:
            trait.write_to_abc(abc)

    def write_to_pool(self, pool):
        for trait in self.traits:
            trait.write_to_pool(pool)
        for exc in self.exceptions:
            exc.write_to_pool(pool)

class AbcException(object):
    def __init__(self, from_, to_, target, exc_type, var_name):
        self.from_ = from_
        self.to_ = to_
        self.target = target
        
        self.exc_type = exc_type
        self._exc_type_index = None

        self.var_name = var_name
        self._var_name_index = None

    @classmethod
    def parse(cls, bitstream, abc, constants):
        u = bitstream.read_u32
        return cls(u(), u(), u(),
                   constants.multiname_pool.value_at(u()),
                   constants.utf8_pool.value_at(u()))
    
    def serialize(self):
        code = ""
        code += s_u32(self.from_)
        code += s_u32(self.to_)
        code += s_u32(self.target)
        code += s_u32(self._exc_type_index)
        code += s_u32(self._var_name_index)
        return code

    def write_to_pool(self, pool):
        self._exc_type_index = pool.multiname_pool.index_for(self.exc_type)
        self._var_name_index = pool.utf8_pool.index_for(self.var_name)
        
        
