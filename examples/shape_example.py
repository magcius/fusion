
from mech.fusion.swf import SwfData

swf = SwfData()
shape = swf.new_shape()
shape.graphics.lineStyle(3)
shape.graphics.moveTo(100, 100)
shape.graphics.lineTo(-100, -100)
swf.next_frame()

f = open('shape_example.swf', 'wb')
f.write(swf.serialize())
f.close()
