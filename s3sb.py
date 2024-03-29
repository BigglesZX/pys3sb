'''
pys3sb core file

Reads backup tasks from the config file and executes them with the help of boto.

Also requires mysqldump and gzip in the local environment.

Usage: python pys3sb [--daily | --weekly | --monthly] [--only <taskname>]
'''


import os
os.umask(0o077)

import boto3
import config
import sys
import time
from datetime import datetime
from getopt import getopt, GetoptError


''' 0. Some internal config '''
START_TIME = datetime.now()
MODE = False
SINGLE_TASK = False
AWS_KEY_LENGTH = 20
AWS_SECRET_KEY_LENGTH = 40
TMP_DIR = '.pys3sb'
TMP_DIR_PERMISSIONS = 0o0700

''' 1. Some helper functions '''
def validate_task(task):
    ''' Check a task definition for basic validity. '''
    if ('name' in task and
        'friendly_name' in task and
        'frequency' in task and
        's3_directory_name' in task and
            ('database' in task or 'files' in task)):
        return True
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
        opts, args = getopt(sys.argv[1:], '', ['daily', 'weekly', 'monthly', 'test', 'only='])
        if opts:
            SINGLE_TASK = False
            for o, a in opts:
                if o == '--daily':
                    MODE = 'daily'
                elif o == '--weekly':
                    MODE = 'weekly'
                elif o == '--monthly':
                    MODE = 'monthly'
                elif o == '--test':
                    MODE = 'test'
                elif o == '--only':
                    SINGLE_TASK = a
        if not MODE:
            raise GetoptError('')
    except GetoptError:
        print("No frequency option specified.")
        print("Usage: python pys3sb [--daily | --weekly | --monthly] [--only <taskname>]")
        sys.exit(1)

    print("Starting pys3sb in %s mode..." % MODE)


    ''' 2. Sanity checks '''
    if not config.AWS_KEY:
        print("Error: AWS_KEY is not defined in your config file.")
        sys.exit(1)
    if len(config.AWS_KEY) != AWS_KEY_LENGTH:
        print("Warning: AWS_KEY doesn't match the expected length of %s chars." % AWS_KEY_LENGTH)

    if not config.AWS_SECRET_KEY:
        print("Error: AWS_SECRET_KEY is not defined in your config file.")
        sys.exit(1)
    if len(config.AWS_SECRET_KEY) != AWS_SECRET_KEY_LENGTH:
        print("Warning: AWS_SECRET_KEY doesn't match the expected length of %s chars." % AWS_SECRET_KEY_LENGTH)

    if not config.S3_BUCKET:
        print("Error: S3_BUCKET is not defined in your config file.")
        sys.exit(1)

    if not config.TASKS:
        print("Error: no TASKS defined in your config file.")
        sys.exit(1)

    if not os.path.exists(TMP_DIR):
        try:
            os.makedirs(TMP_DIR)
            os.chmod(TMP_DIR, TMP_DIR_PERMISSIONS)
        except OSError:
            print("Couldn't create temporary working directory %s, do we have write permission?")
            sys.exit(1)

    s3_client = boto3.client(
        's3',
        aws_access_key_id=config.AWS_KEY,
        aws_secret_access_key=config.AWS_SECRET_KEY
    )


    ''' 3. Process tasks '''
    task_count = 0
    for task in config.TASKS:
        if MODE == 'test':
            if validate_task(task):
                print("Task '%s' tested OK" % task['friendly_name'])
            else:
                print("Task '%s' failed testing" % task['friendly_name'])
            continue


        print("---")
        print("Running task '%s'..." % task['friendly_name'])

        if not validate_task(task):
            print("Error: task failed validation - please check it against the sample config file to ensure all required fields are present.")
            sys.exit(1)
        if task['frequency'] != MODE:
            print("Skipping task: frequency %s" % task['frequency'])
            continue
        if SINGLE_TASK and task['name'] != SINGLE_TASK:
            print("Skipping task: single task mode specified.")
            continue
        task_count = task_count + 1
        timestamp = datetime.now().strftime('%Y%m%d.%H%M%S')

        if 'database' in task:
            if not ('hostname' in task['database'] and
                    'username' in task['database'] and
                    'password' in task['database'] and
                    'name' in task['database']):
                print("Error: missing some database details, please check your config file.")
                sys.exit(1)

            filename = '%s.db.%s.sql.gz' % (task['name'], timestamp)
            filepath = os.path.join(TMP_DIR, filename)
            if os.path.exists(filepath):
                print("Error: file already exists at %s, did a previous operation fail?" % filepath)
                sys.exit(1)
            print("Dumping database...", end='')
            os.system('mysqldump -h %s -u %s -p%s --no-tablespaces %s | gzip > %s' % (task['database']['hostname'], task['database']['username'], task['database']['password'], task['database']['name'], filepath))
            print("done.")
            time.sleep(1)

            print("Uploading database dump...", end='')
            object_name = '%s/%s' % (task['s3_directory_name'], filename)
            s3_client.upload_file(filepath, config.S3_BUCKET, object_name)
            print("done, %s uploaded." % readable_size(os.path.getsize(filepath)))

            os.remove(filepath)

        if 'files' in task:
            if 'path' not in task['files']:
                print("Error: missing path to site files, please check your config file.")
                sys.exit(1)

            filename = '%s.files.%s.tar.gz' % (task['name'], timestamp)
            filepath = os.path.join(TMP_DIR, filename)
            if os.path.exists(filepath):
                print("Error: file already exists at %s, did a previous operation fail?" % filepath)
                sys.exit(1)
            exclusions = ''
            if 'exclude' in task['files'] and task['files']['exclude']:
                exclusions = '--exclude={'
                for expath in task['files']['exclude']:
                    exclusions = '%s"%s",' % (exclusions, expath)
                exclusions.rstrip(',')
                exclusions = '%s}' % exclusions
                print("Archiving site (with exclusions)...", end='')
            else:
                print("Archiving site...", end='')

            os.system('tar -czf %s %s %s' % (filepath, exclusions, task['files']['path']))
            print("done.")
            time.sleep(1)

            print("Uploading site archive...", end='')
            object_name = '%s/%s' % (task['s3_directory_name'], filename)
            s3_client.upload_file(filepath, config.S3_BUCKET, object_name)
            print("done, %s uploaded." % readable_size(os.path.getsize(filepath)))

            os.remove(filepath)

    print("---")
    delta = datetime.now() - START_TIME
    print("%s task(s) completed in %s." % (task_count, readable_secs(delta.seconds)))


if __name__ == "__main__":
    main()
