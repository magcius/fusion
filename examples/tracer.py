
from fusion.swf.swfdata import SwfData
from fusion.swf.records import Rect, RGBA
from fusion.swf import tags

from fusion.avm2.abc_ import AbcFile
from fusion.avm2.node import export_function, INode, Slot
from fusion.avm2.loadable import Chain, This, Field, Stack, Local
from fusion.avm2.playerglobal import flash

swf = SwfData()

abc = AbcFile()
gen = abc.create_generator()

@export_function(["Object", flash.text.TextField], rettype="void")
def dump(gen, params, tracer):
    gen.load(0)
    gen.emit('convert_i')
    index_reg = gen.store_var("idx")
    params_reg = params.get_index(gen)

    gen.set_label("loop")

    gen.emit('hasnext2', params_reg, index_reg)
    gen.branch_if_false("done")

    gen.load(params)
    gen.load(Local("idx"))
    gen.emit('nextname')
    gen.load("=")
    gen.emit('add')

    gen.load(params)
    gen.load(Local("idx"))
    gen.emit('nextvalue')
    gen.emit('add')
    gen.store_var("disp")
    gen.call_function("ktrace", [Local("disp"), tracer], void=True)

    gen.branch_unconditionally("loop")

    gen.set_label("done")

@export_function(["String", flash.text.TextField], rettype="void")
def ktrace(gen, S, tracer):
    gen.load(S)
    gen.load("\n")
    gen.emit('add')
    gen.store_var("S")
    gen.call_method("appendText", tracer, [Local("S")])
    gen.call_function("trace", [Local("S")])

class Main(INode(flash.display.MovieClip)):
    tracer = Slot(flash.text.TextField)
    def __iinit__(self, gen):
        # Standard prologue
        gen.emit('getlocal0')
        gen.emit('constructsuper', 0)

        dump(gen, Chain(This, Field("root"), Field("loaderInfo"), Field("parameters")), self.tracer)

gen.add_node(Main)
gen.add_node(dump)
gen.add_node(ktrace)
gen.render_nodes()
gen.finish()

swf.add_tag(tags.FileAttributes())
swf.add_tag(tags.DoABC("Main", abc))
swf.add_tag(tags.SymbolClass({0:"Main"}))
swf.add_tag(tags.DefineEditText(Rect(0, 0, 600, 400), "tracer", "", color=RGBA(0x000000)))
swf.add_tag(tags.PlaceObject2(0, 1, name="tracer"))
swf.add_tag(tags.ShowFrame())
swf.add_tag(tags.End())

with open("tracer.swf", "wb") as f:
    f.write(swf.serialize())
