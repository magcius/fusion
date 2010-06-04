
from mech.fusion.swf import SwfData

swf = SwfData()
shape = swf.new_shape()
shape.graphics.lineStyle(3)
shape.graphics.moveTo(100, 100)
shape.graphics.lineTo(-100, -100)
shape2 = swf.new_shape()
shape2.graphics.lineStyle(3)
shape2.graphics.moveTo(-5119, -6749)
shape2.graphics.lineTo(-5119, -6749)
shape2.graphics.lineTo(-5094, -6717)
shape2.graphics.lineTo(-5069, -6686)
swf.next_frame()

f = open('shape_example.swf', 'wb')
f.write(swf.serialize())
f.close()
