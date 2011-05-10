
"""
Structures for ABC, ActionScript Byte Code
"""

import struct
import os

from fusion.bitstream import BitStream, BitStreamParseMixin
from fusion.bitstream.formats import Bit, Zero
from fusion.bitstream.flash_formats import UI8, UI16, U32

from fusion.avm2.interfaces import IAbcContainer, IConstantPoolWriter, IMultiname
from fusion.avm2.constants import ConstantPool, QName, MethodFlag
from fusion.avm2.traits import parse_trait, eval_traits
from fusion.avm2.assembler import CodeAssembler
from fusion.avm2.util import serialize_u32 as s_u32, ValuePool

from zope.interface import implements

MAJOR_VERSION = 46
MINOR_VERSION = 16

class AbcFile(BitStreamParseMixin):
    def __init__(self, constants=None):
        self.constants = constants or ConstantPool()

        self.methods   = ValuePool(self)
        self.metadatas = ValuePool(self)
        self.instances = ValuePool(self)
        self.classes   = ValuePool(self)
        self.scripts   = ValuePool(self)
        self.bodies    = ValuePool(self)

    def write(self, value):
        self.constants.write(value)

        try:
            IAbcContainer(value).add_abc_elements(self)
        except TypeError:
            pass

    def merge(self, abc):
        for name in ("methods", "metadatas", "instances",
                     "classes", "scripts", "bodies"):
            getattr(self, name).merge(getattr(abc, name))

    def create_generator(self, make_script=True):
        from fusion.avm2.codegen import CodeGenerator
        return CodeGenerator(self, make_script)

    @classmethod
    def from_bitstream(cls, bitstream):
        assert bitstream.read(UI16) == MINOR_VERSION
        assert bitstream.read(UI16) == MAJOR_VERSION
        constants = ConstantPool.from_bitstream(bitstream)
        abc = cls(constants)

        def read_pool(pool, info, length=None):
            if length is None:
                length = bitstream.read(U32)
            for i in xrange(length):
                pool.index_for(info.parse(bitstream, abc, constants))
            return length

        read_pool(abc.methods, MethodInfo)
        read_pool(abc.metadatas, MetadataInfo)
        count = read_pool(abc.instances, InstanceInfo)
        read_pool(abc.classes, ClassInfo, count)
        read_pool(abc.scripts, ScriptInfo)
        read_pool(abc.bodies, MethodBodyInfo)

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

        code = struct.pack("<HH", MINOR_VERSION, MAJOR_VERSION)
        code += self.constants.serialize()

        code += write_pool(self.methods)
        code += write_pool(self.metadatas)
        code += write_pool(self.instances)
        code += write_pool(self.classes, False)
        code += write_pool(self.scripts)
        code += write_pool(self.bodies)

        return code

class MethodInfo(object):
    implements(IConstantPoolWriter, IAbcContainer)
    def __init__(self, namestr, param_types, return_type, flags=0, options=None, param_names=None, varargs=None):
        self.namestr = namestr
        self._namestr_index = None

        self.param_types = [IMultiname(t) for t in param_types] if param_types else []
        self._param_types_indices = None

        self.param_names = param_names or []
        self._param_names_indices = None

        self.return_type = IMultiname(return_type)
        self._return_type_index = None

        self.flags = flags
        self.varargs = varargs

        self.body = None

        self.options = options or []
        self._options_indices = None

    @classmethod
    def parse(cls, bitstream, abc, constants):
        PTL = bitstream.read(U32)

        return_type = constants.multiname.value_at(bitstream.read(U32))
        param_types = [constants.multiname.value_at(bitstream.read(U32)) for i in xrange(PTL)]
        namestr = constants.utf8.value_at(bitstream.read(U32))

        flags = bitstream.read(UI8)

        options = None
        if flags & MethodFlag.HasOptional:
            L = bitstream.read(U32)
            options = [abc_to_py((bitstream.read(U32),
                                  bitstream.read(UI8)),
                                 constants) for i in xrange(L)]

        param_names = None
        if flags & MethodFlag.HasParamNames:
            param_names = [constants.utf8.value_at(bitstream.read(U32)) for i in xrange(PTL)]

        varargs = bool(flags & MethodFlag.NeedRest)

        return cls(namestr, param_types, return_type, flags, options, param_names, varargs)

    def serialize(self):
        code = ""

        code += s_u32(len(self.param_types))
        code += s_u32(self._return_type_index)

        code += ''.join(s_u32(index) for index in self._param_types_indices)
        code += s_u32(self._namestr_index)

        if self.options:
            self.flags |= MethodFlag.HasOptional

        if self.param_names:
            self.flags |= MethodFlag.HasParamNames

        if self.varargs:
            self.flags |= MethodFlag.NeedRest

        code += chr(self.flags & 0xFF)

        if self.options:
            code += s_u32(len(self.options))
            for ctype, index in self._options_indices:
                code += s_u32(index)
                code += chr(ctype)

        if self.param_names:
            code += ''.join(s_u32(index) for index in self._param_names_indices)

        return code

    def add_abc_elements(self, abcfile):
        if self.body is not None:
            # XXX: hack to avoid dep
            body, self.body = self.body, None
            abcfile.bodies.index_for(body)
            self.body = body

    def write_constants(self, pool):
        self._namestr_index = pool.utf8.index_for(self.namestr)
        self._return_type_index = pool.multiname.index_for(self.return_type)

        self._param_types_indices = [pool.multiname.index_for(i) for i in self.param_types]
        self._param_names_indices = [pool.utf8.index_for(i) for i in self.param_names]

        self._options_indices = [py_to_abc(value, pool) for value in self.options]

    def __repr__(self):
        return "MethodInfo(%r)" % (self.namestr,)

