
import struct

from fusion.bitstream.formats import CString
from fusion.bitstream.flash_formats import UI32, Byte

class VersionCommand(object):
    pointer_size = None

    # Pointer size can be 4 for the 32-bit player,
    # or 8 for the 64-bit player.
    def parse(self, context, data):
        self.player_version = data.read(UI32)
        if data.bits_available >= 8:
            self.pointer_size = data.read(Byte)

    def handle(self, context):
        context.player_version = self.player_version
        if self.pointer_size:
            context.pointer_size = self.pointer_size

class BaseFault(object):
    def __init__(self, context, data):
        pass

class InvalidWith(BaseFault):
    pass

class RecursionLimitHit(BaseFault):
    pass

class ProtoLimitHit(BaseFault):
    pass


class InvalidURL(BaseFault):
    def __init__(self, context, data):
        self.url = data.read(CString)

class InvalidTarget(BaseFault):
    def __init__(self, context, data):
        self.name = data.read(CString)

class FaultBaseCommand(object):
    def handle(self, context):
        context.handle_fault(self._fault)

class ExceptionFault(object):
    def __init__(self, message, caught, thrown):
        self.message = message
        self.caught = caught
        self.thrown = thrown

class ExceptionCommand(FaultBaseCommand):
    def parse(self, context, data):
        data.read(UI32) # offset - ignored

        message, caught, thrown = "", False, None

        # AVM+ will throw the toString() of the exception.
        if data.bits_available > 0:
            message = data.read(CString)
            if data.bits_available > 0:
                if data.read(Byte):
                    caught = bool(data.read(Byte))
                    context.get_pointer(data) # Skip a pointer, unknown.
                    thrown_var = context.get_variable(data)
                    thrown = thrown_var.get_value(context)

        self._fault = ExceptionFault(message, caught, thrown)

class OutGetVariableCommand(object):

    InvokeGetter      = 0x01
    AlsoGetChildren   = 0x02
    DontGetFunctions  = 0x04
    GetClassHierarchy = 0x08

    flags = 0

    def __init__(self, addr, name, flags=0):
        self.addr, self.name, self.iflags = addr, name, flags

    def build(self, context):
        data  = struct.pack("<L", self.command_id)
        data += context.build_pointer(self.addr)
        data += self.name + "\0"

        # XXX -- cheating with the command ID
        flags = self.flags | self.iflags
        data += struct.pack("<L", flags)

        return data

class InGetVariableCommand(object):
    def parse(self, context, data):
        parent, child = None, None
        currentclass, level, maxlevel = None, 0, 0

        classes = []

        # Build parent node.
        parentId = context.get_pointer(data)
        name = data.read(CString)
        parent = context.get_variable(data, name)

        while data.bits_available > 0:
            child = context.get_variable(data)
            # We're getting a class or instance slot here -- the fqn should
            # have the class's name.
            if child.is_traits:
                currentclass = child.fqname
                level = len(classes)

                static = False
                if currentclass.endswith("$"):
                    # We have a class object -- look for its associated
                    # instance.
                    instance = currentclass[:-1]
                    try:
                        level = classes.index(instance)
                    except ValueError:
                        pass
                    else:
                        currentclass = instance
                        static = True

                if not static:
                    # Nope. Not static. Add it.
                    classes.append(currentclass)
            else:
                # XXX: Handle dynamic
                child.level = min(255, level)
                child.definingclass = currentclass
                if currentclass:
                    maxlevel = max(level, maxlevel)

            context.add_member(parent, child)

class TraceCommand(object):
    def parse(self, context, data):
        self.message = data.read(CString)

    def handle(self, context):
        context.handle_trace(self.message)

class UnknownCommand(object):
    def __repr__(self):
        pass

def C(command_id, base=UnknownCommand, **kw):
    return command_id, base, kw

