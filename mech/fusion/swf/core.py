
from zope.interface import implements
from zope.component import adapter, provideAdapter

from mech.fusion.swf.interfaces import ISwfPart, IPlaceable
from mech.fusion.swf.tags import (ShowFrame, SwfTagNotAllowed,
    DefineShape4, PlaceObject2, RemoveObject2)
from mech.fusion.swf.records import (StraightEdgeRecord, CurvedEdgeRecord,
    StyleChangeRecord, LineStyle2, FillStyleSolidFill, ShapeWithStyle)

class SwfGraphicsEmulation(object):
    def __init__(self, owner):
        self.owner = owner
        self.last_x = 0
        self.last_y = 0

    def get_delta(self, new_x, new_y):
        delta = new_x - self.last_x, new_y - self.last_y
        self.last_x, self.last_y = new_x, new_y
        return delta

    def moveTo(self, x, y):
        self.owner.add_shape_record(StyleChangeRecord(*self.get_delta(x, y)))

    def curveTo(self, controlx, controly, anchorx, anchory):
        self.owner.add_shape_record(CurvedEdgeRecord(controlx-self.last_x,
            controly-self.last_y, *self.get_delta(anchorx, anchory)))

    def lineTo(self, x, y):
        self.owner.add_shape_record(StraightEdgeRecord(*self.get_delta(x, y)))

    def lineStyle(self, width, color=0, alpha=1, pixel_hinting=False,
                  scale_mode="normal", caps=None, joints=None, miter_limit=3):
        self.owner.add_shape_record(StyleChangeRecord(0, 0,
            LineStyle2(width, color, alpha, pixel_hinting)))

class SwfTagContainer(object):
    """
    A SwfTagContainer contains swf tags.
    """
    
    header = ""
    allowed_tags = None

    def __init__(self):
        self.tags = []

    def add_part(self, part):
        return ISwfPart(part).add_to(self)

    add_tag = add_part

    def add_raw_tag(self, tag):
        if self.allowed_tags and tag not in self.allowed_tags:
            raise SwfTagNotAllowed("The tag %s is not allowed in a %s"
                                   " container" % (tag, self))
        self.tags.append(tag)

    def serialize(self):
        return ''.join(tag.serialize() for tag in self.tags)

class SwfMovieClip(SwfTagContainer):
    """
    A SwfMovieClip is a tag container that
    has the concept of a stage, and frames.
    """
    implements(ISwfPart)
    def __init__(self, movie):
        super(SwfMovieClip, self).__init__()
        self.num_frames = 0
        self.depth = 1
        self.movie = movie

    @property
    def next_character_id(self):
        return self.movie._next_character_id

    @next_character_id.setter
    def next_character_id(self, value):
        self.movie._next_character_id = value

    def new_movie_clip(self):
        mc = SwfMovieClip(self.movie)
        self.add_part(mc)
        return mc

    def new_shape(self):
        shape = SwfShape()
        self.add_part(shape)
        return shape

    def next_frame(self):
        self.add_tag(ShowFrame())

    def place(self, obj):
        displayobject = SwfDisplayObject(self, IPlaceable(obj).characterid, self.depth)
        self.add_part(displayobject)
        self.depth += 1
        return displayobject

class SwfDisplayObject(object):
    def __init__(self, cont, charid, depth):
        self.cont, self.charid, self.depth = cont, charid, depth

    def remove(self):
        self.cont.add_tag(RemoveObject2(self.depth))

def swfdisplayobject_to_ipart(self):
    return PlaceObject2(self.depth, self.charid)

provideAdapter(swfdisplayobject_to_ipart, [SwfDisplayObject], ISwfPart)

class SwfShape(object):
    implements(ISwfPart)
    def __init__(self):
        self.shape = ShapeWithStyle()
        self.graphics = SwfGraphicsEmulation(self.shape)

    def add_to(self, data):
        # TODO: account for SWF version
        data.add_tag(DefineShape4(self.shape))

def swfshape_to_iplaceable(self):
    return self.shape

provideAdapter(swfshape_to_iplaceable, [SwfShape], IPlaceable)