class MetadataInfo(object):
    implements(IConstantPoolWriter)
    def __init__(self, name, items):
        self.name = name
        self._name_index = None

        self.items = items
        self._keys_indices = None
        self._values_indices = None

    @classmethod
    def parse(cls, bitstream, abc, constants):
        name = constants.utf8.value_at(bitstream.read(U32))
        item_count = bitstream.read(U32)
        keys   = [constants.utf8.value_at(bitstream.read(U32)) for i in xrange(item_count)]
        values = [constants.utf8.value_at(bitstream.read(U32)) for i in xrange(item_count)]
        items = dict(zip(keys, values))

        return cls(name, items)

    def serialize(self):
        code = ""
        code += s_u32(self._name_index)
        code += s_u32(len(self.items))

        for key_i in self._keys_indices:
            code += s_u32(key_i)

        for val_i in self._values_indices:
            code += s_u32(val_i)

        return code

    def write_constants(self, pool):
        self._name_index = pool.utf8.index_for(self.name)
        self._keys_indices   = [pool.utf8.index_for(k) for k in self.items.iterkeys()]
        self._values_indices = [pool.utf8.index_for(v) for v in self.items.itervalues()]

    def __repr__(self):
        return "Metadata(%r, %s)" % (self.name, ''.join("%s=%r" % t for t in self.items.iteritems()))

class TraitContainer(object):
    implements(IConstantPoolWriter, IAbcContainer)
    def __init__(self, traits):
        self.traits = traits or []

    def add_abc_elements(self, abcfile):
        for trait in self.traits:
            abcfile.write(trait)

    def write_constants(self, pool):
        for trait in self.traits:
            pool.write(trait)

class InstanceInfo(TraitContainer):
    def __init__(self, name, iinit, interfaces=None,
                 is_interface=False, final=False, sealed=True,
                 super_name=None, traits=None, protectedNs=None):

        super(InstanceInfo, self).__init__(traits)

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

        self.protectedNs = protectedNs
        self._protectedNs_index = None

    @classmethod
    def parse(cls, bitstream, abc, constants):
        name = constants.multiname.value_at(bitstream.read(U32))
        super_name = constants.multiname.value_at(bitstream.read(U32))

        bitstream.seek(4, os.SEEK_CUR)
        FlagProtectedNS = bitstream.read(Bit)
        FlagIsInterface = bitstream.read(Bit)
        FlagIsFinal     = bitstream.read(Bit)
        FlagIsSealed    = bitstream.read(Bit)

        protectedNs = None
        if FlagProtectedNS:
            protectedNs = constants.namespace.value_at(bitstream.read(U32))

        interfaces = [constants.multiname.value_at(bitstream.read(U32)) for i in xrange(bitstream.read(U32))]
        iinit = abc.methods.value_at(bitstream.read(U32))

        traits = [parse_trait(bitstream, abc, constants) for i in xrange(bitstream.read(U32))]
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

    def write_constants(self, pool):
        super(InstanceInfo, self).write_constants(pool)
        self._name_index = pool.multiname.index_for(self.name)
        self._super_name_index = pool.multiname.index_for(self.super_name)
        self._interface_indices = [pool.multiname.index_for(i) for i in self.interfaces]

        if self.protectedNs:
            self._protectedNs_index = pool.namespace.index_for(self.protectedNs)

    def add_abc_elements(self, abcfile):
        super(InstanceInfo, self).add_abc_elements(abcfile)
        self._iinit_index = abcfile.methods.index_for(self.iinit)

    def __repr__(self):
        return "Instance(%r, %r)" % (self.name, self.super_name)

