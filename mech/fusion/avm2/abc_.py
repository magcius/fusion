
import struct
import os

from mech.fusion.bitstream import BitStream, BitStreamParseMixin
from mech.fusion.bitstream.formats import Bit, Zero
from mech.fusion.bitstream.flash_formats import UI8, UI16, U32

from mech.fusion.avm2.constants import (AbcConstantPool,
    METHODFLAG_HasOptional, METHODFLAG_HasParamNames,
    METHODFLAG_NeedRest, py_to_abc, abc_to_py, QName)

from mech.fusion.avm2 import instructions, traits as TRAITS
from mech.fusion.avm2.assembler import Avm2CodeAssembler
from mech.fusion.avm2.interfaces import IMultiname
from mech.fusion.avm2.util import serialize_u32 as s_u32, ValuePool

MAJOR_VERSION = 46
MINOR_VERSION = 16

def eval_traits(self):
    fields     = {}
    methods    = {}
    properties = {}
    for trait in self.traits:
        trait.owner = self
        if isinstance(trait, TRAITS.AbcSlotTrait):
            trait.kind = "slot"
            if isinstance(trait, TRAITS.AbcConstTrait):
                trait.kind = "const"
            fields[trait.name] = trait
        if isinstance(trait, TRAITS.AbcMethodTrait):
            trait.method.kind  = "method"
            trait.method.name  = trait.name
            trait.method.owner = self
            if isinstance(trait, TRAITS.AbcGetterTrait):
                trait.type_name = trait.method.return_type
                if trait.name in properties:
                    properties[trait.name] = (trait.name, trait.type_name,
                                              trait, properties[trait.name][3])
                    trait.kind = properties[trait.name][3].kind = "property"
                else:
                    trait.method.kind = trait.kind = "getter"
                    properties[trait.name] = (trait.name, trait.type_name,
                                              trait, None)
            elif isinstance(trait, TRAITS.AbcSetterTrait):
                trait.type_name = trait.method.param_types[0]
                if trait.name in properties:
                    properties[trait.name] = (trait.name, trait.type_name,
                                              properties[trait.name][2], trait)
                    trait.kind = properties[trait.name][2].kind = "property"
                else:
                    trait.method.kind = trait.kind = "setter"
                    properties[trait.name] = (trait.name, trait.type_name,
                                              None, trait)
            else:
                methods[trait.name] = trait
        elif isinstance(trait, TRAITS.AbcClassTrait):
            trait.cls.name           = trait.name
            trait.cls.owner          = self
            trait.cls.instance.name  = trait.name
            trait.cls.instance.owner = self
    self.fields     = fields
    print self, fields
    self.methods    = methods
    self.properties = properties

