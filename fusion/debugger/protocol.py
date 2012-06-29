
import collections
import struct

from fusion.bitstream.bitstream import BitStream
from fusion.debugger import commands

from twisted.internet import protocol

class DebugProtocol(protocol.Protocol):
    """
    Flash's debugger protocol.
    """

    recvd = ""
    headerStruct = struct.Struct(">LL")
    headerSize = headerStruct.sizeof()

    def __init__(self, context):
        self._commandQueue = collections.deque()
        self.context = context

    def dataReceived(self, data):
        self.recvd = self.recvd + data
        while len(self.recvd) >= self.headerSize:
            header = self.recvd[:self.headerSize]
            length, commandid = self.headerSize.unpack(header)
            if len(self.recvd) < self.headerSize+length:
                break
            data = self.recvd[self.headerSize:self.headerSize+length]

            command = commands.get_in_command(commandid)()
            command.raw_data = data
            command.data = BitStream(data)
            self.commandReceived(command)

    def sendCommand(self, command):
        data = command.build(self.context)
        header = self.headerStruct.pack(len(data), command.command_id)
        self.transport.write(header + data)

    def queueCommandResponse(self, commandid, deferred):
        self._commandQueue.append((commandid, deferred))

    def commandReceived(self, command):
        command.parse(self.context, command.data)
        commandid, deferred = self._commandQueue.popleft()
        if commandid == command.command_id:
            deferred.callback(command)

        command.handle(self.context)
