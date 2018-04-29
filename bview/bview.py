#!/usr/bin/env python

#
# JMS need to add docs and explanation here
#

import os
import json
import shutil
import argparse
import subprocess

#====================================================================

metadata_dirname = '.bview'
metadata_filename = 'data.json'
html_filename = 'bview.html'

dirs_to_skip = [ metadata_dirname, '.git', '.svn', '.Trash', '.TemporaryItems'
                 '.ssh', '.subversion', '.gnupg', '.bash_sessions',
                 '.cache', '.credentials', '.cups', '.dropbox' ]

files_to_skip = [ '.DS_Store', html_filename ]

#====================================================================

def parse_cli():
    parser = argparse.ArgumentParser(description='BView')
    parser.add_argument('--dir', default='.',
                        help='Directory tree to process')
    parser.add_argument('--verbose', action='store_true',
                        default=True,
                        help='Verbose output')
    parser.add_argument('--debug', action='store_true',
                        default=False,
                        help='Debug output')

    args = parser.parse_args()

    if args.debug:
        args.verbose = True

    dir = args.dir
    if not os.path.isdir(dir):
        print("Must supply a directory ('{dir}' is not a directory)"
              .format(dir=dir))
        exit(1)

    return args

#====================================================================

def verbose(kwargs):
    global args
    if args.verbose:
        print(kwargs)

def debug(kwargs):
    global args
    if args.debug:
        print(kwargs)

#====================================================================

def write_metadata(datafile, subdirs, files):
    data = {
        'dirs'  : subdirs,
        'files' : files,
    }

    with open(datafile, 'w') as f:
        json.dump(data, f)

def read_metadata(datafile):
    try:
        with open(datafile, 'r') as f:
            return json.load(f)
    except:
        return {
            'dirs'  : list(),
            'files' : dict(),
        }

#====================================================================

def write_index(dirname, index_filename, subdirs, files,
                generate_parent_link=True):
    def _entry(type, file, file_href=None, thumbnail=None):
        str = "<tr>\n<td>{type}</td>\n".format(type=type)

        str += "<td>"
        if file_href:
            str += '<a href="file://{af}">{f}</a>'.format(af=file_href, f=file)
        else:
            str += file
        str += '</td>\n'

        str += "<td>"
        if thumbnail and os.path.exists(thumbnail):
            str += '<img align="center" valign="center" src="file://{thumb}">'.format(thumb=thumbnail)
        str += '</td>\n\n'

        return str

    #----------------------------------------------------------------

    str = '''<html>
<head>
<title>Listing of {d}</title>
</head>
<body>
<p>Index of files for directory: {d}</p>

<style>
table, th, td {{
  border: 1px solid black;
  padding: 15px
}}
</style>

<table>\n'''.format(d=dirname)

    if generate_parent_link:
        parent_bview = '{d}/../bview.html'.format(d=dirname)
        str += _entry(type='Folder',
                      file='Parent directory',
                      file_href=parent_bview)

    for d in subdirs:
        str += _entry(type='Folder',
                      file=d,
                      file_href='{d}/{hf}'.format(d=d, hf=html_filename))

    for ff in files:
        str += _entry(type='File',
                      file=ff,
                      file_href=files[ff]['abs_filename'],
                      thumbnail=files[ff]['thumbname'])

    str += '</body>\n'
    str += '</html>\n'

    with open(index_filename, 'w') as f:
        f.write(str)

#====================================================================

def process_metadata(datafile, metadata, subdirs, files):

    def _dir_changes(data, subdirs):
        # If the lengths are different, then *something* is different
        # (it doesn't really matter what).
        data_dirs_len = 0
        if data and 'dirs' in data:
            data_dirs_len = len(data['dirs'])
        if len(subdirs) != data_dirs_len:
            debug("   Current dir and previous dir metadata different lengths -- changed")
            return True
        if len(subdirs) == 0:
            debug("   Current/previous dir metadata empty -- no change")
            return False

        # If we have a subdir that isn't in the previous metadata,
        # then that's a different.
        for d in subdirs:
            if d not in data['dirs']:
                debug("   Current dir metadata has new entry -- changed")
                return True

        # If the previous metadata has a subdir that is not in the
        # current metadata, then that's different.
        for d in data['dirs']:
            if d not in subdirs:
                debug("   Current dir metadata missing an entry -- changed")
                return True

        # Everything was the same.
        debug("   Current/previous dir metadata identical -- no change")
        return False

    #----------------------------------------------------------------

    def _file_changes(data, files):
        # If the lengths are different, then *something* is different
        # (it doesn't really matter what).
        data_files_len = 0
        if data and 'files' in data:
            data_files_len = len(data['files'])
        if len(files) != data_files_len:
            debug("   Current file and previous file metadata different lengths -- changed")
            return True
        if len(files) == 0:
            debug("   Current/previous file metadata empty -- no change")
            return False

        for f in files:
            # If we have a file that isn't in the previous metadata,
            # then that's a different.
            if f not in data['files']:
                debug("   Current file metadata has new entry -- changed")
                return True

            # If we just generated a thumbnail, that means the file
            # changed.  So that's different.
            if ('thumb_exists' in files[f] and
                files[f]['thumb_stat_mtime'] > data['files'][f]['stat_mtime']):
                debug("   Current file metadata has newly-generated thumbnail -- changed")
                return True

            # If the previous metadata has a file that is not in the
            # current metadata, then that's different.
            for f in data['files']:
                if f not in files:
                    debug("   Current file metadata missing an entry -- changed")
                    return True

        # Everything was the same.
        debug("   Current/previous file metadata identical -- no change")
        return False

    #----------------------------------------------------------------

    changes_since_last_time = ((len(metadata['files']) == 0 and
                                len(metadata['dirs']) == 0) or
                               _dir_changes(metadata, subdirs) or
                               _file_changes(metadata, files))

    # If there are changes since last time, write out a new datafile
    if changes_since_last_time:
        write_metadata(datafile, subdirs, files)

    return changes_since_last_time

