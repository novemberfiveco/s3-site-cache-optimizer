'''
Optimize a static website for hosting in S3, by including a
fingerprint into all assets\' filenames. The optimized website
is uploaded into the specified S3 bucket with the right cache
headers.
'''

from __future__ import print_function
import sys
import argparse
import os.path
import logging
import fileinput
import re
import gzip
from pkg_resources import Requirement, resource_filename, require
from hashlib import sha256
from shutil import copyfile, move, rmtree
from fnmatch import fnmatch
from tempfile import mkdtemp, mkstemp
from urlparse import urlparse, urljoin
from boto import connect_s3
from boto.s3 import connect_to_region
from boto.s3.key import Key
from boto.exception import BotoClientError, BotoServerError

__author__ = "Ruben Van den Bossche"
__email__ = "ruben@appstrakt.com"
__copyright__ = "Copyright 2015, Appstrakt BVBA"
__license__ = "MIT"

logger = None


def calculate_fingerprint(fname):
    '''
    Calculate a hash from a file name.
    '''
    hasher = sha256()
    blocksize = 65536

    with open(fname, 'rb') as f:
        buf = f.read(blocksize)
        while len(buf) > 0:
            hasher.update(buf)
            buf = f.read(blocksize)
        filehash = hasher.hexdigest()
        logger.debug("Fingerprint of {0} is {1}".format(fname, filehash))
        return filehash


def convert_filename(filename, filehash):
    '''
    Convert filename to include file hash
    '''
    ftup = os.path.splitext(filename)

    return ftup[0] + '.' + filehash + ftup[1]


class OptimizerError(Exception):

    '''
    Error thrown by Optimizer class.
    '''

    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return str(self.msg)


