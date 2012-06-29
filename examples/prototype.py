
from fusion.avm2.abc_ import AbcFile
from fusion.avm2.constants import packagedQName

abc = AbcFile()
gen = abc.create_generator()
with gen.Class("testing"):
    pass
gen.script0.make_init()
gen.emit('findpropstrict', "print")
gen.emit('findpropstrict', "testing")
gen.emit('constructprop', "testing", 0)
gen.gettype()
gen.emit('callpropvoid', "print", 1)
gen.finish()
abc.serialize()

f = open("prototype.abc", "wb")
f.write(abc.serialize())
f.close()
