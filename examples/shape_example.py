
from fusion.swf.swfdata import SwfData
from fusion.swf.tags import DefineSprite

swf = SwfData()

for i in xrange(10):
    shape = swf.new_shape()
    shape.graphics.lineStyle(3)
    shape.graphics.moveTo(0, 0)
    shape.graphics.lineTo(10*i, 10*i)
    obj = swf.place(shape)
    swf.next_frame()
    obj.remove()

f = open('shape_example.swf', 'wb')
f.write(swf.serialize())
f.close()
