BitStream API Introduction
==========================

The BitStream API has gone through several revisions, starting with an extension
of ByteArray in the Flash world.

History
=======

At first, when Josh Lory was implementing SWF creation in `Mecheye Fusion - the
AS3 version`_ - he was originally working with the `ByteArray`_ class in
ActionScript 3. For a good time, this API had all we needed when implementing
sane formats that didn't decide to bitpack their fields to save minimal amounts
of space. In order to support the SWF format Josh created an `EnhancedByteArray`_
class that provided some helpful utility methods along with two other items: a
`BitWriteStream`_ and a `BitReadStream`_, two classes that wrote to and read from the
same EnhancedByteArray.

These classes were implemented as helper classes and were closely tied to the
`EnhancedByteArray`_, and like the original ByteArray class, did not lend itself
to a modular design very well, by having every type of "format" have its own
method in both readFoo and writeFoo forms, usually with two variations in the
method, one for little and one for big-endian, set with a field on the ByteArray
called "endianness".

When I finally :del:`discovered` started to like Python, I decided to test my
programming skills by porting Fusion to Python, inspired by a lack of both SWF
readers *and* parsers, or ones that didn't rely on an external library like
ming, which was in quite a big development stall at the time.



.. _`Mecheye Fusion - the AS3 version`:
   http://github.com/mecheye/mecheye-fusion-as3/

.. _`EnhancedByteArray`:
   http://github.com/mecheye/mecheye-fusion-as3/

.. _`ByteArray`:
   http://help.adobe.com/en_US/FlashPlatform/reference/actionscript/3/flash/utils/ByteArray.html
