from setuptools import setup
import json
import os

setup(
    name="dmdlib",
    version="0.0.1",
    packages=['dmdlib'],
    author="Edmund Chong",
    description=("Control your DMDs."),
    license="MIT",
    keywords="DMD, Vialux, Mightex",
    entry_points={
        'gui_scripts': ['maskmaker=dmdlib.mask_maker.main:main'],
        'console_scripts': ['sparsenoise=dmdlib.randpatterns.sparsenoise:main',
                            'scanner=dmdlib.randpatterns.scanner:main',
                            'whitenoise=dmdlib.randpatterns.whitenoise:main']

    }
)

if os.name == 'nt':
    appdataroot = os.environ['APPDATA']
    appdatapath = os.path.join(appdataroot, 'dmdlib')
else:  # assume posix
    appdataroot = os.path.expanduser('~')
    appdatapath = os.path.join(appdataroot, '.dmdlib')
if not os.path.exists(appdatapath):
    os.mkdir(appdatapath)
with open(os.path.join(appdatapath, 'mask_maker_config.json'), 'w') as f:
    json.dump({}, f)  # initialize empty json file.
print('Made config file at {}'.format(appdatapath))
