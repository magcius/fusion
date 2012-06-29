
from zope.interface import implements
from zope.component import adapter, provideAdapter

from fusion.swf.interfaces import ISwfPart, IPlaceable
from fusion.swf.tags import (ShowFrame, SwfTagNotAllowed,
    DefineShape4, PlaceObject2, RemoveObject2, End)
from fusion.swf.records import (StraightEdgeRecord, CurvedEdgeRecord,
    StyleChangeRecord, LineStyle2, FillStyleSolidFill, ShapeWithStyle,
    Matrix)

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
        delta = self.get_delta(x, y)
        if delta != (0, 0):
            self.owner.add_shape_record(StyleChangeRecord(*delta))

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
        data = ''.join(tag.serialize() for tag in self.tags)
        # Make sure there is an end.
        if not isinstance(self.tags[-1], End):
            data += "\0\0"
        return data

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
        self.placed_parts = []

    def get_next_charid(self):
        return self.movie._next_character_id

    def set_next_charid(self, value):
        self.movie._next_character_id = value

    next_character_id = property(get_next_charid, set_next_charid)

    def new_movie_clip(self):
        mc = SwfMovieClip(self.movie)
        self.add_part(mc)
        return mc

    def new_shape(self):
        shape = SwfShape()
        self.add_part(shape)
        return shape

    def next_frame(self):
        for part in self.placed_parts:
            if part.update:
                self.add_part(part)

        self.add_tag(ShowFrame())

    def place(self, obj):
        displayobject = SwfDisplayObject(self, IPlaceable(obj).characterid, self.depth)
        self.placed_parts.append(displayobject)
        self.add_part(displayobject)
        self.depth += 1
        return displayobject

class SwfDisplayObject(object):
    def __init__(self, cont, charid, depth):
        self.cont, self.charid, self.depth = cont, charid, depth
        self.update, self._matrix = False, Matrix()

    def _get_x(self):
        return self._matrix.tx

    def _set_x(self, x):
        self._matrix.tx = x
        self.update = True

    x = property(_get_x, _set_x)

    def _get_y(self):
        return self._matrix.ty

    def _set_y(self, y):
        self._matrix.ty = y
        self.update = True

    y = property(_get_y, _set_y)

    def moveTo(self, x, y):
        self._matrix.tx = x
        self._matrix.ty = y
        self.update = True

    def _get_scaleX(self):
        return self._matrix.a

    def _set_scaleX(self, a):
        self._matrix.a = a
        self.update = True

    scaleX = property(_get_scaleX, _set_scaleX)

    def _get_scaleY(self):
        return self._matrix.d

    def _set_scaleY(self, d):
        self._matrix.d = d
        self.update = True

    scaleY = property(_get_scaleY, _set_scaleY)

    def remove(self):
        self.cont.placed_parts.remove(self)
        self.cont.add_tag(RemoveObject2(self.depth))

def swfdisplayobject_to_ipart(self):
    tag = PlaceObject2(self.depth, self.charid)
    if self.update:
        self.update = False
        tag.update = True
        tag.transform.a = self._matrix.a
        tag.transform.b = self._matrix.b
        tag.transform.c = self._matrix.c
        tag.transform.d = self._matrix.d
        tag.transform.tx = self._matrix.tx
        tag.transform.ty = self._matrix.ty
    return tag

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
