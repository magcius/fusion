
import os

from mech.fusion.bitstream.bitstream import BitStream
from mech.fusion.bitstream.formats import U32, Bit, UB
from mech.fusion.bitstream.flash_formats import UI8

from mech.fusion.avm2.interfaces import ILoadable, IStorable, IMultiname
from mech.fusion.avm2.constants import py_to_abc, abc_to_py, QName
from mech.fusion.avm2.util import serialize_u32 as s_u32

from zope.interface import implements

(TRAIT_Slot, TRAIT_Method, TRAIT_Getter, TRAIT_Setter,
 TRAIT_Class, TRAIT_Function, TRAIT_Const) = range(7)

class AbcTrait(object):
    """
    Traits are used to give names and owners to methods, variables,
    constants, getters/setters and classes. There are four things
    that can hold traits: method bodies, instances, classes, and
    scripts. Abc

    Slot and Const traits have a way of optimization called a "slot
    index", which allows you to use an integer with getslot/setslot
    instead of getproperty/setproperty.

    Traits on methods are called "activation" traits, these traits
    are usually used for implementing the "this" object in JavaScript.

    Traits on classes are actually the static variables/constants/
    methods. They are initialized when the class is created from the
    script and only exist in one place in memory.

    Traits on instances are members variables/constants/methods.
    They control the things the object itself is able to hold/do.

    Last, traits on scripts aren't used very often in the context of
    the Flash Player, as far as I can tell they give the actual name
    to the class that is used.
    """
    KIND = None
    def __init__(self, name, final=False, override=False):
        self.name = IMultiname(name)
        self._name_index = None

        self.is_final = final
        self.is_override = override

        self.metadata = []
        self._metadata_indices = None

    def write_to_abc(self, abc):
        self._metadata_indices = [abc.metadatas.index_for(m) for m in self.metadata]

    def write_to_pool(self, pool):
        self._name_index = pool.multiname_pool.index_for(self.name)

    @classmethod
    def parse(cls, bitstream, abc, constants):
        name = constants.multiname_pool.value_at(bitstream.read(U32))
        bitstream.seek(1, os.SEEK_CUR)
        has_metadata = bitstream.read(Bit)
        override = bitstream.read(Bit)
        final    = bitstream.read(Bit)
        cls = TRAIT_KINDS[bitstream.read(UB[4])]
        inst = cls.parse_inner(bitstream, abc, constants)
        inst.name     = name
        inst.final    = final
        inst.override = override
        if has_metadata:
            L = xrange(bitstream.read(U32))
            inst.metadata = [abc.metadatas.value_at(bitstream.read(U32)) for i in L]
        return inst

    def serialize_inner(self):
        return ""

    def serialize(self):
        code = ""
        code += s_u32(self._name_index)

        flags = BitStream()
        flags.write(False)
        flags.write(bool(self.metadata)) # ATTR_Metadata
        flags.write(self.is_override)    # ATTR_Override
        flags.write(self.is_final)       # ATTR_Final
        flags.write(self.KIND, UB[4])  # kind

        code += flags.serialize()
        code += self.serialize_inner()

        if self.metadata:
            code += s_u32(len(self.metadata))
            for m in self._metadata_indices:
                code += s_u32(m)
        return code

class AbcClassTrait(AbcTrait):
    KIND = TRAIT_Class

    def __init__(self, name, cls, slot_id=0, final=False, override=False):
        super(AbcClassTrait, self).__init__(name, final, override)
        self.slot_id = slot_id
        self.cls = cls
        self._class_index = None

    def write_to_abc(self, abc):
        super(AbcClassTrait, self).write_to_abc(abc)
        self._class_index = abc.classes.index_for(self.cls)

    @classmethod
    def parse_inner(cls, bitstream, abc, constants):
        slot_id = bitstream.read(U32)
        clazz   = abc.classes.value_at(bitstream.read(U32))
        return cls(None, clazz, slot_id)

    def serialize_inner(self):
        return s_u32(self.slot_id) + s_u32(self._class_index)

class AbcSlotTrait(AbcTrait):
    KIND = TRAIT_Slot

    def __init__(self, name, type_name, value=None, slot_id=0):
        super(AbcSlotTrait, self).__init__(name, False, False)
        self.slot_id = slot_id

        self.type_name = IMultiname(type_name)
        self._type_name_index = None

        self.value = value
        self._value_index = None
        self._value_kind  = None

    def write_to_pool(self, pool):
        super(AbcSlotTrait, self).write_to_pool(pool)
        if self.value is None:
            self._value_index = 0
        else:
            self._value_kind, self._value_index = py_to_abc(self.value, pool)
            if self._value_index is None:
                self._value_index = self._value_kind

        self._type_name_index = pool.multiname_pool.index_for(self.type_name)

    @classmethod
    def parse_inner(cls, bitstream, abc, constants):
        slot_id   = bitstream.read(U32)
        type_name = constants.multiname_pool.value_at(bitstream.read(U32))
        vindex    = bitstream.read(U32)
        value     = None
        if vindex:
            vkind = bitstream.read(UI8)
            value = abc_to_py((vindex, vkind), constants)

        return cls(None, type_name, value, slot_id)

    def serialize_inner(self):
        code = ""

        code += s_u32(self.slot_id)
        code += s_u32(self._type_name_index)
        code += s_u32(self._value_index)
        if self._value_index:
            code += s_u32(self._value_kind)

        return code

class AbcConstTrait(AbcSlotTrait):
    KIND = TRAIT_Const

class AbcFunctionTrait(AbcTrait):
    KIND = TRAIT_Function
    def __init__(self, name, function, slot_id=0):
        super(AbcFunctionTrait, self).__init__(name, False, False)
        self.slot_id = slot_id

        self.function = function
        self._function_index = None

    def write_to_abc(self, abc):
        super(AbcFunctionTrait, self).write_to_abc(abc)
        self._function_index = abc.methods.index_for(self.function)

    @classmethod
    def parse_inner(cls, bitstream, abc, constants):
        slot_id  = bitstream.read(U32)
        function = abc.methods.value_at(bitstream.read(U32))
        return cls(None, function, slot_id)

    def serialize_inner(self):
        return s_u32(self.slot_id) + s_u32(self._function_index)

class AbcMethodTrait(AbcTrait):
    KIND = TRAIT_Method
    def __init__(self, name, method, disp_id=0, final=False, override=False):
        super(AbcMethodTrait, self).__init__(name, final, override)
        self.disp_id = disp_id

        self.method = method
        self._method_index = None

    def write_to_abc(self, abc):
        super(AbcMethodTrait, self).write_to_abc(abc)
        self._method_index = abc.methods.index_for(self.method)

    @classmethod
    def parse_inner(cls, bitstream, abc, constants):
        disp_id = bitstream.read(U32)
        method = abc.methods.value_at(bitstream.read(U32))
        return cls(None, method, disp_id)

    def serialize_inner(self):
        return s_u32(self.disp_id) + s_u32(self._method_index)

class AbcGetterTrait(AbcMethodTrait):
    KIND = TRAIT_Getter

class AbcSetterTrait(AbcMethodTrait):
    KIND = TRAIT_Setter

TRAIT_KINDS = {0: AbcSlotTrait,
               1: AbcMethodTrait,
               2: AbcGetterTrait,
               3: AbcSetterTrait,
               4: AbcClassTrait,
               5: AbcFunctionTrait,
               6: AbcConstTrait}
