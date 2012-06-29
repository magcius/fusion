
from mech.fusion.avm2.abc_ import AbcFile
from mech.fusion.avm2.constants import packagedQName

req = packagedQName("flash.net", "URLRequest")

abc = AbcFile()
gen = abc.create_generator()
gen.script0.make_init()
gen.emit("findpropstrict", req)
gen.load("http://example.com")
gen.emit("constructprop", req, 1)
gen.finish()
abc.serialize()

f = open("urlreq.abc", "wb")
f.write(abc.serialize())
f.close()
