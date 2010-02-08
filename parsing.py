
from mech.fusion.swf.swfdata import SwfData

swf = SwfData.parse_filename("example.swf")
print swf.tags
