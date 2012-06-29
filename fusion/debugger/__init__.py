"""
The Flash debugger protocol.

This code is heavily based on the (probably unintentionally)
open-source `Flex Debugger found in the Flex SDK`_.

I say unintentionally because there's a surprising amount of player
code pasted inside comments, or a direct filename reference (splay.h
is mentioned several times).

Indeed, when talking with Jeff Dyer from Adobe, he admitted that the
entire SDK was originally C++, but was ported to Java due to
Macromedia's need for a server-based Flex product.

ASC_, the Java-based ActionScript Compiler, indeed appears to be that
way.  Several headers have documentation that are in a strange,
foreign C++ format, not JavaDocs, and several files explicitly mention
that they were part of "Parser.cpp". ASC, here, looks to be the code
for the AS2 compiler, ported to Java and then improved to spit out
ABC. And indeed, according to `other people who work at Adobe`_, it
seems to have the same name as the tool internal to the Flash
authoring environment.

This debugger looks to have starfed out the same way: directly ported
from C++. During its days there, it probably shared a lot of the code
with the Flash Player itself, and it leaks into there to help with
porting.

.. _ASC:
   http://opensource.adobe.com/svn/opensource/flex/sdk/trunk/modules/asc/

.. _Flex Debugger found in the Flex SDK:
   http://opensource.adobe.com/svn/opensource/flex/sdk/trunk/modules/debugger/

.. _other people who work at Adobe:
   http://senocular.com/flash/tutorials/versions/#Compiler
"""
