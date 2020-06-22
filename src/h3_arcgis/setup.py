import setuptools

with open('../README.md', 'r') as readme:
    long_description = readme.read()

setuptools.setup(
    name='h3-arcgis',
    version='0.1.0',
    author='Joel McCune',
    author_email='knu2xs@gmail.com',
    description='Useful tools for working with Uber H3 in ArcGIS.',
    license='Apache 2.0',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/knu2xs/h3-arcgis',
    packages=['ba_tools'],
    install_requires=[
        'arcgis>=1.8.0',
        'h3-py',
        'dask',
        'swifter'
    ],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Programming Language :: Python :: 3 :: Only',
        'Programming Language :: Python :: 3.6',
        'License :: OSI Approved :: MIT License',
        'Topic :: Scientific/Engineering :: GIS'
    ]
)
