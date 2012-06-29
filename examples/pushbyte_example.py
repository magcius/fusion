
from mech.fusion.avm2.abc_ import AbcFile
from mech.fusion.avm2.instructions import pushbyte

abc = AbcFile()
gen = abc.create_generator()
gen.script0.make_init()
gen.I(pushbyte(255))
abc.serialize()
gen.finish()

f = open("pushbyte.abc", "wb")
f.write(abc.serialize())
f.close()
