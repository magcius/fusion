
from fusion.bitstream.formats import FloatFormat, FixedFormat, U32, S32, SignedByte, Byte, CUTF8

FLOAT16    = FloatFormat[16:"<":"FLOAT16"]
FLOAT      = FloatFormat[32:"<":"FLOAT"]
DOUBLE     = FloatFormat[64:"<":"DOUBLE"]

FIXED8     = FixedFormat[16:"<":"FIXED8"]
FIXED      = FixedFormat[32:"<":"FIXED"]

SI8        = SignedByte[1:"<":"SI8"]
SI16       = SignedByte[2:"<":"SI16"]
SI24       = SignedByte[3:"<":"SI24"]
SI32       = SignedByte[4:"<":"SI32"]

UI8        = Byte[1:"<":"UI8"]
UI16       = Byte[2:"<":"UI16"]
UI24       = Byte[3:"<":"UI24"]
UI32       = Byte[4:"<":"UI32"]
UI64       = Byte[8:"<":"UI64"]

STRING     = CUTF8
EncodedU32 = U32
