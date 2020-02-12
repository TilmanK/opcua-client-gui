from setuptools import setup, find_packages


setup(name="opcua-client",
      version="0.8.0",
      description="OPC-UA Client GUI",
      author="Olivier R-D",
      url='https://github.com/FreeOpcUa/opcua-client-gui',
      packages=["uaclient"],
      license="GNU General Public License",
      install_requires=["asyncua>=0.8.0", "PyQt5>=5.13.1"],
      entry_points={'console_scripts':
                    ['opcua-client = uaclient.mainwindow:main']
                    }
      )
