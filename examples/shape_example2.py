
from fusion.swf.swfdata import SwfData
from fusion.swf.tags import DefineSprite

swf = SwfData(fps=1)

shape = swf.new_shape()
shape.graphics.lineStyle(10)
shape.graphics.moveTo(0, 0)
shape.graphics.lineTo(10, 10)
obj = swf.place(shape)
swf.next_frame()

for i in xrange(1, 11):
    obj.moveTo(10*i, 10*i)
    swf.next_frame()

obj.remove()

f = open('shape_example2.swf', 'wb')
f.write(swf.serialize())
f.close()