#====================================================================

def process_file(dirname, thumb_dir, filedata, metadata):
    debug("- Processing file {f}".format(f=filedata['filename']))

    need_to_write_thumb = False

    thumbname = "{d}/{f}.png".format(d=thumb_dir, f=filedata['filename'])
    filedata['thumbname'] = thumbname

    if os.path.exists(thumbname):
        # If the file is newer than its thumbmail, we need to
        # regenerate the thumbnail
        fs = os.stat(thumbname)
        if fs.st_mtime < filedata['stat_mtime']:
            need_to_write_thumb = True
        else:
            filedata['thumb_exists']     = True
            filedata['thumb_stat_mtime'] = fs.st_mtime
    else:
        # If the thumbnail does not exist, check the metadata to see
        # if we tried to generate the thumbnail last time (i.e., if we
        # determined last time that qlmanage doesn't generate
        # thumbnails for this file type).
        f = filedata['filename']
        if (f in metadata and
            metadata[f]['thumb_generated'] and
            metadata[f]['thumb_exists']):
            need_to_write_thumb = True

    # If we need to write the thumbnail, do it
    if need_to_write_thumb:
        fd = None
        global args
        if not args.debug:
            fd = open('/dev/null', 'w')

        subargs = ['qlmanage', '-t', filedata['abs_filename'], '-o', thumb_dir]
        debug("   Regenerating: {args}".format(args=subargs))
        ret = subprocess.call(subargs, stdout=fd, stderr=fd)

        filedata['thumb_generated'] = True

        # qlmanage does not make thumbnails for all file types.  See
        # if a thumbnail was actually created.
        try:
            fs = os.stat(thumbname)
            filedata['thumb_exists']     = True
            filedata['thumb_stat_mtime'] = fs.st_mtime
        except:
            filedata['thumb_exists']     = False
            filedata['thumb_stat_mtime'] = 0

    return filedata

#====================================================================

def process_dir_work(contents, dirname, topdir=False):
    files   = dict()
    subdirs = list()

    # Check all the contents of this dir
    debug("   Examining contents of directory {d}".format(d=dirname))
    for f in sorted(os.listdir(dirname)):
        thisname = "{d}/{f}".format(d=dirname, f=f)

        if os.path.isdir(thisname):
            # Skip some specific directories
            if f in dirs_to_skip:
                debug("      NOT adding subdirectory {d}".format(d=f))
            else:
                debug("      Adding subdirectory {d}".format(d=f))
                subdirs.append(thisname)
        else:
            if f in files_to_skip:
                debug("      NOT adding file {f}".format(f=f))
            elif os.path.exists(thisname):
                debug("      Adding file {f}".format(f=f))
                files[f] = {
                    'filename'     : f,
                    'abs_filename' : thisname,
                    'stat_mtime'   : os.stat(thisname).st_mtime
                }

    bview_dir = "{d}/.bview".format(d=dirname)
    if not os.path.exists(bview_dir):
        os.makedirs(bview_dir)
    mfile = "{d}/{md}".format(d=bview_dir, md=metadata_filename)
    metadata = read_metadata(mfile)

    # Process each subdirectory
    for d in sorted(subdirs):
        process_dir(d)

    # Process each file
    if len(files) > 0:
        # Make a .bview subddirectory if it doesn't already exist
        thumb_dir = "{d}/thumbs".format(d=bview_dir)
        if not os.path.exists(thumb_dir):
            os.makedirs(thumb_dir)

        for f in sorted(files):
            files[f] = process_file(dirname, thumb_dir, files[f], metadata)

    # Process the metadata for this directory
    need_to_write_index = process_metadata(mfile, metadata, subdirs, files)

    # Write out the index for this directory
    if need_to_write_index:
        index_filename = "{d}/{hf}".format(d=dirname, hf=html_filename)
        write_index(dirname, index_filename, subdirs, files,
                    generate_parent_link=not topdir)

def process_dir(dirname, topdir=False):
    verbose("Processing dir {d}".format(d=dirname))

    # If there is anything in this directory, process it.
    contents = os.listdir(dirname)
    if len(contents) == 0:
        debug("   Directory {d} is empty -- skipping".format(d=dirname))
        return False

    if len(contents) == 1 and contents[0] == ".bview":
        debug("   Directory {d} is now empty -- skipping".format(d=dirname))
        shutil.rmtree("{d}/.bview".format(d=dirname))
        return False

    else:
        # There's at least one non-.bview entry in this directory.  So
        # process it.
        process_dir_work(contents, dirname, topdir)

#====================================================================

# Main

args = parse_cli()
process_dir(os.path.realpath(args.dir), topdir=True)
