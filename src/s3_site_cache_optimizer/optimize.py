'''
Optimize a static website before uploading to S3
@author: Ruben Van den Bossche
'''

from __future__ import print_function
import sys
import argparse
import os.path
import logging
import fileinput
from boto import connect_s3
from boto.s3.key import Key
from boto.exception import BotoClientError, BotoServerError
from pkg_resources import Requirement, resource_filename, require
from hashlib import sha256
from shutil import copyfile
from fnmatch import fnmatch
from tempfile import mkdtemp

logger = None

# http://stackoverflow.com/questions/3431825/generating-a-md5-checksum-of-a-file
def hashfile(afile, hasher, blocksize=65536):
    buf = afile.read(blocksize)
    while len(buf) > 0:
        hasher.update(buf)
        buf = afile.read(blocksize)
    return hasher.hexdigest()

def convert_filename(filename, filehash):
    ftup = os.path.splitext(filename)

    return ftup[0] + '.' + filehash + ftup[1]


class OptimizerError(Exception):
    def __init__(self, msg):
        self.msg = msg
    def __str__(self):
        return str(self.msg)


class Optimizer(object):

    def __init__(self, source_dir, destination_bucket, exclude=[]):
        logger.debug('Initialize Optimizer class')

        if not os.path.isdir(source_dir):
            raise OptimizerError("{0} is not a valid path".format(source_dir))

        if not os.access(source_dir, os.R_OK):
            raise OptimizerError("{0} is not a readable dir".format(source_dir))

        # if not os.path.isdir(destination_dir):
        #     try:
        #         os.makedirs(destination_dir)
        #     except os.error as e:
        #         raise OptimizerError("{0} is not a directory and cannot be created".format(destination_dir))

        # if not os.access(destination_dir, os.W_OK):
        #     raise OptimizerError("{0} is not a writable dir".format(destination_dir))

        self._assets_ext = ['.css', '.svg', '.ttf', '.woff', '.woff2', '.otf', '.eot', '.png', '.jpg', '.jpeg', '.gif', '.js']
        self._rewriteables_ext = ['.html', '.htm', '.js', '.css']

        self._source_dir = source_dir
        self._destination_dir = mkdtemp()
        self._destination_bucket = destination_bucket

        self._subdirs = []
        self._files = []
        self._assets_map = {}
        self._rewritables = []
        self._exclude = exclude

        logger.debug('Optimizer class initialized')


    def _index_source_dir(self):
        logger.debug('Indexing source dir')
        for dirpath, dirnames, fnames in os.walk(self._source_dir):

            for d in dirnames:
                relpath = os.path.relpath(os.path.join(dirpath, d), self._source_dir)
                if True in [fnmatch(relpath, exclude) for exclude in self._exclude]:
                    continue

                logger.debug("Found subdir {0}".format(relpath))
                self._subdirs.append(relpath)

            for f in fnames:
                relpath = os.path.relpath(os.path.join(dirpath, f), self._source_dir)
                if True in [fnmatch(relpath, exclude) for exclude in self._exclude]:
                    continue

                self._files.append(relpath)

                ext = os.path.splitext(f)[1]
                if ext in self._assets_ext:
                    logger.debug("Found asset {0}".format(f))
                    self._assets_map[relpath] = {}

                if ext in self._rewriteables_ext:
                    logger.debug("Found rewritable {0}".format(f))
                    self._rewritables.append(relpath)

        logger.debug('Finished indexing source dir')


    def _calculate_fingerprints(self):
        logger.debug('Calculating fingerprints')

        for fname in self._assets_map.keys():
            with open(os.path.join(self._source_dir, fname), 'rb') as f:
                filehash = hashfile(f, sha256())
                logger.debug("Fingerprint of {0} is {1}".format(fname, filehash))
                self._assets_map[fname]['new_filename'] = convert_filename(fname, filehash)

        logger.debug('Finished calculating fingerprints')


    def _write_dirs(self):
        logger.debug('Writing dirs')
        for reldir in self._subdirs:
            absdir = os.path.join(self._destination_dir, reldir)
            if not os.path.isdir(absdir):
                logger.debug("Making dir {0}".format(absdir))
                os.makedirs(absdir)

        logger.debug('Finished writing dirs')

    def _write_files(self):
        logger.debug('Writing files')
        assets = self._assets_map.keys()

        for src_filename in self._files:
            dst_filename = src_filename

            # if file is asset
            if src_filename in assets:
                dst_filename = self._assets_map[src_filename]['new_filename']

            src = os.path.join(self._source_dir, src_filename)
            dest = os.path.join(self._destination_dir, dst_filename)

            # if file is rewritable
            if src_filename in self._rewritables:
                logger.debug("Rewriting {0}".format(dest))
                # open old and new file for reading and writing
                with open(src, 'r') as f_src:
                    with open(dest, 'w') as f_dst:
                        # replace asset urls line by line
                        for line in f_src:
                            for asset in assets:
                                # TODO: won't work if using relative paths (such as ../../main.css)
                                # TODO: won't work if html contains filenames in plain text
                                # TODO: won't work if files contain absolute paths to other domains
                                line = line.replace(asset, self._assets_map[asset]['new_filename'])
                            f_dst.write(line)

            else:
                # no rewriting necessary, just copy the file
                logger.debug("Writing file to {0}".format(dest))
                copyfile(src, dest)

        logger.debug('Finished writing files')

    def _upload_to_bucket(self):
        logger.debug('Uploading to bucket')

        try:
            s3 = connect_s3()
            bucket = s3.get_bucket(self._destination_bucket)

            to_be_deleted = [l.key for l in bucket.list()]

            for dirpath, dirnames, fnames in os.walk(self._destination_dir):

                for f in fnames:
                    abspath = os.path.join(dirpath, f)
                    relpath = os.path.relpath(abspath, self._destination_dir)

                    # do not delete this file
                    to_be_deleted.remove(relpath)

                    # check if file should be cached / reuploaded
                    is_asset = os.path.splitext(f)[1] in self._assets_ext


                    k = bucket.get_key(relpath)
                    if k == None or not is_asset:
                        # asset doesn't exist or file is not an asset and should be uploaded anyway

                        k = Key(bucket)
                        k.key = relpath

                        headers = {}
                        if is_asset:
                            # set infinite headers
                            headers['Cache-Control'] = "public, max-age=31556926"
                        else:
                            # set no-cache headers
                            headers['Cache-Control'] = "no-cache, max-age=0"
                        logger.debug("Uploading file {0} to {1}".format(relpath, self._destination_bucket))
                        k.set_contents_from_filename(abspath, replace=True, headers=headers)

            # remove files not currently touched
            for del_file in to_be_deleted:
                logger.debug("Deleting key {0} from {1}".format(del_file, self._destination_bucket))
            bucket.delete_keys(to_be_deleted)

        except (BotoClientError, BotoServerError) as e:
            raise OptimizerError("Error uploading to S3")

        logger.debug('Finished uploading to bucket')



    def run(self):
        logger.debug('Running optimize')

        self._index_source_dir()
        self._calculate_fingerprints()
        self._write_dirs()
        self._write_files()
        self._upload_to_bucket()

        logger.debug('Finished running optimize')


def main():

    # init logger
    global logger
    logger = logging.getLogger('s3-site-cache-optimizer')
    ch = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # parse arguments
    parser = argparse.ArgumentParser(prog='sifaka', description='Run Appstrakt commands')
    parser.add_argument('--debug', action='store_true', help='Enable debug output')
    parser.add_argument('--version', action='version', version='%(prog)s ' + str(require("s3-site-cache-optimizer")[0].version))
    parser.add_argument("source_dir")
    parser.add_argument("destination_bucket")
    parser.add_argument('--exclude', nargs='+')

    try:
        args = parser.parse_args()
    except argparse.ArgumentTypeError as e:
        logger.error(e)
        exit(1)

    # set logging level
    if args.debug:
        logger.setLevel(logging.DEBUG)

    try:
        Optimizer(args.source_dir, args.destination_bucket, exclude=args.exclude).run()
    except Exception as e:
        logger.error(e)
        exit(1)