class Optimizer(object):

    '''
    Optimizer class: Optimize a static website for hosting in S3.
    '''

    def __init__(self, source_dir, destination_bucket, exclude=[], output_dir=None,
                 aws_access_key_id=None, aws_secret_access_key=None, skip_s3_upload=False,
                 region=None, domains=[], prefix=None, gzip=False):
        '''
        Initialize Optimizer
        '''

        logger.info('Initialize Optimizer class')

        if not os.path.isdir(source_dir):
            raise OptimizerError("{0} is not a valid path".format(source_dir))

        if not os.access(source_dir, os.R_OK):
            raise OptimizerError(
                "{0} is not a readable dir".format(source_dir))

        if output_dir is not None:
            output_dir_is_temp = False
            if not os.path.isdir(output_dir):
                try:
                    os.makedirs(output_dir)
                except os.error as e:
                    raise OptimizerError(
                        "{0} is not a directory and cannot be created".format(output_dir))

            if not os.access(output_dir, os.W_OK):
                raise OptimizerError("{0} is not a writable dir".format(output_dir))
        else:
            output_dir_is_temp = True
            output_dir = mkdtemp()

        self._assets_ext = ['.css', '.svg', '.ttf', '.woff', '.woff2', '.otf', '.eot', '.png',
                            '.jpg', '.jpeg', '.gif', '.js', '.mp4', '.webm', '.webp']
        self._rewriteables_ext = ['.html', '.htm', '.js', '.css', '.xml', '.json']
        self._gzip_ext = ['.html', '.htm', '.css', '.js', '.svg', '.xml', '.json']

        self._source_dir = source_dir
        self._output_dir = output_dir
        self._output_dir_is_temp = output_dir_is_temp
        self._destination_bucket = destination_bucket
        self._subdirs = []
        self._files = []
        self._assets_map = {}
        self._rewritables = []
        self._exclude = exclude
        self._domains = domains
        self._prefix = prefix
        self._gzip = gzip
        self._skip_s3_upload = skip_s3_upload

        if not self._skip_s3_upload:
            try:
                if region == None:
                    self._s3 = connect_s3(aws_access_key_id=aws_access_key_id,
                                          aws_secret_access_key=aws_secret_access_key)
                else:
                    self._s3 = connect_to_region(region, aws_access_key_id=aws_access_key_id,
                                                 aws_secret_access_key=aws_secret_access_key)
            except (BotoClientError, BotoServerError) as e:
                raise OptimizerError("Cannot connect to S3")

            try:
                self._bucket = self._s3.get_bucket(self._destination_bucket)
            except (BotoClientError, BotoServerError) as e:
                raise OptimizerError("Bucket {0} does not exist or is not accessible."
                                     .format(self._destination_bucket))

        logger.debug('Optimizer class initialized')

    def __del__(self):
        if self._output_dir_is_temp:
            try:
                logger.debug('Deleting temporary directory')
                rmtree(self._output_dir)
            except OSError as exc:
                raise OptimizerError("Can't delete temporary directory.")

    def _index_source_dir(self):
        '''
        Index all files and directories under the source directory
        '''

        logger.info('Indexing source dir')
        for dirpath, dirnames, fnames in os.walk(self._source_dir):

            for d in dirnames:
                relpath = os.path.relpath(
                    os.path.join(dirpath, d), self._source_dir)
                if True in [fnmatch(relpath, exclude) for exclude in self._exclude]:
                    continue

                logger.debug("Found subdir {0}".format(relpath))
                self._subdirs.append(relpath)

            for f in fnames:
                relpath = os.path.relpath(
                    os.path.join(dirpath, f), self._source_dir)
                if True in [fnmatch(relpath, exclude) for exclude in self._exclude]:
                    continue

                self._files.append(relpath)

                ext = os.path.splitext(f)[1]
                if ext in self._assets_ext:
                    logger.debug("Found asset {0}".format(f))
                    self._assets_map[relpath] = {
                        'basename': os.path.basename(relpath)}

                if ext in self._rewriteables_ext:
                    logger.debug("Found rewritable {0}".format(f))
                    self._rewritables.append(relpath)

        logger.debug('Finished indexing source dir')

    def _calculate_fingerprints(self):
        '''
        Calculate fingerprints of all assets in the source dir
        '''

        logger.info('Calculating fingerprints')

        for fname in self._assets_map.keys():
            fingerprint = calculate_fingerprint(os.path.join(self._source_dir, fname))
            self._assets_map[fname]['new_filename'] = convert_filename(fname, fingerprint)

        logger.debug('Finished calculating fingerprints')

    def _write_dirs(self):
        '''
        Write directory structure to output folder
        '''

        logger.info('Writing dirs')
        for reldir in self._subdirs:
            absdir = os.path.join(self._output_dir, reldir)
            if not os.path.isdir(absdir):
                logger.debug("Making dir {0}".format(absdir))
                os.makedirs(absdir)

        logger.debug('Finished writing dirs')

    def _rewrite_file(self, src, dst):
        '''
        rewrite a single file from source to dest
        '''

        with open(src, 'r') as f_src:
            src_reldirpath = os.path.dirname(os.path.relpath(src, self._source_dir))

            with open(dst, 'w') as f_dst:
                # replace asset urls line by line
                for line in f_src:
                    for asset in self._assets_map.keys():
                        if self._assets_map[asset]['basename'] in line:
                            url_chars = '''a-z0-9''' + re.escape('''-_.~!#$&*+,/:;=?@[]''')
                            regex = r'''[''' + url_chars + ''']*''' + \
                                    re.escape(self._assets_map[asset]['basename']) + \
                                    '[' + url_chars + ']*'

                            it = re.finditer(regex, line, re.IGNORECASE)
                            for result in reversed(list(it)):
                                url = result.group()
                                parsed_url = urlparse(url)
                                if parsed_url.netloc and \
                                        parsed_url.netloc not in self._domains:
                                    # leave this url alone, is third party
                                    logger.warning("Skipping rewriting url {0}.".format(url))
                                    continue
                                logger.debug("Found asset {0} in {1}".format(url, src))
                                normalized_relative_path = os.path.normpath(
                                    os.path.join(src_reldirpath, parsed_url.path)).lstrip('/')

                                if asset == normalized_relative_path:
                                    new_path = '/' + os.path.join(
                                        os.path.dirname(normalized_relative_path),
                                        os.path.basename(self._assets_map[asset]['new_filename']))

                                    if parsed_url.netloc:
                                        # don't remove domain from absolute urls
                                        new_path = urljoin(url, new_path)

                                    logger.debug("Replacing with {0}".format(new_path))

                                    line = line[:result.start()] + new_path + line[result.end():]

                    f_dst.write(line)

    def _write_files(self):
        '''
        Write files to output folder, and rewrite file names/content if necessary.
        '''

        logger.info('Writing files')
        assets = set(self._assets_map.keys())
        rewritables = set(self._rewritables)

        # (1) Assets that are not rewritables
        for src_filename in assets - rewritables:
            dst_filename = self._assets_map[src_filename]['new_filename']

            src = os.path.join(self._source_dir, src_filename)
            dest = os.path.join(self._output_dir, dst_filename)

            logger.debug("1. Writing asset {0} to {1}".format(src_filename, dst_filename))
            copyfile(src, dest)

        # (2) Assets that are also rewritables
        for src_filename in assets & rewritables:
            # we assume these files don't have mutual references to eachother
            # if they do, we need to build a dependency tree and solve order
            # that way (TODO)

            # make temp file
            tmp_handle, tmp_filename = mkstemp(text=True)

            src = os.path.join(self._source_dir, src_filename)
            logger.debug("2. Rewriting asset {0} to temp file".format(src_filename))
            self._rewrite_file(src, tmp_filename)

            # close temp file and calculate fingerprint
            fingerprint = calculate_fingerprint(tmp_filename)
            dst_filename = convert_filename(src_filename, fingerprint)
            self._assets_map[src_filename]['new_filename'] = dst_filename

            # move temp file to destination
            dest = os.path.join(self._output_dir, dst_filename)

            logger.debug("2. Writing asset {0} to {1}".format(src_filename, dst_filename))
            move(tmp_filename, dest)

        # (3) Other rewritables
        for src_filename in rewritables - assets:
            src = os.path.join(self._source_dir, src_filename)
            dest = os.path.join(self._output_dir, src_filename)

            logger.debug("3. Rewriting asset {0}".format(src_filename))
            self._rewrite_file(src, dest)

        # (4) Other files
        for src_filename in set(self._files) - assets - rewritables:
            src = os.path.join(self._source_dir, src_filename)
            dest = os.path.join(self._output_dir, src_filename)

            logger.debug("4. Copying file {0}".format(src_filename))
            copyfile(src, dest)

        logger.debug('Finished writing files')


    def _gzip_files(self):
        '''
        Gzip text files in output folder.
        '''

        logger.info('Gzipping files')

        for dirpath, dirnames, fnames in os.walk(self._output_dir):
            for f in fnames:
                abspath = os.path.join(dirpath, f)

                is_gzippable = os.path.splitext(f)[1] in self._gzip_ext
                if is_gzippable:
                    tmp_handle, tmp_filename = mkstemp()

                    logger.debug('Gzipping {0}'.format(abspath))
                    with open(abspath, 'rb') as f_in:
                        with gzip.open(tmp_filename, 'wb') as f_out:
                            f_out.writelines(f_in)

                    # overwrite existing file
                    move(tmp_filename, abspath)

        logger.debug('Finished gzipping files')


    def _upload_to_bucket(self):
        '''
        Upload contents of output folder to S3.
        '''
        logger.info('Uploading to bucket')

        try:
            to_be_deleted = [l.key for l in self._bucket.list(prefix=self._prefix)]

            for dirpath, dirnames, fnames in os.walk(self._output_dir):

                for f in fnames:
                    abspath = os.path.join(dirpath, f)
                    relpath = os.path.relpath(abspath, self._output_dir)

                    if self._prefix != None:
                        relpath = os.path.join(self._prefix, relpath)

                    # do not delete this file
                    try:
                        to_be_deleted.remove(relpath)
                    except:
                        pass

                    # check if file should be cached / reuploaded
                    ext = os.path.splitext(f)[1]
                    is_asset = ext in self._assets_ext
                    is_gzipped = self._gzip and (ext in self._gzip_ext)

                    k = self._bucket.get_key(relpath)
                    if k is None or not is_asset:
                        # asset doesn't exist or file is not an asset and
                        # should be uploaded anyway

                        k = Key(self._bucket)
                        k.key = relpath

                        headers = {}
                        if is_asset:
                            # set infinite headers
                            headers['Cache-Control'] = "public, max-age=31556926"
                        else:
                            # set no-cache headers
                            headers['Cache-Control'] = "no-cache, max-age=0"

                        if is_gzipped:
                            headers['Content-Encoding'] = "gzip"

                        logger.debug("Uploading file {0} to {1}".format(relpath,
                                                                        self._destination_bucket))
                        k.set_contents_from_filename(abspath, replace=True, headers=headers)

            # remove files not currently touched
            for del_file in to_be_deleted:
                logger.debug(
                    "Deleting key {0} from {1}".format(del_file, self._destination_bucket))
            self._bucket.delete_keys(to_be_deleted)

        except (BotoClientError, BotoServerError) as e:
            raise OptimizerError("Error uploading to S3" + str(e))

        logger.debug('Finished uploading to bucket')

    def run(self):
        '''
        Main entry method for the Optimizer object.
        '''
        logger.debug('Running optimize')

        self._index_source_dir()
        self._calculate_fingerprints()
        self._write_dirs()
        self._write_files()
        if self._gzip:
            self._gzip_files()

        if not self._skip_s3_upload:
            self._upload_to_bucket()

        logger.info('Finished optimizing static website for S3.')


