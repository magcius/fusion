
from mech.fusion.avm2.constants import QName
from mech.fusion.avm2.abc_ import AbcFile
from mech.fusion.avm2.node import Slot, export_method, convert_package
from mech.fusion.avm2.traits import AbcSlotTrait

from mech.fusion.avm2 import playerglobal
flash = convert_package(playerglobal.flash)

class NodeAPIExampleEntryPoint(flash.display.Sprite):
    edittext = Slot(flash.text.TextField)
    def __iinit__(self, asm):
        self.graphics.lineStyle(asm, 3)
        self.graphics.beginFill(asm, 0xFF0000)
        self.draw_circle(asm, 10, 20, 30)
        self.graphics.endFill(asm)

    @export_method(["int", "int", "int"], "void")
    def draw_circle(self, asm, x, y, radius):
        asm.push_this()
        asm.get_field("graphics")
        asm.call_method_constargs("drawCircle", x, y, radius, void=True)

abc = AbcFile()
generator = abc.create_generator()
generator.add_node(NodeAPIExampleEntryPoint)
generator.finish()

f = open("node_api_example.abc", "wb")
f.write(AbcFile.serialize(abc))
f.close()
