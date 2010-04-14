
from mech.fusion.swf.swfdata import SwfData
from mech.fusion.swf.tags import (FileAttributes, SetBackgroundColor,
                                  DefineEditText, PlaceObject2, DoABC,
                                  SymbolClass, ShowFrame, End)
from mech.fusion.swf.records import RGBA, Rect

from mech.fusion.avm2.constants import QName
from mech.fusion.avm2.abc_ import AbcFile
from mech.fusion.avm2.traits import AbcSlotTrait
from mech.fusion.avm2.playerglobal import flash

swf = SwfData()
swf.add_tag(FileAttributes())
swf.add_tag(SetBackgroundColor(0x333333))
swf.add_tag(DefineEditText(Rect(0, 0, 600, 400), "tt",
                             "Testing drawing circles.", color=RGBA(0xFFFFFF)))
swf.add_tag(PlaceObject2(1, 2, name="edittext"))
abc = DoABC()
actions = abc.create_generator()

swf.add_tag(abc)
swf.add_tag(SymbolClass({0:"Example3EntryPoint"}))
swf.add_tag(ShowFrame())
swf.add_tag(End())

with actions.Class("Example3EntryPoint", flash.display.Sprite) as cls:
    cls.add_instance_trait(AbcSlotTrait('edittext', flash.text.TextField))
    with actions.Constructor():
        actions.push_this()
        actions.get_field("graphics")
        actions.dup()
        actions.dup()
        actions.dup()
        actions.call_method_constargs("lineStyle", 3, void=True)
        actions.call_method_constargs("beginFill", 0xFF0000, void=True)
        actions.call_method_constargs("drawCircle", 10, 20, 30, void=True)
        actions.call_method_constargs("endFill", void=True)

actions.finish()

f = open("example3.abc", "wb")
f.write(AbcFile.serialize(abc))
f.close()

f = open("example3.swf", "wb")
f.write(swf.serialize())
f.close()

