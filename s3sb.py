'''
pys3sb core file

Reads backup tasks from the config file and executes them with the help of boto.

Also requires mysqldump and gzip in the local environment.

Usage: python pys3sb [--daily | --weekly]
'''


import os
os.umask(077)

import boto
import config
import sys
import time
from boto.s3.key import Key
from boto.s3.bucket import Bucket
from datetime import datetime
from getopt import getopt, GetoptError


''' 0. Some internal config '''
START_TIME = datetime.now()
MODE = False
AWS_KEY_LENGTH = 20
AWS_SECRET_KEY_LENGTH = 40
TMP_DIR = '.pys3sb'
TMP_DIR_PERMISSIONS = 0700

''' 1. Some helper functions '''
def validate_task(task):
    ''' Check a task definition for basic validity. '''
    try:
        if (task['name'] and
            task['friendly_name'] and
            task['frequency'] and
            task['s3_directory_name'] and
            (task['database'] or task['files'])):
            return True
    except KeyError:
        pass
    return False

def readable_size(size):
    ''' Convert a byte count into a sensible larger unit. '''    
    suffixes = ['KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB']
    if size == 0:
        return '0B'
    for suffix in suffixes:
        size /= 1024
        if size < 1024:
            return '{0:.1f}{1}'.format(size, suffix)
    return 'N/A'


def readable_secs(secs):
    ''' Convert a number of seconds into a human-readable format. '''
    if secs >= 60:
        delta_readable = '%s min' % (secs / 60)
        if secs % 60 > 0:
            delta_readable = '%s %s sec' % (delta_readable, secs % 60)
    else:
        delta_readable = '%s sec' % secs
    return delta_readable

    
def main():
    try:
        opts, args = getopt(sys.argv[1:], '', ['daily', 'weekly'])
        if opts:
            for o, a in opts:
                if o == '--daily':
                    MODE = 'daily'
                elif o == '--weekly':
                    MODE = 'weekly'
        if not MODE:
            raise GetoptError('')
    except GetoptError:
        print "No frequency option specified."
        print "Usage: python pys3sb [--daily | --weekly]"
        sys.exit(1)
    
    print "Starting pys3sb in %s mode..." % MODE
    print "---"
    

    ''' 2. Sanity checks '''
    if not config.AWS_KEY:
        print "Error: AWS_KEY is not defined in your config file."
        sys.exit(1)
    if len(config.AWS_KEY) != AWS_KEY_LENGTH:
        print "Warning: AWS_KEY doesn't match the expected length of %s chars." % AWS_KEY_LENGTH
    
    if not config.AWS_SECRET_KEY:
        print "Error: AWS_SECRET_KEY is not defined in your config file."
        sys.exit(1)
    if len(config.AWS_SECRET_KEY) != AWS_SECRET_KEY_LENGTH:
        print "Warning: AWS_SECRET_KEY doesn't match the expected length of %s chars." % AWS_SECRET_KEY_LENGTH
    
    if not config.S3_BUCKET:
        print "Error: S3_BUCKET is not defined in your config file."
        sys.exit(1)
    
    if not config.TASKS:
        print "Error: no TASKS defined in your config file."
        sys.exit(1)
    
    if not os.path.exists(TMP_DIR):
        try:
            os.makedirs(TMP_DIR)
            os.chmod(TMP_DIR, TMP_DIR_PERMISSIONS)
        except OSError:
            print "Couldn't create temporary working directory %s, do we have write permission?"
            sys.exit(1)
        
    s3_connection = boto.connect_s3(config.AWS_KEY, config.AWS_SECRET_KEY)
    bucket = Bucket(s3_connection, config.S3_BUCKET)


    ''' 3. Process tasks '''
    task_count = 0
    for task in config.TASKS:
        print "Running task '%s'..." % task['friendly_name']
    
        if not validate_task(task):
            print "Error: task failed validation - please check it against the sample config file to ensure all required fields are present."
            sys.exit(1)
        if task['frequency'] != MODE:
            print "Skipping task: frequency %s" % task['frequency']
            continue
        task_count = task_count + 1
        timestamp = datetime.now().strftime('%Y%m%d.%H%M%S')
    
        try:
            if task['database']:
                try:
                    if not (task['database']['hostname'] and
                            task['database']['username'] and
                            task['database']['password'] and
                            task['database']['name']):
                        raise KeyError
                except KeyError:
                    print "Error: missing some database details, please check your config file."
                    sys.exit(1)
                    
                filename = '%s.db.%s.sql.gz' % (task['name'], timestamp)
                filepath = os.path.join(TMP_DIR, filename)
                if os.path.exists(filepath):
                    print "Error: file already exists at %s, did a previous operation fail?" % filepath
                    sys.exit(1)
                print "Dumping database...",
                os.system('mysqldump -h %s -u %s -p%s --opt %s | gzip > %s' % (task['database']['hostname'], task['database']['username'], task['database']['password'], task['database']['name'], filepath))
                print "done."
                time.sleep(1)
        
                print "Uploading database dump...",
                s3_obj = Key(bucket)
                s3_obj.key = '%s/%s' % (task['s3_directory_name'], filename)
                s3_obj.set_contents_from_filename(filepath)
                print "done, %s uploaded." % readable_size(os.path.getsize(filepath))
        
                os.remove(filepath)
        except KeyError:
            pass
        
        try:
            if task['files']:
                try:
                    if not task['files']['path']:
                        raise KeyError
                except KeyError:
                    print "Error: missing path to site files, please check your config file."
                    sys.exit(1)
        
                filename = '%s.files.%s.tar.gz' % (task['name'], timestamp)
                filepath = os.path.join(TMP_DIR, filename)
                if os.path.exists(filepath):
                    print "Error: file already exists at %s, did a previous operation fail?" % filepath
                    sys.exit(1)
                exclusions = ''
                if task['files']['exclude']:
                    exclusions = '--exclude={'
                    for expath in task['files']['exclude']:
                        exclusions = '%s"%s",' % (exclusions, expath)
                    exclusions.rstrip(',')
                    exclusions = '%s}' % exclusions
                    print "Archiving site...",
                else:
                    print "Archiving site (with exclusions)...",
                os.system('tar -czf %s %s %s' % (filepath, exclusions, task['files']['path']))
                print "done."
                time.sleep(1)
        
                print "Uploading site archive...",
                s3_obj = Key(bucket)
                s3_obj.key = '%s/%s' % (task['s3_directory_name'], filename)
                s3_obj.set_contents_from_filename(filepath)
                print "done, %s uploaded." % readable_size(os.path.getsize(filepath))
        
                os.remove(filepath)
        except KeyError:
            pass
    
        print "---"

    delta = datetime.now() - START_TIME
    print "%s task(s) completed in %s." % (task_count, readable_secs(delta.seconds))


if __name__ == "__main__":
    main()