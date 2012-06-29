
import os

from fusion.bitstream.bitstream import BitStream
from fusion.bitstream.formats import U32, Bit, UB
from fusion.bitstream.flash_formats import UI8

from fusion.avm2.interfaces import IMultiname, IConstantPoolWriter, IAbcContainer
from fusion.avm2.util import serialize_u32 as s_u32

from zope.interface import implements

class TraitKinds(object):
    Slot     = 0
    Method   = 1
    Getter   = 2
    Setter   = 3
    Class    = 4
    Function = 5
    Const    = 6

def parse_trait(bitstream, abc, constants):
    name = constants.multiname.value_at(bitstream.read(U32))

    bitstream.seek(1, os.SEEK_CUR)
    has_metadata = bitstream.read(Bit)
    override = bitstream.read(Bit)
    final = bitstream.read(Bit)

    kind = bitstream.read(UB[4])
    cls = Traits[kind]
    trait = cls.parse(bitstream, abc, constants)
    trait.name     = name
    trait.final    = final
    trait.override = override

    if has_metadata:
        L = xrange(bitstream.read(U32))
        trait.metadata = [abc.metadatas.value_at(bitstream.read(U32)) for i in L]

    return trait

def eval_traits(owner):
    # name -> SlotTrait
    fields     = {}

    # name -> MethodTrait
    methods    = {}

    # name -> [type, GetterTrait, SetterTrait]
    properties = {}

    for trait in owner.traits:
        trait.owner = owner
        if isinstance(trait, SlotTrait):
            fields[trait.name] = trait

        elif isinstance(trait, MethodTrait):
            method = trait.method

            method.trait = trait
            method.name  = trait.name
            method.owner = owner

            if isinstance(trait, GetterTrait):
                trait.type_name = method.return_type
                new_trait = [trait.type_name, None, None]
                properties.setdefault(trait.name, new_trait)[1] = trait

            elif isinstance(trait, SetterTrait):
                trait.type_name = method.param_types[0]
                new_trait = [trait.type_name, None, None]
                properties.setdefault(trait.name, new_trait)[2] = trait

            else:
                methods[trait.name] = trait

        elif isinstance(trait, ClassTrait):
            cls = trait.cls
            instance = cls.instance

            cls.name = trait.name
            cls.owner = owner
            cls.trait = trait
            instance.name = trait.name
            instance.owner = owner
            instance.trait = trait

    owner.fields     = fields
    owner.methods    = methods
    owner.properties = properties

class TraitBase(object):
    """
    Traits are things that specify ownership of a specific
    part elsewhere in the ABC file. Scripts, classes,
    instances and methods are all 'trait containers'.

    Script traits are usually only used in AS3 to hold
    a class trait, which will usually have the entry
    point of the script.

    Class traits are static traits, like static methods
    and slots.
    """

    implements(IConstantPoolWriter, IAbcContainer)
    kind = None
    def __init__(self, name, final=False, override=False):
        if name is not None:
            self.name = IMultiname(name)
        else:
            self.name = None
        self._name_index = None

        self.is_final = final
        self.is_override = override

        self.metadata = []
        self._metadata_indices = None

    def add_abc_elements(self, abc):
        self._metadata_indices = [abc.metadatas.index_for(m) for m in self.metadata]

    def write_constants(self, pool):
        self._name_index = pool.multiname.index_for(self.name)

    def serialize_inner(self):
        return ""

    def serialize(self):
        code = ""
        code += s_u32(self._name_index)

        flags = BitStream()
        flags.write(False)
        flags.write(bool(self.metadata)) # Has Metadata
        flags.write(self.is_override)    # Is Override
        flags.write(self.is_final)       # Is Final
        flags.write(self.kind, UB[4])    # kind

        code += flags.serialize()
        code += self.serialize_inner()

        if self.metadata:
            code += s_u32(len(self.metadata))
            for m in self._metadata_indices:
                code += s_u32(m)
        return code

