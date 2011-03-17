
from fusion.avm2 import assembler, constants

def test_simple():
    asm = assembler.CodeAssembler([])
    asm.emit("pushint", 25)
    asm.emit("pushstring", "Hello")

    const = constants.ConstantPool()
    const.write(asm)

    assert const.int.value_at(1) == 25
    assert const.utf8.value_at(1) == "Hello"

def test_serialization():
    asm = assembler.CodeAssembler([])
    asm.emit("pushint", 25)
    asm.emit("pushstring", "Hello")

    const = constants.ConstantPool()
    const.write(asm)
    bytes = const.serialize()

    assert bytes == ("\x02\x19"      # int
                     "\x01\x01"      # uint, double
                     "\x02\x05Hello" # utf8
                     "\x01\x01\x01") # namespace, nsset, mn

def test_defaults():
    asm = assembler.CodeAssembler([])
    pi = asm.emit("pushint", 0)
    pu = asm.emit("pushuint", 0)
    pd = asm.emit("pushdouble", float('nan'))
    ps = asm.emit("pushstring", "")

    const = constants.ConstantPool()
    const.write(asm)

    assert pi._arg_index == 0
    assert pu._arg_index == 0

    # NaN is a tricky situation in ValuePools.
    assert pd._arg_index == 0

    # "" should be assigned to 1 in the case of pushstring.
    assert ps._arg_index == 1

def test_conflicts():
    asm = assembler.CodeAssembler([])
    inst1 = asm.emit("pushint", 25)
    inst2 = asm.emit("pushint", 25)

    assert inst1 is not inst2

    const = constants.ConstantPool()
    const.write(asm)

    assert inst1._arg_index == 1
    assert inst2._arg_index == 1

def test_multinames():
    asm = assembler.CodeAssembler([])
    asm.emit("getlex", "String")

    const = constants.ConstantPool()
    const.write(asm)

    assert const.multiname.value_at(1) == constants.QName("String")
