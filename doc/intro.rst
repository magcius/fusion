Intro to Mecheye Fusion
=======================

"Mecheye Fusion"? Sounds like a secret government project.
----------------------------------------------------------

**Mecheye Fusion**, the latest project from Mecheye Labs (I'm not an Iranian
contractor, I promise), is a Python codebase for writing and parsing SWF files
and the Tamarin bytecode format. Fusion was originally All SWFs built by Fusion
should follow the `official Adobe SWF spec`_, except where the spec is wrong in
relation to the Flash Player implementation, which has happened multiple times.

Alright, how do I get it?
-------------------------

Oh yeah, you'll need ``zope.interface`` and ``zope.component`` too.

Fusion is egg-installable. Not sure if that's a good thing, and I've been told
it's not, but it's pretty easy until setuptools decides to go the way of PJE
and start giving advice for people better off than it::

  $ pip install zope.interface zope.component mecheye-fusion

Don't like setuptools? Good. Here's a better way to do the same thing (it also
doubles as an indicator of where the git repo is)::

  $ git clone http://github.com/mecheye/mecheye-fusion
  $ cd mecheye-fusion
  $ python setup.py install --local

Don't like cryptic error messages and narcissistic dictators? We also have a
Launchpad bzr mirror::

  $ bzr branch lp:mecheye-fusion
  $ cd mecheye-fusion
  $ python setup.py install --local

Note that "--local" is a per-user install, so you don't need to go mucking
about with cracking the superuser password on Ubuntu and shared hosts.

If you feel like an adventure, I also have an unstable repository::

  $ git clone http://github.com/magcius/mecheye-fusion
  $ cd mecheye-fusion
  $ python setup.py install --local

My fork of Fusion is where development happens, and when nothing's broken and
seems like a good time to tack on a ".1", I create a tag and push to the
"official" mecheye repository. Well, I'll start creating tags soon, because
I'm not too git-savvy yet.

What can I do?
--------------

.. role:: del

Not much at this point. The current focus is on the Tamarin and ABC stuff and
making that nice and easy to use, and then the other stuff :del:`will`
should fall into place.

.. sourcecode:: python

  from mech.fusion.avm2.abc_ import AbcFile
  from mech.fusion.avm2.constants import packagedQName

  abc = AbcFile()
  gen = abc.create_generator()
  with gen.Class(packagedQName("foo.bar", "WhatUpHomies")):
      with gen.Constructor():
          gen.load("I'm on a ")
          gen.push_this()
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
parse SWF and ABC. **mf-swfdump** can handle both .abc and .swf files. It lives
in ``bin/mf-swfdump`` in the Fusion repository.

If this breaks, please file a bug at `Launchpad`_.

But I want that buggy PyPy translator!
--------------------------------------

Oh, that's right. There's the starting of a PyPy translator `here
<http://codespeak.net/svn/pypy/branch/avm>`_ as well. It doesn't do very
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

Oh no... please don't tell me where this came from...
-----------------------------------------------------

Thankfully, there's a little scrollbar on the right side of your screen if you
don't want to hear my story.

Fusion was originally developed as an `ActionScript 3 library`_ as a
collaborative development between Josh Lory and I (Jasper St. Pierre). I had
recently found Python at the time, and had the idea of developing a Python fork
in the likes of IronPython and Jython, but built for Tamarin. Talking with some
fellow members on the #python IRC channel, I was redirected to PyPy. Some of
the PyPy developers and I talked about the benefits of using PyPy instead of
forking Jython (i.e. write a translator once, gain the benefits of an
ever-improving interpreter).

Originally, all the SWF work was merged in with the PyPy translator work in the
pypy.translator.avm1 package. Debugging was originally tough: with the lack of
a good output mechanism from the Flash Player, it was difficult to understand
what went wrong, and I figured using something open-source that I could poke at
would be better. The Gnash developers were interested in my work for testcases,
and I began the long process of splitting the SWF package out.

All the stuff you probably don't care about
-------------------------------------------

Fusion itself is licensed under the **`Mozilla Public License version 1.1`_**,
whereas the associated PyPy translator is licensed under the MIT license. If
you want to use Fusion in your own project and want to use GPLv3 or the WTFPL,
just contact me. I am very flexible about licensing.

Because I don't feel like testing Google's spam filter today, you can find my
email address in the git log. On IRC, I'm in a lot of channels all over the
place. If you see some loser named "magcius" in your /who, that's me. There's
`#mecheye`_ on Freenode too, I guess that's where you can ask me questions
(highlight me though, otherwise I won't catch it).

.. _official Adobe SWF spec:
   http://www.adobe.com/devnet/swf/pdf/swf_file_format_spec_v10.pdf

.. _Launchpad: http://bugs.launchpad.net/mecheye-fusion
.. _ActionScript 3 library: http://github.com/mecheye/mecheye-fusion-as3
.. _Tamarind: http://en.wikipedia.org/wiki/Tamarind
.. _#mecheye: irc://irc.freenode.net/mecheye
.. _Mozilla Public License version 1.1:
   http://www.mozilla.org/MPL/MPL-1.1.html