class AbcFile(BitStreamParseMixin):
    write_to = "abc"
    def __init__(self, constants=None):
        self.constants = constants or AbcConstantPool()
        (self.methods, self.metadatas, self.instances,
        self.classes, self.scripts, self.bodies) = (ValuePool(parent=self) \
                                                    for i in xrange(6))

    def merge(self, file, *files):
        for name in ("methods", "metadatas", "instances",
                     "classes", "scripts", "bodies"):
            getattr(self, name).merge(getattr(file, name))

        for f in files:
            self.merge(f)

    def write(self, value):
        m1 = getattr(value, "write_to_abc", None)
        m2 = getattr(value, "write_to_pool", None)
        if m1: m1(self)
        if m2: m2(self.constants)

    def create_generator(self, make_script=True):
        from mech.fusion.avm2.codegen import CodeGenerator
        return CodeGenerator(self, make_script)

    @classmethod
    def from_bitstream(cls, bitstream):
        assert bitstream.read(UI16) == MINOR_VERSION
        assert bitstream.read(UI16) == MAJOR_VERSION
        constants = AbcConstantPool.from_bitstream(bitstream)
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

        for cls, instance in zip(abc.classes, abc.instances):
            cls.instance = instance
            instance.cls = cls
            cls.cinit.owner = cls
            instance.iinit.owner = instance
            eval_traits(cls)
            eval_traits(instance)

        for meth in abc.bodies:
            eval_traits(meth)

        for script in abc.scripts:
            script.init.owner = script
            eval_traits(script)

        return abc

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
    def __init__(self, namestr, param_types, return_type, flags=0, options=None, param_names=None, varargs=None):
        self.namestr = namestr
        self._namestr_index = None

        self.param_types = [IMultiname(t) for t in param_types] if param_types else []
        self._param_types_indices = None

        self.param_names = param_names or []
        self._param_names_indices = None

        self.return_type = QName(return_type)
        self._return_type_index = None

        self.flags = flags
        self.varargs = varargs

        if varargs and varargs is not True:
            self.param_types.append(QName("Array"))
            self.param_names.append(QName(varargs))

        self.options = options or []
        self._options_indices = None

    @classmethod
    def parse(cls, bitstream, abc, constants):
        PTL = bitstream.read(U32)
        return_type = constants.multiname_pool.value_at(bitstream.read(U32))

        param_types = [constants.multiname_pool.value_at(bitstream.read(U32)) for i in xrange(PTL)]
        namestr = constants.utf8_pool.value_at(bitstream.read(U32))

        flags = bitstream.read(UI8)

        options = None
        if flags & METHODFLAG_HasOptional:
            L = bitstream.read(U32)
            options = [abc_to_py((bitstream.read(U32),
                                  bitstream.read(UI8)),
                                 constants) for i in xrange(L)]

        param_names = None
        if flags & METHODFLAG_HasParamNames:
            param_names = [constants.utf8_pool.value_at(bitstream.read(U32)) for i in xrange(PTL)]

        varargs = bool(flags & METHODFLAG_NeedRest)

        return cls(namestr, param_types, return_type, flags, options, param_names, varargs)

    def serialize(self):
        code = ""

        code += s_u32(len(self.param_types))
        code += s_u32(self._return_type_index)

        code += ''.join(s_u32(index) for index in self._param_types_indices)
        code += s_u32(self._namestr_index)

        if self.options:
            self.flags |= METHODFLAG_HasOptional

        if self.param_names:
            self.flags |= METHODFLAG_HasParamNames

        if self.varargs:
            self.flags |= METHODFLAG_NeedRest

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
        self._namestr_index = pool.utf8_pool.index_for(self.namestr)
        self._return_type_index = pool.multiname_pool.index_for(self.return_type)

        self._param_types_indices = [pool.multiname_pool.index_for(i) for i in self.param_types]
        self._param_names_indices = [pool.utf8_pool.index_for(i) for i in self.param_names]

        self._options_indices = [py_to_abc(value, pool) for value in self.options]

    def __repr__(self):
        return "AbcMethod(%r)" % (self.namestr,)

class AbcMetadataInfo(object):
    def __init__(self, name, items):
        self.name = name
        self._name_index = None

        self.items = items
        self._items_indices = None

    @classmethod
    def parse(cls, bitstream, abc, constants):
        def uv():
            return constants.utf8_pool.value_at(bitstream.read(U32))

        name = uv()
        item_count = bitstream.read(U32)
        keys   = [uv() for i in xrange(item_count)]
        values = [uv() for i in xrange(item_count)]
        items = dict(zip(keys, values))

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

    def __repr__(self):
        return "Metadata(%r, %s)" % (self.name, ''.join("%s=%r" % t for t in self.items.iteritems()))

class AbcInstanceInfo(object):
    def __init__(self, name, iinit, interfaces=None,
                 is_interface=False, final=False, sealed=True,
                 super_name=None, traits=None, protectedNs=None):

        self.name = IMultiname(name)
        self._name_index = None

        self.super_name = IMultiname(super_name)
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

    @classmethod
    def parse(cls, bitstream, abc, constants):
        name = constants.multiname_pool.value_at(bitstream.read(U32))
        super_name = constants.multiname_pool.value_at(bitstream.read(U32))

        bitstream.seek(4, os.SEEK_CUR)
        FlagProtectedNS = bitstream.read(Bit)
        FlagIsInterface = bitstream.read(Bit)
        FlagIsFinal     = bitstream.read(Bit)
        FlagIsSealed    = bitstream.read(Bit)

        protectedNs = None
        if FlagProtectedNS:
            protectedNs = constants.namespace_pool.value_at(bitstream.read(U32))

        interfaces = [constants.multiname_pool.index_for(bitstream.read(U32)) for i in xrange(bitstream.read(U32))]
        iinit = abc.methods.value_at(bitstream.read(U32))

        traits = [TRAITS.AbcTrait.parse(bitstream, abc, constants) for i in xrange(bitstream.read(U32))]
        return cls(name, iinit, interfaces, FlagIsInterface, FlagIsFinal, FlagIsSealed, super_name, traits, protectedNs)

    def serialize(self):
        code = ""
        code += s_u32(self._name_index)
        code += s_u32(self._super_name_index)

        # Flags
        flags = BitStream()
        flags.write(Zero[4])                  # first four bits = not defined
        flags.write(self.protectedNs != None) # 1000 = 0x08 = CLASSFLAG_ClassProtectedNs
        flags.write(self.is_interface)        # 0100 = 0x04 = CLASSFLAG_ClassInterface
        flags.write(self.is_final)            # 0010 = 0x02 = CLASSFLAG_ClassFinal
        flags.write(self.is_sealed)           # 0001 = 0x01 = CLASSFLAG_ClassSealed

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

    def __repr__(self):
        return "AbcInstance(%r, %r)" % (self.name, self.super_name)

