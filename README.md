# s3-site-cache-optimizer

Optimize a static website for hosting in S3, by including a fingerprint into
all assets' filenames. The optimized website is uploaded into the specified S3
bucket with the right cache headers.


## Installation

You can install the stable version using the following [pip](https://pip.pypa.io/en/latest/)
command:

	pip install --upgrade s3-site-cache-optimizer

If you want to keep up with the latest features, install the development version:

	pip install --upgrade https://github.com/novemberfiveco/s3-site-cache-optimizer/archive/develop.zip


## Operation

The command line tool executes the following steps:

1. Index the (local) source dir containing the static website, and search for _assets_ and
_rewritables_.
2. Calculate a hash from the contents of each _asset_, and rename it with the filehash in the
filename.
3. Search the contents of the _rewritables_ for references to each of the assets, and rewrite
the urls if necessary.
4. (optional) Gzip all text-based files.
5. (optional) Upload all files to a path in an S3 bucket, and *remove all other files* from that path.
Assets are given a never-expiring cache header in order to optimize browser and proxy caching.

All file operations are executed in a (temporary) output directory, the source directory is not
altered.

_Assets_ and _rewritables_ are recognized based on their file extension. Currently, the following
file extensions are considered as _assets_:

- css
- svg
- ttf
- woff
- woff2
- otf
- eot
- png
- jpg
- jpeg
- gif
- js
- xml
- mp4
- webm
- webp

_Rewritables_ are text-based files with one of the following extensions:

- html
- htm
- js
- css
- xml
- json

File a [feature request](https://github.com/novemberfiveco/s3-site-cache-optimizer/issues/new)
if you want to see other file extensions added.


## Usage

	usage: s3-site-cache-optimizer [-h] [--debug] [--version]
	                               [--exclude PATTERN [PATTERN ...]]
	                               [-o OUTPUT_DIR]
	                               [--access-key AWS_ACCESS_KEY_ID]
	                               [--secret-key AWS_SECRET_ACCESS_KEY]
	                               [--region REGION]
	                               [--gzip]
	                               [--prefix PREFIX]
	                               [--domains DOMAIN [DOMAIN ...]]
	                               [--skip-s3-upload]
	                               source_dir destination_bucket

	positional arguments:
	  source_dir            Local directory containing a static website.
	  destination_bucket    S3 bucket name.

	optional arguments:
	  -h, --help            show this help message and exit
	  --debug               Enable debug output
	  --version             show program's version number and exit
	  --exclude PATTERN [PATTERN ...]
	                        Exclude files and directories matching these patterns.
	  -o OUTPUT_DIR, --output OUTPUT_DIR
	                        Output directory in which local files are written.
	                        When absent a temporary directory is created and used.
	  --access-key AWS_ACCESS_KEY_ID
	                        AWS access key. If this field is not specified,
	                        credentials from environment or credentials files will
	                        be used.
	  --secret-key AWS_SECRET_ACCESS_KEY
	                        AWS access secret. If this field is not specified,
	                        credentials from environment or credentials files will
	                        be used.
	  --region REGION       AWS region to connect to.
	  --gzip                Gzip text-based files.
	  --prefix PREFIX       Subdirectory in which files are stored in the bucket.
	                        Stored in the root of the bucket by default.
	  --domains DOMAIN [DOMAIN ...]
	                        Domain names on which the site will be hosted.
	  --skip-s3-upload      Skip uploading to S3.


### Example

	$ s3-site-cache-optimizer ~/srv/www.example.com www.example.com --access-key XXXXXNOVEMBERFIVEXXXXX --secret-key XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
	$ s3-site-cache-optimizer ~/srv/www.example.com www.example.com --exclude ".git/*" ".git*" --region eu-west-1
	$ s3-site-cache-optimizer ~/srv/www.example.com www.example.com --output ~/srv/example-optimized/ --skip-s3-upload
	$ s3-site-cache-optimizer ~/srv/www.example.com my_bucket --domains www.example.com example.com --prefix "user/sites/www.example.com"

## License

The s3-site-cache-optimizer is released under the MIT license.
