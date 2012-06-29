
from fusion.avm2.instructions import get_instruction

def group(L, offset=2, sentinel=None):
    """
    group([1, 2, 3]) => [(1, 2), (2, 3), (3, None)]
    """
    L += [sentinel]
    return zip(*[L[i:] for i in xrange(offset)])

class LocalInstructionOptimizer(object):
    """
    Optimizes getlocal 0-3 into their single-opcode variants.
    """

    def optimize(self, instructions):
        for i, inst in enumerate(instructions):
            if inst.name in ("getlocal", "setlocal") and 0 <= inst.argument < 4:
                new_instruction = "%s%s" % (inst.name, inst.argument)
                instructions[i] = get_instruction(new_instruction)()
        return instructions

class BranchOptimizer(object):
    """
    A set of branch optimizations geared towards the PyPy
    code generator.
    """

    branches = {
        ("not",            "iftrue"):  "iffalse",
        ("not",            "iffalse"): "iftrue",
        ("equals",         "iftrue"):  "ifeq",
        ("equals",         "iffalse"): "ifne",
        ("lessthan",       "iftrue"):  "iflt",
        ("lessthan",       "iffalse"): "ifnlt",
        ("lessequals",     "iftrue"):  "ifle",
        ("lessequals",     "iffalse"): "ifnle",
        ("greaterthan",    "iftrue"):  "ifgt",
        ("greaterthan",    "iffalse"): "ifngt",
        ("greaterequals",  "iftrue"):  "ifge",
        ("greaterequals",  "iffalse"): "ifnge",
        ("strictequals",   "iftrue"):  "ifstricteq",
        ("strictequals",   "iffalse"): "ifstrictne",
    }

    def optimize(self, instructions):
        new_instructions = []
        for inst1, inst2 in group(instructions):
            if inst1 is None or inst2 is None:
                continue

            key = inst1.name, inst2.name
            if key in self.branches:
                combined = get_instruction(self.branches[key])
                new_instructions.append(combined(inst2.labelname))
            else:
                new_instructions.append(inst1)

        return new_instructions