class ClassInfo(TraitContainer):
    def __init__(self, cinit, traits=None):
        super(ClassInfo, self).__init__(traits)

        self.instance = None
        self.cinit = cinit
        self._cinit_index = None

    @classmethod
    def parse(cls, bitstream, abc, constants):
        cinit = abc.methods.value_at(bitstream.read(U32))
        traits = [parse_trait(bitstream, abc, constants) for i in xrange(bitstream.read(U32))]
        return cls(cinit, traits)

    def serialize(self):
        code = ""
        code += s_u32(self._cinit_index)
        code += s_u32(len(self.traits))
        for trait in self.traits:
            code += trait.serialize()

        return code

    def add_abc_elements(self, abcfile):
        super(ClassInfo, self).add_abc_elements(abcfile)
        self._cinit_index = abcfile.methods.index_for(self.cinit)

    def __repr__(self):
        if self.instance:
            return "Class(%r, %r)" % (self.instance.name, self.instance.super_name)
        return "Class(unknown)"

class ScriptInfo(TraitContainer):
    def __init__(self, init, traits=None):
        super(ScriptInfo, self).__init__(traits)

        self.init = init
        self._init_index = None

    @classmethod
    def parse(cls, bitstream, abc, constants):
        init = abc.methods.value_at(bitstream.read(U32))
        traits = [parse_trait(bitstream, abc, constants) for i in xrange(bitstream.read(U32))]
        return cls(init, traits)

    def serialize(self):
        code = ""

        code += s_u32(self._init_index)
        code += s_u32(len(self.traits))
        for trait in self.traits:
            code += trait.serialize()

        return code

    def add_abc_elements(self, abcfile):
        super(ScriptInfo, self).add_abc_elements(abcfile)
        self._init_index = abcfile.methods.index_for(self.init)

    def __repr__(self):
        return "ScriptInfo(unknown)"

class MethodBodyInfo(TraitContainer):
    def __init__(self, method_info, code, traits=None, exceptions=None, optimize=True):
        super(MethodBodyInfo, self).__init__(traits)

        self.method_info = method_info
        self.method_info.body = self
        self._method_info_index = None

        self.code = code
        self.exceptions = exceptions
        self.optimize = optimize

    @classmethod
    def parse(cls, bitstream, abc, constants):
        minfo = abc.methods.value_at(bitstream.read(U32))
        stack_depth_max  = bitstream.read(U32)
        local_count      = bitstream.read(U32)
        init_scope_depth = bitstream.read(U32)
        scope_depth_max  = bitstream.read(U32)
        code = CodeAssembler.parse(bitstream, abc, constants, local_count)
        code.max_stack_depth = stack_depth_max
        code.max_scope_depth = scope_depth_max - init_scope_depth

        exceptions = [Exception.parse(bitstream, abc, constants) for i in xrange(bitstream.read(U32))]
        traits     = [parse_trait(bitstream, abc, constants) for i in xrange(bitstream.read(U32))]

        return cls(minfo, code, traits, exceptions)

    def serialize(self):
        self.code.emit('returnvoid')

#        if self.optimize:
#            self.code.optimize()

        self.code.pass1()

        code = ""
        code += s_u32(self._method_info_index)
        code += s_u32(self.code.max_stack_depth)
        code += s_u32(self.code.max_local_count)
        code += s_u32(0)
        code += s_u32(self.code.max_scope_depth)
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

    def add_abc_elements(self, abcfile):
        super(MethodBodyInfo, self).add_abc_elements(abcfile)
        self._method_info_index = abcfile.methods.index_for(self.method_info)

    def write_constants(self, pool):
        super(MethodBodyInfo, self).write_constants(pool)
        for exc in self.exceptions:
            pool.write(exc)
        pool.write(self.code)

    def __repr__(self):
        return "MethodBody(%r)" % (self.method_info.namestr,)

class Exception(object):
    implements(IConstantPoolWriter)
    def __init__(self, from_, to_, target, exc_type, var_name):
        self.from_ = from_
        self.to_ = to_
        self.target = target

        self.exc_type = IMultiname(exc_type)
        self._exc_type_index = None

        self.var_name = IMultiname(var_name)
        self._var_name_index = None

    @classmethod
    def parse(cls, bitstream, abc, constants):
        return cls(bitstream.read(U32),
                   bitstream.read(U32),
                   bitstream.read(U32),
                   constants.multiname.value_at(bitstream.read(U32)),
                   constants.multiname.value_at(bitstream.read(U32)))

    def serialize(self):
        code = ""
        code += s_u32(self.from_)
        code += s_u32(self.to_)
        code += s_u32(self.target)
        code += s_u32(self._exc_type_index)
        code += s_u32(self._var_name_index)
        return code

    def write_constants(self, pool):
        self._exc_type_index = pool.multiname.index_for(self.exc_type)
        self._var_name_index = pool.multiname.index_for(self.var_name)