class SlotTrait(TraitBase):
    """
    A `slot` trait is used to hold fields on something,
    like a "var".
    """
    kind = TraitKinds.Slot
    def __init__(self, name, type_name, default=None, slot_id=0):
        super(SlotTrait, self).__init__(name, False, False)
        self.slot_id = slot_id

        self.type_name = IMultiname(type_name)
        self._type_name_index = None

        self.default = default
        self._default_index = None
        self._default_kind  = None

    def write_constants(self, pool):
        super(SlotTrait, self).write_constants(pool)
        if self.default is None:
            self._default_index = 0
        else:
            self._default_kind, self._default_index = (self.value, pool)
            if self._default_index is None:
                self._default_index = self._default_kind

        self._type_name_index = pool.multiname.index_for(self.type_name)

    @classmethod
    def parse(cls, bitstream, abc, constants):
        slot_id   = bitstream.read(U32)
        type_name = constants.multiname.value_at(bitstream.read(U32))
        vindex    = bitstream.read(U32)
        value     = None

        if vindex:
            vkind = bitstream.read(UI8)
            value = None
            #value = abc_to_py((vindex, vkind), constants)

        return cls(None, type_name, value, slot_id)

    def serialize_inner(self):
        code = ""

        code += s_u32(self.slot_id)
        code += s_u32(self._type_name_index)
        code += s_u32(self._default_index)
        if self._default_index:
            code += s_u32(self._default_kind)

        return code

class ConstTrait(SlotTrait):
    """
    A `const` trait is like a `slot` trait, but cannot
    be set dynamically, it can only be initialized with
    `initproperty`.
    """
    kind = TraitKinds.Const

class ClassTrait(TraitBase):
    kind = TraitKinds.Class

    def __init__(self, name, cls, slot_id=0, final=False, override=False):
        super(ClassTrait, self).__init__(name, final, override)
        self.slot_id = slot_id
        self.cls = cls
        self._cls_index = None

    def add_abc_elements(self, abc):
        super(ClassTrait, self).add_abc_elements(abc)
        self._cls_index = abc.classes.index_for(self.cls)

    @classmethod
    def parse(cls, bitstream, abc, constants):
        slot_id = bitstream.read(U32)
        clazz   = abc.classes.value_at(bitstream.read(U32))
        return cls(None, clazz, slot_id)

    def serialize_inner(self):
        return s_u32(self.slot_id) + s_u32(self._cls_index)

class MethodTrait(TraitBase):
    kind = TraitKinds.Method
    def __init__(self, name, method, disp_id=0, final=False, override=False):
        super(MethodTrait, self).__init__(name, final, override)
        self.disp_id = disp_id

        self.method = method
        self._method_index = None

    def add_abc_elements(self, abc):
        super(MethodTrait, self).add_abc_elements(abc)
        self._method_index = abc.methods.index_for(self.method)

    @classmethod
    def parse(cls, bitstream, abc, constants):
        disp_id = bitstream.read(U32)
        method = abc.methods.value_at(bitstream.read(U32))
        return cls(None, method, disp_id)

    def serialize_inner(self):
        return s_u32(self.disp_id) + s_u32(self._method_index)

class GetterTrait(MethodTrait):
    kind = TraitKinds.Getter

class SetterTrait(MethodTrait):
    kind = TraitKinds.Setter

class FunctionTrait(TraitBase):
    kind = TraitKinds.Function
    def __init__(self, name, function, slot_id=0):
        super(FunctionTrait, self).__init__(name, False, False)
        self.slot_id = slot_id

        self.function = function
        self._function_index = None

    def add_abc_elements(self, abc):
        super(FunctionTrait, self).add_abc_elements(abc)
        self._function_index = abc.methods.index_for(self.function)

    @classmethod
    def parse(cls, bitstream, abc, constants):
        slot_id  = bitstream.read(U32)
        function = abc.methods.value_at(bitstream.read(U32))
        return cls(None, function, slot_id)

    def serialize_inner(self):
        return s_u32(self.slot_id) + s_u32(self._function_index)

Traits = [SlotTrait, MethodTrait, GetterTrait,
          SetterTrait, ClassTrait, FunctionTrait,
          ConstTrait]