InCommands = dict(
    Unknown                     = C(-1),
    SetMenuState                = C(0),
    SetProperty                 = C(1),
    Exit                        = C(2),
    NewObject                   = C(3),
    RemoveObject                = C(4),
    Trace                       = C(5, base=TraceCommand),
    ErrorTarget                 = C(6, base=FaultBaseCommand, fault=InvalidTarget),
    ErrorExecLimit              = C(7, base=FaultBaseCommand, fault=RecursionLimitHit),
    ErrorWith                   = C(8, base=FaultBaseCommand, fault=InvalidWith),
    ErrorProtoLimit             = C(9, base=FaultBaseCommand, fault=ProtoLimitHit),
    SetVariable                 = C(10),
    DeleteVariable              = C(11),
    Param                       = C(12),
    PlaceObject                 = C(13),
    Script                      = C(14),
    AskBreakpoints              = C(15),
    BreakAt                     = C(16),
    Continue                    = C(17),
    SetLocalVariables           = C(18),
    SetBreakpoint               = C(19),
    NumScript                   = C(20),
    RemoveScript                = C(21),
    RemoveBreakpoint            = C(22),
    NotSynced                   = C(23),
    ErrorURLOpen                = C(24, base=FaultBaseCommand, fault=InvalidURL),
    ProcessTag                  = C(25),
    Version                     = C(26, base=VersionCommand),
    BreakAtExt                  = C(27),
    SetVariable2                = C(28),
    Squelch                     = C(29),
    GetVariable                 = C(30),
    Frame                       = C(31),
    Option                      = C(32),
    Watch                       = C(33),
    GetSwf                      = C(34),
    GetSwd                      = C(35),
    ErrorException              = C(36),
    ErrorStackUnderflow         = C(37),
    ErrorZeroDivide             = C(38),
    ErrorScriptStuck            = C(39),
    BreakReason                 = C(40),
    GetActions                  = C(41),
    SwfInfo                     = C(42),
    ConstantPool                = C(43),
    ErrorConsole                = C(44),
    GetFncNames                 = C(45),

    # 46 through 52 are for profiling.
    CallFunction                = C(54),
    Watch2                      = C(55),
    PassAllExceptionsToDebugger = C(56),
    BinaryOp                    = C(57),
)

OutCommands = dict(
    Unknown                       = -2,
    ZoomIn                        = 0,
    ZoomOut                       = 1,
    Zoom100                       = 2,
    Home                          = 3,
    SetQuality                    = 4,
    Play                          = 5,
    Loop                          = 6,
    Rewind                        = 7,
    Forward                       = 8,
    Back                          = 9,
    Print                         = 10,
    SetVariable                   = 11,
    SetProperty                   = 12,
    Exit                          = 13,
    SetFocus                      = 14,
    Continue                      = 15,
    StopDebug                     = 16,
    SetBreakpoints                = 17,
    RemoveBreakpoints             = 18,
    RemoveAllBreakpoints          = 19,
    StepOver                      = 20,
    StepInto                      = 21,
    StepOut                       = 22,
    ProcessedTag                  = 23,
    SetSquelch                    = 24,
    GetVariable                   = 25,
    GetFrame                      = 26,
    GetOption                     = 27,
    SetOption                     = 28,
    AddWatch                      = 29, # 16-bit ID, used for AS2
    RemoveWatch                   = 30, # 16-bit ID, used for AS2
    StepContinue                  = 31,
    GetSwf                        = 32,
    GetSwd                        = 33,
    GetVariableWhichInvokesGetter = 34,
    GetBreakReason                = 35,
    GetActions                    = 36,
    SetActions                    = 37,
    SwfInfo                       = 38,
    ConstantPool                  = 39,
    GetFncNames                   = 40,

    # 41 through 47 are for profiling
    CallFunction                  = 48,
    AddWatch2                     = 49, # 32-bit ID, used for AS3
    RemoveWatch2                  = 40, # 32-bit ID, used for AS3
    PassAllExceptionsToDebugger   = 51,
    BinaryOp                      = 52,
)

def _make_name_table(tbl):
    names = {}
    for name, (command_id, _, __) in tbl.iteritems():
        names[command_id] = name
    return names

InCommandNames = _make_name_table(InCommands)

## Public API.

_InCommandCache = {}

def get_in_command(commandid):
    if commandid not in _InCommandCache:
        name, base, kw = InCommands[commandid]

        command = type(name, (base,), kw)
        command.command_id = commandid
        command.name = name

        _InCommandCache[commandid] = command
    return _InCommandCache[commandid]

__all__ = ["get_in_command"]
