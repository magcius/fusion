
import struct

from fusion.avm2.constants import undefined
from fusion.bitstream.formats import CString
from fusion.bitstream.flash_formats import UI16, UI32, Byte

from fusion.debugger import atoms, commands

def convert_player_URI(uri):
    # The player sends us a URI using '|' instead of ':'
    return uri.replace("|", ":")

class Context(object):
    def __init__(self):
        self.pointer_size = 4
        self.player_version = None
        self.values = {}
        self.protocol = None

    def fetch_variable(self, valueid, name, getters, children):
        flags = commands.OutGetVariableCommand.DontGetFunctions

        if getters:
            flags |= commands.OutGetVariableCommand.InvokeGetter
        if children:
            flags |= commands.OutGetVariableCommand.AlsoGetChildren
            flags |= commands.OutGetVariableCommand.GetClassHierarchy

        command = commands.OutGetVariableCommand(valueid, name, flags)
        self.protocol.sendCommand(command)

    def get_value(self, valueid):
        return self.values.setdefault(id, atoms.DebugValue.for_pointer(valueid))

    def get_pointer(self, data):
        return data.read(Byte[self.pointer_size*8])

    def build_pointer(self, addr):
        if self.pointer_size == 8:
            return struct.pack("<Q", addr)
        else:
            return struct.pack("<L", addr)

    def get_variable(self, data, name=None):
        if name is None:
            name = data.read(CString)

        otype, flags = data.read(UI16), data.read(UI32)
        return self.get_atom(data, name, otype, flags)

    def get_register(self, data, idx):
        otype = data.read(UI16)
        return self.get_atom(data, "$%s" % (idx,), otype, 0)

    def get_atom(self, data, name, objtype, flags):
        """
        Does the dirty work of making a variable based on the type of object.
        """

        # Here be spaghetti.

        primitives = {
            atoms.AtomTypes.NumberType: lambda: float(data.read(CString)),
            atoms.AtomTypes.BooleanType: lambda: bool(data.read(Byte)),
            atoms.AtomTypes.StringType: lambda: data.read(CString),
            atoms.AtomTypes.NullType: lambda: None,
            atoms.AtomTypes.UndefinedType: lambda: undefined,
        }

        if objtype in primitives:
            value = primitives[objtype]()
            vtype = atoms.VariableTypes.from_atom(objtype, False)
            typename = atoms.VariableTypes.get_name(vtype)
            debugval = atoms.DebugValue(vtype, typename, "", 0, value)

        elif objtype in (atoms.AtomTypes.ObjectType, atoms.AtomTypes.NamespaceType):
            objID = self.get_pointer(data)
            classtype, isfunc, typename = 0, 0, ""
            if objID != -1:
                classtype = data.read(UI32)
                isfunc = data.read(UI16)
                data.read(UI16) # rsvd - ignored.
                typename = data.read(CString)

            classname = atoms.AVM1ClassTypes.get_classname(classtype, False)
            vtype = atoms.VariableTypes.Function if isfunc else atoms.VariableTypes.Object
            debugval = atoms.DebugValue(vtype, typename, classname, flags,
                                        atoms.PointerValue(objID))

        elif objtype == atoms.AtomTypes.MovieClipType:
            objID = self.get_pointer(data)
            classtype, typename = 0, ""
            if objID != -1:
                classtype = data.read(UI32)
                data.read(UI16) # rsvd - ignored.
                typename = data.read(CString)

            classname = atoms.AVM1ClassTypes.get_classname(classtype, True)
            debugval = atoms.DebugValue(atoms.VariableTypes.MovieClip,
                                        typename, classname, flags,
                                        atoms.PointerValue(objID))

        elif objtype == atoms.AtomTypes.TraitsType:
            debugval = atoms.DebugValue(atoms.VariableTypes.Unknown,
                                        "traits", "", flags, None)

        return atoms.DebugVariable(name, debugval)
