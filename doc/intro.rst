Intro to Fusion
===============

"Fusion"? Sounds like a secret government project.
--------------------------------------------------

'''Fusion''' is a library for creating and parsing Flash-related formats,
including `SWF`_ and `ActionScript Byte Code`_.

Alright, what does it do for me?
--------------------------------

Oh yeah, you'll need ``zope.interface`` and ``zope.component`` too.

Fusion is egg-installable. Not sure if that's a good thing, and I've been told
it's not, but it's pretty easy until setuptools decides to go the way of PJE
and start giving advice for people better off than it::

  $ pip install zope.interface zope.component fusion

Don't like setuptools? Good. Here's a better way to do the same thing, by
checking out direct from the development repository::

  $ git clone git://github.com/magcius/fusion.git
  $ cd fusion
  $ python setup.py install --local

Don't like cryptic error messages and narcissistic dictators? There's also
a bzr mirror, which I reluctantly made for my friends.

  $ bzr branch lp:mecheye-fusion
  $ cd fusion
  $ python setup.py install --local

Note that "--local" is a per-user install, so you don't need to go mucking
about with cracking the superuser password on Ubuntu and some other random
stuff.

What can I do?
--------------

.. sourcecode:: python

  from fusion.avm2.abc_ import AbcFile
  from fusion.avm2.loadable import This
  from fusion.avm2.constants import packagedQName

  abc = AbcFile()
  gen = abc.create_generator()
  with gen.Class(packagedQName("foo.bar", "WhatUpHomies")):
      with gen.Constructor():
          gen.load("I'm on a ")
          gen.pus
          gen.get_field("vehicle")
          gen.emit('add')
          gen.load("!")
          gen.emit('add')
          gen.call_function("trace", 1)

      with gen.Method("vehicle", kind="getter", returntype="String"):
          gen.load("boat")
          gen.return_value()
  gen.finish()
  with open("wordout.abc", "wb") as f:
      f.write(abc.serialize())

There's also another, newer API in development called the "Node" API. It will
require the development version.

This should generate the same result as above::

  from mech.fusion.avm2.abc_ import AbcFile
  from mech.fusion.avm2.constants import packagedQName
  from mech.fusion.avm2.node import ClassNode, getter

  abc = AbcFile()
  gen = abc.create_generator()

  class ExampleNode(ClassNode):
      name = packagedQName("foo.bar", "WhatUpHomies")
      def __iinit__(self, gen):
          gen.load("I'm on a ")
          gen.push_this()
          gen.get_field("vehicle")
          gen.emit('add')
          gen.load("!")
          gen.emit('add')
          gen.call_function("trace", 1)

      @getter("String")
      def vehicle(self, gen):
          gen.load("boat")
          gen.return_value()

  gen.add_node(ExampleNode)
  gen.finish()

  with open("wordout.abc", "wb") as f:
      f.write(abc.serialize())

If this breaks, please file a bug at `Launchpad`_.

Okay, is there anything else?
-----------------------------

Um, there's also a few  **mf-swfdump**, which shows off Fusion's ability to
parse SWF and ABC. **mf-swfdump** can handle both .abc and .swf files.

If this breaks, please file a bug at `Launchpad`_.

But I want that buggy PyPy translator!
--------------------------------------

Oh, that's right. There's the starting of a PyPy translator `here
<http://bitbucket>`_ as well. It doesn't do very
much right now, but it's a start. In order to do that not very much, you'll
need Fusion too.

That branch also has a little tool called SudanPython ripped off of
CarbonPython. Sudan is a major supplier of `Tamarind`_, which is both a tree
and a spice. (sorry, the name isn't perfect, but it's the best I could do while
I was up late at night).

Here's a simple example::

   from pypy.translator.avm2.sudanpython import export

   @export(int, int)
   def add(x, y):
     return x + y

You can compile this by passing the Python module filename to
``bin/sudanpython.py``

If this breaks, please file a bug at `Launchpad`_, not at the PyPy bug tracker.

All the stuff you probably don't care about
-------------------------------------------

Fusion itself is licensed under the **`Mozilla Public License version 1.1`_**,
whereas the associated PyPy translator is licensed under the MIT license. If
you want to use Fusion in your own project and want to use GPLv3 or the WTFPL,
just contact me.

Because I don't feel like testing Google's spam filter today, you can find my
email address in the git log. On IRC, I'm in a lot of channels all over the
place. If you see some loser named "magcius" in your /who, that's me. There's
`#mecheye`_ on Freenode too, I guess that's where you can ask me questions
(highlight me though, otherwise I won't catch it).

.. _SWF:
   http://www.adobe.com/devnet/swf/pdf/swf_file_format_spec_v10.pdf
.. _ActionScript Byte Code:
   http://learn.adobe.com/wiki/display/AVM2/
.. _Tamarin:
   http://hg.mozilla.org/tamarin-redux
.. _official Adobe SWF spec:
   http://www.adobe.com/devnet/swf/pdf/swf_file_format_spec_v10.pdf
.. _Launchpad: http://bugs.launchpad.net/mecheye-fusion
.. _Tamarind: http://en.wikipedia.org/wiki/Tamarind
.. _#mecheye: irc://irc.freenode.net/mecheye
.. _Mozilla Public License version 1.1:
   http://www.mozilla.org/MPL/MPL-1.1.html
