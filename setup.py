from setuptools import setup
from s3_site_cache_optimizer.optimize import __version__

setup(
    name='s3-site-cache-optimizer',
    description='Optimize a static website before uploading to S3',
    author='Ruben Van den Bossche',
    author_email='ruben@appstrakt.com',
    version=__version__,

    packages=['s3_site_cache_optimizer'],
    package_dir={'': 'src'},

    install_requires=[],
    entry_points={ 'console_scripts' : ['s3-site-cache-optimizer=s3_site_cache_optimizer.optimize:main'] },
)
