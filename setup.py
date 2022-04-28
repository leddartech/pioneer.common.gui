import os
import re
import sys
import platform
import subprocess
import setuptools

from setuptools import setup, Extension
from setuptools.command.build_ext import build_ext
from distutils.version import LooseVersion

def parse_requirements(filename):
    """ load requirements from a pip requirements file """
    lineiter = (line.strip() for line in open(filename))
    return [line for line in lineiter if line and not line.startswith("#")]

install_reqs = parse_requirements('requirements.txt')


class CMakeExtension(Extension):
    def __init__(self, name, sourcedir=''):
        Extension.__init__(self, name, sources=[])
        self.sourcedir = os.path.abspath(sourcedir)

class CMakeBuild(build_ext):
    def run(self):
        try:
            out = subprocess.check_output(['cmake', '--version'])
        except OSError:
            raise RuntimeError("CMake must be installed to build the following extensions: " +
                               ", ".join(e.name for e in self.extensions))

        if platform.system() == "Windows":
            cmake_version = LooseVersion(re.search(r'version\s*([\d.]+)', out.decode()).group(1))
            if cmake_version < '3.1.0':
                raise RuntimeError("CMake >= 3.1.0 is required on Windows")

        for ext in self.extensions:
            self.build_extension(ext)

    def build_extension(self, ext):
        extdir = os.path.abspath(os.path.dirname(self.get_ext_fullpath(ext.name)))
        lib_output_dir = os.path.join(extdir, 'pioneer')
        cmake_args = ['-DPYTHON_EXECUTABLE=' + sys.executable]

        print(cmake_args)
        cfg = 'Debug' if self.debug else 'Release'
        build_args = ['--config', cfg]

        if platform.system() == "Windows":
            cmake_args += ['-DCMAKE_LIBRARY_OUTPUT_DIRECTORY_{}={}'.format(cfg.upper(), lib_output_dir)]
            cmake_args += ['-DCMAKE_RUNTIME_OUTPUT_DIRECTORY_{}={}'.format(cfg.upper(), lib_output_dir)]
            cmake_args += ['-DCMAKE_TOOLCHAIN_FILE={}/scripts/buildsystems/vcpkg.cmake'.format(os.environ['VCPKG_ROOT'])]
            if sys.maxsize > 2**32:
                cmake_args += ['-A', 'x64', '-G', 'Visual Studio 15 2017']
            build_args += ['--', '/m']
        else:
            cmake_args += ['-DCMAKE_LIBRARY_OUTPUT_DIRECTORY={}'.format(lib_output_dir)]
            cmake_args += ['-DCMAKE_RUNTIME_OUTPUT_DIRECTORY={}'.format(lib_output_dir)]
            cmake_args += ['-DCMAKE_BUILD_TYPE=' + cfg]
            build_args += ['--', '-j4']

        env = os.environ.copy()
        env['CXXFLAGS'] = '{} -DVERSION_INFO=\\"{}\\"'.format(env.get('CXXFLAGS', ''),
                                                              self.distribution.get_version())
        if not os.path.exists(self.build_temp):
            os.makedirs(self.build_temp)
        subprocess.check_call(['cmake', ext.sourcedir] + cmake_args, cwd=self.build_temp, env=env)
        subprocess.check_call(['cmake', '--build', '.'] + build_args, cwd=self.build_temp)

from subprocess import CalledProcessError

kwargs = dict(
    name='pioneer_common_gui',
    version='1.4.0',
    author='Leddartech',
    description='Pioneer gui utility package',
    long_description='',
    ext_modules=[CMakeExtension('leddar_utils_cpp')],
    cmdclass=dict(build_ext=CMakeBuild),
    zip_safe=False,
    packages=[
        'pioneer', 
        'pioneer.common', 
        'pioneer.common.gui',
        'pioneer.common.gui.qml',
        'pioneer.common.gui.qml.backend_qtquick5'
    ],
    dependency_links = [
        "https://pioneer:yK6RUkhUCNHg3e1yxGT4@svleddar-gitlab.leddartech.local/api/v4/projects/481/packages/pypi/simple"
    ],
    install_requires=install_reqs,
    include_package_data = True
)

# likely there are more exceptions, take a look at yarl example
try:
    setup(**kwargs)
except CalledProcessError:
    print('Failed to build extension!')
    del kwargs['ext_modules']
    setup(**kwargs)
