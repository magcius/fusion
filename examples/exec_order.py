
from mech.fusion.swf import SwfData, tags
from mech.fusion.swf.records import Rect, RGBA
from mech.fusion.avm2.abc_ import AbcFile
from mech.fusion.avm2.constants import packagedQName

def print_(gen, S):
    gen.emit('debugfile', "Print.as")
    gen.emit('debugline', 5)
    gen.emit('findpropstrict', "trace")
    gen.load(S)
    gen.emit('callpropvoid', "trace", 1)

def script_(gen, base):
    gen.context.new_script()
    gen.context.make_init()
    gen.emit('debugfile', base+".as")
    gen.emit('debugline', 10)
    print_(gen, "Running " + base)
    gen.exit_context()
    for i in xrange(3):
        name = "%s__%d" % (base, i)
        with gen.Class(name):
            with gen.Constructor():
                gen.emit('debugline', 10+i*5)
                print_(gen, name +" Constructor")
    gen.exit_context()

def abc_(i):
    abc = AbcFile()
    gen = abc.create_generator(False)
    for j in xrange(3):
        script_(gen, "ABC%d__Script%d" % (i, j))
    gen.finish()
    return abc

swf = SwfData()
swf.add_tag(tags.FileAttributes())
swf.add_tag(tags.EnableDebugger2())
swf.add_tag(tags.SetBackgroundColor(0x333333))
swf.add_tag(tags.DefineEditText(Rect(0, 0, 600, 400), "bb", "Testing script order.", color=RGBA(0xFFFFFF)))
swf.add_tag(tags.PlaceObject2(1, 0))

abc = abc_(1)
swf.add_tag(tags.DoABC("ABC1", abc))

abc = abc_(2)
swf.add_tag(tags.DoABC("ABC2", abc, flags=1))

abc = abc_(3)
swf.add_tag(tags.DoABCDefine(abc))

abc = AbcFile()
gen = abc.create_generator(False)
gen.context.new_script()
with gen.Class("Main", packagedQName("flash.display", "Sprite")):
    with gen.Constructor():
        print_(gen, "Main Constructor")
        gen.load("ABC0__Script0")

gen.finish()
swf.add_tag(tags.DoABC("Main", abc))
swf.add_tag(tags.SymbolClass({0:"Main"}))
swf.add_tag(tags.ShowFrame())
swf.add_tag(tags.End())

f = open("script_order.swf", "wb")
f.write(swf.serialize())
f.close()
