
from fusion.avm2 import optimizer, assembler

def test_branch_optimizer():
    asm = assembler.CodeAssembler([])
    asm.emit("getlocal0")
    asm.emit("pushscope")
    asm.emit("pushtrue")
    asm.emit("not")
    asm.emit("iftrue", "blank")

    opz = optimizer.BranchOptimizer()
    instructions = opz.optimize(asm.instructions)

    names = [inst.name for inst in instructions]

    assert names == ["getlocal0", "pushscope", "pushtrue", "iffalse"]

