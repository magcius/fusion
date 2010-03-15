

from distutils.core import setup

setup(name='mecheye-fusion',
      version='0.1.2',
      description='SWF export/parse library',
      author='JP "magcius" St. Pierre, Josh Lory, Jon "Jonanin" Morton',
      author_email='jstpierre@mecheye.net, josh21409@gmail.com, jonanin@gmail.com',
      url='http://github.com/mecheye/mecheye-fusion',
      packages=['mech','mech.fusion','mech.fusion.swf',
                'mech.fusion.avm1','mech.fusion.avm2',
                'mech.fusion.bitstream'])
