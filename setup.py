from setuptools import setup

setup(
    name='s3-site-cache-optimizer',
    version='0.6.0',
    license='MIT',

    description='Optimize a static website before uploading to S3',
    long_description='Optimize a static website for hosting in S3, by including a fingerprint into \
    all assets\' filenames. The optimized website is uploaded into the specified S3 bucket with \
    the right cache headers.',

    author='Ruben Van den Bossche, Matteo De Wint',
    author_email='ruben@novemberfive.co, matteo@novemberfive.co',
    url='https://github.com/novemberfiveco/s3-site-cache-optimizer',

    packages=['s3_site_cache_optimizer'],
    package_dir={'': 'src'},

    install_requires=['boto'],
    entry_points={ 'console_scripts' : ['s3-site-cache-optimizer=s3_site_cache_optimizer.optimize:main'] },
)
