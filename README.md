# s3-site-cache-optimizer

Optimize a static website for hosting in S3, by including a fingerprint into
all assets' filenames. The optimized website is uploaded into the specified S3
bucket with the right cache headers.


## Usage

	usage: s3-site-cache-optimizer [-h] [--debug] [--version]
	                               [--exclude PATTERN [PATTERN ...]]
	                               [-o OUTPUT_DIR]
	                               [--access-key AWS_ACCESS_KEY_ID]
	                               [--secret-key AWS_SECRET_ACCESS_KEY]
	                               [--skip-s3-upload]
	                               source_dir destination_bucket

	positional arguments:
	  source_dir            Local directory containing a static website.
	  destination_bucket    Domain name of the website and S3 bucket name.

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
	  --skip-s3-upload      Skip uploading to S3.

### Example

	$ s3-site-cache-optimizer ~/srv/www.example.com www.example.com --access-key XXXXXAPPSTRAKTXXXXX --secret-key XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
	$ s3-site-cache-optimizer ~/srv/www.example.com www.example.com --exclude ".git/*" ".git*"
	$ s3-site-cache-optimizer ~/srv/www.example.com www.example.com --output ~/srv/example-optimized/ --skip-s3-upload

---
Version 0.1
