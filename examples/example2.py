
from mech.fusion.swf.swfdump import dump_abc
from mech.fusion.avm2.abc_ import AbcFile
from mech.fusion.avm2.constants import packagedQName
 
abc = AbcFile()
gen = abc.create_generator()
with gen.Class(packagedQName("foo.bar", "WhatUpHomies")):
    with gen.Constructor():
        gen.load("I'm on a ")
        gen.push_this()
        gen.get_field("vehicle")
        gen.emit('add')
        gen.load("!")
        gen.emit('add')
        gen.call_function("trace", 1)
    with gen.Method("vehicle", kind="getter", returntype="String"):
        gen.load("boat")
        gen.return_value()
gen.finish()
with open("example2.abc", "wb") as f:
    f.write(abc.serialize())

abc = AbcFile.from_filename("example2.abc")
dump_abc(abc)
