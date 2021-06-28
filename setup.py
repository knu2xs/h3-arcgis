from setuptools import find_packages, setup

with open('README.md', 'r') as readme:
    long_description = readme.read()

setup(
    name='h3_arcgis',
    package_dir={"": "src"},
    packages=find_packages('src'),
    version='0.0.0',
    description='Making Uber H3 and ArcGIS a littel easier to work with.',
    long_description=long_description,
    author='Joel McCune (https://github.com/knu2xs)',
    license='Apache 2.0',
)
