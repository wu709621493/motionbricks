"""Build a platform wheel for the ctypes library, without a CPython ABI tie."""
from pathlib import Path
import platform
import subprocess
import sys

from setuptools import setup
from setuptools.command.build_py import build_py
from wheel.bdist_wheel import bdist_wheel


class NativeBuild(build_py):
    def run(self):
        super().run()
        suffix = '.dylib' if platform.system() == 'Darwin' else '.so'
        subprocess.run([sys.executable, str(Path(__file__).with_name('build.py')),
                        '--output', str(Path(self.build_lib) / 'pyignite' / ('libpyignite' + suffix))],
                       check=True)


class PlatformWheel(bdist_wheel):
    def finalize_options(self):
        super().finalize_options()
        self.root_is_pure = False

    def get_tag(self):
        _, _, platform_tag = super().get_tag()
        if platform.system() == 'Darwin':
            # setup-python may itself be universal2, but build.py invokes one
            # native compiler target. Never advertise a second Mach-O slice.
            major, minor = map(int, platform.mac_ver()[0].split('.')[:2])
            platform_tag = f'macosx_{major}_{0 if major >= 11 else minor}_{platform.machine()}'
        return 'py3', 'none', platform_tag


setup(cmdclass={'build_py': NativeBuild, 'bdist_wheel': PlatformWheel})
