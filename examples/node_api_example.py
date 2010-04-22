
from mech.fusion.swf.swfdata import SwfData
from mech.fusion.swf.tags import (FileAttributes, SetBackgroundColor,
                                  DefineEditText, PlaceObject2, DoABC,
                                  SymbolClass, ShowFrame, End)
from mech.fusion.swf.records import RGBA, Rect

from mech.fusion.avm2.constants import QName
from mech.fusion.avm2.abc_ import AbcFile
from mech.fusion.avm2.node import Slot, export_method, convert_package
from mech.fusion.avm2.traits import AbcSlotTrait

from mech.fusion.avm2 import playerglobal
flash = convert_package(playerglobal.flash)

swf = SwfData()
swf.add_tag(FileAttributes())
swf.add_tag(SetBackgroundColor(0x333333))
swf.add_tag(DefineEditText(Rect(0, 0, 600, 400), "tt",
                             "Testing drawing circles.", color=RGBA(0xFFFFFF)))
swf.add_tag(PlaceObject2(1, 2, name="edittext"))
abc = DoABC()
generator = abc.create_generator()

swf.add_tag(abc)
swf.add_tag(SymbolClass({0:"Example3EntryPoint"}))
swf.add_tag(ShowFrame())
swf.add_tag(End())

class Example3EntryPoint(flash.display.Sprite):
    edittext = Slot(flash.text.TextField)
    def __iinit__(self, asm):
        asm.push_this()
        asm.get_field("graphics")
        asm.dup()
        asm.dup()
        asm.call_method_constargs("lineStyle", 3, void=True)
        asm.call_method_constargs("beginFill", 0xFF0000, void=True)
        self.draw_circle(asm, 10, 20, 30)
        asm.call_method_constargs("endFill", void=True)

    @export_method(["int", "int", "int"], "void")
    def draw_circle(self, asm, x, y, radius):
        asm.push_this()
        asm.get_field("graphics")
        asm.call_method_constargs("drawCircle", x, y, radius, void=True)

generator.add_node(Example3EntryPoint)
generator.finish()

f = open("node_api_example.abc", "wb")
f.write(AbcFile.serialize(abc))
f.close()

f = open("node_api_example.swf", "wb")
f.write(swf.serialize())
f.close()
