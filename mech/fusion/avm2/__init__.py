
"""
AVM2/Tamarin routines and work.
"""

from mech.fusion.avm2.library import get_playerglobal

playerglobal_lib = get_playerglobal()
playerglobal_lib.install_global(__name__+".playerglobal")
