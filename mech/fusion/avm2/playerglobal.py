import sys
from mech.fusion.avm2.library import get_playerglobal
playerglobal = get_playerglobal()
sys.modules[__name__] = playerglobal