def main():
    '''
    Main function for the s3-site-cache-optimizer CLI.
    '''

    # init logger
    global logger
    logger = logging.getLogger('s3-site-cache-optimizer')
    ch = logging.StreamHandler()
    formatter = logging.Formatter('%(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # parse arguments
    parser = argparse.ArgumentParser(
        prog='s3-site-cache-optimizer',
        description='Optimize a static website for hosting in S3, by including a fingerprint \
        into all assets\' filenames. The optimized website is uploaded into the specified S3 \
        bucket with the right cache headers.')
    parser.add_argument('--debug', action='store_true', help='Enable debug output')
    parser.add_argument('--version', action='version', version='%(prog)s ' +
                        str(require("s3-site-cache-optimizer")[0].version))
    parser.add_argument("source_dir", help='Local directory containing a static website.')
    parser.add_argument("destination_bucket", help='S3 bucket name.')
    parser.add_argument('--exclude', nargs='+', metavar="PATTERN", default=[],
                        help='Exclude files and directories matching these patterns.')
    parser.add_argument('-o', '--output', dest='output_dir', default=None,
                        help='Output directory in which local files are written. When absent a \
                        temporary directory is created and used.')
    parser.add_argument('--access-key', dest="aws_access_key_id", default=None,
                        help='AWS access key. If this field is not specified, credentials from \
                        environment or credentials files will be used.')
    parser.add_argument('--secret-key', dest="aws_secret_access_key", default=None,
                        help='AWS access secret. If this field is not specified, credentials from \
                        environment or credentials files will be used.')
    parser.add_argument('--region', default=None, help='AWS region to connect to.')
    parser.add_argument('--gzip', action='store_true', help='Gzip text-based files.', default=False)
    parser.add_argument('--prefix', default=None, help='Subdirectory in which files are stored in \
                                                        the bucket. Stored in the root of the \
                                                        bucket by default.')
    parser.add_argument('--domains', nargs='+', metavar="DOMAIN", default=[],
                        help='Domain names on which the site will be hosted.')
    parser.add_argument('--skip-s3-upload', dest="skip_s3_upload",
                        action='store_true', help='Skip uploading to S3.')

    try:
        args = parser.parse_args()
    except argparse.ArgumentTypeError as e:
        logger.error(e)
        exit(1)

    # set logging level
    if args.debug:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)

    try:
        Optimizer(args.source_dir, args.destination_bucket, exclude=args.exclude,
                  output_dir=args.output_dir, aws_access_key_id=args.aws_access_key_id,
                  aws_secret_access_key=args.aws_secret_access_key,
                  skip_s3_upload=args.skip_s3_upload, region=args.region,
                  domains=args.domains, prefix=args.prefix, gzip=args.gzip).run()
    except Exception as e:
        logger.critical(e)
        exit(1)
