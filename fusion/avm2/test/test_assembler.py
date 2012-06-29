
from fusion.avm2 import assembler, constants

def assemble(asm):
    const = constants.ConstantPool()
    const.write(asm)

    asm.pass1()
    return const, asm.serialize()

def test_nothing_function():
    asm = assembler.CodeAssembler([])
    asm.emit("getlocal0")
    asm.emit("pushscope")
    asm.emit("returnvoid")

    _, bytes = assemble(asm)
    assert bytes == "\xd0\x30\x47"

def test_push_pool():
    asm = assembler.CodeAssembler([])
    asm.emit("getlocal0")
    asm.emit("pushscope")

    asm.emit("pushstring", "This is the string that never ends...")
    asm.emit("pushint", -16384)
    asm.emit("pushuint", 32768)
    asm.emit("pushdouble", 5000.0)
    asm.emit("returnvoid")

    # These instructions should all be index 1.
    _, bytes = assemble(asm)
    assert bytes == ("\xd0\x30" # getlocal0, pushscope
                     "\x2c\x01" # pushstring, index 1
                     "\x2d\x01" # pushint   , index 1
                     "\x2e\x01" # pushuint  , index 1
                     "\x2f\x01" # pushdouble, index 1
                     "\x47")    # returnvoid


def test_jumping():
    asm = assembler.CodeAssembler([])