class AbcClassInfo(object):
    def __init__(self, cinit, traits=None):
        self.traits = traits or []

        self.instance = None
        self.cinit = cinit
        self._cinit_index = None

    @classmethod
    def parse(cls, bitstream, abc, constants):
        cinit = abc.methods.value_at(bitstream.read(U32))
        traits = [TRAITS.AbcTrait.parse(bitstream, abc, constants) for i in xrange(bitstream.read(U32))]
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

    def __repr__(self):
        if self.instance:
            return "AbcClass(%r, %r)", (self.instance.name, self.instance.super_name)

class AbcScriptInfo(object):
    def __init__(self, init, traits=None):
        self.traits = traits or []

        self.init = init

    @classmethod
    def parse(cls, bitstream, abc, constants):
        init = abc.methods.value_at(bitstream.read(U32))
        traits = [TRAITS.AbcTrait.parse(bitstream, abc, constants) for i in xrange(bitstream.read(U32))]
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
    def __init__(self, method_info, code, traits=None, exceptions=None, optimize=True):
        self.method_info = method_info
        self.method_info.body = self
        self._method_info_index = None

        self.code = code

        self.optimize = optimize

        self.traits = traits
        self.exceptions = exceptions

    @classmethod
    def parse(cls, bitstream, abc, constants):
        minfo = abc.methods.value_at(bitstream.read(U32))
        stack_depth_max  = bitstream.read(U32)
        local_count      = bitstream.read(U32)
        init_scope_depth = bitstream.read(U32)
        scope_depth_max  = bitstream.read(U32)
        code = Avm2CodeAssembler.parse(bitstream, abc, constants, local_count)
        code._stack_depth_max = stack_depth_max
        code._scope_depth_max = scope_depth_max

        exceptions = [AbcException.parse(bitstream, abc, constants) for i in xrange(bitstream.read(U32))]
        traits     = [TRAITS.AbcTrait.parse(bitstream, abc, constants) for i in xrange(bitstream.read(U32))]

        return cls(minfo, code, traits, exceptions)

    def serialize(self):
        self.code.add_instruction(instructions.returnvoid())

        if self.optimize:
            self.code.optimize()

        self.code.pass1()

        code = ""
        code += s_u32(self._method_info_index)
        code += s_u32(self.code._stack_depth_max+1) # just to be safe.
        code += s_u32(self.code._numlocals_max+1)
        code += s_u32(0) # FIXME: For now, init_scope_depth is always 0.
        code += s_u32(self.code._scope_depth_max)
        body = self.code.serialize()
        code += s_u32(len(body))
        code += body

        code += s_u32(len(self.exceptions))
        for exc in self.exceptions or []:
            code += exc.serialize()

        code += s_u32(len(self.traits))
        for trait in self.traits or []:
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
        self.code.write_to_pool(pool)

    def __repr__(self):
        return "AbcMethodBody(%r)" % (self.method_info.namestr,)

class AbcException(object):
    def __init__(self, from_, to_, target, exc_type, var_name):
        self.from_ = from_
        self.to_ = to_
        self.target = target

        self.exc_type = IMultiname(exc_type)
        self._exc_type_index = None
        self.var_name = var_name
        self._var_name_index = None

    @classmethod
    def parse(cls, bitstream, abc, constants):
        u = lambda : bitstream.read(U32)
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
